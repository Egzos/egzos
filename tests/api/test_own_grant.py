# Copyright 2026 Ali Sasanian
# SPDX-License-Identifier: LicenseRef-PolyForm-Strict-1.0.0
"""rest.md §4.3, "A person reads their own grant": `GET /v1/grant` serves a person signed in at
the provider through this container's own client their own grant's capabilities and node ids, and
nothing else; every other caller gets the one refusal and its probe; a parameter is `400` to every
caller alike; and `GET /v1/limits` names `grants.own` where it is served (§4.6)."""

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


@pytest.fixture
def c(tmp_path):
    box = Container(tmp_path)
    box.owner = box.init()
    return box


@pytest.fixture
def door(c):
    return TestClient(create_app(c))


@pytest.fixture
def bearer(c):
    """A bearer value per kind of caller. alice is an admin over everything; bob reads one place
    and has an agent and a terminal of his own."""
    key = ec.generate_private_key(ec.SECP256R1())
    jwk = {**jwt.algorithms.ECAlgorithm.to_jwk(key.public_key(), as_dict=True), "kid": "k1",
           "alg": "ES256"}
    c.set_config("identity.issuer", ISSUER, token=c.owner)
    c.set_config("identity.client_id", "box", token=c.owner)
    jwks = Jwks("x", fetch=lambda url: {"keys": [jwk]})
    c.identity._jwks_for = lambda url: jwks
    c.p = c.nodes.create("project", "p", c.nodes.user_root(), token=c.owner, **KW)
    c.identity.grant_user("alice", name="Alice", role="admin", scopes=["*"], **KW)
    c.identity.grant_user("bob", name="Bob", capabilities=["remember", "fetch"], scopes=[c.p.id],
                          **KW)
    for client_id, kind in (("helper", "agent"), ("laptop", "terminal")):
        c.backend.put_agent_registration({
            "client_id": client_id, "sub": "bob", "kind": kind, "name": client_id,
            "capabilities": ["fetch"], "scopes": [c.p.id], "created_at": "2026-11-01T00:00:00Z",
            "revoked": False})
    agent = c.auth.mint(principal="client", owner=OWNER, client="probe", role="admin",
                        scopes=["*"], actor=OWNER, by_principal="interactive")
    person = c.auth.mint(principal="interactive", owner="user:bob", client="tab", role="admin",
                         scopes=["*"], actor=OWNER, by_principal="interactive")

    def provider(sub, client_id="box"):
        now = int(time.time())
        return jwt.encode({"iss": ISSUER, "aud": "authenticated", "exp": now + 600, "iat": now,
                           "sub": sub, "client_id": client_id}, key, algorithm="ES256",
                          headers={"kid": "k1"})

    values = {"alice": provider("alice"), "bob": provider("bob"),
              "bob's agent": provider("bob", "helper"), "bob's terminal": provider("bob", "laptop"),
              "the owner's token": c.owner.secret, "an agent's token": agent.secret,
              "a container token naming a person": person.secret}
    return lambda who: {"Authorization": f"Bearer {values[who]}"}


def _reads(c):
    return [e for e in c.ledger.tail(3000) if e["event"] == "context.fetch"]


def test_a_person_reads_their_own_grant_as_capabilities_and_node_ids(c, door, bearer):
    r = door.get("/v1/grant", headers=bearer("bob"))
    assert r.status_code == 200
    assert r.json() == {"grant": {"capabilities": ["fetch", "remember"], "scopes": [c.p.id]}}
    read = _reads(c)[-1]
    assert (read["actor"], read["principal"], read["subject"], read["scope"]) == (
        "user:bob", "interactive", None, None)
    assert (read["details"]["read"], read["details"]["items"]) == ("grant", [])


def test_an_admin_over_everything_reads_star_and_nothing_of_anyone_else(c, door, bearer):
    r = door.get("/v1/grant", headers=bearer("alice"))
    assert r.json() == {"grant": {"capabilities": ["admin", "curate", "fetch", "organize",
                                                   "publish", "remember"], "scopes": ["*"]}}
    assert "bob" not in r.text and "Alice" not in r.text  # no sub, name or other grant


def test_it_serves_only_ids_of_places_that_exist_and_star(c, door, bearer):
    # A record may hold what this door would never write: a ref, or an id whose node is gone.
    grant = c.backend.get_user_grant("bob")
    c.backend.put_user_grant({**grant, "scopes": [c.p.id, "project:p", "01ARZ3NDEKTSV4RRFFQ69G5FAV",
                                                  "*"]})
    assert door.get("/v1/grant", headers=bearer("bob")).json()["grant"]["scopes"] == [c.p.id, "*"]


@pytest.mark.parametrize("who", ["bob's agent", "bob's terminal", "the owner's token",
                                 "an agent's token", "a container token naming a person"])
def test_every_other_caller_gets_the_one_refusal_and_its_probe(c, door, bearer, who):
    reads = len(_reads(c))
    r = door.get("/v1/grant", headers=bearer(who))
    assert (r.status_code, r.content) == (404, NOT_FOUND)
    assert [(e["details"]["items"], e["details"].get("read")) for e in _reads(c)[reads:]] == [
        ([], None)]  # the probe, never the read


def test_a_grant_revoked_after_the_door_is_the_refusal(c, door, bearer, monkeypatch):
    verify = c.identity.verify

    def verified_then_revoked(value, **kw):
        token = verify(value, **kw)
        c.identity.revoke_user("bob", **KW)
        return token

    monkeypatch.setattr(c.identity, "verify", verified_then_revoked)
    assert door.get("/v1/grant", headers=bearer("bob")).content == NOT_FOUND


@pytest.mark.parametrize("who", ["bob", "alice", "bob's agent", "the owner's token"])
@pytest.mark.parametrize("query", ["?sub=alice", "?x=", "?a=1&a=2"])
def test_any_parameter_is_400_to_every_caller_alike_and_reads_nothing(c, door, bearer, who, query):
    reads = len(_reads(c))
    r = door.get(f"/v1/grant{query}", headers=bearer(who))
    assert (r.status_code, r.content) == (400, INVALID)
    assert len(_reads(c)) == reads


def test_no_bearer_is_401_and_another_method_the_refusal(door, bearer):
    assert door.get("/v1/grant").status_code == 401
    assert door.post("/v1/grant", headers=bearer("bob"), json={}).content == NOT_FOUND


def test_the_limits_name_grants_own_where_the_read_is_served(door, bearer):
    assert door.get("/v1/limits", headers=bearer("bob")).json()["features"] == [
        "terminals.machine", "grants.own"]
