# Copyright 2026 Ali Sasanian
# SPDX-License-Identifier: LicenseRef-PolyForm-Strict-1.0.0
"""
The two value helpers the container's own credentials share: `digest`, the one hash behind
`Token.secret_hash`, and `same`, the one constant-time comparison. They outlived the retired
authorization server (`identity.md` §9), whose issued values and user codes went with it.
"""

from __future__ import annotations

import hashlib
import hmac


def digest(value: str) -> str:
    """The lowercase hex sha256 of the whole value: the one hash behind `Token.secret_hash`.
    `auth.py` imports it rather than keeping a copy, so no second lookup can drift from it."""
    # `surrogatepass`: a lone surrogate from a JSON body hashes like any other string, never raises
    return hashlib.sha256(value.encode("utf-8", "surrogatepass")).hexdigest()


def same(given: object, stored: object) -> bool:
    """Constant-time equality for stored strings: a digest, the tap's path value.
    Anything but two `str`s is unequal. `hmac.compare_digest` raises on a non-ASCII `str` and
    `encode` on a lone surrogate, and a raise would be a second answer shape beside the refusal,
    so both sides compare as bytes. The one helper every such comparison goes through."""
    if not isinstance(given, str) or not isinstance(stored, str):
        return False
    return hmac.compare_digest(
        given.encode("utf-8", "surrogatepass"), stored.encode("utf-8", "surrogatepass")
    )

