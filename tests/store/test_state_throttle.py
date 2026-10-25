# Copyright 2026 Ali Sasanian
# SPDX-License-Identifier: LicenseRef-PolyForm-Strict-1.0.0
"""
`ThrottleState` on every backend — storage.md §3.1, the door's throttle counters (rest.md §2 item
7).

On the same substrate and the same connection as `ContainerState`, never process memory: a
restart lifts no throttle (the Chief on #173, option (A)). Every atomicity claim here is checked
with **two backend instances on one store** (two connections), per the issue's instruction,
not two calls on one connection — a single connection serialises its own calls trivially and would
prove nothing about the store's own atomicity.
"""

from __future__ import annotations

import inspect
import threading

from egzos._types import AS_THROTTLE_SURFACES, ThrottleState

#: `ThrottleState` is not `@runtime_checkable`, so conformance is checked as the method set and
#: each method's own signature.
THROTTLE_STATE = frozenset({"throttle_incr", "throttle_count", "throttle_buckets",
                            "throttle_windows", "throttle_forget"})


def test_method_set_matches_the_protocol(backend_class):
    """The backend offers every `ThrottleState` method the Protocol declares, unrenamed."""
    for name in THROTTLE_STATE:
        assert callable(getattr(backend_class, name, None)), name


def test_the_backend_conforms_to_throttle_state_signatures(backend_class):
    """Each method's own parameter names match the Protocol's, so a caller typed against
    `ThrottleState` calls the backend with the same keywords."""
    for name in THROTTLE_STATE:
        protocol_params = list(inspect.signature(getattr(ThrottleState, name)).parameters)
        backend_params = list(inspect.signature(getattr(backend_class, name)).parameters)
        assert backend_params == protocol_params, name


# -- throttle counters -----------------------------------------------------------------------


def test_throttle_incr_starts_at_one(backend: ThrottleState):
    assert backend.throttle_incr("rest", "global", "w1") == 1


def test_throttle_incr_accumulates(backend: ThrottleState):
    assert backend.throttle_incr("rest", "global", "w1") == 1
    assert backend.throttle_incr("rest", "global", "w1") == 2
    assert backend.throttle_incr("rest", "global", "w1") == 3


def test_throttle_count_reads_without_incrementing(backend: ThrottleState):
    backend.throttle_incr("rest", "global", "w1")
    assert backend.throttle_count("rest", "global", "w1") == 1
    assert backend.throttle_count("rest", "global", "w1") == 1  # unchanged by the read


def test_throttle_count_is_zero_for_an_unseen_key(backend: ThrottleState):
    assert backend.throttle_count("rest", "global", "w1") == 0


def test_throttle_keys_are_compared_as_opaque_tuples(backend: ThrottleState):
    """Every one of `surface`, `bucket_key` and `window_key` is its own axis: changing any one
    starts a fresh counter, and the store draws no relationship between two keys."""
    backend.throttle_incr("rest", "global", "w1")
    assert backend.throttle_count("device", "global", "w1") == 0
    assert backend.throttle_count("rest", "source:1.2.3.4", "w1") == 0
    assert backend.throttle_count("rest", "global", "w2") == 0
    assert backend.throttle_count("rest", "global", "w1") == 1


def test_every_throttle_surface_gets_its_own_counter(backend: ThrottleState):
    for surface in AS_THROTTLE_SURFACES:
        assert backend.throttle_incr(surface, "global", "w1") == 1


def test_a_throttle_count_survives_a_restart(make_backend):
    """One substrate (storage.md §3.1): a restart lifts nothing."""
    make_backend().throttle_incr("rest", "global", "w1")
    reopened = make_backend()
    assert reopened.throttle_count("rest", "global", "w1") == 1
    assert reopened.throttle_incr("rest", "global", "w1") == 2


def test_throttle_incr_is_atomic_across_two_connections(make_backend):
    """Of two concurrent incrementers on two connections, the counter ends at exactly 2 and each
    caller's own return value is distinct — no lost update. One backend instance is one
    connection used by one thread at a time (`backends/sqlite.py`'s own documented contract); the
    concurrency this proves is between the two connections, not within either one."""
    a = make_backend()
    b = make_backend()
    results: list[int] = []
    lock = threading.Lock()
    barrier = threading.Barrier(2)

    def incr(conn: ThrottleState) -> None:
        barrier.wait()
        value = conn.throttle_incr("rest", "global", "w1")
        with lock:
            results.append(value)

    t1 = threading.Thread(target=incr, args=(a,))
    t2 = threading.Thread(target=incr, args=(b,))
    t1.start()
    t2.start()
    t1.join()
    t2.join()

    assert sorted(results) == [1, 2]  # every return value distinct, no loss
    assert a.throttle_count("rest", "global", "w1") == 2


def test_throttle_buckets_lists_one_window_and_one_surface(backend: ThrottleState):
    backend.throttle_incr("rest", "global", "w1")
    backend.throttle_incr("rest", "global", "w1")
    backend.throttle_incr("rest", "source:a", "w1")
    backend.throttle_incr("rest", "global", "w2")
    backend.throttle_incr("tap", "global", "w1")
    assert backend.throttle_buckets("rest", "w1") == [("global", 2), ("source:a", 1)]
    assert backend.throttle_buckets("rest", "w3") == []
