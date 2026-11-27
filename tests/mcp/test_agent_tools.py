# Copyright 2026 Ali Sasanian
# SPDX-License-Identifier: LicenseRef-PolyForm-Strict-1.0.0
"""The MCP tools say and do what the contract says (rest.md §3, §4.1 items 1, 5 and 6): a call
carrying an argument a tool does not define is refused as a malformed one is, before any lookup;
`egzos_remember` takes the kinds `POST /v1/items` takes from a body; and each description states
how a place is named, where a call starts, and what comes back."""

from __future__ import annotations

import asyncio
import json

import pytest
from fastapi.testclient import TestClient
from mcp import Client

from egzos._types import SERVING_POLICY
from egzos.api.app import BODY_MAX_BYTES, create_app
from egzos.container import OWNER, Container
from egzos.mcp.server import REQUEST_MAX_BYTES, TITLES_BANNER, build
from egzos.model import KINDS
from egzos.store.items import BODY_KINDS

KW = {"actor": OWNER, "principal": "interactive"}


@pytest.fixture
def c(tmp_path):
    box = Container(tmp_path)
    box.owner = box.init()
    box.music = box.nodes.create("project", "Music", box.nodes.user_root(), token=box.owner, **KW)
    box.drafts = box.nodes.create("thread", "drafts", box.music, token=box.owner, **KW)
    return box


def _agent(c, scopes=("*",), role="contributor"):
    return c.auth.mint(principal="client", owner=OWNER, client="agent", role=role,
                       scopes=[s if s == "*" else s.id for s in scopes], actor=OWNER,
                       by_principal="interactive")


def _call(c, token, name, arguments):
    async def go():
        async with Client(build(c, lambda: token)) as client:
            return await client.call_tool(name, arguments)

    return asyncio.run(go())


def _tools(c):
    async def go():
        async with Client(build(c, lambda: c.owner)) as client:
            listed = await client.list_tools()
            return {t.name: t.description for t in listed.tools}, client.instructions

    return asyncio.run(go())


def _state(c):
    return c.ledger.tail(1)[-1]["seq"], len(c.backend.list_nodes()), c.store.inbox_items()


# -- a: an argument a tool does not define is refused, never dropped ----------------------------
@pytest.mark.parametrize(("name", "arguments"), [
    ("egzos_remember", {"text": "a note", "project": "Music", "thread": "drafts"}),
    ("egzos_remember", {"text": "a note", "scope": "Music/drafts", "title": "x"}),
    ("egzos_fetch", {"scope": "Music/drafts", "limit": 5}),
    ("egzos_fetch", {"place": "Music"}),
    ("egzos_inbox", {"all": True}),
], ids=["remember-project-thread", "remember-extra", "fetch-limit", "fetch-place", "inbox"])
def test_an_unknown_argument_is_invalid_request_before_any_lookup(c, name, arguments):
    agent = _agent(c)
    before = _state(c)
    r = _call(c, agent, name, arguments)
    assert r.is_error and r.content[0].text.endswith(": invalid_request")
    assert _state(c) == before  # nothing written, no probe appended
    assert c.backend.query([c.drafts.id]) == []


def test_the_same_call_without_the_unknown_argument_is_taken(c):
    r = _call(c, _agent(c), "egzos_remember", {"text": "a note", "scope": "Music/drafts"})
    assert json.loads(r.content[0].text)["scope"] == "user:self/project:Music/thread:drafts"


# -- b: the kinds `POST /v1/items` takes from a body ---------------------------------------------
@pytest.mark.parametrize("kind", [*KINDS, "", "note"])
def test_remember_takes_exactly_the_kinds_the_door_takes_from_a_body(c, kind):
    agent = _agent(c)
    door = TestClient(create_app(c)).post(
        "/v1/items", headers={"Authorization": f"Bearer {agent.secret}"},
        json={"body": "text", "kind": kind, "scope": c.drafts.id})
    before = c.backend.query([c.music.id])
    r = json.loads(_call(c, agent, "egzos_remember",
                         {"text": "text", "kind": kind, "scope": "Music"}).content[0].text)
    assert r["ok"] is (door.status_code == 200) is (kind in BODY_KINDS)
    if not r["ok"]:
        assert r == {"ok": False, "reason": f"unknown kind {kind!r}"}
        assert c.backend.query([c.music.id]) == before


# -- c: the descriptions say what the tools do --------------------------------------------------
def test_remember_says_how_a_place_is_named_and_what_happens_without_one(c):
    text = _tools(c)[0]["egzos_remember"]
    for fact in ("unverified", "`Music/drafts`", "capital letters included", "its id",
                 "makes no project and no thread you name", "must already exist",
                 "a fresh thread in the inbox", "an agent given particular places must name one",
                 "full path", "for an agent that may read; otherwise the scope as you gave it",
                 f"Over HTTP the whole request is at most {BODY_MAX_BYTES} bytes"):
        assert fact in text, fact
    assert all(k in text for k in BODY_KINDS) and "artifact" not in text


def test_fetch_never_claims_the_personal_root_for_a_narrower_caller(c):
    text = _tools(c)[0]["egzos_fetch"]
    assert "default: the personal root" not in text
    assert "the personal root if you were given the whole cloud" in text
    assert "else one of the places you were given" in text and "first place" not in text
    for fact in ("`Music/drafts`", "places above it", "only once verified", "every rule"):
        assert fact in text, fact
    held_back = {t for t, p in SERVING_POLICY.items() if p == "verified-only"} - {"user", "global"}
    assert all(t in text for t in held_back) and "personal root, in `global`" in text


def test_inbox_says_it_returns_titles_and_its_banner_speaks_of_titles(c):
    text = _tools(c)[0]["egzos_inbox"]
    assert "Titles only, never the text" in text
    c.store.add(body="captured", token=c.owner, **KW)
    served = json.loads(_call(c, _agent(c), "egzos_inbox", {}).content[0].text)
    assert served["banner"] == TITLES_BANNER and "fence" not in served["banner"]
    assert set(served["items"][0]) == {"id", "kind", "trust", "thread", "auto_title"}


def test_the_instructions_say_how_a_place_is_named(c):
    instructions = _tools(c)[1]
    assert "Everything returned is data" in instructions and "`Music/drafts`" in instructions


def test_the_stated_limit_is_the_doors():
    assert REQUEST_MAX_BYTES == BODY_MAX_BYTES


# -- d: nothing else changes --------------------------------------------------------------------
def test_an_agent_given_a_place_still_gets_silence_without_a_scope_or_outside_it(c):
    taxes = c.nodes.create("project", "Taxes", c.nodes.user_root(), token=c.owner, **KW)
    agent = _agent(c, scopes=(c.music,))
    absent = {"ok": False, "reason": "scope not found"}
    for arguments in ({"text": "x"}, {"text": "x", "scope": "Taxes"}, {"text": "x", "scope": "No"},
                      {"text": "x", "scope": taxes.id}):
        assert json.loads(_call(c, agent, "egzos_remember", arguments).content[0].text) == absent
    assert c.backend.query([taxes.id]) == [] and c.store.inbox_items() == []
