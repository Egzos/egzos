# Copyright 2026 Ali Sasanian
# SPDX-License-Identifier: LicenseRef-PolyForm-Strict-1.0.0
"""Which database a container keeps its state in, where it keeps its blobs, and its home's binding
to both (storage.md §3.7, §4).

`EGZOS_DATABASE_URL` names a postgres database, whose schema `egzos` holds the container's state;
unset, the state stays in the home's own `egzos.db`, as before. A home made on a named database
keeps `binding.json` beside its keys: the hash of the chain's first entry, and the `seq` and hash
of the newest entry it has seen, none of them secret. Every open checks the two before anything
serves, and stops with `HomeBindingError`. The connection string is the host's secret: it is read
from the environment where it is used and kept in no local, attribute, file or message, and a
driver's error, which can echo it, is never chained to the one raised.

The six `EGZOS_BLOBS_S3_*` variables name an object store beside a named database; none set, blobs
stay in the home's `blobs/`. The binding records the blob root, `"home"` or the store's endpoint,
bucket and prefix, and every open stops when the root named differs. The store's two keys are read
from the environment only where the store is built, and handed to OpenDAL.

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
from urllib.parse import urlsplit

from egzos.backends import SqliteBackend
from egzos.store.blobs import BlobStore

DATABASE_URL = "EGZOS_DATABASE_URL"
#: The object store's six variables (§3.7): the first four name it, the last two are its keys.
BLOBS_S3 = ("EGZOS_BLOBS_S3_ENDPOINT", "EGZOS_BLOBS_S3_REGION", "EGZOS_BLOBS_S3_BUCKET",
            "EGZOS_BLOBS_S3_PREFIX", "EGZOS_BLOBS_S3_ACCESS_KEY_ID",
            "EGZOS_BLOBS_S3_SECRET_ACCESS_KEY")
#: The blob root of a home whose blobs are its own `blobs/`; a binding that records none reads so.
HOME_BLOBS = "home"
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
    "blobs-partial": "the EGZOS_BLOBS_S3_* variables name an object store all six or none, and "
                     "these are unset: ",
    "blobs-alone": "the EGZOS_BLOBS_S3_* variables name an object store, and EGZOS_DATABASE_URL "
                   "is unset: an object store is named only beside a named database",
    "blobs-userinfo": "EGZOS_BLOBS_S3_ENDPOINT holds userinfo: the object store's keys travel in "
                      "EGZOS_BLOBS_S3_ACCESS_KEY_ID and EGZOS_BLOBS_S3_SECRET_ACCESS_KEY only",
    "blobs-moved": "the blob root the EGZOS_BLOBS_S3_* variables name (the home's blobs/ when they "
                   "are unset) differs from the one this home recorded: blobs never move to "
                   "another store, or back to the home, without the operator's rebind",
    "blobs-driver": "the EGZOS_BLOBS_S3_* variables are set, and object store support is not "
                    'installed: pip install "egzos[objects]"',
    "blobs-endpoint": "EGZOS_BLOBS_S3_ENDPOINT is not an endpoint the object store can use: check "
                      "its scheme, host and port",
}


class HomeBindingError(RuntimeError):
    """The container stops before anything serves (storage.md §3.7): its home and the database do
    not belong together, or the database or the object store cannot be used. `case` names which;
    the message names the variables, never a value."""

    def __init__(self, case: str, unset: tuple[str, ...] = ()):
        self.case = case
        super().__init__(f"the container stops ({case}): {_CASES[case]}{', '.join(unset)}")


def _endpoint_fault(endpoint: str) -> str | None:
    """The stop an endpoint calls for, or None: userinfo in its authority, read by urllib's parser
    with a scheme or without (OpenDAL then adds one), or an endpoint that parser refuses. Never
    raises, so the endpoint is in no frame a stop passes through (a6 on #345)."""
    try:
        authority = urlsplit(endpoint if "://" in endpoint else "//" + endpoint).netloc
    except ValueError:
        return "blobs-endpoint"
    return "blobs-userinfo" if "@" in authority else None


def blob_root() -> str | dict[str, str]:
    """The blob root the environment names (§3.7, §4): the home's `blobs/`, or the object store's
    endpoint, bucket and prefix, none of them secret, spelled as OpenDAL roots them, so that one
    root spelled twice is one root. Empty is unset, as for `EGZOS_DATABASE_URL`; a prefix of `/`
    is the bucket's root. Stops when the six are set in part, beside no named database, or the
    endpoint holds userinfo or is no endpoint, before any connection is made."""
    unset = tuple(name for name in BLOBS_S3 if not os.environ.get(name))
    if len(unset) == len(BLOBS_S3):
        return HOME_BLOBS
    if unset:
        raise HomeBindingError("blobs-partial", unset)
    if not os.environ.get(DATABASE_URL):
        raise HomeBindingError("blobs-alone")
    if (fault := _endpoint_fault(os.environ["EGZOS_BLOBS_S3_ENDPOINT"])) is not None:
        raise HomeBindingError(fault)
    return {"endpoint": os.environ["EGZOS_BLOBS_S3_ENDPOINT"].rstrip("/"),
            "bucket": os.environ["EGZOS_BLOBS_S3_BUCKET"],
            "prefix": os.environ["EGZOS_BLOBS_S3_PREFIX"].strip("/")}


def object_store(root: dict[str, str]) -> Any:
    """An `ObjectBlobStore` at `root`, on an s3 operator as Supabase Storage needs one: the region
    signs each request, addressing is path-style (OpenDAL's default), and nothing asks for
    Content-MD5 or SSE, which it does not support. It does not honour If-None-Match either, so a
    layer turns off the create-only write and `put` asks `exists` before it writes. The keys are
    read from the environment here and handed to OpenDAL, kept in no attribute, file or message,
    and OpenDAL reads no other credentials (no AWS config, no instance metadata). Building it does
    no I/O. Stops when OpenDAL is not installed."""
    try:
        import opendal
        from opendal.layers import CapabilityOverrideLayer
    except ImportError:
        opendal = None  # type: ignore[assignment]
    if opendal is None:
        raise HomeBindingError("blobs-driver")
    from egzos.store.objects import ObjectBlobStore

    try:
        op = opendal.Operator(
            "s3", endpoint=root["endpoint"], bucket=root["bucket"], root=f"/{root['prefix']}",
            region=os.environ["EGZOS_BLOBS_S3_REGION"],
            access_key_id=os.environ["EGZOS_BLOBS_S3_ACCESS_KEY_ID"],
            secret_access_key=os.environ["EGZOS_BLOBS_S3_SECRET_ACCESS_KEY"],
            disable_config_load="true", disable_ec2_metadata="true")
    except Exception:  # noqa: BLE001 — OpenDAL's own text can carry the endpoint or a key
        op = None
    if op is None:  # raised past the except block, so no OpenDAL error is chained (a1r on #345)
        raise HomeBindingError("blobs-endpoint")
    return ObjectBlobStore(op.layer(CapabilityOverrideLayer("write_with_if_not_exists=false")))


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
    """A home's binding to the database its container keeps its state in, and to its blob root."""

    def __init__(self, home: Path):
        self.home = home
        self.path = home / BINDING_FILE
        self.local = home / "egzos.db"
        # Empty is unset: an empty connection string would reach libpq's defaults, not a choice.
        self.named = bool(os.environ.get(DATABASE_URL))
        self.first: str | None = None  # the first entry's hash, once the home is bound
        self.blobs: str | dict[str, str] = HOME_BLOBS  # the blob root named, as `open` read it
        self._error: Any = ()  # the driver's error class, once it is imported

    def open(self) -> tuple[Any, Any]:
        """The container's backend and blob store, once every check passes. The object store's
        own stops come first, and its store is built before any connection, since that does no
        I/O; a home's `blobs/` is made only once the checks pass."""
        self.blobs = blob_root()
        objects = None if self.blobs == HOME_BLOBS else object_store(self.blobs)
        backend = self._backend()
        return backend, objects if objects is not None else BlobStore(self.home / "blobs")

    def _backend(self) -> Any:
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
        if bound.get("blobs", HOME_BLOBS) != self.blobs:
            return "blobs-moved"
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
        doc = json.dumps({"first": first, "seen": {"seq": last["seq"], "hash": last["hash"]},
                          "blobs": self.blobs})
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
