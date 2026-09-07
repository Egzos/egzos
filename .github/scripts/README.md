# .github/scripts — egzos CI scripts

## check_ownership.py

Enforces path ownership on every pull request.  Reads `.github/OWNERSHIP.yml`
and exits 0 (pass) or 1 (fail).

### How it works

1. **Branch classification** — branches starting with `agent/` are agent
   branches; all others are human (Chief) branches.
2. **Human branches** — print "human branch — Chief owns everything" and pass.
   The size cap is a warning, not a failure, on human branches (the Chief is the gate); governance path notices are still emitted.
3. **Agent branches** — derive the agent name from the second path segment
   (`agent/<name>/<slug>`).  The agent must exist in `OWNERSHIP.yml`.
4. **File ownership** — each changed file must match at least one of the
   agent's `paths:` globs.  If it does not, the check fails.
5. **Exclusive paths** — if the file matches another agent's `exclusive:` glob,
   the check fails even if the file is also in the acting agent's `paths:`.
6. **Chief-only paths** (`egzos-platform` only, `chief_only:` key) — any agent
   branch touching a chief-only path fails immediately.
7. **Governance notices** (`egzos` only, `governance_paths:` key) — touching
   these paths emits a `::notice::` annotation for the Watcher; it is not a
   failure when the file is otherwise owned by the agent.
8. **Size cap** — counts added+removed lines (excluding `size_cap.exclude`
   globs) and total non-excluded files.  Exceeding `size_cap.lines` (600) or
   `size_cap.files` (30) is a failure on agent branches — a `::warning::` on human branches — unless the PR carries the `size-exception`
   label.

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
    --branch "$(git rev-parse --abbrev-ref HEAD)" \
    --labels ""

# With canned changed-files and numstat (for unit testing)
python3 .github/scripts/check_ownership.py \
    --base unused \
    --head unused \
    --branch "agent/a3-store/issue-1" \
    --labels "" \
    --changed-files /tmp/files.txt \
    --numstat /tmp/numstat.txt
```

### Running the self-tests

The test suite in `/tmp/` is created by hand or CI during the validation run.
See the `VALIDATION` section of the scaffold spec for the canonical test cases.
