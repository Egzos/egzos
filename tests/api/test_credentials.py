# Copyright 2026 Ali Sasanian
# SPDX-License-Identifier: LicenseRef-PolyForm-Strict-1.0.0
"""rest.md §4.3 and identity.md §5: Face ID / Touch ID for the confirm. A person registers a
credential, the biometric proof confirms, and once they have one the button is refused for them."""

from __future__ import annotations

import time

import jwt
import pytest
from authenticator import SoftAuthenticator
from cryptography.hazmat.primitives.asymmetric import ec
from fastapi.testclient import TestClient

from egzos.api.app import create_app
from egzos.container import OWNER, Container
from egzos.identity import Jwks

EGZOS = "https://egzos.io"
ISSUER = "https://project.supabase.co/auth/v1"
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


def _h(token, origin=EGZOS):
    value = token.secret if hasattr(token, "secret") else token
    return {"Authorization": f"Bearer {value}", **({"Origin": origin} if origin else {})}


def _events(c, name):
    return [e for e in c.ledger.tail(3000) if e["event"] == name]


def _enrol(door, token, device, *, headers=None):
    """A first credential: the first leg, then the attestation with the button."""
    h = headers or _h(token)
    first = door.post("/v1/credentials", headers=h).json()
    assert first["result"] == "register" and "confirm" not in first
    r = door.post("/v1/credentials", headers=h, json={
        "challenge": first["challenge"], "attestation": device.create(first["webauthn"]),
        "confirm": {"challenge": first["challenge"], "proof": "button"}, "name": "phone"})
    return r


@pytest.fixture
def widening(c):
    root = c.nodes.user_root()
    nk = {"token": c.owner, **KW}
    mine = c.nodes.create("project", "mine", root, **nk)
    ours = c.nodes.create("project", "ours", root, **nk)
    note = c.store.add(body="a note", scope=mine, **nk)
    c.identity.grant_user("bob", name="Bob", role="reader", scopes=[ours.id], **KW)
    return note, ours


# -- registering the first credential -------------------------------------------------------------
def test_the_owner_enrols_a_first_credential(c, door):
    phone = SoftAuthenticator(EGZOS)
    r = _enrol(door, c.owner, phone)
    assert r.status_code == 200 and set(r.json()["credential"]) == {
        "id", "name", "created_at", "last_used"}
    listed = door.get("/v1/credentials", headers=_h(c.owner)).json()["credentials"]
    assert [x["name"] for x in listed] == ["phone"]
    added = _events(c, "identity.credential")[-1]["details"]
    assert added["op"] == "add" and added["outcome"] == "added"
    stored = c.backend.list_credentials(OWNER)[0]
    assert stored["rp_id"] == "egzos.io" and "public_key" not in listed[0]


def test_registration_needs_an_allowed_browser_origin(c, door):
    for origin in (None, "https://evil.example"):
        r = door.post("/v1/credentials", headers=_h(c.owner, origin))
        assert r.content == NOT_FOUND


def test_a_forged_attestation_is_refused_and_recorded(c, door):
    first = door.post("/v1/credentials", headers=_h(c.owner)).json()
    elsewhere = SoftAuthenticator("https://egzos.io.evil.example")
    elsewhere.rp_id = "egzos.io"  # claims the right relying party, signs for the wrong origin
    r = door.post("/v1/credentials", headers=_h(c.owner), json={
        "challenge": first["challenge"], "attestation": elsewhere.create(first["webauthn"]),
        "confirm": {"challenge": first["challenge"], "proof": "button"}})
    assert r.json()["result"] == "register"
    assert _events(c, "identity.credential")[-1]["details"]["reason"] == "attestation"
    assert c.backend.list_credentials(OWNER) == []


def test_an_authenticator_without_user_verification_is_refused(c, door):
    r = _enrol(door, c.owner, SoftAuthenticator(EGZOS, verify_user=False))
    assert r.json()["result"] == "register"
    assert c.backend.list_credentials(OWNER) == []


# -- the biometric proof ---------------------------------------------------------------------------
def test_face_id_confirms_and_the_button_is_refused_once_a_credential_exists(c, door, widening):
    note, ours = widening
    phone = SoftAuthenticator(EGZOS)
    _enrol(door, c.owner, phone)
    first = door.post(f"/v1/items/{note.id}/move", headers=_h(c.owner), json={"to": ours.id}).json()
    assert first["webauthn"]["rpId"] == "egzos.io"
    pressed = door.post(f"/v1/items/{note.id}/move", headers=_h(c.owner), json={
        "to": ours.id, "confirm": {"challenge": first["challenge"], "proof": "button"}}).json()
    assert pressed["result"] == "confirm"
    assert _events(c, "step_up")[-1]["details"]["reason"] == "button_off"
    r = door.post(f"/v1/items/{note.id}/move", headers=_h(c.owner), json={
        "to": ours.id, "confirm": {"challenge": pressed["challenge"], "proof": "biometric",
                                   "assertion": phone.get(pressed["webauthn"])}})
    assert r.json()["result"] == "moved"
    step_up = _events(c, "step_up")[-1]["details"]
    assert step_up["outcome"] == "confirmed" and step_up["proof"] == "biometric"
    assert c.backend.list_credentials(OWNER)[0]["sign_count"] == 1


def test_an_assertion_for_another_challenge_or_device_is_refused(c, door, widening):
    note, ours = widening
    phone, stranger = SoftAuthenticator(EGZOS), SoftAuthenticator(EGZOS)
    _enrol(door, c.owner, phone)
    first = door.post(f"/v1/items/{note.id}/move", headers=_h(c.owner), json={"to": ours.id}).json()
    stolen = stranger.get(first["webauthn"])
    r = door.post(f"/v1/items/{note.id}/move", headers=_h(c.owner), json={
        "to": ours.id, "confirm": {"challenge": first["challenge"], "proof": "biometric",
                                   "assertion": stolen}}).json()
    assert r["result"] == "confirm"
    assert _events(c, "step_up")[-1]["details"]["reason"] == "assertion"
    old = phone.get(first["webauthn"])  # signed over the spent challenge
    r = door.post(f"/v1/items/{note.id}/move", headers=_h(c.owner), json={
        "to": ours.id, "confirm": {"challenge": r["challenge"], "proof": "biometric",
                                   "assertion": old}}).json()
    assert r["result"] == "confirm"
    assert _events(c, "step_up")[-1]["details"]["reason"] == "assertion"


# -- adding and removing ---------------------------------------------------------------------------
def test_a_second_credential_needs_the_first_ones_biometric(c, door):
    phone, laptop = SoftAuthenticator(EGZOS), SoftAuthenticator(EGZOS)
    _enrol(door, c.owner, phone)
    first = door.post("/v1/credentials", headers=_h(c.owner)).json()
    assert "confirm" in first and first["confirm"]["webauthn"]["rpId"] == "egzos.io"
    pressed = door.post("/v1/credentials", headers=_h(c.owner), json={
        "challenge": first["challenge"], "attestation": laptop.create(first["webauthn"]),
        "confirm": {"challenge": first["confirm"]["challenge"], "proof": "button"}}).json()
    assert pressed["result"] == "register"
    assert _events(c, "identity.credential")[-1]["details"]["reason"] == "button_refused"
    r = door.post("/v1/credentials", headers=_h(c.owner), json={
        "challenge": pressed["challenge"], "attestation": laptop.create(pressed["webauthn"]),
        "confirm": {"challenge": pressed["confirm"]["challenge"], "proof": "biometric",
                    "assertion": phone.get(pressed["confirm"]["webauthn"])}})
    assert "credential" in r.json()
    assert len(c.backend.list_credentials(OWNER)) == 2


def test_removing_a_credential_needs_a_biometric_never_the_button(c, door):
    phone = SoftAuthenticator(EGZOS)
    cred = _enrol(door, c.owner, phone).json()["credential"]
    first = door.request("DELETE", f"/v1/credentials/{cred['id']}", headers=_h(c.owner)).json()
    pressed = door.request("DELETE", f"/v1/credentials/{cred['id']}", headers=_h(c.owner), json={
        "confirm": {"challenge": first["challenge"], "proof": "button"}}).json()
    assert pressed["result"] == "confirm"
    assert _events(c, "identity.credential")[-1]["details"]["outcome"] == "refused"
    r = door.request("DELETE", f"/v1/credentials/{cred['id']}", headers=_h(c.owner), json={
        "confirm": {"challenge": pressed["challenge"], "proof": "biometric",
                    "assertion": phone.get(pressed["webauthn"])}})
    assert r.json() == {"result": "removed"}
    assert door.get("/v1/credentials", headers=_h(c.owner)).json()["credentials"] == []
    removed = _events(c, "identity.credential")[-1]["details"]
    assert removed["op"] == "remove" and removed["outcome"] == "removed"


def test_another_persons_credentials_are_an_admins_to_name(c, door):
    t = c.auth.mint(principal="interactive", owner="someone", client="tab", role="contributor",
                    scopes=["*"], actor=OWNER, by_principal="interactive")
    _enrol(door, c.owner, SoftAuthenticator(EGZOS))
    assert door.get("/v1/credentials?sub=self", headers=_h(t)).content == NOT_FOUND
    agent = c.auth.mint(principal="client", owner=OWNER, client="a", role="admin",
                        scopes=["*"], actor=OWNER, by_principal="interactive")
    assert door.get("/v1/credentials", headers=_h(agent)).content == NOT_FOUND


# -- a provider sign-in's first credential needs a fresh sign-in -----------------------------------
@pytest.fixture
def sign(c):
    key = ec.generate_private_key(ec.SECP256R1())
    jwk = {**jwt.algorithms.ECAlgorithm.to_jwk(key.public_key(), as_dict=True), "kid": "k1",
           "alg": "ES256"}
    c.set_config("identity.issuer", ISSUER, token=c.owner)
    c.set_config("identity.client_id", "box", token=c.owner)
    jwks = Jwks("x", fetch=lambda url: {"keys": [jwk]})
    c.identity._jwks_for = lambda url: jwks
    c.identity.grant_user("alice", name="Alice", role="contributor", scopes=["*"], **KW)

    def token(signed_in_ago: int) -> str:
        now = int(time.time())
        claims = {"iss": ISSUER, "aud": "authenticated", "exp": now + 600, "iat": now,
                  "sub": "alice", "client_id": "box",
                  "amr": [{"method": "otp", "timestamp": now - signed_in_ago}]}
        return jwt.encode(claims, key, algorithm="ES256", headers={"kid": "k1"})

    return token


def test_a_stale_sign_in_cannot_enrol_a_first_credential(c, door, sign):
    stale = _enrol(door, None, SoftAuthenticator(EGZOS), headers=_h(sign(3600)))
    assert stale.json()["result"] == "register"
    assert _events(c, "identity.credential")[-1]["details"]["reason"] == "not_fresh"
    fresh = _enrol(door, None, SoftAuthenticator(EGZOS), headers=_h(sign(30)))
    assert "credential" in fresh.json()
    assert c.backend.list_credentials("user:alice")[0]["person"] == "user:alice"
