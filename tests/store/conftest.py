# Copyright 2026 Ali Sasanian
# SPDX-License-Identifier: LicenseRef-PolyForm-Strict-1.0.0
"""The backend conformance harness, and the one place under `tests/store/` that names a substrate,
but for the two older modules `test_backend_agnostic.py` exempts. Each `make_backend()` is a new
connection to one per-test store, so two calls are two connections and a later call is a restart;
it and `blobs` run over `BACKENDS` and `BLOB_STORES`, so a new substrate is one entry. The probes
are test-only and join no Protocol: `refuses` tries an update or a delete of an audit entry
(events.md §4 item 1), and `staged` reads what no `BlobStore` reader may (storage.md §4)."""

from __future__ import annotations

import functools
import sqlite3
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pytest

from egzos.backends.sqlite import SqliteBackend
from egzos.store.blobs import BlobStore


@dataclass(frozen=True)
class BackendKind:
    cls: type
    open: Callable[[Path], Any]  # a new connection to the store kept under this per-test place
    refuses: Callable[[Any, str, int], bool]  # True if the store refuses that act on that entry


@dataclass(frozen=True)
class BlobStoreKind:
    open: Callable[[Path], Any]
    staged: Callable[[Any, str], bytes | None]  # the bytes staged at this address, if any


def _sqlite_refuses(backend: SqliteBackend, act: str, seq: int) -> bool:
    sql = {"update": "UPDATE audit SET doc='{}' WHERE seq=?",
           "delete": "DELETE FROM audit WHERE seq=?"}[act]
    try:
        backend.db.execute(sql, (seq,))
    except sqlite3.IntegrityError:  # the trigger's RAISE(ABORT)
        return True
    finally:
        backend.db.rollback()  # whatever happened, the connection is left as it was found
    return False


def _fs_staged(store: BlobStore, sha: str) -> bytes | None:
    path = store.root / "staging" / sha
    return path.read_bytes() if path.exists() else None


BACKENDS: dict[str, BackendKind] = {
    "sqlite": BackendKind(cls=SqliteBackend, refuses=_sqlite_refuses,
                          open=lambda where: SqliteBackend(where / "container.db")),
}
BLOB_STORES: dict[str, BlobStoreKind] = {
    "fs": BlobStoreKind(open=lambda where: BlobStore(where / "blobs"), staged=_fs_staged),
}


@pytest.fixture(params=sorted(BACKENDS))
def backend_name(request: pytest.FixtureRequest) -> str:
    return request.param


@pytest.fixture
def backend_class(backend_name: str) -> type:
    return BACKENDS[backend_name].cls


@pytest.fixture
def make_backend(backend_name: str, tmp_path: Path) -> Callable[[], Any]:
    return functools.partial(BACKENDS[backend_name].open, tmp_path)


@pytest.fixture
def backend(make_backend: Callable[[], Any]) -> Any:
    return make_backend()


@pytest.fixture
def refuses(backend_name: str) -> Callable[[Any, str, int], bool]:
    return BACKENDS[backend_name].refuses


@pytest.fixture(params=sorted(BLOB_STORES))
def blob_store_name(request: pytest.FixtureRequest) -> str:
    return request.param


@pytest.fixture
def blobs(blob_store_name: str, tmp_path: Path) -> Any:
    return BLOB_STORES[blob_store_name].open(tmp_path)


@pytest.fixture
def staged(blob_store_name: str) -> Callable[[Any, str], bytes | None]:
    return BLOB_STORES[blob_store_name].staged
