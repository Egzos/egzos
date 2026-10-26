# Copyright 2026 Ali Sasanian
# SPDX-License-Identifier: LicenseRef-PolyForm-Strict-1.0.0
"""The backend conformance harness, and the one place under `tests/store/` that names a substrate,
but for the modules `test_backend_agnostic.py` exempts. Each `make_backend()` is a new connection
to one per-test store, so two calls are two connections and a later call is a restart; it and
`blobs` run over `BACKENDS` and `BLOB_STORES`, so a new substrate is one entry. postgres is one
when `EGZOS_TEST_POSTGRES` names a database as a role that may create roles: each test gets a fresh
schema, applied as that owner, and a role of its own holding only the container's grants, as which
every backend connects. The probes are test-only and join no Protocol: `refuses` tries an update or
a delete of an audit entry (events.md §4 item 1), and `staged` reads what no `BlobStore` reader may
(storage.md §4)."""

from __future__ import annotations

import contextlib
import functools
import os
import secrets
import sqlite3
from collections.abc import Callable, Iterator
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import pytest

from egzos.backends.sqlite import SqliteBackend
from egzos.store.blobs import BlobStore

#: An owner DSN. Set, the postgres case runs, and a missing psycopg fails the run (v0.7 §AF).
POSTGRES = os.environ.get("EGZOS_TEST_POSTGRES")


@dataclass(frozen=True)
class BackendKind:
    cls: type
    open: Callable[[Any], Any]  # a new connection to the store kept at this per-test place
    refuses: Callable[[Any, str, int], bool]  # True if the store refuses that act on that entry
    brief: tuple[str, Any]  # the write lock's bound, and a twentieth of a second for it
    place: Callable[[Path], contextlib.AbstractContextManager[Any]] = contextlib.nullcontext


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
                          brief=("egzos.backends.sqlite.LOCK_TIMEOUT", 0.05),
                          open=lambda where: SqliteBackend(where / "container.db")),
}
BLOB_STORES: dict[str, BlobStoreKind] = {
    "fs": BlobStoreKind(open=lambda where: BlobStore(where / "blobs"), staged=_fs_staged),
}

if POSTGRES:
    from psycopg import connect, errors
    from psycopg.conninfo import make_conninfo
    from psycopg.sql import SQL, Identifier, Literal

    from egzos.backends.postgres import PostgresBackend, apply_schema

    @dataclass
    class PostgresPlace:
        """One test's schema, the role it grants to (one name), and the owner's connection."""

        schema: str
        conninfo: str = field(repr=False)  # as that role, its password made for this test alone
        owner: Any
        opened: list[Any] = field(default_factory=list)

    @contextlib.contextmanager
    def _postgres_place(_: Path) -> Iterator[PostgresPlace]:
        name, password = f"egzos_t_{secrets.token_hex(6)}", secrets.token_urlsafe(18)
        owner = connect(POSTGRES, autocommit=True)
        place = PostgresPlace(name, make_conninfo(POSTGRES, user=name, password=password), owner)
        try:
            owner.execute(SQL("CREATE ROLE {} LOGIN PASSWORD {}").format(
                Identifier(name), Literal(password)))
            apply_schema(owner, name, name)
            owner.execute(SQL("SET search_path TO {}").format(Identifier(name)))
            yield place
        finally:
            for backend in place.opened:  # a thread's too: no connection outlives its test
                backend.db.close()
            owner.execute(SQL("DROP SCHEMA IF EXISTS {0} CASCADE; DROP ROLE IF EXISTS {0}").format(
                Identifier(name)))
            owner.close()

    def _postgres_open(place: PostgresPlace) -> PostgresBackend:
        place.opened.append(backend := PostgresBackend(place.conninfo, place.schema))
        return backend

    def _postgres_refuses(backend: PostgresBackend, act: str, seq: int) -> bool:
        sql = {"update": "UPDATE audit SET doc = '{{}}' WHERE seq = {}",
               "delete": "DELETE FROM audit WHERE seq = {}"}[act].format(int(seq))
        try:
            with backend.db.transaction(force_rollback=True):  # whatever happens, nothing is kept
                backend.db.execute(sql)
        except (errors.InsufficientPrivilege, errors.RaiseException):  # its grants, the trigger
            return True
        return False

    BACKENDS["postgres"] = BackendKind(cls=PostgresBackend, open=_postgres_open,
                                       refuses=_postgres_refuses, place=_postgres_place,
                                       brief=("egzos.backends.postgres.LOCK_TIMEOUT", "50ms"))


@pytest.fixture(params=sorted(BACKENDS))
def backend_name(request: pytest.FixtureRequest) -> str:
    return request.param


@pytest.fixture
def backend_class(backend_name: str) -> type:
    return BACKENDS[backend_name].cls


@pytest.fixture
def where(backend_name: str, tmp_path: Path) -> Iterator[Any]:
    """Where this test's store is kept: its tmp_path, or a schema of its own."""
    with BACKENDS[backend_name].place(tmp_path) as place:
        yield place


@pytest.fixture
def make_backend(backend_name: str, where: Any) -> Callable[[], Any]:
    return functools.partial(BACKENDS[backend_name].open, where)


@pytest.fixture
def backend(make_backend: Callable[[], Any]) -> Any:
    return make_backend()


@pytest.fixture
def brief_lock(backend_name: str, monkeypatch: pytest.MonkeyPatch) -> None:
    """A backend opened after this waits a twentieth of a second for the write lock, not ten."""
    monkeypatch.setattr(*BACKENDS[backend_name].brief)


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
