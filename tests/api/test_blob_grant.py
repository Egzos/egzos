# Copyright 2026 Ali Sasanian
# SPDX-License-Identifier: LicenseRef-PolyForm-Strict-1.0.0
"""rest.md §6: a `BlobGrant` minted on a read."""

from __future__ import annotations

import hashlib
import os
import time
from urllib.parse import parse_qsl, urlsplit

import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import ec
from fastapi.testclient import TestClient

from egzos.api.app import create_app
from egzos.container import OWNER, Container
from egzos.identity import Jwks

NOT_FOUND = b'{"error":"not_found"}'
KW = {"actor": OWNER, "principal": "interactive"}
T0 = 1_900_000_000.0  # a time the grant's arithmetic holds exactly
ISSUER = "https://project.supabase.co/auth/v1"


@pytest.fixture
def c(tmp_path):
    box = Container(tmp_path / "home")
    box.owner = box.init()
    box.p = box.nodes.create("project", "p", box.nodes.user_root(), token=box.owner, **KW)
    return box


@pytest.fixture
def door(c):
    return TestClient(create_app(c))


def _auth(token) -> dict[str, str]:
    return {"Authorization": f"Bearer {getattr(token, 'secret', token)}"}


def _client(c, role="reader", scopes=("*",)):
    return c.auth.mint(principal="client", owner="bot", client="probe", role=role,
                       scopes=list(scopes), actor=OWNER, by_principal="interactive")


def _artifact(c, tmp_path, name="a.bin", data=None):
    path = tmp_path / name
    path.write_bytes(os.urandom(256) if data is None else data)
    return c.store.add(file=path, scope=c.p, token=c.owner, **KW)


def _upload(door, token, scope, name, mime, data) -> str:
    """An artifact through §4.4's upload: an agent's stays staged until a person promotes it."""
    h = _auth(token)
    opened = door.post("/v1/uploads", headers=h, json={
        "scope": scope, "name": name, "mime": mime, "size": len(data),
        "sha256": hashlib.sha256(data).hexdigest()}).json()["upload"]
    door.put(f"/v1/uploads/{opened}", headers=h, content=data)
    return door.post("/v1/items", headers=h, json={"kind": "artifact", "upload": opened}).json()[
        "item"]["id"]


def _url(client, token, item) -> str:
    return client.get(f"/v1/items/{item.id}", headers=_auth(token)).json()["grant_url"]


def _events(c, name):
    return [e for e in c.ledger.tail(10_000) if e["event"] == name]


def test_a_fetch_carries_a_grant_and_its_url_which_nothing_redeems_yet(c, door, tmp_path):
    item = _artifact(c, tmp_path)
    body = door.get("/v1/fetch?scope=project:p", headers=_auth(c.owner)).json()
    (entry,) = [e for e in body["items"] if e["item"]["id"] == item.id]
    grant = entry["grant"]
    assert set(entry) == {"item", "layer", "layer_type", "shadowed_by", "grant", "grant_url"}
    assert "inline" not in entry["item"]["content"] and "grant" not in entry["item"]
    assert grant["sha256"] == item.content["sha256"]
    assert (grant["item"], grant["token"]) == (item.id, c.owner.id)
    url = urlsplit(entry["grant_url"])
    assert url.path == f"/v1/blobs/{grant['sha256']}"
    assert parse_qsl(url.query) == [(k, grant[k]) for k in ("item", "token", "expires_at", "sig")]
    minted = _events(c, "blob.grant")[-1]
    assert (minted["subject"], minted["scope"], minted["actor"]) == (item.id, c.p.id, OWNER)
    assert minted["details"] == {k: grant[k] for k in ("token", "sha256", "expires_at")}
    assert door.get(entry["grant_url"], headers=_auth(c.owner)).content == NOT_FOUND


@pytest.mark.parametrize(
    "name, size, granted",
    [("t.txt", 64 * 1024, False), ("t.txt", 64 * 1024 + 1, True), ("b.bin", 10, True)],
    ids=["text-at-threshold", "text-above", "binary-small"],
)
def test_text_at_or_below_the_threshold_rides_inline_and_the_rest_gets_a_grant(
    c, door, tmp_path, name, size, granted
):
    data = b"x" * size
    item = _artifact(c, tmp_path, name, data)
    entry = door.get(f"/v1/items/{item.id}", headers=_auth(c.owner)).json()
    assert entry["item"]["content"].get("inline") == (None if granted else data.decode())
    assert ("grant" in entry) is granted and ("grant_url" in entry) is granted
    assert len(_events(c, "blob.grant")) == int(granted)


def test_find_and_inbox_mint_no_grant(c, door, tmp_path):
    (tmp_path / "loose.bin").write_bytes(os.urandom(64))
    item = c.store.add(file=tmp_path / "loose.bin", token=c.owner, **KW)
    h = _auth(c.owner)
    hits = door.get("/v1/find?q=kind:artifact", headers=h).json()["items"]
    boxed = door.get("/v1/inbox", headers=h).json()["items"]
    assert item.id in {e["item"]["id"] for e in hits} & {e["item"]["id"] for e in boxed}
    assert not any("grant" in e for e in [*hits, *boxed]) and not _events(c, "blob.grant")


@pytest.mark.parametrize(
    "name, mime, data",
    [("x.bin", "application/octet-stream", os.urandom(512)), ("x.txt", "text/plain", b"a note")],
    ids=["binary", "small-text"],
)
def test_an_agents_artifact_gets_a_grant_once_a_person_promotes_it(c, door, name, mime, data):
    bot = _client(c, role="contributor")
    item_id, h = _upload(door, bot, c.p.id, name, mime, data), _auth(bot)
    path = f"/v1/items/{item_id}"
    assert "grant" not in door.get(path, headers=h).json()
    c.trust.promote(c.store.get(item_id), token=c.owner, actor=OWNER)
    served = door.get(path, headers=h).json()
    assert "inline" not in served["item"]["content"]  # promoted after its write: by a grant
    assert served["grant"]["item"] == item_id


def test_a_copy_is_granted_once_it_or_its_source_is_promoted(c, door):
    bot, data = _client(c, role="contributor"), os.urandom(64)
    source = _upload(door, bot, c.p.id, "x.bin", "application/octet-stream", data)
    q = c.nodes.create("project", "q", c.nodes.user_root(), token=c.owner, **KW)
    early = c.trust.copy(c.store.get(source), q, token=c.owner, actor=OWNER)["item"]
    assert "grant" not in door.get(f"/v1/items/{early.id}", headers=_auth(c.owner)).json()
    c.trust.promote(c.store.get(source), token=c.owner, actor=OWNER)
    late = c.trust.copy(c.store.get(source), q, token=c.owner, actor=OWNER)["item"]
    for copy in (early, late):
        assert _url(door, c.owner, copy).startswith("/v1/blobs/")


def test_a_grant_lives_three_hundred_seconds_written_to_the_microsecond(c, door, tmp_path):
    item = _artifact(c, tmp_path)
    c.trust.clock = lambda: T0
    url = _url(door, c.owner, item)
    expires_at = dict(parse_qsl(urlsplit(url).query))["expires_at"]
    assert expires_at == "2030-03-17T17:51:40.000000Z"  # T0 plus 300 seconds, fixed width


def test_the_key_is_made_at_first_need_and_an_unusable_one_mints_nothing(c, door, tmp_path):
    item = _artifact(c, tmp_path)
    assert not (c.home / "grant.key").exists() and _url(door, c.owner, item)  # never at init
    assert (c.home / "grant.key").stat().st_mode & 0o777 == 0o600
    (c.home / "grant.key").write_bytes(b"short")  # nothing is signed under it
    entry = door.get(f"/v1/items/{item.id}", headers=_auth(c.owner))
    assert entry.status_code == 200 and "grant" not in entry.json()


# -- a provider token's grant --------------------------------------------------------------------
def test_a_provider_tokens_grant_names_its_caller(c, door, tmp_path):
    key = ec.generate_private_key(ec.SECP256R1())
    jwk = {**jwt.algorithms.ECAlgorithm.to_jwk(key.public_key(), as_dict=True), "kid": "k1",
           "alg": "ES256"}
    c.set_config("identity.issuer", ISSUER, token=c.owner)
    c.set_config("identity.client_id", "box", token=c.owner)
    jwks = Jwks("x", fetch=lambda url: {"keys": [jwk]})
    c.identity._jwks_for = lambda url: jwks

    def bearer(client_id):
        claims = {"iss": ISSUER, "aud": "authenticated", "exp": time.time() + 600,
                  "iat": time.time(), "sub": "alice", "client_id": client_id}
        return jwt.encode(claims, key, algorithm="ES256", headers={"kid": "k1"})

    c.identity.grant_user("alice", name="alice", role="contributor", scopes=["*"], **KW)
    c.backend.put_agent_registration({
        "client_id": "agent-1", "sub": "alice", "name": "an agent", "capabilities": ["fetch"],
        "scopes": ["*"], "created_at": "2026-01-01T00:00:00Z", "revoked": False})
    item = _artifact(c, tmp_path)
    for client, named in (("box", "user:alice"), ("agent-1", "agent:agent-1:alice")):
        assert dict(parse_qsl(urlsplit(_url(door, bearer(client), item)).query))["token"] == named
    minted = _events(c, "blob.grant")[-1]
    assert (minted["actor"], minted["principal"], minted["details"]["for"]) == (
        "agent:agent-1", "client", "user:alice")
