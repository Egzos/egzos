# Copyright 2026 Ali Sasanian
# SPDX-License-Identifier: LicenseRef-PolyForm-Strict-1.0.0
"""
`SqliteBackend`'s `ASGateState` — storage.md §3.1, draft binding on #173.

Sessions and throttle counters, on the same sqlite file and the same connection as
`ContainerState`, never process memory: a restart lifts no throttle and ends no session (the
Chief on #173, option (A)). Every atomicity claim here is checked with **two `SqliteBackend`
instances on one file** (two connections), per the issue's instruction, not two calls on one
connection — a single connection serialises its own calls trivially and would prove nothing about
the store's own atomicity.
"""

from __future__ import annotations

import inspect
import threading

import pytest

from egzos._types import AS_THROTTLE_SURFACES, ASGateState, SessionRecord
from egzos.backends.sqlite import SqliteBackend

#: `ASGateState` is not `@runtime_checkable` (a1p's `_types.py`), so conformance is checked the
#: way `tests/_types/test_as_state.py` does: the method set, and each method's own signature.
AS_GATE_STATE = frozenset(
    {"put_session", "get_session", "touch_session", "end_session", "throttle_incr",
     "throttle_count"}
)

SESSION_HASH = "a" * 64
CREATED_AT = "2026-10-12T09:00:00Z"
LAST_SEEN_AT = "2026-10-12T09:00:00Z"


def _session(**over: object) -> SessionRecord:
    base: dict[str, object] = {
        "session_hash": SESSION_HASH,
        "created_at": CREATED_AT,
        "last_seen_at": LAST_SEEN_AT,
    }
    base.update(over)
    return base  # type: ignore[return-value]


@pytest.fixture
def backend(tmp_path):
    return SqliteBackend(tmp_path / "container.db")


def test_method_set_matches_the_protocol():
    """`SqliteBackend` offers every `ASGateState` method the Protocol declares, with no renaming."""
    for name in AS_GATE_STATE:
        assert callable(getattr(SqliteBackend, name, None)), name


def test_sqlite_backend_conforms_to_as_gate_state_signatures():
    """Each method's own parameter names match the Protocol's, so a caller typed against
    `ASGateState` calls `SqliteBackend` with the same keywords."""
    for name in AS_GATE_STATE:
        protocol_params = list(inspect.signature(getattr(ASGateState, name)).parameters)
        backend_params = list(inspect.signature(getattr(SqliteBackend, name)).parameters)
        assert backend_params == protocol_params, name


# -- sessions -------------------------------------------------------------------------------


def test_put_then_get_session(backend: SqliteBackend):
    backend.put_session(_session())
    assert backend.get_session(SESSION_HASH) == _session()


def test_get_session_is_none_for_an_absent_key(backend: SqliteBackend):
    assert backend.get_session("unknown") is None


def test_touch_session_sets_last_seen_at_alone(backend: SqliteBackend):
    backend.put_session(_session())
    assert backend.touch_session(SESSION_HASH, "2026-10-12T09:05:00Z") is True
    record = backend.get_session(SESSION_HASH)
    assert record["last_seen_at"] == "2026-10-12T09:05:00Z"
    assert record["created_at"] == CREATED_AT  # untouched


def test_touch_session_is_false_for_an_absent_key(backend: SqliteBackend):
    assert backend.touch_session("unknown", "2026-10-12T09:05:00Z") is False


def test_end_session_then_get_is_a_miss(backend: SqliteBackend):
    backend.put_session(_session())
    assert backend.end_session(SESSION_HASH) is True
    assert backend.get_session(SESSION_HASH) is None


def test_end_session_twice_is_true_then_false(backend: SqliteBackend):
    backend.put_session(_session())
    assert backend.end_session(SESSION_HASH) is True
    assert backend.end_session(SESSION_HASH) is False


def test_touch_after_end_is_false(backend: SqliteBackend):
    """A poll that races a sign-out must not resurrect the session (sessions.py's `resolve`)."""
    backend.put_session(_session())
    backend.end_session(SESSION_HASH)
    assert backend.touch_session(SESSION_HASH, "2026-10-12T09:05:00Z") is False


def test_a_session_survives_a_restart(tmp_path):
    """One substrate: a reopened backend on the same path finds the session intact."""
    path = tmp_path / "container.db"
    SqliteBackend(path).put_session(_session())
    reopened = SqliteBackend(path)
    assert reopened.get_session(SESSION_HASH) == _session()


def test_touch_session_is_atomic_across_two_connections(tmp_path):
    """Of two concurrent `touch_session` calls on the same key, each still observes a consistent
    record and only one of two racing writers' stamps survives — never a torn write."""
    path = tmp_path / "container.db"
    a = SqliteBackend(path)
    a.put_session(_session())
    b = SqliteBackend(path)

    results: list[bool] = []
    barrier = threading.Barrier(2)

    def touch(conn: SqliteBackend, stamp: str) -> None:
        barrier.wait()
        results.append(conn.touch_session(SESSION_HASH, stamp))

    t1 = threading.Thread(target=touch, args=(a, "2026-10-12T09:05:00Z"))
    t2 = threading.Thread(target=touch, args=(b, "2026-10-12T09:06:00Z"))
    t1.start()
    t2.start()
    t1.join()
    t2.join()

    assert results == [True, True]
    record = a.get_session(SESSION_HASH)
    assert record["last_seen_at"] in ("2026-10-12T09:05:00Z", "2026-10-12T09:06:00Z")


def test_touch_after_end_is_false_across_two_connections(tmp_path):
    """Carry-forward from #263's review (a1r minor 1): a `touch_session` that races a concurrent
    `end_session` on another connection must not resurrect the session. Unlike
    `test_touch_session_is_atomic_across_two_connections` and
    `test_end_session_is_atomic_across_two_connections`, which race a method against itself, this
    races the two methods against each other."""
    path = tmp_path / "container.db"
    a = SqliteBackend(path)
    a.put_session(_session())
    b = SqliteBackend(path)

    results: dict[str, bool] = {}
    barrier = threading.Barrier(2)

    def end(conn: SqliteBackend) -> None:
        barrier.wait()
        results["end"] = conn.end_session(SESSION_HASH)

    def touch(conn: SqliteBackend) -> None:
        barrier.wait()
        results["touch"] = conn.touch_session(SESSION_HASH, "2026-10-12T09:05:00Z")

    t1 = threading.Thread(target=end, args=(a,))
    t2 = threading.Thread(target=touch, args=(b,))
    t1.start()
    t2.start()
    t1.join()
    t2.join()

    # `end_session` always finds the session, whichever side ran first: `touch_session` never
    # recreates an absent record, so the session is never resurrected after it ends.
    assert results["end"] is True
    assert a.get_session(SESSION_HASH) is None


def test_end_session_is_atomic_across_two_connections(tmp_path):
    """Of two concurrent `end_session` calls on the same key, exactly one observes the record
    before the other's delete — the other finds it already gone."""
    path = tmp_path / "container.db"
    a = SqliteBackend(path)
    a.put_session(_session())
    b = SqliteBackend(path)

    results: list[bool] = []
    barrier = threading.Barrier(2)

    def end(conn: SqliteBackend) -> None:
        barrier.wait()
        results.append(conn.end_session(SESSION_HASH))

    t1 = threading.Thread(target=end, args=(a,))
    t2 = threading.Thread(target=end, args=(b,))
    t1.start()
    t2.start()
    t1.join()
    t2.join()

    assert sorted(results) == [False, True]
    assert a.get_session(SESSION_HASH) is None


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
