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

- **decided** — carried from a frozen clause, which is cited. The wording may improve; the decision
  is the cited document's and may not change here.
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
   - **What counts:** every `401` answer and every refused redemption, whichever §6 check refused
     it. A request the door serves, or answers with §3's refusal on a live token, does not count.
   - **Two buckets, both enforced** ([0.3 · 24]): one container-global, one keyed on the transport
     source address, never on a value the caller supplies. A network identifier keys a bucket and
     never enters the chain. The `rest` counters are the door's own, so exhausting them never
     locks the owner out of `/login`, and the reverse holds too.
   - **A throttle that holds does not evaluate, and fails closed** (§12.1 rule 4). While either
     bucket holds, every request at the door gets its route's uniform failure, counted and not
     evaluated: `401` on a bearer route, a live token included; §3's refusal at redemption, a
     valid descriptor included, which is therefore not spent.
   - **The chain.** No attempt at the door appends an engage entry: the door has no per-attempt
     event a caller-less attempt could carry. The release appends `authz.release` with `surface:
     rest`, `refused` and `window_key` whenever the throttle engaged, `refused: 0` included (§12.1
     rule 5). At the close of each container-global window in which the throttle admitted any
     `401`, or any redemption refused at §6's check 1 or 2, the timer appends **`rest.tally`**
     once, as `authorization-server.md` §12 row (h) does: `principal: none`, `actor: rest`, and
     three closed `details` keys, `unauthorized` (the count of those `401`s), `forged` (the count
     of those redemptions) and `window_key`, derived from that bucket as §12.2 states. No such
     admission, no entry. The response is unchanged by any of it.
   - **What the chain bounds.** An unauthenticated sweep reaches the chain at one `rest.tally` per
     window plus one release per engagement, never once per attempt. A redemption refused at check
     3 or later names its token and appends its own `context.fetch` (§6), so a replayed grant
     appends at the throttle's admitted rate and no faster.
   - **Rates.** `TODO(chief)`, #141: the rates and windows join #141's batch. **a1p proposes**, for
     the Chief's pick: container-global, 300 counted attempts per 300-second window; per source
     address, 30 per 300-second window; a bucket that engages holds until its window closes. A
     well-behaved client meets a `401` only on an expired or revoked token, a handful per window.
     A 300-second window shows a sweep on the chain within five minutes, the grant's own lifetime
     (§6), and caps `rest.tally` at 288 entries a day under a sustained sweep. **The cost, for the
     Chief:** under the fail-closed rule above, a sweep that exhausts the container-global bucket
     refuses the owner's own live tokens at this door until its window closes. Until the Chief
     names the rates, the build issues carry them as open.

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
(`capabilities.md` §6 clause 1, `storage.md` §5).

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
  A replayed or expired grant is refused this way, and each such refusal counts toward §2 item 7's
  throttle.
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

## 7 · Browser clients: the questions open on #153

A browser client reaches this door with a token from `authorization-server.md` §2. #153 records five
questions such a client meets. **All five are the Chief's. This document decides none of them**, and
carries each so the review reads them in one place:

- **`[open · #153 q1]`, where the authorization code is returned.** An AS question. No clause here
  depends on it.
- **`[open · #153 q2]`, CORS.** #153 asks it of the token and revocation endpoints. The flagship
  calls this door cross-origin too, so the answer reaches here. **Until the Chief answers, this door
  sends no `Access-Control-*` header and answers no preflight.** That is the absence of a decision,
  not one. A builder may not implement CORS on this door against this draft.
- **`[open · #153 q3]`, the flagship's `client_id`.** An AS question. No clause here depends on it.
- **`[open · #153 q4]`, what the flagship's request carries as `scope`.** An AS question. This door
  enforces whatever grant the minted token carries (`authorization-server.md` §7), so it depends on
  no answer.
- **`[open · #153 q5]`, RFC 9207's `iss` on the authorization response.** An AS question, and §6's
  ten-field document. No clause here depends on it.

## 8 · What this document does not fix

The AS's endpoints, pages, tokens and their events → `authorization-server.md`. The MCP HTTP
transport, protected-resource metadata and the `resource` parameter → contract v1.1 at Phase 5
(`authorization-server.md` §4). The step-up tap and every human-only act over HTTP → Phase 2.2. The
lifeboat → `spec/design/lifeboat.md`. Where the AS's state and the grant key persist →
`authorization-server.md` §13's `TODO(a1p)` and #165 item 4. The look of any client → its design
spec.
