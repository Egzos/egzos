# Copyright 2026 Ali Sasanian
# SPDX-License-Identifier: LicenseRef-PolyForm-Strict-1.0.0
"""identity.md §2 and §4: the identity keys, the grants, and the audience they join."""

from __future__ import annotations

import pytest

from egzos.container import OWNER, Container
from egzos.identity import ConfigError, LastAdmin, validate

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
    import threading

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
