# Copyright 2026 Ali Sasanian
# SPDX-License-Identifier: LicenseRef-PolyForm-Strict-1.0.0
"""Whose an upload is (rest.md §4.4, v0.7 §AC): a person's sixteen take in every agent serving
them, counted and written as one step whichever of their principals open at once, and a container
`Token` is a person of its own."""

from __future__ import annotations

import threading
import time

import pytest

from egzos.container import OWNER, Container
from egzos.identity import principal_id
from egzos.store.uploads import MAX_HELD, TooManyUploads, person_of

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
