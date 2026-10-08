# Copyright 2026 Ali Sasanian
# SPDX-License-Identifier: Apache-2.0
"""
Two adversarial follow-ups read off the running code: an artifact's bytes leave only by a path
the item itself would be served on (#135), and a container is initialized once, however many
`init`s race for it (#136).
"""

from __future__ import annotations

import threading
from pathlib import Path

import pytest

from egzos.container import OWNER, Container


@pytest.fixture()
def box(tmp_path: Path) -> Container:
    c = Container(tmp_path / "home")
    c.init()
    return c


def _artifact(box: Container, tmp_path: Path, **kw):
    f = tmp_path / "blob.txt"
    f.write_text("bytes")
    owner = box.auth.interactive_token()
    return owner, box.store.add(file=f, token=owner, actor=OWNER, principal="interactive", **kw)


def test_a_quarantined_artifact_is_never_pulled(box: Container, tmp_path: Path):
    owner, item = _artifact(box, tmp_path)
    assert box.store.blob_pull(item, token=owner, actor=OWNER, principal="interactive")
    box.trust.quarantine(item, token=owner, actor=OWNER, reason="poisoned")
    item = box.backend.get(item.id)
    assert box.store.blob_pull(item, token=owner, actor=OWNER, principal="interactive") is None


def test_an_unpromoted_rule_artifact_is_not_pulled_by_a_client(box: Container, tmp_path: Path):
    owner, item = _artifact(box, tmp_path, kind="rule")
    bot = box.auth.mint(principal="client", owner=OWNER, client="bot", role="reader",
                        scopes=[item.scope], actor=OWNER, by_principal="interactive")
    assert box.store.blob_pull(item, token=bot, actor="bot", principal="client") is None
    box.trust.promote(item, token=owner, actor=OWNER)
    item = box.backend.get(item.id)
    assert box.store.blob_pull(item, token=bot, actor="bot", principal="client") == b"bytes"


def test_racing_inits_mint_one_owner_and_one_set_of_roots(tmp_path: Path):
    home = tmp_path / "home"
    Container(home)  # the schema exists before the race, as after any first open
    go, tokens, errors = threading.Barrier(4), [], []

    def init():
        try:
            c = Container(home)
            go.wait()
            tokens.append(c.init().id)
        except Exception as e:  # pragma: no cover - surfaced by the assertion below
            errors.append(e)

    threads = [threading.Thread(target=init) for _ in range(4)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert not errors
    c = Container(home)
    owners = [t for t in c.backend.list_tokens() if t.principal == "interactive"]
    assert len(owners) == 1 and set(tokens) == {owners[0].id}
    users = c.backend.db.execute("SELECT COUNT(*) FROM nodes WHERE type = 'user'").fetchone()[0]
    assert users == 1


# --- #118: two deciders racing on one proposal land one decision -------------------------------
def _parked(home: Path):
    c = Container(home)
    t = c.auth.interactive_token()
    root = c.nodes.user_root()
    org = c.nodes.create("org", "acme", root, token=t, actor=OWNER, principal=t.principal)
    proj = c.nodes.create("project", "p", org, token=t, actor=OWNER, principal=t.principal)
    other = c.nodes.create("project", "q", org, token=t, actor=OWNER, principal=t.principal)
    c.auth.mint(principal="client", owner=OWNER, client="watcher", role="reader",
                scopes=[other.id], actor=OWNER, by_principal="interactive")
    item = c.store.add(body="draft", scope=proj, token=t, actor=OWNER, principal=t.principal)
    result = c.trust.move(item, other, token=t, actor=OWNER)
    assert result["gate"] == "pending"
    return result["proposal"]["id"]


def _race(box: Container, tmp_path: Path, monkeypatch, first: str):
    """B passes execute's pre-lock checks; then, before B takes the lock (while B reads the
    audience for the manifest), A decides (`first`)."""
    from egzos.trust import TrustEngine, TrustError

    home = tmp_path / "home"
    pid = _parked(home)
    a, b = Container(home), Container(home)
    ta, tb = a.auth.interactive_token(), b.auth.interactive_token()
    real = TrustEngine.audience

    def a_decides_first(self, *args, **kw):
        if self is b.trust and not getattr(self, "_raced", False):
            self._raced = True
            getattr(a.trust, first)(pid, token=ta, actor=OWNER)
        return real(self, *args, **kw)

    monkeypatch.setattr(TrustEngine, "audience", a_decides_first)
    with pytest.raises(TrustError, match="no open proposal"):
        b.trust.execute(pid, token=tb, actor=OWNER)
    c = Container(home)
    events = [e["event"] for e in c.ledger.tail(50) if e.get("subject") == pid]
    return c.backend.get_proposal(pid)["status"], events


def test_a_second_execute_that_lost_the_race_lands_nothing(box, tmp_path, monkeypatch):
    status, events = _race(box, tmp_path, monkeypatch, "execute")
    assert status == "executed"
    assert events.count("approval.execute") == 1 and "approval.stale" not in events


def test_an_execute_that_lost_to_a_deny_lands_nothing(box, tmp_path, monkeypatch):
    status, events = _race(box, tmp_path, monkeypatch, "deny")
    assert status == "denied"
    assert events.count("approval.deny") == 1 and "approval.execute" not in events
