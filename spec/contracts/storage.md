# Contract · Storage

**Status: drafted — awaiting the Phase 0.3 freeze review.** Not law yet. The freeze is declared by
A6 and the Chief personally (build plan 0.3); a1p-planner prepares, it does not declare.

**Derivation.** The walking skeleton (`chief/walking-skeleton`, `docs/build/WALKING-SKELETON.md` §7)
runs **one wide `Backend` Protocol** — `src/egzos/backends/base.py`, implemented by
`src/egzos/backends/sqlite.py`. Blobs are already a separate class, `src/egzos/store/blobs.py`.

**This document specifies a split the skeleton does not run.** Freeze decision **F3** (Chief,
2026-09-21) divides the union into two contracts along the method groups already present in
`base.py`; the third, `BlobStore`, is separate in the skeleton already. Every method set below is
verbatim from the running code — the *methods* are running, the *partition* is decided. The 0.3
review must read §1–§3 knowing it is reading a **decided split, not a running one**.

Every clause is marked **running** (observed in the skeleton), **decided, not running** (a Chief
freeze decision F1–F5 the skeleton does not yet execute), or `[OPEN→0.3]` (the freeze review must
settle it — deliberately not decided here).

## 1 · Three contracts, not one (F3)

| contract | method groups | delegable to a third party? |
|---|---|---|
| `ItemStore` | items | **yes** — sqlite → postgres+pgvector → mem0/zep |
| `ContainerState` | nodes, tokens, proposals, **the audit chain** | **never** |
| `BlobStore` | content-addressed bytes, staging | no (own substrate) |

**decided, not running** — the skeleton's `Backend` Protocol is the union of the first two.
The split introduces no method, removes none, and renames none.

### Why `audit_append` sits in `ContainerState`

`audit_append / audit_last / audit_iter / audit_tail` belong to `ContainerState`, **not** to the
pluggable contract, because **the ledger's integrity must not depend on whoever wrote the backend**.
A delegated item store is a third party's code holding a third party's substrate; an append-only
hash chain that lives there is append-only at that third party's discretion. Append-only is enforced
by the store — triggers in the sqlite backend, no update or delete path at all — and verified
independently by walking the chain (`events.md` §4). Neither half of that survives delegation.

**This amends v0.4 §11 (DECIDED)**, which placed `audit_append` in the single pluggable backend
contract. The amendment is stated here rather than left to be discovered: the freeze review is
reading a change to a previously decided sentence, and should review it as one. The second-order
effect the Chief named: a mem0 or zep backend is no longer "partial by construction", because the
part it could not honestly implement is no longer in the contract it implements.

`[OPEN→0.3]` **Whether `ContainerState` may be delegated to a *self-hosted* postgres** — Phase 5
puts postgres behind both contracts, and a container's own postgres is not a "third-party store" in
F3's sense. F3 says "postgres at Phase 5, never delegated to a third-party store" and does not draw
the line between *operating* a substrate and *delegating* to one. The freeze review should draw it,
because Phase 5 is where the distinction first has to hold.

## 2 · `ItemStore` — pluggable, delegable

```
put(item)                            -> None
get(item_id)                         -> ContextItem | None
query(scopes, *, kinds=None, key=None, statuses=None, text=None,
      include_tombstoned=False)      -> list[ContextItem]
tombstone(item_id)                   -> bool
```

**running** (as `Backend.put / get / query / tombstone`).

### The division of labour

**The backend returns candidates; the resolver applies precedence, trust and key-override above it**
(v0.4 §11). `query` is a filter, not a decision. It does not walk the chain, does not rank by ring,
does not apply the serving policy, and does not resolve `(kind, key)` collisions — the resolver does
all four, above the storage boundary (`container.md`). A backend that ranked results would be making
trust decisions inside a substrate a third party may have written. **running.**

| filter | meaning |
|---|---|
| `scopes` | node ids; an empty iterable returns an empty list, never all items |
| `kinds` | restrict to these `kind` values (`context-item.md` §2) |
| `key` | exact match on the override key |
| `statuses` | restrict to these trust statuses (`context-item.md` §5) |
| `text` | free-text match over the item body |
| `include_tombstoned` | default `False`; tombstoned items are excluded |

`text` is a **substring** match in the skeleton (`doc LIKE`), deliberately degraded — embeddings are
Phase 1 and Store's, not the backend's. **running.**

`[OPEN→0.3]` **Whether `text` stays lexical at this boundary.** A delegated mem0/zep store does
semantic retrieval natively, and pgvector does it in the same query; pushing `text` down would mean
identical calls return different result *sets* per backend, which the resolver above cannot correct
for. Either `text` is contractually lexical and semantic search is a separate Store-side surface, or
the contract admits per-backend retrieval and says so. No source settles this and it is the
pluggable contract's central question — not decided here.

`[OPEN→0.3]` **Whether result ordering is contractual.** The skeleton orders `created_at DESC`. If
ordering is the backend's choice, the resolver's recency tie-break is non-deterministic across
backends, and `%n` positional refs differ between two conforming containers. This is the same
unsettled question as path disambiguation by recency (`WALKING-SKELETON.md` §"still open" item 1) at
a different layer; the review should settle both together.

### `tombstone` and `get`

Deletion is a tombstone, not a removal — the audit chain must keep referring to something
(`context-item.md` §6). `tombstone` returns `True` when an item was found and marked, `False` when
it was not found. `get` on a tombstoned item returns `None`: to every read path a tombstoned item is
**a miss**, not a distinguishable state. **running.**

That boolean is **internal to the storage boundary and MUST NOT be reflected to a caller** — see §5.

TODO(a1p): `put` is unconditional replace (`INSERT OR REPLACE`) with no return and no
compare-and-swap parameter, while `lifecycle.version` increments on every mutation
(`context-item.md` §6). Two concurrent writers therefore lose an update silently and the version
counter records only one of them. No source names a concurrency model for the storage boundary. The
freeze should either put the expected-version argument in the signature or state that serialising
writes is the caller's problem — inventing either one here would be guessing in a contract.

## 3 · `ContainerState` — never delegated

```
put_node(node)                       -> None
get_node(node_id)                    -> Node | None
list_nodes(parent=None, type=None)   -> list[Node]
find_root(type)                      -> Node | None

put_token(token)                     -> None
get_token(token_id)                  -> Token | None
list_tokens()                        -> list[Token]

put_proposal(proposal)               -> None
get_proposal(proposal_id)            -> Proposal | None
list_proposals(status=None)          -> list[Proposal]

audit_append(entry)                  -> AuditEntry
audit_last()                         -> AuditEntry | None
audit_iter()                         -> Iterator[AuditEntry]
audit_tail(n)                        -> list[AuditEntry]
```

**running** (all fourteen, as methods of the skeleton's `Backend`). sqlite by default, postgres at
Phase 5. **Never delegated to a third-party store.**

`audit_append` receives an entry **without** `seq`: the ledger computes `hash` over the entry minus
`hash` and minus `seq`, and the store assigns `seq` and returns the stored entry
(`events.md` §3). The store appends; it never computes the chain. **running.**

Node and chain semantics — container types, ring ranks, the chain walk, the serving policy, the
gate and the container config object — are `container.md`'s, not this document's. This document
fixes only how those shapes are **persisted**.

## 4 · `BlobStore` — content-addressed, staged

```
put(data)      -> sha256        # promoted store, dedup by construction
stage(data)    -> sha256        # staging prefix, invisible to resolution
promote(sha)   -> None          # staging -> promoted, on approval
get(sha)       -> bytes | None
exists(sha)    -> bool
```

Two prefixes under the blob root: `sha256/<hash>` for promoted bytes and `staging/<hash>` for staged
bytes. `put` is idempotent — an identical write of existing content is a no-op returning the same
address. **running.**

### Store/Vault never mints a URL on its own authority

**The blob store issues nothing.** It **renders** a `BlobGrant` minted by Trust
(`Trust.authorize_pull(token, item) -> BlobGrant | silence`, **F5**) into a URL, and it decides
nothing about whether the grant should exist. **Signed-URL issuance passes Trust's capability check
— artifact download IS fetch** (decisions log, DECIDED). A `BlobStore` method that consulted a token
would be Store deciding a Trust question inside a module that is about to move to Vault.

The mint and the redemption are **two separate audit events**: `blob.grant` when Trust mints the
descriptor, `blob.pull` when the bytes are actually served (`events.md`). One without the other is a
finding, not a shortcut. **decided, not running** — the skeleton serves `text/*` inline at or below
64 KiB, records every pull, and has no grant.

The descriptor is `{sha256, item, token, expires_at, sig}`; `sig`'s shape is `[OPEN→0.3]` and is
A6's call on the enumeration surface (`context-item.md` §3).

### The staging prefix is invisible to resolution

**A staged blob is not reachable by any read path until `promote`.** `get` and `exists` address
`sha256/<hash>` only; there is no argument, flag or alternate method that reads `staging/`. An
agent-proposed artifact awaiting approval is therefore not merely unserved but unaddressable —
staging is not a trust status applied to a reachable blob, it is a different location. `promote`
moves the bytes into the promoted store; only then does the content address resolve. **running.**

`[OPEN→0.3]` **`promote`'s behaviour on a missing or already-promoted address.** The skeleton is
silent in both cases: `promote` of an unstaged sha does nothing and reports nothing. Silence is
right at an external boundary (§5) but this caller is the approval path, and an approval that
promoted nothing should not look like an approval that promoted something. Whether `promote` returns
a result to its *internal* caller is not decided here.

TODO(a1p): no source names a deletion or garbage-collection path for blobs. Tombstoning an artifact
item leaves its bytes addressable forever, and abandoned staged bytes are never reclaimed. Whether
that is intended (the audit chain keeps referring to the address) or an omission is the review's to
say.

## 5 · Silence-not-errors at the storage boundary

**A miss and a not-permitted are indistinguishable to the caller.** The contract defines **no error
shape that separates them**, because a distinguishable "exists but forbidden" is enumeration by
another name — the API would be answering a question about content the caller cannot see.

Concretely, and binding on every implementation:

1. `get`, `get_node`, `get_token`, `get_proposal` and `BlobStore.get` return **`None`** for absent,
   tombstoned, and out-of-coverage alike. No exception, no status, no distinct null.
2. `query` and the `list_*` methods return a **shorter list**. An uncovered scope contributes
   nothing; it is never an error and never a marked-absent entry.
3. `tombstone`'s `False` and `exists`'s `bool` are **internal to this boundary**. No surface — CLI,
   MCP, REST or web — may reflect either to an external caller as a distinguishable outcome, because
   both are existence oracles over content the caller may not hold.
4. `exists` in particular MUST NOT be reachable from any externally-driven path. Content addresses
   are guessable for known content; a caller who can probe `exists` for an arbitrary `sha256` learns
   whether this container holds a specific known document without holding any capability over it.
5. The single exception is `audit verify`, which reports a chain break specifically and exits
   non-zero — the audience there is the owner inspecting their own container, not a caller probing
   it (`events.md` §4.1).

**running** for (1) and (2) — the skeleton returns `None` and short lists throughout, and defines no
error type at this boundary.

TODO(a1p): (3) and (4) are a1p's reading of the trust posture applied to two signatures the skeleton
exposes without naming their permitted callers. No source restricts who may call `exists`. If the
review disagrees, the alternative is to remove `exists` from the contract entirely and let `get`'s
`None` carry the answer — which costs a read of the bytes.

## 6 · The Store/Vault seam (R5)

`BlobStore` and the backends **move to Vault whole at Phase 5**, so the split is a rename, not a
refactor (R5). Vault takes the blob store, the backends (sqlite, postgres+pgvector) and the `.xmb`
core; Store keeps nodes, resolver, find/`%n`, embeddings and auto-title.

| today | owner | after Phase 5 | owner |
|---|---|---|---|
| `src/egzos/backends/{base,sqlite}.py` | a3-store | `src/egzos/vault/backends/**` | a3-vault |
| `src/egzos/store/blobs.py` | a3-store | `src/egzos/vault/blobs.py` | a3-vault |
| `src/egzos/store/{nodes,items,autotitle}.py` | a3-store | unchanged | a3-store |
| `src/egzos/resolver.py` | a3-store | unchanged | a3-store |

**The Protocol definitions themselves do not move.** `ItemStore`, `ContainerState` and `BlobStore`
are declared in `src/egzos/_types.py` (shared, a1p-planner's), and only their *implementations* live
under `backends/` and `blobs.py`. Store, Trust and Ledger consume `ContainerState` — nodes, tokens,
proposals and the chain are all read through it — and none of them may acquire an import of Vault's
package to get a type. This is what makes Phase 5 a rename: the seam is already the type, and the
type already sits above both modules.

The binding requirement, enforceable in review on every Phase 1–4 PR:

- **No back-references.** `blobs.py` and `backends/**` import nothing from `store/nodes.py`,
  `store/items.py` or `resolver.py`. Today `blobs.py` imports only `hashlib` and `pathlib`, and
  `backends/base.py` imports only the shared model — that is the property to hold, not to restore.
- Blob addressing is by `sha256` alone. The blob store never resolves an item id, a scope or a node.
- A PR that gives either module knowledge of the node tree breaks R5 whether or not it passes tests.

**running** for the current import graph; **decided, not running** for the Phase 5 destinations.

## 7 · What this document does not fix

Item shape and the blob's metadata item → `context-item.md`. Container types, the chain, the serving
policy, the gate and the container config object (`blobs.inline_max_bytes`) → `container.md`.
Capabilities, principals, tokens and `Trust.authorize_pull` → `capabilities.md`. The chain's hash
rule, `canonical` and the event list → `events.md`.

The postgres+pgvector and mem0/zep backends themselves are Phase 5. This document fixes only the
contract they must satisfy.

TODO(a1p): `Node` and `Proposal` are referenced by `ContainerState`'s signatures and are **issue
#28's** to define (container contract). The signatures above are final; only the referent is
outstanding. `src/egzos/_types.py` carries provisional aliases until #28 lands, and #30 removes them.
