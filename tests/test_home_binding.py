# Copyright 2026 Ali Sasanian
# SPDX-License-Identifier: LicenseRef-PolyForm-Strict-1.0.0
"""A home stays bound to the database it was made on, and to its blob root (storage.md §3.7, §4):
each stop an open makes, the make's own, the object store's, and a sqlite home without
`EGZOS_DATABASE_URL` as before. The object store's values are fake: building one does no I/O, and
no test here reaches it (`tests/store/test_s3_only.py` does). The postgres tests run
when `EGZOS_TEST_POSTGRES` names a database, as `tests/store/conftest.py`'s do, each on schemas
and roles of its own, named to the container by the variable and by `binding.SCHEMA`."""

from __future__ import annotations

import json
import os
import secrets
import sys
import threading
import traceback
from typing import NamedTuple

import pytest
from typer.testing import CliRunner

from egzos import binding
from egzos.binding import BINDING_FILE, BLOBS_S3, DATABASE_URL, HOME_BLOBS, HomeBindingError
from egzos.container import Container

POSTGRES = os.environ.get("EGZOS_TEST_POSTGRES")
PASSWORD = "hunter2-not-a-real-one"
REFUSED = f"postgresql://egzos_user:{PASSWORD}@127.0.0.1:1/egzos?connect_timeout=2"
KEY_ID, SECRET = "AKIA-not-a-real-key-id", "not-a-real-secret-access-key"
ENDPOINT = "http://127.0.0.1:1/storage/v1/s3"
STORE = dict(zip(BLOBS_S3, (ENDPOINT, "region-not-real", "bucket-not-real", "prefix/not-real",
                            KEY_ID, SECRET), strict=True))
ROOT = {"endpoint": ENDPOINT, "bucket": "bucket-not-real", "prefix": "prefix/not-real"}
S3_VARS = ("EGZOS_BLOBS_S3_*",)


@pytest.fixture(autouse=True)
def _no_database(monkeypatch):
    for name in (DATABASE_URL, *BLOBS_S3):
        monkeypatch.delenv(name, raising=False)


def _stops(case, home, *hidden, names=(DATABASE_URL,)):
    """Opening `home` stops for `case`, naming the variables and nothing in `hidden`: not in the
    error, no driver's error chained to it, and not in the locals of any frame it was raised
    through, which a traceback can print. Its message holds no value of the object store's."""
    with pytest.raises(HomeBindingError) as raised:
        Container(home)
    err = raised.value
    assert err.case == case and all(name in str(err) for name in names)
    assert err.__cause__ is None and err.__context__ is None
    shown = repr(err) + "".join(traceback.TracebackException(
        type(err), err, err.__traceback__.tb_next, capture_locals=True).format())
    assert [h for h in hidden if h in shown] == []
    assert [v for v in (*STORE.values(), *ROOT.values()) if v in str(err)] == []
    return err


def _name_store(monkeypatch, changed=()):
    """The object store named in the environment: STORE, with `changed` over it (None unsets)."""
    for name, value in {**STORE, **dict(changed)}.items():
        if value is None:
            monkeypatch.delenv(name, raising=False)
        else:
            monkeypatch.setenv(name, value)


def _binding(home):
    return json.loads((home / BINDING_FILE).read_text())


def _seen(entry):
    return {"seq": entry["seq"], "hash": entry["hash"]}


def _fetch(c):
    return c.ledger.append("context.fetch", actor="self", principal="interactive")


# -- without a database -----------------------------------------------------------------------
def test_a_named_database_keeps_the_state_in_the_egzos_schema():
    assert binding.SCHEMA == "egzos"


def test_a_sqlite_home_without_the_variable_is_as_before(tmp_path):
    c = Container(tmp_path)
    token = c.init()
    c.close()
    c.close()  # a second close does nothing
    assert Container(tmp_path).init().id == token.id
    assert not (tmp_path / BINDING_FILE).exists()


def test_each_cli_command_closes_its_container(tmp_path, monkeypatch):
    from egzos.cli import app

    closed = []
    monkeypatch.setattr(Container, "close", lambda self: closed.append(self.home))
    monkeypatch.setenv("EGZOS_HOME", str(tmp_path))
    result = CliRunner().invoke(app, ["init"])
    assert result.exit_code == 0, result.output
    assert closed == [tmp_path]


def test_a_stop_reaches_the_cli_as_its_message_and_exit_2_never_a_traceback(tmp_path, monkeypatch):
    from egzos.cli import app

    (tmp_path / BINDING_FILE).write_text("{}")
    monkeypatch.setenv("EGZOS_HOME", str(tmp_path))
    result = CliRunner().invoke(app, ["ls"])
    assert result.exit_code == 2
    assert DATABASE_URL in result.output and "Traceback" not in result.output
    assert not isinstance(result.exception, HomeBindingError)  # handled, not raised through
    assert not (tmp_path / "egzos.db").exists()


def test_a_bound_home_never_falls_back_to_its_own_egzos_db(tmp_path):
    (tmp_path / BINDING_FILE).write_text("{}")
    _stops("unset", tmp_path)
    assert not (tmp_path / "egzos.db").exists()


@pytest.mark.parametrize("doc", ["not json", "[1]", '{"first": "a"}',
                                 '{"first": "a", "seen": {"seq": true, "hash": "b"}}'])
def test_a_binding_that_cannot_be_read_stops(tmp_path, monkeypatch, doc):
    (tmp_path / BINDING_FILE).write_text(doc)
    monkeypatch.setenv(DATABASE_URL, REFUSED)
    _stops("unreadable", tmp_path, PASSWORD, REFUSED)


def test_a_home_whose_own_egzos_db_holds_a_chain_stops_when_a_database_is_named(
    tmp_path, monkeypatch
):
    c = Container(tmp_path)
    c.init()
    c.close()  # its chain is checkpointed into egzos.db, and no WAL holds it
    monkeypatch.setenv(DATABASE_URL, REFUSED)
    _stops("local", tmp_path, PASSWORD, REFUSED)
    (tmp_path / "egzos.db").write_bytes(b"not a database, " * 64)  # unread, taken to hold one
    _stops("local", tmp_path, PASSWORD, REFUSED)


def test_a_named_database_without_postgres_support_stops(tmp_path, monkeypatch):
    Container(tmp_path / "unmade").close()  # its egzos.db holds no chain: none is left behind
    (tmp_path / "blank").mkdir()
    (tmp_path / "blank" / "egzos.db").touch()  # nor does an empty file
    monkeypatch.setitem(sys.modules, "psycopg", None)  # as if the extra were not installed
    monkeypatch.setitem(sys.modules, "egzos.backends.postgres", None)
    monkeypatch.setenv(DATABASE_URL, REFUSED)
    for home in ("new", "unmade", "blank"):
        _stops("driver", tmp_path / home, PASSWORD, REFUSED)
    assert not (tmp_path / "new" / "egzos.db").exists()


@pytest.mark.parametrize("url", [REFUSED, f"host=127.0.0.1 port=1 {PASSWORD}"])
def test_an_unreachable_database_stops_and_its_url_is_never_shown(tmp_path, monkeypatch, url):
    pytest.importorskip("psycopg")  # the second's error from psycopg would echo the password
    monkeypatch.setenv(DATABASE_URL, url)
    _stops("unreachable", tmp_path, PASSWORD, url, "egzos_user", "127.0.0.1")
    assert not (tmp_path / "egzos.db").exists()


# -- the object store's own stops, before any database is reached ------------------------------
@pytest.mark.parametrize("changed", [
    {"EGZOS_BLOBS_S3_SECRET_ACCESS_KEY": None},
    {"EGZOS_BLOBS_S3_REGION": "", "EGZOS_BLOBS_S3_ACCESS_KEY_ID": None},  # empty is unset
    dict.fromkeys(BLOBS_S3[1:]),  # the endpoint alone
])
def test_an_object_store_named_in_part_stops_naming_the_variables_unset(
    tmp_path, monkeypatch, changed
):
    monkeypatch.setenv(DATABASE_URL, REFUSED)
    _name_store(monkeypatch, changed)
    err = _stops("blobs-partial", tmp_path, KEY_ID, SECRET, PASSWORD, REFUSED, names=tuple(changed))
    assert [name for name in BLOBS_S3 if name in str(err)] == list(changed)


def test_an_object_store_named_without_a_database_stops(tmp_path, monkeypatch):
    _name_store(monkeypatch)
    _stops("blobs-alone", tmp_path, KEY_ID, SECRET, names=(DATABASE_URL, *S3_VARS))
    assert not (tmp_path / "egzos.db").exists() and not (tmp_path / "blobs").exists()


@pytest.mark.parametrize("endpoint", [
    f"https://{KEY_ID}:{SECRET}@127.0.0.1:1/storage/v1/s3", f"{KEY_ID}:{SECRET}@127.0.0.1:1/s3",
    f"http://{KEY_ID}@127.0.0.1:1", f"http://{SECRET}@127.0.0.1:1?x=1",
])
def test_an_endpoint_holding_userinfo_stops_and_is_never_shown(tmp_path, monkeypatch, endpoint):
    monkeypatch.setenv(DATABASE_URL, REFUSED)
    _name_store(monkeypatch, {"EGZOS_BLOBS_S3_ENDPOINT": endpoint})
    _stops("blobs-userinfo", tmp_path, KEY_ID, SECRET, endpoint, PASSWORD, REFUSED,
           names=("EGZOS_BLOBS_S3_ENDPOINT", "EGZOS_BLOBS_S3_ACCESS_KEY_ID"))


def test_an_object_store_without_opendal_stops_before_the_database_is_reached(
    tmp_path, monkeypatch
):
    monkeypatch.setitem(sys.modules, "opendal", None)  # as if the extra were not installed
    monkeypatch.setenv(DATABASE_URL, REFUSED)
    _name_store(monkeypatch)
    err = _stops("blobs-driver", tmp_path, KEY_ID, SECRET, PASSWORD, REFUSED, names=S3_VARS)
    assert 'pip install "egzos[objects]"' in str(err)


@pytest.mark.parametrize(("changed", "root"), [
    ({}, ROOT),
    ({"EGZOS_BLOBS_S3_ENDPOINT": f"{ENDPOINT}/", "EGZOS_BLOBS_S3_PREFIX": "/prefix/not-real/"},
     ROOT),  # one root spelled two ways is one root
    ({"EGZOS_BLOBS_S3_ENDPOINT": "http://127.0.0.1:1/a@b"},
     {**ROOT, "endpoint": "http://127.0.0.1:1/a@b"}),  # an @ in the path is no userinfo
    ({"EGZOS_BLOBS_S3_PREFIX": "/"}, {**ROOT, "prefix": ""}),  # the bucket's root
])
def test_the_blob_root_named_is_its_endpoint_bucket_and_prefix(monkeypatch, changed, root):
    monkeypatch.setenv(DATABASE_URL, REFUSED)
    _name_store(monkeypatch, changed)
    assert binding.blob_root() == root


def test_the_object_store_never_relies_on_a_create_only_write_and_holds_no_key(monkeypatch):
    _name_store(monkeypatch)
    store = binding.object_store(ROOT)  # no I/O: the endpoint refuses every connection
    assert not store.create_only and store.promotes_by == "copy+delete"
    shown = repr(vars(store)) + repr(store.op)
    assert KEY_ID not in shown and SECRET not in shown


# -- on a database ----------------------------------------------------------------------------
class Place(NamedTuple):
    schema: str
    url: str
    password: str


class Database:
    """Schemas on the test database, each with a role of its own that holds only the container's
    grants. `use` names one to the container; `open` opens a container closed after the test."""

    def __init__(self, monkeypatch):
        from psycopg import connect

        self.monkeypatch, self.owner = monkeypatch, connect(POSTGRES, autocommit=True)
        self.roles, self.opened = [], []

    def place(self) -> Place:
        from psycopg.conninfo import make_conninfo
        from psycopg.sql import SQL, Identifier, Literal

        from egzos.backends.postgres import apply_schema

        name, password = f"egzos_t_{secrets.token_hex(6)}", secrets.token_urlsafe(18)
        self.owner.execute(SQL("CREATE ROLE {} LOGIN PASSWORD {}").format(
            Identifier(name), Literal(password)))
        self.roles.append(name)
        apply_schema(self.owner, name, name)
        return Place(name, make_conninfo(POSTGRES, user=name, password=password), password)

    def use(self, place: Place) -> None:
        self.monkeypatch.setenv(DATABASE_URL, place.url)
        self.monkeypatch.setattr(binding, "SCHEMA", place.schema)

    def open(self, home) -> Container:
        self.opened.append(c := Container(home))
        return c


@pytest.fixture
def db(monkeypatch):
    if not POSTGRES:
        pytest.skip("no postgres database is named (EGZOS_TEST_POSTGRES)")
    from psycopg.sql import SQL, Identifier

    d = Database(monkeypatch)
    yield d
    for c in d.opened:  # a thread's too: no connection outlives its test
        c.backend.db.close()
    for name in d.roles:
        d.owner.execute(SQL("DROP SCHEMA IF EXISTS {0} CASCADE; DROP ROLE IF EXISTS {0}").format(
            Identifier(name)))
    d.owner.close()


def test_a_home_made_on_a_database_is_bound_and_its_newest_seen_advances(db, tmp_path):
    db.use(place := db.place())
    c = db.open(tmp_path)
    assert not (tmp_path / BINDING_FILE).exists()  # a new home on an empty database: unmade
    c.init()
    entries = list(c.backend.audit_iter())
    assert entries[0]["event"] == "container.init"
    assert _binding(tmp_path) == {"first": entries[0]["hash"], "seen": _seen(entries[-1]),
                                  "blobs": HOME_BLOBS}
    assert c.init().principal == "interactive"  # made once: init again answers, never remakes
    head = _fetch(db.open(tmp_path))  # another process on the home, never closed cleanly
    assert _binding(tmp_path)["seen"] == _seen(entries[-1])
    db.open(tmp_path)  # the entry seen is still held; the open records the newest
    assert _binding(tmp_path)["seen"] == _seen(head)
    head = _fetch(c)
    c.close()  # and so does a clean close
    assert _binding(tmp_path) == {"first": entries[0]["hash"], "seen": _seen(head),
                                  "blobs": HOME_BLOBS}
    text = (tmp_path / BINDING_FILE).read_text()
    assert place.password not in text and place.schema not in text


def test_a_home_stops_on_another_database_and_on_an_empty_one(db, tmp_path):
    mine, theirs, empty = db.place(), db.place(), db.place()
    db.use(mine)
    db.open(tmp_path / "a").init()
    db.use(theirs)
    db.open(tmp_path / "b").init()
    _stops("mismatch", tmp_path / "a", theirs.password, theirs.url)
    db.use(empty)
    _stops("mismatch", tmp_path / "a", empty.password, empty.url)


def test_a_database_with_no_schema_the_container_may_read_stops(db, tmp_path):
    place = db.place()
    db.use(place._replace(schema="no_such_schema"))
    _stops("unreachable", tmp_path, place.password, place.url)


def test_a_chain_with_no_binding_stops_a_new_home_and_one_that_lost_it(db, tmp_path):
    db.use(place := db.place())
    db.open(tmp_path / "a").init()
    _stops("unbound", tmp_path / "new", place.password, place.url)
    (tmp_path / "a" / BINDING_FILE).unlink()
    _stops("unbound", tmp_path / "a", place.password, place.url)


def test_a_home_whose_make_finds_a_chain_already_there_stops(db, tmp_path):
    db.use(db.place())
    late = db.open(tmp_path / "late")  # opened on the empty database, as the other one was
    db.open(tmp_path / "first").init()
    with pytest.raises(HomeBindingError) as raised:
        late.init()
    assert raised.value.case == "taken"
    assert not any((tmp_path / "late" / f).exists() for f in (BINDING_FILE, "keychain.json"))
    assert [e["event"] for e in late.backend.audit_iter()].count("container.init") == 1


def test_two_homes_making_on_one_empty_database_at_once_one_makes_and_one_stops(db, tmp_path):
    db.use(db.place())
    homes, start, outcome = [db.open(tmp_path / n) for n in "ab"], threading.Barrier(2), {}

    def make(c):
        start.wait()
        try:
            outcome[c.home.name] = c.init().principal
        except HomeBindingError as e:
            outcome[c.home.name] = e.case

    threads = [threading.Thread(target=make, args=(c,)) for c in homes]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert sorted(outcome.values()) == ["interactive", "taken"]
    assert sorted((tmp_path / n / BINDING_FILE).exists() for n in "ab") == [False, True]


def test_a_database_restored_without_its_home_stops(db, tmp_path):
    from psycopg.sql import SQL, Identifier

    db.use(place := db.place())
    c = db.open(tmp_path)
    c.init()
    c.close()
    with db.owner.transaction():  # the operator restores the database to its first entry
        db.owner.execute(SQL("ALTER TABLE {0}.audit DISABLE TRIGGER audit_append_only; "
                             "DELETE FROM {0}.audit WHERE seq > 1; ALTER TABLE {0}.audit "
                             "ENABLE TRIGGER audit_append_only").format(Identifier(place.schema)))
    _stops("restored", tmp_path, place.password, place.url)
    bound = _binding(tmp_path)  # or holds another entry at the seq the home saw last
    (tmp_path / BINDING_FILE).write_text(json.dumps({**bound, "seen": {"seq": 1, "hash": "0"}}))
    _stops("restored", tmp_path, place.password, place.url)


def test_a_close_after_the_database_is_lost_keeps_the_newest_seen_it_recorded(db, tmp_path):
    db.use(db.place())
    c = db.open(tmp_path)
    c.init()
    before = _binding(tmp_path)
    _fetch(c)
    c.backend.db.close()  # the connection is lost
    c.close()
    assert _binding(tmp_path) == before


def test_a_home_records_its_object_store_and_stops_when_another_root_is_named(
    db, tmp_path, monkeypatch
):
    from egzos.store.objects import ObjectBlobStore

    db.use(place := db.place())
    _name_store(monkeypatch)
    c = db.open(tmp_path)
    assert isinstance(c.blobs, ObjectBlobStore) and not (tmp_path / "blobs").exists()
    c.init()
    c.close()
    assert _binding(tmp_path)["blobs"] == ROOT  # made, and kept by the close
    shown = (tmp_path / BINDING_FILE).read_text() + repr(vars(c.binding))
    assert KEY_ID not in shown and SECRET not in shown
    _name_store(monkeypatch, {  # new keys, another region, the root spelled another way
        "EGZOS_BLOBS_S3_ACCESS_KEY_ID": "AKIA-rotated", "EGZOS_BLOBS_S3_SECRET_ACCESS_KEY": "new",
        "EGZOS_BLOBS_S3_REGION": "region-2", "EGZOS_BLOBS_S3_PREFIX": "/prefix/not-real/"})
    db.open(tmp_path)
    for changed in ({"EGZOS_BLOBS_S3_PREFIX": "prefix/other"}, {"EGZOS_BLOBS_S3_BUCKET": "other"},
                    {"EGZOS_BLOBS_S3_ENDPOINT": "http://127.0.0.1:2/s3"}, dict.fromkeys(BLOBS_S3)):
        _name_store(monkeypatch, changed)
        _stops("blobs-moved", tmp_path, KEY_ID, SECRET, place.password, place.url, names=S3_VARS)
    assert _binding(tmp_path)["blobs"] == ROOT  # a stop never writes over the root recorded


def test_a_home_made_on_its_own_blobs_or_before_the_root_was_recorded_stays_there(
    db, tmp_path, monkeypatch
):
    db.use(place := db.place())
    db.open(tmp_path).init()
    assert _binding(tmp_path)["blobs"] == HOME_BLOBS
    before = {k: v for k, v in _binding(tmp_path).items() if k != "blobs"}
    (tmp_path / BINDING_FILE).write_text(json.dumps(before))  # as written before the root was
    _name_store(monkeypatch)
    _stops("blobs-moved", tmp_path, KEY_ID, SECRET, place.password, place.url, names=S3_VARS)
    _name_store(monkeypatch, dict.fromkeys(BLOBS_S3))
    db.open(tmp_path)  # none named: the home's blobs/, the only root there was
    assert _binding(tmp_path) == {**before, "blobs": HOME_BLOBS}
