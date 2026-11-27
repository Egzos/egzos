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

The running doors (CLI, `egzos_fetch` / `egzos_remember` / `egzos_inbox` / `egzos_places`, the
lifeboat) are cited
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
- **TLS at a host's edge. decided** (the Chief, 2026-10-30, v0.7 §AF, amending [0.3 · 9] for a
  container egzos hosts): such a container may serve plain HTTP on its host's private network to the
  host's own TLS-terminating proxy, which alone faces the internet. It opts in by an explicit host
  setting, never by default; everywhere else the loopback rule stands. As the loopback rule is, the
  setting is checked from the socket: the door binds no globally routable address, and refuses to
  start if any address it binds, or the unspecified address on a host holding a globally routable
  one, is. It also refuses to start without an explicit `identity.origin` (`identity.md` §2) whose
  scheme is `https`, the proxy's, never the plain origin it binds. **The private network holds no
  one but the container and the proxy**, as loopback held no one but the machine: the host gives each
  hosted container a network of its own (on Fly, a custom private network for its app, never the
  organization's shared one), so no other container or app can open the socket. Where that does not
  hold, the setting is not used. Even so, every request still bears its own credential (§2), and
  nothing is trusted for arriving on that network.
  No forwarded header decides a caller's identity, scheme or origin, and the throttle's per-source
  bucket sees the proxy's address, as behind a proxy on loopback (§2 item 7). **a1p**, the wording.

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
   - **Two kinds of request stand outside the throttle. a1p** (#294): every `OPTIONS`
     (`identity.md` §6's preflight, or §3's refusal of one), and every request at the
     protected-resource metadata's path (`identity.md` §7: the metadata on `GET`, §3's refusal
     otherwise). None reads a credential, and each answer turns on the request alone, the same for
     every caller, so it is answered as usual while a bucket holds and is never counted.
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
  lifeboat's R12: a framework `405` would confirm the path exists. One exception: a verified
  caller's `GET` or `DELETE` at `/mcp` gets the transport's `405`, since `/mcp`'s `401` already
  tells everyone it exists (`identity.md` §7);
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
A string anywhere in the request that holds U+0000 is one such fact: no store keeps it outside a
document (`storage.md` §3.7). **a1p** (#331).
A string anywhere in the request that is not well-formed Unicode (a surrogate code point outside a
pair) is another such fact. **a1p**.

**An ambiguous path tail gets the third answer.** A scope parameter or body field accepts a node id
or a path tail, as `resolve_ref` does (`container.md` §2). A tail that matches more than one node the
token covers is refused and nothing is picked ([0.3 · 1]): status `409`, the same four headers, and
`{"error":"ambiguous","matches":[<path>, …]}`, the paths sorted. **decided**, that the refusal names
the matches; **a1p**, the bytes (#187). The candidates are only the nodes the token covers, so the
answer names nothing the token could not list at `GET /v1/scopes`; a tail whose only matches are
uncovered is §3's refusal. It appends one `context.fetch` with `items: []`, as the running MCP door's
`_probe` does. `GET /v1/find` never answers it: a search covers every match (`store.find`).

**Only a principal holding `fetch` is told the matches. a1p** (#294): they are what
`GET /v1/scopes` would list, and it needs `fetch`. Any other gets §3's refusal and §4's probe
instead, as for an absent tail, on every route that takes a reference, `POST /v1/items` included,
and in the MCP tools alike (`egzos_fetch`, `egzos_remember`, `egzos_places`).

**A store that cannot take the container's write lock in time answers `503`**, with
`{"error":"busy"}`, `Retry-After: 1` and the same four headers: the store raised `StorageBusy`
(`storage.md` §3.6), and nothing was written. It depends on the container's load and on no fact the
request names, so it tells a caller nothing §3's refusal hides. A request reaches the write lock
only after authentication and its route's checks, but for §2's token check itself, which every
well-formed container token value reaches alike, so a `503` there names no token either. **a1p**
(#331).

**Any other failure answers `500` with `{"error":"internal"}`** and the same four headers, never a
stack, a path, a driver's message or an exception's text. **running** (the door's catch-all);
**a1p**, binding it (#331).

**The MCP tools and the CLI answer these alike.** Each carries the same word (`invalid_request`,
`busy`, `internal`) in its own channel (an MCP tool's error result, the CLI's exit status and
message), and neither ever shows a driver's message. **a1p** (#331).

## 4 · The v1.0 endpoints

Every response body is JSON. An item is serialised per `context-item.md` §1, unknown fields
included. **The door never renders an item**: a body, a title or a tag is a JSON string value,
returned verbatim, and is data. **a1p.** A browser client that displays one escapes it (its design
spec's job).

| method · path | does | needs | mirrors | events |
|---|---|---|---|---|
| `GET /v1/fetch?scope=&query=&kind=` | resolve the layered context at a scope (default: the token's start, as `egzos_fetch`) | `fetch` | `egzos_fetch` | `context.fetch`; `blob.grant` per §6 |
| `GET /v1/find?q=` | search across what the token sees, in the query grammar of `egzos.store.find` | `fetch` | `egzos find` | `context.fetch` |
| `GET /v1/items/{id}` | one item | `fetch` on its scope | the lifeboat's item read; `egzos_get` (§4.7, not running) | `context.fetch`; `blob.grant` per §6 |
| `GET /v1/inbox` | captured, not yet wrapped or promoted | `fetch` on the inbox | `egzos_inbox` | `context.fetch` |
| `GET /v1/scopes?under=` | the child nodes of a node the token covers | `fetch` | `egzos ls`, `egzos_places` | `context.fetch` |
| `POST /v1/items` | write an item — text, or an artifact from an upload (§4.4); it lands `unverified` | `remember` on the target scope | `egzos_remember`; an artifact: `egzos_upload_finish`, and within `egzos_add_file` (§4.7, not running) | `item.add`; `blob.put` where an artifact is promoted |
| `POST /v1/uploads` | open an artifact upload (§4.4) | `remember` on its scope | `egzos_upload_open`, and within `egzos_add_file` (§4.7, not running) | none |
| `POST /v1/uploads/{id}/address` | a fresh single-use address for the bytes of an upload of the caller's own (§4.4 item 2a; not running) | the opener | `egzos_upload_address` (§4.7, not running) | none |
| `PUT /v1/uploads/{id}` | send the upload's bytes; they are staged (§4.4) | the opener; or, with no bearer, the upload's address (§4.4 item 2a; not running) | within `egzos_add_file`; the address: an agent's own program (§4.7, not running) | `upload.put`; or `context.fetch` on a refused id |
| `DELETE /v1/uploads/{id}` | discard an upload no item was written from, open or orphaned, and its staged bytes (§4.4) | the opener; for an orphan, also the person an agent or a terminal opener serves (v0.7 §AC, §AJ); or an admin | `egzos_upload_discard`, the opener's (§4.7, not running) | `upload.discard` |
| `POST /v1/items/{id}/move` | move an item; the gate decides, and asks for the confirm inline when the audience widens (§4.2) | `organize`; `publish` to widen | `egzos mv` | `item.move` with `gate.pass.silent`; or `context.fetch` (first leg), then `step_up`, `gate.pass.confirmed` and `item.move`; or `gate.propose` |
| `POST /v1/items/{id}/copy` | copy an item; the same gate as move (§4.2) | `fetch` on the source; `remember` and `organize` on the destination; `publish` to widen | — (new: v0.7 §V) | as move, with `item.copy` |
| `POST /v1/pending/{proposal}/approve` | approve a parked proposal, with the confirm (§4.2) | an `interactive` principal that decides over it | `egzos trust approve` | `context.fetch` (first leg); `step_up`, then `approval.execute` or `approval.stale` |
| `POST /v1/pending/{proposal}/deny` | deny a parked proposal, with the confirm | as approve | `egzos trust deny` | `context.fetch` (first leg); `step_up`, `approval.deny` |
| `POST /v1/items/{id}/promote` | promote an unverified item to verified, with the confirm | an `interactive` principal covering its scope | `egzos trust promote` | `context.fetch` (first leg); `step_up`, `approval.promote`; `blob.put` where a staged artifact's bytes are promoted (§4.4) |
| `DELETE /v1/items/{id}` | tombstone an item: at once, or with the confirm where a person promoted it (below) | an `interactive` principal holding `organize` on its scope | `egzos rm` (new, beside it) | `item.tombstone`, with `details.staged_deleted` where it releases staged bytes; a promoted item's: `context.fetch` (first leg), then `step_up` and `item.tombstone` |
| `POST /v1/scopes` | create a container node | coverage of the parent; `admin` above its `structure_floor` | `egzos mk` | `node.create` |
| `PATCH /v1/items/{id}` | rename an item: an artifact's file name, a text item's title; at once, or with the confirm where it is verified or a person promoted it (§4.5) | an `interactive` principal holding `organize` and `fetch` on its scope | — (new: #404) | `item.rename`; a verified or promoted item's: `context.fetch` (first leg), then `step_up` and `item.rename` |
| `PATCH /v1/scopes/{id}` | rename a project or a thread, with the confirm; its id stays (§4.5) | a person holding a provider token whose grant holds `admin` over `["*"]`, and `organize` and `fetch` on it | — (new: #404) | `context.fetch` (first leg), then `step_up` and `node.rename` |
| `GET /v1/limits` | what this door serves, and its upload limits (§4.6) | any valid token | — (new: #360) | `context.fetch` (`read: limits`) |
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
agent:<client_id>` with `details.for: user:<sub>`. **decided.** A person at a terminal is `actor:
user:<sub>` too, with `details.terminal` naming the terminal (`identity.md` §3a; **a1p**, v0.7 §AJ).

**Artifacts arrive through an upload** (§4.4): the staging rule for an agent-proposed artifact
(`storage.md` §4) and the dedup rule ([0.3 · 41]) apply to it.

**A person tombstones an item; an agent never does** (#296). **a1p**, the `DELETE /v1/items/{id}`
row and these bullets:

- **Needs** an `interactive` principal holding `organize` where the item sits. `capabilities.md`
  §1 gives `organize` the moving of items between containers, and a tombstone takes the item out
  of every one, and so out of every audience: the furthest inward move, which `container.md` §6
  floors on `organize` at the source, as it does every move. Six capabilities are the whole
  vocabulary (§1), so none is added for it. A `client` principal gets §3's refusal: an agent's
  write waits for a person (§4.4), and MCP has no tool for this. The inbox thread a pure capture
  opened keeps the name the item's title gave it (`container.md` [0.3 · 2]).
- **An item no person has promoted goes at once**, an unverified `rule` included (the route
  serves nothing of it), answering `{"result": "tombstoned"}`: §4.4's release. An artifact whose
  bytes are still staged releases them, deleted (`BlobStore.discard`) unless another upload or
  staged item holds the same `sha256` (`storage.md` §4), a copy of a staged artifact included, and
  its upload frees its slot. A `confirm` sent with it is ignored and concludes nothing.
- **A verified item, or one a person has promoted (`provenance.approved_by`) whatever its status
  now, takes the confirm** (§4.2): removing curated knowledge goes behind a re-authentication, by
  analogy to v0.7 §AD's sudo model (a1p). The first leg answers `newly: []` and names what it
  removes, `"tombstones": {"item", "kind", "auto_title"}`, the title untrusted display data; its
  `context.fetch` carries the same as `details.tombstones`.
- **One atomic step** holds a second leg's `step_up`, the tombstone and its `item.tombstone`
  (`kind`, `status` as it stood, and `staged_deleted: <sha256>` only where it deleted staged bytes
  nothing else holds). The bytes are deleted inside the same lock, before the entry, so the entry
  claims only a deletion that happened (another item's promotion may have moved them already); a
  failure rolls the tombstone back with it. Promoted bytes are never deleted ([0.3 · 44]).
- **Absent, uncovered, already tombstoned, quarantined, or without `organize`**: §3's refusal and
  §4's probe, the same for each.
- **`egzos rm <id>`** tombstones an item no person has promoted, with the owner `Token` (`admin` over
  the whole container), and appends the same `item.tombstone`. A promoted item it refuses, whatever
  its status now: any process that can run the terminal could run `rm`, so a promoted item is
  tombstoned only at the door, where the confirm asks the person. A quarantined item reads as absent,
  as at the door. **a1p.**

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
| `DELETE /v1/items/{id}` | `{"confirm"?}` | `{"result": "tombstoned"}`; a promoted item's: `{"result": "confirm", …, "tombstones"}` (§4.2) first |
| `POST /v1/scopes` | `{"type", "name", "parent"?}` | `{"node": <node>}` |
| `PATCH /v1/items/{id}` | `{"name", "confirm"?}` | `{"item": <item>}` (§4.5); a verified or promoted item's: `{"result": "confirm", …, "renames"}` (§4.2) first |
| `PATCH /v1/scopes/{id}` | `{"name", "confirm"?}` | `{"result": "confirm", …, "renames"}` (§4.2), then `{"node": <node>}` (§4.5) |
| `GET /v1/limits` | — | `{"contract", "features", "upload_max_bytes", "inline_max_bytes", "uploads_held_max"}` (§4.6) |
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
  `from` (`PROPOSAL_WIRE_KEY_FROM`), except that its `from_path` and `to_path` are rendered from
  its ids as they stand when it is served (§4.5; **a1p**, v0.7 §AK, not running).
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
   token's start, as `egzos_fetch`'s default: the personal root for a token over everything, the
   token's first scope for a narrower one. **a1p** (a1r on #288). `egzos_places`, the same read
   for an agent, answers with no `under` for a narrower token every place its grant or registration
   names that exists and it covers, each as a `<node>` whose `parent` is null where the token does
   not cover that parent, sorted by path, in one `context.fetch` whose `subject` and `scope` are
   null. **a1p** (#415, 2026-11-27).
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
   `egzos mk`. To a principal without `fetch`, the node's `path` is `null`: a computed path names
   its ancestors, and only `fetch` reads names (§3). **a1p.**
9. **`GET /v1/pending`** is two lists as `Trust.pending` returns them (a proposal's paths rendered
   as §4.5 says), plus §4.4's `staged` and
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
   non-empty, asked by an `interactive` principal holding `publish`; or approve, deny or promote;
   or, **a1p** (§4, #296), a tombstone of an item a person promoted; or, **a1p** (§4.5, v0.7 §AK),
   a rename of an item that is verified or that a person promoted, or of a place — sent
   **without** a `confirm` field moves and decides nothing. After the route's own checks pass
   (coverage and capability first, `container.md` §6's order, so a token that may not do the act gets
   §3's refusal whatever the delta), it answers `{"result": "confirm", "newly": [<name>],
   "challenge": <id>, "webauthn": <options> | null, "expires_at"}`. `newly` names who would newly see
   the item — each grant's or registration's display name — and is `[]` for approve, deny and promote
   of an item already in place. The same request sent again **with** `confirm` completes it (item 3).
   There is no separate challenge route: a challenge exists only as the first leg of the act it is for.
2. **The first leg is a read, and is audited.** It appends one `context.fetch` with `items: []`,
   `subject` the item, proposal or node, and `details: {"confirm_for": <act>, "newly": [<name>]}`:
   showing who would newly see an item is a read of credential metadata (`events.md` §4 invariant
   2). It is served only to the `interactive` principal about to act — the same reader
   `GET /v1/pending` serves a proposal's audience to.
3. **The second leg** carries `"confirm": {"challenge": <id>, "proof": "biometric", "assertion":
   <WebAuthn assertion>}`, or `"proof": "button"` with no assertion where `confirm.allow_button` is
   `true` **and the person has no registered credential** — once they have one, the button is refused
   for them (`identity.md` §5) — and, on §4.3's acts on grants and registrations, a fresh sign-in
   (§4.3). A terminal's token concludes no second leg, whatever the proof (`identity.md` §5). The
   container then, as **one atomic step** — of two concurrent requests presenting one
   challenge, at most one proceeds past it, as §6's grant spend:
   - finds the challenge live, unspent and **bound to this request**: the same principal (the
     `Token.id`, or the provider token's `sub` and `client_id`), the same act, subject and destination,
     and the same audience delta, recomputed now; and, **a1p** (v0.7 §AK, not running), on an act on
     an item (a promote, a tombstone or a rename that takes the confirm, a move or copy's confirm,
     and an approve, for each item its proposal names), the item's `lifecycle.version`, `scope`
     and `trust.status`, each as the first leg read it: a second leg that finds any of the three
     changed concludes `mismatch` and changes nothing, and the person asks again and sees the item
     as it now is. An approve that passes this still meets `container.md` §6's manifest check,
     which binds the items' ids, the target and the audience, and not an item's name. Each act
     that changes an item between the two legs moves at least one of the three: a rename, the
     version (§4.5); a promote, `trust.status` and the version; a move, `scope`; a quarantine,
     `trust.status`; a tombstone ends the item, and a second leg on a tombstoned item is §3's
     refusal; a copy leaves its source as it was; a title pass, where one runs, moves the version
     with the title it writes. The running code moves the version on a promote alone today, which
     is why a rename is served only where it moves the version too and every confirm on an item
     is bound to the three (§4.6). A place's rename is bound to the node's name as the first leg
     read it and to the body's new `name` (§4.5) (**a1p**);
   - verifies the proof (`identity.md` §5);
   - spends the challenge.

   Then it appends `step_up` (`outcome: confirmed`, `details.proof`), the act's gate or approval event
   (`gate.pass.confirmed` with `audience_delta` and the `step_up`'s `seq`; or `approval.execute` /
   `approval.stale`, `approval.deny`, `approval.promote`), and `item.move` or `item.copy` where one
   moved.
4. **Every proof that is presented and concludes is audited, success or failure.** A stale, spent,
   foreign or mismatched challenge, a failed assertion, a button where buttons are off, any proof
   from a terminal's token, a `client_id` that may not be registered (§4.3), and a delta
   that changed since the challenge append `step_up` with `outcome: refused`, `details.proof` as
   presented and `details.reason` (`stale`, `spent`, `foreign`, `mismatch`, `assertion`, `button_off`,
   `delta_changed`, `terminal`, and §4.3's `not_fresh` and `registered`), as `events.md` §1 requires
   of every concluded presence
   check. The answer to the caller is the same whatever the reason: `{"result": "confirm", …}` with a
   fresh challenge and the act's first-leg fields as they now stand: the new `newly`, where the
   delta changed, and the act's own field where its first leg carries one: `tombstones`,
   `registers`, `signs_in` or `revokes` (**running**), or `renames` (**a1p**, v0.7 §AK, not
   running).
   The ledger says which case it was; the response does not (`capabilities.md` §6 clause 3).
5. **A challenge is single use and lives `step_up.window_seconds`, at least 60 seconds.** A proof
   that concludes spends its challenge whether it is confirmed or refused, as §6's grant is spent at
   check 4 whatever the later checks decide (a6 on #284); a refused attempt always gets a fresh one.
6. **A `client` principal never gets `confirm`.** Its widening move or copy parks as a proposal
   (`gate.propose`, `pending`) for a person to decide, as today; approve, deny and promote are §3's
   refusal to it; a `confirm` field from a `client` principal is ignored, never honoured, and appends
   nothing beyond the route's own refusal or proposal. **decided** (§U).
7. **`webauthn` is `null`** when the person has registered no credential with this container: only
   the button is then possible, and an owner who set `confirm.allow_button` to `false` must register
   one (§4.3) before any confirm-gated act. A first leg served to a terminal's token answers
   `webauthn: null` whatever the person has registered: no proof is possible from it, and the act is
   finished in a browser (`identity.md` §5, §8).

### 4.3 · Grants, agents, terminals and confirm credentials

The routes behind `identity.md` §4–§5. **a1p**, every clause that cites no decision, binding those
records onto HTTP. Every route here needs an **`interactive` principal**: a `client` principal gets
§3's refusal on all of them, reads included, because who else holds access is credential metadata an
agent is never served. Every list is viewer-scoped and complete (§4). Every read appends
`context.fetch` with `items: []` and `details.read` naming what was read. The `/v1/grants`,
`/v1/grant`, `/v1/agents` and `/v1/terminals` routes need a person holding a provider token: a
container `Token` names no `sub`, so it gets §3's refusal there, and its holder acts on grants from
the CLI or the lifeboat (`identity.md` §4).

| method · path | does | needs | `200` body | events |
|---|---|---|---|---|
| `GET /v1/grants` | the user grants | `admin` over `["*"]` | `{"grants": [<grant>]}` | `context.fetch` (`read: grants`) |
| `POST /v1/grants` | grant a provider user access, with the confirm (§4.2) | `admin` over `["*"]` | `confirm`, then `{"grant": <grant>}` | first leg; `step_up`, `identity.grant` |
| `DELETE /v1/grants/{sub}` | revoke a user grant and every registration serving that `sub`; another person's with the confirm (below) | `admin` over `["*"]` | `{"result": "revoked"}`; another person's: `confirm` first | `identity.revoke`, and one per registration it ends (`kind: agent` or `terminal`); another person's: first leg; `step_up`, then each `identity.revoke` |
| `GET /v1/grant` | the caller's own grant: what they hold, and over which places (below) | a person's token issued to this container's own client | `{"grant": {"capabilities", "scopes"}}` | `context.fetch` (`read: grant`) |
| `GET /v1/agents` | agent registrations serving this person; all of them for an admin | any grant | `{"agents": [<agent>]}` | `context.fetch` (`read: agents`) |
| `POST /v1/agents` | register an agent to serve the caller, on the terms they chose on the consent page (below), with the confirm | any grant; the registration within it | `confirm`, then `{"agent": <agent>}` | first leg; `step_up`, `identity.grant` |
| `DELETE /v1/agents/{client_id}?sub=` | revoke one registration; one serving someone else with the confirm (below) | the person it serves, or an admin | `{"result": "revoked"}`; someone else's: `confirm` first | `identity.revoke`; someone else's: first leg; `step_up`, `identity.revoke` |
| `GET /v1/agents/{client_id}/log?sub=&limit=` | what the agent did for that person, newest first (the pyramid's log facet) | the person it serves, or an admin | `{"entries": [<entry-line>]}` | `context.fetch` (`read: agent_log`) |
| `GET /v1/terminals?ended=` | the live terminals signed in as this person, or with `ended=1` the ended ones; all of them for an admin | any grant | `{"terminals": [<terminal>]}` | `context.fetch` (`read: terminals`) |
| `POST /v1/terminals` | register a terminal as the caller's own, from the hand-off's flow, with the confirm | any grant | `confirm`, then `{"terminal": <terminal>}` | first leg; `step_up`, `identity.grant` |
| `DELETE /v1/terminals/{client_id}?sub=` | end one terminal's sign-in; one serving someone else with the confirm (below) | the person it serves, or an admin | `{"result": "revoked"}`; someone else's: `confirm` first | `identity.revoke`; someone else's: first leg; `step_up`, `identity.revoke` |
| `GET /v1/terminals/{client_id}/log?sub=&limit=` | what was done through that terminal, newest first | the person it serves, or an admin | `{"entries": [<entry-line>]}` | `context.fetch` (`read: terminal_log`) |
| `GET /v1/credentials?sub=` | confirm credentials | the person; an admin with `sub` | `{"credentials": [<credential>]}` | `context.fetch` (`read: credentials`) |
| `POST /v1/credentials` | register a WebAuthn credential for this person | any grant, and the rules below | `register`, then `{"credential": <credential>}` | `context.fetch` where the first leg issues a confirm challenge; `step_up` where a proof was presented; `identity.credential` |
| `DELETE /v1/credentials/{id}?sub=` | remove one, with a biometric confirm only, from the caller's own credential: an admin's recovery uses the admin's (below) | the person; an admin with `sub` (recovery) | `confirm`, then `{"result": "removed"}` | first leg; `step_up`, `identity.credential` |

- **Shapes.** `<grant>` is `{"sub", "name", "capabilities", "scopes", "created_at"}`. `<agent>` is
  `{"client_id", "name", "sub", "capabilities", "scopes", "created_at", "last_seen"}`, `last_seen` read
  from the ledger. `<terminal>` is `{"client_id", "name", "sub", "created_at", "last_seen"}`, its
  `last_seen` read the same way, null for a terminal not used yet; one that said what kind of
  machine it is also carries `"machine"` (below), and an ended one `"ended_at"`, read from its
  `identity.revoke`. `<credential>` is
  `{"id", "name", "created_at", "last_used"}` — never the public key
  or the credential id's bytes. `<entry-line>` is `{"ts", "event", "subject", "scope"}`, with no
  chain position, which would count the lines the reader cannot see (the log's omission rule
  below). The log's `limit` is 1 to 200, 50 when absent; any other value is §3's `400`. **a1p.**
- **`sub` in a query** names the person a registration or credential belongs to. Absent, it is the
  caller; present and not the caller, the caller must be an admin. A `client_id` names one registration
  per person, so the pair `(client_id, sub)` is what a revoke or a log read acts on.
- **Request bodies.** `POST /v1/grants`: `{"sub", "name", "role"? | "capabilities"?, "scopes",
  "confirm"?}`. `POST /v1/agents`: `{"authorization_id", "client_id", "name", "role"? |
  "capabilities"?, "scopes", "confirm"?}`; the registration serves the caller; `name` is at most 128
  characters, untrusted display data. `POST /v1/terminals`: `{"authorization_id", "client_id",
  "name", "machine"?, "confirm"?}`; it serves the caller too, and its `name` is held to the same
  rule, as is its `machine`, the line a terminal may give for the kind of machine it is (below):
  the key is left out when the terminal gives none, and a `machine` that is null or not a string
  is §3's `400`. A role bundle expands at grant time (`capabilities.md` §2). No
  grant or registration exceeds the caller's own grant: wider capabilities or scopes are §3's refusal.
  The body of `POST /v1/grants` or `POST /v1/agents` names exactly one of `role` and `capabilities`
  (a role of `capabilities.md` §2, or at least one of §1's six) and 1 to 64 `scopes`; anything
  else is §3's `400`, before any lookup. (**running**, the rule of this sentence.)
- **Who registers an agent: each person, their own.** Anyone holding a user grant registers agents
  that serve themselves, an admin the same way, with the confirm and never beyond their own grant
  (above), and needs no `publish`; `identity.md` §4's intersection still applies at check time. Nobody
  registers an agent to serve someone else. The person it serves, or an admin, revokes it. **decided**
  (v0.7 §AB). A person holds at most 16 live agent registrations: a 17th answers `429` with
  `{"error":"too_many_agents"}` and §3's headers before any leg, a fact about the caller's own, so the
  audience the gate computes over registrations (`identity.md` §4) stays bounded. A `client_id` equal
  to `identity.client_id` is §3's refusal: it names a person here, never an agent. **a1p.**
- **A person reads their own grant.** `GET /v1/grant` → `{"grant": {"capabilities", "scopes"}}`: the
  capabilities and the scopes of the caller's own live user grant, read from its record
  (`identity.md` §4), the capabilities by name and each scope a node id or `"*"`. **decided** (the
  Chief, 2026-11-26, v0.7 §AM; #377), in his words "The screen lists your things and you tick what
  this agent gets", that the person chooses an agent's terms on the consent page; and **decided**
  (the Chief, 2026-11-26, v0.7 §AM: "go with your suggestion") that a person who is not an admin
  reads their own grant for it. **a1p**, the route, whom it serves and its shape. **Running**,
  after every rule it needs below; a door from before it answers the path with §3's refusal, as a
  path no route declares. **It never lands before the rules it needs:** a door serves this read only where it already runs
  every rule below that is marked as landing with it (the first leg's `terms` and `replaces` and
  their binding, `"*"` alone, and ids alone) and keeps §4.5's rule on a place's name, so a page
  that is served the read is at a door that runs them all, and a page refused it offers no choice
  (below). §4.6 names the word `grants.own` where this read is served, and only there.
  - **It serves the caller's own grant and nothing else.** It takes no parameter and names no one:
    an admin reads another person's grant at `GET /v1/grants`, never here. The body holds no `sub`,
    `name` or `created_at`, and no count or trace of any other grant, registration or `Token`.
  - **It serves ids, never a name.** A grant written at this door keeps the node ids its refs
    resolved to, never the refs, and `"*"` as itself (**running**). The route serves a scope only
    where it is `"*"` or the id of a node that exists, and leaves out, with no marker, anything else
    the record holds. It serves the id alone: no name, type, path or parent of the node, and no node
    above or beneath it. Each id it serves is a scope of the caller's own grant, so the caller
    covers it (`capabilities.md` §5) and none lies outside what they hold. The route adds no name to
    what a caller can read: a place's name is served, as before, by other reads, among them `GET
    /v1/scopes`, for the places under a place, and `GET /v1/fetch`, whose first `chain` layer is the
    scope it was asked for (§4.1), both of which need `fetch`. A person whose grant holds no `fetch`
    gets ids here and no name.
  - **What it newly serves:** to a person who is not an admin over `["*"]`, their own capability
    set and the node ids their grant names, as they stand at the time of the read. A node id holds
    the time its place was made. `capabilities.md` §6 clause 1 is unchanged: every refusal stays
    the one refusal, and this read answers a person about their own grant only, never a `client`
    principal or a `Token` about itself. It is not `[v1.1 · #137 5, 10 or 11]`, which stay
    deferred: it returns the grant's record as written, says of no place whether the caller may
    write there, computes no coverage and lists no token. An admin over `["*"]` already reads both
    at `GET /v1/grants`.
  - **Needs** a person's provider token issued to this container's own client (`identity.md` §4),
    which a registered terminal's is not. Every other caller gets §3's refusal and §4's probe: a
    `client` principal, which no route serves anything of what its person holds, its own
    registration included; a container `Token`, which names no `sub` and has no grant record (a
    `Token`'s own read is `[v1.1 · #137 10]`); and a registered terminal's token, because the read is
    for the consent page, which runs in a browser, and a terminal's token registers
    nothing (below). A sign-in a terminal kept before terminals were registered names the container's
    own client (`identity.md` §8), and is served as any person's token is. No MCP tool reads it.
  - **Answers:** `200`, and otherwise only §2's and §3's; no `409` or `429` is this route's. A
    request that carries any parameter is §3's `400` to every caller alike, decided on the request
    alone, as a parameter on `GET /v1/grants` is (**running** there), before the caller's kind or
    anything else is looked up. A person whose grant was revoked is unauthenticated (`identity.md`
    §3, check 7), so a `200` always carries a live grant.
  - **Event:** one `context.fetch` with `items: []` and `details.read: grant`, its `subject` and
    `scope` null as `GET /v1/grants`' read runs; its `actor` is the person whose grant was read. A
    refusal appends §4's probe instead.
- **An agent's terms are its person's own choice.** A registration's capabilities and scopes are
  what the person it will serve chose on the consent page, for that agent, in that visit.
  **decided** (the Chief, 2026-11-26, v0.7 §AM; #377): "The screen lists your things and you tick
  what this agent gets." **a1p**, the rest of this clause and each clause below that cites no
  decision of its own: that the choice is of places and of what the agent may do in them; that the
  terms come from nowhere else; and that the provider's own scopes carry none of it. That the terms
  lie within the person's own grant is **decided** (v0.7 §AB). The clauses say what the door
  enforces and what the consent page owes, egzos.io's and a self-hosted provider's alike, since the
  door cannot see a screen.
  - **The door enforces the bound, twice.** A body whose capabilities, as expanded, hold one the
    caller's grant lacks, or whose `scopes` reach beyond the caller's coverage (a place it does not
    cover, an absent one, or `"*"` for a caller who does not hold it), is §3's refusal and §4's
    probe before any leg. The second leg checks the bound again inside the registration's atomic
    step, against the caller's grant as it stands then: where the grant has narrowed since the first
    leg, or was revoked after the door verified the caller, nothing is registered, no proof is
    concluded, and the answer is §3's refusal and §4's probe (a caller whose grant was revoked
    before that is §2's `401`). A choice of nothing cannot be sent: a body with no capability or no
    scope is §3's `400` (above). The door takes the bound from its own records, never from the page.
    **running.**
  - **The door binds the terms.** The challenge is bound to the capabilities as expanded and to the
    scopes as the node ids the door resolved them to, so the terms a first leg was asked for are the
    only terms its second leg can land: a second leg that names any other within the bound concludes
    §4.2's `mismatch` and registers nothing (one beyond the bound is §3's refusal first, above). Its
    answer is a fresh first leg, as for every refused proof (§4.2 item 4), and that leg's challenge
    is bound to the terms the second leg named: the page shows the person those terms before it
    asks for another proof, and presents no proof for terms it has not shown. A registration keeps
    those ids, never the refs it was sent. **running**, each thing this clause says the door does;
    what the page shows is the page's (**a1p**). **The first leg says the terms it bound.** It
    answers, beside `registers`, `"terms": {"capabilities", "scopes"}`: the capabilities as expanded
    and the scopes as those node ids, or `["*"]`. Its `context.fetch` carries the same as
    `details.terms`, so the chain holds the terms each first leg was asked for, a leg the person
    walks away from included. The page draws what the person confirms from that answer, never from
    its own record of what it sent. The answer serves the caller nothing new: each id is a place
    they cover, as `<agent>` answers it once registered. **a1p**, **running**, ahead of the read
    (above), which lands only after it.
  - **The page offers only what the person holds, and ticks nothing for them.** It offers the
    capabilities and the places that the person's `GET /v1/grant`, read at this door in that visit,
    bounds, and no others, and the whole container only as its own choice (below). Nothing is ticked
    until the person ticks it, so the least choice is none, and a page with no choice sends nothing. The
    contract fixes this, and does not leave it to a page's design, because a tick the person did not
    make is not their choice. Nothing the client supplies selects, suggests, orders or ticks a place or
    a capability: not the provider's `scope` string, not any other parameter of its authorization
    request, not what it registered about itself at the provider, not its name, which stays display data
    labelled as the agent's own claim (below), and not the name of any place, which is the text of whoever
    named it (below). A page that finds no `grants.own` among `GET /v1/limits`' words (§4.6), or gets
    §3's refusal from `GET /v1/grant`, as from a door before this read, offers no choice and
    registers no agent there.
  - **What the page sends is what it shows.** It sends `capabilities`, each by its name in
    `capabilities.md` §1, never a `role`; and each chosen place as its node id, never a path, or
    `"*"` for the whole-container choice alone (below). So the door expands and resolves nothing out
    of the person's sight, and the body is what the challenge binds. It shows each place by the path
    the person's own read served for that id in that visit, or by the id alone where no read served
    one (above), and two places whose paths are the same with their ids as well. It shows the terms
    as the rules give them: one set of capabilities over every chosen place, since a registration
    holds one set (`identity.md` §4); each place with everything beneath it, now and later, since
    coverage is computed down the path at check time (`capabilities.md` §5); that covering a place
    lets its holder create a container under it at or below its `structure_floor`, a thread or a
    project by default, whatever its capabilities (§4's `POST /v1/scopes`); and that an agent
    holding `fetch` is served each chosen place's path, which names every place above it
    (§4.1 item 8).
  - **A place's name on this page is untrusted display data**, as an agent's name is: a place is
    named by whoever made it (§4's `POST /v1/scopes`), or from the first words of what was written
    where a capture opened it (`container.md` §2), or by the admin who last renamed it (§4.5, **not
    running** until its code lands), and `<node>` names no maker. The page draws
    each name inert: escaped, with no control or formatting character of a name acting on the text
    around it, never where or in the style in which the page's own words stand, each segment of a
    path set apart by the page's own drawing and never by a character a name holds. It shows each
    place beside its kind and its path where a read of the person's own served them, and by its id
    alone where none did (above). It lists the places in an order it states on the page, which no
    client and no name can steer: an order by name, and one that puts the place made last first,
    are both steered by whoever makes or renames a place (§4's `POST /v1/scopes`, §4.5). A tick gives the node whose
    id the page sends and what lies beneath it, whatever any name says. The choose step is not
    offered at a door that does not keep §4.5's rule on a place's name ("A name's shape"), which
    is **running** where a place is made: a door from before it lets `POST /v1/scopes` take any 1
    to 255 characters but U+0000, and a capture name its thread from the first 40 characters of
    its item's title, the writer's own text. That rule holds every name a place is given
    or renamed to, on any surface, a captured thread's included, to 1 to 255 characters with no
    `/` or `:`, no control, line-separator or paragraph-separator character, no bidirectional
    control, and never `*`. It does not reach a name given before it ran, which stays as it is; it
    leaves every other formatting character, a zero-width one among them, and names that look
    alike; and it lets two places side by side share a name. A door serves `GET /v1/grant` only
    where it keeps that rule (above), so a page that is not served the read offers no choice and
    registers no agent. Every name, one the rule does not reach included, is drawn inert all the
    same, and two places whose paths are the same are shown with their ids (above). **a1p.**
  - **The whole container is one choice of its own.** **decided** (the Chief, 2026-11-26, v0.7 §AM):
    an agent may be given the whole container, now and later. **a1p**, how it is offered. The page
    offers it only to a person whose `GET /v1/grant` holds `"*"`, as one choice set apart from the
    places, never ticked until the person ticks it, and worded plainly as everything in this cloud,
    what is made later and the inbox included. It sends `scopes: ["*"]` for that choice and for
    nothing else: never because the person ticked every place listed, and never beside a place,
    which `"*"` already covers. The door registers `"*"` for an agent only where the registrant's
    own grant holds `"*"`, and for anyone else it is §3's refusal by the bound (above); the
    challenge is bound to `"*"` as to any scope, and the registration's `identity.grant` carries
    `scopes: ["*"]`, the chain's record of the whole container (**running**). Before the rules below
    ran, the first leg answered `registers` and not the terms; an entry `"*"` was never resolved as
    a ref, and where every other entry resolved the door registered `["*"]`; and the other entries
    were §3's refs, an id or a path tail, so the page alone kept `"*"` to the whole-container
    choice. Three rules put that at the door, **a1p** and **running**, ahead of the read (above),
    which lands only after them: the first leg answers `terms`, `scopes: ["*"]` for the
    whole container, and the page words that confirm from the answer; `"*"` stands alone, so a body
    whose `scopes` hold it beside any other entry is §3's `400`; and on this route a scope is `"*"`
    or has the form of a node id, any other string being §3's `400`, and one of that form is read as
    an id alone, one that names no node the caller covers being §3's refusal, so no name is ever
    read as a place here. They replace for this route what `identity.md` §4 and
    §4.5 say of a scope given as a path tail and of a first leg naming no place. **Ticking places is not the whole container.** A place ticked gives that
    place and what is under it, a top place included. Today every place hangs under one of the
    container's two top places, since a place is made only under a parent and `init` makes the two
    that have none, so a registration on both top places covers what `"*"` covers (**running**). The
    page therefore shows a choice of both top places as covering everything now in the container and
    whatever is later made under them, and sends them as those two ids, never as `"*"`. The rule is
    that such a registration covers those two trees and no other: a place the container came to hold
    under neither would be covered by `"*"` and not by it. No such place can be made today, so the
    difference is **not running**.
  - **A place renamed, moved or removed between the choice and the confirm.** The terms are ids, so
    a place that was renamed is the place that was chosen, and its name was only how the page showed
    it. The door takes each place as an id alone (above; **running**), and finds it at each leg:
    one that names no node the caller covers is §3's refusal; and a place that has left the caller's coverage is §3's refusal by the bound. In each
    case nothing is registered. No route or command moves or removes a place today (**running**),
    and a place is renamed only as §4.5 has it (**not running** until its code lands); these
    answers do not turn on which act changed it. Two rules are owed before
    any door removes a place, and are **running**: that a scope is read as an id alone (above); and
    that the registration's atomic step finds each place again by its id as it then stands, and
    registers nothing where one is gone.
  - **The provider's scopes give nothing here, and are not shown as if they did.** The container
    reads no `scope` claim of any token: what a token may do is its grant's or its registration's
    (`identity.md` §4). **running.** The provider's own scopes are `openid`, `email`, `profile`,
    `phone` and `offline_access`, and it accepts no others: it refuses an authorization that names
    any other word itself, before a page is shown one. The first four select what the provider puts
    in an ID token and returns at UserInfo, and they limit nothing else: by its documentation, "All
    OAuth access tokens have full access to user data (same as regular session tokens)", and its
    scopes "do not control access to your database tables or API endpoints" (Supabase,
    https://supabase.com/docs/guides/auth/oauth-server/, the pages `oauth-flows` and
    `token-security`, read 2026-11-26). `offline_access` is the word a client asks a refresh token
    with, and many agents' clients send it. Here it decides nothing a client receives: not whether
    a refresh token is issued, which this provider hands a client with its first access token
    whether or not the word was asked; no claim beyond the `scope` string; no length of time. Like
    the other words, it is kept in the provider's record of the consent and in each token's `scope`
    claim, which this container does not read, so a later authorization that asks for no more than
    was last approved is approved without asking (below). So whatever its `scope` said, an agent
    approved here can keep signing in to this cloud until its registration is ended (`identity.md`
    §4). The documentation's list stops at four; the fifth, and what it decides, were read in the
    provider's public source on 2026-11-27, at release v2.199.0 of Supabase Auth
    (`internal/models/oauth_scope.go`, `internal/api/oauthserver/authorize.go` and `handlers.go`,
    `internal/tokens/service.go`). That is a reading of the source, as `identity.md` §3a's is. So
    the page reads no capability, no place and no length of time from an authorization's `scope`,
    shows the string nowhere, and treats two authorizations that differ only in it alike. It says
    instead, in fixed words of its own that are the same for every authorization: that approving
    lets this agent sign in to this cloud as the person, within what they tick; that it stays
    signed in to this cloud, with no end date of its own, until they or an admin end its access;
    and that the agent can read their account's record at the sign-in provider: their
    profile, their email, a phone number where the account holds one, and how they sign in. Those
    words are true only while `identity.md` §3a's two records stand: the operator's check that the
    identity project gives a client's token nothing more, and the live test at the provider. While
    either is missing or fallen the page approves no agent: it denies the authorization at the
    provider and calls no route here. The door checks neither record (`identity.md` §3a). An
    authorization whose `scope` names any word but those five is refused: the page denies it at the
    provider and calls no route here, having no true words for what such a scope would give. The
    provider refuses such a word first today; the page's own refusal is for a release that comes to
    accept one. **a1p** (the fifth word and the page's third sentence, 2026-11-27).
  - **Choosing again.** No route changes a registration's terms in place. Where the provider asks
    the person again about a client that already serves them, whatever made it ask, the client's
    own request included, the page offers the choice anew, from nothing, and says beside it that
    declining or leaving ends nothing: the agent keeps what it holds until the person ends it
    (below). The registration then confirmed replaces the earlier one in place and whole: the record
    is keyed on the pair `(client_id, sub)` (`storage.md` §3.2), so nothing of the earlier terms
    carries over and the two are never merged, and it takes no new slot (**running**). **The door
    says what a registration replaces.** Where a live agent registration of that `client_id` already
    serves the caller, the first leg answers, beside `registers` and `terms`, `"replaces":
    {"capabilities", "scopes", "created_at"}`: that registration as the door holds it, which
    `GET /v1/agents` already serves this caller. Its `context.fetch` carries the same as
    `details.replaces`. The challenge is bound to it, and to there being none where the first leg
    carried none: a second leg that finds, inside the registration's atomic step, another
    registration there, one where none was, or none where one was, concludes §4.2's `mismatch` and
    registers nothing. The `identity.grant` that records the new registration carries
    `details.replaces` too, so the chain says which terms ended with it. A first leg for a client
    that does not serve the caller carries no such key. The page shows `replaces` beside `terms`,
    both from that first leg's answer, before the confirm, and where either is `["*"]` it says so in
    the whole-container choice's own words: a narrower registration replaced by the whole container,
    or the reverse. **Running**, ahead of the read (above), which lands only after it, so no page
    offers the choice at a door that does not answer `replaces`. That an agent already approved is chosen for again and
    replaces what it had, with what is replaced shown before the confirm, is **decided** (the Chief,
    2026-11-26, v0.7 §AM: "go with your suggestion"); it answers the second question in #308's body,
    on re-registration: it is not refused. **a1p**, that the door's first leg is what shows it, and
    the shape above. The provider remembers a consent (`identity.md` §3a), and an authorization it
    approved without asking is not pending, so the page calls no route for it (below). A client with
    a live registration keeps it; for a client with none, the page withdraws the stale consent in
    place of following the approval (`identity.md` §4). A person who wants to choose again ends the
    agent, which is never gated (below), and egzos.io then withdraws their consent to that client at
    the provider, so that the client's next authorization is asked about. Narrowing a registration
    short of ending it is not in this door.
- **Who registers a terminal: each person, their own.** A terminal registration is the person's own
  sign-in at a terminal (`identity.md` §4): it holds no capabilities or scopes, and its token holds
  the person's grant as it stands at each request. **decided** (v0.7 §AJ). **a1p**, the rest:
  - Anyone holding a user grant registers their own, with the confirm, and nobody registers one for
    someone else. The person it serves, or an admin, ends it, and so does the terminal itself,
    whose token is its person's.
  - **A `client_id` is registered as a terminal once.** One that names any registration here, an
    agent's or a terminal's, live or revoked, for any person, is never registered as a terminal, and
    one that names a terminal's is never registered as an agent. **The door does not say so before a
    leg.** Such a request is served its first leg like any other; its second leg, inside the
    registration's atomic step, concludes `step_up` refused, `registered`, and is answered with a
    fresh first leg, as every refused proof is (§4.2 item 4). The answer is the same whether or not
    the `client_id` was ever registered here, and the ledger says which case it was. A terminal that
    was ended never returns. A `client_id` equal to `identity.client_id` is §3's refusal before any
    leg, as on `POST /v1/agents`: that id is no secret. **What stays open:** a caller whose proof
    they know to be good, and who is refused, may infer that the id was taken; each such try costs
    a confirm and is on the ledger.
  - A person holds at most 16 live terminal registrations, counted apart from their agents: a 17th
    answers `429` with `{"error":"too_many_terminals"}` and §3's headers before any leg.
  - **A terminal may say what kind of machine it is.** `machine` is one line beside the name
    (`identity.md` §8), there to help the person recognise their terminals: the terminal's own
    claim, kept on the registration and served in `<terminal>`. Nothing checks it and nothing is
    decided on it. A registration made without one never gains one. On the chain it is written
    where the name is, in `details.signs_in` of each first leg's `context.fetch` (below), the
    fresh first leg that answers a refused second leg included, and in no other entry: the
    `identity.grant` that records the registration does not carry it, and every entry made at a
    terminal already names the terminal (`identity.md` §3a). A door from before `machine` answers
    §3's `400` to a body that carries the key, as to any key it does not name, and a page that
    gets that answer registers the terminal without it. **a1p** (v0.7 §AJ, the Chief's ask of
    2026-11-15; #394).
- **Each family of routes reads and acts on its own kind.** `GET /v1/agents` never lists a terminal
  and `GET /v1/terminals` never an agent, and a `client_id` of the other kind is §3's refusal on
  every agent and terminal route, the revoke and the log included. `GET /v1/terminals` lists live
  registrations; with `ended=1` it lists the ended ones instead, so that a terminal's log can still
  be read after it is ended, and egzos.io can withdraw the person's consent to it at the provider
  (`identity.md` §4). **a1p** (v0.7 §AJ).
- **A terminal's token gives no one access.** `POST /v1/grants`, `POST /v1/agents`,
  `POST /v1/terminals`, `POST /v1/credentials` and `DELETE /v1/credentials/{id}` are §3's refusal to
  a terminal's token before any leg: access is given, and a confirm credential kept or removed,
  from a browser. On every other confirm-gated act it is served the first leg and concludes no
  second (§4.2 item 3). **a1p** (v0.7 §AJ). `GET /v1/grant` is §3's refusal to it too (above;
  **a1p**, v0.7 §AM; **running**).
- **The container never presents a caller's token to the provider**, here or anywhere (`identity.md`
  §3a), so it does not read the provider's authorization itself. **The consent page owes the checks
  instead**, egzos.io's and a self-hosted provider's alike: it reads the authorization with its own
  first-party session, and calls this route only for one that is pending, was requested by the
  person whose container token makes the call, is for the body's `client_id`, and names no scope
  but the provider's five; and it refuses a `client_id` registered on another container (`identity.md`
  §3a). **a1p** (a1r and a6 on #285; the scope check, v0.7 §AM). For a terminal it owes one more
  check: it calls `POST /v1/terminals` only for a client it registered at the provider itself,
  in this browser, for a sign-in the person continued, with egzos.io's callback that client's
  one redirect URI (`identity.md` §3a). **a1p** (v0.7 §AJ).
- **What the container holds to is the registrant's confirm.** The first leg answers `newly: []` and, in
  its own field, `"registers": {"client_id", "name"}`: the agent is not a person, and its `name` is
  the agent's own claim, untrusted display data that every surface escapes and labels as the agent's
  (design-gap Egzos/egzos-platform#117). The first leg's `context.fetch` carries the same
  `details.registers` (the `name` as escaped display data), so a first leg the person walks away from
  still names the agent it showed. The challenge is bound to the body's `client_id`, its capabilities
  as expanded and its `scopes`, so a second leg naming any other is §4.2's `mismatch`. The first
  leg also answers `terms`, and `replaces` where it replaces one (above; **running**). **a1p** (a6
  and a1r on #285). A terminal's first leg answers `newly: []` too and, in its own field,
  `"signs_in": {"client_id", "name"}`, with `"machine"` beside them where the body gave one, and
  the same `details.signs_in` on its `context.fetch`: the name and the machine are the terminal's
  own claims, escaped and labelled as an agent's name is. Its challenge is bound to the body's
  `client_id`, its `name` and its `machine`, a body that gives none included, so a second leg that
  names another machine, adds one or drops one is §4.2's `mismatch`. **a1p** (v0.7 §AJ).
- **`authorization_id` keys the registration, atomically**: of two concurrent requests naming one
  authorization, at most one registers, as an agent or as a terminal, and every later request
  naming it, on either route, is §3's refusal.
  `identity.grant` records it as `details.authorization_id`, so the consent page's record and the
  container's join; it is **what the caller claimed**, which the container cannot check, never a
  verified fact. Only after the registration is written does egzos.io tell the provider to issue.
- **The agent log serves only what the reader may see now.** It lists the agent's entries for that
  person (`details.for`), and omits every entry that was a refusal — a probe's `context.fetch` with
  `items: []`, a refused act — and every entry whose `subject` the reader's grant does not cover
  **today**. An omitted line leaves no marker and no count, so the log cannot tell a reader what exists
  outside their sight, or whether a probed target existed. The terminal log is the same reader over
  the entries whose `actor` is that person and whose `details.terminal` is that `client_id`
  (`identity.md` §3a), with the same omissions but one: it also serves an entry whose subject is
  the person's own `sub`, a registration serving them or an upload of theirs, so what a terminal did
  to its person's other access shows in its log. An ended terminal's log stays readable to the
  person it served and to an admin.
- **Ending someone else's access takes the confirm; narrowing your own does not.** Granting and
  registering are gated (§4.2), so ending a grant or a registration that serves another person is
  gated the same way: `DELETE /v1/grants/{sub}` for a `sub` other than the caller's own, and an
  admin's `DELETE /v1/agents/{client_id}?sub=` or `DELETE /v1/terminals/{client_id}?sub=` for a
  registration serving someone else, answer §4.2's first leg and revoke nothing until its second
  leg confirms. The first leg answers `newly: []` and,
  in `"revokes"` (and its `context.fetch`'s `details.revokes`), the grant or registration it ends and
  every registration a grant takes with it; its challenge is bound to the `sub`, or to the pair
  `(client_id, sub)`, so a second leg naming another is `mismatch`. `last_admin` (below) is the
  route's own check: it answers before any leg (§4.2 item 1) and is checked again inside the second
  leg's atomic step. An admin revoking their own grant, or a person revoking a registration that
  serves them, narrows only their own access: it is never gated, answers `{"result": "revoked"}` at
  once, and appends only its `identity.revoke`s. **a1p** (GHSA-c3gg-hwx9-473g).
- **On `POST /v1/grants`, `POST /v1/agents`, `POST /v1/terminals` and a gated revoke, the button
  also needs a fresh sign-in**, as a first credential does (below): the provider token's `amr`
  within the last 300
  seconds; a stale one concludes `step_up` refused `not_fresh` (§4.2 item 4). **What stays open, on
  the record:** for a person with no credential, where buttons are on, these acts rest on a fresh
  sign-in and the button; a credential of their own, or `confirm.allow_button` at `false`, closes it.
  **a1p** (GHSA-c3gg-hwx9-473g).
- **Revoking the last admin grant, or re-granting it narrower,** answers `409` with
  `{"error":"last_admin"}` and §3's headers, to the admin who asked — a fact about their own
  container — and appends `identity.revoke` (a revoke) or `identity.grant` (a narrowing re-grant)
  with `outcome: refused`, `details.reason: last_admin`, and no `capabilities` or `scopes`: nothing
  changed hands. **a1p** (a1r on #287).
- **Credential registration has two legs.** The first answers `{"result": "register", "challenge",
  "webauthn": <PublicKeyCredentialCreationOptions>, "expires_at"}`, a challenge bound to the caller as
  §4.2's are. It also answers `"confirm": {"challenge", "webauthn"}`: a second challenge, for the
  proof the second leg's `confirm` carries, issued and bound as §4.2's first leg issues one (the act
  `credential.add`). For a person who already has a credential, `webauthn` is the
  `<PublicKeyCredentialRequestOptions>` for the assertion; for a person with none it is `null`, and
  the challenge is the button's. A first leg whose options list the person's credentials to their
  authenticator appends §4.2's first-leg `context.fetch` (`details.read: credentials`), the fresh
  first leg answered after a refusal included; a first leg for a person with no credential appends
  nothing. The second leg carries `{"challenge", "attestation", "confirm"?}`; user verification is
  required. Every proof presented is concluded as §4.2's are, so the button's first enrolment leaves
  its `step_up` too. **decided** (v0.7 §AD: the button is the first enrolment's act, and every add is
  audited; a1r on #290); **a1p**, the legs' shapes.
  - **A person with a credential adds another only with a biometric proof from an existing one** in
    `confirm`. The button is refused on this route whatever `confirm.allow_button` says, so a stolen
    session cannot add the thief's authenticator, and a fresh sign-in does not stand in for the proof:
    the provider sign-in may be only an email link, and the authenticator is the stronger factor.
    **decided** (v0.7 §AD).
  - **Removing a credential needs a biometric proof too, never the button** — the person's own, from
    any of their credentials, or, for an admin's recovery of another person, the admin's own (an admin
    with none registers one first). A stolen session can therefore neither remove a person's
    credentials to fall back to the button, nor clear them to enrol a first one of its own.
    **decided** (v0.7 §AD).
  - **The first credential** needs, in `confirm`, the button **and a fresh sign-in**: the provider
    token's most recent authentication (its `amr` timestamp) within the last 300 seconds. A token
    lifted from a session that signed in earlier cannot enrol one. **decided** (v0.7 §AD). Where
    `confirm.allow_button` is `false`, the first credential is enrolled only from the owner's own
    surfaces (the lifeboat or the CLI, holding the owner `Token`), which enrol the owner's own
    authenticator: **while buttons are off, a person other than the owner who has no credential
    cannot enrol one, and so cannot perform a confirm-gated act.** That is the cost of the stronger
    setting, taken on purpose: an owner turns buttons off after the people who need the confirm have
    enrolled. **a1p** (a1r on #285). **This door is never the owner's own surface**, and a container
    `Token` carries no sign-in to be fresh: over REST, only a provider sign-in enrols a first
    credential. **decided** (v0.7 §AD; a1r on #290).
  - **What stays open, on the record:** whoever holds a fresh session of a person who has no
    credential yet can enrol the first one. Where that person is an admin, the residual reaches every
    person, since an admin's credential confirms recovery over theirs; `confirm.allow_button` at
    `false` closes it, keeping a first enrolment to the owner's surfaces. **Recovery:** an admin
    removes another person's credentials (`DELETE /v1/credentials/{id}?sub=`) with the admin's own
    biometric proof, never the button, and the owner removes any from the CLI or the lifeboat with the
    owner `Token`, egzos's analogue of GitHub's recovery codes; the person then enrols again.
    **decided** (v0.7 §AD).
  - **Every second leg that concludes is audited**: `step_up` first where a `confirm` proof was
    presented (as §4.2 item 4, refused ones included), then `identity.credential`. An add carries
    `details.op: add` and `outcome: added`, or `refused` with `details.reason` (`attestation`, `stale`,
    `no_proof`, `not_fresh`, `button_refused`); the caller's answer to a refusal is a fresh `register`,
    whatever the reason. A removal carries `details.op: remove` and `outcome: removed`, or `refused`
    with `details.reason` (`stale`, `no_proof`, `button_refused`, `assertion`); the answer to a refusal
    is a fresh `confirm`. **Every removal appends it, on every surface**: the owner's removal from the
    CLI or the lifeboat with the owner `Token` appends `identity.credential` (`op: remove`, `actor` the
    owner) too, since a removal reopens the button for that person. A `sub` the admin does not cover is
    §3's refusal before any leg, and follows §4's rule for a refusal. **decided** (v0.7 §AD), the
    audit of every add and remove; **a1p**, its details.
- **New events**: `identity.grant` and `identity.revoke` (`details.kind`: `user`, `agent` or
  `terminal`), as
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
   person holds at most 16 uploads that are open or orphaned (below), **or written as an artifact
   item whose bytes are still staged** (step 3: an agent's, until a person promotes or tombstones it),
   counting the uploads of every agent serving them (`identity.md` §4); a container `Token` counts as
   a person of its own, so each `Token` the owner mints holds its own 16, as before (only the owner
   mints one). A 17th answers `429` with `{"error":"too_many_uploads"}` and §3's headers — a
   fact about what the caller's own person holds. So what a person holds staged, and nobody has
   decided on, is capped at 16 times `blobs.upload_max_bytes`, and a person's decision is what frees a
   slot (v0.7 §Z: asked about, never purged). **decided**, the per-person cap on staged bytes (v0.7
   §AC); **a1p**, the 16 (a6 on #285). A successful open appends nothing: no bytes have moved. A
   refused open — a `scope` the token cannot write to — follows §4's rule and appends `context.fetch`
   with `items: []`.
   **A file's name keeps a place name's characters** (v0.7 §AL; **a1p**, not running): beside the
   1 to 255 characters, it holds no character of category Cc, Zl or Zp and none with the
   Bidi_Control property (§4.5), as on every surface that opens an upload, the MCP tools' included.
   A name is display data only: no store ever uses it as a path or a key, and two files may share
   one.
   **An agent's kept bytes are bounded per agent** (v0.7 §AL; **a1p**, not running): the files a
   `client` principal keeps (item 3), counted as the sizes of its artifact items that are not
   tombstoned, with the declared sizes of its uploads that are open or orphaned, stay within
   `blobs.agent_kept_max_bytes` (default 1073741824, 1 GiB; an `admin` may change it), a new key
   that enters `container.md` §8 and `_types.py` with the code that reads it. An open that would
   pass it answers `429` with `{"error":"too_many_bytes"}` and §3's headers, before the 16 are
   counted: a fact about what that agent holds. The count is per `Token.id` (§6): each agent
   registration and each client container `Token` has its own, and a person's own uploads count
   toward none. A person frees room by removing the agent's files (§4). An agent's file kept at
   once holds none of the 16 once its item is written: the 16 still count its open and orphaned
   uploads, and the staged items agents wrote before item 3's keep.
   **The answer also carries the bytes' address**: `{"upload", "expires_at", "put_url",
   "put_expires_at"}`, item 2a's (**a1p**, not running).
2. **Bytes.** `PUT /v1/uploads/{id}` with the raw bytes. The id is bound to the principal that opened
   it and expires after one hour; the container reads at most `size` bytes, checks length and sha256, and
   **stages** them (`BlobStore.stage`) — never `put`, so staging never answers whether the content
   already exists. Each `PUT` on a live id of the caller's own appends **`upload.put`** (`subject` the
   upload, `scope`, `size`, `sha256`, `outcome: staged` or `refused` with `details.reason`: `length`,
   `hash`, `already`). A `PUT` naming an unknown, expired or another principal's id is §3's refusal and
   appends `context.fetch` with `items: []`. `200` `{"upload": <id>, "sha256"}`; a refused `PUT`
   answers `400` (`invalid_request`), a fact about the caller's own bytes, and a later `PUT` of the
   right bytes may still stage them.
2a. **The bytes' address** (v0.7 §AL; **a1p**, not running). `put_url` is `PUT
   <public origin>/v1/uploads/<id>?opener=<Token.id>&size=<n>&sha256=<hex>&expires_at=<UTC
   ISO-8601>&sig=<sig>`, the origin `identity.md` §2's, `expires_at` written as §6 writes it, and
   `sig` an HMAC-SHA256 under §6's container key over `canonical` JSON (`events.md` §3) of
   `{"use": "upload", "upload", "opener", "size", "sha256", "expires_at"}`. The `use` field is in no
   `BlobGrant`, so no grant's `sig` verifies as an address and no address's as a grant.
   - **It is bound** to the upload, to its opener (the `Token.id` that opened it), to the declared
     `size` and `sha256`, and to one use. It lives 900 seconds from its issue and never past the
     upload's own `expires_at`; that is a fixed contract value, not configurable.
     **It is handed only** in the answer to its opener's own open, or to that opener's
     `POST /v1/uploads/{id}/address` (`egzos_upload_address`), which issues a fresh one for an
     upload of its own that is live and whose bytes have not arrived, and appends nothing.
   - **It is redeemed with no bearer.** A `PUT` to this path that carries no `Authorization` header
     and carries the descriptor is read as an address; one that carries the header is item 2's
     route, where a query parameter is §3's `400`. No other route and no other method reads the
     descriptor, `/mcp` included: **it is never a bearer for anything else**. It delivers exactly
     the declared bytes to that one upload. It reads nothing, lists nothing, writes no item and
     discards nothing. Like §6's redemption, it is a request §2 reads no bearer on: a `PUT` to this
     path with no `Authorization` header is never answered `401`, and its answers are the ones
     below.
   - **The checks, in this order:** (1) every parameter is present and well-formed; (2) `sig`
     verifies, compared in constant time; (3) `expires_at` has not passed; (4) the address has not
     been spent, and this arrival spends it, whatever the later checks decide, atomically, as §6's
     check 4 spends a grant, in §6's spent records (`storage.md` §3.5); (5) the upload exists, its
     opener is the descriptor's, it is live and not discarded, its bytes have not arrived, and its
     `size` and `sha256` are the descriptor's; (6) the opener is live and still holds `remember` on
     the upload's scope, checked now; (7) the bytes, read only up to `size`, are exactly `size`
     long and hash to `sha256`. Checks 1 to 6 refuse with §3's refusal, byte-identical whichever
     failed: a second use, a late use and a forged one answer alike. Check 7 refuses with `400`
     (`invalid_request`), a fact about the bytes the holder sent, and leaves the upload's bytes
     unarrived, so its opener may ask for a fresh address.
   - **On success** the bytes are staged as item 2 stages them, the bytes step is spent, and
     `upload.put` (`outcome: staged`) is appended, attributed to the opener. `200` `{"upload",
     "sha256"}` with §3's headers.
   - **Traces.** Where `sig` verifies, a refusal appends `context.fetch` with `items: []`, the
     failed check in `details`, attributed to the opener, and counts toward its per-token bucket
     (§2 item 7), as §6's refused redemption does; where it does not verify, the refusal is counted
     by the `rest` throttle and tallied under `forged` (§6). **No log and no entry keeps an
     address**: its spent record is its `sig`'s sha256 and its `expires_at`, and the door writes
     neither the address nor its query to any log.
3. **Item.** `POST /v1/items` with `{"kind": "artifact", "upload": <id>, "scope"?, "key"?, "tags"?}`
   writes the item, `unverified` like every write. The id must be the caller's own, staged, and not yet
   itemised; `scope`, when given, must equal the upload's; otherwise §3's refusal. Bytes and item are two
   separate spends of one id, **each an atomic check-and-mark**: of two concurrent `PUT`s, or two
   concurrent item writes, naming one id, at most one proceeds, and the other is refused as spent. A
   person's artifact is promoted at once (`BlobStore.promote`, `blob.put`). **An agent's is kept at
   once too** (v0.7 §AL): it is promoted with its item, in a place the agent's terms cover, which a
   write needs anyway (`remember` on the scope), the whole container where its person gave it that
   (§4.3). Its item stays `unverified`, its provenance names the agent (`actor`, `client`, and the
   person it serves in `details.for`), and a person promotes it to verified or removes it as any
   unverified item; nothing else is decided for them. An agent's artifact written before this
   stays staged until a person decides on it, as it did. **decided** (the Chief, 2026-11-26: "go
   with keep"), that it is kept; **a1p**, the rest; **not running**: until the code lands, an
   agent's stays staged. Events: `item.add`, and `blob.put` where promoted.

**Nothing staged is deleted on a timer, and nothing staged goes untracked** (v0.7 §Z, amending R11's
"30 days cold, then purge"):

- **An orphan** is an upload whose bytes were staged but which expired before an item was written. It
  is listed in `GET /v1/pending` under `"uploads": [{"upload", "name", "size", "sha256", "scope",
  "opened_at"}]` to its opener, an agent's or a terminal's to the person it serves (an agent reads no
  `GET /v1/pending`, §4), and to an admin; it counts toward the 16, and is removed only by
  `DELETE /v1/uploads/{id}` (its opener, the person an agent or a terminal opener serves, or a person
  with `admin`
  over the whole container), which deletes the staged bytes and appends **`upload.discard`**
  (`opener`, and `bytes_deleted`: false when another live upload or staged item holds the same bytes,
  which then stay). Its opener may discard an open upload the same way, to free its slot before the
  hour is up. **decided** (v0.7 §AC, applying §Z); **a1p**, the cap of 16 and `upload.discard`'s
  details.
- **A staged artifact item past `blobs.staging_retention_days`** appears in `GET /v1/pending` under
  `"staged": [<item>]` — to an interactive principal covering its scope, and **instead of** in `items`,
  never both — until a person promotes it or tombstones it (§4); a tombstone deletes the **staged**
  bytes (never promoted ones: [0.3 · 44] holds) unless another upload or staged item still holds
  them, and its `item.tombstone` entry then carries `details.staged_deleted: <sha256>` where bytes
  were deleted, so the deletion is on the record. A promotion of such an item
  appends `blob.put` (§4's promote row). **decided** (§Z); **a1p** the two event details.

**Not in this door at v1.0:**
- **Quarantine and config.** No flagship screen #137 cites needs either at v1.0. They stay on the CLI.
- **`[v1.1 · #137 1–7, 9–12]`**: a revision on reads (1); window state and its events (2, 3);
  `return_to` (4); writability per scope (5); a nonzero-delta move inside a window (6); pending
  facets and filters (7); anomaly sentences (9); token reads and their events (10); where coverage is
  computed (11); a quarantine flag per ring (12). A builder adds none of them.

### 4.5 · Renaming an item or a place

**a1p**, every clause of this subsection (v0.7 §AK; #404), and **not running** until its code lands,
but for "A name's shape" where a place is made, which is **running**: until then each of these
routes is §3's refusal, as a path no route declares, and §4.6 lists none of their words. The `{id}` in each path is an id, never a path tail, so §3's
`ambiguous` never arises on these routes.

**A name's shape.** A place's name, made or renamed on any surface (`NodeService.create` and the
rename, which the door and `egzoscore mk` call), is 1 to 255 Unicode scalar values, kept and
compared as given, with no normalisation. It holds no `/` and no `:`, which a path and its
`type:name` labels reserve (`container.md` §2), no character of general category Cc (U+0000 and
U+007F among them), Zl or Zp, and none with the Bidi_Control property. A place's name is never
the one character `*`, which a list of scopes reserves for the whole container (`capabilities.md`
§5; `identity.md` §4). An item's new name is held to an upload `name`'s rule (§4.4) and holds no
character of Cc, Zl, Zp or Bidi_Control. A name, a place's or an item's, that is not well-formed
Unicode (a lone surrogate) is `400`. Anything else is §3's `400` at the door, before any lookup,
and refused on every other surface. Names given before this stay as they are. Pure capture, when it
names a thread from a title, does three steps in order: it writes each `/` and `:` as `-` and drops
every character of Cc, Zl, Zp or Bidi_Control and every lone surrogate; it keeps the first 40
characters, the length it
keeps today; and where nothing is left, or only `*`, the thread's name falls back to the item's
id. Sibling names may still repeat, a tail naming two is still refused as ambiguous (§3), and no
rule is added on which type sits under which: both are left for a later change, because pure
capture names inbox threads from titles that may repeat, and a rule there needs its own decision
(v0.7 §AK).

**Renaming an item: a person's act, as a tombstone is** (§4). `PATCH /v1/items/{id}` with
`{"name", "confirm"?}` → `{"item": <item>}`.

- **Needs** an `interactive` principal holding `organize` and `fetch` where the item sits: the
  answer carries the item as stored, and a name is given by someone who reads what it names. A
  `client` principal gets §3's refusal, and MCP has no tool for it: an agent's write waits for a
  person (§4.4), and a name is what the person finds an item by.
- **It sets one field.** An artifact's `content.filename`; a text item's `content.auto_title`, with
  `content.title_engine` set to `person`, so a title a person gave is told from one an engine made
  and no later title pass replaces it (`context-item.md` §3). The bytes, `content.sha256`, `scope`,
  `key`, `tags` and `trust` stay as they were. **The rename moves `lifecycle.version` in the same
  atomic step as its write and its `item.rename`** (`context-item.md` §6), so a confirm on the item
  opened before the rename concludes `mismatch` (§4.2 item 3); `lifecycle.updated_at` moves with
  it. An inbox thread keeps its name when its item is renamed (`container.md` [0.3 · 2]).
- **An item that is not verified and that no person has promoted is renamed at once**, an
  unverified `rule` aside (below). A `confirm` sent with it is ignored and concludes nothing.
- **A verified item, or one a person has promoted (`provenance.approved_by`) whatever its status
  now, an unverified `rule` aside, takes the confirm** (§4.2): renaming curated knowledge goes
  behind a re-authentication, as its tombstone does (§4). The first leg answers `newly: []` and
  names what it renames, `"renames": {"item", "kind", "from", "to"}`, the names untrusted display
  data; its `context.fetch` carries the same as `details.renames`. The challenge is bound to the
  body's `name` and, as on every act on an item, to the item's version, `scope` and
  `trust.status` (§4.2 item 3), so a second leg that names another, or finds the item changed, is
  §4.2's `mismatch`. What a challenge on an item is bound to moves only by an act its own rule
  admits and the chain records, on the item or, for a quarantine, on the item it was copied from:
  a rename, a promote, a move, a quarantine. A title pass, where one runs, moves the version with
  the title it writes (§4.2 item 3). So any principal whose rule admits such an act, an
  agent holding `organize` among them and a terminal as its person, can keep a person's confirm
  from concluding; each such act is on the chain, revoking that principal ends it, and a
  `mismatch` says nothing of why.
- **One atomic step** holds a second leg's `step_up`, the write, the version's move and its
  `item.rename`, and an item renamed at once is written so, with its `item.rename`, in one atomic
  step too. The step reads the item as it stands under the lock (`storage.md` §3.6) and decides
  there whether it takes the confirm: an item promoted, quarantined, moved or tombstoned since the
  door read it is treated as it then stands, and is never written over. `item.rename` carries
  `kind`, `field` (`filename` or `title`), `from`, the name as it stood, and the new `name`, both
  untrusted display data.
- **A `name` equal to the name the item bears now**, compared as given, changes nothing: after the
  route's own checks pass, the door answers `{"item": <item>}` as it stands, opens no confirm,
  writes nothing, moves no version, and appends one `context.fetch` whose `subject` is the item
  and whose `items` names it, as `GET /v1/items/{id}` does (§4.1 item 3), in place of
  `item.rename`: the answer serves the item, so the entry is a read of it and not a probe's.
- **Absent, uncovered, tombstoned, quarantined, an unverified `rule` whatever its provenance
  (served only at `GET /v1/pending`), or without `organize` or `fetch`**: §3's refusal and §4's
  probe, the same for each.

**Renaming a place: the container's admin's act, behind the confirm.** `PATCH /v1/scopes/{id}`
with `{"name", "confirm"?}` → `{"node": <node>}`. The place is a `project` or a `thread`
(`container.md` §1); a node of any other type is not renamed (below).

- **Needs** a person holding a provider token whose grant holds `admin` over the whole container
  (`["*"]`), as §4.3's `GET /v1/grants` needs (a container `Token` gets §3's refusal, as there),
  and `organize` and `fetch` on the node; any such person may, the owner or another admin. The
  answer carries the node. After a rename a path names whatever bears the name now. The rename
  changes no coverage and no audience, since tokens, grants and registrations hold ids; it changes
  only what a path names. So it is kept to the container's admin, who already decides who may see
  and act on every place, and made a confirmed act the chain records with the old name and the
  new. The name it frees is free, and so is every path that ran through it. Anyone whose token
  covers a parent, a person or an agent, with no capability at or below the floor (§4), may make a
  place that bears the name, before the rename or after it, and a pure capture names an inbox
  thread from its title; a tail that matches then names that place, without the confirm. A read
  or a write still addressed by the old path then reaches that place and its audience, and a
  grant or a registration asked for by a tail is written over the place the tail names when the
  door resolves it (`identity.md` §4), its first leg naming no place. A move or a copy still
  passes the gate, which names who would newly see the item at the place the path names now
  (§4.2). Nothing here refuses the rest: the door keeps no old name to refuse it by. That is why a
  client keeps ids, and sends an id wherever an act takes the confirm.
- **It takes the confirm** (§4.2). The first leg answers `newly: []` and names what it renames,
  `"renames": {"node", "type", "from", "to"}`, the names untrusted display data; its
  `context.fetch` has the node as `subject` and carries the same as `details.renames`. The
  challenge is bound to the node's id and its name as the first leg read it, and to the body's new
  `name`, so a second leg that finds the node's name changed, or that names another, concludes
  `mismatch` (§4.2 item 3). A name renamed away and back between the legs matches again, and the
  rename concludes as the first leg showed it. A `client` principal never gets the confirm (§4.2
  item 6), MCP has no tool for it, and a terminal's token concludes no second leg (§4.2 item 3,
  `identity.md` §5).
- **What a rename changes.** The node's id never changes, and a rename writes the node alone: a
  container `Token`'s `scopes`, and a grant and an agent registration this door writes, hold node
  ids (`capabilities.md` §5, `identity.md` §4). A reference held as a path may stop resolving, or
  may come to name another node that now bears the name; nothing redirects from an old name
  (`container.md` §2). A path names every ancestor of a node, covered or not (`container.md` §2;
  §4.1 item 8), so whoever reads a path beneath a renamed place it does not cover, a principal
  holding `fetch` there, a person or an agent, or a person shown a proposal at `GET /v1/pending`,
  sees the new name in its paths from the moment of the rename: a place's rename shows its new
  name, and so that it was renamed and when, to whoever reads a path beneath it. **decided** (the Chief, 2026-11-26; v0.7 §AK). For a
  principal that reads no path beneath the place, a tail it gives through the old name no longer
  reaches the place and, unless it now matches another place that bears the name (above), gets
  §3's refusal, the same answer as for a place its token no longer covers. It may so learn
  that a name it gave itself no longer names the place, and when; it never learns the new name. A client that keeps a place to act on keeps its id, never its path, and acts on the id
  a path resolved to at once.
- **A proposal is shown as its ids now stand.** A parked proposal keeps the `from_path` and
  `to_path` it was parked with (`container.md` §6), which may hold a name a place no longer bears.
  This door never serves them: `GET /v1/pending` renders both from the proposal's ids as they
  stand when it is served (§4.1's `<proposal>`), an approve's or a deny's first leg carries no
  path (§4.2 item 1), and a proposal is decided on ids. A place's rename is not served without
  this (§4.6).
- **One atomic step** holds the second leg's `step_up`, the node's write (`storage.md` §3.6) and
  its `node.rename`, which carries `type`, `from`, the name as it stood, and the new `name`, both
  untrusted display data.
- **A `name` equal to the name the place bears now**, compared as given, changes nothing: after
  the route's own checks pass, the door answers `{"node": <node>}` as it stands, opens no confirm,
  writes nothing, and appends one `context.fetch` with `items: []` and the node as `subject`, in
  place of `node.rename`.
- **Only a `project` or a `thread` is renamed.** The inbox, the personal root and `global` are
  never renamed, and no other type is renamed in this change (v0.7 §AK). A node of any other type,
  an absent or uncovered node, a `client` principal, and a caller short of what this needs get §3's
  refusal and §4's probe.

### 4.6 · What this door serves

`GET /v1/limits`, to any valid token, a `client` principal's included → `{"contract",
"features": [<word>], "upload_max_bytes", "inline_max_bytes", "uploads_held_max"}`, and, once v0.7
§AL's code runs, `"agent_kept_max_bytes"` and `"file_call_max_bytes"` beside them (**a1p**, not
running). **a1p** (v0.7
§AK; #360), **running**, its `features` naming `terminals.machine` and `grants.own` until another
word's code runs.

- `upload_max_bytes` and `inline_max_bytes` are `blobs.upload_max_bytes` and
  `blobs.inline_max_bytes` as they stand (`container.md` §8), and `uploads_held_max` is §4.4's 16:
  facts about the caller's own container and no secret, so a client says "too big" before it opens
  an upload. `agent_kept_max_bytes` is `blobs.agent_kept_max_bytes` as it stands, and
  `file_call_max_bytes` is §4.7's 131,072 (**a1p**, not running). **It is a read of config keys and
  constants, not a config surface**: it sets nothing and serves no other key, and config stays on
  the CLI (§4.4).
- `contract` is the contract set's version (`README.md`), `"1.1"` today. `features` names, one word each and in
  no order, what this door serves beyond the set as release 0.2.0 served it: `terminals.machine`
  (§4.3's `machine` line), and §4.5's `items.rename` and `scopes.rename`, each only once its code
  runs, and `items.rename` only where its rename moves `lifecycle.version` in the same step as its
  write (§4.5) and every confirm on an item, an approve of a proposal that names it included, is
  bound to the item's `lifecycle.version`, `scope` and `trust.status` (§4.2 item 3): the route is
  not served without both. `scopes.rename` is named only where `GET /v1/pending` renders a
  proposal's paths from its ids as they stand (§4.5): the route is not served without it, so no
  proposal parked before a rename shows a name a place no longer bears. A client ignores a word it
  does not know.
  `grants.own` (§4.3's `GET /v1/grant`) is named only once its code runs, and only where the door
  runs every rule §4.3 says lands with that read and keeps §4.5's rule on a place's name (v0.7
  §AM): the read is not served without them.
  `files.agent` (v0.7 §AL) is named only once §4.4's address (item 2a), its keeping of an agent's
  artifact (item 3) and its bound on an agent's kept bytes, and §4.7's file tools, all run: an agent
  that finds it can save and read back files of any size through the MCP door (**a1p**, not
  running).
- **A container from before this route answers it with §3's refusal**, and a client reads that as
  none of the words: it offers none of those acts, rather than reading a later `404` on one as a
  refusal of the act.
- Reading it appends one `context.fetch` with `items: []` and `details.read: limits`, as §4.3's
  reads do, its `subject` null as a container-wide `config.set`'s is (`events.md` §1) and its
  `scope` null, as `scope` may be (`events.md` §2): it serves no item or node, but `events.md` §4
  invariant 2 excepts nothing else.

### 4.7 · The MCP tools

The tools both MCP transports serve (`src/egzos/mcp/server.py`): over stdio as the client `Token`
the door was started with, at `/mcp` as the bearer the door verified (`identity.md` §7).
**decided** (v0.7 §AL), that the MCP door carries every file a person's other doors carry, that an
approved agent's file is kept at once, and that a file larger than one call goes to a single-use
address; **a1p**, every other clause of this subsection, which the Chief may veto clause by clause.
**Not running**, but for the four tools marked running in the table, until the code lands.

**An MCP tool mirrors a route this door already has, under the same capabilities, coverage,
validation, refusal and audit events, so no tool gives a caller a power its token lacks at `/v1/`.**
A tool that would need a rule of its own is a route first, defined in §4–§4.6. The token that can
call a tool can call its route.

**Answers, in the running tools' channels** (§3's last paragraph; v0.7 §AL):

- **Not live:** `{"ok": false, "reason": "this token is no longer valid"}`, the same from every tool.
- **Malformed:** the word `invalid_request` in the tool's error result, decided on the arguments
  alone and before any lookup: an argument the tool does not define (#421's rule), U+0000 or a
  string that is not well-formed Unicode (§3), and each shape §4.1 and §4.4 refuse with `400`. A
  mistyped argument is refused by the transport's own validation, before the tool runs. **`busy`**
  likewise; an `internal` answer is bound with the code.
- **§3's refusal.** A read answers its empty result, as `egzos_fetch` does, so a refused read and an
  empty one are one answer. A write answers `{"ok": false, "reason": "scope not found"}`, one answer
  for every case §3 lists, a missing capability included. Either appends §4's probe, a
  `context.fetch` with `items: []`. `egzos_remember`'s running texts for a missing `remember` and an
  unknown `kind` stand as they run until #155 brings them into line with §3.
- **Ambiguous:** a read carries `"ambiguous": [<path>]` beside its empty result, as `egzos_fetch`
  does; a write answers `{"ok": false, "reason": "ambiguous", "matches": [<path>]}`; only to a
  principal holding `fetch`, and to any other §3's refusal (§3).
- **A fact about the caller's own:** where the route answers `429`, the tool answers `{"ok": false,
  "reason": <the route's error word>}`: `too_many_uploads`, `too_many_bytes` (§4.4).

**Every string an item, a file or a node holds is untrusted data.** Each read opens with
`egzos_fetch`'s `banner`; an item's body or `inline` text sits inside the response's fence; titles,
tags, file names, types and place names are keys of the block beside it, under the banner.

| tool | arguments | result | mirrors | events |
|---|---|---|---|---|
| `egzos_fetch` | `scope?`, `query?`, `kinds?` | `{"banner", "fence", "scope", "chain", "items": [<block>]}` | `GET /v1/fetch`, minting no grant | `context.fetch` |
| `egzos_remember` | `text`, `kind?`, `scope?`, `key?`, `tags?` | `{"ok": true, "id", "status", "auto_title", "scope"}` | `POST /v1/items` (text) | `item.add`; `context.fetch` on a refusal |
| `egzos_inbox` | — | `{"banner", "items": [{"id", "kind", "trust", "thread", "auto_title"}]}` | `GET /v1/inbox` | `context.fetch` |
| `egzos_places` | `under?` | `{"nodes": [<node>]}` | `GET /v1/scopes` (§4.1 item 5) | `context.fetch` |
| `egzos_get` | `id` | `{"banner", "fence", "items": [<block>]}`, one block | `GET /v1/items/{id}` | `context.fetch`; `blob.grant` per §6 |
| `egzos_add_file` | `scope`, `name`, `mime?`, `content_base64`, `key?`, `tags?` | `{"ok": true, "id", "status", "scope", "name", "size", "sha256"}` | §4.4's open, bytes and item, as one step | `upload.put`, `item.add`, `blob.put`; `context.fetch` on a refusal |
| `egzos_upload_open` | `scope`, `name`, `mime`, `size`, `sha256` | `{"ok": true, "upload", "expires_at", "put_url", "put_expires_at"}` | `POST /v1/uploads` | none; `context.fetch` on a refusal |
| `egzos_upload_address` | `upload` | `{"ok": true, "upload", "put_url", "put_expires_at"}` | `POST /v1/uploads/{id}/address` | none; `context.fetch` on a refusal |
| `egzos_upload_finish` | `upload`, `scope?`, `key?`, `tags?` | `{"ok": true, "id", "status", "scope", "name", "size", "sha256"}` | `POST /v1/items` (`kind: artifact`) | `item.add`, `blob.put`; `context.fetch` on a refusal |
| `egzos_upload_discard` | `upload` | `{"ok": true}` | `DELETE /v1/uploads/{id}` | `upload.discard`; `context.fetch` on a refusal |

The first four are **running**. A test per row asserts the row's events when its code lands.

- **`<block>`** is `egzos_fetch`'s running item block, `{"id", "kind", "key", "layer", "trust",
  "shadowed_by", "auto_title", "tags", "content"}`, `content` the fenced body or `inline` text, and
  `trust` the item's `trust.status`. **For an artifact it also names the file**: `"name"` (its
  `content.filename`), `"mime"`, `"size"` and `"sha256"`, all read from the item as stored.
- **`egzos_fetch` mints no grant**, at any scope: a fetch names files and carries no address for
  their bytes, so a broad read puts no credential in a caller's answer. **running**, that it mints
  none.
- **`egzos_get(id)`** is `GET /v1/items/{id}`: `fetch` on the item's scope and the route's serving
  check (an `interactive` principal holding `curate` is shown every covered item but quarantined
  ones, as the route shows it), one block whose `layer` is its own node and `shadowed_by` `null`,
  one `context.fetch`. For an artifact whose bytes do not ride `inline`, it asks Trust for §6's grant
  and, where Trust mints one, carries `"download": {"url", "expires_at"}` beside the block: `url` is
  `grant_url` written on the container's public origin (`identity.md` §2), absent where the
  container names none and the call came over stdio, and never `null`. The banner says that the
  address is good once, for five minutes, at this container only, and is never to be sent
  anywhere else. Refused, it answers `{"banner", "items": []}`.
- **`egzos_places`** is §4.1 item 5's read, **running** (#415).
- **`egzos_add_file`** writes a file small enough to ride in the call's own arguments: §4.4's open,
  bytes and item **as one atomic step**, with every check of each, in the route's order:
  1. `remember`, then the shapes, before any lookup: `name` and `mime` as §4.4 item 1 has them, a
     `mime` left out read as `application/octet-stream`; `content_base64` standard base64 (RFC 4648
     §4) of at most 174,764 characters, checked before it is decoded, that decodes to at most
     131,072 bytes (`file_call_max_bytes`, §4.6); `key` and `tags` as `POST /v1/items` takes them.
     The same bound holds on both transports. At `/mcp` it leaves room for the call's envelope
     inside the 262,144 bytes the door reads of a request (`BODY_MAX_BYTES`).
  2. `remember` on `scope`, which is required, as at `POST /v1/uploads`; otherwise the write's
     §3 answer. A place the caller's terms do not cover is refused, never held.
  3. §4.4 item 1's caps, counted as the route counts them.
  4. The container computes `size` and `sha256` from the decoded bytes; the caller declares
     neither. The upload record, its slot, the staged bytes, `upload.put`, the item, `item.add`, the
     promotion and `blob.put` commit together or not at all, the bytes written last as §4.4 writes
     them: a call that fails leaves no upload, no slot taken and no entry but §4's probe.

  `scope` in the answer is answered as `egzos_remember` answers it: the resolved path to a
  principal holding `fetch`, the caller's own argument otherwise (§4.1 item 8).
- **`egzos_upload_open`, `egzos_upload_finish` and `egzos_upload_discard`** are §4.4's open, item
  and discard for a file of any size up to `blobs.upload_max_bytes`, under the routes' checks and
  answers, each taking only the caller's own upload. **`egzos_upload_address`** asks for a fresh
  address for the caller's own live upload whose bytes have not arrived (§4.4 item 2a). The bytes
  never travel through a tool: the caller sends them to `put_url`, a single-use address the door
  redeems with no bearer (§4.4 item 2a), so a program that holds no bearer value, such as an agent's
  own sandbox under a host that keeps the bearer to itself, can send them. `finish`'s `scope` is
  answered as `egzos_add_file`'s is.

**What stays out:**

- **No human-only act has a tool**: promote, approve, deny, tombstone, a rename, a grant or a
  registration, a confirm (`identity.md` §7).
- **No tool makes a place.** An agent saves into places its person made, and learns their names
  with `egzos_places`. A tool that makes one waits on a rule of its own at `POST /v1/scopes` for a
  `client` principal: a capability for it, a bound on how many it makes, its places shown as its
  own, and a way for the person to remove one (v0.7 §AL).
- **No tool fetches an address a caller chose.** The container never fetches a URL on a caller's
  behalf; the bytes arrive in the call or at this door.

## 5 · Audit coverage

`events.md` §4 invariant 2 binds this door without exception: every read, grant mint and blob pull
is an event, and a door that produces an effect without one is non-conforming. **decided.** The
whole list is given below, under **The whole list**. A test per row asserts the event.

The two invariant-2 exceptions (the owner's read inside an AS session; refresh rotation) are the
AS's, and neither reaches this door: §2 accepts no session. **decided.**

**The whole list** of what the door appends is the tables of §4 and §4.3, §4.2's, §4.4's, §4.5's and
§4.6's clauses, and §2 item 7's `rest.tally` and `authz.release`. §4.7's tools append only what the
routes they mirror append.

**New events.** `item.copy` (a copy is made; `subject` the new item, `details.from` the source),
`gate.pass.confirmed` (a widening move or copy confirmed inline; `audience_delta` and the `step_up`'s
`seq`), §4.3's `identity.grant`, `identity.revoke` and `identity.credential`, and §4.4's `upload.put`
and `upload.discard` are this door's. Like `identity.md`'s, they enter `events.md` §1 and `_types.py`
with the code that appends them, because the conformance tests pin that table to running code. **a1p.**
So do §4.5's `item.rename` and `node.rename`, named meanwhile beneath `events.md` §1's table
(v0.7 §AK).

## 6 · `BlobGrant` — issue and redemption

**Issue. decided** (F5; `context-item.md` §3; `storage.md` §4):

1. When a read in §4 serves an `artifact` item, `inline` carries the bytes only when the size is at
   or below `blobs.inline_max_bytes` **and** `mime` matches `text/*`.
2. Otherwise (**a1p**: whenever `inline` does not carry the bytes) the door asks Trust:
   `Trust.authorize_pull(token, item) -> BlobGrant | silence`. Trust applies the same capability,
   coverage and serving check as a fetch: **artifact download IS fetch**. A minted grant appends
   `blob.grant`. On silence the item is served with no grant.
   Trust is silent, too, on an artifact an agent wrote, until a person promotes it, and on a copy
   of one, until the copy or its source is promoted: an agent's upload stays staged that long,
   unaddressable (`storage.md` §4, §4.4 here). **a1p.** An agent's artifact kept at once (§4.4 item
   3) is promoted at its write, so Trust decides on it as on any artifact, and the sentence before
   binds those written before (v0.7 §AL; **a1p**, not running).
3. Store renders the grant into a URL. It decides nothing, and it never mints on its own authority.
4. The response carries the item with `grant` (the descriptor `{sha256, item, token, expires_at,
   sig}`) and `grant_url` beside it. **a1p**: the two field names.

**The URL. a1p:**

```
/v1/blobs/<sha256>?item=<item id>&token=<Token.id>&expires_at=<UTC ISO-8601>&sig=<sig>
```

`token` is the `Token.id`, an identifier and not a value (`capabilities.md` §5); for a provider
token, its grant's: `user:<sub>`, or `agent:<client_id>:<sub>`, or for a terminal's token
`terminal:<client_id>:<sub>` (v0.7 §AJ), each of which check 5 re-derives from `identity.md` §4's
records. `expires_at` is written to the microsecond, `%Y-%m-%dT%H:%M:%S.%fZ`,
fixed width, so two compare as the times they are; two mints for one token and item within one
tick of the clock are one grant. **a1p.**

**A provider token's id names exactly one `(client_id, sub)` pair. a1p** (GHSA-9g46-638p-v4xm,
#316). The id is a kind followed by each part, joined by `:`. Where no part holds `%` or `:`, the
kind is `user`, `agent` or `terminal` and each part is written as it is: the form above. Every
Supabase-issued
id has that form, since a UUID holds neither character. Where any part holds `%` or `:`, the kind
is `user%`, `agent%` or `terminal%`, and in each part every `%` is written `%25` and every `:` is
written `%3A`: `user%:<sub>`, `agent%:<client_id>:<sub>` or `terminal%:<client_id>:<sub>`, with each
part so escaped. A string is read back only
where its parts, none empty, decode to a pair that writes the same string, so no other spelling
names a pair, and a container `Token`'s id, which holds no `:`, names none. This id is not
attribution: `actor` and `details.for` carry their one part raw (`identity.md` §3a).

**A terminal's token is told apart by its id, and is still its person. a1p** (v0.7 §AJ). What is
issued to a token is issued to that id: a challenge (§4.2 item 3), a `BlobGrant`, an upload (§4.4)
and the per-token bucket (§2) are that terminal's alone, so the browser's token and another
terminal's get `foreign`, or §3's refusal, on them, and a grant minted through a terminal that has
since been ended is refused at check 5. The bucket is each terminal's own on purpose: a terminal
that spends its bucket does not spend its person's browser's, and the cap on live terminals (§4.3)
bounds what one person's tokens spend together. What is counted or kept per person stays per person,
under `user:<sub>`: confirm credentials, the cap on uploads, the audience and `actor`.

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
- The spent record is kept at least a lifetime past the grant's `expires_at`, keyed on the sha256
  of the descriptor's `sig` and never on the `sig` itself: with the other four fields, the `sig` is
  the credential, and a credential is kept only as its hash, as `Token.secret_hash` is
  (`model.py`). **a1p.** Where it persists is decided with the key, below.

**The redemption checks, in this order. decided** for each check, **a1p** for the order:

1. Every query parameter is present and well-formed. Otherwise, §3's refusal.
2. `sig` verifies under the container key, over every descriptor field other than `sig`, compared in
   constant time (`context-item.md` §3).
3. `expires_at` has not passed.
4. The grant has not been spent, and this redemption spends it (single use, above).
5. The named token is live (revocation first) and still holds `fetch` over the item's scope, checked
   now, not at mint. **a1p**: a person's grant or an agent's registration written since the mint is
   not the one the descriptor named, so a caller revoked and granted again since is refused here.
6. The item is still served to that token: not tombstoned, not quarantined, within the serving
   policy. **a1p**: its bytes out of staging (issue, item 2).
7. `<sha256>` in the path equals the descriptor's `sha256` and the item's `content.sha256`.
8. `BlobStore.get(sha256)` returns bytes.

Any failure is §3's refusal, byte-identical, whichever check failed. **decided**
(`capabilities.md` §6 clause 1, `storage.md` §5). Between checks 2 and 3 the door reads §2 item 7's
per-token bucket for the named token; while it holds, the redemption stops there with the same
refusal, so the response never says which bucket or check refused it. **a1p**, the placement.

**On success** the door streams the bytes and appends one `blob.pull` (`subject` the item, `scope`,
`sha256`, `size`), attributed to the token the descriptor names. **decided** (`events.md` §1).

**Redemption stays at the container, on every substrate. a1p** (v0.7 §AF). Check 8 reads the
bytes from the container's own blob store, a directory or an object-store prefix (`storage.md` §4),
and the door streams them itself, under the headers below. `grant_url` is always this door's
`/v1/blobs/` URL: no storage vendor's signed URL, and no object-store location, reaches a client,
in a response body or through a redirect. A vendor's URL is honoured by the vendor, not the
container, so it would bypass the single-use spend and the other checks, those headers and
`blob.pull`'s entry.

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

**The key. a1p** (#165 item 4), for a container its owner runs (`init`: a local or a self-hosted
one). The MAC is HMAC-SHA256 over every descriptor field but `sig`, written as `canonical` JSON
(`events.md` §3), from the standard library.

- **Provisioned at first need**, never at `init`: the first mint or redemption that finds no key
  makes one, 32 bytes from the platform CSPRNG (`capabilities.md` §5), so a container made before
  this clause needs no step to get one. A `grant.key` that is not 32 bytes signs and verifies
  nothing: Trust is silent, every redemption is refused, and reads go on.
- **Stored as `grant.key` in the container's home, 0600**, written as `throttle.key` is (`storage.md`
  §3.1): whole, linked into place, first writer wins. It is never a config key (`container.md` §8)
  and never a row of the container's state, so no read route serves it. **No export or sync
  carries `grant.key` or `throttle.key`**: a place makes its own, and a grant verifies only at the
  place that minted it, where its spent record is. A copy of the whole home carries the key with
  the state, and restoring one brings both back as they stood, so a grant spent since the copy
  reads unspent for what is left of its 300 seconds: after such a restore the owner replaces the
  key (below). Restored without the key, the container makes a new one at first need, which voids
  every grant minted under the old one.
- **Rotated by the owner, from the CLI with the owner `Token`** (`egzos blob rotate`): a new key
  replaces the old one in place, every outstanding grant fails check 2 from then on, and
  `blob.rotate` is appended, `actor` the owner and no key material. Every mint and redemption
  reads the key afresh, so a rotation reaches a running door at its next request. `blob.rotate`
  enters `events.md` §1 and `_types.py` with the code that appends it. **Not running**: until it
  does, the owner deletes `grant.key`, and the next mint or redemption makes a new one, to the same
  effect but with no entry.
- **The spent records persist in the container's state**, as `storage.md` §3.5's `GrantState`, on
  the `ContainerState` substrate as the confirm's challenges are: a spend is one atomic write every
  process serving the container sees. A record is a `sig`'s sha256 and its grant's `expires_at`, no
  secret, kept at least a lifetime past that.
- **A container egzos hosts** keeps its key on its home's volume, and its operator, not its owner,
  replaces it: `identity.md` §4 (v0.7 §AF).

**The lifeboat's same-origin route** redeems the same descriptor under the same checks on its own
host (#138). It is a5-dinghy's and is not an endpoint of this door. The deployment preview limit
#138 asks for is `container.md`'s, open on #138.

## 7 · Browser clients

**CORS is decided: `identity.md` §6.** The door answers CORS for `identity.browser_origins` exactly,
with headers that do not vary with the outcome, and a preflight that does not map the routes. #153's
other four questions were the retired authorization server's and close with it.

## 8 · What this document does not fix

Who may call the door, provider-token verification, grants, the confirm, CORS and MCP over HTTP →
`identity.md`. Copy, the confirm, the human-only routes, grants, agents, credentials, upload,
renaming items and places, and what the door serves → §4–§4.6 here. The MCP tools' shapes → §4.7
here; their transport → `identity.md` §7. The lifeboat →
`spec/design/lifeboat.md`. The grant key of a container egzos hosts →
`identity.md` §4.
The look of any client → its design spec.
