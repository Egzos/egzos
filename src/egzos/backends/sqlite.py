# Copyright 2026 Ali Sasanian
# SPDX-License-Identifier: LicenseRef-PolyForm-Strict-1.0.0
"""sqlite backend — what `pip install` gives everyone (v0.5 §E). JSON documents in typed rows."""

from __future__ import annotations

import json
import sqlite3
from collections.abc import Iterable, Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Any

from egzos._types import AgentRegistration, ConfirmChallenge, ThrottleSurface, UserGrant
from egzos.backends.base import ChainConflict
from egzos.model import ContextItem, Node, Token

_SCHEMA = """
CREATE TABLE IF NOT EXISTS nodes (
  id TEXT PRIMARY KEY, type TEXT NOT NULL, name TEXT NOT NULL, parent TEXT, doc TEXT NOT NULL);
CREATE INDEX IF NOT EXISTS nodes_parent ON nodes(parent);
CREATE TABLE IF NOT EXISTS items (
  id TEXT PRIMARY KEY, kind TEXT NOT NULL, scope TEXT NOT NULL, key TEXT, status TEXT NOT NULL,
  tombstoned INTEGER NOT NULL DEFAULT 0, created_at TEXT NOT NULL, doc TEXT NOT NULL);
CREATE INDEX IF NOT EXISTS items_scope ON items(scope);
CREATE INDEX IF NOT EXISTS items_kind_key ON items(kind, key);
CREATE TABLE IF NOT EXISTS audit (
  seq INTEGER PRIMARY KEY AUTOINCREMENT, ts TEXT NOT NULL, hash TEXT NOT NULL UNIQUE,
  prev_hash TEXT NOT NULL, doc TEXT NOT NULL);
-- One successor per entry: two writers (the CLI and `serve --mcp` are separate processes) that read
-- the same head cannot both append after it; the loser re-reads and re-chains (Ledger.append).
CREATE UNIQUE INDEX IF NOT EXISTS audit_prev_hash ON audit(prev_hash);
CREATE TABLE IF NOT EXISTS tokens (id TEXT PRIMARY KEY, doc TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS proposals (id TEXT PRIMARY KEY, status TEXT NOT NULL, doc TEXT NOT NULL);
-- append-only is a PROPERTY of the design (a3-ledger charter): no update or delete path exists.
CREATE TRIGGER IF NOT EXISTS audit_no_update BEFORE UPDATE ON audit
  BEGIN SELECT RAISE(ABORT, 'audit is append-only'); END;
CREATE TRIGGER IF NOT EXISTS audit_no_delete BEFORE DELETE ON audit
  BEGIN SELECT RAISE(ABORT, 'audit is append-only'); END;
-- The retired authorization server's tables (identity.md §9): never written, since the AS was
-- never mounted, and dropped from a file made before their removal.
DROP TABLE IF EXISTS as_sessions;
DROP TABLE IF EXISTS as_throttle;
DROP TABLE IF EXISTS as_clients;
DROP TABLE IF EXISTS as_codes;
DROP TABLE IF EXISTS as_decided;
DROP TABLE IF EXISTS as_devices;
DROP TABLE IF EXISTS as_refresh;
-- ThrottleState (storage.md §3.1): the door's throttle counters, on this same substrate and
-- connection as ContainerState, never process memory, so a restart lifts no throttle.
CREATE TABLE IF NOT EXISTS throttle (
  surface TEXT NOT NULL, bucket_key TEXT NOT NULL, window_key TEXT NOT NULL,
  count INTEGER NOT NULL, PRIMARY KEY (surface, bucket_key, window_key));
-- IdentityState and ConfigState (storage.md §3.2): identity.md §4's grants and registrations,
-- and container.md §8's settings. No column holds a credential: a grant names a provider user id.
CREATE TABLE IF NOT EXISTS user_grants (sub TEXT PRIMARY KEY, doc TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS agent_registrations (
  client_id TEXT NOT NULL, sub TEXT NOT NULL, doc TEXT NOT NULL, PRIMARY KEY (client_id, sub));
CREATE TABLE IF NOT EXISTS config (key TEXT PRIMARY KEY, value TEXT NOT NULL);
-- ConfirmState (storage.md §3.3): the confirm's challenges, spent once.
CREATE TABLE IF NOT EXISTS challenges (
  id TEXT PRIMARY KEY, spent INTEGER NOT NULL DEFAULT 0, expires_at TEXT NOT NULL,
  doc TEXT NOT NULL);
CREATE INDEX IF NOT EXISTS challenges_expiry ON challenges(expires_at);
"""


class SqliteBackend:
    def __init__(self, path: Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        # One connection, shared: safe while every caller runs on one thread at a time — the CLI,
        # and the lifeboat, whose handlers are all `async def` on the event loop (its test client's
        # portal included). A sync handler would run in Starlette's threadpool; add a lock here
        # before writing one. Writers in other processes are serialised by sqlite itself, and the
        # chain by its unique prev_hash.
        self.db = sqlite3.connect(str(self.path), check_same_thread=False, timeout=10)
        self.db.execute("PRAGMA journal_mode=WAL")
        self.db.execute("PRAGMA foreign_keys=ON")
        self.db.executescript(_SCHEMA)
        self._depth = 0  # > 0 inside atomic(): writes wait for its one commit

    @contextmanager
    def atomic(self):
        """Every write inside lands together or not at all. BEGIN IMMEDIATE takes the write lock
        up front, so no other process can move the chain head mid-act."""
        if self._depth == 0 and not self.db.in_transaction:
            self.db.execute("BEGIN IMMEDIATE")
        self._depth += 1
        try:
            yield
        except BaseException:
            self._depth -= 1
            if self._depth == 0:
                self.db.rollback()
            raise
        self._depth -= 1
        if self._depth == 0:
            self.db.commit()

    def _commit(self) -> None:
        if self._depth == 0:
            self.db.commit()

    # -- nodes --------------------------------------------------------------------------
    def put_node(self, node: Node) -> None:
        self.db.execute(
            "INSERT OR REPLACE INTO nodes(id,type,name,parent,doc) VALUES(?,?,?,?,?)",
            (node.id, node.type, node.name, node.parent, json.dumps(node.to_dict())),
        )
        self._commit()

    def get_node(self, node_id: str) -> Node | None:
        row = self.db.execute("SELECT doc FROM nodes WHERE id=?", (node_id,)).fetchone()
        return Node.from_dict(json.loads(row[0])) if row else None

    def list_nodes(self, parent: str | None = None, type: str | None = None) -> list[Node]:
        sql, args = "SELECT doc FROM nodes WHERE 1=1", []
        if parent is not None:
            sql += " AND parent=?"
            args.append(parent)
        if type is not None:
            sql += " AND type=?"
            args.append(type)
        return [
            Node.from_dict(json.loads(r[0])) for r in self.db.execute(sql + " ORDER BY rowid", args)
        ]

    def find_root(self, type: str) -> Node | None:
        row = self.db.execute(
            "SELECT doc FROM nodes WHERE type=? AND parent IS NULL", (type,)
        ).fetchone()
        return Node.from_dict(json.loads(row[0])) if row else None

    # -- items --------------------------------------------------------------------------
    def put(self, item: ContextItem) -> None:
        self.db.execute(
            "INSERT OR REPLACE INTO items(id,kind,scope,key,status,tombstoned,created_at,doc) "
            "VALUES(?,?,?,?,?,?,?,?)",
            (
                item.id,
                item.kind,
                item.scope,
                item.key,
                item.status,
                1 if item.lifecycle.get("tombstoned") else 0,
                item.lifecycle.get("created_at", ""),
                json.dumps(item.to_dict()),
            ),
        )
        self._commit()

    def get(self, item_id: str) -> ContextItem | None:
        row = self.db.execute(
            "SELECT doc FROM items WHERE id=? AND tombstoned=0", (item_id,)
        ).fetchone()
        return ContextItem.from_dict(json.loads(row[0])) if row else None

    def query(
        self,
        scopes: Iterable[str],
        *,
        kinds: Iterable[str] | None = None,
        key: str | None = None,
        statuses: Iterable[str] | None = None,
        text: str | None = None,
        include_tombstoned: bool = False,
    ) -> list[ContextItem]:
        scopes = list(scopes)
        if not scopes:
            return []
        sql = f"SELECT doc FROM items WHERE scope IN ({','.join('?' * len(scopes))})"
        args: list[Any] = list(scopes)
        if not include_tombstoned:
            sql += " AND tombstoned=0"
        if kinds:
            kinds = list(kinds)
            sql += f" AND kind IN ({','.join('?' * len(kinds))})"
            args += kinds
        if key is not None:
            sql += " AND key=?"
            args.append(key)
        if statuses:
            statuses = list(statuses)
            sql += f" AND status IN ({','.join('?' * len(statuses))})"
            args += statuses
        if text:
            sql += " AND doc LIKE ?"
            args.append(f"%{text}%")  # SKELETON: substring; embeddings later
        sql += " ORDER BY created_at DESC"
        return [ContextItem.from_dict(json.loads(r[0])) for r in self.db.execute(sql, args)]

    def tombstone(self, item_id: str) -> bool:
        item = self.get(item_id)
        if not item:
            return False
        item.lifecycle["tombstoned"] = True
        self.put(item)
        return True

    # -- audit --------------------------------------------------------------------------
    def audit_append(self, entry: dict[str, Any]) -> dict[str, Any]:
        try:
            cur = self.db.execute(
                "INSERT INTO audit(ts,hash,prev_hash,doc) VALUES(?,?,?,?)",
                (entry["ts"], entry["hash"], entry["prev_hash"], json.dumps(entry)),
            )
        except sqlite3.IntegrityError as e:
            if self._depth == 0:  # inside atomic() the whole act unwinds, not just this entry
                self.db.rollback()
            raise ChainConflict(str(e)) from e
        self._commit()
        return {**entry, "seq": cur.lastrowid}

    def audit_last(self) -> dict[str, Any] | None:
        row = self.db.execute("SELECT seq, doc FROM audit ORDER BY seq DESC LIMIT 1").fetchone()
        return {**json.loads(row[1]), "seq": row[0]} if row else None

    def audit_iter(self) -> Iterator[dict[str, Any]]:
        for seq, doc in self.db.execute("SELECT seq, doc FROM audit ORDER BY seq ASC"):
            yield {**json.loads(doc), "seq": seq}

    def audit_tail(self, n: int) -> list[dict[str, Any]]:
        rows = self.db.execute(
            "SELECT seq, doc FROM audit ORDER BY seq DESC LIMIT ?", (n,)
        ).fetchall()
        return [{**json.loads(doc), "seq": seq} for seq, doc in reversed(rows)]

    # -- tokens -------------------------------------------------------------------------
    def put_token(self, token: Token) -> None:
        self.db.execute(
            "INSERT OR REPLACE INTO tokens(id,doc) VALUES(?,?)",
            (token.id, json.dumps(token.to_dict(with_secret_hash=True))),
        )
        self._commit()

    def get_token(self, token_id: str) -> Token | None:
        row = self.db.execute("SELECT doc FROM tokens WHERE id=?", (token_id,)).fetchone()
        return Token.from_dict(json.loads(row[0])) if row else None

    def list_tokens(self) -> list[Token]:
        return [
            Token.from_dict(json.loads(r[0]))
            for r in self.db.execute("SELECT doc FROM tokens ORDER BY rowid")
        ]

    # -- proposals ----------------------------------------------------------------------
    def put_proposal(self, proposal: dict[str, Any]) -> None:
        self.db.execute(
            "INSERT OR REPLACE INTO proposals(id,status,doc) VALUES(?,?,?)",
            (proposal["id"], proposal["status"], json.dumps(proposal)),
        )
        self._commit()

    def get_proposal(self, proposal_id: str) -> dict[str, Any] | None:
        row = self.db.execute("SELECT doc FROM proposals WHERE id=?", (proposal_id,)).fetchone()
        return json.loads(row[0]) if row else None

    def list_proposals(self, status: str | None = None) -> list[dict[str, Any]]:
        if status:
            rows = self.db.execute(
                "SELECT doc FROM proposals WHERE status=? ORDER BY rowid", (status,)
            )
        else:
            rows = self.db.execute("SELECT doc FROM proposals ORDER BY rowid")
        return [json.loads(r[0]) for r in rows]

    # -- ThrottleState (storage.md §3.1) ----------------------------------------------------
    # The door's throttle counters, on this file and this connection, never process memory (the
    # Chief on #173, option (A)).
    def throttle_incr(self, surface: ThrottleSurface, bucket_key: str, window_key: str) -> int:
        """Increments and returns the new count, atomically: of two concurrent callers on the
        same key, each observes its own correctly incremented total, never the other's. Names no
        rate and no window length (Trust's, #141); the three keys are compared as opaque values."""
        with self.atomic():
            self.db.execute(
                "INSERT INTO throttle(surface,bucket_key,window_key,count) VALUES(?,?,?,1) "
                "ON CONFLICT(surface,bucket_key,window_key) DO UPDATE SET count=count+1",
                (surface, bucket_key, window_key),
            )
            row = self.db.execute(
                "SELECT count FROM throttle WHERE surface=? AND bucket_key=? AND window_key=?",
                (surface, bucket_key, window_key),
            ).fetchone()
        return row[0]

    def throttle_count(self, surface: ThrottleSurface, bucket_key: str, window_key: str) -> int:
        row = self.db.execute(
            "SELECT count FROM throttle WHERE surface=? AND bucket_key=? AND window_key=?",
            (surface, bucket_key, window_key),
        ).fetchone()
        return row[0] if row else 0

    def throttle_buckets(self, surface: ThrottleSurface, window_key: str) -> list[tuple[str, int]]:
        rows = self.db.execute(
            "SELECT bucket_key, count FROM throttle WHERE surface=? AND window_key=? "
            "ORDER BY bucket_key",
            (surface, window_key),
        )
        return [(k, n) for k, n in rows]

    def throttle_windows(self, surface: ThrottleSurface) -> list[str]:
        rows = self.db.execute(
            "SELECT DISTINCT window_key FROM throttle WHERE surface=? ORDER BY window_key",
            (surface,),
        )
        return [r[0] for r in rows]

    def throttle_forget(self, surface: ThrottleSurface, window_key: str) -> None:
        self.db.execute(
            "DELETE FROM throttle WHERE surface=? AND window_key=?", (surface, window_key)
        )
        self._commit()

    # -- IdentityState (storage.md §3.2) -----------------------------------------------------
    def put_user_grant(self, grant: UserGrant) -> None:
        self.db.execute(
            "INSERT OR REPLACE INTO user_grants(sub,doc) VALUES(?,?)",
            (grant["sub"], json.dumps(grant)),
        )
        self._commit()

    def get_user_grant(self, sub: str) -> UserGrant | None:
        row = self.db.execute("SELECT doc FROM user_grants WHERE sub=?", (sub,)).fetchone()
        return json.loads(row[0]) if row else None

    def list_user_grants(self) -> list[UserGrant]:
        rows = self.db.execute("SELECT doc FROM user_grants ORDER BY rowid")
        return [json.loads(r[0]) for r in rows]

    def put_agent_registration(self, registration: AgentRegistration) -> None:
        self.db.execute(
            "INSERT OR REPLACE INTO agent_registrations(client_id,sub,doc) VALUES(?,?,?)",
            (registration["client_id"], registration["sub"], json.dumps(registration)),
        )
        self._commit()

    def get_agent_registration(self, client_id: str, sub: str) -> AgentRegistration | None:
        row = self.db.execute(
            "SELECT doc FROM agent_registrations WHERE client_id=? AND sub=?", (client_id, sub)
        ).fetchone()
        return json.loads(row[0]) if row else None

    def list_agent_registrations(self, client_id: str | None = None) -> list[AgentRegistration]:
        if client_id is None:
            rows = self.db.execute("SELECT doc FROM agent_registrations ORDER BY rowid")
        else:
            rows = self.db.execute(
                "SELECT doc FROM agent_registrations WHERE client_id=? ORDER BY rowid", (client_id,)
            )
        return [json.loads(r[0]) for r in rows]

    # -- ConfigState (storage.md §3.2) -------------------------------------------------------
    def get_config(self) -> dict[str, Any]:
        return {k: json.loads(v) for k, v in self.db.execute("SELECT key, value FROM config")}

    def put_config(self, key: str, value: Any) -> None:
        self.db.execute(
            "INSERT OR REPLACE INTO config(key,value) VALUES(?,?)", (key, json.dumps(value))
        )
        self._commit()

    # -- ConfirmState (storage.md §3.3) ------------------------------------------------------
    def put_challenge(self, challenge: ConfirmChallenge) -> None:
        self.db.execute(
            "INSERT INTO challenges(id,spent,expires_at,doc) VALUES(?,0,?,?)",
            (challenge["id"], challenge["expires_at"], json.dumps(challenge)),
        )
        self._commit()

    def forget_challenges(self, expired_before: str) -> None:
        self.db.execute("DELETE FROM challenges WHERE expires_at < ?", (expired_before,))
        self._commit()

    def spend_challenge(self, challenge_id: str) -> ConfirmChallenge | None:
        """Mark it spent and return it as it stood: of two concurrent spends, one sees it fresh."""
        with self.atomic():
            row = self.db.execute(
                "SELECT spent, doc FROM challenges WHERE id=?", (challenge_id,)
            ).fetchone()
            if row is None:
                return None
            self.db.execute("UPDATE challenges SET spent=1 WHERE id=?", (challenge_id,))
        return {**json.loads(row[1]), "spent": bool(row[0])}
