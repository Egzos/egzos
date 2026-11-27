# Copyright 2026 Ali Sasanian
# SPDX-License-Identifier: LicenseRef-PolyForm-Strict-1.0.0
"""rest.md §4.3, "An agent's terms are its person's own choice": on `POST /v1/agents` a scope is
`"*"` alone or a node id read as an id alone; the first leg says the terms it bound and what a
registration replaces, and the challenge is bound to both; the second leg finds each place again
by its id under the lock, and the bound again, and registers nothing where either fails."""

from __future__ import annotations

import time

import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import ec
from fastapi.testclient import TestClient

from egzos.api.app import create_app
from egzos.container import OWNER, Container
from egzos.identity import Jwks

ISSUER = "https://project.supabase.co/auth/v1"
NOT_FOUND = b'{"error":"not_found"}'
INVALID = b'{"error":"invalid_request"}'
KW = {"actor": OWNER, "principal": "interactive"}
ABSENT = "01ARZ3NDEKTSV4RRFFQ69G5FAV"  # the form of a node id, naming no node
HELPER = {"authorization_id": "auth-1", "client_id": "helper", "name": "Helper",
          "capabilities": ["fetch"], "scopes": ["*"]}


@pytest.fixture
def c(tmp_path):
    box = Container(tmp_path)
    box.owner = box.init()
    return box


@pytest.fixture
def door(c):
    return TestClient(create_app(c))


@pytest.fixture
def sign(c):
    """alice is an admin over everything, bob a reader over everything; pat is added per test."""
    key = ec.generate_private_key(ec.SECP256R1())
    jwk = {**jwt.algorithms.ECAlgorithm.to_jwk(key.public_key(), as_dict=True), "kid": "k1",
           "alg": "ES256"}
    c.set_config("identity.issuer", ISSUER, token=c.owner)
    c.set_config("identity.client_id", "box", token=c.owner)
    jwks = Jwks("x", fetch=lambda url: {"keys": [jwk]})
    c.identity._jwks_for = lambda url: jwks
    c.identity.grant_user("alice", name="Alice", role="admin", scopes=["*"], **KW)
    c.identity.grant_user("bob", name="Bob", role="reader", scopes=["*"], **KW)

    def headers(sub="alice"):
        now = int(time.time())
        claims = {"iss": ISSUER, "aud": "authenticated", "exp": now + 600, "iat": now, "sub": sub,
                  "client_id": "box", "amr": [{"method": "otp", "timestamp": now - 30}]}
        value = jwt.encode(claims, key, algorithm="ES256", headers={"kid": "k1"})
        return {"Authorization": f"Bearer {value}", "Origin": "https://egzos.io"}

    return headers


def _events(c, name):
    return [e for e in c.ledger.tail(3000) if e["event"] == name]


def _node(c, kind, name, parent=None):
    return c.nodes.create(kind, name, parent=parent or c.nodes.user_root(), token=c.owner, **KW)


def _button(first, **body):
    return {**body, "confirm": {"challenge": first["challenge"], "proof": "button"}}


def _legs(door, headers, body, second=None):
    first = door.post("/v1/agents", headers=headers, json=body).json()
    return first, door.post("/v1/agents", headers=headers, json=_button(first, **(second or body)))


# -- the first leg says the terms it bound ---------------------------------------------------------
def test_the_first_leg_answers_the_terms_beside_registers_and_the_chain_holds_them(c, door, sign):
    p, q = _node(c, "project", "p"), _node(c, "project", "q")
    body = {**HELPER, "role": "contributor", "capabilities": None, "scopes": [q.id, p.id]}
    first = door.post("/v1/agents", headers=sign(),
                      json={k: v for k, v in body.items() if v is not None}).json()
    terms = {"capabilities": ["fetch", "remember"], "scopes": sorted([p.id, q.id])}
    registers = {"client_id": "helper", "name": "Helper"}
    assert (first["registers"], first["terms"]) == (registers, terms)
    assert "replaces" not in first  # the client serves no one yet
    shown = _events(c, "context.fetch")[-1]["details"]
    assert (shown["confirm_for"], shown["terms"]) == ("agent.add", terms)
    assert "replaces" not in shown


def test_the_whole_container_is_named_as_the_one_scope_star(c, door, sign):
    first, done = _legs(door, sign(), HELPER)
    assert first["terms"] == {"capabilities": ["fetch"], "scopes": ["*"]}
    assert done.json()["agent"]["scopes"] == ["*"]
    assert _events(c, "identity.grant")[-1]["details"]["scopes"] == ["*"]


# -- a scope is "*" alone, or an id read as an id alone  -------------------------------------------
@pytest.mark.parametrize("scopes", [
    ["*", "P"], ["P", "*"], ["*", "*"], ["*", ABSENT],  # "*" beside any other entry
    ["project:p"], ["p"], ["user:self/project:p"], ["P", "project:p"],  # a path tail
    ["P-lower"], [ABSENT.lower()], [ABSENT + "0"], [ABSENT[:-1]],  # not an id
    [ABSENT[:-1] + "U"], [" " + ABSENT],  # U is outside an id's alphabet
])
def test_any_other_scope_is_400_before_any_lookup(c, door, sign, scopes):
    p = _node(c, "project", "p")
    scopes = [{"P": p.id, "P-lower": p.id.lower()}.get(s, s) for s in scopes]
    reads = len(_events(c, "context.fetch"))
    r = door.post("/v1/agents", headers=sign(), json={**HELPER, "scopes": scopes})
    assert (r.status_code, r.content) == (400, INVALID)
    assert len(_events(c, "context.fetch")) == reads  # no lookup, so no probe
    assert c.backend.list_agent_registrations() == []


def test_a_place_named_like_an_id_is_never_read_as_that_place(c, door, sign):
    # A captured thread may bear an item's id as its name (§4.5); here a place bears the form of an
    # id that names no node. Sent as a scope, it is an id and nothing else: absent, so refused.
    named = _node(c, "project", ABSENT)
    reads = len(_events(c, "context.fetch"))
    r = door.post("/v1/agents", headers=sign(), json={**HELPER, "scopes": [ABSENT]})
    assert (r.status_code, r.content) == (404, NOT_FOUND)
    assert [e["details"]["items"] for e in _events(c, "context.fetch")[reads:]] == [[]]
    assert c.backend.get_node(named.id).name == ABSENT
    assert c.backend.list_agent_registrations() == []


# -- the bound, before any leg and again inside the second  ----------------------------------------
@pytest.mark.parametrize("change", [{"capabilities": ["remember"]}, {"scopes": "Q"},
                                    {"scopes": ["*"]}])
def test_terms_wider_than_the_registrants_grant_are_refused_before_any_leg(c, door, sign, change):
    p, q = _node(c, "project", "p"), _node(c, "project", "q")
    c.identity.grant_user("pat", name="Pat", role="reader", scopes=[p.id], **KW)
    change = {"scopes": [q.id]} if change.get("scopes") == "Q" else change
    r = door.post("/v1/agents", headers=sign("pat"), json={**HELPER, "scopes": [p.id], **change})
    assert (r.status_code, r.content) == (404, NOT_FOUND)
    assert "confirm_for" not in _events(c, "context.fetch")[-1]["details"]  # the probe, no leg


@pytest.mark.parametrize("narrowed", [(["remember"], ["*"]), (["fetch"], "P")])
def test_terms_wider_than_the_grant_as_it_stands_are_refused_inside_the_second_leg(
        c, door, sign, monkeypatch, narrowed):
    p, q = _node(c, "project", "p"), _node(c, "project", "q")
    first = door.post("/v1/agents", headers=sign("bob"), json={**HELPER, "scopes": [q.id]}).json()
    refresh = c.identity.refresh

    def narrowed_under_the_lock(token):  # after the door's checks, inside the atomic step
        caps, scopes = narrowed
        c.identity.grant_user("bob", name="Bob", capabilities=caps,
                              scopes=[p.id] if scopes == "P" else scopes, **KW)
        return refresh(token)

    monkeypatch.setattr(c.identity, "refresh", narrowed_under_the_lock)
    r = door.post("/v1/agents", headers=sign("bob"),
                  json=_button(first, **{**HELPER, "scopes": [q.id]}))
    assert (r.status_code, r.content) == (404, NOT_FOUND)
    assert not _events(c, "step_up")  # no proof concluded
    assert c.backend.list_agent_registrations() == []


# -- a place renamed, moved or removed between the legs  -------------------------------------------
@pytest.mark.parametrize("who", ["alice", "pat"])  # a holder of "*", and one over a place
def test_a_place_gone_inside_the_second_leg_registers_nothing(c, door, sign, monkeypatch, who):
    top = _node(c, "project", "top")
    t = _node(c, "thread", "t", parent=top)
    c.identity.grant_user("pat", name="Pat", role="reader", scopes=[top.id], **KW)
    body = {**HELPER, "scopes": [t.id]}
    first = door.post("/v1/agents", headers=sign(who), json=body).json()
    refresh, get_node = c.identity.refresh, c.backend.get_node

    def removed_under_the_lock(token):
        monkeypatch.setattr(c.backend, "get_node", lambda i: None if i == t.id else get_node(i))
        return refresh(token)

    monkeypatch.setattr(c.identity, "refresh", removed_under_the_lock)
    r = door.post("/v1/agents", headers=sign(who), json=_button(first, **body))
    assert (r.status_code, r.content) == (404, NOT_FOUND)
    assert not _events(c, "step_up") and c.backend.list_agent_registrations() == []


def test_a_place_gone_before_the_second_leg_is_the_refusal(c, door, sign, monkeypatch):
    t = _node(c, "thread", "t")
    body = {**HELPER, "scopes": [t.id]}
    first = door.post("/v1/agents", headers=sign(), json=body).json()
    get_node = c.backend.get_node
    monkeypatch.setattr(c.backend, "get_node", lambda i: None if i == t.id else get_node(i))
    r = door.post("/v1/agents", headers=sign(), json=_button(first, **body))
    assert (r.status_code, r.content) == (404, NOT_FOUND)
    assert c.backend.list_agent_registrations() == []


def test_a_place_renamed_between_the_legs_is_the_place_chosen(c, door, sign):
    p = _node(c, "project", "p")
    body = {**HELPER, "scopes": [p.id]}
    first = door.post("/v1/agents", headers=sign(), json=body).json()
    p.name = "renamed"  # as a rename writes it (storage.md §3), and another place takes the name
    c.backend.put_node(p)
    _node(c, "project", "p")
    r = door.post("/v1/agents", headers=sign(), json=_button(first, **body))
    assert r.json()["agent"]["scopes"] == [p.id]


# -- choosing again: what a registration replaces  -------------------------------------------------
def test_a_re_registration_that_widens_shows_what_it_replaces_and_the_chain_says_so(
        c, door, sign):
    p = _node(c, "project", "p")
    _, made = _legs(door, sign("bob"), {**HELPER, "scopes": [p.id]})
    was = {k: made.json()["agent"][k] for k in ("capabilities", "scopes", "created_at")}
    wider = {**HELPER, "authorization_id": "auth-2", "scopes": ["*"]}
    first, done = _legs(door, sign("bob"), wider)
    assert (first["terms"], first["replaces"]) == (
        {"capabilities": ["fetch"], "scopes": ["*"]}, was)
    assert _events(c, "context.fetch")[-1]["details"]["replaces"] == was  # the first leg's read
    assert done.json()["agent"]["scopes"] == ["*"]
    granted = _events(c, "identity.grant")[-1]["details"]
    assert (granted["scopes"], granted["replaces"]) == (["*"], was)
    # Replaced whole and in place: one registration, nothing carried over, no new slot.
    assert [r["scopes"] for r in c.identity.serving("bob")] == [["*"]]


def test_another_persons_registration_of_the_client_is_never_shown_as_replaced(c, door, sign):
    p = _node(c, "project", "p")
    _legs(door, sign("bob"), {**HELPER, "scopes": [p.id]})  # helper serves bob
    mine = {**HELPER, "authorization_id": "auth-2"}
    first = door.post("/v1/agents", headers=sign("alice"), json=mine).json()
    assert "replaces" not in first
    assert "replaces" not in _events(c, "context.fetch")[-1]["details"]
    done = door.post("/v1/agents", headers=sign("alice"), json=_button(first, **mine))
    assert done.json()["agent"]["sub"] == "alice"
    assert "replaces" not in _events(c, "identity.grant")[-1]["details"]
    assert c.backend.get_agent_registration("helper", "bob")["scopes"] == [p.id]  # bob's stays


def test_an_ended_registration_is_replaced_by_nothing(c, door, sign):
    _legs(door, sign("bob"), HELPER)
    c.identity.revoke_agent("helper", "bob", **KW)
    first, _ = _legs(door, sign("bob"), {**HELPER, "authorization_id": "auth-2"})
    assert "replaces" not in first


@pytest.mark.parametrize("between", ["one appears", "it ends", "it changes"])
def test_a_registration_that_changes_between_the_legs_is_mismatch(c, door, sign, between):
    p = _node(c, "project", "p")
    if between != "one appears":
        _legs(door, sign("bob"), {**HELPER, "scopes": [p.id]})
    body = {**HELPER, "authorization_id": "auth-2"}
    first = door.post("/v1/agents", headers=sign("bob"), json=body).json()
    if between == "it ends":
        c.identity.revoke_agent("helper", "bob", **KW)
    else:  # another tab registers it, or registers it again, before this second leg
        _legs(door, sign("bob"), {**HELPER, "authorization_id": "auth-3",
                                  "capabilities": ["fetch"], "scopes": [p.id]})
        if between == "it changes":
            c.backend.put_agent_registration({**c.backend.get_agent_registration("helper", "bob"),
                                              "created_at": "2030-01-01T00:00:00Z"})
    before = c.backend.get_agent_registration("helper", "bob")
    again = door.post("/v1/agents", headers=sign("bob"), json=_button(first, **body)).json()
    assert again["result"] == "confirm"
    assert _events(c, "step_up")[-1]["details"]["reason"] == "mismatch"
    assert c.backend.get_agent_registration("helper", "bob") == before  # nothing registered
    # The fresh first leg shows what the registration would replace as it now stands.
    now = None if before is None or before["revoked"] else {
        k: before[k] for k in ("capabilities", "scopes", "created_at")}
    assert again.get("replaces") == now


def test_the_fresh_first_leg_binds_the_terms_the_second_leg_named(c, door, sign):
    p = _node(c, "project", "p")
    first, refused = _legs(door, sign(), HELPER, second={**HELPER, "scopes": [p.id]})
    assert refused.json()["terms"] == {"capabilities": ["fetch"], "scopes": [p.id]}
    done = door.post("/v1/agents", headers=sign(),
                     json=_button(refused.json(), **{**HELPER, "scopes": [p.id]}))
    assert done.json()["agent"]["scopes"] == [p.id]
