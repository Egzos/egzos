# Copyright 2026 Ali Sasanian
# SPDX-License-Identifier: LicenseRef-PolyForm-Strict-1.0.0
"""
`/authorize`'s pre-trust tier (authorization-server.md §5.3), against `ASState`.

It runs after §11.0's three substeps, so only a request inside a live interactive session reaches
it, and before §7's post-trust tier. `admit` takes the query as received, pairs after one decode,
and either admits it or refuses it. Its checks, in this order:

1. `malformed`: `response_type` is not `code` (§2), `client_id` or `redirect_uri` is absent or
   empty, or one of the request's parameters appears more than once (RFC 6749 §3.1). An unknown
   parameter is ignored, a `principal` among them (§10.3).
2. `unknown_client`: no usable entry for `client_id` (§11.1, `screen.client_entry`).
3. `redirect_mismatch`: `redirect_uri` matches none of that entry's URIs (§5.1, §5.2).
4. `missing_pkce`: no `code_challenge`, or a method other than `S256`, `plain` included. A
   challenge no SHA-256 digest could encode to is `malformed` (§5.3 clause 1, `pkce`).
5. `replayed`: a session has already decided this request (§11.4, `decided.replayed`).

A refusal appends row (d) once, `authz.refuse` with the first failing check's cause,
`principal: none` and `actor: authorize` (§12, §12.2), and the caller answers with `STATUS` and
`COPY` (§5.3 [0.3 · 23]). That answer is never a redirect, and its cause is never on it. §5.3
clause 2's time budget is owed by that response, not here. Admission appends nothing: the request
goes on to §7's tier, whose entry is (f) or (g). `throttled` and `token_presented` are §11.0's
causes, decided before this tier, so they do not arise here.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from egzos._types import AS_AUTHORIZE_PRETRUST_CAUSES, ASState, AuthorizePretrustCause
from egzos.authz import AuditLedger, decided, pkce, redirects, screen

# §5.3: one status for every cause, and one line of copy, `consent.md` §2.5's heading.
STATUS = 400
COPY = "This request can't be completed."

# The parameters this tier and §7's read. Each may appear at most once.
_PARAMS = frozenset(
    {
        "response_type",
        "client_id",
        "redirect_uri",
        "code_challenge",
        "code_challenge_method",
        "state",
        "scope",
    }
)


@dataclass(frozen=True)
class Admitted:
    """A request the pre-trust tier let through, for §7's tier. `key` is §11.4's request key, for
    `decided.record` once the owner decides."""

    client: screen.ClientEntry
    redirect_uri: str
    code_challenge: str
    state: str | None
    scope: str | None
    key: str


def refuse(ledger: AuditLedger, cause: AuthorizePretrustCause) -> None:
    """Append row (d). No `client_id`, no session and no parameter: (d) names no client (§12).
    A cause outside `AS_AUTHORIZE_PRETRUST_CAUSES` is a caller's bug and raises `ValueError`,
    so no entry is written."""
    if not isinstance(cause, str) or cause not in AS_AUTHORIZE_PRETRUST_CAUSES:
        raise ValueError("row (d) takes a closed cause")
    ledger.append("authz.refuse", actor="authorize", principal="none", cause=cause)


def _single(params: Sequence[tuple[str, str]]) -> dict[str, str] | None:
    """The request's own parameters, or None when one repeats or a pair is not two strings."""
    seen: dict[str, str] = {}
    for pair in params:
        if not isinstance(pair, tuple) or len(pair) != 2:
            return None
        name, value = pair
        if not isinstance(name, str) or not isinstance(value, str):
            return None
        if name not in _PARAMS:
            continue
        if name in seen:
            return None
        seen[name] = value
    return seen


def _check(
    state: ASState, params: Sequence[tuple[str, str]]
) -> AuthorizePretrustCause | tuple[dict[str, str], screen.ClientEntry, str]:
    """Checks 1–4, in order: the first failing check's cause, or what they admitted."""
    query = _single(params)
    if query is None or query.get("response_type") != "code":
        return "malformed"
    client_id, redirect_uri = query.get("client_id"), query.get("redirect_uri")
    if not client_id or not redirect_uri:
        return "malformed"
    entry = screen.client_entry(state, client_id)
    if entry is None:
        return "unknown_client"
    if not redirects.match_any(redirect_uri, list(entry.redirect_uris)):
        return "redirect_mismatch"
    try:
        challenge = pkce.check_challenge(
            query.get("code_challenge"), query.get("code_challenge_method")
        )
    except pkce.MissingPKCE:
        return "missing_pkce"
    except pkce.MalformedPKCE:
        return "malformed"
    return query, entry, challenge


def admit(
    state: ASState, ledger: AuditLedger, params: Sequence[tuple[str, str]]
) -> Admitted | None:
    """§5.3's tier for one `/authorize` request. `None` means it was refused and row (d) is
    appended: answer with `STATUS` and `COPY`. Call it only after §11.0 has admitted the request
    on a live session."""
    found = _check(state, params)
    if isinstance(found, str):
        refuse(ledger, found)
        return None
    query, entry, challenge = found
    redirect_uri = query["redirect_uri"]
    # RFC 6749 §3.1: a parameter sent without a value is treated as omitted, so `state=` and no
    # `state` are one request to §11.4, and an empty `state` never reaches §11.6's redirect.
    request_state, scope = query.get("state") or None, query.get("scope") or None
    key = decided.request_key(
        client_id=entry.client_id,
        redirect_uri=redirect_uri,
        state=request_state,
        code_challenge=challenge,
    )
    # `replayed` appends its own row (d).
    if decided.replayed(state, ledger, key=key):
        return None
    return Admitted(
        client=entry,
        redirect_uri=redirect_uri,
        code_challenge=challenge,
        state=request_state,
        scope=scope,
        key=key,
    )
