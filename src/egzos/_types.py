# Copyright 2026 Ali Sasanian
# SPDX-License-Identifier: Apache-2.0
"""
Shared types — owned by a1p-planner.

The typed face of ``spec/contracts/``. Nothing here is invented: every name below is derived from
the running walking skeleton (``chief/walking-skeleton``) and carries the contract document it
belongs to. Shapes marked in the contracts as *decided, not running* are typed here too, so that
Phase 1 builds against the frozen surface rather than the skeleton's.

**Drafted, awaiting the Phase 0.3 freeze review** — A6 and the Chief declare the freeze, not a1p.

Covered so far: ``context-item.md``, ``capabilities.md``, ``events.md`` (issue #26),
``storage.md`` (issue #27) and ``container.md`` (issue #28). The authorization-server surface (#29)
lands in its own PR; the consolidation pass is #30.
"""

from __future__ import annotations

from collections.abc import Iterable, Iterator
from typing import Any, Literal, NotRequired, Protocol, TypedDict, get_args

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


# --- containers, the chain and the gate (spec/contracts/container.md) -----------------------

ContainerType = Literal["inbox", "thread", "project", "team", "org", "exo", "uxo", "global"]
#: Declaration order IS ring rank. `enterprise` is omitted from the vocabulary (v0.5 §A); `uxo`
#: keeps rank 6 and is never instantiated (R11), so the ranks around it stay stable.
CONTAINER_TYPES: tuple[ContainerType, ...] = get_args(ContainerType)
#: An ATTRIBUTE — UI order and the gate's outward test — never the resolution order (container.md
#: §1). The chain is the tree walk, and its ranks need not be monotonic.
RING_RANK: dict[ContainerType, int] = {t: i for i, t in enumerate(CONTAINER_TYPES)}

RootType = Literal["user", "global"]
#: Tree roots. `user` is the personal tree (`user:self`) and is NOT a ring: it has no entry in
#: RING_RANK and still rides along in every chain (container.md §2).
ROOT_TYPES: tuple[RootType, ...] = get_args(RootType)

ServingPolicy = Literal["serve-unverified", "verified-only"]
#: Keyed by container type AND by the `user` root (F4). A type absent from this mapping MUST be
#: treated as `verified-only`: the lookup fails closed, so a forgotten entry withholds, never leaks.
SERVING_POLICY: dict[str, ServingPolicy] = {
    "inbox": "serve-unverified",
    "thread": "serve-unverified",
    "project": "serve-unverified",
    "team": "verified-only",
    "org": "verified-only",
    "exo": "verified-only",
    "uxo": "verified-only",
    "global": "verified-only",
    "user": "verified-only",  # F4 — the personal root rides along everywhere: reach → verification
}


class Node(TypedDict):
    """A container. `parent` is the ONLY location state; the path is computed from it, so moving a
    node is a metadata update (v0.4 §16). `type` is a `ContainerType` or a `RootType`.
    """

    id: str
    type: str
    name: str
    parent: str | None
    created_at: str


class AudienceMember(TypedDict):
    """One live token whose coverage reaches a node — people AND agents, never a count."""

    token: str
    owner: str
    client: str
    principal: Principal
    role: Role


ProposalStatus = Literal["open", "executed", "denied", "stale"]
#: `stale` is written when approval recomputes the manifest and it no longer matches — the TOCTOU
#: close is contract, not an implementation detail (container.md §6).
PROPOSAL_STATUSES: tuple[ProposalStatus, ...] = get_args(ProposalStatus)


class Proposal(TypedDict):
    """A move parked at the gate: nonzero audience delta, awaiting a human-only confirm. `manifest`
    binds the approval to `{items, target, audience}`; `execute` recomputes it and refuses on
    mismatch. `approved_by`/`executed_at` appear only once executed.
    """

    id: str
    status: ProposalStatus
    kind: Literal["move"]
    items: list[str]
    from_: str
    to: str
    from_path: str
    to_path: str
    audience: list[AudienceMember]
    audience_delta: list[AudienceMember]
    blast_radius: int
    manifest: str
    proposed_by: dict[str, Any]
    reason: str
    created_at: str
    executed_at: NotRequired[str]
    approved_by: NotRequired[str]


#: The wire key is `from`, which is a Python keyword; `Proposal` spells it `from_` and every
#: (de)serializer MUST map the two. Named here so no implementation invents a third spelling.
PROPOSAL_WIRE_KEY_FROM: str = "from"

StructureFloor = Literal["thread", "project", "team", "org", "exo"]
#: F2: a per-node scope-policy floor, NOT a seventh capability. Creating a container strictly above
#: the floor by ring rank, at that parent, needs `admin`. Keeps the vocabulary six wide.
STRUCTURE_FLOORS: tuple[StructureFloor, ...] = get_args(StructureFloor)

PersonalRootMode = Literal["between", "sovereign"]


class ContainerConfig(TypedDict):
    """The one config object F1, F2, F5 and R11 each needed (container.md §8).

    *Decided, not running* — the skeleton has no config surface and every value below is a constant
    in `model.py`. `CONTAINER_CONFIG_DEFAULTS` is exactly what it runs, so the shipped default and
    the observed behaviour are the same thing.
    """

    #: F1 — `sovereign` puts the personal root before the org ancestors. Per container.
    chain_personal_root: PersonalRootMode
    #: F1 — an org forbids the inversion inside its own subtree. Per org node.
    org_policy_sovereign_chain: Literal["allow", "deny"]
    #: F2 — per node, inherited by the subtree.
    node_policy_structure_floor: StructureFloor
    #: F5 — at or below this, and `text/*` only, a fetch carries the bytes inline.
    blobs_inline_max_bytes: int
    #: R11 — staged blobs: 30 days cold, then purge.
    blobs_staging_retention_days: int
    #: R11 — per source→destination ring pair, manifest-shape bounded, org-configurable to ZERO.
    step_up_window_seconds: int


CONTAINER_CONFIG_DEFAULTS: ContainerConfig = {
    "chain_personal_root": "between",
    "org_policy_sovereign_chain": "allow",  # a1p's reading — TODO(chief), container.md §8
    "node_policy_structure_floor": "project",
    "blobs_inline_max_bytes": 64 * 1024,
    "blobs_staging_retention_days": 30,
    "step_up_window_seconds": 300,
}


# --- the storage boundary (spec/contracts/storage.md) ---------------------------------------
#
# F3 splits the skeleton's ONE wide `Backend` Protocol into `ItemStore` (pluggable, delegable) and
# `ContainerState` (never delegated); `BlobStore` was already separate. The METHODS below are
# verbatim from the running code; the PARTITION is decided, not running. `audit_append` sits in
# `ContainerState` so the chain's integrity never depends on whoever wrote the backend — this
# amends v0.4 §11. See storage.md §1.
#
# These Protocols stay HERE when Phase 5 moves the implementations to Vault (R5): the seam is the
# type, and the type sits above both modules, so Store/Trust/Ledger never import Vault for a name.

# `Node` and `Proposal` are defined above, with `container.md`. `storage.md` §3's signatures were
# final before their referents existed and carried provisional `dict[str, Any]` aliases; issue #28
# replaces the aliases, and no signature below changed.


class ItemStore(Protocol):
    """Pluggable and delegable: sqlite -> postgres+pgvector -> mem0/zep.

    A filter, never a decision. The backend returns CANDIDATES; the resolver applies precedence,
    trust and key-override above it (v0.4 §11). Every getter returns `None`/a shorter list for
    absent, tombstoned and out-of-coverage alike — a distinguishable "exists but forbidden" is
    enumeration by another name (storage.md §5).
    """

    def put(self, item: ContextItem) -> None: ...
    def get(self, item_id: str) -> ContextItem | None: ...
    def query(
        self,
        scopes: Iterable[str],
        *,
        kinds: Iterable[Kind] | None = None,
        key: str | None = None,
        statuses: Iterable[TrustStatus] | None = None,
        text: str | None = None,
        include_tombstoned: bool = False,
    ) -> list[ContextItem]: ...
    def tombstone(self, item_id: str) -> bool: ...
    #: ^ internal to this boundary. No surface may reflect it to an external caller.


class ContainerState(Protocol):
    """The container's own state: nodes, tokens, proposals and the audit chain.

    sqlite by default, postgres at Phase 5, **never delegated to a third-party store** (F3).
    """

    # nodes
    def put_node(self, node: Node) -> None: ...
    def get_node(self, node_id: str) -> Node | None: ...
    def list_nodes(self, parent: str | None = None, type: str | None = None) -> list[Node]: ...
    def find_root(self, type: str) -> Node | None: ...

    # tokens
    def put_token(self, token: Token) -> None: ...
    def get_token(self, token_id: str) -> Token | None: ...
    def list_tokens(self) -> list[Token]: ...

    # pending proposals (cross-audience moves, staged artifacts)
    def put_proposal(self, proposal: Proposal) -> None: ...
    def get_proposal(self, proposal_id: str) -> Proposal | None: ...
    def list_proposals(self, status: str | None = None) -> list[Proposal]: ...

    # audit chain — append-only; the LEDGER computes the chain, the store only appends
    def audit_append(self, entry: AuditEntry) -> AuditEntry: ...
    #: ^ the input carries no `seq`: the store assigns it, returns the stored entry (events.md §3)
    def audit_last(self) -> AuditEntry | None: ...
    def audit_iter(self) -> Iterator[AuditEntry]: ...
    def audit_tail(self, n: int) -> list[AuditEntry]: ...


class BlobStore(Protocol):
    """Content-addressed bytes over `sha256/<hash>`, staged under `staging/<hash>`.

    Issues NOTHING. Trust mints a `BlobGrant`; Store/Vault renders it and decides nothing (F5) —
    signed-URL issuance passes Trust's capability check, because artifact download IS fetch. The
    mint (`blob.grant`) and the redemption (`blob.pull`) are two separate audit events.

    The staging prefix is invisible to resolution: `get`/`exists` address `sha256/<hash>` ONLY, and
    no flag or alternate method reads `staging/`. A staged blob is unaddressable until `promote`.

    Moves to Vault whole at Phase 5 (R5) — no back-reference into nodes, resolver or items, and
    addressing is by `sha256` alone.
    """

    def put(self, data: bytes) -> str: ...
    def stage(self, data: bytes) -> str: ...
    def promote(self, sha: str) -> None: ...
    def get(self, sha: str) -> bytes | None: ...
    def exists(self, sha: str) -> bool: ...
    #: ^ an existence oracle over guessable addresses: never reachable from an external path.


#: The two contracts F3 split out of the skeleton's union, and the third seam that was already
#: separate. Ordered as storage.md §1 lists them.
STORAGE_CONTRACTS: tuple[str, ...] = ("ItemStore", "ContainerState", "BlobStore")


__all__ = [
    "ArtifactContent",
    "AudienceMember",
    "AuditEntry",
    "BlobGrant",
    "BlobStore",
    "CAPABILITIES",
    "CONTAINER_CONFIG_DEFAULTS",
    "CONTAINER_TYPES",
    "CONTEXT_ITEM_FIELDS",
    "Capability",
    "ContainerConfig",
    "ContainerState",
    "ContainerType",
    "ContextItem",
    "EVENTS",
    "Event",
    "GENESIS_HASH",
    "HUMAN_ONLY_ACTS",
    "ItemStore",
    "KINDS",
    "Kind",
    "Lifecycle",
    "Node",
    "PRINCIPALS",
    "PROPOSAL_STATUSES",
    "PROPOSAL_WIRE_KEY_FROM",
    "PersonalRootMode",
    "Principal",
    "Proposal",
    "ProposalStatus",
    "Provenance",
    "RING_RANK",
    "ROLE_BUNDLES",
    "ROOT_TYPES",
    "Role",
    "RootType",
    "SERVING_POLICY",
    "STORAGE_CONTRACTS",
    "STRUCTURE_FLOORS",
    "ServingPolicy",
    "StructureFloor",
    "TRUST_STATUSES",
    "TextContent",
    "Token",
    "Trust",
    "TrustStatus",
    "VERIFIED_ONLY_KINDS",
]
