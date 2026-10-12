# Copyright 2026 Ali Sasanian
# SPDX-License-Identifier: LicenseRef-PolyForm-Strict-1.0.0
"""
Issuance and rotation (authorization-server.md §9.2, §9.3 rows 1, 2 and 5), against `ASState`.

- `mint`: a decided `ASGrant` becomes a `Token` (`capabilities.md` §5) and the first refresh token
  of its family, and appends `token.mint` carrying the family id (§9.3 row 1, [0.3 · 30]).
- `exchange_code`: the token endpoint's `authorization_code` grant, `codes.redeem` then `mint`.
  The `device_code` grant's twin (`device.poll` then `mint`) is the next slice's.
- `refresh`: the `refresh_token` grant. Single-use: the presented value is spent by the store
  before anything is judged. Reuse revokes the whole family and appends one `token.revoke` per
  revoked `Token` (§9.2 rotation clause 2). A successful rotation appends only the new
  `token.mint` (row 5). The new token carries the stored grant unchanged, so rotation can neither
  widen it nor upgrade its principal (clause 3), and the owner is the first token's.

Every refusal is `None`, alike; which check failed never leaves this module. An access token
always expires: `AS_ACCESS_TOKEN_LIFETIME_SECONDS` after issue, or at the grant's own expiry if
that is sooner, never null ([0.3 · 17]). The access token's value is `egzos.auth`'s format, so it
resolves through `Auth.use` like any other token (`values` module docstring). No HTTP here; the
throttle and the response shape belong to the endpoint that calls these.
"""

from __future__ import annotations

import hmac
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any, Protocol

from egzos._ids import ulid
from egzos._types import (
    AS_ACCESS_TOKEN_LIFETIME_SECONDS,
    CAPABILITIES,
    TOKEN_PRINCIPALS,
    ASGrant,
    ASState,
    RefreshRecord,
)
from egzos.auth import new_secret
from egzos.authz import codes, values
from egzos.model import Token

_ISO = "%Y-%m-%dT%H:%M:%SZ"


class TokenState(ASState, Protocol):
    """`ASState` plus the two `ContainerState` token methods it leans on. storage.md §3.1 rule 4
    makes them one implementer on one substrate."""

    def put_token(self, token: Token) -> None: ...
    def get_token(self, token_id: str) -> Token | None: ...


class AuditLedger(Protocol):
    def append(
        self, event: str, *, actor: str, principal: str, subject: str | None = None, **details: Any
    ) -> dict[str, Any]: ...


@dataclass(frozen=True)
class Issued:
    """What the token endpoint hands the client. The two values exist nowhere else: the store
    holds only their digests and the chain only `token.id`."""

    access_token: str
    refresh_token: str
    expires_in: int
    token: Token
    family_id: str


def _aware(at: datetime) -> bool:
    return at.tzinfo is not None and at.utcoffset() is not None


def _iso(at: datetime) -> str:
    return at.astimezone(UTC).strftime(_ISO)


def _parse(text: object) -> datetime | None:
    try:
        return datetime.strptime(text, _ISO).replace(tzinfo=UTC)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return None


def _same(given: str | None, stored: str) -> bool:
    if not isinstance(given, str):
        return False
    return hmac.compare_digest(
        given.encode("utf-8", "surrogatepass"), stored.encode("utf-8", "surrogatepass")
    )


def _sound(decided: ASGrant) -> bool:
    # Defence in depth on what the store hands back: a grant naming a principal no token may
    # carry, or a capability outside the six, mints nothing (§7, §10.3).
    caps = decided.get("capabilities")
    return (
        decided.get("principal") in TOKEN_PRINCIPALS
        and isinstance(caps, list)
        and all(c in CAPABILITIES for c in caps)
        and isinstance(decided.get("scopes"), list)
        and all(isinstance(s, str) for s in decided["scopes"])
    )


def mint(
    state: TokenState,
    ledger: AuditLedger,
    *,
    grant: ASGrant,
    client_id: str,
    owner: str,
    family_id: str | None = None,
    now: datetime | None = None,
) -> Issued | None:
    """Issue an access token and a refresh token for a grant already decided, and append
    `token.mint`. `family_id` is None for a first issue (a new family) and the presented record's
    on a rotation. None, storing nothing, for an expired or unreadable grant or a naive clock."""
    at = now or datetime.now(UTC)
    until = _parse(grant.get("grant_expires_at"))
    if not _aware(at) or until is None or at >= until or not _sound(grant):
        return None
    expires = min(at + timedelta(seconds=AS_ACCESS_TOKEN_LIFETIME_SECONDS), until)
    token = Token(
        id=ulid(),
        principal=grant["principal"],
        owner=owner,
        client=client_id,
        capabilities=list(grant["capabilities"]),
        scopes=list(grant["scopes"]),
        created_at=_iso(at),
        expires_at=_iso(expires),
    )
    access = new_secret(token.id)
    token.secret_hash = values.digest(access)
    family = family_id or ulid()
    refresh_value = values.new_value()
    state.put_token(token)
    state.put_refresh(
        RefreshRecord(
            refresh_hash=values.digest(refresh_value),
            family_id=family,
            client_id=client_id,
            access_token_id=token.id,
            grant=ASGrant(
                capabilities=list(grant["capabilities"]),
                scopes=list(grant["scopes"]),
                principal=grant["principal"],
                grant_expires_at=grant["grant_expires_at"],
            ),
            redeemed_at=None,
            revoked=False,
        )
    )
    # The caller at the token endpoint is the client; the owner's act was the decision, which
    # `authz.grant` records where it happened (§9.3 rows 3, 4).
    ledger.append(
        "token.mint",
        actor=client_id,
        principal="client",
        subject=token.id,
        token_principal=token.principal,
        client=client_id,
        capabilities=token.capabilities,
        scopes=token.scopes,
        expires_at=token.expires_at,
        family_id=family,
    )
    return Issued(
        access_token=access,
        refresh_token=refresh_value,
        expires_in=int((expires - at).total_seconds()),
        token=token,
        family_id=family,
    )


def exchange_code(
    state: TokenState,
    ledger: AuditLedger,
    *,
    code: str | None,
    client_id: str | None,
    redirect_uri: str | None,
    code_verifier: str | None,
    owner: str,
    now: datetime | None = None,
) -> Issued | None:
    """The `authorization_code` grant: §2's checks in `codes.redeem`, then the mint."""
    at = now or datetime.now(UTC)
    record = codes.redeem(
        state,
        code=code,
        client_id=client_id,
        redirect_uri=redirect_uri,
        code_verifier=code_verifier,
        now=at,
    )
    if record is None:
        return None
    return mint(
        state, ledger, grant=record["grant"], client_id=record["client_id"], owner=owner, now=at
    )


def refresh(
    state: TokenState,
    ledger: AuditLedger,
    *,
    refresh_token: str | None,
    client_id: str | None,
    now: datetime | None = None,
) -> Issued | None:
    """The `refresh_token` grant (§9.2 rotation). None for an unknown, revoked, reused, expired or
    other client's refresh token, alike. The presented one is spent in every case where the store
    knew it, so a refusal is never a retry."""
    at = now or datetime.now(UTC)
    if not isinstance(refresh_token, str) or not refresh_token or not _aware(at):
        return None
    prior = state.redeem_refresh(values.digest(refresh_token))
    if prior is None or prior["revoked"]:
        return None  # a revoked family has written its `token.revoke`s already
    if prior["redeemed_at"] is not None:
        _revoke_family(state, ledger, prior)
        return None
    previous = state.get_token(prior["access_token_id"])  # whose owner the new token keeps
    if previous is None or not _same(client_id, prior["client_id"]):
        return None
    return mint(
        state,
        ledger,
        grant=prior["grant"],
        client_id=prior["client_id"],
        owner=previous.owner,
        family_id=prior["family_id"],
        now=at,
    )


def _revoke_family(state: TokenState, ledger: AuditLedger, prior: RefreshRecord) -> None:
    """Rotation clause 2: a race or a theft, and the AS cannot tell which, so the whole chain goes.
    The list `revoke_family` returns stays here (storage.md §3.1); only the chain sees it."""
    for token_id in state.revoke_family(prior["family_id"]):
        ledger.append(
            "token.revoke",
            actor=prior["client_id"],
            principal="client",
            subject=token_id,
            family_id=prior["family_id"],
        )
