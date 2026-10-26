# Copyright 2026 Ali Sasanian
# SPDX-License-Identifier: LicenseRef-PolyForm-Strict-1.0.0
"""What the postgres backend holds beyond the shared suite (storage.md §3.6, §3.7, events.md §4
item 1), each test named for its claim. It reaches past the harness on purpose, to the backend's
connection and the owner's, so `test_backend_agnostic.py` exempts it. Skipped unless
`EGZOS_TEST_POSTGRES` names a database (`conftest.py`)."""

from __future__ import annotations

import json
import os
import threading
import time

import pytest

from egzos._types import GENESIS_HASH, ChainConflict, StorageBusy
from egzos.ledger import Ledger
from egzos.model import ContextItem, Node

if not os.environ.get("EGZOS_TEST_POSTGRES"):
    pytest.skip("no postgres database is named (EGZOS_TEST_POSTGRES)", allow_module_level=True)

from psycopg import errors  # noqa: E402  (the `postgres` extra's: imported only to run)

from egzos.backends import postgres  # noqa: E402

AT = "2026-10-24T00:00:00Z"
DOC = {"name": "café ☕", "nested": {"b": [1, 2.5, None], "a": {}}, "nul": "a\u0000b"}
REWRITES = {"update": "UPDATE audit SET doc = '{}'", "delete": "DELETE FROM audit",
            "truncate": "TRUNCATE audit"}


@pytest.fixture
def backend_name() -> str:
    return "postgres"


def _append(backend, **details):
    return Ledger(backend).append("context.fetch", actor="self", principal="interactive", **details)


def _node(nid):
    return Node(id=nid, type="thread", name=nid, parent=None, created_at=AT)


@pytest.mark.parametrize("act", sorted(REWRITES))
def test_the_chain_is_refused_a_rewrite_by_its_grants_and_by_its_trigger(backend, where, act):
    head = _append(backend)
    with pytest.raises(errors.InsufficientPrivilege):  # the container's role: SELECT, INSERT
        backend.db.execute(REWRITES[act])
    with pytest.raises(errors.RaiseException, match="append-only"):  # the owner, who could not
        where.owner.execute(REWRITES[act])  # be refused by grants, is refused by the trigger
    assert list(backend.audit_iter()) == [head]


@pytest.mark.parametrize("ddl", [
    "ALTER TABLE audit DISABLE TRIGGER audit_append_only", "DROP TABLE audit",
    "DROP TRIGGER audit_append_only ON audit", "ALTER TABLE nodes ADD COLUMN x text",
    "CREATE TABLE more (x text)",
])
def test_the_containers_role_owns_no_table_and_makes_none(backend, ddl):
    with pytest.raises(errors.InsufficientPrivilege):
        backend.db.execute(ddl)


def test_no_role_but_the_owner_and_the_containers_holds_a_privilege_here(where):
    rows = where.owner.execute(
        "SELECT DISTINCT coalesce(r.rolname, 'PUBLIC') FROM ("
        " SELECT (aclexplode(coalesce(relacl, acldefault('r', relowner)))).grantee FROM pg_class"
        "  WHERE relnamespace = current_schema()::regnamespace UNION ALL"
        " SELECT (aclexplode(coalesce(proacl, acldefault('f', proowner)))).grantee FROM pg_proc"
        "  WHERE pronamespace = current_schema()::regnamespace UNION ALL"
        " SELECT (aclexplode(nspacl)).grantee FROM pg_namespace WHERE nspname = current_schema()"
        ") g LEFT JOIN pg_roles r ON r.oid = g.grantee").fetchall()
    owner = where.owner.execute("SELECT current_user").fetchone()[0]
    assert sorted(r[0] for r in rows) == sorted([owner, where.schema])


def test_a_block_holds_the_lock_from_its_start_and_the_next_waits_then_reads(make_backend, where):
    first, second = make_backend(), make_backend()
    pids, seen = [first.db.info.backend_pid, second.db.info.backend_pid], []

    def held():  # each connection's advisory lock, granted or waited for
        return dict(where.owner.execute("SELECT pid, granted FROM pg_locks WHERE locktype = "
                                        "'advisory' AND pid = ANY(%s)", (pids,)).fetchall())

    def read_then_write():
        with second.atomic():
            seen.extend(n.id for n in second.list_nodes())  # every commit before the lock's
            second.put_node(_node("second"))

    with first.atomic():  # taken before the block's first statement
        assert held() == {pids[0]: True}
        waiter = threading.Thread(target=read_then_write)
        waiter.start()
        deadline = time.monotonic() + 10
        while held() != {pids[0]: True, pids[1]: False} and time.monotonic() < deadline:
            time.sleep(0.01)
        assert held() == {pids[0]: True, pids[1]: False}
        first.put_node(_node("first"))
    waiter.join(10)
    assert not waiter.is_alive() and held() == {} and seen == ["first"]
    assert [n.id for n in make_backend().list_nodes()] == ["first", "second"]


def test_a_writer_waits_a_bounded_time_then_raises_and_leaves_nothing_open(make_backend,
                                                                            monkeypatch):
    first = make_backend()
    monkeypatch.setattr(postgres, "LOCK_TIMEOUT", "50ms")
    second = make_backend()
    with first.atomic(), pytest.raises(StorageBusy):  # the driver's LockNotAvailable, renamed
        second.put_node(_node("n"))
    second.put_node(_node("n"))  # the next write takes the lock afresh
    assert first.get_node("n") == _node("n")


def test_a_block_lets_go_of_a_transaction_left_open(backend):
    backend.db.execute("BEGIN")  # as a caller of `db` may leave one (#329)
    backend.db.execute("INSERT INTO nodes (id, type, name, doc) VALUES ('stray', 't', 'n', '{}')")
    with backend.atomic():
        backend.put_node(_node("n"))
    assert [n.id for n in backend.list_nodes()] == ["n"]


def test_a_second_successor_is_refused_and_the_block_it_ran_in_goes_on(make_backend):
    backend = make_backend()
    head = _append(backend)
    rival = {**{k: v for k, v in head.items() if k != "seq"}, "hash": "f" * 64}  # after GENESIS
    with backend.atomic():
        with pytest.raises(ChainConflict):
            backend.audit_append(rival)
        backend.put_node(_node("n"))  # no error was raised in the transaction to abort it
        _append(backend)  # and the ledger chains on inside it
    reader = make_backend()
    assert reader.get_node("n") == _node("n")
    assert [e["prev_hash"] for e in reader.audit_iter()] == [GENESIS_HASH, head["hash"]]


def test_seq_is_the_heads_plus_one_and_the_chain_is_walked_a_page_at_a_time(backend, where,
                                                                            monkeypatch):
    monkeypatch.setattr(postgres, "_PAGE", 2)
    entries = [_append(backend) for _ in range(5)]
    assert list(backend.audit_iter()) == entries and backend.audit_tail(-1) == entries  # sqlite's
    gap = (9, "t", "h", entries[-1]["hash"], '{"hash": "h"}')  # as an imported chain may hold
    where.owner.execute("INSERT INTO audit VALUES (%s, %s, %s, %s, %s)", gap)
    assert _append(backend)["seq"] == 10  # the head's plus one, past a gap (events.md §2)


def test_a_document_is_kept_as_the_exact_text_written_never_jsonb(backend, where):
    item = ContextItem(id="i", kind="memory", scope="n", content={"body": "b", **DOC})
    backend.put(item)
    entry = _append(backend, **DOC)
    stored = {k: v for k, v in entry.items() if k != "seq"}  # as audit_append was given it
    written = (json.dumps(item.to_dict()), json.dumps(stored))
    assert where.owner.execute("SELECT i.doc, a.doc FROM items i, audit a").fetchone() == written
    assert backend.get("i") == item and list(backend.audit_iter()) == [entry]
    assert where.owner.execute(
        "SELECT DISTINCT data_type FROM information_schema.columns "
        "WHERE table_schema = current_schema() AND column_name IN ('doc', 'value')"
    ).fetchall() == [("text",)]


def test_where_postgres_would_answer_otherwise_it_answers_as_sqlite(backend):
    item = ContextItem(id="i", kind="memory", scope="n", content={"body": "b"})
    backend.put(item)
    assert backend.query(["n"], text="\0tail") == [item]  # sqlite's pattern ends at a NUL: `%`
    assert backend.query(["n"], text="b\0") == []  # `%b`: no document ends so
    assert backend.query(["n"], text="\u212a") == []  # the Kelvin sign: a locale folds it to `k`
