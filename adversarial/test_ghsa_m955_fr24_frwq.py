# Copyright 2026 Ali Sasanian
# SPDX-License-Identifier: LicenseRef-PolyForm-Strict-1.0.0
"""GHSA-m955-fr24-frwq: a read-then-write that must not lose a concurrent writer's update runs
inside one `atomic()` block, which holds the container's write lock from before its read and reads
the record again inside it. The concurrent writer here is a second `Container` on the same home:
a second connection, as a second process has."""

from __future__ import annotations

import contextlib
import threading

import pytest

from egzos.container import OWNER, Container
from egzos.trust import TrustError

pytestmark = pytest.mark.adversarial

KW = {"actor": OWNER, "principal": "interactive"}


def _events(c: Container, event: str) -> list[dict]:
    return [e for e in c.ledger.tail(100) if e["event"] == event]


def test_ghsa_m955_fr24_frwq_token_record(tmp_path, monkeypatch):
    c = Container(tmp_path)
    c.init()
    token = c.auth.mint(principal="client", owner=OWNER, client="agent", role="reader",
                        scopes=["*"], actor=OWNER, by_principal="interactive")
    other = Container(tmp_path)
    revoker = threading.Thread(target=other.auth.revoke, args=(token.id,), kwargs=KW)
    read = c.backend.get_token

    def read_then_wait(token_id):
        current = read(token_id)
        revoker.start()  # the other connection writes between this read and the write after it
        revoker.join(0.5)  # a writer that waits for the lock is not waited for here
        return current

    with monkeypatch.context() as m:
        m.setattr(c.backend, "get_token", read_then_wait)
        assert c.auth.use(token.secret).id == token.id
    revoker.join()
    stored = c.backend.get_token(token.id)
    assert not stored.live and stored.last_used is not None  # both writes stand
    assert c.auth.use(token.secret) is None
    assert [e["subject"] for e in _events(c, "token.revoke")] == [token.id]


@pytest.fixture
def window(tmp_path):
    """An item, its first read, and a second connection to write in between."""
    c = Container(tmp_path)
    owner = c.init()
    here, there = (c.nodes.create("project", name, c.nodes.user_root(), token=owner, **KW)
                   for name in ("here", "there"))
    item = c.store.add(body="note", scope=here, token=owner, **KW)
    return c, owner, c.store.get(item.id), there, Container(tmp_path)


def test_ghsa_m955_fr24_frwq_item_record_tombstone(window):
    c, owner, read, _, other = window
    assert other.uploads.tombstone(owner, read.id) is not None
    with pytest.raises(TrustError, match="^not found$"):
        c.trust.quarantine(read, token=owner, actor=OWNER, reason="x")
    assert c.store.get(read.id) is None
    assert not _events(c, "trust.quarantine")


def test_ghsa_m955_fr24_frwq_item_record_scope(window):
    c, owner, read, there, other = window
    assert other.trust.move(other.store.get(read.id), there, token=owner, actor=OWNER)["moved"]
    with pytest.raises(TrustError, match="^not found$"):
        c.trust.quarantine(read, token=owner, actor=OWNER, reason="x")
    stored = c.store.get(read.id)
    assert (stored.scope, stored.status) == (there.id, "unverified")
    assert not _events(c, "trust.quarantine")


@pytest.mark.parametrize("write", ["tombstone", "move"])
def test_ghsa_m955_fr24_frwq_item_record_under_the_lock(window, monkeypatch, write):
    c, owner, read, there, other = window

    def land():
        with contextlib.suppress(TrustError):  # a quarantined item does not move
            if write == "tombstone":
                other.uploads.tombstone(owner, read.id)
            else:
                other.trust.move(other.store.get(read.id), there, token=owner, actor=OWNER)

    writer = threading.Thread(target=land)
    get = c.backend.get

    def read_then_wait(item_id):
        current = get(item_id)
        if writer.ident is None:  # the first read only: quarantine reads again for its answer
            writer.start()
            writer.join(0.5)  # a writer that waits for the lock is not waited for here
        return current

    with monkeypatch.context() as m:
        m.setattr(c.backend, "get", read_then_wait)
        assert c.trust.quarantine(read, token=owner, actor=OWNER, reason="x") == [read.id]
    writer.join()
    stored = c.store.get(read.id)
    assert (stored.scope, stored.status) == (read.scope, "quarantined")
    assert not _events(c, "item.tombstone") and not _events(c, "item.move")
    assert len(_events(c, "trust.quarantine")) == 1
