# Copyright 2026 Ali Sasanian
# SPDX-License-Identifier: LicenseRef-PolyForm-Strict-1.0.0
"""
The F3 partition, pinned.

`spec/contracts/storage.md` splits the walking skeleton's one wide `Backend` Protocol into
`ItemStore` (pluggable, delegable) and `ContainerState` (never delegated), leaving `BlobStore` as
the third seam. The split's whole value is *where the line falls* — a method that drifts across it
silently un-decides F3. These tests fail if it moves.

The method names below are transcribed from `chief/walking-skeleton`
(`src/egzos/backends/base.py`, `src/egzos/store/blobs.py`), which is the source the contract was
frozen from. They are deliberately written out rather than derived from the Protocols they check:
a test that asks the code what it contains cannot notice the code changing.
"""

from __future__ import annotations

import inspect
import typing
from contextlib import AbstractContextManager

import egzos._types as t

# The skeleton's `Backend` union, verbatim — the 18 methods F3 partitions.
SKELETON_BACKEND = frozenset(
    {
        "put_node", "get_node", "list_nodes", "find_root",
        "put", "get", "query", "tombstone",
        "audit_append", "audit_last", "audit_iter", "audit_tail",
        "put_token", "get_token", "list_tokens",
        "put_proposal", "get_proposal", "list_proposals",
    }
)

ITEM_STORE = frozenset({"put", "get", "query", "tombstone"})

CONTAINER_STATE = frozenset(
    {
        "put_node", "get_node", "list_nodes", "find_root",
        "put_token", "get_token", "list_tokens",
        "put_proposal", "get_proposal", "list_proposals",
        "audit_append", "audit_last", "audit_iter", "audit_tail",
    }
)

BLOB_STORE = frozenset({"put", "stage", "promote", "get", "exists", "discard"})


def _methods(protocol: type) -> frozenset[str]:
    """The methods a Protocol declares in its own body."""
    return frozenset(
        name for name, value in vars(protocol).items()
        if not name.startswith("_") and callable(value)
    )


def test_item_store_method_set():
    assert _methods(t.ItemStore) == ITEM_STORE


def test_container_state_method_set():
    assert _methods(t.ContainerState) == CONTAINER_STATE


def test_blob_store_method_set():
    assert _methods(t.BlobStore) == BLOB_STORE


def test_split_is_a_partition_of_the_skeleton_union():
    """F3 introduces no method, removes none and renames none."""
    assert ITEM_STORE | CONTAINER_STATE == SKELETON_BACKEND
    assert not (ITEM_STORE & CONTAINER_STATE)


def test_the_audit_chain_is_never_in_the_pluggable_contract():
    """The one clause F3 exists for: the ledger's integrity must not ride a delegated backend.

    Amends v0.4 §11, which had `audit_append` in the single pluggable backend contract.
    """
    audit = {"audit_append", "audit_last", "audit_iter", "audit_tail"}
    assert audit <= _methods(t.ContainerState)
    assert not (audit & _methods(t.ItemStore))


def test_blob_store_exposes_no_read_path_into_staging():
    """A staged blob is unaddressable until `promote` (storage.md §4).

    `get` and `exists` address `sha256/<hash>` only; the guard here is that no *additional* reader
    appears alongside them, since a `get_staged`/`list_staging` would make staging resolvable.
    """
    writers = {"put", "stage", "promote", "discard"}
    readers = {name for name in _methods(t.BlobStore) if name not in writers}
    assert readers == {"get", "exists"}


def test_promote_reports_to_its_internal_caller():
    """[0.3 · 43]: an approval that promoted nothing must not look like one that did."""
    assert typing.get_type_hints(t.BlobStore.promote)["return"] is bool


def test_storage_contracts_names_resolve_and_are_exported():
    assert t.STORAGE_CONTRACTS == ("ItemStore", "ContainerState", "BlobStore")
    for name in t.STORAGE_CONTRACTS:
        assert name in t.__all__
        assert getattr(t, name) is not None


# --- storage.md §3.6 · one writer per container (v0.7 §AF) -------------------------------------
TRANSACTIONAL = frozenset({"atomic"})


def test_transactional_declares_atomic_beside_container_state_never_in_it():
    assert _methods(t.Transactional) == TRANSACTIONAL
    assert not (TRANSACTIONAL & (_methods(t.ContainerState) | _methods(t.ItemStore)))


def test_atomic_takes_nothing_and_returns_a_context_manager():
    assert list(inspect.signature(t.Transactional.atomic).parameters) == ["self"]
    hints = typing.get_type_hints(t.Transactional.atomic)
    assert hints["return"] == AbstractContextManager[None]


def test_atomic_is_the_one_the_skeleton_backend_runs():
    """§3.6 types what the skeleton's `Backend` already runs; it adds no method and renames none."""
    from egzos.backends.base import Backend

    assert inspect.signature(t.Transactional.atomic) == inspect.signature(Backend.atomic)


def test_chain_conflict_is_the_shared_type_wherever_it_is_imported_from():
    """Declared in `_types.py`; `backends.base` still exports it, and the class the sqlite backend
    raises is the one the ledger's retry catches."""
    from egzos import ledger
    from egzos.backends import base, sqlite

    assert issubclass(t.ChainConflict, Exception)
    assert base.ChainConflict is t.ChainConflict
    assert sqlite.ChainConflict is t.ChainConflict
    assert ledger.ChainConflict is t.ChainConflict
