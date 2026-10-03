# Copyright 2026 Ali Sasanian
# SPDX-License-Identifier: Apache-2.0
"""
The store: add, get, inbox. Every write lands UNVERIFIED (CLAUDE.md invariant 5; v0.3 §5) and is
auto-titled at write time. `add` with no scope → the inbox (v0.3 §4). `add ./file` → artifact:
metadata item + content-addressed blob. Pure capture (R11): every unaddressed add opens an
auto-created, auto-titled thread inside the inbox.
"""

from __future__ import annotations

import mimetypes
from collections.abc import Callable
from pathlib import Path
from typing import Any

from egzos._ids import ulid
from egzos.backends.base import Backend
from egzos.ledger import Ledger
from egzos.model import INLINE_BLOB_LIMIT, KINDS, ContextItem, Node, Token, now_iso
from egzos.store.autotitle import DegradedTitler, Titler
from egzos.store.blobs import BlobStore
from egzos.store.nodes import NodeService


class StoreError(Exception):
    pass


class Store:
    def __init__(
        self,
        backend: Backend,
        ledger: Ledger,
        nodes: NodeService,
        blobs: BlobStore,
        titler: Titler | None = None,
    ):
        self.backend = backend
        self.ledger = ledger
        self.nodes = nodes
        self.blobs = blobs
        self.titler = titler or DegradedTitler()
        # coverage predicate, wired by the container once the trust engine exists
        self.covers: Callable[[Token, Node], bool] | None = None

    # -- add ------------------------------------------------------------------------------
    def add(
        self,
        *,
        body: str | None = None,
        file: Path | None = None,
        kind: str | None = None,
        scope: Node | None = None,
        key: str | None = None,
        tags: list[str] | None = None,
        token: Token,
        actor: str,
        principal: str,
    ) -> ContextItem:
        if not token.has("remember"):
            raise StoreError("token lacks `remember`")
        if body is None and file is None:
            raise StoreError("nothing to add")
        kind = kind or ("artifact" if file else "memory")
        if kind not in KINDS:
            raise StoreError(f"unknown kind {kind!r}")

        # Pure capture (R11): no scope → a fresh auto-titled thread inside the inbox.
        opened_thread: Node | None = None
        if scope is None:
            inbox = self.nodes.inbox()
            assert inbox is not None
            opened_thread = Node(id=ulid(), type="thread", name="", parent=inbox.id)
            scope = opened_thread

        # remember is same-scope only (v0.3 §5): the token must cover where the write lands.
        anchor = scope if opened_thread is None else self.nodes.inbox()
        if self.covers is not None and anchor is not None and not self.covers(token, anchor):
            raise StoreError("scope not found")  # silence-not-errors

        content: dict[str, Any] = {}
        if file is not None:
            data = Path(file).read_bytes()
            sha = self.blobs.put(data)
            mime = mimetypes.guess_type(str(file))[0] or "application/octet-stream"
            content.update(sha256=sha, mime=mime, size=len(data), filename=Path(file).name)
            if len(data) <= INLINE_BLOB_LIMIT and mime.startswith("text/"):
                content["inline"] = data.decode("utf-8", errors="replace")
            self.ledger.append(
                "blob.put",
                actor=actor,
                principal=principal,
                subject=sha,
                scope=scope.id,
                size=len(data),
                mime=mime,
            )
            title_body = content.get("inline")
        else:
            content["body"] = body
            title_body = body
        content["auto_title"] = self.titler.title(
            body=title_body, filename=content.get("filename"), mime=content.get("mime")
        )
        content["title_engine"] = self.titler.name

        ts = now_iso()
        item = ContextItem(
            id=ulid(),
            kind=kind,
            scope=scope.id,
            key=key,
            content=content,
            tags=tags or [],
            provenance={
                "actor": actor,
                "principal": principal,
                "client": token.client,
                "derived_from": None,
                "imported_from": None,
                "approved_by": None,
            },
            trust={"status": "unverified"},
            lifecycle={"created_at": ts, "updated_at": ts, "version": 1},
            visibility={"ring": scope.type},
        )
        if opened_thread is not None:
            opened_thread.name = content["auto_title"][:40]
            self.backend.put_node(opened_thread)
            self.ledger.append(
                "node.create",
                actor=actor,
                principal=principal,
                subject=opened_thread.id,
                scope=opened_thread.parent,
                type="thread",
                auto=True,
            )
        self.backend.put(item)
        self.ledger.append(
            "item.add",
            actor=actor,
            principal=principal,
            subject=item.id,
            scope=scope.id,
            kind=kind,
            status="unverified",
            auto_title=content["auto_title"],
        )
        return item

    # -- read -----------------------------------------------------------------------------
    def get(self, item_id: str) -> ContextItem | None:
        return self.backend.get(item_id)

    def inbox_items(self) -> list[tuple[Node, ContextItem]]:
        """Everything captured but not yet wrapped: items in the inbox's auto-threads."""
        inbox = self.nodes.inbox()
        if not inbox:
            return []
        out: list[tuple[Node, ContextItem]] = []
        for thread in self.backend.list_nodes(parent=inbox.id):
            for item in self.backend.query([thread.id]):
                out.append((thread, item))
        for item in self.backend.query([inbox.id]):
            out.append((inbox, item))
        return out

    def blob_pull(
        self, item: ContextItem, *, token: Token, actor: str, principal: str
    ) -> bytes | None:
        """Artifact download IS fetch (v0.3 §5); the pull is its own audit event."""
        if not token.has("fetch"):
            return None
        sha = item.content.get("sha256")
        if not sha:
            return None
        data = self.blobs.get(sha)
        if data is not None:
            self.ledger.append(
                "blob.pull",
                actor=actor,
                principal=principal,
                subject=item.id,
                scope=item.scope,
                sha256=sha,
                size=len(data),
            )
        return data
