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
speaks to every other the same way — that is what the rest of §6 is for.

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

**TLS.** Every AS endpoint is served over TLS, with the single exception of loopback origins on a
developer's own machine (§5). `serve --tls` is a3-doorman's surface; the requirement is this
document's. **a1p**.

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
