# Copyright 2026 Ali Sasanian
# SPDX-License-Identifier: LicenseRef-PolyForm-Strict-1.0.0
"""GHSA-9g46-638p-v4xm: a provider principal's `Token.id` names exactly one `(client_id, sub)`
pair, so two registrations whose pairs differ never act for each other: neither sends bytes into
or discards the other's upload, confirms with the other's challenge, redeems a `BlobGrant` on the
other's standing, or counts as the other in an audience. An id written before names its own pair
or none."""

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
from egzos.store.uploads import UPLOAD_TTL_SECONDS

pytestmark = pytest.mark.adversarial

ISSUER = "https://project.supabase.co/auth/v1"
NOT_FOUND = b'{"error":"not_found"}'
KW = {"actor": OWNER, "principal": "interactive"}
DATA = b"the first registration's bytes"
#: Two registrations, each `(client_id, sub)`.
PAIRS = [(("A", "z:1"), ("A:z", "1")), (("A", "z%3A1"), ("A", "z:1"))]


def _door(tmp_path, pairs):
    """A container linked to a provider: each pair's person granted here, and its agent."""
    c = Container(tmp_path)
    owner = c.init()
    key = ec.generate_private_key(ec.SECP256R1())
    jwk = {**jwt.algorithms.ECAlgorithm.to_jwk(key.public_key(), as_dict=True), "kid": "k",
           "alg": "ES256"}
    c.set_config("identity.issuer", ISSUER, token=owner)
    c.set_config("identity.client_id", "box", token=owner)
    keys = Jwks("x", fetch=lambda url: {"keys": [jwk]})
    c.identity._jwks_for = lambda url: keys
    for client_id, sub in pairs:
        c.identity.grant_user(sub, name="a person", role="contributor", scopes=["*"], **KW)
        c.backend.put_agent_registration({
            "client_id": client_id, "sub": sub, "name": "an agent",
            "capabilities": ["fetch", "remember"], "scopes": ["*"],
            "created_at": "2026-10-23T00:00:00Z", "revoked": False})

    def bearer(client_id, sub):
        now = int(time.time())
        claims = {"iss": ISSUER, "aud": "authenticated", "exp": now + 600, "iat": now,
                  "sub": sub, "client_id": client_id}
        return jwt.encode(claims, key, algorithm="ES256", headers={"kid": "k"})

    project = c.nodes.create("project", "p", c.nodes.user_root(), token=owner, **KW)
    return c, owner, project, TestClient(create_app(c)), bearer


def _auth(value):
    return {"Authorization": f"Bearer {value}"}


def _last(c, event):
    return [e for e in c.ledger.tail(500) if e["event"] == event][-1]


def _open(door, headers, scope):
    return door.post("/v1/uploads", headers=headers, json={
        "scope": scope.id, "name": "a.bin", "mime": "application/octet-stream",
        "size": len(DATA), "sha256": hashlib.sha256(DATA).hexdigest()}).json()["upload"]


@pytest.mark.parametrize(("one", "other"), PAIRS)
def test_ghsa_9g46_638p_v4xm_neither_writes_into_nor_discards_the_others_upload(
    tmp_path, one, other
):
    c, _, project, door, bearer = _door(tmp_path, (one, other))
    mine, theirs = _auth(bearer(*one)), _auth(bearer(*other))
    opened = _open(door, mine, project)
    assert door.put(f"/v1/uploads/{opened}", headers=theirs, content=DATA).content == NOT_FOUND
    assert door.delete(f"/v1/uploads/{opened}", headers=theirs).content == NOT_FOUND
    assert not c.backend.get_upload(opened)["staged"]
    assert door.put(f"/v1/uploads/{opened}", headers=mine, content=DATA).status_code == 200
    c.uploads.clock = lambda: time.time() + UPLOAD_TTL_SECONDS  # an orphan now
    for h in (theirs, _auth(bearer("box", other[1]))):  # the other, and the person it serves
        assert door.delete(f"/v1/uploads/{opened}", headers=h).content == NOT_FOUND
    assert not c.backend.get_upload(opened)["discarded"]
    assert door.delete(f"/v1/uploads/{opened}", headers=_auth(bearer("box", one[1]))).json() == {
        "result": "discarded"}
    # Each refusal is its caller's own read; the upload's own entries are its opener's alone.
    entries = c.ledger.tail(500)
    probes = [(e["actor"], e["details"].get("for")) for e in entries
              if e["event"] == "context.fetch" and e["details"].get("ref") == opened]
    assert probes == [(f"agent:{other[0]}", f"user:{other[1]}")] * 3 + [(f"user:{other[1]}", None)]
    assert [(e["event"], e["actor"]) for e in entries if e["subject"] == opened] == [
        ("upload.put", f"agent:{one[0]}"), ("upload.discard", f"user:{one[1]}")]


@pytest.mark.parametrize(("one", "other"), PAIRS)
def test_ghsa_9g46_638p_v4xm_neither_confirms_with_the_others_challenge(tmp_path, one, other):
    c, _, _, _, bearer = _door(tmp_path, (one, other))
    # The confirm the door runs, with the principals the door verifies.
    mine, theirs = c.identity.verify(bearer(*one)), c.identity.verify(bearer(*other))
    act = {"act": "move", "subject": "an item", "destination": "a scope", "delta": []}
    issued = c.confirm.issue(mine, newly=[], **act)["challenge"]
    assert c.confirm.conclude(theirs, {"challenge": issued, "proof": "button"}, **act) == "foreign"
    refused = _last(c, "step_up")
    assert (refused["actor"], refused["details"]["outcome"], refused["details"]["reason"]) == (
        f"agent:{other[0]}", "refused", "foreign")
    # A refused second leg spends the challenge too (rest.md §4.2 item 5): `one` takes a new one.
    again = c.confirm.issue(mine, newly=[], **act)["challenge"]
    assert c.confirm.conclude(mine, {"challenge": again, "proof": "button"}, **act) is None


@pytest.mark.parametrize(("one", "other"), PAIRS)
def test_ghsa_9g46_638p_v4xm_neither_redeems_a_grant_on_the_others_standing(tmp_path, one, other):
    c, owner, project, door, bearer = _door(tmp_path, (one, other))
    path = tmp_path / "a.bin"
    path.write_bytes(DATA)
    item = c.store.add(file=path, scope=project, token=owner, **KW)
    urls = {pair: door.get(f"/v1/items/{item.id}", headers=_auth(bearer(*pair))).json()[
        "grant_url"] for pair in (one, other)}
    c.backend.put_agent_registration({**c.backend.get_agent_registration(*other), "revoked": True})
    assert door.get(urls[other]).content == NOT_FOUND
    refused = _last(c, "context.fetch")
    assert (refused["actor"], refused["details"]["for"], refused["details"]["check"]) == (
        f"agent:{other[0]}", f"user:{other[1]}", 5)
    assert door.get(urls[one]).content == DATA
    pulled = _last(c, "blob.pull")
    assert (pulled["actor"], pulled["details"]["for"]) == (f"agent:{one[0]}", f"user:{one[1]}")


@pytest.mark.parametrize(("one", "other"), PAIRS)
def test_ghsa_9g46_638p_v4xm_each_is_its_own_member_of_an_audience(tmp_path, one, other):
    c, owner, here, door, _ = _door(tmp_path, (one, other))
    there = c.nodes.create("project", "q", c.nodes.user_root(), token=owner, **KW)
    for pair, scope, name in ((one, here, "one"), (other, there, "other")):  # each its own scope
        c.backend.put_agent_registration(
            {**c.backend.get_agent_registration(*pair), "scopes": [scope.id], "name": name})
    item = c.store.add(body="a note", scope=here, token=owner, **KW)
    first = door.post(f"/v1/items/{item.id}/move", headers=_auth(owner.secret),
                      json={"to": there.id}).json()
    assert (first["result"], first["newly"]) == ("confirm", ["other"])
    assert c.store.get(item.id).scope == here.id  # nothing moves without the second leg


@pytest.mark.parametrize(("one", "other"), PAIRS)
def test_ghsa_9g46_638p_v4xm_an_id_written_before_names_no_other_pair(tmp_path, one, other):
    c, owner, project, door, bearer = _door(tmp_path, (one, other))
    agents = [_auth(bearer(*pair)) for pair in (one, other)]
    opened = _open(door, agents[0], project)
    # Stored as an upload opened before was: its opener's id in the form written then.
    c.backend.put_upload({**c.backend.get_upload(opened), "principal": f"agent:{one[0]}:{one[1]}"})
    for h in agents:
        assert door.put(f"/v1/uploads/{opened}", headers=h, content=DATA).content == NOT_FOUND
    c.backend.put_upload({**c.backend.get_upload(opened), "staged": True})
    c.blobs.stage(DATA)
    c.uploads.clock = lambda: time.time() + UPLOAD_TTL_SECONDS  # an orphan now
    people = [_auth(bearer("box", pair[1])) for pair in (one, other)]
    for h in agents + people:
        assert door.delete(f"/v1/uploads/{opened}", headers=h).content == NOT_FOUND
    assert [door.get("/v1/pending", headers=h).json()["uploads"] for h in people] == [[], []]
    assert door.delete(f"/v1/uploads/{opened}", headers=_auth(owner.secret)).json() == {
        "result": "discarded"}  # an admin's alone
