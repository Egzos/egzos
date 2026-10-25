# Copyright 2026 Ali Sasanian
# SPDX-License-Identifier: LicenseRef-PolyForm-Strict-1.0.0
"""`ItemStore` (storage.md §2) on every backend: a filter, never a decision; a miss is `None` or a
shorter list (§5). Ids compare as sets: `query`'s order, [0.3 · 1], is decided, not running."""

from __future__ import annotations

from egzos.model import ContextItem

AT = "2026-10-24T00:00:00Z"


def _item(iid, scope="n1", kind="memory", key=None, status="unverified"):
    return ContextItem(id=iid, kind=kind, scope=scope, content={"body": iid}, key=key,
                       trust={"status": status},
                       lifecycle={"created_at": AT, "updated_at": AT, "version": 1},
                       extra={"someday_field": {"nested": True}})


def _ids(items):
    return sorted(i.id for i in items)


def test_empty_scopes_return_nothing_and_an_uncovered_scope_contributes_nothing(backend):
    backend.put(_item("a"))
    assert backend.query([]) == []
    assert backend.query(iter(())) == []  # any empty iterable, never all items
    assert _ids(backend.query(["n1", "nowhere"])) == ["a"]


def test_a_tombstoned_item_is_a_miss_unless_asked_for(backend):
    backend.put(_item("a"))
    backend.put(_item("b"))
    assert backend.get("a") == _item("a")  # as put, unknown fields included (context-item.md §1)
    assert backend.tombstone("a") is True
    assert backend.get("a") is None and backend.get("never") is None
    assert _ids(backend.query(["n1"])) == ["b"]
    kept = {i.id: i for i in backend.query(["n1"], include_tombstoned=True)}
    assert sorted(kept) == ["a", "b"]  # a tombstone, not a removal
    assert kept["a"].lifecycle["tombstoned"] is True  # context-item.md §6
    assert backend.tombstone("never") is False


def test_kinds_key_and_statuses_restrict_combine_and_follow_a_replacing_put(backend):
    backend.put(_item("m", kind="memory", key="k", status="verified"))
    backend.put(_item("r", kind="rule", key="k"))
    backend.put(_item("p", kind="preference", key="k2", status="quarantined"))
    backend.put(_item("u"))
    backend.put(_item("x", scope="n2", key="k", status="verified"))
    assert _ids(backend.query(["n1"], kinds=["memory", "rule"])) == ["m", "r", "u"]
    assert _ids(backend.query(["n1"], key="k")) == ["m", "r"]  # exact: not k2, not unkeyed
    assert _ids(backend.query(["n1"], statuses=["verified", "quarantined"])) == ["m", "p"]
    assert _ids(backend.query(["n1"], kinds=["memory"], key="k", statuses=["verified"])) == ["m"]
    assert _ids(backend.query(["n1", "n2"], key="k", statuses=["verified"])) == ["m", "x"]
    backend.put(_item("u", scope="n2", kind="rule", key="k", status="verified"))  # replaces u (§2)
    assert _ids(backend.query(["n1"])) == ["m", "p", "r"] and backend.get("u").scope == "n2"
    assert _ids(backend.query(["n2"], kinds=["rule"], key="k", statuses=["verified"])) == ["u"]
