# REVIEW-DECISIONS

Settled review dispositions for `Egzos/egzos`. **Reviewers consult this file before raising a
finding.** If a finding you are about to raise is already settled here, cite the entry id in one
line and move on — do not re-litigate it in your review comment.

This file exists because a reviewer runs on a fresh checkout with no memory of the last run. Left
to itself it re-raises the same settled point on every PR that touches the same paths, which trains
the Chief to skim reviews. The register is the reviewer's memory, committed and reviewable like
anything else.

`Egzos/egzos-platform` keeps its own register at the same path. Entry ids are **repo-local**: this
file's `RD-001` and the platform's `RD-001` are unrelated. Never cite an entry across repositories.

## What this file is not

It is **not** a suppression list, and it cannot be used as one.

- **Only `minor` and `major` findings can be settled here.** A `blocker` is never settleable in
  advance. Raise it.
- **Security-class findings are never settleable here.** No entry in this file excuses a
  credential in a diff, an enumeration path, a missing audit event, or a capability check that
  Store or Vault performed on its own authority. If an entry appears to cover one, the entry is
  wrong — raise the finding and say the entry misled you.
- **An entry settles a specific claim about specific paths, not a topic.**
- **An entry can expire.** Where a disposition depends on repository state, the entry names the
  state under `Holds while`. When that state changes, the entry stops holding and the finding is
  live again.

## Who writes it

The Chief, only, and the `ownership` check enforces it: this path is listed under `chief_only`
in `.github/OWNERSHIP.yml`, so an agent branch that touches it fails the check even though
`docs/**` is otherwise a1p-planner's and haiku-mechanic's to write. An agent that believes an
entry is wrong files a `governance` issue saying so — it never edits this file, and it never adds
an entry to pre-settle its own work.

## Entry format

Each entry carries: the finding as a reviewer actually phrases it, the disposition, the reasoning,
the state the reasoning depends on, and the paths in scope. Status is one of:

- **CLOSED** — the finding was correct and the underlying issue was fixed. Cite and move on.
- **ACCEPTED** — the finding is correct and the Chief is knowingly living with it. Cite and move on.
- **REJECTED** — the finding rests on a mistaken premise, named in the entry.
- **PRE-EMPTIVE** — not yet raised by a reviewer; recorded because the tree looks wrong at a glance
  and the explanation is not local to the file being read.

---

## RD-001 · Review checks early-pass on `dependabot[bot]` PRs

**Status:** ACCEPTED · PRE-EMPTIVE — not yet raised

**The finding a reviewer would raise.**

> `.github/workflows/a1r-review.yml` (and the other model-backed checks) guard every meaningful
> step with `if: github.actor != 'dependabot[bot]'`. Dependabot PRs therefore report a green
> `a1r-review` without any review having happened — a required check that can be trivially
> bypassed by opening a PR as Dependabot.

**Disposition.** ACCEPTED. The observation is exactly right and the behaviour is deliberate.

**Reasoning.** Dependabot runs carry a read-only token and **no access to secrets**, so
`ANTHROPIC_API_KEY` and `CLAUDE_CODE_OAUTH_TOKEN` are empty in that context and the action cannot
run at all. Without the early pass the check fails rather than skips, and under a ruleset a failing
required check makes every dependency bump unmergeable — which is worse than the exposure, because
the alternative is an unpatched action pin. The bypass is not free to an attacker either: opening a
PR *as* `dependabot[bot]` requires control of the Dependabot identity on the org, which is a
GitHub-side compromise well upstream of this workflow.

The residual risk is named and owned rather than hidden: **the Chief reviews Dependabot PRs
personally.** Before merging a bump, verify the action's `action.yml` inputs and outputs at the
target version against what the workflows actually pass — a green early-pass is not evidence the
new action version was exercised.

**Holds while.** Dependabot runs remain secret-less. If GitHub ever grants Dependabot access to
Actions secrets on this org, remove the early pass and this entry with it.

**Paths in scope.** `.github/workflows/a1r-review.yml`, `.github/workflows/a2-conformance.yml`,
`.github/workflows/a6-adversary.yml`, `.github/dependabot.yml`.

---

## RD-002 · Workflows use `--append-system-prompt-file`, not `--agent`

**Status:** REJECTED · PRE-EMPTIVE — not yet raised

**The finding a reviewer would raise.**

> The repository defines agents in `.claude/agents/*.md`, but no workflow invokes them with
> `--agent`. Each workflow instead strips the frontmatter with `awk` and passes the body via
> `--append-system-prompt-file`, duplicating what the agent definition already expresses.

**Disposition.** REJECTED — the premise that `--agent` is the correct mechanism here is mistaken,
and it was tried.

**Reasoning.** Phase 0.0 established empirically that `--agent` applies the definition's frontmatter
`tools:` list as a **hard restriction on the tool pool**, which removes `StructuredOutput`
(`--json-schema`), the sticky-comment MCP tool and `Skill`. The verdict JSON that the required
checks read is structured output, so `--agent` silently produced an empty verdict and the
fail-closed gate turned every review red. Stripping the frontmatter and appending the body
preserves the charter's content while leaving the tool pool under the workflow's explicit
`--allowedTools`, which is where least-privilege belongs in CI anyway. The `awk` line and a
two-line comment recording the reason sit directly above each call site.

The duplication is real and accepted: the frontmatter `tools:` list in each definition is now
documentation of intent rather than an enforced restriction, and the enforced list is
`--allowedTools` in the workflow. A PR that changes one without the other is a genuine finding —
raise that.

**Holds while.** `claude-code-action` behaves this way. If a release makes `--agent` compatible
with structured output, this is worth revisiting, and the entry is void.

**Paths in scope.** `.github/workflows/**`, `.claude/agents/**`.
