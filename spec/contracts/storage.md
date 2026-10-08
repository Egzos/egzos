# Contract · Storage

**Status: frozen at 0.3 (Chief, date of merge).** Law: a change is a `contract-change` escalation to
a1p-planner, batched at a phase boundary (`spec/contracts/README.md`). The freeze is the Chief's merge of
the commit that set this line, dated by that merge; a1p-planner prepared the text and did not declare it.

**Derivation.** The walking skeleton (`chief/walking-skeleton`, `docs/build/WALKING-SKELETON.md` §7)
runs **one wide `Backend` Protocol** — `src/egzos/backends/base.py`, implemented by
`src/egzos/backends/sqlite.py`. Blobs are already a separate class, `src/egzos/store/blobs.py`.

**This document specifies a split the skeleton does not run.** Freeze decision **F3** (Chief,
2026-09-21) divides the union into two contracts along the method groups already present in
`base.py`; the third, `BlobStore`, is separate in the skeleton already. Every method set below is
verbatim from the running code — the *methods* are running, the *partition* is decided. The 0.3
review must read §1–§3 knowing it is reading a **decided split, not a running one**.

Every clause is marked **running** (observed in the skeleton), **decided, not running** (a Chief
freeze decision F1–F5 or 0.3 decision the skeleton does not yet execute). A `[0.3 · N]` marking
cites item `N` of the Chief's freeze record on #31 (2026-10-03). The open→0.3 marking the draft
carried is gone: the record answered every one.

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

**`ContainerState` may run on the operator's own self-hosted postgres. [0.3 · 5]** Operating a
substrate is not delegating to one: a container's own postgres, run by the operator who runs the
container, is not a "third-party store" in F3's sense. **Delegation to a third-party store stays
forbidden** — mem0, zep, a hosted vector database, or any service whose operator is not the
container's. The line is who operates the substrate, not which engine it is. **decided, not
running** (postgres is Phase 5).

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

**`text` is lexical on every backend. [0.3 · 6]** A delegated mem0/zep store does semantic
retrieval natively, and pgvector does it in the same query, but `ItemStore.text` stays a lexical
match everywhere, so identical calls return identical result *sets* on every conforming backend and
the resolver above never has to correct for a backend's retrieval. **Semantic search is a separate
surface on the Store side**, above this boundary (Phase 1's embeddings), never a reinterpretation of
`text`. **running** (substring match).

**Result ordering is contractual. [0.3 · 1]** `query` returns candidates ordered by **most recent
activity, then ULID**, newest first, where an item's activity is its own latest write, so `%n`
positional refs are identical between two conforming containers. A backend that orders otherwise is
non-conforming. This key orders **results** only. Since the Chief's revision of item 1 it
disambiguates nothing: an ambiguous path is refused (`container.md` §2), so no ordering here can
steer which node a reference names. **decided, not running**: the skeleton orders
`created_at DESC`.

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
promote(sha)   -> bool          # staging -> promoted, on approval
get(sha)       -> bytes | None
exists(sha)    -> bool
```

Two prefixes under the blob root: `sha256/<hash>` for promoted bytes and `staging/<hash>` for staged
bytes. `put` is idempotent — an identical write of existing content is a no-op returning the same
address. **running.**

**Dedup is unobservable. [0.3 · 41]** `put` and `stage` are internal to the storage boundary: no
external surface calls either or sees its result beyond the content address of the bytes the caller
itself supplied. **`blob.put` is emitted on every `put`**, a deduplicated one included, so neither
the response nor the ledger tells a caller whether the bytes were already stored. **`stage` does not
dedup against the promoted store**: staging bytes that are already promoted writes them to
`staging/` like any other, so staging never answers whether content exists. **running**: the skeleton's one
`put` path (`Store.add` with a file, `store/items.py`) appends `blob.put` after every `put`, whether or not
the bytes were already stored.

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

The descriptor is `{sha256, item, token, expires_at, sig}`; `sig` is an **HMAC over the descriptor
with a container key** (`context-item.md` §3, [0.3 · 45]).

### The staging prefix is invisible to resolution

**A staged blob is not reachable by any read path until `promote`.** `get` and `exists` address
`sha256/<hash>` only; there is no argument, flag or alternate method that reads `staging/`. An
agent-proposed artifact awaiting approval is therefore not merely unserved but unaddressable —
staging is not a trust status applied to a reachable blob, it is a different location. `promote`
moves the bytes into the promoted store; only then does the content address resolve. **running.**

**`promote` returns its result to its internal caller only. [0.3 · 43]** It returns `True` when
staged bytes moved to the promoted store and `False` when nothing was staged at that address,
missing and already-promoted alike, so an approval that promoted nothing does not look like one
that promoted something. The approval path is the only caller, and the result never crosses an
external boundary (§5). **a1p**, the `bool`: the record fixes who sees the result, not its shape.
**decided, not running**: the skeleton returns `None`.

**Deletion. [0.3 · 44]** v1.0 **never deletes promoted bytes** behind a tombstoned item: the audit
chain keeps referring to the address. **Staged bytes are purged** after
`blobs.staging_retention_days` (30 by default, `container.md` §8). An owner purge act for promoted
bytes is `[v1.1]`: the record defers it to the v1.1 boundary.

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

`Node` and `Proposal`, referenced by `ContainerState`'s signatures above, are defined by the
container contract (**#28**, landed) and typed in `src/egzos/_types.py`. The provisional aliases
this note once pointed at are gone; nothing here is outstanding.
