# Copyright 2026 Ali Sasanian
# SPDX-License-Identifier: LicenseRef-PolyForm-Strict-1.0.0
"""rest.md §4.6: `GET /v1/limits` tells any valid token, an agent's included, the contract's
version, the words for what this door serves beyond release 0.2.0, and the upload limits; it reads
two config keys and one constant, and appends one read."""

from __future__ import annotations

import time

import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import ec
from fastapi.testclient import TestClient

import egzos._types as t
from egzos.api.app import FEATURES, create_app
from egzos.container import OWNER, Container
from egzos.identity import Jwks
from egzos.store.uploads import MAX_HELD

ISSUER = "https://project.supabase.co/auth/v1"
KW = {"actor": OWNER, "principal": "interactive"}
KEYS = {"contract", "features", "upload_max_bytes", "inline_max_bytes", "uploads_held_max"}


@pytest.fixture
def c(tmp_path):
    box = Container(tmp_path)
    box.owner = box.init()
    return box


@pytest.fixture
def door(c):
    return TestClient(create_app(c))


@pytest.fixture
def callers(c):
    """One bearer of each kind the door verifies: the owner's `Token`, an agent's `Token`, a
    person, an agent registered for them and a terminal of theirs (the last three, provider
    tokens)."""
    key = ec.generate_private_key(ec.SECP256R1())
    jwk = {**jwt.algorithms.ECAlgorithm.to_jwk(key.public_key(), as_dict=True), "kid": "k1",
           "alg": "ES256"}
    c.set_config("identity.issuer", ISSUER, token=c.owner)
    c.set_config("identity.client_id", "box", token=c.owner)
    jwks = Jwks("x", fetch=lambda url: {"keys": [jwk]})
    c.identity._jwks_for = lambda url: jwks
    c.identity.grant_user("bob", name="Bob", role="reader", scopes=["*"], **KW)
    for client_id, kind in (("helper", "agent"), ("laptop", "terminal")):
        c.backend.put_agent_registration({
            "client_id": client_id, "sub": "bob", "kind": kind, "name": client_id,
            "capabilities": ["fetch"], "scopes": ["*"], "created_at": "2026-11-01T00:00:00Z",
            "revoked": False})
    agent = c.auth.mint(principal="client", owner=OWNER, client="probe", role="reader",
                        scopes=["*"], actor=OWNER, by_principal="interactive")

    def provider(client_id):
        now = int(time.time())
        claims = {"iss": ISSUER, "aud": "authenticated", "exp": now + 600, "iat": now,
                  "sub": "bob", "client_id": client_id}
        return jwt.encode(claims, key, algorithm="ES256", headers={"kid": "k1"})

    return {"owner": (c.owner.secret, OWNER, "interactive"),
            "agent token": (agent.secret, OWNER, "client"),
            "person": (provider("box"), "user:bob", "interactive"),
            "registered agent": (provider("helper"), "agent:helper", "client"),
            "terminal": (provider("laptop"), "user:bob", "interactive")}


@pytest.mark.parametrize("who", ["owner", "agent token", "person", "registered agent",
                                 "terminal"])
def test_every_valid_token_reads_what_the_door_serves_and_the_read_is_recorded(
        c, door, callers, who):
    bearer, actor, principal = callers[who]
    r = door.get("/v1/limits", headers={"Authorization": f"Bearer {bearer}"})
    assert r.status_code == 200 and set(r.json()) == KEYS
    assert r.json() == {"contract": "1.1", "features": ["terminals.machine", "grants.own"],
                        "upload_max_bytes": 100 * 1024 * 1024, "inline_max_bytes": 64 * 1024,
                        "uploads_held_max": 16}
    read = c.ledger.tail(1)[-1]
    assert (read["event"], read["actor"], read["principal"], read["subject"], read["scope"]) == (
        "context.fetch", actor, principal, None, None)
    assert (read["details"]["read"], read["details"]["items"]) == ("limits", [])


def test_the_limits_are_the_config_as_it_stands(c, door):
    c.set_config("blobs.upload_max_bytes", 12345, token=c.owner)
    body = door.get("/v1/limits", headers={"Authorization": f"Bearer {c.owner.secret}"}).json()
    assert (body["upload_max_bytes"], body["uploads_held_max"]) == (12345, MAX_HELD)


def test_no_rename_word_is_named_before_its_route_runs():
    # §4.6: a word only once its code runs. No rename route runs in this tree.
    assert FEATURES == ("terminals.machine", "grants.own")
    assert set(FEATURES) <= set(t.DOOR_FEATURES)


@pytest.mark.parametrize("query", ["?x=1", "?features=all", "?contract=", "?a=1&a=2"])
def test_a_parameter_is_400_and_reads_nothing(c, door, query):
    seq = c.ledger.tail(1)[-1]["seq"]
    r = door.get(f"/v1/limits{query}", headers={"Authorization": f"Bearer {c.owner.secret}"})
    assert (r.status_code, r.content) == (400, b'{"error":"invalid_request"}')
    assert c.ledger.tail(1)[-1]["seq"] == seq


@pytest.mark.parametrize("headers", [{}, {"Authorization": "Bearer egz_nope"}])
def test_no_valid_token_is_the_one_unauthenticated_answer(c, door, headers):
    seq = c.ledger.tail(1)[-1]["seq"]
    r = door.get("/v1/limits", headers=headers)
    assert (r.status_code, r.content) == (401, b'{"error":"unauthorized"}')
    assert c.ledger.tail(1)[-1]["seq"] == seq


@pytest.mark.parametrize("method", ["POST", "PUT", "DELETE", "PATCH"])
def test_it_sets_nothing_another_method_is_the_refusal(c, door, method):
    r = door.request(method, "/v1/limits", headers={"Authorization": f"Bearer {c.owner.secret}"},
                     json={"blobs.upload_max_bytes": 1})
    assert (r.status_code, r.content) == (404, b'{"error":"not_found"}')
    assert c.config_value("blobs.upload_max_bytes") == 100 * 1024 * 1024
