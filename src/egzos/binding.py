# Copyright 2026 Ali Sasanian
# SPDX-License-Identifier: LicenseRef-PolyForm-Strict-1.0.0
"""Which database a container keeps its state in, and its home's binding to it (storage.md §3.7).

`EGZOS_DATABASE_URL` names a postgres database, whose schema `egzos` holds the container's state;
unset, the state stays in the home's own `egzos.db`, as before. A home made on a named database
keeps `binding.json` beside its keys: the hash of the chain's first entry, and the `seq` and hash
of the newest entry it has seen, none of them secret. Every open checks the two before anything
serves, and stops with `HomeBindingError`. The connection string is the host's secret: it is read
from the environment where it is used and kept in no local, attribute, file or message, and a
driver's error, which can echo it, is never chained to the one raised.

The first entry's hash is no secret, and it binds because no other database can reproduce it: an
entry's hash covers its whole body, its `ts`, actor and details included (events.md §2-§3), not a
label, so an empty database, or another container's, never matches it. Narrowing what the first
entry carries would weaken the binding (a6 on #334)."""

from __future__ import annotations

import contextlib
import json
import os
import secrets
import sqlite3
from pathlib import Path
from typing import Any

from egzos.backends import SqliteBackend

DATABASE_URL = "EGZOS_DATABASE_URL"
#: The schema the operator applies the container's tables in (`backends.postgres.apply_schema`).
SCHEMA = "egzos"
BINDING_FILE = "binding.json"

_CASES = {
    "unset": "this home is bound to a database, and EGZOS_DATABASE_URL is unset: it never falls "
             "back to its own egzos.db",
    "mismatch": "this home was made on another database than the one EGZOS_DATABASE_URL names "
                "(its chain differs, or is empty)",
    "unreachable": "the database EGZOS_DATABASE_URL names cannot be reached, or holds no egzos "
                   "schema this container may read: it never falls back to a local store",
    "unbound": "the database EGZOS_DATABASE_URL names holds a chain, and this home holds no "
               "binding to it, as a new or lost home would: its keys would be fresh",
    "taken": "the database EGZOS_DATABASE_URL names already holds a chain: another home made its "
             "container there",
    "local": "this home's own egzos.db holds a chain, and EGZOS_DATABASE_URL is set: that chain, "
             "its tokens and its counters would be left behind",
    "restored": "the database EGZOS_DATABASE_URL names no longer holds the newest entry this home "
                "has seen: it was restored to an earlier point without its home",
    "driver": 'EGZOS_DATABASE_URL is set, and postgres support is not installed: pip install '
              '"egzos[postgres]"',
    "unreadable": "this home's binding.json, which binds it to the database EGZOS_DATABASE_URL "
                  "names, cannot be read",
}


class HomeBindingError(RuntimeError):
    """The container stops before anything serves (storage.md §3.7): its home and the database do
    not belong together, or the database cannot be used. `case` names which; the message names
    the variable, never its value."""

    def __init__(self, case: str):
        self.case = case
        super().__init__(f"the container stops ({case}): {_CASES[case]}")


def _holds_chain(db: Path) -> bool:
    """Whether the home's own `egzos.db` holds a chain, read without writing it. One that cannot
    be read is taken to hold one: the container stops rather than leave a chain behind."""
    if not db.exists():
        return False
    try:
        con = sqlite3.connect(f"{db.resolve().as_uri()}?mode=ro", uri=True)
        try:
            table = con.execute("SELECT 1 FROM sqlite_master WHERE name = 'audit'").fetchone()
            return bool(table) and con.execute("SELECT 1 FROM audit LIMIT 1").fetchone() is not None
        finally:
            con.close()
    except sqlite3.Error:
        return True


def _hash_at(backend: Any, seq: int) -> str | None:
    """The hash of the entry at `seq`, read by its key: a binding is postgres's alone, and the
    backend Protocol reads no single entry. The chain's first entry is `seq` 1."""
    row = backend.db.execute("SELECT hash FROM audit WHERE seq = %s", (seq,)).fetchone()
    return row[0] if row else None


class HomeBinding:
    """A home's binding to the database its container keeps its state in."""

    def __init__(self, home: Path):
        self.path = home / BINDING_FILE
        self.local = home / "egzos.db"
        # Empty is unset: an empty connection string would reach libpq's defaults, not a choice.
        self.named = bool(os.environ.get(DATABASE_URL))
        self.first: str | None = None  # the first entry's hash, once the home is bound
        self._error: Any = ()  # the driver's error class, once it is imported

    def open(self) -> Any:
        """The container's backend, once every check passes; the newest entry seen is rewritten."""
        if not self.named:
            if self.path.exists():
                raise HomeBindingError("unset")
            return SqliteBackend(self.local)
        if _holds_chain(self.local):
            raise HomeBindingError("local")
        bound = self._read()
        try:
            import psycopg

            from egzos.backends.postgres import PostgresBackend
        except ImportError:
            psycopg = None  # type: ignore[assignment]
        if psycopg is None:
            raise HomeBindingError("driver")
        self._error = psycopg.Error
        backend, case = None, "unreachable"
        try:
            backend = PostgresBackend(os.environ[DATABASE_URL], SCHEMA)
            case = self._check(backend, bound)
        except psycopg.Error:
            pass  # its message can echo the connection string: raised below, unchained
        finally:
            if case and backend is not None:
                backend.db.close()
        if case:
            raise HomeBindingError(case)
        return backend

    def _read(self) -> dict[str, Any] | None:
        if not self.path.exists():
            return None
        try:
            doc = json.loads(self.path.read_text())
            if (isinstance(doc["first"], str) and type(doc["seen"]["seq"]) is int
                    and isinstance(doc["seen"]["hash"], str)):
                return doc
        except (OSError, ValueError, KeyError, TypeError):
            pass
        raise HomeBindingError("unreadable")  # never read as absent: its keys would be fresh

    def _check(self, backend: Any, bound: dict[str, Any] | None) -> str | None:
        """Which stop applies, if any. None: a new home on an empty database, or a bound one."""
        last = backend.audit_last()
        if bound is None:
            return "unbound" if last is not None else None
        if last is None or _hash_at(backend, 1) != bound["first"]:
            return "mismatch"
        if _hash_at(backend, bound["seen"]["seq"]) != bound["seen"]["hash"]:
            return "restored"
        self._write(bound["first"], last)
        return None

    def making(self, backend: Any) -> bool:
        """Inside the make's `atomic()` block (§3.6): whether it makes the container here. A home
        with no binding whose block finds a chain already there stops: another home made it."""
        if not self.named or self.path.exists():
            return False
        if backend.audit_last() is not None:
            raise HomeBindingError("taken")
        return True

    def made(self, backend: Any) -> None:
        """After the make's commit, its first entry and the newest seen. A crash before this
        leaves a chain with no binding, which stops at the next open: unavailable, never unsafe."""
        first, last = _hash_at(backend, 1), backend.audit_last()
        if first is not None and last is not None:
            self._write(first, last)

    def record(self, backend: Any) -> None:
        """At a clean close, the newest entry this home has seen. A database that can no longer be
        read leaves the entry recorded before, which it still held."""
        if self.first is None:
            return
        try:
            last = backend.audit_last()
        except self._error:
            return
        if last is not None:
            self._write(self.first, last)

    def _write(self, first: str, last: dict[str, Any]) -> None:
        """Whole or not at all: written to a private file, then renamed over the binding."""
        doc = json.dumps({"first": first, "seen": {"seq": last["seq"], "hash": last["hash"]}})
        tmp = self.path.with_name(f".{self.path.name}.{secrets.token_hex(8)}")
        fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        try:
            with os.fdopen(fd, "w") as fh:
                fh.write(doc)
                fh.flush()
                os.fsync(fh.fileno())
            os.replace(tmp, self.path)
        finally:
            with contextlib.suppress(FileNotFoundError):
                os.unlink(tmp)
        self.first = first
