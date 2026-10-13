# Copyright 2026 Ali Sasanian
# SPDX-License-Identifier: LicenseRef-PolyForm-Strict-1.0.0
"""
The two reads the consent screen makes of container state (authorization-server.md §11.1, §11.3).

- `client_entry`: §11.1's client-registry read. One entry, keyed by the request's `client_id`, and
  never a listing. It carries exactly `AS_CLIENT_REGISTRY_READ_FIELDS`, and the kind word the page
  renders comes from `CONSENT_KIND_FROM_CLIENT_TYPE` and is never re-derived from the literal. An
  unregistered `client_id` is `None`, the same `None` as an unreadable entry. The caller answers it
  with §5.3's uniform failure, whose time budget is owed at the response and not here.
- `existing_tokens`: §11.3's read for the pair (viewer, client). It returns a count of live tokens
  and the most recent `created_at`. Live is `Token.live`, `capabilities.md` §5's own fields. Only
  tokens the viewer owns are counted, and no `Token.id`, token value or other client's total
  leaves it.

`client_name` is owner-supplied data (§11.1): nothing here branches on it. Neither read appends:
the page's own entry is §12 row (g)'s, written where the page is rendered.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Protocol

from egzos._types import (
    CONSENT_KIND_FROM_CLIENT_TYPE,
    ASClientType,
    ASState,
    ConsentKind,
)
from egzos.model import Token

_ISO = "%Y-%m-%dT%H:%M:%SZ"


class TokenListing(Protocol):
    """`ContainerState`'s token listing, the one method §11.3's read leans on."""

    def list_tokens(self) -> list[Token]: ...


@dataclass(frozen=True)
class ClientEntry:
    """§11.1's one entry. Its fields are `AS_CLIENT_REGISTRY_READ_FIELDS`, no more and no fewer."""

    client_id: str
    client_name: str
    client_type: ASClientType
    redirect_uris: tuple[str, ...]
    registered_at: str

    @property
    def kind(self) -> ConsentKind:
        """The kind word the page renders: `cli` is `device` (§11.1's table), never `cli`."""
        return CONSENT_KIND_FROM_CLIENT_TYPE[self.client_type]


@dataclass(frozen=True)
class ExistingTokens:
    """§11.3: a count and a timestamp, nothing that names a token."""

    live: int
    latest_created_at: str | None


def client_entry(state: ASState, client_id: str | None) -> ClientEntry | None:
    """§11.1: the entry for `client_id`, or `None` for one not registered. An entry the store
    hands back malformed is `None` too, so the page never renders a field it cannot vouch for."""
    if not isinstance(client_id, str) or not client_id:
        return None
    entry = state.get_client(client_id)
    if not isinstance(entry, dict):
        return None
    kind = entry.get("client_type")
    name = entry.get("client_name")
    uris = entry.get("redirect_uris")
    registered = entry.get("registered_at")
    if (
        entry.get("client_id") != client_id
        or kind not in CONSENT_KIND_FROM_CLIENT_TYPE
        or not isinstance(name, str)
        or not isinstance(uris, list)
        or not all(isinstance(u, str) for u in uris)
        or not isinstance(registered, str)
    ):
        return None
    return ClientEntry(
        client_id=client_id,
        client_name=name,
        client_type=kind,
        redirect_uris=tuple(uris),
        registered_at=registered,
    )


def _created(token: Token) -> datetime | None:
    try:
        return datetime.strptime(token.created_at, _ISO).replace(tzinfo=UTC)
    except (TypeError, ValueError):
        return None


def existing_tokens(state: TokenListing, *, viewer: str, client_id: str) -> ExistingTokens:
    """§11.3 for the pair (viewer, client). `viewer` is the session owner's identity, which the
    endpoint supplies and never reads from the request. A token whose `created_at` cannot be read
    is still counted when live, and never offered as the most recent."""
    if not isinstance(viewer, str) or not viewer or not isinstance(client_id, str) or not client_id:
        return ExistingTokens(live=0, latest_created_at=None)
    tokens: Iterable[Token] = state.list_tokens()
    count = 0
    latest: tuple[datetime, str] | None = None
    for token in tokens:
        if token.owner != viewer or token.client != client_id or not token.live:
            continue
        count += 1
        at = _created(token)
        if at is not None and (latest is None or at > latest[0]):
            latest = (at, token.created_at)
    return ExistingTokens(live=count, latest_created_at=latest[1] if latest else None)
