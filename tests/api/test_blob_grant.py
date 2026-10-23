# Copyright 2026 Ali Sasanian
# SPDX-License-Identifier: LicenseRef-PolyForm-Strict-1.0.0
"""rest.md §6: a `BlobGrant` minted on a read, redeemed once at the door, with no header."""

from __future__ import annotations

import threading
from urllib.parse import parse_qs, urlsplit

import pytest
from fastapi.testclient import TestClient

from egzos.api.app import create_app
from egzos.api.throttle import PER_TOKEN, RATE, Throttle
from egzos.container import OWNER, Container

NOT_FOUND = b'{"error":"not_found"}'
KW = {"actor": OWNER, "principal": "interactive"}
BIG = b"\x89PNG" + bytes(range(256)) * 300  # an image, past the inline limit either way


@pytest.fixture
def c(tmp_path):
    box = Container(tmp_path)
    box.owner = box.init()
    return box


@pytest.fixture
def door(c):
    return TestClient(create_app(c))


@pytest.fixture
def art(c, tmp_path):
    path = tmp_path / "plan.png"
    path.write_bytes(BIG)
    p = c.nodes.create("project", "plans", c.nodes.user_root(), token=c.owner, **KW)
    return c.store.add(file=path, scope=p, token=c.owner, **KW)


def _h(token):
    return {"Authorization": f"Bearer {token.secret}"}


def _events(c, name):
    return [e for e in c.ledger.tail(3000) if e["event"] == name]


def _grant(door, c, art, token=None):
    body = door.get(f"/v1/items/{art.id}", headers=_h(token or c.owner)).json()
    return body["grant"], body["grant_url"]


def test_a_read_mints_a_grant_beside_the_item_and_it_redeems_once(c, door, art):
    body = door.get(f"/v1/items/{art.id}", headers=_h(c.owner)).json()
    grant, url = body["grant"], body["grant_url"]
    assert "grant" not in body["item"] and "inline" not in body["item"]["content"]
    assert set(grant) == {"sha256", "item", "token", "expires_at", "sig"}
    assert grant["token"] == c.owner.id and grant["sha256"] == art.content["sha256"]
    minted = _events(c, "blob.grant")[-1]
    assert minted["subject"] == art.id and "sig" not in minted["details"]
    r = door.get(url)  # no Authorization: the descriptor is the credential
    assert r.status_code == 200 and r.content == BIG
    for header, value in [("content-type", "application/octet-stream"),
                          ("content-disposition", "attachment"),
                          ("x-content-type-options", "nosniff"),
                          ("content-security-policy", "sandbox"),
                          ("cache-control", "no-store"), ("referrer-policy", "no-referrer")]:
        assert r.headers[header] == value
    pulled = _events(c, "blob.pull")[-1]
    assert (pulled["subject"], pulled["actor"]) == (art.id, c.owner.owner)
    again = door.get(url)  # single use
    assert (again.status_code, again.content) == (404, NOT_FOUND)
    assert _events(c, "context.fetch")[-1]["details"]["check"] == 4


def test_fetch_grants_its_artifacts_and_the_inbox_does_not(c, door, art):
    items = door.get(f"/v1/fetch?scope={art.scope}", headers=_h(c.owner)).json()["items"]
    (entry,) = [e for e in items if e["item"]["id"] == art.id]
    assert set(entry) >= {"grant", "grant_url"}
    small = c.store.add(body="text stays inline", token=c.owner, **KW)
    inbox = door.get("/v1/inbox", headers=_h(c.owner)).json()["items"]
    assert all("grant" not in e for e in inbox) and small.id in [e["item"]["id"] for e in inbox]


def test_a_forged_or_altered_descriptor_is_refused_and_tallied_not_attributed(c, door, art):
    _grant_body, url = _grant(door, c, art)
    parts = urlsplit(url)
    q = {k: v[0] for k, v in parse_qs(parts.query).items()}
    other = c.nodes.create("project", "x", c.nodes.user_root(), token=c.owner, **KW).id
    before = len(c.ledger.tail(3000))
    forged = [
        f"{parts.path}?item={other}&token={q['token']}&expires_at={q['expires_at']}&sig={q['sig']}",
        f"/v1/blobs/{'0' * 64}?{parts.query}",
        f"{parts.path}?item={q['item']}&token={q['token']}&expires_at=2099-01-01T00:00:00Z"
        f"&sig={q['sig']}",
        f"{parts.path}?item={q['item']}",
        f"{parts.path}?{parts.query}&extra=1",
    ]
    for u in forged:
        r = door.get(u)
        assert (r.status_code, r.content) == (404, NOT_FOUND), u
    assert len(c.ledger.tail(3000)) == before  # nobody to attribute it to
    assert door.get(url).content == BIG  # the real one was never spent
    # Close every window on the same counters, as the door's timer does an hour later.
    Throttle(c.backend, c.ledger, b"k" * 32, clock=lambda: 4_000_000_000.0).close()
    tally = _events(c, "rest.tally")[-1]["details"]
    assert tally["forged"] == len(forged) and tally["unauthorized"] == 0


def test_an_expired_grant_is_refused_under_its_token(c, door, art):
    _g, url = _grant(door, c, art)
    now = c.trust.clock()
    c.trust.clock = lambda: now + 301
    assert door.get(url).content == NOT_FOUND
    refused = _events(c, "context.fetch")[-1]
    assert refused["actor"] == c.owner.owner and refused["details"]["check"] == 3


def test_a_grant_answers_to_its_token_as_it_stands_now(c, door, art):
    reader = c.auth.mint(principal="interactive", owner=OWNER, client="tab", role="reader",
                         scopes=["*"], actor=OWNER, by_principal="interactive")
    _g, url = _grant(door, c, art, reader)
    c.auth.revoke(reader.id, **KW)
    assert door.get(url).content == NOT_FOUND
    assert _events(c, "context.fetch")[-1]["details"]["check"] == 5
    # Quarantined after the mint: the item is no longer served.
    _g, url = _grant(door, c, art)
    c.trust.quarantine(art, token=c.owner, actor=OWNER, reason="bad")
    assert door.get(url).content == NOT_FOUND
    assert _events(c, "context.fetch")[-1]["details"]["check"] == 6


def test_no_grant_for_a_token_that_may_not_read_it(c, door, art):
    elsewhere = c.nodes.create("project", "elsewhere", c.nodes.user_root(), token=c.owner, **KW)
    narrow = c.auth.mint(principal="interactive", owner=OWNER, client="tab", role="reader",
                         scopes=[elsewhere.id], actor=OWNER, by_principal="interactive")
    assert c.trust.authorize_pull(narrow, art) is None
    assert door.get(f"/v1/items/{art.id}", headers=_h(narrow)).content == NOT_FOUND


def test_two_racing_redemptions_pull_once(tmp_path, c, art):
    _g, url = _grant(TestClient(create_app(c)), c, art)
    codes: list[int] = []
    gate = threading.Barrier(2)

    def go():
        door = TestClient(create_app(Container(tmp_path)))
        gate.wait()
        codes.append(door.get(url).status_code)

    threads = [threading.Thread(target=go) for _ in range(2)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert sorted(codes) == [200, 404]
    assert len(_events(c, "blob.pull")) == 1


def test_a_tokens_replays_are_bounded_by_its_own_bucket(c, door, art):
    _g, url = _grant(door, c, art)
    assert door.get(url).status_code == 200
    for _ in range(PER_TOKEN):
        assert door.get(url).content == NOT_FOUND  # each a refused replay, recorded
    recorded = len(_events(c, "context.fetch"))
    assert door.get(url).content == NOT_FOUND  # the bucket holds: counted, not recorded
    assert len(_events(c, "context.fetch")) == recorded
    # Another token's grant is not held by it.
    _g2, url2 = _grant(door, c, art, c.auth.mint(
        principal="interactive", owner=OWNER, client="tab", role="reader", scopes=["*"],
        actor=OWNER, by_principal="interactive"))
    assert door.get(url2).status_code == 200
    assert PER_TOKEN <= RATE.per_source


def test_the_grant_key_is_the_containers_own_and_rotates_by_deletion(c, door, art):
    _g, url = _grant(door, c, art)
    key = c.home / "blob.key"
    assert key.exists() and oct(key.stat().st_mode & 0o777) == "0o600"
    key.unlink()
    assert door.get(url).content == NOT_FOUND  # every outstanding grant is void


def test_a_staged_artifacts_bytes_are_never_served_by_another_promotion(c, door, tmp_path):
    """An agent's artifact still undecided: a person's own upload of the same bytes fills the
    address, and the agent's item still gets no grant and no bytes (a1r on #291)."""
    import hashlib

    p = c.nodes.create("project", "shared", c.nodes.user_root(), token=c.owner, **KW)
    agent = c.auth.mint(principal="client", owner=OWNER, client="bot", role="contributor",
                        scopes=["*"], actor=OWNER, by_principal="interactive")

    def upload(token):
        h = _h(token)
        uid = door.post("/v1/uploads", headers=h, json={
            "scope": p.id, "name": "x.png", "mime": "image/png", "size": len(BIG),
            "sha256": hashlib.sha256(BIG).hexdigest()}).json()["upload"]
        door.put(f"/v1/uploads/{uid}", headers=h, content=BIG)
        return door.post("/v1/items", headers=h,
                         json={"kind": "artifact", "upload": uid}).json()["item"]

    staged = c.store.get(upload(agent)["id"])
    upload(c.owner)  # a person's: promoted at once, to the same address
    assert c.blobs.get(staged.content["sha256"]) == BIG
    assert c.trust.authorize_pull(c.owner, staged) is None
    assert c.store.blob_pull(staged, token=c.owner, actor=OWNER, principal="interactive") is None
