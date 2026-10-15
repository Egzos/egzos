# Copyright 2026 Ali Sasanian
# SPDX-License-Identifier: LicenseRef-PolyForm-Strict-1.0.0
"""Authorization surfaces the container serves to a human: the step-up tap (`presence`), and — when
the authorization server lands — consent. The tap spec's Consumers line places them here."""

from __future__ import annotations

from typing import Any, Protocol


class AuditLedger(Protocol):
    """The one `Ledger` method the AS modules append through. One definition, so `clients` and
    `tokens` cannot drift apart on it."""

    def append(
        self, event: str, *, actor: str, principal: str, subject: str | None = None, **details: Any
    ) -> dict[str, Any]: ...
