# Copyright 2026 Ali Sasanian
# SPDX-License-Identifier: Apache-2.0
"""Standing targets for the MVP's boundaries: a client principal never widens itself, never reads
the owner's views, and learns nothing from the MCP door about scopes it cannot see."""

from __future__ import annotations

import asyncio
import json
import os
import subprocess
import sys

import pytest

from egzos.auth import AuthError
from egzos.container import OWNER, Container
from egzos.mcp.server import build_server

pytestmark = pytest.mark.adversarial


@pytest.fixture()
def box(tmp_path):
    c = Container(tmp_path / "home")
    c.init()
    return c


def _client(c: Container, role: str = "contributor", scopes: list[str] | None = None):
    return c.auth.mint(
        principal="client", owner=OWNER, client="bot", role=role,
        scopes=scopes or [c.nodes.inbox().id], actor=OWNER, by_principal="interactive",
    )


def _egzos(home, *args, token=None):
    env = {k: v for k, v in os.environ.items() if k != "EGZOS_TOKEN"}
    env["EGZOS_HOME"] = str(home)
    if token:
        env["EGZOS_TOKEN"] = token
    return subprocess.run([sys.executable, "-m", "egzos.cli", *args], capture_output=True,
                          text=True, env=env, timeout=60)


# --- minting is the owner's act ---
def test_a_client_principal_cannot_mint(box):
    bot = _client(box, role="curator", scopes=["*"])
    with pytest.raises(AuthError):
        box.auth.mint(principal="client", owner=OWNER, client="wider", role="curator",
                      scopes=["*"], actor="bot", by_principal=bot.principal)


@pytest.mark.parametrize("argv", [
    ("connect", "claude-code", "--role", "curator"),
    ("token", "create", "--client", "x", "--role", "curator"),
])
def test_a_client_token_cannot_mint_through_the_cli(tmp_path, argv):
    assert _egzos(tmp_path, "init").returncode == 0
    secret = json.loads(_egzos(tmp_path, "--json", "token", "create", "--client", "bot",
                               "--role", "curator").stdout)["secret"]
    before = len(json.loads(_egzos(tmp_path, "--json", "token", "ls").stdout))
    r = _egzos(tmp_path, *argv, token=secret)
    assert r.returncode != 0
    assert len(json.loads(_egzos(tmp_path, "--json", "token", "ls").stdout)) == before


# --- the owner's views stay the owner's ---
@pytest.mark.parametrize("argv", [
    ("trust", "pending"), ("token", "ls"), ("audit", "tail"), ("audit", "verify"),
    ("trust", "close-window"),
])
def test_owner_views_refuse_a_client_principal(tmp_path, argv):
    assert _egzos(tmp_path, "init").returncode == 0
    secret = json.loads(_egzos(tmp_path, "--json", "token", "create", "--client", "bot",
                               "--role", "curator").stdout)["secret"]
    r = _egzos(tmp_path, *argv, token=secret)
    assert r.returncode != 0 and "owner" in (r.stdout + r.stderr)


def test_the_lifeboat_refuses_a_client_principal(box, monkeypatch):
    from egzos.web import serve_web

    monkeypatch.setenv("EGZOS_TOKEN", _client(box).secret)
    with pytest.raises(PermissionError):
        serve_web(box, port=0, open_browser=False)


def test_ls_of_an_uncovered_scope_answers_like_an_absent_one(tmp_path):
    assert _egzos(tmp_path, "init").returncode == 0
    assert _egzos(tmp_path, "mk", "project", "secret-plans").returncode == 0
    secret = json.loads(_egzos(tmp_path, "--json", "token", "create", "--client", "bot",
                               "--role", "reader", "--scope", "inbox:inbox").stdout)["secret"]
    hidden = _egzos(tmp_path, "ls", "--scope", "project:secret-plans", token=secret)
    absent = _egzos(tmp_path, "ls", "--scope", "project:no-such-thing", token=secret)
    assert (hidden.returncode, hidden.stdout, hidden.stderr) == (
        absent.returncode, absent.stdout, absent.stderr)


# --- the MCP door: one answer for "absent" and "not yours" ---
def _call(server, tool, args):
    r = asyncio.run(server.call_tool(tool, args))
    return json.loads(r.content[0].text)


def test_mcp_fetch_and_remember_cannot_tell_absent_from_uncovered(box):
    owner = box.auth.interactive_token()
    hidden = box.nodes.create("project", "hidden", box.nodes.user_root(), token=owner,
                              actor=OWNER, principal="interactive")
    server = build_server(box, _client(box))
    for tool, extra in (("egzos_fetch", {}), ("egzos_remember", {"text": "x"})):
        seen = []
        for ref in (hidden.id, "01HZZZZZZZZZZZZZZZZZZZZZZZ"):
            out = _call(server, tool, {**extra, "scope": ref})
            out.pop("scope", None)  # fetch echoes the caller's own input back, nothing more
            last = box.ledger.tail(1)[0]
            seen.append((out, last["event"], last["subject"], last["scope"]))
        assert seen[0] == seen[1], tool
    # the uncovered scope's path never leaks
    assert "hidden" not in json.dumps(_call(server, "egzos_fetch", {"scope": hidden.id}))


def test_blob_pull_checks_coverage_like_a_fetch(box, tmp_path):
    owner = box.auth.interactive_token()
    f = tmp_path / "secret.txt"
    f.write_text("not for the bot")
    item = box.store.add(file=f, token=owner, actor=OWNER, principal="interactive")
    bot = _client(box, role="reader", scopes=[box.nodes.global_root().id])
    assert box.store.blob_pull(item, token=bot, actor="bot", principal="client") is None
    assert box.store.blob_pull(item, token=owner, actor=OWNER, principal="interactive")
