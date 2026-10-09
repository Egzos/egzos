# Contract · Storage

**Status: frozen at 0.3 (Chief, 2026-10-08).** Law: a change is a `contract-change` escalation to
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
carried is gone from `spec/contracts/` and `src/`: the record answered every one. The design specs
still carry the retired marker; design-gap #157 tracks their revision by A2 (`README.md`).

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

## 3.1 · The authorization server's state — `ASState` and `ASGateState`

**Status of this section: draft binding (a1p), not frozen.** Added at the Phase 2 boundary on
`contract-change` **#173** (filed by a3-trust from #166). The rest of this document is frozen at 0.3
and this section changes none of it: §1's table, §3's fourteen methods and `ContainerState` itself
are untouched. Where this section and a frozen clause disagree, the frozen clause governs and the
disagreement is a finding against this section. **decided, not running** throughout: the skeleton has
no authorization server.

`authorization-server.md` requires seven kinds of durable state that §3 named no method group for.
They are declared as **two Protocols beside `ContainerState`**, in `src/egzos/_types.py` like the
other three, so that the partition question below can be answered without reshaping either:

| Protocol | groups | source clause in `authorization-server.md` |
|---|---|---|
| `ASState` | clients · codes · device authorizations · refresh chains · decided requests | §5, §2, §3, §9.2, §11.4 |
| `ASGateState` | interactive sessions · throttle counters | §10.1, §11.0 / §12 |

`ASGateState` is the two objects that gate a request **before** evaluation (§11.0's substeps); that is
the line the partition question falls on, and the only reason for the second Protocol.

```
# ASState — clients (§5; registration is an owner act and writes client.register)
put_client(registration)                  -> None    # add and amend
get_client(client_id)                     -> ClientRegistration | None
remove_client(client_id)                  -> bool    # internal
# codes (§2)
put_code(record)                          -> None
consume_code(code_hash)                   -> AuthorizationCodeRecord | None
# device authorizations (§3, §11.8)
put_device(record)                        -> None    # insert-only
poll_device(device_code_hash, at)         -> DeviceAuthorizationRecord | None
get_device_by_user_code(user_code_hash)   -> DeviceAuthorizationRecord | None
decide_device(device_code_hash, grant)    -> bool    # internal; grant None = denied
consume_device(device_code_hash)          -> DeviceAuthorizationRecord | None
# refresh chains (§9.2)
put_refresh(record)                       -> None
redeem_refresh(refresh_hash)              -> RefreshRecord | None
family_of_token(token_id)                 -> str | None
revoke_family(family_id)                  -> list[str]   # internal
# decided requests (§11.4)
put_decided(record)                       -> None
get_decided(request_key)                  -> DecidedRequestRecord | None
claim_resubmission(session_hash, request_key) -> bool    # internal

# ASGateState — interactive sessions (§10.1)
put_session(record)                       -> None
get_session(session_hash)                 -> SessionRecord | None
touch_session(session_hash, at)           -> bool    # internal
end_session(session_hash)                 -> bool    # internal
# throttle counters (§11.0, §12)
throttle_incr(surface, bucket_key, window_key)  -> int
throttle_count(surface, bucket_key, window_key) -> int
```

**Never delegated.** Both Protocols are `ContainerState`-class by F3's own reason: this is state that,
edited around Trust, forges presence (a session), un-decides an authorization (a decided-request
record), lifts §12's only bound on the chain (a throttle counter) or widens the redirect allowlist (a
client entry). No method here is offered to an `ItemStore` backend. Operating the substrate is still
not delegating it ([0.3 · 5], §1).

**Credential values are stored as hashes, never the value.** The authorization code, the
`device_code`, the refresh-token value and the session identifier each reach the store only as the
lowercase hex sha256 of the whole value, as `auth.py` already does for `Token.secret_hash`. Each
carries §9.1's entropy floor, so an unkeyed hash of it is not reversible.

The `user_code` is the exception. It has 20⁸ ≈ 2³⁴·⁶ values (§11.8, [0.3 · 20]), so an unkeyed
sha256 of it can be inverted by enumeration from a store leak, a backup or a replica. The `/device`
throttle bounds only online guessing. So **`user_code_hash` is the lowercase hex HMAC-SHA256 of the
normalized `user_code` under a container-held key** (the *device-code key*), never a bare sha256. A
store read alone then yields no live `user_code`. The key MUST NOT be held in the store beside the
hashes it keys, since a key that leaks with the store protects nothing. TODO(a1p) #143 / #165 item 4: how the device-code key is provisioned at `init`,
where it is held and how it rotates is not decided here. It joins the login secret (#143) and the
grant key (#165 item 4) in the same batch. Rotating it orphans every pending device authorization,
which expires within §3's lifetime anyway.

**No method takes a credential value.** Every key parameter that names one is a `*_hash`, and no
record carries a field that holds one. A backend cannot store a code or a refresh token in the clear,
because it is never handed one.

**Single use is the store's, atomically.** Each of these is one indivisible step against concurrent
callers on the same key — of two concurrent calls, exactly one observes the state before the change:

1. `consume_code` returns the record and invalidates it in the same step; every later call returns
   `None`. It does **not** judge expiry or the §2 bindings — Trust re-checks `client_id`,
   `redirect_uri`, `code_challenge` and `expires_at` on what it returns — so the code is spent on the
   first redemption attempt, successful or not (§2).
2. `consume_device` is the same step for a decided device authorization at the token endpoint. It
   returns `None` while the authorization is still pending, so a poll before the decision spends
   nothing. `decide_device` moves a record from pending exactly once and returns `False` if it was
   not pending (§3 mitigation 3: one approval, one request).
   **The record is never rewritten whole.** `put_device` is insert-only: a put on a
   `device_code_hash` that already exists changes nothing. After the insert, the record changes only
   through three atomic methods, and each touches only its own fields. `poll_device` sets
   `last_polled_at` to `at`. `decide_device` sets `decision` and `grant`. `consume_device` spends the
   record. `poll_device` is the poll's read, and it returns the record **as it stood before the
   call**, so Trust compares the prior `last_polled_at` with `at` for §3 mitigation 1's
   `slow_down`. A poll can therefore never write back a stale `pending` copy over a concurrent
   `decide_device`, so one authorization cannot be decided twice.
   **The request is stored at insert, so `/device` can show it.** `put_device` writes two fields
   that no later method touches. `requested` holds the `capabilities` and `scopes` that §7 expanded
   from the device client's `scope` at the device authorization endpoint. That is what §3 mitigation 2's
   screen renders, and §3 mitigation 3 lets an approval grant only that. `decide_device`'s `grant`
   carries the same capabilities and scopes, adding only the principal (§10.3) and the clamped expiry
   (§11.5), per §11.2 consequence 1. An unparseable `scope` is refused at the endpoint (§11.2
   consequence 2), so no record holds one. `requester_hint` is §11.8's client-supplied device or
   host name, **unverified**. It is truncated to `AS_REQUESTER_HINT_MAX_CHARS` (64, **a1p**, draft)
   before the insert and never refused for its length, since a refusal would branch on it. It is no
   lookup key, enters no `request_key`, and no record or event field that reads as verified ever
   carries it.
3. `redeem_refresh` marks the record redeemed and returns it **as it stood before the call**. A
   returned record with a non-null `redeemed_at` is reuse, and Trust then calls `revoke_family`
   (§9.2 rotation clause 2). The store detects nothing; it reports the prior state truthfully.
4. `revoke_family` revokes every refresh record in the family **and** every `Token` those records
   name, in one step on one substrate, and returns the revoked `Token.id`s to its internal caller for
   `token.revoke` ([0.3 · 30]). A family half-revoked by a crash is the failure rotation exists to
   prevent. This couples the two Protocols: **the `ASState` implementer MUST be the `ContainerState`
   implementer, on one substrate**, under either partition answer. No backend may split them, because
   `revoke_family` writes `ContainerState`'s `Token` records. Whether revoking one access token by `Token.id` revokes its family is not decided here;
   `family_of_token` only makes the family id available to the entry.
5. `claim_resubmission` returns `True` exactly once per `(session_hash, request_key)` that
   `put_decided` recorded, and `False` otherwise — §11.0 substep 1's "first re-submission on the
   deciding session". `get_decided` is the request-keyed read after the counter (§11.4).
6. `throttle_incr` increments and returns the new count. It names no rate and no window length
   (#141): `window_key` is an opaque value Trust derives, and so is `bucket_key` — the constant
   container-global bucket or a digest of the transport source address (§11.0, [0.3 · 24]). A network
   identifier reaches the store only as Trust chooses to key it and never enters the chain.

**Silence-not-errors (§5) applies unchanged, to the plain getters and to what reaches an external
caller.** The plain getters (`get_client`, `get_device_by_user_code`, `get_decided`, `get_session`,
`family_of_token`) return `None` for absent, expired, spent and revoked alike. The consumers do not
judge, so they return more than that, and all of it stays inside Trust. `consume_code` returns the
record without judging its expiry or its §2 bindings (rule 1). `redeem_refresh` and `poll_device`
return the record as it stood before the call (rules 2 and 3), so a non-null `redeemed_at` stays
visible and reuse stays detectable. An implementation that collapses an already-redeemed refresh
record to `None` silences §9.2's reuse detection, and that is a finding. What Trust then sends an
external caller is §5's single shape for absent, expired, spent and revoked. Every `bool` and
`revoke_family`'s list are internal to this boundary as well, and MUST NOT be reflected to an
external caller. `get_client` is §11.1's one keyed read, and
there is **no client listing method** (§11.1, §7.1). TODO(a1p): an owner's `client ls` at the CLI is
not in any contract; if a3-doorman needs one, it is a `contract-change`, not a method added here.

**Client registrations live here, not in `ContainerConfig`. a1p**, answering #173 question 4.
`authorization-server.md` §5's "container config" is read as the container's own owner-written state,
not the `ContainerConfig` object: a registry loaded from a config file would let an allowlist change
land without `client.register`, which [0.3 · 31] makes an audit event. `ContainerConfig` gains no
`clients` key.

**Record shapes** (`AuthorizationCodeRecord`, `DeviceAuthorizationRecord`, `RefreshRecord`,
`DecidedRequestRecord`, `SessionRecord`, the `ASGrant` they carry and the `DeviceRequest` a device
record carries) are typed in `_types.py`, each
field cited there to the clause that requires it. They are **a1p**'s, drafted from those clauses; a
field a3-trust finds missing is an escalation on #173's thread, not a field added in a builder's PR.

**Implementations.** The sqlite implementation of `ASState` is in `backends/sqlite.py`, and so is
`ASGateState`'s **only if** the partition below is answered (A). Under (B), `ASGateState` is an
in-process class and gets no table. Until the Chief answers, a3-store builds no `ASGateState` table.
Either way the sqlite implementation is a3-store's (§6) and moves to Vault at Phase 5 with the rest
of the backends. a3-trust consumes the Protocols and adds no table itself. **a1p**, answering #173
question 5.

TODO(chief) #173 — **the partition: is `ASGateState` `ContainerState`-class too, or process memory?**
`ASState` is durable under either answer; only the sessions and the throttle counters are in question.

- **(A) All seven are container state, persisted with `ContainerState` on the same substrate.** A
  restart lifts nothing: throttles hold and sessions survive. Costs: a store write on every throttled
  request and on every page view that extends a session (`touch_session`), on the same sqlite file as
  the chain; transport-address digests and session hashes persisted on disk; and a session survives a
  restart the owner may have expected to sign them out.
- **(B) Sessions and throttle counters are process memory**, implemented by an in-process
  `ASGateState`. Nothing extra on disk, no write amplification. Costs: **every restart lifts every
  throttle**, so anyone who can cause or wait for a restart resets §12's only bound on the chain's
  growth and the `user_code` attempt bound; §12's engage/release pairs lose the release of any window
  open at the restart; every restart signs the owner out; and a container served by more than one
  process holds one counter per process, multiplying every bound by the process count.

The interface fits either answer: under (A) the backend that implements `ContainerState` implements
both Protocols; under (B) it implements `ASState` and an in-process class implements `ASGateState`.
No signature changes between the two.

Open note beside the partition, not a method: `ASGateState` has no bulk form. `end_session` and the
throttle counters are per key. Nothing ends every session, or clears every throttle bucket, tied to
one principal or one client in a single step, as `revoke_family` does for a refresh chain. A
principal or client found compromised therefore has no sweep on this half of the state. Whether one
is needed, and its shape, depends on the partition: under (B) a restart is a crude sweep. It is
raised on #173 with the partition and is not added here.

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

§3.1's `ASState` and `ASGateState` are a draft binding on #173, not part of the 0.3 freeze; their
partition is the Chief's TODO there.

`Node` and `Proposal`, referenced by `ContainerState`'s signatures above, are defined by the
container contract (**#28**, landed) and typed in `src/egzos/_types.py`. The provisional aliases
this note once pointed at are gone; nothing here is outstanding.
