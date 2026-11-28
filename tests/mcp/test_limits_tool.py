# Copyright 2026 Ali Sasanian
# SPDX-License-Identifier: LicenseRef-PolyForm-Strict-1.0.0
"""rest.md §4.6, §4.7: `egzos_limits` is `GET /v1/limits`, its answer and its read, for an agent
that cannot reach the route: any live token, one that may not read included, gets the same
answer and appends the same `context.fetch` (`read: limits`)."""

from __future__ import annotations

import asyncio
import json

import pytest
from fastapi.testclient import TestClient
from mcp import Client

from egzos.api.app import create_app
from egzos.container import OWNER, Container
from egzos.mcp.server import NOT_LIVE, build

KW = {"actor": OWNER, "principal": "interactive"}
SUB = "11111111-1111-4111-8111-111111111111"
KEYS = ("upload_max_bytes", "inline_max_bytes", "uploads_held_max")


@pytest.fixture
def c(tmp_path):
    box = Container(tmp_path)
    box.owner = box.init()
    box.drafts = box.nodes.create("project", "Music", box.nodes.user_root(), token=box.owner, **KW)
    return box


def _limits(c, caller):
    async def go():
        async with Client(build(c, caller)) as client:
            listed = {t.name: t.description for t in (await client.list_tools()).tools}
            return listed["egzos_limits"], await client.call_tool("egzos_limits", {})

    description, r = asyncio.run(go())
    return description, r.content[0].text


def _read(c):
    entry = c.ledger.tail(1)[-1]
    return (entry["event"], entry["actor"], entry["principal"], entry["subject"], entry["scope"],
            entry["details"])


@pytest.mark.parametrize("scopes", ["one place", "whole cloud"])
def test_egzos_limits_answers_get_v1_limits_and_appends_its_read(c, scopes):
    c.set_config("blobs.upload_max_bytes", 5_000_000, token=c.owner)
    token = c.auth.mint(principal="client", owner=OWNER, client="agent", role="reader",
                        scopes=[c.drafts.id] if scopes == "one place" else ["*"], actor=OWNER,
                        by_principal="interactive")
    description, served = _limits(c, lambda: token)
    tool_read = _read(c)
    r = TestClient(create_app(c)).get("/v1/limits",
                                      headers={"Authorization": f"Bearer {token.secret}"})
    assert r.status_code == 200 and json.loads(served) == r.json()
    assert r.json()["upload_max_bytes"] == 5_000_000
    assert tool_read == _read(c)  # the same read, entry for entry
    assert tool_read[0] == "context.fetch" and tool_read[5]["read"] == "limits"
    assert tool_read[5]["items"] == [] and tool_read[3] is tool_read[4] is None
    assert all(f"`{k}`" in description for k in ("contract", "features", *KEYS))


def test_a_caller_that_may_not_read_still_reads_the_limits(c):
    c.identity.grant_user(SUB, name="P", role="admin", scopes=["*"], **KW)
    c.backend.put_agent_registration({
        "client_id": "scribe", "sub": SUB, "kind": "agent", "name": "scribe",
        "capabilities": ["remember"], "scopes": ["*"], "created_at": "2026-11-28T00:00:00Z",
        "revoked": False})
    _, served = _limits(c, lambda: c.identity._agent("scribe", SUB))
    assert json.loads(served) == TestClient(create_app(c)).get(
        "/v1/limits", headers={"Authorization": f"Bearer {c.owner.secret}"}).json()
    assert [e["actor"] for e in c.ledger.tail(2)] == ["agent:scribe", OWNER]


def test_a_token_no_longer_live_gets_the_one_answer_and_appends_nothing(c):
    seq = c.ledger.tail(1)[-1]["seq"]
    assert _limits(c, lambda: None)[1] == NOT_LIVE
    assert c.ledger.tail(1)[-1]["seq"] == seq
