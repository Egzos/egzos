# Copyright 2026 Ali Sasanian
# SPDX-License-Identifier: Apache-2.0
"""
Adversarial test configuration — owned by a6-adversary.

Markers are registered in pyproject.toml [tool.pytest.ini_options].
a6-adversary adds fixtures here as the suite grows.
"""

import importlib.util
import sys
import types
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
CHECK_OWNERSHIP_PY = REPO_ROOT / ".github" / "scripts" / "check_ownership.py"


@pytest.fixture(scope="session")
def repo_root():
    """Absolute path to the repository root."""
    return REPO_ROOT


@pytest.fixture(scope="session")
def check_ownership():
    """The `.github/scripts/check_ownership.py` module, imported by path.

    The script is not importable as a package (it lives under a dot-directory and is
    invoked as `python3 .github/scripts/check_ownership.py`), so it is loaded from its
    file location.

    It imports pyyaml at module scope and calls `sys.exit(1)` if that import fails.
    pyyaml is not in the `dev` extra that the `tests` workflow installs, so an
    unguarded import here would abort the whole pytest session rather than fail one
    test. A stub module stands in when pyyaml is absent; nothing exercised from
    `adversarial/` touches yaml (only `main()` parses OWNERSHIP.yml, and these tests
    never call it).
    """
    if not CHECK_OWNERSHIP_PY.is_file():
        pytest.fail(f"ownership checker not found at {CHECK_OWNERSHIP_PY}")

    stubbed = "yaml" not in sys.modules and importlib.util.find_spec("yaml") is None
    if stubbed:
        sys.modules["yaml"] = types.ModuleType("yaml")
    try:
        spec = importlib.util.spec_from_file_location(
            "egzos_check_ownership", CHECK_OWNERSHIP_PY
        )
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
    finally:
        if stubbed:
            sys.modules.pop("yaml", None)
    return module
