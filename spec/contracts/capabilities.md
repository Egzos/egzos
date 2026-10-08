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
| `publish` | proposing a widening of audience | yes — the gate, on a widening move (freeze item 3) |
| `curate` | quarantine, and lifting it | yes — `TrustEngine.quarantine` |
| `admin` | creating a container above a node's `structure_floor` (**F2**) | yes — `NodeService.create` |

**`publish` gates proposing a widening** (freeze item 3, the Chief on #31). `organize` is the floor
on both branches of the gate and is checked before the audience delta (`container.md` §6); a move
whose audience widens is then parked only for a token that also holds `publish`. Both refusals carry
one text, so a refusal never says whether the destination's audience is wider. **running.** The
six-capability sentence is DECIDED and unchanged.

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

`interactive | client | none`. A bearer token cannot prove a human, so the token carries the claim
and the container enforces on it. **running** for the first two; `none` is **decided, not running**
([0.3 · 34]).

**A token carries `interactive` or `client`, never `none`.** `none` is an *audit entry's* principal
only: the value `events.md` §2 writes when an append has no caller to name —
`authorization-server.md` §12.2's rows (a), (b), (d), (e) and (h), which fire before any session or
token exists, or on no request at all. A third closed word rather than a nullable field, so that
`principal` stays mandatory and every `audit` reader carries no null branch. `_types.py` types this
split: `Principal` is the three words, `TokenPrincipal` the two a `Token`, an `AudienceMember` or an
item's provenance may carry.

- `principal: interactive` — established, for browser sessions, by the login PKCE performs against
  the container. The flow is `authorization-server.md` §2; **where in it the principal is established
  is issue #61** (Part B, presence composition), as `container.md` §9 already says. In the skeleton
  the interactive owner token *is* the proof; the step-up tap arrives at Phase 2.2.
- `principal: client` — every machine client.
- `principal: none` — no caller. It is never minted onto a token and never presented, so no
  surface enforces on it; it exists only in the chain.
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

**The principal gate is the floor, not the whole gate. [0.3 · 38]** A bearer token cannot prove a
human (§3), and an `interactive` token can be minted to software, so the gate has two parts:

1. **Principal.** A `client` principal is refused outright. **running.**
2. **Presence, the backstop.** An `interactive` principal is necessary and not sufficient. Every
   human-only act additionally requires presence proven within a live presence window, the
   `step_up.window_seconds` of the **ring pair the act crosses**, source → destination, and of the
   act's manifest shape (`container.md` §8, R11). All three acts are gated this way: `yes.consume`
   (decided 2026-10-03), and `approve.pending` and `gate.confirm` ([0.3 · 14]). A window of `0`
   means presence is proven at the act itself, the strictest setting, never that no check runs.
   An expired window, or an absent one where the configured window is nonzero, refuses the act as a
   human-only violation. **decided, not running** (Phase 2.2). Until then the interactive owner
   token is the proof (§3), a stated and dated gap.

The backstop's full text, and the test a conforming container must pass, is
`authorization-server.md` §10.4. A call site that lacks the act's source, destination or manifest
shape cannot evaluate this gate and must not approximate it.

**Interactive tokens are independent of the session that authorized them** ([0.3 · 12];
`authorization-server.md` §10.3). Ending the session revokes nothing. One the AS issues always
expires (§5), and the backstop above, not the session, is what gates a human-only act.

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
- `expires_at` may be null (no expiry) **only on a token the owner mints with `token mint`**.
  A token the authorization server issues always carries `expires_at`, 1 hour by default
  ([0.3 · 17]); the grant behind it expires at 30 days by default and 90 days at most, a longer
  request being clamped ([0.3 · 18]). `authorization-server.md` §9.3 and §11.5 carry the two, and no AS
  path, parameter or config key yields a null.

**Every issued value has at least 128 bits of entropy from the platform CSPRNG. [0.3 · 19]** This is
the container-wide clause `authorization-server.md` §9.1 defers to. It binds every value the
container issues as a secret, **whatever path issues it**: token values from `token mint` as well
as from the AS, refresh tokens, authorization codes and `device_code`s. The amount and the source
are both normative: 128 bits of a weak generator is not 128 bits of entropy. It is a floor on the
random core, not a string length: a prefix or a checksum around a conforming core conforms. A floor
binding only the AS would leave the same forgeable value reachable through another verb. Two things
it does not govern: `Token.id`, an identifier and not a value (it is an audit subject, `events.md`
§4 invariant 4), and the AS's `user_code`, which a human types and which is bounded by attempts
and expiry instead ([0.3 · 20]; `authorization-server.md` §9.1 reading 2). No other value may
borrow that exception.

**Revocation has two paths and one result** ([0.3 · 11]): RFC 7009's endpoint, and the owner
revoking by `Token.id` on the container's pages (`authorization-server.md` §9.2, §11.9). A token
revoked by either is the revoked token above.

**Audience.** The audience of a container is every **live** token whose coverage reaches it —
people **and** agents alike. This is the basis of the conditional gate; see `container.md`.

Minting and revoking are audit events (`token.mint`, `token.revoke`); see `events.md`. Both carry
the refresh-family id where the token has one, and a refresh rotation appends no event of its own
(`events.md` §4 invariant 2; [0.3 · 30]).

## 6 · Silence, not errors

Restated as numbered binding clauses at the 0.3 freeze ([0.3 · 42]). Each clause is normative on
every surface: CLI, both MCP transports, REST, the lifeboat and the authorization server.

1. **One refusal.** A request naming a scope that is **absent**, a scope the token does **not
   cover**, or a covered scope where the token **lacks the capability** gets one refusal, and that
   refusal MUST be **byte-identical to not-found**: the same status, the same body, the same
   headers, the same exit code. No surface may answer any of the three differently from the others
   or from a scope that never existed. The third case is the Chief's decision, not an inference
   from the other two: a capability refusal on a covered scope tells the caller what its token
   cannot do there, and the record closes that too ([0.3 · 42]).
   - **running** for the absent and uncovered cases (the skeleton's write path raises "scope not
     found" when a token does not cover the target: the required behaviour, not a mislabelled
     error).
   - **decided, not running** for the lacking-capability case. These running surfaces still answer
     it with their own text: `store/items.py`'s remember refusal in `Store.add` ("token lacks `remember`");
     `trust.py`'s "quarantine needs `curate`" and its `_MOVE_REFUSED` floor text; and the CLI's
     "needs `admin`" refusals on `token create`, `token revoke` and `connect`. The running not-found
     texts also differ from each other ("not found", "scope not found", "scope not found: <ref>").
     Bringing them into line is #155.
   - **How this fits `container.md` §6's floor-before-delta refusal.** That clause fixes an
     **order**: the gate checks `organize` before it computes the delta, and both gate refusals carry
     one text, so no refusal depends on the branch the move would have taken. Clause 1 changes what
     that one text **is**: the not-found refusal instead of `_MOVE_REFUSED`. The order stays binding
     as it stands. A gate that computed the delta first would still leak through which check failed,
     whatever text it sent.
2. **No enumeration through error shapes, anywhere.** No error text, field, ordering, count or
   pagination cursor may reveal that something the caller cannot see exists. A partial result and
   a result with nothing in the hidden part are indistinguishable (`container.md` §4 invariant 3).
3. **The audit entry may distinguish what the response may not.** The owner's ledger may record
   which of clause 1's three cases occurred, in `details`. The uniformity is owed to the caller,
   never to the owner reading their own container (`events.md` §4 invariant 1 states the same for
   `audit verify`).
4. **Timing is a SHOULD.** A surface SHOULD answer clause 1's three cases in time a caller cannot
   distinguish. It is not a MUST container-wide: equalising every refusal to the cost of a validated
   request gives up part of what a throttle is for. Where a contract makes a timing difference a
   MUST, that contract's clause governs its surface: `authorization-server.md` §5.3 clause 2 does so
   for the two differences that leak a fact about the client registry, and keeps the third, which
   leaks only a fact about the caller's own request, at this SHOULD.
