# Copyright 2026 Ali Sasanian
# SPDX-License-Identifier: LicenseRef-PolyForm-Strict-1.0.0
"""rest.md §4.7 `egzos_get(id)` is `GET /v1/items/{id}`: `fetch` on the item's scope and the
route's serving check, one block whose `layer` is its own node and `shadowed_by` null, one
`context.fetch`. For an artifact whose bytes do not ride `inline` it asks Trust for §6's grant and,
where Trust mints one, carries `"download": {"url", "expires_at"}` beside the block, `url` being
`grant_url` written on the container's public origin (identity.md §2); where the container names
no `identity.origin` and the call came over stdio, it asks for no grant. Refused, it answers
`{"banner", "items": []}`, and the tool serves less than its route, never more."""

from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import time
from datetime import datetime
from urllib.parse import urlsplit

import httpx2
import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import ec
from fastapi.testclient import TestClient
from mcp import Client
from mcp.client.streamable_http import streamable_http_client

from egzos.api.app import create_app
from egzos.container import OWNER, Container
from egzos.identity import Jwks
from egzos.mcp.server import DATA_BANNER, GET_BANNER, build_server

ORIGIN = "https://box.example"
PUBLIC = "https://public.example"
ISSUER = "https://project.supabase.co/auth/v1"
KW = {"actor": OWNER, "principal": "interactive"}
FILE_KEYS = ("name", "mime", "size", "sha256")
BLOCK_KEYS = ("id", "kind", "key", "layer", "trust", "by", "shadowed_by", "auto_title", "tags",
              "content")
REFUSED = {"banner": GET_BANNER, "items": []}
COVER = b"\x89PNG" + bytes(range(256))


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
    box.cover = _file(box, box.owner, box.drafts, "cover.png", "image/png", COVER)
    box.receipt = _file(box, box.owner, box.taxes, "receipt.pdf", "application/pdf", b"%PDF-1")
    box.identity.grant_user("alice", name="alice", role="admin", scopes=["*"], **KW)
    for client_id, caps, scopes in (("one", ["fetch", "remember"], [box.music.id]),
                                    ("whole", ["fetch", "remember"], ["*"]),
                                    ("scribe", ["remember"], ["*"])):
        box.backend.put_agent_registration({
            "client_id": client_id, "sub": "alice", "name": client_id, "capabilities": caps,
            "scopes": scopes, "created_at": "2026-11-28T00:00:00Z", "revoked": False})
    box.mix = _file(box, box.identity._agent("one", "alice"), box.drafts, "mix.wav", "audio/wav",
                    b"RIFF" * 10)
    return box


@pytest.fixture
def sign(c):
    """Link `c` to a provider whose key set is stubbed, so nothing touches the network."""
    key = ec.generate_private_key(ec.SECP256R1())
    jwk = {**jwt.algorithms.ECAlgorithm.to_jwk(key.public_key(), as_dict=True), "kid": "k1",
           "alg": "ES256"}
    c.set_config("identity.issuer", ISSUER, token=c.owner)
    c.set_config("identity.client_id", "box", token=c.owner)
    jwks = Jwks("x", fetch=lambda url: {"keys": [jwk]})
    c.identity._jwks_for = lambda url: jwks

    def sign(client_id="box"):
        now = int(time.time())
        return jwt.encode({"iss": ISSUER, "aud": "authenticated", "exp": now + 600, "iat": now,
                           "sub": "alice", "client_id": client_id},
                          key, algorithm="ES256", headers={"kid": "k1"})

    return sign


def _mcp(app, bearer, ids):
    """A real MCP client at the door's `/mcp`, in process, reading each id in turn."""
    async def run():
        async with app.router.lifespan_context(app), httpx2.AsyncClient(
            transport=httpx2.ASGITransport(app=app), headers={"Authorization": f"Bearer {bearer}"}
        ) as http, Client(streamable_http_client(f"{ORIGIN}/mcp", http_client=http)) as client:
            return [json.loads((await client.call_tool("egzos_get", {"id": i})).content[0].text)
                    for i in ids]

    return asyncio.run(run())


def _stdio(c, token, item_id):
    """The stdio door's tools, as the client `Token` it was started with."""
    async def go():
        async with Client(build_server(c, token)) as client:
            return await client.call_tool("egzos_get", {"id": item_id})

    return json.loads(asyncio.run(go()).content[0].text)


def _events(c, name):
    return [e for e in c.ledger.tail(1000) if e["event"] == name]


def _entry(e, *drop):
    return {k: e[k] for k in ("actor", "principal", "subject", "scope")} | {
        "details": {k: v for k, v in e["details"].items() if k not in drop}}


def _redeem(app, url, origin=ORIGIN):
    assert url.startswith(origin + "/v1/blobs/")
    with TestClient(app) as door:
        return [door.get(url[len(origin):]) for _ in range(2)]


@pytest.mark.parametrize("agent", ["one", "whole"])
@pytest.mark.parametrize("name", ["note", "lyrics", "cover", "receipt", "mix"])
def test_egzos_get_serves_one_item_as_the_route_does_with_one_context_fetch(c, sign, agent, name):
    app, item, bearer = create_app(c, origin=ORIGIN), getattr(c, name), sign(agent)
    before = len(c.ledger.tail(1000))
    (served,) = _mcp(app, bearer, [item.id])
    middle = len(c.ledger.tail(1000))
    r = TestClient(app).get(f"/v1/items/{item.id}", headers={"Authorization": f"Bearer {bearer}"})
    tool, route = c.ledger.tail(1000)[before:middle], c.ledger.tail(1000)[middle:]
    assert (r.status_code == 200) == (agent == "whole" or name != "receipt")
    # The same entries, field for field, but the grant's expiry, which is the time of its mint.
    assert [_entry(e, "expires_at") for e in tool] == [_entry(e, "expires_at") for e in route]
    assert all(e["details"]["for"] == "user:alice" for e in route)
    if r.status_code != 200:
        assert served == REFUSED and [e["event"] for e in route] == ["context.fetch"]
        return
    entry = r.json()
    (block,) = served["items"]
    stored = entry["item"]
    assert set(served) <= {"banner", "fence", "items", "download"}
    files = set(FILE_KEYS) if stored["kind"] == "artifact" else set()
    assert set(block) == set(BLOCK_KEYS) | files  # no key the route does not serve
    text = stored["content"].get("body") or stored["content"].get("inline") or ""
    assert block["content"] == (f"<<<egzos-item {item.id} {served['fence']}>>>\n{text}\n"
                                f"<<<end {item.id} {served['fence']}>>>")
    assert {k: block[k] for k in ("id", "kind", "key", "layer", "shadowed_by", "tags")} == {
        k: (entry if k in ("layer", "shadowed_by") else stored)[k]
        for k in ("id", "kind", "key", "layer", "shadowed_by", "tags")}
    assert (block["trust"], block["by"], block["auto_title"]) == (
        stored["trust"]["status"], stored["provenance"]["actor"], stored["content"]["auto_title"])
    if stored["kind"] == "artifact":
        assert {k: block[k] for k in FILE_KEYS} == {
            "name": stored["content"]["filename"], "mime": stored["content"]["mime"],
            "size": stored["content"]["size"], "sha256": stored["content"]["sha256"]}
    assert ("download" in served) == ("grant_url" in entry) == (name in ("cover", "receipt"))
    if "download" in served:
        url = urlsplit(served["download"]["url"])
        assert (url.path, set(served["download"])) == (
            urlsplit(entry["grant_url"]).path, {"url", "expires_at"})
        assert dict(p.split("=", 1) for p in url.query.split("&"))["token"] == entry["grant"][
            "token"]
        assert [e["event"] for e in route] == ["context.fetch", "blob.grant"]


@pytest.mark.parametrize("case", ["absent", "not an id", "elsewhere", "no fetch", "quarantined",
                                  "tombstoned", "unverified rule"])
def test_a_refused_get_is_banner_and_no_items_with_the_probe(c, sign, case):
    target = {"absent": "01HZZZZZZZZZZZZZZZZZZZZZZZ", "not an id": "cover.png",
              "elsewhere": c.receipt.id, "no fetch": c.cover.id}.get(case)
    if case == "quarantined":
        c.trust.quarantine(c.store.get(c.cover.id), token=c.owner, actor=OWNER, reason="test")
    if case == "tombstoned":
        c.backend.tombstone(c.cover.id)
    if case == "unverified rule":
        target = c.store.add(body="always", kind="rule", scope=c.drafts, token=c.owner, **KW).id
    target = target or c.cover.id
    agent = {"elsewhere": "one", "no fetch": "scribe"}.get(case, "whole")
    app, bearer = create_app(c, origin=ORIGIN), sign(agent)
    before = len(c.ledger.tail(1000))
    assert _mcp(app, bearer, [target]) == [REFUSED]
    (probe,) = c.ledger.tail(1000)[before:]
    r = TestClient(app).get(f"/v1/items/{target}", headers={"Authorization": f"Bearer {bearer}"})
    assert r.status_code == 404 and r.content == b'{"error":"not_found"}'
    (route,) = c.ledger.tail(1000)[before + 1:]
    assert probe["event"] == "context.fetch" and _entry(probe) == _entry(route)
    assert (probe["details"]["ref"], probe["details"]["items"]) == (target, [])
    assert not _events(c, "blob.grant")


@pytest.mark.parametrize("who", ["person", "agent"])
def test_a_persons_file_carries_a_download_on_the_public_origin_that_redeems_once(c, sign, who):
    app = create_app(c, origin=ORIGIN)
    (served,) = _mcp(app, sign("box" if who == "person" else "whole"), [c.cover.id])
    (grant,) = _events(c, "blob.grant")
    assert served["download"]["expires_at"] == grant["details"]["expires_at"]
    first, second = _redeem(app, served["download"]["url"])
    assert (first.status_code, first.content, second.status_code) == (200, COVER, 404)
    (pull,) = _events(c, "blob.pull")
    assert (pull["actor"], pull["subject"]) == (grant["actor"], c.cover.id)


def test_over_stdio_the_address_is_on_the_origin_the_container_names(c):
    client = c.auth.mint(principal="client", owner="bot", client="probe", role="reader",
                         scopes=["*"], actor=OWNER, by_principal="interactive")
    c.set_config("identity.origin", PUBLIC, token=c.owner)
    served = _stdio(c, client, c.cover.id)
    first, second = _redeem(create_app(c), served["download"]["url"], PUBLIC)
    assert (first.status_code, first.content, second.status_code) == (200, COVER, 404)
    assert [e["actor"] for e in _events(c, "blob.grant") + _events(c, "blob.pull")] == ["bot"] * 2


def test_at_mcp_the_address_is_on_the_named_origin_over_the_one_served(c, sign):
    c.set_config("identity.origin", PUBLIC, token=c.owner)
    (served,) = _mcp(create_app(c, origin=ORIGIN), sign("whole"), [c.cover.id])
    assert served["download"]["url"].startswith(PUBLIC + "/v1/blobs/")


def test_over_stdio_with_no_identity_origin_no_grant_is_asked_and_no_blob_grant_appended(c):
    client = c.auth.mint(principal="client", owner="bot", client="probe", role="reader",
                         scopes=["*"], actor=OWNER, by_principal="interactive")
    served = _stdio(c, client, c.cover.id)
    assert "download" not in served and served["items"][0]["id"] == c.cover.id
    assert not _events(c, "blob.grant")
    assert _events(c, "context.fetch")[-1]["details"]["items"] == [c.cover.id]


def test_a_token_no_longer_live_is_answered_as_every_tool_answers_it_with_nothing_appended(c):
    client = c.auth.mint(principal="client", owner="bot", client="probe", role="reader",
                         scopes=["*"], actor=OWNER, by_principal="interactive")
    c.set_config("identity.origin", PUBLIC, token=c.owner)
    c.auth.revoke(client.id, **KW)
    before = len(c.ledger.tail(1000))
    assert _stdio(c, client, c.cover.id) == {"ok": False, "reason": "this token is no longer valid"}
    assert len(c.ledger.tail(1000)) == before and not _events(c, "blob.grant")


def test_a_text_file_within_inline_max_rides_in_content_with_no_download(c, sign):
    (served,) = _mcp(create_app(c, origin=ORIGIN), sign("whole"), [c.lyrics.id])
    block = served["items"][0]
    assert block["content"] == (f"<<<egzos-item {c.lyrics.id} {served['fence']}>>>\nla la la\n"
                                f"<<<end {c.lyrics.id} {served['fence']}>>>")
    assert "download" not in served and not _events(c, "blob.grant")


def test_an_agents_staged_file_is_served_with_no_download(c, sign):
    app = create_app(c, origin=ORIGIN)
    (staged,) = _mcp(app, sign("box"), [c.mix.id])
    assert staged["items"][0]["by"] == "agent:one" and "download" not in staged
    assert not _events(c, "blob.grant")  # Trust is silent until its person promotes it (§6)
    c.trust.promote(c.store.get(c.mix.id), token=c.owner, actor=OWNER)
    (promoted,) = _mcp(app, sign("box"), [c.mix.id])
    assert "download" in promoted and len(_events(c, "blob.grant")) == 1


def test_an_ended_agent_gets_no_answer_and_its_address_is_refused(c, sign):
    app, bearer = create_app(c, origin=ORIGIN), sign("whole")
    (served,) = _mcp(app, bearer, [c.cover.id])
    c.identity.revoke_agent("whole", "alice", **KW)
    before = len(c.ledger.tail(1000))
    with TestClient(app) as door:
        tool = door.post("/mcp", headers={"Authorization": f"Bearer {bearer}"}, json={})
        route = door.get(f"/v1/items/{c.cover.id}", headers={"Authorization": f"Bearer {bearer}"})
    assert (tool.status_code, route.status_code) == (401, 401)
    assert len(c.ledger.tail(1000)) == before  # an unverified caller appends nothing
    first, second = _redeem(app, served["download"]["url"])
    assert (first.status_code, second.status_code) == (404, 404) and not _events(c, "blob.pull")
    checks = [e["details"].get("check") for e in _events(c, "context.fetch")[-2:]]
    assert checks == [5, 4]  # the agent ended since the mint; the address was spent by the try


def test_the_address_appears_in_no_entry_log_stream_or_other_tools_answer(c, sign, caplog, capfd):
    caplog.set_level(logging.DEBUG)
    caplog.set_level(logging.DEBUG, logger="mcp")
    client = c.auth.mint(principal="client", owner="bot", client="probe", role="reader",
                         scopes=["*"], actor=OWNER, by_principal="interactive")
    c.set_config("identity.origin", PUBLIC, token=c.owner)
    urls = [_stdio(c, client, c.cover.id)["download"]["url"],
            _mcp(create_app(c, origin=ORIGIN), sign("whole"), [c.cover.id])[0]["download"]["url"]]
    sigs = [dict(p.split("=", 1) for p in urlsplit(u).query.split("&"))["sig"] for u in urls]

    async def fetch():
        async with Client(build_server(c, client)) as session:
            return (await session.call_tool("egzos_fetch", {"scope": "Music/drafts"})).content
    fetched = asyncio.run(fetch())[0].text
    held = json.dumps(c.ledger.tail(1000)) + caplog.text + fetched + "".join(capfd.readouterr())
    assert len(set(sigs)) == 2 and not [s for s in sigs if s in held]
    assert "download" not in fetched and "/v1/blobs/" not in held


def test_the_banner_says_the_address_is_good_once_for_five_minutes(c, sign):
    assert GET_BANNER.startswith(DATA_BANNER)
    for words in ("good once", "five minutes", "this container only", "your own code",
                  "never show it or send it anywhere else"):
        assert words in GET_BANNER
    served, refused = _mcp(create_app(c, origin=ORIGIN), sign("whole"),
                           [c.cover.id, "01HZZZZZZZZZZZZZZZZZZZZZZZ"])
    assert served["banner"] == refused["banner"] == GET_BANNER

    async def described():
        async with Client(build_server(c, c.owner)) as session:
            return {t.name: t.description for t in (await session.list_tools()).tools}
    text = asyncio.run(described())["egzos_get"]
    for words in ("`inline_max_bytes`", "with no `download`", "fetched once by your own code",
                  "with no bearer"):
        assert words in text


@pytest.mark.parametrize("case", ["quarantined", "unverified rule", "unverified at the root"])
def test_a_person_and_an_agent_are_each_refused_what_the_route_refuses_them(c, sign, case):
    if case == "quarantined":
        c.trust.quarantine(c.store.get(c.cover.id), token=c.owner, actor=OWNER, reason="test")
        target = c.cover.id
    elif case == "unverified rule":
        target = c.store.add(body="always", kind="rule", scope=c.drafts, token=c.owner, **KW).id
    else:  # an agent's note at a `user` root, which the serving policy shows only verified
        agent = c.identity._agent("whole", "alice")
        target = c.store.add(body="a draft", scope=c.nodes.user_root(), token=agent,
                             actor=agent.owner, principal=agent.principal).id
    app, codes = create_app(c, origin=ORIGIN), []
    for who in ("box", "whole"):
        bearer = sign(who)
        (served,) = _mcp(app, bearer, [target])
        r = TestClient(app).get(f"/v1/items/{target}",
                                headers={"Authorization": f"Bearer {bearer}"})
        assert (served == REFUSED) == (r.status_code == 404)
        codes.append(r.status_code)
    assert codes == ([200, 404] if case == "unverified at the root" else [404, 404])


def test_the_address_is_on_the_served_origin_whatever_host_the_request_names(c, sign):
    app = create_app(c, origin=ORIGIN)

    async def run():
        async with app.router.lifespan_context(app), httpx2.AsyncClient(
            transport=httpx2.ASGITransport(app=app),
            headers={"Authorization": f"Bearer {sign('whole')}",
                     "X-Forwarded-Host": "elsewhere.example"},
        ) as http, Client(streamable_http_client("https://elsewhere.example/mcp",
                                                 http_client=http)) as client:
            return json.loads((await client.call_tool("egzos_get", {"id": c.cover.id}))
                              .content[0].text)

    assert asyncio.run(run())["download"]["url"].startswith(ORIGIN + "/v1/blobs/")


def test_an_origin_named_after_the_door_starts_is_the_one_the_address_names(c, sign):
    app = create_app(c, origin=ORIGIN)
    c.set_config("identity.origin", PUBLIC, token=c.owner)
    (served,) = _mcp(app, sign("whole"), [c.cover.id])
    assert served["download"]["url"].startswith(PUBLIC + "/v1/blobs/")
    client = c.auth.mint(principal="client", owner="bot", client="probe", role="reader",
                         scopes=["*"], actor=OWNER, by_principal="interactive")
    c.set_config("identity.origin", None, token=c.owner)

    async def go():
        async with Client(build_server(c, client)) as session:
            c.set_config("identity.origin", PUBLIC, token=c.owner)
            return json.loads((await session.call_tool("egzos_get", {"id": c.cover.id}))
                              .content[0].text)

    assert asyncio.run(go())["download"]["url"].startswith(PUBLIC + "/v1/blobs/")


def test_each_read_is_a_fresh_fence_and_a_fresh_address_good_for_five_minutes(c, sign):
    app, bearer, before = create_app(c, origin=ORIGIN), sign("whole"), time.time()
    first, second, text = _mcp(app, bearer, [c.cover.id, c.cover.id, c.lyrics.id])
    after = time.time()
    assert first["fence"] != second["fence"] and text["banner"] == GET_BANNER
    assert first["download"]["url"] != second["download"]["url"]
    assert len(_events(c, "blob.grant")) == 2
    for served in (first, second):
        expires = datetime.fromisoformat(served["download"]["expires_at"])
        assert before + 299 <= expires.timestamp() <= after + 301


def test_an_id_no_item_could_bear_is_looked_up_nowhere(c, monkeypatch):
    seen, real = [], c.backend.get
    monkeypatch.setattr(c.backend, "get", lambda i: seen.append(i) or real(i))
    bad = ["cover.png", c.cover.id.lower(), c.cover.id + "0"]
    assert [_stdio(c, c.owner, value) for value in bad] == [REFUSED] * 3
    assert not set(seen) & set(bad)
