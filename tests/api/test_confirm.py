# Copyright 2026 Ali Sasanian
# SPDX-License-Identifier: LicenseRef-PolyForm-Strict-1.0.0
"""rest.md §4.2: the confirm at the door — two legs, one route, a challenge spent once."""

from __future__ import annotations

import threading

import pytest
from fastapi.testclient import TestClient

from egzos.api.app import create_app
from egzos.container import OWNER, Container

NOT_FOUND = b'{"error":"not_found"}'
KW = {"actor": OWNER, "principal": "interactive"}


@pytest.fixture
def c(tmp_path):
    box = Container(tmp_path)
    box.owner = box.init()
    return box


@pytest.fixture
def door(c):
    return TestClient(create_app(c))


def _h(token):
    return {"Authorization": f"Bearer {token.secret}"}


def _events(c, name):
    return [e for e in c.ledger.tail(2000) if e["event"] == name]


@pytest.fixture
def widening(c):
    """A note in a private project, and a project a granted person (bob) can see."""
    root = c.nodes.user_root()
    nk = {"token": c.owner, **KW}
    mine = c.nodes.create("project", "mine", root, **nk)
    ours = c.nodes.create("project", "ours", root, **nk)
    note = c.store.add(body="a note", scope=mine, **nk)
    c.identity.grant_user("bob", name="Bob", role="reader", scopes=[ours.id], **KW)
    return note, mine, ours


def _confirm(r):
    assert r.status_code == 200 and r.json()["result"] == "confirm", r.content
    return r.json()


# -- the two legs ----------------------------------------------------------------------------------
def test_a_widening_move_asks_then_moves_with_the_button(c, door, widening):
    note, _mine, ours = widening
    first = _confirm(door.post(f"/v1/items/{note.id}/move", headers=_h(c.owner),
                               json={"to": ours.id}))
    assert first["newly"] == ["Bob"] and first["webauthn"] is None
    assert c.store.get(note.id).scope != ours.id  # the first leg moves nothing
    shown = _events(c, "context.fetch")[-1]["details"]
    assert shown["confirm_for"] == "move" and shown["newly"] == ["Bob"]
    second = door.post(f"/v1/items/{note.id}/move", headers=_h(c.owner),
                       json={"to": ours.id, "confirm": {"challenge": first["challenge"],
                                                        "proof": "button"}})
    assert second.json()["result"] == "moved"
    assert c.store.get(note.id).scope == ours.id
    tail = [e["event"] for e in c.ledger.tail(4)]
    assert tail[-3:] == ["step_up", "gate.pass.confirmed", "item.move"]
    step_up = _events(c, "step_up")[-1]
    assert step_up["details"]["outcome"] == "confirmed" and step_up["details"]["proof"] == "button"
    passed = _events(c, "gate.pass.confirmed")[-1]
    assert passed["details"]["step_up"] == step_up["seq"]
    assert passed["details"]["audience_delta"] == ["user:bob"]


def test_a_copy_is_a_new_unverified_item_derived_from_the_source(c, door, widening):
    note, mine, ours = widening
    first = _confirm(door.post(f"/v1/items/{note.id}/copy", headers=_h(c.owner),
                               json={"to": ours.id}))
    r = door.post(f"/v1/items/{note.id}/copy", headers=_h(c.owner),
                  json={"to": ours.id, "confirm": {"challenge": first["challenge"],
                                                   "proof": "button"}})
    copy = r.json()["item"]
    assert r.json()["result"] == "copied" and copy["id"] != note.id
    assert copy["scope"] == ours.id and copy["trust"]["status"] == "unverified"
    assert copy["provenance"]["derived_from"] == note.id
    assert c.store.get(note.id).scope == mine.id  # the source is unchanged
    (made,) = _events(c, "item.copy")
    assert made["subject"] == copy["id"] and made["details"]["from"] == note.id


def test_a_move_nobody_new_would_see_is_silent(c, door):
    root = c.nodes.user_root()
    nk = {"token": c.owner, **KW}
    a = c.nodes.create("project", "a", root, **nk)
    b = c.nodes.create("project", "b", root, **nk)
    note = c.store.add(body="x", scope=a, **nk)
    r = door.post(f"/v1/items/{note.id}/move", headers=_h(c.owner), json={"to": b.id})
    assert r.json()["result"] == "moved" and r.json()["item"]["scope"] == b.id
    assert _events(c, "gate.pass.silent") and not _events(c, "step_up")


def test_a_silent_copy_needs_no_confirm(c, door):
    root = c.nodes.user_root()
    nk = {"token": c.owner, **KW}
    a = c.nodes.create("project", "a", root, **nk)
    b = c.nodes.create("project", "b", root, **nk)
    note = c.store.add(body="x", scope=a, **nk)
    r = door.post(f"/v1/items/{note.id}/copy", headers=_h(c.owner), json={"to": b.id})
    assert r.json()["result"] == "copied" and r.json()["item"]["scope"] == b.id


# -- refusals and their record ---------------------------------------------------------------------
def _second(door, c, note, ours, challenge, proof="button"):
    return door.post(f"/v1/items/{note.id}/move", headers=_h(c.owner),
                     json={"to": ours.id, "confirm": {"challenge": challenge, "proof": proof}})


def test_a_challenge_spends_once_and_a_refusal_gets_a_fresh_one(c, door, widening):
    note, _mine, ours = widening
    first = _confirm(door.post(f"/v1/items/{note.id}/move", headers=_h(c.owner),
                               json={"to": ours.id}))
    # A biometric proof with no credential registered is refused, and spends the challenge.
    again = _confirm(_second(door, c, note, ours, first["challenge"], proof="biometric"))
    assert again["challenge"] != first["challenge"]
    refused = _events(c, "step_up")[-1]["details"]
    assert (refused["outcome"], refused["reason"]) == ("refused", "assertion")
    spent = _confirm(_second(door, c, note, ours, first["challenge"]))
    assert _events(c, "step_up")[-1]["details"]["reason"] == "spent"
    assert spent["challenge"] not in (first["challenge"], again["challenge"])
    unknown = _confirm(_second(door, c, note, ours, "nope"))
    assert _events(c, "step_up")[-1]["details"]["reason"] == "stale"
    assert c.store.get(note.id).scope != ours.id
    assert _second(door, c, note, ours, unknown["challenge"]).json()["result"] == "moved"


def test_a_challenge_is_bound_to_its_act_and_its_principal(c, door, widening):
    note, _mine, ours = widening
    first = _confirm(door.post(f"/v1/items/{note.id}/move", headers=_h(c.owner),
                               json={"to": ours.id}))
    r = door.post(f"/v1/items/{note.id}/copy", headers=_h(c.owner),
                  json={"to": ours.id, "confirm": {"challenge": first["challenge"],
                                                   "proof": "button"}})
    assert r.json()["result"] == "confirm"
    assert _events(c, "step_up")[-1]["details"]["reason"] == "mismatch"
    other = c.auth.mint(principal="interactive", owner=OWNER, client="tab", role="admin",
                        scopes=["*"], actor=OWNER, by_principal="interactive")
    first = _confirm(door.post(f"/v1/items/{note.id}/move", headers=_h(c.owner),
                               json={"to": ours.id}))
    r = door.post(f"/v1/items/{note.id}/move", headers=_h(other),
                  json={"to": ours.id, "confirm": {"challenge": first["challenge"],
                                                   "proof": "button"}})
    assert r.json()["result"] == "confirm"
    assert _events(c, "step_up")[-1]["details"]["reason"] == "foreign"


def test_a_delta_that_changed_since_the_challenge_is_refused(c, door, widening):
    note, _mine, ours = widening
    first = _confirm(door.post(f"/v1/items/{note.id}/move", headers=_h(c.owner),
                               json={"to": ours.id}))
    c.identity.grant_user("carol", name="Carol", role="reader", scopes=[ours.id], **KW)
    again = _confirm(_second(door, c, note, ours, first["challenge"]))
    assert _events(c, "step_up")[-1]["details"]["reason"] == "delta_changed"
    assert sorted(again["newly"]) == ["Bob", "Carol"]


def test_buttons_off_refuses_the_button(c, door, widening):
    note, _mine, ours = widening
    c.set_config("confirm.allow_button", "false", token=c.owner)
    first = _confirm(door.post(f"/v1/items/{note.id}/move", headers=_h(c.owner),
                               json={"to": ours.id}))
    _confirm(_second(door, c, note, ours, first["challenge"]))
    assert _events(c, "step_up")[-1]["details"]["reason"] == "button_off"


def test_two_racing_second_legs_land_one_move(tmp_path, widening, c):
    note, _mine, ours = widening
    first = _confirm(TestClient(create_app(c)).post(
        f"/v1/items/{note.id}/move", headers=_h(c.owner), json={"to": ours.id}))
    results: list[str] = []
    gate = threading.Barrier(2)

    def go():
        door = TestClient(create_app(Container(tmp_path)))
        gate.wait()
        results.append(_second(door, c, note, ours, first["challenge"]).json()["result"])

    threads = [threading.Thread(target=go) for _ in range(2)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    # The loser either spent nothing (`confirm`: the challenge was gone) or arrived after the move
    # committed, when the item already sat where it was going (a silent no-op). Never two confirms.
    assert sorted(results) in (["confirm", "moved"], ["moved", "moved"])
    assert len(_events(c, "gate.pass.confirmed")) == 1
    confirmed = [e for e in _events(c, "step_up") if e["details"]["outcome"] == "confirmed"]
    assert len(confirmed) == 1


@pytest.mark.parametrize("confirm", [{"challenge": "x"}, {"challenge": 1, "proof": "button"},
                                     {"challenge": "x", "proof": "wave"}, "yes"])
def test_a_malformed_confirm_is_400(c, door, widening, confirm):
    note, _mine, ours = widening
    r = door.post(f"/v1/items/{note.id}/move", headers=_h(c.owner),
                  json={"to": ours.id, "confirm": confirm})
    assert r.status_code == 400


# -- a client principal never confirms (§4.2 item 6) -----------------------------------------------
def test_a_clients_widening_move_parks_and_its_confirm_is_ignored(c, door, widening):
    note, _mine, ours = widening
    agent = c.auth.mint(principal="client", owner=OWNER, client="agent", role="curator",
                        scopes=["*"], actor=OWNER, by_principal="interactive")
    r = door.post(f"/v1/items/{note.id}/move", headers=_h(agent),
                  json={"to": ours.id, "confirm": {"challenge": "x", "proof": "button"}})
    assert r.json()["result"] == "pending" and set(r.json()) == {"result", "proposal"}
    assert not _events(c, "step_up")
    for path in (f"/v1/pending/{r.json()['proposal']}/approve", f"/v1/items/{note.id}/promote"):
        assert door.post(path, headers=_h(agent), json={}).content == NOT_FOUND


# -- approve, deny, promote ------------------------------------------------------------------------
def test_approve_and_deny_take_the_confirm(c, door, widening):
    note, _mine, ours = widening
    agent = c.auth.mint(principal="client", owner=OWNER, client="agent", role="curator",
                        scopes=["*"], actor=OWNER, by_principal="interactive")
    pid = door.post(f"/v1/items/{note.id}/move", headers=_h(agent),
                    json={"to": ours.id}).json()["proposal"]
    first = _confirm(door.post(f"/v1/pending/{pid}/approve", headers=_h(c.owner)))
    assert first["newly"] == []
    r = door.post(f"/v1/pending/{pid}/approve", headers=_h(c.owner),
                  json={"confirm": {"challenge": first["challenge"], "proof": "button"}})
    assert r.json()["result"] == "executed" and r.json()["item"]["scope"] == ours.id
    assert [e["event"] for e in c.ledger.tail(3)][-3:] == ["step_up", "item.move",
                                                           "approval.execute"]
    assert door.post(f"/v1/pending/{pid}/deny", headers=_h(c.owner)).content == NOT_FOUND


def test_promote_takes_the_confirm(c, door):
    note = c.store.add(body="true", token=c.owner, **KW)
    first = _confirm(door.post(f"/v1/items/{note.id}/promote", headers=_h(c.owner)))
    r = door.post(f"/v1/items/{note.id}/promote", headers=_h(c.owner),
                  json={"confirm": {"challenge": first["challenge"], "proof": "button"}})
    assert r.json()["result"] == "promoted"
    assert r.json()["item"]["trust"]["status"] == "verified"
    again = door.post(f"/v1/items/{note.id}/promote", headers=_h(c.owner))
    assert again.content == NOT_FOUND  # only an unverified item is promoted


def test_a_copy_proposal_executes_as_a_copy(c, door, widening):
    note, mine, ours = widening
    agent = c.auth.mint(principal="client", owner=OWNER, client="agent", role="curator",
                        scopes=["*"], actor=OWNER, by_principal="interactive")
    pid = door.post(f"/v1/items/{note.id}/copy", headers=_h(agent),
                    json={"to": ours.id}).json()["proposal"]
    first = _confirm(door.post(f"/v1/pending/{pid}/approve", headers=_h(c.owner)))
    door.post(f"/v1/pending/{pid}/approve", headers=_h(c.owner),
              json={"confirm": {"challenge": first["challenge"], "proof": "button"}})
    assert c.store.get(note.id).scope == mine.id
    (made,) = _events(c, "item.copy")
    assert c.store.get(made["subject"]).scope == ours.id
