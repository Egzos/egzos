# Copyright 2026 Ali Sasanian
# SPDX-License-Identifier: LicenseRef-PolyForm-Strict-1.0.0
"""
The interactive session (authorization-server.md §10.1, §10.2), against `ASGateState`
(storage.md §3.1).

A session is not a `Token`. It has no `Token.id`, carries no capabilities or scopes, and appears
in no `token ls`. Nothing here resolves a `Token` or a bearer value, and nothing in `auth.py`
resolves a session, so neither can be presented where the other is accepted. Its value is a
`values.new_value()` that the caller puts in a cookie on the container's own origin and nowhere
else. It reaches the store only as `values.digest` of the whole value.

The store holds the clocks and does not judge them. Trust does, here, on every `resolve`: a
session ends at `AS_SESSION_IDLE_SECONDS` (30 min) since its last page request, or at
`AS_SESSION_ABSOLUTE_SECONDS` (8 h) since the login that established it, whichever comes first
([0.3 · 13]). A live session's `resolve` restarts the idle clock. Nothing restarts the absolute
clock, so no stream of page loads can keep a session alive past it. An ended session is ended in
the store too, so the next `resolve` finds nothing.

Every answer that is not a live session is `None`: unknown, idle-ended, absolute-ended, signed
out, a record whose clocks cannot be read, and a `now` that reads more than `_SKEW` behind the
record's clocks. Which one never leaves this module. All but signed out and unknown end the
session in the store: a clock nobody can measure from fails closed.

This module appends nothing. The login's row (a) `authz.login` is §11.7's, and needs §11.0's
throttle in front of it (#208). A session ending on its clocks is not one of §9.3's seven
effects, and has no §12 row.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from egzos._types import (
    AS_SESSION_ABSOLUTE_SECONDS,
    AS_SESSION_IDLE_SECONDS,
    ASGateState,
    SessionRecord,
)
from egzos.authz import values

_ISO = "%Y-%m-%dT%H:%M:%SZ"

_IDLE = timedelta(seconds=AS_SESSION_IDLE_SECONDS)
_ABSOLUTE = timedelta(seconds=AS_SESSION_ABSOLUTE_SECONDS)
# How far `now` may read behind a stored stamp and still be judged: two requests racing on one
# session, stamps truncated to the second. This implementation's number, not a contract value.
_SKEW = timedelta(seconds=2)


def _aware(at: datetime) -> bool:
    return at.tzinfo is not None and at.utcoffset() is not None


def _iso(at: datetime) -> str:
    return at.astimezone(UTC).strftime(_ISO)


def _parse(text: object) -> datetime | None:
    try:
        return datetime.strptime(text, _ISO).replace(tzinfo=UTC)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return None


def _judge(record: SessionRecord, at: datetime) -> datetime | None:
    """The idle clock's new start for a live session, else `None` for an ended one.

    `now` can run up to `_SKEW` behind a stored stamp without anything being wrong. Two requests
    on one session race: B reads `now`, A then touches with a later second, and B reads A's
    stamp. A live session in that window is judged live, and the idle clock restarts from the
    later of `now` and the stored stamp, so B does not move it back. Further behind (an NTP step
    backwards, or stamps written while the clock ran ahead) there is no instant to measure from,
    and the session fails closed: kept dormant, it would come back live once the clock reached
    stamps written ahead of true time, and live longer than §10.2's bounds in true time."""
    created = _parse(record.get("created_at"))
    seen = _parse(record.get("last_seen_at"))
    if created is None or seen is None:
        return None  # a clock nobody can read fails closed
    if at < created - _SKEW or at < seen - _SKEW:
        return None
    if at - seen < _IDLE and at - created < _ABSOLUTE:
        return max(at, seen)
    return None


def establish(gate: ASGateState, *, now: datetime | None = None) -> str:
    """Store a new session and return its value. The caller sets it as a cookie and writes it
    nowhere else: not in a page, a redirect or the chain.

    §11.7 calls this after the login's credential verifies, and only then. A naive `now` is a
    caller's bug and raises `ValueError`; no session is stored."""
    at = now or datetime.now(UTC)
    if not _aware(at):
        raise ValueError("sessions.establish needs an aware datetime")
    value = values.new_value()
    stamp = _iso(at)
    gate.put_session(
        SessionRecord(session_hash=values.digest(value), created_at=stamp, last_seen_at=stamp)
    )
    return value


def resolve(gate: ASGateState, value: str | None, *, now: datetime | None = None) -> str | None:
    """The `session_hash` of a live session, after restarting its idle clock, else `None`.

    Call it once per request to one of §11's pages, which is what restarts the idle clock
    (§10.2), and nowhere else: never at the REST surface or the token endpoint (§10.1). A session
    found ended on either clock is ended in the store. A naive `now` is `None` and ends nothing:
    the clock is the caller's fault, not the session's."""
    if not isinstance(value, str) or not value:
        return None
    at = now or datetime.now(UTC)
    if not _aware(at):
        return None
    session_hash = values.digest(value)
    record = gate.get_session(session_hash)
    if record is None:
        return None
    seen = _judge(record, at)
    if seen is None:
        gate.end_session(session_hash)
        return None
    # `touch_session` writes unconditionally, so two requests that both read before either
    # writes can leave the earlier of their two instants. That is still an instant the session
    # was seen live, so it can only shorten the idle clock, never stretch it.
    # `touch_session` is False when the record went between the read and the write (a sign-out
    # in another request): that session is no longer live, whatever the read said.
    return session_hash if gate.touch_session(session_hash, _iso(seen)) else None


def end(gate: ASGateState, value: str | None) -> None:
    """Sign out. Ending an unknown or already-ended session is the same call and the same answer:
    the store's `bool` stays here (storage.md §3.1)."""
    if isinstance(value, str) and value:
        gate.end_session(values.digest(value))
