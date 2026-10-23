# Copyright 2026 Ali Sasanian
# SPDX-License-Identifier: LicenseRef-PolyForm-Strict-1.0.0
"""
`SqliteBackend`'s `ThrottleState` — storage.md §3.1, the door's throttle counters (rest.md §2 item
7).

On the same sqlite file and the same connection as `ContainerState`, never process memory: a
restart lifts no throttle (the Chief on #173, option (A)). Every atomicity claim here is checked
with **two `SqliteBackend` instances on one file** (two connections), per the issue's instruction,
not two calls on one connection — a single connection serialises its own calls trivially and would
prove nothing about the store's own atomicity.
"""

from __future__ import annotations

import inspect
import threading

import pytest

from egzos._types import AS_THROTTLE_SURFACES, ThrottleState
from egzos.backends.sqlite import SqliteBackend

#: `ThrottleState` is not `@runtime_checkable`, so conformance is checked as the method set and
#: each method's own signature.
THROTTLE_STATE = frozenset({"throttle_incr", "throttle_count"})

@pytest.fixture
def backend(tmp_path):
    return SqliteBackend(tmp_path / "container.db")


def test_method_set_matches_the_protocol():
    """`SqliteBackend` offers every `ThrottleState` method the Protocol declares, unrenamed."""
    for name in THROTTLE_STATE:
        assert callable(getattr(SqliteBackend, name, None)), name


def test_sqlite_backend_conforms_to_throttle_state_signatures():
    """Each method's own parameter names match the Protocol's, so a caller typed against
    `ThrottleState` calls `SqliteBackend` with the same keywords."""
    for name in THROTTLE_STATE:
        protocol_params = list(inspect.signature(getattr(ThrottleState, name)).parameters)
        backend_params = list(inspect.signature(getattr(SqliteBackend, name)).parameters)
        assert backend_params == protocol_params, name


# -- throttle counters -----------------------------------------------------------------------


def test_throttle_incr_starts_at_one(backend: SqliteBackend):
    assert backend.throttle_incr("login", "global", "w1") == 1


def test_throttle_incr_accumulates(backend: SqliteBackend):
    assert backend.throttle_incr("login", "global", "w1") == 1
    assert backend.throttle_incr("login", "global", "w1") == 2
    assert backend.throttle_incr("login", "global", "w1") == 3


def test_throttle_count_reads_without_incrementing(backend: SqliteBackend):
    backend.throttle_incr("login", "global", "w1")
    assert backend.throttle_count("login", "global", "w1") == 1
    assert backend.throttle_count("login", "global", "w1") == 1  # unchanged by the read


def test_throttle_count_is_zero_for_an_unseen_key(backend: SqliteBackend):
    assert backend.throttle_count("login", "global", "w1") == 0


def test_throttle_keys_are_compared_as_opaque_tuples(backend: SqliteBackend):
    """Every one of `surface`, `bucket_key` and `window_key` is its own axis: changing any one
    starts a fresh counter, and the store draws no relationship between two keys."""
    backend.throttle_incr("login", "global", "w1")
    assert backend.throttle_count("device", "global", "w1") == 0
    assert backend.throttle_count("login", "source:1.2.3.4", "w1") == 0
    assert backend.throttle_count("login", "global", "w2") == 0
    assert backend.throttle_count("login", "global", "w1") == 1


def test_every_throttle_surface_gets_its_own_counter(backend: SqliteBackend):
    for surface in AS_THROTTLE_SURFACES:
        assert backend.throttle_incr(surface, "global", "w1") == 1


def test_a_throttle_count_survives_a_restart(tmp_path):
    """One substrate (storage.md §3.1): a restart lifts nothing."""
    path = tmp_path / "container.db"
    SqliteBackend(path).throttle_incr("login", "global", "w1")
    reopened = SqliteBackend(path)
    assert reopened.throttle_count("login", "global", "w1") == 1
    assert reopened.throttle_incr("login", "global", "w1") == 2


def test_throttle_incr_is_atomic_across_two_connections(tmp_path):
    """Of two concurrent incrementers on two connections, the counter ends at exactly 2 and each
    caller's own return value is distinct — no lost update. One `SqliteBackend` is one sqlite
    connection used by one thread at a time (the module's own documented contract); the
    concurrency this proves is between the two connections, not within either one."""
    path = tmp_path / "container.db"
    a = SqliteBackend(path)
    b = SqliteBackend(path)
    results: list[int] = []
    lock = threading.Lock()
    barrier = threading.Barrier(2)

    def incr(conn: SqliteBackend) -> None:
        barrier.wait()
        value = conn.throttle_incr("login", "global", "w1")
        with lock:
            results.append(value)

    t1 = threading.Thread(target=incr, args=(a,))
    t2 = threading.Thread(target=incr, args=(b,))
    t1.start()
    t2.start()
    t1.join()
    t2.join()

    assert sorted(results) == [1, 2]  # every return value distinct, no loss
    assert a.throttle_count("login", "global", "w1") == 2
