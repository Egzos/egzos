# Copyright 2026 Ali Sasanian
# SPDX-License-Identifier: LicenseRef-PolyForm-Strict-1.0.0
"""`Transactional` (storage.md §3.6) on every backend: the container's one write lock. A nested
block joins the outer one, an exception leaving the outermost block undoes every write in it, a
write outside any block commits alone, a second writer waits for the first's commit and then reads
it, and no grant is spent inside a block (§3.5). Not pinned: how long a writer waits before it
raises, which the contract bounds without naming the bound (ten seconds on sqlite)."""

from __future__ import annotations

import inspect
import threading

import pytest

from egzos._types import GENESIS_HASH, ChainConflict, Transactional
from egzos.ledger import Ledger
from egzos.model import ContextItem, Node

AT = "2026-10-24T00:00:00Z"
WHEN = "2026-10-23T00:05:00.000000Z"
GRANT = {"sub": "alice", "name": "alice", "capabilities": ["fetch"], "scopes": ["*"],
         "created_at": AT, "revoked": False}


class Boom(Exception):
    """An act failing partway."""


def _append(backend):
    return Ledger(backend).append("context.fetch", actor="self", principal="interactive")


def test_the_backend_runs_the_protocol(backend_class):
    expected = list(inspect.signature(Transactional.atomic).parameters)
    assert list(inspect.signature(backend_class.atomic).parameters) == expected


def test_a_nested_block_joins_the_outer_one_and_is_no_savepoint(make_backend):
    backend, other = make_backend(), make_backend()
    with backend.atomic():
        with backend.atomic():
            backend.put_config("inner", 1)
        assert other.get_config() == {}  # leaving the inner block committed nothing
        with pytest.raises(Boom), backend.atomic():
            backend.put_config("raised", 2)
            raise Boom  # it leaves the inner block only, which undoes nothing of its own
        backend.put_config("outer", 3)
    assert other.get_config() == {"inner": 1, "raised": 2, "outer": 3}  # one commit, at the end


def test_an_exception_leaving_the_outermost_block_undoes_every_write_in_it(make_backend):
    backend = make_backend()
    with pytest.raises(Boom), backend.atomic():
        backend.put(ContextItem(id="i", kind="memory", scope="n", content={"body": "b"}))
        backend.put_node(Node(id="n", type="thread", name="t", parent=None, created_at=AT))
        backend.put_config("k", 1)
        _append(backend)
        with backend.atomic():
            backend.put_user_grant(GRANT)
            backend.throttle_incr("rest", "global", "w1")  # its own block joins this one too
        raise Boom
    for reader in (backend, make_backend()):  # undone, not merely unseen by another connection
        assert reader.get("i") is None and reader.get_node("n") is None
        assert reader.get_config() == {} and reader.audit_last() is None
        assert reader.get_user_grant("alice") is None
        assert reader.throttle_count("rest", "global", "w1") == 0
    assert _append(backend)["prev_hash"] == GENESIS_HASH  # the chain goes on from its old head


def test_a_write_outside_any_block_commits_alone(make_backend):
    backend, other = make_backend(), make_backend()
    head = _append(backend)
    backend.put_config("kept", 1)
    assert other.get_config() == {"kept": 1}  # committed at once
    with other.atomic():  # the lock was held for that write only
        other.put_config("other", 2)
    rival = {**{k: v for k, v in head.items() if k != "seq"}, "hash": "0" * 64}  # after GENESIS too
    with pytest.raises(ChainConflict):  # a lone write that fails takes no earlier one with it
        backend.audit_append(rival)
    with pytest.raises(Boom), backend.atomic():  # nor does a later block's rollback
        backend.put_config("kept", "lost")
        raise Boom
    assert other.get_config() == {"kept": 1, "other": 2} and other.audit_last() == head


@pytest.mark.parametrize("lone", [False, True], ids=["block", "lone-write"])
def test_a_second_writer_waits_for_the_first_commit_then_reads_it(make_backend, lone):
    first, second, third = make_backend(), make_backend(), make_backend()
    trying = threading.Event()

    def write():
        trying.set()
        if lone:  # a write outside any block takes the same lock
            second.put_config("second", "waited")
        else:  # the lock is taken before the block's first read
            with second.atomic():
                second.put_config("second", f"saw {second.get_config().get('first')}")

    with first.atomic():
        first.put_config("first", 1)
        waiter = threading.Thread(target=write)
        waiter.start()
        assert trying.wait(10)
        waiter.join(0.5)
        assert waiter.is_alive() and third.get_config() == {}  # held off while the block is open
    waiter.join(10)
    assert not waiter.is_alive()
    assert third.get_config() == {"first": 1, "second": "waited" if lone else "saw 1"}


def test_a_grant_is_refused_in_a_nested_block_and_the_refusal_spends_nothing(make_backend):
    backend, other = make_backend(), make_backend()
    with backend.atomic():
        backend.put_config("k", 1)
        with backend.atomic(), pytest.raises(RuntimeError):
            backend.spend_grant("h", WHEN)  # a rollback would unspend it: refused at any depth
        backend.put_config("j", 2)  # the refusal wrote nothing, and the block goes on
    assert other.get_config() == {"k": 1, "j": 2}
    assert backend.spend_grant("h", WHEN) is True  # the refused spend recorded nothing
    assert other.spend_grant("h", WHEN) is False  # and this one committed alone, at once
