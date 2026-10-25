# Copyright 2026 Ali Sasanian
# SPDX-License-Identifier: LicenseRef-PolyForm-Strict-1.0.0
"""`TrustEngine.quarantine` (container.md §5): `curate` over a covered item, and its checks run
again under the lock, against the item as it stands there."""

from __future__ import annotations

import pytest

from egzos.container import OWNER, Container
from egzos.trust import TrustError

KW = {"actor": OWNER, "principal": "interactive"}


@pytest.fixture
def box(tmp_path):
    c = Container(tmp_path)
    owner = c.init()
    return c, owner, c.store.add(body="note", token=owner, **KW)


def _quarantines(c: Container) -> list[dict]:
    return [e for e in c.ledger.tail(100) if e["event"] == "trust.quarantine"]


def test_an_already_quarantined_item_keeps_its_quarantine(box):
    c, owner, item = box
    assert c.trust.quarantine(item, token=owner, actor=OWNER, reason="first") == [item.id]
    with pytest.raises(TrustError, match="^already quarantined$"):
        c.trust.quarantine(item, token=owner, actor=OWNER, reason="second")
    assert c.store.get(item.id).trust["reason"] == "first"
    assert len(_quarantines(c)) == 1


def test_quarantine_needs_curate(box):
    c, _, item = box
    reader = c.auth.mint(principal="client", owner=OWNER, client="bot", role="reader",
                         scopes=["*"], actor=OWNER, by_principal="interactive")
    with pytest.raises(TrustError, match="needs `curate`"):
        c.trust.quarantine(item, token=reader, actor="bot", reason="x")
    assert c.store.get(item.id).status == "unverified" and not _quarantines(c)


def test_coverage_is_checked_again_after_the_item_is_read_again(box, monkeypatch):
    c, owner, item = box
    fresh = c.trust._fresh

    def lapse_then_read(*args, **kwargs):
        owner.expires_at = "2000-01-01T00:00:00Z"  # live at the first check, past by the second
        return fresh(*args, **kwargs)

    monkeypatch.setattr(c.trust, "_fresh", lapse_then_read)
    with pytest.raises(TrustError, match="^not found$"):
        c.trust.quarantine(item, token=owner, actor=OWNER, reason="x")
    assert c.store.get(item.id).status == "unverified" and not _quarantines(c)
