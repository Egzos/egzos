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
