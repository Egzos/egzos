# Copyright 2026 Ali Sasanian
# SPDX-License-Identifier: LicenseRef-PolyForm-Strict-1.0.0
"""
The device-code flow (authorization-server.md §3, §11.8), against `ASState` (storage.md §3.1).

Four steps, one function each, none of them HTTP:

- `authorize`: the device authorization endpoint. Expands `scope` by §7 (refused whole, never
  narrowed), stores the pending record under the `device_code`'s digest and the `user_code`'s keyed
  HMAC, and answers exactly `{device_code, user_code, verification_uri, expires_in, interval}`.
- `enter`: the `user_code` typed at `/device`. One page answer for every failure; the closed row
  (b) cause is returned for the ledger and never for the page (§11.8, §12).
- `decide`: the owner's approve or deny at `/device`. The grant is built here from the stored
  `requested`, capabilities and scopes unchanged, so no caller can widen it (§3 mitigation 3,
  §11.2 consequence 1). Device-flow tokens carry `principal: client` (§10.3).
- `poll`: the token endpoint's `device_code` grant, up to (not including) the mint.

The device-code key is a container secret whose provisioning is #143's; it is a parameter here and
is never stored beside the hashes it keys. Throttling (§3 mitigation 1's attempt bound, §11.0) and
every audit append belong to the endpoint that calls these.
"""

from __future__ import annotations

import hashlib
import hmac
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Literal, cast

from egzos._types import (
    AS_REQUESTER_HINT_MAX_CHARS,
    ASGrant,
    ASState,
    Capability,
    DeviceAuthorization,
    DeviceAuthorizationRecord,
    DeviceRedemptionCause,
    DeviceRequest,
)
from egzos.authz import grant, values

#: §3 mitigation 1: the code expires. Not a contract value: this implementation's, kept short
#: because the `user_code` is ~34.6 bits and its lifetime is half of what carries it (§9.1).
DEVICE_CODE_LIFETIME_SECONDS = 600
#: RFC 8628 §3.2's default; a poll sooner than this after the last one is `slow_down`.
POLL_INTERVAL_SECONDS = 5

# A fresh `user_code` that collides with a live one is drawn again, a bounded number of times.
_USER_CODE_DRAWS = 8
_ISO = "%Y-%m-%dT%H:%M:%SZ"

PollError = Literal[
    "authorization_pending", "slow_down", "access_denied", "expired_token", "invalid_grant"
]


@dataclass(frozen=True)
class Entry:
    """What `/device` learns from a typed `user_code`. `record` is set exactly when row (b)'s
    outcome is `found`; otherwise `cause` is the closed word for `details.cause`, which never
    reaches the page."""

    record: DeviceAuthorizationRecord | None
    cause: DeviceRedemptionCause | None


@dataclass(frozen=True)
class Poll:
    """The token endpoint's answer. `record` is set, with its `grant`, exactly when `error` is
    None: the authorization was approved and is now spent."""

    error: PollError | None
    record: DeviceAuthorizationRecord | None = None


def _aware(at: datetime) -> bool:
    return at.tzinfo is not None and at.utcoffset() is not None


def _clock(now: datetime | None) -> datetime:
    at = now or datetime.now(UTC)
    if not _aware(at):
        raise ValueError("authz.device needs an aware datetime")
    return at


def _iso(at: datetime) -> str:
    return at.astimezone(UTC).strftime(_ISO)


def _parse(text: str | None) -> datetime | None:
    try:
        return datetime.strptime(text, _ISO).replace(tzinfo=UTC)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return None


def _same(given: str | None, stored: str) -> bool:
    # Bytes, as `codes` does: `compare_digest` raises on non-ASCII `str`, and a raise would be a
    # second answer shape beside `invalid_grant`.
    if not isinstance(given, str):
        return False
    return hmac.compare_digest(
        given.encode("utf-8", "surrogatepass"), stored.encode("utf-8", "surrogatepass")
    )


def _expired(record: DeviceAuthorizationRecord, at: datetime) -> bool:
    until = _parse(record["expires_at"])
    return until is None or at >= until  # an expiry nobody can read fails closed


def user_code_hash(key: bytes, code: str) -> str:
    """storage.md §3.1: the lowercase hex HMAC-SHA256 of the canonical `user_code` under the
    device-code key, never a bare sha256 (the code is low-entropy)."""
    if not isinstance(key, bytes) or not key:
        raise ValueError("the device-code key is a non-empty byte string")
    return hmac.new(key, code.encode("ascii", "replace"), hashlib.sha256).hexdigest()


def authorize(
    state: ASState,
    *,
    key: bytes,
    client_id: str,
    scope: str | None,
    requester_hint: object,
    verification_uri: str,
    now: datetime | None = None,
) -> DeviceAuthorization:
    """Store a pending authorization and return RFC 8628's response, less
    `verification_uri_complete` ([0.3 · 21]).

    `client_id` is one the endpoint already found registered as `cli`. An unparseable `scope`
    raises `grant.ScopeVocabularyError` and stores nothing. `requester_hint` is unverified: kept
    only if it is a string, truncated, never refused for its length (§11.8)."""
    at = _clock(now)
    expanded = grant.parse_scope(scope)
    hint = requester_hint[:AS_REQUESTER_HINT_MAX_CHARS] if isinstance(requester_hint, str) else None
    for _ in range(_USER_CODE_DRAWS):
        user_code = values.new_user_code()
        code_hash = user_code_hash(key, user_code)
        if state.get_device_by_user_code(code_hash) is None:
            break
    else:  # 8 collisions in a 2^34.6 space is a broken CSPRNG or store, not a load: store nothing
        raise RuntimeError("no free user_code")
    device_code = values.new_value()
    state.put_device(
        DeviceAuthorizationRecord(
            device_code_hash=values.digest(device_code),
            user_code_hash=code_hash,
            client_id=client_id,
            requested=DeviceRequest(
                capabilities=cast(list[Capability], list(expanded.capabilities)),
                scopes=list(expanded.scopes),
            ),
            requester_hint=hint,
            decision="pending",
            grant=None,
            expires_at=_iso(at + timedelta(seconds=DEVICE_CODE_LIFETIME_SECONDS)),
            last_polled_at=None,
        )
    )
    return DeviceAuthorization(
        device_code=device_code,
        user_code=values.display_user_code(user_code),
        verification_uri=verification_uri,
        expires_in=DEVICE_CODE_LIFETIME_SECONDS,
        interval=POLL_INTERVAL_SECONDS,
    )


def enter(
    state: ASState, *, key: bytes, user_code: str | None, now: datetime | None = None
) -> Entry:
    """Row (b): look up a typed `user_code`. Found only while pending and unexpired; a decided
    authorization's code is spent whether it was approved or denied (§11.8)."""
    at = _clock(now)
    code = values.normalize_user_code(user_code)
    # A malformed code still costs one keyed hash and one store read, so it is not a faster
    # answer than an unknown one: one timing class for all five causes (§11.8).
    record = state.get_device_by_user_code(user_code_hash(key, code or ""))
    if code is None:
        return Entry(None, "malformed")
    if record is None:
        return Entry(None, "invalid")
    if _expired(record, at):
        return Entry(None, "expired")
    if record["decision"] != "pending":
        return Entry(None, "used")
    return Entry(record, None)


def decide(
    state: ASState,
    *,
    key: bytes,
    user_code: str | None,
    approve: bool,
    lifetime_seconds: int | None = None,
    now: datetime | None = None,
) -> bool:
    """The owner's decision at `/device`: True exactly when this call moved the authorization out
    of pending. The record is read again here and the grant built from what `put_device` stored,
    so nothing a caller holds, or edits, reaches `decide_device`. `lifetime_seconds` is clamped
    by §11.5."""
    at = _clock(now)
    record = enter(state, key=key, user_code=user_code, now=at).record
    if record is None:
        return False
    if approve is not True:
        return state.decide_device(record["device_code_hash"], None)
    requested = record["requested"]
    decided = ASGrant(
        capabilities=list(requested["capabilities"]),
        scopes=list(requested["scopes"]),
        principal="client",  # §10.3: only §2's browser flow mints `interactive`
        grant_expires_at=_iso(at + timedelta(seconds=grant.clamp_grant_lifetime(lifetime_seconds))),
    )
    return state.decide_device(record["device_code_hash"], decided)


def poll(
    state: ASState,
    *,
    device_code: str | None,
    client_id: str | None,
    now: datetime | None = None,
) -> Poll:
    """RFC 8628 §3.5 at the token endpoint. An unknown `device_code`, another client's, a spent
    one and a naive clock all answer `invalid_grant`, alike."""
    at = now or datetime.now(UTC)
    if not isinstance(device_code, str) or not device_code or not _aware(at):
        return Poll("invalid_grant")
    device_hash = values.digest(device_code)
    prior = state.poll_device(device_hash, _iso(at))
    if prior is None or not _same(client_id, prior["client_id"]):
        return Poll("invalid_grant")
    if _expired(prior, at):
        return Poll("expired_token")
    if prior["last_polled_at"] is not None:
        last = _parse(prior["last_polled_at"])
        if last is None or at - last < timedelta(seconds=POLL_INTERVAL_SECONDS):
            return Poll("slow_down")
    if prior["decision"] == "pending":
        return Poll("authorization_pending")
    spent = state.consume_device(device_hash)
    if spent is None:
        return Poll("invalid_grant")  # a concurrent poll spent it first
    if spent["decision"] == "granted" and spent["grant"] is not None:
        return Poll(None, spent)
    return Poll("access_denied")
