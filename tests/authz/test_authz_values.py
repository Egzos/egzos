# Copyright 2026 Ali Sasanian
# SPDX-License-Identifier: LicenseRef-PolyForm-Strict-1.0.0
"""§9.1 issued values and §11.8 user codes (authz/values.py)."""

from __future__ import annotations

import math

import pytest

from egzos import auth
from egzos._types import AS_USER_CODE_ALPHABET, AS_USER_CODE_LENGTH
from egzos.authz import values


def test_issued_values_clear_the_128_bit_floor_and_do_not_repeat():
    assert values.VALUE_BYTES * 8 >= 128
    seen = {values.new_value() for _ in range(256)}
    assert len(seen) == 256
    assert all(len(v) >= 43 for v in seen)  # 32 bytes, base64url


def test_issued_values_are_not_access_tokens():
    # Access tokens are `Token`s minted by `egzos.auth` (capabilities.md §5); a code, a
    # `device_code` or a refresh token is never resolvable as one.
    assert all(auth.token_id_of(values.new_value()) is None for _ in range(256))


def test_user_code_shape():
    code = values.new_user_code()
    assert len(code) == AS_USER_CODE_LENGTH
    assert set(code) <= set(AS_USER_CODE_ALPHABET)
    shown = values.display_user_code(code)
    assert shown == f"{code[:4]}-{code[4:]}"
    assert values.normalize_user_code(shown.lower()) == code
    assert math.log2(len(AS_USER_CODE_ALPHABET)) * AS_USER_CODE_LENGTH < 128  # [0.3 · 20]


@pytest.mark.parametrize(
    "typed",
    [None, "", "BCDF-GHJ", "BCDF-GHJKL", "BCDF GHJK", "ABCD-EFGH", "BCDF-GHJ1", "ſCDF-GHJK",
     "-" * 100],
)
def test_user_code_that_cannot_be_one_is_malformed(typed):
    assert values.normalize_user_code(typed) is None


def test_token_secrets_and_issued_values_share_one_digest():
    # storage.md §3.1: the AS hashes "as auth.py already does". One function, not two copies.
    assert auth._hash is values.digest
    assert values.digest("abc") == (
        "ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad"
    )


@pytest.mark.parametrize(
    ("given", "stored", "equal"),
    [
        ("client", "client", True),
        ("client", "Client", False),
        ("ñ", "ñ", True),  # non-ASCII `str` would raise in a bare `compare_digest`
        ("ñ", "n", False),
        ("\ud800", "\ud800", True),  # a lone surrogate would raise in a bare `encode`
        ("\ud800", "x", False),
        (None, "client", False),
        ("client", None, False),
        (b"client", "client", False),
        (["client"], "client", False),
        ("", "", True),
    ],
)
def test_same_is_total_and_never_raises(given, stored, equal):
    assert values.same(given, stored) is equal


def test_every_authz_comparison_goes_through_one_helper():
    # Four private copies once existed (#241's review); a fifth must not reappear.
    from pathlib import Path

    root = Path(values.__file__).parent
    for path in root.glob("*.py"):
        if path.name in ("values.py", "pkce.py"):  # pkce compares two ASCII base64url digests
            continue
        assert "compare_digest" not in path.read_text(), path.name


def test_a_bearer_value_with_a_lone_surrogate_is_refused_not_raised(tmp_path):
    from egzos.container import OWNER, Container

    c = Container(tmp_path)
    c.init()
    t = c.auth.mint(principal="client", owner=OWNER, client="probe", role="reader",
                    scopes=["*"], actor=OWNER, by_principal="interactive")
    assert c.auth.use(t.secret + "\ud800") is None
    assert c.auth.use(t.secret).id == t.id
