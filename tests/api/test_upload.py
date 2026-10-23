# Copyright 2026 Ali Sasanian
# SPDX-License-Identifier: LicenseRef-PolyForm-Strict-1.0.0
"""Artifact upload at the REST door (rest.md §4.4): open, bytes, item, the orphan, its discard."""

from __future__ import annotations

import hashlib
import threading
import time

import pytest
from fastapi.testclient import TestClient

from egzos.api.app import create_app
from egzos.container import OWNER, Container
from egzos.store.items import StoreError
from egzos.store.uploads import MAX_HELD, UPLOAD_TTL_SECONDS

NOT_FOUND = b'{"error":"not_found"}'
INVALID = b'{"error":"invalid_request"}'
KW = {"actor": OWNER, "principal": "interactive"}
DATA = b"a note, as a file\n"


class Clock:
    def __init__(self):
        self.now = time.time()

    def __call__(self):
        return self.now


@pytest.fixture
def c(tmp_path):
    box = Container(tmp_path)
    box.owner = box.init()
    box.clock = box.uploads.clock = Clock()
    return box


@pytest.fixture
def door(c):
    return TestClient(create_app(c))


@pytest.fixture
def notes(c):
    return c.nodes.create("project", "notes", c.nodes.user_root(), token=c.owner, **KW)


def _auth(token) -> dict[str, str]:
    return {"Authorization": f"Bearer {token.secret}"}


def _agent(c, role="contributor", scopes=("*",)):
    return c.auth.mint(principal="client", owner=OWNER, client="agent", role=role,
                       scopes=list(scopes), actor=OWNER, by_principal="interactive")


def _events(c, name):
    return [e for e in c.ledger.tail(2000) if e["event"] == name]


def _open(door, token, scope, data=DATA, **over):
    body = {"scope": scope, "name": "note.txt", "mime": "text/plain", "size": len(data),
            "sha256": hashlib.sha256(data).hexdigest(), **over}
    return door.post("/v1/uploads", headers=_auth(token), json=body)


def _upload(door, token, scope, data=DATA):
    r = _open(door, token, scope, data)
    assert r.status_code == 200, r.content
    uid = r.json()["upload"]
    assert door.put(f"/v1/uploads/{uid}", headers=_auth(token), content=data).status_code == 200
    return uid


def _item(door, token, uid, **over):
    return door.post("/v1/items", headers=_auth(token),
                     json={"kind": "artifact", "upload": uid, **over})


def _staged(c, sha):
    return (c.blobs.root / "staging" / sha).exists()


# -- the whole path --------------------------------------------------------------------------------
def test_a_persons_artifact_is_promoted_with_its_item(c, door, notes):
    r = _open(door, c.owner, notes.id)
    assert r.status_code == 200 and set(r.json()) == {"upload", "expires_at"}
    uid = r.json()["upload"]
    assert _events(c, "upload.put") == []  # an open appends nothing
    sha = hashlib.sha256(DATA).hexdigest()
    r = door.put(f"/v1/uploads/{uid}", headers=_auth(c.owner), content=DATA)
    assert r.json() == {"upload": uid, "sha256": sha}
    assert _staged(c, sha) and c.blobs.get(sha) is None  # staged, never `put`
    put = _events(c, "upload.put")[-1]
    assert put["subject"] == uid and put["details"]["outcome"] == "staged"
    r = _item(door, c.owner, uid, key="note", tags=["t"])
    assert r.status_code == 200
    item = r.json()["item"]
    assert item["kind"] == "artifact" and item["trust"]["status"] == "unverified"
    assert item["content"]["sha256"] == sha and item["content"]["filename"] == "note.txt"
    assert item["content"]["inline"] == DATA.decode()
    assert c.blobs.get(sha) == DATA and not _staged(c, sha)
    names = [e["event"] for e in c.ledger.tail(3)]
    assert names[-2:] == ["blob.put", "item.add"]


def test_an_agents_artifact_stays_staged_until_a_person_promotes_it(c, door, notes):
    agent = _agent(c)
    uid = _upload(door, agent, notes.id)
    sha = hashlib.sha256(DATA).hexdigest()
    r = _item(door, agent, uid)
    assert r.status_code == 200
    item = c.store.get(r.json()["item"]["id"])
    assert "inline" not in item.content
    assert c.blobs.get(sha) is None and _staged(c, sha)
    assert not [e for e in _events(c, "blob.put") if e["subject"] == sha]
    c.trust.promote(item, token=c.owner, actor=OWNER)
    assert c.blobs.get(sha) == DATA
    assert _events(c, "blob.put")[-1]["subject"] == sha
    # A promotion that moved nothing says nothing of bytes.
    again = c.store.get(item.id)
    c.trust.promote(again, token=c.owner, actor=OWNER)
    assert len([e for e in _events(c, "blob.put") if e["subject"] == sha]) == 1


# -- 1 · open --------------------------------------------------------------------------------------
@pytest.mark.parametrize("over", [
    {"name": ""}, {"name": "x" * 256}, {"mime": "text"}, {"mime": "text/plain; charset=utf-8"},
    {"mime": "a/" + "b" * 126}, {"size": -1}, {"size": True}, {"size": "3"},
    {"sha256": "ABC"}, {"sha256": "0" * 63}, {"extra": 1},
])
def test_an_open_of_the_wrong_shape_is_400(c, door, notes, over):
    r = _open(door, c.owner, notes.id, **over)
    assert (r.status_code, r.content) == (400, INVALID)


def test_an_open_above_the_limit_is_400_and_an_admin_sets_the_limit(c, door, notes):
    assert _open(door, c.owner, notes.id, b"x" * 20).status_code == 200
    c.set_config("blobs.upload_max_bytes", "10", token=c.owner)
    assert _open(door, c.owner, notes.id, b"x" * 20).status_code == 400
    assert _open(door, c.owner, notes.id, b"x" * 10).status_code == 200
    for bad in ("0", "-1", "lots", True):
        with pytest.raises(ValueError):
            c.set_config("blobs.upload_max_bytes", bad, token=c.owner)


def test_an_open_where_the_caller_may_not_write_is_the_refusal(c, door, notes):
    reader = _agent(c, role="reader")
    narrow = _agent(c, scopes=[notes.id])
    elsewhere = c.nodes.create("project", "elsewhere", c.nodes.user_root(), token=c.owner, **KW)
    before = len(_events(c, "context.fetch"))
    answers = [
        _open(door, reader, notes.id),
        _open(door, narrow, elsewhere.id),
        _open(door, narrow, "01HZZZZZZZZZZZZZZZZZZZZZZZ"),
    ]
    assert {(r.status_code, r.content) for r in answers} == {(404, NOT_FOUND)}
    assert len(_events(c, "context.fetch")) == before + 3


def test_a_principal_holds_at_most_sixteen(c, door, notes):
    ids = [_open(door, c.owner, notes.id).json()["upload"] for _ in range(MAX_HELD)]
    r = _open(door, c.owner, notes.id)
    assert (r.status_code, r.json()) == (429, {"error": "too_many_uploads"})
    assert r.headers["cache-control"] == "no-store"
    # Another principal's count is its own.
    assert _open(door, _agent(c), notes.id).status_code == 200
    # An open upload with nothing staged lapses at the hour; discarding one frees it sooner.
    assert door.delete(f"/v1/uploads/{ids[0]}", headers=_auth(c.owner)).status_code == 200
    assert _open(door, c.owner, notes.id).status_code == 200


def test_an_agents_staged_artifacts_hold_their_slots_until_a_person_decides(c, door, notes):
    agent = _agent(c)
    items = []
    for n in range(MAX_HELD):
        uid = _upload(door, agent, notes.id, data=b"%d" % n)
        items.append(_item(door, agent, uid).json()["item"]["id"])
    c.clock.now += UPLOAD_TTL_SECONDS * 2
    assert _open(door, agent, notes.id).status_code == 429
    c.trust.promote(c.store.get(items[0]), token=c.owner, actor=OWNER)
    assert _open(door, agent, notes.id).status_code == 200


def test_two_concurrent_opens_never_both_take_the_last_slot(tmp_path):
    first = Container(tmp_path)
    owner = first.init()
    node = first.nodes.user_root()
    for _ in range(MAX_HELD - 1):
        first.uploads.open(owner, scope=node, name="n", mime="a/b", size=1, sha256="0" * 64)
    took: list[bool] = []
    gate = threading.Barrier(2)

    def race():
        box = Container(tmp_path)
        gate.wait()
        try:
            box.uploads.open(owner, scope=node, name="n", mime="a/b", size=1, sha256="0" * 64)
            took.append(True)
        except Exception:  # noqa: BLE001 — TooManyUploads, the one that lost
            took.append(False)

    threads = [threading.Thread(target=race) for _ in range(2)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert sorted(took) == [False, True]


# -- 2 · bytes -------------------------------------------------------------------------------------
def test_wrong_bytes_are_refused_and_recorded_then_the_right_ones_stage(c, door, notes):
    uid = _open(door, c.owner, notes.id).json()["upload"]
    url = f"/v1/uploads/{uid}"
    assert door.put(url, headers=_auth(c.owner), content=DATA + b"!").content == INVALID
    assert door.put(url, headers=_auth(c.owner), content=DATA[:-1]).content == INVALID
    wrong = bytes(len(DATA))
    assert door.put(url, headers=_auth(c.owner), content=wrong).content == INVALID
    assert door.put(url, headers=_auth(c.owner), content=DATA).status_code == 200
    assert door.put(url, headers=_auth(c.owner), content=DATA).content == INVALID
    reasons = [e["details"].get("reason") for e in _events(c, "upload.put")]
    assert reasons == ["length", "length", "hash", None, "already"]
    assert not _staged(c, hashlib.sha256(wrong).hexdigest())


def test_bytes_for_an_id_not_the_callers_are_the_refusal_and_never_read(c, door, notes):
    uid = _open(door, c.owner, notes.id).json()["upload"]
    other = _agent(c)
    before = len(_events(c, "context.fetch"))
    answers = [
        door.put(f"/v1/uploads/{uid}", headers=_auth(other), content=DATA),
        door.put("/v1/uploads/nope", headers=_auth(c.owner), content=DATA),
    ]
    c.clock.now += UPLOAD_TTL_SECONDS
    answers.append(door.put(f"/v1/uploads/{uid}", headers=_auth(c.owner), content=DATA))
    assert {(r.status_code, r.content) for r in answers} == {(404, NOT_FOUND)}
    assert len(_events(c, "context.fetch")) == before + 3
    assert _events(c, "upload.put") == []


# -- 3 · item --------------------------------------------------------------------------------------
def test_an_item_needs_the_callers_own_staged_unwritten_upload(c, door, notes):
    agent = _agent(c)
    unsent = _open(door, c.owner, notes.id).json()["upload"]
    uid = _upload(door, c.owner, notes.id)
    elsewhere = c.nodes.create("project", "elsewhere", c.nodes.user_root(), token=c.owner, **KW)
    answers = [
        _item(door, c.owner, unsent),  # nothing staged
        _item(door, agent, uid),  # not its own
        _item(door, c.owner, uid, scope=elsewhere.id),  # not the upload's scope
        _item(door, c.owner, "nope"),
    ]
    assert {(r.status_code, r.content) for r in answers} == {(404, NOT_FOUND)}
    assert _item(door, c.owner, uid, scope=notes.id).status_code == 200
    assert _item(door, c.owner, uid).content == NOT_FOUND  # spent


@pytest.mark.parametrize("body", [
    {"kind": "artifact"}, {"upload": "u"}, {"kind": "memory", "upload": "u"},
    {"kind": "artifact", "upload": "u", "body": "x"}, {},
])
def test_text_or_an_upload_never_both_never_neither(c, door, body):
    r = door.post("/v1/items", headers=_auth(c.owner), json=body)
    assert (r.status_code, r.content) == (400, INVALID)


def test_an_expired_upload_writes_no_item(c, door, notes):
    uid = _upload(door, c.owner, notes.id)
    c.clock.now += UPLOAD_TTL_SECONDS
    assert _item(door, c.owner, uid).content == NOT_FOUND


def test_an_item_the_store_refuses_spends_nothing(c, door, notes, monkeypatch):
    uid = _upload(door, c.owner, notes.id)

    def refuse(**kw):
        raise StoreError("scope not found")

    monkeypatch.setattr(c.store, "add", refuse)
    assert _item(door, c.owner, uid).content == NOT_FOUND
    assert c.backend.get_upload(uid)["item"] is None
    assert c.backend.spend_upload(uid, "item") is True  # rolled back with the refusal


# -- the orphan ------------------------------------------------------------------------------------
def test_an_orphan_is_listed_to_its_opener_and_an_admin_and_discarded(c, door, notes):
    person = c.auth.mint(principal="interactive", owner="user:bo", client="tab",
                         role="contributor", scopes=["*"], actor=OWNER,
                         by_principal="interactive")
    uid = _upload(door, person, notes.id)
    sha = hashlib.sha256(DATA).hexdigest()
    assert door.get("/v1/pending", headers=_auth(person)).json()["uploads"] == []  # still open
    c.clock.now += UPLOAD_TTL_SECONDS
    mine = door.get("/v1/pending", headers=_auth(person)).json()["uploads"]
    assert [u["upload"] for u in mine] == [uid]
    assert set(mine[0]) == {"upload", "name", "size", "sha256", "scope", "opened_at"}
    assert [u["upload"] for u in door.get("/v1/pending", headers=_auth(c.owner)).json()[
        "uploads"]] == [uid]
    # Not another principal's to discard, unless an admin's over everything.
    assert door.delete(f"/v1/uploads/{uid}", headers=_auth(_agent(c, role="admin"))).content == (
        NOT_FOUND)
    assert door.delete(f"/v1/uploads/{uid}", headers=_auth(c.owner)).json() == {
        "result": "discarded"}
    assert not _staged(c, sha)
    entry = _events(c, "upload.discard")[-1]
    assert entry["subject"] == uid and entry["details"]["bytes_deleted"] is True
    assert entry["details"]["opener"] == "user:bo"
    assert door.get("/v1/pending", headers=_auth(person)).json()["uploads"] == []
    assert door.delete(f"/v1/uploads/{uid}", headers=_auth(person)).content == NOT_FOUND


def test_a_discard_keeps_bytes_another_upload_still_holds(c, door, notes):
    agent = _agent(c)
    first = _upload(door, agent, notes.id)
    second = _upload(door, agent, notes.id)
    sha = hashlib.sha256(DATA).hexdigest()
    assert door.delete(f"/v1/uploads/{first}", headers=_auth(agent)).status_code == 200
    assert _events(c, "upload.discard")[-1]["details"]["bytes_deleted"] is False
    assert _staged(c, sha)
    assert _item(door, agent, second).status_code == 200  # its bytes are still there
    assert door.delete(f"/v1/uploads/{second}", headers=_auth(agent)).content == NOT_FOUND


def test_a_staged_artifact_past_the_retention_is_asked_about_apart(c, door, notes):
    agent = _agent(c)
    item = _item(door, agent, _upload(door, agent, notes.id)).json()["item"]["id"]
    text = c.store.add(body="plain", scope=notes, token=agent, actor=OWNER, principal="client")
    body = door.get("/v1/pending", headers=_auth(c.owner)).json()
    assert item in [i["id"] for i in body["items"]] and body["staged"] == []
    c.clock.now += 31 * 86400
    body = door.get("/v1/pending", headers=_auth(c.owner)).json()
    assert [i["id"] for i in body["staged"]] == [item]
    assert item not in [i["id"] for i in body["items"]] and text.id in [i["id"] for i in
                                                                        body["items"]]
    assert _events(c, "context.fetch")[-1]["details"]["staged"] == [item]
