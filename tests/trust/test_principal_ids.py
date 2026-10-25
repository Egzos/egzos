# Copyright 2026 Ali Sasanian
# SPDX-License-Identifier: LicenseRef-PolyForm-Strict-1.0.0
"""GHSA-9g46-638p-v4xm: a provider principal's `Token.id` names exactly one `(client_id, sub)`
pair, the one `rest.md` §6 check 5 re-derives and §4.2 item 3 binds a challenge to. An id holding
no `%` and no `:`, a UUID among them, is as it was, and an id written before names its own pair or
none."""

from __future__ import annotations

import uuid

import pytest

from egzos.container import OWNER, Container
from egzos.identity import principal_id, principal_parts

KW = {"actor": OWNER, "principal": "interactive"}
#: `(client_id, sub)`, `client_id` None for a person.
PAIRS = [(None, "alice"), ("helper", "alice"), ("A", "z:1"), ("A:z", "1"), ("A%3Az", "1"),
         ("A", "z%3A1"), (None, "z:1"), (None, "z%3A1"), ("https://c.example/m.json", "s1"),
         ("auth0|abc", "alice@example.com"), ("é", "ü:%"), ("%", ":")]


@pytest.mark.parametrize("pair", PAIRS)
def test_an_id_reads_back_as_the_pair_it_was_written_from(pair):
    token_id = principal_id(*pair)
    assert principal_parts(token_id) == pair
    assert token_id.count(":") == (1 if pair[0] is None else 2)  # no part holds a raw colon


def test_pairs_that_differ_get_ids_that_differ():
    assert len({principal_id(*pair) for pair in PAIRS}) == len(PAIRS)


def test_an_id_holding_no_percent_and_no_colon_is_as_it_was():
    client_id, sub = str(uuid.uuid4()), str(uuid.uuid4())
    assert principal_id(None, sub) == f"user:{sub}"
    assert principal_id(client_id, sub) == f"agent:{client_id}:{sub}"
    assert principal_id("auth0|abc", "alice@example.com") == "agent:auth0|abc:alice@example.com"


@pytest.mark.parametrize("pair", PAIRS)
def test_an_id_written_before_names_its_own_pair_or_none(pair):
    client_id, sub = pair
    before = f"user:{sub}" if client_id is None else f"agent:{client_id}:{sub}"
    assert principal_parts(before) in (pair, None)
    # A changed id takes a kind no id written before held.
    token_id = principal_id(*pair)
    assert token_id == before or not token_id.startswith(("user:", "agent:"))


@pytest.mark.parametrize("token_id", [
    "", "user", "user:", "agent:a", "agent::s", "agent:a:", "agent:a:b:c", "user:a:b",
    "user:%3a", "user:%61", "user:%", "user:%zz", "user:%FF", "agent:a%:b", "nobody:a",
    "user:a%3Ab", "agent:a:b%25", "user%:a", "agent%:a:b", "user%:a%3ab", "user%:a:b",
    "01J9Z3K4M5N6P7Q8R9S0T1V2W3",  # a container `Token`'s ULID
])
def test_a_string_principal_id_would_not_write_names_no_pair(token_id):
    assert principal_parts(token_id) is None


# -- the ids the grants answer with (§4) -----------------------------------------------------------
@pytest.fixture
def box(tmp_path):
    """Two people granted here, and an agent registered to serve each."""
    c = Container(tmp_path)
    c.owner = c.init()
    c.set_config("identity.client_id", "box", token=c.owner)
    for sub in ("z:1", "1"):
        c.identity.grant_user(sub, name=f"person {sub}", role="reader", scopes=["*"], **KW)
    for client_id, sub in (("A", "z:1"), ("A:z", "1")):
        c.backend.put_agent_registration({
            "client_id": client_id, "sub": sub, "name": f"agent {client_id}",
            "capabilities": ["fetch"], "scopes": ["*"], "created_at": "2026-10-23T00:00:00Z",
            "revoked": False})
    return c


def test_each_grant_and_registration_is_its_own_member_of_the_audience(box):
    tokens = box.identity.audience_tokens()
    assert sorted(t.id for t in tokens) == sorted(
        principal_id(*pair) for pair in ((None, "z:1"), (None, "1"), ("A", "z:1"), ("A:z", "1")))
    members = {a["token"] for a in box.trust.audience(box.nodes.user_root())}
    assert {t.id for t in tokens} <= members
    # The owner and `acting_for` keep their parts raw (identity.md §3a): attribution, not ids.
    agents = {t.client_id: t for t in tokens if t.principal == "client"}
    assert (agents["A:z"].owner, agents["A:z"].acting_for) == ("agent:A:z", "user:1")
    assert {t.owner for t in tokens if t.principal == "interactive"} == {"user:z:1", "user:1"}


def test_an_id_is_named_back_as_the_one_it_was_written_for(box):
    for token in box.identity.audience_tokens():
        named = box.identity.named(token.id)
        assert (named.id, named.client_id, named.sub, named.owner, named.revoked) == (
            token.id, token.client_id, token.sub, token.owner, False)
    assert box.identity.named(principal_id("A", "1")) is None  # no registration names that pair
    assert box.identity.named("agent:A:z:1") is None  # nor an id `principal_id` never writes
    box.identity.revoke_user("1", **KW)  # and with it, `A:z` serving `1`
    agent, person = box.identity.named(principal_id("A:z", "1")), box.identity.named("user:1")
    assert (agent.revoked, agent.owner, agent.acting_for, agent.capabilities) == (
        True, "agent:A:z", "user:1", [])
    assert (person.revoked, person.owner, person.scopes) == (True, "user:1", [])
    assert not box.identity.named(principal_id("A", "z:1")).revoked  # the other stands


def test_whom_a_grant_opens_to_is_named_by_id(box):
    box.backend.put_agent_registration({
        "client_id": "A:z", "sub": "q:1", "name": "agent A:z", "capabilities": ["fetch"],
        "scopes": ["*"], "created_at": "2026-10-23T00:00:00Z", "revoked": False})
    expected = [(principal_id(None, "q:1"), "Q"), (principal_id("A:z", "q:1"), "agent A:z")]
    assert box.identity.opens("q:1", "Q", ["fetch"], ["*"]) == sorted(expected)
