# The walking skeleton (Phase 0.1)

**Status: running, ugly, throwaway by decision** (decisions log v0.5 §H; build plan 0.1). Contracts
are frozen at Phase 0.2 **from these running shapes**, not from prose. This file is the handoff to
a1p-planner: what runs, how to run it, every shape 0.2 must read off it, and the **five freeze
decisions the Chief took on 2026-09-21 (F1–F5)** where the log had been silent. Three of the five
are *running* in the skeleton (F1's default, F4, and F2's admin gate); two (F3's split and F5's
`BlobGrant`) are **decided shapes the skeleton does not yet run** — a1p drafts them from the
decision text below, and the freeze review (0.3) reads them knowing that.

Branch: `chief/walking-skeleton`. Not merged; the contracts derive from it and Phase 1 builds
properly along the Store/Vault seam.

## Run it

```bash
uv venv --python 3.12 .venv && uv pip install --python .venv/bin/python -e ".[dev]"
bash scripts/demo.sh                 # add → inbox → resolve → serve --mcp → audit, end to end
.venv/bin/python -m pytest -q        # 13 tests, one per shape
```

The five verbs, by hand:

```bash
export EGZOS_HOME=$(mktemp -d); alias egzos='python -m egzos.cli'
egzos init                                    # roots user:self + global, inbox, interactive admin token
egzos add "Prefer imperative commits" --kind preference --key commit.style     # → inbox thread, unverified
egzos ls --inbox
egzos mk project health && egzos find commit && egzos mv %1 project:health     # solo: silent gate pass
egzos token create --client claude-code --role contributor --scope project:health
egzos fetch project:health                    # chain innermost-first, policies, most-specific-wins
EGZOS_TOKEN=<client> egzos serve --mcp        # the door; scripts/mcp_client_probe.py stands in for Claude Code
egzos audit tail && egzos audit verify        # every read on the record; the chain verifies
```

## Module map (Store/Vault seam respected — R5)

| module | owner at Phase 1 | what the skeleton has |
|---|---|---|
| `egzos/_ids.py` | store | ULIDs |
| `egzos/model.py` | a1p (shared types) | every constant and shape below |
| `egzos/backends/{base,sqlite}.py` | store → Vault at Phase 5 | the storage union (to be split per F3) + sqlite |
| `egzos/store/{nodes,items,autotitle}.py` | store | node model, chain, add, inbox, degraded titler |
| `egzos/store/blobs.py` | store → Vault at Phase 5 | content-addressed blobs, staging prefix; no back-references |
| `egzos/ledger.py` | ledger | hash chain, verify, event taxonomy |
| `egzos/trust.py` | trust | statuses, promotion, quarantine, the gate, manifest binding |
| `egzos/resolver.py` | store (chain) / trust (policy) | chain walk, coverage, policy, key override |
| `egzos/auth.py` | trust | principals, tokens, role bundles, keychain stand-in |
| `egzos/cli/`, `egzos/mcp/` | doorman | the two doors |

## Freeze decisions F1–F5 (Chief, 2026-09-21)

Each names the option taken, the second-order effect, and the alternative rejected. These belong
in the decisions-log amendment set that is owed (v0.8); until it exists, this section is the record.

| | decision | second-order effect | rejected |
|---|---|---|---|
| **F1** | **Personal root sits between org and global** in every chain (R11 default, from v0.3 §2's LEAN: *org policy overrides personal preference inside org scopes*), with a **per-deployment inversion key** `chain.personal_root: between \| sovereign`. `sovereign` places the personal root immediately after the scope's own ring and *before* the org ancestors — personal beats org everywhere. An org **may forbid** inversion for its work branches (`org.policy.sovereign_chain: deny`). | The contract carries a container-config object from v1.0; the same object hosts F2's floor and the org-configurable step-up window (R11). Skeleton runs `between` only. | Personal root never inside an org chain — contradicts v0.3 §2 reason (2): *the personal layer must ride along in every fetch*. |
| **F2** | **`structure` is a scope-policy floor on a node, not a capability.** `node.policy.structure_floor ∈ {thread, project, team, org, exo}`; creating a container of a type *above* the floor at that parent needs `admin`. Default floor: `project` (v0.3 §2: threads/projects baseline). | *"Six capabilities are the ENTIRE vocabulary"* (v0.3 §5, DECIDED) stays intact; `token ls` stays six-wide; a firm sets `structure_floor: project` on its org and gets the log's sentence. Skeleton runs the default floor as a hard `admin` check. | A seventh token capability — breaks a DECIDED sentence, and gives an agent structural power without the admin warning. |
| **F3** | **Two storage contracts.** `ItemStore` — `put / get / query / tombstone` — pluggable and delegable (sqlite → postgres+pgvector → mem0/zep). `ContainerState` — nodes, tokens, proposals and **the audit chain (`audit_append`)** — sqlite by default, postgres at Phase 5, **never delegated** to a third-party store. Blobs remain the third seam (`BlobStore`). | Amends v0.4 §11 (DECIDED): `audit_append` leaves the pluggable contract. The ledger's integrity no longer depends on whoever wrote the backend. Phase 5's postgres proves both contracts. Skeleton runs the union (`backends/base.py`); the split is a rename along the method groups already there. | One wide backend — a mem0 backend is "partial" by construction, and the un-rewritable log would sit on a third-party substrate. |
| **F4** | **The personal root is `verified-only`** (`SERVING_POLICY["user"]`). | The rarest write in the system — an owner `add --scope user:self` — costs one `trust approve`; an agent's write there is withheld until promoted instead of reaching every chain immediately. Same logic as org+ and as rules-everywhere: reach → verification. **Running.** | `serve-unverified` at the root — the personal root would be more permissive than an org while reaching further. |
| **F5** | **`BlobGrant` is minted by Trust, never by Store/Vault.** `Trust.authorize_pull(token, item) → BlobGrant{sha256, item, token, expires_at, sig} \| silence`; Store/Vault *renders* a grant into a URL and never decides. The mint is one audit event (`blob.grant`), the redemption another (`blob.pull`). **Below the inline threshold** a fetch carries the bytes inline; **above it, a stdio client receives the grant descriptor** and redeems it at the REST door (Phase 2) — never a URL it cannot use. The threshold is container config (`blobs.inline_max_bytes`, default 64 KiB) and applies by size, with `text/*` inline-eligible only. | Contract v1.0 carries `BlobGrant` from day one, so the Phase 5 Vault split and the Phase 7 preview pipeline inherit the shape; v0.4 §15 *"previews never become the leak"* has something to attach to. The first-five-minutes demo can include a PDF once REST exists. Skeleton serves inline ≤ 64 KiB `text/*` and has **no grant yet**. | Store mints URLs on its own authority (forbidden by §N / a3-store charter); or inline-only until Phase 5 (leaves the shape to be invented under Vault pressure). |

## The shapes — read these off the code, freeze them at 0.2

### 1 · ContextItem (`model.ContextItem`, `test_unknown_fields_survive_round_trip`)

`id` (ULID) · `kind` ∈ memory, preference, skill, artifact, integration, alias, rule · `scope` (node id —
location, not identity) · `key` (optional; enables cross-scope override) · `content` · `tags` ·
`provenance{actor, principal, client, derived_from, imported_from, approved_by}` ·
`trust{status, promoted_at, manifest | reason, at}` · `lifecycle{created_at, updated_at, version,
tombstoned?}` · `visibility{ring}` · **unknown fields survive round-trip** (`extra`).

`content` for text: `{body, auto_title, title_engine}`. For artifacts: `{sha256, mime, size, filename,
inline?, auto_title, title_engine}` — `inline` only when ≤ `blobs.inline_max_bytes` and `text/*` (F5);
above it the fetch carries a `BlobGrant` descriptor instead (F5 — *decided, not running*).

### 2 · Containers (`model.CONTAINER_TYPES`, `store/nodes.py`)

Types with ring rank: `inbox 0 · thread 1 · project 2 · team 3 · org 4 · exo 5 · uxo 6 · global 7`.
`enterprise` dropped (v0.5 §A). `uxo` keeps its slot, is never instantiated (R11). Roots: `user`
(the personal tree, `user:self`, not a ring) and `global`. The inbox is a node of type `inbox` under
the personal root. Threads opened by pure capture are `thread` nodes under the inbox, named by the
first item's auto-title (**SKELETON**).

Paths are computed: `user:self/org:acme/project:p`. `resolve_ref` accepts an id or a path tail;
ambiguity resolves by recency (**SKELETON**: created_at, not last activity).

Structure creation follows **F2**: a per-node `structure_floor` (default `project`); above the floor
needs `admin`. The skeleton runs the default floor as a hard check (`NodeService.create`); the
per-node policy object is the contract's to name.

### 3 · The chain (`NodeService.chain`, `test_serving_policy_…`)

Innermost first: the scope's ancestors up the tree; an `exo` ancestor **ends the tree walk** (exo
never inherits inward); then the personal root if not already present; then `global` unless
`--no-global`. This is **F1's `between`**: when the tree contains an org, `user:self` lands after it
and before `global` — org policy overrides personal preference inside org scopes, personal
preference still beats global defaults. `sovereign` (decided, not running) inserts the personal root
immediately after the scope's own ring and before the org ancestors.

### 4 · Serving policy (`model.SERVING_POLICY`, `Resolver.serve`)

`serve-unverified` at inbox/thread/project; **`verified-only` at the personal root (F4)** and from
team outward. Rules are verified-only at every scope. Quarantined items are never served. Coverage
is checked per layer; an uncovered layer is **absent**, never an error. Most-specific-wins per
`(kind, key)`; the outer value is returned with `shadowed_by` set (clients may see the full chain).

### 5 · Trust (`trust.py`, three gate tests)

Statuses `unverified · verified · quarantined`. Writes land unverified — human and agent alike.
Promotion is **human-only** (interactive principal), stamps `approved_by` and a manifest hash.
Quarantine needs `curate` and propagates via `derived_from`. The gate: audience(node) = every live
token whose coverage reaches it; delta = audience(to) − audience(from). Zero delta → move +
`gate.pass.silent {audience_delta: none}`. Nonzero → proposal `{items, from, to, audience,
audience_delta (client, role, principal), blast_radius, manifest, proposed_by, reason}`; `trust
approve <proposal>` recomputes the manifest and refuses on mismatch (status `stale`). Inward moves
with a nonzero delta cannot occur (audience only grows outward), so "inward = instant" falls out of
the delta rule rather than being special-cased — the contract should say so explicitly.

### 6 · Capabilities and principals (`model.CAPABILITIES`, `auth.py`)

`fetch < remember < organize < publish < curate < admin` — **six, and only six (F2)**; role bundles
reader/contributor/operator/curator/admin. Principals `interactive | client`. Tokens: `{id,
principal, owner, client, capabilities, scopes, created_at, last_used, revoked, expires_at}`;
`scopes` are node ids, coverage computed down the path at check time, `["*"]` for the owner.
Human-only acts are outside the vocabulary and refused to any client principal (`HumanOnly`).
`serve` refuses to run on an interactive token.

### 7 · Storage contracts (`backends/base.py`) — **F3**

The skeleton's `Backend` Protocol is the union; the freeze names two contracts along its method
groups:

- **`ItemStore`** — `put / get / query / tombstone`. Pluggable, delegable. The resolver applies
  precedence, trust and key-override above it (v0.4 §11).
- **`ContainerState`** — `put_node / get_node / list_nodes / find_root`, `put_token / get_token /
  list_tokens`, `put_proposal / get_proposal / list_proposals`, and **`audit_append / audit_last /
  audit_iter / audit_tail`**. Never delegated.
- **`BlobStore`** (third seam, already separate) — `put / stage / promote / get / exists` over
  `sha256/<hash>` and `staging/<hash>`; URL rendering for `BlobGrant`s arrives with F5.

### 8 · Event taxonomy (`ledger.EVENTS`)

`container.init · node.create · item.add · blob.put · context.fetch · blob.pull · item.move ·
gate.pass.silent · gate.propose · approval.promote · approval.execute · approval.deny ·
trust.quarantine · step_up (reserved) · token.mint · token.revoke · item.tombstone` — plus
**`blob.grant`** (F5, decided, not running). Entry: `{seq, ts, event, actor, principal, subject,
scope, details, prev_hash, hash}`; `hash = sha256(prev_hash ‖ canonical(entry minus hash))`;
genesis `0×64`. Append-only is enforced by the store (triggers) and verified by the chain
(`audit verify` exits 1 on a break).

### 9 · Container config (F1, F2, F5 — decided, not running)

The freeze introduces one config object the log already needed in three places:
`chain.personal_root` (F1) · `node.policy.structure_floor`, `org.policy.sovereign_chain` (F2) ·
`blobs.inline_max_bytes` (F5) · and R11's `step_up.window_seconds` (per ring pair, org-configurable
to zero). The skeleton has no config surface; every value above is a constant in `model.py`.

## What the skeleton does NOT do (on purpose)

No `login`/device-code (init mints the owner token) · no step-up tap (Phase 2.2) · no REST, no
Streamable HTTP (Phase 5) · no embeddings (degraded titler and substring `find`) · no `cp`, no
aliases, no `organize`, no `.xmb` · no staging semantics for agent-proposed artifacts beyond the
blob prefix · no multi-user; the audience is tokens, and `owner` is always `self` · no config
surface, no `BlobGrant`, no `sovereign` chain (F1/F3/F5 decided in text, above).

## Still open for the freeze review (0.3)

1. Recency for path disambiguation — created_at (skeleton) or last activity? (§2)
2. Auto-thread naming — first item's auto-title (skeleton), or a thread-level title pass? (§2)
3. Whether `BlobGrant.sig` is an HMAC over the descriptor with a container key, or the grant id is
   itself the bearer secret (§1, F5) — a6's call on the enumeration surface.
