# Copyright 2026 Ali Sasanian
# SPDX-License-Identifier: LicenseRef-PolyForm-Strict-1.0.0
"""rest.md §4.7: an argument not of its exact JSON type is `invalid_request`, decided on the
arguments alone and before any lookup: an integer is never a string, a boolean or a float, and a
string is never a null, a list or an object. The answer is one, whatever the call names and
whoever makes it, and every tool the door serves is read this way."""

from __future__ import annotations

import asyncio

import pytest
from mcp import Client

from egzos.container import OWNER, Container
from egzos.mcp.server import build, known

KW = {"actor": OWNER, "principal": "interactive"}
SUB = "11111111-1111-4111-8111-111111111111"


@pytest.fixture
def c(tmp_path):
    box = Container(tmp_path)
    box.owner = box.init()
    box.music = box.nodes.create("project", "Music", box.nodes.user_root(), token=box.owner, **KW)
    box.drafts = box.nodes.create("thread", "drafts", box.music, token=box.owner, **KW)
    box.store.add(body="a note", scope=box.drafts, token=box.owner, **KW)
    return box


def _callers(c):
    """An agent given one place, an agent given the whole cloud, an agent that may not read, and
    a token no longer live."""
    def agent(scopes):
        token = c.auth.mint(principal="client", owner=OWNER, client="agent", role="contributor",
                            scopes=scopes, actor=OWNER, by_principal="interactive")
        return lambda: token

    c.identity.grant_user(SUB, name="P", role="admin", scopes=["*"], **KW)
    c.backend.put_agent_registration({
        "client_id": "scribe", "sub": SUB, "kind": "agent", "name": "scribe",
        "capabilities": ["remember"], "scopes": ["*"], "created_at": "2026-11-28T00:00:00Z",
        "revoked": False})
    return {"one place": agent([c.drafts.id]), "whole cloud": agent(["*"]),
            "no fetch": lambda: c.identity._agent("scribe", SUB), "not live": lambda: None}


def _call(c, caller, name, arguments, ran=None):
    """One call through a real MCP client. With `ran`, the server also serves a tool taking an
    integer, a boolean, a string and a list of strings, which records each call it receives."""
    server = build(c, caller)
    if ran is not None:
        @server.tool(name="probe")
        async def probe(n: int, flag: bool = False, name: str | None = None,
                        words: list[str] | None = None) -> str:
            ran.append((n, flag, name, words))
            return "ran"

    async def go():
        async with Client(server) as client:
            return await client.call_tool(name, arguments)

    return asyncio.run(go())


def _state(c):
    return c.ledger.tail(1)[-1]["seq"], len(c.backend.list_nodes()), len(c.store.inbox_items())


WRONG_INTEGERS = [{"n": "5"}, {"n": 5.0}, {"n": True}, {"n": False}, {"n": None}, {"n": [5]},
                  {"n": {"n": 5}}, {"n": 5, "flag": "true"}, {"n": 5, "flag": 1},
                  {"n": 5, "flag": None}, {"n": 5, "name": 5}, {"n": 5, "words": "a"},
                  {"n": 5, "words": [1]}, {"n": 5, "words": [["a"]]}, {}]


@pytest.mark.parametrize("arguments", WRONG_INTEGERS, ids=repr)
def test_an_integer_is_never_a_string_a_boolean_a_float_or_a_list(c, arguments):
    ran, callers = [], _callers(c)
    before = _state(c)
    answers = {who: _call(c, caller, "probe", arguments, ran) for who, caller in callers.items()}
    assert {(r.is_error, r.content[0].text) for r in answers.values()} == {
        (True, "Error executing tool probe: invalid_request")}
    assert ran == [] and _state(c) == before  # the tool never ran, and nothing was read


def test_each_value_of_its_exact_type_is_taken_as_it_is(c):
    ran = []
    r = _call(c, lambda: c.owner, "probe",
              {"n": 5, "flag": True, "name": None, "words": ["a"]}, ran)
    assert not r.is_error and ran == [(5, True, None, ["a"])]


#: Each running tool's arguments: "s" a string, "a" a list of strings, "?" where null is taken.
TYPED = {"egzos_fetch": {"scope": "s?", "query": "s?", "kinds": "a?"},
         "egzos_remember": {"text": "s", "kind": "s", "scope": "s?", "key": "s?", "tags": "a?"},
         "egzos_places": {"under": "s?"}, "egzos_inbox": {}, "egzos_limits": {},
         "egzos_get": {"id": "s"}}


def _wrong(form):
    values = [5, 5.0, True, {"x": 1}] + ([] if form.endswith("?") else [None])
    if form.startswith("a"):
        return [*values, "x", *([v] for v in (5, 5.0, True, None, ["x"], {"x": 1}))]
    return [*values, ["x"]]


#: Each argument of each type it does not take, a required one left out, and a place that exists
#: and one that does not wrapped alike, so the answer cannot turn on what the call names.
WRONG_STRINGS = [
    (tool, {**({"text": "x"} if tool == "egzos_remember" else {}), arg: v})
    for tool, args in TYPED.items() for arg, form in args.items() for v in _wrong(form)
] + [("egzos_remember", {}), ("egzos_get", {}), ("egzos_places", {"under": ["Music"]})] + [
    (tool, {**({"text": "x"} if tool == "egzos_remember" else {}), "scope": [place]})
    for tool in ("egzos_remember", "egzos_fetch") for place in ("Music/drafts", "Nowhere")]


@pytest.mark.parametrize(("name", "arguments"), WRONG_STRINGS, ids=repr)
def test_an_argument_of_the_wrong_type_is_one_invalid_request_for_every_caller(c, name, arguments):
    callers = _callers(c)
    before = _state(c)
    answers = {who: _call(c, caller, name, arguments) for who, caller in callers.items()}
    assert {(r.is_error, r.content[0].text) for r in answers.values()} == {
        (True, f"Error executing tool {name}: invalid_request")}
    assert _state(c) == before  # nothing written, no probe appended


def test_a_null_where_an_argument_is_optional_is_left_out_as_at_the_route(c):
    agent = _callers(c)["whole cloud"]
    r = _call(c, agent, "egzos_remember", {"text": "x", "scope": None, "key": None, "tags": None})
    assert not r.is_error and '"ok":true' in r.content[0].text.replace(" ", "")


def test_every_tool_served_has_arguments_read_by_exact_type(c):
    async def go():
        async with Client(build(c, lambda: c.owner)) as client:
            return (await client.list_tools()).tools

    tools = asyncio.run(go())
    assert {t.name: set(t.input_schema.get("properties", {})) for t in tools} == {
        name: set(args) for name, args in TYPED.items()}
    assert all(known(schema) for t in tools
               for schema in t.input_schema.get("properties", {}).values())
    assert not any(known(schema) for schema in [  # unread forms, and a bound on a value
        {"type": "number"}, {"type": "array"}, {"type": "string", "enum": ["a"]},
        {"type": "integer", "minimum": 0}, {"type": "string", "pattern": "^a$"},
        {"type": "array", "items": {"type": "string"}, "maxItems": 2},
        {"anyOf": [{"type": "string", "maxLength": 3}, {"type": "null"}]}])


def test_build_refuses_a_tool_whose_argument_type_it_cannot_read(c, monkeypatch):
    monkeypatch.setattr("egzos.mcp.server.known", lambda schema: False)
    with pytest.raises(TypeError, match="cannot be read exactly"):
        build(c, lambda: c.owner)
