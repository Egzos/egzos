# Copyright 2026 Ali Sasanian
# SPDX-License-Identifier: LicenseRef-PolyForm-Strict-1.0.0
"""`UploadState` (storage.md §3.4) on every backend: each step spent once, records kept."""

from __future__ import annotations

import inspect
import threading

import pytest

from egzos._types import UploadState

UPLOAD_STATE = frozenset({"put_upload", "get_upload", "list_uploads", "spend_upload"})


def _upload(uid="u1", principal="t1"):
    return {"id": uid, "principal": principal, "actor": "self", "scope": "n", "name": "a.txt",
            "mime": "text/plain", "size": 3, "sha256": "0" * 64,
            "opened_at": "2026-10-23T00:00:00Z", "expires_at": "2026-10-23T01:00:00Z",
            "staged": False, "item": None, "promoted": False, "discarded": False}


def test_the_protocol_is_pinned_and_the_backend_matches_it(backend_class):
    names = {n for n, _ in inspect.getmembers(UploadState, inspect.isfunction) if n[0] != "_"}
    assert names == UPLOAD_STATE
    for name in names:
        expected = list(inspect.signature(getattr(UploadState, name)).parameters)
        assert list(inspect.signature(getattr(backend_class, name)).parameters) == expected, name


def test_each_step_spends_once_and_apart(backend):
    backend.put_upload(_upload())
    assert backend.spend_upload("u1", "bytes") is True
    assert backend.spend_upload("u1", "bytes") is False
    assert backend.spend_upload("u1", "item") is True
    assert backend.spend_upload("u1", "item") is False
    assert backend.spend_upload("never", "bytes") is False


def test_a_spend_rolls_back_with_its_transaction(backend):
    backend.put_upload(_upload())
    with pytest.raises(RuntimeError), backend.atomic():
        assert backend.spend_upload("u1", "item") is True
        raise RuntimeError
    assert backend.spend_upload("u1", "item") is True


def test_records_list_by_principal_and_keep_the_discarded(backend):
    backend.put_upload(_upload("a", "t1"))
    backend.put_upload(_upload("b", "t2"))
    backend.put_upload({**_upload("a", "t1"), "discarded": True})
    assert [u["id"] for u in backend.list_uploads("t1")] == ["a"]
    assert backend.get_upload("a")["discarded"] is True
    assert sorted(u["id"] for u in backend.list_uploads()) == ["a", "b"]
    assert backend.get_upload("never") is None


def test_two_connections_spending_one_step_proceed_once(make_backend):
    make_backend().put_upload(_upload())
    seen: list[bool] = []
    gate = threading.Barrier(2)

    def spend():
        b = make_backend()
        gate.wait()
        seen.append(b.spend_upload("u1", "item"))

    threads = [threading.Thread(target=spend) for _ in range(2)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert sorted(seen) == [False, True]
