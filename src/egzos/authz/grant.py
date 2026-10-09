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
"""

from __future__ import annotations

from dataclasses import dataclass

from egzos._types import (
    AS_GRANT_LIFETIME_DEFAULT_SECONDS,
    AS_GRANT_LIFETIME_MAX_SECONDS,
    AS_SCOPE_ALL_NODES,
    AS_SCOPE_NODE_PREFIX,
    CAPABILITIES,
)

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
            if not node:
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
