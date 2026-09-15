# Copyright 2026 Ali Sasanian
# SPDX-License-Identifier: Apache-2.0
"""
Append-only, hash-chained audit (v0.4 §15; a3-ledger charter). Each entry carries the hash of the
previous one; verification fails loudly and specifically. Reads are logged, not just writes.

Event taxonomy — the skeleton's vocabulary, for 0.2 to freeze:
  container.init · node.create · item.add · blob.put · context.fetch · blob.pull · item.move
  gate.pass.silent (audience_delta:none) · gate.propose · approval.promote · approval.execute
  approval.deny · trust.quarantine · step_up (reserved; Phase 2.2)
  token.mint · token.revoke · item.tombstone
"""

from __future__ import annotations

import hashlib
from typing import Any

from egzos.backends.base import Backend
from egzos.model import canonical, now_iso

GENESIS = "0" * 64

EVENTS: tuple[str, ...] = (
    "container.init",
    "node.create",
    "item.add",
    "blob.put",
    "context.fetch",
    "blob.pull",
    "item.move",
    "gate.pass.silent",
    "gate.propose",
    "approval.promote",
    "approval.execute",
    "approval.deny",
    "trust.quarantine",
    "step_up",
    "token.mint",
    "token.revoke",
    "item.tombstone",
)


def _hash(prev_hash: str, body: dict[str, Any]) -> str:
    return hashlib.sha256((prev_hash + canonical(body)).encode("utf-8")).hexdigest()


class Ledger:
    def __init__(self, backend: Backend):
        self.backend = backend

    def append(
        self,
        event: str,
        *,
        actor: str,
        principal: str,
        subject: str | None = None,
        scope: str | None = None,
        **details: Any,
    ) -> dict[str, Any]:
        if event not in EVENTS:
            raise ValueError(f"unknown audit event {event!r}")
        last = self.backend.audit_last()
        prev_hash = last["hash"] if last else GENESIS
        body = {
            "ts": now_iso(),
            "event": event,
            "actor": actor,
            "principal": principal,
            "subject": subject,
            "scope": scope,
            "details": details,
            "prev_hash": prev_hash,
        }
        entry = {**body, "hash": _hash(prev_hash, body)}
        return self.backend.audit_append(entry)

    def tail(self, n: int = 20) -> list[dict[str, Any]]:
        return self.backend.audit_tail(n)

    def verify(self) -> dict[str, Any]:
        """Walk the chain from genesis. Returns {ok, entries, broken_at, reason}."""
        prev = GENESIS
        count = 0
        for entry in self.backend.audit_iter():
            count += 1
            body = {
                k: entry[k]
                for k in (
                    "ts",
                    "event",
                    "actor",
                    "principal",
                    "subject",
                    "scope",
                    "details",
                    "prev_hash",
                )
            }
            if entry["prev_hash"] != prev:
                return {
                    "ok": False,
                    "entries": count,
                    "broken_at": entry["seq"],
                    "reason": f"prev_hash mismatch: expected {prev[:12]}…, "
                    f"found {entry['prev_hash'][:12]}…",
                }
            if _hash(prev, body) != entry["hash"]:
                return {
                    "ok": False,
                    "entries": count,
                    "broken_at": entry["seq"],
                    "reason": "entry hash does not match its content (entry rewritten)",
                }
            prev = entry["hash"]
        return {"ok": True, "entries": count, "head": prev}
