# Copyright 2026 Ali Sasanian
# SPDX-License-Identifier: Apache-2.0
"""Bearer values: the id is public, the value is >= 128 random bits and is never stored."""

from __future__ import annotations

import base64
import json
import stat

import pytest

from egzos.auth import token_id_of
from egzos.container import OWNER, Container


@pytest.fixture
def box(tmp_path):
    c = Container(tmp_path)
    c.init()
    return c


def _client(c: Container):
    return c.auth.mint(principal="client", owner=OWNER, client="probe", role="reader",
                       scopes=["*"], actor=OWNER, by_principal="interactive")


def test_value_carries_at_least_128_random_bits(box):
    t = _client(box)
    assert token_id_of(t.secret) == t.id
    random_part = t.secret[len("egz_") + 26 + 1:]   # egz_<26-char id>_<random>
    raw = base64.urlsafe_b64decode(random_part + "=" * (-len(random_part) % 4))
    assert len(raw) * 8 >= 128


def test_only_the_value_authenticates(box):
    t = _client(box)
    assert box.auth.use(t.secret).id == t.id
    assert box.auth.use(t.id) is None                       # the public id is not a credential
    assert box.auth.use(t.secret[:-1] + ("A" if t.secret[-1] != "A" else "B")) is None
    assert box.auth.use("") is None and box.auth.use("egz_x_y") is None
    box.auth.revoke(t.id, actor=OWNER, principal="interactive")
    assert box.auth.use(t.secret) is None


def test_value_is_never_stored_or_logged(box):
    t = _client(box)
    db = (box.home / "egzos.db").read_bytes()
    assert t.secret.encode() not in db
    chain = json.dumps(box.ledger.tail(1000))
    assert t.secret not in chain
    assert t.id in chain                                     # the id is what the record names


def test_keychain_holds_the_owner_value_owner_only(box):
    kc = box.home / "keychain.json"
    assert stat.S_IMODE(kc.stat().st_mode) == 0o600
    value = json.loads(kc.read_text())["token"]
    assert box.auth.use(value).principal == "interactive"


@pytest.mark.parametrize("principal", ["none", "owner", "", "Interactive"])
def test_mint_refuses_a_principal_no_token_can_hold(tmp_path, principal):
    # a6 on #151: `none` is audit-only (events.md §2), and the token vocabulary is closed.
    from egzos.auth import AuthError

    c = Container(tmp_path / "home")
    c.init()
    before = len(c.backend.list_tokens())
    with pytest.raises(AuthError, match="unknown token principal"):
        c.auth.mint(principal=principal, owner=OWNER, client="bot", role="reader", scopes=["*"],
                    actor=OWNER, by_principal="interactive")
    assert len(c.backend.list_tokens()) == before
