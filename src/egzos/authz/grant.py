# Copyright 2026 Ali Sasanian
# SPDX-License-Identifier: LicenseRef-PolyForm-Strict-1.0.0
"""
The grant an AS token carries (authorization-server.md §7, §11.5): six capabilities and node ids,
nothing else.

A `scope` value is a space-delimited set drawn from exactly two forms — a bare name from
`CAPABILITIES`, or `node:<id>` (`node:*` the whole container). Anything else refuses the whole
value: a request is never silently narrowed to the part that parsed (§7, §11.2 consequence 2).
Role bundle names are not scope strings, and `admin` is the capability, never the bundle.

The refusal is `invalid_scope` and row (f) cause `vocabulary` (§7.1): a fact about this document's
vocabulary, identical for every container. Whether a parsed node id exists or is reachable is NOT
decided here — that answer is `access_denied` for both, decided where the viewer's coverage is.

`offer` is §11.2's one value for the browser flow: the expansion, the clamped lifetime and the
principal §10.3 fixes, rendered by the screen and minted unchanged.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from egzos._types import (
    AS_CLIENT_TYPES,
    AS_GRANT_LIFETIME_DEFAULT_SECONDS,
    AS_GRANT_LIFETIME_MAX_SECONDS,
    AS_SCOPE_ALL_NODES,
    AS_SCOPE_NODE_PREFIX,
    CAPABILITIES,
    TOKEN_PRINCIPALS,
    ASClientType,
    ASGrant,
    TokenPrincipal,
)

_ISO = "%Y-%m-%dT%H:%M:%SZ"

# A bound on what is parsed at all. A node id is otherwise opaque here — one or more printable,
# non-space characters — and whether it exists is not this module's question (§7.1).
_MAX_SCOPE_BYTES = 4096


class ScopeVocabularyError(ValueError):
    """The `scope` value is malformed or names a word outside §7's two forms (§7.1, `vocabulary`).

    Deliberately carries no detail: the cause is one closed word, and the redirect carries no
    `error_description` (§11.6), so there is nothing a message could be used for."""

    def __init__(self) -> None:
        super().__init__("invalid_scope")


@dataclass(frozen=True)
class Grant:
    """The expansion of a `scope` value: what the screen renders and the mint produces (§11.2)."""

    capabilities: tuple[str, ...]
    scopes: tuple[str, ...]


def parse_scope(value: str | None) -> Grant:
    """Expand a `scope` value into `{capabilities, scopes}`, or refuse it whole.

    An absent or empty value is malformed: §7 defines no default grant, so there is nothing to
    expand it into. Duplicates collapse; nothing else about the request changes."""
    if not isinstance(value, str) or not value or len(value.encode()) > _MAX_SCOPE_BYTES:
        raise ScopeVocabularyError()
    # RFC 6749 §3.3: scope-tokens are separated by single spaces. Any other whitespace, or an
    # empty token from a doubled or edge space, is malformed rather than tolerated.
    words = value.split(" ")
    capabilities: list[str] = []
    scopes: list[str] = []
    for word in words:
        if not word or not word.isprintable() or any(c.isspace() for c in word):
            raise ScopeVocabularyError()
        if word in CAPABILITIES:
            if word not in capabilities:
                capabilities.append(word)
        elif word.startswith(AS_SCOPE_NODE_PREFIX):
            # The prefix does not survive the mint: `node:*` lands as `["*"]` (§7 consequence 3).
            node = "*" if word == AS_SCOPE_ALL_NODES else word[len(AS_SCOPE_NODE_PREFIX) :]
            # `node:node:x` is the one form refused here: its id would reach the token still
            # prefixed, which the mint cannot round-trip (§7 consequence 3). Ids stay opaque
            # otherwise (§7.1), and an `Offer` never has to refuse the prefixed form.
            if not node or node.startswith(AS_SCOPE_NODE_PREFIX):
                raise ScopeVocabularyError()
            if node not in scopes:
                scopes.append(node)
        else:
            # A role bundle (`reader`, `operator`, …), a principal in any spelling (§10.3
            # consequence 1), or any other word: not one of the two forms.
            raise ScopeVocabularyError()
    order = {c: i for i, c in enumerate(CAPABILITIES)}
    return Grant(tuple(sorted(capabilities, key=order.__getitem__)), tuple(scopes))


def clamp_grant_lifetime(requested_seconds: int | None) -> int:
    """§11.5: the grant's lifetime in seconds — the default when none is asked for, clamped to the
    maximum when more is, never refused for length and never non-expiring ([0.3 · 18]).

    Both numbers are contract values with no config key (#142 holds the question)."""
    if requested_seconds is None:
        return AS_GRANT_LIFETIME_DEFAULT_SECONDS
    if (
        isinstance(requested_seconds, bool)
        or not isinstance(requested_seconds, int)
        or requested_seconds <= 0
    ):
        # Not a lifetime at all: malformed, which is the caller's to answer, never clamped into one.
        raise ValueError("grant lifetime is a positive integer number of seconds")
    return min(requested_seconds, AS_GRANT_LIFETIME_MAX_SECONDS)


def _bare_node_id(value: object) -> bool:
    """A scope entry as the token holds it: `*` or an id, never the request's `node:` form."""
    return (
        isinstance(value, str)
        and bool(value)
        and value.isprintable()
        and not any(c.isspace() for c in value)
        and not value.startswith(AS_SCOPE_NODE_PREFIX)
    )


@dataclass(frozen=True)
class Offer:
    """§11.2: what the consent screen renders and what the mint produces, as one value.

    The page renders these fields and the decision passes `decided` to the code issue. Nothing is
    added between the two, because there is nowhere to add it (§11.2 consequence 1). The lifetime
    is held already clamped (§11.5), and the instant is fixed only at the decision."""

    capabilities: tuple[str, ...]
    scopes: tuple[str, ...]
    principal: TokenPrincipal
    lifetime_seconds: int

    def __post_init__(self) -> None:
        # Built directly rather than through `offer`, it still holds only what §7, §10.3 and
        # §11.5 allow: a lifetime past the maximum is not clamped here but refused, as a misuse.
        # Both fields are tuples, so nothing mutates them between render and `decided` (§11.2
        # consequence 1); ids are bare (§7 consequence 3); and neither field repeats an entry.
        # Membership is tested only on strings, so an unhashable entry is refused, never raised on.
        caps, scopes = self.capabilities, self.scopes
        if (
            not isinstance(caps, tuple)
            or not isinstance(scopes, tuple)
            or not all(isinstance(c, str) and c in CAPABILITIES for c in caps)
            or len(set(caps)) != len(caps)
            or not all(_bare_node_id(s) for s in scopes)
            or len(set(scopes)) != len(scopes)
            or not isinstance(self.principal, str)
            or self.principal not in TOKEN_PRINCIPALS
            or isinstance(self.lifetime_seconds, bool)
            or not isinstance(self.lifetime_seconds, int)
            or not 0 < self.lifetime_seconds <= AS_GRANT_LIFETIME_MAX_SECONDS
        ):
            raise ValueError("an offer holds §7's grant, a principal and a clamped lifetime")

    def decided(self, at: datetime) -> ASGrant | None:
        """The `ASGrant` for a decision taken at `at`. None for a naive clock, which has no instant
        to count the grant's expiry from."""
        if at.tzinfo is None or at.utcoffset() is None:
            return None
        until = at + timedelta(seconds=self.lifetime_seconds)
        return ASGrant(
            capabilities=list(self.capabilities),  # type: ignore[arg-type]
            scopes=list(self.scopes),
            principal=self.principal,
            grant_expires_at=until.astimezone(UTC).strftime(_ISO),
        )


def offer(scope: str | None, *, client_type: ASClientType, lifetime_seconds: int | None) -> Offer:
    """§11.2 for an `/authorize` request: `scope` expanded by §7 and the lifetime clamped by §11.5.

    The principal comes from the client's registered type, never from the request (§10.3
    consequence 1). `interactive` is minted only for a `browser` client, since only there are the
    owner and the software on one surface. Any other type gets `client`. Whether a non-browser
    client may use `/authorize` at all is the endpoint's to decide, not this function's.

    Raises `ScopeVocabularyError` for §7.1's `vocabulary` cause and `ValueError` for a lifetime
    or `client_type` that is malformed."""
    if not isinstance(client_type, str) or client_type not in AS_CLIENT_TYPES:
        raise ValueError("client_type is one of AS_CLIENT_TYPES")
    grant = parse_scope(scope)
    lifetime = clamp_grant_lifetime(lifetime_seconds)
    principal: TokenPrincipal = "interactive" if client_type == "browser" else "client"
    return Offer(grant.capabilities, grant.scopes, principal, lifetime)
