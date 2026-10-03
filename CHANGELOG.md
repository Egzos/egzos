# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

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
