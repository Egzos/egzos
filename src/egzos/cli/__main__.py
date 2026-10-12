# Copyright 2026 Ali Sasanian
# SPDX-License-Identifier: LicenseRef-PolyForm-Strict-1.0.0
"""Allow `python -m egzos.cli` to invoke the CLI."""
from __future__ import annotations

import sys

from egzos.cli import main

if __name__ == "__main__":
    sys.exit(main())
