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
