# Contract · containers, the chain, serving policy and the gate

**Status: drafted — awaiting the Phase 0.3 freeze review.** Not law yet. The freeze is declared by
A6 and the Chief personally (build plan 0.3); a1p-planner prepares, it does not declare.

**Derivation.** The walking skeleton (`chief/walking-skeleton`, `docs/build/WALKING-SKELETON.md`
§2–§5, §9). Code: `model.py` (`CONTAINER_TYPES`, `RING_RANK`, `ROOT_TYPES`, `BASELINE_CREATE`,
`SERVING_POLICY`, `VERIFIED_ONLY_KINDS`), `store/nodes.py`, `resolver.py`, `trust.py`. Freeze
decisions **F1, F2, F4, F5** (Chief, 2026-09-21) and handoff **R11**.

**The authorization-server surface is not here** — it is `authorization-server.md` (issue #29), a
sibling document in this set. This document fixes containers, addressing, the chain, serving policy,
trust statuses, the gate and the container-config object; nothing about how a client obtains a
token.

Every clause is marked **running** (observed in the skeleton), **decided, not running** (a freeze
decision the skeleton does not execute), or `[OPEN→0.3]` (the freeze review must settle it).

## 1 · Container types and ring rank

`inbox 0 · thread 1 · project 2 · team 3 · org 4 · exo 5 · uxo 6 · global 7` — eight types, ring
rank fixed by declaration order. **running** (`model.CONTAINER_TYPES`, `model.RING_RANK`).

**`enterprise` is omitted from the vocabulary** (v0.5 §A). Said here rather than silently absent, so
the freeze review reads a decision and not an oversight: a reviewer who expects `enterprise` between
`org` and `exo` should find this sentence instead of a gap. **`uxo` keeps its slot and is never instantiated** (R11) — undefined, with #1 open and explicitly
non-blocking for v0.1. The slot is held rather than reclaimed **so the ranks around it stay stable**:
reclaiming rank 6 would move `global` to 6, and ring rank is persisted on items as `visibility.ring`
and compared numerically. `NodeService.create` refuses `uxo`. **running.**

**Ring rank is an attribute, not the chain.** It orders containers for the UI and answers the
**outward test** — whether `RING_RANK[to] > RING_RANK[from]` (v0.4 §2). It does **not** define
resolution order: the chain is the *tree walk* of §3, and a chain's ranks need not be monotonic. Two
clauses depend on this being said plainly: the personal root has **no ring rank at all** (§2) and
still appears in every chain; and the outward test is a recorded detail on `gate.pass.silent`,
**not** what decides the gate — the audience delta is (§6). **running.**

## 2 · Roots, the inbox, and addressing

Two tree roots exist from `init` (`NodeService.ensure_roots`): **`user`** — the personal tree,
`user:self`, rooted at identity and peer to org trees — and **`global`**. **running.**

**`user` is not a ring.** It is absent from `CONTAINER_TYPES` and from `RING_RANK`
(`ring_rank` returns `None`); it is a *root type*, not a container type. It rides along in every
chain (§3) and carries its own serving policy (§4, **F4**). Any code that ranks the personal root,
compares it outward, or offers it in a container-type menu is wrong against this clause. **running.**

**The inbox is a node of type `inbox` under the personal root** — not a root, not a resolver special
case. `init` creates it and there is one; pure capture opens an auto-created, auto-titled `thread`
under it (R11). **running.**

### Paths are computed, never stored

A node persists `{id, type, name, parent, created_at}`: **the parent pointer is the only location
state**, and the path is derived by walking it (`NodeService.path`). Moving a node is a metadata
update — zero bytes move (v0.4 §16). Each ancestor renders root-first as `type:name`, except
`global`, which renders bare: `user:self/org:acme/project:p`. **running.** `resolve_ref` accepts **either a node id or a path tail** — `project:health`,
`user:self/project:health`, or the bare `health`. A tail matches when each segment equals the full
`type:name` label or the name alone, against the same number of trailing path segments. **running.**

`[OPEN→0.3]` **Disambiguation when a tail matches more than one node.** v0.3 §4 says recency decides;
the skeleton uses **`created_at`**. Whether recency means creation or **last activity** is
**question 1 for the freeze review and is not decided here.** The two differ exactly where it
matters: a dormant `project:health` created last week beats one created last year that the user
touched this morning. Settle it with `storage.md` §2's open question on contractual result ordering —
the same question at two layers, and answers that disagree make `%n` non-deterministic.

`[OPEN→0.3]` **Auto-thread naming.** Pure capture names the thread from the **first item's
auto-title** (skeleton); whether it instead comes from a **thread-level title pass** once the thread
has several items is **question 2 for the freeze review and is not decided here.** It bears on this
document because a thread that renames itself changes its own path, and paths are the addressing
surface.

## 3 · The chain

`NodeService.chain(scope, include_global=True)` returns the chain **innermost first**: (1) the scope,
then each ancestor up the tree, **stopping at and including an `exo` ancestor**, which ends the
*tree walk*; (2) then the **personal root**, if not already present; (3) then **`global`**, unless
`--no-global` (`include_global=False`). **running.**

**An `exo` ancestor ends the tree walk, not the chain.** `exo` is a branch beside the org tree and
**never inherits inward** (v0.4 §2), so the walk stops — but steps 2 and 3 still run: a chain under
an `exo` is `…/exo:x` → `user:self` → `global`, never `…/exo:x` alone. **running.**

### F1 · where the personal root sits

The ordering above **is F1's `between`**: the personal root lands after the org ancestors and before
`global`. Where `org:acme` sits under `user:self`, step 1 already produces it there; where org trees
are peers of the personal tree, step 2 appends it to the same position. Both yield `between`.
**running** — the only mode the skeleton has.

**F1** makes this a config key, `chain.personal_root: between | sovereign`, default `between` (§8).
**`sovereign`** inserts the personal root **immediately after the scope's own ring and before the
org ancestors** — personal preference beats org policy everywhere. **decided, not running.**
**The rationale, carried verbatim from F1 so it survives the freeze:** under `between`, *org policy
overrides personal preference inside org scopes, and personal preference still beats global
defaults*. That is why the default is `between`, and why the personal layer is inside the chain at
all rather than beside it (v0.3 §2 reason (2): the personal layer must ride along in every fetch).

**An org may forbid the inversion in its own branches**: `org.policy.sovereign_chain: deny` (§8).
Where an org denies it, the chain is `between` inside that subtree whatever the container-level key
says. **decided, not running.**

## 4 · Serving policy and resolution

Exactly as `model.SERVING_POLICY` runs it — `serve-unverified` at **`inbox`, `thread`, `project`**;
`verified-only` at **`team`, `org`, `exo`, `uxo`, `global`, and the personal root `user`** (**F4**).
**running.** A type absent from the mapping resolves to **`verified-only`**: the lookup is
`SERVING_POLICY.get(type, "verified-only")` and it **fails closed**, so a new container type that
forgets its entry withholds rather than leaks. **running.**
**F4's rationale, carried:** the personal root **rides along in every chain** (§3), so an unverified
item there reaches further than an unverified item in any org scope. **Reach implies verification** —
the same logic behind team-and-outward and behind rules-everywhere. The cost the Chief accepted: the
owner's own `add --scope user:self`, the rarest write in the system, costs one `trust approve`.

### Three invariants above the policy

1. **Rules are verified-only at every scope.** `kind: rule` is served only when
   `trust.status == verified`, at `inbox` and `thread` too. This is an **invariant, not a policy
   row** — it *overrides* the policy wherever that says `serve-unverified`
   (`VERIFIED_ONLY_KINDS`, `Resolver.serve`). **running.**
2. **Quarantined items are never served** — at any scope, under any policy, in **any status query**.
   `quarantined` is checked before the kind and before the policy, and no filter, flag or status
   argument reaches past it on a read path. **running.**
3. **Coverage is checked per layer, and an uncovered layer is absent — never an error.** The
   resolver skips a layer the token does not cover (`TrustEngine.covers`) and that layer does not
   appear in the response: **the token never learns the layer exists.** A partial chain and a chain
   with nothing in those layers are indistinguishable — silence-not-errors stated at the resolver
   boundary (`capabilities.md` §6, `storage.md` §5). Every layer is filtered **server-side, before
   serialization**: a surface that received the full chain and filtered it for display would
   satisfy the letter of this clause and break it. **running.**

### Most-specific-wins, and the visible chain

For each `(kind, key)` pair the **innermost** item wins. Outer items with the same pair are **still
returned**, each carrying `shadowed_by` set to the id of the item that beat it; the winner carries
`shadowed_by: null`. Items without a `key` never shadow and are never shadowed. **running.**

**Clients may see the full chain, overridden values included** (v0.4 §7) — `shadowed_by` is the
mechanism, and it is deliberate: a client that sees only the winner cannot explain *why* a preference
took the value it did. Not a leak — every returned layer already passed coverage and the policy.

TODO(a1p): when the token lacks `fetch`, `Resolver.resolve` returns
`{"scope": None, "chain": [], "items": []}` with **no `withheld` key**, while every other return
carries one. A silent refusal must be **shape-identical** to a legitimately empty result, or the
missing key is itself the oracle. That reading of silence-not-errors is a1p's, not a source's; the
asymmetry looks like an oversight rather than a decision, and the freeze should say which.

## 5 · Trust statuses

`unverified · verified · quarantined` (`context-item.md` §5). **running.**

**Writes land unverified — human and agent alike.** No capability, principal or flag makes a write
land verified. The owner's own `add` is unverified exactly as an agent's is; the difference between
them is the audit trail, not the status. **running.**

**Promotion is human-only.** `promote` demands the **interactive** principal and raises `HumanOnly`
otherwise — `approve.pending` sits outside the capability vocabulary, so a maximally granted client
(`admin` included) cannot reach it (`capabilities.md` §4). It stamps `trust.promoted_at`,
`trust.manifest` (§6's hash) and `provenance.approved_by`, and increments `lifecycle.version`. A
**quarantined item is not promoted** — lifting a quarantine is a separate deliberate act. **running.**

**Quarantine requires `curate`** and **propagates via `derived_from`**: quarantining an item also
quarantines every item whose `provenance.derived_from` names it, with reason `derived from <id>`.
Every affected id is recorded on the single `trust.quarantine` event (`events.md` §1). **running.**

TODO(a1p): propagation walks **one generation** — an item derived from a *derived* item is not
reached, because the sweep matches `derived_from == item.id` and does not re-run over what it just
marked. v0.3 §5 says quarantine "propagates immediately to descendants", which reads transitive. The
freeze should say whether this is transitive closure (and whether a `derived_from` cycle must then be
tolerated) or one generation by design. The skeleton's single pass is the thing in doubt, not the
answer.

## 6 · The gate

**audience(node)** = every **live token whose coverage reaches that node** — people *and* agents,
each as `{token, owner, client, principal, role}`, ordered by token id. Coverage is computed down
the path at check time; a revoked token is never in an audience. **delta** = audience(to) −
audience(from), by token id. **running.**

**Zero delta** → the move executes and is **silently logged**: `gate.pass.silent` with
`audience_delta: none`. **Nonzero delta** → the move **does not execute**; a proposal is parked in
pending and `gate.propose` is logged. **running.** "Silently" means without interrupting the user,
**never** without an audit event: a zero-delta move that produced no `gate.pass.silent` entry is a
finding (`events.md` §4). A parked proposal carries, at minimum:

```
{items, from, to, from_path, to_path, audience, audience_delta, blast_radius,
 manifest, proposed_by{actor, principal, client}, reason, status, created_at}
```

`audience_delta` names **client, role and principal** for each newly-reached token — the gate shows
*who* gains sight, not a count. `blast_radius` is the number of current descendants of the target
that inherit what lands there. **The gate parks even for the interactive owner**: a nonzero delta is
a publish, and the confirm is a separate human act, never an inferred one. **running.**

### Inward is instant, and is not special-cased

**"Inward moves are instant" falls out of the delta rule rather than being implemented.** Audience
only grows outward, so moving inward can only *shrink* the set of tokens that reach the item;
audience(to) − audience(from) is empty and the zero-delta branch takes it. **There is no inward check
anywhere in the gate, and there must not be one** — the `outward` flag on `gate.pass.silent` is a
recorded detail, never a branch condition. `WALKING-SKELETON.md` §5 asks for this sentence by name;
it is here so an implementation cannot "optimize" the gate by testing ring rank and thereby make
inward-ness the rule instead of its consequence. **running.**

### Approval recomputes the manifest — TOCTOU is closed in the contract

`manifest = sha256(canonical({items: sorted(item_ids), target, audience}))`. **running.**

`trust approve <proposal>` **recomputes the manifest from current state and refuses on mismatch**:
the proposal moves to status **`stale`**, an `approval.deny` event is written with `stale: true`, and
nothing moves. The approver must re-propose against the audience they can actually see. `execute` and
`deny` are both **human-only** (`gate.confirm`); a client principal can only propose. **running.**
This is **contract text, not an implementation detail.** What the Chief approved was a named
audience; a token minted between proposal and approval makes the approval one for a different act
than the one displayed. An implementation that executed against the *stored* manifest would pass
every test that does not mint a token mid-flight — and would break the only thing the gate is for.

TODO(a1p): the **nonzero-delta** path parks a proposal **without checking any capability**, while the
*zero*-delta path requires `organize`. A `reader` token holding only `fetch` can therefore fill the
owner's pending queue — the surface the Chief approves from. No source names a floor for proposing;
the freeze should name one (`organize` at the source scope, matching the silent path, is the obvious
candidate) or state that proposing is deliberately uncapped. a1p does not answer it in the spec.

## 7 · Structure creation — a floor, not a capability (F2)

Creating a container is governed by a **per-node scope-policy floor**, not a seventh capability:
`node.policy.structure_floor ∈ {thread, project, team, org, exo}`, default **`project`** (§8).
Creating a container whose type is **strictly above the floor by ring rank**, at that parent,
requires **`admin`**; at or below the floor the baseline applies and no `admin` is needed.

With the default floor `project` (rank 2), `thread` and `project` are baseline while `team`, `org`
and `exo` need `admin` — which is v0.3 §2's sentence exactly. **running** as the default floor
(`BASELINE_CREATE`, `NodeService.create`); the **per-node policy object is decided, not running**.
**This is what keeps the vocabulary six wide.** *"Six capabilities are the ENTIRE vocabulary"* is a
DECIDED sentence (v0.3 §5); a seventh `structure` capability would break it and hand an agent
structural power without the `admin` warning attached. `token ls` stays six columns
(`capabilities.md` §1). `inbox` and `global` are **never created** through this path — they exist
from `init`, and `create` refuses both, as it refuses `uxo` (§1). **running.**

TODO(a1p): the skeleton checks `token.has("admin")` but **not** that the token *covers the parent
node*, while its own error reads "needs admin at the parent scope". The clause above says **at that
parent** and means it: a token scoped to `project:a` must not create an `org` beside `project:b`.
That is a1p's reading of `capabilities.md` §5 — capability is held *within a scope*, coverage
computed at check time — applied to a check the skeleton wrote scope-free. If the freeze disagrees it
must say so explicitly, because scope-free `admin` makes every floor in this section global.

## 8 · The container-config object

**decided, not running.** The skeleton has no config surface; every value below is a constant in
`model.py`. F1, F2 and F5 each need a configurable value and R11 needs a fourth, so the freeze
introduces **one object** rather than four ad-hoc settings — defined here.

| key | default | applies at | may a deployment change it? |
|---|---|---|---|
| `chain.personal_root` | `between` | container | **yes** — F1's inversion key (§3) |
| `org.policy.sovereign_chain` | `allow` | org node | **yes** — forbids inversion in that subtree (§3) |
| `node.policy.structure_floor` | `project` | node | **yes** — set on an org, inherited by its subtree (§7) |
| `blobs.inline_max_bytes` | `65536` (64 KiB) | container | **yes** — F5 (`storage.md` §4) |
| `blobs.staging_retention_days` | `30` | container | **yes** — R11: 30 days cold, then purge |
| `step_up.window_seconds` | `300` (≈5 min) | container, per source→destination **ring pair** | **yes, including `0`** — R11 |

A deployment that omits the object gets the defaults, and the defaults are exactly what the skeleton
runs as constants — so `between` + floor `project` + 64 KiB is both the shipped default and the
observed behaviour. Four notes the table cannot carry:

- **`chain.personal_root`** is per-deployment by F1 and "invertible **per user**" by R11 — the same
  key in a single-owner container, which is all v0.1 has. Recorded so the freeze reads a known
  equivalence rather than a contradiction.
- **`org.policy.sovereign_chain`'s default `allow`** is a1p's reading, not a quoted source: F1 says
  an org *may* forbid inversion, and a permission that must first be granted before it can be
  withheld is not a permission to withhold. TODO(chief): confirm `allow`, or say `deny` and make org
  branches sovereign-proof by default.
- **`step_up.window_seconds`** is per source→destination ring pair and **manifest-shape bounded**
  (R11) — a window opened for one shape of act does not cover another. **Zero is supported.** The
  flow is Phase 2.2 and `step_up` is a reserved event (`events.md` §1); only the *key* is frozen.
- **`blobs.staging_retention_days`** closes `storage.md` §4's `TODO(a1p)` on abandoned staged bytes,
  written before this key existed: R11 ratifies 30 days cold, then purge. TODO(a1p): #30 should
  strike that TODO's "no source names" clause and point it here. It covers **staged** bytes only —
  no source names a reclamation path for *promoted* bytes behind a tombstoned artifact.

`[OPEN→0.3]` **Where the object lives and who may write it.** The config is read on the resolution
path (`chain.personal_root`), the structure path (`structure_floor`) and the blob path
(`inline_max_bytes`), so it is `ContainerState` by F3's rule — but `storage.md` §3 names four method
groups and config is not among them, and no source says whether changing a key is an `admin` act, an
audit event, or a restart-only file. Not decided here: the freeze should name the method group, the
capability and the event, because **a config surface Trust does not gate is a way to widen an
audience without passing the gate.**

## 9 · What this document does not fix

The item's own shape, `visibility.ring` and `content` → `context-item.md`. Capabilities, role
bundles, principals, tokens, coverage and human-only acts → `capabilities.md`. The event list, the
entry shape and the hash chain → `events.md`. How nodes, tokens and proposals are **persisted**, and
`BlobGrant`'s rendering → `storage.md`. **The authorization-server surface — auth-code + PKCE,
device-code, MCP clients, client registration and the redirect allowlist, AS metadata — is
`authorization-server.md`** (issue #29); nothing above constrains it beyond §5's human-only clause.
Presence, the localhost step-up tap and the consent pages are Phase 2.2 and A2's spec (issue #61);
only `step_up.window_seconds` and the reserved `step_up` event are frozen now.
