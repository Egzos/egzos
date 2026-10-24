# Copyright 2026 Ali Sasanian
# SPDX-License-Identifier: LicenseRef-PolyForm-Strict-1.0.0
"""MCP over Streamable HTTP at the door's `/mcp` (identity.md §7): one `401`, the metadata, and the
stdio tools running as the bearer the door verified, an agent within its intersected grant."""

from __future__ import annotations

import asyncio
import json
import time

import httpx2
import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import ec
from fastapi.testclient import TestClient
from mcp import Client
from mcp.client.streamable_http import streamable_http_client

from egzos.api import bound_origin, serve_http
from egzos.api.app import BODY_MAX_BYTES, Door, create_app
from egzos.api.throttle import RATE, WINDOW_SECONDS, Throttle
from egzos.container import OWNER, Container
from egzos.identity import Jwks
from egzos.mcp.server import DATA_BANNER

ORIGIN = "https://box.example"
METADATA = "/.well-known/oauth-protected-resource"
CHALLENGE = f'Bearer resource_metadata="{ORIGIN}{METADATA}"'
ISSUER = "https://project.supabase.co/auth/v1"
UNAUTHORIZED = b'{"error":"unauthorized"}'
NOT_FOUND = b'{"error":"not_found"}'
KW = {"actor": OWNER, "principal": "interactive"}
H = {"Accept": "application/json, text/event-stream", "Content-Type": "application/json"}
INIT = {"jsonrpc": "2.0", "id": 1, "method": "initialize",
        "params": {"protocolVersion": "2025-06-18", "capabilities": {},
                   "clientInfo": {"name": "probe", "version": "1"}}}


@pytest.fixture
def c(tmp_path):
    box = Container(tmp_path)
    box.owner = box.init()
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

    def sign(sub, client_id="box", **claims):
        now = int(time.time())
        return jwt.encode({"iss": ISSUER, "aud": "authenticated", "exp": now + 600, "iat": now,
                           "sub": sub, "client_id": client_id, **claims},
                          key, algorithm="ES256", headers={"kid": "k1"})

    return sign


def _bearer(value) -> dict[str, str]:
    return {"Authorization": f"Bearer {value}"}


def _events(c, name):
    return [e for e in c.ledger.tail(1000) if e["event"] == name]


def _agent(c, client_id, capabilities, scopes):
    c.backend.put_agent_registration({
        "client_id": client_id, "sub": "alice", "name": "an agent", "capabilities": capabilities,
        "scopes": scopes, "created_at": "2026-10-23T00:00:00Z", "revoked": False})


def _session(c, bearer, calls, *, mode="legacy"):
    """A real MCP client at the door, in process: it connects, lists the tools and makes each
    call. `legacy` is the initialize handshake; `auto` negotiates 2026-07-28's single exchange."""
    app = create_app(c, origin=ORIGIN)

    async def run():
        async with app.router.lifespan_context(app), httpx2.AsyncClient(
            transport=httpx2.ASGITransport(app=app), headers=_bearer(bearer)
        ) as http, Client(streamable_http_client(f"{ORIGIN}/mcp", http_client=http),
                          mode=mode) as client:
            names = sorted(t.name for t in (await client.list_tools()).tools)
            results = [await client.call_tool(name, args) for name, args in calls]
            return names, [json.loads(r.content[0].text) for r in results]

    return asyncio.run(run())


# -- identity.md §7 and §3: one unauthenticated answer ---------------------------------------------
def test_every_unauthenticated_mcp_request_is_one_answer(c, sign):
    c.identity.grant_user("alice", name="alice", role="contributor", scopes=["*"], **KW)
    past = int(time.time()) - 3600
    cases = [{}, _bearer("garbage"), _bearer(sign("alice", exp=past, iat=past - 600)),
             _bearer(sign("alice", iss="https://other.supabase.co/auth/v1")),
             _bearer(sign("alice", client_id="another-box")), _bearer(sign("never-granted"))]
    before = len(c.ledger.tail(1000))
    with TestClient(create_app(c, origin=ORIGIN)) as door:
        answers = [door.post("/mcp", headers={**H, **h}, json=INIT) for h in cases]
        ok = door.post("/mcp", headers={**H, **_bearer(sign("alice"))}, json=INIT)
        plain = door.get("/v1/fetch")
    shapes = [(r.status_code, r.content, sorted(r.headers.items())) for r in answers]
    assert shapes == [shapes[0]] * len(cases) and shapes[0][:2] == (401, UNAUTHORIZED)
    assert answers[0].headers["www-authenticate"] == CHALLENGE
    assert answers[0].headers["cache-control"] == "no-store"
    assert ok.status_code == 200  # the same request, with a token that passes every check
    assert plain.headers["www-authenticate"] == "Bearer"  # the parameter is /mcp's (rest.md §2)
    assert len(c.ledger.tail(1000)) == before  # an unverified caller appends nothing


def test_the_metadata_is_the_same_for_every_caller(c, sign):
    door = TestClient(create_app(c, origin=ORIGIN))
    want = (b'{"resource":"https://box.example",'
            b'"authorization_servers":["https://project.supabase.co/auth/v1"]}')
    answers = [door.get(METADATA, headers=h) for h in ({}, _bearer("garbage"), _bearer(sign("x")))]
    assert {(r.status_code, r.content) for r in answers} == {(200, want)}
    assert answers[0].headers["cache-control"] == "no-store"
    assert door.post(METADATA).content == NOT_FOUND


def test_serve_publishes_the_origin_it_binds(c, monkeypatch):
    assert bound_origin("box.example", 443, tls=True) == "https://box.example"
    assert bound_origin("::1", 7426, tls=False) == "http://[::1]:7426"
    served = {}
    monkeypatch.setattr("uvicorn.run", lambda app, **kw: served.update(app=app))
    serve_http(c, host="127.0.0.1", port=8123)
    r = TestClient(served["app"]).get(METADATA)
    # no provider linked: no authorization server to name (identity.md §1), so no key (§7)
    assert r.content == b'{"resource":"http://127.0.0.1:8123"}'


def test_the_public_origin_names_the_resource_and_the_challenge(c, sign):
    """identity.md §2: behind a proxy the owner names the origin clients reach, read per request,
    so a change reaches a running door; unset, the bound origin is back."""
    with TestClient(create_app(c, origin="http://127.0.0.1:7426")) as door:
        c.set_config("identity.origin", "https://public.example", token=c.owner)
        doc = door.get(METADATA).json()
        challenge = door.post("/mcp", headers=H, json=INIT).headers["www-authenticate"]
        c.set_config("identity.origin", None, token=c.owner)
        bound = door.get(METADATA).json()
    assert doc == {"resource": "https://public.example", "authorization_servers": [ISSUER]}
    assert challenge == f'Bearer resource_metadata="https://public.example{METADATA}"'
    assert bound["resource"] == "http://127.0.0.1:7426"


# -- the tools, as the verified caller -------------------------------------------------------------
def test_an_agent_reaches_only_what_its_registration_and_its_user_both_cover(c, sign):
    a, b = (c.nodes.create("project", n, c.nodes.user_root(), token=c.owner, **KW) for n in "ab")
    mine = c.store.add(body="in a", scope=a, token=c.owner, **KW)
    c.store.add(body="in b", scope=b, token=c.owner, **KW)
    c.identity.grant_user("alice", name="alice", role="reader", scopes=[a.id], **KW)
    _agent(c, "agent-1", ["fetch", "remember"], ["*"])  # wider than alice; she bounds it
    names, (seen, hidden, absent, wrote) = _session(c, sign("alice", "agent-1"), [
        ("egzos_fetch", {"scope": a.id}), ("egzos_fetch", {"scope": b.id}),
        ("egzos_fetch", {"scope": "01HZZZZZZZZZZZZZZZZZZZZZZZ"}),
        ("egzos_remember", {"text": "x", "scope": a.id})])
    assert names == ["egzos_fetch", "egzos_inbox", "egzos_remember"]
    assert [i["id"] for i in seen["items"]] == [mine.id]
    hidden.pop("scope"), absent.pop("scope")  # each echoes the caller's own input, nothing more
    assert hidden == absent and hidden["chain"] == hidden["items"] == []
    assert wrote["ok"] is False  # alice may not write here, so neither may her agent
    reads = _events(c, "context.fetch")  # one per fetch, and one per refusal (rest.md §4)
    assert [e["details"]["items"] for e in reads] == [[mine.id], [], [], []]
    assert {(e["actor"], e["principal"], e["details"]["for"]) for e in reads} == {
        ("agent:agent-1", "client", "user:alice")}
    keep = ("event", "actor", "principal", "subject", "scope")
    hidden_read, absent_read = ([e[k] for k in keep] + [{**e["details"], "ref": "-"}]
                                for e in reads[1:3])
    assert hidden_read == absent_read


def test_a_caller_without_fetch_gets_the_absent_answer_wherever_it_asks(c, sign):
    c.identity.grant_user("alice", name="alice", role="contributor", scopes=["*"], **KW)
    _agent(c, "scribe", ["remember"], ["*"])  # covers everything, may read nothing
    a, b = (c.nodes.create("project", n, c.nodes.user_root(), token=c.owner, **KW) for n in "ab")
    for parent in (a, b):
        c.nodes.create("thread", "same", parent, token=c.owner, **KW)
    c.store.add(body="already here", token=c.owner, **KW)
    refs = [a.id, "project:a", "thread:same", "01HZZZZZZZZZZZZZZZZZZZZZZZ", None]
    _, out = _session(c, sign("alice", "scribe"), [
        ("egzos_remember", {"text": "noted"}), ("egzos_remember", {"text": "x", "scope": a.id}),
        *(("egzos_remember", {"text": "x", "scope": r}) for r in refs[2:4]),
        *(("egzos_remember", {"text": "x", "kind": "zzz", "scope": r}) for r in refs[:4]),
        ("egzos_inbox", {}),
        *(("egzos_fetch", {"scope": r} if r else {}) for r in refs)], mode="auto")
    (kept, placed, ambiguous, absent), odd, (inbox, *fetched) = out[:4], out[4:8], out[8:]
    assert kept["ok"] is True and kept["status"] == "unverified"
    # rest.md §3: paths and matches go only to a caller holding `fetch`: this one hears its own ref
    assert (placed["ok"], placed["scope"], kept["scope"]) == (True, a.id, None)
    assert ambiguous == absent == {"ok": False, "reason": "scope not found"}
    assert odd == [{"ok": False, "reason": "unknown kind 'zzz'"}] * 4  # the request, first
    assert inbox["items"] == []
    assert [f.pop("scope") for f in fetched] == refs  # each echoes the caller's own input
    # covered id, covered tail, ambiguous tail, absent id, default: no fence, no matches named
    assert fetched == [{"banner": DATA_BANNER, "chain": [], "items": []}] * len(refs)
    reads = _events(c, "context.fetch")
    assert len(reads) == 3 + len(refs)  # the two refused writes', the inbox's, one per fetch
    assert {(e["actor"], e["details"]["for"]) for e in reads} == {("agent:scribe", "user:alice")}
    added = _events(c, "item.add")[-1]
    assert (added["actor"], added["details"]["for"]) == ("agent:scribe", "user:alice")
    # as at `POST /v1/items` (rest.md §3): the capability first, one answer for every ref
    c.identity.grant_user("bob", name="bob", capabilities=["organize"], scopes=["*"], **KW)
    _, refused = _session(c, sign("bob"), [
        ("egzos_remember", {"text": "x", "scope": r}) for r in refs[:4]])
    assert refused == [{"ok": False, "reason": "token lacks `remember`"}] * 4
    assert [e["actor"] for e in _events(c, "context.fetch")[len(reads):]] == ["user:bob"] * 4


def test_a_token_that_covers_nothing_gets_the_absent_answer(c):
    t = c.auth.mint(principal="client", owner=OWNER, client="probe", role="contributor",
                    scopes=[], actor=OWNER, by_principal="interactive")
    _, (fetched, kept) = _session(c, t.secret, [  # the resolver refuses one, the store the other
        ("egzos_fetch", {}), ("egzos_remember", {"text": "x"})])
    assert fetched == {"banner": DATA_BANNER, "scope": None, "chain": [], "items": []}
    assert kept == {"ok": False, "reason": "scope not found"} and not _events(c, "item.add")
    assert len(_events(c, "context.fetch")) == 2  # each refusal is a read


def test_a_persons_token_works_as_interactive(c, sign):
    c.identity.grant_user("alice", name="alice", role="contributor", scopes=["*"], **KW)
    _, (fetched,) = _session(c, sign("alice"), [("egzos_fetch", {})])
    assert fetched["chain"]
    entry = _events(c, "context.fetch")[-1]
    assert (entry["actor"], entry["principal"]) == ("user:alice", "interactive")
    assert "for" not in entry["details"]


# -- stateless: no session to steal, nothing but POST ----------------------------------------------
def test_no_session_is_issued_and_only_post_is_declared(c):
    nobody = c.auth.mint(principal="client", owner=OWNER, client="probe", role="reader", scopes=[],
                         actor=OWNER, by_principal="interactive")
    h = {**H, **_bearer(c.owner.secret)}
    with TestClient(create_app(c, origin=ORIGIN)) as door:
        r = door.post("/mcp", headers=h, json=INIT)
        assert r.status_code == 200 and "mcp-session-id" not in r.headers
        assert r.headers["cache-control"] == "no-store"
        # identity.md §7: no stream to open, no session to end: the transport's 405, the same for
        # every verified caller; an unverified one meets the 401 first
        for method in ("GET", "DELETE"):
            owner, other = (door.request(method, "/mcp", headers={**H, **_bearer(t.secret)})
                            for t in (c.owner, nobody))
            assert (owner.status_code, owner.content) == (405, b'{"error":"method_not_allowed"}')
            assert sorted(owner.headers.items()) == sorted(other.headers.items())
            assert (owner.headers["allow"], owner.headers["content-type"]) == (
                "POST", "application/json")
            assert owner.headers["cache-control"] == "no-store"
            assert owner.headers["x-content-type-options"] == "nosniff"
            unverified = door.request(method, "/mcp", headers=H)
            assert (unverified.status_code, unverified.headers["www-authenticate"]) == (
                401, CHALLENGE)
        for method in ("PUT", "PATCH"):  # not the transport's: rest.md §3's refusal
            assert door.request(method, "/mcp", headers=h).content == NOT_FOUND, method
    # outside the door's lifespan there is no transport: it fails closed, with no detail
    r = TestClient(create_app(c)).post("/mcp", headers=h, json=INIT)
    assert (r.status_code, r.content) == (500, b'{"error":"internal"}')


def test_a_listen_is_answered_and_never_held_open(c):
    """2026-07-28's `subscriptions/listen` is not served: an answer, not a stream that outlives
    the one check of its caller. Raw ASGI, under a timeout, so a held stream fails, not hangs."""
    app = create_app(c, origin=ORIGIN)
    body = json.dumps({"jsonrpc": "2.0", "id": 7, "method": "subscriptions/listen", "params": {
        "notifications": {"toolsListChanged": True},
        "_meta": {f"io.modelcontextprotocol/{k}": v for k, v in (
            ("protocolVersion", "2026-07-28"), ("clientCapabilities", {}),
            ("clientInfo", {"name": "probe", "version": "1"}))}}}).encode()
    headers = {**H, **_bearer(c.owner.secret), "MCP-Protocol-Version": "2026-07-28",
               "Mcp-Method": "subscriptions/listen"}
    scope = {"type": "http", "asgi": {"version": "3.0"}, "http_version": "1.1", "method": "POST",
             "scheme": "https", "path": "/mcp", "raw_path": b"/mcp", "query_string": b"",
             "root_path": "", "client": ("127.0.0.1", 1), "server": ("box.example", 443),
             "headers": [(k.lower().encode(), v.encode()) for k, v in headers.items()]}
    pending, sent = [{"type": "http.request", "body": body}], []

    async def receive():
        return pending.pop() if pending else await asyncio.Event().wait()  # the client stays

    async def send(message):
        sent.append(message)

    async def run():
        async with app.router.lifespan_context(app):
            await asyncio.wait_for(app(scope, receive, send), 5)

    asyncio.run(run())
    start = next(m for m in sent if m["type"] == "http.response.start")
    assert dict(start["headers"])[b"content-type"] == b"application/json"
    answer = json.loads(b"".join(m["body"] for m in sent if m["type"] == "http.response.body"))
    assert answer["error"]["code"] == -32601  # method not found


def test_mcp_reads_no_larger_a_body_than_the_door(c):
    big = {"jsonrpc": "2.0", "id": 2, "method": "tools/call",
           "params": {"name": "egzos_remember", "arguments": {"text": "x" * BODY_MAX_BYTES}}}
    with TestClient(create_app(c, origin=ORIGIN)) as door:
        r = door.post("/mcp", headers={**H, **_bearer(c.owner.secret)}, json=big)
    assert r.status_code == 413 and not _events(c, "item.add")


def test_past_the_credential_the_transports_own_answers_are_its_own(c):
    """identity.md §7: once verified, a refused Accept, a body that is not JSON and one that does
    not parse are answered by the transport, on the request alone, the same for every caller; the
    same request unverified is the door's one 401."""
    nobody = c.auth.mint(principal="client", owner=OWNER, client="probe", role="reader", scopes=[],
                         actor=OWNER, by_principal="interactive")
    asked = [({"Accept": "text/plain", "Content-Type": "application/json"}, json.dumps(INIT)),
             ({**H, "Content-Type": "text/plain"}, json.dumps(INIT)), (H, "{")]
    with TestClient(create_app(c, origin=ORIGIN)) as door:
        answers = [[door.post("/mcp", headers={**h, **_bearer(t.secret)}, content=body)
                    for t in (c.owner, nobody)] for h, body in asked]
        unverified = [door.post("/mcp", headers=h, content=body) for h, body in asked]
    for owner, other in answers:  # byte for byte, whoever asks
        assert (owner.status_code, owner.content, sorted(owner.headers.items())) == (
            other.status_code, other.content, sorted(other.headers.items()))
    refused, untyped, broken = (owner for owner, _ in answers)
    assert refused.status_code == 406 and refused.json()["error"]["code"] == -32600
    assert refused.headers["cache-control"] == "no-store"
    assert untyped.status_code == 400 and "content-type" not in untyped.headers  # a bare 400
    assert broken.status_code == 400 and broken.json()["error"]["code"] == -32700  # parse error
    assert [(r.status_code, r.content) for r in unverified] == [(401, UNAUTHORIZED)] * 3


# -- identity.md §6: CORS at /mcp, exactly as at /v1/ ----------------------------------------------
def test_mcp_is_answered_cors_as_v1_is_its_preflight_included(c):
    pre = {"Origin": "https://egzos.io", "Access-Control-Request-Method": "POST"}
    with TestClient(create_app(c, origin=ORIGIN)) as door:
        mcp, v1 = door.options("/mcp", headers=pre), door.options("/v1/fetch", headers=pre)
        foreign = door.options("/mcp", headers={**pre, "Origin": "https://evil.example"})
        h = {**H, **_bearer(c.owner.secret), "Origin": pre["Origin"]}
        posted = door.post("/mcp", headers=h, json=INIT)
    assert mcp.status_code == v1.status_code == 204
    assert sorted(mcp.headers.items()) == sorted(v1.headers.items())
    assert (foreign.status_code, foreign.content) == (404, NOT_FOUND)
    assert "access-control-allow-origin" not in foreign.headers
    assert posted.status_code == 200
    assert posted.headers["access-control-allow-origin"] == "https://egzos.io"


# -- rest.md §2 item 7: one door, one throttle -----------------------------------------------------
def test_the_throttle_holds_mcp_with_its_own_401(c):
    now = [1_800_000_000.0]
    throttle = Throttle(c.backend, c.ledger, b"k" * 32, clock=lambda: now[0])
    pre = {"Origin": "https://egzos.io", "Access-Control-Request-Method": "POST"}
    with TestClient(create_app(c, door=Door(c, throttle), origin=ORIGIN)) as door:
        for _ in range(RATE.per_source + 1):  # public, the same for everyone: never counted
            assert door.get(METADATA).status_code == 200
            assert door.options("/mcp", headers=pre).status_code == 204
        live = door.post("/mcp", headers={**H, **_bearer(c.owner.secret)}, json=INIT)
        assert live.status_code == 200  # so nothing above filled a bucket
        for _ in range(RATE.per_source):
            door.post("/mcp", headers=H, json=INIT)
        held = door.post("/mcp", headers={**H, **_bearer(c.owner.secret)}, json=INIT)
        assert (held.status_code, held.content) == (401, UNAUTHORIZED)
        assert held.headers["www-authenticate"] == CHALLENGE
        held_v1 = door.get("/v1/fetch", headers=_bearer(c.owner.secret))
        assert (held_v1.status_code, held_v1.headers["www-authenticate"]) == (401, "Bearer")
        assert door.get(METADATA).status_code == 200  # served while held (rest.md §2 item 7)
        assert door.options("/mcp", headers=pre).status_code == 204
    now[0] += WINDOW_SECONDS
    throttle.close()
    (tally,) = _events(c, "rest.tally")
    assert tally["details"]["unauthorized"] == RATE.per_source
