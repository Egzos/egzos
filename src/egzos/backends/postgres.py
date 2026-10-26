# Copyright 2026 Ali Sasanian
# SPDX-License-Identifier: LicenseRef-PolyForm-Strict-1.0.0
"""postgres backend — a container's own database (storage.md §1's reading of [0.3 · 5], §3.6,
§3.7; v0.7 §AF). The sqlite backend is the reference: each method does what its sqlite twin does,
its order, ties and quirks included, so the harness under `tests/store/` runs both alike.

psycopg 3 is the `postgres` extra's, and only this module imports it. One synchronous connection
per instance (v0.7 §AF), in autocommit outside `atomic()`. `SCHEMA` is applied by
`apply_schema`, as the role that owns the tables, from outside the container: this class never
creates or alters a table, and the role it connects as owns none (§3.7)."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Iterable, Iterator, Sequence
from contextlib import contextmanager
from typing import Any

import psycopg
from psycopg import errors, pq
from psycopg.sql import SQL, Identifier

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

#: How long a writer waits for the container's write lock before it raises `StorageBusy`
#: (storage.md §3.6): sqlite's busy timeout.
LOCK_TIMEOUT = "10s"

#: storage.md §3.7. Documents are the JSON text the backend wrote, never `jsonb`. `write_order`
#: is sqlite's rowid: a replaced record moves to the end of its list. Columns that are ordered,
#: ranged or matched are `COLLATE "C"`, byte-wise as sqlite's BINARY, so ILIKE folds ASCII alone.
SCHEMA = """
CREATE SCHEMA {schema};
SET LOCAL search_path TO {schema};
CREATE SEQUENCE write_order;
CREATE TABLE nodes (id text PRIMARY KEY, type text NOT NULL, name text NOT NULL, parent text,
  doc text NOT NULL, write_order bigint NOT NULL DEFAULT nextval('write_order'));
CREATE INDEX nodes_parent ON nodes (parent);
CREATE TABLE items (
  id text COLLATE "C" PRIMARY KEY, kind text NOT NULL, scope text NOT NULL, key text,
  status text NOT NULL, tombstoned boolean NOT NULL, created_at text COLLATE "C" NOT NULL,
  doc text COLLATE "C" NOT NULL, write_order bigint NOT NULL DEFAULT nextval('write_order'));
CREATE INDEX items_scope ON items (scope);
CREATE INDEX items_kind_key ON items (kind, key);
-- seq is the head's plus one, under the write lock, never a sequence's (events.md §2); one
-- successor per entry (storage.md §3.6).
CREATE TABLE audit (seq bigint PRIMARY KEY, ts text NOT NULL, hash text NOT NULL UNIQUE,
  prev_hash text NOT NULL UNIQUE, doc text NOT NULL);
-- Append-only twice (events.md §4 item 1): this trigger, which refuses every role, and the
-- grants below, since the tables' owner can set a trigger aside.
CREATE FUNCTION audit_refuse() RETURNS trigger LANGUAGE plpgsql
  AS $$BEGIN RAISE EXCEPTION 'audit is append-only'; END$$;
CREATE TRIGGER audit_append_only BEFORE UPDATE OR DELETE OR TRUNCATE ON audit
  FOR EACH STATEMENT EXECUTE FUNCTION audit_refuse();
CREATE TABLE tokens (id text PRIMARY KEY, doc text NOT NULL,
  write_order bigint NOT NULL DEFAULT nextval('write_order'));
CREATE TABLE proposals (id text PRIMARY KEY, status text NOT NULL, doc text NOT NULL,
  write_order bigint NOT NULL DEFAULT nextval('write_order'));
CREATE TABLE throttle (surface text NOT NULL, bucket_key text COLLATE "C" NOT NULL,
  window_key text COLLATE "C" NOT NULL, count integer NOT NULL,
  PRIMARY KEY (surface, bucket_key, window_key));
CREATE TABLE user_grants (sub text PRIMARY KEY, doc text NOT NULL,
  write_order bigint NOT NULL DEFAULT nextval('write_order'));
CREATE TABLE agent_registrations (client_id text NOT NULL, sub text NOT NULL, doc text NOT NULL,
  write_order bigint NOT NULL DEFAULT nextval('write_order'), PRIMARY KEY (client_id, sub));
CREATE TABLE config (key text PRIMARY KEY, value text NOT NULL,
  write_order bigint NOT NULL DEFAULT nextval('write_order'));
CREATE TABLE challenges (id text PRIMARY KEY, spent boolean NOT NULL DEFAULT false,
  expires_at text COLLATE "C" NOT NULL, doc text NOT NULL);
CREATE INDEX challenges_expiry ON challenges (expires_at);
CREATE TABLE credentials (id text PRIMARY KEY, person text NOT NULL, doc text NOT NULL,
  write_order bigint NOT NULL DEFAULT nextval('write_order'));
CREATE INDEX credentials_person ON credentials (person);
CREATE TABLE uploads (id text PRIMARY KEY, principal text NOT NULL, doc text NOT NULL,
  bytes_spent boolean NOT NULL DEFAULT false, item_spent boolean NOT NULL DEFAULT false,
  write_order bigint NOT NULL DEFAULT nextval('write_order'));
CREATE INDEX uploads_principal ON uploads (principal);
CREATE TABLE spent_grants (sig_hash text PRIMARY KEY, expires_at text COLLATE "C" NOT NULL);
-- The container's role holds only what the methods need, and no other role holds anything here:
-- a new schema grants nothing to PUBLIC, but a new function is PUBLIC's to execute.
REVOKE ALL ON FUNCTION audit_refuse() FROM PUBLIC;
GRANT USAGE ON SCHEMA {schema} TO {role};
GRANT USAGE ON SEQUENCE write_order TO {role};
GRANT SELECT, INSERT ON audit TO {role};
GRANT SELECT, INSERT, UPDATE ON nodes, items, tokens, proposals, user_grants,
  agent_registrations, config, credentials, uploads TO {role};
GRANT SELECT, INSERT, UPDATE, DELETE ON throttle, challenges TO {role};
GRANT SELECT, INSERT, DELETE ON spent_grants TO {role};
"""


def apply_schema(owner: psycopg.Connection[Any], schema: str, container_role: str) -> None:
    """Create `schema` as `owner`, the role that then owns its tables, and grant `container_role`
    only what `PostgresBackend` needs (storage.md §3.7). Run by the operator, from outside the
    container, which never holds the owner's credentials: all of it lands, or none."""
    with owner.transaction():
        owner.execute(SQL(SCHEMA).format(schema=Identifier(schema),
                                         role=Identifier(container_role)))


def _upsert(table: str, keys: str, cols: str) -> str:
    """sqlite's INSERT OR REPLACE: the record is replaced, and moves last in the write order."""
    names = f"{keys},{cols}".split(",")
    sets = ", ".join(f"{c} = excluded.{c}" for c in cols.split(","))
    return (f"INSERT INTO {table} ({', '.join(names)}) VALUES ({', '.join(['%s'] * len(names))}) "
            f"ON CONFLICT ({keys}) DO UPDATE SET {sets}, write_order = DEFAULT")


_PUT = {table: _upsert(table, keys, cols) for table, keys, cols in [
    ("nodes", "id", "type,name,parent,doc"),
    ("items", "id", "kind,scope,key,status,tombstoned,created_at,doc"),
    ("tokens", "id", "doc"),
    ("proposals", "id", "status,doc"),
    ("user_grants", "sub", "doc"),
    ("agent_registrations", "client_id,sub", "doc"),
    ("config", "key", "value"),
    ("credentials", "id", "person,doc"),
]}
_PAGE = 1000  # chain entries `audit_iter` reads at a time


class PostgresBackend:
    def __init__(self, conninfo: str, schema: str):
        # As the sqlite backend's: one connection, used by one caller at a time. Autocommit, so a
        # read outside a block is a statement of its own; every write takes the lock (atomic()).
        # The connection string is the host's secret (§3.7): used here, and kept nowhere.
        self.db = psycopg.connect(conninfo, autocommit=True)
        self.db.execute(SQL("SET search_path TO {}").format(Identifier(schema)))
        # The container's one write lock (§3.6), keyed on its database and its schema.
        name = f"egzos\0{self.db.info.dbname}\0{schema}".encode()
        key = int.from_bytes(hashlib.sha256(name).digest()[:8], "big", signed=True)
        self._begin = (f"BEGIN ISOLATION LEVEL READ COMMITTED; SET LOCAL lock_timeout = "
                       f"'{LOCK_TIMEOUT}'; SELECT pg_advisory_xact_lock({key})")
        self._depth = 0  # > 0 inside atomic(): writes wait for its one commit

    @contextmanager
    def atomic(self) -> Iterator[None]:
        """Every write inside lands together or not at all. The lock is taken before the block's
        first read, at READ COMMITTED, so each later statement sees every earlier commit, and a
        block opened inside this one joins it. A lock not taken within `LOCK_TIMEOUT` raises
        `StorageBusy`, and nothing was written (storage.md §3.6)."""
        if self._depth:
            self._depth += 1
            try:
                yield
            finally:
                self._depth -= 1
            return
        if self.db.info.transaction_status != pq.TransactionStatus.IDLE:
            self.db.rollback()  # as sqlite's: the block holds the lock from its start
        self._depth = 1
        try:
            self.db.execute(self._begin, prepare=False)
            yield
        except BaseException as e:
            self.db.rollback()
            if isinstance(e, errors.LockNotAvailable):
                raise StorageBusy("the container's write lock was not taken in time") from e
            raise
        else:
            self.db.commit()
        finally:
            self._depth = 0

    def _write(self, query: str, args: Sequence[Any] = ()) -> psycopg.Cursor[Any]:
        """One write under the lock: inside a block it joins it, outside it commits alone."""
        with self.atomic():
            return self.db.execute(query, args)

    def _all(self, query: str, args: Sequence[Any] = ()) -> list[Any]:
        return self.db.execute(query, args).fetchall()

    def _get(self, table: str, **keys: str) -> Any:
        where = " AND ".join(f"{k} = %s" for k in keys)
        rows = self._all(f"SELECT doc FROM {table} WHERE {where}", list(keys.values()))
        return json.loads(rows[0][0]) if rows else None

    def _list(self, table: str, **match: str | None) -> list[Any]:
        """The table's documents in write order, filtered on each column given a value."""
        given = {k: v for k, v in match.items() if v is not None}
        where = "".join(f" AND {k} = %s" for k in given)
        query = f"SELECT doc FROM {table} WHERE true{where} ORDER BY write_order"
        return [json.loads(r[0]) for r in self._all(query, list(given.values()))]

    # -- nodes --------------------------------------------------------------------------
    def put_node(self, node: Node) -> None:
        refuse_nul(node.id, node.type, node.name, node.parent)
        self._write(_PUT["nodes"],
                    (node.id, node.type, node.name, node.parent, json.dumps(node.to_dict())))

    def get_node(self, node_id: str) -> Node | None:
        refuse_nul(node_id)
        doc = self._get("nodes", id=node_id)
        return Node.from_dict(doc) if doc is not None else None

    def list_nodes(self, parent: str | None = None, type: str | None = None) -> list[Node]:
        refuse_nul(parent, type)
        return [Node.from_dict(d) for d in self._list("nodes", parent=parent, type=type)]

    def find_root(self, type: str) -> Node | None:
        refuse_nul(type)
        rows = self._all("SELECT doc FROM nodes WHERE type = %s AND parent IS NULL "
                         "ORDER BY write_order LIMIT 1", (type,))  # sqlite's first, by rowid
        return Node.from_dict(json.loads(rows[0][0])) if rows else None

    # -- items --------------------------------------------------------------------------
    def put(self, item: ContextItem) -> None:
        created_at = item.lifecycle.get("created_at", "")
        refuse_nul(item.id, item.kind, item.scope, item.key, item.status, created_at)
        self._write(_PUT["items"], (
            item.id, item.kind, item.scope, item.key, item.status,
            bool(item.lifecycle.get("tombstoned")), created_at, json.dumps(item.to_dict()),
        ))

    def get(self, item_id: str) -> ContextItem | None:
        refuse_nul(item_id)
        rows = self._all("SELECT doc FROM items WHERE id = %s AND NOT tombstoned", (item_id,))
        return ContextItem.from_dict(json.loads(rows[0][0])) if rows else None

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
        sql, args = "SELECT doc FROM items WHERE scope = ANY(%s)", [scopes]
        if not include_tombstoned:
            sql += " AND NOT tombstoned"
        if kinds:
            kinds = list(kinds)
            refuse_nul(kinds)
            sql += " AND kind = ANY(%s)"
            args.append(kinds)
        if key is not None:
            sql += " AND key = %s"
            args.append(key)
        if statuses:
            statuses = list(statuses)
            refuse_nul(statuses)
            sql += " AND status = ANY(%s)"
            args.append(statuses)
        if text:
            # sqlite's `doc LIKE` over the stored JSON: ASCII letters fold (COLLATE "C"), `%` and
            # `_` are wildcards, `\` is literal (ESCAPE ''), and the pattern ends at a NUL.
            sql += " AND doc ILIKE %s ESCAPE ''"
            args.append(f"%{text}%".split("\0", 1)[0])
        sql += " ORDER BY created_at DESC, id DESC"  # same-second items by id (storage.md §2)
        return [ContextItem.from_dict(json.loads(r[0])) for r in self._all(sql, args)]

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
        # A second successor of one entry is not inserted, so no error spoils a block it runs in:
        # the block goes on, as sqlite's does after a failed statement, and the ledger re-chains.
        refuse_nul(entry["ts"], entry["hash"], entry["prev_hash"])
        with self.atomic():
            row = self.db.execute(
                "INSERT INTO audit (seq, ts, hash, prev_hash, doc) "
                "SELECT coalesce(max(seq), 0) + 1, %s, %s, %s, %s FROM audit "
                "ON CONFLICT DO NOTHING RETURNING seq",
                (entry["ts"], entry["hash"], entry["prev_hash"], json.dumps(entry)),
            ).fetchone()
            if row is None:
                raise ChainConflict("an entry already follows that prev_hash, or is this one")
        return {**entry, "seq": row[0]}

    def audit_last(self) -> dict[str, Any] | None:
        rows = self._all("SELECT seq, doc FROM audit ORDER BY seq DESC LIMIT 1")
        return {**json.loads(rows[0][1]), "seq": rows[0][0]} if rows else None

    def audit_iter(self) -> Iterator[dict[str, Any]]:
        # A page at a time, so a walk of a long chain holds one page; an entry appended during
        # the walk is read too, as a later reader of the tail would read it (events.md §2).
        page = self._all("SELECT seq, doc FROM audit ORDER BY seq LIMIT %s", (_PAGE,))
        while page:
            yield from ({**json.loads(doc), "seq": seq} for seq, doc in page)
            page = self._all("SELECT seq, doc FROM audit WHERE seq > %s ORDER BY seq LIMIT %s",
                             (page[-1][0], _PAGE))

    def audit_tail(self, n: int) -> list[dict[str, Any]]:
        rows = self._all("SELECT seq, doc FROM audit ORDER BY seq DESC LIMIT %s",
                         (n if n >= 0 else None,))  # sqlite reads a negative LIMIT as none
        return [{**json.loads(doc), "seq": seq} for seq, doc in reversed(rows)]

    # -- tokens -------------------------------------------------------------------------
    def put_token(self, token: Token) -> None:
        refuse_nul(token.id)
        self._write(_PUT["tokens"], (token.id, json.dumps(token.to_dict(with_secret_hash=True))))

    def get_token(self, token_id: str) -> Token | None:
        refuse_nul(token_id)
        doc = self._get("tokens", id=token_id)
        return Token.from_dict(doc) if doc is not None else None

    def list_tokens(self) -> list[Token]:
        return [Token.from_dict(d) for d in self._list("tokens")]

    # -- proposals ----------------------------------------------------------------------
    def put_proposal(self, proposal: dict[str, Any]) -> None:
        refuse_nul(proposal["id"], proposal["status"])
        self._write(_PUT["proposals"],
                    (proposal["id"], proposal["status"], json.dumps(proposal)))

    def get_proposal(self, proposal_id: str) -> dict[str, Any] | None:
        refuse_nul(proposal_id)
        return self._get("proposals", id=proposal_id)

    def list_proposals(self, status: str | None = None) -> list[dict[str, Any]]:
        refuse_nul(status)
        return self._list("proposals", status=status or None)  # sqlite's `if status:`

    # -- ThrottleState (storage.md §3.1) ----------------------------------------------------
    def throttle_incr(self, surface: ThrottleSurface, bucket_key: str, window_key: str) -> int:
        """Increments and returns the new count, atomically, under the lock."""
        refuse_nul(surface, bucket_key, window_key)
        return self._write(
            "INSERT INTO throttle (surface, bucket_key, window_key, count) VALUES (%s, %s, %s, 1) "
            "ON CONFLICT (surface, bucket_key, window_key) "
            "DO UPDATE SET count = throttle.count + 1 RETURNING count",
            (surface, bucket_key, window_key),
        ).fetchone()[0]

    def throttle_count(self, surface: ThrottleSurface, bucket_key: str, window_key: str) -> int:
        refuse_nul(surface, bucket_key, window_key)
        rows = self._all(
            "SELECT count FROM throttle WHERE surface = %s AND bucket_key = %s AND window_key = %s",
            (surface, bucket_key, window_key),
        )
        return rows[0][0] if rows else 0

    def throttle_buckets(self, surface: ThrottleSurface, window_key: str) -> list[tuple[str, int]]:
        refuse_nul(surface, window_key)
        rows = self._all("SELECT bucket_key, count FROM throttle WHERE surface = %s "
                         "AND window_key = %s ORDER BY bucket_key", (surface, window_key))
        return [(k, n) for k, n in rows]

    def throttle_windows(self, surface: ThrottleSurface) -> list[str]:
        refuse_nul(surface)
        rows = self._all("SELECT DISTINCT window_key FROM throttle WHERE surface = %s "
                         "ORDER BY window_key", (surface,))
        return [r[0] for r in rows]

    def throttle_forget(self, surface: ThrottleSurface, window_key: str) -> None:
        refuse_nul(surface, window_key)
        self._write("DELETE FROM throttle WHERE surface = %s AND window_key = %s",
                    (surface, window_key))

    # -- IdentityState (storage.md §3.2) -----------------------------------------------------
    def put_user_grant(self, grant: UserGrant) -> None:
        refuse_nul(grant["sub"])
        self._write(_PUT["user_grants"], (grant["sub"], json.dumps(grant)))

    def get_user_grant(self, sub: str) -> UserGrant | None:
        refuse_nul(sub)
        return self._get("user_grants", sub=sub)

    def list_user_grants(self) -> list[UserGrant]:
        return self._list("user_grants")

    def put_agent_registration(self, registration: AgentRegistration) -> None:
        refuse_nul(registration["client_id"], registration["sub"])
        self._write(_PUT["agent_registrations"],
                    (registration["client_id"], registration["sub"], json.dumps(registration)))

    def get_agent_registration(self, client_id: str, sub: str) -> AgentRegistration | None:
        refuse_nul(client_id, sub)
        return self._get("agent_registrations", client_id=client_id, sub=sub)

    def list_agent_registrations(self, client_id: str | None = None) -> list[AgentRegistration]:
        refuse_nul(client_id)
        return self._list("agent_registrations", client_id=client_id)

    # -- ConfigState (storage.md §3.2) -------------------------------------------------------
    def get_config(self) -> dict[str, Any]:
        rows = self._all("SELECT key, value FROM config ORDER BY write_order")
        return {k: json.loads(v) for k, v in rows}

    def put_config(self, key: str, value: Any) -> None:
        refuse_nul(key)
        self._write(_PUT["config"], (key, json.dumps(value)))

    # -- ConfirmState (storage.md §3.3) ------------------------------------------------------
    def put_challenge(self, challenge: ConfirmChallenge) -> None:
        refuse_nul(challenge["id"], challenge["expires_at"])
        self._write("INSERT INTO challenges (id, expires_at, doc) VALUES (%s, %s, %s)",
                    (challenge["id"], challenge["expires_at"], json.dumps(challenge)))

    def forget_challenges(self, expired_before: str) -> None:
        refuse_nul(expired_before)
        self._write("DELETE FROM challenges WHERE expires_at < %s", (expired_before,))

    def spend_challenge(self, challenge_id: str) -> ConfirmChallenge | None:
        """Mark it spent and return it as it stood: of two concurrent spends, one sees it fresh."""
        refuse_nul(challenge_id)
        with self.atomic():
            rows = self._all("SELECT spent, doc FROM challenges WHERE id = %s", (challenge_id,))
            if not rows:
                return None
            self.db.execute("UPDATE challenges SET spent = true WHERE id = %s", (challenge_id,))
        return {**json.loads(rows[0][1]), "spent": rows[0][0]}

    def put_credential(self, credential: ConfirmCredential) -> None:
        refuse_nul(credential["id"], credential["person"])
        self._write(_PUT["credentials"],
                    (credential["id"], credential["person"], json.dumps(credential)))

    def get_credential(self, credential_id: str) -> ConfirmCredential | None:
        refuse_nul(credential_id)
        return self._get("credentials", id=credential_id)

    def list_credentials(self, person: str | None = None) -> list[ConfirmCredential]:
        refuse_nul(person)
        return self._list("credentials", person=person)

    # -- UploadState (storage.md §3.4) -------------------------------------------------------
    def put_upload(self, upload: UploadRecord) -> None:
        # Rewritten in place, as sqlite's UPDATE: its open order, principal and spends stand.
        refuse_nul(upload["id"], upload["principal"])
        self._write("INSERT INTO uploads (id, principal, doc) VALUES (%s, %s, %s) "
                    "ON CONFLICT (id) DO UPDATE SET doc = excluded.doc",
                    (upload["id"], upload["principal"], json.dumps(upload)))

    def get_upload(self, upload_id: str) -> UploadRecord | None:
        refuse_nul(upload_id)
        return self._get("uploads", id=upload_id)

    def list_uploads(self, principal: str | None = None) -> list[UploadRecord]:
        refuse_nul(principal)
        return self._list("uploads", principal=principal)

    def spend_upload(self, upload_id: str, step: str) -> bool:
        refuse_nul(upload_id)
        column = {"bytes": "bytes_spent", "item": "item_spent"}[step]
        cur = self._write(f"UPDATE uploads SET {column} = true WHERE id = %s AND NOT {column}",
                          (upload_id,))
        return cur.rowcount == 1

    # -- GrantState (storage.md §3.5) --------------------------------------------------------
    def spend_grant(self, sig_hash: str, expires_at: str) -> bool:
        """Record a spend, committed at once: of two concurrent spends of one grant, exactly one
        inserts. Refused inside `atomic()` or any open transaction, whose rollback would undo it."""
        refuse_nul(sig_hash, expires_at)
        if self._depth or self.db.info.transaction_status != pq.TransactionStatus.IDLE:
            raise RuntimeError("a grant is spent outside any transaction")
        cur = self._write("INSERT INTO spent_grants (sig_hash, expires_at) VALUES (%s, %s) "
                          "ON CONFLICT DO NOTHING", (sig_hash, expires_at))
        return cur.rowcount == 1

    def forget_grants(self, expired_before: str) -> None:
        refuse_nul(expired_before)
        self._write("DELETE FROM spent_grants WHERE expires_at < %s", (expired_before,))
