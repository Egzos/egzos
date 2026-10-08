# Contract · event taxonomy and the audit chain

**Status: drafted — awaiting the Phase 0.3 freeze review.** Not law yet.

**Derivation.** RUNNING shapes of the walking skeleton (`docs/build/WALKING-SKELETON.md` §8); code
`src/egzos/ledger.py` (`EVENTS`, `Ledger.append`, `Ledger.verify`), `src/egzos/model.py`
(`canonical`). Pinned by `tests/test_skeleton.py::test_audit_is_hash_chained_append_only_and_detects_rewrites`
and `::test_reads_are_audited`.

## 1 · The vocabulary

An appended event whose name is not in this list MUST be rejected. **Thirty names are listed
below**: eighteen **run**, and twelve (`blob.grant`, `client.register`, `config.set` and the nine
`authz.*` rows) are **decided, not running** — `blob.grant` by F5, the other eleven by the 0.3
freeze: the nine `authz.*` and `client.register` for the container's authorization server
(`authorization-server.md` §5, §9.3, §11.9 and §12; [0.3 · 29, 31, 33, 36], #140, #144), and
`config.set` for the config object (`container.md` §8; [0.3 · 40]). The typed vocabulary in this
repository — `_types.py`'s `Event`, and the `EVENTS` tuple derived from it — carries **all
thirty**, the twelve included: `AuditEntry.event` is typed `Event`, and each emitter needs its
member on the day it lands. So a validator written against `EVENTS` accepts an append under any of
the twelve today, and **nothing in this tree rejects one** — what is not running is the *emitter*:
no code path mints a `BlobGrant`, serves an AS page, registers a client or changes a config key, so
no such entry is ever produced. `ledger.py` imports this tuple rather than restating it. Counted
here because a count that disagrees with its own table, or with the constant beside it, is the kind
of drift a reader resolves by guessing.

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
| `approval.deny` | a proposal is denied — a human "no" | running |
| `approval.stale` | a proposal is refused because its manifest changed since it was filed (TOCTOU; freeze item 39) | running |
| `trust.quarantine` | an item is quarantined; carries every `affected` id | running |
| `step_up` | a presence check concludes, whatever its `outcome` (the MVP tap, ahead of Phase 2.2) | running |
| `token.mint` | a token is minted | running |
| `token.revoke` | a token is revoked | running |
| `item.tombstone` | an item is tombstoned | running |
| `blob.grant` | Trust mints a `BlobGrant` (**F5**) | decided, not running |
| `authz.login` | a login attempt at `/login` is evaluated (AS §12 row (a)) | decided, not running |
| `authz.redeem` | a device-code redemption at `/device` is evaluated (row (b)) | decided, not running |
| `authz.refuse` | `/authorize` answers with the pre-trust uniform failure (AS §5.3; row (d)) | decided, not running |
| `authz.release` | a throttle releases, `refused: 0` included (row (e)) | decided, not running |
| `authz.reject` | `/authorize` rejects a matched client's request post-trust (row (f)) | decided, not running |
| `authz.render` | a consent screen is rendered at `/authorize` (row (g)) | decided, not running |
| `authz.tally` | a window closes in which the throttle admitted a session-less 303 (row (h)) | decided, not running |
| `authz.revoke_refuse` | the owner path refuses a revoke by `Token.id` (AS §11.9) | decided, not running |
| `authz.grant` | the owner decides a consent request, `decision: granted` or `denied` (AS §9.3) | decided, not running |
| `client.register` | the owner registers, amends or removes a client, `op: add · amend · remove` (AS §5) | decided, not running |
| `config.set` | a container-config key is changed — an `admin` act (`container.md` §8) | decided, not running |

**`gate.pass.silent` is silent to the user, never to the log.** A zero-delta move is not an
unaudited move; it is an audited move that does not interrupt anyone.

**The `authz.*` rows are specified where their surfaces are.** Each row's outcome, its closed
`details.cause` word and its `principal` are `authorization-server.md` §12's table and §12.2, and
§11.9 item 3 for `authz.revoke_refuse`; the cause vocabularies are pinned in `_types.py`
(`AS_LOGIN_CAUSES`, `AS_DEVICE_REDEMPTION_CAUSES`, `AS_AUTHORIZE_PRETRUST_CAUSES`,
`AS_AUTHORIZE_POSTTRUST_CAUSES`, `AS_REVOKE_REFUSAL_CAUSES`). **`refuse` is pre-trust, `reject` is
post-trust, and `revoke_refuse` is the owner's revoke page** — three refusals, each under its own
event, so an `audit` query never has to tell them apart by `details`.

**A consent decision is none of the three: it is `authz.grant`** (`authorization-server.md` §9.3,
[0.3 · 29]). One row, `details` `{client_id, decision, scopes, capabilities}`, with `decision`
closed to `granted` · `denied` (`_types.py`'s `AS_GRANT_DECISIONS`) and `scopes`/`capabilities`
recording what was *requested*, a denial included. It fires on an owner's decision inside an
authenticated session and on nothing else, so it carries `principal: interactive` and no `cause`.

**`client.register` and `config.set` are owner acts on container state, not `authz.*` rows.**
`client.register`'s `details` are `{client_id, op, redirect_uris}`, `op` closed to `add` · `amend` ·
`remove` (`AS_CLIENT_REGISTER_OPS`), and `redirect_uris` is the allowlist **after** the change, empty
on `remove` (`authorization-server.md` §5, [0.3 · 31]). `config.set`'s `details` are `{key, value}`:
`key` is the dotted wire key (`container.md` §8, F6) and `value` the value after the change, so the
log states the setting as it then stood, the same rule `client.register` follows. **a1p**, the field
names: the record names the event and the capability and leaves the shape open. `subject` is the
node the key applies at for a node-scoped key (`org.policy.sovereign_chain`,
`node.policy.structure_floor`) and null for a container-wide one. A change that leaves the value
as it was still appends: the act happened. No config value is a secret, so invariant 4 permits the
value in `details`. [0.3 · 40]

## 2 · The entry

```
{ seq, ts, event, actor, principal, subject, scope, details, prev_hash, hash }
```

- `seq` — monotonic, assigned by the store on append.
- `actor` / `principal` — who acted, and as what: `interactive`, `client` or `none`
  (`capabilities.md` §3). Both are mandatory on every entry; `principal` is never null. **`none`
  is for an entry with no caller to name** — `authorization-server.md` §12.2: rows (a), (b), (d),
  (e) and (h) — and on such an entry `actor` carries the **surface** the append is about, one of
  `_types.py`'s `AS_THROTTLE_SURFACES`, **never the caller's network identifier**: an IP in an
  append-only chain is a surveillance record the owner cannot prune. An append with
  `principal: none` under any event other than `authz.login`, `authz.redeem`, `authz.refuse`,
  `authz.release` and `authz.tally` **MUST be rejected**: a read, a pull or an act is never
  unattributed. `_types.py` pins the five as `PRINCIPAL_NONE_EVENTS`. **decided, not running**
  (no AS in this tree emits one yet, and the ledger does not check it yet). [0.3 · 34, 35]
- `subject` — the id the event is about (item, node, token, proposal, or a blob's `sha256`).
- `scope` — the container the event happened in; nullable.
- `details` — event-specific, open. A reader MUST tolerate unknown keys here.
- **The converse binds too: an append under one of the five `PRINCIPAL_NONE_EVENTS` MUST carry
  `principal: none`**, and an append under one of them with `interactive` or `client` MUST be
  rejected. `authorization-server.md` §12.2 puts `none` on **every** row (a), (b), (d), (e) and
  (h), (d) included although five of its seven causes are reached only inside a session, so that
  the principal never tells a reader which cause a uniform page had or whether a throttled caller
  held a session. A `principal` that varied within one of these events would be that signal.
  So `none` and the five are one set seen from both sides: `none` appears under these events
  and nowhere else, and these events carry `none` and nothing else. **a1p**, reading §12.2's row
  binding as the converse of the rule above (a1r on #147). [0.3 · 34] **decided, not running.**
  TODO(chief): the ledger check for this direction belongs beside #150's, in a file no agent owns.

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
   **Two exceptions, each closed and each decided at the 0.3 freeze; nothing else is excepted.**
   - **The owner's read inside their own session** ([0.3 · 36, 38]). A read the owner makes of their
     own container's state, inside a session `authorization-server.md` §10.1 has authenticated, to
     decide an act they are performing, gets no read event of its own. It has exactly three
     instances: (1) §11.1's client-registry read and (2) §11.3's existing-tokens read, both recorded
     by the consent render, `authz.render`; (3) §11.0 substep 1's match against §11.4's
     decided-request record, recorded by `authz.refuse` with cause `replayed` where it matches and
     otherwise by the entry the request goes on to. Each is bounded (one keyed entry, a count and a
     timestamp, one record). §11.4's request-keyed read is **not** an instance: every path through
     it appends. A fourth instance is a contract change, not a reading of this one.
   - **Refresh-token rotation** ([0.3 · 30]). Retiring the presented refresh token in a successful
     rotation gets no event of its own: the rotation writes `token.mint` for the token it issues,
     and nothing else. `token.mint` and `token.revoke` carry the refresh-family id in `details`, so a
     family is followable from first mint to last revocation, and a reused chain is revoked under
     `token.revoke` (`authorization-server.md` §9.2 clause 2, §9.3 effect 5).
3. **The ledger's substrate is never delegated.** `audit_append` belongs to `ContainerState`, not to
   the pluggable item store (**F3**) — the chain's integrity must not depend on whoever wrote a
   third-party backend. See `storage.md` (issue #27).
4. **No secrets in `details`.** Token ids are subjects; token *values*, grant signatures and blob
   bytes never enter the log.

## 5 · What this document does not fix

The gate's delta rule and the manifest binding → `container.md`. Capabilities and principals →
`capabilities.md`. Anomaly primitives and `audit anomalies` are Ledger's to build on this taxonomy
(Phase 1); they add no events.

Decided at the 0.3 freeze (item 39): a TOCTOU refusal is `approval.stale`, its own event, and
`approval.deny` is only a human "no" — anomaly detection tells them apart by name.
