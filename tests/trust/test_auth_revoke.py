# Copyright 2026 Ali Sasanian
# SPDX-License-Identifier: LicenseRef-PolyForm-Strict-1.0.0
"""`Auth.revoke` (`token rm`) against authorization-server.md §9.2: one `token.revoke` per revoked
`Token`, never a second (#242). And `Auth.use`'s comparison is `authz.values.same`'s: total, so a
stored hash of the wrong shape refuses rather than raises."""

from __future__ import annotations

import pytest

from egzos.container import OWNER, Container


@pytest.fixture
def box(tmp_path):
    c = Container(tmp_path)
    c.init()
    return c


def _client(c: Container):
    return c.auth.mint(principal="client", owner=OWNER, client="probe", role="reader",
                       scopes=["*"], actor=OWNER, by_principal="interactive")


def _revokes(c: Container, token_id: str) -> list[dict]:
    return [e for e in c.ledger.tail(1000)
            if e["event"] == "token.revoke" and e.get("subject") == token_id]


def test_revoke_appends_one_token_revoke(box):
    t = _client(box)
    assert box.auth.revoke(t.id, actor=OWNER, principal="interactive") is True
    assert box.backend.get_token(t.id).revoked
    [event] = _revokes(box, t.id)
    assert event["actor"] == OWNER and event["principal"] == "interactive"


def test_an_already_revoked_token_gets_no_second_token_revoke(box):
    t = _client(box)
    box.auth.revoke(t.id, actor=OWNER, principal="interactive")
    before = box.ledger.tail(1000)
    assert box.auth.revoke(t.id, actor=OWNER, principal="interactive") is True
    assert box.ledger.tail(1000) == before          # nothing appended, nothing rewritten
    assert len(_revokes(box, t.id)) == 1
    assert box.auth.use(t.secret) is None


def test_an_unknown_id_revokes_nothing_and_appends_nothing(box):
    before = box.ledger.tail(1000)
    assert box.auth.revoke("01" + "Z" * 24, actor=OWNER, principal="interactive") is False
    assert box.ledger.tail(1000) == before


def test_token_revoke_carries_no_family_id_until_backend_has_a_family_read(box):
    # #242's second half waits on a contract read; until then no family id is guessed at.
    t = _client(box)
    box.auth.revoke(t.id, actor=OWNER, principal="interactive")
    [event] = _revokes(box, t.id)
    assert "family_id" not in event["details"]


@pytest.mark.parametrize("stored", ["é" * 64, "0" * 63])
def test_use_refuses_without_raising_on_a_stored_hash_of_the_wrong_shape(box, stored):
    # `secrets.compare_digest` raised TypeError on a non-ASCII str; `same` answers False.
    t = _client(box)
    held = box.backend.get_token(t.id)
    held.secret_hash = stored
    box.backend.put_token(held)
    assert box.auth.use(t.secret) is None


def test_use_still_resolves_the_true_value(box):
    t = _client(box)
    assert box.auth.use(t.secret).id == t.id
