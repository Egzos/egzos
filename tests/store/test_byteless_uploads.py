# Copyright 2026 Ali Sasanian
# SPDX-License-Identifier: LicenseRef-PolyForm-Strict-1.0.0
"""rest.md §4.4 item 1 on every backend: a `client` principal's uploads whose bytes have not
arrived are its own to count, at most 4, and hold no slot of its person's 16 until their bytes are
staged. Both caps and the open's record are one atomic step, and the step that records an agent's
staged bytes counts the 16 again under the same lock: of two concurrent acts that together pass a
cap, at most one is recorded. Each act runs on a connection of its own, as two processes would."""

from __future__ import annotations

import hashlib
import threading
import time
from collections.abc import Callable
from typing import Any

import pytest

from egzos._ids import ulid
from egzos.identity import principal_id
from egzos.ledger import Ledger
from egzos.model import Node, Token
from egzos.store.items import Store
from egzos.store.nodes import NodeService
from egzos.store.uploads import AGENT_BYTELESS_MAX, MAX_HELD, TooManyUploads, Uploads

DATA = b"agent bytes"
SHAPE = {"name": "n", "mime": "a/b", "size": len(DATA), "sha256": hashlib.sha256(DATA).hexdigest()}
PLACE = Node(id=ulid(), type="project", name="p", parent=None)
ALICE = Token(id=principal_id(None, "alice"), principal="interactive", owner="user:alice",
              client="box", capabilities=["remember"], scopes=["*"])
AGENT, OTHER = (Token(id=principal_id(a, "alice"), principal="client", owner=f"agent:{a}",
                      client=a, capabilities=["remember"], scopes=["*"]) for a in ("a1", "a2"))


def _uploads(make_backend: Callable[[], Any], blobs: Any) -> Uploads:
    backend = make_backend()
    ledger = Ledger(backend)
    store = Store(backend, ledger, NodeService(backend, ledger), blobs)
    return Uploads(backend, ledger, blobs, store)


def _race(make_backend, blobs, acts: list[Callable[[Uploads], bool]], widen: str) -> list[bool]:
    """Runs each act at once on a connection of its own, the count it passes slowed."""
    took: list[bool] = []
    gate = threading.Barrier(len(acts))

    def run(act):
        uploads = _uploads(make_backend, blobs)
        count = getattr(uploads, widen)

        def slow(record):  # widens the window between the count and the write
            time.sleep(0.005)
            return count(record)

        setattr(uploads, widen, slow)
        gate.wait()
        took.append(act(uploads))

    threads = [threading.Thread(target=run, args=(act,)) for act in acts]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    return sorted(took)


def _open(token: Token) -> Callable[[Uploads], bool]:
    def act(uploads: Uploads) -> bool:
        try:
            uploads.open(token, scope=PLACE, **SHAPE)
        except TooManyUploads:
            return False
        return True
    return act


def test_two_concurrent_byteless_opens_never_both_take_an_agents_fourth(make_backend, blobs):
    first = _uploads(make_backend, blobs)
    for _ in range(AGENT_BYTELESS_MAX - 1):
        first.open(AGENT, scope=PLACE, **SHAPE)
    assert _race(make_backend, blobs, [_open(AGENT), _open(AGENT)], "byteless") == [False, True]
    assert len(first.backend.list_uploads(principal=AGENT.id)) == AGENT_BYTELESS_MAX


@pytest.mark.parametrize("rival", ["its person's open", "another agent's bytes"])
def test_an_agents_bytes_and_a_rival_never_both_take_the_sixteenth(make_backend, blobs, rival):
    first = _uploads(make_backend, blobs)
    for _ in range(MAX_HELD - 1):
        first.open(ALICE, scope=PLACE, **SHAPE)

    def put(token: Token) -> Callable[[Uploads], bool]:
        waiting = first.open(token, scope=PLACE, **SHAPE)["id"]  # holds no slot yet
        return lambda uploads: uploads.put(token, waiting, DATA) == "staged"

    other = _open(ALICE) if rival == "its person's open" else put(OTHER)
    assert _race(make_backend, blobs, [put(AGENT), other], "holds") == [False, True]
    held = [r for r in first.backend.list_uploads() if first.holds(r)]
    assert len(held) == MAX_HELD


def test_an_agents_bytes_refused_at_the_sixteen_leave_its_upload_byteless(make_backend, blobs):
    uploads = _uploads(make_backend, blobs)
    for _ in range(MAX_HELD):
        uploads.open(ALICE, scope=PLACE, **SHAPE)
    waiting = uploads.open(AGENT, scope=PLACE, **SHAPE)["id"]
    assert uploads.put(AGENT, waiting, DATA[:-1]) == "too_many_uploads"  # before its length
    entry = uploads.ledger.tail(1)[-1]
    assert (entry["event"], entry["details"]["reason"]) == ("upload.put", "too_many_uploads")
    record = uploads.backend.get_upload(waiting)
    assert record["staged"] is False and uploads.byteless(record)
    assert uploads.backend.spend_upload(waiting, "bytes") is True  # the bytes step was not spent
