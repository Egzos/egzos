# The walking skeleton (Phase 0.1)

**Status: running, ugly, throwaway by decision** (decisions log v0.5 §H; build plan 0.1). Contracts
are frozen at Phase 0.2 **from these running shapes**, not from prose. This file is the handoff to
a1p-planner: what runs, how to run it, and every shape 0.2 must read off it — with each place the
log was silent marked **SKELETON** so the freeze decides it deliberately instead of inheriting it.

Branch: `chief/walking-skeleton`. Not merged; the contracts derive from it and Phase 1 builds
properly along the Store/Vault seam.

## Run it

```bash
uv venv --python 3.12 .venv && uv pip install --python .venv/bin/python -e ".[dev]"
scripts/demo.sh                      # add → inbox → resolve → serve --mcp → audit, end to end
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
| `egzos/backends/{base,sqlite}.py` | store → Vault at Phase 5 | the backend contract + sqlite |
| `egzos/store/{nodes,items,autotitle}.py` | store | node model, chain, add, inbox, degraded titler |
| `egzos/store/blobs.py` | store → Vault at Phase 5 | content-addressed blobs, staging prefix; no back-references |
| `egzos/ledger.py` | ledger | hash chain, verify, event taxonomy |
| `egzos/trust.py` | trust | statuses, promotion, quarantine, the gate, manifest binding |
| `egzos/resolver.py` | store (chain) / trust (policy) | chain walk, coverage, policy, key override |
| `egzos/auth.py` | trust | principals, tokens, role bundles, keychain stand-in |
| `egzos/cli/`, `egzos/mcp/` | doorman | the two doors |

## The shapes — read these off the code, freeze them at 0.2

### 1 · ContextItem (`model.ContextItem`, `test_unknown_fields_survive_round_trip`)

`id` (ULID) · `kind` ∈ memory, preference, skill, artifact, integration, alias, rule · `scope` (node id —
location, not identity) · `key` (optional; enables cross-scope override) · `content` · `tags` ·
`provenance{actor, principal, client, derived_from, imported_from, approved_by}` ·
`trust{status, promoted_at, manifest | reason, at}` · `lifecycle{created_at, updated_at, version,
tombstoned?}` · `visibility{ring}` · **unknown fields survive round-trip** (`extra`).

`content` for text: `{body, auto_title, title_engine}`. For artifacts: `{sha256, mime, size, filename,
inline?, auto_title, title_engine}` — `inline` only when ≤ 64 KiB and `text/*` (**SKELETON** threshold).

### 2 · Containers (`model.CONTAINER_TYPES`, `store/nodes.py`)

Types with ring rank: `inbox 0 · thread 1 · project 2 · team 3 · org 4 · exo 5 · uxo 6 · global 7`.
`enterprise` dropped (v0.5 §A). `uxo` keeps its slot, is never instantiated (R11). Roots: `user`
(the personal tree, `user:self`, not a ring) and `global`. The inbox is a node of type `inbox` under
the personal root. Threads opened by pure capture are `thread` nodes under the inbox, named by the
first item's auto-title (**SKELETON**).

Paths are computed: `user:self/org:acme/project:p`. `resolve_ref` accepts an id or a path tail;
ambiguity resolves by recency (**SKELETON**: created_at, not last activity).

Structure-creation permission: thread/project baseline; team/org/exo need `admin` (**SKELETON**: the
`structure` capability from v0.3 §2 is not modelled — the freeze must say whether it is a seventh
capability or a grant).

### 3 · The chain (`NodeService.chain`, `test_serving_policy_…`)

Innermost first: the scope's ancestors up the tree; an `exo` ancestor **ends the tree walk** (exo
never inherits inward); then the personal root if not already present; then `global` unless
`--no-global`. **SKELETON**: the personal root is appended after *all* tree ancestors — when the tree
contains an org, this puts `user:self` between org and global (R11's default). Whether a personal
root should ever sit *inside* an org chain at all is a freeze question.

### 4 · Serving policy (`model.SERVING_POLICY`, `Resolver.serve`)

`serve-unverified` at inbox/thread/project (and the personal root — **SKELETON**); `verified-only` from
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
approve <proposal>` recomputes the manifest and refuses on mismatch (status `stale`). **SKELETON**:
inward moves with a nonzero delta cannot occur (audience only grows outward) so "inward = instant"
falls out of the delta rule rather than being special-cased; the freeze should say so explicitly.

### 6 · Capabilities and principals (`model.CAPABILITIES`, `auth.py`)

`fetch < remember < organize < publish < curate < admin`; role bundles reader/contributor/operator/
curator/admin. Principals `interactive | client`. Tokens: `{id, principal, owner, client, capabilities,
scopes, created_at, last_used, revoked, expires_at}`; `scopes` are node ids, coverage computed down
the path at check time, `["*"]` for the owner. Human-only acts are outside the vocabulary and refused
to any client principal (`HumanOnly`). `serve` refuses to run on an interactive token.

### 7 · Backend contract (`backends/base.py`)

`put / get / query / tombstone / audit_append` as decided — **plus** what the skeleton needed:
`put_node / get_node / list_nodes / find_root`, `audit_last / audit_iter / audit_tail`,
`put_token / get_token / list_tokens`, `put_proposal / get_proposal / list_proposals`. The freeze
decides which of these belong to the backend contract and which to the store above it. Blobs are
NOT in the backend: `BlobStore` is a separate seam module (`sha256/<hash>`, `staging/<hash>`).

### 8 · Event taxonomy (`ledger.EVENTS`)

`container.init · node.create · item.add · blob.put · context.fetch · blob.pull · item.move ·
gate.pass.silent · gate.propose · approval.promote · approval.execute · approval.deny ·
trust.quarantine · step_up (reserved) · token.mint · token.revoke · item.tombstone`.
Entry: `{seq, ts, event, actor, principal, subject, scope, details, prev_hash, hash}`;
`hash = sha256(prev_hash ‖ canonical(entry minus hash))`; genesis `0×64`. Append-only is enforced by
the store (triggers) and verified by the chain (`audit verify` exits 1 on a break).

## What the skeleton does NOT do (on purpose)

No `login`/device-code (init mints the owner token) · no step-up tap (Phase 2.2) · no REST, no
Streamable HTTP (Phase 5) · no embeddings (degraded titler and substring `find`) · no `cp`, no
aliases, no `organize`, no `.xmb` · no staging semantics for agent-proposed artifacts beyond the
blob prefix · no multi-user; the audience is tokens, and `owner` is always `self`.

## Open for the freeze review (0.3)

1. Personal root inside org chains (§3) — default or never?
2. `structure` — capability or grant (§2)?
3. Backend contract boundary (§7) — nodes/tokens/proposals in or above the backend?
4. `SERVING_POLICY["user"]` — is the personal root a serve-unverified scope (§4)?
5. Inline blob threshold and the shape of "signed URL" issuance through Trust's check (§1).
