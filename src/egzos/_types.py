# Copyright 2026 Ali Sasanian
# SPDX-License-Identifier: Apache-2.0
"""
Shared types — owned by a1p-planner.

The typed face of ``spec/contracts/``. Nothing here is invented: every name below is derived from
the running walking skeleton (``chief/walking-skeleton``) and carries the contract document it
belongs to. Shapes marked in the contracts as *decided, not running* are typed here too, so that
Phase 1 builds against the frozen surface rather than the skeleton's.

**Drafted, awaiting the Phase 0.3 freeze review** — A6 and the Chief declare the freeze, not a1p.

Covered so far (issue #26): ``context-item.md``, ``capabilities.md``, ``events.md``.
Storage protocols (#27), container and chain (#28) and the authorization-server surface (#29)
land in their own PRs; the consolidation pass is #30.
"""

from __future__ import annotations

from typing import Any, Literal, NotRequired, TypedDict, get_args

# The runtime tuples below are DERIVED from their Literal unions, never written out twice: a
# vocabulary that can drift from its own type is a vocabulary that will.

# --- capabilities, principals, tokens (spec/contracts/capabilities.md) ---------------------

Capability = Literal["fetch", "remember", "organize", "publish", "curate", "admin"]
#: The ladder order. Six is the ENTIRE vocabulary (v0.3 §5, DECIDED); `structure` is a per-node
#: scope-policy floor (F2), not a seventh capability.
CAPABILITIES: tuple[Capability, ...] = get_args(Capability)

Role = Literal["reader", "contributor", "operator", "curator", "admin"]
#: Expanded at mint time — the token carries capabilities, never the bundle name.
ROLE_BUNDLES: dict[Role, frozenset[Capability]] = {
    "reader": frozenset({"fetch"}),
    "contributor": frozenset({"fetch", "remember"}),
    "operator": frozenset({"fetch", "remember", "organize", "publish"}),
    "curator": frozenset({"fetch", "remember", "organize", "publish", "curate"}),
    "admin": frozenset(CAPABILITIES),
}

Principal = Literal["interactive", "client"]
PRINCIPALS: tuple[Principal, ...] = get_args(Principal)

#: Outside the capability vocabulary by construction: no token reaches these, `admin` included.
#: A client principal can only propose. Not configurable, at any deployment.
HUMAN_ONLY_ACTS: tuple[str, ...] = ("gate.confirm", "yes.consume", "approve.pending")


class Token(TypedDict):
    """`scopes` are node ids; coverage is computed down the path AT CHECK TIME. `["*"]` = owner."""

    id: str
    principal: Principal
    owner: str
    client: str
    capabilities: list[Capability]
    scopes: list[str]
    created_at: str
    last_used: str | None
    revoked: bool
    expires_at: str | None


# --- the item (spec/contracts/context-item.md) ---------------------------------------------

Kind = Literal["memory", "preference", "skill", "artifact", "integration", "alias", "rule"]
KINDS: tuple[Kind, ...] = get_args(Kind)

TrustStatus = Literal["unverified", "verified", "quarantined"]
TRUST_STATUSES: tuple[TrustStatus, ...] = get_args(TrustStatus)

#: Rules are served verified-only at EVERY scope, overriding the per-container serving policy.
VERIFIED_ONLY_KINDS: frozenset[Kind] = frozenset({"rule"})


class TextContent(TypedDict):
    body: str
    auto_title: str
    title_engine: str


class ArtifactContent(TypedDict):
    """`inline` is present ONLY when size <= blobs.inline_max_bytes AND mime matches text/*."""

    sha256: str
    mime: str
    size: int
    filename: str
    auto_title: str
    title_engine: str
    inline: NotRequired[str]


class Provenance(TypedDict):
    """All five keys present, null where unknown — never absent-vs-unset."""

    actor: str | None
    principal: Principal | None
    client: str | None
    derived_from: str | None
    imported_from: str | None
    approved_by: str | None


class Trust(TypedDict):
    """`promoted_at`/`manifest` accompany `verified`; `reason`/`at` accompany `quarantined`."""

    status: TrustStatus
    promoted_at: NotRequired[str]
    manifest: NotRequired[str]
    reason: NotRequired[str]
    at: NotRequired[str]


class Lifecycle(TypedDict):
    created_at: str
    updated_at: str
    version: int
    tombstoned: NotRequired[bool]


class ContextItem(TypedDict):
    """`scope` is a LOCATION, not an identity. Unknown fields survive round-trip (see below)."""

    id: str
    kind: Kind
    scope: str
    content: TextContent | ArtifactContent
    key: str | None
    tags: list[str]
    provenance: Provenance
    trust: Trust
    lifecycle: Lifecycle
    visibility: dict[str, Any]


#: Fields an implementation knows. Anything else on the wire MUST be preserved verbatim and written
#: back unchanged — the contract fixes the behaviour, not the carrier the skeleton calls `extra`.
CONTEXT_ITEM_FIELDS: tuple[str, ...] = (
    "id",
    "kind",
    "scope",
    "content",
    "key",
    "tags",
    "provenance",
    "trust",
    "lifecycle",
    "visibility",
)


class BlobGrant(TypedDict):
    """Minted by TRUST, never by Store/Vault (F5). Store renders it; it decides nothing.

    *Decided, not running.* `sig` is `[OPEN->0.3]`: HMAC over the descriptor with a container key,
    or the grant id as the bearer secret — A6's call on the enumeration surface.
    """

    sha256: str
    item: str
    token: str
    expires_at: str
    sig: str


# --- the audit chain (spec/contracts/events.md) ---------------------------------------------

Event = Literal[
    "container.init",
    "node.create",
    "item.add",
    "blob.put",
    "context.fetch",
    "blob.pull",
    "item.move",
    "gate.pass.silent",
    "gate.propose",
    "approval.promote",
    "approval.execute",
    "approval.deny",
    "trust.quarantine",
    "step_up",
    "token.mint",
    "token.revoke",
    "item.tombstone",
    "blob.grant",
]
#: An append whose event name is not here MUST be rejected. `step_up` is reserved (Phase 2.2);
#: `blob.grant` is decided, not running (F5).
EVENTS: tuple[Event, ...] = get_args(Event)

#: Genesis `prev_hash`: 64 ASCII zeros.
GENESIS_HASH: str = "0" * 64


class AuditEntry(TypedDict):
    """hash = sha256(prev_hash || canonical(entry minus `hash` and `seq`)).

    `canonical` is contract, not implementation: sorted keys, no whitespace, non-ASCII preserved.
    Never put a token value, a grant signature or blob bytes in `details`.
    """

    seq: int
    ts: str
    event: Event
    actor: str
    principal: Principal
    subject: str | None
    scope: str | None
    details: dict[str, Any]
    prev_hash: str
    hash: str


__all__ = [
    "ArtifactContent",
    "AuditEntry",
    "BlobGrant",
    "CAPABILITIES",
    "CONTEXT_ITEM_FIELDS",
    "Capability",
    "ContextItem",
    "EVENTS",
    "Event",
    "GENESIS_HASH",
    "HUMAN_ONLY_ACTS",
    "KINDS",
    "Kind",
    "Lifecycle",
    "PRINCIPALS",
    "Principal",
    "Provenance",
    "ROLE_BUNDLES",
    "Role",
    "TRUST_STATUSES",
    "TextContent",
    "Token",
    "Trust",
    "TrustStatus",
    "VERIFIED_ONLY_KINDS",
]
