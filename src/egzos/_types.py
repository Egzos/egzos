# Copyright 2026 Ali Sasanian
# SPDX-License-Identifier: Apache-2.0
"""
Shared types — owned by a1p-planner.

The typed face of ``spec/contracts/``. Nothing here is invented: every name below is derived from
the running walking skeleton (``chief/walking-skeleton``) and carries the contract document it
belongs to. Shapes marked in the contracts as *decided, not running* are typed here too, so that
Phase 1 builds against the frozen surface rather than the skeleton's.

**Frozen at 0.3 with the contracts it types** (Chief, 2026-10-08; ``spec/contracts/README.md``).
A change to a vocabulary here is a change to a frozen contract: a ``contract-change`` escalation,
never a drive-by.

Covers all six documents: ``context-item.md``, ``capabilities.md``, ``events.md`` (issue #26),
``storage.md`` (issue #27), ``container.md`` (issue #28) and ``authorization-server.md`` (#67 and
#61, with the 0.3 decisions written in by #109). Consolidated by #30: one naming convention
(``SCREAMING_CASE`` runtime values derived from ``CamelCase`` types), no Literal union defined
twice, and ``__all__`` complete (``tests/_types/test_exports.py``) and isort-sorted (ruff RUF022).
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

Principal = Literal["interactive", "client", "none"]
#: `none` is an AUDIT ENTRY's principal, never a token's (capabilities.md §3, [0.3 · 34]): the
#: pre-authorization appends that have no caller to name (authorization-server.md §12.2).
PRINCIPALS: tuple[Principal, ...] = get_args(Principal)

#: What a token, an audience member or an item's provenance can carry: `none` excluded by type, so
#: a token minted for nobody is a type error rather than a value a check has to remember to refuse.
TokenPrincipal = Literal["interactive", "client"]
TOKEN_PRINCIPALS: tuple[TokenPrincipal, ...] = get_args(TokenPrincipal)

#: Outside the capability vocabulary by construction: no token reaches these, `admin` included.
#: A client principal can only propose. Not configurable, at any deployment.
HUMAN_ONLY_ACTS: tuple[str, ...] = ("gate.confirm", "yes.consume", "approve.pending")


class Token(TypedDict):
    """`scopes` are node ids; coverage is computed down the path AT CHECK TIME. `["*"]` = owner."""

    id: str
    principal: TokenPrincipal
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
    """All six keys present, null where unknown — never absent-vs-unset."""

    actor: str | None
    principal: TokenPrincipal | None
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


class ResolvedItem(TypedDict):
    """One item as a resolution returns it (container.md §4).

    `shadowed_by` is a property of THIS resolution, not of the item: the same item is shadowed in
    one chain and the winner in another. It is the id of the item that beat this one on its
    `(kind, key)` pair, or `None` for the winner and for every item without a `key`. `layer` and
    `layer_type` are here for the same reason — where this copy was found is not the item's own
    business. `layer_type` is a `ContainerType` or a `RootType`, as `Node.type` is, and is the key
    `SERVING_POLICY` is read by. Nothing here is ever persisted onto the `ContextItem`.

    The item's trust status is deliberately NOT a key here. It has one home,
    `item["trust"]["status"]`, and a `TrustStatus` restated on the envelope would be the same fact
    in two places with no rule for which wins when they differ — the copy a resolver snapshots
    before serialisation, and serves a quarantined item under. Read it from the item. The walking
    skeleton's resolver does emit a `trust` key here; the 0.3 freeze removed it (container.md §4),
    and Phase 1's resolver drops it.

    The envelope AROUND this list (`{scope, chain, items, withheld}`) is deliberately not typed
    here: `container.md` §4's `TODO(a1p)` on whether a silent refusal carries `withheld` is
    `[OPEN->0.3]`, and typing the response would answer it by accident.
    """

    item: ContextItem
    layer: str
    layer_type: str
    shadowed_by: str | None


class BlobGrant(TypedDict):
    """Minted by TRUST, never by Store/Vault (F5). Store renders it; it decides nothing.

    *Decided, not running.* `sig` is an HMAC over the descriptor with a container key ([0.3 · 45]);
    the grant id is not the bearer secret.
    """

    sha256: str
    item: str
    token: str
    expires_at: str
    sig: str


#: rest.md §6 — a `BlobGrant`'s `expires_at` is its mint time plus this, and the first verified
#: redemption spends it. A fixed contract value, never a config key: the Chief on #165 item 1,
#: option (a), 2026-10-09. A leaked grant URL is dead after one pull or five minutes at most.
BLOB_GRANT_LIFETIME_SECONDS: int = 300


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
    "approval.stale",
    "trust.quarantine",
    "step_up",
    "token.mint",
    "token.revoke",
    "item.tombstone",
    "blob.grant",
    "authz.login",
    "authz.redeem",
    "authz.refuse",
    "authz.release",
    "authz.reject",
    "authz.render",
    "authz.tally",
    "authz.revoke_refuse",
    "authz.grant",
    "client.register",
    "config.set",
]
#: An append whose event name is not here MUST be rejected. `approval.stale` is a TOCTOU refusal,
#: split from a human `approval.deny` (freeze item 39); `step_up` runs (the MVP tap, ahead of 2.2);
#: `blob.grant` is decided, not running (F5) — IN the vocabulary, so a validator built on this tuple
#: accepts it (`AuditEntry.event` needs the member the day F5 lands); what does not exist yet is any
#: code that emits it. The nine `authz.*` names and `client.register` are the same case: decided at
#: the 0.3 freeze (authorization-server.md §12 rows (a), (b), (d)–(h), §11.9, §9.3 and §5;
#: [0.3 · 29, 31, 33, 36], #140, #144), with no AS in this tree to emit them; so is `config.set`
#: (container.md §8, [0.3 · 40]), with no config surface. events.md §1 says the same thing from the
#: contract's side.
EVENTS: tuple[Event, ...] = get_args(Event)

#: The only events an entry with `principal: none` may carry (events.md §2): the caller-less rows
#: (a), (b), (d), (e) and (h) of authorization-server.md §12.2. An append with `principal: none`
#: under any other event MUST be rejected — a read or an act is never unattributed. The converse
#: binds too: an append under one of these five MUST carry `principal: none` (events.md §2).
#: [0.3 · 34]
PRINCIPAL_NONE_EVENTS: tuple[Event, ...] = (
    "authz.login",
    "authz.redeem",
    "authz.refuse",
    "authz.release",
    "authz.tally",
)

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
    principal: Principal  # `none` only under PRINCIPAL_NONE_EVENTS (events.md §2)
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
    principal: TokenPrincipal
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
    "org_policy_sovereign_chain": "allow",  # Chief decision [0.3 · 4], container.md §8
    "node_policy_structure_floor": "project",
    "blobs_inline_max_bytes": 64 * 1024,
    "blobs_staging_retention_days": 30,
    "step_up_window_seconds": 300,
}

#: Wire key -> `ContainerConfig` field. **The dotted names are canonical** (container.md §8): they
#: are what a config file and the wire carry, and no other spelling of them is a key.
#: `ContainerConfig` underscores them only because a dotted name is not a Python identifier — the
#: same situation as the wire's `from` against `Proposal.from_`, named by `PROPOSAL_WIRE_KEY_FROM`.
#:
#: A loader that does not consult this mapping does not read §8's keys at all: it silently ignores
#: every one of them and serves `CONTAINER_CONFIG_DEFAULTS`. That is the failure this constant
#: exists to prevent — an org that sets `step_up.window_seconds` to `0` gets `0`, not the 300 it
#: refused.
#:
#: Loading rule, from the same clause: **absence is tested by absence, never by truthiness.** `0`,
#: `""` and `False` are values. `cfg.get(wire_key) or default` is wrong for every row below and
#: silently wrong for the one row where it matters most.
CONTAINER_CONFIG_FIELD_FROM_WIRE_KEY: dict[str, str] = {
    "chain.personal_root": "chain_personal_root",
    "org.policy.sovereign_chain": "org_policy_sovereign_chain",
    "node.policy.structure_floor": "node_policy_structure_floor",
    "blobs.inline_max_bytes": "blobs_inline_max_bytes",
    "blobs.staging_retention_days": "blobs_staging_retention_days",
    "step_up.window_seconds": "step_up_window_seconds",
}


# --- the authorization server (spec/contracts/authorization-server.md) ----------------------
#
# The one contract with NO running shape: the skeleton mints the owner token at `init` and has no
# login, device-code or consent screen. Prose-derived — core mechanics from #67 (Part A, with #73
# and #78), the consent, login and device-code half from #61 (Part B), both covered as of this
# module.

ASClientType = Literal["browser", "cli", "mcp"]
#: The entire client vocabulary in v1.0 (§1). All three are public and hold no secret — there is no
#: confidential type, which is why no registration below carries a `client_secret`.
AS_CLIENT_TYPES: tuple[ASClientType, ...] = get_args(ASClientType)

ConsentKind = Literal["browser", "device", "mcp"]
#: The kind words the consent page renders (`spec/design/consent.md` §14 item 1, R4's client block,
#: the `kind.*` copy keys). Three words, and they are NOT `AS_CLIENT_TYPES`.
CONSENT_KINDS: tuple[ConsentKind, ...] = get_args(ConsentKind)

#: `ASClientType` -> the kind word rendered beside the client name (authorization-server.md §11.1).
#: The AS literal and the rendered word differ for exactly ONE type: `cli` renders as `device`,
#: because the design names that client by its flow (device-code) rather than by its category,
#: while this document's type predates Part B. A page renders the copy key `kind.device`, never
#: `kind.cli`, which does not exist.
#:
#: Named here for the same reason as `CONTAINER_CONFIG_FIELD_FROM_WIRE_KEY`: the mapping was
#: prose-only (#10 F25), and a mapping that lives only in prose is one each surface re-derives. The
#: AS-internal literal does not change; only its display name does, at the one place a display name
#: is rendered.
CONSENT_KIND_FROM_CLIENT_TYPE: dict[ASClientType, ConsentKind] = {
    "browser": "browser",
    "cli": "device",
    "mcp": "mcp",
}


class ClientRegistration(TypedDict):
    """A client entry in container config (§5); registration is an owner act.

    `redirect_uris` compare by EXACT STRING match — no prefixes, no wildcards, at any position —
    with one bounded relaxation: for a literal loopback host (`127.0.0.1`, `[::1]`) the port is
    ignored. A `localhost` host is refused at registration in any case spelling, with or without a
    port ([0.3 · 22], §5.2); a dev client registers `http://127.0.0.1/...` or `http://[::1]/...`.

    `registered_at` is §11.1's addition to §5's four: the consent screen renders it, and §5 named no
    timestamp. It is the seventh `*_at: str` timestamp in this module, and the first naming a
    *registration* rather than a mint, an update, or an expiry — deliberately not spelled
    `created_at`: `created_at` is generic across every other TypedDict here, but
    `Token.created_at` (a mint) and this registration's timestamp (an owner act at §5, not a
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
#: a1p's reading of what `actor` carries on every pre-authorization append, as a `Literal` alias
#: read back with `get_args`, matching the pattern `Capability`/`CAPABILITIES`,
#: `Principal`/`PRINCIPALS` and `ASClientType`/`AS_CLIENT_TYPES` already use above: a typo at a
#: call site that writes `details.surface` is a type error, not a string `str` would accept
#: silently. `tap` is the step-up tap's page, throttled unconditionally by `consent.md`'s D-C6
#: rather than by this contract; if §10.5's `[LEAN]` is not taken the tap rides a channel of its
#: own instead of these AS endpoints, but the word is still used there — D-C6's release entry is
#: `consent.md` §14.8 (e), the same event this vocabulary pins, and the tap spec §14.5 binds to it
#: by citing the decision rather than restating it in an entry of its own — never unused, only
#: ridden elsewhere. `revoke` is §11.9's page (decided at §9.2), the fifth word
#: ([0.3 · 11]). The caller's network identifier is NEVER the actor ([0.3 · 34]): a network
#: identifier may key a throttle bucket (§11.0, [0.3 · 24]) and never enters the chain.
#: The event NAMES these entries append under are `Event`'s `authz.*` members (§12, [0.3 · 33]).
ThrottleSurface = Literal["login", "device", "authorize", "tap", "revoke"]
AS_THROTTLE_SURFACES: tuple[ThrottleSurface, ...] = get_args(ThrottleSurface)

#: §12's table, rows (a), (b), (d) and (f) — the closed `details.cause` vocabulary each pre-token
#: effect appends under, as `Literal` aliases read back with `get_args`, matching the pattern
#: `Capability`/`CAPABILITIES`, `Principal`/`PRINCIPALS` and `ASClientType`/`AS_CLIENT_TYPES`
#: already use above: a typo at a call site that writes `details.cause` is a type error, not a
#: string `str` would accept silently. Row (d)'s `token_presented` is this Part's own addition over
#: `consent.md` §14.8 (d)'s six — named as the addition it is at row (d) itself, not silently
#: absorbed into the tuple. Row (f)'s two, not three: `expiry` is not a cause here, because §11.5
#: clamps an over-long expiry rather than ever rejecting it for that reason alone (row (f)'s own
#: paragraph). These four are closed; the event *names* these causes travel under are §12's
#: ([0.3 · 33]): `authz.login`, `authz.redeem`, `authz.refuse` and `authz.reject` in `Event`.
LoginCause = Literal["wrong", "unknown", "throttled"]
AS_LOGIN_CAUSES: tuple[LoginCause, ...] = get_args(LoginCause)

DeviceRedemptionCause = Literal["invalid", "expired", "used", "malformed", "throttled"]
AS_DEVICE_REDEMPTION_CAUSES: tuple[DeviceRedemptionCause, ...] = get_args(DeviceRedemptionCause)

AuthorizePretrustCause = Literal[
    "unknown_client",
    "redirect_mismatch",
    "malformed",
    "missing_pkce",
    "throttled",
    "replayed",
    "token_presented",
]
AS_AUTHORIZE_PRETRUST_CAUSES: tuple[AuthorizePretrustCause, ...] = get_args(AuthorizePretrustCause)

AuthorizePosttrustCause = Literal["vocabulary", "scope"]
AS_AUTHORIZE_POSTTRUST_CAUSES: tuple[AuthorizePosttrustCause, ...] = get_args(
    AuthorizePosttrustCause
)

#: §11.9 item 3 — the closed `details.cause` of `authz.revoke_refuse`, the owner-path revoke
#: refusal (#144, a1p). `unknown`: no token has that id; `unreachable`: one exists and the session
#: may not reach it; `throttled`: the attempt that engages the `revoke` throttle (§12.1 rule 3).
#: Both of the first two get the same response (§7.1); the cause is the owner's ledger's, never
#: the page's.
RevokeRefusalCause = Literal["unknown", "unreachable", "throttled"]
AS_REVOKE_REFUSAL_CAUSES: tuple[RevokeRefusalCause, ...] = get_args(RevokeRefusalCause)

#: §9.3 — `authz.grant`'s closed `details.decision` ([0.3 · 29]). One event with two outcomes, not
#: an `authz.grant`/`authz.deny` pair: the halves carry identical fields and differ only in outcome.
GrantDecision = Literal["granted", "denied"]
AS_GRANT_DECISIONS: tuple[GrantDecision, ...] = get_args(GrantDecision)

#: §5 — `client.register`'s closed `details.op` ([0.3 · 31]). `redirect_uris` beside it is the
#: allowlist AFTER the change, empty on `remove`.
ClientRegisterOp = Literal["add", "amend", "remove"]
AS_CLIENT_REGISTER_OPS: tuple[ClientRegisterOp, ...] = get_args(ClientRegisterOp)

#: §11.6 — a standard error redirect from `/authorize` carries exactly these two keys and nothing
#: else. `error_description` and `error_uri` are MUST NOT, with any value, under any cause — removed
#: rather than constrained, because a uniform constant description would satisfy §7's convergence
#: while leaving a field every implementation eventually fills with the cause it already computed.
#: Written out, not derived, the same reason `AS_CLIENT_REGISTRY_READ_FIELDS` is: a field added here
#: reaches the redirect the moment this module imports, with no test failing, unless a new member is
#: a deliberate act against this set.
AS_AUTHORIZE_ERROR_REDIRECT_FIELDS: frozenset[str] = frozenset({"error", "state"})

#: The two names §11.6 forbids outright — never emitted, not even empty or constant — so a test can
#: assert their absence as directly as it asserts the two permitted keys' presence.
AS_AUTHORIZE_ERROR_REDIRECT_FORBIDDEN_FIELDS: frozenset[str] = frozenset(
    {"error_description", "error_uri"}
)


class DeviceAuthorization(TypedDict):
    """RFC 8628's device-authorization response (§3) — CLI and headless only; browsers are retired.

    `verification_uri_complete` is NOT issued ([0.3 · 21]) — the key is absent from the response
    entirely, not optional and not null, and `/device` ignores a `user_code` query parameter. The
    typing step IS the mitigation: a code in a URL is a code a user can be asked to forward.
    """

    device_code: str
    user_code: str
    verification_uri: str
    expires_in: int
    interval: int


#: RFC 8414's location, at the container's own origin, unauthenticated (§6).
AS_METADATA_ENDPOINT: str = "/.well-known/oauth-authorization-server"

#: The metadata document IS the interoperability surface: a container MUST NOT advertise what it
#: does not implement, or implement what it does not advertise. This is the whole field vocabulary
#: of TEN, and every row is unconditional: omitting one is non-conforming, and advertising a field
#: that is not here is too. `registration_endpoint` is ABSENT, not present-and-null — [0.3 · 10]
#: decided there is no open dynamic client registration, and RFC 8414 omits an unsupported optional
#: field rather than nulling it. `revocation_endpoint` is here unconditionally — [0.3 · 11] decided
#: the RFC 7009 endpoint exists. The predecessor `AS_METADATA_CONDITIONAL_FIELDS` is gone with them:
#: an empty constant is a place for a later field to be quietly added.
AS_METADATA_FIELDS: tuple[str, ...] = (
    "issuer",
    "authorization_endpoint",
    "token_endpoint",
    "device_authorization_endpoint",
    "revocation_endpoint",
    "response_types_supported",
    "grant_types_supported",
    "code_challenge_methods_supported",
    "token_endpoint_auth_methods_supported",
    "scopes_supported",
)

#: §2 — an authorization code expires 60 seconds after issuance ([0.3 · 16]). A contract value, not
#: a default: there is no config key that raises it and a deployment may not add one.
AS_CODE_LIFETIME_SECONDS: int = 60

#: §9.3 — an AS-issued access token ALWAYS carries a non-null `expires_at`, 1 hour by default
#: ([0.3 · 17]). `capabilities.md` §5's `expires_at: null` stays reachable through `token mint`
#: ONLY, where the owner chooses it deliberately; no AS path, parameter or config key yields a
#: non-expiring token.
AS_ACCESS_TOKEN_LIFETIME_SECONDS: int = 3600

#: §11.5 — grant expiry: 30 d default, 90 d max; longer is CLAMPED, never refused ([0.3 · 18]).
AS_GRANT_LIFETIME_DEFAULT_SECONDS: int = 30 * 24 * 3600
AS_GRANT_LIFETIME_MAX_SECONDS: int = 90 * 24 * 3600

#: §10.2 — the interactive session ends at 30 min idle or 8 h absolute ([0.3 · 13]).
AS_SESSION_IDLE_SECONDS: int = 30 * 60
AS_SESSION_ABSOLUTE_SECONDS: int = 8 * 3600

#: §11.8 — a `user_code` is 8 of RFC 8628 §6.1's 20 consonants, shown `XXXX-XXXX` ([0.3 · 20]).
AS_USER_CODE_ALPHABET: str = "BCDFGHJKLMNPQRSTVWXZ"
AS_USER_CODE_LENGTH: int = 8

#: §11.7 — `continue` is at most 2048 bytes, still percent-encoded, as received ([0.3 · 25]).
AS_CONTINUE_MAX_BYTES: int = 2048

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
#: is absent from this map because its value is container-independent but not literal: it is the six
#: capability names, i.e. `CAPABILITIES`, and the `node:` form is NOT advertised ([0.3 · 28]).
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
    def promote(self, sha: str) -> bool: ...
    #: ^ True if staged bytes moved, False if nothing was staged there. Internal caller only
    #:   ([0.3 · 43]): the result never crosses an external boundary.
    def get(self, sha: str) -> bytes | None: ...
    def exists(self, sha: str) -> bool: ...
    #: ^ an existence oracle over guessable addresses: never reachable from an external path.


#: The two contracts F3 split out of the skeleton's union, and the third seam that was already
#: separate. Ordered as storage.md §1 lists them.
STORAGE_CONTRACTS: tuple[str, ...] = ("ItemStore", "ContainerState", "BlobStore")


# --- the authorization server's state (storage.md §3.1) — DRAFT binding (a1p), #173 ----------
#
# Not frozen. Two Protocols beside `ContainerState`, which is untouched: `ASState` is durable under
# any answer, and `ASGateState` (sessions, throttle counters) is the half whose partition is the
# Chief's TODO on #173 — container state, or process memory. Either answer implements the same
# signatures. No method takes a credential value: every credential key is the lowercase hex sha256
# of the whole value (`auth.py`'s `_hash`), except `user_code_hash`, which is a keyed HMAC-SHA256
# because the `user_code` is low-entropy. No record carries the value itself.


class ASGrant(TypedDict):
    """What a decided authorization will mint (§7: six capabilities and node ids, nothing else)."""

    capabilities: list[Capability]
    scopes: list[str]
    principal: TokenPrincipal  # §10.3: `interactive` only where presence was composed
    grant_expires_at: str  # §11.5: after the clamp


class AuthorizationCodeRecord(TypedDict):
    """§2: single-use, 60 s, bound to client, redirect and challenge, and the initiating session."""

    code_hash: str
    client_id: str
    redirect_uri: str
    code_challenge: str  # S256 only (§2); the method is not stored because there is one
    session_hash: str
    grant: ASGrant
    expires_at: str  # issued + `AS_CODE_LIFETIME_SECONDS`


DeviceDecision = Literal["pending", "granted", "denied"]

#: §11.8 — the requester hint is bounded. Trust truncates a longer one before `put_device` and never
#: refuses for it: refusing would branch on the hint. Draft (a1p, storage.md §3.1), not frozen.
AS_REQUESTER_HINT_MAX_CHARS: int = 64


class DeviceRequest(TypedDict):
    """§3 mitigations 2–3: what the device client asked for, as §7 expands its `scope`. An
    unparseable `scope` is refused at the endpoint (§11.2 consequence 2), so it never lands here.
    Principal (§10.3) and the clamped expiry (§11.5) are Trust's at `/device`, not requested."""

    capabilities: list[Capability]
    scopes: list[str]


class DeviceAuthorizationRecord(TypedDict):
    """§3 / §11.8: the pending authorization, bound to its `device_code` (mitigation 3)."""

    device_code_hash: str
    user_code_hash: str  # HMAC-SHA256 under the device-code key, not a bare sha256 (§3.1)
    client_id: str
    requested: DeviceRequest  # written by `put_device` only; what `/device` renders (mitigation 2)
    requester_hint: str | None  # UNVERIFIED client-supplied text (§11.8); `put_device` only
    decision: DeviceDecision
    grant: ASGrant | None  # set by `decide_device`; None while pending or when denied
    expires_at: str
    last_polled_at: str | None  # §3 mitigation 1's `slow_down`; written only by `poll_device`


class RefreshRecord(TypedDict):
    """§9.2: one link of a rotating chain. Kept after redemption, so reuse is detectable."""

    refresh_hash: str
    family_id: str  # `token.revoke` carries it ([0.3 · 30])
    client_id: str
    access_token_id: str  # the `Token.id` minted beside it; `revoke_family` revokes it too
    grant: ASGrant  # rotation does not widen a grant (§9.2 clause 3)
    redeemed_at: str | None
    revoked: bool


class DecidedRequestRecord(TypedDict):
    """§11.4: a request reaches a decision once. `request_key` is Trust's digest of the request's
    `(client_id, redirect_uri, state, code_challenge)`; opaque to the store."""

    request_key: str
    session_hash: str  # the deciding session (§11.0 substep 1)
    decision: GrantDecision
    decided_at: str
    resubmission_seen: bool


class SessionRecord(TypedDict):
    """§10.1: not a `Token`, not a bearer credential, never in `token ls`. Ends at
    `AS_SESSION_IDLE_SECONDS` idle or `AS_SESSION_ABSOLUTE_SECONDS` absolute — judged by Trust."""

    session_hash: str
    created_at: str
    last_seen_at: str


class ASState(Protocol):
    """The AS's durable state (storage.md §3.1). `ContainerState`-class: never delegated (F3).

    The plain getters return `None` for absent, expired, spent and revoked alike. The consumers do
    not judge: `consume_code` ignores expiry, and `redeem_refresh` and `poll_device` return the
    record as it stood before the call, so reuse stays detectable. All of it, every `bool` and
    `revoke_family`'s list stay inside Trust (storage.md §5). No client listing. The implementer
    MUST be the `ContainerState` implementer: `revoke_family` revokes its `Token`s.
    """

    # clients (§5) — the registry, not a `ContainerConfig` key
    def put_client(self, registration: ClientRegistration) -> None: ...
    def get_client(self, client_id: str) -> ClientRegistration | None: ...
    def remove_client(self, client_id: str) -> bool: ...

    # codes (§2) — consume is the only read, and spends the code whatever Trust then decides
    def put_code(self, record: AuthorizationCodeRecord) -> None: ...
    def consume_code(self, code_hash: str) -> AuthorizationCodeRecord | None: ...

    # device authorizations (§3, §11.8)
    def put_device(self, record: DeviceAuthorizationRecord) -> None: ...
    #: ^ insert-only: a put on an existing `device_code_hash` changes nothing
    def poll_device(self, device_code_hash: str, at: str) -> DeviceAuthorizationRecord | None: ...
    #: ^ sets `last_polled_at` alone, atomically; returns the record as it stood before the call
    def get_device_by_user_code(self, user_code_hash: str) -> DeviceAuthorizationRecord | None: ...
    def decide_device(self, device_code_hash: str, grant: ASGrant | None) -> bool: ...
    #: ^ pending -> granted/denied exactly once; False if it was not pending. Trust builds `grant`
    #:   from the record's `requested`, capabilities and scopes unchanged (§11.2 consequence 1)
    def consume_device(self, device_code_hash: str) -> DeviceAuthorizationRecord | None: ...
    #: ^ None while pending: a poll before the decision spends nothing

    # refresh chains (§9.2)
    def put_refresh(self, record: RefreshRecord) -> None: ...
    def redeem_refresh(self, refresh_hash: str) -> RefreshRecord | None: ...
    #: ^ returns the record AS IT STOOD before the call; a non-null `redeemed_at` is reuse
    def family_of_token(self, token_id: str) -> str | None: ...
    def revoke_family(self, family_id: str) -> list[str]: ...
    #: ^ every refresh record AND every `Token` they name, in one step; returns the `Token.id`s

    # decided requests (§11.4)
    def put_decided(self, record: DecidedRequestRecord) -> None: ...
    def get_decided(self, request_key: str) -> DecidedRequestRecord | None: ...
    def claim_resubmission(self, session_hash: str, request_key: str) -> bool: ...
    #: ^ True exactly once per recorded (session, request): §11.0 substep 1


class ASGateState(Protocol):
    """What gates a request before evaluation (§11.0): sessions and throttle counters.

    TODO(chief) #173: container state like `ASState`, or process memory a restart lifts. The
    signatures are the same either way (storage.md §3.1).
    """

    # interactive sessions (§10.1)
    def put_session(self, record: SessionRecord) -> None: ...
    def get_session(self, session_hash: str) -> SessionRecord | None: ...
    def touch_session(self, session_hash: str, at: str) -> bool: ...
    def end_session(self, session_hash: str) -> bool: ...

    # throttle counters (§11.0, §12) — no rate, no window length (#141); keys are Trust's
    def throttle_incr(self, surface: ThrottleSurface, bucket_key: str, window_key: str) -> int: ...
    def throttle_count(self, surface: ThrottleSurface, bucket_key: str, window_key: str) -> int: ...


#: storage.md §3.1, draft. Kept apart from `STORAGE_CONTRACTS`, which is the frozen 0.3 set.
AS_STATE_CONTRACTS: tuple[str, ...] = ("ASState", "ASGateState")


__all__ = [
    "AS_ACCESS_TOKEN_LIFETIME_SECONDS",
    "AS_AUTHORIZE_ERROR_REDIRECT_FIELDS",
    "AS_AUTHORIZE_ERROR_REDIRECT_FORBIDDEN_FIELDS",
    "AS_AUTHORIZE_POSTTRUST_CAUSES",
    "AS_AUTHORIZE_PRETRUST_CAUSES",
    "AS_CLIENT_REGISTER_OPS",
    "AS_CLIENT_REGISTRY_READ_FIELDS",
    "AS_CLIENT_TYPES",
    "AS_CODE_LIFETIME_SECONDS",
    "AS_CONTINUE_MAX_BYTES",
    "AS_DEVICE_REDEMPTION_CAUSES",
    "AS_GRANT_DECISIONS",
    "AS_GRANT_LIFETIME_DEFAULT_SECONDS",
    "AS_GRANT_LIFETIME_MAX_SECONDS",
    "AS_LOGIN_CAUSES",
    "AS_METADATA_CLOSED_VALUES",
    "AS_METADATA_ENDPOINT",
    "AS_METADATA_FIELDS",
    "AS_REQUESTER_HINT_MAX_CHARS",
    "AS_REVOKE_REFUSAL_CAUSES",
    "AS_SCOPE_ALL_NODES",
    "AS_SCOPE_NODE_PREFIX",
    "AS_SESSION_ABSOLUTE_SECONDS",
    "AS_SESSION_IDLE_SECONDS",
    "AS_STATE_CONTRACTS",
    "AS_THROTTLE_SURFACES",
    "AS_USER_CODE_ALPHABET",
    "AS_USER_CODE_LENGTH",
    "BLOB_GRANT_LIFETIME_SECONDS",
    "CAPABILITIES",
    "CONSENT_KINDS",
    "CONSENT_KIND_FROM_CLIENT_TYPE",
    "CONTAINER_CONFIG_DEFAULTS",
    "CONTAINER_CONFIG_FIELD_FROM_WIRE_KEY",
    "CONTAINER_TYPES",
    "CONTEXT_ITEM_FIELDS",
    "EVENTS",
    "GENESIS_HASH",
    "HUMAN_ONLY_ACTS",
    "KINDS",
    "PRINCIPALS",
    "PRINCIPAL_NONE_EVENTS",
    "PROPOSAL_STATUSES",
    "PROPOSAL_WIRE_KEY_FROM",
    "RING_RANK",
    "ROLE_BUNDLES",
    "ROOT_TYPES",
    "SERVING_POLICY",
    "STORAGE_CONTRACTS",
    "STRUCTURE_FLOORS",
    "TOKEN_PRINCIPALS",
    "TRUST_STATUSES",
    "VERIFIED_ONLY_KINDS",
    "ASClientType",
    "ASGateState",
    "ASGrant",
    "ASState",
    "ArtifactContent",
    "AudienceMember",
    "AuditEntry",
    "AuthorizationCodeRecord",
    "AuthorizePosttrustCause",
    "AuthorizePretrustCause",
    "BlobGrant",
    "BlobStore",
    "Capability",
    "ClientRegisterOp",
    "ClientRegistration",
    "ConsentKind",
    "ContainerConfig",
    "ContainerState",
    "ContainerType",
    "ContextItem",
    "DecidedRequestRecord",
    "DeviceAuthorization",
    "DeviceAuthorizationRecord",
    "DeviceDecision",
    "DeviceRedemptionCause",
    "DeviceRequest",
    "Event",
    "GrantDecision",
    "ItemStore",
    "Kind",
    "Lifecycle",
    "LoginCause",
    "Node",
    "PersonalRootMode",
    "Principal",
    "Proposal",
    "ProposalStatus",
    "Provenance",
    "RefreshRecord",
    "ResolvedItem",
    "RevokeRefusalCause",
    "Role",
    "RootType",
    "ServingPolicy",
    "SessionRecord",
    "StructureFloor",
    "TextContent",
    "ThrottleSurface",
    "Token",
    "TokenPrincipal",
    "Trust",
    "TrustStatus",
]
