# Copyright 2026 Ali Sasanian
# SPDX-License-Identifier: LicenseRef-PolyForm-Strict-1.0.0
"""The suite under `tests/store/` reaches its substrates only through `conftest.py`, the harness,
so a second backend runs every module unchanged: none imports `sqlite3`, a concrete store or
`Container`, names a `.db` file, or touches a backend's `db` or `path` or a blob store's `root`.
Every module is in by default but two older ones, which build a `Store` and a `Container` over
sqlite above this seam, and this one, which names what it forbids and holds the harness to its
own promise."""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

HERE = Path(__file__).parent
OUTSIDE = frozenset({"test_items.py", "test_uploads.py", Path(__file__).name})
FORBIDDEN = ("sqlite3", "egzos.backends.sqlite", "egzos.backends.SqliteBackend",
             "egzos.store.blobs", "egzos.container")


def _suite() -> list[Path]:
    return sorted(p for p in HERE.glob("test_*.py") if p.name not in OUTSIDE)


def _imported(node: ast.AST) -> list[str]:
    if isinstance(node, ast.Import):
        return [a.name for a in node.names]
    if isinstance(node, ast.ImportFrom):
        return [node.module or ""] + [f"{node.module}.{a.name}" for a in node.names]
    return []


def _findings(source: str) -> list[str]:
    found = []
    for node in ast.walk(ast.parse(source)):
        found += [n for n in _imported(node) if any(n == f or n.startswith(f + ".")
                                                    for f in FORBIDDEN)]
        if isinstance(node, ast.Constant) and str(node.value).endswith(".db"):
            found.append(node.value)
        if isinstance(node, ast.Attribute) and node.attr in ("db", "path", "root", "SqliteBackend"):
            found.append(f".{node.attr}")
    return found


def test_the_guard_reads_the_suite_and_its_exemptions_exist():
    assert len(_suite()) >= 9 and all((HERE / name).exists() for name in OUTSIDE)


def test_no_suite_module_reaches_a_substrate_directly():
    assert {p.name: f for p in _suite() if (f := _findings(p.read_text()))} == {}


@pytest.mark.parametrize("source", [
    "import sqlite3", "import sqlite3 as s", "from sqlite3 import connect",
    "from egzos.backends.sqlite import SqliteBackend", "from egzos.backends import sqlite",
    "from egzos.backends import SqliteBackend", "import egzos.backends as b\nb.SqliteBackend(p)",
    "from egzos.store.blobs import BlobStore", "from egzos.container import Container",
    "path = tmp_path / 'container.db'", "backend.db.execute('SELECT 1')", "backend.path",
    "blobs.root / 'staging'",
])
def test_the_guard_sees_each_way_past_the_fixtures(source):
    assert _findings(source) != []


def test_make_backend_gives_two_connections_to_one_store(make_backend):
    a, b = make_backend(), make_backend()
    with a.atomic():
        a.put_config("harness.probe", 1)
        assert "harness.probe" not in b.get_config()  # unseen by b until a commits
    assert b.get_config()["harness.probe"] == 1  # one store
