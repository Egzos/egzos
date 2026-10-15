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

from egzos._types import (
    ASGrant,
    AuthorizationCodeRecord,
    ClientRegistration,
    DecidedRequestRecord,
    DeviceAuthorizationRecord,
    RefreshRecord,
    SessionRecord,
    ThrottleSurface,
)
from egzos.backends.base import ChainConflict
from egzos.model import ContextItem, Node, Token, now_iso

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
-- ASGateState (storage.md §3.1, draft binding on #173): the AS's gate, on this same substrate and
-- connection as ContainerState, never process memory, so a restart lifts no throttle and ends no
-- session. A credential value never lands in a column here: `session_hash` is already a digest.
CREATE TABLE IF NOT EXISTS as_sessions (session_hash TEXT PRIMARY KEY, doc TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS as_throttle (
  surface TEXT NOT NULL, bucket_key TEXT NOT NULL, window_key TEXT NOT NULL,
  count INTEGER NOT NULL, PRIMARY KEY (surface, bucket_key, window_key));
-- ASState (storage.md §3.1, draft binding on #173): clients, codes and decided requests, on the
-- same file and connection as ContainerState. No column here holds a credential value: `code_hash`
-- and `request_key` arrive already hashed/digested, never a bare code or token.
CREATE TABLE IF NOT EXISTS as_clients (client_id TEXT PRIMARY KEY, doc TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS as_codes (code_hash TEXT PRIMARY KEY, doc TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS as_decided (request_key TEXT PRIMARY KEY, doc TEXT NOT NULL);
-- ASState: device authorizations and refresh chains (storage.md §3.1 rules 2-4). `user_code_hash`
-- and `access_token_id` get their own column only to key the lookups `ASState` names
-- (`get_device_by_user_code`, `family_of_token`); the record itself still lives whole in `doc`.
CREATE TABLE IF NOT EXISTS as_devices (
  device_code_hash TEXT PRIMARY KEY, user_code_hash TEXT NOT NULL, doc TEXT NOT NULL);
CREATE INDEX IF NOT EXISTS as_devices_user_code ON as_devices(user_code_hash);
CREATE TABLE IF NOT EXISTS as_refresh (
  refresh_hash TEXT PRIMARY KEY, family_id TEXT NOT NULL, access_token_id TEXT NOT NULL,
  revoked INTEGER NOT NULL DEFAULT 0, doc TEXT NOT NULL);
CREATE INDEX IF NOT EXISTS as_refresh_family ON as_refresh(family_id);
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

    # -- ASGateState (storage.md §3.1, draft binding on #173) ---------------------------
    # Sessions and throttle counters, on this file and this connection, never process memory
    # (the Chief on #173, option (A)). No method here takes a credential value: `session_hash`
    # reaches the store only as `values.digest` of the session value (sessions.py).
    def put_session(self, record: SessionRecord) -> None:
        self.db.execute(
            "INSERT OR REPLACE INTO as_sessions(session_hash,doc) VALUES(?,?)",
            (record["session_hash"], json.dumps(record)),
        )
        self._commit()

    def get_session(self, session_hash: str) -> SessionRecord | None:
        row = self.db.execute(
            "SELECT doc FROM as_sessions WHERE session_hash=?", (session_hash,)
        ).fetchone()
        return json.loads(row[0]) if row else None

    def touch_session(self, session_hash: str, at: str) -> bool:
        """Sets `last_seen_at` alone, atomically against a concurrent `end_session` on the same
        key: of two concurrent calls, exactly one observes the record before the other's change."""
        with self.atomic():
            row = self.db.execute(
                "SELECT doc FROM as_sessions WHERE session_hash=?", (session_hash,)
            ).fetchone()
            if row is None:
                return False
            record = json.loads(row[0])
            record["last_seen_at"] = at
            self.db.execute(
                "UPDATE as_sessions SET doc=? WHERE session_hash=?",
                (json.dumps(record), session_hash),
            )
        return True

    def end_session(self, session_hash: str) -> bool:
        """Ends the session: a later `get_session` on this key is a miss, like any other absent
        key (silence-not-errors). `True` when a session was found and ended, `False` otherwise."""
        with self.atomic():
            cur = self.db.execute("DELETE FROM as_sessions WHERE session_hash=?", (session_hash,))
        return cur.rowcount > 0

    def throttle_incr(self, surface: ThrottleSurface, bucket_key: str, window_key: str) -> int:
        """Increments and returns the new count, atomically: of two concurrent callers on the
        same key, each observes its own correctly incremented total, never the other's. Names no
        rate and no window length (Trust's, #141); the three keys are compared as opaque values."""
        with self.atomic():
            self.db.execute(
                "INSERT INTO as_throttle(surface,bucket_key,window_key,count) VALUES(?,?,?,1) "
                "ON CONFLICT(surface,bucket_key,window_key) DO UPDATE SET count=count+1",
                (surface, bucket_key, window_key),
            )
            row = self.db.execute(
                "SELECT count FROM as_throttle WHERE surface=? AND bucket_key=? AND window_key=?",
                (surface, bucket_key, window_key),
            ).fetchone()
        return row[0]

    def throttle_count(self, surface: ThrottleSurface, bucket_key: str, window_key: str) -> int:
        row = self.db.execute(
            "SELECT count FROM as_throttle WHERE surface=? AND bucket_key=? AND window_key=?",
            (surface, bucket_key, window_key),
        ).fetchone()
        return row[0] if row else 0

    # -- ASState: clients (storage.md §3.1, draft binding on #173) ----------------------
    # Registration is an owner act (§5); this is the registry itself, not a `ContainerConfig`
    # key, and there is no listing method (§11.1, §7.1).
    def put_client(self, registration: ClientRegistration) -> None:
        """Add and amend: a second put on the same `client_id` replaces the entry whole."""
        self.db.execute(
            "INSERT OR REPLACE INTO as_clients(client_id,doc) VALUES(?,?)",
            (registration["client_id"], json.dumps(registration)),
        )
        self._commit()

    def get_client(self, client_id: str) -> ClientRegistration | None:
        row = self.db.execute(
            "SELECT doc FROM as_clients WHERE client_id=?", (client_id,)
        ).fetchone()
        return json.loads(row[0]) if row else None

    def remove_client(self, client_id: str) -> bool:
        cur = self.db.execute("DELETE FROM as_clients WHERE client_id=?", (client_id,))
        self._commit()
        return cur.rowcount > 0

    # -- ASState: codes (storage.md §3.1 rule 1) -----------------------------------------
    def put_code(self, record: AuthorizationCodeRecord) -> None:
        self.db.execute(
            "INSERT OR REPLACE INTO as_codes(code_hash,doc) VALUES(?,?)",
            (record["code_hash"], json.dumps(record)),
        )
        self._commit()

    def consume_code(self, code_hash: str) -> AuthorizationCodeRecord | None:
        """Returns the record and invalidates it in one step: of two concurrent callers on the
        same `code_hash`, exactly one observes it, and every later call is a miss. Does not judge
        expiry or the §2 bindings — that is Trust's, on what this returns."""
        with self.atomic():
            row = self.db.execute(
                "SELECT doc FROM as_codes WHERE code_hash=?", (code_hash,)
            ).fetchone()
            if row is None:
                return None
            self.db.execute("DELETE FROM as_codes WHERE code_hash=?", (code_hash,))
        return json.loads(row[0])

    # -- ASState: decided requests (storage.md §3.1 rule 5, §11.4) ----------------------
    def put_decided(self, record: DecidedRequestRecord) -> None:
        """Insert-only (#226): a put on an existing `request_key` changes nothing."""
        self.db.execute(
            "INSERT OR IGNORE INTO as_decided(request_key,doc) VALUES(?,?)",
            (record["request_key"], json.dumps(record)),
        )
        self._commit()

    def get_decided(self, request_key: str) -> DecidedRequestRecord | None:
        row = self.db.execute(
            "SELECT doc FROM as_decided WHERE request_key=?", (request_key,)
        ).fetchone()
        return json.loads(row[0]) if row else None

    def claim_resubmission(self, session_hash: str, request_key: str) -> bool:
        """`True` exactly once per `(session_hash, request_key)` that `put_decided` recorded,
        atomically against a concurrent claim on the same key; `False` otherwise, including an
        unrecorded `request_key` or a `session_hash` that does not match the deciding session."""
        with self.atomic():
            row = self.db.execute(
                "SELECT doc FROM as_decided WHERE request_key=?", (request_key,)
            ).fetchone()
            if row is None:
                return False
            record = json.loads(row[0])
            if record["session_hash"] != session_hash or record["resubmission_seen"]:
                return False
            record["resubmission_seen"] = True
            self.db.execute(
                "UPDATE as_decided SET doc=? WHERE request_key=?",
                (json.dumps(record), request_key),
            )
        return True

    # -- ASState: device authorizations (storage.md §3.1 rule 2) -----------------------
    def put_device(self, record: DeviceAuthorizationRecord) -> None:
        """Insert-only: a put on an existing `device_code_hash` changes nothing."""
        self.db.execute(
            "INSERT OR IGNORE INTO as_devices(device_code_hash,user_code_hash,doc) "
            "VALUES(?,?,?)",
            (record["device_code_hash"], record["user_code_hash"], json.dumps(record)),
        )
        self._commit()

    def poll_device(self, device_code_hash: str, at: str) -> DeviceAuthorizationRecord | None:
        """Sets `last_polled_at` alone, atomically; returns the record as it stood before the
        call, so Trust compares the prior stamp with `at` for §3 mitigation 1's `slow_down`."""
        with self.atomic():
            row = self.db.execute(
                "SELECT doc FROM as_devices WHERE device_code_hash=?", (device_code_hash,)
            ).fetchone()
            if row is None:
                return None
            prior = json.loads(row[0])
            record = {**prior, "last_polled_at": at}
            self.db.execute(
                "UPDATE as_devices SET doc=? WHERE device_code_hash=?",
                (json.dumps(record), device_code_hash),
            )
        return prior

    def get_device_by_user_code(self, user_code_hash: str) -> DeviceAuthorizationRecord | None:
        row = self.db.execute(
            "SELECT doc FROM as_devices WHERE user_code_hash=?", (user_code_hash,)
        ).fetchone()
        return json.loads(row[0]) if row else None

    def decide_device(self, device_code_hash: str, grant: ASGrant | None) -> bool:
        """Moves a pending record to decided exactly once, atomically; sets only `decision` and
        `grant`. `False` if the record was not pending, including an absent one."""
        with self.atomic():
            row = self.db.execute(
                "SELECT doc FROM as_devices WHERE device_code_hash=?", (device_code_hash,)
            ).fetchone()
            if row is None:
                return False
            record = json.loads(row[0])
            if record["decision"] != "pending":
                return False
            record["decision"] = "granted" if grant is not None else "denied"
            record["grant"] = grant
            self.db.execute(
                "UPDATE as_devices SET doc=? WHERE device_code_hash=?",
                (json.dumps(record), device_code_hash),
            )
        return True

    def consume_device(self, device_code_hash: str) -> DeviceAuthorizationRecord | None:
        """`None` while the record is pending — a poll before the decision spends nothing — and
        spends a decided one exactly once, atomically."""
        with self.atomic():
            row = self.db.execute(
                "SELECT doc FROM as_devices WHERE device_code_hash=?", (device_code_hash,)
            ).fetchone()
            if row is None:
                return None
            record = json.loads(row[0])
            if record["decision"] == "pending":
                return None
            self.db.execute("DELETE FROM as_devices WHERE device_code_hash=?", (device_code_hash,))
        return record

    # -- ASState: refresh chains (storage.md §3.1 rules 3-4, §9.2) ----------------------
    def put_refresh(self, record: RefreshRecord) -> None:
        self.db.execute(
            "INSERT OR REPLACE INTO as_refresh"
            "(refresh_hash,family_id,access_token_id,revoked,doc) VALUES(?,?,?,?,?)",
            (
                record["refresh_hash"],
                record["family_id"],
                record["access_token_id"],
                1 if record["revoked"] else 0,
                json.dumps(record),
            ),
        )
        self._commit()

    def redeem_refresh(self, refresh_hash: str) -> RefreshRecord | None:
        """Marks the record redeemed and returns it as it stood before the call, atomically, so
        a non-null `redeemed_at` on the returned record is visible reuse. A record already
        redeemed keeps its original `redeemed_at` rather than being overwritten."""
        with self.atomic():
            row = self.db.execute(
                "SELECT doc FROM as_refresh WHERE refresh_hash=?", (refresh_hash,)
            ).fetchone()
            if row is None:
                return None
            prior = json.loads(row[0])
            if prior["redeemed_at"] is None:
                record = {**prior, "redeemed_at": now_iso()}
                self.db.execute(
                    "UPDATE as_refresh SET doc=? WHERE refresh_hash=?",
                    (json.dumps(record), refresh_hash),
                )
        return prior

    def family_of_token(self, token_id: str) -> str | None:
        """`None` for absent, expired, spent and revoked alike: a revoked family reads as
        `None`, like any other plain getter (silence-not-errors)."""
        row = self.db.execute(
            "SELECT family_id FROM as_refresh WHERE access_token_id=? AND revoked=0", (token_id,)
        ).fetchone()
        return row[0] if row else None

    def revoke_family(self, family_id: str) -> list[str]:
        """Revokes every unrevoked refresh record in the family and every `Token` they name, in
        one transaction on the `tokens` table this file already owns. Until #214 items 4/5 are
        answered, returns only the newly revoked ids: a family already revoked returns `[]`,
        so a replayed reuse never double-counts or double-fires `token.revoke`."""
        with self.atomic():
            rows = self.db.execute(
                "SELECT refresh_hash, doc FROM as_refresh WHERE family_id=? AND revoked=0",
                (family_id,),
            ).fetchall()
            token_ids: list[str] = []
            for refresh_hash, doc in rows:
                record = {**json.loads(doc), "revoked": True}
                self.db.execute(
                    "UPDATE as_refresh SET revoked=1, doc=? WHERE refresh_hash=?",
                    (json.dumps(record), refresh_hash),
                )
                token = self.get_token(record["access_token_id"])
                if token is not None:
                    token.revoked = True
                    self.put_token(token)
                token_ids.append(record["access_token_id"])
        return token_ids
