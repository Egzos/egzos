# Copyright 2026 Ali Sasanian
# SPDX-License-Identifier: Apache-2.0
"""
Freeze decisions read off the running code: `publish` gates widening and `organize` gates the
silent move (item 3), a TOCTOU refusal is `approval.stale` not `approval.deny` (item 39), and an
ambiguous path resolves to the most recently ACTIVE node (item 1).
"""

from __future__ import annotations

from pathlib import Path

import pytest

from egzos.container import OWNER, Container
from egzos.trust import TrustError


@pytest.fixture()
def box(tmp_path: Path) -> Container:
    c = Container(tmp_path / "home")
    c.init()
    return c


def _client(box: Container, name: str, role: str, scopes: list[str]):
    return box.auth.mint(
        principal="client",
        owner=OWNER,
        client=name,
        role=role,
        scopes=scopes,
        actor=OWNER,
        by_principal="interactive",
    )


def _tree(box: Container):
    t = box.auth.interactive_token()
    root = box.nodes.user_root()
    org = box.nodes.create("org", "acme", root, token=t, actor=OWNER, principal=t.principal)
    proj = box.nodes.create("project", "p", org, token=t, actor=OWNER, principal=t.principal)
    other = box.nodes.create("project", "q", org, token=t, actor=OWNER, principal=t.principal)
    return t, org, proj, other


# --- item 3: publish gates widening, organize gates the silent move ------------------------------
def test_widening_without_publish_is_refused_and_parks_nothing(box: Container):
    t, org, proj, other = _tree(box)
    _client(box, "watcher", "reader", [other.id])  # `other` has an audience `proj` lacks
    writer = _client(box, "writer", "contributor", [org.id])
    item = box.store.add(body="draft", scope=proj, token=t, actor=OWNER, principal=t.principal)
    with pytest.raises(TrustError, match="needs `publish`"):
        box.trust.move(item, other, token=writer, actor="writer")
    assert box.backend.list_proposals(status="open") == []
    assert box.backend.get(item.id).scope == proj.id


def test_widening_with_publish_parks_a_proposal_for_the_human(box: Container):
    t, org, proj, other = _tree(box)
    _client(box, "watcher", "reader", [other.id])
    op = _client(box, "op", "operator", [org.id])
    item = box.store.add(body="draft", scope=proj, token=t, actor=OWNER, principal=t.principal)
    r = box.trust.move(item, other, token=op, actor="op")
    assert r["moved"] is False and r["gate"] == "pending"
    assert [d["client"] for d in r["proposal"]["audience_delta"]] == ["watcher"]
    assert box.backend.get(item.id).scope == proj.id  # nothing moved before the human's yes


def test_zero_delta_move_without_organize_is_refused_not_parked(box: Container):
    t, org, proj, other = _tree(box)
    writer = _client(box, "writer", "contributor", [org.id])
    item = box.store.add(body="note", scope=proj, token=t, actor=OWNER, principal=t.principal)
    with pytest.raises(TrustError, match="needs `organize`"):
        box.trust.move(item, other, token=writer, actor="writer")
    # a fetch/remember-only token can no longer fill the owner's pending queue (#94)
    assert box.backend.list_proposals(status="open") == []
    assert box.backend.get(item.id).scope == proj.id


def test_zero_delta_move_with_organize_is_silent(box: Container):
    t, org, proj, other = _tree(box)
    op = _client(box, "op", "operator", [org.id])
    item = box.store.add(body="note", scope=proj, token=t, actor=OWNER, principal=t.principal)
    r = box.trust.move(item, other, token=op, actor="op")
    assert r == {"moved": True, "gate": "silent", "audience_delta": []}
    assert box.ledger.tail(1)[0]["event"] == "gate.pass.silent"


# --- item 39: a TOCTOU refusal is its own event --------------------------------------------------
def test_manifest_drift_emits_approval_stale_not_deny(box: Container):
    t, org, proj, other = _tree(box)
    _client(box, "watcher", "reader", [other.id])
    item = box.store.add(body="draft", scope=proj, token=t, actor=OWNER, principal=t.principal)
    pid = box.trust.move(item, other, token=t, actor=OWNER)["proposal"]["id"]
    _client(box, "late", "reader", [other.id])  # the audience changes before the yes
    with pytest.raises(TrustError, match="re-propose"):
        box.trust.execute(pid, token=t, actor=OWNER)
    last = box.ledger.tail(1)[0]
    assert last["event"] == "approval.stale" and last["subject"] == pid
    events = [e["event"] for e in box.ledger.tail(50)]
    assert "approval.deny" not in events
    assert box.ledger.verify()["ok"]


def test_a_human_no_is_still_approval_deny(box: Container):
    t, org, proj, other = _tree(box)
    _client(box, "watcher", "reader", [other.id])
    item = box.store.add(body="draft", scope=proj, token=t, actor=OWNER, principal=t.principal)
    pid = box.trust.move(item, other, token=t, actor=OWNER)["proposal"]["id"]
    box.trust.deny(pid, token=t, actor=OWNER)
    assert box.ledger.tail(1)[0]["event"] == "approval.deny"


# --- item 1: recency means last activity ---------------------------------------------------------
def test_ambiguous_path_resolves_to_the_most_recently_active_node(box: Container):
    t = box.auth.interactive_token()
    root = box.nodes.user_root()
    a = box.nodes.create("org", "a", root, token=t, actor=OWNER, principal=t.principal)
    b = box.nodes.create("org", "b", root, token=t, actor=OWNER, principal=t.principal)
    older = box.nodes.create("project", "health", a, token=t, actor=OWNER, principal=t.principal)
    newer = box.nodes.create("project", "health", b, token=t, actor=OWNER, principal=t.principal)
    older.created_at, newer.created_at = "2026-01-01T00:00:00Z", "2026-02-01T00:00:00Z"
    box.backend.put_node(older)
    box.backend.put_node(newer)
    # created later wins while nothing has been written
    assert box.nodes.resolve_ref("project:health").id == newer.id
    # a write deep in the OLDER node's subtree makes it the active one
    thread = box.nodes.create("thread", "t", older, token=t, actor=OWNER, principal=t.principal)
    thread.created_at = "2026-01-02T00:00:00Z"
    box.backend.put_node(thread)
    item = box.store.add(body="x", scope=thread, token=t, actor=OWNER, principal=t.principal)
    item.lifecycle["updated_at"] = "2026-03-01T00:00:00Z"
    box.backend.put(item)
    assert box.nodes.last_activity(older) == "2026-03-01T00:00:00Z"
    assert box.nodes.resolve_ref("project:health").id == older.id
    # a qualified path is never ambiguous
    assert box.nodes.resolve_ref("org:b/project:health").id == newer.id


# --- the chain never forks; the manifest binds the source; roles come from ROLE_BUNDLES ---------
def test_a_lost_append_race_re_chains_instead_of_forking(box: Container):
    real = box.backend.audit_last
    stale = real()
    calls = {"n": 0}

    def racing_head():
        calls["n"] += 1
        return stale if calls["n"] == 1 else real()

    box.ledger.append("context.fetch", actor=OWNER, principal="interactive")  # the other writer
    box.backend.audit_last = racing_head
    box.ledger.append("context.fetch", actor=OWNER, principal="interactive")
    assert calls["n"] == 2 and box.ledger.verify()["ok"]


def test_an_item_moved_after_the_proposal_makes_it_stale(box: Container):
    t, org, proj, other = _tree(box)
    _client(box, "watcher", "reader", [other.id])
    item = box.store.add(body="draft", scope=proj, token=t, actor=OWNER, principal=t.principal)
    pid = box.trust.move(item, other, token=t, actor=OWNER)["proposal"]["id"]
    box.trust._do_move(item, org, OWNER, "interactive")  # moved under the proposal's feet
    with pytest.raises(TrustError, match="re-propose"):
        box.trust.execute(pid, token=t, actor=OWNER)
    assert box.ledger.tail(1)[0]["event"] == "approval.stale"


def test_role_names_are_read_from_the_bundles():
    from egzos._types import ROLE_BUNDLES
    from egzos.trust import _role_name

    for role, bundle in ROLE_BUNDLES.items():
        assert _role_name(sorted(bundle)) == role
