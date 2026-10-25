# Copyright 2026 Ali Sasanian
# SPDX-License-Identifier: LicenseRef-PolyForm-Strict-1.0.0
"""rest.md §4.3 and identity.md §4-§5: the agent routes. Each person lists the agents serving them
and registers their own, with the confirm, never beyond their own grant; an admin over the whole
container lists everyone's. With the button, registering also needs a fresh sign-in. The person an
agent serves ends it at once; an admin ending one that serves someone else takes the confirm, bound
to the pair; either reads the agent's log, limited to what the reader covers today."""

from __future__ import annotations

import time

import jwt
import pytest
from authenticator import SoftAuthenticator
from cryptography.hazmat.primitives.asymmetric import ec
from fastapi.testclient import TestClient

from egzos.api.app import create_app
from egzos.container import OWNER, Container
from egzos.identity import MAX_AGENTS, Jwks
from egzos.ledger import acting_for

EGZOS = "https://egzos.io"
ISSUER = "https://project.supabase.co/auth/v1"
NOT_FOUND = b'{"error":"not_found"}'
TOO_MANY = b'{"error":"too_many_agents"}'
INVALID = b'{"error":"invalid_request"}'
KW = {"actor": OWNER, "principal": "interactive"}
HELPER = {"authorization_id": "auth-1", "client_id": "helper", "name": "Helper", "role": "reader",
          "scopes": ["*"]}


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


def _put(c, client_id, sub, revoked=False, caps=("fetch",)):
    c.backend.put_agent_registration({
        "client_id": client_id, "sub": sub, "name": client_id.title(), "capabilities": list(caps),
        "scopes": ["*"], "created_at": "2026-10-23T00:00:00Z", "revoked": revoked})


def _button(first, **body):
    return {**body, "confirm": {"challenge": first["challenge"], "proof": "button"}}


def _register(door, headers, **change):
    """Both legs, with the button, as the consent page sends them."""
    body = {**HELPER, **change}
    first = door.post("/v1/agents", headers=headers, json=body).json()
    return door.post("/v1/agents", headers=headers, json=_button(first, **body))


def _node(c, kind, name, parent=None):
    return c.nodes.create(kind, name, parent=parent or c.nodes.user_root(), token=c.owner, **KW)


# -- who may call ----------------------------------------------------------------------------------
@pytest.mark.parametrize("who", ["owner token", "a container token naming a person", "an agent"])
def test_only_a_person_signed_in_at_the_provider_reaches_the_agent_routes(c, door, sign, who):
    _put(c, "tool", "alice")
    tab = c.auth.mint(principal="interactive", owner="user:alice", client="tab", role="admin",
                      scopes=["*"], actor=OWNER, by_principal="interactive")
    tokens = {"owner token": c.owner, "a container token naming a person": tab}
    h = ({"Authorization": f"Bearer {tokens[who].secret}"} if who in tokens
         else sign("alice", client_id="tool"))
    reads = len(_events(c, "context.fetch"))
    for method, body in [("GET", None), ("POST", HELPER), ("POST", {"not": "a registration"})]:
        assert door.request(method, "/v1/agents", headers=h, json=body).content == NOT_FOUND
    assert len(_events(c, "context.fetch")) == reads + 3  # a refusal is a read too
    assert c.backend.get_agent_registration("helper", "alice") is None


# -- listing ---------------------------------------------------------------------------------------
def test_a_person_lists_the_agents_serving_them_and_an_admin_everyones(c, door, sign):
    p = _node(c, "project", "p")
    c.identity.grant_user("pat", name="Pat", role="admin", scopes=[p.id], **KW)
    for client_id, sub in (("helper", "bob"), ("helper", "alice"), ("tool", "pat")):
        _put(c, client_id, sub)
    _put(c, "gone", "bob", revoked=True)

    def listed(sub):
        return [(a["client_id"], a["sub"])
                for a in door.get("/v1/agents", headers=sign(sub)).json()["agents"]]

    assert listed("bob") == [("helper", "bob")]
    assert listed("pat") == [("tool", "pat")]  # an admin over less than everything: their own
    everyone = [("helper", "bob"), ("helper", "alice"), ("tool", "pat")]
    assert listed("alice") == everyone
    assert door.get("/v1/agents?x=1", headers=sign("bob")).status_code == 400  # and reads nothing
    read = _events(c, "context.fetch")[-1]
    assert (read["actor"], read["details"]["read"], read["details"]["items"]) == (
        "user:alice", "agents", [])
    assert read["details"]["agents"] == [{"client_id": i, "sub": s} for i, s in everyone]
    assert door.get("/v1/agents", headers=sign("bob")).json()["agents"] == [{
        "client_id": "helper", "name": "Helper", "sub": "bob", "capabilities": ["fetch"],
        "scopes": ["*"], "created_at": "2026-10-23T00:00:00Z", "last_seen": None}]


def test_last_seen_is_the_agents_newest_entry_for_that_person(c, door, sign, monkeypatch):
    for sub in ("alice", "bob", "carol"):  # one client, serving three people
        _put(c, "helper", sub)

    def seen():
        agents = door.get("/v1/agents", headers=sign()).json()["agents"]
        return {a["sub"]: a["last_seen"] for a in agents}

    assert seen() == {"alice": None, "bob": None, "carol": None}
    for hour, sub in (("09", "alice"), ("10", "bob"), ("11", "bob")):
        monkeypatch.setattr("egzos.ledger.now_iso", lambda hour=hour: f"2026-10-23T{hour}:00:00Z")
        assert door.get("/v1/fetch", headers=sign(sub, client_id="helper")).status_code == 200
    monkeypatch.setattr("egzos.ledger.now_iso", lambda: "2026-10-23T12:00:00Z")
    door.get("/v1/fetch", headers=sign("bob"))  # bob's own read is not his agent's
    # Each its own: the client has not acted for carol, and the listing is not an act.
    assert seen() == {"alice": "2026-10-23T09:00:00Z", "bob": "2026-10-23T11:00:00Z",
                      "carol": None}
    assert _register(door, sign("bob")).json()["agent"]["last_seen"] == "2026-10-23T11:00:00Z"


# -- registering -----------------------------------------------------------------------------------
def test_a_person_registers_their_own_agent_with_the_confirm_and_it_signs_in(c, door, sign):
    bob = sign("bob")  # a reader: no `publish`, and none needed
    first = door.post("/v1/agents", headers=bob, json=HELPER).json()
    registers = {"client_id": "helper", "name": "Helper"}
    assert (first["result"], first["newly"], first["registers"]) == ("confirm", [], registers)
    shown = _events(c, "context.fetch")[-1]
    assert (shown["actor"], shown["subject"], shown["details"]["confirm_for"],
            shown["details"]["newly"], shown["details"]["registers"]) == (
        "user:bob", "helper", "agent.add", [], registers)
    assert c.backend.get_agent_registration("helper", "bob") is None
    made = door.post("/v1/agents", headers=bob, json=_button(first, **HELPER)).json()["agent"]
    assert set(made) == {"client_id", "name", "sub", "capabilities", "scopes", "created_at",
                         "last_seen"}
    assert (made["sub"], made["capabilities"], made["scopes"], made["last_seen"]) == (
        "bob", ["fetch"], ["*"], None)
    # Attributed to the person who registered it, never to the agent.
    step_up, granted = c.ledger.tail(2)
    assert (step_up["event"], step_up["actor"], step_up["details"]["outcome"]) == (
        "step_up", "user:bob", "confirmed")
    assert (granted["event"], granted["actor"], granted["principal"], granted["subject"]) == (
        "identity.grant", "user:bob", "interactive", "helper")
    assert granted["details"] == {"kind": "agent", "outcome": "granted", "capabilities": ["fetch"],
                                  "scopes": ["*"], "authorization_id": "auth-1", "for": "user:bob"}
    assert door.get("/v1/fetch", headers=sign("bob", client_id="helper")).status_code == 200
    assert _events(c, "context.fetch")[-1]["actor"] == "agent:helper"


@pytest.mark.parametrize("change", [{"client_id": "other"}, {"role": "contributor"},
                                    {"scopes": ["project:p"]}, {"name": "Other"},
                                    {"authorization_id": "auth-2"}])
def test_a_second_leg_naming_any_other_registration_is_mismatch(c, door, sign, change):
    _node(c, "project", "p")
    first = door.post("/v1/agents", headers=sign(), json=HELPER).json()
    again = door.post("/v1/agents", headers=sign(), json=_button(first, **{**HELPER, **change}))
    assert again.json()["result"] == "confirm"
    assert _events(c, "step_up")[-1]["details"]["reason"] == "mismatch"
    assert c.backend.list_agent_registrations() == []


def test_scopes_named_by_path_are_registered_as_node_ids(c, door, sign):
    p = _node(c, "project", "p")
    first = door.post("/v1/agents", headers=sign(), json={**HELPER, "scopes": ["project:p"]})
    # The challenge binds the node, so another path to it names the same registration.
    r = door.post("/v1/agents", headers=sign(), json=_button(first.json(), **{
        **HELPER, "scopes": ["p"]}))
    assert r.json()["agent"]["scopes"] == [p.id]
    assert c.backend.get_agent_registration("helper", "alice")["scopes"] == [p.id]


@pytest.mark.parametrize("signed_in_ago", [3600, None])
def test_the_button_registers_nothing_without_a_fresh_sign_in(c, door, sign, signed_in_ago):
    stale = sign(signed_in_ago=signed_in_ago)
    first = door.post("/v1/agents", headers=stale, json=HELPER).json()
    again = door.post("/v1/agents", headers=stale, json=_button(first, **HELPER)).json()
    assert (again["result"], again["registers"]) == ("confirm", first["registers"])
    assert _events(c, "step_up")[-1]["details"]["reason"] == "not_fresh"
    assert c.backend.list_agent_registrations() == []


def test_a_biometric_needs_no_fresh_sign_in(c, door, sign):
    phone = SoftAuthenticator(EGZOS)
    enrol = door.post("/v1/credentials", headers=sign()).json()
    door.post("/v1/credentials", headers=sign(), json={
        "challenge": enrol["challenge"], "attestation": phone.create(enrol["webauthn"]),
        "confirm": {"challenge": enrol["confirm"]["challenge"], "proof": "button"}})
    stale = sign(signed_in_ago=3600)
    first = door.post("/v1/agents", headers=stale, json=HELPER).json()
    r = door.post("/v1/agents", headers=stale, json={**HELPER, "confirm": {
        "challenge": first["challenge"], "proof": "biometric",
        "assertion": phone.get(first["webauthn"])}})
    assert r.json()["agent"]["client_id"] == "helper"


@pytest.mark.parametrize("bad", [
    {"authorization_id": None}, {"client_id": None}, {"name": None}, {"scopes": None},
    {"capabilities": ["fetch"]}, {"role": None}, {"role": "emperor"}, {"name": "x" * 129},
    {"name": "Help\u202eer"}, {"client_id": "hel per"}, {"client_id": 7},
    {"authorization_id": ""}, {"authorization_id": "a\nb"}, {"authorization_id": "x" * 256},
    {"scopes": []}, {"scopes": "*"}, {"scopes": [""]}, {"scopes": ["x"] * 65}, {"extra": 1},
    {"confirm": {"challenge": "", "proof": "button"}},
])
def test_a_malformed_registration_is_400_before_any_lookup(c, door, sign, bad):
    """Its scope names no node, so a lookup made first would answer §3's refusal instead."""
    body = {k: v for k, v in {**HELPER, "scopes": ["no-such-node"], **bad}.items() if v is not None}
    reads = len(_events(c, "context.fetch"))
    r = door.post("/v1/agents", headers=sign(), json=body)
    assert r.status_code == 400 and len(_events(c, "context.fetch")) == reads


@pytest.mark.parametrize("case", ["beyond the caller's capabilities", "beyond the caller's scopes",
                                  "an absent scope", "an ambiguous path", "this container's own",
                                  "a spent authorization"])
def test_every_refused_registration_appends_its_probe(c, door, sign, case):
    p = _node(c, "project", "p")
    _node(c, "thread", "t", parent=p)
    _node(c, "thread", "t", parent=_node(c, "project", "q"))
    c.identity.grant_user("pat", name="Pat", role="admin", scopes=[p.id], **KW)
    if case == "a spent authorization":  # spent whoever names it, the registration ended since
        assert _register(door, sign("bob"), client_id="tool").status_code == 200
        _put(c, "tool", "bob", revoked=True)
    who, change = {"beyond the caller's capabilities": ("bob", {"role": "contributor"}),
                   "beyond the caller's scopes": ("pat", {"scopes": ["*"]}),
                   "an absent scope": ("alice", {"scopes": ["no-such-node"]}),
                   "an ambiguous path": ("alice", {"scopes": ["t"]}),
                   "this container's own": ("alice", {"client_id": "box"}),
                   "a spent authorization": ("alice", {})}[case]
    reads = len(_events(c, "context.fetch"))
    r = door.post("/v1/agents", headers=sign(who), json={**HELPER, **change})
    assert r.status_code == (409 if case == "an ambiguous path" else 404)
    assert [e["details"]["items"] for e in _events(c, "context.fetch")[reads:]] == [[]]
    assert [a for a in c.backend.list_agent_registrations() if not a["revoked"]] == []


# -- at most sixteen -------------------------------------------------------------------------------
def test_a_person_holds_at_most_sixteen_agents(c, door, sign):
    for n in range(16):  # rest.md §4.3's number, never read back from the code under test
        _put(c, f"a{n}", "bob")
    _put(c, "gone", "bob", revoked=True)  # a revoked one holds no slot
    reads = len(_events(c, "context.fetch"))
    r = door.post("/v1/agents", headers=sign("bob"), json=HELPER)
    assert (r.status_code, r.content) == (429, TOO_MANY)
    assert (r.headers["cache-control"], r.headers["x-content-type-options"]) == (
        "no-store", "nosniff")
    assert len(_events(c, "context.fetch")) == reads  # before any leg: no challenge, no read
    # Registering one of the sixteen again replaces it, under the lock too; another person's count
    # apart. Not auth-1, which alice's registration spends.
    again = _register(door, sign("bob"), client_id="a0", authorization_id="auth-2")
    assert again.status_code == 200 and len(c.identity.serving("bob")) == 16
    assert _register(door, sign("alice")).status_code == 200


def test_a_sixteenth_that_lands_after_the_door_is_refused_under_the_lock(c, door, sign,
                                                                        monkeypatch):
    for n in range(MAX_AGENTS - 1):
        _put(c, f"a{n}", "bob")
    first = door.post("/v1/agents", headers=sign("bob"), json=HELPER).json()
    conclude = c.confirm.conclude

    def racing(*args, **kwargs):  # another registration of bob's took the last slot first
        _put(c, "late", "bob")
        monkeypatch.setattr(c.backend, "audit_iter", None)  # the lock reads only the chain's tail
        return conclude(*args, **kwargs)

    monkeypatch.setattr(c.confirm, "conclude", racing)
    r = door.post("/v1/agents", headers=sign("bob"), json=_button(first, **HELPER))
    assert (r.status_code, r.content) == (429, TOO_MANY)
    assert _events(c, "step_up")[-1]["details"]["outcome"] == "confirmed"  # it concluded: audited
    assert c.backend.get_agent_registration("helper", "bob") is None
    assert len(c.identity.serving("bob")) == MAX_AGENTS


# -- the second leg, under the lock ----------------------------------------------------------------
@pytest.mark.parametrize("since", ["revoked", "without the capability", "over less"])
def test_the_callers_own_grant_is_read_again_under_the_lock(c, door, sign, monkeypatch, since):
    p = _node(c, "project", "p")
    first = door.post("/v1/agents", headers=sign("bob"), json=HELPER).json()
    verify = c.identity.verify

    def verified_then_changed(value, **kw):  # the caller's grant changes after the door
        token = verify(value, **kw)
        if since == "revoked":
            c.identity.revoke_user("bob", **KW)
        else:
            caps, scopes = (["remember"], ["*"]) if since == "without the capability" else (
                ["fetch"], [p.id])
            c.identity.grant_user("bob", name="Bob", capabilities=caps, scopes=scopes, **KW)
        return token

    monkeypatch.setattr(c.identity, "verify", verified_then_changed)
    reads = len(_events(c, "context.fetch"))
    r = door.post("/v1/agents", headers=sign("bob"), json=_button(first, **HELPER))
    assert r.content == NOT_FOUND and not _events(c, "step_up")
    assert len(_events(c, "context.fetch")) == reads + 1  # its probe
    # Nothing was written, so no grant to bob later finds an agent it did not register.
    assert c.backend.list_agent_registrations() == []


def test_a_later_grant_starts_with_no_agents(c, door, sign):
    """Registered while bob's grant was live, the agent ends with it, and a new grant revives
    none (identity.md §4's cascade)."""
    assert _register(door, sign("bob")).status_code == 200
    c.identity.revoke_user("bob", **KW)
    c.identity.grant_user("bob", name="Bob", role="reader", scopes=["*"], **KW)
    assert door.get("/v1/agents", headers=sign("bob")).json() == {"agents": []}
    assert door.get("/v1/fetch", headers=sign("bob", client_id="helper")).status_code == 401


# -- ending one ------------------------------------------------------------------------------------
def test_the_person_an_agent_serves_ends_it_at_once(c, door, sign):
    for client_id, sub in (("helper", "bob"), ("tool", "bob"), ("helper", "alice")):
        _put(c, client_id, sub)
    # Never gated, an admin's own included; a confirm sent with it concludes nothing.
    stray = door.request("DELETE", "/v1/agents/helper", headers=sign("bob"),
                         json=_button({"challenge": "x"}))
    assert stray.json() == {"result": "revoked"}
    stale = sign("bob", signed_in_ago=3600)  # nor does it need a fresh sign-in
    assert door.delete("/v1/agents/tool?sub=bob", headers=stale).json() == {"result": "revoked"}
    assert door.delete("/v1/agents/helper", headers=sign()).json()["result"] == "revoked"
    assert not _events(c, "step_up") and not _events(c, "context.fetch")
    ended = [(e["actor"], e["principal"], e["subject"], e["details"])
             for e in _events(c, "identity.revoke")]
    assert ended == [(f"user:{sub}", "interactive", client_id, {
        "kind": "agent", "outcome": "revoked", "capabilities": ["fetch"], "scopes": ["*"],
        "for": f"user:{sub}"}) for client_id, sub in (("helper", "bob"), ("tool", "bob"),
                                                      ("helper", "alice"))]
    assert all(r["revoked"] for r in c.backend.list_agent_registrations())
    assert door.get("/v1/fetch", headers=sign("bob", client_id="helper")).status_code == 401


def test_ending_someone_elses_agent_takes_the_confirm_bound_to_the_pair(c, door, sign):
    for client_id, sub in (("helper", "bob"), ("helper", "carol"), ("tool", "bob")):
        _put(c, client_id, sub)

    def ask():
        return door.delete("/v1/agents/helper?sub=bob", headers=sign()).json()

    first = ask()
    revokes = {"agent": {"client_id": "helper", "name": "Helper", "sub": "bob"}}
    assert (first["result"], first["newly"], first["revokes"]) == ("confirm", [], revokes)
    shown = _events(c, "context.fetch")[-1]
    assert (shown["actor"], shown["subject"], shown["details"]["confirm_for"],
            shown["details"]["revokes"]) == ("user:alice", "helper", "agent.revoke", revokes)
    for other in ("helper?sub=carol", "tool?sub=bob"):  # another pair, each live
        again = door.request("DELETE", f"/v1/agents/{other}", headers=sign(), json=_button(ask()))
        assert again.json()["result"] == "confirm"
        assert _events(c, "step_up")[-1]["details"]["reason"] == "mismatch"
    stale = door.request("DELETE", "/v1/agents/helper?sub=bob", headers=sign(signed_in_ago=3600),
                         json=_button(ask())).json()
    assert (stale["result"], stale["revokes"]) == ("confirm", revokes)
    assert _events(c, "step_up")[-1]["details"]["reason"] == "not_fresh"
    assert not _events(c, "identity.revoke")
    assert not any(r["revoked"] for r in c.backend.list_agent_registrations())
    r = door.request("DELETE", "/v1/agents/helper?sub=bob", headers=sign(), json=_button(stale))
    assert r.json() == {"result": "revoked"}
    step_up, ended = c.ledger.tail(2)
    assert (step_up["event"], step_up["actor"], step_up["details"]["outcome"]) == (
        "step_up", "user:alice", "confirmed")
    assert (ended["event"], ended["actor"], ended["subject"], ended["details"]["for"]) == (
        "identity.revoke", "user:alice", "helper", "user:bob")
    assert [(r["client_id"], r["sub"]) for r in c.backend.list_agent_registrations()
            if r["revoked"]] == [("helper", "bob")]


@pytest.mark.parametrize("since", ["revoked", "no longer an admin", "ended already"])
def test_the_second_leg_reads_the_caller_and_the_agent_again_under_the_lock(
        c, door, sign, monkeypatch, since):
    _put(c, "helper", "bob")
    first = door.delete("/v1/agents/helper?sub=bob", headers=sign()).json()
    verify, conclude = c.identity.verify, c.confirm.conclude

    def verified_then_changed(value, **kw):  # the caller's grant changes after the door
        token = verify(value, **kw)
        if since == "revoked":
            c.identity.revoke_user("alice", **KW)
        else:
            c.identity.grant_user("alice", name="Alice", role="reader", scopes=["*"], **KW)
        return token

    def racing(*args, **kwargs):  # bob ended it himself before this one's lock
        c.identity.revoke_agent("helper", "bob", actor="user:bob", principal="interactive")
        return conclude(*args, **kwargs)

    if since == "ended already":
        monkeypatch.setattr(c.confirm, "conclude", racing)
    else:
        monkeypatch.setattr(c.identity, "verify", verified_then_changed)
    reads = len(_events(c, "context.fetch"))
    r = door.request("DELETE", "/v1/agents/helper?sub=bob", headers=sign(), json=_button(first))
    assert r.content == NOT_FOUND and len(_events(c, "context.fetch")) == reads + 1  # its probe
    revokes = _events(c, "identity.revoke")
    if since == "ended already":  # concluded, so audited; and nothing ends twice
        assert _events(c, "step_up")[-1]["details"]["outcome"] == "confirmed"
        assert [e["actor"] for e in revokes if e["details"]["kind"] == "agent"] == ["user:bob"]
    else:
        assert not _events(c, "step_up")
        assert not c.backend.get_agent_registration("helper", "bob")["revoked"]


def test_every_refusal_to_end_an_agent_or_read_its_log_is_one_answer(c, door, sign):
    p = _node(c, "project", "p")
    c.identity.grant_user("pat", name="Pat", role="admin", scopes=[p.id], **KW)
    for client_id, sub, revoked in (("helper", "bob", False), ("tool", "alice", False),
                                    ("gone", "bob", True)):
        _put(c, client_id, sub, revoked=revoked)
    tab = c.auth.mint(principal="interactive", owner="user:bob", client="tab", role="admin",
                      scopes=["*"], actor=OWNER, by_principal="interactive")
    junk = {"not": "a confirm"}  # a caller who may not act never makes the door read a body
    cases = [
        ({"Authorization": f"Bearer {c.owner.secret}", "Origin": EGZOS}, "helper?sub=bob", junk),
        ({"Authorization": f"Bearer {tab.secret}", "Origin": EGZOS}, "helper?sub=bob", junk),
        (sign("bob", client_id="helper"), "helper", junk),  # the agent itself
        (sign("bob"), "tool?sub=alice", junk),  # neither the person it serves nor an admin
        (sign("pat"), "helper?sub=bob", junk),  # an admin over less than everything
        (sign(), "nobody?sub=bob", None),  # absent
        (sign(), "gone?sub=bob", None),  # ended already: its log is still served (below)
    ]
    head, answers, asked = c.ledger.tail(1)[-1]["seq"], set(), 0
    for h, target, body in cases:
        log = target.replace("?", "/log?") if "?" in target else f"{target}/log"
        for method, path in [("DELETE", target)] + ([("GET", log)] if "gone" not in target else []):
            r = door.request(method, f"/v1/agents/{path}", headers=h,
                             json=body if method == "DELETE" else None)
            answers.add((r.status_code, tuple(sorted(r.headers.items())), r.content))
            asked += 1
    assert len(answers) == 1 and next(iter(answers))[2] == NOT_FOUND
    new = c.ledger.tail(c.ledger.tail(1)[-1]["seq"] - head)
    assert [(e["event"], e["subject"], e["details"]["items"]) for e in new] == [
        ("context.fetch", None, [])] * asked
    assert [r["revoked"] for r in c.backend.list_agent_registrations()] == [False, False, True]
    assert door.get("/v1/agents/gone/log?sub=bob", headers=sign()).json() == {"entries": []}
    for method, path in [("GET", "/v1/agents/helper"), ("DELETE", "/v1/agents/helper/log")]:
        assert door.request(method, path, headers=sign("bob")).content == NOT_FOUND


@pytest.mark.parametrize("query, body", [
    ("?x=1", None), ("?sub=alice&sub=alice", None), ("", {"extra": 1}), ("", {"confirm": "yes"}),
    ("", {"confirm": {"challenge": "", "proof": "button"}})])
def test_a_malformed_end_is_400_before_any_lookup_and_ends_nothing(c, door, sign, query, body):
    _put(c, "helper", "alice")
    reads = len(_events(c, "context.fetch"))
    for client_id in ("helper", "nobody"):  # a live pair and an absent one answer alike
        r = door.request("DELETE", f"/v1/agents/{client_id}{query}", headers=sign(), json=body)
        assert (r.status_code, r.content) == (400, INVALID)
    assert len(_events(c, "context.fetch")) == reads and not _events(c, "identity.revoke")
    assert not c.backend.get_agent_registration("helper", "alice")["revoked"]


# -- the log ---------------------------------------------------------------------------------------
def test_the_log_serves_only_what_the_reader_covers_today(c, door, sign):
    p, q = _node(c, "project", "p"), _node(c, "project", "q")
    x, y = (c.store.add(body=n, scope=s, token=c.owner, **KW) for n, s in (("x", p), ("y", q)))
    c.identity.grant_user("bob", name="Bob", role="contributor", scopes=["*"], **KW)
    _put(c, "helper", "bob", caps=("fetch", "remember"))
    _put(c, "helper", "carol")
    helper = sign("bob", client_id="helper")
    for path in (f"/v1/items/{x.id}", f"/v1/items/{y.id}", "/v1/items/01ABSENTABSENTABSENTABSENT",
                 f"/v1/fetch?scope={q.id}"):  # the absent item's read is a probe
        door.get(path, headers=helper)
    z = door.post("/v1/items", headers=helper, json={"body": "z", "scope": q.id}).json()["item"]
    door.get(f"/v1/items/{x.id}", headers=sign("carol", client_id="helper"))  # carol's, not bob's
    c.trust.move(c.store.get(z["id"]), p, token=c.owner, actor=OWNER)  # z sits in p now
    door.get(f"/v1/items/{z['id']}", headers=helper)
    with acting_for("user:bob"):  # a refused act, on a subject every reader here covers
        c.ledger.append("step_up", actor="agent:helper", principal="client", subject=x.id,
                        outcome="refused", reason="button_off")
    c.identity.grant_user("bob", name="Bob", role="reader", scopes=[p.id], **KW)  # over p only

    def log(reader, query=""):
        lines = door.get(f"/v1/agents/helper/log{query}", headers=reader).json()["entries"]
        assert all(set(e) == {"ts", "event", "subject", "scope"} for e in lines)  # no position
        return [(e["event"], e["subject"], e["scope"]) for e in lines]

    # Newest first. Bob sees x's read and z's since it moved, never what names q (z's write in
    # q included), the probe or the refusal; an admin over everything, all of it but those two.
    read_x, read_z = ("context.fetch", x.id, p.id), ("context.fetch", z["id"], p.id)
    assert log(sign("bob")) == [read_z, read_x]
    shown = _events(c, "context.fetch")[-1]
    assert (shown["actor"], shown["subject"]) == ("user:bob", "helper")
    assert {k: shown["details"][k] for k in ("read", "items", "withheld", "agent")} == {
        "read": "agent_log", "items": [], "withheld": 5, "agent": {"client_id": "helper",
                                                                   "sub": "bob"}}
    everything = [read_z, ("item.add", z["id"], q.id), ("context.fetch", q.id, q.id),
                  ("context.fetch", y.id, q.id), read_x]
    assert log(sign(), "?sub=bob") == everything
    assert log(sign(), "?sub=bob&limit=2") == everything[:2]
    assert _events(c, "context.fetch")[-1]["details"]["withheld"] == 1  # the refusal it passed
    c.trust.move(c.store.get(x.id), q, token=c.owner, actor=OWNER)  # out of bob's sight today
    assert log(sign("bob")) == [read_z]
    assert door.delete("/v1/agents/helper", headers=sign("bob")).json()["result"] == "revoked"
    assert log(sign("bob")) == [read_z]  # its history, still
    # A quarantined item reads as absent to every reader, as at every item route: z's lines go.
    c.trust.quarantine(c.store.get(z["id"]), token=c.owner, actor=OWNER, reason="flagged")
    assert log(sign("bob")) == [] and log(sign(), "?sub=bob") == everything[2:]
    c.backend.tombstone(x.id)  # and so does a tombstoned one
    assert log(sign(), "?sub=bob") == everything[2:4]


def test_the_log_is_newest_first_and_at_most_limit_lines(c, door, sign):
    p = _node(c, "project", "p")
    _put(c, "helper", "bob")
    with acting_for("user:bob"):  # 51 reads that served nothing, each still the agent's act
        for _ in range(51):
            c.ledger.append("context.fetch", actor="agent:helper", principal="client",
                            subject=p.id, scope=p.id, items=[], layers=[], withheld=0)

    def seqs(query=""):  # the chain positions served, which only the record holds
        assert door.get(f"/v1/agents/helper/log{query}", headers=sign("bob")).status_code == 200
        return _events(c, "context.fetch")[-1]["details"]["entries"]

    every = seqs("?limit=200")
    assert len(every) == 51 and every == sorted(every, reverse=True)
    assert seqs() == every[:50] and seqs("?limit=1") == every[:1]
    assert _events(c, "context.fetch")[-1]["details"]["entries"] == every[:1]


@pytest.mark.parametrize("limit", ["0", "201", "-1", "", "x", "1.5", "\uff11", "1000", "5&limit=6"])
def test_a_limit_outside_1_to_200_is_400_before_any_lookup(c, door, sign, limit):
    """The pair is absent, so a lookup made first would answer §3's refusal instead."""
    reads = len(_events(c, "context.fetch"))
    r = door.get(f"/v1/agents/nobody/log?limit={limit}", headers=sign())
    assert (r.status_code, r.content) == (400, INVALID)
    assert len(_events(c, "context.fetch")) == reads
