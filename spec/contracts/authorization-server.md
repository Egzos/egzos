# Contract · the container's authorization server (core mechanics)

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

Clauses carry one of three markings instead:

- **§K** — carried from a `[DECIDED]` paragraph of §K. The wording may be improved; the decision may
  not be changed here.
- **a1p** — a1p's binding of a §K decision onto the already-drafted contracts, or onto OAuth 2.1
  where §K names a standard and stops. Reviewable, and the review should read it as a proposal.
- `[OPEN→0.3]` — the freeze review must settle it. Not decided here, deliberately.

**Scope of this document.** The AS core mechanics: the client types, the two flows, registration and
the redirect allowlist, metadata discovery, the grant vocabulary, the separation of authorities, and
revocation. The **consent screen, the step-up pages and presence composition** are issue #61 and
append to this file — see §10. `container.md` fixes everything about the container *except* how a
client obtains a token; this document fixes only that, and neither overrides the other.

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
omission. `[OPEN→0.3]` if the review wants a confidential type reserved for a future server-side
integration, it must say so now: adding one after the freeze widens the trust model.

### Device-code in a browser is retired

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

`[OPEN→0.3]` **Code lifetime.** No source names one. OAuth 2.1's guidance is a maximum of ten
minutes, and one minute is achievable for a redirect that is already in flight. The review should
name a number rather than leave it to each implementation — an hour-long code is a different
security posture from a one-minute code, and both would satisfy every clause above.

**Response type.** `code` only. The implicit grant and the resource-owner-password grant do not
exist in this AS, are not advertised, and MUST be rejected. **a1p** — OAuth 2.1 removes both; said
here because "we implement OAuth 2.1" is a claim a reader cannot test and this sentence is.

**TLS.** Every AS endpoint is served over TLS, and this document grants no exception to that.
**a1p** — `serve --tls` is a3-doorman's surface; the requirement is this document's. §5's `http`
allowance is **not** an exception to this clause: it governs a *client's* registered redirect URI —
the client's own listener, on the same machine — and an AS endpoint is not a redirect URI. §5 says
so in its own words, and the two sections are consistent only if read that way.

`[OPEN→0.3]` **Whether a container on the user's own machine is exempt.** Read literally, the clause
above requires a personal laptop container to serve its own AS over TLS: a certificate story for
every local user, and a real requirement landing on `serve --tls`. TODO(a1p): **no source names
it.** §K's Phase 0.2 freeze constraints cover metadata, registration, PKCE, device-code and
revocation and say nothing about transport; build plan 5.3 gives Doorman `serve --tls` / ACME without
saying when TLS is mandatory; 6.3 names "localhost + TLS" as a coverage matrix, not a rule. The
review must pick one of three: TLS always; TLS except where the AS is bound to a loopback interface,
for **any** user and not only a developer; or TLS except in an explicitly enabled developer mode.
Until it does, this clause stands as written — failing closed, because a default that serves tokens
in the clear is the wrong way to be wrong.

## 3 · CLI and headless — device code

**Device-code is the CLI's native habitat, unchanged. §K.** A CLI has no redirect URI and no browser
origin to bind to; the device flow's trade is exactly the right one there, and §1's retirement is
about browsers only.

The endpoints are RFC 8628's: a **device authorization endpoint** issuing
`{device_code, user_code, verification_uri, verification_uri_complete, expires_in, interval}`, and
the token endpoint redeeming `urn:ietf:params:oauth:grant-type:device_code`. **a1p** — §K names
"device-code endpoints" as a freeze constraint and does not enumerate them; these are the standard's.

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

`[OPEN→0.3]` **`verification_uri_complete`.** Including the `user_code` in a URL removes the typing
step and with it most of the phishing surface the browser retirement was about — but it also makes
the code copy-pasteable into a chat window, which is the same mistake with fewer steps. No source
names it. The review should decide whether the AS issues it.

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
redirect_uris}` enters container config through an owner-authenticated path. **a1p** — no source
names the verb, and the CLI spelling belongs to a3-doorman, not to this document.

**Whether registering, amending or removing a client writes an audit event is `[OPEN→0.3]`, in §9's
marking and in #68.** It is named here because §5 is where a reader looks for it: this section's
exact-match rule is only as strong as the allowlist it compares against, so a change to that
allowlist is a change to the AS's security posture, and `events.md` §4 invariant 2 does not currently
name an event for it.

`[OPEN→0.3]` **Dynamic client registration** (RFC 7591) is what the MCP authorization spec expects
(§4), and an **open** registration endpoint on a personal container lets any caller create a client
entry. The two pull in opposite directions and the review must settle which wins before Phase 5
builds against either. The AS metadata's `registration_endpoint` (§6) is advertised only if the
answer is yes.

### The matching rule is exact string comparison

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

A registered URI is absolute and `https`, with the loopback exception stated next: it relaxes the
scheme to `http`, and — for the literal loopback address only — the port.

### The exception: loopback redirect URIs

**A registered loopback redirect URI matches with its port ignored and everything else exact. a1p**,
from RFC 8252 §7.3: a native or dev client binds to an ephemeral port it cannot know at registration
time, so the port is the one component that varies. The exception is bounded to:

- host is the **literal loopback address** — `127.0.0.1` or `[::1]`;
- scheme is `http` — and this relaxes the **redirect URI**, never an AS endpoint: §2 requires TLS on
  every AS endpoint and grants no exception to it;
- **only the port is ignored.** Path, query, scheme and host are compared exactly, as above.

**`localhost` as a hostname is permitted — as an exact registered string, including the port. a1p**,
binding §K's "localhost dev origins". RFC 8252 §8.3 prefers the literal IP precisely because
`localhost` resolves through a name, and a name is something a resolver, a hosts file or a hostile
network can move — so the name form gets the scheme relaxation and **no port exception**:
`http://localhost:<port>/…` matches only the exact string registered, port included, and a developer
registers the port they will actually bind. The port relaxation above stays bounded to `127.0.0.1`
and `[::1]`.

`[OPEN→0.3]` **Whether the hostname form is dropped entirely.** The clause above is a1p's binding,
not a §K decision, and it is the only part of this rule left open: A6 and the freeze may rule that
only the literal loopback address is registrable and `localhost` entries are refused. The scheme,
the port and the matching are settled above, because this is the difference between one hole and
none.

## 6 · AS metadata discovery

**AS metadata discovery is part of the frozen surface. §K** (a named Phase 0.2 freeze constraint).
The reason §K gives is the one that makes it a contract rather than a convenience: *"any UI, ours or
a fork's, authenticates to a container the same way."* A UI cannot be written against "the egzos
container" as a category unless every container announces itself identically — the metadata document
**is** the interoperability surface, and the rest of this document is only reachable through it.

**Endpoint:** `/.well-known/oauth-authorization-server`, at the container's own origin, served
**unauthenticated** over TLS (§2, whose `[OPEN→0.3]` governs any local exemption). **a1p** — RFC 8414's location; §K
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
| `revocation_endpoint` | §9 — `[OPEN→0.3]`; **advertised only if** the endpoint exists |
| `registration_endpoint` | §5 — **advertised only if** dynamic registration is enabled |
| `response_types_supported` | `["code"]` — and nothing else, ever (§2) |
| `grant_types_supported` | `["authorization_code", "refresh_token", "urn:ietf:params:oauth:grant-type:device_code"]` |
| `code_challenge_methods_supported` | `["S256"]` — `plain` is never advertised (§2) |
| `token_endpoint_auth_methods_supported` | `["none"]` — every client is public (§1) |
| `scopes_supported` | the six capability names (§7) |

**The metadata is a conformance surface, not a description.** A container MUST NOT advertise a
method, grant or endpoint it does not implement, and MUST NOT implement one it does not advertise —
a fork's UI reads this document *through* the metadata, so a mismatch is a conformance failure and
not a documentation bug.

**Two of the eleven rows are therefore conditional, and the table says which: `revocation_endpoint`
and `registration_endpoint`.** Both name an endpoint whose existence is an open question — §9's for
revocation, §5's for dynamic registration — and the clause above forbids advertising either until
the answer is yes. The other nine are unconditional: a container that omits one of them is
non-conforming. **a1p** — the distinction is stated rather than left to the reader because the field
list is what an implementation will copy, and copying a conditional row as an unconditional one is
exactly the mismatch this paragraph forbids. `AS_METADATA_FIELDS` in `src/egzos/_types.py` is the
whole vocabulary of eleven; `AS_METADATA_CONDITIONAL_FIELDS` names these two.

`[OPEN→0.3]` **Whether `scopes_supported` also advertises the `node:` form.** §7's node-scope
strings are container-specific by construction; listing the *prefix* reveals nothing, listing any
actual node id would break the "nothing container-specific" rule above. The review should say
`node:` is advertised as a form, or that it is not advertised at all and clients learn it from this
contract.

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
- **`node:<node-id>`** — a scope entry of `Token.scopes`. `node:*` is the whole container.

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
3. **`node:*` is the owner's grant.** `capabilities.md` §5 says `["*"]` is the owner's token; a
   client asking for `node:*` is asking for the whole container, and the consent screen must render
   it as that (#61).

### The AS is not an enumeration oracle

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
  nothing about any of them.

This applies to the device flow (§3) identically: a rejected device authorization reveals no more
than a rejected redirect does.

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

**Double login is the default posture. §K.** A deployment **MAY** configure its container to trust
`egzos.io`, or any IdP, as OIDC identity to collapse the two logins into one — **never the default.**

Stated as the document is required to state it, in terms an implementation can be tested against:

- the collapse ships **off**, in every distribution, including the flagship's hosted containers;
- it is enabled **only** by configuration inside the user's own container — there is no flagship-side
  switch, and no remote party can turn it on;
- **a container that collapses the two authorities without the owner having configured it to is
  non-conforming.** Not misconfigured: non-conforming.

`[OPEN→0.3]` The collapse is named by §K and not designed by it — which IdP claims map to which
container identity, and what happens to live tokens when the trust is withdrawn, are unanswered. The
review should either scope the collapse out of v1.0 explicitly or name the missing piece. It is not
drafted here, because a half-specified identity bridge is worse than an absent one.

## 9 · Issuance, revocation, rotation and expiry

**A token the AS issues writes `token.mint` (`events.md` §1), like any other mint. a1p** — §7 makes
an AS token a `Token` per `capabilities.md` §5, and a mint is a mint whether it came from
`token mint`, §2's code exchange or §3's device redemption. The event already exists, so this needs
no freeze decision; it is stated because an implementation conforming to this document alone would
otherwise complete an exchange and leave no trace in the chain.

**Revocation is `token rm`, like any other client. §K.** The flagship's token is removed by the same
verb, from the same list, with the same effect as a script's. There is no "sign out of egzos.io"
that is also a container revocation, and no container revocation that requires the flagship.

A revoked token is `capabilities.md` §5's: it holds **no** capabilities, and revocation is checked
**before** the capability set. `token.revoke` is written (`events.md` §1). **a1p** — the AS adds no
second revocation semantics, which is the point.

`[OPEN→0.3]` **Whether the AS exposes an RFC 7009 revocation endpoint at all.** §K names
"revocation" as a Phase 0.2 freeze constraint and answers it with one verb — *"revocation is
`token rm` like any client"* — which is an **owner** path, on the container's own CLI. §6 advertises
a `revocation_endpoint` and §6 also forbids advertising an endpoint a container does not implement,
so the metadata row and §9 cannot both stand as written. This is not cosmetic: **a browser or an MCP
client cannot run `token rm`**, so an HTTP endpoint is the only revocation path those two of §1's
three client types have. The review must pick one, and a1p does not pick for it:

1. **Define the endpoint, per RFC 7009.** `POST` to `revocation_endpoint` with `token` and an
   optional `token_type_hint`, over TLS (§2), with no client authentication because no client has a
   secret (§1, §6's `["none"]`). Two clauses would have to come with it, and both are this
   document's rather than the RFC's:
   - **The silence rule.** The endpoint returns **200 for an unknown, malformed or already-revoked
     token** — the same status, shape and time budget as for a token it really did revoke. RFC 7009
     asks for 200 on an invalid token; §7's "the AS is not an enumeration oracle" is why it is a
     MUST here, because an endpoint that answered differently would let any caller test whether a
     token value exists without holding one.
   - **Whether a client may revoke a token not issued to it.** a1p's reading, for the review to
     take or reject: the AS compares the presented token's `client` (`capabilities.md` §5) against
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

     **What a real bound would require**, if the review wants one instead of entropy: proof that
     the caller holds the *grant*, not the string. Three shapes, none of them free — a
     confidential client, which §1 forbids in v1.0 and which downloadable software cannot be
     anyway; a **sender-constrained** token (DPoP, RFC 9449), which binds revocation to a key the
     caller proves per request and is therefore a change to every token this AS issues rather than
     to this endpoint; or no endpoint at all, which is option 3. The cost of entropy-only is
     bounded and should be stated as what it is: a token value that leaks can be revoked by
     whoever holds it. That is a denial of service against *that* token's client and nothing
     wider — a revocation cannot widen a grant, reach another token, or reveal whether the value
     was live, which is what the silence rule above is for.
2. **Leave it `[OPEN→0.3]` and advertise the row conditionally** — which is what this document does,
   pending the review.
3. **Drop the row and say revocation is owner-path only in v1.0.** `token rm`, plus whatever the
   owner is given in a browser by #61's surface. The cost is explicit: a client cannot revoke its
   own token, and a UI's "log out" is a local forget, not a revocation — a stolen browser token
   stays live until the owner removes it from `token ls`.

**Until the review decides, this document takes (2).** `revocation_endpoint` is a conditional row in
§6, advertised only if the endpoint exists, and **no endpoint is defined here** — a container that
advertises one today is advertising something this contract does not specify. `token rm` is the
revocation *semantics* under every option: whatever the transport, a revoked token is
`capabilities.md` §5's and `token.revoke` is written.

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

`[OPEN→0.3]` **Whether rotation is an audit event, whether a denied or abandoned authorization is one
at all, and whether client registration is one.** `events.md` §1 closes its vocabulary by
construction — *"an appended event whose name is not in this list MUST be rejected"* — and §4
invariant 2 closes the other side: *"a surface that produces an effect without a corresponding event
is non-conforming."* The AS produces **six** effects with only two events between them.

**Registration (§5) is the sixth, and this document adds it to the question.** It is an owner act
that writes the redirect-URI allowlist — the one piece of container state that decides where an
authorization code may be delivered — and it currently leaves no entry in the chain. An allowlist
entry added quietly is §5's exact-match rule undone without a trace, and the chain is where that
would otherwise be visible; a registration is also, by §4 invariant 2's own vocabulary, closer to an
approval than to a read. Filed as **#68** for the 0.3 batch, so grant, deny, rotate and registration
are settled together with one edit to `events.md` rather than four. a1p's recommendation is on the
issue. **Not answered in this document.**

`[OPEN→0.3]` **Default access-token lifetime.** `capabilities.md` §5 permits `expires_at: null`, and
that is right for a long-lived script token the owner mints deliberately. It is **wrong as the AS
default for a public browser client**, and no source names a number. The review should name one —
a1p's reading is that an AS-issued public-client access token MUST carry a non-null `expires_at`,
whatever the value, and that the null case stays available to `token mint` only.

## 10 · What this document does not fix

**The consent screen, the step-up pages and presence composition are issue #61**, Part B, which
appends to this file: `/authorize` rendering the grant in `token ls` vocabulary, the in-process
server-rendered consent and step-up pages, and where `principal: interactive` is established for
browser sessions. §7 fixes what a grant may *contain*; #61 fixes how it is *shown* and what it
proves about presence.

The token's own shape, coverage, role bundles and human-only acts → `capabilities.md`. Containers,
the chain, serving policy and the gate → `container.md`. The event list and the hash chain →
`events.md`, plus **#68**. The MCP-specific surface → contract v1.1 at the Phase 5 boundary (§4).

TODO(a1p): **nothing says where the AS's own state is persisted.** Client registrations,
authorization codes, pending device authorizations and refresh-token chains are all durable state
this document requires and `storage.md` §3 does not name a method group for — the same shape as
`container.md` §8's open question about the config object, and the same reason it matters: state
that Trust does not own is state that can be edited around Trust. a1p's reading is that all of it is
`ContainerState` by F3's rule (it is never delegated to a pluggable backend), but F3 was written
before this surface existed and should be asked, not assumed. The 0.3 review or the #30
consolidation pass should settle it.
