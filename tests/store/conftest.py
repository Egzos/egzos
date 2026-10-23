# Copyright 2026 Ali Sasanian
# SPDX-License-Identifier: LicenseRef-PolyForm-Strict-1.0.0
"""A throwaway Postgres for the Postgres backend's tests: one cluster per session, one database
per test. Skipped where no Postgres server binaries are installed."""

from __future__ import annotations

import glob
import itertools
import os
import shutil
import subprocess
import tempfile
from pathlib import Path

import pytest

_PORT = 55433
_count = itertools.count()


def _bin() -> Path | None:
    found = sorted(glob.glob("/usr/lib/postgresql/*/bin/initdb"))
    if found:
        return Path(found[-1]).parent
    initdb = shutil.which("initdb")
    return Path(initdb).parent if initdb else None


@pytest.fixture(scope="session")
def postgres_server():
    pytest.importorskip("psycopg")
    bindir = _bin()
    if bindir is None:
        pytest.skip("no Postgres server binaries here")
    # initdb refuses root; where tests run as root, the cluster runs as `postgres`.
    as_root = os.geteuid() == 0
    prefix = ["runuser", "-u", "postgres", "--"] if as_root else []
    base = Path(tempfile.mkdtemp(prefix="egzpg."))
    if as_root:
        shutil.chown(base, "postgres")
    data = base / "data"
    subprocess.run([*prefix, str(bindir / "initdb"), "-D", str(data), "-U", "postgres",
                    "--auth=trust", "-E", "UTF8"], check=True, capture_output=True)
    subprocess.run([*prefix, str(bindir / "pg_ctl"), "-D", str(data), "-o",
                    f"-k {base} -p {_PORT} -c listen_addresses=''", "-l", str(base / "log"),
                    "-w", "start"], check=True, capture_output=True)
    try:
        yield f"host={base} port={_PORT} user=postgres"
    finally:
        subprocess.run([*prefix, str(bindir / "pg_ctl"), "-D", str(data), "-m", "immediate",
                        "stop"], capture_output=True)
        shutil.rmtree(base, ignore_errors=True)


@pytest.fixture
def postgres_url(postgres_server):
    """A fresh, empty database on the session's cluster."""
    import psycopg

    name = f"egzos_{os.getpid()}_{next(_count)}"
    with psycopg.connect(f"{postgres_server} dbname=postgres", autocommit=True) as admin:
        admin.execute(f'CREATE DATABASE "{name}"')
    return f"{postgres_server} dbname={name}"
