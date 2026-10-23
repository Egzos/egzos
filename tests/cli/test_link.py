# Copyright 2026 Ali Sasanian
# SPDX-License-Identifier: LicenseRef-PolyForm-Strict-1.0.0
"""`egzos link`, `config` and `grant`: the owner links the container to a provider (identity.md
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
