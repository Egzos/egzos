# Copyright 2026 Ali Sasanian
# SPDX-License-Identifier: LicenseRef-PolyForm-Strict-1.0.0
"""
The revocation endpoint's request and response (authorization-server.md §9.2 clause 1; RFC 7009
§2.1, §2.2; RFC 6749 §5.2). Like `token_endpoint`, no HTTP framework: the router hands `respond`
one `POST`'s form body as decoded pairs and sends back `Answer.status`, `token_endpoint.HEADERS`
and `Answer.body` as JSON.

`respond` checks, in this order, and the first failure is the answer:

1. `invalid_request`: `token_endpoint`'s checks 1 and 2, shared and not copied. The body is a
   form with every parameter once, and no client authentication is attempted (§1).
2. `invalid_request` with no `token` (RFC 7009 §2.1 requires it) or no `client_id`, the one way a
   public client identifies itself (RFC 6749 §2.3, §3.2.1). Neither answer depends on anything
   stored: nothing has been read when it is given.
3. Otherwise `revoke.by_value`, and the answer is `REVOKED`, one 200 with an empty body, whatever
   happened: a token really revoked, and an unknown, malformed, already-revoked or other client's
   token alike (§9.2's silence rule). `by_value` returns nothing, so no outcome can reach the
   answer. `token_type_hint` is not read, and any value of it is accepted: a hint only orders a
   lookup (RFC 7009 §2.1), so `unsupported_token_type` is never answered.

The only entry is `token.revoke`, appended by `revoke` for a token really revoked ([0.3 · 30]). A
refusal appends nothing. The endpoint is not among `AS_THROTTLE_SURFACES`: §9.2's `revoke`
surface is the owner path's (§11.9), and this one is bounded by §9.1's entropy alone.

§9.2's time budget is the router's to keep, with `budget.Budget` started before `respond` and
settled after it. A token really revoked writes and appends, and an unknown one returns before the
digest, so the paths differ in time here and converge only at the padded response.
"""

from __future__ import annotations

from collections.abc import Sequence

from egzos.authz import AuditLedger, revoke
from egzos.authz.token_endpoint import Answer, authenticates, form_body
from egzos.authz.tokens import TokenState

#: The one answer to every request that reaches `revoke.by_value` (§9.2 clause 1).
REVOKED = Answer(200, {})


def _invalid_request() -> Answer:
    return Answer(400, {"error": "invalid_request"})


def respond(
    state: TokenState,
    ledger: AuditLedger,
    params: Sequence[tuple[str, str]],
    *,
    content_type: str | None,
    authorization: str | None,
) -> Answer:
    """One revocation request. `params`, `content_type` and `authorization` are as in
    `token_endpoint.respond`."""
    form = form_body(params, content_type)
    if form is None or authenticates(form, authorization):
        return _invalid_request()
    token, client_id = form.get("token"), form.get("client_id")
    if token is None or client_id is None:
        return _invalid_request()
    revoke.by_value(state, ledger, token=token, client_id=client_id)
    return Answer(REVOKED.status, dict(REVOKED.body))
