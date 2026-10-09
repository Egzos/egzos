# Copyright 2026 Ali Sasanian
# SPDX-License-Identifier: Apache-2.0
"""
Every value the AS issues (authorization-server.md §9.1, §11.8).

Access tokens, refresh tokens, authorization codes and `device_code`s carry 256 bits from the
platform CSPRNG (`secrets`), twice §9.1's 128-bit floor, and nothing derived from a counter, a
clock, a client id or an owner. The `user_code` is the one exception, bounded by the attempt limit
and expiry rather than by entropy ([0.3 · 20]): 8 characters of RFC 8628 §6.1's 20 consonants,
shown `XXXX-XXXX`, matched case-insensitively with the hyphen ignored.
"""

from __future__ import annotations

import secrets

from egzos._types import AS_USER_CODE_ALPHABET, AS_USER_CODE_LENGTH

#: Bytes of CSPRNG output behind every non-`user_code` value. §9.1's floor is 16.
VALUE_BYTES = 32


def new_value() -> str:
    """An opaque, unguessable credential value: a code, a `device_code` or a token."""
    return secrets.token_urlsafe(VALUE_BYTES)


def new_user_code() -> str:
    """A fresh `user_code`, in its canonical (undisplayed) form: 8 characters, no hyphen."""
    return "".join(secrets.choice(AS_USER_CODE_ALPHABET) for _ in range(AS_USER_CODE_LENGTH))


def display_user_code(code: str) -> str:
    half = AS_USER_CODE_LENGTH // 2
    return f"{code[:half]}-{code[half:]}"


def normalize_user_code(typed: str | None) -> str | None:
    """What a human typed, as a canonical `user_code`, or None when it cannot be one (row (b)
    cause `malformed`). Case and hyphens are ignored, and nothing else is: a space, a digit or a
    vowel is not silently dropped into a different code."""
    # ASCII first: `"ſ".upper()` is `"S"`, and a code is not reachable through case folding.
    if not isinstance(typed, str) or not typed.isascii() or len(typed) > 4 * AS_USER_CODE_LENGTH:
        return None
    code = typed.replace("-", "").upper()
    if len(code) != AS_USER_CODE_LENGTH or any(c not in AS_USER_CODE_ALPHABET for c in code):
        return None
    return code
