# spec/contracts/

**Nothing is frozen yet.** The contract freeze happens at Phase 0.3, after A6 and the Chief review
the artifacts drafted in Phase 0.2. Until then, everything here is a draft.

## What arrives at Phase 0.2

a1p-planner drafts the following from the running walking skeleton (Phase 0.2):

- **ContextItem schema** — the canonical shape of a context item in the store
- **Container contract** — the full surface the container exposes, including:
  - The authorization-server surface:
    - Auth-code + PKCE endpoints (browsers and the flagship)
    - Device-code endpoints (CLI and headless clients)
    - MCP client authorization (per the MCP authorization spec; Phase 5)
    - Client registration and redirect-URI allowlist per container config,
      accommodating `egzos.io` and `localhost` dev origins
    - AS metadata discovery
- **Backend contract** — the interface between the store/vault and its persistence backend
- **Capability vocabulary** — the canonical capability names (`enterprise` omitted)
- **Event taxonomy** — all auditable events, including approvals
- **Typed stubs** — Python stubs derived from the contracts, committed alongside

## Interface rules the freeze must honor

These rules from the decisions log (§N, §K) constrain what the frozen contracts may say:

- Signed-URL issuance passes Trust's capability check — artifact download IS fetch; blob pulls
  are separate audit events; Store/Vault never mints a URL on its own authority.
- Writes land unverified; rules are served verified-only everywhere.
- Silence-not-errors — the API does not reveal what exists to a caller who cannot see it; no
  enumeration through error shapes.
- PKCE mandatory for all public clients (browsers and the flagship).
- AS metadata discovery is part of the frozen surface; any UI, ours or a fork's, authenticates
  to a container the same way.

## After the freeze

`spec/contracts/**` is law after Phase 0.3. Changing a frozen contract is an escalation issue to
a1p-planner, batched at phase boundaries. Contract v1.1 is planned at the Phase 5 boundary:
intelligence read surface + AS metadata; reviewed by the Chief, a1p-planner, and a6-adversary.

Never change a frozen contract as a drive-by. File the `contract-change` issue and take the next item.
