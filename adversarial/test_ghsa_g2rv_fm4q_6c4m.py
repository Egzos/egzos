# Copyright 2026 Ali Sasanian
# SPDX-License-Identifier: LicenseRef-PolyForm-Strict-1.0.0
"""GHSA-g2rv-fm4q-6c4m: request strings must be well-formed Unicode (rest.md §3). A string anywhere
in a request that holds a surrogate code point outside a pair is refused as U+0000 is: `400
invalid_request` at the REST door before any lookup, with nothing written and no entry appended,
and `invalid_request` in an MCP tool's error result."""

from __future__ import annotations

import asyncio
import hashlib
import json

import pytest
from fastapi.testclient import TestClient
from mcp import Client

from egzos.api.app import create_app
from egzos.container import OWNER, Container
from egzos.mcp.server import build

pytestmark = pytest.mark.adversarial

LONE = "\ud800"
INVALID = b'{"error":"invalid_request"}'
KW = {"actor": OWNER, "principal": "interactive"}


@pytest.fixture
def c(tmp_path):
    box = Container(tmp_path)
    box.owner = box.init()
    box.project = box.nodes.create("project", "shared", box.nodes.user_root(), token=box.owner,
                                   **KW)
    return box


def _post(c, path, body):
    """The body as JSON text with `\\ud800` escaped, as any JSON client may send it."""
    return TestClient(create_app(c)).post(
        path, headers={"Authorization": f"Bearer {c.owner.secret}",
                       "Content-Type": "application/json"},
        content=json.dumps(body).encode())


def _state(c):
    tail = c.ledger.tail(1)[-1]
    return (len(c.backend.list_nodes()), tail["seq"], tail["hash"],
            sorted(i.id for _, i in c.store.inbox_items()), c.backend.query([c.project.id]))


@pytest.mark.parametrize("body", [
    {"body": "a note", "tags": [LONE]},
    {"body": "a fine title\n" + LONE + " and the rest"},
], ids=["in a tag", "past the title"])
def test_text_that_is_not_well_formed_is_refused_and_nothing_is_stored(c, body):
    before = _state(c)
    r = _post(c, "/v1/items", {**body, "scope": c.project.id})
    assert (r.status_code, r.content) == (400, INVALID)
    assert _state(c) == before


@pytest.mark.parametrize(("path", "body"), [
    ("/v1/items", {"body": LONE}),
    ("/v1/items", {"body": "ok " + LONE + " x", "scope": "inbox"}),
    ("/v1/items", {"body": "x", "scope": LONE}),
    ("/v1/items", {"body": "x", "key": LONE}),
    ("/v1/scopes", {"type": "thread", "name": "ok", "parent": LONE}),
], ids=["pure capture", "inbox", "scope", "key", "parent"])
def test_a_request_string_that_is_not_well_formed_is_a_400_and_leaves_the_chain_as_it_was(
        c, path, body):
    before = _state(c)
    r = _post(c, path, body)
    assert (r.status_code, r.content) == (400, INVALID)
    assert _state(c) == before
    assert c.ledger.verify()["ok"]


def test_an_upload_whose_strings_are_not_well_formed_is_refused(c):
    data = b"hello world" * 10
    sha = hashlib.sha256(data).hexdigest()
    opened = {"scope": c.nodes.inbox().id, "mime": "application/octet-stream", "size": len(data),
              "sha256": sha}
    r = _post(c, "/v1/uploads", {**opened, "name": "a" + LONE})
    assert (r.status_code, r.content) == (400, INVALID)
    assert c.backend.list_uploads() == []
    # Staged well, then written as an item with a key that is not well-formed.
    up = _post(c, "/v1/uploads", {**opened, "name": "a.bin"}).json()["upload"]
    door = TestClient(create_app(c))
    put = door.put(f"/v1/uploads/{up}", headers={"Authorization": f"Bearer {c.owner.secret}"},
                   content=data)
    assert put.status_code == 200
    before = _state(c)
    r = _post(c, "/v1/items", {"kind": "artifact", "upload": up, "key": LONE})
    assert (r.status_code, r.content) == (400, INVALID)
    assert _state(c) == before
    assert not c.blobs.exists(sha)  # the upload stays staged


def _call(c, name, arguments):
    server = build(c, lambda: c.owner)

    async def go():
        async with Client(server) as client:
            return await client.call_tool(name, arguments)

    return asyncio.run(go())


@pytest.mark.parametrize("arguments", [
    {"text": LONE}, {"text": "t", "tags": [LONE]}, {"text": "t", "scope": LONE},
    {"text": "t", "key": LONE},
], ids=["text", "tag", "scope", "key"])
def test_an_mcp_argument_that_is_not_well_formed_is_invalid_request_and_writes_nothing(
        c, arguments):
    before = _state(c)
    r = _call(c, "egzos_remember", arguments)
    assert r.is_error and r.content[0].text.endswith(": invalid_request")
    assert _state(c) == before


def test_text_already_held_is_served_whole_by_every_mcp_read_tool(c):
    # Written straight through the store.
    for scope in (c.project, None):
        c.store.add(body="a title\n" + LONE + " held", tags=[LONE], scope=scope, token=c.owner,
                    **KW)
    for name, arguments in (("egzos_fetch", {"scope": c.project.id}), ("egzos_inbox", {})):
        r = _call(c, name, arguments)
        assert not r.is_error
        wire = r.model_dump_json()
        wire.encode("utf-8")
        served = json.loads(r.content[0].text)
        assert served["items"], name
        if name == "egzos_fetch":  # the body as it was written, surrogate and all
            assert any(LONE in i["content"] for i in served["items"])
