# Copyright 2026 Ali Sasanian
# SPDX-License-Identifier: LicenseRef-PolyForm-Strict-1.0.0
"""#10's nightly report, F33: the lifeboat's pending count and queue must be scoped to what the
viewer's token decides over (`TrustEngine.decides_over`), the same rule `build_act` already
applies to a single id. A token covering only one end of a proposal's move sees it nowhere —
not the nav count, not the queue, not its own page — exactly as it sees an unknown id."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from egzos.container import OWNER, Container
from egzos.web.app import Lifeboat, create_app

ORIGIN = "http://testserver"


@pytest.fixture
def world(tmp_path, monkeypatch):
    """A proposal whose `from` and `to` live under different scopes, and a narrow token that
    covers only the `from` end — the shape `decides_over` is supposed to catch."""
    monkeypatch.delenv("EGZOS_TOKEN", raising=False)
    monkeypatch.setenv("EGZOS_STEP_UP_WINDOW_SECONDS", "0")
    c = Container(tmp_path / "home")
    owner = c.init()
    root = c.nodes.user_root()
    org = c.nodes.create("org", "acme", root, token=owner, actor=OWNER, principal="interactive")
    src = c.nodes.create("project", "p", org, token=owner, actor=OWNER, principal="interactive")
    dst = c.nodes.create("project", "q", org, token=owner, actor=OWNER, principal="interactive")
    # An audience member on `dst` only, so the move widens the audience and parks a proposal
    # instead of landing silently (TrustEngine.move).
    c.auth.mint(principal="client", owner=OWNER, client="watcher", role="reader",
                scopes=[dst.id], actor=OWNER, by_principal="interactive")
    item = c.store.add(body="draft", scope=src, token=owner, actor=OWNER,
                       principal="interactive")
    result = c.trust.move(item, dst, token=owner, actor=OWNER)
    assert result["gate"] == "pending"
    pid = result["proposal"]["id"]
    # A second interactive-principal token, scoped to `src` alone: it covers one end of the
    # move, not both, so `decides_over` must answer False for it.
    narrow = c.auth.mint(principal="interactive", owner=OWNER, client="cli2", role="admin",
                         scopes=[src.id], actor=OWNER, by_principal="interactive")
    boat = Lifeboat(c, key="k" * 32, host="testserver")
    client = TestClient(create_app(boat, ORIGIN), base_url=ORIGIN)
    assert client.get(f"/?k={boat.key}", follow_redirects=False).status_code == 303
    return c, boat, client, pid, narrow, monkeypatch


def test_narrow_token_counts_zero_owner_counts_one(world):
    c, boat, _client, pid, narrow, monkeypatch = world
    assert boat.pending_count() == 1  # the owner token, scope "*", covers both ends
    monkeypatch.setenv("EGZOS_TOKEN", narrow.secret)
    assert boat.pending_count() == 0
    assert [p["id"] for p in boat.open_proposals()] == []
    monkeypatch.delenv("EGZOS_TOKEN", raising=False)
    assert pid in [p["id"] for p in boat.open_proposals()]


def test_narrow_token_sees_an_empty_queue_owner_sees_the_proposal(world):
    _c, _boat, client, pid, narrow, monkeypatch = world
    monkeypatch.setenv("EGZOS_TOKEN", narrow.secret)
    r = client.get("/pending")
    assert r.status_code == 200
    assert "Nothing is waiting for you." in r.text
    assert pid not in r.text
    monkeypatch.delenv("EGZOS_TOKEN", raising=False)
    r = client.get("/pending")
    assert r.status_code == 200
    assert "Nothing is waiting for you." not in r.text
    assert pid in r.text


def test_narrow_token_gets_the_same_page_as_an_unknown_id(world):
    _c, _boat, client, pid, narrow, monkeypatch = world
    monkeypatch.setenv("EGZOS_TOKEN", narrow.secret)
    seen = client.get(f"/pending/{pid}")
    unknown = client.get("/pending/01ZZZZZZZZZZZZZZZZZZZZZZZZ")
    assert seen.status_code == unknown.status_code == 404
    assert seen.text == unknown.text
    monkeypatch.delenv("EGZOS_TOKEN", raising=False)
    r = client.get(f"/pending/{pid}")
    assert r.status_code == 200


def test_context_fetch_pending_count_is_the_scoped_count(world):
    c, boat, client, _pid, narrow, monkeypatch = world
    monkeypatch.setenv("EGZOS_TOKEN", narrow.secret)
    client.get("/pending")
    event = [e for e in c.ledger.tail(20) if e["details"].get("view") == "pending"][-1]
    assert event["details"]["pending_count"] == 0
    monkeypatch.delenv("EGZOS_TOKEN", raising=False)
    client.get("/pending")
    event = [e for e in c.ledger.tail(20) if e["details"].get("view") == "pending"][-1]
    assert event["details"]["pending_count"] == 1
