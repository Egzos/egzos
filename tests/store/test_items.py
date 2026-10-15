# Copyright 2026 Ali Sasanian
# SPDX-License-Identifier: LicenseRef-PolyForm-Strict-1.0.0
"""
`Store`'s inline-blob threshold (F30, #271, #10). `model.py` used to hard-code
`INLINE_BLOB_LIMIT = 64 * 1024`, a second copy of `_types.py`'s
`CONTAINER_CONFIG_DEFAULTS["blobs_inline_max_bytes"]` that a container configured with a different
`blobs.inline_max_bytes` could never reach — `Store.add` read the constant, never the config.
`Store` now takes an optional `ContainerConfig` and serves `self.inline_blob_limit` off it,
falling back to the `_types.py` default when no config (or no key) is given.
"""

from __future__ import annotations

from pathlib import Path

from egzos._ids import ulid
from egzos._types import CONTAINER_CONFIG_DEFAULTS
from egzos.backends.sqlite import SqliteBackend
from egzos.ledger import Ledger
from egzos.model import Token
from egzos.store.blobs import BlobStore
from egzos.store.items import Store
from egzos.store.nodes import NodeService

OWNER = "self"


def _store(tmp_path: Path, *, config: dict | None = None) -> Store:
    backend = SqliteBackend(tmp_path / "container.db")
    ledger = Ledger(backend)
    nodes = NodeService(backend, ledger)
    nodes.ensure_roots(actor=OWNER, principal="interactive")
    blobs = BlobStore(tmp_path / "blobs")
    return Store(backend, ledger, nodes, blobs, config=config)


def _token() -> Token:
    return Token(
        id=ulid(),
        principal="interactive",
        owner=OWNER,
        client="cli",
        capabilities=["remember"],
        scopes=["*"],
    )


def test_default_inline_blob_limit_matches_the_types_default(tmp_path: Path):
    """No config passed: `Store` serves exactly `_types.py`'s default, never a second constant."""
    store = _store(tmp_path)
    assert store.inline_blob_limit == CONTAINER_CONFIG_DEFAULTS["blobs_inline_max_bytes"]


def test_default_behaviour_is_unchanged_for_a_small_text_blob(tmp_path: Path):
    """Unconfigured: a small text blob is still inlined, exactly as before this change."""
    store = _store(tmp_path)
    f = tmp_path / "small.txt"
    f.write_text("hello blob")
    item = store.add(file=f, token=_token(), actor=OWNER, principal="interactive")
    assert item.content["inline"] == "hello blob"


def test_configured_smaller_limit_pushes_a_text_blob_out_of_line(tmp_path: Path):
    """A container configured with a smaller `blobs.inline_max_bytes` stores a text blob above
    that smaller limit out of line, even though it is well under the 64 KiB skeleton default."""
    store = _store(tmp_path, config={"blobs_inline_max_bytes": 4})
    f = tmp_path / "small.txt"
    f.write_text("hello blob")  # 10 bytes: under the 64 KiB default, over the configured 4
    item = store.add(file=f, token=_token(), actor=OWNER, principal="interactive")
    assert "inline" not in item.content
    assert item.content["sha256"] == store.blobs.digest(b"hello blob")
    assert store.blobs.get(item.content["sha256"]) == b"hello blob"


def test_configured_larger_limit_inlines_a_blob_the_default_would_not(tmp_path: Path):
    """The configured limit is actually read, not just floored at the default: a blob the 64 KiB
    default would push out of line still inlines under a larger configured limit."""
    store = _store(tmp_path, config={"blobs_inline_max_bytes": 10 * 1024})
    f = tmp_path / "medium.txt"
    f.write_text("x" * 8000)
    item = store.add(file=f, token=_token(), actor=OWNER, principal="interactive")
    assert item.content["inline"] == "x" * 8000


def test_configured_zero_disables_inlining_entirely(tmp_path: Path):
    """`0` is a value, not an absent key (`_types.py`'s own loading rule) — a container that sets
    `blobs.inline_max_bytes` to `0` never inlines, even the smallest text blob."""
    store = _store(tmp_path, config={"blobs_inline_max_bytes": 0})
    f = tmp_path / "tiny.txt"
    f.write_text("x")
    item = store.add(file=f, token=_token(), actor=OWNER, principal="interactive")
    assert "inline" not in item.content


def test_config_missing_the_key_falls_back_to_the_types_default(tmp_path: Path):
    """A config object that omits `blobs_inline_max_bytes` falls back to the `_types.py`
    default rather than inlining nothing (or everything)."""
    store = _store(tmp_path, config={})
    assert store.inline_blob_limit == CONTAINER_CONFIG_DEFAULTS["blobs_inline_max_bytes"]
