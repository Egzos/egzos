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
out, a record whose clocks cannot be read, and a `now` that reads well behind the record's
clocks. Which one never leaves this module. Only the last leaves the session in the store.

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


def _judge(record: SessionRecord, at: datetime) -> bool | None:
    """True for live, False for ended, `None` for a `now` earlier than the record's clocks.

    `now` can run up to `_SKEW` behind a stored stamp without anything being wrong. Two requests
    on one session race: B reads `now`, A then touches with a later second, and B reads A's
    stamp. A live session in that window is judged live. Further behind (an NTP step backwards)
    there is no instant to measure from, so the request is refused and the session is not ended.
    The owner is not signed out for the host's clock, and the clocks keep running from the
    stored stamps, which nothing here moves backwards."""
    created = _parse(record.get("created_at"))
    seen = _parse(record.get("last_seen_at"))
    if created is None or seen is None:
        return False  # a clock nobody can read fails closed
    if at < created - _SKEW or at < seen - _SKEW:
        return None
    return at - seen < _IDLE and at - created < _ABSOLUTE


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
    live = _judge(record, at)
    if live is None:
        return None  # refused; the session stays for a request whose clock reads true
    if not live:
        gate.end_session(session_hash)
        return None
    # The later of the two stamps, so a request inside `_SKEW` never moves the idle clock back.
    # Both are `_ISO` strings `_judge` has parsed, so they compare as text.
    stamp = max(_iso(at), record["last_seen_at"])
    # `touch_session` is False when the record went between the read and the write (a sign-out
    # in another request): that session is no longer live, whatever the read said.
    return session_hash if gate.touch_session(session_hash, stamp) else None


def end(gate: ASGateState, value: str | None) -> None:
    """Sign out. Ending an unknown or already-ended session is the same call and the same answer:
    the store's `bool` stays here (storage.md §3.1)."""
    if isinstance(value, str) and value:
        gate.end_session(values.digest(value))
