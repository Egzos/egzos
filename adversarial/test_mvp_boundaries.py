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


# --- a client is served, never shown the store ---
def _json(r):
    assert r.returncode == 0, r.stderr
    return json.loads(r.stdout)


def test_a_clients_ls_is_served_under_the_policy(tmp_path):
    assert _egzos(tmp_path, "init").returncode == 0
    rule = _json(_egzos(tmp_path, "--json", "add", "unverified rule", "--kind", "rule"))
    bad = _json(_egzos(tmp_path, "--json", "add", "poisoned"))
    ok = _json(_egzos(tmp_path, "--json", "add", "plain memory"))
    assert _egzos(tmp_path, "trust", "quarantine", bad["id"], "--reason", "x").returncode == 0
    secret = _json(_egzos(tmp_path, "--json", "token", "create", "--client", "bot",
                          "--role", "reader", "--scope", "inbox:inbox"))["secret"]
    listed = {i["id"] for i in _json(_egzos(tmp_path, "--json", "ls", "--inbox", token=secret))}
    assert ok["id"] in listed and rule["id"] not in listed and bad["id"] not in listed


@pytest.mark.parametrize("argv", [
    ("fetch", "{ref}"), ("cd", "{ref}"), ("mk", "thread", "t", "--in", "{ref}"),
    ("ls", "--scope", "{ref}"),
])
def test_every_scope_verb_answers_uncovered_like_absent(tmp_path, argv):
    assert _egzos(tmp_path, "init").returncode == 0
    hidden = _json(_egzos(tmp_path, "--json", "mk", "project", "hidden"))
    secret = _json(_egzos(tmp_path, "--json", "token", "create", "--client", "bot",
                          "--role", "curator", "--scope", "inbox:inbox"))["secret"]
    answers = []
    for ref in (hidden["id"], "01HZZZZZZZZZZZZZZZZZZZZZZZ"):
        r = _egzos(tmp_path, *(a.format(ref=ref) for a in argv), token=secret)
        answers.append((r.returncode, r.stdout.replace(ref, "<ref>"), r.stderr))
    assert answers[0] == answers[1] and "hidden" not in answers[0][1]


def test_item_verbs_answer_uncovered_like_absent(tmp_path):
    assert _egzos(tmp_path, "init").returncode == 0
    proj = _json(_egzos(tmp_path, "--json", "mk", "project", "hidden"))
    item = _json(_egzos(tmp_path, "--json", "add", "theirs", "--scope", proj["id"]))
    secret = _json(_egzos(tmp_path, "--json", "token", "create", "--client", "bot",
                          "--role", "curator", "--scope", "inbox:inbox"))["secret"]
    for argv in (("mv", "{ref}", "inbox:inbox"), ("trust", "quarantine", "{ref}", "--reason", "x")):
        answers = []
        for ref in (item["id"], "01HZZZZZZZZZZZZZZZZZZZZZZZ"):
            r = _egzos(tmp_path, *(a.format(ref=ref) for a in argv), token=secret)
            answers.append((r.returncode, r.stdout, r.stderr))
        assert answers[0] == answers[1] and answers[0][0] != 0
    owner_view = _json(_egzos(tmp_path, "--json", "ls", "--scope", proj["id"]))
    assert [i["trust"]["status"] for i in owner_view] == ["unverified"]  # untouched


def test_the_engine_checks_coverage_whatever_the_surface(box):
    owner = box.auth.interactive_token()
    root = box.nodes.user_root()
    hidden = box.nodes.create("project", "hidden", root, token=owner, actor=OWNER,
                              principal="interactive")
    item = box.store.add(body="theirs", scope=hidden, token=owner, actor=OWNER,
                         principal="interactive")
    bot = _client(box, role="curator")
    from egzos.store.nodes import StructureError
    from egzos.trust import TrustError

    with pytest.raises(StructureError, match="scope not found"):
        box.nodes.create("thread", "t", hidden, token=bot, actor="bot", principal="client")
    with pytest.raises(TrustError, match="not found"):
        box.trust.move(item, box.nodes.inbox(), token=bot, actor="bot")
    with pytest.raises(TrustError, match="not found"):
        box.trust.quarantine(item, token=bot, actor="bot", reason="x")
    served = box.resolver.resolve(hidden, token=bot, actor="bot")
    assert served == {"scope": None, "chain": [], "items": [], "withheld": 0}
    assert box.nodes.resolve_ref("project:hidden", bot) is None
    assert box.nodes.resolve_ref(hidden.id, bot) is None


def test_an_invisible_node_never_breaks_a_tie(box):
    owner = box.auth.interactive_token()
    root = box.nodes.user_root()
    mine = box.nodes.create("project", "p", box.nodes.inbox(), token=owner, actor=OWNER,
                            principal="interactive")
    theirs = box.nodes.create("project", "p", root, token=owner, actor=OWNER,
                              principal="interactive")
    box.store.add(body="recent", scope=theirs, token=owner, actor=OWNER, principal="interactive")
    bot = _client(box)
    assert box.nodes.resolve_ref("project:p", bot).id == mine.id


def test_percent_n_belongs_to_the_principal_that_found_it(tmp_path):
    assert _egzos(tmp_path, "init").returncode == 0
    mine = _json(_egzos(tmp_path, "--json", "add", "owner picks this"))
    _json(_egzos(tmp_path, "--json", "add", "bot would pick this"))
    assert _egzos(tmp_path, "find", "owner picks").returncode == 0
    secret = _json(_egzos(tmp_path, "--json", "token", "create", "--client", "bot",
                          "--role", "reader", "--scope", "inbox:inbox"))["secret"]
    assert _egzos(tmp_path, "find", "bot would", token=secret).returncode == 0
    r = _egzos(tmp_path, "--json", "trust", "quarantine", "%1", "--reason", "owner's %1")
    assert _json(r)["affected"] == [mine["id"]]


def test_the_mcp_inbox_serves_no_quarantined_item_and_no_unverified_rule(box):
    owner = box.auth.interactive_token()
    rule = box.store.add(body="r", kind="rule", token=owner, actor=OWNER, principal="interactive")
    bad = box.store.add(body="b", token=owner, actor=OWNER, principal="interactive")
    ok = box.store.add(body="o", token=owner, actor=OWNER, principal="interactive")
    box.trust.quarantine(bad, token=owner, actor=OWNER, reason="x")
    ids = {i["id"] for i in _call(build_server(box, _client(box)), "egzos_inbox", {})["items"]}
    assert ok.id in ids and rule.id not in ids and bad.id not in ids


# --- round 3: approve what you saw; report only what the caller may see ---
def test_cli_promotes_the_item_the_page_showed_even_if_percent_n_moves(tmp_path, monkeypatch):
    from egzos.authz import presence
    from egzos.cli import main

    monkeypatch.setenv("EGZOS_HOME", str(tmp_path))
    monkeypatch.delenv("EGZOS_TOKEN", raising=False)
    assert main(["init"]) == 0
    c = Container(tmp_path)
    owner = c.auth.interactive_token()
    seen = c.store.add(body="the one I saw", token=owner, actor=OWNER, principal="interactive")
    other = c.store.add(body="swapped in", token=owner, actor=OWNER, principal="interactive")
    (tmp_path / f"last-find-{owner.id}.json").write_text(json.dumps({"1": seen.id}))

    def swap_then_approve(self, act, **kw):
        assert act["subject"] == seen.id
        (tmp_path / f"last-find-{owner.id}.json").write_text(json.dumps({"1": other.id}))
        return "approved"

    monkeypatch.setattr(presence.Presence, "require", swap_then_approve)
    assert main(["trust", "approve", "%1"]) == 0
    assert c.backend.get(seen.id).status == "verified"
    assert c.backend.get(other.id).status == "unverified"


def test_quarantine_reports_only_ids_the_caller_covers(box):
    owner = box.auth.interactive_token()
    hidden = box.nodes.create("project", "hidden", box.nodes.user_root(), token=owner,
                              actor=OWNER, principal="interactive")
    src = box.store.add(body="src", token=owner, actor=OWNER, principal="interactive")
    copy = box.store.add(body="copy", scope=hidden, token=owner, actor=OWNER,
                         principal="interactive")
    copy.provenance["derived_from"] = src.id
    box.backend.put(copy)
    bot = _client(box, role="curator")
    assert box.trust.quarantine(src, token=bot, actor="bot", reason="x") == [src.id]
    assert box.backend.get(copy.id).status == "quarantined"  # propagation is not narrowed
    assert box.ledger.tail(1)[0]["details"]["affected"] == [src.id, copy.id]


def test_connect_apply_json_never_echoes_the_secret(tmp_path, monkeypatch, capsys):
    from egzos.cli import main

    monkeypatch.setenv("EGZOS_HOME", str(tmp_path))
    monkeypatch.delenv("EGZOS_TOKEN", raising=False)
    monkeypatch.setattr("egzos.cli.shutil.which", lambda name: f"/usr/bin/{name}")
    monkeypatch.setattr("egzos.cli.subprocess.run", lambda *a, **k: None)
    assert main(["init"]) == 0
    capsys.readouterr()
    assert main(["--json", "connect", "--apply"]) == 0
    assert "egz_" not in capsys.readouterr().out


def test_init_never_mints_a_second_owner(tmp_path):
    assert _egzos(tmp_path, "init").returncode == 0
    keychain = (tmp_path / "keychain.json").read_text()
    r = _egzos(tmp_path, "init", token="egz_01HZZZZZZZZZZZZZZZZZZZZZZZ_forged")
    assert r.returncode != 0
    assert (tmp_path / "keychain.json").read_text() == keychain
    owners = [t for t in json.loads(_egzos(tmp_path, "--json", "token", "ls").stdout)
              if t["principal"] == "interactive"]
    assert len(owners) == 1
