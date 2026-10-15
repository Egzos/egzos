# Copyright 2026 Ali Sasanian
# SPDX-License-Identifier: LicenseRef-PolyForm-Strict-1.0.0
"""
The login's evaluated attempt (authorization-server.md §11.7, §12 row (a)), against `ASGateState`.

v1.0's credential is the container secret ([0.3 · 7]). How it is provisioned, stored and rotated
is #143's and not in the record, so it reaches this module only through `LoginSecret`, whose one
method answers whether a presented value is the secret. Nothing here holds, derives or compares the
secret itself.

`attempt` is one evaluated attempt, and appends exactly one `authz.login` (§12.1 rule 1):

- the credential verifies: an interactive session is established (`sessions.establish`), no token
  is minted, and the entry is outcome `established`. The 303 goes to `continue` as
  `continuation.resolve` matches it, re-run here on the POST (§11.7, [0.3 · 26]), so a value that
  fails D-C5 lands on `/` with the session established;
- it does not: nothing is stored, and the entry is outcome `failed`, cause `wrong`. The page
  answer is one answer, whatever the credential was (§11.7).

`unknown` is never emitted here: v1.0's login takes no user identifier, so no attempt is evaluated
against a user that could be missing. `throttled` is §11.0's, written by the counter in front of
this function at the attempt that engages it (#208); a held throttle never calls `attempt`, which is
what keeps §12.1 rule 4's "a correct secret included" true. The entry carries `principal: none` and
`actor: login` (§12.2), and never the credential or `continue` (§12.1 rule 7).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Protocol

from egzos._types import ASGateState, LoginCause
from egzos.authz import AuditLedger, continuation, sessions

# A bound on what is handed to the verifier at all, so a caller cannot make one attempt cost what a
# long input costs a slow comparison. A longer value is verified as the empty one and fails alike.
_MAX_CREDENTIAL_BYTES = 1024


class LoginSecret(Protocol):
    """The container secret, behind the interface #143 has yet to fill.

    `verify` MUST compare in constant time over the presented value, and MUST return `False` for
    the empty string: `attempt` calls it on every evaluated attempt, a missing credential included,
    so a wrong value and an absent one cost the same."""

    def verify(self, presented: str) -> bool: ...


@dataclass(frozen=True)
class Login:
    """The answer to one evaluated attempt. `session` and `location` are set together, exactly when
    the credential verified: the cookie value and the 303's relative reference. Otherwise both are
    `None`, and the caller renders §11.7's one failure. The cause stays in the ledger."""

    session: str | None
    location: str | None


def attempt(
    gate: ASGateState,
    ledger: AuditLedger,
    secret: LoginSecret,
    *,
    credential: str | None,
    continue_value: str | None,
    now: datetime | None = None,
) -> Login:
    """§11.7's credential POST, after §11.0's counter has admitted it. A naive `now` is a caller's
    bug: it raises `ValueError` before anything is verified, stored or appended."""
    at = now or datetime.now(UTC)
    if at.tzinfo is None or at.utcoffset() is None:
        raise ValueError("login.attempt needs an aware datetime")
    presented = ""
    if isinstance(credential, str):
        try:
            if len(credential.encode("utf-8")) <= _MAX_CREDENTIAL_BYTES:
                presented = credential
        except UnicodeEncodeError:
            pass  # a lone surrogate is no secret anyone was given
    verified = secret.verify(presented)
    if verified is not True or not presented:
        cause: LoginCause = "wrong"
        ledger.append("authz.login", actor="login", principal="none", outcome="failed", cause=cause)
        return Login(None, None)
    # The location first: nothing is stored or appended until every part of the answer exists.
    location = continuation.resolve(continue_value)
    session = sessions.establish(gate, now=at)
    ledger.append("authz.login", actor="login", principal="none", outcome="established")
    return Login(session, location)
