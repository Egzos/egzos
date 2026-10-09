# Copyright 2026 Ali Sasanian
# SPDX-License-Identifier: Apache-2.0
"""§11.7 `continue` (authz/continuation.py)."""

from __future__ import annotations

import pytest

from egzos._types import AS_CONTINUE_MAX_BYTES
from egzos.authz import continuation


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
