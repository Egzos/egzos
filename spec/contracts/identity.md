# Contract · identity — the container as a resource server

**Status: contract v1.1, law from the Chief's merge of the commit that adds this file.** It carries the
Chief's decisions of 2026-10-22/23 (`docs/build/egzos-decisions-v0.7-amendments.txt` §R–§U) into the
contract set, and **retires `authorization-server.md`** (§9). One login takes effect with this merge:
`CLAUDE.md`'s transition clause in `Egzos/egzos-platform` points here.

**Derivation.** No running shape yet: the walking skeleton accepts only its own `Token` (the CLI,
stdio MCP, the lifeboat). Every clause is derived from the v0.7 decisions and from Supabase Auth's
published behaviour (asymmetric JWT signing with a public JWKS; an OAuth 2.1 server for third-party
clients whose access tokens carry a `client_id` claim; no RFC 8707 resource indicators). Clauses carry:

- **decided** — the Chief's v0.7 decision, cited by section. The wording may improve; the decision may not
  change here.
- **a1p** — the operator's binding of a decision onto the container, a proposal the review reads as one.
- **carried** — a frozen clause from another contract, restated here because this document now governs
  the surface it was written for.

## 1 · Two credentials, one door

The container issues no credential over the network. **decided** (§S: its own authorization server is
retired). A request reaches it with one of two:

1. **The container's own `Token`** (`capabilities.md` §5): the owner token `init` mints, and tokens
   minted with `token mint`. Used by the CLI, MCP over stdio and the lifeboat, and accepted at the REST
   door. Unchanged. **carried.**
2. **An access token signed by the container's identity provider**: Supabase Auth, the egzos project for
   a container egzos hosts, the owner's own for a self-hosted one (§S). A person's token, issued to this
   container's own client, and an agent's OAuth token are both this kind, and each is bound to this one
   container (§3a). **decided** (§S, §T, and §AA for the binding).

A container with no identity provider configured (§2) accepts only the first, and is exactly the
container that runs today. **a1p.**

## 2 · Configuration

Six keys join the container-config object (`container.md` §8), changed by the same `admin` act and
recorded by the same `config.set`. None holds a secret: the provider's keys are public (§3), and the
container's client is a public client. **a1p**, all six. They enter `container.md` §8's table and
`_types.py`'s `ContainerConfig` with the code that reads them, as that table's conformance test
requires.

| key | default | what it is |
|---|---|---|
| `identity.issuer` | absent | the provider's issuer URL, e.g. `https://<project>.supabase.co/auth/v1`. Absent: no provider (§1) |
| `identity.client_id` | absent | this container's own OAuth client at the provider (§3a), registered when the container is linked to it |
| `identity.audience` | `authenticated` | the `aud` value an access token must carry |
| `identity.algorithms` | `ES256 RS256` | the signing algorithms accepted. Never `none`, never a symmetric `HS*` |
| `identity.browser_origins` | `https://egzos.io` | origins the REST door answers CORS for (§6) |
| `confirm.allow_button` | `true` | whether the confirm accepts the button proof (§5); `false` requires `biometric` |

**Symmetric signing is refused outright.** An `HS256` token can only be checked with the provider's
shared secret, which would put that secret in every container. A project still on a shared secret must
move to asymmetric keys before a container trusts it. **a1p.**

## 3 · Verification

Every request bearing a provider token is checked **in this order, on every request** (no verdict is
cached past the token's own `exp`). **decided** for the checks (§S; a1r on #281: issuer, signature
against a fixed algorithm list, audience, expiry, an ungranted user and an unregistered client), **a1p**
for the order.

1. **Signature.** The token's `kid` names a key in the provider's JWKS (`{issuer}/.well-known/jwks.json`),
   that key's algorithm is in `identity.algorithms`, and the signature verifies under it with a maintained
   JWT library. The algorithm is taken from the key, never from the token header alone. The JWKS is
   cached and re-fetched on an unknown `kid` at most once a minute.
2. **Issuer.** `iss` equals `identity.issuer`, byte for byte.
3. **Audience.** `aud` is, or contains, `identity.audience`.
4. **Time.** `exp` is in the future and `iat` is not, each with at most 60 seconds of skew.
5. **Subject.** `sub` is present: the provider's user id.
6. **Binding.** The token carries `client_id`, and it names **this** container: either it equals
   `identity.client_id` (a person using this container), or it names a live agent registration made
   here (§4). A token with no `client_id` — a provider session issued to egzos.io itself — is refused,
   because it is not bound to any one container (§3a).
7. **Grant.** §4 finds a live user grant for `sub`; for an agent, its registration is live too.

**Every failure is one answer**: `rest.md` §2's `401`, byte-identical whether the header was missing,
the signature bad, the issuer foreign, the audience wrong, the token expired, the token bound to another
container or to none, the user never granted or the client never registered. **decided**
(`capabilities.md` §6 clause 1; §S: an unregistered client is refused like an unknown token). Every
account in the provider holds a validly signed session, so check 7 is what keeps a stranger with a real
egzos account out of someone else's container.

### 3a · Every token is bound to one container

**decided** (v0.7 §AA, which amends §S's mapping and §T's "the browser presents the session directly";
recorded on a1r's and a6's review of #282), and the reason for check 6. A provider session is valid at every
container that trusts the provider, and the shared audience (`authenticated`) does not tell containers
apart; the provider issues no resource indicators. A container that received a person's session could
therefore present it at another container the same person can reach. So no container accepts a bare
session. Each token is bound to one container through the provider's own OAuth 2.1 server:

- **Each container is a public OAuth client of the provider** (`identity.client_id`), registered when the
  container is linked to it. Its redirect URIs are exactly two full URIs, matched exactly — egzos.io's
  callback, `https://egzos.io/oauth/callback`, and the container's own, `<container origin>/oauth/callback`
  — never an origin, a prefix or a pattern, so an open redirect elsewhere on either origin cannot receive
  a code. PKCE with `code_challenge_method=S256` is required; `plain` is refused. **a1p** (a6 on #282).
- **A person reaches a container with a token issued to that container's client.** egzos.io runs the
  authorization-code flow with PKCE for the container's `client_id`; the consent page egzos.io hosts
  approves a person's own containers without asking again. One sign-in still covers every container:
  no second password, no second login (§T). The token is presented only to the container it names.
- **An agent's token is bound by its own registration, and a `client_id` is registered on one container
  only.** MCP clients register with the provider per resource (`/mcp` of one container, §7), but the
  binding cannot rest on clients behaving: every agent authorization passes through the consent page
  egzos.io hosts, which records the container it registered a `client_id` on and refuses that
  `client_id` for any other container, and a container registers a `client_id` only from that page's
  request, under the confirm (§4). A self-hosted provider with its own consent page owes the same
  rule, and the checks `rest.md` §4.3 lists before it calls the container. **a1p** (a1r on #282). A
  container accepts only a `client_id` registered here.
- **A token for one container is refused at every other**, at check 6, with the one `401`.
- **A container-bound token is not a provider session.** It is presented only to the container it
  names: never to the provider's authorization, consent or account endpoints, and a container never
  forwards a caller's token anywhere, the provider included. A provider whose consent endpoint
  accepted such a token would let any container that receives a person's token approve a sign-in in
  that person's name, for that person's other containers, and be handed the code. So the consent page
  egzos.io hosts acts with egzos.io's own first-party session (a token with no `client_id`, which
  every container refuses at check 6), and a container reads nothing from the provider with a
  caller's token (`rest.md` §4.3). **a1p** (a6 on #285). `TODO(a1p)`, #283: confirm, before the door
  ships, that Supabase's consent endpoints refuse an access token carrying a `client_id`; if they
  accept one, this binding does not hold against a hostile container, and the Chief decides before
  the door ships.

**A failed check appends no entry of its own**: the request is unauthenticated (`rest.md` §2 clauses 5
and 6), and the container appends no entry naming a caller it could not verify, whichever check failed.
The `rest` throttle counts it and the window's `rest.tally` records it (`rest.md` §2 clause 7), so a
sweep with forged, foreign, unbound or ungranted tokens leaves its trace there. An unauthenticated
request at `/mcp` (§7) counts under the same surface word, `rest`: one door, one throttle. **a1p.**

**Attribution of a verified provider token** (`events.md` §2: every entry names its `actor`). A person:
`actor` is `user:<sub>`. An agent: `actor` is `agent:<client_id>`, and `details.for` is `user:<sub>`,
the user it acted for, so "who read this" names both. `principal` is `interactive` or `client` as §4
maps it. A container `Token` keeps its owner as `actor`, as today. **a1p** (a1r on #282).

## 4 · Grants: who may do what here

The provider proves *who*; the container alone decides *what*. **decided** (§T: a subscription is not an
authorization; the container decides what a session may do). Two records, kept in `ContainerState` and
never delegated (F3):

```
UserGrant          { sub, name, capabilities, scopes, created_at, revoked }
AgentRegistration  { client_id, sub, name, capabilities, scopes, created_at, revoked }
```

- **The owner's grant.** A container egzos provisions gets it at provisioning: the provider user who
  created it, all six capabilities, `["*"]`. A container made by `init` (a local, or a self-hosted one)
  has no provider user until its owner links it: the link is run by the holder of the owner `Token`
  (the CLI), and it registers the container's client (§3a) and writes the owner's grant for the `sub`
  the owner signs in as. **a1p.**
- **The owner cannot be locked out.** The last live grant holding `admin` over `["*"]` cannot be
  revoked; the owner `Token` from `init` stays the way back in. **a1p.**
- **Every other grant and registration is an admin's act**, under `admin`, from an interactive
  principal, **and it requires the confirm** (§5): a grant or a registration widens who can see
  everything it covers, so it is gated like a move that widens an audience (§U), never a silent write.
  A role bundle is expanded at grant time, as it is at mint (`capabilities.md` §2). **a1p.**
- **An agent registration is how an agent gets in.** When an agent signs in through the provider's OAuth
  server, the consent page egzos.io hosts — a security surface, whose anti-phishing shape (telling the
  requesting client's real identity and scopes apart from a deceptively named registrant) is A2's to
  design and a6's to review (`design-gap` Egzos/egzos-platform#117) — shows the request in `token ls`
  vocabulary; approving it (with the confirm) writes the registration here before the provider is told
  to issue. Its route is `rest.md` §4.3. Without the registration the provider's token is refused at
  checks 6 and 7. **a1p.**
- **Principal.** A token whose `client_id` is this container's own (`identity.client_id`) is a person:
  `principal: interactive`. A token whose `client_id` names a registered agent is that agent acting for
  the user: `principal: client`. **a1p**, onto `capabilities.md` §3.
- **An agent registration serves the one user who approved it.** It carries that user's `sub`, and a
  token naming the registration's `client_id` with any other `sub` is refused at check 7: another user
  who authorizes the same agent at the provider gets nothing until a registration serving them exists.
  **a1p** (a1r on #282). In v1.1 a registration serves the admin who approves it (`rest.md` §4.3);
  an agent serving another granted person is later work.
- **What a request may do.** For a session: the user grant's capabilities and scopes. For an agent: the
  registration's, **intersected** with the user grant's — an agent never holds more than the user it acts
  for. Coverage is computed down the path at check time, as for a `Token` (`capabilities.md` §5).
  **a1p.**
- **Audience** (`capabilities.md` §5) is every live `Token`, user grant and agent registration whose
  coverage reaches a container. The gate computes its delta over all three. **a1p.**
- **Revocation** is an admin revoking a grant or a registration here, or the person a registration
  serves revoking it (narrowing is never gated), effective on the next request (check 7 runs every
  time); the last grant holding `admin` over `["*"]` is never revoked. Signing the user out at the
  provider ends their tokens at `exp`.
- **Events**: `identity.grant` and `identity.revoke`, each with `subject` the `sub` or `client_id`,
  `outcome`, `capabilities` and `scopes`; a refusal (`outcome: refused`, `reason: last_admin`,
  `rest.md` §4.3) carries no `capabilities` or `scopes`, since nothing changed hands. They enter
  `events.md` §1 with the code that appends them. **a1p.**

## 5 · The confirm — the presence backstop

`capabilities.md` §4's backstop — presence proven inside the window for every human-only act — is now
**the confirm**. **decided** (§U).

- **When.** Every human-only act (`gate.confirm`, `approve.pending`, `yes.consume`); every move or copy
  whose audience delta is non-empty: the person is shown, inline, who will newly see the item, and
  confirms (**decided**, §U, §V); and every user grant and agent registration (§4), which widen an
  audience the same way (**a1p**, a1r's finding 2 on #282).
- **Two proofs.**
  - `biometric` — a WebAuthn assertion with user verification **required**, from a credential the user
    registered with this container under an interactive principal, verified against the stored public
    key with a maintained WebAuthn library, over a challenge the container issued for this act and
    spends once. Face ID, Touch ID and Windows Hello are this proof. **decided** (§U), **a1p** the
    binding.
  - `button` — an explicit confirm, for a device with no user-verifying authenticator. **decided** (§U).
    **Only for a person with no registered credential**: once a person has registered one, every
    confirm of theirs needs the biometric proof, and the button is refused for them. Otherwise a
    stolen session would skip the biometric by pressing the button. On a device with no authenticator
    such a person confirms from another device of theirs, through WebAuthn's cross-device flow (a phone
    scanning the code the browser shows). **a1p** (a6 on #285). **A credential belongs to the origin
    it was made on** (its relying party, one of `identity.browser_origins`), and an assertion verifies
    only there. A person with a credential on one origin and none on another is refused the button
    on that other origin and cannot assert there either; they enrol there through recovery (`rest.md`
    §4.3), or confirm on the origin that holds their credential. Taken on purpose: the alternative is
    a button the thief of a session on the second origin could press. **a1p** (a1r on #290).
- **The button is refused to `principal: client`**, from either credential, always: an agent's token
  cannot confirm on the human's behalf. **decided** (§U, as amended on #281). That is all the refusal
  achieves. Software that drives a person's own browser session holds an `interactive` token
  (`capabilities.md` §4 records that gap) and can press a button; **the biometric proof is the real
  backstop**, and an owner who wants it everywhere sets `confirm.allow_button` to `false`. **a1p.**
- **The owner may require the stronger proof**: `confirm.allow_button` (§2) at `false` accepts only
  `biometric`. **a1p.**
- **The window** is `step_up.window_seconds`, per ring pair and manifest shape, unchanged. **carried**
  (`container.md` §8, R11).
- **The record.** The existing `step_up` event carries `details.proof`: `biometric` or `button`. The
  ledger shows the weaker proof for what it is. **decided** (§U).
- **The localhost tap is retired.** The lifeboat runs the same confirm: WebAuthn works on a loopback
  origin. **decided** (§U). Until the code lands, the MVP tap is what runs, a stated and dated gap.

## 6 · Browser clients and CORS

egzos.io calls the user's container cross-origin. **a1p**, closing `rest.md` §7's CORS question for the
door:

- An origin in `identity.browser_origins`, exactly, is answered with `Access-Control-Allow-Origin` set to
  that origin, `Vary: Origin`, `Access-Control-Allow-Headers: Authorization, Content-Type`, and the
  methods of the door. **No credentials mode**: the token is a header, never a cookie.
- **The CORS headers do not vary with the outcome.** For an allowed origin they are identical on a
  success, on `rest.md` §3's refusal and on its `401`, so a browser script learns from them nothing the
  body withholds.
- A preflight (`OPTIONS`) from an allowed origin gets `204` with the same headers **on every `/v1/` path,
  declared or not**, so a preflight does not map the routes. From any other origin it gets `rest.md` §3's
  refusal, with no CORS header.
- Any other origin gets no CORS header on any answer. Non-browser callers are unaffected.

## 7 · Agents over HTTP (MCP)

An agent that is not on the user's machine reaches the container over MCP's Streamable HTTP transport
at `/mcp`. **decided** (§S), **a1p** the binding:

- The container publishes protected-resource metadata (RFC 9728) at
  `/.well-known/oauth-protected-resource`: `resource` its own origin, `authorization_servers`
  `[identity.issuer]`. Nothing in it is secret or varies by caller.
- An unauthenticated MCP request gets `401` with `WWW-Authenticate: Bearer resource_metadata="<that
  URL>"`, identical for every unauthenticated case (§3).
- The agent registers with and signs in through the provider's OAuth server, then presents its token
  here; §3 and §4 decide the rest. MCP over stdio is unchanged.

## 8 · Places

A local (a laptop, a desktop) with no provider keeps working offline on its own `Token`. To push to or
pull from its cloud (§V), its owner signs in through the cloud's provider like any client. Push and pull
are `storage.md`'s, in the contract version that carries §V. **a1p.**

## 9 · What this retires, and what it does not fix

- **`authorization-server.md` is retired** (§S): its endpoints, pages, device-code flow, client registry,
  throttle and state no longer bind a builder. The document stays as the record of what was frozen at 0.3.
  Its code (`src/egzos/authz/**`, never mounted) and its tables (`storage.md` §3.1's `ASState`,
  `ASGateState`) are removed, ahead of the PR that lands §3, but for three things a living surface
  still runs on: the MVP tap (`authz/presence.py`) and its two value helpers (`authz/values.py`),
  which go when §5's confirm lands, and the throttle counters the door runs on (`rest.md` §2 item 7),
  now `storage.md` §3.1's `ThrottleState`. No deployment holds a token it issued.
- **Double login is retired** (§T). One sign-in at egzos.io covers every container, through a token
  bound to each (§3a); no container accepts a bare provider session.
- **Not fixed here:** the REST routes and their shapes, copy, upload and the agent reads (`rest.md`
  §4–§4.4), places and push/pull (`storage.md`, the §V contract), billing (egzos-platform).
