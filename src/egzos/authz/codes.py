# Copyright 2026 Ali Sasanian
# SPDX-License-Identifier: LicenseRef-PolyForm-Strict-1.0.0
"""
The authorization code (authorization-server.md §2), against `ASState` (storage.md §3.1).

A code is single-use, lives `AS_CODE_LIFETIME_SECONDS` (60), and is bound to the `client_id`, the
`redirect_uri` and the `code_challenge` it was issued against, and to the initiating session. Its
value reaches the store only as `values.digest` of the whole value.

Redemption spends the code before it judges anything: `consume_code` invalidates it in the same
step that returns it, so the first attempt, successful or not, is the last (§2). Every binding,
the PKCE verifier and the expiry are then checked on what came back, all of them every time, and
any failure is `None` — the same answer as an unknown code, an expired one and a spent one (§2,
§5.3). Which check failed never leaves this function.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from egzos._types import AS_CODE_LIFETIME_SECONDS, ASGrant, ASState, AuthorizationCodeRecord
from egzos.authz import pkce, values

_ISO = "%Y-%m-%dT%H:%M:%SZ"


def _aware(at: datetime) -> bool:
    # A naive `datetime` has no instant: `astimezone` would read it as local time and comparing it
    # with an aware one raises. Neither is an answer this module may give.
    return at.tzinfo is not None and at.utcoffset() is not None


def _iso(at: datetime) -> str:
    return at.astimezone(UTC).strftime(_ISO)


def _expired(expires_at: str, now: datetime) -> bool:
    try:
        until = datetime.strptime(expires_at, _ISO).replace(tzinfo=UTC)
    except (TypeError, ValueError):
        return True  # an expiry nobody can read fails closed
    return not _aware(now) or now >= until  # so does a clock nobody can place


def issue(
    state: ASState,
    *,
    client_id: str,
    redirect_uri: str,
    code_challenge: str,
    session_hash: str,
    grant: ASGrant,
    now: datetime | None = None,
) -> str:
    """Mint a code for a decided authorization and store its digest. Returns the value, which the
    caller puts in the redirect and nowhere else.

    `redirect_uri` and `code_challenge` are the ones the request was admitted with (`redirects`,
    `pkce.check_challenge`); this function binds them and does not re-validate them. A naive
    `now` is a caller's bug and raises `ValueError`; no code is stored."""
    at = now or datetime.now(UTC)
    if not _aware(at):
        raise ValueError("codes.issue needs an aware datetime")
    value = values.new_value()
    state.put_code(
        AuthorizationCodeRecord(
            code_hash=values.digest(value),
            client_id=client_id,
            redirect_uri=redirect_uri,
            code_challenge=code_challenge,
            session_hash=session_hash,
            grant=grant,
            expires_at=_iso(at + timedelta(seconds=AS_CODE_LIFETIME_SECONDS)),
        )
    )
    return value


def redeem(
    state: ASState,
    *,
    code: str | None,
    client_id: str | None,
    redirect_uri: str | None,
    code_verifier: str | None,
    now: datetime | None = None,
) -> AuthorizationCodeRecord | None:
    """The token endpoint's `authorization_code` grant, up to (not including) the mint.

    Returns the spent record when every §2 check holds, else `None` for every failure alike. The
    code is spent by the attempt either way; a second attempt with the right verifier finds
    nothing. A naive `now` counts as expired: `None`, never a raise."""
    if not isinstance(code, str) or not code:
        return None
    record = state.consume_code(values.digest(code))
    if record is None:
        return None
    at = now or datetime.now(UTC)
    # A list, not `and`: every check runs on every attempt, so no failure is cheaper than another.
    checks = [
        values.same(client_id, record["client_id"]),
        isinstance(redirect_uri, str) and redirect_uri == record["redirect_uri"],  # §5.1: exact
        pkce.verify(code_verifier, record["code_challenge"]),
        not _expired(record["expires_at"], at),
    ]
    return record if all(checks) else None
