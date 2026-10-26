# Copyright 2026 Ali Sasanian
# SPDX-License-Identifier: LicenseRef-PolyForm-Strict-1.0.0
"""rest.md §3's other answers at every door: U+0000 anywhere in a request is `400`
`invalid_request` before any lookup, a store that cannot take the write lock in time is `503`
`busy` with `Retry-After: 1`, and any other failure is `500` `internal`, each under the same four
headers; the MCP tools and the CLI carry the same words in their own channel, never a driver's
message (storage.md §3.6, §3.7)."""

from __future__ import annotations

import asyncio
import contextlib
import json
import sqlite3

import pytest
from fastapi.testclient import TestClient
from mcp import Client

from egzos._types import StorageBusy
from egzos.api.app import Door, create_app
from egzos.auth import PREFIX
from egzos.backends.sqlite import SqliteBackend
from egzos.cli import main
from egzos.container import OWNER, Container
from egzos.mcp.server import build

FOUR = {"content-type": "application/json", "cache-control": "no-store",
        "x-content-type-options": "nosniff"}
DRIVER = "database is locked at /home/someone/egzos.db"  # what no answer may carry


@pytest.fixture
def c(tmp_path):
    box = Container(tmp_path)
    box.owner = box.init()
    return box


def _agent(c):
    return c.auth.mint(principal="client", owner=OWNER, client="probe", role="admin",
                       scopes=["*"], actor=OWNER, by_principal="interactive")


def _bearer(token) -> dict[str, str]:
    return {"Authorization": f"Bearer {token.secret}"}


@contextlib.contextmanager
def _held(path):
    """The container's write lock, held by a second connection for the block."""
    holder = SqliteBackend(path)
    with holder.atomic():
        yield
    holder.db.close()


def _shape(r, status, body):
    assert (r.status_code, r.content) == (status, body)
    assert {k: r.headers.get(k) for k in FOUR} == FOUR
    assert r.headers.get("retry-after") == ("1" if status == 503 else None)


@pytest.mark.parametrize(("method", "path", "body"), [
    ("GET", "/v1/items/nope%00", None),  # a path parameter, naming nothing
    ("GET", "/v1/fetch?scope=nope%00", None),  # a query parameter
    ("POST", "/v1/items/nope/move", {"to": "nope\0"}),  # a body value, for an item that is absent
    ("POST", "/v1/items", {"body": "b", "tags": ["a", "b\0"]}),  # nested, where a store keeps it
], ids=["path", "query", "body", "nested"])
def test_u0000_anywhere_in_a_request_is_a_400_before_any_lookup(c, method, path, body):
    agent, door = _agent(c), TestClient(create_app(c))
    before = c.ledger.tail(1000)
    r = door.request(method, path, headers=_bearer(agent), json=body)
    _shape(r, 400, b'{"error":"invalid_request"}')
    assert c.ledger.tail(1000) == before  # no probe: a 404 would have appended one


def test_a_store_that_cannot_take_the_write_lock_in_time_is_a_503(c):
    agent, door = _agent(c), TestClient(create_app(c))
    c.backend.db.execute("PRAGMA busy_timeout = 50")
    with _held(c.backend.path):  # the token check writes, as the throttle does for no token
        answers = [door.get("/v1/fetch", headers=_bearer(agent)), door.get("/v1/fetch")]
    for r in answers:
        _shape(r, 503, b'{"error":"busy"}')
    assert door.get("/v1/fetch", headers=_bearer(agent)).status_code == 200  # nothing was left


@pytest.mark.parametrize(("raised", "status", "body"), [
    (StorageBusy, 503, b'{"error":"busy"}'),
    (sqlite3.OperationalError, 500, b'{"error":"internal"}'),
], ids=["busy", "internal"])
@pytest.mark.parametrize("where", ["token-check", "route"])
def test_a_failure_before_or_in_the_route_answers_its_word_alone(c, monkeypatch, raised, status,
                                                                 body, where):
    agent = _agent(c)

    def fail(*args, **kwargs):
        raise raised(DRIVER)

    monkeypatch.setattr(*((Door, "caller") if where == "token-check" else (c.resolver, "resolve")),
                        fail)
    _shape(TestClient(create_app(c)).get("/v1/fetch", headers=_bearer(agent)), status, body)


def test_the_mcp_tools_answer_u0000_and_a_busy_store_with_the_doors_words(c):
    agent = _agent(c)
    server = build(c, lambda: agent)
    c.backend.db.execute("PRAGMA busy_timeout = 50")

    async def call(name, arguments):
        async with Client(server) as client:
            return await client.call_tool(name, arguments)

    answers = {"invalid_request": asyncio.run(call("egzos_remember", {"text": "t",
                                                                      "scope": "nope\0"}))}
    with _held(c.backend.path):
        answers["busy"] = asyncio.run(call("egzos_remember", {"text": "t"}))
    for word, r in answers.items():
        assert r.is_error and r.content[0].text.endswith(f": {word}")
        assert "locked" not in r.content[0].text
    assert c.store.inbox_items() == []  # neither wrote


def test_the_cli_answers_u0000_and_a_busy_store_with_the_doors_words(tmp_path, monkeypatch,
                                                                     capsys):
    monkeypatch.setenv("EGZOS_HOME", str(tmp_path / ".egzos"))
    monkeypatch.delenv("EGZOS_TOKEN", raising=False)
    monkeypatch.chdir(tmp_path)
    assert main(["init"]) == 0
    capsys.readouterr()
    assert main(["add", "x\0"]) == 2 and capsys.readouterr().err == "Error: invalid_request\n"
    assert main(["--json", "add", "x\0"]) == 2
    assert json.loads(capsys.readouterr().out) == {"error": "invalid_request"}
    monkeypatch.setattr("egzos.backends.sqlite.LOCK_TIMEOUT", 0.05)
    with _held(tmp_path / ".egzos" / "egzos.db"):
        assert main(["--json", "add", "note"]) == 1
    out = capsys.readouterr().out
    assert json.loads(out) == {"error": "busy"} and "locked" not in out


def test_u0000_in_a_bearer_is_the_one_unauthenticated_answer(c):
    """§2 item 5: a malformed bearer is the unauthenticated answer, counted as one, never a 500."""
    agent, door = _agent(c), TestClient(create_app(c))
    bad = PREFIX + "\0" + agent.secret[len(PREFIX) + 1:]  # the id's first character, U+0000
    unknown = PREFIX + "0" * 26 + "_" + "x" * 32
    r_bad = door.get("/v1/fetch", headers={"Authorization": f"Bearer {bad}"})
    r_unknown = door.get("/v1/fetch", headers={"Authorization": f"Bearer {unknown}"})
    assert (r_bad.status_code, r_bad.content) == (r_unknown.status_code, r_unknown.content)
    assert r_bad.status_code == 401


def test_a_deeply_nested_body_is_refused_by_its_shape_not_by_recursion(c):
    agent, door = _agent(c), TestClient(create_app(c))
    deep: list = []
    for _ in range(900):
        deep = [deep]
    r = door.post("/v1/items", headers=_bearer(agent), json={"body": "b", "tags": deep})
    assert r.status_code == 400
