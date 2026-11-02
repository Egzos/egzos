# Copyright 2026 Ali Sasanian
# SPDX-License-Identifier: LicenseRef-PolyForm-Strict-1.0.0
"""GHSA-wf2m-wg6h-v6wf: a door stopped with SIGTERM, as Docker, systemd and Kubernetes stop a
process, ends as one stopped with SIGINT (Ctrl-C) does: its command closes the container and exits
0, so a home bound to a database records the newest entry it has seen (storage.md §3.7). Each door,
`egzos serve --http` and `egzos web`, runs in a process of its own, so a stop that ends that process
cannot end the test run. The postgres case runs when `EGZOS_TEST_POSTGRES` names a database, as
`tests/test_home_binding.py`'s do, on a schema and a role of its own."""

from __future__ import annotations

import http.client
import json
import os
import secrets
import signal
import socket
import subprocess
import sys
import threading
import time
from pathlib import Path

import pytest

import egzos
from egzos import binding
from egzos.binding import BINDING_FILE, BLOBS_S3, DATABASE_URL
from egzos.container import Container

pytestmark = [pytest.mark.adversarial,
              pytest.mark.skipif(sys.platform == "win32", reason="a POSIX host's stop")]

POSTGRES = os.environ.get("EGZOS_TEST_POSTGRES")
STOPS = pytest.mark.parametrize("stop", [signal.SIGINT, signal.SIGTERM], ids=["SIGINT", "SIGTERM"])
#: The two doors that run uvicorn, as their commands start them on a port.
DOORS = pytest.mark.parametrize("door", [("serve", "--http"), ("web", "--no-open")],
                                ids=["serve-http", "web"])
#: `egzos`, as its console script runs it, with the stops a host's process starts with, on the
#: schema the test's database names, and `Container.close` leaving a mark once it has run.
DOOR = """
import signal, sys
from pathlib import Path
from egzos import binding
from egzos.cli import main
from egzos.container import Container

signal.signal(signal.SIGINT, signal.default_int_handler)
signal.signal(signal.SIGTERM, signal.SIG_DFL)
binding.SCHEMA, mark, close = sys.argv[1], Path(sys.argv[2]), Container.close

def closing(self):
    close(self)
    mark.write_text("closed")

Container.close = closing
sys.exit(main(sys.argv[3:]))
"""


@pytest.fixture(autouse=True)
def _no_database(monkeypatch):
    for name in (DATABASE_URL, *BLOBS_S3):
        monkeypatch.delenv(name, raising=False)


def _port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def _stop(tmp_path: Path, stop: int, *, door=("serve", "--http"), schema: str = "egzos",
          named=None, serving=None):
    """Serve `tmp_path/home`'s `door` until it answers, call `serving(port)`, then send `stop`: the
    door's exit code, whether `Container.close` ran, and what it printed. Its environment holds
    no `EGZOS_*` setting but its home and those `named`, and finds the egzos under test first."""
    env = {k: v for k, v in os.environ.items() if not k.startswith("EGZOS_")}
    src = str(Path(egzos.__file__).resolve().parents[1])
    env["PYTHONPATH"] = os.pathsep.join(filter(None, (src, env.get("PYTHONPATH"))))
    env.update(EGZOS_HOME=str(tmp_path / "home"), **(named or {}))
    port, mark = _port(), tmp_path / "closed"
    door = subprocess.Popen(
        [sys.executable, "-c", DOOR, schema, str(mark), *door, "--port", str(port)],
        cwd=tmp_path, env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    try:
        deadline = time.monotonic() + 60
        while door.poll() is None:  # serving once it answers: uvicorn holds the stops by then
            try:
                socket.create_connection(("127.0.0.1", port), timeout=1).close()
                break
            except OSError:
                if time.monotonic() > deadline:
                    raise
                time.sleep(0.05)
        if serving is not None and door.poll() is None:
            serving(port)
        door.send_signal(stop)
        out = door.communicate(timeout=60)[0]
    finally:
        if door.poll() is None:
            door.kill()
            door.communicate()
    return door.returncode, mark.exists(), out


@DOORS
@STOPS
def test_ghsa_wf2m_wg6h_v6wf_a_stopped_door_closes_its_container(tmp_path, door, stop):
    """SIGTERM ends either door as SIGINT does: its command closes the container and exits 0."""
    c = Container(tmp_path / "home")
    c.init()
    c.close()
    code, closed, out = _stop(tmp_path, stop, door=door)
    assert (code, closed) == (0, True), out


@pytest.fixture
def place(monkeypatch):
    """A schema on the test database with a role of its own, named to this process's containers;
    the door's process is given the URL and the schema itself."""
    if not POSTGRES:
        pytest.skip("no postgres database is named (EGZOS_TEST_POSTGRES)")
    from psycopg import connect
    from psycopg.conninfo import make_conninfo
    from psycopg.sql import SQL, Identifier, Literal

    from egzos.backends.postgres import apply_schema

    name, password = f"egzos_t_{secrets.token_hex(6)}", secrets.token_urlsafe(18)
    with connect(POSTGRES, autocommit=True) as owner:
        owner.execute(SQL("CREATE ROLE {} LOGIN PASSWORD {}").format(
            Identifier(name), Literal(password)))
        try:
            apply_schema(owner, name, name)
            url = make_conninfo(POSTGRES, user=name, password=password)
            monkeypatch.setenv(DATABASE_URL, url)
            monkeypatch.setattr(binding, "SCHEMA", name)
            yield owner, name, url
        finally:
            owner.execute(SQL("DROP SCHEMA IF EXISTS {0} CASCADE; DROP ROLE IF EXISTS {0}").format(
                Identifier(name)))


@STOPS
def test_ghsa_wf2m_wg6h_v6wf_a_stopped_door_records_the_newest_entry_seen(tmp_path, place, stop):
    """On a home bound to a database, SIGTERM's close, as SIGINT's, records the newest entry the
    door has seen, read here from the database itself: an open would record it too."""
    from psycopg.sql import SQL, Identifier

    owner, schema, url = place
    c = Container(tmp_path / "home")
    secret = c.init().secret
    c.close()
    made = json.loads((tmp_path / "home" / BINDING_FILE).read_text())["seen"]

    def read(port):  # a read appends to the chain while the door serves
        con = http.client.HTTPConnection("127.0.0.1", port, timeout=30)
        try:
            con.request("GET", "/v1/fetch", headers={"Authorization": f"Bearer {secret}"})
            assert con.getresponse().status == 200
        finally:
            con.close()

    code, closed, out = _stop(tmp_path, stop, schema=schema, named={DATABASE_URL: url},
                              serving=read)
    seq, digest = owner.execute(SQL("SELECT seq, hash FROM {}.audit ORDER BY seq DESC LIMIT 1")
                                .format(Identifier(schema))).fetchone()
    seen = json.loads((tmp_path / "home" / BINDING_FILE).read_text())["seen"]
    assert (code, closed, seen) == (0, True, {"seq": seq, "hash": digest}), out
    assert seq > made["seq"]  # the chain grew while the door served


def test_ghsa_wf2m_wg6h_v6wf_sigterm_is_sigints_only_while_a_door_runs(tmp_path, monkeypatch):
    """The door takes SIGTERM as SIGINT while it runs, in place of SIGTERM's default handler only,
    and puts the default back, after a run that fails too. An ignored SIGTERM, or a handler set by
    whatever embeds the door, is left as it is; on any other thread than the main one, which takes
    no signal, nothing changes."""
    import uvicorn

    from egzos.api import serve_http

    during, errors, kept, found = [], [], [], signal.getsignal(signal.SIGTERM)

    def run(app, **kw):
        during.append(signal.getsignal(signal.SIGTERM))
        if threading.current_thread() is threading.main_thread():
            raise OSError("the port is taken")

    def off_main():
        try:
            serve_http(c)
        except Exception as e:  # noqa: BLE001 — reported by the assert below
            errors.append(e)

    def embedder(signum, frame):  # a handler set by whatever embeds the door
        pass

    monkeypatch.setattr(uvicorn, "run", run)
    monkeypatch.setattr("egzos.api.app.create_app", lambda container, origin: None)
    c = Container(tmp_path)
    try:
        signal.signal(signal.SIGTERM, signal.SIG_DFL)
        with pytest.raises(OSError):
            serve_http(c)
        after = signal.getsignal(signal.SIGTERM)
        thread = threading.Thread(target=off_main)
        thread.start()
        thread.join()
        for handler in (signal.SIG_IGN, embedder):
            signal.signal(signal.SIGTERM, handler)
            with pytest.raises(OSError):
                serve_http(c)
            kept.append(signal.getsignal(signal.SIGTERM))
    finally:
        signal.signal(signal.SIGTERM, signal.SIG_DFL if found is None else found)
        c.close()
    assert (during, errors, after) == (
        [signal.default_int_handler, signal.SIG_DFL, signal.SIG_IGN, embedder], [], signal.SIG_DFL)
    assert kept == [signal.SIG_IGN, embedder]
