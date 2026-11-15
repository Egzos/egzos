# Copyright 2026 Ali Sasanian
# SPDX-License-Identifier: LicenseRef-PolyForm-Strict-1.0.0
"""identity.md §4, rest.md §4.3 (v0.7 §AJ): a terminal registration is the person at a terminal of
theirs. Registered once per `client_id`, by its person from a browser, sixteen at most, ended for
good, and never counted, listed or read as an agent."""

from __future__ import annotations

import pytest

from egzos.container import OWNER, Container
from egzos.identity import (
    MAX_AGENTS,
    MAX_TERMINALS,
    Registered,
    TooManyAgents,
    TooManyTerminals,
    principal_id,
)
from egzos.store.uploads import person_of

ALICE, BOB = "alice-sub", "bob-sub"
KW = {"actor": OWNER, "principal": "interactive"}
AGENT_TERMS = {"name": "Helper", "capabilities": ["fetch"], "scopes": ["*"]}


@pytest.fixture
def box(tmp_path):
    c = Container(tmp_path)
    c.owner = c.init()
    c.set_config("identity.client_id", "box", token=c.owner)
    for sub in (ALICE, BOB):
        c.identity.grant_user(sub, name=sub, role="admin", scopes=["*"], **KW)
    return c


def _events(c, name):
    return [e for e in c.ledger.tail(1000) if e["event"] == name]


def _person(c, sub=BOB):
    return c.identity._person(sub, "box")


def _sign_in(c, client_id, sub=BOB, *, authorization_id=None):
    """A terminal registered by its person, as the door will after the confirm."""
    return c.identity.register_terminal(
        _person(c, sub), client_id, authorization_id=authorization_id or f"auth-{client_id}-{sub}",
        name="a laptop")


def _agent(c, client_id, sub=BOB, *, authorization_id=None):
    return c.identity.register_agent(
        _person(c, sub), client_id, authorization_id=authorization_id or f"auth-{client_id}-{sub}",
        **AGENT_TERMS)


# -- registering (§4, rest.md §4.3) ----------------------------------------------------------------
def test_a_person_registers_a_terminal_and_it_is_recorded(box):
    made = _sign_in(box, "t1")
    assert made == {"client_id": "t1", "sub": BOB, "kind": "terminal", "name": "a laptop",
                    "created_at": made["created_at"], "revoked": False}
    assert box.backend.get_agent_registration("t1", BOB) == made
    (entry,) = [e for e in _events(box, "identity.grant") if e["subject"] == "t1"]
    assert (entry["actor"], entry["principal"]) == (f"user:{BOB}", "interactive")
    # No capabilities or scopes: a terminal holds none of its own.
    assert entry["details"] == {"kind": "terminal", "outcome": "granted",
                                "authorization_id": "auth-t1-bob-sub", "for": f"user:{BOB}"}


def test_only_a_person_in_a_browser_registers_a_terminal(box):
    _sign_in(box, "t1")
    _agent(box, "a1")
    for who in (box.owner, box.identity._agent("a1", BOB), box.identity._terminal("t1", BOB)):
        with pytest.raises(PermissionError):
            box.identity.register_terminal(who, "t2", authorization_id="x", name="n")
    # A terminal's token registers no agent either: access is given from a browser.
    with pytest.raises(PermissionError):
        box.identity.register_agent(box.identity._terminal("t1", BOB), "a2", authorization_id="y",
                                    **AGENT_TERMS)
    assert box.backend.list_agent_registrations(client_id="t2") == []
    assert box.backend.list_agent_registrations(client_id="a2") == []


def test_the_containers_own_client_is_neither_a_terminal_nor_an_agent(box):
    with pytest.raises(ValueError):
        _sign_in(box, "box")
    with pytest.raises(ValueError):
        _agent(box, "box")
    assert box.backend.list_agent_registrations() == []


@pytest.mark.parametrize("case", ["same person", "another person", "after an end",
                                  "an agent's", "an ended agent's"])
def test_a_client_id_is_registered_as_a_terminal_once(box, case):
    if case in ("same person", "another person", "after an end"):
        _sign_in(box, "t1")
    else:
        _agent(box, "t1", ALICE)
    if case == "after an end":
        box.identity.revoke_terminal("t1", BOB, **KW)
    if case == "an ended agent's":
        box.identity.revoke_agent("t1", ALICE, **KW)
    who = ALICE if case == "another person" else BOB
    assert box.identity.taken("t1", "terminal")
    before = box.backend.list_agent_registrations(client_id="t1")
    head = len(box.ledger.tail(1000))
    with pytest.raises(Registered):
        _sign_in(box, "t1", who, authorization_id="fresh")
    # Nothing written, nothing appended: an ended terminal never returns, and an agent's client
    # never becomes a terminal's.
    assert box.backend.list_agent_registrations(client_id="t1") == before
    assert len(box.ledger.tail(1000)) == head


@pytest.mark.parametrize("ended", [False, True])
def test_a_terminals_client_id_is_never_registered_as_an_agent(box, ended):
    _sign_in(box, "t1")
    if ended:
        box.identity.revoke_terminal("t1", BOB, **KW)
    assert box.identity.taken("t1", "agent")
    for who in (BOB, ALICE):
        with pytest.raises(Registered):
            _agent(box, "t1", who, authorization_id=f"fresh-{who}")
    record = box.backend.get_agent_registration("t1", BOB)
    assert (record["kind"], record["revoked"]) == ("terminal", ended)
    assert box.backend.get_agent_registration("t1", ALICE) is None


def test_an_agent_registers_again_as_before_and_a_fresh_client_is_free(box):
    _agent(box, "a1")
    assert not box.identity.taken("a1", "agent")  # an agent's own replaces itself, as before
    assert _agent(box, "a1", authorization_id="again")["kind"] == "agent"
    assert not box.identity.taken("new", "terminal") and not box.identity.taken("new", "agent")


@pytest.mark.parametrize("first", ["agent", "terminal"])
def test_one_authorization_registers_once_as_either_kind(box, first):
    register = {"agent": _agent, "terminal": _sign_in}
    assert register[first](box, "c1", authorization_id="auth-1") is not None
    second = "terminal" if first == "agent" else "agent"
    assert register[second](box, "c2", authorization_id="auth-1") is None
    assert box.identity.claimed("auth-1")
    assert box.backend.list_agent_registrations(client_id="c2") == []


def test_a_person_holds_at_most_sixteen_terminals_counted_apart_from_agents(box):
    for n in range(MAX_AGENTS):
        _agent(box, f"a{n}")
    for n in range(MAX_TERMINALS):  # sixteen agents leave every terminal slot open
        _sign_in(box, f"t{n}")
    head = len(box.ledger.tail(1000))
    with pytest.raises(TooManyTerminals):
        _sign_in(box, "t-extra")
    with pytest.raises(TooManyAgents):  # and sixteen terminals are not counted as agents
        _agent(box, "a-extra")
    assert len(box.ledger.tail(1000)) == head
    assert box.backend.list_agent_registrations(client_id="t-extra") == []
    assert not box.identity.full(ALICE, "x") and not box.identity.terminals_full(ALICE)
    box.identity.revoke_terminal("t0", BOB, **KW)  # an ended one frees its slot, not its id
    assert _sign_in(box, "t-extra") is not None
    with pytest.raises(Registered):
        _sign_in(box, "t0", authorization_id="back")


# -- ending (§4) -----------------------------------------------------------------------------------
def test_ending_a_terminal_is_recorded_with_no_capabilities_and_once(box):
    _sign_in(box, "t1")
    _agent(box, "a1")
    assert not box.identity.revoke_agent("t1", BOB, **KW)  # the agents' revoke ends no terminal
    assert not box.identity.revoke_terminal("a1", BOB, **KW)  # nor the terminals' an agent
    assert box.identity.revoke_terminal("t1", BOB, actor=f"user:{BOB}", principal="interactive")
    (ended,) = _events(box, "identity.revoke")
    assert (ended["actor"], ended["subject"], ended["details"]) == (
        f"user:{BOB}", "t1", {"kind": "terminal", "outcome": "revoked", "for": f"user:{BOB}"})
    assert not box.identity.revoke_terminal("t1", BOB, **KW)  # ended already: nothing recorded
    assert len(_events(box, "identity.revoke")) == 1
    assert box.backend.get_agent_registration("t1", BOB)["revoked"]


def test_a_grants_revoke_ends_every_agent_and_terminal_serving_that_person(box):
    _agent(box, "a1")
    _sign_in(box, "t1")
    _sign_in(box, "t2")
    _sign_in(box, "t3", ALICE)
    box.identity.revoke_terminal("t2", BOB, **KW)  # ended before: nothing to end again
    assert box.identity.revoke_user(BOB, **KW)
    ends = [(e["subject"], e["details"]["kind"], e["details"].get("for"))
            for e in _events(box, "identity.revoke")][1:]
    assert ends == [(BOB, "user", None), ("a1", "agent", f"user:{BOB}"),
                    ("t1", "terminal", f"user:{BOB}")]
    assert "capabilities" not in _events(box, "identity.revoke")[-1]["details"]
    assert box.identity.serving(BOB, "terminal") == []
    assert [t["client_id"] for t in box.identity.serving(ALICE, "terminal")] == ["t3"]
    # A later grant to that person starts with no agents and no terminals.
    box.identity.grant_user(BOB, name="bob", role="reader", scopes=["*"], **KW)
    assert box.identity._terminal("t1", BOB) is None and box.identity._agent("a1", BOB) is None


# -- kept apart (§4: every reader names the kind it wants) -----------------------------------------
def test_no_terminal_is_counted_listed_or_read_as_an_agent(box):
    _agent(box, "a1")
    _sign_in(box, "t1")
    assert [r["client_id"] for r in box.identity.serving(BOB)] == ["a1"]
    assert [r["client_id"] for r in box.identity.serving(BOB, "agent")] == ["a1"]
    assert [r["client_id"] for r in box.identity.serving(BOB, "terminal")] == ["t1"]
    assert [r["client_id"] for r in box.identity.registrations("agent")] == ["a1"]
    assert [r["client_id"] for r in box.identity.registrations("terminal")] == ["t1"]
    assert box.identity.registration("t1", BOB, "agent") is None
    assert box.identity.registration("a1", BOB, "terminal") is None
    assert box.identity.registration("t1", BOB, "terminal")["kind"] == "terminal"
    # The audience: the people and their agents, and no terminal; nobody `client` but an agent.
    tokens = box.identity.audience_tokens()
    assert sorted(t.id for t in tokens) == sorted(
        [principal_id(None, ALICE), principal_id(None, BOB), principal_id("a1", BOB)])
    assert all(t.terminal is None for t in tokens)
    members = {a["token"] for a in box.trust.audience(box.nodes.user_root())}
    assert not any(m.startswith("terminal") for m in members)
    # Whom a grant opens to: the person and their agents, never a terminal.
    box.identity.revoke_user(BOB, **KW)
    _sign_in(box, "t9", ALICE)
    assert [m for m, _ in box.identity.opens(ALICE, "A", ["fetch"], ["*"])] == []
    # A record of a kind neither reader knows is neither's.
    box.backend.put_agent_registration({**box.backend.get_agent_registration("t9", ALICE),
                                        "client_id": "odd", "kind": "other"})
    assert box.identity.taken("odd", "agent") and box.identity.taken("odd", "terminal")
    assert box.identity._agent("odd", ALICE) is None
    assert box.identity._terminal("odd", ALICE) is None
    assert box.identity.registrations("agent") and all(
        r["client_id"] != "odd" for r in box.identity.registrations("agent"))


# -- what a terminal did, and when (rest.md §4.3) --------------------------------------------------
def test_a_terminals_history_is_read_by_its_person_and_its_client(box):
    from egzos.ledger import through_terminal

    t1, t2 = _sign_in(box, "t1"), _sign_in(box, "t2")
    agent = _agent(box, "a1")
    assert box.identity.terminal_last_seen([t1, t2, agent]) == {}
    with through_terminal("t1"):
        first = box.ledger.append("context.fetch", actor=f"user:{BOB}", principal="interactive",
                                  items=[])
        last = box.ledger.append("context.fetch", actor=f"user:{BOB}", principal="interactive",
                                 items=[])
    box.ledger.append("context.fetch", actor=f"user:{BOB}", principal="interactive", items=[])
    with through_terminal("t1"):  # another person through the same id is not this terminal
        box.ledger.append("context.fetch", actor=f"user:{ALICE}", principal="interactive",
                          items=[])
    assert [e["seq"] for e in box.identity.terminal_acted("t1", BOB)] == [first["seq"],
                                                                         last["seq"]]
    assert box.identity.terminal_acted("t2", BOB) == []
    # An agent's readers do not read a terminal, and the terminal's do not read an agent.
    assert box.identity.terminal_last_seen([t1, t2, agent]) == {("t1", BOB): last["ts"]}
    assert box.identity.last_seen([t1, t2]) == {}
    assert box.identity.acted("t1", BOB) == []
    assert box.identity.terminal_ended([t1, t2, agent]) == {}
    box.identity.revoke_terminal("t1", BOB, actor=f"user:{BOB}", principal="interactive")
    box.identity.revoke_agent("a1", BOB, **KW)
    (ended,) = [e for e in _events(box, "identity.revoke") if e["details"]["kind"] == "terminal"]
    assert box.identity.terminal_ended([t1, t2, agent]) == {("t1", BOB): ended["ts"]}


def test_an_upload_a_terminal_opens_is_its_persons(box):
    """rest.md §6: what is counted per person stays per person, under `user:<sub>`."""
    _sign_in(box, "t:1")
    token = box.identity._terminal("t:1", BOB)
    assert person_of(token.id, token.owner) == principal_id(None, BOB)
    assert person_of(principal_id("t:1", BOB, "terminal"), "agent:t:1") is None
    assert person_of(principal_id("t:1", BOB, "terminal"), f"user:{ALICE}") is None
