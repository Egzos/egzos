# Copyright 2026 Ali Sasanian
# SPDX-License-Identifier: LicenseRef-PolyForm-Strict-1.0.0
"""rest.md §4.1 item 5: `egzos_places` is `GET /v1/scopes` for an agent, built on the same
function: the same capability, read, silence and node shape. With no `under`, a caller given the
whole cloud gets the places under the personal root, and a narrower caller every place it was
given. It lists places and nothing else (#415)."""

from __future__ import annotations

import asyncio
import json

import pytest
from fastapi.testclient import TestClient
from mcp import Client

from egzos.api.app import create_app
from egzos.container import OWNER, Container
from egzos.mcp.server import build

KW = {"actor": OWNER, "principal": "interactive"}
SUB = "11111111-1111-4111-8111-111111111111"


@pytest.fixture
def c(tmp_path):
    box = Container(tmp_path)
    box.owner = box.init()
    make = box.nodes.create
    box.music = make("project", "Music", box.nodes.user_root(), token=box.owner, **KW)
    box.drafts = make("thread", "drafts", box.music, token=box.owner, **KW)
    box.taxes = make("project", "Taxes 2026", box.nodes.user_root(), token=box.owner, **KW)
    box.receipts = make("thread", "receipts", box.taxes, token=box.owner, **KW)
    box.store.add(body="a note", scope=box.drafts, token=box.owner, **KW)
    return box


def _token(c, *places, role="reader"):
    return c.auth.mint(principal="client", owner=OWNER, client="agent", role=role,
                       scopes=[p if p == "*" else p.id for p in places], actor=OWNER,
                       by_principal="interactive")


def _registered(c, caps):
    """An agent registered for a person over everything, read as the grants stand at each call."""
    c.identity.grant_user(SUB, name="P", role="admin", scopes=["*"], **KW)
    c.backend.put_agent_registration({
        "client_id": "helper", "sub": SUB, "kind": "agent", "name": "helper",
        "capabilities": caps, "scopes": [c.music.id], "created_at": "2026-11-27T00:00:00Z",
        "revoked": False})
    return lambda: c.identity._agent("helper", SUB)


def _places(c, caller, arguments=None):
    async def go():
        async with Client(build(c, caller)) as client:
            return await client.call_tool("egzos_places", arguments or {})

    r = asyncio.run(go())
    return r, (None if r.is_error else r.content[0].text)


def _paths(text):
    return [n["path"] for n in json.loads(text)["nodes"]]


def _route(c, token, under=None):
    query = f"?under={under}" if under else ""
    return TestClient(create_app(c)).get(f"/v1/scopes{query}",
                                         headers={"Authorization": f"Bearer {token.secret}"})


def test_an_agent_over_one_project_sees_it_and_what_is_inside(c):
    t = _token(c, c.music)
    assert _paths(_places(c, lambda: t)[1]) == ["user:self/project:Music"]
    inside = _places(c, lambda: t, {"under": "Music"})[1]
    assert _paths(inside) == ["user:self/project:Music/thread:drafts"]
    assert json.loads(inside)["nodes"] == _route(c, t, c.music.id).json()["nodes"]


def test_an_agent_over_three_places_sees_every_one_sorted_by_path(c):
    t = _token(c, c.taxes, c.drafts, c.receipts)
    assert _paths(_places(c, lambda: t)[1]) == [
        "user:self/project:Music/thread:drafts", "user:self/project:Taxes 2026",
        "user:self/project:Taxes 2026/thread:receipts"]
    node = json.loads(_places(c, lambda: t)[1])["nodes"][0]
    assert set(node) == {"id", "type", "name", "parent", "created_at", "path"}


def test_an_agent_over_everything_sees_the_places_under_the_personal_root_as_the_route(c):
    t = _token(c, "*")
    text = _places(c, lambda: t)[1]
    assert json.loads(text)["nodes"] == _route(c, t).json()["nodes"]
    assert "user:self/project:Music" in _paths(text)


def test_it_lists_places_only_writes_nothing_and_its_read_is_the_routes(c):
    t = _token(c, "*")
    nodes, items = len(c.backend.list_nodes()), c.backend.query([c.drafts.id])
    text = _places(c, lambda: t, {"under": c.music.id})[1]
    assert "note" not in text and set(json.loads(text)) == {"nodes"}
    tool = c.ledger.tail(1)[-1]
    _route(c, t, c.music.id)
    route = c.ledger.tail(1)[-1]
    same = ("event", "actor", "principal", "subject", "scope", "details")
    assert {k: tool[k] for k in same} == {k: route[k] for k in same}
    assert (len(c.backend.list_nodes()), c.backend.query([c.drafts.id])) == (nodes, items)


def test_without_fetch_it_is_refused_as_the_route_refuses(c):
    caller = _registered(c, ["remember"])
    seq = c.ledger.tail(1)[-1]["seq"]
    assert json.loads(_places(c, caller)[1]) == {"nodes": []}
    assert json.loads(_places(c, caller, {"under": "Music"})[1]) == {"nodes": []}
    probes = c.ledger.tail(c.ledger.tail(1)[-1]["seq"] - seq)
    assert [(e["event"], e["details"]["items"], "nodes" in e["details"]) for e in probes] == [
        ("context.fetch", [], False)] * 2


def test_under_a_place_outside_its_places_answers_as_an_absent_one_byte_for_byte(c):
    t = _token(c, c.music)
    outside = _places(c, lambda: t, {"under": c.taxes.id})[1]
    absent = _places(c, lambda: t, {"under": "Nowhere/at all"})[1]
    by_name = _places(c, lambda: t, {"under": "Taxes 2026"})[1]
    assert outside == absent == by_name == '{"nodes": []}'


def test_an_ended_registration_is_no_longer_live(c):
    caller = _registered(c, ["fetch"])
    assert _paths(_places(c, caller)[1]) == ["user:self/project:Music"]
    c.identity.revoke_agent("helper", SUB, **KW)
    assert json.loads(_places(c, caller)[1]) == {
        "ok": False, "reason": "this token is no longer valid"}


@pytest.mark.parametrize("arguments", [{"scope": "Music"}, {"under": "Music", "depth": 2}])
def test_an_unknown_argument_is_invalid_request(c, arguments):
    t = _token(c, "*")
    seq = c.ledger.tail(1)[-1]["seq"]
    r, _ = _places(c, lambda: t, arguments)
    assert r.is_error and r.content[0].text.endswith(": invalid_request")
    assert c.ledger.tail(1)[-1]["seq"] == seq


def test_its_description_says_to_use_it_before_saving_and_how_paths_are_used(c):
    async def go():
        async with Client(build(c, lambda: c.owner)) as client:
            return {t.name: t.description for t in (await client.list_tools()).tools}

    text = asyncio.run(go())["egzos_places"]
    for fact in ("exact name and path", "before saving or fetching",
                 "used as `scope` exactly as it is printed", "every place you were given"):
        assert fact in text, fact
    assert "egzos_places lists them all" in asyncio.run(go())["egzos_fetch"]


def test_a_given_place_names_its_parent_only_where_the_caller_covers_it(c):
    thread_only = json.loads(_places(c, lambda: _token(c, c.drafts))[1])["nodes"]
    assert [(n["path"], n["parent"]) for n in thread_only] == [
        ("user:self/project:Music/thread:drafts", None)]
    both = json.loads(_places(c, lambda: _token(c, c.music, c.drafts))[1])["nodes"]
    assert [n["parent"] for n in both] == [None, c.music.id]  # Music's own parent is uncovered
    inside = json.loads(_places(c, lambda: _token(c, c.music), {"under": "Music"})[1])["nodes"]
    assert inside[0]["parent"] == c.music.id
    t = _token(c, "*")
    assert json.loads(_places(c, lambda: t)[1])["nodes"] == _route(c, t).json()["nodes"]


def test_an_empty_under_is_no_under(c):
    t = _token(c, c.taxes, c.drafts)
    assert _places(c, lambda: t, {"under": ""})[1] == _places(c, lambda: t)[1]
