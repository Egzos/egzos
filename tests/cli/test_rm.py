# Copyright 2026 Ali Sasanian
# SPDX-License-Identifier: LicenseRef-PolyForm-Strict-1.0.0
"""`egzos rm`: the owner token tombstones an item no person has promoted, and the chain records it
as the door's does. A promoted item is the door's, where the confirm asks the person (rest.md
§4)."""

from __future__ import annotations

import hashlib
import json

import pytest

from egzos.cli import main
from egzos.container import OWNER, Container

KW = {"actor": OWNER, "principal": "interactive"}


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


def _agent(c):
    return c.auth.mint(principal="client", owner=OWNER, client="agent", role="admin",
                       scopes=["*"], actor=OWNER, by_principal="interactive")


def test_rm_tombstones_an_unpromoted_item_without_the_confirm(home, capsys):
    c = Container(home)
    note = c.store.add(body="draft", token=c.require_token(), **KW)
    assert _json(capsys, ["rm", note.id]) == (0, {"id": note.id, "tombstoned": True})
    c = Container(home)
    assert c.store.get(note.id) is None
    tail = c.ledger.tail(3)
    assert [e["event"] for e in tail][-1] == "item.tombstone" and "step_up" not in [
        e["event"] for e in tail]
    assert (tail[-1]["actor"], tail[-1]["details"]) == (OWNER, {"kind": "memory",
                                                                "status": "unverified"})
    assert _json(capsys, ["rm", note.id]) == (1, {"error": "not found"})


@pytest.mark.parametrize("lowered", [False, True])
def test_rm_refuses_a_promoted_item_whatever_its_status_now(home, capsys, lowered):
    """Any process that can run the terminal could run `rm`: a promoted item goes only at the door,
    where the confirm asks the person, even once a move has lowered its status."""
    c = Container(home)
    note = c.store.add(body="curated", token=c.require_token(), **KW)
    c.trust.promote(note, token=c.require_token(), actor=OWNER)
    if lowered:
        item = c.backend.get(note.id)
        item.trust["status"] = "unverified"  # as a move lowers it; the approval stays on provenance
        c.backend.put(item)
    before = c.ledger.tail(1)[0]["seq"]
    code, out = _json(capsys, ["rm", note.id])
    assert code == 1 and "door" in out["error"]
    c = Container(home)
    assert c.store.get(note.id) is not None
    assert "item.tombstone" not in [e["event"] for e in c.ledger.tail(5) if e["seq"] > before]


def test_rm_takes_an_agents_staged_file_with_it(home, capsys):
    c = Container(home)
    agent, data = _agent(c), b"staged\n"
    sha = hashlib.sha256(data).hexdigest()
    record = c.uploads.open(agent, scope=c.nodes.user_root(), name="f", mime="text/plain",
                            size=len(data), sha256=sha)
    assert c.uploads.put(agent, record["id"], data) == "staged"
    item = c.uploads.item(agent, record["id"], scope=None, key=None, tags=[])
    assert _json(capsys, ["rm", item.id])[0] == 0
    assert not (home / "blobs" / "staging" / sha).exists()
    assert Container(home).ledger.tail(1)[0]["details"]["staged_deleted"] == sha


def test_rm_refuses_a_quarantined_item_and_any_token_but_the_owners(home, capsys, monkeypatch):
    c = Container(home)
    owner = c.require_token()
    note, bad = (c.store.add(body=b, token=owner, **KW) for b in ("kept", "bad"))
    c.trust.quarantine(bad, token=owner, actor=OWNER, reason="poisoned")
    assert _json(capsys, ["rm", bad.id]) == (1, {"error": "not found"})  # as an absent one
    bo = c.auth.mint(principal="interactive", owner="user:bo", client="tab", role="operator",
                     scopes=["*"], actor=OWNER, by_principal="interactive")
    for token in (_agent(c), bo):  # a client principal; a person without `admin` over the whole
        monkeypatch.setenv("EGZOS_TOKEN", token.secret)
        assert _json(capsys, ["rm", note.id])[0] == 1
    c = Container(home)
    assert c.store.get(note.id) is not None and c.store.get(bad.id) is not None
    assert not [e for e in c.ledger.tail(20) if e["event"] == "item.tombstone"]
