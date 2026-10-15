# Copyright 2026 Ali Sasanian
# SPDX-License-Identifier: LicenseRef-PolyForm-Strict-1.0.0
"""
`/authorize`'s post-trust tier (authorization-server.md §7, §7.1, §11.2), for a request
`pretrust.admit` let through.

`judge` expands the request's `scope` by §7 and asks the endpoint whether the viewer reaches each
node it names. Then exactly one of three things happens:

- `vocabulary`: the `scope` value is malformed or names a word outside §7's two forms. Row (f)
  `authz.reject` is appended, and the error is `invalid_scope`. It is a fact about this
  document's vocabulary, identical for every container.
- `scope`: a node the viewer does not reach, or one that does not exist. Row (f) is appended,
  and the error is `access_denied`. Both cases get one answer, with the same append and the same
  error, so the tier is no enumeration oracle (§7.1). The owner declining at the screen gives the
  same `access_denied`, but that is `authz.grant`'s to record (§9.3), not this tier's.
- render: row (g) `authz.render` is appended with the client's id, and the `Offer` is returned.
  The screen renders it, and the decision mints `Offer.decided(at)` unchanged (§11.2).

Rows (f) and (g) are reached only inside a session, so they carry `principal: interactive` (§12.2).
`actor` is the session owner's identity, which the endpoint supplies and never reads from the
request. Neither row carries the `scope` value, the `state` or the challenge (§12.1 rule 7).

The error redirect itself is not built here. How §11.6's `{error, state}` combines with a
registered `redirect_uri` that carries a query is #234's question. §7.1's time budget, like §5.3
clause 2's, is owed at the response.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Literal

from egzos._types import AuthorizePosttrustCause
from egzos.authz import AuditLedger, grant, pretrust

#: §7.1's two error words, one per row (f) cause.
ERROR: dict[AuthorizePosttrustCause, Literal["invalid_scope", "access_denied"]] = {
    "vocabulary": "invalid_scope",
    "scope": "access_denied",
}


@dataclass(frozen=True)
class Rejected:
    """A post-trust rejection. `error` is the redirect's one error word (§11.6). The cause stays
    in the ledger and never reaches the response."""

    error: Literal["invalid_scope", "access_denied"]


def _reject(ledger: AuditLedger, actor: str, cause: AuthorizePosttrustCause) -> Rejected:
    ledger.append(
        "authz.reject", actor=actor, principal="interactive", outcome="rejected", cause=cause
    )
    return Rejected(ERROR[cause])


def _reached(reaches: Callable[[str], bool], node: str) -> bool:
    # Only `True` reaches. A lookup that raises `LookupError` on an unknown id is one more way of
    # saying the node is not there, and it gets the same answer as an unreachable one (§7.1).
    # Anything else (an outage, a bug) surfaces with nothing appended: the owner's ledger must not
    # record an infrastructure failure as row (f) `cause: scope` (§12.1 rule 1).
    try:
        return reaches(node) is True
    except LookupError:
        return False


def judge(
    admitted: pretrust.Admitted,
    ledger: AuditLedger,
    *,
    actor: str,
    reaches: Callable[[str], bool],
) -> grant.Offer | Rejected:
    """§7's tier for one admitted `/authorize` request: the `Offer` to render, or a rejection.

    `reaches(node_id)` is the endpoint's answer to whether the viewer covers that node, with `*`
    meaning the whole container. It returns `False` for an id that does not exist, and is called
    once for every node in the request, even after one has failed. The grant's lifetime is §11.5's
    default: §2's request has no lifetime parameter to clamp. An empty `actor` is a caller's bug
    and raises `ValueError`, and nothing is appended."""
    if not isinstance(actor, str) or not actor:
        raise ValueError("posttrust.judge needs the session owner as actor")
    try:
        offer = grant.offer(
            admitted.scope, client_type=admitted.client.client_type, lifetime_seconds=None
        )
    except grant.ScopeVocabularyError:
        return _reject(ledger, actor, "vocabulary")
    # Every node is asked, so the number of reads does not depend on which node failed.
    reached = [_reached(reaches, node) for node in offer.scopes]
    if not all(reached):
        return _reject(ledger, actor, "scope")
    ledger.append(
        "authz.render",
        actor=actor,
        principal="interactive",
        outcome="rendered",
        client_id=admitted.client.client_id,
    )
    return offer
