# Contract · the REST door

**Status: contract v1.1 — law from the Chief's merge of the commit that set this line** (2026-10-23,
decisions v0.7; tracking #283). Opened as a draft at the Phase 2 boundary (#42); from that merge a
builder implements against it. Where it and
another contract disagree, the disagreement is a finding against whichever is newer, raised before
either is built.

**Amended for contract v1.1 (2026-10-23).** The container's own authorization server is retired
(decisions v0.7 §S). This door accepts the container's own `Token` and access tokens signed by the
container's identity provider, as `identity.md` defines; §1, §2, §7 and §8 below say so. Clauses that
still cite `authorization-server.md` for a rule this door keeps (the TLS rule, the throttle's
mechanics) now own that rule here; the retired document is only its record.

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

**An HTTP resource server, in-process with the container, served from the container's own origin**,
under one path prefix, `/v1/`. **decided** (v0.7 §S; `identity.md` §1): there is no authorization
server on the container; tokens come from the container's identity provider, or are the container's
own.

- **Clients:** any program holding a container `Token` or a provider access token bound to this
  container (`identity.md` §3a), and browser clients holding such a token for the person: egzos.io, or
  any fork's UI. A bare provider session is never accepted. The lifeboat is not a
  client of this door; it is in-process on its own host (`spec/design/lifeboat.md`).
- **TLS.** Plain HTTP only when the listening socket is bound to loopback, decided from the socket and
  never from a forwarded header ([0.3 · 9], frozen for the retired AS and owned here now). A door that
  relaxed it would expose bearer tokens on the hop the rule protects. `serve --tls` enforces it
  (a3-doorman).

## 2 · Authentication

1. **One credential position: `Authorization: Bearer <token value>`.** A token value in a query
   string, a form body, a cookie or any other header is never read. **a1p**: a value in a URL lands
   in logs and referrers.
2. **Two credentials are accepted** (`identity.md` §1): a live container `Token` (`capabilities.md`
   §3, §5), or a provider access token that passes `identity.md` §3, which maps it to a principal and
   a grant (§4 there). **decided** (v0.7 §S, §T).
3. **No cookie is ever a credential here.** A browser client presents, as the bearer, the token the
   provider issued for this container's client (`identity.md` §3a, §6), never the user's session. A
   request carrying only a cookie is unauthenticated. **decided.**
4. **Liveness is checked on every request, at request time**: for a `Token`, revocation before the
   capability set (`capabilities.md` §5), then `expires_at`; for a provider token, every check of
   `identity.md` §3, the grant included. A token or grant revoked between two requests fails the
   second. **decided**; the running MCP door does the same for a `Token` (`_live`).
5. **The unauthenticated answer is one answer.** No header, a malformed value, an unknown value, a
   revoked token, an expired token, and every failure of `identity.md` §3 get status `401`, the body
   `{"error":"unauthorized"}`, and `WWW-Authenticate: Bearer` with no parameters, byte-identical
   across all of them. **a1p**, applying
   `capabilities.md` §6 clause 1: an answer that varied would test a token value without holding one.
   RFC 9728's `resource_metadata` parameter belongs to the MCP surface at `/mcp` (`identity.md` §7)
   and is not sent on `/v1/`.
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
| `POST /v1/items` | write an item — text, or an artifact from an upload (§4.4); it lands `unverified` | `remember` on the target scope | `egzos_remember` | `item.add`; `blob.put` where an artifact is promoted |
| `POST /v1/uploads` | open an artifact upload (§4.4) | `remember` on its scope | — (new) | none |
| `PUT /v1/uploads/{id}` | send the upload's bytes; they are staged (§4.4) | the opener | — (new) | `upload.put`; or `context.fetch` on a refused id |
| `DELETE /v1/uploads/{id}` | discard an orphaned upload and its staged bytes (§4.4) | the opener, or an admin | — (new) | `upload.discard` |
| `POST /v1/items/{id}/move` | move an item; the gate decides, and asks for the confirm inline when the audience widens (§4.2) | `organize`; `publish` to widen | `egzos mv` | `item.move` with `gate.pass.silent`; or `context.fetch` (first leg), then `step_up`, `gate.pass.confirmed` and `item.move`; or `gate.propose` |
| `POST /v1/items/{id}/copy` | copy an item; the same gate as move (§4.2) | `fetch` on the source; `remember` and `organize` on the destination; `publish` to widen | — (new: v0.7 §V) | as move, with `item.copy` |
| `POST /v1/pending/{proposal}/approve` | approve a parked proposal, with the confirm (§4.2) | an `interactive` principal that decides over it | `egzos trust approve` | `context.fetch` (first leg); `step_up`, then `approval.execute` or `approval.stale` |
| `POST /v1/pending/{proposal}/deny` | deny a parked proposal, with the confirm | as approve | `egzos trust deny` | `context.fetch` (first leg); `step_up`, `approval.deny` |
| `POST /v1/items/{id}/promote` | promote an unverified item to verified, with the confirm | an `interactive` principal covering its scope | `egzos trust promote` | `context.fetch` (first leg); `step_up`, `approval.promote`; `blob.put` where a staged artifact's bytes are promoted (§4.4) |
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

**Attribution.** Every entry this door appends names its caller, never `none` (`events.md` §2). For a
container `Token`: `actor` = its `owner`, `principal` its principal. For a provider token: as
`identity.md` §3a's attribution clause — a person is `actor: user:<sub>`; an agent is `actor:
agent:<client_id>` with `details.for: user:<sub>`. **decided.**

**Artifacts arrive through an upload** (§4.4): the staging rule for an agent-proposed artifact
(`storage.md` §4) and the dedup rule ([0.3 · 41]) apply to it.

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
| `POST /v1/items` | `{"body", "kind"?, "scope"?, "key"?, "tags"?}`, or `{"kind": "artifact", "upload", "scope"?, "key"?, "tags"?}` (§4.4) | `{"item": <item>}` |
| `POST /v1/uploads` | `{"scope", "name", "mime", "size", "sha256"}` | `{"upload": <id>, "expires_at"}` |
| `PUT /v1/uploads/{id}` | the raw bytes | `{"upload": <id>, "sha256"}` |
| `DELETE /v1/uploads/{id}` | — | `{"result": "discarded"}` |
| `POST /v1/items/{id}/move` | `{"to", "confirm"?}` | `{"result": "moved", "item": <item>}`, `{"result": "confirm", …}` (§4.2) or `{"result": "pending", "proposal": <id>}` |
| `POST /v1/items/{id}/copy` | `{"to", "confirm"?}` | `{"result": "copied", "item": <item>}` (the new copy), `{"result": "confirm", …}` or `{"result": "pending", "proposal": <id>}` |
| `POST /v1/pending/{proposal}/approve` | `{"confirm"?}` | `{"result": "confirm", …}` (§4.2), then `{"result": "executed", "item": <item>}` or `{"result": "stale"}` |
| `POST /v1/pending/{proposal}/deny` | `{"confirm"?}` | `{"result": "confirm", …}`, then `{"result": "denied"}` |
| `POST /v1/items/{id}/promote` | `{"confirm"?}` | `{"result": "confirm", …}`, then `{"result": "promoted", "item": <item>}` |
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
7. **`POST /v1/items/{id}/move`** tells the gate's outcomes apart by `result` alone. `moved`
   is the silent pass (`gate.pass.silent`), or the confirmed one (`gate.pass.confirmed`, §4.2), and
   carries the item at its new scope, unverified again where the mover is a client
   (`_reset_if_agent_run`). `confirm` asks the human (§4.2). `pending` is the parked proposal
   (`gate.propose`) and carries **its id and nothing else**. The proposal's `audience` names other
   tokens' owners and clients: credential metadata, which this door serves only to the interactive
   principal at `GET /v1/pending`, since a client-facing token read needs the event `[v1.1 · #137
   10]` defers. The flagship's *moved* and *pending* states read `result`.
8. **`POST /v1/scopes`** returns the created node. `parent` absent is the personal root, as
   `egzos mk`.
9. **`GET /v1/pending`** is two lists as `Trust.pending` returns them, plus §4.4's `staged` and
   `uploads` where the reader has any: `items`, every `unverified`
   item in a scope the token covers, and `proposals`, every `open` proposal the token decides over
   (`Trust.decides_over`: it covers both ends). Both are viewer-scoped; the running CLI lists every
   pending item and proposal because its owner token covers `*`, and a narrower grant (`identity.md`
   §4) sees only its own. Quarantined items are never in `items`
   (`container.md` §4 invariant 2). `items` includes an unverified `rule`, as `egzos trust pending`
   and the lifeboat's queue show one today, because promotion is read from this queue: the queue is
   the one place an `interactive` principal reads one, and §3 refuses an unverified rule at every
   other route. **decided** by the Chief's merge of this PR, closing #187's `TODO(chief)` on the
   running behaviour: the one carve-out from "rules are served verified-only", and only to the person
   who decides whether a rule becomes verified.

10. **`POST /v1/items/{id}/copy`** answers as move does. `copied` carries the new item: a fresh id, the
   destination's scope, `trust.status` `unverified` (the copy is a new write), `provenance.derived_from`
   the source's id; the source is unchanged. Bytes are not duplicated: an artifact copy names the same
   `content.sha256` ([0.3 · 41]'s dedup).

### 4.2 · The confirm at this door

The confirm (`identity.md` §5) is how a person says yes to something that widens who can see an item,
and to every human-only act. **decided** (v0.7 §U); **a1p** the HTTP shape.

1. **Two legs, one route.** A confirm-gated request — a move or copy whose audience delta is
   non-empty, asked by an `interactive` principal holding `publish`; or approve, deny or promote —
   sent **without** a `confirm` field moves and decides nothing. After the route's own checks pass
   (coverage and capability first, `container.md` §6's order, so a token that may not do the act gets
   §3's refusal whatever the delta), it answers `{"result": "confirm", "newly": [<name>],
   "challenge": <id>, "webauthn": <options> | null, "expires_at"}`. `newly` names who would newly see
   the item — each grant's or registration's display name — and is `[]` for approve, deny and promote
   of an item already in place. The same request sent again **with** `confirm` completes it (item 3).
   There is no separate challenge route: a challenge exists only as the first leg of the act it is for.
2. **The first leg is a read, and is audited.** It appends one `context.fetch` with `items: []`,
   `subject` the item or proposal, and `details: {"confirm_for": <act>, "newly": [<name>]}`: showing
   who would newly see an item is a read of credential metadata (`events.md` §4 invariant 2). It is
   served only to the `interactive` principal about to act — the same reader `GET /v1/pending` serves a
   proposal's audience to.
3. **The second leg** carries `"confirm": {"challenge": <id>, "proof": "biometric", "assertion":
   <WebAuthn assertion>}`, or `"proof": "button"` with no assertion where `confirm.allow_button` is
   `true` **and the person has no registered credential** — once they have one, the button is refused
   for them (`identity.md` §5). The container then, as **one atomic step** — of two concurrent requests
   presenting one challenge, at most one proceeds past it, as §6's grant spend:
   - finds the challenge live, unspent and **bound to this request**: the same principal (the
     `Token.id`, or the provider token's `sub` and `client_id`), the same act, subject and destination,
     and the same audience delta, recomputed now;
   - verifies the proof (`identity.md` §5);
   - spends the challenge.

   Then it appends `step_up` (`outcome: confirmed`, `details.proof`), the act's gate or approval event
   (`gate.pass.confirmed` with `audience_delta` and the `step_up`'s `seq`; or `approval.execute` /
   `approval.stale`, `approval.deny`, `approval.promote`), and `item.move` or `item.copy` where one
   moved.
4. **Every proof that is presented and concludes is audited, success or failure.** A stale, spent,
   foreign or mismatched challenge, a failed assertion, a button where buttons are off, and a delta
   that changed since the challenge append `step_up` with `outcome: refused`, `details.proof` as
   presented and `details.reason` (`stale`, `spent`, `foreign`, `mismatch`, `assertion`, `button_off`,
   `delta_changed`), as `events.md` §1 requires of every concluded presence check. The answer to the
   caller is the same whatever the reason: `{"result": "confirm", …}` with a fresh challenge (and the
   new `newly`, where the delta changed). The ledger says which case it was; the response does not
   (`capabilities.md` §6 clause 3).
5. **A challenge is single use and lives `step_up.window_seconds`, at least 60 seconds.** A proof
   that concludes spends its challenge whether it is confirmed or refused, as §6's grant is spent at
   check 4 whatever the later checks decide (a6 on #284); a refused attempt always gets a fresh one.
6. **A `client` principal never gets `confirm`.** Its widening move or copy parks as a proposal
   (`gate.propose`, `pending`) for a person to decide, as today; approve, deny and promote are §3's
   refusal to it; a `confirm` field from a `client` principal is ignored, never honoured, and appends
   nothing beyond the route's own refusal or proposal. **decided** (§U).
7. **`webauthn` is `null`** when the person has registered no credential with this container: only
   the button is then possible, and an owner who set `confirm.allow_button` to `false` must register
   one (§4.3) before any confirm-gated act.

### 4.3 · Grants, agents and confirm credentials

The routes behind `identity.md` §4–§5. **a1p**, every clause, binding those records onto HTTP. Every
route here needs an **`interactive` principal**: a `client` principal gets §3's refusal on all of them,
reads included, because who else holds access is credential metadata an agent is never served. Every
list is viewer-scoped and complete (§4). Every read appends `context.fetch` with `items: []` and
`details.read` naming what was read.

| method · path | does | needs | `200` body | events |
|---|---|---|---|---|
| `GET /v1/grants` | the user grants | `admin` over `["*"]` | `{"grants": [<grant>]}` | `context.fetch` (`read: grants`) |
| `POST /v1/grants` | grant a provider user access, with the confirm (§4.2) | `admin` over `["*"]` | `confirm`, then `{"grant": <grant>}` | first leg; `step_up`, `identity.grant` |
| `DELETE /v1/grants/{sub}` | revoke a user grant | `admin` over `["*"]` | `{"result": "revoked"}` | `identity.revoke` |
| `GET /v1/agents` | registrations serving this person; all of them for an admin | any grant | `{"agents": [<agent>]}` | `context.fetch` (`read: agents`) |
| `POST /v1/agents` | register an agent, from the consent page's flow, with the confirm | `admin` over `["*"]` | `confirm`, then `{"agent": <agent>}` | first leg; `step_up`, `identity.grant` |
| `DELETE /v1/agents/{client_id}?sub=` | revoke one registration | the person it serves, or an admin | `{"result": "revoked"}` | `identity.revoke` |
| `GET /v1/agents/{client_id}/log?sub=&limit=` | what the agent did for that person, newest first (the pyramid's log facet) | as revoke | `{"entries": [<entry-line>]}` | `context.fetch` (`read: agent_log`) |
| `GET /v1/credentials?sub=` | confirm credentials | the person; an admin with `sub` | `{"credentials": [<credential>]}` | `context.fetch` (`read: credentials`) |
| `POST /v1/credentials` | register a WebAuthn credential for this person | any grant, and the rules below | `register`, then `{"credential": <credential>}` | `context.fetch` where the first leg issues a confirm challenge; `step_up` where a proof was presented; `identity.credential` |
| `DELETE /v1/credentials/{id}?sub=` | remove one, with a biometric confirm only (below) | the person; an admin with `sub` (recovery) | `confirm`, then `{"result": "removed"}` | first leg; `step_up`, `identity.credential` |

- **Shapes.** `<grant>` is `{"sub", "name", "capabilities", "scopes", "created_at"}`. `<agent>` is
  `{"client_id", "name", "sub", "capabilities", "scopes", "created_at", "last_seen"}`, `last_seen` read
  from the ledger. `<credential>` is `{"id", "name", "created_at", "last_used"}` — never the public key
  or the credential id's bytes. `<entry-line>` is `{"seq", "ts", "event", "subject", "scope"}`.
- **`sub` in a query** names the person a registration or credential belongs to. Absent, it is the
  caller; present and not the caller, the caller must be an admin. A `client_id` names one registration
  per person, so the pair `(client_id, sub)` is what a revoke or a log read acts on.
- **Request bodies.** `POST /v1/grants`: `{"sub", "name", "role"? | "capabilities"?, "scopes",
  "confirm"?}`. `POST /v1/agents`: `{"authorization_id", "client_id", "name", "role"? |
  "capabilities"?, "scopes", "confirm"?}`; the registration serves the caller; `name` is at most 128
  characters, untrusted display data. A role bundle expands at grant time (`capabilities.md` §2). No
  grant or registration exceeds the granter's own grant: wider capabilities or scopes are §3's refusal.
- **Who registers an agent.** Only an admin, and the registration serves that admin (`identity.md` §4).
- **The container never presents a caller's token to the provider**, here or anywhere (`identity.md`
  §3a), so it does not read the provider's authorization itself. **The consent page owes the checks
  instead**, egzos.io's and a self-hosted provider's alike: it reads the authorization with its own
  first-party session, and calls this route only for one that is pending, was requested by the
  person whose container token makes the call, is for the body's `client_id`, and asks for no scopes
  beyond the body's; and it refuses a `client_id` registered on another container (`identity.md`
  §3a). **a1p** (a1r and a6 on #285).
- **What the container holds to is the admin's confirm.** The first leg answers `newly: []` and, in
  its own field, `"registers": {"client_id", "name"}`: the agent is not a person, and its `name` is
  the agent's own claim, untrusted display data that every surface escapes and labels as the agent's
  (design-gap Egzos/egzos-platform#117). The first leg's `context.fetch` carries the same
  `details.registers` (the `name` as escaped display data), so a first leg the admin walks away from
  still names the agent it showed. The challenge is bound to the body's `client_id`, its capabilities
  as expanded and its `scopes`, so a second leg naming any other is §4.2's `mismatch`. **a1p** (a6
  and a1r on #285).
- **`authorization_id` keys the registration, atomically**: of two concurrent requests naming one
  authorization, at most one registers, and every later request naming it is §3's refusal.
  `identity.grant` records it as `details.authorization_id`, so the consent page's record and the
  container's join; it is **what the caller claimed**, which the container cannot check, never a
  verified fact. Only after the registration is written does egzos.io tell the provider to issue.
- **The agent log serves only what the reader may see now.** It lists the agent's entries for that
  person (`details.for`), and omits every entry that was a refusal — a probe's `context.fetch` with
  `items: []`, a refused act — and every entry whose `subject` the reader's grant does not cover
  **today**. An omitted line leaves no marker and no count, so the log cannot tell a reader what exists
  outside their sight, or whether a probed target existed.
- **Revoking the last admin grant** answers `409` with `{"error":"last_admin"}` and §3's headers, to the
  admin who asked — a fact about their own container — and appends `identity.revoke` with `outcome:
  refused`, `details.reason: last_admin`.
- **Credential registration has two legs.** The first answers `{"result": "register", "challenge",
  "webauthn": <PublicKeyCredentialCreationOptions>, "expires_at"}`, a challenge bound to the caller as
  §4.2's are. For a person who already has a credential it also answers `"confirm": {"challenge",
  "webauthn": <PublicKeyCredentialRequestOptions>}`: a second challenge, for the assertion the second
  leg's `confirm` carries, issued and bound as §4.2's first leg issues one (the act `credential.add`).
  That first leg lists the person's credentials to their authenticator, so it appends §4.2's first-leg
  `context.fetch` (`details.read: credentials`); a first leg for a person with no credential appends
  nothing. The second leg carries `{"challenge", "attestation", "confirm"?}`; user verification is
  required.
  - **A person with a credential adds another only with a biometric proof from an existing one** in
    `confirm`. The button is refused on this route whatever `confirm.allow_button` says, so a stolen
    session cannot add the thief's authenticator.
  - **Removing a credential needs a biometric proof too, never the button** — the person's own, from
    any of their credentials, or, for an admin's recovery of another person, the admin's own (an admin
    with none registers one first). A stolen session can therefore neither remove a person's
    credentials to fall back to the button, nor clear them to enrol a first one of its own.
  - **The first credential** needs, in `confirm`, the button **and a fresh sign-in**: the provider
    token's most recent authentication (its `amr` timestamp) within the last 300 seconds. A token
    lifted from a session that signed in earlier cannot enrol one. Where `confirm.allow_button` is
    `false`, the first credential is enrolled only from the owner's own surfaces (the lifeboat or the
    CLI, holding the owner `Token`), which enrol the owner's own authenticator: **while buttons are
    off, a person other than the owner who has no credential cannot enrol one, and so cannot perform
    a confirm-gated act.** That is the cost of the stronger setting, taken on purpose: an owner turns
    buttons off after the people who need the confirm have enrolled. **a1p** (a1r on #285).
  - **What stays open, on the record:** whoever holds a fresh session of a person who has no
    credential yet can enrol the first one. **Recovery:** an admin removes a person's credentials
    (`DELETE /v1/credentials/{id}?sub=`, with the admin's own confirm), and the owner can remove any
    from the CLI or the lifeboat with the owner `Token`; the person then enrols again.
  - **Every second leg that concludes is audited**: `step_up` first where a `confirm` proof was
    presented (as §4.2 item 4, refused ones included), then `identity.credential`. An add carries
    `details.op: add` and `outcome: added`, or `refused` with `details.reason` (`attestation`, `stale`,
    `no_proof`, `not_fresh`, `button_refused`); the caller's answer to a refusal is a fresh `register`,
    whatever the reason. A removal carries `details.op: remove` and `outcome: removed`, or `refused`
    with `details.reason` (`stale`, `no_proof`, `button_refused`, `assertion`); the answer to a refusal
    is a fresh `confirm`. **Every removal appends it, on every surface**: the owner's removal from the
    CLI or the lifeboat with the owner `Token` appends `identity.credential` (`op: remove`, `actor` the
    owner) too, since a removal reopens the button for that person. A `sub` the admin does not cover is
    §3's refusal before any leg, and follows §4's rule for a refusal.
- **New events**: `identity.grant` and `identity.revoke` (`details.kind`: `user` or `agent`), as
  `identity.md` §4 names them, and `identity.credential` (`details.op`: `add` or `remove`; never key
  material). They enter `events.md` §1 with their code (§5).

### 4.4 · Artifact upload

`POST /v1/items` takes text in its body, or an artifact through an upload. **a1p**, the shape;
**decided**, the staging rule and dedup ([0.3 · 41]; `storage.md` §4). The bytes travel to the
container and nowhere else; the container keeps them in its `BlobStore`, which may sit on object
storage (v0.7 §S).

1. **Open.** `POST /v1/uploads` with `{"scope", "name", "mime", "size", "sha256"}` → `{"upload": <id>,
   "expires_at"}`. Needs `remember` on `scope`; shape-validated before any lookup (§3): `name` is 1 to
   255 characters, `mime` a `type/subtype` token of at most 127, both untrusted display data that every
   surface escapes; `size` above the container's upload limit is `400`. The limit is a new key,
   `blobs.upload_max_bytes` (default 104857600, 100 MiB; an `admin` may change it), which enters
   `container.md` §8 and `_types.py` with the code that reads it, as `identity.md` §2's keys do. A
   principal holds at most 16 uploads that are open or orphaned (below), **or written as an artifact
   item whose bytes are still staged** (step 3: an agent's, until a person promotes or tombstones it);
   a 17th answers `429` with `{"error":"too_many_uploads"}` and §3's headers — a fact about the
   caller's own uploads. So what a principal holds staged, and nobody has decided on, is bounded at 16
   times `blobs.upload_max_bytes`, and a person's decision is what frees a slot (v0.7 §Z: asked about,
   never purged). **a1p** (a6 on #285). A successful open appends nothing: no bytes have moved. A
   refused open — a `scope` the token cannot write to — follows §4's rule and appends `context.fetch`
   with `items: []`.
2. **Bytes.** `PUT /v1/uploads/{id}` with the raw bytes. The id is bound to the principal that opened
   it and expires after one hour; the container reads at most `size` bytes, checks length and sha256, and
   **stages** them (`BlobStore.stage`) — never `put`, so staging never answers whether the content
   already exists. Each `PUT` on a live id of the caller's own appends **`upload.put`** (`subject` the
   upload, `scope`, `size`, `sha256`, `outcome: staged` or `refused` with `details.reason`: `length`,
   `hash`, `already`). A `PUT` naming an unknown, expired or another principal's id is §3's refusal and
   appends `context.fetch` with `items: []`. `200` `{"upload": <id>, "sha256"}`.
3. **Item.** `POST /v1/items` with `{"kind": "artifact", "upload": <id>, "scope"?, "key"?, "tags"?}`
   writes the item, `unverified` like every write. The id must be the caller's own, staged, and not yet
   itemised; `scope`, when given, must equal the upload's; otherwise §3's refusal. Bytes and item are two
   separate spends of one id, **each an atomic check-and-mark**: of two concurrent `PUT`s, or two
   concurrent item writes, naming one id, at most one proceeds, and the other is refused as spent. A
   person's artifact is promoted at once (`BlobStore.promote`, `blob.put`); an agent's stays staged until
   a person promotes the item (`storage.md` §4's staging rule for agent-proposed artifacts). Events:
   `item.add`, and `blob.put` where promoted.

**Nothing staged is deleted on a timer, and nothing staged goes untracked** (v0.7 §Z, amending R11's
"30 days cold, then purge"):

- **An orphan** is an upload whose bytes were staged but which expired before an item was written. It
  is listed to its opener — and to an admin — in `GET /v1/pending` under `"uploads": [{"upload",
  "name", "size", "sha256", "scope", "opened_at"}]`, counts toward the 16, and is removed only by
  `DELETE /v1/uploads/{id}` (its opener or an admin), which deletes the staged bytes and appends
  **`upload.discard`**.
- **A staged artifact item past `blobs.staging_retention_days`** appears in `GET /v1/pending` under
  `"staged": [<item>]` — to an interactive principal covering its scope, and **instead of** in `items`,
  never both — until a person promotes it or tombstones it; a tombstone deletes the **staged** bytes
  (never promoted ones: [0.3 · 44] holds), and its `item.tombstone` entry carries
  `details.staged_deleted: <sha256>` so the deletion is on the record. A promotion of such an item
  appends `blob.put` (§4's promote row). **decided** (§Z); **a1p** the two event details.

**Not in this door at v1.0:**
- **Quarantine and config.** No flagship screen #137 cites needs either at v1.0. They stay on the CLI.
- **`[v1.1 · #137 1–7, 9–12]`**: a revision on reads (1); window state and its events (2, 3);
  `return_to` (4); writability per scope (5); a nonzero-delta move inside a window (6); pending
  facets and filters (7); anomaly sentences (9); token reads and their events (10); where coverage is
  computed (11); a quarantine flag per ring (12). A builder adds none of them.

## 5 · Audit coverage

`events.md` §4 invariant 2 binds this door without exception: every read, grant mint and blob pull
is an event, and a door that produces an effect without one is non-conforming. **decided.** The
whole list is given below, under **The whole list**. A test per row asserts the event.

The two invariant-2 exceptions (the owner's read inside an AS session; refresh rotation) are the
AS's, and neither reaches this door: §2 accepts no session. **decided.**

**The whole list** of what the door appends is the tables of §4 and §4.3, §4.2's and §4.4's clauses,
and §2 item 7's `rest.tally` and `authz.release`.

**New events.** `item.copy` (a copy is made; `subject` the new item, `details.from` the source),
`gate.pass.confirmed` (a widening move or copy confirmed inline; `audience_delta` and the `step_up`'s
`seq`), §4.3's `identity.grant`, `identity.revoke` and `identity.credential`, and §4.4's `upload.put`
and `upload.discard` are this door's. Like `identity.md`'s, they enter `events.md` §1 and `_types.py`
with the code that appends them, because the conformance tests pin that table to running code. **a1p.**

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
  `sig` and never on the `sig` itself: with the other four fields, the `sig` is the credential, and
  a credential is kept only as its hash, as `Token.secret_hash` is (`model.py`). **a1p.** Where it
  is persisted joins #165 item 4's batch, beside the grant key.

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
Rotation voids every outstanding grant. It was drafted for the #143 batch beside the authorization
server's own keys, which retired with it (`identity.md` §9).

**The lifeboat's same-origin route** redeems the same descriptor under the same checks on its own
host (#138). It is a5-dinghy's and is not an endpoint of this door. The deployment preview limit
#138 asks for is `container.md`'s, open on #138.

## 7 · Browser clients

**CORS is decided: `identity.md` §6.** The door answers CORS for `identity.browser_origins` exactly,
with headers that do not vary with the outcome, and a preflight that does not map the routes. #153's
other four questions were the retired authorization server's and close with it.

## 8 · What this document does not fix

Who may call the door, provider-token verification, grants, the confirm, CORS and MCP over HTTP →
`identity.md`. Copy, the confirm, the human-only routes, grants, agents, credentials and upload →
§4–§4.4 here. The lifeboat → `spec/design/lifeboat.md`. Where the grant key persists → #165 item 4.
The look of any client → its design spec.
