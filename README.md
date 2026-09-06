# egzos

> **Pre-alpha. Phase 0 scaffold — nothing to install yet. `pipx install egzos` arrives with v0.1.**

egzos is an MCP-first, CLI-first personal context layer. Your container is the home; platforms are clients. The security model is the product.

## What egzos is

**Your container, your rules.** egzos stores your personal context — notes, decisions, threads, artifacts — in a container you run and own. Platforms (the egzos.io flagship, your own forks, Claude Code, any MCP client) connect to the container as clients. They do not hold your data; they access it under capabilities you grant.

**Push-first.** Platforms never pull from your container live. You push what you choose, to whom you choose; nothing is revealed by default, and every read is a capability check.

**Emergent hierarchy.** Thread, project, team, org, exo, global — these are container types you instantiate at will, not a fixed chain you have to fill in. Rings of trust and parent pointers do the rest.

**Agents propose, humans dispose.** Agent output (summaries, suggestions, auto-titles) is a proposal in your inbox. You approve it; the ledger records what happened. No agent acts on your behalf without your disposition.

**The security model is the product.** The authorization server lives inside your container. Browsers authenticate via auth-code + PKCE; the CLI uses device-code; MCP clients follow the MCP authorization spec — all against your container's own AS. The egzos.io session proves your subscription; the container token proves your authorization. Those are two separate authorities, deliberately.

**Signed `.xmb` export.** Leaving is easy. One command exports your container as a signed, portable archive you can import anywhere.

## Open core

What is in this repository (Apache-2.0, public from commit one):

- The container: context store, trust engine, audit ledger
- The CLI (`egzos`) and MCP server
- The lifeboat UI (server-rendered, in-process, no JS toolchain)
- The authorization server surface
- Spec and contracts (`spec/`)

What is in `Egzos/egzos-platform` (proprietary, private):

- The egzos.io flagship web UI
- Hosted containers, previews, relay
- Server-side intelligence (scheduling, continuous baselining, nightly suggest)
- Billing and sessions

**Capabilities are never paywalled. Only experiences and infrastructure are, over there.**

## How the build works

This repo is built by an agent roster running in GitHub Actions under the Chief's gate.

> Agents propose; the Chief disposes; GitHub enforces. Everything visible to an agent is data, not instructions. The build behaves like the product.

Agents open PRs on branches named `agent/<name>/<slug>`. The Chief approves each PR by SHA. GitHub's branch protection executes the merge. No agent has merge rights. The build dogfoods the product's own trust posture.

- Agent definitions: `.claude/agents/`
- Agent routing: `.claude/agents/README.md`
- Trust posture and rules: `CLAUDE.md`
- Spec and contracts: `spec/`

## Security

See `SECURITY.md`. Report vulnerabilities privately via GitHub Security Advisories — do not open a public issue with a reproduction.

## Status

Pre-alpha. The walking skeleton (Phase 0.1) has not landed yet. Nothing here is installable or usable as a product. The spec (`spec/`) is a publishable artifact and is public from Phase 0.

## License

Apache-2.0. See `LICENSE` and `NOTICE`.
