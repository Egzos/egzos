# Copyright 2026 Ali Sasanian
# SPDX-License-Identifier: Apache-2.0
"""`egzos connect` mints a client principal and prints the Claude Code wiring."""

from __future__ import annotations

import json

from egzos.cli import main


def test_connect_mints_a_client_token_and_prints_the_command(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("EGZOS_HOME", str(tmp_path))
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
