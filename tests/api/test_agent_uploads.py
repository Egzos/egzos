# Copyright 2026 Ali Sasanian
# SPDX-License-Identifier: LicenseRef-PolyForm-Strict-1.0.0
"""rest.md §4.4 item 1 at the REST door: a `client` principal's upload whose bytes have not arrived
holds no slot of its person's 16; a `client` principal holds at most 4 such uploads, and a 5th open
answers `429` `too_many_uploads`; a client container `Token` holds its own 4. Once its bytes are
staged it holds one of its person's 16, and its bytes are refused with the same `429` while its
person holds 16, staging nothing and leaving it byteless to try again once a slot frees. An upload
recorded before this rule counts as it always did."""

from __future__ import annotations

import hashlib
import time

import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import ec
from fastapi.testclient import TestClient

from egzos.api.app import create_app
from egzos.container import OWNER, Container
from egzos.identity import Jwks
from egzos.store.uploads import AGENT_BYTELESS_MAX, MAX_HELD, UPLOAD_TTL_SECONDS

TOO_MANY = (429, b'{"error":"too_many_uploads"}')
KW = {"actor": OWNER, "principal": "interactive"}
DATA = b"an agent's file\n"
ISSUER = "https://project.supabase.co/auth/v1"


class Clock:
    def __init__(self):
        self.now = time.time()

    def __call__(self):
        return self.now


@pytest.fixture
def c(tmp_path):
    box = Container(tmp_path)
    box.owner = box.init()
    box.uploads.clock = Clock()
    return box


@pytest.fixture
def door(c):
    return TestClient(create_app(c))


@pytest.fixture
def notes(c):
    return c.nodes.create("project", "notes", c.nodes.user_root(), token=c.owner, **KW)


@pytest.fixture
def sign(c):
    """Provider sign-ins (identity.md §3): alice granted here, two agents registered for her."""
    key = ec.generate_private_key(ec.SECP256R1())
    jwk = {**jwt.algorithms.ECAlgorithm.to_jwk(key.public_key(), as_dict=True), "kid": "k1",
           "alg": "ES256"}
    c.set_config("identity.issuer", ISSUER, token=c.owner)
    c.set_config("identity.client_id", "box", token=c.owner)
    jwks = Jwks("x", fetch=lambda url: {"keys": [jwk]})
    c.identity._jwks_for = lambda url: jwks
    c.identity.grant_user("alice", name="alice", role="contributor", scopes=["*"], **KW)
    for client_id in ("a1", "a2"):
        c.backend.put_agent_registration({
            "client_id": client_id, "sub": "alice", "name": client_id,
            "capabilities": ["fetch", "remember"], "scopes": ["*"],
            "created_at": "2026-10-23T00:00:00Z", "revoked": False})

    def headers(client_id="box"):
        now = int(time.time())
        claims = {"iss": ISSUER, "aud": "authenticated", "exp": now + 600, "iat": now,
                  "sub": "alice", "client_id": client_id}
        return {"Authorization": f"Bearer {jwt.encode(claims, key, 'ES256', {'kid': 'k1'})}"}

    return headers


def _auth(token):
    return token if isinstance(token, dict) else {"Authorization": f"Bearer {token.secret}"}


def _open(door, token, scope, data=DATA):
    body = {"scope": scope, "name": "f.txt", "mime": "text/plain", "size": len(data),
            "sha256": hashlib.sha256(data).hexdigest()}
    return door.post("/v1/uploads", headers=_auth(token), json=body)


def _put(door, token, uid, data=DATA):
    return door.put(f"/v1/uploads/{uid}", headers=_auth(token), content=data)


def _client_token(c):
    return c.auth.mint(principal="client", owner=OWNER, client="agent", role="contributor",
                       scopes=["*"], actor=OWNER, by_principal="interactive")


def test_an_agent_holds_at_most_four_byteless_opens_and_a_fifth_is_429(c, door, notes, sign):
    alice, a1, a2 = sign(), sign("a1"), sign("a2")
    mine = [_open(door, a1, notes.id).json()["upload"] for _ in range(4)]
    r = _open(door, a1, notes.id)
    assert (r.status_code, r.content) == TOO_MANY and r.headers["cache-control"] == "no-store"
    # Another agent of the same person, and the person, count apart.
    assert {_open(door, a2, notes.id).status_code for _ in range(AGENT_BYTELESS_MAX)} == {200}
    assert _open(door, alice, notes.id).status_code == 200
    # Bytes that arrive, or a discard, free one of the four.
    assert _put(door, a1, mine[0]).status_code == 200
    assert _open(door, a1, notes.id).status_code == 200
    assert door.delete(f"/v1/uploads/{mine[1]}", headers=a1).status_code == 200
    assert _open(door, a1, notes.id).status_code == 200
    assert _open(door, a1, notes.id).status_code == 429


def test_a_client_container_token_holds_its_own_four(c, door, notes):
    first, second = _client_token(c), _client_token(c)
    for token in (first, second):
        assert {_open(door, token, notes.id).status_code
                for _ in range(AGENT_BYTELESS_MAX)} == {200}
        assert (_open(door, token, notes.id).status_code) == 429


def test_an_agents_byteless_uploads_hold_no_slot_of_its_persons_and_expired_none_of_its_own(
        c, door, notes, sign):
    alice, a1 = sign(), sign("a1")
    for _ in range(AGENT_BYTELESS_MAX):
        _open(door, a1, notes.id)
    c.uploads.clock.now += UPLOAD_TTL_SECONDS
    assert {_open(door, a1, notes.id).status_code for _ in range(AGENT_BYTELESS_MAX)} == {200}
    assert {_open(door, alice, notes.id).status_code for _ in range(MAX_HELD)} == {200}
    r = _open(door, alice, notes.id)
    assert (r.status_code, r.content) == TOO_MANY


def test_its_bytes_are_refused_while_its_person_holds_sixteen_and_stage_once_one_frees(
        c, door, notes, sign):
    alice, a1 = sign(), sign("a1")
    held = [_open(door, alice, notes.id).json()["upload"] for _ in range(MAX_HELD)]
    uid = _open(door, a1, notes.id).json()["upload"]
    with pytest.MonkeyPatch.context() as m:  # counted before the body is read: `put` not reached
        m.setattr(c.uploads, "put", None)
        r = _put(door, a1, uid)
    assert (r.status_code, r.content) == TOO_MANY and r.headers["cache-control"] == "no-store"
    put = [e for e in c.ledger.tail(5) if e["event"] == "upload.put"][-1]
    assert (put["subject"], put["actor"], put["details"]["outcome"], put["details"]["reason"]) == (
        uid, "agent:a1", "refused", "too_many_uploads")
    with pytest.MonkeyPatch.context() as m:  # a slot taken after the first count: the second
        m.setattr(c.uploads, "turned_away", lambda token, upload_id: False)
        r = _put(door, a1, uid)
    assert (r.status_code, r.content) == TOO_MANY
    record = c.backend.get_upload(uid)
    assert record["staged"] is False and c.uploads.byteless(record)  # still one of a1's four
    assert not (c.blobs.root / "staging" / hashlib.sha256(DATA).hexdigest()).exists()
    # A slot the person frees is the agent's to take; then its upload holds it.
    assert door.delete(f"/v1/uploads/{held[0]}", headers=alice).status_code == 200
    assert _put(door, a1, uid).status_code == 200
    assert _open(door, alice, notes.id).status_code == 429
    r = _put(door, a1, uid)  # staged already: `already`, though its person holds 16
    put = [e for e in c.ledger.tail(3) if e["event"] == "upload.put"][-1]
    assert (r.status_code, put["details"]["reason"]) == (400, "already")


def test_an_upload_recorded_before_the_rule_counts_as_it_always_did(c, door, notes, sign):
    alice, a1 = sign(), sign("a1")
    uid = _open(door, a1, notes.id).json()["upload"]
    record = c.backend.get_upload(uid)
    del record["client"]  # as an open before this rule wrote it
    c.backend.put_upload(record)
    # It holds one of alice's sixteen, and is none of a1's four.
    assert {_open(door, alice, notes.id).status_code for _ in range(MAX_HELD - 1)} == {200}
    assert _open(door, alice, notes.id).status_code == 429
    assert {_open(door, a1, notes.id).status_code for _ in range(AGENT_BYTELESS_MAX)} == {200}
    assert _put(door, a1, uid).status_code == 200  # its slot is its own already

