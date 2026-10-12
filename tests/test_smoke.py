# Copyright 2026 Ali Sasanian
# SPDX-License-Identifier: LicenseRef-PolyForm-Strict-1.0.0
"""Smoke tests for the Phase 0 scaffold stub."""
from __future__ import annotations

import egzos
import egzos.cli


def test_version():
    assert egzos.__version__ == "0.1.2"


def test_cli_main_returns_zero():
    result = egzos.cli.main([])
    assert result == 0
