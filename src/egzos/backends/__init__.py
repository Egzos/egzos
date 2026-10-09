# Copyright 2026 Ali Sasanian
# SPDX-License-Identifier: LicenseRef-PolyForm-Strict-1.0.0
"""Pluggable persistence behind the backend contract (v0.3 §8). sqlite is the default."""

from egzos.backends.base import Backend
from egzos.backends.sqlite import SqliteBackend

__all__ = ["Backend", "SqliteBackend"]
