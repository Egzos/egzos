# Copyright 2026 Ali Sasanian
# SPDX-License-Identifier: LicenseRef-PolyForm-Strict-1.0.0
"""
`/authorize`'s session check, §11.0 substep 3 (authorization-server.md §10.2, §11.0, §11.7).

It runs after the counter (substep 2, #208) and before either validation tier, on every
`/authorize` request, the render and the decision alike. `check` branches on the session first,
so a request holding both a session and a credential is decided on the session and the credential
is never looked at. Exactly one of three things happens:

- `Session`: a live interactive session (`sessions.resolve`, which restarts its idle clock). The
  request goes on to `pretrust.admit`.
- `Refused`: no live session, and a bearer credential in the `Authorization` header. Row (d)
  `authz.refuse` is appended once, cause `token_presented`, and the caller answers with §5.3's
  page (`pretrust.STATUS`, `pretrust.COPY`). The credential is presence-tested and nothing more:
  no `Token` lookup, no parse, no expiry check, so a live token and a forged one cost the same
  and get the same answer (§10.2's first bound). It is refused, never redirected (the second).
- `ToLogin`: neither. A 303 to `/login`, whose `continue` is `/authorize` with the request's
  query exactly as received, so §2's flow and `consent.md` R3's hand-off resume after the login
  (§11.7). Nothing is read, validated, stored or appended for it: the location is built from the
  caller's own bytes alone, so the status and the path are the same whatever the request names.

The `Authorization` header is the one position this surface looks at. `/authorize` reads no
`access_token` parameter: `pretrust` ignores a parameter it does not know, so a value there is
neither presented nor carried anywhere but back to the same caller.

§12 row (h)'s `redirected` tally, and the counter's increment for a `ToLogin`, are the throttle's
(#208). This module counts nothing.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from urllib.parse import quote

from egzos._types import ASGateState
from egzos.authz import AuditLedger, metadata, pretrust, sessions

#: §11.0 substep 3's redirect status.
REDIRECT_STATUS = 303


@dataclass(frozen=True)
class Session:
    """A live interactive session: its `session_hash`, which keys §11.0 substep 1 and §11.4."""

    session_hash: str


@dataclass(frozen=True)
class ToLogin:
    """Answer with `REDIRECT_STATUS` and `Location: location`, a relative reference."""

    location: str


@dataclass(frozen=True)
class Refused:
    """Row (d) `token_presented` is appended. Answer with `pretrust.STATUS` and `pretrust.COPY`."""


def presents_credential(authorization: str | None) -> bool:
    """Whether the `Authorization` header carries anything at all. Presence only: whatever the
    scheme and whatever the value, it is never parsed or looked up (§10.2)."""
    return isinstance(authorization, str) and bool(authorization.strip())


def login_location(query: str | None) -> str:
    """`/login?continue=…` for a session-less `/authorize` request whose raw query string, still
    percent-encoded, is `query`. `continue` is encoded once more here, so the framework's one
    decode of the parameter hands `continuation.resolve` `/authorize?<query>` exactly as received.
    A query with no UTF-8 form is dropped for the bare path, as no request off the wire has one."""
    target = metadata.AUTHORIZE_PATH
    if isinstance(query, str) and query:
        target = f"{target}?{query}"
    try:
        carried = quote(target, safe="")
    except UnicodeEncodeError:
        carried = quote(metadata.AUTHORIZE_PATH, safe="")
    return f"{metadata.LOGIN_PATH}?continue={carried}"


def check(
    gate: ASGateState,
    ledger: AuditLedger,
    *,
    session: str | None,
    authorization: str | None,
    query: str | None,
    now: datetime | None = None,
) -> Session | ToLogin | Refused:
    """§11.0 substep 3 for one `/authorize` request that the counter let through. `session` is the
    session cookie's value, `authorization` the `Authorization` header, `query` the raw query
    string. A naive `now` is a caller's bug: it raises `ValueError` before anything is read,
    touched or appended."""
    at = now or datetime.now(UTC)
    if at.tzinfo is None or at.utcoffset() is None:
        raise ValueError("gate.check needs an aware datetime")
    live = sessions.resolve(gate, session, now=at)
    if live is not None:
        return Session(live)
    if presents_credential(authorization):
        pretrust.refuse(ledger, "token_presented")
        return Refused()
    return ToLogin(login_location(query))
