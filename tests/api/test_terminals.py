# Copyright 2026 Ali Sasanian
# SPDX-License-Identifier: LicenseRef-PolyForm-Strict-1.0.0
"""rest.md §4.3 and identity.md §4-§5: the terminal routes. Each person registers a terminal of
theirs with the confirm, from a browser, and lists their terminals, live or ended, with when each
was last used; an admin over the whole container lists everyone's. A client id is registered as a
terminal once, and the door says so behind the first leg, never before it. The person a terminal
serves, or the terminal itself, ends it at once; an admin ending someone else's takes the confirm.
Either reads what was done through it. Each family of routes reads its own kind only."""

from __future__ import annotations

import hashlib
import time

import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import ec
from fastapi.testclient import TestClient

from egzos.api.app import create_app
from egzos.container import OWNER, Container
from egzos.identity import MAX_TERMINALS, Jwks
from egzos.ledger import through_terminal

EGZOS = "https://egzos.io"
ISSUER = "https://project.supabase.co/auth/v1"
NOT_FOUND = b'{"error":"not_found"}'
UNAUTHORIZED = b'{"error":"unauthorized"}'
TOO_MANY = b'{"error":"too_many_terminals"}'
INVALID = b'{"error":"invalid_request"}'
KW = {"actor": OWNER, "principal": "interactive"}
LAPTOP = {"authorization_id": "auth-1", "client_id": "laptop", "name": "Bob's laptop"}
HELPER = {"authorization_id": "auth-9", "client_id": "helper", "name": "Helper", "role": "reader",
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
        now = int(time.time())
        claims = {"iss": ISSUER, "aud": "authenticated", "exp": now + 600, "iat": now,
                  "sub": sub, "client_id": client_id,
                  "amr": [{"method": "otp", "timestamp": now - signed_in_ago}]}
        value = jwt.encode(claims, key, algorithm="ES256", headers={"kid": "k1"})
        return {"Authorization": f"Bearer {value}", "Origin": EGZOS}

    return headers


def _events(c, name):
    return [e for e in c.ledger.tail(3000) if e["event"] == name]


def _since(c, head):
    return c.ledger.tail(c.ledger.tail(1)[-1]["seq"] - head)


def _head(c):
    return c.ledger.tail(1)[-1]["seq"]


def _terminal(c, client_id, sub, revoked=False):
    c.backend.put_agent_registration({
        "client_id": client_id, "sub": sub, "kind": "terminal", "name": client_id.title(),
        "created_at": "2026-11-01T00:00:00Z", "revoked": revoked})


def _agent(c, client_id, sub, revoked=False):
    c.backend.put_agent_registration({
        "client_id": client_id, "sub": sub, "name": client_id.title(), "capabilities": ["fetch"],
        "scopes": ["*"], "created_at": "2026-10-23T00:00:00Z", "revoked": revoked})


def _button(first, **body):
    return {**body, "confirm": {"challenge": first["challenge"], "proof": "button"}}


def _register(door, headers, **change):
    """Both legs, with the button, as the hand-off's page sends them."""
    body = {**LAPTOP, **change}
    first = door.post("/v1/terminals", headers=headers, json=body).json()
    return door.post("/v1/terminals", headers=headers, json=_button(first, **body))


def _node(c, kind, name, parent=None):
    return c.nodes.create(kind, name, parent=parent or c.nodes.user_root(), token=c.owner, **KW)


def _bare(r):
    """An answer as a caller could compare two: everything but the fresh challenge and its time."""
    body = {k: v for k, v in r.json().items() if k not in ("challenge", "expires_at")}
    return r.status_code, sorted(r.headers.items()), body, len(r.content)


# -- who may call ----------------------------------------------------------------------------------
@pytest.mark.parametrize("who", ["owner token", "a container token naming a person", "an agent"])
def test_only_a_person_signed_in_at_the_provider_reaches_the_terminal_routes(c, door, sign, who):
    _agent(c, "tool", "alice")
    _terminal(c, "laptop", "alice")
    tab = c.auth.mint(principal="interactive", owner="user:alice", client="tab", role="admin",
                      scopes=["*"], actor=OWNER, by_principal="interactive")
    tokens = {"owner token": c.owner, "a container token naming a person": tab}
    h = ({"Authorization": f"Bearer {tokens[who].secret}"} if who in tokens
         else sign("alice", client_id="tool"))
    reads = len(_events(c, "context.fetch"))
    for method, path, body in [("GET", "/v1/terminals", None),
                               ("GET", "/v1/terminals?ended=1", None),
                               ("POST", "/v1/terminals", {**LAPTOP, "client_id": "desk"}),
                               ("POST", "/v1/terminals", {"not": "a registration"}),
                               ("DELETE", "/v1/terminals/laptop", None),
                               ("GET", "/v1/terminals/laptop/log", None)]:
        assert door.request(method, path, headers=h, json=body).content == NOT_FOUND
    assert len(_events(c, "context.fetch")) == reads + 6  # a refusal is a read too
    assert c.backend.get_agent_registration("desk", "alice") is None
    assert not c.backend.get_agent_registration("laptop", "alice")["revoked"]


# -- listing ---------------------------------------------------------------------------------------
def test_a_person_lists_their_live_terminals_and_an_admin_everyones(c, door, sign, monkeypatch):
    p = _node(c, "project", "p")
    c.identity.grant_user("pat", name="Pat", role="admin", scopes=[p.id], **KW)
    for client_id, sub in (("laptop", "bob"), ("desk", "alice"), ("phone", "pat")):
        _terminal(c, client_id, sub)
    _agent(c, "helper", "bob")  # an agent is never a terminal
    _terminal(c, "old", "bob")
    monkeypatch.setattr("egzos.ledger.now_iso", lambda: "2026-11-02T10:00:00Z")
    c.identity.revoke_terminal("old", "bob", actor="user:bob", principal="interactive")
    monkeypatch.undo()

    def listed(sub, query=""):
        return [(t["client_id"], t["sub"]) for t in
                door.get(f"/v1/terminals{query}", headers=sign(sub)).json()["terminals"]]

    assert listed("bob") == [("laptop", "bob")]
    assert listed("pat") == [("phone", "pat")]  # an admin over less than everything: their own
    everyone = [("laptop", "bob"), ("desk", "alice"), ("phone", "pat")]
    assert listed("alice") == everyone
    read = _events(c, "context.fetch")[-1]
    assert (read["actor"], read["details"]["read"], read["details"]["items"]) == (
        "user:alice", "terminals", [])
    assert read["details"]["terminals"] == [{"client_id": i, "sub": s} for i, s in everyone]
    assert door.get("/v1/terminals", headers=sign("bob")).json() == {"terminals": [{
        "client_id": "laptop", "name": "Laptop", "sub": "bob",
        "created_at": "2026-11-01T00:00:00Z", "last_seen": None}]}
    # With ended=1, the ended ones instead, each with when it was ended.
    assert listed("bob", "?ended=1") == listed("alice", "?ended=1") == [("old", "bob")]
    assert listed("pat", "?ended=1") == []
    assert door.get("/v1/terminals?ended=1", headers=sign("bob")).json() == {"terminals": [{
        "client_id": "old", "name": "Old", "sub": "bob", "created_at": "2026-11-01T00:00:00Z",
        "last_seen": None, "ended_at": "2026-11-02T10:00:00Z"}]}
    assert _events(c, "context.fetch")[-1]["details"]["terminals"] == [
        {"client_id": "old", "sub": "bob"}]
    assert door.get("/v1/agents", headers=sign("bob")).json()["agents"][0]["client_id"] == "helper"


@pytest.mark.parametrize("query", ["?ended=0", "?ended=", "?ended=true", "?ended=1&ended=1",
                                   "?x=1", "?ended=1&sub=bob"])
def test_any_other_query_on_the_list_is_400_and_reads_nothing(c, door, sign, query):
    reads = len(_events(c, "context.fetch"))
    r = door.get(f"/v1/terminals{query}", headers=sign("bob"))
    assert (r.status_code, r.content) == (400, INVALID)
    assert len(_events(c, "context.fetch")) == reads


def test_last_seen_is_the_newest_entry_that_came_through_that_terminal(c, door, sign,
                                                                      monkeypatch):
    for client_id, sub in (("laptop", "bob"), ("desk", "bob"), ("laptop2", "carol")):
        _terminal(c, client_id, sub)

    def seen():
        terminals = door.get("/v1/terminals", headers=sign()).json()["terminals"]
        return {t["client_id"]: t["last_seen"] for t in terminals}

    assert seen() == {"laptop": None, "desk": None, "laptop2": None}
    for hour, sub, client_id in (("09", "bob", "laptop"), ("10", "bob", "desk"),
                                 ("11", "bob", "laptop")):
        monkeypatch.setattr("egzos.ledger.now_iso", lambda hour=hour: f"2026-11-02T{hour}:00:00Z")
        assert door.get("/v1/fetch", headers=sign(sub, client_id=client_id)).status_code == 200
    monkeypatch.setattr("egzos.ledger.now_iso", lambda: "2026-11-02T12:00:00Z")
    door.get("/v1/fetch", headers=sign("bob"))  # bob's own read in a browser is no terminal's
    assert seen() == {"laptop": "2026-11-02T11:00:00Z", "desk": "2026-11-02T10:00:00Z",
                      "laptop2": None}


# -- registering -----------------------------------------------------------------------------------
def test_a_person_registers_their_own_terminal_with_the_confirm_and_it_signs_in(c, door, sign):
    bob = sign("bob")
    first = door.post("/v1/terminals", headers=bob, json=LAPTOP).json()
    signs_in = {"client_id": "laptop", "name": "Bob's laptop"}
    assert (first["result"], first["newly"], first["signs_in"]) == ("confirm", [], signs_in)
    shown = _events(c, "context.fetch")[-1]
    assert (shown["actor"], shown["subject"], shown["details"]["confirm_for"],
            shown["details"]["newly"], shown["details"]["signs_in"]) == (
        "user:bob", "laptop", "terminal.add", [], signs_in)
    assert c.backend.get_agent_registration("laptop", "bob") is None  # the first leg writes none
    made = door.post("/v1/terminals", headers=bob, json=_button(first, **LAPTOP)).json()
    assert made["terminal"] == {"client_id": "laptop", "name": "Bob's laptop", "sub": "bob",
                                "created_at": made["terminal"]["created_at"], "last_seen": None}
    step_up, granted = c.ledger.tail(2)
    assert (step_up["event"], step_up["actor"], step_up["details"]["outcome"]) == (
        "step_up", "user:bob", "confirmed")
    assert (granted["event"], granted["actor"], granted["principal"], granted["subject"]) == (
        "identity.grant", "user:bob", "interactive", "laptop")
    assert granted["details"] == {"kind": "terminal", "outcome": "granted",
                                  "authorization_id": "auth-1", "for": "user:bob"}
    # Its token is bob, at that terminal.
    assert door.get("/v1/fetch", headers=sign("bob", client_id="laptop")).status_code == 200
    read = _events(c, "context.fetch")[-1]
    assert (read["actor"], read["principal"], read["details"]["terminal"]) == (
        "user:bob", "interactive", "laptop")
    assert "for" not in read["details"]
    assert [t["client_id"] for t in door.get("/v1/agents", headers=sign()).json()["agents"]] == []


@pytest.mark.parametrize("change", [{"client_id": "other"}, {"name": "Other"},
                                    {"authorization_id": "auth-2"}])
def test_a_second_leg_naming_any_other_terminal_is_mismatch(c, door, sign, change):
    first = door.post("/v1/terminals", headers=sign(), json=LAPTOP).json()
    again = door.post("/v1/terminals", headers=sign(), json=_button(first, **{**LAPTOP, **change}))
    assert again.json()["result"] == "confirm"
    assert _events(c, "step_up")[-1]["details"]["reason"] == "mismatch"
    assert c.backend.list_agent_registrations() == []


def test_the_button_registers_no_terminal_without_a_fresh_sign_in(c, door, sign):
    stale = sign(signed_in_ago=3600)
    first = door.post("/v1/terminals", headers=stale, json=LAPTOP).json()
    again = door.post("/v1/terminals", headers=stale, json=_button(first, **LAPTOP)).json()
    assert (again["result"], again["signs_in"]) == ("confirm", first["signs_in"])
    assert _events(c, "step_up")[-1]["details"]["reason"] == "not_fresh"
    assert c.backend.list_agent_registrations() == []


@pytest.mark.parametrize("bad", [
    {"authorization_id": None}, {"client_id": None}, {"name": None}, {"name": "x" * 129},
    {"name": "Lap‮top"}, {"name": ""}, {"client_id": "lap top"}, {"client_id": 7},
    {"authorization_id": "a\nb"}, {"scopes": ["*"]}, {"role": "reader"}, {"extra": 1},
    {"confirm": {"challenge": "", "proof": "button"}}, {"confirm": "yes"},
])
def test_a_malformed_registration_is_400_before_any_lookup(c, door, sign, bad):
    """Its client id is this container's own, so a lookup made first would answer §3's refusal."""
    body = {k: v for k, v in {**LAPTOP, "client_id": "box", **bad}.items() if v is not None}
    reads = len(_events(c, "context.fetch"))
    r = door.post("/v1/terminals", headers=sign(), json=body)
    assert (r.status_code, r.content) == (400, INVALID)
    assert len(_events(c, "context.fetch")) == reads


@pytest.mark.parametrize("case", ["this container's own", "a spent authorization",
                                  "an authorization an agent spent"])
def test_the_containers_own_client_and_a_spent_authorization_are_refused_before_any_leg(
        c, door, sign, case):
    if case == "a spent authorization":
        assert _register(door, sign("bob"), client_id="desk").status_code == 200
    if case == "an authorization an agent spent":
        first = door.post("/v1/agents", headers=sign("bob"), json={
            **HELPER, "authorization_id": "auth-1"}).json()
        assert door.post("/v1/agents", headers=sign("bob"), json=_button(
            first, **{**HELPER, "authorization_id": "auth-1"})).status_code == 200
    change = {"client_id": "box"} if case == "this container's own" else {}
    head = _head(c)
    r = door.post("/v1/terminals", headers=sign(), json={**LAPTOP, **change})
    assert r.content == NOT_FOUND
    assert [(e["event"], e["details"]["items"]) for e in _since(c, head)] == [
        ("context.fetch", [])]
    assert c.backend.get_agent_registration("laptop", "alice") is None


# -- at most sixteen -------------------------------------------------------------------------------
def test_a_person_holds_at_most_sixteen_terminals_counted_apart_from_agents(c, door, sign):
    for n in range(16):  # rest.md §4.3's number, never read back from the code under test
        _terminal(c, f"t{n}", "bob")
        _agent(c, f"a{n}", "carol")  # sixteen agents hold no terminal's slot
    _terminal(c, "gone", "bob", revoked=True)  # an ended one holds no slot
    reads = len(_events(c, "context.fetch"))
    r = door.post("/v1/terminals", headers=sign("bob"), json=LAPTOP)
    assert (r.status_code, r.content) == (429, TOO_MANY)
    assert (r.headers["cache-control"], r.headers["x-content-type-options"]) == (
        "no-store", "nosniff")
    assert len(_events(c, "context.fetch")) == reads  # before any leg: no challenge, no read
    # Bob's sixteen terminals hold no agent's slot, and carol's sixteen agents no terminal's.
    first = door.post("/v1/agents", headers=sign("bob"), json=HELPER).json()
    assert door.post("/v1/agents", headers=sign("bob"),
                     json=_button(first, **HELPER)).status_code == 200
    assert _register(door, sign("carol")).status_code == 200


def test_a_sixteenth_that_lands_after_the_door_is_refused_under_the_lock(c, door, sign,
                                                                        monkeypatch):
    for n in range(MAX_TERMINALS - 1):
        _terminal(c, f"t{n}", "bob")
    first = door.post("/v1/terminals", headers=sign("bob"), json=LAPTOP).json()
    conclude = c.confirm.conclude

    def racing(*args, **kwargs):  # another terminal of bob's took the last slot first
        _terminal(c, "late", "bob")
        return conclude(*args, **kwargs)

    monkeypatch.setattr(c.confirm, "conclude", racing)
    r = door.post("/v1/terminals", headers=sign("bob"), json=_button(first, **LAPTOP))
    assert (r.status_code, r.content) == (429, TOO_MANY)
    assert _events(c, "step_up")[-1]["details"]["outcome"] == "confirmed"  # it concluded: audited
    assert c.backend.get_agent_registration("laptop", "bob") is None


def test_the_callers_own_grant_is_read_again_under_the_lock(c, door, sign, monkeypatch):
    first = door.post("/v1/terminals", headers=sign("bob"), json=LAPTOP).json()
    verify = c.identity.verify

    def verified_then_revoked(value, **kw):  # the caller's grant ends after the door
        token = verify(value, **kw)
        c.identity.revoke_user("bob", **KW)
        return token

    monkeypatch.setattr(c.identity, "verify", verified_then_revoked)
    reads = len(_events(c, "context.fetch"))
    r = door.post("/v1/terminals", headers=sign("bob"), json=_button(first, **LAPTOP))
    assert r.content == NOT_FOUND and not _events(c, "step_up")
    assert len(_events(c, "context.fetch")) == reads + 1  # its probe
    assert c.backend.list_agent_registrations() == []  # so no later grant finds a terminal


# -- registered once, said behind the first leg ----------------------------------------------------
@pytest.mark.parametrize("taken", ["an agent's", "an ended agent's", "a terminal's",
                                   "an ended terminal's", "another person's terminal"])
def test_a_client_id_registered_here_is_refused_behind_a_first_leg_like_any_other(
        c, door, sign, taken):
    sub = "carol" if taken == "another person's terminal" else "bob"
    put = _agent if "agent" in taken else _terminal
    put(c, "laptop", sub, revoked="ended" in taken)
    before = c.backend.list_agent_registrations()
    bob = sign("bob")
    # The first leg: as for a client id never seen here.
    fresh = door.post("/v1/terminals", headers=bob, json={**LAPTOP, "client_id": "newtop",
                                                          "authorization_id": "auth-0"})
    first = door.post("/v1/terminals", headers=bob, json=LAPTOP)
    (status, headers, body, size), seen = _bare(first), _bare(fresh)
    assert (status, headers, size) == (seen[0], seen[1], seen[3])
    assert body == {**seen[2], "signs_in": {"client_id": "laptop", "name": "Bob's laptop"}}
    # A good proof is answered as a wrong one is: a fresh first leg, the same bytes but for the
    # challenge. Only the ledger says which case it was.
    wrong = door.post("/v1/terminals", headers=bob, json={**LAPTOP, "confirm": {
        "challenge": "no-such-challenge", "proof": "button"}})
    assert _events(c, "step_up")[-1]["details"]["reason"] == "stale"
    good = door.post("/v1/terminals", headers=bob, json=_button(first.json(), **LAPTOP))
    assert _bare(good) == _bare(wrong) and good.json()["challenge"] != first.json()["challenge"]
    step_up = _events(c, "step_up")[-1]
    assert (step_up["actor"], step_up["details"]["outcome"], step_up["details"]["reason"]) == (
        "user:bob", "refused", "registered")
    assert c.backend.list_agent_registrations() == before
    assert all(e["details"]["kind"] == "user" for e in _events(c, "identity.grant"))
    # The challenge was spent: presented again, it is no longer good.
    again = door.post("/v1/terminals", headers=bob, json=_button(first.json(), **LAPTOP))
    assert again.json()["result"] == "confirm"
    assert _events(c, "step_up")[-1]["details"]["reason"] == "spent"


def test_a_terminal_ended_never_returns(c, door, sign):
    assert _register(door, sign("bob")).status_code == 200
    assert door.delete("/v1/terminals/laptop", headers=sign("bob")).json() == {
        "result": "revoked"}
    r = _register(door, sign("bob"), authorization_id="auth-2")
    assert r.json()["result"] == "confirm"
    assert _events(c, "step_up")[-1]["details"]["reason"] == "registered"
    assert c.backend.get_agent_registration("laptop", "bob")["revoked"] is True
    assert door.get("/v1/fetch", headers=sign("bob", client_id="laptop")).status_code == 401


@pytest.mark.parametrize("ended", [False, True])
def test_a_terminals_client_id_is_never_registered_as_an_agent(c, door, sign, ended):
    _terminal(c, "helper", "bob", revoked=ended)
    first = door.post("/v1/agents", headers=sign("bob"), json=HELPER)
    assert first.json()["registers"] == {"client_id": "helper", "name": "Helper"}  # a first leg
    again = door.post("/v1/agents", headers=sign("bob"), json=_button(first.json(), **HELPER))
    assert again.json()["result"] == "confirm"
    assert _events(c, "step_up")[-1]["details"]["reason"] == "registered"
    record = c.backend.get_agent_registration("helper", "bob")
    assert (record["kind"], record["revoked"]) == ("terminal", ended)
    assert all(e["details"]["kind"] != "agent" for e in _events(c, "identity.grant"))


# -- each family its own kind ----------------------------------------------------------------------
def test_a_client_id_of_the_other_kind_is_the_one_refusal_on_every_route(c, door, sign):
    _agent(c, "helper", "bob")
    _terminal(c, "laptop", "bob")
    cases = []
    for family, other in (("agents", "laptop"), ("terminals", "helper")):
        for target in (other, "nobody"):
            cases += [("DELETE", f"/v1/{family}/{target}?sub=bob"),
                      ("GET", f"/v1/{family}/{target}/log?sub=bob")]
    head, answers = _head(c), set()
    for h, named in ((sign(), True), (sign("bob"), False)):  # an admin naming bob, and bob himself
        for method, path in cases:
            r = door.request(method, path if named else path.replace("?sub=bob", ""), headers=h)
            answers.add((r.status_code, tuple(sorted(r.headers.items())), r.content))
    assert answers == {next(iter(answers))} and next(iter(answers))[2] == NOT_FOUND
    # Each refusal reads alike on the record too, but for the id it names.
    probes = [{k: v for k, v in e["details"].items() if k != "ref"} for e in _since(c, head)]
    assert len(probes) == 2 * len(cases) and all(p == probes[0] for p in probes)
    assert not _events(c, "identity.revoke")
    assert [r["revoked"] for r in c.backend.list_agent_registrations()] == [False, False]
    assert [a["client_id"] for a in door.get("/v1/agents", headers=sign()).json()["agents"]] == [
        "helper"]
    assert [t["client_id"] for t in door.get("/v1/terminals", headers=sign()).json()[
        "terminals"]] == ["laptop"]


# -- ending one ------------------------------------------------------------------------------------
def test_the_person_a_terminal_serves_ends_it_at_once_and_its_next_request_is_the_one_401(
        c, door, sign):
    for client_id in ("laptop", "desk"):
        _terminal(c, client_id, "bob")
    laptop = sign("bob", client_id="laptop")
    assert door.get("/v1/fetch", headers=laptop).status_code == 200
    stray = door.request("DELETE", "/v1/terminals/laptop", headers=sign("bob", signed_in_ago=3600),
                         json=_button({"challenge": "x"}))  # never gated, nor needs a fresh one
    assert stray.json() == {"result": "revoked"}
    assert not _events(c, "step_up")
    (ended,) = _events(c, "identity.revoke")
    assert (ended["actor"], ended["principal"], ended["subject"], ended["details"]) == (
        "user:bob", "interactive", "laptop", {"kind": "terminal", "outcome": "revoked",
                                              "for": "user:bob"})
    head = _head(c)
    after = door.get("/v1/fetch", headers=laptop)
    garbage = door.get("/v1/fetch", headers={"Authorization": "Bearer garbage", "Origin": EGZOS})
    assert (after.status_code, after.content, sorted(after.headers.items())) == (
        garbage.status_code, garbage.content, sorted(garbage.headers.items()))
    assert after.content == UNAUTHORIZED and _head(c) == head  # an unverified caller appends none
    assert door.get("/v1/fetch", headers=sign("bob", client_id="desk")).status_code == 200


def test_a_terminal_ends_itself_with_the_token_it_holds(c, door, sign):
    _terminal(c, "laptop", "bob")
    laptop = sign("bob", client_id="laptop")
    assert door.delete("/v1/terminals/laptop", headers=laptop).json() == {"result": "revoked"}
    (ended,) = _events(c, "identity.revoke")
    assert ended["details"] == {"kind": "terminal", "outcome": "revoked", "for": "user:bob",
                                "terminal": "laptop"}
    assert door.get("/v1/terminals", headers=laptop).content == UNAUTHORIZED


def test_ending_someone_elses_terminal_takes_the_confirm_bound_to_the_pair(c, door, sign):
    for client_id, sub in (("laptop", "bob"), ("laptop2", "carol"), ("desk", "bob")):
        _terminal(c, client_id, sub)

    def ask():
        return door.delete("/v1/terminals/laptop?sub=bob", headers=sign()).json()

    first = ask()
    revokes = {"terminal": {"client_id": "laptop", "name": "Laptop", "sub": "bob"}}
    assert (first["result"], first["newly"], first["revokes"]) == ("confirm", [], revokes)
    shown = _events(c, "context.fetch")[-1]
    assert (shown["actor"], shown["subject"], shown["details"]["confirm_for"],
            shown["details"]["revokes"]) == ("user:alice", "laptop", "terminal.revoke", revokes)
    for other in ("laptop2?sub=carol", "desk?sub=bob"):  # another pair, each live
        again = door.request("DELETE", f"/v1/terminals/{other}", headers=sign(),
                             json=_button(ask()))
        assert again.json()["result"] == "confirm"
        assert _events(c, "step_up")[-1]["details"]["reason"] == "mismatch"
    stale = door.request("DELETE", "/v1/terminals/laptop?sub=bob",
                         headers=sign(signed_in_ago=3600), json=_button(ask())).json()
    assert (stale["result"], stale["revokes"]) == ("confirm", revokes)
    assert _events(c, "step_up")[-1]["details"]["reason"] == "not_fresh"
    assert not _events(c, "identity.revoke")
    r = door.request("DELETE", "/v1/terminals/laptop?sub=bob", headers=sign(), json=_button(stale))
    assert r.json() == {"result": "revoked"}
    step_up, ended = c.ledger.tail(2)
    assert (step_up["event"], step_up["actor"], step_up["details"]["outcome"]) == (
        "step_up", "user:alice", "confirmed")
    assert (ended["event"], ended["actor"], ended["subject"], ended["details"]["for"]) == (
        "identity.revoke", "user:alice", "laptop", "user:bob")
    assert door.get("/v1/fetch", headers=sign("bob", client_id="laptop")).status_code == 401


def test_a_grant_revoke_names_the_terminals_it_ends_and_ends_them(c, door, sign):
    _agent(c, "helper", "bob")
    _terminal(c, "laptop", "bob")
    _terminal(c, "old", "bob", revoked=True)
    first = door.delete("/v1/grants/bob", headers=sign()).json()
    assert first["revokes"] == {"grant": {"sub": "bob", "name": "Bob"},
                                "agents": [{"client_id": "helper", "name": "Helper"}],
                                "terminals": [{"client_id": "laptop", "name": "Laptop"}]}
    assert _events(c, "context.fetch")[-1]["details"]["revokes"] == first["revokes"]
    r = door.request("DELETE", "/v1/grants/bob", headers=sign(), json=_button(first))
    assert r.json() == {"result": "revoked"}
    kinds = [(e["subject"], e["details"]["kind"]) for e in _events(c, "identity.revoke")]
    assert kinds == [("bob", "user"), ("helper", "agent"), ("laptop", "terminal")]
    assert door.get("/v1/fetch", headers=sign("bob", client_id="laptop")).status_code == 401
    # A later grant starts with no terminals, and the one ended stays ended.
    c.identity.grant_user("bob", name="Bob", role="reader", scopes=["*"], **KW)
    assert door.get("/v1/terminals", headers=sign("bob")).json() == {"terminals": []}
    assert door.get("/v1/fetch", headers=sign("bob", client_id="laptop")).status_code == 401


def test_every_refusal_to_end_a_terminal_or_read_its_log_is_one_answer(c, door, sign):
    p = _node(c, "project", "p")
    c.identity.grant_user("pat", name="Pat", role="admin", scopes=[p.id], **KW)
    for client_id, sub, revoked in (("laptop", "bob", False), ("desk", "alice", False),
                                    ("gone", "bob", True)):
        _terminal(c, client_id, sub, revoked=revoked)
    _agent(c, "helper", "bob")
    tab = c.auth.mint(principal="interactive", owner="user:bob", client="tab", role="admin",
                      scopes=["*"], actor=OWNER, by_principal="interactive")
    junk = {"not": "a confirm"}  # a caller who may not act never makes the door read a body
    cases = [
        ({"Authorization": f"Bearer {c.owner.secret}", "Origin": EGZOS}, "laptop?sub=bob", junk),
        ({"Authorization": f"Bearer {tab.secret}", "Origin": EGZOS}, "laptop?sub=bob", junk),
        (sign("bob", client_id="helper"), "laptop?sub=bob", junk),  # an agent of bob's
        (sign("bob"), "desk?sub=alice", junk),  # neither the person it serves nor an admin
        (sign("bob", client_id="laptop"), "desk?sub=alice", junk),  # nor at a terminal of theirs
        (sign("pat"), "laptop?sub=bob", junk),  # an admin over less than everything
        (sign(), "nobody?sub=bob", None),  # absent
        (sign(), "gone?sub=bob", None),  # ended already: its log is still served (below)
    ]
    head, answers, asked = _head(c), set(), 0
    for h, target, body in cases:
        log = target.replace("?", "/log?")
        for method, path in [("DELETE", target)] + ([("GET", log)] if "gone" not in target else []):
            r = door.request(method, f"/v1/terminals/{path}", headers=h,
                             json=body if method == "DELETE" else None)
            answers.add((r.status_code, tuple(sorted(r.headers.items())), r.content))
            asked += 1
    assert len(answers) == 1 and next(iter(answers))[2] == NOT_FOUND
    assert [(e["event"], e["subject"], e["details"]["items"]) for e in _since(c, head)] == [
        ("context.fetch", None, [])] * asked
    assert [r["revoked"] for r in c.backend.list_agent_registrations()] == [
        False, False, True, False]
    assert door.get("/v1/terminals/gone/log?sub=bob", headers=sign()).json() == {"entries": []}


# -- the log ---------------------------------------------------------------------------------------
def test_the_log_serves_what_came_through_that_terminal_and_the_persons_own_access(c, door, sign):
    p, q = _node(c, "project", "p"), _node(c, "project", "q")
    x, y = (c.store.add(body=n, scope=s, token=c.owner, **KW) for n, s in (("x", p), ("y", q)))
    c.identity.grant_user("bob", name="Bob", role="contributor", scopes=["*"], **KW)
    for client_id in ("laptop", "desk", "spare"):
        _terminal(c, client_id, "bob")
    _terminal(c, "laptop", "carol")  # one id per person: carol's laptop is another registration
    _agent(c, "helper", "bob")
    laptop = sign("bob", client_id="laptop")
    for path in (f"/v1/items/{x.id}", f"/v1/items/{y.id}", "/v1/items/01ABSENTABSENTABSENTABSENT"):
        door.get(path, headers=laptop)  # the absent item's read is a probe
    door.get(f"/v1/items/{x.id}", headers=sign("bob"))  # bob in a browser: not the laptop's
    door.get(f"/v1/items/{x.id}", headers=sign("bob", client_id="desk"))  # nor another's
    door.get(f"/v1/items/{x.id}", headers=sign("carol", client_id="laptop"))  # nor carol's
    # What the laptop did to bob's other access: an agent and another terminal of his, ended.
    assert door.delete("/v1/agents/helper", headers=laptop).json()["result"] == "revoked"
    assert door.delete("/v1/terminals/spare", headers=laptop).json()["result"] == "revoked"
    with through_terminal("laptop"):  # on bob's own sub, and on what is someone else's
        for subject in ("bob", "carol", "laptop"):
            c.ledger.append("context.fetch", actor="user:bob", principal="interactive",
                            subject=subject, items=[], layers=[], withheld=0)
        c.ledger.append("step_up", actor="user:bob", principal="interactive", subject=x.id,
                        outcome="refused", reason="terminal")  # a refused act
    c.identity.grant_user("bob", name="Bob", role="reader", scopes=[p.id], **KW)  # over p only

    def log(reader, query=""):
        lines = door.get(f"/v1/terminals/laptop/log{query}", headers=reader).json()["entries"]
        assert all(set(e) == {"ts", "event", "subject", "scope"} for e in lines)  # no position
        return [(e["event"], e["subject"], e["scope"]) for e in lines]

    # Newest first: bob's own sub, his laptop (a registration serving him), the two he ended, and
    # x's read; never carol's sub, y's read in q, the probe or the refusal.
    own = [("context.fetch", "laptop", None), ("context.fetch", "bob", None),
           ("identity.revoke", "spare", None), ("identity.revoke", "helper", None),
           ("context.fetch", x.id, p.id)]
    assert log(sign("bob")) == own
    shown = _events(c, "context.fetch")[-1]
    assert (shown["actor"], shown["subject"]) == ("user:bob", "laptop")
    assert {k: shown["details"][k] for k in ("read", "items", "withheld", "registration")} == {
        "read": "terminal_log", "items": [], "withheld": 4,
        "registration": {"client_id": "laptop", "sub": "bob"}}
    assert "terminal" not in shown["details"]  # read in a browser: through no terminal
    everything = [*own[:4], ("context.fetch", y.id, q.id), own[4]]
    assert log(sign(), "?sub=bob") == everything
    assert log(sign(), "?sub=bob&limit=2") == everything[:2]
    assert door.get("/v1/terminals/laptop/log?limit=0", headers=sign("bob")).status_code == 400
    # Ended, its log stays readable to the person it served, and its token is refused.
    assert door.delete("/v1/terminals/laptop", headers=sign("bob")).json()["result"] == "revoked"
    assert log(sign("bob")) == own
    assert door.get("/v1/terminals/laptop/log", headers=laptop).content == UNAUTHORIZED


def test_an_upload_of_the_persons_shows_in_the_log_and_anothers_does_not(c, door, sign):
    p = _node(c, "project", "p")
    c.identity.grant_user("bob", name="Bob", role="contributor", scopes=["*"], **KW)
    _terminal(c, "laptop", "bob")
    data = b"a file"
    sha = hashlib.sha256(data).hexdigest()

    def upload(h):
        uid = door.post("/v1/uploads", headers=h, json={
            "scope": p.id, "name": "f.txt", "mime": "text/plain", "size": len(data),
            "sha256": sha}).json()["upload"]
        assert door.put(f"/v1/uploads/{uid}", headers=h, content=data).status_code == 200
        return uid

    mine, carols = upload(sign("bob", client_id="laptop")), upload(sign("carol"))
    with through_terminal("laptop"):
        c.ledger.append("context.fetch", actor="user:bob", principal="interactive",
                        subject=carols, items=[], layers=[], withheld=0)
    lines = door.get("/v1/terminals/laptop/log", headers=sign("bob")).json()["entries"]
    assert [(e["event"], e["subject"]) for e in lines] == [("upload.put", mine)]
