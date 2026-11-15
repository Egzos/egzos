# Copyright 2026 Ali Sasanian
# SPDX-License-Identifier: LicenseRef-PolyForm-Strict-1.0.0
"""`egzoscore link`, `config` and `grant`: the owner links the container to a provider (identity.md
§4)."""

from __future__ import annotations

import json

import pytest

from egzos.cli import main
from egzos.container import Container

ISSUER = "https://project.supabase.co/auth/v1"


@pytest.fixture
def home(tmp_path, monkeypatch):
    monkeypatch.setenv("EGZOS_HOME", str(tmp_path / ".egzos"))
    monkeypatch.delenv("EGZOS_TOKEN", raising=False)
    monkeypatch.chdir(tmp_path)
    assert main(["init"]) == 0
    return tmp_path / ".egzos"


def _json(capsys, argv):
    capsys.readouterr()
    code = main(["--json", *argv])
    return code, json.loads(capsys.readouterr().out)


def test_link_sets_the_provider_and_grants_the_owner_everything(home, capsys):
    code, out = _json(capsys, ["link", "--issuer", ISSUER, "--client-id", "c-1", "--sub", "me"])
    assert code == 0
    assert out["grant"]["capabilities"] == sorted(out["grant"]["capabilities"])
    c = Container(home)
    assert c.config_value("identity.issuer") == ISSUER
    assert c.config_value("identity.client_id") == "c-1"
    grant = c.backend.get_user_grant("me")
    assert "admin" in grant["capabilities"] and grant["scopes"] == ["*"]
    events = [e["event"] for e in c.ledger.tail(20)]
    assert events.count("config.set") == 2 and "identity.grant" in events


def test_link_refuses_a_plain_http_issuer_and_changes_nothing(home, capsys):
    code, out = _json(capsys, ["link", "--issuer", "http://p.example/auth/v1", "--client-id", "c",
                               "--sub", "me"])
    assert code == 1 and "loopback" in out["error"]
    c = Container(home)
    assert c.config_value("identity.issuer") is None
    assert c.backend.list_user_grants() == []


def test_config_get_reads_defaults_and_set_changes_one(home, capsys):
    code, out = _json(capsys, ["config", "get"])
    assert code == 0 and out["identity.audience"] == "authenticated"
    assert out["identity.issuer"] is None
    code, out = _json(capsys, ["config", "set", "identity.audience", "authenticated-egzos"])
    assert code == 0 and out == {"identity.audience": "authenticated-egzos"}
    code, out = _json(capsys, ["config", "set", "identity.algorithms", "HS256"])
    assert code == 1
    code, out = _json(capsys, ["config", "set", "step_up.window_seconds", "0"])
    assert code == 1
    code, out = _json(capsys, ["config", "get", "nope"])
    assert code == 1


def test_config_sets_gets_and_unsets_the_public_origin(home, capsys):
    """identity.md §2: `identity.origin` is handled as the other identity keys are."""
    code, out = _json(capsys, ["config", "set", "identity.origin", "https://box.example"])
    assert code == 0 and out == {"identity.origin": "https://box.example"}
    assert _json(capsys, ["config", "get", "identity.origin"]) == (
        0, {"identity.origin": "https://box.example"})
    assert _json(capsys, ["config", "set", "identity.origin", "http://box.example"])[0] == 1
    assert _json(capsys, ["config", "set", "identity.origin", "--unset"]) == (
        0, {"identity.origin": None})


def test_config_set_unset_makes_a_key_absent(home, capsys):
    assert _json(capsys, ["config", "set", "identity.client_id", "c-1"])[0] == 0
    code, out = _json(capsys, ["config", "set", "identity.client_id", "--unset"])
    assert code == 0 and out == {"identity.client_id": None}
    assert _json(capsys, ["config", "set", "identity.client_id"])[0] == 1


def test_grant_ls_and_rm_keep_the_last_admin(home, capsys):
    _json(capsys, ["link", "--issuer", ISSUER, "--client-id", "c-1", "--sub", "me"])
    code, out = _json(capsys, ["grant", "ls"])
    assert code == 0 and [g["sub"] for g in out["grants"]] == ["me"]
    code, out = _json(capsys, ["grant", "rm", "me"])
    assert code == 1 and "last admin" in out["error"]
    code, out = _json(capsys, ["grant", "rm", "nobody"])
    assert code == 1


def test_grant_ls_lists_agents_and_terminals_each_apart(home, capsys):
    """identity.md §4: a terminal is never listed as an agent."""
    _json(capsys, ["link", "--issuer", ISSUER, "--client-id", "c-1", "--sub", "me"])
    c = Container(home)
    c.backend.put_agent_registration({
        "client_id": "a1", "sub": "me", "name": "helper", "capabilities": ["fetch"],
        "scopes": ["*"], "created_at": "2026-11-14T00:00:00Z", "revoked": False})
    c.backend.put_agent_registration({
        "client_id": "t1", "sub": "me", "kind": "terminal", "name": "laptop",
        "created_at": "2026-11-14T00:00:00Z", "revoked": True})
    code, out = _json(capsys, ["grant", "ls"])
    assert code == 0
    assert [a["client_id"] for a in out["agents"]] == ["a1"]
    assert [t["client_id"] for t in out["terminals"]] == ["t1"]
    capsys.readouterr()
    assert main(["grant", "ls"]) == 0
    text = capsys.readouterr().out
    assert "agent a1 for me" in text and "terminal t1 [ended] for me" in text
    assert "agent t1" not in text


def test_grant_ls_shows_a_terminals_machine_and_never_a_raw_control_character(
        home, capsys):
    _json(capsys, ["link", "--issuer", ISSUER, "--client-id", "c-1", "--sub", "me"])
    c = Container(home)
    for client_id, extra in (("t1", {"machine": "laptop · macOS 15"}),
                             ("t2", {"machine": "desk\x1b[2Jtop"}), ("t3", {})):
        c.backend.put_agent_registration({
            "client_id": client_id, "sub": "me", "kind": "terminal", "name": "Bob's laptop",
            "created_at": "2026-11-14T00:00:00Z", "revoked": False, **extra})
    capsys.readouterr()
    assert main(["grant", "ls"]) == 0
    text = capsys.readouterr().out
    assert "\x1b" not in text
    lines = {ln.split()[1]: ln for ln in text.splitlines() if ln.startswith("terminal ")}
    assert "Bob's laptop" in lines["t1"] and "laptop · macOS 15" in lines["t1"]
    assert lines["t1"].index("Bob's laptop") < lines["t1"].index("laptop · macOS 15")
    assert "desk" in lines["t2"]
    assert lines["t3"].rstrip().endswith("Bob's laptop") and "machine=" not in lines["t3"]
    assert "machine=laptop · macOS 15" in lines["t1"]
    code, out = _json(capsys, ["grant", "ls"])
    assert code == 0
    assert {t["client_id"]: t.get("machine") for t in out["terminals"]} == {
        "t1": "laptop · macOS 15", "t2": "desk\x1b[2Jtop", "t3": None}


def test_grant_ls_marks_an_ended_terminal_where_a_claimed_machine_cannot_imitate_it(
        home, capsys):
    _json(capsys, ["link", "--issuer", ISSUER, "--client-id", "c-1", "--sub", "me"])
    c = Container(home)
    for client_id, revoked, extra in (("t1", False, {"machine": "ENDED"}),
                                      ("t2", True, {"machine": "macOS 15"}),
                                      ("t3", True, {}), ("t4", False, {})):
        c.backend.put_agent_registration({
            "client_id": client_id, "sub": "me", "kind": "terminal", "name": "Bob's laptop",
            "created_at": "2026-11-14T00:00:00Z", "revoked": revoked, **extra})
    capsys.readouterr()
    assert main(["grant", "ls"]) == 0
    lines = {ln.split()[1]: ln for ln in capsys.readouterr().out.splitlines()
             if ln.startswith("terminal ")}
    assert lines["t1"] == "terminal t1 for me  Bob's laptop    machine=ENDED"
    assert lines["t2"] == "terminal t2 [ended] for me  Bob's laptop    machine=macOS 15"
    assert lines["t3"].startswith("terminal t3 [ended] for me")
    assert "[ended]" not in lines["t1"] and "[ended]" not in lines["t4"]


def test_a_client_token_cannot_link(home, capsys, monkeypatch):
    c = Container(home)
    agent = c.auth.mint(principal="client", owner="self", client="a", role="admin", scopes=["*"],
                        actor="self", by_principal="interactive")
    monkeypatch.setenv("EGZOS_TOKEN", agent.secret)
    code, _ = _json(capsys, ["link", "--issuer", ISSUER, "--client-id", "c", "--sub", "x"])
    assert code == 1
    assert Container(home).backend.list_user_grants() == []


def test_the_grant_list_is_an_admins_over_everything(home, capsys, monkeypatch):
    c = Container(home)
    narrow = c.auth.mint(principal="interactive", owner="self", client="tab", role="admin",
                         scopes=[c.nodes.user_root().id], actor="self", by_principal="interactive")
    monkeypatch.setenv("EGZOS_TOKEN", narrow.secret)
    code, out = _json(capsys, ["grant", "ls"])
    assert code == 1 and "over the whole container" in out["error"]


def test_the_token_list_is_an_admins_over_everything(home, capsys, monkeypatch):
    c = Container(home)
    narrow = c.auth.mint(principal="interactive", owner="self", client="tab", role="admin",
                         scopes=[c.nodes.user_root().id], actor="self", by_principal="interactive")
    monkeypatch.setenv("EGZOS_TOKEN", narrow.secret)
    code, out = _json(capsys, ["token", "ls"])
    assert code == 1 and "over the whole container" in out["error"]


def test_grant_rm_ends_the_agents_serving_that_person_on_the_record(home, capsys):
    _json(capsys, ["link", "--issuer", ISSUER, "--client-id", "c-1", "--sub", "me"])
    c = Container(home)
    c.identity.grant_user("bob", name="bob", role="reader", scopes=["*"], actor="self",
                          principal="interactive")
    c.backend.put_agent_registration({**c.backend.get_user_grant("bob"), "client_id": "helper"})
    assert _json(capsys, ["grant", "rm", "bob"])[0] == 0
    ended = [e for e in Container(home).ledger.tail(5) if e["event"] == "identity.revoke"]
    assert [(e["actor"], e["details"]["kind"]) for e in ended] == [("self", "user"),
                                                                   ("self", "agent")]
