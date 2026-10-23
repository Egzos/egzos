# Copyright 2026 Ali Sasanian
# SPDX-License-Identifier: LicenseRef-PolyForm-Strict-1.0.0
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
from urllib.parse import urlencode

from egzos._ids import ulid
from egzos._types import CONTAINER_CONFIG_DEFAULTS, BlobGrant, ContainerConfig, UploadRecord
from egzos.backends.base import Backend
from egzos.ledger import Ledger
from egzos.model import KINDS, ContextItem, Node, Token, now_iso
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
        config: ContainerConfig | None = None,
    ):
        self.backend = backend
        self.ledger = ledger
        self.nodes = nodes
        self.blobs = blobs
        self.titler = titler or DegradedTitler()
        # F5/F30 (#271): the container's `blobs_inline_max_bytes`, never a second constant.
        # `config` may omit the key (absence tested by absence, per `_types.py`'s own loading
        # rule) — `CONTAINER_CONFIG_DEFAULTS` is the fallback either way.
        default_limit = CONTAINER_CONFIG_DEFAULTS["blobs_inline_max_bytes"]
        self.inline_blob_limit = (
            default_limit if config is None else config.get("blobs_inline_max_bytes", default_limit)
        )
        # coverage predicate, wired by the container once the trust engine exists
        self.covers: Callable[[Token, Node], bool] | None = None
        # the serving predicate search uses (`find.shown`), wired by the container likewise
        self.shown: Callable[[Token, ContextItem, Node], bool] | None = None
        # whether an artifact item's own bytes are still staged, wired by the container
        self.staged: Callable[[str], bool] = lambda item_id: False

    # -- add ------------------------------------------------------------------------------
    def add(
        self,
        *,
        body: str | None = None,
        file: Path | None = None,
        upload: UploadRecord | None = None,
        promote: bool = False,
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
        if body is None and file is None and upload is None:
            raise StoreError("nothing to add")
        kind = kind or ("artifact" if file or upload else "memory")
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
            if len(data) <= self.inline_blob_limit and mime.startswith("text/"):
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
        elif upload is not None:
            # rest.md §4.4 item 3: the bytes are staged already. A person's are promoted now; an
            # agent's stay staged, unaddressable, until a person promotes the item (§4).
            sha = upload["sha256"]
            content.update(sha256=sha, mime=upload["mime"], size=upload["size"],
                           filename=upload["name"])
            if promote and self.blobs.promote(sha):
                self.ledger.append("blob.put", actor=actor, principal=principal, subject=sha,
                                   scope=scope.id, size=upload["size"], mime=upload["mime"])
                if upload["size"] <= self.inline_blob_limit and upload["mime"].startswith("text/"):
                    data = self.blobs.get(sha) or b""
                    content["inline"] = data.decode("utf-8", errors="replace")
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
            # A name is one path segment: a "/" in writer-supplied text would split it.
            opened_thread.name = content["auto_title"][:40].replace("/", "-")
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
        """Artifact download IS fetch (v0.3 §5): the same capability, coverage AND serving check
        as a fetch, one silent None when any fails; the pull is its own audit event. Serving here
        is search's own predicate, so bytes never leave by a path the item itself would not: a
        quarantined or tombstoned item never, an unpromoted rule only to the curator (#135)."""
        if not token.has("fetch"):
            return None
        node = self.backend.get_node(item.scope)
        if node is None or self.covers is None or not self.covers(token, node):
            return None
        if item.status == "quarantined" or item.lifecycle.get("tombstoned"):
            return None
        if self.staged(item.id):
            return None  # its own bytes are undecided, whatever the address holds (a1r on #291)
        if self.shown is None or not self.shown(token, item, node):
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

    @staticmethod
    def grant_url(grant: BlobGrant) -> str:
        """Render a `BlobGrant` minted by Trust into its redemption URL (rest.md §6). Store decides
        nothing here, and mints nothing on its own authority (F5)."""
        query = {k: grant[k] for k in ("item", "token", "expires_at", "sig")}  # type: ignore[literal-required]
        return f"/v1/blobs/{grant['sha256']}?{urlencode(query)}"
