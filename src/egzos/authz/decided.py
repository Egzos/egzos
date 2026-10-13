# Copyright 2026 Ali Sasanian
# SPDX-License-Identifier: LicenseRef-PolyForm-Strict-1.0.0
"""
An authorization request reaches a decision exactly once (authorization-server.md §11.4), against
`ASState`'s decided-request methods (storage.md §3.1 rule 5).

§2 makes the *code* single-use. This makes the *request* single-use, which is the object the back
button re-submits. A request is identified by the tuple it carries, `(client_id, redirect_uri,
state, code_challenge)`, as `request_key` digests it. When the owner decides it, granted or
denied, `record` binds the decision to the deciding session.

Two reads recognise a re-submission, one per position in the order of evaluation:

- `first_replay` is §11.0 substep 1, ahead of the throttle counter. It is keyed on the
  interactive session, never on anything the request carries, and matches once per decided
  request: `claim_resubmission` is `True` exactly once per recorded `(session, request)`. A caller
  with no session matches nothing.
- `replayed` is the request-keyed read at the pre-trust tier, after the counter, which §12 counts
  as its fourth read of container state. It catches every other re-submission: another session,
  or a second one on the deciding session.

A match at either is §5.3's uniform failure and appends row (d), `authz.refuse` with cause
`replayed`, `principal: none` and `actor: authorize` (§12.2). The caller renders the page and
mints nothing. A miss appends nothing here: the request goes on to the entry its own path owes.
Every `bool` in this module stays inside Trust (storage.md §5).
"""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime

from egzos._types import AS_GRANT_DECISIONS, ASState, DecidedRequestRecord, GrantDecision
from egzos.authz import AuditLedger

_ISO = "%Y-%m-%dT%H:%M:%SZ"
# Namespaces the digest, so a request key never equals a credential digest from `values.digest`.
_DOMAIN = "egzos.authz.request.v1"


def _aware(at: datetime) -> bool:
    return at.tzinfo is not None and at.utcoffset() is not None


def request_key(
    *, client_id: str, redirect_uri: str, state: str | None, code_challenge: str
) -> str:
    """§11.4's request identity: the lowercase hex sha256 of the four values, encoded so that no
    two distinct tuples share an encoding. A missing `state` and an empty one are different
    requests. The requester hint never enters it (storage.md §3.1 rule 2).

    Call it on values `/authorize` has already admitted (a registered client, a matched redirect,
    a well-formed S256 challenge). A non-string argument is a caller's bug and raises `TypeError`."""
    for value in (client_id, redirect_uri, code_challenge):
        if not isinstance(value, str):
            raise TypeError("request_key takes strings")
    if state is not None and not isinstance(state, str):
        raise TypeError("request_key takes a string state or None")
    # `ensure_ascii` escapes a lone surrogate rather than raising on it.
    encoded = json.dumps([_DOMAIN, client_id, redirect_uri, state, code_challenge])
    return hashlib.sha256(encoded.encode("ascii")).hexdigest()


def record(
    state: ASState,
    *,
    key: str,
    session_hash: str,
    decision: GrantDecision,
    now: datetime | None = None,
) -> None:
    """Record the owner's decision on a request, bound to the session that made it.

    Call it with the decision and before the mint, so no code exists for a request that a
    re-submission could still reach a second decision on. The decision's own event,
    `authz.grant`, is the caller's (§9.3). A naive `now`, an empty key or session, or a decision
    outside `AS_GRANT_DECISIONS` is a caller's bug and raises `ValueError`; nothing is stored."""
    at = now or datetime.now(UTC)
    if not _aware(at):
        raise ValueError("decided.record needs an aware datetime")
    if decision not in AS_GRANT_DECISIONS:
        raise ValueError("decided.record takes a closed decision")
    if not isinstance(key, str) or not key or not isinstance(session_hash, str) or not session_hash:
        raise ValueError("decided.record needs a request key and a session")
    state.put_decided(
        DecidedRequestRecord(
            request_key=key,
            session_hash=session_hash,
            decision=decision,
            decided_at=at.astimezone(UTC).strftime(_ISO),
            resubmission_seen=False,
        )
    )


def _refuse(ledger: AuditLedger) -> None:
    # Row (d). No `client_id`, no session, no key: (d) is uniform and names no client (§12).
    ledger.append("authz.refuse", actor="authorize", principal="none", cause="replayed")


def first_replay(state: ASState, ledger: AuditLedger, *, session_hash: str | None, key: str) -> bool:
    """§11.0 substep 1, and §12.1 rule 6's one unthrottled path: is this the deciding session's
    first re-submission of this request? Run it before the throttle counter, at `/authorize` only.

    `True` appends row (d) `replayed`; the caller answers with §5.3's page whatever the counter
    holds, and does not touch the counter. `False` appends nothing, and the request goes on to
    substep 2. A caller with no session, or a session the request was not decided on, is
    `False`, and so is a second re-submission on the deciding session."""
    if not isinstance(session_hash, str) or not session_hash or not isinstance(key, str) or not key:
        return False
    if not state.claim_resubmission(session_hash, key):
        return False
    _refuse(ledger)
    return True


def replayed(state: ASState, ledger: AuditLedger, *, key: str) -> bool:
    """§11.4's request-keyed read, at the pre-trust tier after the counter, so a caller varying
    the key is still throttled. Only a request inside a live session reaches it (§11.0 substep 3).

    `True` when any session decided this request: it appends row (d) `replayed`, and the caller
    answers with §5.3's page and never reaches a decision or a mint. `False` appends nothing."""
    if not isinstance(key, str) or not key or state.get_decided(key) is None:
        return False
    _refuse(ledger)
    return True
