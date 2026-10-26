# Copyright 2026 Ali Sasanian
# SPDX-License-Identifier: LicenseRef-PolyForm-Strict-1.0.0
"""Whose an upload is (rest.md §4.4, v0.7 §AC): a person's sixteen take in every agent serving
them, counted and written as one step whichever of their principals open at once, and a container
`Token` is a person of its own. And when staged bytes go (storage.md §3.6, §4): after the act's
COMMIT, unless something holds them by then, or at the next open, on each of the harness's blob
stores."""

from __future__ import annotations

import hashlib
import threading
import time

import pytest

from egzos.container import OWNER, Container
from egzos.identity import principal_id
from egzos.store.items import StoreError
from egzos.store.uploads import MAX_HELD, TooManyUploads, person_of
from egzos.trust import TrustError

KW = {"actor": OWNER, "principal": "interactive"}
SHAPE = {"name": "n", "mime": "a/b", "size": 1, "sha256": "0" * 64}


def _people(c) -> dict:
    """Alice's sign-in and two agents serving her, as `Identity` builds them (identity.md §4)."""
    c.set_config("identity.client_id", "box", token=c.owner)
    c.identity.grant_user("alice", name="Alice", role="contributor", scopes=["*"], **KW)
    for client_id in ("a1", "a2"):
        c.backend.put_agent_registration({
            "client_id": client_id, "sub": "alice", "name": client_id,
            "capabilities": ["fetch", "remember"], "scopes": ["*"],
            "created_at": "2026-10-23T00:00:00Z", "revoked": False})
    return {t.client_id if t.principal == "client" else t.sub: t
            for t in c.identity.audience_tokens()}


@pytest.fixture
def c(tmp_path):
    box = Container(tmp_path)
    box.owner = box.init()
    return box


def test_an_upload_is_its_persons_whichever_principal_opens_it(c):
    people = _people(c)
    tab = c.auth.mint(principal="interactive", owner="user:alice", client="tab",
                      role="contributor", scopes=["*"], actor=OWNER, by_principal="interactive")
    node = c.nodes.user_root()
    for token in (*people.values(), c.owner, tab):
        record = c.uploads.open(token, scope=node, **SHAPE)
        # The person an agent serves, by that person's id; anyone else is its own person.
        expected = principal_id(None, token.sub) if token.principal == "client" else token.id
        assert person_of(record["principal"], record["actor"]) == expected
        assert person_of(token.id, token.owner) == expected
    # A provider principal's id names one (client_id, sub) pair, beside its own owner only.
    url = "https://c.example/m.json"
    assert person_of(principal_id(url, "s1"), f"agent:{url}") == "user:s1"
    assert person_of(principal_id("a1", "x:y"), "agent:a1") == principal_id(None, "x:y")
    assert person_of(principal_id(None, "x:y"), "user:x:y") == principal_id(None, "x:y")
    for principal, actor in [(principal_id("a1", "x"), "agent:a2"), ("agent:a1:x:y", "agent:a1"),
                             ("agent:a1:x%3Ay", "agent:a1"), ("user:x:y", "user:x"),
                             (principal_id(None, "x:y"), "user:x%3Ay")]:
        assert person_of(principal, actor) is None  # nobody's: an admin's alone to discard


@pytest.mark.parametrize("pair", [("alice", "a1"), ("a1", "a2")])
def test_two_principals_of_one_person_never_both_take_the_last_slot(tmp_path, pair):
    first = Container(tmp_path)
    first.owner = first.init()
    people = _people(first)
    node = first.nodes.user_root()
    for _ in range(MAX_HELD - 1):
        first.uploads.open(people["alice"], scope=node, **SHAPE)
    took: list[bool] = []
    gate = threading.Barrier(2)

    def race(token):
        box = Container(tmp_path)
        count = box.uploads.holds

        def slow(record):  # widens the window between the count and the write
            time.sleep(0.005)
            return count(record)

        box.uploads.holds = slow
        gate.wait()
        try:
            box.uploads.open(token, scope=node, **SHAPE)
            took.append(True)
        except TooManyUploads:
            took.append(False)

    threads = [threading.Thread(target=race, args=(people[name],)) for name in pair]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert sorted(took) == [False, True]


# -- staged deletes after the COMMIT, and the open-time sweep (storage.md §3.6, §4; #342) --------
DATA = b"agent bytes"
SHA = hashlib.sha256(DATA).hexdigest()


class Boom(Exception):
    """An act failing after its writes."""


@pytest.fixture
def box(tmp_path, monkeypatch, blobs):
    """A container on the harness's blob store, over sqlite, and an agent serving its person."""
    monkeypatch.setattr("egzos.binding.BlobStore", lambda root: blobs)
    c = Container(tmp_path)
    c.owner = c.init()
    c.agent = _people(c)["a1"]
    return c


def _staged(c, data=DATA, token=None):
    record = c.uploads.open(token or c.agent, scope=c.nodes.user_root(), name="n", mime="a/b",
                            size=len(data), sha256=hashlib.sha256(data).hexdigest())
    assert c.uploads.put(token or c.agent, record["id"], data) == "staged"
    return record


def _item(c):
    return c.uploads.item(c.agent, _staged(c)["id"], scope=None, key=None, tags=[])


def _since(c, head):
    return [e["event"] for e in c.backend.audit_iter() if e["seq"] > head["seq"]]


def test_a_commit_that_fails_after_a_promote_leaves_the_staged_copy_for_a_retry(
        box, blobs, staged, fail_commit):
    """The retried promote copies again and returns True, and its act appends `blob.put`: no
    verified item's bytes reach the promoted store without one on the chain."""
    item = _item(box)
    head = box.backend.audit_last()
    fail_commit(box.backend)
    with pytest.raises(ConnectionError, match="COMMIT"):
        box.trust.promote(item, token=box.owner, actor=OWNER)
    assert staged(blobs, SHA) == DATA and box.backend.audit_last() == head
    assert box.backend.get(item.id).status == "unverified"
    assert box.trust.promote(item, token=box.owner, actor=OWNER).status == "verified"
    assert _since(box, head) == ["approval.promote", "blob.put"]
    assert staged(blobs, SHA) is None and blobs.get(SHA) == DATA  # deleted after the COMMIT


def test_a_discard_whose_block_rolls_back_discarded_nothing(box, blobs, staged):
    record = _staged(box)
    with pytest.raises(Boom), box.backend.atomic():
        assert box.uploads.discard(box.owner, record["id"], admin=True) is True
        raise Boom
    assert staged(blobs, SHA) == DATA and not box.backend.get_upload(record["id"])["discarded"]
    assert box.uploads.discard(box.owner, record["id"], admin=True) is True
    assert staged(blobs, SHA) is None


def test_a_stage_committed_between_a_commit_and_its_delete_keeps_the_bytes(box, blobs, staged):
    first = _staged(box)
    second = box.uploads.open(box.agent, scope=box.nodes.user_root(), name="n", mime="a/b",
                              size=len(DATA), sha256=SHA)
    with box.backend.atomic():
        # Queued ahead of the discard's delete: it commits after the COMMIT, before the delete.
        box.backend.after_commit(lambda: box.uploads.put(box.agent, second["id"], DATA))
        assert box.uploads.discard(box.owner, first["id"], admin=True) is True
    assert box.backend.get_upload(second["id"])["staged"] and staged(blobs, SHA) == DATA
    assert box.uploads.discard(box.owner, second["id"], admin=True) is True
    assert staged(blobs, SHA) is None  # nothing holds them now


def test_an_approval_whose_bytes_are_gone_is_refused_and_changes_nothing(box, blobs):
    item = _item(box)
    blobs._unstage(SHA)  # lost from staging, and never promoted
    head = box.backend.audit_last()
    with pytest.raises(TrustError, match="nothing staged"):
        box.trust.promote(item, token=box.owner, actor=OWNER)
    assert box.backend.audit_last() == head and box.backend.get(item.id).status == "unverified"
    blobs.put(DATA)  # held at the promoted address now, as a file's bytes are
    assert box.trust.promote(item, token=box.owner, actor=OWNER).status == "verified"
    assert _since(box, head) == ["approval.promote"]  # it moved nothing, and says so


def test_a_persons_item_whose_bytes_are_gone_is_refused_and_spends_nothing(box, blobs):
    record = _staged(box, token=box.owner)
    blobs._unstage(SHA)
    head = box.backend.audit_last()
    with pytest.raises(StoreError, match="nothing staged"):
        box.uploads.item(box.owner, record["id"], scope=None, key=None, tags=[])
    assert box.backend.audit_last() == head and box.backend.get_upload(record["id"])["item"] is None


def test_the_open_time_sweep_deletes_only_staged_bytes_nothing_holds(box, blobs, staged, tmp_path):
    """A crash's leftover, or bytes an act staged before its block rolled back, go at the next open,
    under the lock, and nothing is appended. An open upload's, an orphan's and a staged item's
    stay."""
    left = blobs.stage(b"left between a COMMIT and its delete")
    with pytest.raises(Boom), box.backend.atomic():
        rolled = blobs.stage(b"staged by an act that rolled back")
        raise Boom
    item = _item(box)
    _staged(box, b"an open upload's")
    box.uploads.clock = lambda: time.time() - 2 * 3600  # opened two hours ago: an orphan now
    _staged(box, b"an orphan's")
    head = box.backend.audit_last()
    again = Container(tmp_path)
    assert staged(blobs, left) is None and staged(blobs, rolled) is None
    for data in (DATA, b"an open upload's", b"an orphan's"):
        assert staged(blobs, hashlib.sha256(data).hexdigest()) == data
    assert again.backend.audit_last() == head and again.backend.get(item.id) is not None
