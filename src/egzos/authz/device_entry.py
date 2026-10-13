# Copyright 2026 Ali Sasanian
# SPDX-License-Identifier: LicenseRef-PolyForm-Strict-1.0.0
"""
`/device`'s two acts and what each appends (authorization-server.md §3, §9.3 rows 3–4, §11.8,
§12 row (b)), against `ASState`. `device` runs the flow; this module adds the ledger.

- `redeem`: a `user_code` typed at the entry form. One evaluated attempt, one `authz.redeem`
  (§12.1 rule 1): outcome `found`, or `failed` with row (b)'s closed cause. The page gets the
  pending record or `None`, one answer for all five causes (§11.8). The entry carries
  `principal: none` and `actor: device` (§12.2), because the redemption is reachable without a
  session and is not an owner act (§11.0 substep 3). It never carries the `user_code` (§12.1
  rule 7), nor the requester hint or the client's id: row (b)'s shape is closed at `outcome` and
  `cause` (§12), and the hint is untrusted client text (§11.8).
- `decide`: the owner's approve or deny, inside a session the endpoint has already checked.
  When this call moves the authorization out of pending, it appends one `authz.grant
  {client_id, decision, scopes, capabilities}` with `principal: interactive`, carrying what was
  requested, on a deny too (§9.3, [0.3 · 29]). A decision that moves nothing appends nothing:
  rows 3 and 4 fire on an owner's decision and on nothing else.

`throttled` is §11.0's, written by the counter in front of `redeem` at the attempt that engages
it (#208). A held throttle never calls `redeem`. `/device` has no substeps 1 or 3 (§11.0).
"""

from __future__ import annotations

from datetime import UTC, datetime

from egzos._types import ASState, DeviceAuthorizationRecord, GrantDecision
from egzos.authz import AuditLedger, device, grant


def redeem(
    state: ASState,
    ledger: AuditLedger,
    *,
    key: bytes,
    user_code: str | None,
    now: datetime | None = None,
) -> DeviceAuthorizationRecord | None:
    """Row (b) for one entry-form POST, after §11.0's counter has admitted it. The record is for
    rendering §3 mitigation 2's screen, so the owner sees the client and the grant. A naive `now`
    raises `ValueError` before anything is read or appended."""
    entry = device.enter(state, key=key, user_code=user_code, now=now or datetime.now(UTC))
    if entry.record is None:
        ledger.append(
            "authz.redeem", actor="device", principal="none", outcome="failed", cause=entry.cause
        )
        return None
    ledger.append("authz.redeem", actor="device", principal="none", outcome="found")
    return entry.record


def decide(
    state: ASState,
    ledger: AuditLedger,
    *,
    key: bytes,
    user_code: str | None,
    approve: bool,
    actor: str,
    lifetime_seconds: object = None,
    now: datetime | None = None,
) -> bool:
    """The owner's decision for one pending authorization. True exactly when this call decided it.

    `actor` is the session owner's identity, which the endpoint supplies and never reads from the
    request. An empty one is a caller's bug and raises `ValueError` before anything is read. On an
    approval, a `lifetime_seconds` that is not a positive integer is refused before the lookup,
    with the same `False` as a code that is no longer pending (#213's review); anything else is
    clamped by §11.5. A deny carries no lifetime, so it never reads one: an unrelated field cannot
    starve a deny (#250's review). A naive `now` raises `ValueError` before anything is read."""
    if not isinstance(actor, str) or not actor:
        raise ValueError("device_entry.decide needs the session owner as actor")
    at = now or datetime.now(UTC)
    if at.tzinfo is None or at.utcoffset() is None:
        raise ValueError("device_entry.decide needs an aware datetime")
    approved = approve is True
    if approved:
        try:
            grant.clamp_grant_lifetime(lifetime_seconds)  # type: ignore[arg-type]
        except ValueError:
            return False
    # Read for the entry's fields. `client_id` and `requested` never change after `put_device`,
    # and `device.decide` reads the record again for the grant it stores.
    record = device.enter(state, key=key, user_code=user_code, now=at).record
    if record is None:
        return False
    moved = device.decide(
        state,
        key=key,
        user_code=user_code,
        approve=approved,
        lifetime_seconds=lifetime_seconds if approved else None,  # type: ignore[arg-type]
        now=at,
    )
    if not moved:
        return False
    decision: GrantDecision = "granted" if approved else "denied"
    requested = record["requested"]
    ledger.append(
        "authz.grant",
        actor=actor,
        principal="interactive",
        client_id=record["client_id"],
        decision=decision,
        scopes=list(requested["scopes"]),
        capabilities=list(requested["capabilities"]),
    )
    return True
