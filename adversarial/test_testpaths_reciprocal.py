# Copyright 2026 Ali Sasanian
# SPDX-License-Identifier: Apache-2.0
"""`tests` stays in pytest's `testpaths`, the reciprocal of #81's guard (#84).

`tests/conformance/test_testpaths.py` proves `adversarial` stays in
`[tool.pytest.ini_options].testpaths` — from a file under `tests/`, because a guard for that entry
placed under `adversarial/` would go uncollected along with the very entry it exists to check.

The same reasoning applies in mirror: nothing under `tests/` can prove `tests` is still in
`testpaths`, because that file would be uncollected along with its own directory's entry. This file
carries that reciprocal half from `adversarial/`, which stays collected independently via its own
`testpaths` entry.

This is a plain read of pyproject.toml — no subprocess, and no re-parsing of
`.github/workflows/tests.yml`. The workflow-invocation half is #81's file
(`tests/conformance/test_testpaths.py::test_the_tests_check_collects_adversarial`) and is not
duplicated here: the same `pytest` invocation governs both `testpaths` entries at once, so a second
parse of the same workflow would only restate that check, not add coverage.
"""

import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PYPROJECT = ROOT / "pyproject.toml"

# pytest's default collection patterns; `python_files` is not overridden in pyproject.toml.
COLLECTED_GLOBS = ("test_*.py", "*_test.py")


def _testpaths():
    with PYPROJECT.open("rb") as fh:
        return tomllib.load(fh)["tool"]["pytest"]["ini_options"]["testpaths"]


def test_tests_is_in_testpaths():
    assert "tests" in _testpaths()


def test_tests_holds_tests_pytest_would_collect():
    # `tests` in testpaths is vacuous if nothing inside it (recursively) matches a collection
    # pattern — pytest walks testpaths recursively, unlike a single non-recursive glob.
    found = [p.name for g in COLLECTED_GLOBS for p in (ROOT / "tests").rglob(g)]
    assert found != []
