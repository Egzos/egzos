# Copyright 2026 Ali Sasanian
# SPDX-License-Identifier: LicenseRef-PolyForm-Strict-1.0.0
"""
The AS's own issued values (authorization-server.md §9.1, §11.8).

Authorization codes, `device_code`s and refresh tokens carry 256 bits from the platform CSPRNG
(`secrets`), twice §9.1's 128-bit floor, and nothing derived from a counter, a clock, a client id
or an owner. The `user_code` is the one exception, bounded by the attempt limit and expiry rather
than by entropy ([0.3 · 20]): 8 characters of RFC 8628 §6.1's 20 consonants, shown `XXXX-XXXX`,
matched case-insensitively with the hyphen ignored.

Access tokens are not minted here. A token the AS issues IS a `Token` (§7, `capabilities.md` §5),
so its bearer value is `egz_<id>_<256 bits>` from `egzos.auth`, the same path as `token mint`,
and is resolved by `token_id_of` like any other; a second format would be a second token kind.
"""

from __future__ import annotations

import secrets

from egzos._types import AS_USER_CODE_ALPHABET, AS_USER_CODE_LENGTH

#: Bytes of CSPRNG output behind every `new_value()`. §9.1's floor is 16.
VALUE_BYTES = 32


def new_value() -> str:
    """An opaque, unguessable value for an authorization code, a `device_code` or a refresh token.

    Never an access token's bearer value: that is `egzos.auth`'s, through the `Token` mint."""
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
