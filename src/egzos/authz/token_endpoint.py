# Copyright 2026 Ali Sasanian
# SPDX-License-Identifier: LicenseRef-PolyForm-Strict-1.0.0
"""
The token endpoint's request and response (authorization-server.md §1, §2, §3, §9.2; RFC 6749
§3.2, §5.1, §5.2; RFC 8628 §3.4, §3.5). No HTTP framework here: the router hands `respond` one
`POST`'s form body as decoded pairs and sends back `Answer.status`, `HEADERS` and `Answer.body` as
JSON.

`respond` checks, in this order, and the first failure is the answer:

1. `invalid_request`: the body is not `application/x-www-form-urlencoded`, a pair is not two
   strings, or a parameter repeats (RFC 6749 §3.2). A parameter sent without a value is omitted.
2. `invalid_request`: the request attempts client authentication, with an `Authorization` header,
   a `client_secret` or a `client_assertion`. No client on this AS authenticates (§1, §6's
   `["none"]`), so no path reads a secret: the attempt is refused, never checked.
3. `invalid_request` with no `grant_type`, and `unsupported_grant_type` for any value outside
   `GRANTS`, §6's `grant_types_supported`: the implicit, password and
   client-credentials grants do not exist here (§2).
4. The grant itself, through `tokens`:
   - `authorization_code`: `tokens.exchange_code`. Whatever else is missing, the code is handed
     on, so a present code is spent by this attempt, successful or not (§2). Every refusal is
     `invalid_grant`, alike.
   - the device grant: `tokens.exchange_device`, whose word RFC 8628 §3.5 has the client see.
   - `refresh_token`: `tokens.refresh`, every refusal `invalid_grant`. A `scope` here is
     `invalid_scope` before anything is spent. RFC 6749 §6 lets a refresh narrow, but rotation
     carries the stored grant unchanged (§9.2 clause 3) and a request is never silently narrowed
     (§7); telling an equal `scope` from a narrower one needs the stored grant, which only the
     spending read returns (#240).

`owner` is the container's identity, supplied by the router and never read from the request
(#216's review). A refusal appends nothing: the token endpoint's entries are §9.3's `token.mint`,
and `token.revoke` on refresh reuse, both appended by `tokens`. No response carries
`error_description` or `scope`: the first is §11.6's rule applied to every error this AS words, and
the second is RFC 6749 §5.1's to omit when the grant is the one requested, which is the only grant
this AS issues (§7). The endpoint is not among `AS_THROTTLE_SURFACES`.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Literal

from egzos.authz import AuditLedger, tokens

#: RFC 6749 §5.1: every response from this endpoint, a refusal included, is never cached.
HEADERS = {"Cache-Control": "no-store", "Pragma": "no-cache"}
#: RFC 6749 §5.1's `token_type`; the value resolves through `Auth.use` like any `Token`'s.
TOKEN_TYPE = "Bearer"

CODE_GRANT = "authorization_code"
REFRESH_GRANT = "refresh_token"
DEVICE_GRANT = "urn:ietf:params:oauth:grant-type:device_code"

#: The three grants this endpoint redeems: §6's `grant_types_supported`, which a test pins.
GRANTS = (CODE_GRANT, REFRESH_GRANT, DEVICE_GRANT)

_FORM = "application/x-www-form-urlencoded"
# Client authentication, which no client on this AS has (§1).
_CLIENT_AUTH = frozenset({"client_secret", "client_assertion", "client_assertion_type"})

ErrorWord = Literal[
    "invalid_request",
    "unsupported_grant_type",
    "invalid_grant",
    "invalid_scope",
    "authorization_pending",
    "slow_down",
    "access_denied",
    "expired_token",
]


@dataclass(frozen=True)
class Answer:
    """One response: send `status`, `HEADERS`, and `body` as JSON."""

    status: int
    body: dict[str, Any]


def _error(word: ErrorWord) -> Answer:
    return Answer(400, {"error": word})


def _issued(issued: tokens.Issued) -> Answer:
    return Answer(
        200,
        {
            "access_token": issued.access_token,
            "token_type": TOKEN_TYPE,
            "expires_in": issued.expires_in,
            "refresh_token": issued.refresh_token,
        },
    )


def _form(content_type: str | None) -> bool:
    if not isinstance(content_type, str):
        return False
    return content_type.split(";", 1)[0].strip().lower() == _FORM


def form_body(params: Sequence[tuple[str, str]], content_type: str | None) -> dict[str, str] | None:
    """Check 1 above, which the device authorization endpoint shares: the body's parameters, or
    None for `invalid_request`."""
    return _single(params) if _form(content_type) else None


def authenticates(form: dict[str, str], authorization: str | None) -> bool:
    """Check 2 above, also shared: True when the request attempts client authentication."""
    return bool(isinstance(authorization, str) and authorization.strip()) or bool(
        _CLIENT_AUTH & form.keys()
    )


def _single(params: Sequence[tuple[str, str]]) -> dict[str, str] | None:
    """Every parameter once, an empty one dropped as omitted; None when one repeats or a pair is
    not two strings. Unlike `/authorize`'s, every name counts: a repeated unknown is still a
    repeat, and an unknown one is otherwise ignored."""
    seen: dict[str, str] = {}
    names: set[str] = set()
    for pair in params:
        if not isinstance(pair, tuple) or len(pair) != 2:
            return None
        name, value = pair
        if not isinstance(name, str) or not isinstance(value, str) or name in names:
            return None
        names.add(name)
        if value:
            seen[name] = value
    return seen


def respond(
    state: tokens.TokenState,
    ledger: AuditLedger,
    params: Sequence[tuple[str, str]],
    *,
    content_type: str | None,
    authorization: str | None,
    owner: str,
    now: datetime | None = None,
) -> Answer:
    """One token request. `params` is the form body as decoded pairs, in order; `content_type`
    and `authorization` are the request's headers; `owner` is the container's identity."""
    form = form_body(params, content_type)
    if form is None or authenticates(form, authorization):
        return _error("invalid_request")
    grant_type = form.get("grant_type")
    if grant_type is None:
        return _error("invalid_request")
    if grant_type not in GRANTS:
        return _error("unsupported_grant_type")
    client_id = form.get("client_id")
    if grant_type == CODE_GRANT:
        issued = tokens.exchange_code(
            state,
            ledger,
            code=form.get("code"),
            client_id=client_id,
            redirect_uri=form.get("redirect_uri"),
            code_verifier=form.get("code_verifier"),
            owner=owner,
            now=now,
        )
        return _issued(issued) if issued is not None else _error("invalid_grant")
    if grant_type == DEVICE_GRANT:
        answer = tokens.exchange_device(
            state,
            ledger,
            device_code=form.get("device_code"),
            client_id=client_id,
            owner=owner,
            now=now,
        )
        return _error(answer) if isinstance(answer, str) else _issued(answer)
    if "scope" in form:
        return _error("invalid_scope")
    issued = tokens.refresh(
        state, ledger, refresh_token=form.get("refresh_token"), client_id=client_id, now=now
    )
    return _issued(issued) if issued is not None else _error("invalid_grant")
