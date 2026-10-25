# Copyright 2026 Ali Sasanian
# SPDX-License-Identifier: LicenseRef-PolyForm-Strict-1.0.0
"""The audit chain's half of `ContainerState` (storage.md §3, events.md §2-§4) on every backend:
the store assigns `seq`, accepts one successor per entry, gives back exactly what was hashed, and
refuses an update or a delete. `_hash` is events.md §3 spelled out, not the ledger's code."""

from __future__ import annotations

import hashlib
import json
import threading

import pytest

from egzos._types import GENESIS_HASH
from egzos.backends.base import ChainConflict
from egzos.ledger import Ledger

#: What a store must hand back exactly: non-ASCII, nesting, a float, an empty object, a NUL.
DETAILS = {"name": "café ☕", "nested": {"b": [1, 2.5, None], "a": {}}, "nul": "\u0000"}


def _hash(entry):
    """events.md §3: sha256(prev_hash || canonical(entry minus `hash` and minus `seq`))."""
    body = {k: v for k, v in entry.items() if k not in ("hash", "seq")}
    canon = json.dumps(body, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256((entry["prev_hash"] + canon).encode("utf-8")).hexdigest()


def _entry(prev_hash, event="context.fetch", **details):
    body = {"ts": "2026-10-24T00:00:00Z", "event": event, "actor": "self",
            "principal": "interactive", "subject": None, "scope": None, "details": details,
            "prev_hash": prev_hash}
    return {**body, "hash": _hash(body)}


def test_the_store_assigns_seq_and_returns_the_stored_entry(backend):
    entry = _entry(GENESIS_HASH)
    first = backend.audit_append(entry)
    assert "seq" not in entry and first == {**entry, "seq": first["seq"]}
    assert type(first["seq"]) is int
    second = backend.audit_append(_entry(first["hash"]))
    assert second["seq"] > first["seq"]  # monotonic (events.md §2); gaps are allowed
    assert backend.audit_last() == second
    assert list(backend.audit_iter()) == [first, second]
    assert backend.audit_tail(1) == [second]
    assert backend.audit_tail(5) == [first, second]


def test_an_entry_read_back_re_hashes_to_its_own_hash(make_backend):
    backend = make_backend()
    head = backend.audit_append(_entry(GENESIS_HASH, **DETAILS))
    backend.audit_append(_entry(head["hash"], event="blob.pull"))
    entries = list(make_backend().audit_iter())  # what was stored, not what a connection holds
    assert len(entries) == 2 and [e["hash"] for e in entries] == [_hash(e) for e in entries]
    assert entries[0] == head
    assert Ledger(make_backend()).verify()["ok"] is True


def test_a_second_successor_of_one_entry_raises_chain_conflict(backend):
    head = backend.audit_append(_entry(GENESIS_HASH))
    with pytest.raises(ChainConflict):
        backend.audit_append(_entry(GENESIS_HASH, event="blob.pull"))
    assert list(backend.audit_iter()) == [head]
    assert backend.audit_append(_entry(head["hash"]))["prev_hash"] == head["hash"]  # re-chained


def test_two_connections_appending_after_one_head_produce_exactly_one_winner(make_backend):
    head = make_backend().audit_append(_entry(GENESIS_HASH))
    outcomes: list[str] = []
    gate = threading.Barrier(2, timeout=10)

    def append(event):
        b = make_backend()
        entry = _entry(b.audit_last()["hash"], event=event)  # both chain onto the same head
        gate.wait()
        try:
            outcomes.append(b.audit_append(entry)["event"])
        except ChainConflict:
            outcomes.append("conflict")

    threads = [threading.Thread(target=append, args=(e,)) for e in ("context.fetch", "blob.pull")]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert len(outcomes) == 2 and outcomes.count("conflict") == 1
    chain = list(make_backend().audit_iter())
    assert [e["prev_hash"] for e in chain] == [GENESIS_HASH, head["hash"]]
    assert chain[1]["event"] in outcomes


@pytest.mark.parametrize("act", ["update", "delete"])
def test_the_store_refuses_an_update_or_a_delete_of_an_entry(backend, refuses, act):
    """events.md §4 item 1: enforced by the store, not only by the code that writes."""
    head = backend.audit_append(_entry(GENESIS_HASH))
    assert refuses(backend, act, head["seq"]) is True
