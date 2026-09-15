# Copyright 2026 Ali Sasanian
# SPDX-License-Identifier: Apache-2.0
"""ULIDs — the identity of every node and item. Identity ≠ location (log §2)."""

from __future__ import annotations

import os
import time

_ALPHABET = "0123456789ABCDEFGHJKMNPQRSTVWXYZ"  # Crockford base32


def _b32(value: int, length: int) -> str:
    out = []
    for _ in range(length):
        out.append(_ALPHABET[value & 0x1F])
        value >>= 5
    return "".join(reversed(out))


def ulid(ts_ms: int | None = None) -> str:
    """26-char ULID: 48-bit millisecond timestamp + 80 bits of randomness."""
    ts = int(time.time() * 1000) if ts_ms is None else ts_ms
    rand = int.from_bytes(os.urandom(10), "big")
    return _b32(ts, 10) + _b32(rand, 16)


def is_ulid(value: str) -> bool:
    return len(value) == 26 and all(c in _ALPHABET for c in value)
