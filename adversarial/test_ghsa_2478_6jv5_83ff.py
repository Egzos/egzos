# Copyright 2026 Ali Sasanian
# SPDX-License-Identifier: LicenseRef-PolyForm-Strict-1.0.0
"""GHSA-2478-6jv5-83ff: an act's record and its chain entry land together or not at all, so a
writer that takes the container's write lock between them never leaves the record without its
entry. The other writer is a second connection to the same home, as a second process has."""

from __future__ import annotations

import sqlite3

import pytest

from egzos.container import OWNER, Container

pytestmark = pytest.mark.adversarial

KW = {"actor": OWNER, "principal": "interactive"}


@pytest.fixture
def c(tmp_path):
    box = Container(tmp_path)
    box.init()
    box.backend.db.execute("PRAGMA busy_timeout = 50")  # a twentieth of a second, not ten
    return box


def _between(c, method, monkeypatch):
    """After the act's first record write, a second connection tries to take the write lock and,
    if it gets it, keeps it until the act is over."""
    held = []
    write = getattr(c.backend, method)

    def wrapped(*args, **kwargs):
        out = write(*args, **kwargs)
        if not held:
            other = sqlite3.connect(str(c.home / "egzos.db"), timeout=0.05)
            try:
                other.execute("BEGIN IMMEDIATE")
            except sqlite3.OperationalError:  # the act holds the lock: nothing comes between
                other.close()
                held.append(None)
            else:
                held.append(other)
        return out

    monkeypatch.setattr(c.backend, method, wrapped)
    return held


def _act(held, act):
    try:
        act()
    except Exception:  # noqa: BLE001 — a busy refusal is an answer; what landed is the question
        pass
    finally:
        for other in held:
            if other is not None:
                other.rollback()
                other.close()


def _logged(c, event):
    return {e["subject"] for e in c.ledger.tail(10_000) if e["event"] == event}


def test_ghsa_2478_6jv5_83ff_an_item_never_lands_without_its_entry(c, monkeypatch):
    owner = c.auth.interactive_token()
    held = _between(c, "put", monkeypatch)
    _act(held, lambda: c.store.add(body="between", token=owner, **KW))
    stored = {i.id for i in c.backend.query([n.id for n in c.backend.list_nodes()])}
    assert stored == _logged(c, "item.add")


def test_ghsa_2478_6jv5_83ff_a_scope_never_lands_without_its_entry(c, monkeypatch):
    owner = c.auth.interactive_token()
    before = {n.id for n in c.backend.list_nodes()}
    held = _between(c, "put_node", monkeypatch)
    _act(held, lambda: c.nodes.create("project", "between", c.nodes.user_root(), token=owner,
                                      **KW))
    made = {n.id for n in c.backend.list_nodes()} - before
    assert made == _logged(c, "node.create") - before


def test_ghsa_2478_6jv5_83ff_a_token_never_lands_without_its_entry(c, monkeypatch):
    held = _between(c, "put_token", monkeypatch)
    _act(held, lambda: c.auth.mint(principal="client", owner=OWNER, client="bot", role="reader",
                                   scopes=["*"], actor=OWNER, by_principal="interactive"))
    assert {t.id for t in c.backend.list_tokens()} == _logged(c, "token.mint")
