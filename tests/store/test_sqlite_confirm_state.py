# Copyright 2026 Ali Sasanian
# SPDX-License-Identifier: LicenseRef-PolyForm-Strict-1.0.0
"""`SqliteBackend`'s `ConfirmState` (storage.md §3.3): challenges spent once, credentials kept."""

from __future__ import annotations

import inspect
import threading

import pytest

from egzos._types import ConfirmState
from egzos.backends.sqlite import SqliteBackend

CONFIRM_STATE = frozenset({"put_challenge", "spend_challenge", "forget_challenges",
                           "put_credential", "get_credential", "list_credentials"})


@pytest.fixture
def backend(tmp_path):
    return SqliteBackend(tmp_path / "container.db")


def _challenge(cid="c1"):
    return {"id": cid, "principal": "t", "act": "move", "subject": "i", "destination": "n",
            "delta": [], "expires_at": "2099-01-01T00:00:00Z"}


def test_the_protocol_is_pinned_and_the_backend_matches_it():
    names = {n for n, _ in inspect.getmembers(ConfirmState, inspect.isfunction) if n[0] != "_"}
    assert names == CONFIRM_STATE
    for name in names:
        expected = list(inspect.signature(getattr(ConfirmState, name)).parameters)
        assert list(inspect.signature(getattr(SqliteBackend, name)).parameters) == expected, name


def test_a_challenge_spends_once(backend):
    backend.put_challenge(_challenge())
    assert backend.spend_challenge("c1")["spent"] is False
    assert backend.spend_challenge("c1")["spent"] is True
    assert backend.spend_challenge("never") is None


def test_two_connections_spending_one_challenge_see_it_fresh_once(tmp_path):
    SqliteBackend(tmp_path / "c.db").put_challenge(_challenge())
    seen: list[bool] = []
    gate = threading.Barrier(2)

    def spend():
        b = SqliteBackend(tmp_path / "c.db")
        gate.wait()
        seen.append(b.spend_challenge("c1")["spent"])

    threads = [threading.Thread(target=spend) for _ in range(2)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert sorted(seen) == [False, True]


def test_credentials_list_by_person_and_keep_the_removed(backend):
    base = {"credential_id": "x", "public_key": "k", "sign_count": 0, "rp_id": "egzos.io",
            "name": "phone", "created_at": "t", "last_used": None, "removed": False}
    backend.put_credential({**base, "id": "a", "person": "self"})
    backend.put_credential({**base, "id": "b", "person": "user:alice"})
    backend.put_credential({**base, "id": "a", "person": "self", "removed": True})
    assert [c["id"] for c in backend.list_credentials("self")] == ["a"]
    assert backend.get_credential("a")["removed"] is True
    assert sorted(c["id"] for c in backend.list_credentials()) == ["a", "b"]
