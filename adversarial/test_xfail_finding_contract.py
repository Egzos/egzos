# Copyright 2026 Ali Sasanian
# SPDX-License-Identifier: LicenseRef-PolyForm-Strict-1.0.0
"""
Regression coverage for the xfail_finding pairing enforced in adversarial/conftest.py (#20).

Loads conftest.py by file path rather than `import conftest`, so the result does not depend on
pytest's import-mode configuration or collide with pytest's own loaded copy of the same module.
"""

import importlib.util
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

_CONFTEST_PATH = Path(__file__).parent / "conftest.py"
_PYPROJECT_PATH = Path(__file__).parent.parent / "pyproject.toml"
_spec = importlib.util.spec_from_file_location("_adversarial_conftest_under_test", _CONFTEST_PATH)
_conftest = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_conftest)
_pytest_collection_modifyitems = _conftest.pytest_collection_modifyitems


class _FakeItem:
    """Stands in for a pytest.Item: only get_closest_marker and nodeid are used by the hook."""

    def __init__(self, nodeid, markers):
        self.nodeid = nodeid
        self._markers = {m.name: m for m in markers}

    def get_closest_marker(self, name):
        return self._markers.get(name)


def _xfail_finding_marker():
    return pytest.mark.xfail_finding.mark


def _xfail_marker(reason=None, strict=None):
    kwargs = {}
    if reason is not None:
        kwargs["reason"] = reason
    if strict is not None:
        kwargs["strict"] = strict
    return pytest.mark.xfail(**kwargs).mark


def test_bare_xfail_finding_without_xfail_fails_collection():
    item = _FakeItem("test_mod.py::test_one", [_xfail_finding_marker()])

    with pytest.raises(pytest.UsageError, match="requires a paired"):
        _pytest_collection_modifyitems([item])


def test_xfail_finding_with_non_strict_xfail_fails_collection():
    item = _FakeItem(
        "test_mod.py::test_two",
        [_xfail_finding_marker(), _xfail_marker(reason="see issue #20", strict=False)],
    )

    with pytest.raises(pytest.UsageError, match="strict=True"):
        _pytest_collection_modifyitems([item])


def test_xfail_finding_without_issue_number_fails_collection():
    item = _FakeItem(
        "test_mod.py::test_three",
        [_xfail_finding_marker(), _xfail_marker(reason="known finding, no ticket", strict=True)],
    )

    with pytest.raises(pytest.UsageError, match="must name the public issue"):
        _pytest_collection_modifyitems([item])


def test_xfail_finding_with_missing_reason_fails_collection():
    item = _FakeItem(
        "test_mod.py::test_four",
        [_xfail_finding_marker(), _xfail_marker(strict=True)],
    )

    with pytest.raises(pytest.UsageError, match="must name the public issue"):
        _pytest_collection_modifyitems([item])


def test_correctly_paired_xfail_finding_passes_collection():
    item = _FakeItem(
        "test_mod.py::test_five",
        [_xfail_finding_marker(), _xfail_marker(reason="see issue #20", strict=True)],
    )

    _pytest_collection_modifyitems([item])  # must not raise


def test_items_without_xfail_finding_are_ignored():
    item = _FakeItem("test_mod.py::test_six", [_xfail_marker(reason="unrelated", strict=False)])

    _pytest_collection_modifyitems([item])  # must not raise


def test_multiple_violations_are_all_reported_together():
    items = [
        _FakeItem("test_mod.py::test_bad_one", [_xfail_finding_marker()]),
        _FakeItem(
            "test_mod.py::test_bad_two",
            [_xfail_finding_marker(), _xfail_marker(reason="no ticket", strict=True)],
        ),
    ]

    with pytest.raises(pytest.UsageError) as excinfo:
        _pytest_collection_modifyitems(items)

    assert "test_bad_one" in str(excinfo.value)
    assert "test_bad_two" in str(excinfo.value)


def test_hook_is_actually_wired_into_a_real_pytest_run(tmp_path):
    """Proves the wiring, not just the predicate (issue #75).

    The seven tests above call ``pytest_collection_modifyitems`` directly against an in-process
    fake item list; they never ask pytest itself to discover and load ``conftest.py``. This test
    instead runs a real, separate ``pytest`` process against an isolated copy of the actual
    pyproject.toml and the actual conftest.py, collecting a deliberately bare
    ``@pytest.mark.xfail_finding`` test placed next to that copied conftest. The hook is
    registered as a pytest hook in a conftest that a real collection loads, and it fires: only
    that makes the child process reject the bare marker and exit non-zero.

    This test does not cover a ``testpaths`` guard — if ``adversarial`` fell out of
    ``pyproject.toml``'s ``testpaths``, this probe's own conftest and test file would go
    uncollected too, and the child would exit 5 (no tests collected), not 0. A ``testpaths``
    guard has to live in a directory that stays collected regardless; that's #81, a1r's file.

    The bad test lives only in a subprocess's isolated tmp_path copy, never inside this
    repository's own adversarial/ tree, so it can't ever poison this suite's own collection.
    """
    shutil.copy(_PYPROJECT_PATH, tmp_path / "pyproject.toml")
    (tmp_path / "tests").mkdir()
    probe_dir = tmp_path / "adversarial"
    probe_dir.mkdir()
    shutil.copy(_CONFTEST_PATH, probe_dir / "conftest.py")
    (probe_dir / "test_bare_xfail_finding_probe.py").write_text(
        "import pytest\n\n\n"
        "@pytest.mark.xfail_finding\n"
        "def test_bare_finding_without_companion_xfail():\n"
        "    assert True\n"
    )

    result = subprocess.run(
        [sys.executable, "-m", "pytest"],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        env={**os.environ, "PYTEST_ADDOPTS": ""},
        timeout=60,
    )

    assert result.returncode != 0
    assert "xfail_finding contract violated" in result.stdout + result.stderr
