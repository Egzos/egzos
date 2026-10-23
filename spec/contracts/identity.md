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
   a container egzos hosts, the owner's own for a self-hosted one (§S). A user's session token and an
   agent's OAuth token are both this kind. **decided** (§S, §T).

A container with no identity provider configured (§2) accepts only the first, and is exactly the
container that runs today. **a1p.**

## 2 · Configuration

Five keys join the container-config object (`container.md` §8), changed by the same `admin` act and
recorded by the same `config.set`. None holds a secret: the provider's keys are public (§3). **a1p**, all
five. They enter `container.md` §8's table and `_types.py`'s `ContainerConfig` with the code that reads
them, as that table's conformance test requires.

| key | default | what it is |
|---|---|---|
| `identity.issuer` | absent | the provider's issuer URL, e.g. `https://<project>.supabase.co/auth/v1`. Absent: no provider (§1) |
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
6. **Grant.** §4 finds a live user grant for `sub`; and, when the token carries `client_id`, a live agent
   registration for that `client_id` too.

**Every failure is one answer**: `rest.md` §2's `401`, byte-identical whether the header was missing,
the signature bad, the issuer foreign, the audience wrong, the token expired, the user never granted or
the client never registered. **decided** (`capabilities.md` §6 clause 1; §S: an unregistered client is
refused like an unknown token). Every account in the provider holds a validly signed session, so check 6
is what keeps a stranger with a real egzos account out of someone else's container.

**The audit entry may say which check failed; the response may not** (`capabilities.md` §6 clause 3).
**carried.**

## 4 · Grants: who may do what here

The provider proves *who*; the container alone decides *what*. **decided** (§T: a subscription is not an
authorization; the container decides what a session may do). Two records, kept in `ContainerState` and
never delegated (F3):

```
UserGrant          { sub, capabilities, scopes, created_at, revoked }
AgentRegistration  { client_id, name, capabilities, scopes, created_at, revoked }
```

- **The owner's grant** is written when the container is provisioned: the provider user who created it,
  all six capabilities, `["*"]`. **a1p.**
- **Every other grant and registration is the owner's act**, under `admin`, from an interactive
  principal. A role bundle is expanded at grant time, as it is at mint (`capabilities.md` §2). **a1p.**
- **An agent registration is how an agent gets in.** When an agent signs in through the provider's OAuth
  server, the consent page egzos.io hosts shows the request in `token ls` vocabulary; approving it writes
  the registration here (`POST /v1/agents`, `rest.md`) before the provider is told to issue. Without the
  registration the provider's token is refused at check 6. **a1p.**
- **Principal.** A token without `client_id` is a user's own session: `principal: interactive`. A token
  with one is an agent acting for that user: `principal: client`. **a1p**, onto `capabilities.md` §3.
- **What a request may do.** For a session: the user grant's capabilities and scopes. For an agent: the
  registration's, **intersected** with the user grant's — an agent never holds more than the user it acts
  for. Coverage is computed down the path at check time, as for a `Token` (`capabilities.md` §5).
  **a1p.**
- **Audience** (`capabilities.md` §5) is every live `Token`, user grant and agent registration whose
  coverage reaches a container. The gate computes its delta over all three. **a1p.**
- **Revocation** is the owner revoking a grant or a registration here, effective on the next request
  (check 6 runs every time). Signing the user out at the provider ends their tokens at `exp`.
- **Events**: `identity.grant` and `identity.revoke`, each with `subject` the `sub` or `client_id`,
  `capabilities` and `scopes`. They enter `events.md` §1 with the code that appends them. **a1p.**

## 5 · The confirm — the presence backstop

`capabilities.md` §4's backstop — presence proven inside the window for every human-only act — is now
**the confirm**. **decided** (§U).

- **When.** Every human-only act (`gate.confirm`, `approve.pending`, `yes.consume`), and every move or
  copy whose audience delta is non-empty: the person is shown, inline, who will newly see the item, and
  confirms. **decided** (§U, §V).
- **Two proofs.**
  - `biometric` — a WebAuthn assertion with user verification **required**, from a credential the user
    registered with this container under an interactive principal, verified against the stored public
    key with a maintained WebAuthn library, over a challenge the container issued for this act and
    spends once. Face ID, Touch ID and Windows Hello are this proof. **decided** (§U), **a1p** the
    binding.
  - `button` — an explicit confirm, for a device with no user-verifying authenticator. **decided** (§U).
- **The button is a human act: it is refused to `principal: client`**, from either credential, always.
  An agent driving a browser cannot confirm on the human's behalf. **decided** (§U, as amended on #281).
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
  `ASGateState`) are removed in the PR that lands §3. No deployment holds a token it issued.
- **Double login is retired** (§T). A container trusts its provider's session directly.
- **Not fixed here:** the REST routes and their shapes (`rest.md`), copy, upload and the agent reads
  (`rest.md`, next contract PR), places and push/pull (`storage.md`, the §V contract), billing (egzos-platform).
