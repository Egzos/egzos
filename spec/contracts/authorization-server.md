# Contract · the container's authorization server

**Status: drafted — awaiting the Phase 0.3 freeze review.** Not law yet. The freeze is declared by
A6 and the Chief personally (build plan 0.3); a1p-planner prepares, it does not declare.

**Derivation — read this before any clause below.** Every other document in `spec/contracts/` was
drafted from a running shape: the walking skeleton executes it and the clause records what it does.
**This one has no running shape.** The skeleton mints the owner token at `init` and has no `login`,
no device-code, no consent screen and no REST surface. Every clause here is therefore
**prose-derived** — a translation of `docs/build/egzos-decisions-v0.6-amendments.txt` **§K**
(container authorization — one authorization server), the `a3-trust` charter, and the interface
rules in `spec/contracts/README.md` — and the 0.3 review is reading translated prose, not observed
behaviour. No clause in this document may be marked **running**, and none is.

Clauses carry one of six markings instead:

- **§K** — carried from a `[DECIDED]` paragraph of §K. The wording may be improved; the decision may
  not be changed here.
- **a1p** — a1p's binding of a §K decision onto the already-drafted contracts, or onto OAuth 2.1
  where §K names a standard and stops. Reviewable, and the review should read it as a proposal.
- **[0.3 · N]** — **decided by the Chief at the Phase 0.3 freeze review**, recorded on #31 (the
  freeze record, 2026-10-03). `N` is that record's item number, so the clause is traceable to the
  line that decided it. Law on the same terms as a §K one: the wording may be improved, the decision
  may not be changed here. Where the record settled a question but left a detail unnamed — a config
  key's spelling, a constant's name, a section's number — a1p chose it, and marked it **a1p** too.
- **open→0.3** — the marking a clause carried while the freeze review had still to settle it. The 0.3
  record answered every one, and **none remains**: each was replaced by its **[0.3 · N]** decision,
  or by `[v1.1]` with the reason the record gave.
- `[v1.1]` — named by the 0.3 review as out of v1.0 and deferred to the contract v1.1 boundary at
  Phase 5 (`spec/contracts/README.md`), reviewed there by the Chief, a1p and A6. Planned, not an
  escalation. **A builder may not implement against one**, for the same reason as `[LEAN]`.
- `[LEAN]` — **§K's own fourth marking**, carried with the same word §K uses. A direction the Chief
  leaned toward and did not decide. It is recorded so a reviewer can see it was considered and is
  **not a decision**: no clause marked `[LEAN]` fixes a shape, and **a builder may not implement
  against one.** Part B carries exactly one (§10.5, the step-up tap riding these endpoints), and
  hardening it would be the one thing this marking exists to prevent.

**Scope of this document.** §§1–9, **Part A** (#67, with #73 and #78): the AS core mechanics — the
client types, the two flows, registration and the redirect allowlist, metadata discovery, the grant
vocabulary, the separation of authorities, and revocation. **Part B** (#61) is §§10–13 *and* **§5.3**:
presence composition, the consent screen and the device-code entry as product surfaces, the
pre-authorization audit surface, and what this document does not fix (§13). §5.3 — the pre-trust
uniform failure — is Part B's, written back in §5 because that is where §5.1's "reject" needed an
answer; §11.0, §11.1, §11.4, §7's closing line and the whole of §12's row (d) route to it, and a
reader mapping the document from this paragraph would otherwise place it in Part A. §5's subsection
numbering (§5.1, §5.2), and likewise §1's and §7's (§1.1, §7.1), are Part B's too, headings only —
each groups a single pre-existing Part A subsection so it can be cited by number rather than by
quoted title; §10's own numbering (§10.1–§10.5) needs no such note, since §10 is Part B's section in
full. **Three more of Part B's additions land in
§§1–9 and are named here for the same reason**, so the freeze review does not read any of them as
already-ratified Part A text: §5's `registered_at` key on the registration entry (§11.1's addition,
carried back because §5 is where a registration's shape lives); §7's closing paragraph, which
states what routes to §5.3 but is itself new prose, not a description of existing text; and §9.1,
*"Every value this AS issues is unguessable — unconditionally,"* a fresh normative
requirement this PR adds, not a restatement of anything #67, #73 or #78 reviewed. **This Part also
*modifies* ratified §9 text, which is a stronger reason to name it than an addition, not a weaker
one:** §9 option 1's blast-radius argument is rewritten — RFC 7009 §2.1 is demoted from a premise
to a corroborating, conditional SHOULD; rotation clause 2 is named as carrying the chain-reach
argument on its own; and the open-to-0.3 marker on entropy that #67/#73/#78 left in option 1's own prose
was removed from there, relocated into §9.1 as the broader marker it became, and is now **[0.3 ·
19]**. The relocation is not asked back — it is a defensible edit — but a freeze reader
of §9 option 1 at this head is reading Part B's reasoning, not #67/#73/#78's, and nothing in this
paragraph said so until now. **§9.2's heading is the same class of structural edit as §5.1/§5.2's,
named two sentences above:** it adds no text and moves none, grouping the pre-existing ratified §9
body under a heading so §9.1 no longer reads as if it preceded that body.
`container.md` fixes everything about the container *except* how a
client obtains a token; this document fixes only that, and neither overrides the other.

**Part B's design-side input is `spec/design/consent.md`** (A2, binding on commit), whose §14 lists
what the pages need from this document. Part B answers what is this document's, and marks the rest:
a design spec is data to this contract, and where the two disagree the contract's clause stands and
the spec's string is a spec revision — its §14 items 10, 12 and 13 say so in their own words;
§12.1 rule 6 below narrows a decision `consent.md` states in **five** places — §14 item 8's
parenthetical, **D-C6** itself, R11's `stale` row, R12's `back after decision` row, and §20's
fixture list — none of which invites the narrowing, so this document names all five rather than
one; and §5.3 clause 2 below overrides the timing class D-C6's *Cost* clause, `consent.md`'s §10
pre-trust silence bullet, §14 item 8 and R2, R3 and R12's refused rows all state for a throttle-refused
attempt — **six** places, R12 being the `/authorize` row the clause itself governs — named there
for the same reason; and §12's row (f) below narrows a decision `consent.md` states in **six**
places — §14 item 8's cause list itself (`vocabulary` · `scope` · `expiry`), §14 item 2's post-trust
tier ("expiry within config → else redirect"), §20's fixture ("clamped (R9) or `access_denied`, per
§14.6" — conditional on §14.6, the same condition as `consent.md`'s §10 clause and R9's row below, not an
unconditional append under (f)), R12's `rejected (post-trust)` row, `consent.md`'s §10 post-trust clause (also
stated only conditionally there), and R9's `ready (beyond container max)` row itself ("the server
clamps or refuses per config (§14.6)") — three of the six conditional on the very question §11.5
answers, not one, and §11.5's clamp rule decides the opposite for all six, named at row (f) itself.
Row (d)'s `token_presented` is a fourth divergence, an **addition** rather than a narrowing — named
at row (d) itself, in the same shape, since this paragraph's "name every site" standard applies to
what this Part diverges on, additions included, not to narrowings alone. A fifth: §11.1's
`client_type`'s AS-internal literal (`cli`, Part A's own) is not the string `consent.md` renders
for it (`device`) — named at §11.1 itself, and named here because this paragraph's standard reaches
every divergence this Part states, not only the ones already listed above it. A sixth, the widest:
§11.0's login-first ordering — substeps 1 and 3 preceding validation — puts row (d) and row (f) out
of an unauthenticated caller's reach except for (d)'s `throttled` and `token_presented` causes, the
direct negation of D-C6's premise that *the post-trust tier is as reachable as the pre-trust one*.
Named at §11.0's own "Consequence recorded, not acted on here" clause; named here for the same
reason as the other five. This document does not revise the premise; **#98 took option (a) [0.3 ·
45]**, so `consent.md` D-C6 is revised to this ordering, A2's edit after the freeze. **[0.3 · 45]**
also records these divergences as authoritative (#100), with A2 adding back-pointers in `consent.md`.
§11.8's `user_code` is **not** a seventh: **[0.3 · 20]** confirms `consent.md` D-C4's eight
characters and adds the alphabet D-C4 left open, so the contract restates a committed Decision
rather than reopening it.

## 1 · One AS, three client types

**The container runs its own OAuth 2.1 authorization server. §K.** Not a delegated one, not a hosted
one: the AS is in-process with the container, and its issuer identity is the container's own origin.
A fork that reimplements the container reimplements this AS, and a UI that speaks to one container
speaks to every other the same way — what §6 is for.

One AS serves three client types, and there are no others in v1.0:

| client type | flow | client kind | secret |
|---|---|---|---|
| **browsers** — the flagship UI, any fork's UI | authorization-code + **PKCE** | public | **none** |
| **CLI / headless** | **device-code** | public | **none** |
| **MCP clients** | per the MCP authorization spec, against the **same** AS | public | **none** |

**§K**, verbatim in substance. MCP client authorization is **Phase 5** (§4); the other two are the
v0.1 surface.

**There is no confidential-client type in v1.0.** All three are public, none holds a secret, and the
AS must not grow a `client_secret_post` path to accommodate a client that would rather send one:
every client in the table is software the user can download and read, and a secret compiled into
downloadable software is not a secret. **a1p** — §K says "public client, no secret" of browsers and
leaves the other two implicit; stating it for all three closes the gap deliberately rather than by
omission. **[0.3 · 15]** — the review confirmed it: **there is no confidential client type in v1.0**,
and none is reserved. A server-side integration that would want one is a v1.1 question asked against
a built AS, not a shape held open in a frozen contract; holding it open would have widened the trust
model for a client that does not exist.

### 1.1 · Device-code in a browser is retired

**§K, and the reason is carried because a rejected alternative a reader can see is worth more than a
clean surface they have to re-litigate.** v0.5 §C had browsers log in by device-code against the
user's container. §K supersedes that wording and retires it: device-code in a browser *"imported the
workaround's costs for nothing, including its code-typing phishing surface."*

The cost named is the one that matters to this contract. The device flow asks a human to read a code
from one surface and type it into another; a page that asks for a code is a page an attacker can
also put up, and the user has no way to tell which container they just authorized. The browser has a
redirect and an origin — it does not need the workaround, and carrying it anyway would have meant
carrying its phishing surface into the one client type that never needed it.

**This does not weaken the device flow where it belongs.** §3 keeps it for CLI and headless clients,
which have no redirect and no origin, and states the mitigations that come with it.

## 2 · Browsers — authorization code + PKCE

**PKCE is mandatory for every public client, with no downgrade path. §K** ("PKCE mandatory for
public clients", a freeze constraint). Since v1.0 has no confidential clients (§1), **PKCE is
mandatory for every client, full stop.**

Stated so an implementation can be tested against it:

- The authorization request MUST carry `code_challenge` and `code_challenge_method`.
- **`S256` is the only supported method.** `plain` is not supported, not advertised in metadata
  (§6), and MUST be rejected where offered. **a1p** — OAuth 2.1 permits only `S256` for anything
  but a client that cannot compute it, and every client in §1's table can.
- The token request MUST carry `code_verifier`, and the AS MUST verify it against the stored
  challenge before issuing anything.
- **A server that accepts a public-client authorization-code exchange without a verifier is
  non-conforming** — not degraded, not legacy-tolerant. There is no configuration key that turns
  this off, and a deployment may not add one.

**The code is bound to the initiating session and is single-use. §K** ("code bound to the
initiating session; an intercepted code is useless"). An authorization code MUST be: redeemable
exactly once; invalidated on the first redemption attempt, successful or not; bound to the
`client_id`, the `redirect_uri` and the `code_challenge` it was issued against, each re-checked at
the token endpoint; and short-lived. **a1p** — §K fixes the property ("an intercepted code is
useless"); the four checks are what make the property true, and a binding that is only partly
enforced does not hold.

**Code lifetime: 60 seconds. [0.3 · 16]** An authorization code MUST expire 60 seconds after it is issued, and the token endpoint MUST
refuse an expired one by the same path as an unknown one (§5.3). The number is a contract value, not a default: there is no config key
that raises it, and a deployment may not add one. OAuth 2.1's guidance is a maximum of ten minutes; a redirect already in flight does
not need them, and an hour-long code is a different security posture from a one-minute one while satisfying every clause above.
`AS_CODE_LIFETIME_SECONDS = 60` in `_types.py` carries it — **a1p**'s naming of a `[0.3]` number.

**Response type.** `code` only. The implicit grant and the resource-owner-password grant do not
exist in this AS, are not advertised, and MUST be rejected. **a1p** — OAuth 2.1 removes both; said
here because "we implement OAuth 2.1" is a claim a reader cannot test and this sentence is.

**TLS.** Every AS endpoint is served over TLS, and this document grants no exception to that.
**a1p** — `serve --tls` is a3-doorman's surface; the requirement is this document's. §5's `http`
allowance is **not** an exception to this clause: it governs a *client's* registered redirect URI —
the client's own listener, on the same machine — and an AS endpoint is not a redirect URI. §5 says
so in its own words, and the two sections are consistent only if read that way.

**The loopback exemption. [0.3 · 9]** The clause above is narrowed in exactly one way: **no TLS is required where the AS
is bound to a loopback interface** — and for **any** user, not only a developer, and not behind a developer-mode flag.
**TLS is required everywhere else.** Of the three candidates weighed — TLS always, this exemption, a developer-mode
exemption — the middle was taken because a certificate story for every laptop container is a requirement the product
cannot meet, and a mode a user can enable is a mode an attacker can talk a user into enabling.

The exemption is a property of the **bind address**, not of a request, a header or a hostname:

1. The AS MAY be served over plain HTTP **only** when its listening socket is bound to `127.0.0.1`, `::1`, or another
   address in `127.0.0.0/8`. Any other bind address — including `0.0.0.0`, `::` and a LAN address — requires TLS, because
   a socket reachable from the network is reachable by something other than the user.
2. The decision is made from the socket the listener holds; a forwarded header (`X-Forwarded-For`, `Forwarded`,
   `X-Forwarded-Proto`) MUST NOT be consulted, being attacker-supplied by construction.
3. A container reached through a tunnel or a reverse proxy is **not** exempt. The listener may be on loopback, but the hop
   the user's bytes actually cross is not, and this clause is about that hop.
4. This exemption governs AS endpoints only. §5's `http` allowance for a *client's* registered loopback redirect URI is a
   separate clause with a separate reason, and neither widens the other.

`serve --tls` (a3-doorman, build plan 5.3) is therefore optional for a loopback bind and mandatory
for every other one; enforcing the refusal is Doorman's, requiring it is this document's.

## 3 · CLI and headless — device code

**Device-code is the CLI's native habitat, unchanged. §K.** A CLI has no redirect URI and no browser
origin to bind to; the device flow's trade is exactly the right one there, and §1's retirement is
about browsers only.

The endpoints are RFC 8628's: a **device authorization endpoint** issuing
`{device_code, user_code, verification_uri, expires_in, interval}`, and
the token endpoint redeeming `urn:ietf:params:oauth:grant-type:device_code`. **a1p** — §K names
"device-code endpoints" as a freeze constraint and does not enumerate them; these are the standard's,
less `verification_uri_complete`, which **[0.3 · 21]** below removes from the set.

Because the flow's weakness is a human typing a code, three mitigations are contract, not advice
(**a1p**):

1. **`user_code` is rate-limited and short-lived.** The AS MUST bound both the polling rate
   (`slow_down` on a too-fast poll) and the number of `user_code` attempts, and MUST expire the code.
   A `user_code` that can be brute-forced is a token anyone can mint.
2. **The verification screen names the client and the grant** in the same `token ls` vocabulary the
   consent screen uses — the user is approving a specific grant, not "a login". The screen itself is
   issue #61's; the requirement that it show the grant is stated here so Part A's flow is not
   specifiable without it.
3. **The pending authorization is bound to the `device_code`**, and approval at the verification
   screen grants *that* request only. A second concurrent request is a second approval.

**`verification_uri_complete` is not issued. [0.3 · 21]** The device authorization response MUST NOT carry the key at all
— not empty, not null, absent — and `/device` MUST ignore a `user_code` query parameter, rendering the empty entry form as
if none had been supplied (§11.8). Including the `user_code` in a URL removes the typing step
and with it some of the phishing surface the browser retirement was about, but it makes the code pasteable into a chat
window: a code a user can forward is a code a user can be asked to forward. The typing step is the mitigation.

The response's key set is therefore `{device_code, user_code, verification_uri, expires_in, interval}`, narrowing §3's RFC
8628 list above by one. Ignoring the query parameter rather than refusing the request is deliberate: a refusal would tell
a prober that the parameter was recognised, and the entry form is what a user arriving at `/device` expects either way.

## 4 · MCP clients — Phase 5, against this same AS

**MCP clients authorize per the MCP authorization spec, against the same AS. §K.** Phase 5, and
named here only to fix the two things that are this document's to fix:

1. **The same AS.** An MCP client does not get a second authorization path, a second token shape or
   a second permission vocabulary. It gets §7's grant, in a `Token` per `capabilities.md` §5, like
   every other client.
2. **Nothing in §§1–3 or §§5–9 may be relaxed to accommodate one.** PKCE stays mandatory, the
   redirect rule stays exact, the grant stays six capabilities and node ids.

The MCP-specific surface — protected-resource metadata (RFC 9728), the `WWW-Authenticate` challenge
that points a client at this AS, and the `resource` parameter that binds a token to one container —
is **contract v1.1 at the Phase 5 boundary** (`spec/contracts/README.md`), reviewed there by the
Chief, a1p and A6. It is **planned, not a Phase 6 escalation**, and it is not drafted here: writing
it now would freeze a surface against a spec version we have not built against.

## 5 · Client registration and the redirect-URI allowlist

**Clients are registered per container config, with a redirect-URI allowlist that accommodates both
`egzos.io` and `localhost` dev origins. §K**, which flags this as *"the one BYOC-specific wrinkle"*
— and it is named as such here: every other clause in this document is the same for a container
running on the user's laptop and a container the flagship hosts. This one is not, because a
self-hosted container must be able to authorize a UI it did not ship.

**The flagship is registered like any other client.** `egzos.io` is not pre-trusted, not implicitly
allowlisted, and holds no capability a fork's UI cannot hold. **a1p**, generalising §K's revocation
sentence ("revocation is `token rm` like any client") from revocation to registration: a flagship
that were privileged at registration would be privileged, and §K's whole shape is that it is not.

**Registration is an owner act.** A client entry `{client_id, client_name, client_type,
redirect_uris, registered_at}` enters container config through an owner-authenticated path. **a1p**
— no source names the verb, and the CLI spelling belongs to a3-doorman, not to this document.
`registered_at` is **§11.1's addition to the four §K names**, recorded here because §5 is where a
reader looks for the entry's shape: the consent screen renders the timestamp, and a field the screen
renders is a field the registry has to carry.

**Registering, amending or removing a client writes `client.register`. [0.3 · 31]** The event carries
`{client_id, op, redirect_uris}`, where `op` is one of `add` · `amend` · `remove`, and it is its own event rather than a member of the
`authz.*` family: this section's exact-match rule is only as strong as the allowlist it compares against, so a change to that
allowlist is a change to the AS's security posture whether or not any token is involved. `redirect_uris` carries the entry's URIs
**after** the change (empty on `remove`), so the log states the allowlist as it then stood rather than the delta that produced it.
**`events.md` §1 carries the row, with `authz.grant` beside it** (#109 PR 2b).

**No open dynamic client registration. [0.3 · 10]** RFC 7591's endpoint is what the MCP authorization spec expects (§4), and an open
registration endpoint on a personal container lets any caller create a client entry — which is the direction that loses. Concretely:

1. **Only the owner registers a client, and the owner-authenticated CLI path is the only one.** §11's consent screen is **not** a
   second registration path, and that is why clauses 1 and 3 agree: §11.1 answers an unregistered `client_id` with §5.3's uniform
   pre-trust failure *and no read at all*, so an unregistered client never reaches a §11 page to be approved into existence, and a
   path that let it would need a pre-registration state reachable **before** §5.3's gate — the registry oracle §5.3 and §7.1 exist to
   close. **a1p**, binding item 10 to the one reading clause 3 and §11.1 leave open; a consent-screen path would be a new decision and
   a new §11 subsection, not an implication of this one.
2. **`registration_endpoint` is not advertised** in the AS metadata (§6): the row is absent from the document, not present-and-empty.
3. No unauthenticated path creates, amends or removes a client entry, and a deployment may not add one.

What this costs is named rather than hidden, and clause 1 makes it larger rather than smaller: an MCP client that expects to
self-register against an unknown AS does not work until the owner registers its `client_id` at the CLI — a config-file-class
act, the owner at a terminal rather than at the browser the client just opened. Whether v1.1 adds an owner-gated RFC 7591
endpoint — the standard's shape, behind the consent screen — is a **`[v1.1]`** question at the Phase 5 contract boundary.

### 5.1 · The matching rule is exact string comparison

**A registered redirect URI matches by exact string comparison. a1p**, from OAuth 2.1, which
requires it — and stated as a contract clause rather than left to "we implement OAuth 2.1", because
a loose redirect rule is the classic AS hole and this is the sentence A6 will read the section for.

Concretely, the AS MUST reject an authorization request whose `redirect_uri` is not byte-identical
to a registered entry, and MUST NOT implement:

- **prefix or path-prefix matching** — `https://egzos.io/cb` must not match `https://egzos.io/cb/x`
  or `https://egzos.io/cbx`;
- **wildcards** in host or path, at any position;
- **query or fragment tolerance** — the query string is part of the comparison, and a registered
  URI carries no fragment;
- **scheme or host normalisation** beyond the URI's own case rules — no "http where https was
  registered", no trailing-slash equivalence.

A registered URI is absolute and `https`, with the loopback exception stated next: for the literal
loopback address, and only there, it relaxes the scheme to `http` and ignores the port.

### 5.2 · The exception: loopback redirect URIs

**A registered loopback redirect URI matches with its port ignored and everything else exact. a1p**,
from RFC 8252 §7.3: a native or dev client binds to an ephemeral port it cannot know at registration
time, so the port is the one component that varies. The exception is bounded to:

- host is the **literal loopback address** — `127.0.0.1` or `[::1]`;
- scheme is `http` — and this relaxes the **redirect URI**, never an AS endpoint: §2 requires TLS on
  every AS endpoint and grants no exception to it;
- **only the port is ignored.** Path, query, scheme and host are compared exactly, as above.

**`localhost` as a hostname is refused. [0.3 · 22]** The loopback host set is closed at the two literal addresses above:
**`127.0.0.1` and `[::1]` only**. A draft of this section permitted `http://localhost:<port>/…` as an exact registered
string with no port exception; the review dropped the hostname form entirely, for RFC 8252 §8.3's own reason — `localhost`
resolves through a name, and a name is something a resolver, a hosts file, a DNS answer or a hostile network can move,
while `127.0.0.1` is not a name and cannot be moved. Testably:

1. **Registration refuses** a `redirect_uri` whose host is `localhost`, in any case spelling, with or without a port. The refusal
   happens at registration (§5, an owner act with the owner present to read it) and not at authorization time, so a developer learns
   of it when they can act on it.
2. **An authorization request** naming a `localhost` `redirect_uri` is a request naming an unregistered URI — clause (1) made sure no
   such entry exists — and takes §5.3's pre-trust uniform failure like any other. A distinct "localhost is refused" response at
   `/authorize` would be a registry oracle of exactly the kind §5.3 closes.
3. **§K's "localhost dev origins"** are still accommodated: a dev client registers `http://127.0.0.1/…` or `http://[::1]/…`, and the
   port exception above means the ephemeral port it binds needs no second registration. A browser follows `http://127.0.0.1:8731/cb`
   exactly as it follows the name, so this costs a string and buys a resolver out of the trust path.

This is the one clause in §5 where **a1p's binding was overruled** rather than confirmed, marked so
that a reader of the freeze record and a reader of this section see the same thing.

**One committed design affordance this revises, named the way §5.3 names its six.** `consent.md` §120's client block gains
*"`· local development origin`"* on a "localhost origin", and its R-row fixture renders `redirects to http://localhost:5173
· local development origin` — a string no conforming container can produce, since clause 1 refuses the entry holding it.
What moves is the bullet's **trigger**, not the bullet: a loopback dev origin is `http://127.0.0.1:<port>` or
`http://[::1]:<port>`, so the affordance keeps a case to fire on and the fixture needs its host replaced. The words and the fixture are A2's and the edit is
`consent.md`'s after the freeze; named so a5-dinghy and A2 do not build the affordance against the refused host.

### 5.3 · The pre-trust uniform failure

§5.1 requires the AS to **reject** a request whose `redirect_uri` is not byte-identical to a
registered entry, and nothing said what a rejection *is*. §11.1's registry-enumeration rule, §11.4's
re-submission handling and §12's whole row (d) each lean on the answer, and each cited a "§2.5" — a
number belonging to `consent.md`'s own validation section, never to a subsection of this document's
§2. It is fixed here, where the commonest cause of it is required.

**Two tiers, and only one may redirect. a1p.** The **redirectable** (post-trust) tier is reached only
by a request naming a registered `client_id`, a `redirect_uri` registered to that client under §5.1,
and §2's PKCE — there the AS has a destination it is entitled to send a browser to, and §7's
converging `access_denied` with §11.6's `{error, state}` govern. Everything before it is
**pre-trust**: an unregistered `redirect_uri` is an attacker's URL as readily as a client's, so the
AS has nowhere to send an error and does not invent one.

**Neither tier is reached at `/authorize` without an interactive session. a1p.** §11.0's substep 3
sends a session-less request to §11.7's `/login` **before** the pre-trust checks below and before
§7's post-trust ones, so this section's responses — the `throttled` cause (substep 2 running ahead of
substep 3) and the `token_presented` cause (decided inside substep 3, §10.2) excepted — are answers to
a caller §10.1 has already authenticated. The redirect is not a member of the response set clause 1
converges, because it is decided before any of these causes has been evaluated.

**What is invariant about that redirect, stated as it is actually true. a1p.** The AS reads nothing,
validates nothing and decides nothing about the request before sending it, so the **status and the
destination are the same for every request that reaches this step, whatever it names**. It is **not**
byte-identical, and this section does not need it to be: §11.7's `continue` carries the pending
authorization request through the login, which is the only way §2's flow resumes at all, so two such
redirects differ by exactly the parameters the caller itself sent and by **nothing the AS knows**. A
caller learns from the redirect only what it already supplied. That ordering is load-bearing for
this section rather than incidental to it. Were
validation to run first, a session-less request naming a registered `(client_id, redirect_uri)` pair
would answer with a redirect and one naming an unregistered `client_id` with the page below — a
registered/unregistered distinguisher needing no credential, and one **clause 1 would not catch**,
since clause 1 converges the failures and that leak is a success. §11.0 fixes the order; this clause
records why this section depends on it.

**A pre-trust failure MUST be a page the AS renders at its own origin, and MUST NOT be a redirect,
under any cause.** Testable as written:

1. **One response.** The same status and a byte-identical body across every cause — an unregistered
   `client_id` (§11.1), a registered client with a mismatched `redirect_uri` (§5.1), a malformed
   request, a missing or `plain` `code_challenge` (§2 admits no downgrade, so a request without PKCE
   is not one this AS recognises and never reaches the redirectable tier — a `plain` value is not a
   malformed one; it is a rejected downgrade, and both it and an absent challenge append under the
   same closed cause, `missing_pkce`, never `malformed`), a decided request
   re-submitted (§11.4), a throttled attempt (§11.0, checked before either tier, so the AS has
   not yet determined which tier the request would have reached), and a caller presenting a bearer
   credential where §11 accepts none (§10.2, refused inside §11.0's substep 3 and likewise before
   either tier). Those seven are exactly row (d). The
   page names no client, echoes no request parameter, and **reveals nothing about which occurred**.
   Five of the seven are answers to an authenticated session by the paragraph above; `throttled` and
   `token_presented` are the two an unauthenticated caller can reach, and both are uniform with the
   other five here for the same reason they are bounded in §12.1 rule 3 — each is decided before the
   AS has determined which tier the request would have reached, so there is nothing tier-specific for
   either to reveal.
2. **One time budget.** The responses converge in time as much as in bytes, as §7 requires of the
   post-trust redirect — a surface that leaks through timing what it withheld in its body is the same
   oracle reached slowly. Specifically: §11.1's keyed read *happens or does not happen* according to
   whether the `client_id` is registered, and that difference MUST NOT be observable. It is the one
   measurement that would otherwise turn §11.1's rule back into the enumeration it prevents. **The
   budget covers §12.1 rule 3's append asymmetry too, and not only that read** — the asymmetry is a
   state, not a cause: every cause appends once when evaluated, the engaging attempt included under
   `throttled`, while **every** cause — `throttled` among them — is counted and not appended for any
   further attempt while the throttle *already holds*, whatever that attempt's cause would otherwise
   have been (§11.0 substep 2, §12.1 rules 3 and 6), and an append to a hash-chained log is not free
   work. That asymmetry is not an
   enumeration oracle in §7's sense, since a caller learning it is throttled has learned only its own
   request rate; it is named because it is a second timing difference in the same response set, and
   an implementer who pads the registry read alone has met this clause's rationale and missed its
   rule. (§11.0's substep-1 replay is the same family seen from the other side: it appends where a
   throttled attempt does not.) **A third difference, larger than the first two: `throttled` and
   `token_presented` are decided at §11.0's substeps 2 and 3, before either validation tier runs, so
   neither performs §11.1's keyed read, §5.1's redirect comparison, the PKCE check or §11.4's
   decided-request match — work every other row (d) cause does some or all of.** Not an enumeration
   oracle either, for the same reason the append asymmetry isn't one: a caller measuring an early
   exit learns only a fact about its own request — that it was throttled, or that it carried a
   credential — never a fact about the registry. Padding the registry read and the append asymmetry
   alone still leaves this difference open, and unlike the first two it gets a weaker disposition:
   **padding this third difference to the full validation budget is a SHOULD, not a MUST** — a narrower,
   justified exception, and the one normative demotion in this clause. Full padding is a real cost,
   since pricing a cheap refusal like a validated request gives up part of what a throttle is for.
   **a1p**, on this clause's own reasoning and on no quotation: the first two differences leak a
   fact about the **registry** — what is registered, which is the owner's — while this one leaks
   only a fact about the **caller's own request**, that it was throttled or that it carried a
   credential, which it already knows. An implementation that pads it fully is conforming, one that
   does not is conforming too, and neither may widen the first two, which stay MUSTs.
   **`capabilities.md` §6 clause 4 states the container-wide timing posture ([0.3 · 42]):** a
   SHOULD everywhere, with this clause's two MUSTs governing this surface. **The first two differences' padding is a named
   spec revision, not a rule this document merely restates.** `consent.md` states the opposite in six places, deliberately and with a reason —
   D-C6's own *Cost* clause (a refused attempt "sits outside D-T8's uniform set" because "a refused
   attempt's timing class is the throttle's own, which is not a secret"), `consent.md`'s §10
   pre-trust silence bullet ("evaluated or refused; only the timing class differs"), §14 item 8's identical sentence,
   and R2, R3 **and R12's** refused rows ("the timing class is the throttle's own"), each a distinct
   site — R12 being the `/authorize` row, the surface this clause itself governs, and so the most
   on-point of the six, not an afterthought to the other five. This clause is the stricter
   of the two on purpose — padding the refusal closes a real, if narrow, timing channel the spec
   accepted rather than closed — and the stricter reading stands, but it is a cost `consent.md`
   argued against by name and no source asks a builder to bear, so it is marked **a1p** rather than
   left to read as a restatement.
3. **No `error`, no `state`** — it is not a redirect, and §11.6 does not reach here.
4. **It appends once per evaluated attempt**, row (d), with the cause in `details` (§12.1 rule 1) —
   **except** the one **state**, not cause, this page's responses can fall into, which clause 2 and
   §12.1 rule 3 already except:
   an attempt refused by a throttle that *already holds* is **counted, not appended**, whatever its
   cause would otherwise have been. Stated here too, rather than left for clause 2 alone to carry,
   because this clause sits under "Testable as written" and an implementer who turns it into an
   assertion without the exception has built exactly the unbounded append D-C6 rejected by name.

The uniformity is owed to the caller and never to the owner's ledger: row (d)'s seven causes are
exactly the distinctions §12 records and this page hides.

**The status code is HTTP 400, and the page carries one copy line. [0.3 · 23]** Every cause in clause 1's set answers `400` with the
same single line of copy, and a status that differed by cause breaks clause 1 whatever the page says. `400` rather than `401` or
`403`: those two are claims about the caller's *credential*, and this page is reached by causes with nothing to do with one — a
malformed request, a mismatched `redirect_uri` — so a status naming authentication would be a weak distinguisher and would invite a
retry with a credential §11 accepts none of. `404` is wrong for the opposite reason: the endpoint exists and is advertised (§6).

**One copy line** means a single sentence, identical across causes, naming neither the client, nor
the request, nor which check failed. `consent.md` renders the words and the words are a spec
revision there; the convergence — one status, one body, byte-identical — is this document's.

## 6 · AS metadata discovery

**AS metadata discovery is part of the frozen surface. §K** (a named Phase 0.2 freeze constraint).
The reason §K gives is the one that makes it a contract rather than a convenience: *"any UI, ours or
a fork's, authenticates to a container the same way."* A UI cannot be written against "the egzos
container" as a category unless every container announces itself identically — the metadata document
**is** the interoperability surface, and the rest of this document is only reachable through it.

**Endpoint:** `/.well-known/oauth-authorization-server`, at the container's own origin, served
**unauthenticated** over TLS (§2, whose **[0.3 · 9]** loopback clause governs the one exemption). **a1p** — RFC 8414's location; §K
names the requirement and not the path.

Unauthenticated is deliberate and is not a leak: the document describes the *protocol* a container
speaks, identically for every container, and reveals nothing about what is inside one. Nothing
container-specific — no node ids, no client names, no owner identity — may be added to it.

**The fields, enumerated. a1p** — the set is what §§1–3, §5 and §7 require a client to know:

| field | value |
|---|---|
| `issuer` | the container's own origin; every token's `iss` |
| `authorization_endpoint` | §2 |
| `token_endpoint` | §2, §3 |
| `device_authorization_endpoint` | §3 |
| `revocation_endpoint` | §9 — **[0.3 · 11]**: the endpoint exists, so the row is unconditional |
| `response_types_supported` | `["code"]` — and nothing else, ever (§2) |
| `grant_types_supported` | `["authorization_code", "refresh_token", "urn:ietf:params:oauth:grant-type:device_code"]` |
| `code_challenge_methods_supported` | `["S256"]` — `plain` is never advertised (§2) |
| `token_endpoint_auth_methods_supported` | `["none"]` — every client is public (§1) |
| `scopes_supported` | the six capability names (§7) |

**The metadata is a conformance surface, not a description.** A container MUST NOT advertise a
method, grant or endpoint it does not implement, and MUST NOT implement one it does not advertise —
a fork's UI reads this document *through* the metadata, so a mismatch is a conformance failure and
not a documentation bug.

**All ten rows are unconditional, and the set is closed. [0.3 · 10, 11]** A draft of this section carried eleven rows, two
of them conditional on questions the review has now closed in opposite directions:

- **`revocation_endpoint` is advertised, always.** Item 11 decided that the AS exposes an RFC 7009 endpoint (§9), so its
  existence is no longer a question and the row is like any other: a container that omits it is non-conforming.
- **`registration_endpoint` is not a row at all.** Item 10 decided there is no open dynamic client registration (§5), and
  the clause above forbids advertising an endpoint a container does not implement. The field is **absent from the
  document**, not present-and-null: a null would tell a reader the container considered the question, and RFC 8414 omits
  an unsupported optional field.

A container therefore emits exactly these ten fields, no more and no fewer, so the "MUST NOT advertise what it does not
implement, MUST NOT implement what it does not advertise" clause above runs in both directions with no exception to carry.
`AS_METADATA_FIELDS` in `src/egzos/_types.py` is the whole vocabulary of ten, and `AS_METADATA_CONDITIONAL_FIELDS`, which
named the two exceptions, is removed: an empty constant would be a place for a later field to be quietly added.

**`scopes_supported` does not advertise the `node:` form. [0.3 · 28]** It carries the six capability names from §7 and
nothing else; clients learn the node-scope form from this contract, which is where an interoperability surface's
*vocabulary* belongs. Advertising the bare prefix would reveal nothing on its own — the argument for it — but it would put
a container-specific *form* in the one document whose rule is that nothing container-specific appears there, and the step
from "the prefix is advertised" to "an example is advertised" is short.

## 7 · The grant is six capabilities and node ids — nothing else

**The grant an AS token carries is expressed only in the frozen capability vocabulary. §K.** No scope
string that is not a node id, no capability that is not one of the six. **The AS must not become a
second, parallel permission system** — the one failure mode that would make every clause in
`capabilities.md` and `container.md` advisory.

The marking is **§K** and not **a1p** because the rule is carried, not proposed: §K's consent-screen
paragraph decides that *"authorizing the flagship is indistinguishable from minting any other client
token because it IS one"*, and if an AS token **is** a client token then its grant is a client token's
grant, which `capabilities.md` fixes at six capabilities and node ids. There is no room left for a
second vocabulary to be decided in. The *phrasing* above — the "second, parallel permission system"
framing and the failure mode it names — is a1p's, and a reviewer may reword it; the rule underneath it
is §K's and may not be changed here. Everything below in this section that binds the rule onto OAuth's
`scope` parameter is marked **a1p** separately, because that part is a proposal.

A token minted through the AS **is** a `Token` per `capabilities.md` §5. Same fields, same six
capabilities, same node-id scopes, same coverage computed down the path at check time, same
revocation. §K says it of the flagship — *"authorizing the flagship is indistinguishable from
minting any other client token because it IS one"* — and it is true of every client.

**The binding onto OAuth's `scope` parameter. a1p** — §K fixes the rule and not the spelling; this
is the spelling, and the freeze may change it as long as the rule survives. A `scope` value is a
space-delimited set drawn from exactly two forms:

- **a bare capability name** — one of `fetch remember organize publish curate admin`;
- **`node:<node-id>`** — the `scope`-parameter spelling *of* a `Token.scopes` entry, not the entry
  itself: the AS strips the prefix when it mints (consequence 3). `node:*` is the whole container.

The AS expands the request into `{capabilities, scopes}` on the minted token. Anything else in the
`scope` value is refused; the request is **not** silently narrowed to the part that parsed.

**Pinned**, in `src/egzos/_types.py` and `tests/_types/test_as_shapes.py`: the bare-name half of the
vocabulary is exactly `CAPABILITIES` and the node form is exactly `AS_SCOPE_NODE_PREFIX`
(`AS_SCOPE_ALL_NODES` for `node:*`) — **two forms, no third** — and the collision below is exactly
one word, `set(ROLE_BUNDLES) & set(CAPABILITIES) == {"admin"}`. There is no constant for a third
form because there is no third form; a seventh capability or a sixth bundle named after a capability
breaks a test rather than an implementation.

Three consequences that are contract, not style:

1. **Role bundles are not scope strings.** `reader`, `contributor`, `operator` and `curator` never
   appear in a `scope` value: a bundle is expanded at mint time and the token carries capabilities
   (`capabilities.md` §2), so a bundle in a grant would be a second vocabulary that can drift.
   A consent screen may *display* a bundle's name (#61); the grant does not carry it.
2. **`admin` in a scope value is the capability, never the bundle.** The two vocabularies collide on
   exactly this word — `admin` is a capability and `admin` is the all-six bundle — and a reader who
   guesses wrong grants five capabilities they did not mean to. Stated here so no implementation
   resolves the collision the other way.
3. **`node:*` is the owner's grant, and the prefix does not survive the mint.** `capabilities.md` §5
   says `["*"]` is the owner's token; a client asking for `node:*` is asking for the whole container,
   and the consent screen must render it as that (#61). The `node:` prefix exists only in the
   `scope` parameter — **`Token.scopes` carries bare node ids**, so `node:*` in a request becomes
   `["*"]` on the token, and a token that stored the prefixed form would not match
   `capabilities.md` §5 or the coverage check that reads it.

### 7.1 · The AS is not an enumeration oracle

**A `node:<id>` the requester may not reach and a `node:<id>` that does not exist MUST produce the
same result. a1p** — this is `capabilities.md` §6 and `container.md` §4 invariant 3 applied at the
authorization endpoint, and it needs saying because OAuth's error vocabulary invites the opposite:
an AS that answers `invalid_scope` for an unknown node and `access_denied` for a forbidden one has
handed any registered client a way to enumerate the owner's container through error shapes, without
ever holding a token.

The rule, stated so it is testable:

- **Unknown node id, unreachable node id, owner declined** → the same error, the same shape, in the
  same time budget. `access_denied` is the one to use.
- `invalid_scope` is reserved for a scope value that is **malformed or not one of the six capability
  names** — a fact about the vocabulary in this document, identical for every container, revealing
  nothing about any of them. §12's row (f) carries both halves of this reservation under its one
  closed cause `vocabulary`, never split into two.

This applies to the device flow (§3) identically: a rejected device authorization reveals no more
than a rejected redirect does.

**This subsection is the post-trust half only** — it converges the error *in a redirect*, which the
AS may send only once the request has earned one. The pre-trust half, where there is no redirect to
converge, is **§5.3**; §11.0 fixes that the throttle runs before both.

## 8 · Two authorities, deliberately separate

**§K, ratifying R2.** Two authorities exist and they do not merge:

- **the `egzos.io` session** (Firebase-as-identity) proves **subscription**;
- **the container token** proves **authorization**, is obtained via PKCE against the user's **own**
  container (§2), and is held browser-side.

**The container token is never derived from the `egzos.io` session.** There is no token exchange, no
assertion grant, no path by which holding a flagship session produces container access: the only way
to a container token is §2's or §3's flow against that container. **a1p** — §K fixes the separation;
this sentence is what makes it checkable, and it is the clause that keeps a compromise of the
flagship's identity provider from being a compromise of every container.

The separation is worth the cost in both directions: a lapsed subscription must not revoke a user's
access to their own data, and a revoked container token must not require a flagship account to
restore. The container is the home; the subscription is a service.

**Double login is the posture, and in v1.0 it is the only one. §K, narrowed by [0.3 · 8].** §K records that a deployment **MAY**
configure its container to trust `egzos.io`, or any IdP, as OIDC identity to collapse the two logins into one — never the default. The
review took the second of the two dispositions it was offered and **scoped the collapse out of v1.0 explicitly**:

- **There is no IdP collapse in v1.0. `[v1.1]`.** No container may be configured to accept an external OIDC identity as its
  own, there is no config key that does so, and a deployment may not add one. A container that collapses the two authorities
  is **non-conforming** — not misconfigured: the configuration that would make it conforming does not exist in v1.0.
- **Double login is therefore unconditional here.** §K's `MAY` is preserved above as the record of what was decided at §K and
  is **not** in force in v1.0.
- **v1.0's browser identity for the container is a container secret. [0.3 · 7]**, to be stated at §11.7 where the login lives
  — which is why declining costs the product nothing it has today.

The collapse was named by §K and never designed by it, and what is missing is not a detail: which IdP claims map to which container
identity, what happens to live tokens when the trust is withdrawn, and what an IdP compromise then reaches. Deferring is the cheaper
direction to be wrong in: v1.1 can add it behind the owner's own configuration without breaking any token this contract issues,
while a v1.0 that shipped it could not take it back. **The separation above is not deferred with it**: no token exchange, no
assertion grant, no path from a flagship session to container access, each in force in v1.0. The collapse would have been an
owner-configured exception to the *login*, never to the authority boundary.

## 9 · Issuance, revocation, rotation and expiry

**A token the AS issues writes `token.mint` (`events.md` §1), like any other mint. a1p** — §7 makes
an AS token a `Token` per `capabilities.md` §5, and a mint is a mint whether it came from
`token mint`, §2's code exchange or §3's device redemption. The event already exists, so this needs
no freeze decision; it is stated because an implementation conforming to this document alone would
otherwise complete an exchange and leave no trace in the chain.

### 9.1 · Every value this AS issues is unguessable — unconditionally

**Every credential value the AS mints — an access token, a refresh token, an authorization code, a
`device_code`, a `user_code` — is generated by a cryptographically secure random source, and no
value is derived from a counter, a timestamp, a client id, an owner identity or any other
predictable input. a1p.** Stated here, at the top of the section, and not inside any clause below,
because **a guessable value is a forged grant under every outcome this section can have.** A bearer
token *is* its value: whoever can produce the value holds the grant, whichever way §9.2's revocation
question went — and **[0.3 · 11]** took the endpoint, which makes the dependency below a live one.
§3 mitigation 1 already does this work for the `user_code`, where the value is
short by design and a human types it; the clause above says the same thing about every other value
the AS issues, where nothing about the surface makes the requirement visible.

§9.2's endpoint **additionally** depends on it — an endpoint that accepts a token value from an
unauthenticated caller is bounded by that value's entropy and by nothing else, as the clause says in
its own words — but the dependency runs one way only: it is not the whole of this
requirement, because rotation clause 2 below hands the same reach to the same holder at the token
endpoint, and §2's code binding, §3's device codes and every access token already rest on it.

**The floor is 128 bits, and this clause carries it. [0.3 · 19]** Every value this AS issues carries **at least 128 bits of entropy
from the platform CSPRNG**. The number and the source are both normative: 128 bits of a weak generator is not 128 bits of entropy,
which is why §9.1's opening clause names the source and this one names the amount. **This is the citable clause, here, today.**

It is **not** the whole requirement: `token mint` is the owner's own path, so a floor binding only
the AS leaves the same forgeable value reachable through another verb. **`capabilities.md` §5
carries the container-wide clause** (#109 PR 2b), `token mint` included; nothing below defers to it.

Two readings the number does not have:

1. **It is a floor, not a size.** A format carrying structure around a random core (a prefix, a checksum) conforms as long
   as that core meets the floor: the entropy is what an attacker must search, never what the string's length suggests.
2. **`user_code` is the one exception, bounded differently.** [0.3 · 20] fixes it at eight characters from a 20-consonant
   alphabet — far under this floor, deliberately, because a human types it. Its security comes from §3 mitigation 1's
   attempt bound and expiry instead, as §11.8 states. No other value may borrow that argument.

`Token.id` is a token's *identifier*, not its value, and this clause governs values. **[0.3 · 11]**'s
owner path keys on the identifier precisely because that is the half safe to render on a page.

### 9.2 · Revocation, rotation and expiry

**Revocation is `token rm`, like any other client. §K.** The flagship's token is removed by the same
verb, from the same list, with the same effect as a script's. There is no "sign out of egzos.io"
that is also a container revocation, and no container revocation that requires the flagship.

A revoked token is `capabilities.md` §5's: it holds **no** capabilities, and revocation is checked
**before** the capability set. `token.revoke` is written (`events.md` §1). **a1p** — the AS adds no
second revocation semantics, which is the point.

**The AS exposes an RFC 7009 revocation endpoint, and the owner additionally revokes by `Token.id`. [0.3 · 11]** The
review took **both** halves: clause 1 below as written, **plus** an owner path on the container's own pages. **A browser or
an MCP client cannot run `token rm`**, so an HTTP endpoint is the only revocation path two of §1's three client types have, and
an endpoint bounded by a token's value alone is no path on which an owner should revoke *someone else's* live token:

- **The client path** (clause 1) lets a holder revoke the token it holds, with the silence rule and the `client_id` comparison
  as clause 1 states them, bounded by §9.1's entropy and nothing else.
- **The owner path** lets the owner revoke **any** token in `token ls` by its `Token.id`, from the container's pages, inside
  an authenticated interactive session — reaching tokens whose values the owner does not have. `Token.id` is safe to render
  for §9.1's closing reason: it is the identifier, not the value, so a page listing it hands a reader no credential.

**The owner path adds `revoke` to the closed `surface` vocabulary**: §12.1 rule 5 and `AS_THROTTLE_SURFACES` in `_types.py`
both carry it, beside `login` · `device` · `authorize` · `tap`, and §11.9 states the page. It also adds **an entry on its refusal path**: an attempt
naming a `Token.id` that does not exist, or one the session may not reach, is refused uniformly — §7.1 applied to an identifier
rather than a scope, since a page answering "no such token" differently from "not yours" would enumerate tokens. The throttle
keyed on `revoke` bounds a walk of the id space.

Where the two paths meet: a token revoked by either is `capabilities.md` §5's revoked token, holds no capabilities, and writes
one `token.revoke` (**[0.3 · 30]**, carrying the refresh-family id) — the transport does not change the semantics, which is the
point of stating revocation as `token rm`'s in the first place.

1. **The endpoint, per RFC 7009 — in force, not an option.** `POST` to `revocation_endpoint` with `token` and an
   optional `token_type_hint`, over TLS (§2), with no client authentication because no client has a
   secret (§1, §6's `["none"]`). Two clauses would have to come with it, and both are this
   document's rather than the RFC's:
   - **The silence rule.** The endpoint returns **200 for an unknown, malformed or already-revoked
     token** — the same status, shape and time budget as for a token it really did revoke. RFC 7009
     asks for 200 on an invalid token; §7.1's "the AS is not an enumeration oracle" is why it is a
     MUST here, because an endpoint that answered differently would let any caller test whether a
     token value exists without holding one.
   - **Whether a client may revoke a token not issued to it. [0.3 · 11]** takes a1p's reading
     below as written, *including* its own statement of what the comparison is not: the AS compares the presented token's `client` (`capabilities.md` §5) against
     the presenting `client_id` and, when they differ, revokes nothing and returns the *same* 200 —
     a refusal indistinguishable from a success.

     **Said plainly, because the comparison reads stronger than it is: it is not a boundary.** No
     client on this AS authenticates — §1 has three public client types and §6 advertises
     `["none"]` — so `client_id` is a string the caller chooses, and any caller can send another
     client's. **With no client authentication available, this endpoint is bounded by the entropy
     of the token value alone:** whoever can produce a token's value can revoke it, whatever
     `client_id` they send with it. The comparison is worth keeping as defence-in-depth — it makes
     an accidental cross-client revocation impossible and keeps the chain's actor truthful — and it
     must not be recorded anywhere as the thing that stops one client from revoking another's
     token, because it does not.

     **What a real bound would require**, which the review considered and did not take: proof that
     the caller holds the *grant*, not the string. Three shapes, none of them free — a
     confidential client, which §1 forbids in v1.0 and which downloadable software cannot be
     anyway; a **sender-constrained** token (DPoP, RFC 9449), which binds revocation to a key the
     caller proves per request and is therefore a change to every token this AS issues rather than
     to this endpoint — a `[v1.1]` question if one is ever wanted, not a v1.0 one; or no endpoint
     at all, which was option 3 and which the owner path above is what made unnecessary to accept.
     The cost of entropy-only is accepted knowingly and is stated as what it is: a token value that leaks can be revoked by
     whoever holds it. For a leaked **access** token that is a denial of service against *that*
     token and nothing wider — a revocation cannot widen a grant, reveal whether the value was
     live (the silence rule above), or reach a token the value does not name. For a leaked
     **refresh** token the blast radius is **the whole grant chain**, and not because of this
     endpoint: **rotation clause 2 below already gives the holder that reach at the token
     endpoint** — replaying a refresh value there *is* reuse, and reuse revokes the entire chain
     descended from that grant. That clause is this document's own MUST, and it carries the
     chain-reach argument by itself. RFC 7009 §2.1 points the same way and is **a conditional
     SHOULD, not a premise**: it recommends that revoking a refresh token invalidate the access
     tokens issued under the same grant, and it is conditioned on an AS that supports revoking
     those tokens at all — which is the question option 1 exists to settle, so citing it as a
     given would be circular. It corroborates; nothing above rests on it. The endpoint was weighed
     against the chain rotation clause 2 already reaches, which it adds nothing to, and not against
     a single token — and taken on that basis.

     The entropy this bound rests on is required **unconditionally**, by §9.1 above,
     and it is not this endpoint's to carry: whoever can produce a token's value holds the grant
     whatever this section decides. The endpoint depends on that requirement; the requirement does
     not depend on the endpoint.
2. **The owner path, by `Token.id`.** On the container's pages, inside an authenticated interactive
   session, over the `revoke` surface named above. It reaches every token in `token ls`, needs no
   token value, and refuses uniformly for an unknown and an unreachable identifier alike. `token rm`
   is the same act on the CLI.

**Both paths are in force, and `revocation_endpoint` is an unconditional row in §6** (**[0.3 · 11]**, with §6's own
clause): a container advertising the endpoint now advertises something this contract specifies, which is what §6's
conformance rule requires. `token rm` remains the revocation *semantics* under both transports — a revoked token is
`capabilities.md` §5's, and `token.revoke` is written once, whichever path reached it. **What was given up:** a client
holding only a token's value can revoke that token, and the `client_id` it sends is not what stops it reaching further —
§9.1's entropy is. The alternative was leaving browsers and MCP clients with no revocation path.

**Refresh tokens rotate. §K.** Made testable (**a1p**, from OAuth 2.1's rotation guidance):

1. A refresh token is **single-use**. Redeeming it issues a new access token **and** a new refresh
   token, and invalidates the one presented.
2. **Reuse is detection, not an error.** Presenting an already-redeemed refresh token means either a
   race or a theft, and the AS cannot tell which — so it revokes **the entire chain descended from
   that grant**, access and refresh alike, and writes `token.revoke`. A rotation scheme that merely
   refuses the reused token leaves the thief's copy live, which is the failure the rotation was for.
3. Rotation does not widen a grant. The new token carries the same capabilities and scopes; a
   refresh that could add either would be §7's second permission system arriving through the back
   door.

### 9.3 · The AS's seven effects, each with its event

**[0.3 · 29, 30, 31, 32]**, settling #68. `events.md` §1 closes its vocabulary by construction — *"an appended event whose
name is not in this list MUST be rejected"* — and §4 invariant 2 closes the other side: *"a surface that produces an
effect without a corresponding event is non-conforming."* The AS produces **seven** effects, enumerated so a reader can
count them rather than trust the number, each now with its disposition:

| # | effect | event |
|---|---|---|
| 1 | a token is **issued** (§2, §3) | `token.mint`, carrying the refresh-family id |
| 2 | a token is **revoked** (§9.2, either path) | `token.revoke`, carrying the refresh-family id |
| 3 | the owner **grants** consent (§2, §3) | `authz.grant`, `decision: granted` |
| 4 | the owner **denies** it (§11.4) | `authz.grant`, `decision: denied` |
| 5 | a refresh token is **rotated** (§9.2) | **none** — see below |
| 6 | a client is **registered**, amended or removed (§5) | `client.register` |
| 7 | a **device authorization is requested** (§3) | **none** — *partly* covered by 3/4 plus §12's redemption row; see below |

**`events.md` carries all three of this table's new dispositions** (#109 PR 2b): `authz.grant` (rows 3, 4) and
`client.register` (row 6) are among §1's names, **decided, not running**, and §4 invariant 2 names row 5's rotation as an
exception (**[0.3 · 29]**, **[0.3 · 31]**, **[0.3 · 30]**).

**`authz.grant {client_id, decision, scopes, capabilities}`. [0.3 · 29]** One row with a closed `decision` of `granted` ·
`denied`, not an `authz.grant`/`authz.deny` pair: the two halves carry identical fields and differ only in outcome, and
splitting them would make the *absence* of a deny row a signal in a log an owner reads by name. `scopes` and
`capabilities` record what was *requested*, including on a deny; where a request **is** decided and denied, §7.1's
convergence makes row 4 the only place that attempt is visible at all.

**Rows 3 and 4 fire on an owner's decision and on nothing else. a1p**, bounding item 29 rather than widening it: the row-4
cell read "or the request is rejected", which admitted a broader rule the rest of this document contradicts. Rows 3/4 append
only where §11.4's deciding act happens — an owner answering a rendered screen inside a session §10.1 has authenticated. Four
exclusions: **(i) §5.3's pre-trust set is not covered:** no row (d) cause is a decision; each appends under
§12's row (d) with its cause in `details`. A session-less `/authorize` is the clearest — §11.0 substep 3 answers it with a 303
to `/login` having read, validated and decided nothing, so no denial exists to record and no `client_id` has been looked at.
**(ii) A throttled attempt is not covered:** refused while a throttle already holds, it is counted and not appended at all
(§12.1 rule 3). **(iii) §12's row (f) is not covered and is not folded in:** a post-trust rejection — outcome `rejected`,
closed causes `vocabulary` · `scope`, pinned as `AS_AUTHORIZE_POSTTRUST_CAUSES` — is refused against §7's vocabulary before
the owner is asked, so it keeps its own row, its own outcome and **both causes**; `authz.grant`'s field set is deliberately
**not** widened, having no field a cause fits. Row (f)'s own event is `authz.reject` (§12, **[0.3 · 33]**). **(iv) §12's
own rows are not this table's:** the invariant-2 read exception, the rendered screen (row (g), abandoned or not) and the
session-less 303's throttle accounting are §12's (**[0.3 · 36, 37, 38]**). A session-less sweep gets no row 4 under (i).

**Rotation emits no event. [0.3 · 30]** Clause 2 above revokes a reused chain and writes `token.revoke`; a successful rotation writes
`token.mint` for the token it issues. What is added instead of a `token.rotate` row is that **both carry the refresh-family id**, so a
reuse-detection cascade revokes a chain the log can name and a reader can follow a family from first mint to last revocation. A
`token.rotate` row was rejected for what it would turn the chain into: a rotation fires on a schedule the client picks, so a log
carrying one is a session log, and an audit chain that fills with routine machine traffic is one an owner stops reading. The silence
is a decision, and `events.md` §4 invariant 2 names it as an exception, so it is not a conformance failure.

**`client.register {client_id, op, redirect_uris}`. [0.3 · 31]** Specified at §5, named here so the count closes. Its own
event rather than a member of the `authz.*` family: a registration produces no token and concerns no grant, and what it
writes is the state §5.1's exact-match rule compares against.

**A device authorization request gets no separate event. [0.3 · 32]** Effect 7 is covered wherever it goes anywhere: §12's
device-redemption row appends when a `user_code` is redeemed, rows 3/4 when the owner decides. The **initiated-then-abandoned**
request — a `device_code` and `user_code` minted and never redeemed, by a caller holding no token — is **not** covered, is accepted
knowingly, and is why row 7 reads *partly*. **The reason is what that state is, not what the throttle does. a1p**: the pending record
is bounded (§3 mitigation 1 expires it), reaches nothing, and becomes visible the moment it is used, at §12's redemption row — so
there is no effect to miss until a redemption, and a redemption appends. **An earlier draft argued from §12.1's throttle and had the
mechanism backwards:** rule 3 and §11.0 substep 2 bound the *append* more tightly than the request, since attempts refused while a
throttle holds are counted and not appended — which is how §12 keeps rows (a), (b), (d) and (e) for unauthenticated callers at all.
The throttle is an argument *for* appending, so this silence rests on the bounded, unreaching state alone.

**Default access-token lifetime: 1 hour, and never null. [0.3 · 17]** An AS-issued access token **always** carries a non-null
`expires_at`, defaulting to **1 hour** from issuance. `capabilities.md` §5 permits `expires_at: null`, which is right for a
long-lived script token an owner mints deliberately and wrong for a token handed to a public client by a flow; **the null case
stays available to `token mint` only**. There is no AS path, parameter or config key by which a client obtains a non-expiring
token, and a deployment may not add one. `AS_ACCESS_TOKEN_LIFETIME_SECONDS = 3600` in `_types.py` carries the default —
**a1p**'s naming of a `[0.3]` number. Grant expiry, the longer clock over this one, is **[0.3 · 18]** at §11.5.

## 10 · Presence composition — where `principal: interactive` comes from

**The interactive login PKCE performs against the container is where `principal: interactive` is
established for browser sessions. §K**, verbatim. Read precisely, because the sentence compresses
three different things and only the first of them is the establishing act:

1. **The login.** The human proves identity to the container at the container's own origin (§11).
   This establishes an **interactive session** — the claim *a human is present, at this container,
   now*.
2. **The authorization.** §2's flow renders the grant to that session and carries the owner's
   decision to the client. PKCE protects the *code*; it proves nothing about a human, and no part of
   a `code_verifier` is evidence of presence.
3. **The mint.** The token §2 issues may carry `principal: interactive`. This is the composition step
   and the one that needs bounding, because a token outlives the session that authorized it and is
   handed to software.

### 10.1 · A session is not a token

**The interactive session and an interactive-principal `Token` are different objects, and this
document keeps them apart. a1p** — `capabilities.md` §3 says the principal is *"established, for
browser sessions"*, and a reader who collapses the two ends up with a presence claim in `token ls`
and a bearer credential in a cookie. The session:

- is **not** a `Token`, has no `Token.id`, and does not appear in `token ls`;
- is **not** a bearer credential: it is never accepted at the REST surface, at the token endpoint, or
  anywhere a `Token` is accepted, and it carries no `capabilities` or `scopes` of its own;
- is scoped to the container's **own origin** — the pages of §11 and nothing else;
- ends — at **30 minutes idle or 8 hours absolute**, whichever comes first (§10.2, **[0.3 · 13]**) —
  and it is not renewable by a refresh token.

### 10.2 · `/authorize` is an owner act, and no token can take it

**An authorization decision is taken only by an interactive session — never by a bearer token,
whatever it holds. a1p.** `/authorize` MUST refuse to render, and MUST refuse a decision, for a
caller presenting a `Token` instead of an interactive session; a caller presenting no credential and
holding no session is sent to §11's login first.

**The refusal has a response and an entry, and they are named here rather than left to the reader.
a1p.** A request to `/authorize` that presents a bearer credential — in an `Authorization` header or
any other position the surface would have to look at — while holding no interactive session is
refused with **§5.3's uniform page**, and appends once as **§12 row (d) with cause
`token_presented`**. A request holding both a session and a credential is decided on the session
and never reaches this refusal — §11.0 substep 3 branches on session presence before the credential
is looked at, so `token_presented` fires only for a credential presented *in place of* a session,
never beside one. Two bounds on that check, both load-bearing:

- **The AS MUST NOT validate the presented credential.** No `Token` lookup, no signature check, no
  expiry check: the refusal turns on the credential's *presence*, never on its validity. A check that
  validated would be a read (a timing difference §5.3 clause 2 would then have to cover) and would
  make a live `Token` distinguishable from a forged one at an endpoint that accepts neither.
- **It is refused, not redirected.** Sending it to `/login` would answer a caller that supplied
  something with the same response as a caller that supplied nothing, which is the only case where
  the two are worth telling apart *in the owner's ledger* — §10.2's grant-factory concern is precisely
  software trying to spend a token on an owner act, and an entry is the whole of what the owner gets.
  The caller learns nothing either way: §5.3's page is uniform, and the distinction it can observe is
  between two things it sent itself.

`token_presented` is therefore the second row-(d) cause an unauthenticated caller can reach, beside
`throttled`, and §12.1 rule 3 is written on both. It is bounded by the same counter: substep 2 runs
ahead of substep 3, so a sweep presenting credentials is throttled like any other.

**"First" is an ordering, and §11.0's substep 3 is where it is fixed.** The session check runs after
§11.0's throttle and **before either validation tier** — before §5.3's pre-trust checks and before
§7's post-trust ones. A session-less `/authorize` request that survives the counter and presents no
credential is therefore a 303 to §11.7's `/login` and nothing else: no registry read and no decision
about the request, so the **status and the destination** are the same whatever `client_id` and
`redirect_uri` it names. What varies between two such redirects is §11.7's `continue`, which carries
the pending request so §2's flow can resume after the login — so what is invariant is that **nothing
the AS knows** varies in the redirect, not that its bytes do not. Read the reasoning there, not here;
the consequence to carry into §12 is that rows (d) and (f) are out of an unauthenticated caller's
reach except for (d)'s `throttled` and `token_presented` causes, which is what §12.1 rule 3 is
written on.

This is the clause that keeps §7 honest. Without it `admin` becomes a **grant factory**: a client
holding all six capabilities could walk §2's flow and mint a second client a token, and the
`token.mint` chain would record a grant no human ever saw. `capabilities.md` §4's rule that *no
capability reaches a human-only act, including `admin`* is the same rule; this states it at the one
endpoint where the act is "hand out authority."

**The session this endpoint decides on has two clocks: 30 minutes idle, 8 hours absolute. [0.3 ·
13]** It ends at whichever comes first — `AS_SESSION_IDLE_SECONDS` and `AS_SESSION_ABSOLUTE_SECONDS`
in `_types.py`, **a1p**'s naming. The idle clock restarts on a request the session makes to §11's
pages; the absolute clock runs from the login that established the session and nothing extends it.
**a1p**, binding the two words: a session that a page load could keep alive forever would have no
absolute bound at all. An ended session is no session: the next `/authorize` takes §11.0 substep 3's
303 to `/login`. Both numbers are contract values with no config key, as §2's code lifetime is.
`/authorize` is not among `HUMAN_ONLY_ACTS`, so these clocks, not §10.4's window, are what bound
presence at the endpoint this document calls "hand out authority". §13's `TODO(a1p)` on session
storage is the durable-state half of this question.

### 10.3 · The AS mints `interactive` only where presence can actually be composed

**An AS-minted token carries `principal: interactive` only when it is issued to a `browser` client
through §2's authorization-code flow. Every token issued through §3's device flow carries
`principal: client`, and so does every token issued to an MCP client (§4). a1p.**

The device flow is excluded on its own evidence, not by preference. In §2 the human and the client
share a surface: the browser that holds the session is the browser the code is redirected to, and the
owner's presence is evidence *about the software being granted*. In §3 they do not: the human is in a
browser at the container, and the client is a process on some machine the container has never seen —
possibly not the human's machine at all, which is exactly the remote-approval attack §3 mitigation 1
and the verification screen exist to blunt. **A human's presence at one surface is not evidence about
software at another**, so there is nothing to compose, and a device-flow token that claimed
`interactive` would be asserting a presence no step of the flow observed. §1 retired device-code in
browsers because a typed code proves nothing about *which container*; this is the same gap seen from
the other end — a typed code proves nothing about *which client*.

Two consequences:

1. **There is no `principal` request parameter, and a client cannot ask for one.** The principal
   follows from the flow and the owner's decision, not from the request. §7 fixes a `scope` value at
   two forms, neither of which is a principal, so a request that carries a principal in any spelling
   is refused as malformed — not narrowed.
2. **Rotation never upgrades a principal**, extending §9's rotation clause 3: the new token carries
   the same principal as the one presented, and a refresh that could change it would compose
   presence out of a value replay.

**An interactive-principal token is independent of the session that authorized it. [0.3 · 12]**
The session ending (§10.2's clocks, or a browser close) revokes nothing, so the flagship's long-lived
connection survives it. Two things bound the presence claim that survives the presence instead:
**the token always expires** — §9.3's 1-hour access token, non-null on every AS path (**[0.3 ·
17]**), under §11.5's grant expiry (**[0.3 · 18]**) — and **§10.4's backstop gates every human-only
act** on presence proven at or near the act, whatever the token's principal says. The backstop, not
the token's lifetime, stops a stale interactive claim from reaching a human-only act.

### 10.4 · The presence backstop — an interactive principal is necessary, never sufficient

**Every human-only act requires presence re-proof at the moment of the act, regardless of the
principal the presenting token carries. a1p** — and this is the answer to `spec/design/consent.md`
§14 item 12's `[GAP→a1p]`, raised there against the string *Human-only acts still need your tap.*

The gap was real. `capabilities.md` §4 gates human-only acts on the **principal**, refusing an
attempt by a `client`; §3 of the same document says *"a bearer token cannot prove a human, so the
token carries the claim and the container enforces on it."* Put those together with an
interactive-principal token that can be minted to software, and a machine could take a human-only act
on the strength of a claim recorded when a human was last present — on a page that had just promised
the human it could not.

So the gate has two parts, and `capabilities.md` §4 is the **floor**, not the whole of it:

- **principal** — a `client` principal is refused outright. Unchanged, **running**.
- **presence** — an `interactive` principal is *necessary and not sufficient*. From **Phase 2.2**,
  every human-only act (`gate.confirm`, `approve.pending`, `yes.consume`) additionally requires
  presence proven within a **live presence window** — `container.md`'s `step_up.window_seconds`,
  the step-up tap's window, with a `0` window meaning presence must be proven at the act itself
  rather than that no window is required. That reading is not a choice made here: it is
  `spec/design/step-up-tap-and-pending-approval.md`'s own answer for the zero case — §2.2 item 7
  (*"Signing proves you are here. No window opens."*), item 8 (the *Approve without a window* act is
  absent when policy is zero), R9, R8's *ready (policy zero)* row, and the `presence.zero` copy key
  all describe the same state: at policy zero, the tap itself is the proof, which is the
  **strictest** setting this backstop can take, not the backstop switched off. An expired window,
  or an absent one where the configured window is nonzero, refuses the act, and the refusal is a
  human-only violation like any other.

**`0` is a configured value, and a reader of the config must treat it as one** (`container.md` §8,
Chief 2026-10-03). The clause above is a statement about *policy zero*, which a container only ever
enters if the zero it was given survives being loaded. It does not survive `window or DEFAULT`:
`0` is falsy in Python, so the deployment that asked for the strictest setting in the table is
served the 300-second default it explicitly refused — the one coercion bug in this document whose
failure mode is a silently *weaker* gate than the one configured. Absence is tested by absence.
Stated here, at the clause that reads the window, as well as at the clause that defines it.

Stated so it can be tested when 2.2 lands: an interactive-principal token, presented with no live
window where the configured window is nonzero, and with no proof-at-the-act where it is zero, MUST
be refused a human-only act. A container that admits one is non-conforming.

**`yes.consume` is gated by the window of the ring pair the act crosses** — source → destination,
the pair `container.md` §8's third column already scopes the key by. **There is no single global
step-up window**, and a container that keeps one has collapsed R11's per-pair key into a setting
that lets a tap taken for an inbox-to-thread act satisfy a project-to-org one. Decided by the Chief,
2026-10-03; **decided, not running** (Phase 2.2). The consequence a builder needs: looking the
window up takes the act's *source and destination*, so a call site that has only the destination
cannot evaluate this gate and must not approximate it.

**The other two acts use the same window, and all three are narrowed by manifest shape. [0.3 ·
14]** `approve.pending` and `gate.confirm` are gated, as `yes.consume` is, by the window of the ring
pair the act crosses; and for all three a window opened for one manifest shape does not cover an
act of another (`container.md`'s R11 scoping). So the lookup for any of the three takes the act's
source, destination and manifest shape, and a call site missing one of them cannot evaluate the gate.

**`capabilities.md` §4 is amended to name this backstop. [0.3 · 38]** §4 states the principal gate
as the floor and this backstop as the second, mandatory half, and points here for the full text.

**Until Phase 2.2 the interactive owner token is the proof** (`capabilities.md` §3, **running**), and
this document does not pretend otherwise: that is a **stated, dated gap**, not the posture. The
requirement above is decided here and enforced from 2.2 — so the consent page's promise is a promise
about the shipped product, and a build that ships human-only acts to third-party interactive tokens
*before* 2.2 has shipped the hole. **a1p's reading**, for the review: 2.2 is the right boundary only
because before it there are no third-party interactive tokens at all — there is no AS. If the AS
lands before the tap does, the two must swap order, or the AS must refuse to mint `interactive` until
the window exists.

### 10.5 · `[LEAN]` · the step-up tap later rides these same endpoints

**`[LEAN]`, and §K's own word for it:** *"The step-up tap later rides the same AS endpoints rather
than a parallel bespoke channel."* Recorded and **deliberately not hardened.** This document fixes
**no** tap endpoint, no tap token shape, no binding and no window mechanics; Phase 2.2 and
`spec/design/step-up-tap-and-pending-approval.md` settle those, and the backstop above is stated in
terms of *a live presence window* precisely so it does not depend on how the tap is reached.

One consequence is worth recording because it is a dependency and not a design: the tap spec §14.3
binds a step-up to a **return address** and, under its D-T9 (b), derives that address from the
requesting client's registered `redirect_uris` — the client-registry read §11 defines. If the tap
rides these endpoints that read is already here; if it does not, the tap needs its own. **Routed, not
answered.** The same section's `[GAP→a1p]`s on the step-up's own events stay with #68's batch and
`events.md`, not here.

## 11 · The consent screen, the login and the device-code entry

**The consent screen is a product surface: `/authorize` renders the requested grant in `token ls`
vocabulary — scopes, capabilities, expiry, principal. Authorizing the flagship is indistinguishable
from minting any other client token because it IS one. §K**, verbatim.

The second sentence is the load-bearing one, and it is the same rule §7 carries from the other end:
§7 says an AS token *is* a `Token`, so §11 says the screen that authorizes one is the screen that
mints one. A container that rendered the flagship's request differently — fewer blocks, a shorter
path, a remembered decision — would have made the flagship privileged at the surface after §5 made
sure it was not privileged at registration.

Stated so it can be tested: **every clause in this section applies identically to the flagship, a
fork's UI, a CLI and (from Phase 5) an MCP client.** There is no client-specific rendering path, no
pre-approved client, and no configuration key that skips the screen for one. A container that ships
one is non-conforming.

**Consent and step-up pages are lifeboat-adjacent server-rendered Python, in-process with the
container: no new surface. §K.** The pages are served by the container's own origin — the §6
`issuer`, the origin §2's TLS clause governs — from the process that serves everything else. **a1p**,
binding what "no new surface" has to mean to be checkable: no second listener, no second port, no
separate auth app, and nothing a deployment has to run beside the container for `/authorize` to
answer. A container that reaches its consent screen through a hosted page is not this AS.

**The *look* of these pages is `spec/design/consent.md`, and this section does not touch it.** That
spec fixes the regions, states, copy and every string; this fixes what the pages must be *true
about*. Its §14 lists what it needs from here, and the rest of this section answers that list in its
order — beginning with §11.0, which takes item 2 out of turn because the order of *evaluation* puts
it before every other clause here. Where the two disagree, the contract's clause stands and the spec's string is a spec revision
— the terms §14's items 10, 12 and 13 already state for themselves.

### 11.0 · Every surface here is throttled, the throttle runs first, and the login redirect runs before either validation tier (§14 item 2)

Numbered **0** because that is its place in the order of evaluation: no clause below is reached on a
request this one has refused. **This section fixes the whole of the order that precedes validation** —
the throttle, its one exception, and where `/authorize`'s session check sits — rather than leaving
any part of it to the clauses that use it, because an ordering, and an exception to an ordering,
belong where the ordering is fixed. The substep list below is that order, and it is normative.

**`/authorize`, `/login` and `/device` are each throttled per caller by this section; the tap is
throttled per caller unconditionally too, by `consent.md`'s **D-C6** rather than by this document —
§10.5's `[LEAN]` governs only whether the tap rides *these* AS endpoints or a channel of its own, not
whether it is throttled at all. a1p**, closing the half of `consent.md` §14 item 2 that had fallen
between this document's two parts: item 2 asks for *"both throttled per caller as `/login` and
`/device` are, the throttle checked before either"* and routes itself to §5, which answers the
matching rule and nothing about throttling. §11.7 fixed `/login` and §11.8 device redemption,
leaving `/authorize` — the surface §12's
row (d) already gives a `throttled` cause — stated nowhere.

**The throttle is checked BEFORE either validation tier: before §5.3's pre-trust checks and before
§7's post-trust ones.** A requirement, not an implementation note, because an AS that ran the
post-trust tier first would answer a throttled caller with a **redirect** where the
`(client_id, redirect_uri)` pair is registered and with §5.3's page where it is not — a
registered/unregistered distinguisher surviving the throttle, at the endpoint §7 spends a subsection
silencing. Under this ordering a throttled `/authorize` request is **always** §5.3's page, which
makes `consent.md` §20's *"the same uniform page, never a redirect"* true by construction; and it is
why row (d) carries a `throttled` cause while row (f) cannot, a post-trust rejection being reachable
only by a request the throttle let through.

**A throttle that holds does not evaluate, and MUST fail closed** — §12.1 rules 3 and 4, the same
requirements seen from the ledger's side; and §12.1 rule **6** for the single path that survives it,
stated next so that the ordering and its one exception are read together.

**The exception: the deciding session's replay, and where it sits inside this step. a1p.** §12.1
rule 6 exempts one path from the throttle — a decided request re-submitted **on the session that
decided it** (§11.4). That exemption is only implementable if it is evaluated *within* §11.0, before
the counter, because recognising a re-submission means reading §11.4's decided-request record, and
that read is evaluation of exactly the kind rule 4 forbids once a counter holds. **§10.2's login
redirect has the same property from the other side** — it is an ordering, so it belongs where the
ordering is fixed, and it is the step that decides whether §5.3's tier is reachable at all. So
**§11.0 is three substeps, in this order**:

1. **At `/authorize` only: is this the deciding session's first re-submission of this request?**
   `/login` and `/device` have no substep 1 — §11.4's decided-request record exists only for an
   authorization request, so there is nothing for either surface to match against, the same way
   §3's device redemption has no substep 3 below. Two halves, and the
   document means them separately. The read is **keyed on the interactive session of §10.1 — never on
   anything the request carries**, because a key the caller can vary at no cost is no bound, which is
   the floor this section's throttle-key clause below states. The **match** is then against the decided request
   *that session's record names*: one interactive session can decide more than one authorization
   request — a second client, a second tab, a re-authorization after an expiry — so the session does
   not by itself identify a decided request, and the once-per-decided-request accounting below is per
   request rather than per session. A session-keyed read alone does not carry that state; the key
   bounds who may ask, the match decides what was asked. If the record names *this* request and its
   first re-submission has not been seen, the request is evaluated and appends once, row (d) cause
   `replayed`, whatever the counter's state. A caller with no interactive session matches nothing
   here and falls through.
2. **Otherwise, the counter.** If it holds, nothing below §11.0 is reached, and **each surface
   answers with its own uniform failure** — this step does not give the three surfaces one shared
   response, it gives each of them the response it already gives every other way of failing:
   - at **`/authorize`**, §5.3's page with cause `throttled`, for a caller with a session and a
     caller without one alike;
   - at **`/login`**, §11.7's uniform failure — one message, one status, one timing class — so
     `throttled` is indistinguishable from `wrong` and from `unknown` (§12 row (a));
   - at **`/device`**, §11.8's uniform failure across §12 row (b)'s causes, so `throttled` is
     indistinguishable from `invalid`, `expired`, `used` and `malformed`.

   The cause never reaches the page, at any surface — that much is a per-surface constant, not a
   per-surface choice. Whether it reaches the **ledger** depends on this substep's own state: this
   substep governs a throttle that *already holds*, so the ledger entry it reaches is §12.1 rule 3's,
   not rule 1's — rule 1 is one append per *evaluated* attempt, and rule 4 states plainly that a
   throttle which holds does not evaluate. Every attempt refused while the throttle holds is
   **counted, not appended**, whatever its cause would otherwise have been — the engaging attempt
   above appended once under `throttled`, cause and all; every attempt after it, at every surface,
   still receives the page the bullets above name, and **its cause** is what is discarded, reaching
   **neither** the page nor the ledger, adding only to the causeless count that rides on the
   throttle's eventual release entry (§12.1 rule 5, `surface` and `refused`, no cause) and appending
   nothing of its own. §5.3's page is `/authorize`'s
   answer and is not the other two surfaces' answer to anything.
3. **At `/authorize` only: is there an interactive session?** If there is none and the request
   presents no bearer credential, the response is a **303 to §11.7's `/login`** carrying a `continue`
   under that section's allowlist — §10.2's *"a caller presenting no credential and holding no
   session is sent to §11's login first,"* stated here as its place in the order. **This substep runs
   before either validation tier**: before
   §5.3's pre-trust checks and before §7's post-trust ones. A caller presenting a `Token` instead of
   a session is **not** sent to `/login`: §10.2 refuses it with §5.3's page, cause `token_presented`,
   on the presence of the credential and never on its validity. **A request holding both** — an
   interactive session *and* a bearer credential in the same `Authorization` header or position —
   is decided on the session alone; substep 3 branches on session presence first, so the credential
   is never reached and `token_presented` never fires. §10.2's refusal is for a credential presented
   in place of a session, not beside one. `/login` and `/device` have no substep 3 — `/login` is
   where a session is obtained, and §3's device redemption is not an owner act.

**Why substep 3 sits after the counter and before validation, and what the alternative cost. a1p**,
deciding the ordering a1r and A2 both found unfixed. Validating before the redirect would mean an
unauthenticated `GET /authorize` answers a **303** where the `(client_id, redirect_uri)` pair is
registered and §5.3's **page** where the `client_id` is not — a registered/unregistered
distinguisher, reachable with no credential, at the endpoint §11.1 states *"a caller must not learn
that a client id exists"* for. §5.3 clause 1 would not catch it, because clause 1 converges the
*failures* and that leak is a success. Under this ordering the redirect carries no registry
knowledge at all: **every session-less `/authorize` request that survives the counter gets the same
303 to the same destination, whatever it names**, because nothing has been validated when it is sent.
Substep 3 sits *after* substep 2 so the redirect is itself throttled — an unauthenticated sweep is
bounded by the counter like any other, not amplified into free redirects.

**What the redirect carries, and why that does not weaken the paragraph above. a1p.** The location's
`continue` carries the pending authorization request, because §2's browser flow and `consent.md` R3's
device hand-off both have to **resume** after the login rather than start again — §11.7 fixes the
carrier and its bounds. So two session-less redirects are not byte-identical: they differ by the
parameters the caller itself sent, and that is the whole of the difference. Nothing the AS knows
enters the redirect — no registry fact, no validity verdict, not even whether the `client_id` is a
string the container has ever seen — so a caller comparing two redirects is comparing its own two
requests. **The invariant this ordering needs is that nothing the AS knows varies, not that the bytes
do not**, and §5.3 and §10.2 now state it in those terms.

**The redirect of substep 3 appends nothing, and stores nothing about the request**, and both are
deliberate rather than an omission from §12's table: it performs no read — not §11.1's keyed entry,
not §11.3's — and decides nothing about the request. **The container state it changes is two counts
and nothing else:** the throttle counter's increment, and §12 row (h)'s per-window count of
admitted session-less 303s (`redirected`), which the throttle's timer appends once at the window's
close — so the effect invariant 2 requires an entry of has one, and the 303 itself owes none. The
pending request rides in `continue` (§11.7)
precisely so that no server-side record has to be written to hold it: a design that parked the
request in container state would hand an unauthenticated sweep something to *grow*, which is the very
thing §12.1 rule 3 bounds, and would owe invariant 2 an event besides. A count does not grow with what
the sweep sends, only with how often. What the sweep produces in the chain is row (h)'s one entry per
window, and the attempt that
engages the throttle appends once under §12.1 rule 3 as row (d) cause `throttled`. That entry, and
one row (d) `token_presented` entry per evaluated attempt that presents a bearer credential (§10.2,
bounded by the same counter), are the whole of an unauthenticated *caller's* reach into the chain at
`/authorize`, which is what rule 3 is now written on — rule 5's release entry is not a third addition
to this reach: the throttle's own timer writes it once per engagement, on no request at all (§12.2),
not the caller.

Substep 1 does not reopen rule 3's bound, and the reason is the point of writing it here: it is
unreachable without an authenticated interactive session, so an unauthenticated sweep never enters
it; sessions are themselves bounded by §11.7's throttled `/login`; and the exemption is **once per
decided request, not once per attempt** — a second re-submission of the same request, on the same
session, falls to substep 2 and is an ordinary row (d). The owner's interest is in learning that the
replay happened, which one entry states; a held-down back button is not a second fact.

**Consequence recorded, not acted on here.** Making substeps 1 and 3 precede validation puts rows (d)
and (f) out of an unauthenticated caller's reach except for (d)'s `throttled` and `token_presented`
causes, which is the
direct negation of `consent.md` D-C6's premise that *the post-trust tier is as reachable as the
pre-trust one*. That premise is the design side's to revise; this document does not edit it, and the
revision is filed as **#98** (`design-gap`). **#98 takes option (a): D-C6 is revised, not this
ordering. [0.3 · 45]** `consent.md` D-C6 and its affected §14.8 rows and §20 fixtures are revised so
the session check precedes both tiers; the edit is A2's and lands with #100's back-pointers after the
freeze, and until it does this clause governs where the two disagree.

**What a throttle keys on. [0.3 · 24]** It cannot be left unsaid: §12.1
rule 3 makes the throttle the **only** bound on the chain's growth from unauthenticated callers, so
two containers keying differently have different bounds on an append-only log the owner cannot prune,
and §12.2's pairing key is derived from whatever this is. The floor every bucket below clears:

- **Never a value the caller supplies and can vary at no cost** — not a `client_id`, not a
  `user_code`, not a form field, not a caller-chosen header. A throttle keyed on caller-supplied data
  is no bound at all; the caller lifts it by changing the value.
- **One surface's counter is one surface's**, so exhausting `/device` cannot lock the owner out of
  `/login`.

**Two buckets, both enforced**, as a1p read it and the record took — an outer per-surface
container-global one bounding the ledger absolutely, and an inner one keyed on the transport source
address so a single noisy source cannot spend the global budget. Each alone fails where the other
holds. An attempt is refused when **either** holds, which is what "holds" means throughout §11.0 and
§12.1, and **a network identifier may key a throttle and may never enter the chain.** TODO(chief),
#141: the record names no rates or windows; they bound every sweep, row (h)'s included (§12).

### 11.1 · The client-registry read (§14 item 1)

**The pages read one client entry: `{client_id, client_name, client_type, redirect_uris,
registered_at}`. a1p** — §5 fixes the first four as the registered entry; `registered_at` is added
here because the page renders it and §5 named no timestamp.

Two rules, and they are the section's, not the design spec's:

- **It is a read of one entry, keyed by the request's `client_id` — never a listing.** There is no
  endpoint, page or parameter that enumerates registered clients. A registry listing is an owner act
  on the owner's own surface, not something an authorization request can reach.
- **A `client_id` that is not registered produces §5.3's uniform failure and no read at all** — the
  same page, in the same time budget, as a registered client with a mismatched `redirect_uri`. This
  is §7's enumeration rule at the registry: a caller must not learn that a client id exists.

**The entry's `client_name` is data.** It is owner-supplied at registration (§5) and the AS neither
verifies it nor gives it meaning; a name that imitates the product is a registration the owner made,
and the page's defence is showing the origin and the kind beside it, which is the design spec's.
Nothing in the AS may branch on a client name.

**`client_type`'s literal and the kind word the page renders are not the same string** — named in
the opening provenance register above, and stated here at the clause that binds the page to the
read. `AS_CLIENT_TYPES`
(§1, Part A) is `browser` · `cli` · `mcp`; `consent.md`'s own rendered kind vocabulary (§14 item 1,
R4's client block, the `kind.*` copy keys) is `browser` · `device` · `mcp` — `device` where this
document's own type predates Part B as `cli`, because the design names the client by its flow
(device-code) rather than its category. §11.1 is the clause that binds the page to read
`client_type` and render the kind beside the name, so this is where the mapping belongs: a page
rendering this entry's `client_type` renders `cli` as the copy key `kind.device`, never as
`kind.cli`, which does not exist. The AS-internal literal does not change; only its display name
does, at the one place a display name is rendered.

**The mapping is named, not left to prose** (#10 F25): `_types.py` carries it as
`CONSENT_KIND_FROM_CLIENT_TYPE`, from `ASClientType` to `ConsentKind`, pinned by a test against
both `AS_CLIENT_TYPES` and `consent.md`'s rendered vocabulary.

| `client_type` (§1) | rendered kind / copy key |
|---|---|
| `browser` | `browser` · `kind.browser` |
| `cli` | **`device`** · `kind.device` |
| `mcp` | `mcp` · `kind.mcp` |

Two rows are identities and one is not, which is exactly why it needed a name: a reader who checks
the easy rows concludes the two vocabularies are the same and renders `kind.cli` on the third. A
surface that re-derives the mapping from the literal is non-conforming even where it happens to
agree.

### 11.2 · The screen renders what will be minted, after any clamp (§14 item 3)

**The grant the screen renders MUST equal the grant the mint produces. a1p** — this is the one
clause that makes the screen a security surface rather than a courtesy. §7 expands a `scope` value
into `{capabilities, scopes}`; the screen renders the *expansion*, not the request string, so a
bundle name displays as the capabilities it became (§7 consequence 1), `node:*` displays as the whole
container (§7 consequence 3), and a clamped expiry (§11.5) displays clamped. This clause carries
item 3's render half; §7's scope-expansion paragraph, cited throughout this section, carries the
vocabulary half — what the expansion contains, not that the screen must show it unaltered.

Two consequences:

1. **The AS MUST NOT mint anything the screen did not render.** No scope, capability or lifetime is
   added between the decision and the mint.
2. **A `scope` value the AS would narrow is refused, not narrowed** — §7's scope-expansion
   paragraph (just above its "Pinned" note and three consequences) refuses an
   **unparseable** `scope` rather than silently minting the part that parsed, and it is restated
   here because a screen that rendered a narrowed `scope` would be honest about a request the owner
   never made. **The clamped expiry above is this clause's one named exception, not an
   oversight**: §11.5 clamps rather than refuses precisely so a caller cannot probe the container's
   maximum lifetime by requesting past it and reading the refusal as an answer — the same probe-
   oracle concern §7 spent a subsection closing for `scope`. `scope` has no equivalent probe to
   close by clamping, so it stays refused; expiry does, so it stays clamped. Both are the AS
   refusing to mint anything the screen did not render — the paragraph above is the invariant, and
   this consequence is `scope`'s instance of it, not the general rule.

### 11.3 · The existing-tokens read (§14 item 9)

**The screen may read, for the pair (viewer, client), a count of live tokens and the most recent
`created_at`. a1p.** Bounded exactly:

- **live** means not revoked and not expired, by `capabilities.md` §5's own fields;
- **viewer-scoped** — it counts tokens the viewer owns and nothing else, which is `container.md`'s
  silence rule and not a display choice;
- **no ids and no values leave this read.** A count and a timestamp; never a `Token.id`, never a
  token value, never another client's total.

### 11.4 · An authorization request reaches a decision exactly once (§14 item 11)

**A request that has been decided — authorized or denied — MUST NOT reach a second decision, and
MUST NOT mint. a1p.** §2 makes the *code* single-use; this makes the *request* single-use, which is
a different object and the one the back button re-submits. A re-submission renders §5.3's uniform
failure and appends once, §12's cause `replayed`.

**Two reads recognise a decided request, one per case. a1p, then [0.3 · 27].** A decided request is
bound to the interactive session (§10.1) that decided it, and only that session's **first**
re-submission is §12.1 rule 6's unthrottled `replayed` path, recognised inside §11.0's substep 1,
keyed on the session. The same request arriving on **another** session, or a second time on the
deciding session, falls through substep 1 — and is recognised by **a request-keyed read at the
pre-trust tier, after the counter**: the AS reads §11.4's decided-request record by the request's own
identity, and a match is §5.3's uniform failure with row (d) cause `replayed`, appended under rule 1
and subject to rule 3 like any other row (d) cause. It never mints and never reaches a second
decision, which is what makes the opening paragraph's MUST NOT true in every case. Keying on the
request is safe here and not in substep 1 because this read runs *after* the counter, so a caller
varying the key at no cost is still throttled. **This is §12's fourth read of container state.**
**What identifies a request** is not in the record. **a1p**: the tuple `(client_id, redirect_uri,
state, code_challenge)` the request carries, since `code_challenge` is client-generated per request
and §2 binds the code to it; without the optional `state`, `code_challenge` (PKCE is mandatory) and
the rest identify it. For `consent.md` R3's device hand-off, the pending authorization
§3 mitigation 3 binds to the `device_code`.

**A re-submission carrying no session at all is not one this section ever sees. a1p** — it is
substep 3's redirect like any other session-less `/authorize` request, and nothing here applies to
it. Substep 1 falls through, because the read is keyed on the interactive session and a caller
without one matches nothing; substep 3 then sends the request to `/login` before either validation
tier, so §5.3's page is never reached and **this section's decided-request record is never read for a
caller with no session**. `replayed` is therefore one of the five row-(d) causes that answer an
authenticated session (§5.3 clause 1), and §12.1 rule 3's bound does not have to carry it. Without
this binding, rule 6's exemption is an
unbounded append any caller can drive at will, and it would not compose with §12.1 rule 3 — the
clause that bounds the chain's growth. `consent.md` §15 carries the design half (*"CSRF on the acts
— request bound to the session; form token"*); this is the contract clause underneath it, and §2's
binding of the **code** to the initiating session does not supply it, because the code is a
different object at a later moment.

### 11.5 · Expiry: the container's default and maximum, and the clamp rule (§14 item 6)

**An AS grant has a default lifetime and a maximum lifetime, and a request for a longer expiry is clamped to the maximum — never silently granted, never refused
for that reason alone. a1p**, answering `consent.md` §14.6's `[OPEN→a1p]` on the rule.

Clamping rather than refusing, for a stated reason: a refusal here is an error shape a caller can
probe for the container's maximum, and §7 spent a subsection making sure the AS is not that. A clamp
reveals the same fact **to the owner, on the screen, in the value being minted** — §11.2 requires the
screen to render the clamped expiry — and reveals it to the client only in the token it receives,
which it is entitled to know. A client that needs longer asks the owner, not the AS.

**The two numbers: grant expiry defaults to 30 days and is clamped at 90. [0.3 · 18]** The expiry
this section governs is the **grant's** — how long the refresh-token chain §9.2 rotates stays
redeemable — and §9.3's 1-hour access token (**[0.3 · 17]**) is the shorter clock under it; the screen
renders the grant's expiry, clamped. `AS_GRANT_LIFETIME_DEFAULT_SECONDS` and
`AS_GRANT_LIFETIME_MAX_SECONDS` in `_types.py` carry them, **a1p**'s naming. No AS grant is
non-expiring: `null` is `token mint`'s alone (§9.3). The record names the numbers and no config key.
TODO(chief), #142: whether a container's config may lower either number. Until then both are contract
values with no config key, the stricter reading.

### 11.6 · A standard error redirect carries no description, at all (§14 item 4)

**An error redirect from `/authorize` carries exactly `error` and the request's `state`. The AS MUST
NOT emit `error_description` or `error_uri`, with any value, under any cause. a1p** — §7 fixes that
the *code* is identical across causes, and `consent.md` §14.4 is right that a uniform constant
description would satisfy §7 while leaving a field every implementation will eventually fill with the
cause it already computed. The field is removed rather than constrained.

Testable as written: the redirect's query is `{error, state}` and nothing else; the body is empty;
and the response is byte-identical across §7's three converging causes.

### 11.7 · Login (§14 item 7)

What is fixed here, and it is the §10 boundary said as a requirement on the page:

- **The login establishes an interactive session and mints no token.** §10.1's four bullets hold: the
  session is not a `Token`, appears in no `token ls`, and is accepted at no endpoint that accepts a
  `Token`.
- **`continue` is a relative path, matched against a fixed allowlist of parsed paths.** The rule is
  `consent.md`'s **D-C5**, restated here as a requirement on the AS — and restated in full, because
  the pre-parse half is the half an implementer skips. In D-C5's own order:
  - **Step 1 — reject *before* parsing.** A value is rejected, unparsed, if it does not begin with
    **exactly one `/`**, or begins **`//`** or **`/\`**, or contains a **backslash** anywhere, or
    contains **any control character**. All five conditions are D-C5 step 1's and this clause carries
    all five: the pre-parse rejection is the whole of that step, not the leading-`//` case alone.
  - **Step 2 — compare the parsed *path component* only**, exactly, against D-C5's patterns
    (`/authorize` · `/device` · `/pending` · `/pending/<id>` · `/` · `/items/<id>`, `<id>` on D-C5's
    positive charset). The reference MUST have **no scheme and no authority**; it is never an
    absolute URL; the **fragment is always dropped**.
  - **Step 3 — the query carry — stated below at the `continue`-survives-login bullet**, not here:
    it depends on the login round-trip this list precedes, so restating it in numeric order would
    separate it from the mechanism it belongs to. Genuinely covered, not skipped.
  - **Step 4 — a value failing any step is dropped silently for the container's root** — a 303 to
    `/`, never reported, never echoed back as a reason. `consent.md`'s **R2** login-state table
    fixes the same case the same way — `| invalid continue | ignored; 303 to / |` — no page and no
    form rendered for it; this clause restates R2 rather than deciding it fresh.

  **a1p**: this is the open-redirect hole in the one place a human has just typed a credential, and
  the allowlist is an allowlist rather than a validator because every "validate a redirect" bug in
  the literature is a validator.
- **`continue` is never *rendered*, and it crosses the credential POST in exactly one position.
  a1p.** The anti-reflection rule is a rule about **rendering**: the value MUST NOT be written as
  visible page content, into any attribute of an element rendered *for* it, or into any script or
  style on the page. It is **not** a prohibition on the login form's own carrier — the two-hop this
  section requires (GET `/login?continue=…` → credential POST → 303 to `continue`) cannot complete
  without one. The **one permitted position** is the login form's own `action` query or a single
  hidden input the form posts, and there the value is carried **still percent-encoded and
  contextually escaped for the position it occupies**, then read back only as a parameter of the
  POST. Two bounds on that carrier: a value that failed step 1 or step 2 **never reaches it** —
  Step 4's 303 fires at the GET and no login page, and so no form, is ever rendered for it — and
  the value is re-matched against steps 1 and 2 on the POST before the 303 is issued, because a
  form field is caller-controlled input whatever put it there. A form that round-trips an
  unvalidated value is the same hole one hop later.

  **The POST-hop re-match covers step 3 too. [0.3 · 26]** On the POST the value is re-matched
  against D-C5 steps 1, 2 **and 3**: the query is re-scoped to step 3's two carrying patterns, never
  whatever the form posts back.

  **A POST-hop failure takes step 4's disposition, with the login established. [0.3 · 26]** A
  credential that verifies establishes the session and appends row (a) `established`; a `continue`
  failing the re-match is then dropped for a 303 to the container's root, exactly as at the GET. The
  cost is accepted as named: the carrier's failure is recorded nowhere of its own, and row (a) keeps
  its three closed causes.

- **`continue` is also how the pending authorization request survives the login, and it is the only
  thing that carries it. a1p.** §11.0's substep 3 redirects a session-less `/authorize` request here
  before anything about it has been validated, so the request has to reach the login *and come back*,
  or §2's browser flow cannot complete and the human is left at a container root having authorized
  nothing. Fixed as follows, and testable:
  - **The query rides along only where `consent.md` D-C5 step 3 carries it: `/authorize` and `/`,
    and nowhere else.** D-C5 step 3 carries the query string verbatim — **still percent-encoded,
    never decoded before it is written to `Location`** — for exactly those two patterns, because
    those are the two whose targets consume one (`/authorize`'s parameters *are* the request; `/`
    carries the search the viewer was on), and **drops it** for `/device`, `/pending`,
    `/pending/<id>` and `/items/<id>`. **This clause states D-C5's scope and does not widen it.
    a1p** — an earlier draft here carried the query for every pattern, which would have been a new
    attack-surface decision taken in a contract document over a committed design spec that had
    already decided it, and taken as a side effect of an unrelated ordering fix. D-C5 step 3 is the
    source; if the carry should be wider, that is a revision to D-C5, not a clause here.
  - **Where it is carried, it rides unparsed.** The AS does not inspect it, does not render it, does
    not store it and does not validate it at `/login`. On a successful login the browser is sent to
    the allowlisted path **with that query intact**, and that path validates the request exactly as
    it would have validated the same request sent directly.
  - **Two flows depend on it and both MUST complete without the client re-initiating**: §2's
    browser flow resumes at `/authorize` with the `client_id`, `redirect_uri`, `state`,
    `code_challenge` and `code_challenge_method` the client sent; and `consent.md` R3's device
    hand-off — *approved (code found)* is a `303 to /authorize?user_code=…` — resumes at the same
    path with its `user_code`, which is the case that fails silently if only a bare path survives.
    **Both resume at `/authorize`**, which is one of step 3's two carrying patterns, so scoping the
    carry to D-C5 costs neither flow: the four patterns that drop the query are the ones whose
    targets consume none.
  - **Nothing is written to container state to make this work.** The request rides in the redirect,
    not in a server-side pending record. This is what keeps §11.0's substep 3 a step that appends
    nothing and stores nothing about the request, and it is why an unauthenticated sweep cannot make
    the container retain anything of what it sent (§12.1 rule 3). The 303 does change two counts —
    the throttle counter and §12 row (h)'s per-window `redirected` tally (§11.0) — and neither holds
    a byte of the request. **The login form's carrier is not an exception to this.** The
    hidden field or `action` query named two bullets above lives in the response the AS renders and
    comes back on the POST the browser sends; the AS retains nothing between the two, and a caller
    that never posts leaves nothing behind. What this bullet forbids is a **server-side pending
    record** — something the container holds, that a sweep could grow. A field in a page the caller
    is holding is not one.
  - **A query changes no bound that the path did not already have.** Every value in it is the
    caller's own, handed back to the same caller, and the endpoint it is handed to is one the caller
    could have called directly — so the allowlist still bounds *where* a freshly authenticated
    browser can be sent, which is the whole of what it is for.

  **`continue` is at most 2048 bytes. [0.3 · 25]** Measured as received, still percent-encoded,
  query included (**a1p**); a longer value is dropped for the container's root like any other
  non-matching value, at the GET and at the POST alike. `AS_CONTINUE_MAX_BYTES` in `_types.py`.
- **The login is throttled per caller**, on §12's terms, and its failures are uniform: wrong
  credential, unknown user and a throttled attempt produce one message, one status and one timing
  class. A login page that distinguishes *unknown* from *wrong* has published the container's user
  list.

**The credential is a container secret: v1.0's browser identity. [0.3 · 7]** The human presents the
container's secret at `/login`, and that is the whole of v1.0's login — `consent.md` §2.1's single
*Container secret* field stands as written. Three bounds come with it:

- **More authenticators can be added later without a break.** The rest of this section is stated
  in terms of "the login establishes an interactive session", never in terms of the secret, so a
  passkey or an IdP bridge is a new way to reach the same session, not a new session.
- **Firebase is `egzos.io`'s browser identity, not the container's.** It is the platform's
  subscription session (§8's double login, unchanged); the open-core container has no dependency on
  it, and §8's IdP collapse stays `[v1.1]` (**[0.3 · 8]**).
- **The secret never enters the chain or a page.** §12.1 rule 7 already keeps it out of `details`.

TODO(a1p), #143: how the secret is provisioned at `init`, how it is stored, and how it is rotated are
not in the record. They are a3-trust's at Phase 0.4, under §13's state-persistence TODO.

### 11.8 · The device-code entry (§14 item 5)

§3 fixes the flow, the endpoints and the three mitigations. This fixes what the entry page needs:

- **The `user_code` is 8 characters, shown `XXXX-XXXX`, from RFC 8628 §6.1's 20-consonant
  alphabet `BCDFGHJKLMNPQRSTVWXZ`. [0.3 · 20]** The length is `consent.md` D-C4's own number, so
  the contract confirms that decision rather than reopening it; the alphabet is the record's addition,
  which D-C4 left open. No vowels, so no code spells a word; no digits, so no `0`/`O` or `1`/`I`
  pair. `AS_USER_CODE_ALPHABET` and `AS_USER_CODE_LENGTH` in `_types.py` carry it. Each character
  is drawn from §9.1's CSPRNG. The hyphen is display only, and the entry form matches
  case-insensitively with the hyphen ignored, per RFC 8628 §6.1 (**a1p**). The code is about 34.6
  bits, far under §9.1's floor and deliberately so; §3 mitigation 1's attempt bound and expiry carry
  its security (§9.1 reading 2).
- **Redemption is single-use and throttled**, per §3 mitigation 1 and §12: a code that has been
  redeemed is spent whether or not the authorization it belongs to was approved. **Its failures are
  uniform**, on §11.7's terms and for §11.7's reason: §12 row (b)'s five causes — `invalid`,
  `expired`, `used`, `malformed` and `throttled` — produce one message, one status and one timing
  class, the cause reaching `details` and never the page for the attempt that is *evaluated*
  (§12.1 rule 1) — which is every one of the five for an attempt the throttle admits, and only the
  first `throttled` one once the throttle holds: rule 4 states a held throttle does not evaluate,
  so every further attempt at this page while it holds is counted, not appended (§12.1 rule 3), the
  same exception §5.3 clause 4 states for `/authorize`. A page that distinguished `used` from
  `invalid` would tell an attacker sweeping codes which of its guesses had ever been issued. This is
  the response §11.0's substep 2 means at `/device`; §5.3's page is `/authorize`'s and is not this
  surface's.
- **The requester hint is client-supplied, unverified data.** A device client MAY report a device or
  host name for the client block. **The AS MUST NOT verify it, MUST NOT branch on it, and MUST NOT
  record it anywhere that reads as verified. a1p** — it is a phishing-relevant string a remote
  attacker controls, and the honest handling is to carry it as untrusted, bounded and escaped, the
  same posture `item.add` takes toward content (`unverified-by-default`, applied to a page).

**No prefilled entry: `/device` ignores a `user_code` query parameter. [0.3 · 21]**, stated at §3.
`consent.md` §14.5's point is why both halves were needed: the CLI can build the link itself from a
code it was given, so not issuing `verification_uri_complete` holds only if `/device` also ignores
the parameter. It does, so the CLI's home-made link renders the empty form. `consent.md` R3's
prefilled row and its §20 fixture are a spec revision, A2's after the freeze.

### 11.9 · Revocation the owner can reach from a browser (§14 item 13)

**The owner revokes by `Token.id` on the container's own pages, and a client also gets the RFC 7009
endpoint. [0.3 · 11]** Both halves were taken, so the two questions this section once kept apart are
both answered: §9.2's client path keyed on the token *value*, and this owner path keyed on the
*identifier*, which the browser can see and which is no credential (§9.1). Concretely:

1. **On the container's own pages, inside an interactive session (§10.1),** the owner revokes any
   token in `token ls` by its `Token.id`. It is `token rm` reached from a page — no new authority —
   and writes one `token.revoke` (**[0.3 · 30]**, carrying the refresh-family id).
2. **It is throttled on the fifth `surface` word, `revoke`** (§12.1 rule 5, `AS_THROTTLE_SURFACES`),
   with §11.0's two buckets, so a walk of the id space is bounded.
3. **A refusal is uniform and appends.** An id that does not exist and one the session may not reach
   get the same response, §7.1's rule applied to an identifier; the attempt appends once with its
   cause in `details`, so the refusal path leaves a trace as the success path does. It carries
   `principal: interactive` (**a1p**): the page is reached only inside a session. **Its event is
   `authz.revoke_refuse`, outcome `refused`, and `details.cause` is one closed word: `unknown` (no
   token has that id) · `unreachable` (one does, and the session may not reach it) · `throttled`
   (the attempt that engages the `revoke` throttle, on §12.1 rule 3's terms: every further attempt
   while it holds is counted, not appended, and rule 5's release closes the pair). a1p, #144** —
   pinned as `AS_REVOKE_REFUSAL_CAUSES`. Not `authz.refuse` (row (d), pre-trust) or `authz.reject`
   (row (f), post-trust): a revoke is neither tier of `/authorize`, and an `audit` query should not
   have to read `details` to tell the three apart.

**The flagship dashboard.** It is a separate origin reaching this AS as a browser client, so it holds
no session on the container's pages and cannot use the owner path. It can revoke the token it holds
through §9.2's endpoint, and nothing else. `consent.md` §19's broader revoke sentence is therefore a
spec revision (A2's, after the freeze): the owner revokes other tokens on the container's page or with
`token rm`. `consent.md` §13's `expiry.none` string stands.

## 12 · The pre-authorization audit surface

§9 covers the chain entry a *token* produces. This covers `/login`, `/device` and `/authorize`'s
two tiers, plus the throttle's release and tally entries — three pages and a timer, not the tap page
or §11.9's page (decided at §9.2), which §12.1 rule 5's five-word `surface` vocabulary names but
this section does not cover (its entries are `token.revoke` and §11.9's refusal entry). For the tap, its
endpoint, token shape and window mechanics are §13's to route to Phase 2.2 (§10.5's `[LEAN]`
paragraph withholds binding on the same timeline, a fourth thing neither this section nor §13
carries); its own audit entries are a different pointer, §10.5's `[LEAN]` closing line's, which
keeps them with #68's batch and `events.md` rather than here.

**The effects those three pages produce before any token exists** — (a), (b), (e) and (d)'s
`throttled` and `token_presented` causes before any session exists either, (e) on no request at all
(§12.2), the rest inside a session §11.0's substep 3 has already required — **each now has an event
name. [0.3 · 33, 36]** `events.md` §4 invariant 2 (*"A surface that produces an effect without a
corresponding event is non-conforming"*) and §1's closed vocabulary both hold here: the names are
in `events.md` §1.

**Five `authz.*` events for the pre-authorization surfaces, a sixth for the render, a seventh for
the tally. [0.3 · 33, 36], #140** The rows are `spec/design/consent.md` §14.8's (a), (b), (d), (e)
and (f); its (c), a consent denial, is `authz.grant` with `decision: denied` (§9.3, **[0.3 · 29]**).
Row (g) is the record's sixth row: a rendered consent screen appends. Row (h) is the Chief's #140.
**The names are a1p's**, in `events.md`'s `noun.verb` shape. The seven are in `events.md` §1 and
`_types.py`'s `Event`, eight with §11.9's `authz.revoke_refuse`, all **decided, not running**.

| | the effect | event | outcome | `details.cause`, a closed word |
|---|---|---|---|---|
| **(a)** | a login attempt at `/login` | `authz.login` | `established` · `failed` | `wrong` · `unknown` · `throttled` |
| **(b)** | a device-code redemption at `/device` | `authz.redeem` | `found` · `failed` | `invalid` · `expired` · `used` · `malformed` · `throttled` |
| **(d)** | a pre-trust uniform failure at `/authorize` | `authz.refuse` | `failed` | `unknown_client` · `redirect_mismatch` · `malformed` · `missing_pkce` · `throttled` · `replayed` · `token_presented` |
| **(e)** | a throttle releasing | `authz.release` | `released` | — (see below) |
| **(f)** | a post-trust rejection at `/authorize` | `authz.reject` | `rejected` | `vocabulary` · `scope` |
| **(g)** | a consent screen rendered at `/authorize` | `authz.render` | `rendered` | — |
| **(h)** | session-less `/authorize` traffic the throttle admitted, per window | `authz.tally` | `counted` | — |

**Row (f) is one of the five, which settles what §9.3's exclusion (iii) left raised to #68:** a
post-trust rejection keeps its own row, outcome and both causes, and `authz.grant` is not widened.
**`refuse` is pre-trust, `reject` is post-trust. a1p:** `authz.refuse` is §5.3's uniform page, which
never names the client; `authz.reject` follows a matched client and redirect (§11.6). **Row (g)
carries `client_id`. a1p** — so the owner can see which client put a screen in front of them. It
appends once per render, inside a session §10.1 has authenticated, and §11.0's throttle bounds it.

**Row (d) has a seventh closed cause `consent.md` does not carry — named as the addition it is, not
left for the freeze review to discover.** `consent.md` §14.8 (d) closes at six causes —
`unknown_client`, `redirect_mismatch`, `malformed`, `missing_pkce`, `replayed`, `throttled` — and
§20's Failures fixture list enumerates exactly those six. `token_presented` is this Part's own
addition: it is introduced by §10.2's refusal of a bearer credential presented in place of a session,
and threaded through §5.3 clause 1, §11.0 substep 3, §12.1 rule 3 and §12.2. The addition is sound —
§10.2's reasoning for refusing a presented credential at this endpoint is not in question — but it is
the same kind of divergence the narrowings below are named for, and it carries a cost a narrowing
does not: a builder working from §20's six-cause fixture list produces no `token_presented` fixture
and has no signal that one is owed. **[0.3 · 45]** records this divergence as authoritative (#100):
§20 owes a `token_presented` fixture, added by A2 with the back-pointers after the freeze.

**Row (f) has two closed causes, not three — a narrowing of a decision `consent.md` states in
**six** places, named as the spec revision it is.** §14 item 8's own cause list for (f)
(`vocabulary` · `scope` · `expiry`), §14 item 2's post-trust tier ("expiry within config → else
redirect"), §20's fixture ("clamped (R9) or `access_denied`, per §14.6" — conditional on §14.6, not
an unconditional append under (f)), R12's `rejected (post-trust)` row, `consent.md`'s §10 post-trust clause
(also stated only conditionally there), and R9's own `ready (beyond container max)` row ("the
server clamps or refuses per config (§14.6)") all name a third post-trust rejection cause: an
expiry request beyond the container's maximum. Three of the six — §20's fixture, `consent.md`'s §10 clause and
R9's row — are conditional on the same question, §14.6, not one; §11.5, answering `consent.md`
§14.6's own `[OPEN→a1p]`, decides the
opposite for that one cause: an over-long expiry is **clamped to the maximum, never refused for that
reason alone** — the same probe-oracle reasoning §7 closes for `scope`, and §11.2 consequence 2
already names the clamp as its one exception to the refuse-don't-narrow rule. Row (f)'s cause list
did not carry the same correction until now. `expiry` is not a closed cause of (f): every over-long
expiry is clamped, not rejected, and no clause in this Part rejects one for `expiry` alone — the two
that remain are the whole of what a post-trust request can be rejected for. **`vocabulary` carries
both halves of §7's `invalid_scope` reservation, not one**: a scope value that is **malformed**, and
one that is **not one of the six capability names** — the same error code, the same closed cause,
because both are a fact about the vocabulary in this document and neither reveals anything about the
container. `scope` carries §7's `access_denied` half at this endpoint: a node the viewer does not
cover or one that does not exist.

**Rows (a), (b), (d) and (f)'s cause vocabularies are pinned, not left to be caught by hand.**
`AS_LOGIN_CAUSES`, `AS_DEVICE_REDEMPTION_CAUSES`, `AS_AUTHORIZE_PRETRUST_CAUSES` and
`AS_AUTHORIZE_POSTTRUST_CAUSES` in `src/egzos/_types.py` fix the four tuples this table states,
the same way `AS_THROTTLE_SURFACES` already fixes rule 5's — so a cause arriving that is not in
its row's tuple breaks a test rather than appending quietly, which is exactly the gap this Part's
own row (d) addition sat in until this review caught it by hand.

**The reads a decision rests on, and `events.md` §4 invariant 2's exception. [0.3 · 36, 38]** A
rendered screen performs §11.1's and §11.3's reads, and row (g) records them — so the **abandoned**
render, which a client can drive at will by initiating `/authorize`, leaves a trace. **Invariant 2
is amended** with one exception: a read the owner makes of their own container's state, inside a
session §10.1 has authenticated, to decide an act they are performing, gets no read event of its
own. Its three instances: (1) §11.1's registry read and (2) §11.3's existing-tokens read, both
recorded by row (g); (3) §11.0 substep 1's match against §11.4's decided-request record, recorded by
row (d) `replayed` where it matches, and otherwise by the entry the request goes on to (rule 1, or
rule 3's count while a throttle holds).

Each is bounded — one keyed entry, a count and a timestamp, one record — so none carries out
anything an unrecorded read would hide. **§11.4's request-keyed read, §12's fourth (**[0.3 · 27]**),
is not an instance**: every path through it appends — row (d) `replayed` on a match, otherwise (d),
(f), (g) or §9.3's decision. `events.md` §4 invariant 2 carries the amendment and names these three
instances.

**A session-less 303 to `/login` counts toward the throttle. [0.3 · 37]** Substep 3 runs after
substep 2, so every session-less `/authorize` adds to both §11.0 buckets. A sweep that engages
either appends row (d) `throttled` once and row (e) once at release, whose `refused` count carries its
size. **A sweep under both buckets is tallied, not traceless. #140; the shape is a1p's.** At the
close of each window of `/authorize`'s container-global bucket in which the throttle admitted any
session-less 303, the timer appends row (h) once: `principal: none`, `actor: authorize` (§12.2), and
two closed `details` keys, `redirected` (the count of those 303s) and `window_key`, derived from that
bucket as §12.2 states. No 303, no entry. The 303 appends nothing itself and the caller's response
is unchanged. Not a sample: a sample leaves the unsampled traceless, which D-C6 rejected by name.
Like (e), (h) is written on no request, at most once per window, so §12.1 rule 3's bound holds.
**What remains:** (h) says how many, never who — no network identifier (§11.0), no `client_id`
(substep 3 runs before either tier reads one) — and shows at its window's close; #141 names it.

### 12.1 · The rules, which are not open

**a1p**, and stated so the review can overturn them deliberately rather than lose them inside a
naming decision:

1. **One append per *evaluated* attempt, success and failure alike** — the same shape `events.md`
   invariant 2 already requires of a read. The cause lives in `details` and never on the page: §5.3,
   §7, §11.7 and §11.8 — four sections making **three** surfaces uniform to the *caller*, §5.3 and §7
   being `/authorize`'s two tiers and not two surfaces of their own, matching §12's own "three pages
   and a timer" — **each in its own response, not in one shared one** (§11.0 substep 2) — and that
   uniformity is owed to the caller, never to the owner's own ledger. This rule's three are three of
   rule 5's four closed `surface` words below, but this rule is not using them as that vocabulary —
   the tap is the fourth, the one rule 5's vocabulary "names but this section does not cover" (§12's
   own framing sentence, above), and this rule does not reach it, because this rule covers only the
   pages that render a uniform *failure*.
2. **One append per** ***evaluated*** **path, however the path is reached.** (d)'s page is one page;
   a request the throttle *evaluates* — every cause but the ones rule 3 excepts — writes once each
   time, so among evaluated attempts no cause is distinguishable by the *number* of writes it makes.
   Rule 3, next, is this rule's one exception, not a separate rule that happens to sit beside it:
   `throttled` writes once only for the attempt that engages the throttle, and zero times for every
   attempt refused while it already holds — that difference is real, and it is rule 3's, not this
   one's, to state and bound.
3. **A refused attempt is counted, not appended.** The attempt that *engages* a throttle appends once
   under (a), (b) or (d) with cause `throttled` — always (d) and never (f) at `/authorize`, because
   §11.0 runs the throttle before either validation tier. Every further attempt refused while the
   throttle holds is counted and not appended. This is the clause that bounds the chain, and what it
   bounds is **exactly the part of the table an unauthenticated caller can reach**: (a) and (b), which
   must be reachable unauthenticated because they are the surfaces at which authentication is
   *attempted*; and (d) with two of its seven causes — `throttled`, which §11.0's substep 2 produces
   ahead of its substep 3, and `token_presented`, which substep 3 produces for a caller presenting a
   bearer credential (§10.2). Both are bounded by the same counter, because both are decided after it:
   a sweep presenting credentials is throttled exactly as a sweep presenting none is, and neither
   reaches a response that depends on the registry. **(d)'s other five causes and the whole of (f)
   are not reachable unauthenticated** — a
   session-less `/authorize` is a 303 to `/login` before either validation tier, and the redirect
   appends nothing and stores nothing about the request — it changes only the throttle counter and
   row (h)'s per-window `redirected` count, which the timer appends once per window (§11.0). Nothing here says a client id or a registered redirect URI may be learned: §11.1's
   *"a caller must not learn that a client id exists"* and §5.3 clause 2's time budget hold
   undiminished, and this rule takes no position on what a caller knows — only on what an
   **unauthenticated** caller can make the chain do. Without it a sweep at (a), (b) or a session-less
   `/authorize` grows an **append-only** log the owner cannot prune, at the caller's rate; with it the
   sweep's whole reach **at `/authorize`** is what §11.0's substep 3 already states there: **one
   entry per throttle engagement, plus one `token_presented` entry per attempt the throttle admits
   and (d) evaluates.** Rule 5's release entry is not a third figure this bound omits: it is written
   once per engagement by the throttle's own timer, on no request at all (§12.2) — never a caller's
   own attempt reaching the chain — so it is not part of what an unauthenticated *caller* can make the
   chain do, though it is part of what an engagement costs the chain overall. (a) and (b) append under their own cause per rule 1 on an admitted attempt,
   never under `token_presented` — this rule's bound applies to the endpoint where that cause is
   possible.  It is *not* one entry per engagement flat at `/authorize` — `token_presented` is
   decided inside substep 3 and appends per evaluated attempt, so a sweep that presents bearer
   credentials there appends as often as the throttle lets it through. The bound is therefore **the
   throttle's own admitted rate**, which is the same counter in both cases; the engagement entry is
   one more on top of it, not the whole of it.
4. **A throttle that holds does not evaluate — a correct credential or a valid code included, with
   one exception, rule 6's.** A throttle that evaluated the right answer while refusing wrong ones
   would bound the ledger and not the guessing, which is the opposite of what it is for. **A
   throttle MUST fail closed:** one that fails open turns the audit chain into a write amplifier.
   Rule 6's deciding-session replay is the one case this rule does not reach: it is read inside
   §11.0 substep 1, ahead of the counter this rule governs, which is the ordering rule 6 states and
   this rule's own wording does not point to.
5. **The release appends whenever an engage did, `refused: 0` included.** Beside (h)'s admitted count, (e) is the only entry that
   carries a sweep's size, so a release that appended only on a non-zero count would let the size be
   inferred from a *missing* entry. `details` carry `surface` — a closed word, `login` · `device` ·
   `authorize` · `tap` · `revoke` (`revoke` is §11.9's page (decided at §9.2), the fifth word, **[0.3 · 11]**;
   the step-up tap is the fourth surface, throttled unconditionally by
   `consent.md`'s D-C6; if §10.5's `[LEAN]` is not taken the tap rides a channel of its own rather
   than these AS endpoints, but the word is still used there — D-C6's release entry is
   `consent.md` §14.8 (e), the same event this rule pins, and the tap spec §14.5 binds to it **by
   citing the decision, not by restating it in an entry of its own** — never unused, only ridden
   elsewhere) — `refused`, an integer, and `window_key`, the opaque per-window key pairing (e) with
   the engage entry it summarises (**[0.3 · 35]**, §12.2). **These three are closed.**
6. **The deciding session's replay is never throttled.** §11.4 binds a decided request to the
   interactive session that decided it, and *that* session's re-submission is the one this rule
   exempts: it is evaluated — **in §11.0's substep 1, ahead of the counter, which is where that
   ordering is carved and the only place the read is reachable** — and appends once, cause
   `replayed`, whatever the throttle's state, because a replay after a decision is a fact the owner
   has an interest in and the session it arrives on is one §10.1 has already authenticated. **The
   exemption reaches no further**: not to another session, and not to a second
   re-submission of the same request, substep 1 being once per decided request. Each of those is an
   ordinary (d) under rule 1 — §5.3's page, cause `replayed`, evaluated and appended once, exactly
   like any other row (d) cause — and subject to rule 3's exception the same way every row (d)
   cause is: only while a throttle already holds does it get counted instead of appended, not as a
   rule of its own. A re-submission carrying **no** session reaches neither the exemption nor the page:
   substep 1 falls through, substep 3 redirects it to `/login` before either validation tier, and
   §11.4's decided-request record is not read for it at all — which is why rule 3 does not have to
   carry `replayed` among the causes an unauthenticated caller can reach.
   Read without §11.4's binding and §11.0's substep this rule would be an unthrottled
   append reachable by any caller, which is exactly what rule 3 exists to prevent. **This narrows
   the same decision `consent.md` states in five places, and is named as the spec revision it is**
   (this document's opening provenance rule): §14 item 8's parenthetical, **D-C6** itself, R11's
   `stale` row, R12's `back after decision` row, and §20's fixture list all describe the deciding
   session's replay as unbounded — "whatever the throttle's state," with no limit on how many
   times. Rule 6 exempts only the first re-submission; a second on the same session is an ordinary
   (d), evaluated and appended once like any other row (d) cause unless a throttle already holds,
   in which rule-3 case alone it is counted instead. The contract's bound is the better of the two,
   for the reason rule 3 exists, and wins under §11's own preamble — over every one of the five, not
   only the one this section happened to quote.
7. **`details` never carry the credential, the `user_code`, a token value or a `code_verifier`** —
   `events.md` invariant 4, restated because these are the five entries closest to a credential in
   the whole taxonomy. The cause is a closed word, not a message, and a closed word cannot carry one
   by accident.

### 12.2 · What `actor` and `principal` carry when there is no caller

`events.md` §2 makes `actor` and `principal` **mandatory** on every entry, and before 0.3
`capabilities.md` §3 closed `principal` to `interactive` · `client`. None of the five, nor (h), could
satisfy that: (a)
fires on `/login` *before* the login that would establish `interactive`; (b), (d) and (f) fire before
any token exists; and (e) and (h) fire on **no attempt at all** — a timer releasing or tallying, with
no caller in any request. The record closes the gap as follows; the text that carries it is `events.md`'s and
`capabilities.md`'s.

**a1p's reading, taken by the record. [0.3 · 34, 35]**

- **`principal` gains a third closed value — `none`.** Not a nullable field: `principal` being
  mandatory is what makes the chain readable in one pass, and a nullable one is a branch every reader
  and every `audit` query must carry forever. A third word costs one row in `capabilities.md` §3 and
  says exactly what is true.
- **`actor` carries the *surface*, not the caller** — the same closed five as (e)'s `surface`. It is
  the only honest thing known about the append, and it is what pairs (e) with the entries it
  summarises. **The caller's network identifier MUST NOT be the actor.** An IP or a client hint in
  `actor` writes network identity into an append-only chain the owner cannot prune, which turns the
  audit log into a surveillance record of everyone who ever touched the container's front door — a
  cost the owner never agreed to and cannot undo.
- **The engage entry and the release entry are paired by an opaque throttle key in `details`**,
  `window_key` (**a1p**'s name) — a per-container, per-window value derived from the bucket that
  engaged (§11.0), never the key itself,
  rotating with the window. It correlates the entries of one sweep and correlates nothing across
  time, which is the whole of what pairing needs. **Row (h) carries the same per-window key**,
  derived the same way from `/authorize`'s container-global bucket (§12), so a tally joins the
  engage and release pair of that bucket's window.

**Which rows carry `none`. a1p**, binding item 34, which names the value and not its rows: (a), (b),
(e), (h) and **every** (d) carry `none`; (f) and (g) carry `interactive`. (a) fires before its
session exists, (b) is not an owner act, and (e) and (h) have no caller. (d) is uniform across all
seven causes, although five are reached only inside a session, so that a reader cannot infer from
the principal which cause a uniform page had, or whether a throttled caller held a session. (f) and (g) are not
uniform pages and are reached only inside a session, where `interactive` is available and true.

`none` is in `capabilities.md` §3 and `_types.py`'s `Principal` — an audit entry's principal only,
never a token's (`TokenPrincipal`) — and `events.md` §2's entry description states the above.
Nothing on any page depends on any of it; `consent.md` §14.8 says so in its own words.

## 13 · What this document does not fix

The token's own shape, coverage, role bundles and human-only acts → `capabilities.md`, **including
`consent.md` §14 item 10 — what `publish` renders as on the consent screen** — routed rather than
answered in §11 because the screen renders `publish` in the same vocabulary as the other five
(§11.2), so the string is only as true as the capability's boundary and `capabilities.md` §1 marks
that boundary open. A consent screen may not promise a boundary the capability contract has not
drawn. That closes §14's list: every item is now cited by number somewhere in Part B — §11.2 above
carries item 3's render half, §7 its vocabulary half — and Part B answers or routes each. Containers,
the chain, serving policy and the gate → `container.md`. The event list and the hash chain →
`events.md`; **#68** (§9.3's effects) and **#86** (§12's rows) were settled in the one 0.3
sitting; §12's and §9.3's names are in `events.md` §1. The MCP-specific surface → contract v1.1
at the Phase 5 boundary (§4). The step-up tap's endpoints, token shape and window mechanics → Phase
2.2 and `spec/design/step-up-tap-and-pending-approval.md`; §10.5's `[LEAN]` fixes none of them, and
§10.4's backstop is written in terms of *a live presence window* so that it does not depend on how the
tap is reached. The *look* of §11's pages — regions, states, copy, every string — is
`spec/design/consent.md`; this document fixes what they must be true about, never how they read.

**The flagship's permissions dashboard is not this document's surface**, and §11.9 is the boundary:
the dashboard reaches this AS as a browser client from a separate origin, so it holds no session on
the container's pages. Under **[0.3 · 11]** it can revoke the token it holds through §9.2's endpoint
and nothing else, so `consent.md` §19's broader revoke sentence is a spec revision (§11.9).

TODO(a1p): **nothing says where the AS's own state is persisted.** Client registrations,
authorization codes, pending device authorizations, refresh-token chains, §11.4's decided-request
records, §12's throttle counters and §10.1's interactive sessions are all durable state this document
requires and `storage.md` §3 does not name a method group for — the same shape as `container.md`
§8's open question about the config object, and the same reason it matters: state that Trust does
not own is state that can be edited around Trust. The last three are Part B's additions to the list
and the sharpest cases, because a session store editable around Trust forges presence, a throttle
counter editable around Trust removes §12's only bound on the chain, and a decided-request record
editable around Trust un-decides an authorization. a1p's reading is that all of it is
`ContainerState` by F3's rule (it is never delegated to a pluggable backend), but F3 was written
before this surface existed and should be asked, not assumed. The 0.3 review or the #30
consolidation pass should settle it.
