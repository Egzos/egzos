# Security Policy

## Reporting a vulnerability

Report privately via **GitHub Security Advisories**.

Go to: Security → Report a vulnerability (https://github.com/Egzos/egzos/security/advisories/new)

Do not open a public issue with a reproduction. A public issue with a repro is a zero-day disclosure. Use the advisory mechanism so the finding stays private until a fix is in place.

## Disclosure mechanics

This repository is public from Phase 0 (§L of the decisions log, `docs/build/egzos-decisions-v0.6-amendments.txt`). The disclosure split exists for that reason:

- **Security findings** live as private GitHub Security Advisories with the reproduction attached there. The regression test enters `adversarial/` only in the fix PR, at which point it flips from absent to passing. Before the fix lands, the repro stays out of the public tree.
- **Non-security findings** (contract gaps, behavior bugs) use the xfail pattern: an `@pytest.mark.xfail_finding` test plus a public issue. The fix PR flips the marker to passing.

An xfail with a repro in this public repository is a zero-day disclosure. That distinction is the whole reason for the split.

## Scope

The following surfaces are in scope:

- The container (context store, trust engine, audit ledger)
- The CLI (`egzos` and all subcommands)
- The MCP server (stdio transport; remote transport in Phase 5)
- The container's OAuth 2.1 authorization server (auth-code + PKCE, device-code, client registration, redirect-URI allowlist, AS metadata)
- The lifeboat UI (server-rendered, in-process)
- The `.xmb` export/import surface

## Pre-release status

egzos is pre-alpha. No product code has landed yet. The walking skeleton is Phase 0.1. Findings against the scaffold (boilerplate, stub code) are unlikely to be actionable but will be triaged.

## No bounty program

There is no bug bounty program at this stage. We cannot pay for findings, but we will credit researchers in the advisory and changelog when a fix ships.

## Contact

Use GitHub Security Advisories (link above). The Chief reviews all advisories.
