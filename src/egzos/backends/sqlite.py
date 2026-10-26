# Copyright 2026 Ali Sasanian
# SPDX-License-Identifier: LicenseRef-PolyForm-Strict-1.0.0
"""sqlite backend — what `pip install` gives everyone (v0.5 §E). JSON documents in typed rows."""

from __future__ import annotations

import json
import sqlite3
from collections.abc import Callable, Iterable, Iterator, Sequence
from contextlib import contextmanager
from pathlib import Path
from typing import Any

from egzos._types import (
    AgentRegistration,
    ConfirmChallenge,
    ConfirmCredential,
    StorageBusy,
    ThrottleSurface,
    UploadRecord,
    UserGrant,
)
from egzos.backends.base import ChainConflict, refuse_nul
from egzos.model import ContextItem, Node, Token

#: How long a writer waits for the container's write lock, in seconds, before it raises
#: `StorageBusy` (storage.md §3.6): postgres's `lock_timeout`.
LOCK_TIMEOUT = 10.0

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
CREATE TABLE IF NOT EXISTS credentials (
  id TEXT PRIMARY KEY, person TEXT NOT NULL, doc TEXT NOT NULL);
CREATE INDEX IF NOT EXISTS credentials_person ON credentials(person);
-- UploadState (storage.md §3.4): rest.md §4.4's uploads, each step spent once.
CREATE TABLE IF NOT EXISTS uploads (
  id TEXT PRIMARY KEY, principal TEXT NOT NULL, bytes_spent INTEGER NOT NULL DEFAULT 0,
  item_spent INTEGER NOT NULL DEFAULT 0, doc TEXT NOT NULL);
CREATE INDEX IF NOT EXISTS uploads_principal ON uploads(principal);
-- GrantState (storage.md §3.5): rest.md §6's spent grants, by the sha256 of their sig.
CREATE TABLE IF NOT EXISTS spent_grants (sig_hash TEXT PRIMARY KEY, expires_at TEXT NOT NULL);
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
        self.db = sqlite3.connect(str(self.path), check_same_thread=False, timeout=LOCK_TIMEOUT)
        self.db.execute("PRAGMA journal_mode=WAL")
        self.db.execute("PRAGMA foreign_keys=ON")
        self.db.executescript(_SCHEMA)
        self._depth = 0  # > 0 inside atomic(): writes wait for its one commit
        self._after: list[Callable[[], object]] = []  # what waits for that commit

    @contextmanager
    def atomic(self):
        """Every write inside lands together or not at all. BEGIN IMMEDIATE takes the write lock
        up front, so no other process can move the chain head mid-act. Not taken within
        `LOCK_TIMEOUT`, it raises `StorageBusy`, and nothing was written (storage.md §3.6)."""
        if self._depth == 0:
            if self.db.in_transaction:
                # Every write here takes this block, so only a caller of `db` leaves one open. Let
                # it go, so the block holds the lock from its start (GHSA-m955-fr24-frwq).
                self.db.rollback()
            try:
                self.db.execute("BEGIN IMMEDIATE")
            except sqlite3.OperationalError as e:
                if e.sqlite_errorcode & 0xFF != sqlite3.SQLITE_BUSY:  # and its extended codes
                    raise
                raise StorageBusy("the container's write lock was not taken in time") from e
        self._depth += 1
        try:
            yield
        except BaseException:
            self._depth -= 1
            if self._depth == 0:
                self._after.clear()  # dropped with the writes it waited for
                self.db.rollback()
            raise
        self._depth -= 1
        if self._depth == 0:
            queued, self._after = self._after, []  # a COMMIT that raises drops them
            self.db.commit()
            for fn in queued:
                fn()

    def after_commit(self, fn: Callable[[], object]) -> None:
        """Run `fn` once the outermost block commits, after the COMMIT and with no block open, in
        the order queued; never if that block rolls back or its COMMIT fails. A nested block joins
        the outer one, and outside any block `fn` runs at once (storage.md §3.6)."""
        if self._depth:
            self._after.append(fn)
        else:
            fn()

    def _write(self, sql: str, args: Sequence[Any] = ()) -> sqlite3.Cursor:
        """One write under the lock: inside a block it joins it, outside it commits alone."""
        with self.atomic():
            return self.db.execute(sql, args)

    # -- nodes --------------------------------------------------------------------------
    def put_node(self, node: Node) -> None:
        refuse_nul(node.id, node.type, node.name, node.parent)
        self._write(
            "INSERT OR REPLACE INTO nodes(id,type,name,parent,doc) VALUES(?,?,?,?,?)",
            (node.id, node.type, node.name, node.parent, json.dumps(node.to_dict())),
        )

    def get_node(self, node_id: str) -> Node | None:
        refuse_nul(node_id)
        row = self.db.execute("SELECT doc FROM nodes WHERE id=?", (node_id,)).fetchone()
        return Node.from_dict(json.loads(row[0])) if row else None

    def list_nodes(self, parent: str | None = None, type: str | None = None) -> list[Node]:
        refuse_nul(parent, type)
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
        refuse_nul(type)
        row = self.db.execute(
            "SELECT doc FROM nodes WHERE type=? AND parent IS NULL", (type,)
        ).fetchone()
        return Node.from_dict(json.loads(row[0])) if row else None

    # -- items --------------------------------------------------------------------------
    def put(self, item: ContextItem) -> None:
        created_at = item.lifecycle.get("created_at", "")
        refuse_nul(item.id, item.kind, item.scope, item.key, item.status, created_at)
        self._write(
            "INSERT OR REPLACE INTO items(id,kind,scope,key,status,tombstoned,created_at,doc) "
            "VALUES(?,?,?,?,?,?,?,?)",
            (
                item.id,
                item.kind,
                item.scope,
                item.key,
                item.status,
                1 if item.lifecycle.get("tombstoned") else 0,
                created_at,
                json.dumps(item.to_dict()),
            ),
        )

    def get(self, item_id: str) -> ContextItem | None:
        refuse_nul(item_id)
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
        refuse_nul(scopes, key)
        if not scopes:
            return []
        sql = f"SELECT doc FROM items WHERE scope IN ({','.join('?' * len(scopes))})"
        args: list[Any] = list(scopes)
        if not include_tombstoned:
            sql += " AND tombstoned=0"
        if kinds:
            kinds = list(kinds)
            refuse_nul(kinds)
            sql += f" AND kind IN ({','.join('?' * len(kinds))})"
            args += kinds
        if key is not None:
            sql += " AND key=?"
            args.append(key)
        if statuses:
            statuses = list(statuses)
            refuse_nul(statuses)
            sql += f" AND status IN ({','.join('?' * len(statuses))})"
            args += statuses
        if text:
            sql += " AND doc LIKE ?"
            args.append(f"%{text}%")  # SKELETON: substring; embeddings later
        sql += " ORDER BY created_at DESC, id DESC"  # same-second items by id (storage.md §2)
        return [ContextItem.from_dict(json.loads(r[0])) for r in self.db.execute(sql, args)]

    def tombstone(self, item_id: str) -> bool:
        refuse_nul(item_id)
        item = self.get(item_id)
        if not item:
            return False
        item.lifecycle["tombstoned"] = True
        self.put(item)
        return True

    # -- audit --------------------------------------------------------------------------
    def audit_append(self, entry: dict[str, Any]) -> dict[str, Any]:
        refuse_nul(entry["ts"], entry["hash"], entry["prev_hash"])
        try:  # alone, its block rolls back; inside a block the whole act unwinds, not just this
            cur = self._write(
                "INSERT INTO audit(ts,hash,prev_hash,doc) VALUES(?,?,?,?)",
                (entry["ts"], entry["hash"], entry["prev_hash"], json.dumps(entry)),
            )
        except sqlite3.IntegrityError as e:
            raise ChainConflict(str(e)) from e
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
        refuse_nul(token.id)
        self._write(
            "INSERT OR REPLACE INTO tokens(id,doc) VALUES(?,?)",
            (token.id, json.dumps(token.to_dict(with_secret_hash=True))),
        )

    def get_token(self, token_id: str) -> Token | None:
        refuse_nul(token_id)
        row = self.db.execute("SELECT doc FROM tokens WHERE id=?", (token_id,)).fetchone()
        return Token.from_dict(json.loads(row[0])) if row else None

    def list_tokens(self) -> list[Token]:
        return [
            Token.from_dict(json.loads(r[0]))
            for r in self.db.execute("SELECT doc FROM tokens ORDER BY rowid")
        ]

    # -- proposals ----------------------------------------------------------------------
    def put_proposal(self, proposal: dict[str, Any]) -> None:
        refuse_nul(proposal["id"], proposal["status"])
        self._write(
            "INSERT OR REPLACE INTO proposals(id,status,doc) VALUES(?,?,?)",
            (proposal["id"], proposal["status"], json.dumps(proposal)),
        )

    def get_proposal(self, proposal_id: str) -> dict[str, Any] | None:
        refuse_nul(proposal_id)
        row = self.db.execute("SELECT doc FROM proposals WHERE id=?", (proposal_id,)).fetchone()
        return json.loads(row[0]) if row else None

    def list_proposals(self, status: str | None = None) -> list[dict[str, Any]]:
        refuse_nul(status)
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
        refuse_nul(surface, bucket_key, window_key)
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
        refuse_nul(surface, bucket_key, window_key)
        row = self.db.execute(
            "SELECT count FROM throttle WHERE surface=? AND bucket_key=? AND window_key=?",
            (surface, bucket_key, window_key),
        ).fetchone()
        return row[0] if row else 0

    def throttle_buckets(self, surface: ThrottleSurface, window_key: str) -> list[tuple[str, int]]:
        refuse_nul(surface, window_key)
        rows = self.db.execute(
            "SELECT bucket_key, count FROM throttle WHERE surface=? AND window_key=? "
            "ORDER BY bucket_key",
            (surface, window_key),
        )
        return [(k, n) for k, n in rows]

    def throttle_windows(self, surface: ThrottleSurface) -> list[str]:
        refuse_nul(surface)
        rows = self.db.execute(
            "SELECT DISTINCT window_key FROM throttle WHERE surface=? ORDER BY window_key",
            (surface,),
        )
        return [r[0] for r in rows]

    def throttle_forget(self, surface: ThrottleSurface, window_key: str) -> None:
        refuse_nul(surface, window_key)
        self._write("DELETE FROM throttle WHERE surface=? AND window_key=?", (surface, window_key))

    # -- IdentityState (storage.md §3.2) -----------------------------------------------------
    def put_user_grant(self, grant: UserGrant) -> None:
        refuse_nul(grant["sub"])
        self._write(
            "INSERT OR REPLACE INTO user_grants(sub,doc) VALUES(?,?)",
            (grant["sub"], json.dumps(grant)),
        )

    def get_user_grant(self, sub: str) -> UserGrant | None:
        refuse_nul(sub)
        row = self.db.execute("SELECT doc FROM user_grants WHERE sub=?", (sub,)).fetchone()
        return json.loads(row[0]) if row else None

    def list_user_grants(self) -> list[UserGrant]:
        rows = self.db.execute("SELECT doc FROM user_grants ORDER BY rowid")
        return [json.loads(r[0]) for r in rows]

    def put_agent_registration(self, registration: AgentRegistration) -> None:
        refuse_nul(registration["client_id"], registration["sub"])
        self._write(
            "INSERT OR REPLACE INTO agent_registrations(client_id,sub,doc) VALUES(?,?,?)",
            (registration["client_id"], registration["sub"], json.dumps(registration)),
        )

    def get_agent_registration(self, client_id: str, sub: str) -> AgentRegistration | None:
        refuse_nul(client_id, sub)
        row = self.db.execute(
            "SELECT doc FROM agent_registrations WHERE client_id=? AND sub=?", (client_id, sub)
        ).fetchone()
        return json.loads(row[0]) if row else None

    def list_agent_registrations(self, client_id: str | None = None) -> list[AgentRegistration]:
        refuse_nul(client_id)
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
        refuse_nul(key)
        self._write(
            "INSERT OR REPLACE INTO config(key,value) VALUES(?,?)", (key, json.dumps(value))
        )

    # -- ConfirmState (storage.md §3.3) ------------------------------------------------------
    def put_challenge(self, challenge: ConfirmChallenge) -> None:
        refuse_nul(challenge["id"], challenge["expires_at"])
        self._write(
            "INSERT INTO challenges(id,spent,expires_at,doc) VALUES(?,0,?,?)",
            (challenge["id"], challenge["expires_at"], json.dumps(challenge)),
        )

    def forget_challenges(self, expired_before: str) -> None:
        refuse_nul(expired_before)
        self._write("DELETE FROM challenges WHERE expires_at < ?", (expired_before,))

    def spend_challenge(self, challenge_id: str) -> ConfirmChallenge | None:
        """Mark it spent and return it as it stood: of two concurrent spends, one sees it fresh."""
        refuse_nul(challenge_id)
        with self.atomic():
            row = self.db.execute(
                "SELECT spent, doc FROM challenges WHERE id=?", (challenge_id,)
            ).fetchone()
            if row is None:
                return None
            self.db.execute("UPDATE challenges SET spent=1 WHERE id=?", (challenge_id,))
        return {**json.loads(row[1]), "spent": bool(row[0])}

    def put_credential(self, credential: ConfirmCredential) -> None:
        refuse_nul(credential["id"], credential["person"])
        self._write(
            "INSERT OR REPLACE INTO credentials(id,person,doc) VALUES(?,?,?)",
            (credential["id"], credential["person"], json.dumps(credential)),
        )

    def get_credential(self, credential_id: str) -> ConfirmCredential | None:
        refuse_nul(credential_id)
        row = self.db.execute(
            "SELECT doc FROM credentials WHERE id=?", (credential_id,)
        ).fetchone()
        return json.loads(row[0]) if row else None

    def list_credentials(self, person: str | None = None) -> list[ConfirmCredential]:
        refuse_nul(person)
        if person is None:
            rows = self.db.execute("SELECT doc FROM credentials ORDER BY rowid")
        else:
            rows = self.db.execute(
                "SELECT doc FROM credentials WHERE person=? ORDER BY rowid", (person,)
            )
        return [json.loads(r[0]) for r in rows]

    # -- UploadState (storage.md §3.4) -------------------------------------------------------
    def put_upload(self, upload: UploadRecord) -> None:
        refuse_nul(upload["id"], upload["principal"])
        with self.atomic():
            cur = self.db.execute(
                "UPDATE uploads SET doc=? WHERE id=?", (json.dumps(upload), upload["id"])
            )
            if cur.rowcount == 0:
                self.db.execute(
                    "INSERT INTO uploads(id,principal,doc) VALUES(?,?,?)",
                    (upload["id"], upload["principal"], json.dumps(upload)),
                )

    def get_upload(self, upload_id: str) -> UploadRecord | None:
        refuse_nul(upload_id)
        row = self.db.execute("SELECT doc FROM uploads WHERE id=?", (upload_id,)).fetchone()
        return json.loads(row[0]) if row else None

    def list_uploads(self, principal: str | None = None) -> list[UploadRecord]:
        refuse_nul(principal)
        if principal is None:
            rows = self.db.execute("SELECT doc FROM uploads ORDER BY rowid")
        else:
            rows = self.db.execute(
                "SELECT doc FROM uploads WHERE principal=? ORDER BY rowid", (principal,)
            )
        return [json.loads(r[0]) for r in rows]

    def spend_upload(self, upload_id: str, step: str) -> bool:
        refuse_nul(upload_id)
        column = {"bytes": "bytes_spent", "item": "item_spent"}[step]
        cur = self._write(
            f"UPDATE uploads SET {column}=1 WHERE id=? AND {column}=0", (upload_id,)  # noqa: S608
        )
        return cur.rowcount == 1

    # -- GrantState (storage.md §3.5) --------------------------------------------------------
    def spend_grant(self, sig_hash: str, expires_at: str) -> bool:
        """Record a spend, committed at once: of two concurrent spends of one grant, exactly one
        inserts. Refused inside `atomic()` or any open transaction, whose rollback would undo it."""
        refuse_nul(sig_hash, expires_at)
        if self._depth or self.db.in_transaction:
            raise RuntimeError("a grant is spent outside any transaction")
        cur = self._write(
            "INSERT OR IGNORE INTO spent_grants(sig_hash,expires_at) VALUES(?,?)",
            (sig_hash, expires_at),
        )
        return cur.rowcount == 1

    def forget_grants(self, expired_before: str) -> None:
        refuse_nul(expired_before)
        self._write("DELETE FROM spent_grants WHERE expires_at < ?", (expired_before,))
