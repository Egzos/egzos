# Copyright 2026 Ali Sasanian
# SPDX-License-Identifier: Apache-2.0
"""
Freeze decisions read off the running code: `publish` gates widening and `organize` gates the
silent move (item 3), a TOCTOU refusal is `approval.stale` not `approval.deny` (item 39), and an
ambiguous path is refused with its matches named, never picked (item 1, as the Chief revised it).
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
def test_a_token_below_the_floor_gets_one_refusal_whichever_branch(box: Container):
    t, org, proj, other = _tree(box)
    quiet = box.nodes.create("project", "quiet", org, token=t, actor=OWNER, principal=t.principal)
    _client(box, "watcher", "reader", [other.id])  # `other` has an audience `proj` lacks
    writer = _client(box, "writer", "contributor", [org.id])
    item = box.store.add(body="draft", scope=proj, token=t, actor=OWNER, principal=t.principal)
    refusals = []
    for to in (other, quiet):  # a widening move, then a zero-delta one
        with pytest.raises(TrustError) as e:
            box.trust.move(item, to, token=writer, actor="writer")
        refusals.append(str(e.value))
    # container.md §6: checked before the delta, so the refusal says nothing about the audience
    assert refusals[0] == refusals[1] and "organize" in refusals[0]
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


# --- item 1, as revised by the Chief (2026-10-03): an ambiguous tail is refused, never picked ----
def test_an_ambiguous_path_names_its_matches_and_picks_none(box: Container):
    from egzos.store.nodes import AmbiguousRef

    t = box.auth.interactive_token()
    root = box.nodes.user_root()
    a = box.nodes.create("org", "a", root, token=t, actor=OWNER, principal=t.principal)
    b = box.nodes.create("org", "b", root, token=t, actor=OWNER, principal=t.principal)
    older = box.nodes.create("project", "health", a, token=t, actor=OWNER, principal=t.principal)
    newer = box.nodes.create("project", "health", b, token=t, actor=OWNER, principal=t.principal)
    with pytest.raises(AmbiguousRef) as refused:
        box.nodes.resolve_ref("project:health", t)
    assert refused.value.paths == [box.nodes.path(older), box.nodes.path(newer)]
    # activity in one candidate changes nothing: no write can steer the answer
    box.store.add(body="x", scope=newer, token=t, actor=OWNER, principal=t.principal)
    with pytest.raises(AmbiguousRef):
        box.nodes.resolve_ref("health", t)
    # a qualified path, or the id, is never ambiguous
    assert box.nodes.resolve_ref("org:b/project:health", t).id == newer.id
    assert box.nodes.resolve_ref(older.id, t).id == older.id


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


# --- an agent-run landing is a write: it lands unverified, on every path, on the record ----------
def test_an_agent_run_silent_move_resets_and_says_so_on_the_chain(box: Container):
    t, org, proj, other = _tree(box)
    op = _client(box, "op", "operator", [org.id])
    item = box.store.add(body="note", scope=proj, token=t, actor=OWNER, principal=t.principal)
    box.trust.promote(item, token=t, actor=OWNER)
    box.trust.move(box.backend.get(item.id), other, token=op, actor="op")
    moved = box.backend.get(item.id)
    assert moved.status == "unverified" and moved.trust == {"status": "unverified"}
    silent = [e for e in box.ledger.tail(10) if e["event"] == "gate.pass.silent"][-1]
    assert silent["details"]["reset"] == [item.id]


def test_a_human_run_move_keeps_its_status_until_the_freeze_says_otherwise(box: Container):
    t, org, proj, other = _tree(box)
    item = box.store.add(body="note", scope=proj, token=t, actor=OWNER, principal=t.principal)
    box.trust.promote(item, token=t, actor=OWNER)
    box.trust.move(box.backend.get(item.id), other, token=t, actor=OWNER)
    assert box.backend.get(item.id).status == "verified"


def test_an_approved_agent_move_records_the_reset_on_approval_execute(box: Container):
    t, org, proj, other = _tree(box)
    _client(box, "watcher", "reader", [other.id])
    op = _client(box, "op", "operator", [org.id])
    item = box.store.add(body="note", scope=proj, token=t, actor=OWNER, principal=t.principal)
    box.trust.promote(item, token=t, actor=OWNER)
    pid = box.trust.move(box.backend.get(item.id), other, token=op, actor="op")["proposal"]["id"]
    box.trust.execute(pid, token=t, actor=OWNER)
    done = [e for e in box.ledger.tail(10) if e["event"] == "approval.execute"][-1]
    assert done["details"]["reset"] == [item.id]
    assert box.backend.get(item.id).trust == {"status": "unverified"}


def test_a_quarantined_item_does_not_move(box: Container):
    t, org, proj, other = _tree(box)
    item = box.store.add(body="bad", scope=proj, token=t, actor=OWNER, principal=t.principal)
    box.trust.quarantine(item, token=t, actor=OWNER, reason="x")
    with pytest.raises(TrustError, match="quarantined items do not move"):
        box.trust.move(box.backend.get(item.id), other, token=t, actor=OWNER)


def test_a_quarantine_after_parking_blocks_the_approval_but_not_the_deny(box: Container):
    from egzos.authz.presence import Tap, build_act

    t, org, proj, other = _tree(box)
    _client(box, "watcher", "reader", [other.id])
    item = box.store.add(body="note", scope=proj, token=t, actor=OWNER, principal=t.principal)
    pid = box.trust.move(item, other, token=t, actor=OWNER)["proposal"]["id"]
    box.trust.quarantine(box.backend.get(item.id), token=t, actor=OWNER, reason="poisoned")
    act = build_act(box, pid)
    assert act["blocked"] == "Contains a quarantined item. It cannot move."
    page = Tap(act).page(armed=False)
    assert "Sign and approve" not in page and "Approve without a window" not in page
    assert "It cannot move." in page and "value=deny" in page
    tap = Tap(act)
    tap.post("arm")
    tap.post("confirm")
    assert tap.outcome is None  # no press reaches approve
    with pytest.raises(TrustError, match="cannot move"):
        box.trust.execute(pid, token=t, actor=OWNER)
    refused = box.ledger.tail(1)[0]  # the engine records its own refusal
    assert refused["event"] == "approval.stale" and refused["subject"] == pid
    assert refused["details"]["status"] == "open"
    assert box.backend.get(item.id).scope == proj.id
    box.trust.deny(pid, token=t, actor=OWNER)
    assert box.backend.get_proposal(pid)["status"] == "denied"


def test_a_proposal_into_an_exo_room_names_its_external_audience(box: Container):
    from egzos.authz.presence import build_act

    t, org, proj, other = _tree(box)
    exo = box.nodes.create("exo", "partners", org, token=t, actor=OWNER, principal=t.principal)
    _client(box, "vendor", "reader", [exo.id])
    item = box.store.add(body="draft", scope=proj, token=t, actor=OWNER, principal=t.principal)
    to_exo = box.trust.move(item, exo, token=t, actor=OWNER)["proposal"]["id"]
    # §4 R6 / §13 `consequence.exo`: the room's named external parties, not a subtree.
    assert build_act(box, to_exo)["consequence"] == (
        "Consequence. Everything in the exo room partners sees this — every named external "
        "party, now and in future.")
    _client(box, "watcher", "reader", [other.id])
    second = box.store.add(body="note", scope=proj, token=t, actor=OWNER, principal=t.principal)
    to_project = box.trust.move(second, other, token=t, actor=OWNER)["proposal"]["id"]
    assert build_act(box, to_project)["consequence"].startswith("Consequence. Everything under ")


def test_a_failure_mid_execute_moves_nothing(box: Container, monkeypatch):
    t, org, proj, other = _tree(box)
    _client(box, "watcher", "reader", [other.id])
    a = box.store.add(body="a", scope=proj, token=t, actor=OWNER, principal=t.principal)
    b = box.store.add(body="b", scope=proj, token=t, actor=OWNER, principal=t.principal)
    pid = box.trust.move(a, other, token=t, actor=OWNER)["proposal"]["id"]
    p = box.backend.get_proposal(pid)
    p["items"] = [a.id, b.id]  # one proposal, two moves
    p["manifest"] = box.trust.manifest_hash(p["items"], p["to"], box.trust.audience(other))
    box.backend.put_proposal(p)
    before = len(box.ledger.tail(1000))
    real, calls = box.trust._do_move, []

    def fail_on_second(item, to, actor, principal):
        calls.append(item.id)
        if len(calls) == 2:
            raise OSError("disk went away")
        real(item, to, actor, principal)

    monkeypatch.setattr(box.trust, "_do_move", fail_on_second)
    with pytest.raises(OSError):
        box.trust.execute(pid, token=t, actor=OWNER)
    # The first move rolled back with the second: nothing moved, nothing on the chain.
    assert box.backend.get(a.id).scope == proj.id and box.backend.get(b.id).scope == proj.id
    assert box.backend.get_proposal(pid)["status"] == "open"
    assert len(box.ledger.tail(1000)) == before and box.ledger.verify()["ok"]
    monkeypatch.setattr(box.trust, "_do_move", real)
    box.trust.execute(pid, token=t, actor=OWNER)  # and the same approval lands whole after
    assert box.backend.get(a.id).scope == other.id and box.backend.get(b.id).scope == other.id


def test_a_failure_mid_quarantine_quarantines_nothing(box: Container, monkeypatch):
    t = box.auth.interactive_token()
    src = box.store.add(body="src", token=t, actor=OWNER, principal=t.principal)
    copy = box.store.add(body="copy", token=t, actor=OWNER, principal=t.principal)
    copy.provenance["derived_from"] = src.id
    box.backend.put(copy)
    before = len(box.ledger.tail(1000))
    real_put = box.backend.put

    def fail_on_the_copy(item):
        if item.id == copy.id:
            raise OSError("disk went away")
        real_put(item)

    monkeypatch.setattr(box.backend, "put", fail_on_the_copy)
    with pytest.raises(OSError):
        box.trust.quarantine(box.backend.get(src.id), token=t, actor=OWNER, reason="x")
    monkeypatch.setattr(box.backend, "put", real_put)
    assert box.backend.get(src.id).status == "unverified"  # the source rolled back with the copy
    assert box.backend.get(copy.id).status == "unverified"
    assert len(box.ledger.tail(1000)) == before and box.ledger.verify()["ok"]


def test_a_failed_act_under_an_open_window_is_on_the_chain(tmp_path, monkeypatch):
    from egzos.authz.presence import Presence, build_act
    from egzos.cli import main

    monkeypatch.setenv("EGZOS_HOME", str(tmp_path))
    monkeypatch.setenv("EGZOS_STEP_UP_WINDOW_SECONDS", "300")
    monkeypatch.delenv("EGZOS_TOKEN", raising=False)
    assert main(["init"]) == 0
    c = Container(tmp_path)
    t = c.auth.interactive_token()
    item = c.store.add(body="note", token=t, actor=OWNER, principal=t.principal)
    act = build_act(c, item.id)
    Presence(c).record(act, via="tap", outcome="approved", windowed=True)

    def broken(*a, **kw):
        raise OSError("disk went away")

    monkeypatch.setattr("egzos.trust.TrustEngine.promote", broken)
    assert main(["trust", "approve", item.id]) != 0
    steps = [e["details"] for e in c.ledger.tail(10) if e["event"] == "step_up"]
    assert [s["outcome"] for s in steps[-2:]] == ["window", "closed"]
    assert steps[-1]["reason"] == "act failed" and c.backend.get(item.id).status == "unverified"


def test_a_quarantined_manifest_is_never_covered_and_a_refusal_is_on_the_chain(
        box: Container, monkeypatch):
    from egzos.authz.presence import Presence, build_act

    monkeypatch.setenv("EGZOS_STEP_UP_WINDOW_SECONDS", "300")
    t, org, proj, other = _tree(box)
    _client(box, "watcher", "reader", [other.id])
    item = box.store.add(body="n", scope=proj, token=t, actor=OWNER, principal=t.principal)
    pid = box.trust.move(item, other, token=t, actor=OWNER)["proposal"]["id"]
    p = Presence(box)
    p.record(build_act(box, pid), via="tap", outcome="approved", windowed=True)
    assert p.covers(build_act(box, pid))
    box.trust.quarantine(box.backend.get(item.id), token=t, actor=OWNER, reason="poisoned")
    act = build_act(box, pid)
    assert act["blocked"] and not p.covers(act)  # R5: no window stands in for a blocked manifest
    try:
        box.trust.execute(pid, token=t, actor=OWNER)
    except TrustError as e:
        p.act_failed(act, e, reason="refused")
    last = box.ledger.tail(1)[0]["details"]
    assert last["outcome"] == "closed" and last["reason"] == "refused"
    assert last["error"] == "TrustError"
