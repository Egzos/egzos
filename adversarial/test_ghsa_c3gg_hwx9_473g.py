# Copyright 2026 Ali Sasanian
# SPDX-License-Identifier: LicenseRef-PolyForm-Strict-1.0.0
"""GHSA-c3gg-hwx9-473g, grants: at the REST door, ending another person's grant requires the
confirm (identity.md §4-§5, rest.md §4.3). Without one it revokes nothing and answers the first
leg; only a confirmed second leg revokes. Granting with the button also needs a fresh sign-in."""

from __future__ import annotations

import time

import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import ec
from fastapi.testclient import TestClient

from egzos.api.app import create_app
from egzos.container import OWNER, Container
from egzos.identity import Jwks

pytestmark = pytest.mark.adversarial

ISSUER = "https://project.supabase.co/auth/v1"


def _door(tmp_path):
    """A container linked to a provider: alice an admin over everything, bob a reader."""
    c = Container(tmp_path)
    owner = c.init()
    key = ec.generate_private_key(ec.SECP256R1())
    jwk = {**jwt.algorithms.ECAlgorithm.to_jwk(key.public_key(), as_dict=True), "kid": "k",
           "alg": "ES256"}
    c.set_config("identity.issuer", ISSUER, token=owner)
    c.set_config("identity.client_id", "box", token=owner)
    keys = Jwks("x", fetch=lambda url: {"keys": [jwk]})
    c.identity._jwks_for = lambda url: keys
    kw = {"actor": OWNER, "principal": "interactive"}
    c.identity.grant_user("alice", name="Alice", role="admin", scopes=["*"], **kw)
    c.identity.grant_user("bob", name="Bob", role="reader", scopes=["*"], **kw)

    def alice(signed_in_ago=0):
        now = int(time.time())
        claims = {"iss": ISSUER, "aud": "authenticated", "exp": now + 600, "iat": now,
                  "sub": "alice", "client_id": "box",
                  "amr": [{"method": "otp", "timestamp": now - signed_in_ago}]}
        value = jwt.encode(claims, key, algorithm="ES256", headers={"kid": "k"})
        return {"Authorization": f"Bearer {value}"}

    return c, TestClient(create_app(c)), alice


def test_ghsa_c3gg_hwx9_473g_ending_another_persons_grant_needs_the_confirm(tmp_path):
    c, door, alice = _door(tmp_path)
    admin = alice()

    first = door.delete("/v1/grants/bob", headers=admin)
    assert first.status_code == 200 and first.json()["result"] == "confirm"
    assert not c.backend.get_user_grant("bob")["revoked"]
    assert not [e for e in c.ledger.tail(200) if e["event"] == "identity.revoke"]

    second = door.request("DELETE", "/v1/grants/bob", headers=admin, json={
        "confirm": {"challenge": first.json()["challenge"], "proof": "button"}})
    assert second.json() == {"result": "revoked"}
    assert c.backend.get_user_grant("bob")["revoked"]


def test_ghsa_c3gg_hwx9_473g_granting_with_the_button_needs_a_fresh_sign_in(tmp_path):
    c, door, alice = _door(tmp_path)
    dave = {"sub": "dave", "name": "Dave", "role": "reader", "scopes": ["*"]}

    def grant(headers):
        first = door.post("/v1/grants", headers=headers, json=dave).json()
        assert first["result"] == "confirm" and c.backend.get_user_grant("dave") is None
        return door.post("/v1/grants", headers=headers, json={
            **dave, "confirm": {"challenge": first["challenge"], "proof": "button"}}).json()

    assert grant(alice(signed_in_ago=3600))["result"] == "confirm"
    assert c.backend.get_user_grant("dave") is None
    assert grant(alice())["grant"]["sub"] == "dave"
