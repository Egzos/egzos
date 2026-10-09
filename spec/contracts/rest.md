# Contract · the REST door

**Status: draft (Phase 2 boundary, #42).** **Not frozen, and not law.** Opened as a
`contract-change` at the Phase 2 boundary. The Chief and a6-adversary review it before any builder
implements against it. Until that review, no issue that builds against this text is labeled for
dispatch. Where this draft and a frozen document disagree, the frozen document governs, and the
disagreement is a finding against this draft.

**Derivation — read this before any clause below.** Like `authorization-server.md`, this document
has **no running shape**. The walking skeleton has no REST surface: its doors are the CLI, MCP over
stdio and the lifeboat. Every clause is derived from what is already decided, and from nothing else:

- **F5** and `context-item.md` §3: a `BlobGrant` above `blobs.inline_max_bytes`, minted by Trust,
  redeemed at this door. `storage.md` §4–§5: Store renders the grant into a URL and decides nothing;
  silence at the storage boundary. `events.md` §1, §2 and §4: `blob.grant` and `blob.pull`, the
  entry, audit coverage. Issue #42 (the door's row), #138 (running `blob.grant`).
- `capabilities.md` §3–§6: principals, tokens, liveness, and §6's one refusal, byte-identical to
  not-found on every surface (#155).
- `authorization-server.md`: the tokens it issues (§7, §9.3), its TLS clause (§2, [0.3 · 9]), its
  metadata (§6), its browser client (§2) and the session that is not a token (§10.1).
- The flagship's needs per #137, **v1.0 only**: #137 files its twelve asks as v1.1 inputs. Item 8
  (artifact transport) is already v1.0 by F5 and is §6 here. The other eleven are `[v1.1]` below.

The running doors (CLI, `egzos_fetch` / `egzos_remember` / `egzos_inbox`, the lifeboat) are cited
where an endpoint here mirrors one. That makes the endpoint a transport for an operation that
already runs, not a new operation.

Clauses carry one of five markings:

- **decided** — carried from a frozen clause, or from the Chief's recorded decision on an issue,
  which is cited either way. The wording may improve; the decision is the cited source's and may
  not change here.
- **a1p** — a1p's binding of a decided rule onto HTTP. A proposal; the review should read it as one.
- **`[open · #N]`** — a question someone else owns, open on issue `N`. **A builder may not implement
  against one.** The clause says what the door does meanwhile.
- **`[v1.1 · #137 n]`** — deferred to the contract v1.1 boundary at Phase 5 by #137's item `n`.
  Not in this door at v1.0, and a builder may not add it.
- `TODO(chief)` / `TODO(a1p)` — the sources are silent; each line names its issue.

## 1 · What the door is

**An HTTP resource server, in-process with the container, served from the container's own origin**
(the `issuer` of `authorization-server.md` §6). **a1p**, from §K's one AS on the container (#42): the
door accepts the AS's tokens, so it sits where the AS's issuer is.

- **It is not the AS.** `/authorize`, the token, device-authorization and revocation endpoints, the
  metadata document and §11's pages are `authorization-server.md`'s. This document adds no AS
  endpoint, changes none, and sits beside them under one path prefix, `/v1/`. **a1p.**
- **Clients:** any program holding a token, and browser clients that obtained one through
  `authorization-server.md` §2: the flagship, or any fork's UI. The lifeboat is not a client of this
  door; it is in-process on its own host (`spec/design/lifeboat.md`).
- **TLS.** `authorization-server.md` §2's TLS clause and its loopback exemption ([0.3 · 9]) govern
  this door's listener exactly as they govern the AS's: plain HTTP only when the listening socket is
  bound to loopback, decided from the socket and never from a forwarded header. **a1p**: one
  listener serves both, and a door that relaxed the rule would expose the AS's tokens on the hop the
  rule protects. `serve --tls` enforces it (a3-doorman).

## 2 · Authentication

1. **One credential position: `Authorization: Bearer <token value>`.** A token value in a query
   string, a form body, a cookie or any other header is never read. **a1p**: a value in a URL lands
   in logs and referrers.
2. **Any live `Token` is accepted**, from `token mint` or issued by the AS, with principal
   `interactive` or `client` (`capabilities.md` §3, §5). **decided.**
3. **An interactive session is never a credential here** (`authorization-server.md` §10.1: *"never
   accepted at the REST surface"*). A request carrying only a session cookie is unauthenticated.
   **decided.**
4. **Liveness is checked on every request, at request time**: revocation before the capability set
   (`capabilities.md` §5), then `expires_at`. A token revoked between two requests fails the second.
   **decided**; the running MCP door does the same (`_live`).
5. **The unauthenticated answer is one answer.** No header, a malformed value, an unknown value, a
   revoked token and an expired token all get status `401`, the body `{"error":"unauthorized"}`, and
   `WWW-Authenticate: Bearer` with no parameters, byte-identical across the five. **a1p**, applying
   `authorization-server.md` §9.2's silence rule: an answer that varied would test a token value
   without holding one. RFC 9728's `resource_metadata` parameter is the MCP surface, `[v1.1]` by
   `authorization-server.md` §4, and is not sent.
6. **An unauthenticated request appends no entry of its own.** It read nothing, and it has no caller
   to name. **a1p.** Item 7's throttle counts it, and the window's `rest.tally` records it.
7. **The door is throttled on its own `surface` word, `rest`. decided** (the Chief on #165 item 3,
   2026-10-09, https://github.com/Egzos/egzos/issues/165#issuecomment-6073462009). One word covers
   both sweeps the door is open to: token values at its `401` (item 5) and descriptors at its
   redemption route (§6). **a1p** for the rest of this item, reading `authorization-server.md`
   §11.0 and §12.1 onto this door:
   - **What counts:** what a sweep looks like, and nothing else: every `401` answer, and every
     redemption whose descriptor fails §6's check 1 or 2. **decided** (the Chief on #141,
     2026-10-09). A redemption refused at check 3 or later is a refusal of a *verified* descriptor,
     a replay or a retry after a lost response and not a sweep, so it counts toward neither of
     those two buckets; it counts toward the descriptor's own token's bucket, below, and still
     appends its `context.fetch` under the verified caller (§6). A request the door serves, or
     answers with §3's refusal on a live token, does not count anywhere.
   - **A third bucket for verified-descriptor refusals, keyed on the descriptor's token. decided**
     (the Chief on #184, 2026-10-09, settling #141's replay question). Every redemption refused at
     §6's check 3 or later counts toward a bucket keyed on the `token` the verified descriptor
     names. That key is a `Token.id` the container signed (check 2), not a value the caller chose,
     and not a network identifier. Only such refusals count toward it, so one held descriptor's
     chain growth is bounded, and neither a stranger's sweep nor another token's replays spend it.
     **a1p**, the order: the per-token bucket is read after check 2, the first point at which its
     key is known, and before check 3. While it holds, a redemption naming that token gets §3's
     refusal, counted and not evaluated, a valid descriptor included, which is therefore not spent,
     and appends no `context.fetch`: that is the bound. The two outer buckets are read first, as
     for every request at the door.
   - **Two buckets, both enforced** ([0.3 · 24]): one container-global, one keyed on the transport
     source address, never on a value the caller supplies. A network identifier keys a bucket and
     never enters the chain. The `rest` counters are the door's own, so exhausting them never
     locks the owner out of `/login`, and the reverse holds too.
   - **A throttle that holds does not evaluate, and fails closed** (§12.1 rule 4). While either
     bucket holds, every request at the door gets its route's uniform failure, counted and not
     evaluated: `401` on a bearer route, a live token included; §3's refusal at redemption, a
     valid descriptor included, which is therefore not spent. An attempt refused while a bucket
     holds is counted whatever it carries, since the door has not evaluated it. **Owner lockout
     is accepted. decided** (the Chief on #141, 2026-10-09): live tokens are not exempt from the
     container-global hold, since exempting them would validate a token before the throttle runs.
     The cost is one window per engagement, and it is renewable, not a single-window event: a
     sender who refills the container-global bucket in each new window holds it for as long as it
     keeps sending, about 300 requests per 300 s, and the owner's whole door, blob pulls included,
     stays refused while it does (as `authorization-server.md` §11.0 states for the AS surfaces;
     a6 on #184). The decision stands as written, and it is revisited only if it bites in
     practice. TODO(chief), #141: confirm the decision holds for a renewable, not a capped, cost.
   - **The chain.** No attempt at the door appends an engage entry: the door has no per-attempt
     event a caller-less attempt could carry. The release appends `authz.release` with `surface:
     rest`, `refused` and `window_key` whenever the throttle engaged, `refused: 0` included (§12.1
     rule 5). At the close of each container-global window in which the throttle admitted any
     `401`, or any redemption refused at §6's check 1 or 2, the timer appends **`rest.tally`**
     once, as `authorization-server.md` §12 row (h) does: `principal: none`, `actor: rest`, and
     three closed `details` keys, `unauthorized` (the count of those `401`s), `forged` (the count
     of those redemptions) and `window_key`, derived from that bucket as §12.2 states. No such
     admission, no entry. The response is unchanged by any of it.
   - **What pairs, and what stands alone.** Each release's `window_key` is derived from the
     bucket that engaged, as §12.2 states. A release of the container-global bucket pairs with
     that window's `rest.tally`, when one appended, by `window_key`. A release of a per-source
     bucket carries that bucket's key, which joins no other entry: the door appends no engage
     entry, and no tally carries a per-source key. That release is the engagement's whole trace.
     `rest.tally`'s two counts are what the container-global bucket admitted and counted; a
     redemption refused at check 3 or later is in neither, and is attributed in its own
     `context.fetch`. A window can engage with no `rest.tally` at all, so `authz.release`'s
     `refused` is the complete engagement signal. **a1p**, all of this bullet.
   - **What the chain bounds.** An unauthenticated sweep reaches the chain at one `rest.tally` per
     window plus one release per engagement, never once per attempt. A redemption refused at check
     3 or later names its token and appends its own `context.fetch` (§6), at most the per-token
     rate per window per token, plus one release when that bucket engaged. A per-token release
     carries `surface: rest`, `refused` and a `window_key` derived from that bucket (§12.2), and
     no token id: §12.1 rule 5's three keys are closed. It is attributed by the `context.fetch`
     entries of the same window that name the token. That join is exact only when one per-token
     bucket engages in the window. When two or more do, the chain shows which tokens drew
     refusals and each release's `refused`, but not which count belongs to which token: the
     window's per-token releases are attributable to that set of tokens as a whole. **a1p**: the
     limit is accepted rather than closed, since closing it puts a token-derived key in rule 5's
     closed set, a contract change for a phase boundary. TODO(a1p), #141: raise it there if an
     owner needs the per-token split.
   - **Rates. decided** (the Chief on #141, 2026-10-09): container-global, 300 counted attempts
     per 300-second window; per source address, 30 per 300-second window. A bucket that engages
     holds until its window closes. `AS_THROTTLE_WINDOW_SECONDS` and `AS_THROTTLE_RATES["rest"]` in
     `_types.py` carry them. A well-behaved client meets a `401` only on an expired or revoked
     token, a handful per window. A 300-second window shows a sweep on the chain within five
     minutes, the grant's own lifetime (§6), and caps `rest.tally` at 288 entries a day under a
     sustained sweep.
   - **The per-token rate. a1p proposes**, `TODO(chief)`, #141: 30 refusals per token per
     300-second window, the per-source number. A client that retries a lost response meets one or
     two such refusals per grant; 30 bounds one held descriptor at 8,640 attributed entries a day.
     Lockout is per token: while it holds, that token's own downloads at this door are refused
     until the window closes, and no other token's are. The number is not in `_types.py` until the
     Chief confirms it, and a build issue carries it as open.

## 3 · The one refusal

**Every refusal that turns on what exists or what the token may do is one response, defined once,
byte-identical. decided** (`capabilities.md` §6 clause 1, [0.3 · 42]; #155):

```
HTTP/1.1 404 Not Found
Content-Type: application/json
Cache-Control: no-store
X-Content-Type-Options: nosniff

{"error":"not_found"}
```

The status, the four lines and the body bytes are this door's not-found refusal. **a1p**: the
bytes; §6 clause 1 fixes only that they are one. The response carries no other header that varies
with the request (no `ETag`, no `Last-Modified`, no length that differs).

It is the answer to every one of these, with no distinction between them:

- an item, scope or node id that is **absent**, **tombstoned**, or **outside the token's coverage**;
- a covered scope where the token **lacks the capability** the endpoint needs (§4's table);
- an item the serving policy does not serve to this token: quarantined, or an unverified `rule`
  (`container.md` §4–§5, `context-item.md` §5);
- an `interactive`-only endpoint (§4) called with a `client` principal. **a1p**: the running CLI
  refuses this with its own text (`_owner`), and #155 brings it into line;
- a path no route declares, and a method a route does not declare. **a1p**, following the
  lifeboat's R12: a framework `405` would confirm the path exists;
- a `BlobGrant` redemption that fails any check (§6).

**The move gate keeps its order.** `organize` is checked before the audience delta is computed
(`container.md` §6), so the refusal is the same whichever branch the move would have taken.
**decided.**

**The ledger may record which case occurred; the response may not** (`capabilities.md` §6 clause 3).
Timing is a SHOULD (clause 4). **decided.**

**Malformed requests get one other answer.** A request that fails on a fact identical for every
container (unparseable JSON, a missing required field, a `kind` outside `context-item.md` §2, a
`find` query outside the grammar) gets `400` with `{"error":"invalid_request"}` and the same four
headers. **a1p**, by `authorization-server.md` §7.1's split between `invalid_scope` and
`access_denied`. Validation of the request's shape runs **before any lookup**, so a `400` never
depends on an id the request names.

**An ambiguous path tail gets the third answer.** A scope parameter or body field accepts a node id
or a path tail, as `resolve_ref` does (`container.md` §2). A tail that matches more than one node the
token covers is refused and nothing is picked ([0.3 · 1]): status `409`, the same four headers, and
`{"error":"ambiguous","matches":[<path>, …]}`, the paths sorted. **decided**, that the refusal names
the matches; **a1p**, the bytes (#187). The candidates are only the nodes the token covers, so the
answer names nothing the token could not list at `GET /v1/scopes`; a tail whose only matches are
uncovered is §3's refusal. It appends one `context.fetch` with `items: []`, as the running MCP door's
`_probe` does. `GET /v1/find` never answers it: a search covers every match (`store.find`).

## 4 · The v1.0 endpoints

Every response body is JSON. An item is serialised per `context-item.md` §1, unknown fields
included. **The door never renders an item**: a body, a title or a tag is a JSON string value,
returned verbatim, and is data. **a1p.** A browser client that displays one escapes it (its design
spec's job).

| method · path | does | needs | mirrors | events |
|---|---|---|---|---|
| `GET /v1/fetch?scope=&query=&kind=` | resolve the layered context at a scope (default: the token's start, as `egzos_fetch`) | `fetch` | `egzos_fetch` | `context.fetch`; `blob.grant` per §6 |
| `GET /v1/find?q=` | search across what the token sees, in the query grammar of `egzos.store.find` | `fetch` | `egzos find` | `context.fetch` |
| `GET /v1/items/{id}` | one item | `fetch` on its scope | the lifeboat's item read | `context.fetch`; `blob.grant` per §6 |
| `GET /v1/inbox` | captured, not yet wrapped or promoted | `fetch` on the inbox | `egzos_inbox` | `context.fetch` |
| `GET /v1/scopes?under=` | the child nodes of a node the token covers | `fetch` | `egzos ls` | `context.fetch` |
| `POST /v1/items` | write a text item; it lands `unverified` | `remember` on the target scope | `egzos_remember` | `item.add` |
| `POST /v1/items/{id}/move` | move an item; the gate decides | `organize`; `publish` to propose a widening | `egzos mv` | `item.move` and `gate.pass.silent`, or `gate.propose` |
| `POST /v1/scopes` | create a container node | coverage of the parent; `admin` above its `structure_floor` | `egzos mk` | `node.create` |
| `GET /v1/pending` | unverified items and open proposals | an `interactive` principal | `egzos trust pending` | `context.fetch` |
| `GET /v1/blobs/{sha256}?…` | redeem a `BlobGrant` | the grant (§6) | — (new: F5) | `blob.pull` |

**a1p**: the paths, the parameters and the request bodies. **decided**: each row's capability and
event, from the running door it mirrors, the capability table in `capabilities.md` §1, and
`structure_floor` (F2). `GET /v1/scopes` and `POST /v1/scopes` read and create nodes; a node read
is a read, so it appends `context.fetch` (`events.md` §4 invariant 2). `POST /v1/scopes` needs no
capability at or below the floor, only coverage of the parent, as `NodeService.create` runs today;
a create above the floor without `admin` is §3's refusal, not the CLI's "needs admin" text (#155).

**Lists are viewer-scoped and complete.** `fetch`, `find`, `inbox`, `scopes` and `pending` return
what the token may see and nothing else: no count of what was withheld, no marker where something
was, and no pagination in v1.0. A list with hidden members and a list without them are
indistinguishable (`capabilities.md` §6 clause 2). **decided**; `withheld` belongs in the ledger
entry, as the running doors write it. Cursor pages are `[v1.1 · #137 7, 10]`.

**A refusal appends a read.** A request naming a scope or item that §3 refuses appends one
`context.fetch` with `items: []`, identical for every case. **a1p**, following the running MCP door
(`_probe`: *"a probe is a read too"*). The case may be recorded in `details` (§3).

**Attribution.** Every entry this door appends carries `actor` = the token's `owner`, `principal` =
the token's principal and `client` = the token's `client`. Never `none` (`events.md` §2). **decided.**

**`POST /v1/items` writes text only.** An artifact upload is `TODO(a1p)`, #42: the staging rule for
an agent-proposed artifact (`storage.md` §4) and the dedup rule ([0.3 · 41]) apply to it, and no
running door uploads over HTTP to derive the shape from.

### 4.1 · Success responses (#187)

**a1p**, every clause of this subsection unless it cites otherwise: the bodies below bind the running
shapes each row mirrors onto HTTP (`Resolver.resolve`, `store.find`, `Trust.move`, `Trust.pending`,
`NodeService.create`). A field not named here is not on the wire, and a builder adds none.

**One status, the same headers.** Every success is `200 OK` with the three header lines of §3's
refusal (`Content-Type: application/json`, `Cache-Control: no-store`, `X-Content-Type-Options: nosniff`) and
no `ETag`, `Last-Modified` or `Location`. A write answers `200` too: the body says what happened, and
a create, a silent move and a parked proposal never differ by status code. A cached success beside an
uncached refusal would make the two distinguishable in a shared cache, and a body is user data that
no intermediary keeps. §6's redemption is the one exception: it streams bytes under its own headers.

**Every body is a JSON object, never a bare array.** Each list sits under a key that names its
members, so a v1.1 key (`[v1.1 · #137 7, 10]`'s cursors) is an addition, not a break. A client
ignores a top-level key it does not know. No body carries `withheld`, a count, or any other trace of
what the token was not served (§4's lists rule): the count is the ledger's, as the running doors
write it. This also closes `container.md` §4's `TODO(a1p)` for this door, since no shape here
differs between a silent refusal and an empty result.

**No framing.** The MCP door's `banner` and per-response `fence` exist for a model reading the result
as prompt text. This door returns JSON values, and §4's "data" rule is its framing: a body carries
neither.

**Request bodies** are JSON objects. A missing required field, a field of the wrong type, or a field
the row does not name is `400` (§3).

| route | request | `200` body |
|---|---|---|
| `GET /v1/fetch` | — | `{"scope": <path>, "chain": [<layer>], "items": [<entry>]}` |
| `GET /v1/find` | — | `{"items": [<entry>]}` |
| `GET /v1/items/{id}` | — | `<entry>` |
| `GET /v1/inbox` | — | `{"items": [<entry>]}` |
| `GET /v1/scopes` | — | `{"nodes": [<node>]}` |
| `POST /v1/items` | `{"body", "kind"?, "scope"?, "key"?, "tags"?}` | `{"item": <item>}` |
| `POST /v1/items/{id}/move` | `{"to"}` | `{"result": "moved", "item": <item>}` or `{"result": "pending", "proposal": <id>}` |
| `POST /v1/scopes` | `{"type", "name", "parent"?}` | `{"node": <node>}` |
| `GET /v1/pending` | — | `{"items": [<item>], "proposals": [<proposal>]}` |

- **`<item>`** is a `ContextItem` per `context-item.md` §1, unknown fields included, returned as
  stored. Nothing in this subsection is ever added inside it.
- **`<entry>`** is `{"item": <item>, "layer": <path>, "layer_type": <type>, "shadowed_by": <id> |
  null}`, `container.md` §4's `ResolvedItem` with its `trust` key removed as that clause decides,
  plus, when §6 minted a grant for this read, `"grant": <BlobGrant>` and `"grant_url": <string>`.
  The two grant keys are absent otherwise, never `null`. **They sit beside `item`, never inside it
  or its `content`**: a grant is a fact of this read and this token, as `shadowed_by` is a fact of
  this resolution, and a client that wrote an item back would otherwise persist a credential into
  it. §6 item 4 is read this way.
- **`<layer>`** is `{"node": <id>, "path": <path>, "type": <type>, "policy": "serve-unverified" |
  "verified-only"}`, the running resolver's layer. `chain` lists only the layers the token covers,
  innermost first (`container.md` §3, §4 invariant 3).
- **`<node>`** is `{"id", "type", "name", "parent", "created_at", "path"}`: `container.md` §2's
  persisted node plus its computed path, unknown fields included.
- **`<proposal>`** is `container.md` §6's parked proposal, `_types.Proposal` with the wire key
  `from` (`PROPOSAL_WIRE_KEY_FROM`).
- **`<path>`** is a path as `NodeService.path` renders it (`container.md` §2).

**Per route:**

1. **`GET /v1/fetch`** carries the layering, not a flat list: `scope` is the resolved scope's path,
   `chain` the covered layers, and `items` every served item in layer order, innermost first,
   shadowed items included with `shadowed_by` set (`container.md` §4, most-specific-wins). Within a
   layer the order is newest first by `lifecycle.created_at`, the sqlite backend's running order,
   with ties broken by `id` descending, which the backend does not yet do.
2. **`GET /v1/find`** returns its hits newest first by `lifecycle.updated_at`, then by `id`
   descending, as `store.find` does. `layer` is the hit's own node's path and `shadowed_by` is
   always `null`: a search resolves no chain.
3. **`GET /v1/items/{id}`** returns one `<entry>`, `layer` its own node, `shadowed_by` `null`.
4. **`GET /v1/inbox`** returns the inbox's served items as entries whose `layer` is each item's
   thread (`egzos_inbox`'s `thread`). This row mints no grant (§4's table has no `blob.grant` on
   it): an artifact above the threshold carries neither `inline` nor `grant`, and a client reads it
   at `GET /v1/items/{id}`.
5. **`GET /v1/scopes`** returns the child nodes of `under`, sorted by path. `under` absent is the
   personal root, as `egzos_fetch`'s default.
6. **`POST /v1/items`** returns the item as written: `trust.status` is `unverified` (`container.md`
   §5). `kind` defaults to `memory`; `scope` absent is pure capture, a fresh auto-titled thread in
   the inbox (R11), as `egzos_remember`.
7. **`POST /v1/items/{id}/move`** tells the gate's two branches apart by `result` alone. `moved`
   is the silent pass (`gate.pass.silent`) and carries the item at its new scope, unverified again
   where the mover is a client (`_reset_if_agent_run`). `pending` is the parked proposal
   (`gate.propose`) and carries **its id and nothing else**. The proposal's `audience` names other
   tokens' owners and clients: credential metadata, which this door serves only to the interactive
   principal at `GET /v1/pending`, since a client-facing token read needs the event `[v1.1 · #137
   10]` defers. The flagship's *moved* and *pending* states read `result`.
8. **`POST /v1/scopes`** returns the created node. `parent` absent is the personal root, as
   `egzos mk`.
9. **`GET /v1/pending`** is two lists, as `Trust.pending` returns them: `items`, every `unverified`
   item in a scope the token covers, and `proposals`, every `open` proposal the token decides over
   (`Trust.decides_over`: it covers both ends). Both are viewer-scoped; the running CLI lists every
   pending item and proposal because its owner token covers `*`, and a narrower interactive grant
   (`authorization-server.md` §7) sees only its own. Quarantined items are never in `items`
   (`container.md` §4 invariant 2). `TODO(chief)`, #187: `items` includes an unverified `rule`, as
   `egzos trust pending` and the lifeboat's queue show one today, because promotion is read from
   this queue. §3 refuses an unverified rule at every other route; confirm the queue is the one
   place an `interactive` principal reads one.

**Not in this door at v1.0:**

- **Human-only acts**: promote, approve, deny, `gate.confirm`, `yes.consume`. Each requires
  `capabilities.md` §4's presence backstop, which is Phase 2.2 and decided-not-running, and the step-up
  tap's endpoints are Phase 2.2's (`authorization-server.md` §13). No REST route performs one until
  then. A `client` principal is refused one in every phase.
- **Token management.** Revocation is `authorization-server.md` §9.2's: the RFC 7009 endpoint, or
  the owner's pages. A token list needs a read event for credential metadata that `events.md` does
  not have: `[v1.1 · #137 10]`.
- **Quarantine and config.** No flagship screen #137 cites needs either at v1.0. They stay on the CLI.
- **`[v1.1 · #137 1–7, 9–12]`**: a revision on reads (1); window state and its events (2, 3);
  `return_to` (4); writability per scope (5); a nonzero-delta move inside a window (6); pending
  facets and filters (7); anomaly sentences (9); token reads and their events (10); where coverage is
  computed (11); a quarantine flag per ring (12). A builder adds none of them.

## 5 · Audit coverage

`events.md` §4 invariant 2 binds this door without exception: every read, grant mint and blob pull
is an event, and a door that produces an effect without one is non-conforming. **decided.** The
table in §4, with §2 item 7's `rest.tally` and `authz.release`, is the whole list of what the door
appends. A test per row asserts the event.

The two invariant-2 exceptions (the owner's read inside an AS session; refresh rotation) are the
AS's, and neither reaches this door: §2 accepts no session. **decided.**

## 6 · `BlobGrant` — issue and redemption

**Issue. decided** (F5; `context-item.md` §3; `storage.md` §4):

1. When a read in §4 serves an `artifact` item, `inline` carries the bytes only when the size is at
   or below `blobs.inline_max_bytes` **and** `mime` matches `text/*`.
2. Otherwise the door asks Trust: `Trust.authorize_pull(token, item) -> BlobGrant | silence`. Trust
   applies the same capability, coverage and serving check as a fetch: **artifact download IS
   fetch**. A minted grant appends `blob.grant`. On silence the item is served with no grant.
3. Store renders the grant into a URL. It decides nothing, and it never mints on its own authority.
4. The response carries the item with `grant` (the descriptor `{sha256, item, token, expires_at,
   sig}`) and `grant_url` beside it. **a1p**: the two field names.

**The URL. a1p:**

```
/v1/blobs/<sha256>?item=<item id>&token=<Token.id>&expires_at=<UTC ISO-8601>&sig=<sig>
```

`token` is the `Token.id`, an identifier and not a value (`capabilities.md` §5).

**Redemption is the descriptor, and only the descriptor. a1p**, from `context-item.md` §3: *"a stdio
client receives the descriptor and redeems it at the REST door"*. A stdio client holds no token
value, so redemption takes no `Authorization` header and consults none. **The cost, stated for the
review:** a grant URL is redeemable by whoever holds it, so the grant is bounded twice.

**A grant is single use and lives 300 seconds. decided** (the Chief on #165 item 1, option (a),
2026-10-09, https://github.com/Egzos/egzos/issues/165#issuecomment-6073462009):

- **Single use.** The first verified redemption spends the grant. **a1p**, reading "verified" as
  checks 2 and 3 below: a redemption whose `sig` verifies and whose `expires_at` has not passed
  spends the grant at check 4, **whatever checks 5–8 then decide**. A grant refused at check 5 is
  still spent.
  The spend is atomic: of two concurrent redemptions of one grant, at most one passes check 4.
- **A fixed contract lifetime of 300 seconds from the mint.** Trust sets `expires_at` to the mint
  time plus 300 seconds (`_types.py`'s `BLOB_GRANT_LIFETIME_SECONDS`). **It is not configurable**:
  no config key, no flag and no client parameter lengthens or shortens it.
- A leaked `grant_url` is therefore dead after one pull, or after five minutes at most.
- The spent record is kept until the grant's `expires_at`, keyed on the sha256 of the descriptor's
  `sig` and never on the `sig` itself: with the other four fields, the `sig` is the credential, as
  `storage.md` §3.1 keys the AS's single-use state on credential hashes. **a1p.** Where it is
  persisted joins #165 item 4's batch, beside the grant key.

**The redemption checks, in this order. decided** for each check, **a1p** for the order:

1. Every query parameter is present and well-formed. Otherwise, §3's refusal.
2. `sig` verifies under the container key, over every descriptor field other than `sig`, compared in
   constant time (`context-item.md` §3).
3. `expires_at` has not passed.
4. The grant has not been spent, and this redemption spends it (single use, above).
5. The named token is live (revocation first) and still holds `fetch` over the item's scope, checked
   now, not at mint.
6. The item is still served to that token: not tombstoned, not quarantined, within the serving
   policy.
7. `<sha256>` in the path equals the descriptor's `sha256` and the item's `content.sha256`.
8. `BlobStore.get(sha256)` returns bytes.

Any failure is §3's refusal, byte-identical, whichever check failed. **decided**
(`capabilities.md` §6 clause 1, `storage.md` §5). Between checks 2 and 3 the door reads §2 item 7's
per-token bucket for the named token; while it holds, the redemption stops there with the same
refusal, so the response never says which bucket or check refused it. **a1p**, the placement.

**On success** the door streams the bytes and appends one `blob.pull` (`subject` the item, `scope`,
`sha256`, `size`), attributed to the token the descriptor names. **decided** (`events.md` §1).

**The bytes are never rendered on the container's origin. a1p**: the AS's pages share this origin,
so an HTML or SVG artifact served as its own `mime` would run script beside the login. The response
carries:

```
Content-Type: application/octet-stream
Content-Disposition: attachment
X-Content-Type-Options: nosniff
Content-Security-Policy: sandbox
Cache-Control: no-store
Referrer-Policy: no-referrer
```

**A refused redemption leaves a trace.** #138's audit note: no refused pull may leave no trace.

- Where the descriptor verifies (check 2 passed), the refusal appends `context.fetch` with
  `items: []` and the failed check in `details`, attributed to the named token. The lifeboat records
  a refused download this way. **a1p.**
  A replayed or expired grant is refused this way. Such a refusal counts toward §2 item 7's
  per-token bucket, keyed on the descriptor's `token`, and toward neither the container-global nor
  the per-source bucket. While that token's bucket holds, a redemption naming it is refused
  without evaluation and appends no entry; the bucket's release is the trace. **decided** (the
  Chief on #184, 2026-10-09).
- Where it does not verify (check 1 or 2 failed), the container has no caller it can name, and no
  entry is attributed to one. The refusal is counted by the `rest` throttle and tallied under
  `forged` in the window's `rest.tally` (§2 item 7), so a flood of forged descriptors leaves a
  trace. **decided** (the Chief on #165 item 2, option (b), 2026-10-09); **a1p**, the shape.

**The key.** `TODO(a1p)`, #165 item 4: where the HMAC key is provisioned, stored and rotated.
Rotation voids every outstanding grant. It is drafted in the #143 batch, with the login secret and
the device-code key `storage.md` §3.1 names.

**The lifeboat's same-origin route** redeems the same descriptor under the same checks on its own
host (#138). It is a5-dinghy's and is not an endpoint of this door. The deployment preview limit
#138 asks for is `container.md`'s, open on #138.

## 7 · Browser clients (#153)

A browser client reaches this door with a token from `authorization-server.md` §2. #153's five
questions are decided, and `authorization-server.md` §2.1 records the answers. Four of them are the
AS's, and no clause here depends on them: where the code is returned (q1), the flagship's
`client_id` (q3), the request's `scope` (q4, since this door enforces whatever grant the minted
token carries), and RFC 9207's `iss` (q5).

**CORS at this door (q2). a1p proposes**, `TODO(chief)`, #153. The Chief's answer names the token
and revocation endpoints. The flagship calls this door cross-origin too, so the proposal carries the
same derivation here:

- Every `/v1/` route except `GET /v1/blobs/{sha256}` answers a cross-origin request for exactly the
  origins `authorization-server.md` §2.1 item 2 derives from the registry, with the same headers,
  `Vary: Origin` included. A preflight from an allowed origin also gets
  `Access-Control-Allow-Methods: GET, POST` and `Access-Control-Allow-Headers: Authorization,
  Content-Type`. `Access-Control-Allow-Credentials` is never sent: a session is not a credential
  here (§2 item 3).
- **The headers are identical on a success, a `401`, a `400`, a `409` and §3's refusal**, for one
  `Origin`. They depend on the `Origin` and the registry only, never on the token, the route's
  match or what exists. Otherwise a cross-origin caller could tell §3's refusal from a success by
  whether it could read the response at all.
- A preflight is answered before authentication and appends nothing. It names no resource, and the
  throttle (§2 item 7) does not count it: a preflight is not an attempt.
- The redemption route sends no `Access-Control-*` header. A grant URL is opened as an attachment
  (§6), never read by a page's script.

Until the Chief confirms it, a builder may not implement CORS at this door, and the door sends no
`Access-Control-*` header.

## 8 · What this document does not fix

The AS's endpoints, pages, tokens and their events → `authorization-server.md`. The MCP HTTP
transport, protected-resource metadata and the `resource` parameter → contract v1.1 at Phase 5
(`authorization-server.md` §4). The step-up tap and every human-only act over HTTP → Phase 2.2. The
lifeboat → `spec/design/lifeboat.md`. Where the AS's state and the grant key persist →
`authorization-server.md` §13's `TODO(a1p)` and #165 item 4. The look of any client → its design
spec.
