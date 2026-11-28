# Copyright 2026 Ali Sasanian
# SPDX-License-Identifier: LicenseRef-PolyForm-Strict-1.0.0
"""rest.md §4.7 `<block>`: `egzos_fetch` names each item's writer, `"by"` (its `provenance.actor`),
and for an artifact its file, `"name"`, `"mime"`, `"size"` and `"sha256"`, read from the item as
stored and kept beside the fence, never inside it. Each is a key `GET /v1/fetch` serves the same
caller, so the tool serves no more than its route; and a fetch still mints no grant."""

from __future__ import annotations

import asyncio
import hashlib
import json

import pytest
from fastapi.testclient import TestClient
from mcp import Client

from egzos.api.app import create_app
from egzos.container import OWNER, Container
from egzos.mcp.server import DATA_BANNER, build

KW = {"actor": OWNER, "principal": "interactive"}
SUB = "11111111-1111-4111-8111-111111111111"
FILE_KEYS = ("name", "mime", "size", "sha256")


def _file(c, token, scope, name, mime, data):
    """An artifact written as the upload routes write it: open, bytes, item."""
    record = c.uploads.open(token, scope=scope, name=name, mime=mime, size=len(data),
                            sha256=hashlib.sha256(data).hexdigest())
    c.uploads.put(token, record["id"], data)
    return c.uploads.item(token, record["id"], scope=None, key=None, tags=[])


@pytest.fixture
def c(tmp_path):
    box = Container(tmp_path)
    box.owner = box.init()
    make = box.nodes.create
    box.music = make("project", "Music", box.nodes.user_root(), token=box.owner, **KW)
    box.drafts = make("thread", "drafts", box.music, token=box.owner, **KW)
    box.taxes = make("project", "Taxes", box.nodes.user_root(), token=box.owner, **KW)
    box.note = box.store.add(body="a note", scope=box.drafts, token=box.owner, **KW)
    box.lyrics = _file(box, box.owner, box.drafts, "lyrics.txt", "text/plain", b"la la la")
    box.cover = _file(box, box.owner, box.drafts, "cover.png", "image/png", b"\x89PNG" * 40)
    _file(box, box.owner, box.taxes, "receipt.pdf", "application/pdf", b"%PDF-1.7")
    box.identity.grant_user(SUB, name="P", role="admin", scopes=["*"], **KW)
    box.backend.put_agent_registration({
        "client_id": "helper", "sub": SUB, "kind": "agent", "name": "helper",
        "capabilities": ["fetch", "remember"], "scopes": [box.music.id],
        "created_at": "2026-11-28T00:00:00Z", "revoked": False})
    box.helper = lambda: box.identity._agent("helper", SUB)
    box.mix = _file(box, box.helper(), box.drafts, "mix.wav", "audio/wav", b"RIFF" * 10)
    return box


def _agent(c, scopes):
    return c.auth.mint(principal="client", owner=OWNER, client="agent", role="reader",
                       scopes=scopes, actor=OWNER, by_principal="interactive")


def _fetch(c, caller, scope):
    async def go():
        async with Client(build(c, caller)) as client:
            return await client.call_tool("egzos_fetch", {"scope": scope})

    return json.loads(asyncio.run(go()).content[0].text)


def test_a_fetch_names_each_artifacts_file_and_every_items_writer(c):
    served = _fetch(c, c.helper, "Music/drafts")
    blocks = {b["id"]: b for b in served["items"]}
    assert served["banner"] == DATA_BANNER  # an answer naming a file opens with the banner
    assert set(blocks) == {c.note.id, c.lyrics.id, c.cover.id, c.mix.id}
    assert {i: b["by"] for i, b in blocks.items()} == {
        c.note.id: OWNER, c.lyrics.id: OWNER, c.cover.id: OWNER, c.mix.id: "agent:helper"}
    assert not set(FILE_KEYS) & set(blocks[c.note.id])  # a note names no file
    for item, name, mime, data in ((c.lyrics, "lyrics.txt", "text/plain", b"la la la"),
                                   (c.cover, "cover.png", "image/png", b"\x89PNG" * 40),
                                   (c.mix, "mix.wav", "audio/wav", b"RIFF" * 10)):
        block = blocks[item.id]
        assert {k: block[k] for k in FILE_KEYS} == {
            "name": name, "mime": mime, "size": len(data),
            "sha256": hashlib.sha256(data).hexdigest()}
        assert name not in block["content"]  # beside the fence, never inside it
    assert "la la la" in blocks[c.lyrics.id]["content"]  # a text file's inline text is fenced


def test_a_promoted_items_writer_is_its_writer_never_its_promoter(c):
    c.trust.promote(c.backend.get(c.mix.id), token=c.owner, actor=OWNER)
    blocks = {b["id"]: b for b in _fetch(c, c.helper, "Music/drafts")["items"]}
    assert (c.backend.get(c.mix.id).provenance["approved_by"], blocks[c.mix.id]["by"]) == (
        OWNER, "agent:helper")


def test_an_unverified_file_in_a_place_that_serves_verified_only_is_never_named(c):
    held = _file(c, c.owner, c.nodes.user_root(), "plan.txt", "text/plain", b"held back")
    served = _fetch(c, lambda: _agent(c, ["*"]), "Music/drafts")
    assert held.id not in {b["id"] for b in served["items"]}
    assert "plan.txt" not in str(served) and "held back" not in str(served)


def test_a_fetch_still_mints_no_grant_for_an_artifact(c):
    before = [e for e in c.ledger.tail(1000) if e["event"] == "blob.grant"]
    served = _fetch(c, lambda: _agent(c, ["*"]), "Music/drafts")
    assert all("download" not in b and "grant" not in b for b in served["items"])
    assert [e for e in c.ledger.tail(1000) if e["event"] == "blob.grant"] == before == []


@pytest.mark.parametrize("scopes", ["one place", "whole cloud"])
@pytest.mark.parametrize("scope", ["Music/drafts", "Taxes"])
def test_each_key_is_one_the_route_serves_the_same_caller(c, scopes, scope):
    token = _agent(c, [c.drafts.id] if scopes == "one place" else ["*"])
    served = _fetch(c, lambda: token, scope)
    r = TestClient(create_app(c)).get("/v1/fetch", params={"scope": scope},
                                      headers={"Authorization": f"Bearer {token.secret}"})
    route = {e["item"]["id"]: e["item"] for e in r.json()["items"]} if r.status_code == 200 else {}
    assert {b["id"] for b in served["items"]} == set(route)
    assert bool(route) == (scope == "Music/drafts" or scopes == "whole cloud")
    for block in served["items"]:
        item = route[block["id"]]
        assert block["by"] == item["provenance"]["actor"]
        stored = item["content"] if item["kind"] == "artifact" else {}
        assert {k: block.get(k) for k in FILE_KEYS} == {
            "name": stored.get("filename"), "mime": stored.get("mime"),
            "size": stored.get("size"), "sha256": stored.get("sha256")}


def test_a_caller_that_may_not_read_is_named_no_file_and_no_writer(c):
    c.backend.put_agent_registration({
        "client_id": "scribe", "sub": SUB, "kind": "agent", "name": "scribe",
        "capabilities": ["remember"], "scopes": ["*"], "created_at": "2026-11-28T00:00:00Z",
        "revoked": False})
    served = _fetch(c, lambda: c.identity._agent("scribe", SUB), "Music/drafts")
    assert served == {"banner": DATA_BANNER, "scope": "Music/drafts", "chain": [], "items": []}
