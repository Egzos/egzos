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
``storage.md`` (issue #27), ``container.md`` (issue #28) and the authorization server's core
mechanics (``authorization-server.md``, issue #29; its consent half is #61). The consolidation pass
is #30.
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


# --- the authorization server (spec/contracts/authorization-server.md) ----------------------
#
# The one contract with NO running shape: the skeleton mints the owner token at `init` and has no
# login, device-code or consent screen. Prose-derived (#29, part A); the consent half is #61.

ASClientType = Literal["browser", "cli", "mcp"]
#: The entire client vocabulary in v1.0 (§1). All three are public and hold no secret — there is no
#: confidential type, which is why no registration below carries a `client_secret`.
AS_CLIENT_TYPES: tuple[ASClientType, ...] = get_args(ASClientType)


class ClientRegistration(TypedDict):
    """A client entry in container config (§5); registration is an owner act.

    `redirect_uris` compare by EXACT STRING match — no prefixes, no wildcards, at any position —
    with one bounded relaxation: for a literal loopback host (`127.0.0.1`, `[::1]`) the port is
    ignored. `http://localhost:<port>/...` is registrable only as the exact string, port included.

    `registered_at` is §11.1's addition to §5's four: the consent screen renders it, and §5 named no
    timestamp. It is the fifth `*_at: str` timestamp in this module and the first not spelled
    `created_at` — deliberately: `created_at` is generic across every other TypedDict here, but
    `Token.created_at` (a mint) and this registration's timestamp (an owner act at `/5`, not a
    mint) are two different events that can appear on the same consent screen at once (§11.1's
    client entry beside §11.3's existing-tokens read), and one screen showing two `created_at`
    values for two different things would be the confusion the domain word avoids. `client_name`
    is owner-supplied DATA — the AS never verifies it and nothing in the AS may branch on it; a
    name that imitates the product is a registration the owner made, and the page's defence is
    showing the origin and the kind beside it.
    """

    client_id: str
    client_name: str
    client_type: ASClientType
    redirect_uris: list[str]
    registered_at: str


#: §11.1 — what the consent screen may read about a client: ONE entry, keyed by the request's
#: `client_id`. There is no listing endpoint, page or parameter, and an unregistered `client_id`
#: produces §5.3's uniform failure and no read at all — §7's enumeration rule, at the registry.
#:
#: Written out rather than derived from `ClientRegistration`. Deriving it would make the pin a
#: tautology: a field added to the registration would reach the consent screen the moment this
#: module imported, with no test failing. Written, a new registration field has to be added HERE
#: too — a deliberate act, against a §11.1 clause — before any page may read it.
AS_CLIENT_REGISTRY_READ_FIELDS: frozenset[str] = frozenset(
    {"client_id", "client_name", "client_type", "redirect_uris", "registered_at"}
)

#: §12.1 rule 5 — the closed `surface` vocabulary a throttle-release entry carries, and (§12.2)
#: a1p's reading of what `actor` carries on every pre-authorization append. `tap` is the step-up
#: tap's page, throttled unconditionally by `consent.md`'s D-C6 rather than by this contract; if
#: §10's `[LEAN]` is not taken the tap rides a channel of its own instead of these AS endpoints,
#: but the word is still used there — D-C6's release entry is `consent.md` §14.8 (e), the same
#: event this vocabulary pins, and the tap spec §14.5 binds to it by citing the decision rather
#: than restating it in an entry of its own — never unused, only ridden elsewhere. The caller's
#: network identifier is NEVER the actor: it would write
#: surveillance into a chain the owner cannot prune.
#: The event NAMES these entries append under are `[OPEN->0.3]`, batched as #86 with #68 — so there
#: is no constant for them here, deliberately.
AS_THROTTLE_SURFACES: tuple[str, ...] = ("login", "device", "authorize", "tap")

#: §12's table, rows (a), (b), (d) and (f) — the closed `details.cause` vocabulary each pre-token
#: effect appends under. Written out rather than derived, for the same reason `AS_THROTTLE_SURFACES`
#: is: the point of a closed cause list is that it is closed, and a cause arriving that is not in
#: the tuple should break a test, not append quietly. Row (d)'s `token_presented` is this Part's own
#: addition over `consent.md` §14.8 (d)'s six — named as the addition it is at row (d) itself, not
#: silently absorbed into the tuple. Row (f)'s two, not three: `expiry` is not a cause here, because
#: §11.5 clamps an over-long expiry rather than ever rejecting it for that reason alone (row (f)'s
#: own paragraph). These four tuples are never open — unlike the event *names* these causes travel
#: under, which are `[OPEN->0.3]`, batched as #86 with #68, and so have no constant here.
AS_LOGIN_CAUSES: tuple[str, ...] = ("wrong", "unknown", "throttled")
AS_DEVICE_REDEMPTION_CAUSES: tuple[str, ...] = (
    "invalid",
    "expired",
    "used",
    "malformed",
    "throttled",
)
AS_AUTHORIZE_PRETRUST_CAUSES: tuple[str, ...] = (
    "unknown_client",
    "redirect_mismatch",
    "malformed",
    "missing_pkce",
    "throttled",
    "replayed",
    "token_presented",
)
AS_AUTHORIZE_POSTTRUST_CAUSES: tuple[str, ...] = ("vocabulary", "scope")


class DeviceAuthorization(TypedDict):
    """RFC 8628's device-authorization response (§3) — CLI and headless only; browsers are retired.

    `verification_uri_complete` is `[OPEN->0.3]`, so it is optional here, not absent or mandatory.
    """

    device_code: str
    user_code: str
    verification_uri: str
    expires_in: int
    interval: int
    verification_uri_complete: NotRequired[str]


#: RFC 8414's location, at the container's own origin, unauthenticated (§6).
AS_METADATA_ENDPOINT: str = "/.well-known/oauth-authorization-server"

#: The metadata document IS the interoperability surface: a container MUST NOT advertise what it
#: does not implement, or implement what it does not advertise. This is the whole field vocabulary
#: of eleven; two of them are CONDITIONAL, see `AS_METADATA_CONDITIONAL_FIELDS` below.
AS_METADATA_FIELDS: tuple[str, ...] = (
    "issuer",
    "authorization_endpoint",
    "token_endpoint",
    "device_authorization_endpoint",
    "revocation_endpoint",
    "registration_endpoint",
    "response_types_supported",
    "grant_types_supported",
    "code_challenge_methods_supported",
    "token_endpoint_auth_methods_supported",
    "scopes_supported",
)

#: The two rows whose endpoint's very existence is `[OPEN->0.3]`, so §6's "MUST NOT advertise what
#: it does not implement" forbids advertising either until the freeze says yes:
#:   - `revocation_endpoint` — §9. §K answers revocation with `token rm`, an OWNER path; whether an
#:     RFC 7009 endpoint exists (and its silence rule, and whether a client may revoke another
#:     client's token) is the §9 `[OPEN->0.3]`. A browser or MCP client cannot run `token rm`.
#:   - `registration_endpoint` — §5. Advertised only if dynamic registration (RFC 7591) is enabled.
#: The other nine are unconditional: omitting one of those is non-conforming.
AS_METADATA_CONDITIONAL_FIELDS: frozenset[str] = frozenset(
    {"revocation_endpoint", "registration_endpoint"}
)

#: §7 — the grant is six capabilities and node ids, NOTHING else. An OAuth `scope` value is a
#: space-delimited set drawn from exactly two forms: a bare name from `CAPABILITIES`, or
#: `node:<node-id>`, which is how a `Token.scopes` entry is SPELLED in a `scope` value and not the
#: entry itself — the AS strips the prefix, so `node:*` requests the whole container and lands on
#: the token as `capabilities.md` §5's `["*"]`, the owner's grant (authorization-server.md §7,
#: consequence 3).
#: There is no third form, and no constant here for one. Role bundle NAMES are not scope strings: a
#: bundle is expanded at mint time and the token carries capabilities, so a bundle in a grant would
#: be a second vocabulary that can drift. The two vocabularies collide on exactly one word — `admin`
#: is a capability AND the all-six bundle — and in a `scope` value it is always the capability.
#: Pinned in `tests/_types/test_as_shapes.py`, including the collision being that one word only.
AS_SCOPE_NODE_PREFIX: str = "node:"
AS_SCOPE_ALL_NODES: str = "node:*"

#: Closed values (§2, §6). `code` is the only response type, ever; `plain` is never advertised and
#: MUST be rejected; every client is public, so `none` is the only auth method. `scopes_supported`
#: is absent: it is the six capability names, and whether `node:` joins them is `[OPEN->0.3]`.
AS_METADATA_CLOSED_VALUES: dict[str, tuple[str, ...]] = {
    "response_types_supported": ("code",),
    "grant_types_supported": (
        "authorization_code",
        "refresh_token",
        "urn:ietf:params:oauth:grant-type:device_code",
    ),
    "code_challenge_methods_supported": ("S256",),
    "token_endpoint_auth_methods_supported": ("none",),
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
    "AS_AUTHORIZE_POSTTRUST_CAUSES",
    "AS_AUTHORIZE_PRETRUST_CAUSES",
    "AS_CLIENT_REGISTRY_READ_FIELDS",
    "AS_CLIENT_TYPES",
    "AS_DEVICE_REDEMPTION_CAUSES",
    "AS_LOGIN_CAUSES",
    "AS_METADATA_CLOSED_VALUES",
    "AS_METADATA_CONDITIONAL_FIELDS",
    "AS_METADATA_ENDPOINT",
    "AS_METADATA_FIELDS",
    "AS_SCOPE_ALL_NODES",
    "AS_SCOPE_NODE_PREFIX",
    "AS_THROTTLE_SURFACES",
    "ASClientType",
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
    "ClientRegistration",
    "ContainerConfig",
    "ContainerState",
    "ContainerType",
    "ContextItem",
    "DeviceAuthorization",
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
