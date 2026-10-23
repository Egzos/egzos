# Copyright 2026 Ali Sasanian
# SPDX-License-Identifier: LicenseRef-PolyForm-Strict-1.0.0
"""The Postgres backend (v0.7 §S): the sqlite backend's contract, row for row, on a real Postgres.
Every Protocol it implements has the same methods and signatures, the chain is append-only and
single-successor, each spend is once, and a whole container — door included — runs on it."""

from __future__ import annotations

import hashlib
import inspect
import threading

import pytest
from fastapi.testclient import TestClient

from egzos.backends.base import ChainConflict
from egzos.backends.sqlite import SqliteBackend
from egzos.container import DATABASE_URL_ENV, OWNER, Container

KW = {"actor": OWNER, "principal": "interactive"}


@pytest.fixture
def pg(postgres_url):
    from egzos.backends.postgres import PostgresBackend

    return PostgresBackend(postgres_url)


@pytest.fixture
def box(tmp_path, postgres_url, monkeypatch):
    monkeypatch.setenv(DATABASE_URL_ENV, postgres_url)
    c = Container(tmp_path)
    c.owner = c.init()
    return c


def _public(cls) -> dict[str, list[str]]:
    return {n: list(inspect.signature(f).parameters)
            for n, f in inspect.getmembers(cls, inspect.isfunction) if not n.startswith("_")}


def test_it_is_the_sqlite_backends_contract_method_for_method():
    from egzos.backends.postgres import PostgresBackend

    assert _public(PostgresBackend) == _public(SqliteBackend)


def test_a_container_runs_on_it_and_its_chain_verifies(box):
    from egzos.backends.postgres import PostgresBackend

    assert isinstance(box.backend, PostgresBackend)
    p = box.nodes.create("project", "notes", box.nodes.user_root(), token=box.owner, **KW)
    item = box.store.add(body="on postgres", scope=p, token=box.owner, **KW)
    found = box.resolver.resolve(p, token=box.owner, actor=OWNER, kinds=None, text="POSTGRES")
    assert [e["item"]["id"] for e in found["items"]] == [item.id]  # case-folded, as sqlite's
    assert box.ledger.verify()["ok"]
    seqs = [e["seq"] for e in box.backend.audit_iter()]
    assert seqs == list(range(1, len(seqs) + 1))  # contiguous, as sqlite's


def test_a_search_is_a_substring_and_nothing_more(box):
    p = box.nodes.create("project", "x", box.nodes.user_root(), token=box.owner, **KW)
    box.store.add(body="plain", scope=p, token=box.owner, **KW)
    assert box.backend.query([p.id], text="%") == []
    assert box.backend.query([p.id], text="_lain") == []


def test_the_chain_is_append_only_and_single_successor(pg):
    import psycopg

    entry = {"ts": "t", "hash": "h1", "prev_hash": "0", "event": "container.init"}
    assert pg.audit_append(entry)["seq"] == 1
    with pytest.raises(ChainConflict):
        pg.audit_append({**entry, "hash": "h2"})  # a second successor to the same head
    with pytest.raises(psycopg.errors.RaiseException):
        pg.db.execute("UPDATE audit SET ts='x'")
    with pytest.raises(psycopg.errors.RaiseException):
        pg.db.execute("DELETE FROM audit")
    assert [e["hash"] for e in pg.audit_iter()] == ["h1"]


def test_a_failed_act_lands_nothing(pg):
    pg.put_config("a", 1)
    with pytest.raises(RuntimeError), pg.atomic():
        pg.put_config("a", 2)
        pg.put_config("b", 3)
        raise RuntimeError
    assert pg.get_config() == {"a": 1}


def test_each_spend_is_once(pg):
    pg.put_challenge({"id": "c", "principal": "t", "act": "move", "subject": "i",
                      "destination": None, "delta": [], "expires_at": "2099-01-01T00:00:00Z"})
    assert pg.spend_challenge("c")["spent"] is False
    assert pg.spend_challenge("c")["spent"] is True
    assert pg.claim_authorization("a") is True and pg.claim_authorization("a") is False
    sig = hashlib.sha256(b"sig").hexdigest()
    assert pg.spend_grant(sig, "2099") is True and pg.spend_grant(sig, "2099") is False
    pg.forget_grants("3000")
    assert pg.spend_grant(sig, "2099") is True
    assert [pg.throttle_incr("rest", "g", "1") for _ in range(3)] == [1, 2, 3]
    assert pg.throttle_count("rest", "g", "1") == 3 and pg.throttle_windows("rest") == ["1"]


def test_two_connections_spending_one_challenge_see_it_fresh_once(postgres_url):
    from egzos.backends.postgres import PostgresBackend

    PostgresBackend(postgres_url).put_challenge({
        "id": "c", "principal": "t", "act": "move", "subject": "i", "destination": None,
        "delta": [], "expires_at": "2099-01-01T00:00:00Z"})
    seen: list[bool] = []
    gate = threading.Barrier(4)

    def spend():
        b = PostgresBackend(postgres_url)
        gate.wait()
        seen.append(b.spend_challenge("c")["spent"])

    threads = [threading.Thread(target=spend) for _ in range(4)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert sorted(seen) == [False, True, True, True]


def test_two_containers_on_one_database_keep_one_chain(tmp_path, postgres_url, monkeypatch):
    monkeypatch.setenv(DATABASE_URL_ENV, postgres_url)
    first = Container(tmp_path / "a")
    owner = first.init()
    gate = threading.Barrier(4)

    def write(n):
        box = Container(tmp_path / "a")
        gate.wait()
        for i in range(5):
            box.store.add(body=f"{n}-{i}", token=owner, **KW)

    threads = [threading.Thread(target=write, args=(n,)) for n in range(4)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert first.ledger.verify()["ok"]
    assert len([e for e in first.backend.audit_iter() if e["event"] == "item.add"]) == 20


def test_the_door_runs_on_it(box):
    from egzos.api.app import create_app

    door = TestClient(create_app(box))
    h = {"Authorization": f"Bearer {box.owner.secret}"}
    p = box.nodes.create("project", "door", box.nodes.user_root(), token=box.owner, **KW)
    r = door.post("/v1/items", headers=h, json={"body": "through the door", "scope": p.id})
    assert r.status_code == 200
    got = door.get(f"/v1/items/{r.json()['item']['id']}", headers=h)
    assert got.json()["item"]["content"]["body"] == "through the door"
    assert door.get("/v1/fetch", headers={"Authorization": "Bearer nope"}).status_code == 401
    assert box.ledger.verify()["ok"]
