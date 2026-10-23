# Contract · places — push and pull

**Status: contract v1.1, drafted by #283's author for the Chief to ratify by merging it** (v0.7 §V).
Nothing here runs until the code that cites it lands; each clause is **a1p** unless it says
**decided**, and a clause marked **decided** quotes the decisions log.

**Derivation.** v0.7 §V (`docs/build/egzos-decisions-v0.7-amendments.txt`): *"A container has places:
one hosted cloud and any number of locals … Sync is git-like, not live: a local pushes what it has and
pulls ('catches up') what it lacks, when asked; `status` says what is ahead and behind. Each place
keeps its own ledger, and a push is verified on arrival (its hash chain) before it lands."* And
`identity.md` §8: a local signs in to its cloud through the cloud's provider, like any client.

## 1 · Places

1. **A place is a whole container**: its own store, ledger, tokens, keys and blobs. One container has
   one cloud and any number of locals. **decided** (§V).
2. **Every place has a `place_id`**, minted once, the first time it is read, and kept in its own
   state (§8). It is an identifier, not a secret.
3. **A local knows its cloud** by origin, set by `egzos place link <origin>`, and keeps two cursors:
   `pushed`, the hash of the last entry of its own chain the cloud has acknowledged, and `pulled`,
   the `seq` and hash of the last entry of the cloud's chain it has applied. **A cloud knows its
   locals** by the pushes they make: for each `place_id`, the last entry of that place's chain it
   holds.
4. **`status`** compares them: a local is *ahead* by the entries of its chain after `pushed`, and
   *behind* by the cloud's entries after `pulled` (`GET /v1/sync/status`, §5).

## 2 · What travels

- **Nodes and items**, as their documents stand, for every subject an entry of the travelling chain
  segment names. A tombstone travels too.
- **Promoted blob bytes**, by digest, for every artifact item that travels and whose bytes the
  receiving place lacks. **Staged bytes never travel**: an artifact nobody has decided on stays at
  the place where it was staged (`rest.md` §4.4).
- **The sending place's chain segment**: every entry after the last the receiver holds from it.
  The receiver keeps that segment as the sender's record, apart from its own chain, and never
  appends it to its own.
- **Nothing else.** Tokens, grants, agent registrations, confirm credentials, challenges, uploads,
  throttle counters, config, keys and proposals are each place's own. A proposal parks at the place
  where it was made and is decided there.

## 3 · Push

`POST /v1/sync/push` at the cloud carries `{"place", "after", "entries", "nodes", "items"}`:

- `place` is the local's `place_id`; `after` is the hash of the last entry of the local's chain the
  cloud holds from it, or `null` for its first push; `entries` is the local's chain after that;
  `nodes` and `items` are the documents those entries name, as they stand at the local.
- **Who.** An `interactive` principal holding `admin` over `["*"]` at the cloud: the owner, signed in
  through the cloud's provider (`identity.md` §8). Anyone else gets `rest.md` §3's refusal.
- **The push is a confirmed act** (`rest.md` §4.2), one confirm for the whole push, act `push`. It
  carries what the local decided, statuses included, into a place whose own audiences may differ:
  the cloud has grants and agents the local does not know. So the first leg answers, beside the
  challenge, `"newly"`: everyone at the cloud who would newly see any item the push moves or adds
  there, by the cloud's own audiences; and `"lands": {"nodes", "items", "verified"}`, the counts. The
  challenge is bound to the sha256 of the push body's canonical form, so a second leg carrying any
  other body is `mismatch`. **A status travels only under this confirm**: an item verified at the
  local lands verified because a person at the cloud confirmed the push that carries it, not because
  the local's chain says so; a local's chain is its holder's own account and proves nothing to
  another place on its own.
- **Verified on arrival, before anything lands**, in this order:
  1. The shape (§3's `400`).
  2. `after` equals the last hash the cloud holds for `place` (or both are absent). Otherwise `409`
     `{"error": "diverged", "have": <the hash it holds, or null>}` with §3's headers: a fact about
     the caller's own place.
  3. The segment is a chain: the first entry's `prev_hash` is `after` (or the genesis hash), and
     every entry's `hash` recomputes over its body (`events.md` §3). Otherwise `400`.
  4. Every node and item document names, as its `id`, a subject some entry of the segment names. A
     document no recorded act accounts for is `400`.
- **Then it lands, in one transaction, with the confirm's `step_up`**: the segment is kept as
  `place`'s record; each node and item is written by §6's merge rule; the cloud appends
  **`sync.push`** (`subject` the local's `place_id`; `entries`, `first` and `last` hashes; the ids
  `landed` and `kept`) and, for each item whose landing widened who sees it, `gate.pass.confirmed`
  naming the push's `step_up`. Its answer is `{"result": "pushed", "missing": [<sha256>]}`: the
  promoted bytes it lacks.
- **Bytes.** `PUT /v1/sync/blobs/{sha256}` with the raw bytes, by the same principal, for a digest a
  landed artifact item names and the cloud lacks: checked against the digest, written promoted
  (they were promoted where they came from), and recorded as `blob.put`. Any other digest is §3's
  refusal.
- **At the local**, a push that lands moves `pushed` to the segment's last hash and appends
  `sync.push` to the local's own chain (`subject` the cloud's origin).

## 4 · Pull

`GET /v1/sync/pull?after=<seq>` at the cloud answers `{"entries", "nodes", "items", "blobs"}`: the
cloud's own chain after `seq`, the documents those entries name as they stand now, and the digests of
the promoted bytes their artifacts reference.

- **Who.** As push. **No confirm**: a pull is a read, and what it lands, it lands at the owner's own
  local, by the owner's own act there. It appends `context.fetch` at the cloud (`view: sync`, the
  ids served).
- **At the local, verified before anything lands**: the segment continues the cloud chain the local
  holds (its first `prev_hash` is the `pulled` hash, or genesis) and every hash recomputes; every
  document names a subject an entry names. Then, in one transaction, the segment is kept as the
  cloud's record, the documents are written by §6's rule, `pulled` moves to the last entry, and the
  local appends **`sync.pull`** (`subject` the cloud's origin; `entries`, `landed`, `kept`).
- **Bytes.** `GET /v1/sync/blobs/{sha256}` by the same principal, for a digest a pulled item names:
  the bytes, appending `blob.pull`. The local writes them promoted.

## 5 · Status

`GET /v1/sync/status?place=<place_id>` answers `{"pushed": <hash | null>, "head": {"seq", "hash"}}`:
what the cloud holds from that place, and its own chain's head. Who: as push. A read: it appends
`context.fetch` (`view: sync`).

## 6 · The merge rule

**Last writer wins, by the document.** For a node or item present at both places, the one whose
`lifecycle.updated_at` is later wins; on a tie, the higher `lifecycle.version`; on a tie, the
document from the place whose `place_id` sorts greater. A losing incoming document is not written,
and is counted as `kept`. So two places that exchange the same documents converge, whatever order
the exchanges happen in. **decided**, last-writer-wins (v0.7's open question 2 names it "LWW now;
CRDT later"); **a1p**, the tie-breaks.

## 7 · New events

`sync.push` and `sync.pull`, appended as §3 and §4 say. They enter `events.md` §1 and `_types.py`
with the code that appends them, as `identity.md`'s did.

## 8 · The state it keeps — `PlaceState`

One Protocol beside `ContainerState`, on its substrate and never delegated (F3); it enters
`storage.md` as §3.6 with its code.

```
# PlaceState — this place, its cursors, and the segments it holds from other places
place_self()                                 -> {"place_id", "cloud"}   # minted on first read
link_cloud(origin)                           -> None
get_cursor(name)                             -> dict | None             # "pushed", "pulled"
put_cursor(name, value)                      -> None
keep_segment(place_id, entries)              -> None                    # the other place's record
segment_head(place_id)                       -> dict | None             # its last entry held
```

- The cursors and the kept segments move in the transaction that lands what they describe.
- A kept segment is append-only, like the chain it copies; nothing reads it as this place's own.

## 9 · What this does not fix

- **Signing in from the CLI.** `egzos push` presents a provider token for the cloud's own client
  (`identity.md` §3 check 6). Getting one from a terminal is the flagship's to offer; until it does,
  the CLI reads it from the environment.
- **A biometric confirm from the CLI.** The CLI can present the button where the person has none
  (`identity.md` §5); a person with a credential confirms the push where an authenticator can
  answer: `design-gap`, the flagship's.
- **Each project's home place** (§V) is not enforced here: any place may push any project.
- **Live sync and the relay** stay `[LATER]` (§V).
