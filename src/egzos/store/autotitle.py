# Copyright 2026 Ali Sasanian
# SPDX-License-Identifier: Apache-2.0
"""
Auto-titling runs at write time for every item (v0.3 §3, v0.4 §16). Engines: BYO key, local
model, or DEGRADED — no model, metadata only, nothing breaks. The skeleton ships degraded;
`organize --backfill` retro-titles the moment an engine appears.
"""

from __future__ import annotations

from typing import Protocol


class Titler(Protocol):
    name: str

    def title(self, *, body: str | None, filename: str | None, mime: str | None) -> str: ...


class DegradedTitler:
    name = "degraded"

    def title(self, *, body: str | None, filename: str | None, mime: str | None) -> str:
        if body:
            for line in body.splitlines():
                line = line.strip().lstrip("#-*> ").strip()
                if line:
                    return line[:80]
        if filename:
            return filename
        return f"untitled ({mime or 'text'})"
