# Copyright 2026 Ali Sasanian
# SPDX-License-Identifier: LicenseRef-PolyForm-Strict-1.0.0
"""identity.md §7: MCP over Streamable HTTP at `/mcp`, behind the REST door's credential check."""

from __future__ import annotations

import json
import time

import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import ec
from fastapi.testclient import TestClient

from egzos.api.app import create_app
from egzos.container import OWNER, Container
from egzos.identity import Jwks

ISSUER = "https://project.supabase.co/auth/v1"
KW = {"actor": OWNER, "principal": "interactive"}
MCP = {"Accept": "application/json, text/event-stream", "Content-Type": "application/json"}


@pytest.fixture
def c(tmp_path):
    box = Container(tmp_path)
    box.owner = box.init()
    return box


@pytest.fixture
def door(c):
    with TestClient(create_app(c)) as client:  # the lifespan runs MCP's session manager
        yield client


@pytest.fixture
def sign(c):
    key = ec.generate_private_key(ec.SECP256R1())
    jwk = {**jwt.algorithms.ECAlgorithm.to_jwk(key.public_key(), as_dict=True), "kid": "k1",
           "alg": "ES256"}
    c.set_config("identity.issuer", ISSUER, token=c.owner)
    c.set_config("identity.client_id", "box", token=c.owner)
    jwks = Jwks("x", fetch=lambda url: {"keys": [jwk]})
    c.identity._jwks_for = lambda url: jwks

    def bearer(sub, client_id="box"):
        now = int(time.time())
        claims = {"iss": ISSUER, "aud": "authenticated", "exp": now + 600, "iat": now,
                  "sub": sub, "client_id": client_id}
        return f"Bearer {jwt.encode(claims, key, algorithm='ES256', headers={'kid': 'k1'})}"

    return bearer


def _call(door, authorization, tool, arguments):
    r = door.post("/mcp", headers={**MCP, "Authorization": authorization}, json={
        "jsonrpc": "2.0", "id": 1, "method": "tools/call",
        "params": {"name": tool, "arguments": arguments}})
    assert r.status_code == 200, r.content
    return json.loads(r.json()["result"]["content"][0]["text"])


def _events(c, name):
    return [e for e in c.ledger.tail(2000) if e["event"] == name]


def test_the_tools_are_served_over_http(c, door):
    agent = c.auth.mint(principal="client", owner=OWNER, client="bot", role="contributor",
                        scopes=["*"], actor=OWNER, by_principal="interactive")
    r = door.post("/mcp", headers={**MCP, "Authorization": f"Bearer {agent.secret}"},
                  json={"jsonrpc": "2.0", "id": 1, "method": "tools/list", "params": {}})
    names = {t["name"] for t in r.json()["result"]["tools"]}
    assert names == {"egzos_fetch", "egzos_remember", "egzos_inbox"}
    out = _call(door, f"Bearer {agent.secret}", "egzos_remember", {"text": "over http"})
    assert out["ok"] and out["status"] == "unverified"


def test_an_agent_signed_in_at_the_provider_acts_for_its_person(c, door, sign):
    c.identity.grant_user("alice", name="alice", role="contributor", scopes=["*"], **KW)
    c.backend.put_agent_registration({
        "client_id": "agent-1", "sub": "alice", "name": "an agent",
        "capabilities": ["fetch", "remember"], "scopes": ["*"],
        "created_at": "2026-10-23T00:00:00Z", "revoked": False})
    bearer = sign("alice", "agent-1")
    out = _call(door, bearer, "egzos_remember", {"text": "for alice"})
    added = _events(c, "item.add")[-1]
    assert out["ok"] and added["subject"] == out["id"]
    assert (added["actor"], added["principal"]) == ("agent:agent-1", "client")
    assert added["details"]["for"] == "user:alice"
    captured = _call(door, bearer, "egzos_inbox", {})
    assert out["id"] in [i["id"] for i in captured["items"]]
    assert _events(c, "context.fetch")[-1]["details"]["for"] == "user:alice"
    # Revoked between requests: the next one is not admitted at all.
    c.identity.revoke_agent("agent-1", "alice", **KW)
    r = door.post("/mcp", headers={**MCP, "Authorization": bearer}, json={
        "jsonrpc": "2.0", "id": 1, "method": "tools/list", "params": {}})
    assert r.status_code == 401


def test_two_callers_each_act_as_themselves(c, door):
    root = c.nodes.user_root()
    mine = c.nodes.create("project", "mine", root, token=c.owner, **KW)
    other = c.nodes.create("project", "other", root, token=c.owner, **KW)
    wide = c.auth.mint(principal="client", owner=OWNER, client="wide", role="contributor",
                       scopes=["*"], actor=OWNER, by_principal="interactive")
    narrow = c.auth.mint(principal="client", owner=OWNER, client="narrow", role="contributor",
                         scopes=[mine.id], actor=OWNER, by_principal="interactive")
    written = _call(door, f"Bearer {wide.secret}", "egzos_remember",
                    {"text": "wide only", "scope": other.id})
    assert written["ok"]
    assert written["id"] in [i["id"] for i in _call(
        door, f"Bearer {wide.secret}", "egzos_fetch", {"scope": other.id})["items"]]
    seen = _call(door, f"Bearer {narrow.secret}", "egzos_fetch", {"scope": other.id})
    assert seen["items"] == [] and seen["chain"] == []
    assert _events(c, "context.fetch")[-1]["details"]["client"] == "narrow"


def test_an_unauthenticated_request_names_the_resource_metadata(c, door, sign):
    answers = [door.post("/mcp", headers=MCP, json={}),
               door.post("/mcp", headers={**MCP, "Authorization": "Bearer nope"}, json={}),
               door.post("/mcp", headers={**MCP, "Authorization": sign("nobody")}, json={})]
    assert {(r.status_code, r.content, r.headers["www-authenticate"]) for r in answers} == {
        (401, b'{"error":"unauthorized"}',
         'Bearer resource_metadata="http://testserver/.well-known/oauth-protected-resource"')}
    # The REST routes keep the plain challenge.
    assert door.get("/v1/fetch").headers["www-authenticate"] == "Bearer"


def test_the_resource_metadata_names_the_provider(c, door, sign):
    r = door.get("/.well-known/oauth-protected-resource")
    assert r.status_code == 200 and r.headers["cache-control"] == "no-store"
    assert r.json() == {"resource": "http://testserver", "authorization_servers": [ISSUER],
                        "bearer_methods_supported": ["header"]}
