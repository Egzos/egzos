# Copyright 2026 Ali Sasanian
# SPDX-License-Identifier: LicenseRef-PolyForm-Strict-1.0.0
"""`SqliteBackend`'s `GrantState` (storage.md §3.5): a grant spent once, forgotten once expired."""

from __future__ import annotations

import inspect
import threading

import pytest

from egzos._types import GrantState
from egzos.backends.sqlite import SqliteBackend

GRANT_STATE = frozenset({"spend_grant", "forget_grants"})
WHEN = "2026-10-23T00:05:00.000000Z"


@pytest.fixture
def backend(tmp_path):
    return SqliteBackend(tmp_path / "container.db")


def test_the_protocol_is_pinned_and_the_backend_matches_it():
    names = {n for n, _ in inspect.getmembers(GrantState, inspect.isfunction) if n[0] != "_"}
    assert names == GRANT_STATE
    for name in names:
        expected = list(inspect.signature(getattr(GrantState, name)).parameters)
        assert list(inspect.signature(getattr(SqliteBackend, name)).parameters) == expected, name


def test_a_grant_spends_once_and_its_record_is_kept_until_it_expires(backend):
    assert backend.spend_grant("h", WHEN) is True
    assert backend.spend_grant("h", WHEN) is False
    backend.forget_grants(WHEN)  # expired at that time, not before it: kept
    assert backend.spend_grant("h", WHEN) is False
    backend.forget_grants("2026-10-23T00:05:00.000001Z")
    assert backend.spend_grant("h", WHEN) is True


def test_a_spend_inside_a_transaction_is_refused_and_records_nothing(backend):
    with backend.atomic(), pytest.raises(RuntimeError):
        backend.spend_grant("h", WHEN)  # a rollback would unspend it
    assert backend.spend_grant("h", WHEN) is True


def test_two_connections_spending_one_grant_proceed_once(tmp_path):
    SqliteBackend(tmp_path / "c.db")
    seen: list[bool] = []
    gate = threading.Barrier(2)

    def spend():
        b = SqliteBackend(tmp_path / "c.db")
        gate.wait()
        seen.append(b.spend_grant("h", WHEN))

    threads = [threading.Thread(target=spend) for _ in range(2)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert sorted(seen) == [False, True]
