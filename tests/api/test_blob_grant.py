# Copyright 2026 Ali Sasanian
# SPDX-License-Identifier: LicenseRef-PolyForm-Strict-1.0.0
"""rest.md §6: a `BlobGrant` minted on a read, and redeemed at `GET /v1/blobs` by its descriptor."""

from __future__ import annotations

import hashlib
import os
import threading
import time
from urllib.parse import parse_qsl, urlencode, urlsplit

import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import ec
from fastapi.testclient import TestClient

from egzos import identity
from egzos._types import BLOB_GRANT_LIFETIME_SECONDS
from egzos.api.app import Door, create_app
from egzos.api.throttle import PER_TOKEN, RATE, WINDOW_SECONDS, Throttle
from egzos.container import OWNER, Container
from egzos.identity import Jwks
from egzos.trust import _after, grant_expiry

NOT_FOUND = b'{"error":"not_found"}'
#: rest.md §6, line for line: the bytes go out under these and no others.
SIX = {
    "content-type": "application/octet-stream",
    "content-disposition": "attachment",
    "x-content-type-options": "nosniff",
    "content-security-policy": "sandbox",
    "cache-control": "no-store",
    "referrer-policy": "no-referrer",
}
KW = {"actor": OWNER, "principal": "interactive"}
T0 = 1_900_000_000.0  # a time the grant's arithmetic holds exactly
ISSUER = "https://project.supabase.co/auth/v1"


class Clock:
    def __init__(self):
        self.now = 1_800_000_000.0

    def __call__(self):
        return self.now


@pytest.fixture
def c(tmp_path):
    box = Container(tmp_path / "home")
    box.owner = box.init()
    box.p = box.nodes.create("project", "p", box.nodes.user_root(), token=box.owner, **KW)
    return box


@pytest.fixture
def door(c):
    return TestClient(create_app(c))


def _clocked(c):
    clock = Clock()
    throttle = Throttle(c.backend, c.ledger, b"k" * 32, clock=clock)
    return TestClient(create_app(c, door=Door(c, throttle))), throttle, clock


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


def _check(c) -> int:
    return _events(c, "context.fetch")[-1]["details"]["check"]


# -- issue, the URL, redemption, single use ------------------------------------------------------
def test_a_fetch_carries_a_grant_that_redeems_once_by_its_descriptor(c, door, tmp_path):
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
    # No Authorization header is read on this route: a bad one changes nothing.
    r = door.get(entry["grant_url"], headers={"Authorization": "Bearer nonsense"})
    assert r.status_code == 200 and r.content == (tmp_path / "a.bin").read_bytes()
    assert dict(r.headers) == SIX
    pulled = _events(c, "blob.pull")[-1]
    assert (pulled["subject"], pulled["scope"], pulled["actor"], pulled["principal"]) == (
        item.id, c.p.id, OWNER, "interactive")
    assert pulled["details"] == {"sha256": grant["sha256"], "size": 256}
    # Single use; the spent record is the sig's hash, never the sig.
    again = door.get(entry["grant_url"])
    assert (again.status_code, again.content) == (404, NOT_FOUND) and _check(c) == 4
    assert c.backend.db.execute("SELECT sig_hash FROM spent_grants").fetchall() == [
        (hashlib.sha256(grant["sig"].encode()).hexdigest(),)]


def test_an_allowed_origin_gets_the_same_cors_headers_on_success_and_refusal(c, door, tmp_path):
    c.set_config("identity.browser_origins", "https://app.example", token=c.owner)
    url, origin = _url(door, c.owner, _artifact(c, tmp_path)), {"Origin": "https://app.example"}
    ok, spent = door.get(url, headers=origin), door.get(url, headers=origin)
    cors = {k: v for k, v in ok.headers.items() if k.startswith("access-control-") or k == "vary"}
    assert cors and {k: v for k, v in ok.headers.items() if k not in cors} == SIX
    assert spent.status_code == 404 and all(spent.headers[k] == v for k, v in cors.items())


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
    assert door.get(served["grant_url"]).content == data


def test_a_copy_is_granted_once_it_or_its_source_is_promoted(c, door):
    bot, data = _client(c, role="contributor"), os.urandom(64)
    source = _upload(door, bot, c.p.id, "x.bin", "application/octet-stream", data)
    q = c.nodes.create("project", "q", c.nodes.user_root(), token=c.owner, **KW)
    early = c.trust.copy(c.store.get(source), q, token=c.owner, actor=OWNER)["item"]
    assert "grant" not in door.get(f"/v1/items/{early.id}", headers=_auth(c.owner)).json()
    c.trust.promote(c.store.get(source), token=c.owner, actor=OWNER)
    late = c.trust.copy(c.store.get(source), q, token=c.owner, actor=OWNER)["item"]
    for copy in (early, late):
        assert door.get(_url(door, c.owner, copy)).content == data


def test_of_two_concurrent_redemptions_one_passes(c, door, tmp_path):
    url = _url(door, c.owner, _artifact(c, tmp_path))
    # Two doors on one home: two connections, as two processes serving the container hold.
    doors = [TestClient(create_app(Container(c.home))) for _ in range(2)]
    gate, codes = threading.Barrier(2), []

    def pull(client):
        gate.wait()
        codes.append(client.get(url).status_code)

    threads = [threading.Thread(target=pull, args=(d,)) for d in doors]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert sorted(codes) == [200, 404]


def test_a_grant_lives_three_hundred_seconds_and_an_expired_one_is_not_spent(c, door, tmp_path):
    item = _artifact(c, tmp_path)
    c.trust.clock = lambda: T0
    url = _url(door, c.owner, item)
    expires_at = dict(parse_qsl(urlsplit(url).query))["expires_at"]
    assert grant_expiry(expires_at) == T0 + BLOB_GRANT_LIFETIME_SECONDS
    c.trust.clock = lambda: T0 + BLOB_GRANT_LIFETIME_SECONDS
    assert door.get(url).content == NOT_FOUND
    probe = _events(c, "context.fetch")[-1]
    assert (probe["actor"], probe["details"]["check"], probe["details"]["items"]) == (OWNER, 3, [])
    c.trust.clock = lambda: T0 + BLOB_GRANT_LIFETIME_SECONDS - 1  # check 3 precedes the spend
    assert door.get(url).status_code == 200


def test_a_spent_grant_stays_spent_past_its_expiry(c, door, tmp_path):
    item = _artifact(c, tmp_path)
    c.trust.clock = lambda: T0
    url = _url(door, c.owner, item)
    assert door.get(url).status_code == 200
    expiry = T0 + BLOB_GRANT_LIFETIME_SECONDS
    c.trust.clock = lambda: expiry + 1  # a mint after it forgets older records, not this one
    _url(door, c.owner, item)
    readings = iter([expiry - 0.001])  # one reading per redemption, whatever the clock does next
    c.trust.clock = lambda: next(readings, expiry + 0.001)
    assert door.get(url).content == NOT_FOUND and _check(c) == 4


# -- one refusal, whichever check --------------------------------------------------------------
def _tampered(url: str, field: str) -> str:
    path, _, query = url.partition("?")
    fields = dict(parse_qsl(query), sha256=path.rsplit("/", 1)[1])
    value = fields[field]
    fields[field] = ("1" if value[0] != "1" else "2") + value[1:]  # still well-formed
    sha = fields.pop("sha256")
    return f"/v1/blobs/{sha}?{urlencode(fields, safe=':')}"


def test_a_tampered_or_malformed_descriptor_is_one_refusal_with_no_caller(c, tmp_path):
    client, throttle, clock = _clocked(c)
    url = _url(client, c.owner, _artifact(c, tmp_path))
    path, _, query = url.partition("?")
    q = dict(parse_qsl(query))
    bad = [_tampered(url, f) for f in ("sha256", "item", "token", "expires_at", "sig")] + [
        path, f"{url}&extra=1", f"{url}&sig={q['sig']}", f"{path}?{urlencode({**q, 'item': 'x'})}",
        f"{path}?{urlencode({**q, 'expires_at': 'tomorrow'})}",
        f"{path}?{urlencode({**q, 'expires_at': '2026-13-45T99:99:99.000000Z'})}",
    ]
    before = len(c.ledger.tail(10_000))
    answers = [client.get(u) for u in bad]
    assert {(a.status_code, a.content) for a in answers} == {(404, NOT_FOUND)}
    assert all(dict(a.headers) == dict(answers[0].headers) for a in answers)
    assert len(c.ledger.tail(10_000)) == before  # unverified: no caller to name
    assert client.get(url).status_code == 200  # and none of them spent it
    replay = client.get(url)  # a verified refusal answers byte for byte the same
    assert (replay.content, dict(replay.headers)) == (NOT_FOUND, dict(answers[0].headers))
    clock.now += WINDOW_SECONDS
    throttle.close()
    (tally,) = _events(c, "rest.tally")
    assert (tally["details"]["forged"], tally["details"]["unauthorized"]) == (len(bad), 0)


def test_only_a_get_on_one_blob_path_is_read_without_a_bearer(door):
    sha = "0" * 64
    assert door.get(f"/v1/blobs/{sha}/more").status_code == 401
    assert door.post(f"/v1/blobs/{sha}").status_code == 401
    assert door.get("/v1/scopes", headers={"Host": f"a/v1/blobs/{sha}?"}).status_code == 401
    assert door.get(f"/v1/blobs/{sha}").content == NOT_FOUND


@pytest.mark.parametrize("change", ["revoke", "lose-fetch", "lose-coverage"])
def test_a_token_that_may_no_longer_fetch_is_refused_and_the_grant_spent(
    c, door, tmp_path, change
):
    item = _artifact(c, tmp_path)
    bot = _client(c)
    url = _url(door, bot, item)
    kept, now = c.backend.get_token(bot.id), c.backend.get_token(bot.id)
    if change == "revoke":
        c.auth.revoke(bot.id, **KW)
    else:
        elsewhere = c.nodes.create("project", "q", c.nodes.user_root(), token=c.owner, **KW)
        now.capabilities, now.scopes = (
            (["remember"], ["*"]) if change == "lose-fetch" else (["fetch"], [elsewhere.id]))
        c.backend.put_token(now)
    assert door.get(url).content == NOT_FOUND
    probe = _events(c, "context.fetch")[-1]
    assert (probe["actor"], probe["principal"], probe["details"]["check"]) == ("bot", "client", 5)
    c.backend.put_token(kept)  # as it was, and still the grant is spent
    assert door.get(url).content == NOT_FOUND and _check(c) == 4


@pytest.mark.parametrize("change", ["tombstone", "quarantine"])
def test_an_item_no_longer_served_is_refused_and_the_grant_spent(c, door, tmp_path, change):
    item = _artifact(c, tmp_path)
    url = _url(door, c.owner, item)
    if change == "tombstone":
        c.backend.tombstone(item.id)
    else:
        c.trust.quarantine(item, token=c.owner, actor=OWNER, reason="test")
    assert door.get(url).content == NOT_FOUND and _check(c) == 6
    assert door.get(url).content == NOT_FOUND and _check(c) == 4


def test_bytes_the_item_no_longer_names_or_no_longer_held_are_refused(c, door, tmp_path):
    item, other = _artifact(c, tmp_path), _artifact(c, tmp_path, "other.bin")
    url = _url(door, c.owner, item)
    item.content["sha256"] = other.content["sha256"]
    c.backend.put(item)
    assert door.get(url).content == NOT_FOUND and _check(c) == 7
    assert door.get(url).content == NOT_FOUND and _check(c) == 4
    url = _url(door, c.owner, other)
    (c.home / "blobs" / "sha256" / other.content["sha256"]).unlink()
    assert door.get(url).content == NOT_FOUND and _check(c) == 8
    assert door.get(url).content == NOT_FOUND and _check(c) == 4


def test_a_new_key_voids_every_outstanding_grant_and_an_unusable_one_stops_downloads(
    c, tmp_path
):
    client, throttle, clock = _clocked(c)
    item = _artifact(c, tmp_path)
    url = _url(client, c.owner, item)
    (c.home / "grant.key").unlink()  # rest.md §6: the owner's remedy until rotation runs
    before = len(c.ledger.tail(10_000))
    assert client.get(url).content == NOT_FOUND
    assert len(c.ledger.tail(10_000)) == before  # it no longer verifies: forged, untraced
    assert (c.home / "grant.key").stat().st_mode & 0o777 == 0o600
    assert client.get(_url(client, c.owner, item)).status_code == 200  # under the new key
    (c.home / "grant.key").write_bytes(b"short")  # nothing is signed or verified under it
    entry = client.get(f"/v1/items/{item.id}", headers=_auth(c.owner))
    assert entry.status_code == 200 and "grant" not in entry.json()
    assert client.get(url).content == NOT_FOUND
    (c.home / "grant.key").unlink()
    (c.home / "grant.key").mkdir()  # unreadable: Trust is silent and the read goes on (a1r, #304)
    entry = client.get(f"/v1/items/{item.id}", headers=_auth(c.owner))
    assert entry.status_code == 200 and "grant" not in entry.json()
    clock.now += WINDOW_SECONDS
    throttle.close()
    (tally,) = _events(c, "rest.tally")
    assert tally["details"]["forged"] == 2


# -- the throttle ---------------------------------------------------------------------------------
def test_a_tokens_refusals_hold_its_own_bucket_and_no_one_elses(c, tmp_path):
    client, throttle, clock = _clocked(c)
    item, bot, other = _artifact(c, tmp_path), _client(c), _client(c)
    c.trust.clock = lambda: T0
    stale = _url(client, bot, item)  # expired on arrival: refused at check 3
    c.trust.clock = lambda: T0 + BLOB_GRANT_LIFETIME_SECONDS
    for _ in range(PER_TOKEN):
        assert client.get(stale).content == NOT_FOUND
    fresh, theirs = _url(client, bot, item), _url(client, other, item)
    traced = len(_events(c, "context.fetch"))
    assert client.get(fresh).content == NOT_FOUND  # held: refused, not evaluated
    assert len(_events(c, "context.fetch")) == traced  # and not traced
    assert client.get(theirs).status_code == 200
    clock.now += WINDOW_SECONDS
    throttle.close()
    (release,) = _events(c, "authz.release")
    assert release["details"]["refused"] == 1 and bot.id not in str(release)
    assert not _events(c, "rest.tally")
    assert client.get(fresh).status_code == 200  # never spent


def test_while_the_door_holds_a_redemption_is_the_refusal_and_not_spent(c, tmp_path):
    client, _throttle, clock = _clocked(c)
    url = _url(client, c.owner, _artifact(c, tmp_path))
    for _ in range(RATE.per_source):
        client.get("/v1/fetch")
    assert (client.get(url).status_code, client.get(url).content) == (404, NOT_FOUND)
    clock.now += WINDOW_SECONDS
    assert client.get(url).status_code == 200


# -- a provider token's grant --------------------------------------------------------------------
def test_a_provider_tokens_grant_names_its_caller_and_a_revoke_since_refuses_it(
    c, door, tmp_path, monkeypatch
):
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
    assert door.get(_url(door, bearer("agent-1"), item)).status_code == 200
    pulled = _events(c, "blob.pull")[-1]
    assert (pulled["actor"], pulled["principal"], pulled["details"]["for"]) == (
        "agent:agent-1", "client", "user:alice")
    mine, kept = _url(door, bearer("box"), item), _url(door, bearer("box"), item)
    theirs = _url(door, bearer("agent-1"), item)
    c.identity.revoke_user("alice", **KW)
    assert door.get(mine).content == NOT_FOUND
    probe = _events(c, "context.fetch")[-1]
    assert (probe["actor"], probe["principal"], probe["details"]["check"]) == (
        "user:alice", "interactive", 5)
    assert door.get(theirs).content == NOT_FOUND
    probe = _events(c, "context.fetch")[-1]
    assert (probe["actor"], probe["details"]["for"], probe["details"]["check"]) == (
        "agent:agent-1", "user:alice", 5)
    # Granted again, later: a new grant, which no descriptor minted before it names.
    monkeypatch.setattr(identity, "now_iso", lambda: "2099-01-01T00:00:00Z")
    c.identity.grant_user("alice", name="alice", role="contributor", scopes=["*"], **KW)
    assert door.get(kept).content == NOT_FOUND and _check(c) == 5


def test_a_grant_written_at_a_time_nobody_can_read_counts_as_written_since():
    assert _after("not a time", T0) and _after("2099-01-01T00:00:00", T0)  # no zone: UTC
    assert not _after("2026-10-23T00:00:00Z", T0)
