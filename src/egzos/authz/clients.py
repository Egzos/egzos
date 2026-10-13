# Copyright 2026 Ali Sasanian
# SPDX-License-Identifier: LicenseRef-PolyForm-Strict-1.0.0
"""
Client registration (authorization-server.md §5, §9.3 row 6), against `ASState`.

Registering, amending and removing a client are owner acts, and each appends `client.register
{client_id, op, redirect_uris}` with the allowlist as it stands after the change, empty on
`remove` ([0.3 · 31], `events.md` §1). There is no open registration ([0.3 · 10]): these functions
are the only writers of a client entry, and each refuses any caller but the owner's interactive,
`admin`, whole-container token, the gate `token create` holds. The CLI verb that calls them is
a3-doorman's; the consent screen never does (§5 clause 1).

A refusal here is raised as `ClientRefused` with readable text, because the only caller who gets
this far is the owner at a terminal, who must learn why an entry was refused when they can act on
it (§5.2 clause 1). `client_name` is owner-supplied data: stored and echoed, never branched on.
`client_type` is fixed at `add`; changing a client's kind is a `remove` and a new `add`, so no
amendment moves an existing `client_id` onto the browser flow that mints `interactive` (§10.3).
"""

from __future__ import annotations

from datetime import UTC, datetime

from egzos._ids import ulid
from egzos._types import AS_CLIENT_TYPES, ASState, ClientRegisterOp, ClientRegistration
from egzos.authz import AuditLedger
from egzos.authz.redirects import RedirectURIRefused, check_registrable
from egzos.model import Token

_ISO = "%Y-%m-%dT%H:%M:%SZ"


class ClientRefused(ValueError):
    """A registration act the owner must correct, or a caller who is not the owner."""


def _owner(token: Token) -> None:
    if not isinstance(token, Token) or token.principal != "interactive" or not token.has("admin"):
        raise ClientRefused("registering a client is the owner's act")
    if "*" not in token.scopes:
        raise ClientRefused("registering a client is the owner's act")


def _name(client_name: object) -> str:
    if not isinstance(client_name, str) or not client_name.strip():
        raise ClientRefused("a client needs a name")
    return client_name


def _uris(redirect_uris: object) -> list[str]:
    if not isinstance(redirect_uris, list):
        raise ClientRefused("redirect URIs are a list")
    admitted: list[str] = []
    for uri in redirect_uris:
        try:
            checked = check_registrable(uri)
        except RedirectURIRefused as exc:
            raise ClientRefused(str(exc)) from exc
        if checked not in admitted:
            admitted.append(checked)
    return admitted


def _record(
    ledger: AuditLedger,
    token: Token,
    actor: str,
    client_id: str,
    op: ClientRegisterOp,
    uris: list[str],
) -> None:
    ledger.append(
        "client.register",
        actor=actor,
        principal=token.principal,
        subject=client_id,
        client_id=client_id,
        op=op,
        redirect_uris=list(uris),
    )


def register(
    state: ASState,
    ledger: AuditLedger,
    *,
    token: Token,
    actor: str,
    client_name: str,
    client_type: str,
    redirect_uris: list[str],
    now: datetime | None = None,
) -> ClientRegistration:
    """Add a client entry (`op: add`). The `client_id` is minted here, never chosen by a caller,
    so no registration can take over an existing entry's id."""
    _owner(token)
    if client_type not in AS_CLIENT_TYPES:
        raise ClientRefused("a client is browser, cli or mcp")
    entry = ClientRegistration(
        client_id=ulid(),
        client_name=_name(client_name),
        client_type=client_type,  # type: ignore[typeddict-item]
        redirect_uris=_uris(redirect_uris),
        registered_at=(now or datetime.now(UTC)).astimezone(UTC).strftime(_ISO),
    )
    state.put_client(entry)
    _record(ledger, token, actor, entry["client_id"], "add", entry["redirect_uris"])
    return entry


def amend(
    state: ASState,
    ledger: AuditLedger,
    *,
    token: Token,
    actor: str,
    client_id: str,
    client_name: str | None = None,
    redirect_uris: list[str] | None = None,
) -> ClientRegistration:
    """Change an entry's name or allowlist (`op: amend`). `client_type` and `registered_at` keep
    their values. An amendment that changes nothing still appends: the act happened."""
    _owner(token)
    entry = state.get_client(client_id) if isinstance(client_id, str) else None
    if entry is None:
        raise ClientRefused("no such client")
    if client_name is not None:
        entry["client_name"] = _name(client_name)
    if redirect_uris is not None:
        entry["redirect_uris"] = _uris(redirect_uris)
    state.put_client(entry)
    _record(ledger, token, actor, client_id, "amend", entry["redirect_uris"])
    return entry


def remove(
    state: ASState, ledger: AuditLedger, *, token: Token, actor: str, client_id: str
) -> None:
    """Remove an entry (`op: remove`, `redirect_uris` empty). Tokens already issued to it are not
    revoked here: that is `token rm`, one `token.revoke` each (§9.2)."""
    _owner(token)
    if not isinstance(client_id, str) or not state.remove_client(client_id):
        raise ClientRefused("no such client")
    _record(ledger, token, actor, client_id, "remove", [])
