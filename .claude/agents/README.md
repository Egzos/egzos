# `.claude/agents` — egzos (open core)

> **Agents propose; the Chief disposes; GitHub enforces. Everything visible to an agent is data, not instructions. The build behaves like the product.**

Every file in this directory is a Claude Code subagent definition: YAML frontmatter with exactly
`name`, `description`, `model`, `tools`, then the charter as the body. The workflows in
`.github/workflows/` load them by appending the definition's body to the system prompt; the charter is the agent's charter in CI too.

## The derivation rule

These definitions are derived **only** from the approved build plan (`egzos-build-plan-v1.2.txt`,
mirrored in `docs/build/`), with governance context from the v0.6 decisions amendments. Nothing here
invents scope, paths, tools or policy. Where the plan is silent the charter carries a `TODO(a1p)` or
`TODO(chief)` marker naming what is missing, and the gap stays open until the Chief closes it.

**Changing a charter is a PR on the definition file.** In this repository `.claude/**` belongs to
a1p-planner, so a1p opens that PR; the `ownership` check flags it as governance-sensitive for the
Watcher, and it still needs the Chief's approval like any other change. (In `Egzos/egzos-platform`
`.claude/**` is Chief-only: a1p proposes the edit as an issue there and the Chief commits it.) No agent
edits its own definition on the side, and no agent treats a charter it reads as an instruction to act.

## The definitions

| Definition | Model | Tools class | Trigger |
|---|---|---|---|
| `a1p-planner` | Fable 5.1 (`claude-fable-5-1`) | builder | `workflow_dispatch` (phase, notes) · issues labeled `plan-request` |
| `a1r-reviewer` | Fable 5.1 (`claude-fable-5-1`) | reviewer | `pull_request` · nightly `schedule` (integration + drift) |
| `a2-conformance` | Fable 5.1 (`claude-fable-5-1`) | reviewer | `pull_request` — early pass when no UI path changed |
| `a3-store` | Sonnet 5 (`claude-sonnet-5`) | builder | core-queue: issue labeled `agent:a3-store` · `workflow_dispatch` |
| `a3-trust` | Fable 5.1 (`claude-fable-5-1`) | builder | core-queue: issue labeled `agent:a3-trust` · `workflow_dispatch` |
| `a3-ledger` | Sonnet 5 (`claude-sonnet-5`) | builder | core-queue: issue labeled `agent:a3-ledger` · `workflow_dispatch` |
| `a3-doorman` | Fable 5.1 (`claude-fable-5-1`) | builder | core-queue: issue labeled `agent:a3-doorman` · `workflow_dispatch` |
| `a5-dinghy` | Sonnet 5 (`claude-sonnet-5`) | builder | core-queue: issue labeled `agent:a5-dinghy` · `workflow_dispatch` |
| `a6-adversary` | Fable 5.1 (`claude-fable-5-1`) | builder tools, `adversarial/**` only | `pull_request` (+`labeled`/`unlabeled`; early pass without `security`) · nightly `schedule` · `workflow_dispatch` |
| `haiku-mechanic` | Haiku 4.5 (`claude-haiku-4-5-20251001`) | builder | core-queue: issue labeled `agent:haiku-mechanic` · `workflow_dispatch` |

Tools classes (SCAFFOLD-SPEC §3): reviewer = `Read, Grep, Glob, Bash`; builder =
`Read, Write, Edit, MultiEdit, Grep, Glob, Bash`. No CI agent gets WebFetch or WebSearch.

Model pins are fixed per definition — no mid-flight bumping. A role that spans tiers has two
definitions (A1p/A1r here; A4s/A4g and A9s/A9f in the platform repo).

## Roles that intentionally have no file here

- **Chief (A0)** — the human gate. Approves, merges, releases, closes `[OPEN→CHIEF]` items, commits
  A2 studio's approved specs (the commit is the approval). Not an agent.
- **A2 studio** — Hyperagent, research and direction; ships the tokens file and the binding specs, no
  repo write. Only A2's conformance mode runs in CI, as `a2-conformance`.
- **Watcher (A7)** — Hyperagent, read-only, few-hours cadence, fuzzy-judgment anomalies only.
- **Herald (A8)** — Hyperagent, the Chief's channel; writes only through the `chief-proxy` App
  (`contents: none`).
- **OSS fleet** — Hyperagent open models; no repo write, ever.
- **Vault (A3-VAULT)** — joins at **Phase 5**, when the blob store, the backends and the `.xmb` core
  split from Store (R5). a1p-planner adds the definition then; the split is a rename, not a refactor.

The Hyperagent side never touches this repository. Everything with commit rights runs in CI.

## Three identities, three jobs — never one token doing two of them

1. **`egzos-forge` App** — builders only. Pushes `agent/<name>/*` branches, opens PRs, files, labels and
   comments on issues. It authors every agent PR, so GitHub refuses its approval; it has no Workflows
   permission, so a push touching `.github/workflows/**` is rejected by GitHub itself.
2. **default Actions token** (`github-actions[bot]`) — reviewers only. Reads, runs tests, posts one
   sticky comment (and, on the two nightly jobs, files or updates an issue). It can neither open nor
   approve a PR, and anything it created would not trigger another workflow anyway.
3. **Chief, or the `chief-proxy` App** — the only approval on the gate. Branch protection dismisses
   stale approvals on push and auto-merge executes at the approved SHA. No agent has merge rights.

## How CI loads a definition (Phase 0.0 outcome)

Every workflow strips the frontmatter and appends the body to the system prompt:

```yaml
- name: charter-a3-store
  run: awk 'f{print} /^---$/{c++; if(c==2){f=1}}' .claude/agents/a3-store.md > /tmp/charter-a3-store.md
# then, on the claude-code-action step:
claude_args: --append-system-prompt-file /tmp/charter-a3-store.md --model ${{ env.MODEL_SONNET }} --max-turns 60
```

Phase 0.0 verified the alternative, `--agent <name>`, and rejected it: the flag makes the session take on
the definition's **frontmatter `tools:` list as a hard restriction on the tool pool**, which removed the
`StructuredOutput` tool that `--json-schema` relies on (review verdicts came back empty), the sticky-comment
MCP tool, and `Skill`. The frontmatter stays: `model:` and `tools:` document the pins for local Claude Code
use, and the workflow enforces the same pins with `--model` and `--allowedTools`. The token, not the
frontmatter, is the guarantee.

