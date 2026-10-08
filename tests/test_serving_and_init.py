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
    t = c.init()
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


def _race(tmp_path: Path, monkeypatch, first: str, second: str):
    """B (`second`) passes its pre-lock checks; then, before B takes the write lock, A decides
    (`first`). The hook is `decides_over`, the last pre-lock check of both execute and deny."""
    from egzos.trust import TrustEngine, TrustError

    home = tmp_path / "home"
    pid = _parked(home)
    a, b = Container(home), Container(home)
    ta, tb = a.auth.interactive_token(), b.auth.interactive_token()
    real = TrustEngine.decides_over

    def a_decides_first(self, *args, **kw):
        allowed = real(self, *args, **kw)
        if self is b.trust and not getattr(self, "_raced", False):
            self._raced = True
            getattr(a.trust, first)(pid, token=ta, actor=OWNER)
        return allowed

    monkeypatch.setattr(TrustEngine, "decides_over", a_decides_first)
    with pytest.raises(TrustError, match="no open proposal"):
        getattr(b.trust, second)(pid, token=tb, actor=OWNER)
    c = Container(home)
    events = [e["event"] for e in c.ledger.tail(50) if e.get("subject") == pid]
    return c.backend.get_proposal(pid)["status"], events


def test_a_second_execute_that_lost_the_race_lands_nothing(tmp_path, monkeypatch):
    status, events = _race(tmp_path, monkeypatch, "execute", "execute")
    assert status == "executed"
    assert events.count("approval.execute") == 1 and "approval.stale" not in events


def test_an_execute_that_lost_to_a_deny_lands_nothing(tmp_path, monkeypatch):
    status, events = _race(tmp_path, monkeypatch, "deny", "execute")
    assert status == "denied"
    assert events.count("approval.deny") == 1 and "approval.execute" not in events


def test_a_deny_that_lost_to_an_execute_lands_nothing(tmp_path, monkeypatch):
    # a1r on #146: the guard in deny is the one decider branch the two cases above leave untested.
    status, events = _race(tmp_path, monkeypatch, "execute", "deny")
    assert status == "executed"
    assert events.count("approval.execute") == 1 and "approval.deny" not in events


def test_no_audience_change_lands_between_the_manifest_check_and_the_move(tmp_path, monkeypatch):
    # a1r on #146: approve-what-you-saw holds only if the manifest comparison runs under the lock
    # the move takes. Right after execute hashes the manifest, a second connection tries to widen
    # the destination's audience. Either that write is blocked until the move commits, or execute
    # sees it and refuses; a widened audience and an executed move together is the bug.
    import sqlite3

    from egzos.trust import TrustEngine, TrustError

    home = tmp_path / "home"
    pid = _parked(home)
    a, b = Container(home), Container(home)
    other_id = b.backend.get_proposal(pid)["to"]
    real_hash = TrustEngine.manifest_hash
    widened: list[bool] = []

    def hash_then_widen(*args, **kw):
        h = real_hash(*args, **kw)
        if not widened:
            a.backend.db.execute("PRAGMA busy_timeout = 50")
            try:
                a.auth.mint(principal="client", owner=OWNER, client="late", role="reader",
                            scopes=[other_id], actor=OWNER, by_principal="interactive")
                widened.append(True)
            except sqlite3.OperationalError:  # the write lock is held: execute is mid-decision
                widened.append(False)
        return h

    monkeypatch.setattr(TrustEngine, "manifest_hash", staticmethod(hash_then_widen))
    try:
        b.trust.execute(pid, token=b.auth.interactive_token(), actor=OWNER)
        executed = True
    except TrustError:
        executed = False
    assert widened, "the hook never ran"
    assert not (widened[0] and executed)
