# Copyright 2026 Ali Sasanian
# SPDX-License-Identifier: LicenseRef-PolyForm-Strict-1.0.0
"""`ItemStore` (storage.md §2) on every backend: a filter, never a decision; a miss is `None` or a
shorter list (§5). Ids compare as sets but in the one test of `query`'s order: newest `created_at`
first, and items of one second by id, newest first (v0.7 §AF). Ordering by an item's latest write,
[0.3 · 1], is decided, not running, so each item there is written once, as it was created. `text`
is pinned as far as the contract fixes it: a lexical substring of the body, ASCII case aside."""

from __future__ import annotations

import pytest

from egzos._ids import ulid
from egzos.model import ContextItem

AT = "2026-10-24T00:00:00Z"


def _item(iid, scope="n1", kind="memory", key=None, status="unverified", *, body=None, at=AT):
    return ContextItem(id=iid, kind=kind, scope=scope, content={"body": body or iid}, key=key,
                       trust={"status": status},
                       lifecycle={"created_at": at, "updated_at": at, "version": 1},
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


def test_query_lists_newest_first_and_the_items_of_one_second_by_id_newest_first(backend):
    """storage.md §2: `created_at DESC, id DESC`, so `%n` refs agree across backends, ties too."""
    ids = [ulid(1_792_800_000_000 + n) for n in range(6)]  # minted a millisecond apart, ascending
    newest, *same, oldest = ids  # the oldest item holds the newest id: `created_at` decides first
    backend.put(_item(oldest, at="2026-10-23T23:59:59Z"))
    for n in (1, 3, 0, 2):  # one second's items, written in neither id order nor its reverse
        backend.put(_item(same[n]))
    backend.put(_item(newest, at="2026-10-24T00:00:01Z"))
    assert [i.id for i in backend.query(["n1"])] == [newest, *reversed(same), oldest]


#: Every term asked for below is ASCII and in no field but the body: no key, kind, scope or id.
CORPUS = {"x1": "Xylophone lessons on Friday", "x2": "the xylophone is out of tune", "x3": "a tuba"}


def test_text_is_a_substring_of_the_body_whatever_its_ascii_case(backend):
    for iid, body in CORPUS.items():
        backend.put(_item(iid, body=body))
    assert _ids(backend.query(["n1"], text="xylophone")) == ["x1", "x2"]
    assert _ids(backend.query(["n1"], text="XyLoPhOnE")) == ["x1", "x2"]
    assert _ids(backend.query(["n1"], text="ylophone lessons")) == ["x1"]  # mid-word, across words
    assert _ids(backend.query(["n1"], text="TUBA")) == ["x3"]
    assert _ids(backend.query(["n1"], kinds=["memory"], text="tune")) == ["x2"]
    assert backend.query(["n1"], text="zither") == []  # a term absent everywhere matches nothing


@pytest.mark.xfail(strict=True, reason="#324: text matches the whole stored document, not the body")
def test_text_matches_the_body_alone_literally_and_in_any_script(backend):
    backend.put(_item("c1", body="un café noir"))
    backend.put(_item("c2", body="plain words"))
    assert _ids(backend.query(["n1"], text="café")) == ["c1"]
    assert backend.query(["n1"], text="lifecycle") == []  # a field's name is not the body
    assert backend.query(["n1"], text="%") == []  # the query is taken literally
