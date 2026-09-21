# Contract · capability vocabulary, principals and tokens

**Status: drafted — awaiting the Phase 0.3 freeze review.** Not law yet.

**Derivation.** RUNNING shapes of the walking skeleton (`docs/build/WALKING-SKELETON.md` §6); code
`src/egzos/model.py` (`CAPABILITIES`, `ROLE_BUNDLES`, `PRINCIPALS`, `HUMAN_ONLY_ACTS`),
`src/egzos/auth.py`, `src/egzos/trust.py`. Clauses are marked **running**, **decided, not running**,
or `[OPEN→0.3]`.

## 1 · Six capabilities, and only six

```
fetch  <  remember  <  organize  <  publish  <  curate  <  admin
```

**Six is the entire vocabulary** (decisions log v0.3 §5, DECIDED). The ladder is an ordering for
display and reasoning; a token carries an explicit set, not a level. **running**

| capability | what it gates | enforced in the skeleton |
|---|---|---|
| `fetch` | reading context; **artifact download IS fetch** | yes — resolver, blob pull |
| `remember` | writing, **same-scope only**: the token must cover where the write lands | yes — `Store.add` |
| `organize` | moving items between containers | yes — the gate |
| `publish` | proposing a widening of audience | `[OPEN→0.3]` |
| `curate` | quarantine, and lifting it | yes — `TrustEngine.quarantine` |
| `admin` | creating a container above a node's `structure_floor` (**F2**) | yes — `NodeService.create` |

`[OPEN→0.3]` **`publish` has no distinct enforcement point in the skeleton.** A move whose audience
widens is parked as a proposal regardless of the mover's capabilities, and the confirm is human-only
— so `publish` currently gates nothing that `organize` does not already reach. The freeze review
must either give `publish` a checkable meaning or record why it is carried unenforced. It is **not**
dropped here: the six-capability sentence is DECIDED and a1p does not edit a DECIDED sentence.

### `structure` is not a capability

Creating containers is governed by a **per-node scope-policy floor**, not a seventh capability
(**F2**): `node.policy.structure_floor` in `{thread, project, team, org, exo}`, default `project`.
Creating a container of a type *above* the floor at that parent requires `admin`. Defined in
`container.md`. This is what keeps the vocabulary six wide and `token ls` six columns. **running**
(as the default floor; the per-node policy object is **decided, not running**).

## 2 · Role bundles

Convenience names for capability sets. The bundle is expanded at mint time and the **token carries
the capabilities**, not the bundle name — a bundle's later redefinition cannot widen a live token.

| role | capabilities |
|---|---|
| `reader` | `fetch` |
| `contributor` | `fetch`, `remember` |
| `operator` | `fetch`, `remember`, `organize`, `publish` |
| `curator` | `fetch`, `remember`, `organize`, `publish`, `curate` |
| `admin` | all six |

**running.**

## 3 · Principals

`interactive | client`. A bearer token cannot prove a human, so the token carries the claim and the
container enforces on it. **running**

- `principal: interactive` — established, for browser sessions, by the login PKCE performs against
  the container (`authorization-server` surface, issue #29). In the skeleton the interactive owner
  token *is* the proof; the step-up tap arrives at Phase 2.2.
- `principal: client` — every machine client.
- **`serve` refuses to run on an interactive token.** The door is not opened with the human's own
  credential. **running**

## 4 · Human-only acts sit outside the vocabulary

**No capability reaches a human-only act, including `admin`.** A maximally granted client can only
**propose**. The running acts are:

- `gate.confirm` — approving or denying a parked proposal
- `approve.pending` — promoting an item from unverified to verified
- `yes.consume` — consuming a step-up confirmation (reserved; Phase 2.2)

An attempt by a `client` principal is refused as a human-only violation. This is a product
invariant, not a policy: it is not configurable, and no deployment may relax it. **running**

## 5 · Tokens

```
{ id, principal, owner, client, capabilities, scopes, created_at, last_used, revoked, expires_at }
```

**running.** Notes that are contract, not implementation:

- **`scopes` are node ids.** Coverage is **computed down the path at check time**, not expanded at
  mint time: a token scoped to a node covers containers created under it afterwards. `["*"]` means
  the whole container and is the owner's token.
- `owner` is on every token — capability lives in the token, not in the surface that presents it.
- A revoked token has **no** capabilities: revocation is checked before the capability set.
- `expires_at` may be null (no expiry).

**Audience.** The audience of a container is every **live** token whose coverage reaches it —
people **and** agents alike. This is the basis of the conditional gate; see `container.md`.

Minting and revoking are audit events (`token.mint`, `token.revoke`); see `events.md`.

## 6 · Silence, not errors

A capability failure and a not-found MUST be indistinguishable to the caller wherever the
difference would reveal that something exists. The skeleton's write path raises "scope not found"
when a token does not cover the target — that is the required behaviour, not a mislabelled error.
No enumeration through error shapes, anywhere. **running**
