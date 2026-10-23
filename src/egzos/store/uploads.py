# Copyright 2026 Ali Sasanian
# SPDX-License-Identifier: LicenseRef-PolyForm-Strict-1.0.0
"""
Artifact upload (spec/contracts/rest.md §4.4): open, bytes, item, and the discard of an orphan.

An upload is bound to the principal that opened it (`Token.id`) and is live for an hour. Its bytes
are staged, never `put`, so staging never answers whether the content already exists; its item is
written `unverified` like every write. A person's bytes are promoted with the item, an agent's stay
staged until a person promotes it. The bytes and the item are two spends of one id, each an atomic
check-and-mark. Nothing staged is deleted on a timer (v0.7 §Z): an upload that expired with its
bytes staged is an orphan, listed to its opener, an agent's to the person it serves, and to an admin
until one of them discards it. What a person holds is capped once for them and every agent serving
them (v0.7 §AC).
"""

from __future__ import annotations

import calendar
import re
import time
from collections.abc import Callable
from typing import Any

from egzos._ids import ulid
from egzos._types import UploadRecord
from egzos.backends.base import Backend
from egzos.ledger import Ledger
from egzos.model import ContextItem, Node, Token
from egzos.store.blobs import BlobStore
from egzos.store.items import Store

#: §4.4 item 2: an upload's id is live for an hour after it is opened.
UPLOAD_TTL_SECONDS = 3600
#: §4.4 item 1: uploads a person may hold open, orphaned, or written but still staged, counting
#: every agent serving them; a container `Token` is a person of its own.
MAX_HELD = 16
NAME_MAX = 255
MIME_MAX = 127
#: A `type/subtype` token (RFC 6838's restricted names), no parameters.
_MIME = re.compile(r"[A-Za-z0-9][A-Za-z0-9!#$&^_.+-]*/[A-Za-z0-9][A-Za-z0-9!#$&^_.+-]*")
_DIGEST = re.compile(r"[0-9a-f]{64}")
_ISO = "%Y-%m-%dT%H:%M:%SZ"


class TooManyUploads(Exception):
    """§4.4 item 1: the caller's person already holds `MAX_HELD` uploads. A fact about their own."""


def person_of(principal: str, actor: str) -> str:
    """Whose upload it is (§4.4, v0.7 §AC), from the opener's `Token.id` and `owner`, both recorded
    at open. An agent's principal is `agent:<client_id>:<sub>` and its owner `agent:<client_id>`
    (identity.md §3a), so it serves `user:<sub>`: the owner is stripped as a prefix, never split on
    a colon. Anything else is its own person: a person is `user:<sub>`, and a container `Token`'s id
    is a ULID, whatever owner it names."""
    if principal.startswith("agent:") and principal.startswith(actor + ":"):
        return "user:" + principal[len(actor) + 1:]
    return principal


def valid_open(name: Any, mime: Any, size: Any, sha256: Any, *, limit: int) -> bool:
    """§4.4 item 1's shape, checked before any lookup: the same answer for every container."""
    return (
        isinstance(name, str) and 1 <= len(name) <= NAME_MAX
        and isinstance(mime, str) and len(mime) <= MIME_MAX and _MIME.fullmatch(mime) is not None
        and isinstance(size, int) and not isinstance(size, bool) and 0 <= size <= limit
        and isinstance(sha256, str) and _DIGEST.fullmatch(sha256) is not None
    )


class Uploads:
    def __init__(
        self,
        backend: Backend,
        ledger: Ledger,
        blobs: BlobStore,
        store: Store,
        *,
        clock: Callable[[], float] = time.time,
    ):
        self.backend = backend
        self.ledger = ledger
        self.blobs = blobs
        self.store = store
        self.clock = clock

    def _iso(self, at: float) -> str:
        return time.strftime(_ISO, time.gmtime(at))

    def expired(self, record: UploadRecord) -> bool:
        return calendar.timegm(time.strptime(record["expires_at"], _ISO)) <= self.clock()

    def _staged_item(self, record: UploadRecord) -> ContextItem | None:
        """The item written from `record` while its bytes are still staged: an agent's artifact
        nobody has promoted or tombstoned yet."""
        if record["item"] is None or record["promoted"]:
            return None
        item = self.backend.get(record["item"])  # a tombstoned item reads as absent
        return item if item is not None and item.status != "verified" else None

    def holds(self, record: UploadRecord) -> bool:
        """Whether `record` takes one of its person's `MAX_HELD` slots: open, orphaned, or written
        as an artifact whose bytes are still staged. A person's decision frees a slot."""
        if record["discarded"]:
            return False
        if record["item"] is None:
            return record["staged"] or not self.expired(record)
        return self._staged_item(record) is not None

    def orphan(self, record: UploadRecord) -> bool:
        return (not record["discarded"] and record["staged"] and record["item"] is None
                and self.expired(record))

    def opened(self, token: Token, record: UploadRecord) -> bool:
        """Whether `token` opened `record`: the `Token.id` and `owner` recorded at open."""
        return record["principal"] == token.id and record["actor"] == token.owner

    def answers_to(self, token: Token, record: UploadRecord) -> bool:
        """Whether `record` is listed to and discarded by `token` short of admin: its opener, and
        once it is an orphan, the person an agent opener serves (§4.4: an open upload is its
        opener's). Never another agent of that person."""
        return self.opened(token, record) or (
            self.orphan(record) and token.id == person_of(record["principal"], record["actor"]))

    # -- 1 · open -------------------------------------------------------------------------------
    def open(self, token: Token, *, scope: Node, name: str, mime: str, size: int,
             sha256: str) -> UploadRecord:
        """A new upload of the caller's. Appends nothing: no bytes have moved."""
        now = self.clock()
        record: UploadRecord = {
            "id": ulid(),
            "principal": token.id,
            "actor": token.owner,
            "scope": scope.id,
            "name": name,
            "mime": mime,
            "size": size,
            "sha256": sha256,
            "opened_at": self._iso(now),
            "expires_at": self._iso(now + UPLOAD_TTL_SECONDS),
            "staged": False,
            "item": None,
            "promoted": False,
            "discarded": False,
        }
        mine = person_of(token.id, token.owner)
        with self.backend.atomic():
            # Counted for the person and written under one lock: two concurrent opens never both
            # take slot 16, whichever of that person's principals make them.
            held = [r for r in self.backend.list_uploads()
                    if person_of(r["principal"], r["actor"]) == mine and self.holds(r)]
            if len(held) >= MAX_HELD:
                raise TooManyUploads
            self.backend.put_upload(record)
        return record

    def live(self, token: Token, upload_id: str) -> UploadRecord | None:
        """The caller's own upload, unexpired and not discarded; None for every other case."""
        record = self.backend.get_upload(upload_id)
        if (record is None or not self.opened(token, record) or record["discarded"]
                or self.expired(record)):
            return None
        return record

    # -- 2 · bytes ------------------------------------------------------------------------------
    def put(self, token: Token, upload_id: str, data: bytes | None) -> str | None:
        """Stage the bytes of a live upload of the caller's; `data` is None when what arrived was
        not `size` bytes. Returns `staged` or the refusal's reason (`already`, `length`, `hash`),
        each recorded by `upload.put`; None, and nothing appended, if the id is not the caller's
        live upload."""
        digest = BlobStore.digest(data) if data is not None else None
        with self.backend.atomic():
            record = self.live(token, upload_id)
            if record is None:
                return None
            reason = None
            if record["staged"]:
                reason = "already"
            elif data is None or len(data) != record["size"]:
                reason = "length"
            elif digest != record["sha256"]:
                reason = "hash"
            elif not self.backend.spend_upload(upload_id, "bytes"):
                reason = "already"
            details: dict[str, Any] = {"outcome": "staged"} if reason is None else {
                "outcome": "refused", "reason": reason}
            self.ledger.append("upload.put", actor=token.owner, principal=token.principal,
                               subject=upload_id, scope=record["scope"], size=record["size"],
                               sha256=record["sha256"], **details)
            if reason is None:
                self.backend.put_upload({**record, "staged": True})
                assert data is not None
                self.blobs.stage(data)  # last: a failure before it rolls the spend back
        return reason or "staged"

    # -- 3 · item -------------------------------------------------------------------------------
    def item(self, token: Token, upload_id: str, *, scope: Node | None, key: str | None,
             tags: list[str]) -> ContextItem | None:
        """Write the artifact item from a staged upload of the caller's, once. None when the id is
        not the caller's live, staged, unwritten upload, or `scope` is not the upload's. A token
        that may not write there raises `StoreError`, and nothing is spent."""
        with self.backend.atomic():
            record = self.live(token, upload_id)
            if (record is None or not record["staged"] or record["item"] is not None
                    or (scope is not None and scope.id != record["scope"])):
                return None
            node = self.backend.get_node(record["scope"])
            if node is None or not self.backend.spend_upload(upload_id, "item"):
                return None
            person = token.principal == "interactive"
            written = self.store.add(upload=record, promote=person, kind="artifact", scope=node,
                                     key=key, tags=tags, token=token, actor=token.owner,
                                     principal=token.principal)
            self.backend.put_upload({**record, "item": written.id, "promoted": person})
        return written

    # -- the orphan's discard -------------------------------------------------------------------
    def discard(self, token: Token, upload_id: str, *, admin: bool) -> bool:
        """Discard an upload no item was written from — the caller's own, an orphan an agent serving
        the caller opened, or as an admin anyone's — with its staged bytes, unless another upload
        still holds the same bytes. False is §3's refusal."""
        with self.backend.atomic():
            record = self.backend.get_upload(upload_id)
            if (record is None or record["discarded"] or record["item"] is not None
                    or not (admin or self.answers_to(token, record))):
                return False
            delete = record["staged"] and not self._shared(record)
            self.backend.put_upload({**record, "discarded": True})
            self.ledger.append("upload.discard", actor=token.owner, principal=token.principal,
                               subject=upload_id, scope=record["scope"], size=record["size"],
                               sha256=record["sha256"], opener=record["actor"],
                               bytes_deleted=delete)
            if delete:
                self.blobs.discard(record["sha256"])  # last: a failure before it keeps the bytes
        return True

    def _shared(self, record: UploadRecord) -> bool:
        """Whether another upload still needs the staged bytes at `record`'s address: staging is
        content-addressed, so two uploads of the same bytes share one staged copy."""
        for other in self.backend.list_uploads():
            if (other["id"] != record["id"] and other["sha256"] == record["sha256"]
                    and other["staged"] and not other["discarded"]
                    and (other["item"] is None or self._staged_item(other) is not None)):
                return True
        return False

    # -- what `GET /v1/pending` lists ------------------------------------------------------------
    def orphans(self, token: Token, *, admin: bool) -> list[UploadRecord]:
        """The orphans the caller may see: its own and its agents', or as an admin every
        principal's."""
        return [r for r in self.backend.list_uploads()
                if self.orphan(r) and (admin or self.answers_to(token, r))]

    def staged_items(self) -> set[str]:
        """The ids of artifact items whose bytes are still staged."""
        return {r["item"] for r in self.backend.list_uploads()
                if r["item"] is not None and self._staged_item(r) is not None}
