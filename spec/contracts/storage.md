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
freeze decision F1–F5 or 0.3 decision, or from contract v1.1 a v0.7 one, the skeleton does not yet
execute) or **a1p** (the operator's binding of a decision, a proposal the review reads as one, as in
`identity.md`). A `[0.3 · N]` marking
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

**A managed postgres that only the container's operator administers is the operator's own
substrate** under [0.3 · 5], so `ContainerState` may live on Supabase's postgres, in the container's
own project (§3.7). The database vendor joins the ledger's trust path, as v0.7 §T records for the
identity provider. **decided, not running** (v0.7 §AF). For a container egzos hosts, that operator
is egzos: egzos, the vendor and the host join its trust path, for reading as for writing. The chain
records acts, not the state they leave: tokens, grants, registrations and config are rows it does
not cover, so whoever can write the database can grant itself the container, and whoever can write
the object store can substitute bytes until `get` checks them (§4). The chain is hashed, not signed:
`audit verify` catches an edit, an insertion or a removal only while every later entry is left as
it was. An entry re-hashed with every entry after it verifies, as does a chain whose last entries
are gone, a restore to an earlier point included, or whose `seq` is renumbered (`events.md` §3). An
outside anchor, each place recording the cloud's head when it pulls, is what would catch those;
the Chief has asked that it come with sync (v0.7 §V, §AF). **a1p** (v0.7 §AF), the reach as stated here.

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
`created_at DESC`. **Items written in the same second fall by id, newest first, on every backend**
(`created_at DESC, id DESC`), so sqlite and postgres list alike, ties included. **decided, not
running** (v0.7 §AF); ordering by an item's latest write rather than its creation stays not running.

### `tombstone` and `get`

Deletion is a tombstone, not a removal — the audit chain must keep referring to something
(`context-item.md` §6). `tombstone` returns `True` when an item was found and marked, `False` when
it was not found. `get` on a tombstoned item returns `None`: to every read path a tombstoned item is
**a miss**, not a distinguishable state. **running.**

That boolean is **internal to the storage boundary and MUST NOT be reflected to a caller** — see §5.

**`put` stays an unconditional replace; a read-then-write is serialised by its caller, inside one
`atomic()` block.** `put` has no return and no expected-version argument, while `lifecycle.version`
increments on every mutation (`context-item.md` §6). A read-then-write that must not lose an update
runs inside one block, which holds the container's one write lock from before its first read
(§3.6), so two such writers run one after the other and the version counter records both. A
delegated `ItemStore` (§1) is outside that lock, and none conforms until its specification
serialises a read-then-write on one item as `atomic()` does and lets an act's item writes roll back
with the act's chain entry. **a1p** (v0.7 §AF), closing the question the freeze left open here.

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
(`events.md` §3). The store appends; it never computes the chain. **running.** A second entry
after the same `prev_hash` is refused with `ChainConflict` (§3.6), never the driver's own error, so
the ledger re-chains. **running.**

Node and chain semantics — container types, ring ranks, the chain walk, the serving policy, the
gate and the container config object — are `container.md`'s, not this document's. This document
fixes only how those shapes are **persisted**.

## 3.1 · The door's throttle state — `ThrottleState`

**Status of this section: contract v1.1** (`identity.md` §9). It replaced the draft binding #173 added
for the authorization server, `ASState` and `ASGateState`, when that server was retired: its clients,
codes, device authorizations, refresh chains, decided requests and interactive sessions went with
its code. The rest of this document is frozen at 0.3 and this section changes none of it.

What stays is the throttle the REST door runs on (`rest.md` §2 item 7), declared as one Protocol
beside `ContainerState`, in `src/egzos/_types.py` like the other three:

```
# ThrottleState — counters (rest.md §2 item 7); keys are the door's, opaque to the store
throttle_incr(surface, bucket_key, window_key) -> int    # increments and returns the new count, atomically
throttle_count(surface, bucket_key, window_key) -> int   # reads without incrementing; 0 for an unseen key
throttle_buckets(surface, window_key) -> list           # every (bucket_key, count) of one window
throttle_windows(surface) -> list                       # every window with a counter
throttle_forget(surface, window_key) -> None            # drops a closed window's counters
```

No rate and no window length live here: `_types.py`'s `AS_THROTTLE_RATES` and
`AS_THROTTLE_WINDOW_SECONDS` carry them, and the door reads them. A network identifier may key a
bucket and never enters the chain. A closed window's counters are forgotten once its release and
tally are appended and an hour has passed, so the table holds at most a recent hour of windows.
The per-source and `window_key` digests are keyed by a per-container secret, `throttle.key` in the
container's home (0600); it is the throttle's alone and does not travel with an export or a sync:
a place makes its own. **a1p** (a1r on #288).

**The partition: `ContainerState`-class. decided** (the Chief on #173, option (A), 2026-10-09). The
counters are durable and never delegated: the backend that implements `ContainerState` implements
`ThrottleState`, on the same substrate, never in process memory. A throttle that holds still holds
after a restart, its window's release entry still appends, and a container served by more than one
process keeps one counter, not one per process. The sqlite implementation is in
`backends/sqlite.py` and is a3-store's (§6). The cost, accepted with the decision: a store write on
every throttled request, and the transport-address digests that key the per-source buckets
persisted on disk.

## 3.2 · Who may call, and the settings — `IdentityState` and `ConfigState`

**Status of this section: contract v1.1** (`identity.md` §4, `container.md` §8). Two Protocols beside
`ContainerState`, in `src/egzos/_types.py`, implemented by the backend that implements it, on the
same substrate and never delegated (F3), as §3.1's counters are. **a1p.**

```
# IdentityState — identity.md §4's two records; the getters return revoked records too
put_user_grant(grant)                            -> None             # insert or replace, keyed on sub
get_user_grant(sub)                              -> UserGrant | None
list_user_grants()                               -> list[UserGrant]
put_agent_registration(registration)             -> None             # keyed on (client_id, sub)
get_agent_registration(client_id, sub)           -> AgentRegistration | None
list_agent_registrations(client_id=None)         -> list[AgentRegistration]

# ConfigState — container.md §8's object as set, wire key -> value
get_config()                                     -> dict             # a key never set is absent
put_config(key, value)                           -> None
```

- **A revoked record is kept, marked `revoked`.** The caller judges liveness on every request
  (`identity.md` §3 check 7), and the record's history reads back. No method deletes one.
- **No column holds a credential.** A grant names a provider user id (`sub`) and a registration an
  OAuth `client_id`; neither is a secret, and no token value or hash is stored here.
- **A config key never set is absent**, and the reader serves `CONTAINER_CONFIG_DEFAULTS` for it.
  Absence is tested by absence, never by truthiness (`container.md` §8): an empty string set is a
  value.
- **The writes are the caller's to audit.** `identity.grant`, `identity.revoke` and `config.set` are
  appended by the code that decides the act, in the same transaction as the write.

## 3.3 · The confirm's challenges — `ConfirmState`

**Status of this section: contract v1.1** (`rest.md` §4.2). One Protocol beside `ContainerState`, on
its substrate and never delegated (F3). **a1p.**

```
# ConfirmState — rest.md §4.2's challenges and §4.3's credentials
put_challenge(challenge)                         -> None
spend_challenge(challenge_id)                    -> ConfirmChallenge | None   # marks it spent; returns it as it stood
forget_challenges(expired_before)                -> None                      # drops challenges expired before then
put_credential(credential)                       -> None                      # insert or replace, keyed on id
get_credential(credential_id)                    -> ConfirmCredential | None
list_credentials(person=None)                    -> list[ConfirmCredential]   # removed ones included
```

- **A challenge is spent once, atomically.** Of two concurrent spends of one challenge, exactly one
  sees it unspent; the other sees `spent` and is refused (`rest.md` §4.2 item 3). A spend that
  concludes in a refusal spends it too (item 5). A challenge is kept a day past its expiry, so a
  late second leg still reads as `spent` or `stale`, and is then forgotten; one never issued and one
  forgotten are both `stale`.
- **No column holds a secret.** A challenge is a random value bound to the request that asked for
  it: the principal, the act, its subject and destination, and the audience delta. A confirm
  credential is a WebAuthn public key, which verifies an assertion and proves nothing alone; it is
  never served (`rest.md` §4.3's shape omits it). A removed credential is kept, marked `removed`.

## 3.4 · Uploads — `UploadState`

**Status of this section: contract v1.1** (`rest.md` §4.4). One Protocol beside `ContainerState`, on
its substrate and never delegated (F3). **a1p.**

```
# UploadState — rest.md §4.4's uploads
put_upload(upload)                               -> None                  # insert or replace, keyed on id
get_upload(upload_id)                            -> UploadRecord | None
list_uploads(principal=None)                     -> list[UploadRecord]    # discarded ones included
spend_upload(upload_id, step)                    -> bool                  # step: bytes · item; True for the one call that marks it
```

- **Each step is spent once, atomically.** Of two concurrent spends of one step of one upload,
  exactly one is `True` (`rest.md` §4.4 item 3); the caller writes the outcome with `put_upload` in
  the same transaction, so a spend whose act fails rolls back with it.
- **A discarded upload is kept, marked `discarded`**, and its history reads back. No method deletes
  one. No column holds a secret: an upload names its principal, scope, display name, type, size
  and digest.

## 3.5 · Spent grants — `GrantState`

**Status of this section: contract v1.1** (`rest.md` §6). One Protocol beside `ContainerState`, on
its substrate and never delegated (F3). **a1p.**

```
# GrantState — rest.md §6's spent grants, keyed on the sha256 of a descriptor's sig
spend_grant(sig_hash, expires_at)                -> bool    # True for the one call that records it
forget_grants(expired_before)                    -> None    # drops the records of grants expired before then
```

- **A grant is spent once, atomically.** Of two concurrent spends of one grant, exactly one is
  `True` (`rest.md` §6 check 4). A spend commits on its own and is never rolled back: a redemption
  refused at a later check has still spent its grant.
- **No column holds a secret.** A record is the sha256 of a `sig`, never the `sig`, and the
  grant's `expires_at`; it is kept at least a lifetime past that (`rest.md` §6). The key that signs
  grants is not here: it is a file in the container's home that no export carries (`rest.md` §6).

## 3.6 · One writer per container — `Transactional`

**Status of this section: contract v1.1, a1p** (enacted with v0.7 §AF). One Protocol beside
`ContainerState`, in `src/egzos/_types.py`, implemented by the backend that implements it, on its
substrate and never delegated (F3). It is not one of §1's three contracts, so `STORAGE_CONTRACTS`
and §3's count stand. Its method and `ChainConflict` are **running** (the skeleton's `Backend`);
what follows is **a1p**.

```
# Transactional — the container's one write lock
atomic()                                         -> context manager   # every write to this substrate inside lands together or not at all
```

- **One writer per container.** `atomic()` holds a write lock over the whole container from entry
  to exit, taken before the block's first read, so a read inside sees every earlier commit and a
  check that reads, then writes, still holds at its write. sqlite takes it with `BEGIN IMMEDIATE`;
  postgres with `pg_advisory_xact_lock` at READ COMMITTED, on a key derived from the database and
  schema it is taken on, never from anything a home holds, so every connection to one substrate
  takes one lock. A writer
  waits a bounded time for it, then raises; none waits forever. It raises `StorageBusy`, declared in
  `_types.py` beside `ChainConflict`, on every backend, never its driver's own error, so the door
  answers it alike (`rest.md` §3). **a1p** (#331).
- **Nested calls join.** A block opened inside another is part of it, not a savepoint: the act
  commits once, when the outermost block exits, and an exception leaving the outermost block rolls
  back every write to this substrate in it.
- **A block is one caller's.** Nothing inside it awaits or yields to another request, and every
  statement in it runs on the connection that holds the lock.
- **A write outside any block commits alone**, under the same lock, held for that write only.
- **Each spend says whether its act can undo it.** `spend_grant` commits alone and is refused inside
  a block (§3.5); `spend_upload` rolls back with the act that spent it (§3.4). `spend_challenge`
  commits alone, with the proof's `step_up`, before the act's block opens, so a concluded proof
  stays spent and audited whatever its act then does (`rest.md` §4.2 items 4–5), and the act's block
  re-checks what the challenge bound. Not running for `spend_challenge`: the door concludes the
  proof inside the act's block (#321).
- **`ChainConflict`**, declared in `_types.py` beside this Protocol, is what `audit_append` raises
  when another writer appended after the same head: the ledger re-reads the head and re-chains, so
  the chain never forks. The store keeps one successor per entry whatever the lock, because an
  append outside a block reads the head before it holds the lock.

**A block's `BlobStore` calls run inside it, and its deletes after its COMMIT.** `put`, `stage` and
`promote`'s copy run inside the block. The staged copy a `promote` leaves behind, and the bytes a
`discard` removes, are deleted only once the outermost block has committed. A blob write is not a
write to this substrate and no rollback undoes it, so a COMMIT that fails leaves every staged copy
in place: a retried `promote` copies again, returns `True` and its act appends `blob.put`, as §4
says of a crash between copy and delete, so every byte that reaches the promoted store behind a
verified item has a committed `blob.put`; and a `discard` whose block did not commit discarded
nothing. Bytes a failed COMMIT leaves at a promoted address with nothing referring to them are never
served (§4, `rest.md` §6). **a1p** (v0.7 §AF); not running: both stores delete inside the block
today. A transfer holds the lock for as long as it takes, and a slow one reaches every other writer
as `StorageBusy`. **a1p**, reading v0.7 §AF's "one person's container bears" synchronous database
calls as covering transfers too. `TODO(a1p)`, #283, before a container serves more than one
person: moving transfers out of the lock.

## 3.7 · What every substrate keeps, and how it is named

**Status of this section: contract v1.1, a1p** (enacted with v0.7 §AF). What the container's own
substrate keeps for §3–§3.6, and for §2 when it is not delegated, postgres (§1) as much as sqlite,
and how a container names its own.

- **One container per database.** A database holds no other container's state, and no column names
  a container: one chain grows from one GENESIS with one successor per entry (`events.md` §3), which
  a table two containers shared could not hold. **a1p.** A container egzos hosts has its own
  Supabase project, holding its database and its Storage (§4); sign-in stays in the identity project
  (`identity.md` §1). **decided, not running** (v0.7 §AF).
- **No process holds a credential that reaches another container's state.** A container's host
  holds only its own project's connection string and Storage keys. A vendor credential that reaches
  more than one project, such as a management access token, is used only in the operator's
  provisioning act; no container's host and no process that answers requests holds it, egzos.io's
  included (v0.7 §T). **a1p.**
- **On postgres, the role the container runs as owns no table**, and holds only what its methods
  need: on the audit chain, reading and appending. Append-only is enforced twice, by triggers that
  refuse an update, a delete or a truncate, and by those privileges, since a table's owner can set
  its triggers aside. The owning role applies the schema from outside the container, which never
  holds that role's credentials. No role but those two holds a privilege on the container's schema,
  the vendor's own API roles (`anon`, `authenticated`, `service_role`) included, and the vendor's
  data API never serves it; where row-level security is on, its only policies name the container's
  role. **a1p.**
- **A document reads back exactly as written.** Each one a method stores is kept as the JSON text
  the backend wrote, never in a type that rewrites it (postgres `jsonb` reorders keys, respells
  numbers and refuses `\u0000`), so a reader gets back the text that was written: an entry re-hashes
  to its stored `hash` (`events.md` §3), and an item keeps every field it was put with
  (`context-item.md` §1). **a1p.**
- **Lists come back in last-write order.** Each `list_*` method returns its records in the order
  they were last written, a replaced record last, except `list_uploads`, which keeps the order the
  uploads were opened, since `put_upload` rewrites a record in place. **a1p**, as sqlite runs it.
- **The substrate is named outside the container**, by environment variables of the process that
  opens it, never by a config key (`container.md` §8) or a row: a database's connection string and
  an object store's keys are secrets, the host's. egzos never prints, logs or writes them, to a
  file, an agent's launch configuration or the chain, and an error names the variable, never its
  value. **a1p.** The database is named by **`EGZOS_DATABASE_URL`**, a postgres connection string;
  unset, the container's state stays in its home's `egzos.db`, as before. The object store is named
  by six: `EGZOS_BLOBS_S3_ENDPOINT`, `EGZOS_BLOBS_S3_REGION`, `EGZOS_BLOBS_S3_BUCKET` and
  `EGZOS_BLOBS_S3_PREFIX` name it, and `EGZOS_BLOBS_S3_ACCESS_KEY_ID` and
  `EGZOS_BLOBS_S3_SECRET_ACCESS_KEY` are its keys, the host's secrets. All six are set or none: some
  but not all stops the container, naming the ones missing. An endpoint holding userinfo stops it
  too: the keys travel in their two variables only. An object store is named only beside a
  named database; named without one, the container stops. None set, blobs stay in the home's
  `blobs/`, as before; set, the blob root is the prefix (§4). **a1p** (v0.7 §AF).
- **A home stays bound to the database it was made on**, so that none opens another's database or
  falls back to a fresh local store, and a missing volume never makes fresh keys that lift a
  throttle (§3.1). A home whose state is its own `egzos.db` is bound by being one directory. A home
  makes its container on a named database in one `atomic()` block (§3.6) that finds the chain empty
  and appends its first entry, then records that entry's hash, which is no secret, in a file beside
  its keys, with its blob root: the home's `blobs/`, or the object store's endpoint, bucket and
  prefix, none of them secret. Two homes making a container on one database take that one lock,
  since its key is the database's, and a chain keeps one successor per entry (§3), so only one first
  entry is ever appended. A crash between the block's commit and the file leaves a chain with no
  binding, which stops as below: unavailable, never unsafe. Every open compares the two before the
  door serves, and stops the container, naming the variable and never its value, when:
  - they differ, the database's chain being empty included: the home belongs to another database;
  - the home holds a binding and the variable is unset: it never falls back to its own `egzos.db`;
  - the named database cannot be reached: it never falls back to a local store;
  - the database holds a chain and the home holds no binding, a new or lost volume: its keys would
    be fresh. So does a home making its container whose block finds a chain already there, as when
    two homes are pointed at one empty database: one makes it, the other stops;
  - the home's own `egzos.db` holds a chain and the variable is set: that chain, its tokens and its
    counters would be left behind;
  - the blob root named differs from the one recorded: blobs never move to another store, or back
    to the home, without the operator's rebind. A binding that records no blob root, written
    before this clause, records the home's `blobs/`, the only root there was;
  - the database no longer holds the newest entry the home has seen. The file also records that
    entry's `seq` and hash, rewritten at every open once these checks pass and at every clean close,
    so a database restored to an earlier point without its home stops: its counters and revocations
    would be older than the home's (§3.1; `identity.md` §4).

  The operator restores the home, or rebinds it on the host, an act whose shape enters with its
  code (`TODO(a1p)`, #283, with the hosted home's provisioning). What the binding cannot catch is
  stated as plainly: a rollback to a point after the newest entry the home recorded, and a rollback
  of the database and the home together, or by whoever can write both. Those are the outside
  anchor's (§1), which the Chief has asked to come with sync (v0.7 §V, §AF). **a1p** (v0.7 §AF).
- **U+0000 is kept only inside a document.** A document is JSON text, where U+0000 is always
  written escaped. Every other value a backend stores or matches by, an id, a key, a scope, a kind
  or a name, is refused with `ValueError` before any write when it holds U+0000, on every backend:
  postgres `text` cannot hold it, and sqlite refuses it too, so both answer alike. The door refuses
  it first, as a malformed request (`rest.md` §3). A sqlite store written before this clause may
  already hold such a value: every read that does not name it still returns it, and a read or write
  naming it is refused. **a1p** (#331).

## 4 · `BlobStore` — content-addressed, staged

```
put(data)      -> sha256        # promoted store, dedup by construction
stage(data)    -> sha256        # staging prefix, invisible to resolution
promote(sha)   -> bool          # staging -> promoted, on approval
get(sha)       -> bytes | None
exists(sha)    -> bool
discard(sha)   -> bool          # deletes staged bytes only; True if there were any
```

Two prefixes under the blob root: `sha256/<hash>` for promoted bytes and `staging/<hash>` for staged
bytes. `put` is idempotent — an identical write of existing content is a no-op returning the same
address. **running.**

**The blob root is a directory or an object-store prefix**: the home's `blobs/` locally, and for a
container egzos hosts a prefix in its own project's Storage, named by §3.7's variables, its own
substrate under §1's reading of [0.3 · 5]. **decided, not running** (v0.7 §AF) for the hosted
store; **a1p** for the root.

**`promote` decides by the staged bytes alone**, never by whether promoted ones exist. Where the
store has no rename, as an S3-style store has none, it copies, then deletes the staged copy (the
skeleton's directory store copies too): a crash between the two leaves only a staged copy beside the
promoted bytes, which a retried `promote` (it copies again, deletes, and returns `True`) or a
`discard` removes. The copy lands whole or not at all: one object write, or in a directory a write
to a temporary name renamed into place. **a1p** (v0.7 §AF); not running in the directory store,
whose copy is one plain write.

**The content address is checked.** `get` returns `None` for bytes that do not hash to their
address, and `promote` treats staged bytes that do not as nothing staged, so a store can lose bytes
but never substitute them. **a1p** (v0.7 §AF); not running: the directory store does not re-hash.

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

**Downloads stay at the container**, on an object store too: redemption reads the bytes from the
store and streams them (`rest.md` §6), and no storage vendor's signed URL reaches a client. **a1p**
(v0.7 §AF).

The mint and the redemption are **two separate audit events**: `blob.grant` when Trust mints the
descriptor, `blob.pull` when the bytes are actually served (`events.md`). One without the other is a
finding, not a shortcut. **running**: the REST door's reads mint, and `GET /v1/blobs` redeems
(`rest.md` §6).

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
**running**: the approval path and `rest.md` §4.4's item step append `blob.put` only when it is
`True`.

**Deletion. [0.3 · 44]** v1.0 **never deletes promoted bytes** behind a tombstoned item: the audit
chain keeps referring to the address. **Staged bytes are never purged on a timer** (v0.7 §Z, amending
R11): past `blobs.staging_retention_days` (30 by default, `container.md` §8) they are surfaced to
their owner, who promotes the item or tombstones it, and only a tombstone — or the discard of an
orphaned upload — deletes staged bytes (`rest.md` §4.4), through `discard`, which never touches
`sha256/`. Staging is content-addressed, so two uploads of the same bytes share one staged copy:
the caller deletes it only when no other live upload or staged item holds that address. An owner
purge act for promoted bytes is `[v1.1]`: the record defers it to the v1.1 boundary.

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
  `store/items.py` or `resolver.py`. Today `blobs.py` and `backends/base.py` import only the
  standard library and the shared model and types (`model.py`, `_types.py`) — that is the property
  to hold, not to restore.
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

§3.1's `ThrottleState`, §3.2's `IdentityState` and `ConfigState`, §3.3's `ConfirmState`, §3.4's
`UploadState` and §3.5's `GrantState` are contract v1.1, not part of the 0.3 freeze; their partition
is decided on #173 (option (A), on the `ContainerState` substrate). §3.6's `Transactional` and §3.7
are contract v1.1 too, enacted with v0.7 §AF, as are the paragraphs added with them to §1–§4;
`Transactional` sits on that substrate as well, outside `STORAGE_CONTRACTS`.

`Node` and `Proposal`, referenced by `ContainerState`'s signatures above, are defined by the
container contract (**#28**, landed) and typed in `src/egzos/_types.py`. The provisional aliases
this note once pointed at are gone; nothing here is outstanding.
