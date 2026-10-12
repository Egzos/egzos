# Copyright 2026 Ali Sasanian
# SPDX-License-Identifier: LicenseRef-PolyForm-Strict-1.0.0
"""`egzos connect` mints a client principal and prints the Claude Code wiring."""

from __future__ import annotations

import json

from egzos.cli import main


def test_connect_mints_a_client_token_and_prints_the_command(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("EGZOS_HOME", str(tmp_path))
    monkeypatch.setattr("egzos.authz.presence.is_terminal", lambda: True)  # a person at a terminal
    assert main(["init"]) == 0
    capsys.readouterr()
    assert main(["--json", "connect"]) == 0
    out = json.loads(capsys.readouterr().out)
    assert out["client"] == "claude-code" and out["role"] == "contributor" and not out["applied"]
    cmd = out["command"]
    assert cmd[:6] == ["claude", "mcp", "add", "--scope", "user", "egzos"]
    assert any(a.startswith(f"EGZOS_TOKEN=egz_{out['token']}_") for a in cmd)
    assert cmd[-2:] == ["serve", "--mcp"]
    assert main(["--json", "token", "ls"]) == 0
    tokens = json.loads(capsys.readouterr().out)
    minted = [t for t in tokens if t["id"] == out["token"]]
    assert minted and minted[0]["principal"] == "client"


def test_connect_prints_its_secret_only_to_a_terminal(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("EGZOS_HOME", str(tmp_path))
    monkeypatch.setattr("egzos.authz.presence.is_terminal", lambda: False)  # an agent's pipe
    assert main(["init"]) == 0
    capsys.readouterr()
    assert main(["--json", "connect"]) != 0
    assert "egz_" not in capsys.readouterr().out
    assert main(["--json", "token", "ls"]) == 0
    assert [t for t in json.loads(capsys.readouterr().out) if t["principal"] == "client"] == []


def test_connect_refuses_admin(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("EGZOS_HOME", str(tmp_path))
    assert main(["init"]) == 0
    assert main(["connect", "--role", "admin"]) != 0


def test_container_home_is_owner_only(tmp_path, monkeypatch):
    import stat

    home = tmp_path / "home"
    monkeypatch.setenv("EGZOS_HOME", str(home))
    assert main(["init"]) == 0
    assert stat.S_IMODE(home.stat().st_mode) == 0o700


def test_ls_refuses_inbox_with_a_scope(tmp_path, monkeypatch):
    monkeypatch.setenv("EGZOS_HOME", str(tmp_path))
    monkeypatch.delenv("EGZOS_TOKEN", raising=False)
    assert main(["init"]) == 0
    assert main(["ls", "--inbox", "--scope", "user:self"]) != 0
    assert main(["ls", "--inbox"]) == 0


def test_token_revoke_takes_a_client_token_back(tmp_path, monkeypatch, capsys):
    import json

    from egzos.container import Container

    monkeypatch.setenv("EGZOS_HOME", str(tmp_path))
    monkeypatch.delenv("EGZOS_TOKEN", raising=False)
    assert main(["init"]) == 0
    capsys.readouterr()
    assert main(["--json", "token", "create", "--client", "bot"]) == 0
    minted = json.loads(capsys.readouterr().out)
    c = Container(tmp_path)
    assert c.auth.use(minted["secret"]) is not None
    owner = c.auth.interactive_token()
    assert main(["token", "revoke", owner.id]) != 0  # never the owner's own key
    assert main(["token", "revoke", minted["id"]]) == 0
    assert c.auth.use(minted["secret"]) is None
    assert c.ledger.tail(1)[0]["event"] == "token.revoke"
    assert main(["token", "revoke", minted["id"]]) != 0


def test_an_expired_token_is_not_live(tmp_path):
    from egzos.container import OWNER, Container

    c = Container(tmp_path)
    c.init()
    t = c.auth.mint(principal="client", owner=OWNER, client="bot", role="reader",
                    scopes=["*"], actor=OWNER, by_principal="interactive")
    secret = t.secret
    stored = c.backend.get_token(t.id)
    for when, live in (("2000-01-01T00:00:00Z", False), ("2999-01-01T00:00:00Z", True),
                       ("not a date", False), (None, True)):
        stored.expires_at = when
        c.backend.put_token(stored)
        assert (c.auth.use(secret) is not None) is live, when
        assert c.backend.get_token(t.id).live is live
        assert c.trust.covers(c.backend.get_token(t.id), c.nodes.user_root()) is live


def test_token_ls_is_a_read_on_the_chain(tmp_path, monkeypatch):
    from egzos.container import Container

    monkeypatch.setenv("EGZOS_HOME", str(tmp_path))
    monkeypatch.delenv("EGZOS_TOKEN", raising=False)
    assert main(["init"]) == 0
    assert main(["token", "ls"]) == 0
    last = Container(tmp_path).ledger.tail(1)[0]
    assert last["event"] == "context.fetch" and last["details"]["view"] == "token ls"


def test_a_client_ls_records_what_the_policy_withheld(tmp_path, monkeypatch):
    from egzos.container import OWNER, Container

    monkeypatch.setenv("EGZOS_HOME", str(tmp_path))
    monkeypatch.delenv("EGZOS_TOKEN", raising=False)
    assert main(["init"]) == 0
    c = Container(tmp_path)
    owner = c.auth.interactive_token()
    bad = c.store.add(body="b", token=owner, actor=OWNER, principal="interactive")
    c.store.add(body="o", token=owner, actor=OWNER, principal="interactive")
    c.trust.quarantine(bad, token=owner, actor=OWNER, reason="x")
    bot = c.auth.mint(principal="client", owner=OWNER, client="bot", role="reader",
                      scopes=[c.nodes.inbox().id], actor=OWNER, by_principal="interactive")
    monkeypatch.setenv("EGZOS_TOKEN", bot.secret)
    assert main(["ls", "--inbox"]) == 0
    last = Container(tmp_path).ledger.tail(1)[0]["details"]
    assert last["view"] == "ls --inbox" and last["withheld"] == 1


def test_find_refuses_an_unknown_prefix_and_names_nothing(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("EGZOS_HOME", str(tmp_path))
    monkeypatch.delenv("EGZOS_TOKEN", raising=False)
    assert main(["init"]) == 0
    assert main(["add", "a note"]) == 0
    capsys.readouterr()
    assert main(["find", "colour:red"]) != 0  # an unknown prefix is refused (#128), not searched
    out = capsys.readouterr().out
    assert "a note" not in out
    assert main(["find", "kind:memory"]) == 0
