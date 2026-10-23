# Copyright 2026 Ali Sasanian
# SPDX-License-Identifier: LicenseRef-PolyForm-Strict-1.0.0
"""rest.md §4.3 and identity.md §5: Face ID / Touch ID for the confirm. A person registers a
credential, the biometric proof confirms, and once they have one the button is refused for them."""

from __future__ import annotations

import json
import time

import jwt
import pytest
from authenticator import SoftAuthenticator
from cryptography.hazmat.primitives.asymmetric import ec
from fastapi.testclient import TestClient

from egzos.api.app import create_app
from egzos.cli import main
from egzos.container import OWNER, Container
from egzos.identity import Jwks

EGZOS = "https://egzos.io"
ISSUER = "https://project.supabase.co/auth/v1"
NOT_FOUND = b'{"error":"not_found"}'
KW = {"actor": OWNER, "principal": "interactive"}
ALICE = "user:alice"


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
    """A provider sign-in for a person granted admin here, `signed_in_ago` seconds old."""
    key = ec.generate_private_key(ec.SECP256R1())
    jwk = {**jwt.algorithms.ECAlgorithm.to_jwk(key.public_key(), as_dict=True), "kid": "k1",
           "alg": "ES256"}
    c.set_config("identity.issuer", ISSUER, token=c.owner)
    c.set_config("identity.client_id", "box", token=c.owner)
    jwks = Jwks("x", fetch=lambda url: {"keys": [jwk]})
    c.identity._jwks_for = lambda url: jwks
    for sub in ("alice", "carol"):
        c.identity.grant_user(sub, name=sub.title(), role="admin", scopes=["*"], **KW)

    def headers(sub="alice", signed_in_ago=30, origin=EGZOS):
        now = int(time.time())
        claims = {"iss": ISSUER, "aud": "authenticated", "exp": now + 600, "iat": now,
                  "sub": sub, "client_id": "box",
                  "amr": [{"method": "otp", "timestamp": now - signed_in_ago}]}
        value = jwt.encode(claims, key, algorithm="ES256", headers={"kid": "k1"})
        return {"Authorization": f"Bearer {value}", **({"Origin": origin} if origin else {})}

    return headers


def _h(token, origin=EGZOS):
    return {"Authorization": f"Bearer {token.secret}", **({"Origin": origin} if origin else {})}


def _events(c, name):
    return [e for e in c.ledger.tail(3000) if e["event"] == name]


def _enrol(door, h, device):
    """A first credential: the first leg, then the attestation with the button."""
    first = door.post("/v1/credentials", headers=h).json()
    assert first["result"] == "register" and first["confirm"]["webauthn"] is None
    return door.post("/v1/credentials", headers=h, json={
        "challenge": first["challenge"], "attestation": device.create(first["webauthn"]),
        "confirm": {"challenge": first["confirm"]["challenge"], "proof": "button"},
        "name": "phone"})


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
def test_a_person_enrols_a_first_credential_with_the_button_and_a_fresh_sign_in(c, door, sign):
    reads = len(_events(c, "context.fetch"))
    r = _enrol(door, sign(), SoftAuthenticator(EGZOS))
    assert len(_events(c, "context.fetch")) == reads  # nothing listed, nothing read
    assert r.status_code == 200 and set(r.json()["credential"]) == {
        "id", "name", "created_at", "last_used"}
    step_up, added = _events(c, "step_up")[-1], _events(c, "identity.credential")[-1]
    assert (step_up["details"]["proof"], step_up["details"]["outcome"]) == ("button", "confirmed")
    assert step_up["details"]["act"] == "credential.add" and step_up["seq"] < added["seq"]
    assert (added["details"]["op"], added["details"]["outcome"]) == ("add", "added")
    listed = door.get("/v1/credentials", headers=sign()).json()["credentials"]
    assert [x["name"] for x in listed] == ["phone"] and "public_key" not in listed[0]
    assert _events(c, "context.fetch")[-1]["details"]["read"] == "credentials"
    assert c.backend.list_credentials(ALICE)[0]["rp_id"] == "egzos.io"


@pytest.mark.parametrize("buttons", ["true", "false"])
def test_a_container_token_enrols_no_first_credential_at_the_door(c, door, buttons):
    """The door is never the owner's own surface, and a container token carries no sign-in to be
    fresh: with buttons on it is `not_fresh`, with them off `button_refused` (a1r on #290)."""
    c.set_config("confirm.allow_button", buttons, token=c.owner)
    tab = c.auth.mint(principal="interactive", owner="someone", client="tab", role="admin",
                      scopes=["*"], actor=OWNER, by_principal="interactive")
    for token in (c.owner, tab):
        r = _enrol(door, _h(token), SoftAuthenticator(EGZOS))
        assert r.json()["result"] == "register"
        reason = _events(c, "identity.credential")[-1]["details"]["reason"]
        assert reason == ("not_fresh" if buttons == "true" else "button_refused")
    assert c.backend.list_credentials() == []


def test_a_stale_sign_in_cannot_enrol_a_first_credential(c, door, sign):
    stale = _enrol(door, sign(signed_in_ago=3600), SoftAuthenticator(EGZOS))
    assert stale.json()["result"] == "register"
    assert _events(c, "identity.credential")[-1]["details"]["reason"] == "not_fresh"
    assert _events(c, "step_up")[-1]["details"]["proof"] == "button"  # the proof, on the record
    assert "credential" in _enrol(door, sign(), SoftAuthenticator(EGZOS)).json()


def test_registration_needs_an_allowed_browser_origin(c, door, sign):
    for origin in (None, "https://evil.example"):
        assert door.post("/v1/credentials", headers=sign(origin=origin)).content == NOT_FOUND


def test_a_forged_attestation_is_refused_and_recorded(c, door, sign):
    first = door.post("/v1/credentials", headers=sign()).json()
    elsewhere = SoftAuthenticator("https://egzos.io.evil.example")
    elsewhere.rp_id = "egzos.io"  # claims the right relying party, signs for the wrong origin
    r = door.post("/v1/credentials", headers=sign(), json={
        "challenge": first["challenge"], "attestation": elsewhere.create(first["webauthn"]),
        "confirm": {"challenge": first["confirm"]["challenge"], "proof": "button"}})
    assert r.json()["result"] == "register"
    assert _events(c, "identity.credential")[-1]["details"]["reason"] == "attestation"
    assert c.backend.list_credentials(ALICE) == []


def test_an_authenticator_without_user_verification_is_refused(c, door, sign):
    r = _enrol(door, sign(), SoftAuthenticator(EGZOS, verify_user=False))
    assert r.json()["result"] == "register"
    assert c.backend.list_credentials(ALICE) == []


def test_a_persons_user_handle_is_this_containers_own(tmp_path, c):
    """The same person (the owner, `self`, on both) gets a different handle on each container,
    so an authenticator is never handed an identifier that links them (a1r on #290)."""
    other = Container(tmp_path / "other")
    theirs_owner = other.init()

    def handle(box, token):
        return box.confirm.begin_registration(token, origin=EGZOS, name="x")["webauthn"]["user"]

    assert handle(c, c.owner)["id"] == handle(c, c.owner)["id"]  # stable here
    assert handle(c, c.owner)["id"] != handle(other, theirs_owner)["id"]


# -- the biometric proof ---------------------------------------------------------------------------
def test_face_id_confirms_and_the_button_is_refused_once_a_credential_exists(c, door, sign,
                                                                              widening):
    note, ours = widening
    phone = SoftAuthenticator(EGZOS)
    _enrol(door, sign(), phone)
    first = door.post(f"/v1/items/{note.id}/move", headers=sign(), json={"to": ours.id}).json()
    assert first["webauthn"]["rpId"] == "egzos.io"
    pressed = door.post(f"/v1/items/{note.id}/move", headers=sign(), json={
        "to": ours.id, "confirm": {"challenge": first["challenge"], "proof": "button"}}).json()
    assert pressed["result"] == "confirm"
    assert _events(c, "step_up")[-1]["details"]["reason"] == "button_off"
    r = door.post(f"/v1/items/{note.id}/move", headers=sign(), json={
        "to": ours.id, "confirm": {"challenge": pressed["challenge"], "proof": "biometric",
                                   "assertion": phone.get(pressed["webauthn"])}})
    assert r.json()["result"] == "moved"
    step_up = _events(c, "step_up")[-1]["details"]
    assert step_up["outcome"] == "confirmed" and step_up["proof"] == "biometric"
    assert c.backend.list_credentials(ALICE)[0]["sign_count"] == 1


def test_an_assertion_for_another_challenge_or_device_is_refused(c, door, sign, widening):
    note, ours = widening
    phone, stranger = SoftAuthenticator(EGZOS), SoftAuthenticator(EGZOS)
    _enrol(door, sign(), phone)
    first = door.post(f"/v1/items/{note.id}/move", headers=sign(), json={"to": ours.id}).json()
    r = door.post(f"/v1/items/{note.id}/move", headers=sign(), json={
        "to": ours.id, "confirm": {"challenge": first["challenge"], "proof": "biometric",
                                   "assertion": stranger.get(first["webauthn"])}}).json()
    assert r["result"] == "confirm"
    assert _events(c, "step_up")[-1]["details"]["reason"] == "assertion"
    old = phone.get(first["webauthn"])  # signed over the spent challenge
    r = door.post(f"/v1/items/{note.id}/move", headers=sign(), json={
        "to": ours.id, "confirm": {"challenge": r["challenge"], "proof": "biometric",
                                   "assertion": old}}).json()
    assert r["result"] == "confirm"
    assert _events(c, "step_up")[-1]["details"]["reason"] == "assertion"


# -- adding and removing ---------------------------------------------------------------------------
def test_a_second_credential_needs_the_first_ones_biometric(c, door, sign):
    phone, laptop = SoftAuthenticator(EGZOS), SoftAuthenticator(EGZOS)
    _enrol(door, sign(), phone)
    first = door.post("/v1/credentials", headers=sign()).json()
    assert first["confirm"]["webauthn"]["rpId"] == "egzos.io"
    assert _events(c, "context.fetch")[-1]["details"]["read"] == "credentials"
    reads = len(_events(c, "context.fetch"))
    pressed = door.post("/v1/credentials", headers=sign(), json={
        "challenge": first["challenge"], "attestation": laptop.create(first["webauthn"]),
        "confirm": {"challenge": first["confirm"]["challenge"], "proof": "button"}}).json()
    assert pressed["result"] == "register"
    assert _events(c, "identity.credential")[-1]["details"]["reason"] == "button_refused"
    assert len(_events(c, "context.fetch")) == reads + 1  # the fresh leg lists them again: a read
    r = door.post("/v1/credentials", headers=sign(), json={
        "challenge": pressed["challenge"], "attestation": laptop.create(pressed["webauthn"]),
        "confirm": {"challenge": pressed["confirm"]["challenge"], "proof": "biometric",
                    "assertion": phone.get(pressed["confirm"]["webauthn"])}})
    assert "credential" in r.json()
    assert len(c.backend.list_credentials(ALICE)) == 2


def test_removing_a_credential_needs_a_biometric_never_the_button(c, door, sign):
    phone = SoftAuthenticator(EGZOS)
    cred = _enrol(door, sign(), phone).json()["credential"]
    url = f"/v1/credentials/{cred['id']}"
    first = door.request("DELETE", url, headers=sign()).json()
    pressed = door.request("DELETE", url, headers=sign(), json={
        "confirm": {"challenge": first["challenge"], "proof": "button"}}).json()
    assert pressed["result"] == "confirm"
    refused = _events(c, "identity.credential")[-1]["details"]
    assert (refused["outcome"], refused["reason"]) == ("refused", "button_refused")
    replayed = door.request("DELETE", url, headers=sign(), json={
        "confirm": {"challenge": first["challenge"], "proof": "biometric",
                    "assertion": phone.get(first["webauthn"])}}).json()
    assert replayed["result"] == "confirm"
    assert _events(c, "identity.credential")[-1]["details"]["reason"] == "stale"  # spent
    r = door.request("DELETE", url, headers=sign(), json={
        "confirm": {"challenge": replayed["challenge"], "proof": "biometric",
                    "assertion": phone.get(replayed["webauthn"])}})
    assert r.json() == {"result": "removed"}
    assert door.get("/v1/credentials", headers=sign()).json()["credentials"] == []
    removed = _events(c, "identity.credential")[-1]["details"]
    assert removed["op"] == "remove" and removed["outcome"] == "removed"


def test_an_admin_recovers_a_persons_credential_with_their_own_biometric(c, door, sign):
    alices = _enrol(door, sign(), SoftAuthenticator(EGZOS)).json()["credential"]
    carols_phone = SoftAuthenticator(EGZOS)
    _enrol(door, sign("carol"), carols_phone)
    url = f"/v1/credentials/{alices['id']}?sub=alice"
    first = door.request("DELETE", url, headers=sign("carol")).json()
    r = door.request("DELETE", url, headers=sign("carol"), json={
        "confirm": {"challenge": first["challenge"], "proof": "biometric",
                    "assertion": carols_phone.get(first["webauthn"])}})
    assert r.json() == {"result": "removed"}
    removed = _events(c, "identity.credential")[-1]
    assert removed["actor"] == "user:carol" and removed["subject"] == ALICE
    # A person who is no admin names nobody else's credentials.
    c.identity.grant_user("dave", name="Dave", role="contributor", scopes=["*"], **KW)
    assert door.get("/v1/credentials?sub=carol", headers=sign("dave")).content == NOT_FOUND


def test_an_agent_is_never_served_credentials(c, door):
    agent = c.auth.mint(principal="client", owner=OWNER, client="a", role="admin",
                        scopes=["*"], actor=OWNER, by_principal="interactive")
    assert door.get("/v1/credentials", headers=_h(agent)).content == NOT_FOUND


def test_the_owners_cli_removal_is_on_the_record(c, door, sign, monkeypatch, capsys):
    cred = _enrol(door, sign(), SoftAuthenticator(EGZOS)).json()["credential"]
    monkeypatch.setenv("EGZOS_HOME", str(c.home))
    monkeypatch.delenv("EGZOS_TOKEN", raising=False)
    capsys.readouterr()
    assert main(["--json", "credential", "rm", cred["id"]]) == 0
    assert json.loads(capsys.readouterr().out)
    removed = _events(Container(c.home), "identity.credential")[-1]
    assert (removed["actor"], removed["details"]["op"]) == (OWNER, "remove")


def test_the_owners_cli_list_is_a_read_on_the_record(c, door, sign, monkeypatch, capsys):
    _enrol(door, sign(), SoftAuthenticator(EGZOS))
    monkeypatch.setenv("EGZOS_HOME", str(c.home))
    monkeypatch.delenv("EGZOS_TOKEN", raising=False)
    capsys.readouterr()
    assert main(["--json", "credential", "ls"]) == 0
    listed = json.loads(capsys.readouterr().out)
    assert "public_key" not in json.dumps(listed)
    read = _events(Container(c.home), "context.fetch")[-1]
    assert (read["actor"], read["details"]["read"]) == (OWNER, "credentials")
