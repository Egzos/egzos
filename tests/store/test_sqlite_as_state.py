# Copyright 2026 Ali Sasanian
# SPDX-License-Identifier: LicenseRef-PolyForm-Strict-1.0.0
"""
`SqliteBackend`'s `ASState` — clients, codes and decided requests (storage.md §3.1, draft binding
on #173; issue #262 slice 2).

Device authorizations and refresh chains are slice 3's and are not implemented here. Every
atomicity claim is checked with **two `SqliteBackend` instances on one file** (two connections),
per the issue's instruction, not two calls on one connection.
"""

from __future__ import annotations

import inspect
import threading

import pytest

from egzos._types import (
    ASGrant,
    ASState,
    AuthorizationCodeRecord,
    ClientRegistration,
    DecidedRequestRecord,
)
from egzos.backends.sqlite import SqliteBackend

#: The methods this slice implements. `ASState` also declares the device and refresh groups
#: (slice 3), not yet on `SqliteBackend`, so conformance here is checked method by method rather
#: than with `test_as_state.py`'s whole-Protocol method set.
AS_STATE_CLIENTS = frozenset({"put_client", "get_client", "remove_client"})
AS_STATE_CODES = frozenset({"put_code", "consume_code"})
AS_STATE_DECIDED = frozenset({"put_decided", "get_decided", "claim_resubmission"})
SLICE_METHODS = AS_STATE_CLIENTS | AS_STATE_CODES | AS_STATE_DECIDED

CLIENT_ID = "client-1"
CODE_HASH = "c" * 64
SESSION_HASH = "a" * 64
REQUEST_KEY = "r" * 64


def _client(**over: object) -> ClientRegistration:
    base: dict[str, object] = {
        "client_id": CLIENT_ID,
        "client_name": "Test Client",
        "client_type": "browser",
        "redirect_uris": ["http://127.0.0.1/callback"],
        "registered_at": "2026-10-12T09:00:00Z",
    }
    base.update(over)
    return base  # type: ignore[return-value]


def _grant(**over: object) -> ASGrant:
    base: dict[str, object] = {
        "capabilities": ["fetch"],
        "scopes": ["fetch"],
        "principal": "interactive",
        "grant_expires_at": "2026-11-11T09:00:00Z",
    }
    base.update(over)
    return base  # type: ignore[return-value]


def _code(**over: object) -> AuthorizationCodeRecord:
    base: dict[str, object] = {
        "code_hash": CODE_HASH,
        "client_id": CLIENT_ID,
        "redirect_uri": "http://127.0.0.1/callback",
        "code_challenge": "challenge",
        "session_hash": SESSION_HASH,
        "grant": _grant(),
        "expires_at": "2026-10-12T09:01:00Z",
    }
    base.update(over)
    return base  # type: ignore[return-value]


def _decided(**over: object) -> DecidedRequestRecord:
    base: dict[str, object] = {
        "request_key": REQUEST_KEY,
        "session_hash": SESSION_HASH,
        "decision": "granted",
        "decided_at": "2026-10-12T09:00:00Z",
        "resubmission_seen": False,
    }
    base.update(over)
    return base  # type: ignore[return-value]


@pytest.fixture
def backend(tmp_path):
    return SqliteBackend(tmp_path / "container.db")


def test_method_set_matches_the_protocol():
    """`SqliteBackend` offers every method this slice adds, with no renaming."""
    for name in SLICE_METHODS:
        assert callable(getattr(SqliteBackend, name, None)), name


def test_sqlite_backend_conforms_to_as_state_signatures():
    """Each method's own parameter names match `ASState`'s, so a caller typed against the
    Protocol calls `SqliteBackend` with the same keywords."""
    for name in SLICE_METHODS:
        protocol_params = list(inspect.signature(getattr(ASState, name)).parameters)
        backend_params = list(inspect.signature(getattr(SqliteBackend, name)).parameters)
        assert backend_params == protocol_params, name


# -- clients ----------------------------------------------------------------------------------


def test_put_then_get_client(backend: SqliteBackend):
    backend.put_client(_client())
    assert backend.get_client(CLIENT_ID) == _client()


def test_get_client_is_none_for_an_absent_id(backend: SqliteBackend):
    assert backend.get_client("unknown") is None


def test_put_client_amends_an_existing_entry(backend: SqliteBackend):
    """§5: `put_client` is add AND amend — a second put on the same `client_id` replaces the
    entry whole, it does not merge or refuse."""
    backend.put_client(_client())
    backend.put_client(_client(client_name="Renamed", redirect_uris=["http://127.0.0.1/cb2"]))
    record = backend.get_client(CLIENT_ID)
    assert record["client_name"] == "Renamed"
    assert record["redirect_uris"] == ["http://127.0.0.1/cb2"]


def test_remove_client_true_then_false(backend: SqliteBackend):
    backend.put_client(_client())
    assert backend.remove_client(CLIENT_ID) is True
    assert backend.remove_client(CLIENT_ID) is False
    assert backend.get_client(CLIENT_ID) is None


def test_remove_client_is_false_for_an_absent_id(backend: SqliteBackend):
    assert backend.remove_client("unknown") is False


def test_a_client_survives_a_restart(tmp_path):
    """One substrate: a reopened backend on the same path finds the registration intact."""
    path = tmp_path / "container.db"
    SqliteBackend(path).put_client(_client())
    reopened = SqliteBackend(path)
    assert reopened.get_client(CLIENT_ID) == _client()


# -- codes --------------------------------------------------------------------------------------


def test_put_then_consume_code(backend: SqliteBackend):
    backend.put_code(_code())
    assert backend.consume_code(CODE_HASH) == _code()


def test_consume_code_is_none_for_an_absent_hash(backend: SqliteBackend):
    assert backend.consume_code("unknown") is None


def test_consume_code_spends_the_code(backend: SqliteBackend):
    """§3.1 rule 1: the code is spent on the first redemption attempt; every later call misses."""
    backend.put_code(_code())
    assert backend.consume_code(CODE_HASH) is not None
    assert backend.consume_code(CODE_HASH) is None


def test_consume_code_does_not_judge_expiry(backend: SqliteBackend):
    """§3.1 rule 1: `consume_code` never looks at `expires_at` — Trust re-checks what it gets
    back. An already-expired record is still returned, not silently dropped."""
    backend.put_code(_code(expires_at="2000-01-01T00:00:00Z"))
    record = backend.consume_code(CODE_HASH)
    assert record is not None
    assert record["expires_at"] == "2000-01-01T00:00:00Z"


def test_a_code_survives_a_restart(tmp_path):
    path = tmp_path / "container.db"
    SqliteBackend(path).put_code(_code())
    reopened = SqliteBackend(path)
    assert reopened.consume_code(CODE_HASH) == _code()


def test_consume_code_is_atomic_across_two_connections(tmp_path):
    """Of two concurrent `consume_code` calls on the same `code_hash`, exactly one observes the
    record before the other's delete — the loser gets `None`, never a torn or duplicated read."""
    path = tmp_path / "container.db"
    a = SqliteBackend(path)
    a.put_code(_code())
    b = SqliteBackend(path)

    results: list[AuthorizationCodeRecord | None] = []
    lock = threading.Lock()
    barrier = threading.Barrier(2)

    def consume(conn: SqliteBackend) -> None:
        barrier.wait()
        record = conn.consume_code(CODE_HASH)
        with lock:
            results.append(record)

    t1 = threading.Thread(target=consume, args=(a,))
    t2 = threading.Thread(target=consume, args=(b,))
    t1.start()
    t2.start()
    t1.join()
    t2.join()

    winners = [r for r in results if r is not None]
    losers = [r for r in results if r is None]
    assert len(winners) == 1
    assert len(losers) == 1
    assert winners[0] == _code()
    assert a.consume_code(CODE_HASH) is None  # spent either way


# -- decided requests ---------------------------------------------------------------------------


def test_put_then_get_decided(backend: SqliteBackend):
    backend.put_decided(_decided())
    assert backend.get_decided(REQUEST_KEY) == _decided()


def test_get_decided_is_none_for_an_absent_key(backend: SqliteBackend):
    assert backend.get_decided("unknown") is None


def test_put_decided_is_insert_only(backend: SqliteBackend):
    """#226: a put on an existing `request_key` changes nothing."""
    backend.put_decided(_decided())
    backend.put_decided(_decided(decision="denied"))
    assert backend.get_decided(REQUEST_KEY)["decision"] == "granted"


def test_a_decided_request_survives_a_restart(tmp_path):
    path = tmp_path / "container.db"
    SqliteBackend(path).put_decided(_decided())
    reopened = SqliteBackend(path)
    assert reopened.get_decided(REQUEST_KEY) == _decided()


def test_claim_resubmission_true_once_then_false(backend: SqliteBackend):
    backend.put_decided(_decided())
    assert backend.claim_resubmission(SESSION_HASH, REQUEST_KEY) is True
    assert backend.claim_resubmission(SESSION_HASH, REQUEST_KEY) is False


def test_claim_resubmission_sets_resubmission_seen(backend: SqliteBackend):
    backend.put_decided(_decided())
    backend.claim_resubmission(SESSION_HASH, REQUEST_KEY)
    assert backend.get_decided(REQUEST_KEY)["resubmission_seen"] is True


def test_claim_resubmission_is_false_for_an_unrecorded_request_key(backend: SqliteBackend):
    assert backend.claim_resubmission(SESSION_HASH, "unknown") is False


def test_claim_resubmission_is_false_for_a_mismatched_session(backend: SqliteBackend):
    """§11.0 substep 1: the claim is per deciding session — another session's claim misses."""
    backend.put_decided(_decided())
    assert backend.claim_resubmission("b" * 64, REQUEST_KEY) is False
    # and the real session can still claim it afterwards
    assert backend.claim_resubmission(SESSION_HASH, REQUEST_KEY) is True


def test_claim_resubmission_is_atomic_across_two_connections(tmp_path):
    """Of two concurrent claims on the same `(session_hash, request_key)`, exactly one observes
    `resubmission_seen` as still unset."""
    path = tmp_path / "container.db"
    a = SqliteBackend(path)
    a.put_decided(_decided())
    b = SqliteBackend(path)

    results: list[bool] = []
    lock = threading.Lock()
    barrier = threading.Barrier(2)

    def claim(conn: SqliteBackend) -> None:
        barrier.wait()
        result = conn.claim_resubmission(SESSION_HASH, REQUEST_KEY)
        with lock:
            results.append(result)

    t1 = threading.Thread(target=claim, args=(a,))
    t2 = threading.Thread(target=claim, args=(b,))
    t1.start()
    t2.start()
    t1.join()
    t2.join()

    assert sorted(results) == [False, True]
    assert a.get_decided(REQUEST_KEY)["resubmission_seen"] is True
