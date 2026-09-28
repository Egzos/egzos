# Copyright 2026 Ali Sasanian
# SPDX-License-Identifier: Apache-2.0
"""
Regression coverage for the xfail_finding pairing enforced in adversarial/conftest.py (#20).

Loads conftest.py by file path rather than `import conftest`, so the result does not depend on
pytest's import-mode configuration or collide with pytest's own loaded copy of the same module.
"""

import importlib.util
from pathlib import Path

import pytest

_CONFTEST_PATH = Path(__file__).parent / "conftest.py"
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
