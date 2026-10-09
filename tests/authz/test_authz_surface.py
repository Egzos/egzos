# Copyright 2026 Ali Sasanian
# SPDX-License-Identifier: Apache-2.0
"""§9.1 issued values, §11.8 user codes, §11.7 `continue`, §2 loopback bind."""

from __future__ import annotations

import math

import pytest

from egzos._types import AS_CONTINUE_MAX_BYTES, AS_USER_CODE_ALPHABET, AS_USER_CODE_LENGTH
from egzos.authz import continuation, transport, values


def test_issued_values_clear_the_128_bit_floor_and_do_not_repeat():
    assert values.VALUE_BYTES * 8 >= 128
    seen = {values.new_value() for _ in range(256)}
    assert len(seen) == 256
    assert all(len(v) >= 43 for v in seen)  # 32 bytes, base64url


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


@pytest.mark.parametrize(
    ("value", "location"),
    [
        ("/authorize?response_type=code&state=a%20b", "/authorize?response_type=code&state=a%20b"),
        ("/?q=x%2Fy", "/?q=x%2Fy"),
        ("/", "/"),
        ("/device?user_code=BCDF", "/device"),  # query dropped where the target consumes none
        ("/pending", "/pending"),
        ("/pending/01HZX-a.b_c~", "/pending/01HZX-a.b_c~"),
        ("/items/abc?x=1#frag", "/items/abc"),
        ("/authorize#frag", "/authorize"),
    ],
)
def test_continue_allowlist_carries_what_d_c5_carries(value, location):
    assert continuation.resolve(value) == location


@pytest.mark.parametrize(
    "value",
    [
        None,
        "",
        "//evil.com/x",
        "/\\x",
        "/%2F%2Fx",
        "/items/a/b",
        "/elsewhere",
        "https://evil.com/",
        "authorize",
        "/authorize/",
        "/items/",
        "/items/..",
        "/pending/.",
        "/items/a%2Fb",
        "/items/a\\b",
        "/authorize?\x00",
        "/authorize?\x7f",
        "/\t/evil.com",
        "/authorize?a\r\nLocation: //evil",
        "/authorize?a b",
        "/authorize?é",
        "/AUTHORIZE",
        "/authorize?" + "a" * AS_CONTINUE_MAX_BYTES,
    ],
)
def test_continue_failing_any_step_is_the_root_silently(value):
    assert continuation.resolve(value) == "/"


def test_continue_at_the_byte_limit_still_resolves():
    value = "/authorize?" + "a" * (AS_CONTINUE_MAX_BYTES - len("/authorize?"))
    assert continuation.resolve(value) == value


@pytest.mark.parametrize("host", ["127.0.0.1", "127.255.0.9", "::1", "[::1]", " 127.0.0.1 "])
def test_plain_http_only_on_a_loopback_bind(host):
    assert transport.plain_http_allowed(host)


@pytest.mark.parametrize(
    "host",
    ["0.0.0.0", "::", "[::]", "192.168.1.4", "10.0.0.1", "localhost", "::ffff:127.0.0.1",
     "128.0.0.1", "", "fe80::1",
     "::1%lo", "127.1", "0177.0.0.1", "127.0.0.1:8443"],
)
def test_tls_required_on_every_other_bind(host):
    assert not transport.plain_http_allowed(host)
