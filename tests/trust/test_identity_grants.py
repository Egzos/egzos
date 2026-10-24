# Copyright 2026 Ali Sasanian
# SPDX-License-Identifier: LicenseRef-PolyForm-Strict-1.0.0
"""identity.md §2 and §4: the identity keys, the grants, and the audience they join."""

from __future__ import annotations

import threading

import pytest

from egzos.container import OWNER, Container
from egzos.identity import MAX_AGENTS, ConfigError, LastAdmin, TooManyAgents, validate

ALICE, BOB = "alice-sub", "bob-sub"
KW = {"actor": OWNER, "principal": "interactive"}


@pytest.fixture
def box(tmp_path):
    c = Container(tmp_path)
    c.owner = c.init()
    return c


def _events(c, name):
    return [e for e in c.ledger.tail(1000) if e["event"] == name]


# -- config (§2) -----------------------------------------------------------------------------------
def test_defaults_until_set_and_absence_is_not_falsiness(box):
    assert box.config_value("identity.issuer") is None
    assert box.config_value("identity.audience") == "authenticated"
    assert box.config_value("identity.algorithms") == "ES256 RS256"
    assert box.config_value("identity.browser_origins") == "https://egzos.io"
    box.set_config("identity.browser_origins", "", token=box.owner)
    assert box.config_value("identity.browser_origins") == ""


def test_set_config_is_an_admin_act_and_is_recorded(box):
    box.set_config("identity.issuer", "https://p.supabase.co/auth/v1", token=box.owner)
    (entry,) = _events(box, "config.set")
    assert entry["details"] == {"key": "identity.issuer", "value": "https://p.supabase.co/auth/v1"}
    assert entry["principal"] == "interactive"
    agent = box.auth.mint(principal="client", owner=OWNER, client="a", role="admin", scopes=["*"],
                          **{"actor": OWNER, "by_principal": "interactive"})
    with pytest.raises(PermissionError):
        box.set_config("identity.issuer", "https://x.supabase.co/auth/v1", token=agent)


def test_only_the_keys_this_version_reads_are_settable(box):
    for key in ("step_up.window_seconds", "chain.personal_root", "confirm.allow_button", "nope"):
        with pytest.raises(ConfigError):
            box.set_config(key, "0", token=box.owner)
    assert not _events(box, "config.set")


@pytest.mark.parametrize(
    ("key", "value"),
    [
        ("identity.issuer", "http://p.supabase.co/auth/v1"),
        ("identity.issuer", "https://p.supabase.co/auth/v1?x=1"),
        ("identity.issuer", "https://user:pw@p.supabase.co/auth/v1"),
        ("identity.issuer", "ftp://p"),
        ("identity.client_id", ""),
        ("identity.client_id", "has space"),
        ("identity.audience", "  "),
        ("identity.algorithms", "HS256"),
        ("identity.algorithms", "ES256 none"),
        ("identity.algorithms", ""),
        ("identity.browser_origins", "https://egzos.io/path"),
        ("identity.browser_origins", "http://egzos.io"),
        ("identity.browser_origins", "egzos.io"),
    ],
)
def test_values_a_container_will_not_hold(key, value):
    with pytest.raises(ConfigError):
        validate(key, value)


def test_loopback_may_use_plain_http_and_duplicates_collapse():
    assert validate("identity.issuer", "http://127.0.0.1:54321/auth/v1")
    assert validate("identity.browser_origins", "http://localhost:5173 http://localhost:5173") == (
        "http://localhost:5173"
    )
    assert validate("identity.algorithms", "ES256 ES256 RS256") == "ES256 RS256"


# -- grants (§4) -----------------------------------------------------------------------------------
def test_a_grant_is_recorded_with_what_it_covers(box):
    g = box.identity.grant_user(ALICE, name="alice", role="reader", scopes=["*"], **KW)
    assert g["capabilities"] == ["fetch"] and not g["revoked"]
    (entry,) = _events(box, "identity.grant")
    assert entry["subject"] == ALICE
    assert entry["details"] == {"kind": "user", "outcome": "granted", "capabilities": ["fetch"],
                                "scopes": ["*"]}


@pytest.mark.parametrize(
    "bad",
    [
        {"role": "reader", "capabilities": ["fetch"]},
        {},
        {"capabilities": ["fly"]},
        {"capabilities": []},
        {"role": "reader", "scopes": []},
        {"role": "emperor"},
    ],
)
def test_a_grant_names_a_role_or_known_capabilities_and_a_scope(box, bad):
    args = {"scopes": ["*"], **bad}
    with pytest.raises(ValueError):
        box.identity.grant_user(ALICE, name="alice", **args, **KW)


def test_granting_is_a_persons_act(box):
    with pytest.raises(PermissionError):
        box.identity.grant_user(ALICE, name="a", role="reader", scopes=["*"], actor=OWNER,
                                principal="client")


def test_the_last_admin_over_everything_is_never_revoked(box):
    box.identity.grant_user(ALICE, name="alice", role="admin", scopes=["*"], **KW)
    with pytest.raises(LastAdmin):
        box.identity.revoke_user(ALICE, **KW)
    (refused,) = _events(box, "identity.revoke")
    assert refused["details"]["outcome"] == "refused"
    assert refused["details"]["reason"] == "last_admin"
    box.identity.grant_user(BOB, name="bob", role="admin", scopes=["*"], **KW)
    assert box.identity.revoke_user(ALICE, **KW)
    assert box.backend.get_user_grant(ALICE)["revoked"]
    assert not box.identity.revoke_user(ALICE, **KW)  # already revoked: nothing to do
    with pytest.raises(LastAdmin):
        box.identity.revoke_user(BOB, **KW)


# -- the audience the gate counts (§4) -------------------------------------------------------------
def test_a_granted_person_is_in_the_audience_of_what_they_cover(box):
    root = box.nodes.user_root()
    assert all(a["token"] != f"user:{ALICE}" for a in box.trust.audience(root))
    box.identity.grant_user(ALICE, name="alice", role="reader", scopes=["*"], **KW)
    members = {a["token"]: a for a in box.trust.audience(root)}
    assert members[f"user:{ALICE}"]["principal"] == "interactive"
    box.identity.grant_user(BOB, name="bob", role="admin", scopes=["*"], **KW)
    box.identity.revoke_user(ALICE, **KW)
    assert f"user:{ALICE}" not in {a["token"] for a in box.trust.audience(root)}


def test_moving_into_a_granted_persons_scope_widens_and_parks(box):
    owner, root = box.owner, box.nodes.user_root()
    nk = {"token": owner, "actor": OWNER, "principal": "interactive"}
    private = box.nodes.create("project", "mine", parent=root, **nk)
    shared = box.nodes.create("project", "ours", parent=root, **nk)
    item = box.store.add(body="a note", scope=private, **nk)
    box.identity.grant_user(BOB, name="bob", role="reader", scopes=[shared.id], **KW)
    result = box.trust.move(item, shared, token=owner, actor=OWNER)
    assert result.get("gate") != "silent"
    (proposal,) = box.backend.list_proposals("open")
    assert [a["token"] for a in proposal["audience_delta"]] == [f"user:{BOB}"]


def test_narrowing_the_last_admin_is_refused_like_revoking_it(box):
    box.identity.grant_user(ALICE, name="alice", role="admin", scopes=["*"], **KW)
    with pytest.raises(LastAdmin):
        box.identity.grant_user(ALICE, name="alice", role="reader", scopes=["*"], **KW)
    assert "admin" in box.backend.get_user_grant(ALICE)["capabilities"]
    refused = _events(box, "identity.grant")[-1]
    assert refused["details"] == {"kind": "user", "outcome": "refused", "reason": "last_admin"}
    box.identity.grant_user(BOB, name="bob", role="admin", scopes=["*"], **KW)
    box.identity.grant_user(ALICE, name="alice", role="reader", scopes=["*"], **KW)
    assert box.backend.get_user_grant(ALICE)["capabilities"] == ["fetch"]


def test_two_concurrent_revokes_never_remove_the_last_admin(tmp_path):
    """a1r on #287: the check and the write are one transaction, so of two revokes racing on the
    only two whole-container admins, exactly one lands. Two containers on one file are two
    connections, as two processes would be."""
    first = Container(tmp_path)
    first.init()
    for sub in (ALICE, BOB):
        first.identity.grant_user(sub, name=sub, role="admin", scopes=["*"], **KW)
    second = Container(tmp_path)
    gate = threading.Barrier(2)
    outcomes: dict[str, str] = {}

    def revoke(c, sub):
        gate.wait()
        try:
            outcomes[sub] = "revoked" if c.identity.revoke_user(sub, **KW) else "none"
        except LastAdmin:
            outcomes[sub] = "refused"

    threads = [threading.Thread(target=revoke, args=(first, ALICE)),
               threading.Thread(target=revoke, args=(second, BOB))]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert sorted(outcomes.values()) == ["refused", "revoked"]
    live = [g for g in first.backend.list_user_grants() if not g["revoked"]]
    assert len(live) == 1


def test_a_revoke_and_its_entry_land_together(box, monkeypatch):
    box.identity.grant_user(ALICE, name="alice", role="admin", scopes=["*"], **KW)
    box.identity.grant_user(BOB, name="bob", role="reader", scopes=["*"], **KW)

    def broken(*args, **kwargs):
        raise RuntimeError("the chain cannot take an entry")

    monkeypatch.setattr(box.ledger, "append", broken)
    with pytest.raises(RuntimeError):
        box.identity.revoke_user(BOB, **KW)
    assert not box.backend.get_user_grant(BOB)["revoked"]


@pytest.mark.parametrize("name", ["", " ", "x" * 129, "Bob\u202eevil", "Bob\x00", "a\u2028b"])
def test_a_grants_display_name_is_short_and_shows_what_it_says(name, tmp_path):
    c = Container(tmp_path)
    c.init()
    with pytest.raises(ValueError):
        c.identity.grant_user("bob", name=name, role="reader", scopes=["*"], actor=OWNER,
                              principal="interactive")
    assert c.backend.get_user_grant("bob") is None


@pytest.mark.parametrize("sub", ["", "x" * 256, " bob", "b ob", "bob\n", "b\tob", "b\x00ob",
                                 "bo​b", "bob‮", "b ob", "b ob", 7])
def test_a_grant_names_the_providers_user_id_as_one_token(box, sub):
    with pytest.raises(ValueError, match="a grant names the provider's user id"):
        box.identity.grant_user(sub, name="bob", role="reader", scopes=["*"], **KW)
    assert box.backend.list_user_grants() == []


# -- the cascade (§4) ------------------------------------------------------------------------------
def _agent(c, client_id, sub, revoked=False, caps=("fetch",)):
    c.backend.put_agent_registration({
        "client_id": client_id, "sub": sub, "name": client_id, "capabilities": list(caps),
        "scopes": ["*"], "created_at": "2026-10-23T00:00:00Z", "revoked": revoked})


def test_a_revoke_ends_every_agent_serving_that_person_and_a_new_grant_revives_none(box):
    for sub in (ALICE, BOB):
        box.identity.grant_user(sub, name=sub, role="admin", scopes=["*"], **KW)
    for client_id, sub in (("a1", BOB), ("a2", BOB), ("a1", ALICE)):
        _agent(box, client_id, sub)
    _agent(box, "a0", BOB, revoked=True)  # ended before: nothing to end, nothing to record
    assert box.identity.revoke_user(BOB, **KW)
    ends = _events(box, "identity.revoke")
    assert [(e["subject"], e["details"]["kind"], e["details"].get("for")) for e in ends] == [
        (BOB, "user", None), ("a1", "agent", f"user:{BOB}"), ("a2", "agent", f"user:{BOB}")]
    assert ends[1]["details"]["capabilities"] == ["fetch"] and ends[1]["actor"] == OWNER
    assert [a["client_id"] for a in box.identity.serving(ALICE)] == ["a1"]
    box.identity.grant_user(BOB, name="bob", role="reader", scopes=["*"], **KW)
    assert box.identity.serving(BOB) == [] and box.identity._agent("a1", BOB) is None


# -- agent registrations (§4, rest.md §4.3) --------------------------------------------------------
TERMS = {"authorization_id": "auth-1", "name": "Helper", "capabilities": ["fetch"], "scopes": ["*"]}


def test_only_a_person_registers_an_agent_and_it_serves_them(box):
    box.identity.grant_user(BOB, name="bob", role="reader", scopes=["*"], **KW)
    _agent(box, "a1", BOB)
    for who in (box.owner, box.identity._agent("a1", BOB)):  # the owner's `Token`; an agent
        with pytest.raises(PermissionError):
            box.identity.register_agent(who, "helper", **TERMS)
    made = box.identity.register_agent(box.identity._person(BOB, "box"), "helper", **TERMS)
    assert made["sub"] == BOB and box.backend.list_agent_registrations(client_id="helper") == [made]


@pytest.mark.parametrize("race", ["the sixteenth slot", "one authorization"])
def test_two_concurrent_registrations_never_both_land(tmp_path, race):
    """The checks and the write are one transaction, over the chain past what the door read: two
    containers on one file are two connections, as two processes would be."""
    first = Container(tmp_path)
    first.init()
    first.identity.grant_user(BOB, name="bob", role="reader", scopes=["*"], **KW)
    held = MAX_AGENTS - 1 if race == "the sixteenth slot" else 0
    for n in range(held):
        _agent(first, f"a{n}", BOB)
    head, gate, outcomes = first.ledger.tail(1)[-1]["seq"], threading.Barrier(2, timeout=10), []

    def register(n):
        box = Container(tmp_path)
        terms = {**TERMS, "authorization_id": f"auth-{n}" if held else "auth-1", "after": head}
        gate.wait()
        try:
            made = box.identity.register_agent(box.identity._person(BOB, "box"), f"new{n}", **terms)
            outcomes.append("registered" if made else "spent")
        except TooManyAgents:
            outcomes.append("full")

    threads = [threading.Thread(target=register, args=(n,)) for n in range(2)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert sorted(outcomes) == sorted(["registered", "full" if held else "spent"])
    assert len(first.identity.serving(BOB)) == held + 1


# -- whom a grant opens to, and how far its grantor reaches (§4, rest.md §4.2-§4.3) ----------------
@pytest.fixture
def tree(box):
    """`P` and `Q` under the root, `T` under `P`, and `*` the whole container."""
    root, nk = box.nodes.user_root(), {"token": box.owner, **KW}
    p = box.nodes.create("project", "p", parent=root, **nk)
    return {"*": "*", "P": p.id, "T": box.nodes.create("thread", "t", parent=p, **nk).id,
            "Q": box.nodes.create("project", "q", parent=root, **nk).id}


@pytest.mark.parametrize(("before", "after", "agent", "newly"), [
    (None, "P", None, [f"user:{BOB}"]),  # a first grant opens the person
    ("revoked", "P", None, [f"user:{BOB}"]),  # so does one after a revoke, which reaches nothing
    ("*", "P", None, []),  # narrower opens nobody
    ("P", "*", None, [f"user:{BOB}"]),
    ("P", "T", None, []),  # within what they already cover
    ("T", "P", "fetch", [f"agent:a1:{BOB}", f"user:{BOB}"]),  # their agents widen with them
    ("P", "Q", "curate", [f"user:{BOB}"]),  # an agent sharing no capability reaches nothing
])
def test_a_grant_opens_whoever_it_newly_lets_see_something(box, tree, before, after, agent,
                                                          newly):
    if before:
        box.identity.grant_user(BOB, name="bob", role="reader", scopes=[tree.get(before, "*")],
                                **KW)
    if before == "revoked":
        box.identity.revoke_user(BOB, **KW)
    if agent:
        _agent(box, "a1", BOB, caps=(agent,))
    opens = box.identity.opens(BOB, "Robert", ["fetch"], [tree[after]])
    assert [m for m, _ in opens] == newly
    assert all(name == "Robert" for m, name in opens if m.startswith("user:"))


@pytest.mark.parametrize(("capabilities", "scope", "exceeds"), [
    (["fetch"], "T", False),  # coverage runs down the path
    (["fetch", "remember"], "P", False),
    (["fetch"], "*", True),  # the whole container only from a grantor holding it
    (["fetch"], "Q", True),
    (["publish"], "P", True),  # a capability the grantor lacks
])
def test_no_grant_exceeds_its_grantors_own(box, tree, capabilities, scope, exceeds):
    box.identity.grant_user(ALICE, name="alice", role="contributor", scopes=[tree["P"]], **KW)
    grantor = box.identity._person(ALICE, "box")
    assert box.identity.exceeds(grantor, capabilities, [tree[scope]]) is exceeds
