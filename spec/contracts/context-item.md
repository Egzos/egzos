# Contract · ContextItem

**Status: frozen at 0.3 (Chief, date of merge).** Law: a change is a `contract-change` escalation to
a1p-planner, batched at a phase boundary (`spec/contracts/README.md`). The freeze is the Chief's merge of
the commit that set this line, dated by that merge; a1p-planner prepared the text and did not declare it.

**Derivation.** Frozen from the RUNNING shapes of the walking skeleton (`chief/walking-skeleton`,
`docs/build/WALKING-SKELETON.md` §1), not from prose. Source code: `src/egzos/model.py`
(`ContextItem`), `src/egzos/store/items.py` (`Store.add`, which builds `content`). Pinned by
`tests/test_skeleton.py::test_unknown_fields_survive_round_trip`.

Every clause below is marked **running** (observed in the skeleton), **decided, not running**
(a Chief freeze decision F1–F5 or 0.3 decision the skeleton does not yet execute). A `[0.3 · N]`
marking cites item `N` of the Chief's freeze record on #31 (2026-10-03). The open→0.3 marking the
draft carried is gone from `spec/contracts/` and `src/`: the record answered every one. The design
specs still carry the retired marker; design-gap #157 tracks their revision by A2 (`README.md`).

## 1 · The item

A ContextItem is the atomic unit. **`scope` is a location, not an identity**: an item's meaning does
not change when it moves, only its audience does.

| field | type | notes | status |
|---|---|---|---|
| `id` | ULID | assigned at write | running |
| `kind` | enum, §2 | | running |
| `scope` | node id | the container it currently sits in — location, not identity | running |
| `key` | string \| null | optional; enables cross-scope override per `(kind, key)` | running |
| `content` | object, §3 | shape depends on `kind` | running |
| `tags` | list of string | | running |
| `provenance` | object, §4 | who and what produced it | running |
| `trust` | object, §5 | status and its evidence | running |
| `lifecycle` | object, §6 | | running |
| `visibility` | object | `{ring}` — the container type the item currently sits in | running |

**Unknown fields survive round-trip.** An implementation that reads an item carrying fields it does
not recognise MUST preserve them verbatim and write them back unchanged. In the skeleton the
carrier is a dict named `extra`, flattened into the serialised object alongside the known fields;
the contract fixes the *behaviour*, not the carrier's name. This is what lets a contract version
move through an older reader without silent data loss. **running**

## 2 · `kind`

`memory` · `preference` · `skill` · `artifact` · `integration` · `alias` · `rule` — the whole
vocabulary. **running**

`rule` is special everywhere it appears: **rules are served verified-only at every scope**,
overriding the per-container serving policy. See `container.md` §serving policy. **running**

## 3 · `content`

Two variants. Both carry `auto_title` and `title_engine`: every write is auto-titled at write time,
and the engine that produced the title is recorded so a degraded title can be distinguished from an
embedding-backed one later. **running**

**Text** (`memory`, `preference`, `skill`, `integration`, `alias`, `rule`):

```
{ body, auto_title, title_engine }
```

**Artifact** (`kind: artifact`) — a metadata item plus a content-addressed blob:

```
{ sha256, mime, size, filename, inline?, auto_title, title_engine }
```

- `sha256` is the blob's content address. The bytes live in the blob store, never in the item.
- `inline` carries the bytes on the item **only** when **both** hold: `size` is at or below
  `blobs.inline_max_bytes`, **and** `mime` matches `text/*`. Otherwise `inline` is absent.
  **running** (the skeleton's threshold is the constant 64 KiB).
- The threshold is container configuration — `blobs.inline_max_bytes`, default 64 KiB. The config
  object is defined in `container.md`; this document only references it. **decided, not running**
  (the skeleton has no config surface; the value is a constant).

**Above the threshold a fetch carries a `BlobGrant` descriptor — never the bytes, and never a URL
the client cannot use.** The grant is minted by Trust, never by Store/Vault (**F5**); Store/Vault
renders a grant into a URL and decides nothing. A stdio client receives the descriptor and redeems
it at the REST door (Phase 2). The mint is one audit event (`blob.grant`) and the redemption
another (`blob.pull`) — see `events.md`. **decided, not running** (the skeleton serves inline
`text/*` at or below 64 KiB and has no grant).

**`BlobGrant.sig` is an HMAC over `sha256`, `item`, `token` and `expires_at` under a
container-held key. [0.3 · 45]** The key never leaves the container, and the grant id is not the
bearer secret. Without the key a redeemer therefore cannot forge a descriptor, alter one, or rebind
one to another item or token. The MAC algorithm and key rotation are not pinned at this layer. The
descriptor's other fields are `{sha256, item, token, expires_at, sig}` (**F5**). **decided, not
running.**

**The MAC MUST cover every descriptor field other than `sig`, and verification MUST compare `sig`
in constant time.** A field outside the MAC can be altered by a redeemer without detection, and a
comparison that exits at the first differing byte lets a redeemer recover a valid `sig` byte by
byte from its timing. A field added to the descriptor later is covered by the same rule, with no
edit here. **a1p**, the binding of [0.3 · 45].

## 4 · `provenance`

`{ actor, principal, client, derived_from, imported_from, approved_by }` — **all six present**, null
where unknown, so a reader never has to distinguish "absent" from "unset". **running**

- `principal` is `interactive | client` (see `capabilities.md` §3) — a token's principal, never the
  audit-only `none`; `_types.py` types it `TokenPrincipal`.
- `derived_from` is the item this one was derived from. **Quarantine propagates along it**: see
  `container.md`.
- `approved_by` is stamped by promotion and is null until then.

## 5 · `trust`

`status` is `unverified | verified | quarantined`. **Writes land unverified — human and agent
alike.** **running**

| status | additional fields |
|---|---|
| `unverified` | — |
| `verified` | `promoted_at`, `manifest` (the hash the promotion was bound to) |
| `quarantined` | `reason`, `at` |

Promotion is a **human-only act**: it requires the `interactive` principal and no capability
reaches it (see `capabilities.md` §4). It stamps `provenance.approved_by` and a manifest hash.
Quarantined items are **never served**, at any scope, in any query. **running**

## 6 · `lifecycle`

`{ created_at, updated_at, version, tombstoned? }`. `version` increments on each mutation;
`tombstoned` is absent until the item is tombstoned. Timestamps are UTC ISO-8601 to the second
(`%Y-%m-%dT%H:%M:%SZ`). **running**

Deletion is a tombstone, not a removal — the audit chain must keep referring to something.

## 7 · What this document does not fix

Container types, ring ranks, the chain, serving policy and the container config object →
`container.md`. Capabilities, principals and tokens → `capabilities.md`. Audit events →
`events.md`. The storage interface that persists items → `storage.md`.

TODO(a1p): `visibility` carries only `{ring}` in the skeleton. Whether the object is fixed at one
key or is open for later visibility facets is not stated by any source; raised at the 0.3 review
rather than guessed here.
