# Contributing to egzos

## How this repository is built

egzos is built by an agent roster running in GitHub Actions under the Chief's gate. Agents open PRs; the Chief approves each one by SHA; GitHub's branch protection executes the merge. No agent has merge rights. See `CLAUDE.md` for the full trust posture.

Outside contributions are welcome but the process differs from a typical open-source project: the Chief reviews all outside PRs personally, and the bar is the same as for agent PRs.

## Filing issues

Issues are welcome from anyone. Use the issue templates. For security concerns, do not open a public issue — use GitHub Security Advisories (see `SECURITY.md`).

## Submitting a pull request

Before opening a PR:

1. Read `CLAUDE.md` and `spec/` to understand the contracts and trust posture.
2. Read `.github/PULL_REQUEST_TEMPLATE.md` — fill every field.
3. Add the two header lines to every Python file you create:
   ```
   # Copyright 2026 Ali Sasanian
   # SPDX-License-Identifier: Apache-2.0
   ```
4. Touch only the paths your change logically owns. Governance-sensitive paths (`CLAUDE.md`, `.github/**`, `.claude/**`, `spec/contracts/**`) require a strong justification.
5. Keep the PR within the size cap: 600 changed lines or 30 files (lockfiles and `tests/fixtures/**` excluded).

## Running tests

```
pip install -e ".[dev]"
ruff check src tests adversarial
pytest
```

Ruff is enforced; the CI `tests` check runs both. Add tests for any code you add. Core module coverage standard is 90% of the owned module.

## License and DCO / CLA

`TODO(chief): choose DCO vs CLA before accepting outside PRs.` This has not been decided. Until then, outside PRs are reviewed case by case; the Chief will communicate what sign-off is required.

All code in this repository is Apache-2.0 unless otherwise noted. By submitting a PR you confirm your contribution is yours to offer under that license (or whatever sign-off mechanism the Chief adopts).

## Design and contract questions

- Design question with no obvious answer: open an issue with label `design-gap`. A2 (Taste) returns options for the Chief's pick.
- Contract or interface question: open an issue with label `contract-change`. `a1p-planner` holds `spec/` and triages these.
- Never change a frozen contract (`spec/contracts/**` after Phase 0.3) as a drive-by. Escalate.
