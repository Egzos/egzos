# Copyright 2026 Ali Sasanian
# SPDX-License-Identifier: LicenseRef-PolyForm-Strict-1.0.0
"""`egzos_inbox` is a read: it needs the `fetch` capability as well as coverage of the inbox, and a
token missing either learns the same nothing (#270, F29)."""

from __future__ import annotations

import asyncio
import dataclasses
import json

import pytest

from egzos.container import OWNER, Container
from egzos.mcp.server import build_server

# The parts of an audit entry that are per-write by nature, never per-caller.
_PER_WRITE = {"id", "ts", "hash", "prev", "prev_hash", "seq"}


@pytest.fixture()
def box(tmp_path):
    c = Container(tmp_path / "home")
    c.init()
    return c


def _client(c: Container, *, scopes: list[str], capabilities: list[str] | None = None):
    tok = c.auth.mint(principal="client", owner=OWNER, client="bot", role="contributor",
                      scopes=scopes, actor=OWNER, by_principal="interactive")
    if capabilities is not None:
        # No role bundle lacks `fetch`; a narrower token is stored as the container would hold it.
        tok = dataclasses.replace(tok, capabilities=capabilities)
        c.backend.put_token(tok)
    return tok


def _call(server, tool, args):
    r = asyncio.run(server.call_tool(tool, args))
    return r.content[0].text


def _shape(entry: dict) -> dict:
    return {k: v for k, v in entry.items() if k not in _PER_WRITE}


def _seed(c: Container) -> str:
    owner = c.auth.interactive_token()
    item = c.store.add(body="captured, not yet wrapped", kind="memory", scope=None, key=None,
                       tags=[], token=owner, actor=OWNER, principal="interactive")
    return item.id


def _other(c: Container) -> str:
    owner = c.auth.interactive_token()
    return c.nodes.create("project", "elsewhere", c.nodes.user_root(), token=owner,
                          actor=OWNER, principal="interactive").id


def test_coverage_without_fetch_answers_exactly_as_no_coverage(box):
    planted = _seed(box)
    inbox = box.nodes.inbox().id
    no_fetch = build_server(box, _client(box, scopes=[inbox], capabilities=["remember"]))
    no_cover = build_server(box, _client(box, scopes=[_other(box)]))

    a = _call(no_fetch, "egzos_inbox", {})
    a_entry = box.ledger.tail(1)[0]
    b = _call(no_cover, "egzos_inbox", {})
    b_entry = box.ledger.tail(1)[0]

    assert a == b and json.loads(a)["items"] == []
    assert a_entry["event"] == "context.fetch"
    assert _shape(a_entry) == _shape(b_entry)  # one entry, one shape: nothing tells them apart
    # nothing the token could not read reaches the chain
    assert all(planted not in json.dumps(e) for e in box.ledger.tail(1000)
               if e["event"] == "context.fetch")


def test_without_fetch_writes_one_probe_and_nothing_more(box):
    _seed(box)
    server = build_server(box, _client(box, scopes=[box.nodes.inbox().id],
                                       capabilities=["remember"]))
    before = len(box.ledger.tail(1000))
    _call(server, "egzos_inbox", {})
    after = box.ledger.tail(1000)
    assert len(after) == before + 1
    assert after[-1]["event"] == "context.fetch"


def test_fetch_and_coverage_still_lists_the_inbox(box):
    planted = _seed(box)
    server = build_server(box, _client(box, scopes=[box.nodes.inbox().id]))
    out = json.loads(_call(server, "egzos_inbox", {}))
    assert [i["id"] for i in out["items"]] == [planted]
    last = box.ledger.tail(1)[0]
    assert last["event"] == "context.fetch" and planted in json.dumps(last)


def test_a_fetch_revoked_mid_session_lands_on_the_next_call(box):
    planted = _seed(box)
    tok = _client(box, scopes=[box.nodes.inbox().id])
    server = build_server(box, tok)
    assert [i["id"] for i in json.loads(_call(server, "egzos_inbox", {}))["items"]] == [planted]
    box.backend.put_token(dataclasses.replace(tok, capabilities=["remember"]))
    assert json.loads(_call(server, "egzos_inbox", {}))["items"] == []
