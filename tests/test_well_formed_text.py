# Copyright 2026 Ali Sasanian
# SPDX-License-Identifier: LicenseRef-PolyForm-Strict-1.0.0
"""rest.md §3: request strings must be well-formed Unicode with no U+0000. `malformed` is the one
check every door runs first, the REST door, the MCP tools and the CLI alike."""

from __future__ import annotations

import asyncio
import io
import json

import pytest
from fastapi.testclient import TestClient
from mcp import Client

from egzos._term import json_text
from egzos.api.app import create_app
from egzos.backends.base import holds_nul, malformed
from egzos.cli import main
from egzos.container import OWNER, Container
from egzos.mcp.server import build
from egzos.web.app import Lifeboat
from egzos.web.app import create_app as create_lifeboat


@pytest.mark.parametrize("value", [
    "\ud800", "\udfff", "a\udc80b", ["ok", "\ud83d"], {"k": "\ude00"}, {"\ud800": "v"},
    ("t", ["x", {"y": "\udbff"}]), "nul\0", ["\0"],
], ids=["high", "low", "inside", "list", "value", "key", "nested", "nul", "nul in list"])
def test_a_string_with_a_surrogate_or_u0000_anywhere_is_malformed(value):
    assert malformed(value)


@pytest.mark.parametrize("value", [
    "", "plain", "\U0001f600 a whole emoji", "�", "￿", {"k": ["v", 1, None, True]},
    "‮​", 3, None,
])
def test_every_scalar_value_is_well_formed(value):
    assert not malformed(value)


def test_holds_nul_still_names_u0000_alone():
    # storage.md §3.7's refusal is the store's own, about U+0000 only.
    assert holds_nul("a\0") and not holds_nul("\ud800")


def test_a_deep_nesting_is_walked_not_recursed():
    deep: list = ["\ud800"]
    for _ in range(100_000):
        deep = [deep]
    assert malformed(deep)


def test_a_pair_sent_as_two_escapes_is_one_scalar_value_and_well_formed(tmp_path):
    c = Container(tmp_path)
    owner = c.init()
    r = TestClient(create_app(c)).post(
        "/v1/items", headers={"Authorization": f"Bearer {owner.secret}",
                              "Content-Type": "application/json"},
        content=b'{"body":"smile \\ud83d\\ude00"}')
    assert r.status_code == 200 and r.json()["item"]["content"]["body"] == "smile \U0001f600"


def test_the_cli_refuses_an_argument_that_is_not_well_formed(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("EGZOS_HOME", str(tmp_path / ".egzos"))
    monkeypatch.delenv("EGZOS_TOKEN", raising=False)
    assert main(["init"]) == 0
    capsys.readouterr()
    assert main(["--json", "add", "x\udc80"]) == 2
    assert json.loads(capsys.readouterr().out) == {"error": "invalid_request"}


# -- what already holds such text is still served, and text keeps its characters ------------------
WORDS = "café ☕ שלום 日本"


def test_json_text_keeps_every_character_but_escapes_a_surrogate():
    value = {"t": WORDS, "s": "a" + "\ud800" + "b", "k": ["\ud800"]}
    text = json_text(value)
    assert WORDS in text and "\ud800" not in text and "\\ud800" in text
    text.encode("utf-8")
    assert json.loads(text) == value  # valid JSON, read back to the same values


def _held(tmp_path):
    c = Container(tmp_path)
    owner = c.init()
    project = c.nodes.create("project", "p", c.nodes.user_root(), token=owner, actor=OWNER,
                             principal="interactive")
    item = c.store.add(body=WORDS + "\nheld \ud800 text", tags=["\ud800"], scope=project,
                       token=owner, actor=OWNER, principal="interactive")
    return c, owner, project, item


def test_an_mcp_result_carries_text_as_itself_and_a_held_surrogate_as_its_escape(tmp_path):
    c, owner, project, _ = _held(tmp_path)

    async def go():
        async with Client(build(c, lambda: owner)) as client:
            return await client.call_tool("egzos_fetch", {"scope": project.id})

    r = asyncio.run(go())
    text = r.content[0].text
    assert not r.is_error and WORDS in text and "\\ud800" in text
    r.model_dump_json().encode("utf-8")
    assert "\ud800" in json.loads(text)["items"][0]["content"]


def test_the_clis_json_output_serves_an_item_holding_a_surrogate(tmp_path, monkeypatch, capsys):
    home = tmp_path / ".egzos"
    monkeypatch.setenv("EGZOS_HOME", str(home))
    monkeypatch.delenv("EGZOS_TOKEN", raising=False)
    assert main(["init"]) == 0
    c = Container(home)
    owner = c.require_token()
    c.store.add(body=WORDS + "\nheld \ud800 text", tags=["\ud800"], token=owner, actor=OWNER,
                principal="interactive")
    for argv in (["ls", "--inbox"], ["find", "held"], ["fetch", "inbox"]):
        capsys.readouterr()
        assert main(["--json", *argv]) == 0, argv
        json.loads(capsys.readouterr().out)
        assert main(argv) == 0, argv


def test_the_lifeboat_serves_an_item_holding_a_surrogate(tmp_path):
    c, _, _, item = _held(tmp_path)
    boat = Lifeboat(c, key="k" * 32, host="testserver")
    client = TestClient(create_lifeboat(boat, "http://testserver"), base_url="http://testserver")
    assert client.get(f"/?k={boat.key}", follow_redirects=False).status_code == 303
    for path in ("/", "/?q=held", f"/items/{item.id}"):
        r = client.get(path)
        assert r.status_code == 200, path
    assert "held \ufffd text" in r.text  # drawn as U+FFFD on the item's page


def test_add_from_standard_input_refuses_text_that_is_not_well_formed(
        tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("EGZOS_HOME", str(tmp_path / ".egzos"))
    monkeypatch.delenv("EGZOS_TOKEN", raising=False)
    assert main(["init"]) == 0
    monkeypatch.setattr("sys.stdin", io.StringIO("a title\nx \ud800 y"))
    capsys.readouterr()
    assert main(["--json", "add", "-"]) == 2
    assert json.loads(capsys.readouterr().out) == {"error": "invalid_request"}
    assert Container(tmp_path / ".egzos").store.inbox_items() == []
