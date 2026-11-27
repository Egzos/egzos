# Copyright 2026 Ali Sasanian
# SPDX-License-Identifier: LicenseRef-PolyForm-Strict-1.0.0
"""rest.md §4.5, "A name's shape": a place's name, made on any surface, is 1 to 255 scalar values
with no `/`, no `:`, no Cc, Zl or Zp character, no Bidi_Control and no lone surrogate, and is never
`*`. The door answers anything else `400` before any lookup, `NodeService.create` and `egzoscore
mk` refuse it, and pure capture rewrites a title in three steps. Names given before stay."""

from __future__ import annotations

import json

import pytest
from fastapi.testclient import TestClient

from egzos.api.app import create_app
from egzos.cli import main
from egzos.container import OWNER, Container
from egzos.store.nodes import BIDI_CONTROL, InvalidName, capture_name, valid_name

KW = {"actor": OWNER, "principal": "interactive"}
INVALID = b'{"error":"invalid_request"}'

#: One of each class the rule bars, by name.
BARRED = {
    "slash": "a/b",
    "colon": "a:b",
    "nul (Cc)": "a\x00b",
    "tab (Cc)": "a\tb",
    "newline (Cc)": "a\nb",
    "delete (Cc)": "a\x7fb",
    "C1 next line (Cc)": "a\x85b",
    "C1 control (Cc)": "a\x9bb",
    "line separator (Zl)": "a\u2028b",
    "paragraph separator (Zp)": "a\u2029b",
    "lone high surrogate": "a\ud800b",
    "lone low surrogate": "a\udfffb",
    "empty": "",
    "too long": "x" * 256,
    "the one character *": "*",
    **{f"bidi control U+{ord(ch):04X}": f"a{ch}b" for ch in sorted(BIDI_CONTROL)},
}
#: Names the rule leaves as they are: formatting characters other than Bidi_Control, look-alikes,
#: names that only hold `*` beside other characters, and 255 scalar values beyond the BMP.
KEPT = ["health", "a*", "**", "zero\u200bwidth", "joiner\u200d", "Cafe\u0301", "e\u0301",
        "\U0001f600" * 255, "x" * 255, " leading space", "dot.dot", "-", "a\\b"]


class Titles:
    """A titler that returns what it is told: what an engine might make of a writer's text."""

    name = "test"

    def __init__(self, title: str):
        self.text = title

    def title(self, **_):
        return self.text


@pytest.fixture
def c(tmp_path):
    box = Container(tmp_path)
    box.owner = box.init()
    return box


@pytest.fixture
def door(c):
    return TestClient(create_app(c))


def _auth(c):
    return {"Authorization": f"Bearer {c.owner.secret}"}


def test_the_bidi_controls_are_exactly_unicodes_twelve():
    # PropList.txt's Bidi_Control: U+061C, U+200E-U+200F, U+202A-U+202E, U+2066-U+2069.
    expected = {0x061C, 0x200E, 0x200F, *range(0x202A, 0x202F), *range(0x2066, 0x206A)}
    assert {ord(ch) for ch in BIDI_CONTROL} == expected


@pytest.mark.parametrize("name", list(BARRED.values()), ids=list(BARRED))
def test_a_barred_name_is_refused_by_the_rule(name):
    assert not valid_name(name)


@pytest.mark.parametrize("name", KEPT)
def test_the_rule_keeps_every_other_name_as_given(name):
    assert valid_name(name)


@pytest.mark.parametrize("value", [None, 1, ["a"], {"a": 1}, True])
def test_a_name_that_is_not_a_string_is_refused(value):
    assert not valid_name(value)


@pytest.mark.parametrize("name", list(BARRED.values()), ids=list(BARRED))
def test_the_store_refuses_a_barred_name_and_writes_nothing(c, name):
    before = c.backend.list_nodes()
    with pytest.raises(InvalidName):
        c.nodes.create("project", name, c.nodes.user_root(), token=c.owner, **KW)
    assert c.backend.list_nodes() == before


@pytest.mark.parametrize("name", list(BARRED.values()), ids=list(BARRED))
def test_the_door_answers_400_before_any_lookup(c, door, name):
    entries = c.ledger.tail(1)[-1]["seq"]
    # A parent that does not exist: the 400 comes first, so it never depends on what exists.
    for parent in ({}, {"parent": "project:nowhere"}):
        r = door.post("/v1/scopes", headers=_auth(c),
                      content=json.dumps({"type": "project", "name": name, **parent}))
        assert (r.status_code, r.content) == (400, INVALID)
    assert c.ledger.tail(1)[-1]["seq"] == entries  # no probe: the request was never looked at


@pytest.mark.parametrize("name", KEPT)
def test_the_door_makes_a_place_whose_name_keeps_the_rule_as_given(door, c, name):
    r = door.post("/v1/scopes", headers=_auth(c), json={"type": "project", "name": name})
    assert r.status_code == 200 and r.json()["node"]["name"] == name
    assert c.backend.get_node(r.json()["node"]["id"]).name == name  # no normalisation


def test_two_places_side_by_side_may_still_share_a_name(door, c):
    for _ in range(2):
        assert door.post("/v1/scopes", headers=_auth(c),
                         json={"type": "project", "name": "twin"}).status_code == 200


@pytest.mark.parametrize("name", ["a/b", "a:b", "a\u202eb", "*", "a\tb"])
def test_mk_refuses_a_barred_name_in_the_doors_word(tmp_path, monkeypatch, capsys, name):
    monkeypatch.setenv("EGZOS_HOME", str(tmp_path / ".egzos"))
    monkeypatch.delenv("EGZOS_TOKEN", raising=False)
    monkeypatch.chdir(tmp_path)
    assert main(["init"]) == 0
    before = len(Container(tmp_path / ".egzos").backend.list_nodes())
    capsys.readouterr()
    assert main(["--json", "mk", "project", name]) == 2
    assert json.loads(capsys.readouterr().out) == {"error": "invalid_request"}
    assert len(Container(tmp_path / ".egzos").backend.list_nodes()) == before
    assert main(["mk", "project", "fine"]) == 0


def test_a_name_given_before_the_rule_stays_as_it_is(c, door):
    old = c.nodes.create("project", "ok", c.nodes.user_root(), token=c.owner, **KW)
    old.name = "before: the rule"  # as an older container wrote it
    c.backend.put_node(old)
    nodes = door.get("/v1/scopes", headers=_auth(c)).json()["nodes"]
    assert "before: the rule" in [n["name"] for n in nodes]
    assert door.get(f"/v1/scopes?under={old.id}", headers=_auth(c)).status_code == 200
    # It still takes what is made and written in it: the rule reaches a name given, not a place.
    made = door.post("/v1/scopes", headers=_auth(c),
                     json={"type": "thread", "name": "inside", "parent": old.id})
    assert made.status_code == 200 and made.json()["node"]["parent"] == old.id
    wrote = door.post("/v1/items", headers=_auth(c), json={"body": "a note", "scope": old.id})
    assert wrote.status_code == 200 and wrote.json()["item"]["scope"] == old.id


# -- pure capture's three steps --------------------------------------------------------------------
@pytest.mark.parametrize(("title", "name"), [
    ("plain words", "plain words"),
    ("a/b:c", "a-b-c"),  # step 1: `/` and `:` become `-`
    ("tab\there\nnew\x7fline\x85", "tabherenewline"),  # step 1: Cc dropped, C1 included
    ("lines\u2028and\u2029paras", "linesandparas"),  # Zl and Zp dropped
    ("\u202egnp.exe\u2066x\u2069\u200e\u061c", "gnp.exex"),  # every Bidi_Control dropped
    ("lone\ud800half", "lonehalf"),  # a lone surrogate is dropped with them
    ("zero\u200bwidth stays", "zero\u200bwidth stays"),  # other formatting is left
    ("x" * 39 + "/" + "y" * 10, "x" * 39 + "-"),  # step 2 counts after step 1
    ("\x01" * 50 + "z" * 45, "z" * 40),  # dropped characters free their room first
])
def test_capture_rewrites_then_keeps_forty(title, name):
    assert capture_name(title, "01ITEM") == name


@pytest.mark.parametrize("title", ["", "\n\t\x00", "\u202e\u2069", "*", "\n*\u200e"])
def test_capture_falls_back_to_the_items_id_when_nothing_or_only_a_star_is_left(title):
    assert capture_name(title, "01ITEMID") == "01ITEMID"


def test_capture_never_makes_a_name_the_rule_refuses(c):
    hostile = "a/b:c\u202e\u2028\x00" + "*" * 60
    for title in (hostile, "*", "", "/" * 41):
        c.store.titler = Titles(title)
        item = c.store.add(body="anything", token=c.owner, **KW)
        thread = c.backend.get_node(item.scope)
        assert thread.type == "thread" and valid_name(thread.name)
        assert thread.name == capture_name(title, item.id)


def test_a_captured_thread_with_no_title_left_is_named_by_its_item(c):
    c.store.titler = Titles("\u202e\n")
    item = c.store.add(body="x", token=c.owner, **KW)
    assert c.backend.get_node(item.scope).name == item.id
