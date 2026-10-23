# Copyright 2026 Ali Sasanian
# SPDX-License-Identifier: LicenseRef-PolyForm-Strict-1.0.0
"""Grants and agents at the REST door (rest.md §4.3): who may call, the confirm, and the log."""

from __future__ import annotations

import time

import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import ec
from fastapi.testclient import TestClient

from egzos.api.app import create_app
from egzos.container import OWNER, Container
from egzos.identity import Jwks

NOT_FOUND = b'{"error":"not_found"}'
INVALID = b'{"error":"invalid_request"}'
ISSUER = "https://project.supabase.co/auth/v1"
KW = {"actor": OWNER, "principal": "interactive"}


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
    key = ec.generate_private_key(ec.SECP256R1())
    jwk = {**jwt.algorithms.ECAlgorithm.to_jwk(key.public_key(), as_dict=True), "kid": "k1",
           "alg": "ES256"}
    c.set_config("identity.issuer", ISSUER, token=c.owner)
    c.set_config("identity.client_id", "box", token=c.owner)
    jwks = Jwks("x", fetch=lambda url: {"keys": [jwk]})
    c.identity._jwks_for = lambda url: jwks

    def bearer(sub, client_id="box"):
        now = int(time.time())
        claims = {"iss": ISSUER, "aud": "authenticated", "exp": now + 600, "iat": now,
                  "sub": sub, "client_id": client_id}
        value = jwt.encode(claims, key, algorithm="ES256", headers={"kid": "k1"})
        return {"Authorization": f"Bearer {value}"}

    return bearer


def _owner(c):
    return {"Authorization": f"Bearer {c.owner.secret}"}


def _events(c, name):
    return [e for e in c.ledger.tail(2000) if e["event"] == name]


def _confirmed(door, path, headers, body):
    """Both legs, with the button: the first leg's challenge, spent by the second."""
    first = door.post(path, headers=headers, json=body)
    assert first.status_code == 200 and first.json()["result"] == "confirm", first.content
    return door.post(path, headers=headers, json={
        **body, "confirm": {"challenge": first.json()["challenge"], "proof": "button"}})


def _project(c, name):
    return c.nodes.create("project", name, c.nodes.user_root(), token=c.owner, **KW)


def _admin(c, sub="alice"):
    c.identity.grant_user(sub, name=sub, role="admin", scopes=["*"], **KW)


# -- grants ----------------------------------------------------------------------------------------
def test_the_grant_list_is_an_admins_over_everything(c, door, sign):
    _admin(c)
    c.identity.grant_user("bob", name="bob", role="reader", scopes=["*"], **KW)
    body = door.get("/v1/grants", headers=sign("alice")).json()
    assert [g["sub"] for g in body["grants"]] == ["alice", "bob"]
    assert set(body["grants"][0]) == {"sub", "name", "capabilities", "scopes", "created_at"}
    assert _events(c, "context.fetch")[-1]["details"]["read"] == "grants"
    agent = c.auth.mint(principal="client", owner=OWNER, client="a", role="admin", scopes=["*"],
                        actor=OWNER, by_principal="interactive")
    for headers in (sign("bob"), {"Authorization": f"Bearer {agent.secret}"}):
        assert door.get("/v1/grants", headers=headers).content == NOT_FOUND


def test_a_grant_is_confirmed_then_written(c, door):
    p = _project(c, "work")
    body = {"sub": "bob", "name": "Bob", "role": "contributor", "scopes": [p.id]}
    r = _confirmed(door, "/v1/grants", _owner(c), body)
    assert r.status_code == 200
    assert r.json()["grant"]["capabilities"] == ["fetch", "remember"]
    assert c.backend.get_user_grant("bob")["scopes"] == [p.id]
    granted = _events(c, "identity.grant")[-1]
    assert granted["subject"] == "bob" and granted["details"]["outcome"] == "granted"
    assert _events(c, "step_up")[-1]["details"]["outcome"] == "confirmed"


def test_a_second_leg_with_other_terms_writes_nothing(c, door):
    first = door.post("/v1/grants", headers=_owner(c),
                      json={"sub": "bob", "name": "Bob", "role": "reader", "scopes": ["*"]})
    r = door.post("/v1/grants", headers=_owner(c), json={
        "sub": "bob", "name": "Bob", "role": "admin", "scopes": ["*"],
        "confirm": {"challenge": first.json()["challenge"], "proof": "button"}})
    assert r.json()["result"] == "confirm"  # a fresh challenge
    assert _events(c, "step_up")[-1]["details"]["reason"] == "mismatch"
    assert c.backend.get_user_grant("bob") is None


def test_a_grant_never_exceeds_the_granters_own(c, door, sign):
    c.identity.grant_user("alice", name="alice", capabilities=["admin", "fetch"], scopes=["*"],
                          **KW)
    wider = {"sub": "bob", "name": "Bob", "role": "contributor", "scopes": ["*"]}
    assert door.post("/v1/grants", headers=sign("alice"), json=wider).content == NOT_FOUND
    nowhere = {"sub": "bob", "name": "Bob", "role": "reader", "scopes": ["no-such-node"]}
    assert door.post("/v1/grants", headers=_owner(c), json=nowhere).content == NOT_FOUND


@pytest.mark.parametrize("body", [
    {"sub": "bob", "name": "Bob", "role": "reader", "capabilities": ["fetch"], "scopes": ["*"]},
    {"sub": "bob", "name": "Bob", "scopes": ["*"]},
    {"sub": "bob", "name": "Bob", "role": "reader", "scopes": []},
    {"sub": "b b", "name": "Bob", "role": "reader", "scopes": ["*"]},
    {"sub": "bob", "name": " ", "role": "reader", "scopes": ["*"]},
    {"sub": "bob", "name": "Bob", "role": "emperor", "scopes": ["*"]},
    {"sub": "bob", "name": "Bob", "capabilities": "fetch", "scopes": ["*"]},
])
def test_a_grant_of_the_wrong_shape_is_400(c, door, body):
    r = door.post("/v1/grants", headers=_owner(c), json=body)
    assert (r.status_code, r.content) == (400, INVALID)


def test_the_last_admin_is_neither_narrowed_nor_revoked(c, door):
    _admin(c)
    narrower = {"sub": "alice", "name": "alice", "role": "reader", "scopes": ["*"]}
    r = _confirmed(door, "/v1/grants", _owner(c), narrower)
    assert (r.status_code, r.json()) == (409, {"error": "last_admin"})
    assert r.headers["cache-control"] == "no-store"
    assert _events(c, "identity.grant")[-1]["details"]["outcome"] == "refused"
    assert _events(c, "step_up")[-1]["details"]["outcome"] == "confirmed"
    r = door.delete("/v1/grants/alice", headers=_owner(c))
    assert (r.status_code, r.json()) == (409, {"error": "last_admin"})
    _admin(c, "carol")
    assert door.delete("/v1/grants/alice", headers=_owner(c)).json() == {"result": "revoked"}
    assert door.delete("/v1/grants/alice", headers=_owner(c)).content == NOT_FOUND
    assert door.delete("/v1/grants/nobody", headers=_owner(c)).content == NOT_FOUND


# -- agents ----------------------------------------------------------------------------------------
def _register(door, headers, authorization="auth-1", client_id="agent-a", **over):
    body = {"authorization_id": authorization, "client_id": client_id, "name": "Notes <b>bot</b>",
            "role": "contributor", "scopes": ["*"], **over}
    return _confirmed(door, "/v1/agents", headers, body)


def test_an_admin_registers_an_agent_for_themself_once_per_authorization(c, door, sign):
    _admin(c)
    first = door.post("/v1/agents", headers=sign("alice"), json={
        "authorization_id": "auth-1", "client_id": "agent-a", "name": "Notes <b>bot</b>",
        "role": "contributor", "scopes": ["*"]}).json()
    assert first["newly"] == [] and first["registers"] == {"client_id": "agent-a",
                                                           "name": "Notes <b>bot</b>"}
    assert _events(c, "context.fetch")[-1]["details"]["registers"] == first["registers"]
    r = _register(door, sign("alice"))
    assert r.status_code == 200
    agent = r.json()["agent"]
    assert (agent["client_id"], agent["sub"], agent["last_seen"]) == ("agent-a", "alice", None)
    entry = _events(c, "identity.grant")[-1]
    assert entry["details"]["kind"] == "agent" and entry["details"]["authorization_id"] == "auth-1"
    # The same authorization never registers twice, even for another client.
    assert _register(door, sign("alice"), client_id="agent-b").content == NOT_FOUND
    assert c.backend.get_agent_registration("agent-b", "alice") is None


def test_only_a_signed_in_admin_registers_an_agent(c, door, sign):
    c.identity.grant_user("bob", name="bob", role="operator", scopes=["*"], **KW)
    body = {"authorization_id": "a", "client_id": "x", "name": "x", "role": "reader",
            "scopes": ["*"]}
    assert door.post("/v1/agents", headers=sign("bob"), json=body).content == NOT_FOUND
    # The owner token serves no provider user, so there is nobody to register an agent for.
    assert door.post("/v1/agents", headers=_owner(c), json=body).content == NOT_FOUND


def test_agents_are_listed_to_whom_they_serve_and_revoked(c, door, sign):
    _admin(c)
    _admin(c, "carol")
    assert _register(door, sign("alice")).status_code == 200
    assert _register(door, sign("carol"), authorization="auth-2").status_code == 200
    c.identity.grant_user("bob", name="bob", role="reader", scopes=["*"], **KW)
    assert door.get("/v1/agents", headers=sign("bob")).json() == {"agents": []}
    mine = door.get("/v1/agents", headers=sign("alice")).json()["agents"]
    assert {(a["client_id"], a["sub"]) for a in mine} == {("agent-a", "alice"),
                                                          ("agent-a", "carol")}  # an admin's
    assert len(door.get("/v1/agents", headers=_owner(c)).json()["agents"]) == 2
    # Another person's registration is not bob's to revoke; alice's own is hers.
    assert door.delete("/v1/agents/agent-a?sub=alice", headers=sign("bob")).content == NOT_FOUND
    assert door.delete("/v1/agents/agent-a", headers=sign("alice")).json() == {
        "result": "revoked"}
    assert door.delete("/v1/agents/agent-a", headers=sign("alice")).content == NOT_FOUND
    assert door.delete("/v1/agents/agent-a?sub=carol", headers=_owner(c)).status_code == 200
    assert _events(c, "identity.revoke")[-1]["details"]["kind"] == "agent"


def test_the_agent_log_shows_what_it_did_that_the_reader_sees_now(c, door, sign):
    _admin(c)
    _admin(c, "carol")
    work, private = _project(c, "work"), _project(c, "private")
    assert _register(door, sign("alice")).status_code == 200
    agent = sign("alice", "agent-a")
    for p in (work, private):
        assert door.post("/v1/items", headers=agent,
                         json={"body": f"in {p.name}", "scope": p.id}).status_code == 200
    assert door.get("/v1/items/no-such-item", headers=agent).status_code == 404  # a probe
    log = door.get("/v1/agents/agent-a/log", headers=sign("alice")).json()["entries"]
    assert [e["event"] for e in log] == ["item.add", "item.add"]
    assert set(log[0]) == {"seq", "ts", "event", "subject", "scope"}
    assert log[0]["seq"] > log[1]["seq"]  # newest first
    seen = door.get("/v1/agents", headers=sign("alice")).json()["agents"][0]["last_seen"]
    assert seen is not None
    # Narrowed to `work`, alice's log leaves out what happened in `private`, with no trace.
    c.identity.grant_user("alice", name="alice", role="admin", scopes=[work.id], **KW)
    log = door.get("/v1/agents/agent-a/log", headers=sign("alice")).json()["entries"]
    assert [e["scope"] for e in log] == [work.id]
    assert _events(c, "context.fetch")[-1]["details"]["read"] == "agent_log"
    assert len(door.get("/v1/agents/agent-a/log?sub=alice&limit=1",
                        headers=_owner(c)).json()["entries"]) == 1
    for bad in ("0", "201", "x"):
        assert door.get(f"/v1/agents/agent-a/log?limit={bad}",
                        headers=sign("alice")).content == INVALID
    assert door.get("/v1/agents/nobody/log", headers=sign("alice")).content == NOT_FOUND


def test_every_route_here_refuses_a_client_principal(c, door, sign):
    _admin(c)
    assert _register(door, sign("alice")).status_code == 200
    agent = sign("alice", "agent-a")
    for method, path in [("GET", "/v1/grants"), ("GET", "/v1/agents"),
                         ("DELETE", "/v1/agents/agent-a"), ("GET", "/v1/agents/agent-a/log"),
                         ("DELETE", "/v1/grants/alice")]:
        r = door.request(method, path, headers=agent)
        assert (r.status_code, r.content) == (404, NOT_FOUND), (method, path)
