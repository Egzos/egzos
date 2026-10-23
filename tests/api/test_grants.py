# Copyright 2026 Ali Sasanian
# SPDX-License-Identifier: LicenseRef-PolyForm-Strict-1.0.0
"""rest.md §4.3 and identity.md §4-§5: the grant routes. Granting takes the confirm, and so does
ending someone else's grant, never your own; with the button, both need a fresh sign-in."""

from __future__ import annotations

import time

import jwt
import pytest
from authenticator import SoftAuthenticator
from cryptography.hazmat.primitives.asymmetric import ec
from fastapi.testclient import TestClient

from egzos.api.app import create_app
from egzos.container import OWNER, Container
from egzos.identity import Jwks

EGZOS = "https://egzos.io"
ISSUER = "https://project.supabase.co/auth/v1"
NOT_FOUND = b'{"error":"not_found"}'
KW = {"actor": OWNER, "principal": "interactive"}
DAVE = {"sub": "dave", "name": "Dave", "role": "reader", "scopes": ["*"]}


@pytest.fixture
def c(tmp_path):
    box = Container(tmp_path)
    box.owner = box.init()
    return box


@pytest.fixture
def door(c):
    return TestClient(create_app(c))


@pytest.fixture
def sign(c):
    """Provider sign-ins: alice and carol are admins over everything, bob a reader."""
    key = ec.generate_private_key(ec.SECP256R1())
    jwk = {**jwt.algorithms.ECAlgorithm.to_jwk(key.public_key(), as_dict=True), "kid": "k1",
           "alg": "ES256"}
    c.set_config("identity.issuer", ISSUER, token=c.owner)
    c.set_config("identity.client_id", "box", token=c.owner)
    jwks = Jwks("x", fetch=lambda url: {"keys": [jwk]})
    c.identity._jwks_for = lambda url: jwks
    for sub in ("alice", "carol"):
        c.identity.grant_user(sub, name=sub.title(), role="admin", scopes=["*"], **KW)
    c.identity.grant_user("bob", name="Bob", role="reader", scopes=["*"], **KW)

    def headers(sub="alice", signed_in_ago=30, client_id="box"):
        """`signed_in_ago=None` is a token with no `amr`: it says nothing of when."""
        now = int(time.time())
        claims = {"iss": ISSUER, "aud": "authenticated", "exp": now + 600, "iat": now,
                  "sub": sub, "client_id": client_id}
        if signed_in_ago is not None:
            claims["amr"] = [{"method": "otp", "timestamp": now - signed_in_ago}]
        value = jwt.encode(claims, key, algorithm="ES256", headers={"kid": "k1"})
        return {"Authorization": f"Bearer {value}", "Origin": EGZOS}

    return headers


def _events(c, name):
    return [e for e in c.ledger.tail(3000) if e["event"] == name]


def _register(c, sub="bob", caps=("fetch",)):
    c.backend.put_agent_registration({
        "client_id": "helper", "sub": sub, "name": "Helper", "capabilities": list(caps),
        "scopes": ["*"], "created_at": "2026-10-23T00:00:00Z", "revoked": False})


def _button(first, **body):
    return {**body, "confirm": {"challenge": first["challenge"], "proof": "button"}}


def _node(c, kind, name, parent=None):
    return c.nodes.create(kind, name, parent=parent or c.nodes.user_root(), token=c.owner, **KW)


# -- who may call ----------------------------------------------------------------------------------
@pytest.mark.parametrize("who", ["owner token", "a reader", "an admin's agent",
                                 "an admin over one project"])
def test_only_a_signed_in_admin_over_everything_reaches_the_grant_routes(c, door, sign, who):
    _register(c, sub="alice", caps=("admin", "fetch"))
    p = _node(c, "project", "p")
    c.identity.grant_user("pat", name="Pat", role="admin", scopes=[p.id], **KW)
    h = {"owner token": {"Authorization": f"Bearer {c.owner.secret}"}, "a reader": sign("bob"),
         "an admin's agent": sign("alice", client_id="helper"),
         "an admin over one project": sign("pat")}[who]
    reads = len(_events(c, "context.fetch"))
    # A grant within each caller's own, and a body the door must refuse without reading.
    for method, path, body in [("GET", "/v1/grants", None), ("DELETE", "/v1/grants/carol", None),
                               ("POST", "/v1/grants", {**DAVE, "scopes": [p.id]}),
                               ("POST", "/v1/grants", {"not": "a grant"})]:
        assert door.request(method, path, headers=h, json=body).content == NOT_FOUND
    assert len(_events(c, "context.fetch")) == reads + 4  # a refusal is a read too
    assert not any(g["revoked"] for g in c.backend.list_user_grants())
    assert c.backend.get_user_grant("dave") is None


def test_an_admin_lists_the_live_grants_and_the_read_is_recorded(c, door, sign):
    c.identity.revoke_user("bob", **KW)
    listed = door.get("/v1/grants", headers=sign()).json()["grants"]
    assert [g["sub"] for g in listed] == ["alice", "carol"]
    assert set(listed[0]) == {"sub", "name", "capabilities", "scopes", "created_at"}
    read = _events(c, "context.fetch")[-1]
    assert (read["actor"], read["details"]["read"], read["details"]["items"],
            read["details"]["grants"]) == ("user:alice", "grants", [], ["alice", "carol"])


# -- granting --------------------------------------------------------------------------------------
def test_a_grant_asks_first_and_lands_as_the_callers_act(c, door, sign):
    first = door.post("/v1/grants", headers=sign(), json={**DAVE, "role": "contributor"}).json()
    assert (first["result"], first["newly"]) == ("confirm", ["Dave"])
    shown = _events(c, "context.fetch")[-1]
    assert (shown["actor"], shown["subject"], shown["details"]["confirm_for"],
            shown["details"]["newly"]) == ("user:alice", "dave", "grant.add", ["Dave"])
    assert c.backend.get_user_grant("dave") is None
    # The role is expanded at grant time, so naming its capabilities instead is the same grant.
    named = {"sub": "dave", "name": "Dave", "capabilities": ["remember", "fetch"], "scopes": ["*"]}
    grant = door.post("/v1/grants", headers=sign(), json=_button(first, **named)).json()["grant"]
    assert set(grant) == {"sub", "name", "capabilities", "scopes", "created_at"}
    assert (grant["capabilities"], grant["scopes"]) == (["fetch", "remember"], ["*"])
    tail = c.ledger.tail(2)
    assert [(e["event"], e["actor"]) for e in tail] == [("step_up", "user:alice"),
                                                        ("identity.grant", "user:alice")]
    assert tail[1]["details"] == {"kind": "user", "outcome": "granted",
                                  "capabilities": ["fetch", "remember"], "scopes": ["*"]}


@pytest.mark.parametrize("change", [{"scopes": ["project:p"]}, {"name": "David"},
                                    {"role": "contributor"}, {"sub": "erin"}])
def test_a_second_leg_naming_any_other_grant_is_mismatch(c, door, sign, change):
    _node(c, "project", "p")
    first = door.post("/v1/grants", headers=sign(), json=DAVE).json()
    again = door.post("/v1/grants", headers=sign(), json=_button(first, **{**DAVE, **change}))
    assert again.json()["result"] == "confirm"
    assert _events(c, "step_up")[-1]["details"]["reason"] == "mismatch"
    assert c.backend.get_user_grant(change.get("sub", "dave")) is None


def test_scopes_named_by_path_are_granted_as_node_ids(c, door, sign):
    p = _node(c, "project", "p")
    first = door.post("/v1/grants", headers=sign(), json={**DAVE, "scopes": ["project:p"]}).json()
    # The challenge binds the node, so another path to it names the same grant.
    r = door.post("/v1/grants", headers=sign(), json=_button(first, **{**DAVE, "scopes": ["p"]}))
    assert r.json()["grant"]["scopes"] == [p.id] == c.backend.get_user_grant("dave")["scopes"]


def test_the_button_grants_nothing_without_a_fresh_sign_in(c, door, sign):
    stale = sign(signed_in_ago=3600)
    first = door.post("/v1/grants", headers=stale, json=DAVE).json()
    again = door.post("/v1/grants", headers=stale, json=_button(first, **DAVE)).json()
    assert (again["result"], again["newly"]) == ("confirm", ["Dave"])
    assert _events(c, "step_up")[-1]["details"]["reason"] == "not_fresh"
    assert c.backend.get_user_grant("dave") is None


@pytest.mark.parametrize("bad", [
    {"capabilities": ["fetch"]}, {"role": None}, {"role": "emperor"}, {"role": ["reader"]},
    {"role": None, "capabilities": ["fly"]}, {"role": None, "capabilities": "fetch"},
    {"scopes": []}, {"scopes": "*"}, {"scopes": [""]}, {"scopes": [1]}, {"scopes": ["x"] * 65},
    {"name": "Dave\u202e"}, {"sub": " dave"}, {"sub": "da\nve"}, {"sub": "da\u200bve"},
    {"extra": 1}, {"confirm": {"challenge": "", "proof": "button"}},
])
def test_a_malformed_grant_is_400_before_any_lookup(c, door, sign, bad):
    """Its scope names no node, so a lookup made first would answer §3's refusal instead."""
    body = {k: v for k, v in {**DAVE, "scopes": ["no-such-node"], **bad}.items() if v is not None}
    reads = len(_events(c, "context.fetch"))
    r = door.post("/v1/grants", headers=sign(), json=body)
    assert r.status_code == 400 and len(_events(c, "context.fetch")) == reads


@pytest.mark.parametrize("case", ["beyond the caller's capabilities", "an absent scope",
                                  "an ambiguous path"])
def test_every_refused_grant_appends_its_probe(c, door, sign, case):
    for name in ("p", "q"):
        _node(c, "thread", "t", parent=_node(c, "project", name))
    c.identity.grant_user("erin", name="Erin", capabilities=["admin"], scopes=["*"], **KW)
    who, scopes = {"beyond the caller's capabilities": ("erin", ["*"]),
                   "an absent scope": ("alice", ["no-such-node"]),
                   "an ambiguous path": ("alice", ["t"])}[case]
    reads = len(_events(c, "context.fetch"))
    r = door.post("/v1/grants", headers=sign(who), json={**DAVE, "scopes": scopes})
    assert r.status_code == (409 if case == "an ambiguous path" else 404)
    assert [e["details"]["items"] for e in _events(c, "context.fetch")[reads:]] == [[]]
    assert c.backend.get_user_grant("dave") is None


@pytest.mark.parametrize("narrower", [{"role": "reader"}, {"scopes": ["project:p"]}])
def test_re_granting_the_last_admin_narrower_is_409_before_any_leg(c, door, sign, narrower):
    _node(c, "project", "p")
    c.identity.revoke_user("carol", **KW)
    body = {**DAVE, "sub": "alice", "name": "Alice", "role": "admin", **narrower}
    reads = len(_events(c, "context.fetch"))
    for leg in (body, _button({"challenge": "x"}, **body)):
        r = door.post("/v1/grants", headers=sign(), json=leg)
        assert (r.status_code, r.json()) == (409, {"error": "last_admin"})
    refused = [(e["actor"], e["details"]) for e in _events(c, "identity.grant")[-2:]]
    assert refused == [("user:alice", {"kind": "user", "outcome": "refused",
                                       "reason": "last_admin"})] * 2
    assert len(_events(c, "context.fetch")) == reads and not _events(c, "step_up")
    alice = c.backend.get_user_grant("alice")
    assert ("admin" in alice["capabilities"], alice["scopes"]) == (True, ["*"])


# -- revoking --------------------------------------------------------------------------------------
def test_revoking_your_own_grant_is_never_gated(c, door, sign):
    _register(c, sub="carol")
    r = door.delete("/v1/grants/carol", headers=sign("carol"))
    assert r.json() == {"result": "revoked"} and not _events(c, "step_up")
    ended = [(e["actor"], e["subject"], e["details"]["kind"])
             for e in _events(c, "identity.revoke")]
    assert ended == [("user:carol", "carol", "user"), ("user:carol", "helper", "agent")]


def test_ending_someone_elses_grant_takes_the_confirm_and_their_agents(c, door, sign):
    _register(c)
    first = door.delete("/v1/grants/bob", headers=sign()).json()
    revokes = {"grant": {"sub": "bob", "name": "Bob"},
               "agents": [{"client_id": "helper", "name": "Helper"}]}
    assert (first["result"], first["newly"], first["revokes"]) == ("confirm", [], revokes)
    shown = _events(c, "context.fetch")[-1]
    assert (shown["actor"], shown["details"]["confirm_for"], shown["details"]["revokes"]) == (
        "user:alice", "grant.revoke", revokes)
    other = door.request("DELETE", "/v1/grants/carol", headers=sign(), json=_button(first)).json()
    assert other["result"] == "confirm" and not c.backend.get_user_grant("carol")["revoked"]
    assert _events(c, "step_up")[-1]["details"]["reason"] == "mismatch"
    again = door.delete("/v1/grants/bob", headers=sign()).json()
    stale = door.request("DELETE", "/v1/grants/bob", headers=sign(signed_in_ago=None),
                         json=_button(again)).json()
    assert _events(c, "step_up")[-1]["details"]["reason"] == "not_fresh"
    assert not c.backend.get_user_grant("bob")["revoked"]
    r = door.request("DELETE", "/v1/grants/bob", headers=sign(), json=_button(stale))
    assert r.json() == {"result": "revoked"}
    tail = c.ledger.tail(3)
    assert [(e["event"], e["actor"]) for e in tail] == [("step_up", "user:alice")] + [
        ("identity.revoke", "user:alice")] * 2
    assert (tail[1]["subject"], tail[1]["details"]["outcome"]) == ("bob", "revoked")
    assert (tail[2]["subject"], tail[2]["details"]["for"]) == ("helper", "user:bob")
    assert door.delete("/v1/grants/bob", headers=sign()).content == NOT_FOUND


def test_a_biometric_needs_no_fresh_sign_in(c, door, sign):
    phone = SoftAuthenticator(EGZOS)
    enrol = door.post("/v1/credentials", headers=sign()).json()
    door.post("/v1/credentials", headers=sign(), json={
        "challenge": enrol["challenge"], "attestation": phone.create(enrol["webauthn"]),
        "confirm": {"challenge": enrol["confirm"]["challenge"], "proof": "button"}})
    stale = sign(signed_in_ago=3600)
    first = door.delete("/v1/grants/bob", headers=stale).json()
    r = door.request("DELETE", "/v1/grants/bob", headers=stale, json={"confirm": {
        "challenge": first["challenge"], "proof": "biometric",
        "assertion": phone.get(first["webauthn"])}})
    assert r.json() == {"result": "revoked"}


@pytest.mark.parametrize("body", [{"extra": 1}, {"confirm": "yes"},
                                  {"confirm": {"challenge": "", "proof": "button"}}])
def test_a_malformed_revoke_is_400_and_revokes_nothing(c, door, sign, body):
    r = door.request("DELETE", "/v1/grants/bob", headers=sign(), json=body)
    assert r.status_code == 400 and not c.backend.get_user_grant("bob")["revoked"]


def test_the_last_admin_grant_is_never_revoked(c, door, sign):
    c.identity.revoke_user("carol", **KW)
    reads = len(_events(c, "context.fetch"))
    r = door.delete("/v1/grants/alice", headers=sign())
    assert (r.status_code, r.json()) == (409, {"error": "last_admin"})
    assert _events(c, "identity.revoke")[-1]["details"] == {
        "kind": "user", "outcome": "refused", "reason": "last_admin"}
    assert len(_events(c, "context.fetch")) == reads and not _events(c, "step_up")
    assert not c.backend.get_user_grant("alice")["revoked"]


# -- the second leg, under the lock ----------------------------------------------------------------
@pytest.mark.parametrize("since", ["revoked", "narrowed"])
def test_the_callers_own_grant_is_read_again_under_the_lock(c, door, sign, monkeypatch, since):
    first = door.delete("/v1/grants/bob", headers=sign()).json()
    verify = c.identity.verify

    def verified_then_changed(value, **kw):  # the caller's grant changes after the door
        token = verify(value, **kw)
        if since == "revoked":
            c.identity.revoke_user("alice", **KW)
        else:
            c.identity.grant_user("alice", name="Alice", role="reader", scopes=["*"], **KW)
        return token

    monkeypatch.setattr(c.identity, "verify", verified_then_changed)
    r = door.request("DELETE", "/v1/grants/bob", headers=sign(), json=_button(first))
    assert r.content == NOT_FOUND and not _events(c, "step_up")
    assert not c.backend.get_user_grant("bob")["revoked"]


def test_a_grant_revoked_by_someone_else_first_is_the_refusal(c, door, sign, monkeypatch):
    first = door.delete("/v1/grants/bob", headers=sign()).json()
    conclude = c.confirm.conclude

    def racing(*args, **kwargs):  # another admin's revoke landed before this one's lock
        c.identity.revoke_user("bob", **KW)
        return conclude(*args, **kwargs)

    monkeypatch.setattr(c.confirm, "conclude", racing)
    r = door.request("DELETE", "/v1/grants/bob", headers=sign(), json=_button(first))
    assert r.content == NOT_FOUND
    assert [e["details"]["outcome"] for e in _events(c, "identity.revoke")] == ["revoked"]


@pytest.mark.parametrize("since", ["revoked", "no longer an admin", "without what it grants"])
def test_the_callers_own_grant_is_read_again_under_the_lock_before_granting(
        c, door, sign, monkeypatch, since):
    first = door.post("/v1/grants", headers=sign(), json=DAVE).json()
    verify = c.identity.verify

    def verified_then_changed(value, **kw):  # the caller's grant changes after the door
        token = verify(value, **kw)
        if since == "revoked":
            c.identity.revoke_user("alice", **KW)
        else:  # a reader; or still an admin over everything, without the `fetch` dave would get
            caps = ["fetch"] if since == "no longer an admin" else ["admin", "remember"]
            c.identity.grant_user("alice", name="Alice", capabilities=caps, scopes=["*"], **KW)
        return token

    monkeypatch.setattr(c.identity, "verify", verified_then_changed)
    reads = len(_events(c, "context.fetch"))
    r = door.post("/v1/grants", headers=sign(), json=_button(first, **DAVE))
    assert r.content == NOT_FOUND and not _events(c, "step_up")
    assert len(_events(c, "context.fetch")) == reads + 1  # its probe
    assert c.backend.get_user_grant("dave") is None


def test_the_delta_is_recomputed_under_the_lock(c, door, sign, monkeypatch):
    wider = {**DAVE, "sub": "bob", "name": "Bob", "role": "contributor"}  # bob, a reader, wider
    first = door.post("/v1/grants", headers=sign(), json=wider).json()
    assert first["newly"] == []
    refresh = c.identity.refresh

    def registered_meanwhile(token):  # under the lock: an agent of bob's that the grant opens
        _register(c, sub="bob", caps=("remember",))
        return refresh(token)

    monkeypatch.setattr(c.identity, "refresh", registered_meanwhile)
    again = door.post("/v1/grants", headers=sign(), json=_button(first, **wider)).json()
    assert (again["result"], again["newly"]) == ("confirm", ["Helper"])
    assert _events(c, "step_up")[-1]["details"]["reason"] == "delta_changed"
    assert c.backend.get_user_grant("bob")["capabilities"] == ["fetch"]


def test_the_last_admin_is_checked_again_under_the_lock_and_its_refusal_commits(
        c, door, sign, monkeypatch):
    narrower = {**DAVE, "sub": "alice", "name": "Alice"}  # alice, re-granted as a reader
    first = door.post("/v1/grants", headers=sign(), json=narrower).json()
    conclude = c.confirm.conclude

    def racing(*args, **kwargs):  # carol's revoke lands after the check before the legs
        c.identity.revoke_user("carol", **KW)
        return conclude(*args, **kwargs)

    monkeypatch.setattr(c.confirm, "conclude", racing)
    r = door.post("/v1/grants", headers=sign(), json=_button(first, **narrower))
    assert (r.status_code, r.json()) == (409, {"error": "last_admin"})
    assert [(e["event"], e["actor"], e["details"]["outcome"]) for e in c.ledger.tail(2)] == [
        ("step_up", "user:alice", "confirmed"), ("identity.grant", "user:alice", "refused")]
    assert "admin" in c.backend.get_user_grant("alice")["capabilities"]
