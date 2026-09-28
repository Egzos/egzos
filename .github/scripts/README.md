# .github/scripts — egzos CI scripts

## check_ownership.py

Enforces path ownership on every pull request.  Reads `.github/OWNERSHIP.yml`
and exits 0 (pass) or 1 (fail).

### How it works

1. **Branch classification** — branches starting with `agent/` are agent
   branches; all others are human (Chief) branches. The branch name is the
   agent's choice, so it cannot make a PR the Chief's: a PR opened by an
   identity in `agent_identities` (the forge App) from outside `agent/` fails.
2. **Human branches** — print "human branch — Chief owns everything" and pass.
   The size cap is a warning, not a failure, on human branches (the Chief is the gate); governance path notices are still emitted.
3. **Agent branches** — derive the agent name from the second path segment
   (`agent/<name>/<slug>`).  The agent must exist in `OWNERSHIP.yml`.
4. **File ownership** — each changed file must match at least one of the
   agent's `paths:` globs.  If it does not, the check fails.
5. **Exclusive paths** — if the file matches another agent's `exclusive:` glob,
   the check fails even if the file is also in the acting agent's `paths:`.
6. **Chief-only paths** (`chief_only:` key) — any agent branch touching a
   chief-only path, on either side of a rename, fails immediately.
7. **Governance notices** (`governance_paths:` key) — touching these paths
   emits a `::notice::` annotation for the Watcher; it is not a failure when
   the file is otherwise owned by the agent.
8. **Size cap** — counts added+removed lines (excluding `size_cap.exclude`
   globs) and total non-excluded files.  Exceeding `size_cap.lines` (600) or
   `size_cap.files` (30) is a failure on agent branches — a `::warning::` on
   human branches — unless the PR carries `size-exception` **and** the login
   that last applied it is in `size_exception_approvers`. The workflow looks
   the applier up from the PR's label events.
9. **Fail closed** — a diff record the parser cannot interpret, or labels that
   are not a JSON array, fail the check (exit 1). Nothing is skipped.

Tests: `tests/governance/test_check_ownership.py`, fed by real `git diff
--numstat -z` output from throwaway repositories.

The `tests` check runs this suite from the tree under review, not from the base, and that is
deliberate: it tests the change itself, so a PR that edits a checker or workflow has to carry tests
that pass against its own edit. It is not a gate a PR could loosen by editing it. The gate is
`check_ownership.py` and `OWNERSHIP.yml` resolved from the base by `ownership-check.yml`, and
`tests/governance/**` is a1p-planner's path, so any other agent branch touching it fails.

### Glob syntax

| Pattern | Matches |
|---|---|
| `CLAUDE.md` | exact file |
| `*.lock` | any `.lock` in the root only |
| `src/egzos/store/**` | anything under `src/egzos/store/` (any depth) |
| `**/*.lock` | any `.lock` at any depth |
| `a/**` | `a/x`, `a/x/y/z`, etc. — `**` crosses `/`, `*` does not |

### Local run

```bash
# Install dependency (also done by ownership-check.yml)
pip install pyyaml

# Against a real PR branch
python3 .github/scripts/check_ownership.py \
    --base origin/main \
    --head HEAD \
    --branch "$(git rev-parse --abbrev-ref HEAD)"

# With canned changed-files and numstat (for unit testing)
python3 .github/scripts/check_ownership.py \
    --base unused \
    --head unused \
    --branch "agent/a3-store/issue-1" \
    --changed-files /tmp/files.txt \
    --numstat /tmp/numstat.txt
```

### Running the self-tests

`pytest -q tests/governance` — part of the required `tests` check.

## file_advisory.sh

The a6-adversary nightly sweep's only route to the repository-advisory API, which replaced a raw
`gh api` grant (drift F17). Three verbs, this repository only:

```bash
bash .github/scripts/file_advisory.sh list                           # GHSA id, state, summary
bash .github/scripts/file_advisory.sh create - <<'JSON'               # body on stdin; prints the new GHSA id
{"summary": "…", "description": "…", "severity": "high"}
JSON
# update takes its body the same way: file_advisory.sh update GHSA-xxxx-xxxx-xxxx - <<'JSON' …
```

Requires `GH_TOKEN` (the forge token) and `GITHUB_REPOSITORY`. The body must be a JSON object, in a
file or on standard input (`-`). The sweep uses stdin because its session holds no write tool, so
the script it runs is always the one its checkout holds; it goes to the API from that file and is never echoed, so a run log carries ids and summaries
only — never a reproduction. `update` is append-only: it reads the filed advisory and appends the new
`description` under a dated heading (adding any new `vulnerabilities`), because the advisory is the
only copy of an unfixed reproduction and a plain PATCH would replace it. Filed and new vulnerabilities alike are cut down to the fields a PATCH
accepts before they are merged, so the read shape a GET returns is never echoed back. `list` comes first on every sweep, so a finding already filed is
updated rather than filed again.

## post_review_comment.sh

Creates or updates the one review comment per reviewer on a PR, matched by its first line and by
author. The review session never runs it: the session writes `/tmp/review.md`, and a model-free
`post-review` step runs this script afterwards, read from the base commit by SHA into a fresh
temporary file, with `PATH` pinned. A session that could both write files and run a script it could
have rewritten would hold an interpreter (Egzos/egzos#71 review, round 3).
