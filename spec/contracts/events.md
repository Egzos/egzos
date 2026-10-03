# Contract · event taxonomy and the audit chain

**Status: drafted — awaiting the Phase 0.3 freeze review.** Not law yet.

**Derivation.** RUNNING shapes of the walking skeleton (`docs/build/WALKING-SKELETON.md` §8); code
`src/egzos/ledger.py` (`EVENTS`, `Ledger.append`, `Ledger.verify`), `src/egzos/model.py`
(`canonical`). Pinned by `tests/test_skeleton.py::test_audit_is_hash_chained_append_only_and_detects_rewrites`
and `::test_reads_are_audited`.

## 1 · The vocabulary

An appended event whose name is not in this list MUST be rejected. **Eighteen names are listed
below**: sixteen **run**, one (`step_up`) is **reserved** for Phase 2.2, and one (`blob.grant`) is
**decided, not running** (F5). The typed vocabulary in this repository — `_types.py`'s `Event`, and
the `EVENTS` tuple derived from it — carries **all eighteen**, `blob.grant` included:
`AuditEntry.event` is typed `Event`, and F5's mint needs the member on the day it lands. So a
validator written against `EVENTS` accepts a `blob.grant` append today, and **nothing in this tree
rejects one** — what is not running is the *emitter*: no code path mints a `BlobGrant`, so no such
entry is ever produced. The walking skeleton's own `ledger.py` tuple held seventeen — the sixteen
running plus the reserved `step_up` — but that file is on `chief/walking-skeleton`, not on `main`,
and its count is the skeleton's, not this tree's. Counted here because a count that disagrees with
its own table, or with the constant beside it, is the kind of drift a reader resolves by guessing.

| event | emitted when | status |
|---|---|---|
| `container.init` | a container is initialised | running |
| `node.create` | a container node is created (`auto: true` for pure-capture threads) | running |
| `item.add` | an item is written — always at `status: unverified` | running |
| `blob.put` | blob bytes are stored | running |
| `context.fetch` | context is read — **reads are audited, not just writes** | running |
| `blob.pull` | blob bytes are handed to a caller — artifact download IS fetch | running |
| `item.move` | an item's scope changes | running |
| `gate.pass.silent` | a move with **zero** audience delta, carrying `audience_delta: none` | running |
| `gate.propose` | a move with a nonzero audience delta is parked as a proposal | running |
| `approval.promote` | an item is promoted to verified (human-only) | running |
| `approval.execute` | a parked proposal is approved and executed (human-only) | running |
| `approval.deny` | a proposal is denied, **or refused as `stale` on manifest mismatch** | running |
| `trust.quarantine` | an item is quarantined; carries every `affected` id | running |
| `step_up` | **reserved** — Phase 2.2, the step-up tap | reserved |
| `token.mint` | a token is minted | running |
| `token.revoke` | a token is revoked | running |
| `item.tombstone` | an item is tombstoned | running |
| `blob.grant` | Trust mints a `BlobGrant` (**F5**) | decided, not running |

**`gate.pass.silent` is silent to the user, never to the log.** A zero-delta move is not an
unaudited move; it is an audited move that does not interrupt anyone.

## 2 · The entry

```
{ seq, ts, event, actor, principal, subject, scope, details, prev_hash, hash }
```

- `seq` — monotonic, assigned by the store on append.
- `actor` / `principal` — who acted, and whether as `interactive` or `client`.
- `subject` — the id the event is about (item, node, token, proposal, or a blob's `sha256`).
- `scope` — the container the event happened in; nullable.
- `details` — event-specific, open. A reader MUST tolerate unknown keys here.

**running.**

## 3 · The chain

```
hash = sha256( prev_hash || canonical(entry minus `hash` and minus `seq`) )
```

- The genesis `prev_hash` is **64 ASCII zeros**.
- `||` is string concatenation of the previous hash's hex digest with the canonical body, encoded
  UTF-8.
- The body hashed is the entry **without** `hash` and **without** `seq` — `seq` is the store's, not
  the chain's, and the formula names both exclusions rather than leaving one to this bullet.

`storage.md` §3 and `_types.py`'s `BackendProtocol` say the same thing from the store's side:
`audit_append` receives an entry carrying no `seq`, and the store assigns one. **running.**

**`canonical` is part of the contract, not an implementation detail.** Two implementations that
serialise differently produce different hashes and the chain stops verifying across them. It is
JSON with:

- object keys **sorted**;
- **no whitespace** — `,` and `:` as separators;
- **non-ASCII preserved**, not `\u`-escaped.

**running.**

### Why `seq` stays out of the hashed body

**a1p's reading, pending the freeze — `[OPEN→0.3]`.** The Chief's note on #102 recorded the opposite
recommendation (hash `seq`); this section goes the other way, and the freeze should read it as an
agenda item, not as settled text. Four places already agree on excluding it — §3's bullet, §3's
formula as amended here, `storage.md` §3 and `_types.py`'s `AuditEntry` — so **if the freeze takes
the other reading, those four move together, and `a3-ledger` implements against a skeleton that
does it the other way.** The reasoning below is why a1p chose as it did.

Stated as a decision rather than left as the absence of one, because the drift report found the
formula and the prose disagreeing, and *including* `seq` was the first reading offered (#10 F7,
#102). **Order is already bound** — every entry commits to `prev_hash`, so the entries form a linked
list, and a reordering, an insertion or a deletion in the middle breaks verification at the first
entry whose `prev_hash` no longer matches the one before it. `seq` adds no ordering fact the chain
does not already carry. What it would add is a dependency on the store's numbering.

That dependency has a cost this product cannot pay. `storage.md` plans three backends
(sqlite → postgres → mem0/zep) and the container is meant to move between them. With `seq` hashed, a
container exported from sqlite — where `seq` is `INTEGER PRIMARY KEY AUTOINCREMENT` and the first
entry is `1` — and imported into a store that numbers from `0`, or that renumbers after a
compaction, has an audit chain that can never verify again, for a change that altered no fact about
what happened. With `seq` out, **an exported container verifies unchanged wherever it lands, and its
entries may be renumbered.** That is the rest of the contract's promise applied to the ledger: the
container is the user's, and it travels.

*Rejected:* hashing `seq`, to bind the displayed order to the chained order. The mutations it would
newly catch are exactly the ones that preserve relative order — a uniform offset, or a gap — and
those state nothing false about what happened in which order. A *shuffle* is already caught:
verification walks in `seq` order, and the linkage check fails at the first entry out of place.
*Cost of this choice:* `seq` is a field `audit verify` reports (§4.1) and the hash does not cover, so
a store may renumber its own ledger without the chain objecting. Accepted — the audience is the
owner inspecting their own container, and the order they are shown is the order the chain enforces.

## 4 · Invariants

1. **Append-only.** Enforced by the store (triggers), not only by the code that writes. Verified
   independently by walking the chain: `audit verify` reports the first break with its `seq` and
   the reason, and exits non-zero. A rewritten entry and a re-pointed `prev_hash` are distinct
   failures and are reported distinctly — **this is the one place a specific error is correct**,
   because the audience is the owner inspecting their own container, not a caller probing it.
2. **Audit coverage.** Every read, blob pull, grant mint, silent gate pass, step-up and approval is
   an event. A surface that produces an effect without a corresponding event is non-conforming.
3. **The ledger's substrate is never delegated.** `audit_append` belongs to `ContainerState`, not to
   the pluggable item store (**F3**) — the chain's integrity must not depend on whoever wrote a
   third-party backend. See `storage.md` (issue #27).
4. **No secrets in `details`.** Token ids are subjects; token *values*, grant signatures and blob
   bytes never enter the log.

## 5 · What this document does not fix

The gate's delta rule and the manifest binding → `container.md`. Capabilities and principals →
`capabilities.md`. Anomaly primitives and `audit anomalies` are Ledger's to build on this taxonomy
(Phase 1); they add no events.

TODO(a1p): the skeleton emits `approval.deny` both for a denied proposal and for a `stale`
manifest mismatch, distinguished only by a `stale` flag in `details`. Whether the freeze keeps one
event with a flag or splits them is `[OPEN→0.3]` — a TOCTOU refusal and a human "no" are different
facts, and anomaly detection later has to tell them apart.
