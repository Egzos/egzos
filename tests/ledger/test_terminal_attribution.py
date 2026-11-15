# Copyright 2026 Ali Sasanian
# SPDX-License-Identifier: LicenseRef-PolyForm-Strict-1.0.0
"""identity.md §3a, rest.md §4 and §6 (v0.7 §AJ): a person at a terminal is `actor: user:<sub>`,
and every entry appended for the request names the terminal in `details.terminal`, added as
`details.for` is; a `BlobGrant` redeemed with no bearer takes it from the token its descriptor
names."""

from __future__ import annotations

import os
from urllib.parse import urlencode

import pytest
from starlette.datastructures import QueryParams

from egzos.api.blobs import redeem
from egzos.api.throttle import Throttle
from egzos.container import OWNER, Container
from egzos.ledger import acting_for, attributed, through_terminal
from egzos.store.blobs import GRANT_QUERY

KW = {"actor": OWNER, "principal": "interactive"}
BOB = "bob-sub"


@pytest.fixture
def box(tmp_path):
    c = Container(tmp_path / "home")
    c.owner = c.init()
    c.set_config("identity.client_id", "box", token=c.owner)
    c.identity.grant_user(BOB, name="bob", role="contributor", scopes=["*"], **KW)
    c.backend.put_agent_registration({
        "client_id": "t1", "sub": BOB, "kind": "terminal", "name": "a laptop",
        "created_at": "2026-11-14T00:00:00Z", "revoked": False})
    c.backend.put_agent_registration({
        "client_id": "a1", "sub": BOB, "name": "helper", "capabilities": ["fetch"],
        "scopes": ["*"], "created_at": "2026-11-14T00:00:00Z", "revoked": False})
    return c


def _fetch(c, token):
    return c.ledger.append("context.fetch", actor=token.owner, principal=token.principal,
                           items=[])


def test_every_entry_inside_names_the_terminal_and_none_outside(box):
    with through_terminal("t1"):
        inside = box.ledger.append("step_up", actor=f"user:{BOB}", principal="interactive",
                                   via="confirm", proof="button", outcome="refused")
    outside = box.ledger.append("step_up", actor=f"user:{BOB}", principal="interactive")
    assert inside["details"]["terminal"] == "t1"
    assert inside["details"]["via"] == "confirm"  # the confirm's own key is left as it is
    assert "terminal" not in outside["details"]


def test_an_entry_with_no_caller_names_no_terminal(box):
    with through_terminal("t1"):
        tally = box.ledger.append("rest.tally", actor="rest", principal="none", unauthorized=1,
                                  forged=0, window_key="w")
    assert "terminal" not in tally["details"]


def test_attributed_stamps_what_each_token_asks_for(box):
    terminal = box.identity._terminal("t1", BOB)
    agent = box.identity._agent("a1", BOB)
    person = box.identity._person(BOB, "box")
    seen = {}
    for name, token in (("terminal", terminal), ("agent", agent), ("person", person),
                        ("owner", box.owner)):
        with attributed(token):
            seen[name] = _fetch(box, token)
    assert (seen["terminal"]["actor"], seen["terminal"]["details"].get("terminal"),
            seen["terminal"]["details"].get("for")) == (f"user:{BOB}", "t1", None)
    assert (seen["agent"]["actor"], seen["agent"]["details"].get("for"),
            seen["agent"]["details"].get("terminal")) == ("agent:a1", f"user:{BOB}", None)
    for name in ("person", "owner"):
        assert {"for", "terminal"}.isdisjoint(seen[name]["details"])
    # Both stamps are reset on the way out, and nest as `acting_for` always has.
    with acting_for("user:x"), through_terminal("t9"):
        both = box.ledger.append("context.fetch", actor="user:x", principal="interactive")
    assert (both["details"]["for"], both["details"]["terminal"]) == ("user:x", "t9")
    assert {"for", "terminal"}.isdisjoint(_fetch(box, person)["details"])


def test_a_confirm_from_a_terminal_names_it_on_its_step_up(box):
    terminal = box.identity._terminal("t1", BOB)
    with attributed(terminal):
        first = box.confirm.issue(terminal, act="promote", subject="i", destination=None,
                                  delta=[], newly=[])
        box.confirm.conclude(terminal, {"challenge": first["challenge"], "proof": "button"},
                             act="promote", subject="i", destination=None, delta=[])
    step_up = box.ledger.tail(1)[-1]
    assert (step_up["event"], step_up["actor"], step_up["details"]["terminal"]) == (
        "step_up", f"user:{BOB}", "t1")


# -- a `BlobGrant` redeemed with no bearer (rest.md §6) --------------------------------------------
def _redeem(c, grant, throttle):
    params = QueryParams(urlencode([(k, grant[k]) for k in GRANT_QUERY]))
    return redeem(c, throttle, "127.0.0.1", grant["sha256"], params)


def test_a_redemption_takes_the_terminal_from_the_token_its_descriptor_names(box, tmp_path):
    path = tmp_path / "a.bin"
    path.write_bytes(os.urandom(64))
    project = box.nodes.create("project", "p", box.nodes.user_root(), token=box.owner, **KW)
    item = box.store.add(file=path, scope=project, token=box.owner, **KW)
    terminal = box.identity._terminal("t1", BOB)
    throttle = Throttle(box.backend, box.ledger, b"k" * 32)
    grant = box.trust.authorize_pull(terminal, item)
    assert grant["token"] == "terminal:t1:" + BOB
    assert _redeem(box, grant, throttle) == path.read_bytes()
    pull = box.ledger.tail(1)[-1]
    assert (pull["event"], pull["actor"], pull["details"]["terminal"]) == (
        "blob.pull", f"user:{BOB}", "t1")
    # Spent, its refusal is attributed the same way.
    assert _redeem(box, grant, throttle) is None
    refused = box.ledger.tail(1)[-1]
    assert (refused["event"], refused["details"]["terminal"]) == ("context.fetch", "t1")
    # A grant minted through a terminal since ended is refused at check 5, still named.
    again = box.trust.authorize_pull(terminal, item)
    box.identity.revoke_terminal("t1", BOB, **KW)
    assert _redeem(box, again, throttle) is None
    after = box.ledger.tail(1)[-1]
    assert (after["details"]["check"], after["details"]["terminal"]) == (5, "t1")
