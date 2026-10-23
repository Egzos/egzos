# Copyright 2026 Ali Sasanian
# SPDX-License-Identifier: LicenseRef-PolyForm-Strict-1.0.0
"""
Postgres backend — the hosted container's database (v0.7 §S: Supabase's Postgres, or any other).
The same contract as the sqlite backend, row for row: JSON documents in typed rows, the audit chain
append-only and single-successor, and every door-state Protocol on the same substrate.

Writers are serialised the way sqlite serialises them: every write runs in a transaction that
first takes one transaction-scoped advisory lock, as `BEGIN IMMEDIATE` takes sqlite's write lock.
So no other process moves the chain head mid-act, a read inside `atomic()` sees what it will
write over, and two processes on one database behave as two on one sqlite file. Reads outside a
transaction see what is committed. The driver is psycopg 3 (bought, v0.7 §R).
"""

from __future__ import annotations

import json
from collections.abc import Iterable, Iterator
from contextlib import contextmanager
from typing import Any

from egzos._types import (
    AgentRegistration,
    ConfirmChallenge,
    ConfirmCredential,
    ThrottleSurface,
    UploadRecord,
    UserGrant,
)
from egzos.backends.base import ChainConflict
from egzos.model import ContextItem, Node, Token

#: The advisory lock every write takes: "egzos" in ASCII. Per database, as a container is.
WRITE_LOCK = 0x65677A6F73

_SCHEMA = """
CREATE TABLE IF NOT EXISTS nodes (
  ord BIGSERIAL, id TEXT PRIMARY KEY, type TEXT NOT NULL, name TEXT NOT NULL, parent TEXT,
  doc TEXT NOT NULL);
CREATE INDEX IF NOT EXISTS nodes_parent ON nodes(parent);
CREATE TABLE IF NOT EXISTS items (
  id TEXT PRIMARY KEY, kind TEXT NOT NULL, scope TEXT NOT NULL, key TEXT, status TEXT NOT NULL,
  tombstoned BOOLEAN NOT NULL DEFAULT FALSE, created_at TEXT NOT NULL, doc TEXT NOT NULL);
CREATE INDEX IF NOT EXISTS items_scope ON items(scope);
CREATE INDEX IF NOT EXISTS items_kind_key ON items(kind, key);
CREATE TABLE IF NOT EXISTS audit (
  seq BIGINT PRIMARY KEY, ts TEXT NOT NULL, hash TEXT NOT NULL UNIQUE, prev_hash TEXT NOT NULL,
  doc TEXT NOT NULL);
-- One successor per entry: two writers that read the same head cannot both append after it.
CREATE UNIQUE INDEX IF NOT EXISTS audit_prev_hash ON audit(prev_hash);
CREATE OR REPLACE FUNCTION egzos_audit_append_only() RETURNS trigger AS $$
BEGIN RAISE EXCEPTION 'audit is append-only'; END $$ LANGUAGE plpgsql;
DROP TRIGGER IF EXISTS audit_no_update ON audit;
CREATE TRIGGER audit_no_update BEFORE UPDATE OR DELETE ON audit
  FOR EACH ROW EXECUTE FUNCTION egzos_audit_append_only();
CREATE TABLE IF NOT EXISTS tokens (ord BIGSERIAL, id TEXT PRIMARY KEY, doc TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS proposals (
  ord BIGSERIAL, id TEXT PRIMARY KEY, status TEXT NOT NULL, doc TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS throttle (
  surface TEXT NOT NULL, bucket_key TEXT NOT NULL, window_key TEXT NOT NULL,
  count BIGINT NOT NULL, PRIMARY KEY (surface, bucket_key, window_key));
CREATE TABLE IF NOT EXISTS user_grants (ord BIGSERIAL, sub TEXT PRIMARY KEY, doc TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS agent_registrations (
  ord BIGSERIAL, client_id TEXT NOT NULL, sub TEXT NOT NULL, doc TEXT NOT NULL,
  PRIMARY KEY (client_id, sub));
CREATE TABLE IF NOT EXISTS config (key TEXT PRIMARY KEY, value TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS authorizations (id TEXT PRIMARY KEY);
CREATE TABLE IF NOT EXISTS challenges (
  id TEXT PRIMARY KEY, spent BOOLEAN NOT NULL DEFAULT FALSE, expires_at TEXT NOT NULL,
  doc TEXT NOT NULL);
CREATE INDEX IF NOT EXISTS challenges_expiry ON challenges(expires_at);
CREATE TABLE IF NOT EXISTS credentials (
  ord BIGSERIAL, id TEXT PRIMARY KEY, person TEXT NOT NULL, doc TEXT NOT NULL);
CREATE INDEX IF NOT EXISTS credentials_person ON credentials(person);
CREATE TABLE IF NOT EXISTS spent_grants (sig_hash TEXT PRIMARY KEY, expires_at TEXT NOT NULL);
CREATE INDEX IF NOT EXISTS spent_grants_expiry ON spent_grants(expires_at);
CREATE TABLE IF NOT EXISTS uploads (
  ord BIGSERIAL, id TEXT PRIMARY KEY, principal TEXT NOT NULL,
  bytes_spent BOOLEAN NOT NULL DEFAULT FALSE, item_spent BOOLEAN NOT NULL DEFAULT FALSE,
  doc TEXT NOT NULL);
CREATE INDEX IF NOT EXISTS uploads_principal ON uploads(principal);
"""


class PostgresBackend:
    def __init__(self, url: str):
        import psycopg  # an optional dependency: `egzos[postgres]`

        self._errors = psycopg.errors
        self.db = psycopg.connect(url, autocommit=True)
        self._depth = 0  # > 0 inside atomic(): one transaction, under the write lock
        with self.atomic():
            self.db.execute(_SCHEMA)

    @contextmanager
    def atomic(self):
        """Every write inside lands together or not at all, under the one write lock."""
        if self._depth == 0:
            self.db.execute("BEGIN")
            try:
                self.db.execute("SELECT pg_advisory_xact_lock(%s)", (WRITE_LOCK,))
            except BaseException:
                self.db.execute("ROLLBACK")
                raise
        self._depth += 1
        try:
            yield
        except BaseException:
            self._depth -= 1
            if self._depth == 0:
                self.db.execute("ROLLBACK")
            raise
        self._depth -= 1
        if self._depth == 0:
            self.db.execute("COMMIT")

    def _write(self, sql: str, args: Iterable[Any] = ()) -> Any:
        with self.atomic():
            return self.db.execute(sql, tuple(args))

    def _one(self, sql: str, args: Iterable[Any] = ()) -> Any:
        return self.db.execute(sql, tuple(args)).fetchone()

    def _docs(self, sql: str, args: Iterable[Any] = ()) -> list[Any]:
        return [json.loads(r[0]) for r in self.db.execute(sql, tuple(args))]

    # -- nodes --------------------------------------------------------------------------
    def put_node(self, node: Node) -> None:
        self._write(
            "INSERT INTO nodes(id,type,name,parent,doc) VALUES(%s,%s,%s,%s,%s) "
            "ON CONFLICT(id) DO UPDATE SET type=EXCLUDED.type, name=EXCLUDED.name, "
            "parent=EXCLUDED.parent, doc=EXCLUDED.doc",
            (node.id, node.type, node.name, node.parent, json.dumps(node.to_dict())),
        )

    def get_node(self, node_id: str) -> Node | None:
        row = self._one("SELECT doc FROM nodes WHERE id=%s", (node_id,))
        return Node.from_dict(json.loads(row[0])) if row else None

    def list_nodes(self, parent: str | None = None, type: str | None = None) -> list[Node]:
        sql, args = "SELECT doc FROM nodes WHERE TRUE", []
        if parent is not None:
            sql += " AND parent=%s"
            args.append(parent)
        if type is not None:
            sql += " AND type=%s"
            args.append(type)
        return [Node.from_dict(d) for d in self._docs(sql + " ORDER BY ord", args)]

    def find_root(self, type: str) -> Node | None:
        row = self._one("SELECT doc FROM nodes WHERE type=%s AND parent IS NULL", (type,))
        return Node.from_dict(json.loads(row[0])) if row else None

    # -- items --------------------------------------------------------------------------
    def put(self, item: ContextItem) -> None:
        self._write(
            "INSERT INTO items(id,kind,scope,key,status,tombstoned,created_at,doc) "
            "VALUES(%s,%s,%s,%s,%s,%s,%s,%s) ON CONFLICT(id) DO UPDATE SET kind=EXCLUDED.kind, "
            "scope=EXCLUDED.scope, key=EXCLUDED.key, status=EXCLUDED.status, "
            "tombstoned=EXCLUDED.tombstoned, created_at=EXCLUDED.created_at, doc=EXCLUDED.doc",
            (item.id, item.kind, item.scope, item.key, item.status,
             bool(item.lifecycle.get("tombstoned")), item.lifecycle.get("created_at", ""),
             json.dumps(item.to_dict())),
        )

    def get(self, item_id: str) -> ContextItem | None:
        row = self._one("SELECT doc FROM items WHERE id=%s AND NOT tombstoned", (item_id,))
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
        sql, args = "SELECT doc FROM items WHERE scope = ANY(%s)", [scopes]
        if not include_tombstoned:
            sql += " AND NOT tombstoned"
        if kinds:
            sql += " AND kind = ANY(%s)"
            args.append(list(kinds))
        if key is not None:
            sql += " AND key=%s"
            args.append(key)
        if statuses:
            sql += " AND status = ANY(%s)"
            args.append(list(statuses))
        if text:
            # sqlite's LIKE folds ASCII case; ILIKE is the same answer here. The wildcards in the
            # text are escaped, so it is a substring and nothing more.
            sql += " AND doc ILIKE %s"
            escaped = text.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
            args.append(f"%{escaped}%")
        sql += " ORDER BY created_at DESC"
        return [ContextItem.from_dict(d) for d in self._docs(sql, args)]

    def tombstone(self, item_id: str) -> bool:
        with self.atomic():
            item = self.get(item_id)
            if not item:
                return False
            item.lifecycle["tombstoned"] = True
            self.put(item)
        return True

    # -- audit --------------------------------------------------------------------------
    def audit_append(self, entry: dict[str, Any]) -> dict[str, Any]:
        try:
            with self.atomic():
                # Under the write lock, so the next seq is this one's: contiguous, as sqlite's.
                (seq,) = self._one("SELECT COALESCE(MAX(seq), 0) + 1 FROM audit")
                self.db.execute(
                    "INSERT INTO audit(seq,ts,hash,prev_hash,doc) VALUES(%s,%s,%s,%s,%s)",
                    (seq, entry["ts"], entry["hash"], entry["prev_hash"], json.dumps(entry)),
                )
        except self._errors.UniqueViolation as e:
            raise ChainConflict(str(e)) from e
        return {**entry, "seq": seq}

    def audit_last(self) -> dict[str, Any] | None:
        row = self._one("SELECT seq, doc FROM audit ORDER BY seq DESC LIMIT 1")
        return {**json.loads(row[1]), "seq": row[0]} if row else None

    def audit_iter(self) -> Iterator[dict[str, Any]]:
        # A cursor of its own, so a caller may query the backend while it walks the chain.
        with self.db.cursor() as cur:
            for seq, doc in cur.execute("SELECT seq, doc FROM audit ORDER BY seq ASC"):
                yield {**json.loads(doc), "seq": seq}

    def audit_tail(self, n: int) -> list[dict[str, Any]]:
        rows = self.db.execute(
            "SELECT seq, doc FROM audit ORDER BY seq DESC LIMIT %s", (n,)
        ).fetchall()
        return [{**json.loads(doc), "seq": seq} for seq, doc in reversed(rows)]

    # -- tokens -------------------------------------------------------------------------
    def put_token(self, token: Token) -> None:
        self._write(
            "INSERT INTO tokens(id,doc) VALUES(%s,%s) ON CONFLICT(id) DO UPDATE SET "
            "doc=EXCLUDED.doc",
            (token.id, json.dumps(token.to_dict(with_secret_hash=True))),
        )

    def get_token(self, token_id: str) -> Token | None:
        row = self._one("SELECT doc FROM tokens WHERE id=%s", (token_id,))
        return Token.from_dict(json.loads(row[0])) if row else None

    def list_tokens(self) -> list[Token]:
        return [Token.from_dict(d) for d in self._docs("SELECT doc FROM tokens ORDER BY ord")]

    # -- proposals ----------------------------------------------------------------------
    def put_proposal(self, proposal: dict[str, Any]) -> None:
        self._write(
            "INSERT INTO proposals(id,status,doc) VALUES(%s,%s,%s) ON CONFLICT(id) DO UPDATE "
            "SET status=EXCLUDED.status, doc=EXCLUDED.doc",
            (proposal["id"], proposal["status"], json.dumps(proposal)),
        )

    def get_proposal(self, proposal_id: str) -> dict[str, Any] | None:
        row = self._one("SELECT doc FROM proposals WHERE id=%s", (proposal_id,))
        return json.loads(row[0]) if row else None

    def list_proposals(self, status: str | None = None) -> list[dict[str, Any]]:
        if status:
            return self._docs("SELECT doc FROM proposals WHERE status=%s ORDER BY ord", (status,))
        return self._docs("SELECT doc FROM proposals ORDER BY ord")

    # -- ThrottleState (storage.md §3.1) ----------------------------------------------------
    def throttle_incr(self, surface: ThrottleSurface, bucket_key: str, window_key: str) -> int:
        with self.atomic():
            (count,) = self._one(
                "INSERT INTO throttle(surface,bucket_key,window_key,count) VALUES(%s,%s,%s,1) "
                "ON CONFLICT(surface,bucket_key,window_key) DO UPDATE "
                "SET count=throttle.count+1 RETURNING count",
                (surface, bucket_key, window_key),
            )
        return count

    def throttle_count(self, surface: ThrottleSurface, bucket_key: str, window_key: str) -> int:
        row = self._one(
            "SELECT count FROM throttle WHERE surface=%s AND bucket_key=%s AND window_key=%s",
            (surface, bucket_key, window_key),
        )
        return row[0] if row else 0

    def throttle_buckets(self, surface: ThrottleSurface, window_key: str) -> list[tuple[str, int]]:
        rows = self.db.execute(
            "SELECT bucket_key, count FROM throttle WHERE surface=%s AND window_key=%s "
            "ORDER BY bucket_key",
            (surface, window_key),
        )
        return [(k, n) for k, n in rows]

    def throttle_windows(self, surface: ThrottleSurface) -> list[str]:
        rows = self.db.execute(
            "SELECT DISTINCT window_key FROM throttle WHERE surface=%s ORDER BY window_key",
            (surface,),
        )
        return [r[0] for r in rows]

    def throttle_forget(self, surface: ThrottleSurface, window_key: str) -> None:
        self._write("DELETE FROM throttle WHERE surface=%s AND window_key=%s",
                    (surface, window_key))

    # -- IdentityState and ConfigState (storage.md §3.2) -----------------------------------
    def put_user_grant(self, grant: UserGrant) -> None:
        self._write(
            "INSERT INTO user_grants(sub,doc) VALUES(%s,%s) ON CONFLICT(sub) DO UPDATE "
            "SET doc=EXCLUDED.doc",
            (grant["sub"], json.dumps(grant)),
        )

    def get_user_grant(self, sub: str) -> UserGrant | None:
        row = self._one("SELECT doc FROM user_grants WHERE sub=%s", (sub,))
        return json.loads(row[0]) if row else None

    def list_user_grants(self) -> list[UserGrant]:
        return self._docs("SELECT doc FROM user_grants ORDER BY ord")

    def put_agent_registration(self, registration: AgentRegistration) -> None:
        self._write(
            "INSERT INTO agent_registrations(client_id,sub,doc) VALUES(%s,%s,%s) "
            "ON CONFLICT(client_id,sub) DO UPDATE SET doc=EXCLUDED.doc",
            (registration["client_id"], registration["sub"], json.dumps(registration)),
        )

    def get_agent_registration(self, client_id: str, sub: str) -> AgentRegistration | None:
        row = self._one("SELECT doc FROM agent_registrations WHERE client_id=%s AND sub=%s",
                        (client_id, sub))
        return json.loads(row[0]) if row else None

    def list_agent_registrations(self, client_id: str | None = None) -> list[AgentRegistration]:
        if client_id is None:
            return self._docs("SELECT doc FROM agent_registrations ORDER BY ord")
        return self._docs(
            "SELECT doc FROM agent_registrations WHERE client_id=%s ORDER BY ord", (client_id,)
        )

    def claim_authorization(self, authorization_id: str) -> bool:
        cur = self._write("INSERT INTO authorizations(id) VALUES(%s) ON CONFLICT DO NOTHING",
                          (authorization_id,))
        return cur.rowcount == 1

    def get_config(self) -> dict[str, Any]:
        return {k: json.loads(v) for k, v in self.db.execute("SELECT key, value FROM config")}

    def put_config(self, key: str, value: Any) -> None:
        self._write(
            "INSERT INTO config(key,value) VALUES(%s,%s) ON CONFLICT(key) DO UPDATE "
            "SET value=EXCLUDED.value",
            (key, json.dumps(value)),
        )

    # -- ConfirmState (storage.md §3.3) ------------------------------------------------------
    def put_challenge(self, challenge: ConfirmChallenge) -> None:
        self._write("INSERT INTO challenges(id,expires_at,doc) VALUES(%s,%s,%s)",
                    (challenge["id"], challenge["expires_at"], json.dumps(challenge)))

    def forget_challenges(self, expired_before: str) -> None:
        self._write("DELETE FROM challenges WHERE expires_at < %s", (expired_before,))

    def spend_challenge(self, challenge_id: str) -> ConfirmChallenge | None:
        """Mark it spent and return it as it stood: of two concurrent spends, one sees it fresh."""
        with self.atomic():
            row = self._one("SELECT spent, doc FROM challenges WHERE id=%s", (challenge_id,))
            if row is None:
                return None
            self.db.execute("UPDATE challenges SET spent=TRUE WHERE id=%s", (challenge_id,))
        return {**json.loads(row[1]), "spent": bool(row[0])}

    def put_credential(self, credential: ConfirmCredential) -> None:
        self._write(
            "INSERT INTO credentials(id,person,doc) VALUES(%s,%s,%s) ON CONFLICT(id) DO UPDATE "
            "SET person=EXCLUDED.person, doc=EXCLUDED.doc",
            (credential["id"], credential["person"], json.dumps(credential)),
        )

    def get_credential(self, credential_id: str) -> ConfirmCredential | None:
        row = self._one("SELECT doc FROM credentials WHERE id=%s", (credential_id,))
        return json.loads(row[0]) if row else None

    def list_credentials(self, person: str | None = None) -> list[ConfirmCredential]:
        if person is None:
            return self._docs("SELECT doc FROM credentials ORDER BY ord")
        return self._docs("SELECT doc FROM credentials WHERE person=%s ORDER BY ord", (person,))

    # -- UploadState (storage.md §3.4) -------------------------------------------------------
    def put_upload(self, upload: UploadRecord) -> None:
        self._write(
            "INSERT INTO uploads(id,principal,doc) VALUES(%s,%s,%s) ON CONFLICT(id) DO UPDATE "
            "SET doc=EXCLUDED.doc",
            (upload["id"], upload["principal"], json.dumps(upload)),
        )

    def get_upload(self, upload_id: str) -> UploadRecord | None:
        row = self._one("SELECT doc FROM uploads WHERE id=%s", (upload_id,))
        return json.loads(row[0]) if row else None

    def list_uploads(self, principal: str | None = None) -> list[UploadRecord]:
        if principal is None:
            return self._docs("SELECT doc FROM uploads ORDER BY ord")
        return self._docs("SELECT doc FROM uploads WHERE principal=%s ORDER BY ord", (principal,))

    def spend_upload(self, upload_id: str, step: str) -> bool:
        column = {"bytes": "bytes_spent", "item": "item_spent"}[step]
        cur = self._write(
            f"UPDATE uploads SET {column}=TRUE WHERE id=%s AND NOT {column}",  # noqa: S608
            (upload_id,),
        )
        return cur.rowcount == 1

    # -- GrantState (storage.md §3.5) --------------------------------------------------------
    def spend_grant(self, sig_hash: str, expires_at: str) -> bool:
        cur = self._write(
            "INSERT INTO spent_grants(sig_hash,expires_at) VALUES(%s,%s) ON CONFLICT DO NOTHING",
            (sig_hash, expires_at),
        )
        return cur.rowcount == 1

    def forget_grants(self, expired_before: str) -> None:
        self._write("DELETE FROM spent_grants WHERE expires_at < %s", (expired_before,))
