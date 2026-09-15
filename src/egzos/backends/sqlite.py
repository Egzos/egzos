# Copyright 2026 Ali Sasanian
# SPDX-License-Identifier: Apache-2.0
"""sqlite backend — what `pip install` gives everyone (v0.5 §E). JSON documents in typed rows."""

from __future__ import annotations

import json
import sqlite3
from collections.abc import Iterable, Iterator
from pathlib import Path
from typing import Any

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
CREATE TABLE IF NOT EXISTS tokens (id TEXT PRIMARY KEY, doc TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS proposals (id TEXT PRIMARY KEY, status TEXT NOT NULL, doc TEXT NOT NULL);
-- append-only is a PROPERTY of the design (a3-ledger charter): no update or delete path exists.
CREATE TRIGGER IF NOT EXISTS audit_no_update BEFORE UPDATE ON audit
  BEGIN SELECT RAISE(ABORT, 'audit is append-only'); END;
CREATE TRIGGER IF NOT EXISTS audit_no_delete BEFORE DELETE ON audit
  BEGIN SELECT RAISE(ABORT, 'audit is append-only'); END;
"""


class SqliteBackend:
    def __init__(self, path: Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.db = sqlite3.connect(str(self.path))
        self.db.execute("PRAGMA journal_mode=WAL")
        self.db.execute("PRAGMA foreign_keys=ON")
        self.db.executescript(_SCHEMA)

    # -- nodes --------------------------------------------------------------------------
    def put_node(self, node: Node) -> None:
        self.db.execute(
            "INSERT OR REPLACE INTO nodes(id,type,name,parent,doc) VALUES(?,?,?,?,?)",
            (node.id, node.type, node.name, node.parent, json.dumps(node.to_dict())),
        )
        self.db.commit()

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
        self.db.commit()

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
        cur = self.db.execute(
            "INSERT INTO audit(ts,hash,prev_hash,doc) VALUES(?,?,?,?)",
            (entry["ts"], entry["hash"], entry["prev_hash"], json.dumps(entry)),
        )
        self.db.commit()
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
            (token.id, json.dumps(token.to_dict())),
        )
        self.db.commit()

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
        self.db.commit()

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
