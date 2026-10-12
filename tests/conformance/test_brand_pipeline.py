# Copyright 2026 Ali Sasanian
# SPDX-License-Identifier: LicenseRef-PolyForm-Strict-1.0.0
"""The brand masters conform to BRAND.md: `pipeline/check.py` on its default path (stdlib only,
no fonts, no numpy, no network) exits 0. The font-dependent regeneration (F-09) stays
designer-local (BRAND.md §15)."""

import os
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]

# The default path is stdlib-only and reads a handful of committed files; anything near this budget
# is a hang, and a hang would otherwise burn the `tests` job's 20 minutes (#81).
TIMEOUT_S = 120

# The child inherits this pytest process's environment. Neutralise the variables that let the
# parent's configuration decide the child's exit status for reasons that have nothing to do with the
# masters: PYTHONWARNINGS=error turns any stdlib DeprecationWarning into a non-zero exit, PYTHONPATH
# can put a shadowing module ahead of the stdlib the check is written against, and PYTHONOPTIMIZE
# strips assertions. They are dropped rather than emptied — an empty PYTHONPATH puts '' on sys.path,
# which is the shadowing hazard it was meant to remove.
_DROPPED = ("PYTHONPATH", "PYTHONWARNINGS", "PYTHONOPTIMIZE")
# check.py is not pytest, so PYTEST_ADDOPTS cannot deselect anything here; it is cleared for the
# same reason pytest's own pytester clears it (#80 does this on a6's side), and so that the
# clearing is already right if the pipeline ever shells out to pytest.
CHILD_ENV = {k: v for k, v in os.environ.items() if k not in _DROPPED} | {"PYTEST_ADDOPTS": ""}


def test_brand_check_passes() -> None:
    check = ROOT / "spec" / "design" / "brand" / "pipeline" / "check.py"
    try:
        r = subprocess.run(
            [sys.executable, str(check)],
            cwd=ROOT,
            capture_output=True,
            text=True,
            env=CHILD_ENV,
            timeout=TIMEOUT_S,
        )
    except subprocess.TimeoutExpired:
        pytest.fail(f"pipeline/check.py did not finish within {TIMEOUT_S}s on its default path")
    assert r.returncode == 0, r.stdout + r.stderr
