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
from psycopg import pq
from psycopg.sql import SQL, Identifier

from egzos.backends.base import ChainConflict
from egzos.model import ContextItem, Node, Token

#: How long a writer waits for the container's write lock before it raises: sqlite's busy timeout.
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
-- The container's role holds only what the methods need, and no other role holds anything here:
-- a new schema grants nothing to PUBLIC, but a new function is PUBLIC's to execute.
REVOKE ALL ON FUNCTION audit_refuse() FROM PUBLIC;
GRANT USAGE ON SCHEMA {schema} TO {role};
GRANT USAGE ON SEQUENCE write_order TO {role};
GRANT SELECT, INSERT ON audit TO {role};
GRANT SELECT, INSERT, UPDATE ON nodes, items, tokens, proposals TO {role};
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
        block opened inside this one joins it (storage.md §3.6)."""
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
        except BaseException:
            self.db.rollback()
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
        # postgres keeps no NUL in text, so a value holding one names no row: a read answers the
        # miss sqlite gives for it, never the driver's error (storage.md §5).
        if any(isinstance(a, str) and "\0" in a for a in args):
            return []
        args = [[v for v in a if "\0" not in v] if isinstance(a, list) else a for a in args]
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
        self._write(_PUT["nodes"],
                    (node.id, node.type, node.name, node.parent, json.dumps(node.to_dict())))

    def get_node(self, node_id: str) -> Node | None:
        doc = self._get("nodes", id=node_id)
        return Node.from_dict(doc) if doc is not None else None

    def list_nodes(self, parent: str | None = None, type: str | None = None) -> list[Node]:
        return [Node.from_dict(d) for d in self._list("nodes", parent=parent, type=type)]

    def find_root(self, type: str) -> Node | None:
        rows = self._all("SELECT doc FROM nodes WHERE type = %s AND parent IS NULL "
                         "ORDER BY write_order LIMIT 1", (type,))  # sqlite's first, by rowid
        return Node.from_dict(json.loads(rows[0][0])) if rows else None

    # -- items --------------------------------------------------------------------------
    def put(self, item: ContextItem) -> None:
        self._write(_PUT["items"], (
            item.id, item.kind, item.scope, item.key, item.status,
            bool(item.lifecycle.get("tombstoned")), item.lifecycle.get("created_at", ""),
            json.dumps(item.to_dict()),
        ))

    def get(self, item_id: str) -> ContextItem | None:
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
        if not scopes:
            return []
        sql, args = "SELECT doc FROM items WHERE scope = ANY(%s)", [scopes]
        if not include_tombstoned:
            sql += " AND NOT tombstoned"
        if kinds:
            sql += " AND kind = ANY(%s)"
            args.append(list(kinds))
        if key is not None:
            sql += " AND key = %s"
            args.append(key)
        if statuses:
            sql += " AND status = ANY(%s)"
            args.append(list(statuses))
        if text:
            # sqlite's `doc LIKE` over the stored JSON: ASCII letters fold (COLLATE "C"), `%` and
            # `_` are wildcards, `\` is literal (ESCAPE ''), and the pattern ends at a NUL.
            sql += " AND doc ILIKE %s ESCAPE ''"
            args.append(f"%{text}%".split("\0", 1)[0])
        sql += " ORDER BY created_at DESC, id DESC"  # same-second items by id (storage.md §2)
        return [ContextItem.from_dict(json.loads(r[0])) for r in self._all(sql, args)]

    def tombstone(self, item_id: str) -> bool:
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
        self._write(_PUT["tokens"], (token.id, json.dumps(token.to_dict(with_secret_hash=True))))

    def get_token(self, token_id: str) -> Token | None:
        doc = self._get("tokens", id=token_id)
        return Token.from_dict(doc) if doc is not None else None

    def list_tokens(self) -> list[Token]:
        return [Token.from_dict(d) for d in self._list("tokens")]

    # -- proposals ----------------------------------------------------------------------
    def put_proposal(self, proposal: dict[str, Any]) -> None:
        self._write(_PUT["proposals"],
                    (proposal["id"], proposal["status"], json.dumps(proposal)))

    def get_proposal(self, proposal_id: str) -> dict[str, Any] | None:
        return self._get("proposals", id=proposal_id)

    def list_proposals(self, status: str | None = None) -> list[dict[str, Any]]:
        return self._list("proposals", status=status or None)  # sqlite's `if status:`
