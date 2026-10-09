# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.1.0] — the open core's first release (2026-10-09)

Phase 2's milestone: the doors open. Everything in 0.1.0a1 below, hardened through review, plus:

### Added

- The lifeboat, `egzos web`, on its specified stack: FastAPI + Jinja + htmx, in-process, tokens as
  CSS variables. It renders list, search and the pending queue (#127).
- The authorization server's first mechanics in `egzos.authz` (#166 slices 1–2). These are
  storage-free and not yet served:
  - the scope grammar and grant lifetime;
  - PKCE (S256 only, constant-time);
  - the redirect allowlist, with `localhost` refused in every spelling;
  - the metadata document;
  - the `continue` allowlist and the loopback-only plain-HTTP rule;
  - issued values.
- Contracts v1.0, frozen at 0.3 (below), with the REST door and the authorization server's state as
  drafts for Phase 5.

### Security

- A proposal is decided once under racing deciders, and the decider is re-checked under the lock
  (#146, #149, #151).
- The audit chain refuses an unattributed append. Its principal vocabulary is closed to
  `interactive`, `client` and `none`, and the five caller-less events carry `none` and only `none`
  (#151, #160, #162).
- Minting refuses a principal outside the token vocabulary (#154).
- Consent pages send `Referrer-Policy: same-origin` (#146).

### Changed

- Published to PyPI: `pipx install egzos` (or `uv tool install egzos`, or `pip install egzos` in a
  virtualenv). Publishing is trusted (OIDC), with no stored token, and runs when the Chief publishes a
  GitHub release (`.github/workflows/release.yml`). Or install from the release tag:
  `pipx install "git+https://github.com/Egzos/egzos@v0.1.0"`.

## Contracts v1.0 — post-freeze status changes

### Added

- `spec/contracts/rest.md`: the REST door contract, **draft** at the Phase 2 boundary (#42), for
  the Chief's and a6's review before any builder implements against it.
- `storage.md` §3.1: the authorization server's state as `ASState` and `ASGateState`, **draft**
  binding beside the frozen `ContainerState`, with the partition as a TODO(chief) (#173).

### Changed

- `rest.md` §2, §6, `events.md`, `authorization-server.md` §12 and `_types.py`: the Chief's #165
  answers — a `BlobGrant` is single use with a fixed 300-second lifetime, and the REST door gets
  the `rest` throttle surface and the caller-less `rest.tally` event (rates open on #141).
- `events.md` §2: the converse principal rule (the five `PRINCIPAL_NONE_EVENTS` carry `none` and
  nothing else) moves from decided, not running to running, citing the ledger check (#160, #159).

### Fixed

- `_types.ClientRegistration` docstring: states the frozen rule that registration refuses a
  `localhost` redirect host in any spelling, with or without a port ([0.3 · 22]), replacing the
  overruled draft sentence (#174).

## Contracts v1.0 — frozen at 0.3 (Chief, 2026-10-08)

### Added

- `spec/contracts/`: the Phase 0.2 draft set, drafted from the walking skeleton's running shapes
  (#25–#30) — `context-item.md`, `capabilities.md`, `events.md`, `storage.md`, `container.md` and
  the prose-derived `authorization-server.md` — with typed stubs in `src/egzos/_types.py`.
- The Chief's 45-item freeze record (#31, 2026-10-03) written into the text as `[0.3 · N]`
  clauses (#109: #111, #139, #147, #152 and this pass). No open→0.3 marking remains in
  `spec/contracts/` or `src/`; the design specs still carry the retired marker, and design-gap
  #157 tracks their revision by A2.
- `spec/contracts/README.md` is the index of the set; each document's status line reads frozen at
  0.3. The Chief's merge declares the freeze. Contract v1.1 is planned at the Phase 5 boundary.

### Changed

- `container.md` §2: an ambiguous path tail is refused with the caller-visible matches named,
  never picked by recency (item 1, as revised by the Chief).
- `_types.py`: `__all__` is isort-sorted, pinned by ruff RUF022 (#30).

## [0.1.0a1] — MVP preview (2026-10-03)

### Added

- The walking skeleton's modules land as the MVP's running core: nodes, items and blobs (store),
  trust engine and the gate, hash-chained ledger, resolver, tokens, the CLI and the MCP stdio door.
- `egzos connect [claude-code] [--apply]`: mints a client token (never admin) and registers the MCP
  server with Claude Code at user scope.
- The container home is owner-only (0700): it holds the chain, every item and the token hashes.
- The presence tap (`egzos.authz.presence`): `egzos trust approve` / `trust deny` open a one-shot
  loopback decision page — *Sign and approve* → *Confirm signature* within 10 s, *Approve without a
  window*, or *Deny*. Every check appends `step_up` with its outcome. A signature opens a window
  for that ring pair bounded to the signed shape, read back from the chain, for
  `step_up.window_seconds` (the contract's default 300; `EGZOS_STEP_UP_WINDOW_SECONDS=0` makes
  every act tap); `egzos trust close-window` ends it. An act lands whole or not at all.
- Token values are 256 random bits, stored only as a hash; the id is public (freeze item 19).
  `egzos token revoke <id>` takes a client token back, in a running `serve --mcp` too: the door
  re-reads its token on every call. A token past its `expires_at` is not live.
- The gate: `organize` for a silent move, `publish` to propose a widening one; a manifest drift is
  `approval.stale` (freeze items 3, 39); an ambiguous path is refused with its matches named, never picked (item 1, as revised).

### Security

- Minting is the owner's act (`connect`, `token create`, `Auth.mint`); the owner's views (`trust
  pending`, `token ls`, `audit`) refuse a client principal; `ls` checks coverage.
- The MCP door answers identically for a scope that does not exist and one the token cannot see.
- `egzos_fetch` fences each item with a fresh per-response nonce, so a body cannot forge the
  delimiters that mark where its data ends.
- An open presence window carries out what was asked: `trust deny` under a window denies.
- Every MCP probe of a scope the token cannot see is on the chain, whichever tool asked.
- `ls` and `trust pending` are audited reads; `blob_pull` checks coverage.
- The tap's one-shot URL is printed only to a terminal, never to an agent's pipe.
- Coverage is checked in the engine (`resolve_ref`, node creation, moves, quarantine, the resolver)
  and on every CLI scope and item reference; a client's `ls` and the MCP inbox are served under the
  serving policy; `%n` belongs to the token whose `find` made it; `connect` prints its secret only
  to a terminal.
- The audit chain cannot fork: one successor per entry, and a writer that loses the race re-chains.
- A proposal goes stale if an item moved since it was filed; POSTs without an `Origin` are refused.

### Changed

- Opus-tier agents run on Opus 5.5 (`claude-opus-5-5`).

## [Unreleased] — Phase 0.0 scaffold

### Added

- Repository scaffold: `LICENSE` (Apache-2.0), `NOTICE`, `README.md`, `SECURITY.md`, `CONTRIBUTING.md`
- `pyproject.toml`: packaging stub (hatchling backend, version `0.0.0a0`, `egzos` entry point)
- `src/egzos/__init__.py`, `src/egzos/_types.py`, `src/egzos/py.typed`
- `src/egzos/cli/__init__.py`, `src/egzos/cli/__main__.py`: CLI stub
- `tests/conftest.py`, `tests/test_smoke.py`, `tests/fixtures/README.md`
- `adversarial/README.md`, `adversarial/conftest.py`
- `.gitignore`
- `.github/PULL_REQUEST_TEMPLATE.md`
- `.github/ISSUE_TEMPLATE/` (config, task, design-gap, contract-change, plan-request)
- `spec/README.md`, `spec/contracts/README.md`
- `spec/design/README.md`, `spec/design/DESIGN-PRINCIPLES.md`, `spec/design/DESIGN-SOURCES.md`
- `docs/README.md`, `docs/build/README.md`
- `docs/build/REVIEW-DECISIONS.md`: review decision register and methodology
- `.github/scripts/post_review_comment.sh`: deterministic review comment formatting across workflows
- Allowed bots allowlist for the forge identity in review workflows

### Changed

- Model pins: Fable 5.1 → Opus 5 for every frontier-tier agent (a1p-planner, a1r-reviewer, a2-conformance, a3-doorman, a3-trust, a6-adversary)
- Workflow prompt delivery: charter now appended to system prompt instead of `--agent` flag
- Dependabot early-pass: review checks pass early on Dependabot PRs (no secrets; the Chief reviews pin-bump diffs directly)
- Platform sibling references: egzos-platform visibility wording and contract parity notes
- Agent documentation: references clarified from "21st MCP" to "21st CLI"
- Ownership map (#32): a1p-planner given a writable test path for `src/egzos/_types.py` (`tests/_types/**`, named to avoid colliding with the stdlib `types` module) and for the previously-unowned `tests/test_smoke.py`; `.github/OWNERSHIP.yml` itself added to `chief_only`, hard-enforced since #38 resolves both the checker and the map from the base ref rather than the PR's own tree; `.claude/agents/a1p-planner.md`'s `Owns` line updated to match

### Fixed

- A6 disclosure: one job per required check name (visibility-agnostic disclosure rationale)
- Action SHA-pins: bumped actions/checkout, actions/setup-python, actions/create-github-app-token, actions/stale to latest resolved SHAs
- CLAUDE.md: Dependabot pin-bump rule now documented
- Contract text, drift report #10 findings F6–F10, F13, F14 and F25 (#102, Phase 0.2 corrections — no contract is frozen yet):
  - `container.md` §8: the dotted keys are canonical on the wire, and `_types.py` carries one named mapping (`CONTAINER_CONFIG_FIELD_FROM_WIRE_KEY`) to its underscored `ContainerConfig` fields (F6). A key present with value `0` is a value — absence is tested by absence, never by truthiness — and for `step_up.window_seconds`, `0` means *no grace period*, the strictest setting, never *no check*
  - `container.md` §6 (#94): both gate branches require `organize` at the source scope, checked before the delta, so parking a proposal is not a cheaper way to reach an item than moving it
  - `container.md` §4: `shadowed_by` is a property of a resolution, not of the item, and has a typed home on the resolver's per-item envelope `ResolvedItem` (F10); §8's preamble counted four configurable values over a six-row table (F14)
  - `authorization-server.md` §11.1: the `client_type` → rendered-kind mapping (`cli` → `device`) is named as `CONSENT_KIND_FROM_CLIENT_TYPE` rather than left to prose (F25). §10: `yes.consume` is gated by the window of the ring pair the act crosses, source → destination, never a global one
  - `events.md` §3: the hash formula now names `seq` explicitly as excluded, agreeing with the bullet below it, `storage.md` §3 and `_types.py`, with the reason recorded — `prev_hash` already binds order, and hashing a store-assigned integer makes a container unverifiable once exported to a backend that numbers differently (F7). §1 counted seventeen running events over an eighteen-row table (F8)
  - `context-item.md` §4 and `_types.py`: `provenance` has six keys, not five (F13); `storage.md` §7's TODO pointed at provisional aliases #28 had already replaced (F9)
