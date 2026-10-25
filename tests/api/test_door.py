# Copyright 2026 Ali Sasanian
# SPDX-License-Identifier: LicenseRef-PolyForm-Strict-1.0.0
"""The REST door (rest.md §1–§4.1, identity.md §6): who gets in, the answers it gives, and CORS."""

from __future__ import annotations

import time

import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import ec
from fastapi.testclient import TestClient

from egzos.api import loopback, serve_http
from egzos.api.app import Door, create_app
from egzos.api.throttle import RATE, WINDOW_SECONDS, Throttle
from egzos.container import OWNER, Container
from egzos.identity import Jwks

NOT_FOUND = b'{"error":"not_found"}'
UNAUTHORIZED = b'{"error":"unauthorized"}'
ISSUER = "https://project.supabase.co/auth/v1"
EGZOS = "https://egzos.io"
KW = {"actor": OWNER, "principal": "interactive"}


@pytest.fixture
def c(tmp_path):
    box = Container(tmp_path)
    box.owner = box.init()
    return box


@pytest.fixture
def door(c):
    return TestClient(create_app(c))


def _auth(token) -> dict[str, str]:
    return {"Authorization": f"Bearer {token.secret if hasattr(token, 'secret') else token}"}


def _client(c, scopes=("*",), role="reader"):
    return c.auth.mint(principal="client", owner=OWNER, client="probe", role=role,
                       scopes=list(scopes), actor=OWNER, by_principal="interactive")


def _project(c, name, parent=None):
    return c.nodes.create("project", name, parent or c.nodes.user_root(), token=c.owner, **KW)


def _events(c, name):
    return [e for e in c.ledger.tail(1000) if e["event"] == name]


# -- §2: one unauthenticated answer ----------------------------------------------------------------
@pytest.mark.parametrize(
    "headers",
    [{}, {"Authorization": "Basic x"}, {"Authorization": "Bearer "},
     {"Authorization": "Bearer egz_nope"}, {"Authorization": "Bearer a.b.c"},
     {"Cookie": "session=x"}],
    ids=["none", "basic", "empty", "unknown", "jwt-shaped", "cookie-only"],
)
def test_every_unauthenticated_case_is_one_answer(door, headers):
    r = door.get("/v1/fetch", headers=headers)
    assert r.status_code == 401 and r.content == UNAUTHORIZED
    assert r.headers["www-authenticate"] == "Bearer"
    assert r.headers["cache-control"] == "no-store"
    assert r.headers["x-content-type-options"] == "nosniff"


def test_a_revoked_token_gets_the_same_answer(c, door):
    t = _client(c)
    assert door.get("/v1/fetch", headers=_auth(t)).status_code == 200
    c.auth.revoke(t.id, **KW)
    r = door.get("/v1/fetch", headers=_auth(t))
    assert r.status_code == 401 and r.content == UNAUTHORIZED


def test_a_token_in_the_query_string_is_never_read(c, door):
    r = door.get(f"/v1/fetch?access_token={c.owner.secret}")
    assert r.status_code == 401


def test_an_unauthenticated_request_appends_nothing(c, door):
    before = len(c.ledger.tail(1000))
    door.get("/v1/fetch")
    assert len(c.ledger.tail(1000)) == before


# -- §3: the one refusal, 400 and 409 --------------------------------------------------------------
def test_absent_and_uncovered_are_byte_identical(c, door):
    mine = _project(c, "mine")
    other = _project(c, "other")
    note = c.store.add(body="secret", scope=other, token=c.owner, **KW)
    t = _client(c, scopes=[mine.id])
    absent = door.get("/v1/items/01ABSENTABSENTABSENTABSENT", headers=_auth(t))
    hidden = door.get(f"/v1/items/{note.id}", headers=_auth(t))
    assert absent.status_code == hidden.status_code == 404
    assert absent.content == hidden.content == NOT_FOUND
    assert dict(absent.headers) == dict(hidden.headers)


def test_undeclared_paths_and_methods_are_the_refusal(c, door):
    for method, path in [("GET", "/v1/nope"), ("PATCH", "/v1/fetch"), ("PUT", "/v1/items/x"),
                         ("GET", "/elsewhere"), ("POST", "/v1/items/x/archive")]:
        r = door.request(method, path, headers=_auth(c.owner))
        assert (r.status_code, r.content) == (404, NOT_FOUND), (method, path)


def test_a_refusal_appends_a_read(c, door):
    t = _client(c, scopes=[_project(c, "mine").id])
    door.get("/v1/fetch?scope=user:self", headers=_auth(t))
    probe = _events(c, "context.fetch")[-1]
    assert probe["details"]["items"] == []


@pytest.mark.parametrize(
    "path", ["/v1/fetch?kind=nope", "/v1/fetch?bogus=1", "/v1/find?q=nope:x",
             "/v1/fetch?scope=a&scope=b"],
)
def test_a_malformed_request_is_400(c, door, path):
    r = door.get(path, headers=_auth(c.owner))
    assert r.status_code == 400 and r.content == b'{"error":"invalid_request"}'


def test_an_ambiguous_tail_names_only_what_the_token_covers(c, door):
    a, b = _project(c, "a"), _project(c, "b")
    for parent in (a, b):
        c.nodes.create("thread", "same", parent, token=c.owner, **KW)
    both = {"error": "ambiguous", "matches": sorted(["user:self/project:a/thread:same",
                                                     "user:self/project:b/thread:same"])}
    r = door.get("/v1/fetch?scope=thread:same", headers=_auth(c.owner))
    assert r.status_code == 409 and r.json() == both
    t = _client(c, scopes=[a.id])
    assert door.get("/v1/fetch?scope=thread:same", headers=_auth(t)).status_code == 200
    r = door.post("/v1/items", headers=_auth(c.owner), json={"body": "x", "scope": "thread:same"})
    assert (r.status_code, r.json()) == (409, both) and not _events(c, "item.add")


def test_an_ambiguous_tail_is_the_absent_answer_without_fetch(c, door, linked):
    """§3 (#294): the matches are named only to a principal that could list them, so a person
    who may write here but not read gets an ambiguous tail answered as an absent one."""
    c.identity.grant_user("scribe", name="scribe", capabilities=["remember"], scopes=["*"], **KW)
    for parent in (_project(c, "a"), _project(c, "b")):
        c.nodes.create("thread", "same", parent, token=c.owner, **KW)
    h = {"Authorization": f"Bearer {linked('scribe')}"}
    reads = len(_events(c, "context.fetch"))
    answers = {ref: [door.get(f"/v1/fetch?scope={ref}", headers=h),
                     door.get(f"/v1/scopes?under={ref}", headers=h),
                     door.post("/v1/items", headers=h, json={"body": "x", "scope": ref})]
               for ref in ("thread:same", "thread:none")}  # an ambiguous tail, an absent one
    shapes = {ref: [(r.status_code, r.content, sorted(r.headers.items())) for r in rs]
              for ref, rs in answers.items()}
    assert shapes["thread:same"] == shapes["thread:none"]
    assert {s[:2] for s in shapes["thread:same"]} == {(404, NOT_FOUND)}
    probes = _events(c, "context.fetch")[reads:]  # each refusal is a read (§4), naming the ref
    assert [e["details"]["ref"] for e in probes] == ["thread:same"] * 3 + ["thread:none"] * 3
    assert not _events(c, "item.add")
    ok = door.post("/v1/items", headers=h, json={"body": "x", "scope": "project:a/thread:same"})
    assert ok.status_code == 200  # named in full, the write lands


# -- §4: reads -------------------------------------------------------------------------------------
def test_fetch_carries_the_layering_and_no_trust_key(c, door):
    p = _project(c, "health")
    c.store.add(body="walk daily", scope=p, token=c.owner, **KW)
    r = door.get("/v1/fetch?scope=project:health", headers=_auth(c.owner))
    assert r.status_code == 200
    body = r.json()
    assert set(body) == {"scope", "chain", "items"}
    assert body["chain"][0]["path"] == "user:self/project:health"
    (entry,) = [e for e in body["items"] if e["item"]["content"].get("body") == "walk daily"]
    assert set(entry) == {"item", "layer", "layer_type", "shadowed_by"}
    assert entry["item"]["trust"]["status"] == "unverified"


def test_find_inbox_scopes_and_one_item(c, door):
    p = _project(c, "work")
    c.nodes.create("thread", "t1", p, token=c.owner, **KW)
    note = c.store.add(body="the plan", scope=p, token=c.owner, **KW)
    captured = c.store.add(body="loose thought", token=c.owner, **KW)
    h = _auth(c.owner)
    assert [e["item"]["id"] for e in door.get("/v1/find?q=plan", headers=h).json()["items"]] == [
        note.id
    ]
    inbox = door.get("/v1/inbox", headers=h).json()["items"]
    assert captured.id in {e["item"]["id"] for e in inbox}
    nodes = door.get("/v1/scopes?under=project:work", headers=h).json()["nodes"]
    assert [n["path"] for n in nodes] == ["user:self/project:work/thread:t1"]
    one = door.get(f"/v1/items/{note.id}", headers=h).json()
    assert one["item"]["id"] == note.id and one["layer"] == "user:self/project:work"


def test_an_unverified_rule_is_refused_outside_the_queue(c, door):
    rule = c.store.add(body="always X", kind="rule", token=c.owner, **KW)
    h = _auth(c.owner)
    assert door.get(f"/v1/items/{rule.id}", headers=h).content == NOT_FOUND
    assert rule.id in {i["id"] for i in door.get("/v1/pending", headers=h).json()["items"]}


def test_pending_is_the_interactive_principals(c, door):
    t = _client(c, role="admin")
    assert door.get("/v1/pending", headers=_auth(t)).content == NOT_FOUND
    body = door.get("/v1/pending", headers=_auth(c.owner)).json()
    assert set(body) == {"items", "proposals", "uploads", "staged"}


# -- §4: writes without a confirm ------------------------------------------------------------------
def test_a_write_lands_unverified_and_attributed(c, door):
    p = _project(c, "notes")
    r = door.post("/v1/items", headers=_auth(c.owner), json={"body": "hello", "scope": p.id})
    assert r.status_code == 200
    assert r.json()["item"]["trust"]["status"] == "unverified"
    assert _events(c, "item.add")[-1]["actor"] == OWNER


@pytest.mark.parametrize(
    "body",
    [{"body": ""}, {"body": "x", "kind": "artifact"}, {"body": "x", "kind": "nope"},
     {"body": "x", "extra": 1}, {"kind": "memory"}, {"body": "x", "tags": "t"}],
)
def test_a_malformed_write_is_400(c, door, body):
    assert door.post("/v1/items", headers=_auth(c.owner), json=body).status_code == 400


def test_a_write_to_an_uncovered_scope_is_the_refusal(c, door):
    other = _project(c, "other")
    t = _client(c, scopes=[_project(c, "mine").id], role="contributor")
    r = door.post("/v1/items", headers=_auth(t), json={"body": "x", "scope": other.id})
    assert r.content == NOT_FOUND


def test_creating_a_scope_above_the_floor_needs_admin(c, door):
    t = _client(c, role="contributor")
    ok = door.post("/v1/scopes", headers=_auth(t), json={"type": "project", "name": "p"})
    assert ok.status_code == 200 and ok.json()["node"]["path"] == "user:self/project:p"
    above = door.post("/v1/scopes", headers=_auth(t), json={"type": "org", "name": "o"})
    assert above.content == NOT_FOUND
    bad = door.post("/v1/scopes", headers=_auth(t), json={"type": "inbox", "name": "i"})
    assert bad.status_code == 400


# -- identity.md §6: CORS --------------------------------------------------------------------------
def test_an_allowed_origin_gets_the_same_cors_headers_on_every_answer(c, door):
    def cors(r):
        return {k: v for k, v in r.headers.items() if k.startswith("access-control") or k == "vary"}

    o = {"Origin": EGZOS}
    ok = door.get("/v1/fetch", headers={**o, **_auth(c.owner)})
    refused = door.get("/v1/nope", headers={**o, **_auth(c.owner)})
    unauth = door.get("/v1/fetch", headers=o)
    assert ok.status_code == 200 and refused.status_code == 404 and unauth.status_code == 401
    assert cors(ok) == cors(refused) == cors(unauth)
    assert cors(ok)["access-control-allow-origin"] == EGZOS
    assert "access-control-allow-credentials" not in cors(ok)


def test_preflight_answers_every_v1_path_for_an_allowed_origin_only(door):
    pre = {"Origin": EGZOS, "Access-Control-Request-Method": "GET"}
    declared = door.options("/v1/fetch", headers=pre)
    undeclared = door.options("/v1/no/such/route", headers=pre)
    assert declared.status_code == undeclared.status_code == 204
    assert declared.headers["access-control-allow-origin"] == EGZOS
    foreign = door.options("/v1/fetch", headers={**pre, "Origin": "https://evil.example"})
    assert foreign.status_code == 404 and "access-control-allow-origin" not in foreign.headers


def test_another_origin_gets_no_cors_header(c, door):
    r = door.get("/v1/fetch", headers={"Origin": "https://evil.example", **_auth(c.owner)})
    assert r.status_code == 200 and "access-control-allow-origin" not in r.headers


# -- §2 item 7: the throttle -----------------------------------------------------------------------
class Clock:
    def __init__(self):
        self.now = 1_800_000_000.0

    def __call__(self):
        return self.now


def _door_with_clock(c):
    clock = Clock()
    throttle = Throttle(c.backend, c.ledger, b"k" * 32, clock=clock)
    return TestClient(create_app(c, door=Door(c, throttle))), throttle, clock


def test_a_source_that_sweeps_is_held_and_its_live_token_too(c):
    client, _throttle, _clock = _door_with_clock(c)
    for _ in range(RATE.per_source):
        assert client.get("/v1/fetch").status_code == 401
    r = client.get("/v1/fetch", headers=_auth(c.owner))
    assert r.status_code == 401 and r.content == UNAUTHORIZED


def test_a_closed_window_appends_one_release_and_one_tally(c):
    client, throttle, clock = _door_with_clock(c)
    for _ in range(RATE.per_source + 2):
        client.get("/v1/fetch")
    assert not _events(c, "authz.release")
    clock.now += WINDOW_SECONDS
    throttle.close()
    throttle.close()  # idempotent: a window closes once
    (release,) = _events(c, "authz.release")
    (tally,) = _events(c, "rest.tally")
    assert release["principal"] == tally["principal"] == "none"
    assert release["actor"] == tally["actor"] == "rest"
    assert release["details"]["refused"] == 2 and release["details"]["surface"] == "rest"
    assert tally["details"]["unauthorized"] == RATE.per_source and tally["details"]["forged"] == 0
    assert "testclient" not in str(release) and "testclient" not in str(tally)
    # the held window is over: the owner's token works again
    assert client.get("/v1/fetch", headers=_auth(c.owner)).status_code == 200


def test_a_quiet_window_appends_nothing(c):
    client, throttle, clock = _door_with_clock(c)
    client.get("/v1/fetch", headers=_auth(c.owner))
    clock.now += WINDOW_SECONDS
    throttle.close()
    assert not _events(c, "authz.release") and not _events(c, "rest.tally")


# -- identity.md §3: a provider token at the door --------------------------------------------------
@pytest.fixture
def linked(c):
    key = ec.generate_private_key(ec.SECP256R1())
    jwk = {**jwt.algorithms.ECAlgorithm.to_jwk(key.public_key(), as_dict=True), "kid": "k1",
           "alg": "ES256"}
    c.set_config("identity.issuer", ISSUER, token=c.owner)
    c.set_config("identity.client_id", "box", token=c.owner)
    jwks = Jwks("x", fetch=lambda url: {"keys": [jwk]})
    c.identity._jwks_for = lambda url: jwks

    def sign(sub, client_id="box"):
        now = int(time.time())
        claims = {"iss": ISSUER, "aud": "authenticated", "exp": now + 600, "iat": now,
                  "sub": sub, "client_id": client_id}
        return jwt.encode(claims, key, algorithm="ES256", headers={"kid": "k1"})

    return sign


def test_a_granted_person_reads_and_is_named_on_the_chain(c, door, linked):
    c.identity.grant_user("alice", name="alice", role="contributor", scopes=["*"], **KW)
    r = door.get("/v1/fetch", headers={"Authorization": f"Bearer {linked('alice')}"})
    assert r.status_code == 200
    entry = _events(c, "context.fetch")[-1]
    assert (entry["actor"], entry["principal"]) == ("user:alice", "interactive")
    assert "for" not in entry["details"]


def test_an_ungranted_person_with_a_real_token_is_401(door, linked):
    r = door.get("/v1/fetch", headers={"Authorization": f"Bearer {linked('stranger')}"})
    assert r.status_code == 401 and r.content == UNAUTHORIZED


def test_an_agents_entries_name_who_it_acts_for(c, door, linked):
    c.identity.grant_user("alice", name="alice", role="contributor", scopes=["*"], **KW)
    c.backend.put_agent_registration({
        "client_id": "agent-1", "sub": "alice", "name": "an agent", "capabilities": ["fetch",
        "remember"], "scopes": ["*"], "created_at": "2026-10-23T00:00:00Z", "revoked": False})
    h = {"Authorization": f"Bearer {linked('alice', 'agent-1')}"}
    assert door.post("/v1/items", headers=h, json={"body": "from the agent"}).status_code == 200
    added = _events(c, "item.add")[-1]
    assert (added["actor"], added["principal"]) == ("agent:agent-1", "client")
    assert added["details"]["for"] == "user:alice"
    assert door.get("/v1/pending", headers=h).content == NOT_FOUND


# -- §1: TLS ---------------------------------------------------------------------------------------
def test_plain_http_is_for_a_loopback_socket_only(c):
    assert loopback("127.0.0.1") and loopback("::1") and loopback("localhost")
    assert not loopback("0.0.0.0") and not loopback("10.0.0.1")
    with pytest.raises(PermissionError):
        serve_http(c, host="0.0.0.0")
    with pytest.raises(ValueError):
        serve_http(c, host="0.0.0.0", tls_cert=c.home / "cert.pem")


# -- a6 on #288 ---------------------------------------------------------------------------------
def test_a_window_whose_entries_fail_is_closed_again_on_the_next_pass(c, monkeypatch):
    clock = Clock()
    throttle = Throttle(c.backend, c.ledger, b"k" * 32, clock=clock, atomic=c.backend.atomic)
    client = TestClient(create_app(c, door=Door(c, throttle)))
    client.get("/v1/fetch")
    clock.now += WINDOW_SECONDS
    real = c.ledger.append

    def broken(*args, **kwargs):
        raise RuntimeError("the chain cannot take an entry")

    monkeypatch.setattr(c.ledger, "append", broken)
    with pytest.raises(RuntimeError):
        throttle.close()
    monkeypatch.setattr(c.ledger, "append", real)
    throttle.close()
    assert len(_events(c, "rest.tally")) == 1


def test_an_oversized_body_is_refused_before_it_is_read(c, door):
    big = b'{"body":"' + b"x" * (300 * 1024) + b'"}'
    r = door.post("/v1/items", headers={**_auth(c.owner), "Content-Type": "application/json"},
                  content=big)
    assert r.status_code == 400


def test_a_token_that_may_not_write_never_sends_a_body(c, door):
    reader = _client(c, role="reader")
    r = door.post("/v1/items", headers=_auth(reader), json={"body": "x"})
    assert r.content == NOT_FOUND
