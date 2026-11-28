# Copyright 2026 Ali Sasanian
# SPDX-License-Identifier: LicenseRef-PolyForm-Strict-1.0.0
"""rest.md §4.4 item 1: a file's name holds no control, line-separator or bidi-control character,
that is no character of category Cc, Zl or Zp and none with the Bidi_Control property. An upload's
open answers a name that breaks it with §3's `400` before any lookup, so the answer is the same
whether or not its scope exists. A name is display data only, so `/`, `:` and `*` stay, and a name
stored before the rule ran is served as stored. The owner's local add of a file from disk keeps
the same rule."""

from __future__ import annotations

import hashlib

import pytest
from fastapi.testclient import TestClient

from egzos.api.app import create_app
from egzos.container import OWNER, Container
from egzos.store.items import StoreError
from egzos.store.nodes import BIDI_CONTROL

INVALID = b'{"error":"invalid_request"}'
KW = {"actor": OWNER, "principal": "interactive"}
DATA = b"a note, as a file\n"
BARRED = {
    "bell U+0007": "a\u0007b", "tab U+0009": "a\tb", "line feed U+000A": "a\nb",
    "delete U+007F": "a\x7fb", "next line U+0085": "a\x85b", "line separator U+2028": "a\u2028b",
    "paragraph separator U+2029": "a\u2029b", "right-to-left override U+202E": "a\u202eb",
    "left-to-right isolate U+2066": "a\u2066b", "arabic letter mark U+061C": "a\u061cb",
}


@pytest.fixture
def c(tmp_path):
    box = Container(tmp_path)
    box.owner = box.init()
    return box


@pytest.fixture
def door(c):
    return TestClient(create_app(c))


@pytest.fixture
def notes(c):
    return c.nodes.create("project", "notes", c.nodes.user_root(), token=c.owner, **KW)


def _open(door, token, scope, name):
    body = {"scope": scope, "name": name, "mime": "text/plain", "size": len(DATA),
            "sha256": hashlib.sha256(DATA).hexdigest()}
    return door.post("/v1/uploads", headers={"Authorization": f"Bearer {token.secret}"}, json=body)


@pytest.mark.parametrize("name", BARRED.values(), ids=BARRED.keys())
def test_a_name_with_a_control_line_or_bidi_character_is_400_before_any_lookup(c, door, notes,
                                                                                name):
    head = c.ledger.tail(1)[-1]["seq"]
    for scope in (notes.id, "01HZZZZZZZZZZZZZZZZZZZZZZZ"):  # one that exists, one that does not
        r = _open(door, c.owner, scope, name)
        assert (r.status_code, r.content) == (400, INVALID)
    assert c.ledger.tail(1)[-1]["seq"] == head  # no probe: nothing was looked up
    assert c.backend.list_uploads() == []


def test_every_control_character_and_every_bidi_control_is_refused(c, door, notes):
    for ch in [chr(n) for n in (*range(0x20), *range(0x7F, 0xA0))] + sorted(BIDI_CONTROL):
        assert _open(door, c.owner, notes.id, f"report{ch}.pdf").status_code == 400, hex(ord(ch))


@pytest.mark.parametrize("name", ["a/b:c*.txt", "résumé 履歴書.pdf",
                                  "\U0001f469\u200d\U0001f4bb.png", "x" * 255])
def test_a_name_is_display_data_and_keeps_every_other_character(c, door, notes, name):
    r = _open(door, c.owner, notes.id, name)
    assert r.status_code == 200
    assert c.backend.get_upload(r.json()["upload"])["name"] == name


def test_a_name_stored_before_the_rule_is_served_as_stored(c, door, notes):
    uid = _open(door, c.owner, notes.id, "note.txt").json()["upload"]
    old = "a\u202eb"  # an upload recorded before the rule ran
    c.backend.put_upload({**c.backend.get_upload(uid), "name": old})
    auth = {"Authorization": f"Bearer {c.owner.secret}"}
    assert door.put(f"/v1/uploads/{uid}", headers=auth, content=DATA).status_code == 200
    r = door.post("/v1/items", headers=auth, json={"kind": "artifact", "upload": uid})
    assert r.status_code == 200 and r.json()["item"]["content"]["filename"] == old
    r = door.get(f"/v1/items/{r.json()['item']['id']}", headers=auth)
    assert r.status_code == 200 and r.json()["item"]["content"]["filename"] == old


def test_the_owners_local_add_refuses_a_barred_name_and_keeps_a_colon(c, notes, tmp_path):
    path = tmp_path / "a\u202eb"
    path.write_bytes(DATA)
    head = c.ledger.tail(1)[-1]["seq"]
    with pytest.raises(StoreError):
        c.store.add(file=path, scope=notes, token=c.owner, **KW)
    assert c.ledger.tail(1)[-1]["seq"] == head
    assert c.blobs.get(hashlib.sha256(DATA).hexdigest()) is None
    fine = tmp_path / "a:b*.pdf"  # display data: `:` and `*` stay
    fine.write_bytes(DATA)
    assert c.store.add(file=fine, scope=notes, token=c.owner, **KW).content["filename"] == fine.name
