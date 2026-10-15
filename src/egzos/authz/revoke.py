# Copyright 2026 Ali Sasanian
# SPDX-License-Identifier: LicenseRef-PolyForm-Strict-1.0.0
"""
Revocation's two paths and one result (authorization-server.md §9.2, §11.9; capabilities.md §5).

- `by_id`: §11.9's owner path. The owner, inside an interactive session, revokes a token in
  `token ls` by its `Token.id`. An id that names no token and one the session may not reach get
  the same answer, `False`, and each appends `authz.revoke_refuse` once with its closed cause
  (`unknown`, `unreachable`) and `principal: interactive`. The cause is the owner's ledger's and
  never the page's (§7.1 applied to an identifier).
- `by_value`: §9.2 clause 1's RFC 7009 endpoint. It returns nothing at all, so the endpoint
  answers one 200 for an unknown, malformed, already-revoked or other client's token and for a
  token it really revoked. A token whose `client` differs from the presented `client_id` is left
  alone. That comparison is defence in depth and **not a boundary**: no client authenticates, so
  this path is bounded by the entropy of the value alone (§9.1).

Either path marks the named `Token` revoked and appends one `token.revoke` carrying the
refresh-family id where the token has one ([0.3 · 30]). An already-revoked token is not revoked
twice and gets no second `token.revoke`. That is §9.2's rule, which `Auth.revoke` (`token rm`)
keeps too; its event still carries no family id, as `Backend` has no family read (#242).

Not built here, pending #240: whether revoking an access token takes its refresh family with it
(storage.md §3.1 rule 4 leaves it open), a refresh-token value at the endpoint (`ASState` has no
read that does not spend it, so such a value revokes nothing yet), and the `throttled` cause, which
is §11.0's throttle (#208). The response, its time budget included, belongs to the endpoint.
"""

from __future__ import annotations

from egzos._types import RevokeRefusalCause
from egzos.auth import token_id_of
from egzos.authz import AuditLedger, values
from egzos.authz.tokens import TokenState
from egzos.model import Token


def _revoke(
    state: TokenState, ledger: AuditLedger, token: Token, *, actor: str, principal: str
) -> None:
    family = state.family_of_token(token.id)  # read first: a revoked family reads as None
    token.revoked = True
    state.put_token(token)
    details = {"family_id": family} if family is not None else {}
    ledger.append("token.revoke", actor=actor, principal=principal, subject=token.id, **details)


def _refuse(ledger: AuditLedger, actor: str, cause: RevokeRefusalCause) -> bool:
    ledger.append(
        "authz.revoke_refuse", actor=actor, principal="interactive", outcome="refused", cause=cause
    )
    return False


def by_id(state: TokenState, ledger: AuditLedger, *, token_id: str | None, viewer: str) -> bool:
    """§11.9 for one revoke on the owner's page. `viewer` is the session owner's identity, which
    the endpoint supplies and never reads from the request; an empty one is a caller's bug and
    raises `ValueError` before anything is read or appended. `True` when the token is revoked,
    whether by this call or before it. The refused id itself never enters the chain."""
    if not isinstance(viewer, str) or not viewer:
        raise ValueError("revoke.by_id needs the session owner as viewer")
    token = state.get_token(token_id) if isinstance(token_id, str) and token_id else None
    if token is None:
        return _refuse(ledger, viewer, "unknown")
    if token.owner != viewer:
        return _refuse(ledger, viewer, "unreachable")
    if not token.revoked:
        _revoke(state, ledger, token, actor=viewer, principal="interactive")
    return True


def by_value(
    state: TokenState,
    ledger: AuditLedger,
    *,
    token: str | None,
    client_id: str | None,
) -> None:
    """§9.2 clause 1 for one RFC 7009 request. `token_type_hint` is not taken: a hint only orders
    the lookup, and this AS finds an access token by the id its value carries. Nothing is returned,
    so no outcome can reach the response."""
    if not isinstance(token, str) or not isinstance(client_id, str) or not client_id:
        return
    token_id = token_id_of(token)
    held = state.get_token(token_id) if token_id else None
    if held is None or held.revoked or not held.secret_hash:
        return
    if not values.same(values.digest(token), held.secret_hash):
        return
    if not values.same(client_id, held.client):
        return
    _revoke(state, ledger, held, actor=client_id, principal="client")
