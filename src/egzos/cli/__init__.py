# Copyright 2026 Ali Sasanian
# SPDX-License-Identifier: Apache-2.0
"""
egzos CLI — owned by a3-doorman.

This stub is a Phase 0 placeholder. The walking skeleton (Phase 0.1) adds
the real subcommands: add, inbox, resolve, serve --mcp, audit.
"""
from __future__ import annotations

import sys


def main(argv=None):
    # type: (...) -> int
    """Entry point for the egzos CLI.

    Prints a status line and returns 0. The walking skeleton is next.
    """
    print("egzos 0.0.0a0 — Phase 0 scaffold; the walking skeleton is next")
    return 0


if __name__ == "__main__":
    sys.exit(main())
