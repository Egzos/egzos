# Copyright 2026 Ali Sasanian
# SPDX-License-Identifier: Apache-2.0
"""The brand masters conform to BRAND.md: `pipeline/check.py` on its default path (stdlib only,
no fonts, no numpy, no network) exits 0. The font-dependent regeneration (F-09) stays
designer-local (BRAND.md §15)."""

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def test_brand_check_passes() -> None:
    check = ROOT / "spec" / "design" / "brand" / "pipeline" / "check.py"
    r = subprocess.run([sys.executable, str(check)], cwd=ROOT, capture_output=True, text=True)
    assert r.returncode == 0, r.stdout + r.stderr
