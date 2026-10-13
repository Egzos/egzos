# Copyright 2026 Ali Sasanian
# SPDX-License-Identifier: LicenseRef-PolyForm-Strict-1.0.0
"""
The device authorization endpoint's request and response (authorization-server.md §3, §7, §7.1;
RFC 8628 §3.1, §3.2; RFC 6749 §5.2). Like `token_endpoint`, no HTTP framework: the router hands
`respond` one `POST`'s form body as decoded pairs and sends back `Answer.status`,
`token_endpoint.HEADERS` and `Answer.body` as JSON. The response carries a `device_code`, a
credential, so it is never cached either.

`respond` checks, in this order, and the first failure is the answer:

1. `invalid_request`: `token_endpoint`'s checks 1 and 2, shared and not copied. The body is a
   form with every parameter once, and no client authentication is attempted (§1).
2. `invalid_request` with no `client_id`. `invalid_client` for one that §11.1's registry read
   does not find registered as `cli`: an unknown id, a `browser` or `mcp` client and an entry the
   store hands back malformed are one answer. Browsers are retired from this flow (§1.1). The
   registry read happens once on every path that reaches it, so the answer is one read either way.
3. `invalid_scope` for a `scope` that §7 cannot expand, an absent one included: §7 defines no
   default grant. The request is refused whole and never narrowed (§7). Node ids are not looked
   up here. No owner is present to reach them, so nothing in this answer tells a known node from
   an unknown one (§7.1, applied to the device flow).
4. Otherwise `device.authorize` stores the pending record, and the answer is §3's five keys,
   with no `verification_uri_complete` ([0.3 · 21]). `verification_uri` is the container's own
   `/device`, built from the issuer and never from the request.

Nothing appends: a device authorization request is §9.3 row 7, which has no event of its own
([0.3 · 32]). The endpoint is not among `AS_THROTTLE_SURFACES`. §3 mitigation 1 bounds the
`user_code`'s attempts at `/device` (the `device` surface) and its lifetime here.

The requester hint (§11.8) is not read from the request. The contract names the hint but not the
parameter that carries it, so `requester_hint` stays None until it does (#253). Nothing a client
sends can reach the page that way.
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime
from typing import Literal

from egzos._types import ASState
from egzos.authz import device, grant, metadata, screen
from egzos.authz.token_endpoint import Answer, authenticates, form_body

ErrorWord = Literal["invalid_request", "invalid_client", "invalid_scope"]


def _error(word: ErrorWord) -> Answer:
    return Answer(400, {"error": word})


def respond(
    state: ASState,
    params: Sequence[tuple[str, str]],
    *,
    content_type: str | None,
    authorization: str | None,
    key: bytes,
    issuer: str,
    now: datetime | None = None,
) -> Answer:
    """One device authorization request. `params`, `content_type` and `authorization` are as in
    `token_endpoint.respond`. `key` is the device-code key (#143's to provision) and `issuer` the
    container's origin, both supplied by the router. A naive `now` raises `ValueError` before
    anything is stored."""
    form = form_body(params, content_type)
    if form is None or authenticates(form, authorization):
        return _error("invalid_request")
    client_id = form.get("client_id")
    if client_id is None:
        return _error("invalid_request")
    entry = screen.client_entry(state, client_id)
    if entry is None or entry.client_type != "cli":
        return _error("invalid_client")
    try:
        response = device.authorize(
            state,
            key=key,
            client_id=entry.client_id,
            scope=form.get("scope"),
            requester_hint=None,
            verification_uri=issuer.rstrip("/") + metadata.DEVICE_ENTRY_PATH,
            now=now,
        )
    except grant.ScopeVocabularyError:
        return _error("invalid_scope")
    return Answer(200, dict(response))
