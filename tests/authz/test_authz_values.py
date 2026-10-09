# Copyright 2026 Ali Sasanian
# SPDX-License-Identifier: Apache-2.0
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
