# Copyright 2026 Ali Sasanian
# SPDX-License-Identifier: LicenseRef-PolyForm-Strict-1.0.0
"""A person tombstones an item at the door (rest.md §4, #296): one nobody promoted at once, with
its staged bytes and its upload's slot; one a person promoted with the confirm; an agent never."""

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
from egzos.store.uploads import MAX_HELD

NOT_FOUND = b'{"error":"not_found"}'
KW = {"actor": OWNER, "principal": "interactive"}
DATA = b"an agent's file\n"
SHA = hashlib.sha256(DATA).hexdigest()
ISSUER = "https://project.supabase.co/auth/v1"


@pytest.fixture
def c(tmp_path):
    box = Container(tmp_path)
    box.owner = box.init()
    return box


@pytest.fixture
def door(c):
    return TestClient(create_app(c))


@pytest.fixture
def notes(c):
    return c.nodes.create("project", "notes", c.nodes.user_root(), token=c.owner, **KW)


@pytest.fixture
def sign(c):
    """Provider sign-ins (identity.md §3): alice, an operator here, and her agent a1, which holds
    `organize` too, so its refusal is its principal's."""
    key = ec.generate_private_key(ec.SECP256R1())
    jwk = {**jwt.algorithms.ECAlgorithm.to_jwk(key.public_key(), as_dict=True), "kid": "k1",
           "alg": "ES256"}
    c.set_config("identity.issuer", ISSUER, token=c.owner)
    c.set_config("identity.client_id", "box", token=c.owner)
    jwks = Jwks("x", fetch=lambda url: {"keys": [jwk]})
    c.identity._jwks_for = lambda url: jwks
    c.identity.grant_user("alice", name="alice", role="operator", scopes=["*"], **KW)
    c.backend.put_agent_registration({
        "client_id": "a1", "sub": "alice", "name": "a1", "scopes": ["*"],
        "capabilities": ["fetch", "remember", "organize"], "created_at": "2026-10-23T00:00:00Z",
        "revoked": False})

    def headers(sub, client_id="box"):
        now = int(time.time())
        claims = {"iss": ISSUER, "aud": "authenticated", "exp": now + 600, "iat": now,
                  "sub": sub, "client_id": client_id}
        value = jwt.encode(claims, key, algorithm="ES256", headers={"kid": "k1"})
        return {"Authorization": f"Bearer {value}"}

    return headers


def _auth(token) -> dict[str, str]:
    return token if isinstance(token, dict) else {"Authorization": f"Bearer {token.secret}"}


def _agent(c, role="operator"):
    """A machine client's container `Token`: a `client` principal, whatever it holds."""
    return c.auth.mint(principal="client", owner=OWNER, client="agent", role=role, scopes=["*"],
                       actor=OWNER, by_principal="interactive")


def _events(c, name):
    return [e for e in c.ledger.tail(2000) if e["event"] == name]


def _open(door, token, scope, data):
    body = {"scope": scope, "name": "f.txt", "mime": "text/plain", "size": len(data),
            "sha256": hashlib.sha256(data).hexdigest()}
    return door.post("/v1/uploads", headers=_auth(token), json=body)


def _artifact(door, token, scope, data=DATA) -> str:
    """An artifact written through an upload: a person's promoted at once, an agent's staged."""
    uid = _open(door, token, scope, data).json()["upload"]
    assert door.put(f"/v1/uploads/{uid}", headers=_auth(token), content=data).status_code == 200
    r = door.post("/v1/items", headers=_auth(token), json={"kind": "artifact", "upload": uid})
    assert r.status_code == 200, r.content
    return r.json()["item"]["id"]


def _staged(c, data=DATA) -> bool:
    return (c.blobs.root / "staging" / hashlib.sha256(data).hexdigest()).exists()


def _rm(door, token, item_id, **body):
    return door.request("DELETE", f"/v1/items/{item_id}", headers=_auth(token), json=body or None)


# -- an unverified item goes at once ---------------------------------------------------------------
def test_a_person_tombstones_an_agents_staged_artifact_and_its_slot_frees(c, door, notes, sign):
    alice, a1 = sign("alice"), sign("alice", "a1")
    items = [_artifact(door, a1, notes.id, data=b"%d" % n) for n in range(MAX_HELD)]
    assert _open(door, a1, notes.id, DATA).status_code == 429  # alice's sixteen, a1's in them
    r = _rm(door, alice, items[0])
    assert (r.status_code, r.json()) == (200, {"result": "tombstoned"})
    assert c.store.get(items[0]) is None and not _staged(c, b"0") and _staged(c, b"1")
    entry = _events(c, "item.tombstone")[-1]
    assert (entry["subject"], entry["actor"], entry["scope"]) == (items[0], "user:alice", notes.id)
    assert entry["details"] == {"kind": "artifact", "status": "unverified",
                                "staged_deleted": hashlib.sha256(b"0").hexdigest()}
    assert not _events(c, "step_up")  # nothing verified, so nothing to confirm
    assert _open(door, a1, notes.id, DATA).status_code == 200  # the 17th open, 429 before


def test_staged_bytes_another_upload_holds_stay(c, door, notes):
    agent = _agent(c)
    first, second = [_artifact(door, agent, notes.id) for _ in range(2)]
    assert _rm(door, c.owner, first).status_code == 200
    assert "staged_deleted" not in _events(c, "item.tombstone")[-1]["details"]
    assert _staged(c)  # the second item still holds them
    assert _rm(door, c.owner, second).status_code == 200
    assert _events(c, "item.tombstone")[-1]["details"]["staged_deleted"] == SHA
    assert not _staged(c)


def test_a_copy_keeps_the_staged_bytes_it_shares_until_its_own_tombstone(c, door, notes):
    agent = _agent(c)

    def copy(item_id):  # a copy names its source's address (trust._do_copy)
        r = door.post(f"/v1/items/{item_id}/copy", headers=_auth(agent), json={"to": notes.id})
        return r.json()["item"]["id"]

    item = _artifact(door, agent, notes.id)
    first, second = copy(item), copy(item)
    for gone in (item, first):
        assert _rm(door, c.owner, gone).status_code == 200
        assert "staged_deleted" not in _events(c, "item.tombstone")[-1]["details"] and _staged(c)
    c.trust.promote(c.store.get(second), token=c.owner, actor=OWNER)
    assert c.blobs.get(SHA) == DATA and _events(c, "blob.put")[-1]["subject"] == SHA
    other = _artifact(door, agent, notes.id, data=b"other")
    last = copy(other)
    assert _rm(door, c.owner, other).status_code == 200 and _staged(c, b"other")
    assert _rm(door, c.owner, last).status_code == 200 and not _staged(c, b"other")
    assert _events(c, "item.tombstone")[-1]["details"]["staged_deleted"] == hashlib.sha256(
        b"other").hexdigest()


def test_promoted_bytes_are_never_deleted(c, door, notes):
    mine = _artifact(door, c.owner, notes.id)  # a person's: promoted at once, still unverified
    theirs = _artifact(door, _agent(c), notes.id)  # the same bytes, staged apart (storage.md §4)
    assert _rm(door, c.owner, theirs).status_code == 200
    assert _events(c, "item.tombstone")[-1]["details"]["staged_deleted"] == SHA
    assert not _staged(c) and c.blobs.get(SHA) == DATA  # only the staged copy went
    assert _rm(door, c.owner, mine).json() == {"result": "tombstoned"}
    assert "staged_deleted" not in _events(c, "item.tombstone")[-1]["details"]
    assert c.blobs.get(SHA) == DATA


def test_an_unverified_rule_goes_at_once_and_a_confirm_with_it_concludes_nothing(c, door, notes):
    rule = c.store.add(body="always this", kind="rule", scope=notes, token=_agent(c),
                       actor="agent", principal="client")
    r = _rm(door, c.owner, rule.id, confirm={"challenge": "x", "proof": "button"})
    assert r.json() == {"result": "tombstoned"} and not _events(c, "step_up")
    assert _events(c, "item.tombstone")[-1]["details"] == {"kind": "rule", "status": "unverified"}


# -- a verified item takes the confirm -------------------------------------------------------------
def test_a_verified_item_asks_first_and_the_second_leg_tombstones(c, door, notes):
    item = _artifact(door, _agent(c), notes.id)
    c.trust.promote(c.store.get(item), token=c.owner, actor=OWNER)
    first = _rm(door, c.owner, item).json()
    assert (first["result"], first["newly"], first["webauthn"]) == ("confirm", [], None)
    title = c.store.get(item).content["auto_title"]
    assert first["tombstones"] == {"item": item, "kind": "artifact", "auto_title": title}
    shown = _events(c, "context.fetch")[-1]
    assert (shown["subject"], shown["details"]["confirm_for"]) == (item, "tombstone")
    assert shown["details"]["tombstones"] == first["tombstones"] and shown["details"]["items"] == []
    assert c.store.get(item) is not None  # the first leg removes nothing
    r = _rm(door, c.owner, item, confirm={"challenge": first["challenge"], "proof": "button"})
    assert r.json() == {"result": "tombstoned"} and c.store.get(item) is None
    assert [e["event"] for e in c.ledger.tail(2)] == ["step_up", "item.tombstone"]
    assert _events(c, "item.tombstone")[-1]["details"] == {"kind": "artifact", "status": "verified"}
    assert c.blobs.get(SHA) == DATA  # its promoted bytes stay ([0.3 · 44])


def test_an_item_a_person_promoted_takes_the_confirm_whatever_its_status_now(c, door, notes):
    other = c.nodes.create("project", "other", c.nodes.user_root(), token=c.owner, **KW)
    note = c.store.add(body="curated", scope=notes, token=c.owner, **KW)
    c.trust.promote(note, token=c.owner, actor=OWNER)
    c.trust.move(c.store.get(note.id), other, token=_agent(c), actor=OWNER)
    assert c.store.get(note.id).status == "unverified"  # an agent's move lands it unverified
    first = _rm(door, c.owner, note.id).json()
    assert first["result"] == "confirm" and c.store.get(note.id) is not None
    r = _rm(door, c.owner, note.id, confirm={"challenge": first["challenge"], "proof": "button"})
    assert r.json() == {"result": "tombstoned"}
    assert _events(c, "item.tombstone")[-1]["details"] == {"kind": "memory", "status": "unverified"}


def test_a_failure_rolls_the_whole_act_back(c, door, notes, monkeypatch):
    item = _artifact(door, _agent(c), notes.id)
    note = c.store.add(body="curated", scope=notes, token=c.owner, **KW)
    c.trust.promote(note, token=c.owner, actor=OWNER)
    first = _rm(door, c.owner, note.id).json()

    def fail(*args):
        raise OSError("failed")

    monkeypatch.setattr(c.blobs, "discard", fail)  # the deletion runs last, after the entry
    r = _rm(door, c.owner, item)
    assert (r.status_code, r.content) == (500, b'{"error":"internal"}')
    assert c.store.get(item) is not None and not _events(c, "item.tombstone")
    monkeypatch.undo()
    monkeypatch.setattr(c.backend, "tombstone", fail)  # before the deletion: the bytes stay
    assert _rm(door, c.owner, item).status_code == 500 and _staged(c)
    r = _rm(door, c.owner, note.id, confirm={"challenge": first["challenge"], "proof": "button"})
    assert r.status_code == 500 and c.store.get(note.id) is not None
    assert not _events(c, "step_up") and not _events(c, "item.tombstone")


def test_a_refused_proof_gets_a_fresh_first_leg(c, door, notes):
    one, two = (c.store.add(body=b, scope=notes, token=c.owner, **KW) for b in ("one", "two"))
    for note in (one, two):
        c.trust.promote(note, token=c.owner, actor=OWNER)
    first = _rm(door, c.owner, one.id).json()
    # A challenge is bound to its item: presented for another, it is refused, and spent.
    again = _rm(door, c.owner, two.id, confirm={"challenge": first["challenge"], "proof": "button"})
    assert again.json()["result"] == "confirm" and again.json()["tombstones"]["item"] == two.id
    assert _events(c, "step_up")[-1]["details"]["reason"] == "mismatch"
    # A biometric proof with no credential registered is refused, and a fresh leg follows.
    leg = _rm(door, c.owner, one.id).json()
    proof = {"challenge": leg["challenge"], "proof": "biometric"}
    fresh = _rm(door, c.owner, one.id, confirm=proof).json()
    assert fresh["result"] == "confirm" and fresh["challenge"] != leg["challenge"]
    refused = _events(c, "step_up")[-1]["details"]
    assert (refused["outcome"], refused["reason"], refused["act"]) == (
        "refused", "assertion", "tombstone")
    assert c.store.get(one.id) and c.store.get(two.id) and not _events(c, "item.tombstone")
    done = _rm(door, c.owner, one.id, confirm={"challenge": fresh["challenge"], "proof": "button"})
    assert done.json() == {"result": "tombstoned"} and c.store.get(two.id) is not None


# -- refusals ------------------------------------------------------------------------------------
def test_an_agent_never_tombstones(c, door, notes, sign):
    item = _artifact(door, sign("alice", "a1"), notes.id)
    absent = _rm(door, c.owner, "01ABSENTABSENTABSENTABSENT")
    for agent in (sign("alice", "a1"), _agent(c, role="admin")):
        r = _rm(door, agent, item, confirm={"challenge": "x", "proof": "button"})
        assert (r.status_code, r.content, dict(r.headers)) == (404, NOT_FOUND, dict(absent.headers))
        probe = _events(c, "context.fetch")[-1]["details"]
        assert (probe["ref"], probe["items"]) == (item, [])
    assert c.uploads.tombstone(_agent(c), item) is None  # the store's own check, under the lock
    assert c.store.get(item) is not None and _staged(c)
    assert not _events(c, "item.tombstone") and not _events(c, "step_up")


def test_absent_uncovered_tombstoned_quarantined_and_without_organize_answer_alike(c, door, notes):
    other = c.nodes.create("project", "other", c.nodes.user_root(), token=c.owner, **KW)
    hidden, curated = (c.store.add(body=b, scope=other, token=c.owner, **KW)
                       for b in ("elsewhere", "curated"))
    c.trust.promote(curated, token=c.owner, actor=OWNER)  # its first leg would name it
    gone, bad, kept = (c.store.add(body=b, scope=notes, token=c.owner, **KW)
                       for b in ("gone", "bad", "kept"))
    assert _rm(door, c.owner, gone.id).status_code == 200
    c.trust.quarantine(bad, token=c.owner, actor=OWNER, reason="poisoned")
    person = {"principal": "interactive", "owner": "user:bo", "client": "tab", "actor": OWNER,
              "by_principal": "interactive"}
    narrow = c.auth.mint(role="operator", scopes=[notes.id], **person)
    writer = c.auth.mint(role="contributor", scopes=["*"], **person)  # no `organize`
    cases = [(c.owner, "01ABSENTABSENTABSENTABSENT"), (narrow, hidden.id), (narrow, curated.id),
             (c.owner, gone.id), (c.owner, bad.id), (writer, kept.id)]
    answers = set()
    for token, ref in cases:
        reads = len(_events(c, "context.fetch"))
        r = _rm(door, token, ref)
        answers.add((r.status_code, r.content, tuple(sorted(r.headers.items()))))
        (probe,) = _events(c, "context.fetch")[reads:]
        assert (probe["details"]["ref"], probe["details"]["items"]) == (ref, [])
    assert len(answers) == 1 and next(iter(answers))[:2] == (404, NOT_FOUND)
    assert [e["subject"] for e in _events(c, "item.tombstone")] == [gone.id]
    assert not [e for e in _events(c, "context.fetch") if "confirm_for" in e["details"]]
    assert not _events(c, "step_up") and c.store.get(curated.id) and c.store.get(hidden.id)
    assert c.store.get(bad.id) and c.store.get(kept.id)
