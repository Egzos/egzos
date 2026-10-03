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
- **LIVE** — the finding is correct whenever it applies and is never settled. The entry exists so it
  is not mistaken for a settled point or waved through as drift. Raise it.

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

---

## RD-003 · A model pin change touches four places

**Status:** LIVE — raised on #58

**The finding a reviewer would raise.**

> This PR changes `<agent>`'s model tier, but `<location>` still states the old one.

**Disposition.** LIVE. A pin change that misses any of the four locations is not done. Raise it; no
entry here settles it.

**Reasoning.** A pin is stated in four places, and a change is checked against all four:

1. the workflow's `--model` flag, through the `MODEL_*` env indirection — every call site that runs
   the agent (`a6-adversary.yml` has two; `a1r-reviewer` runs in `a1r-review.yml` and
   `nightly-integration.yml`);
2. the definition's `model:` frontmatter **and** its prose tier line ("Opus 5.5, fixed.");
3. CLAUDE.md's model-pin table and the roster in `.claude/agents/README.md`;
4. every dispatcher that special-cases the agent by name — here, the `case` arms in `core-queue.yml`.

RD-002's rule that frontmatter `tools:` and the workflow's `--allowedTools` change together extends to
`model:` and `--model`. The prose and tables are what every agent reads as its charter, so a stale tier
there is a wrong charter, not cosmetic drift. #58's first commit split `a1r-reviewer` across two tiers;
a1r caught it, not process.

**Holds while.** A pin is stated in more than one place. If the four are ever generated from a single
source, this entry is void.

**Paths in scope.** `.github/workflows/**`, `.claude/agents/**`, `CLAUDE.md`.

---

## RD-004 · Builder prompts checkpoint to a draft PR

**Status:** LIVE · PRE-EMPTIVE — not yet raised

**The finding a reviewer would raise.**

> This builder prompt commits, pushes and opens the PR once, at the end. A run that reaches
> `--max-turns` first leaves nothing behind.

**Disposition.** LIVE. A prompt that ends in a single terminal commit→push→PR→stop sequence is a
turn-budget defect. Raise it.

**Reasoning.** A builder runs on a fresh checkout, so a run killed by the turn ceiling keeps only what
it already pushed — the work is not truncated, it is discarded. `a1p-planner` spent 121 turns and
$10.10 on #29 and committed nothing. A builder prompt therefore opens a draft PR on its first commit
(`gh pr create --draft`, with `Bash(gh pr ready:*)` in `--allowedTools`), pushes after each section,
and marks the PR ready only when the work is complete. A prompt that says "mark ready" without
`gh pr ready` in `--allowedTools` is the same finding. Early drafts cost no review spend — the
model-backed reviews are draft-gated (#58) — while `tests` and `ownership` still run on every push.
#60 applies this to `a1p-planner.yml` and `core-queue.yml`.

**Holds while.** The reviews stay draft-gated. If they ever run on drafts, early drafts carry review
spend and the trade is worth revisiting.

**Paths in scope.** `.github/workflows/a1p-planner.yml`, `.github/workflows/core-queue.yml`, and any
workflow that runs a builder.

---

## RD-005 · Review sessions never execute the tree under review

**Status:** LIVE (half 1) · ACCEPTED (half 2) — raised on #71

**The findings a reviewer would raise.**

> 1. This PR-review model step grants `Bash(python:*)` / `pytest` / `pip` / `ruff`. Running the
>    tree's suite executes the tree's code in the review job, where it can rewrite the controls
>    that `control-inputs-from-base` restored before the model reads or runs them.
> 2. The reviewer cannot run the tests, so its review of test changes rests on reading alone.

**Disposition.** Half 1 is LIVE: a PR-review model step that can execute the tree under review is a
finding whenever it appears. Raise it. Half 2 is ACCEPTED: this is the cost of half 1, and the
Chief is knowingly living with it.

**Reasoning.** A process started by one step of a job outlives that step, so there is no "safe
moment" inside the job to run the PR's code. The only clean separation is a job that runs it and
holds nothing to protect. The `tests` check is exactly that job, and it is required. So the reviewer
reads its result (`gh pr checks`, with `checks`, `statuses` and `actions: read`) and cites it, rather than
producing a second result in a job that holds the review token and the comment script. For the a6
sweep, which holds the forge token and so runs no interpreter either, a separate job holding no
token runs the adversarial suite against `main`. Step order inside one job would not separate it,
for the reason above. The sweep cites `/tmp/adversarial-suite.txt`, which reaches it as a one-day
artifact rather than a job output or step env, so the detail stays out of the run log.
The artifact is as public as the log on this repository: the gain is retention and no plaintext
in an indexed log, not confidentiality. What keeps the detail safe is unchanged: `main` holds no open
reproduction, because a security regression test enters `adversarial/` only in its fix PR. The nightly
integration check is the same shape (drift F22): `integration-suite` runs the suites holding
`contents: read` only, over `tests/` and never `adversarial/` (a6's sweep owns that output), and the
session that holds the drift issue's write token reads `/tmp/suite/suite.txt` and runs no interpreter.

The same rule covers scripts (#71 review, round 3). A session that can write files never also
holds a grant to run a file it could have rewritten, because that grant is an interpreter. The
reviewers write `/tmp/review.md`, and a model-free `post-review` step posts it. That step fetches the
script from the API at the base commit and posts, both under `env -i` with an explicit allowlist. The a6 sweep holds no
write tool, and passes advisory bodies to `file_advisory.sh` on standard input. Every step after a
review session runs with `PATH` pinned, and embedded Python runs with `-I`, so that a PR checkout
in the working directory is not on `sys.path`.

**Residual, named.** The review sessions' `Write` is unscoped. What runs after the session is
covered: a pinned `PATH`, `-I` Python, blanked `BASH_ENV` / `ENV` / `LD_PRELOAD` (a step's own env wins over
anything the session appends to `$GITHUB_ENV`), and a comment script fetched from the API rather
than read from the checkout's `.git`, with the fetch and the post both run under `env -i` and an explicit
allowlist (#79 and platform#42 reviews). What stays open: the session still writes `/tmp/review.md`, which `post-review` posts, so the review
text is the session's by design; the step pins which comment it lands in (the job's own marker, never
another reviewer's). That text is posted verbatim, from a job whose model session holds the provider
credential, so two controls close the channel for the review sessions: every model session denies
`Read(//proc/**)`, which denied Read, Grep and Glob alike on `/proc/self` when checked against the CLI
locally (2.1.283; not yet re-checked in a CI run), and a review session holds no other way to read its
own environment; and `post-review`
refuses a body carrying any credential the job holds (#79 review, a1r minor 3a). An encoded copy would
pass the second control; the first is the one that keeps the credential out of reach. The deny stays on
the builder sessions too, but it does not close them: a builder holds an interpreter (`python`, `git`),
and any interpreter reads its own process environment. That case stays open (Egzos/egzos-platform#42
review). Beyond that, such a session can still leave files that nothing runs yet. Scoping it to the one output path, `/tmp/review.md`,
needs the pinned CLI's path-rule syntax verified in a real run first, because getting it wrong
silently stops every review from being posted.

**Holds while.** The `tests` check runs the full suite (lint included) on every PR, and stays
required. If it ever stops doing either, the reviewer is left with no executed result to cite, and
half 2 has to be reopened.

**Paths in scope.** `.github/workflows/a1r-review.yml`, `.github/workflows/a2-conformance.yml`,
`.github/workflows/a6-adversary.yml`, `.github/workflows/tests.yml`,
`.github/workflows/nightly-integration.yml`, `.claude/agents/a1r-reviewer.md`,
`.claude/agents/a2-conformance.md`, `.claude/agents/a6-adversary.md`,
`.github/scripts/file_advisory.sh`, `.github/scripts/post_review_comment.sh`.

---

## RD-006 · A pull request's checks run from the workflow file in its own tree

**Status:** ACCEPTED — raised on #40 (a1r), tracked as #44 item 3

**The finding a reviewer would raise.**

> The charter and the control inputs come from the base, but everything else a check does — its
> `prompt:`, `--allowedTools`, `--model`, its Verdict step, the ownership step itself — is read
> from the workflow file in the tree under review. A PR that edits a review workflow is judged by
> its own edit.

**Disposition.** ACCEPTED. The observation is exactly right. There is no configuration that fixes it
without something worse.

**Reasoning.** GitHub runs a `pull_request` workflow from the PR's merge ref. The one event that
runs the base's file, `pull_request_target`, does so with the base's secrets, and checking out the
PR's tree under it is the textbook way to hand those secrets to untrusted code. The compensating
controls are identity controls:

- **Agent PRs cannot carry a workflow edit.** The `egzos-forge` App holds no Workflows permission,
  so GitHub itself rejects any agent push that touches `.github/workflows/**`.
- **The Chief's own branches** are gated by the Chief by definition.
- **A fork PR is the residue.** It carries no secrets, so its model steps cannot run. But the fork
  controls the workflow file its checks run from, so **every required check on a fork PR is
  forgeable by that PR**, the ownership check included.

On a fork PR the checks are therefore advisory. The gate is the Chief's approval of the diff, and a
diff touching `.github/workflows/**` is the tell. The stronger control is a setting, not a file:
Settings → Actions → *Fork pull request workflows* → require approval for all outside
collaborators. With it, no fork workflow runs, and so no check reports, until the Chief allows it.

**Holds while.** The forge App holds no Workflows permission, fork runs stay secret-less, and no
other identity with `contents: write` opens pull requests. If any of those changes, this entry is
wrong, and the finding should be raised as it stands.

**Paths in scope.** `.github/workflows/**`.

