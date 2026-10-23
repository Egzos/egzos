# Copyright 2026 Ali Sasanian
# SPDX-License-Identifier: LicenseRef-PolyForm-Strict-1.0.0
"""
The container's own secrets: random keys in its home, each created once and never rewritten.

A key is written whole to a private file and linked into place, first writer wins, so no reader
ever sees a half-written key and every process reads the same one. A short file, left by a crash
under earlier code, is passed over for the next name (`<name>.1`, …), which every process reaches
the same way. Deleting a key's files rotates it: the next read creates a new one. Each key is its
holder's alone and does not travel with an export or a sync: a place makes its own.
"""

from __future__ import annotations

import contextlib
import os
import secrets
from pathlib import Path

KEY_BYTES = 32
#: How many names a key tries, `<name>` first, passing over short ones.
KEY_SLOTS = 4


def container_key(home: Path, name: str) -> bytes:
    """The key `name` in the container's home: 32 bytes, 0600. Should all `KEY_SLOTS` names be
    short, it raises and its holder does not start: it fails closed, never on an empty key."""
    for slot in range(KEY_SLOTS):
        path = Path(home) / (name if slot == 0 else f"{name}.{slot}")
        try:
            data = path.read_bytes()
        except FileNotFoundError:
            data = _create(path, name)
        if len(data) == KEY_BYTES:
            return data
    raise RuntimeError(f"the {name} key cannot be read")


def _create(path: Path, name: str) -> bytes:
    """Link a whole new key at `path` unless another process got there first; either way, return
    the key that is there now."""
    tmp = path.with_name(f".{name}.{secrets.token_hex(8)}")
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    try:
        with os.fdopen(fd, "wb") as fh:
            fh.write(secrets.token_bytes(KEY_BYTES))
            fh.flush()
            os.fsync(fh.fileno())
        with contextlib.suppress(FileExistsError):
            os.link(tmp, path)
    finally:
        with contextlib.suppress(FileNotFoundError):
            os.unlink(tmp)
    return path.read_bytes()
