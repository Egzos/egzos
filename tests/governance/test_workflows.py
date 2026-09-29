# Copyright 2026 Ali Sasanian
# SPDX-License-Identifier: Apache-2.0
"""Control-plane invariants over .github/workflows/*.yml (#44 item 2).

Each of these was established by a fix and, until now, held only as long as the next reviewer
remembered it. Parsing the workflow files moves them into the required `tests` check.
"""

import json
import re
import textwrap
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[2]
WORKFLOWS = sorted((ROOT / ".github" / "workflows").glob("*.yml"))
ACTION = "anthropics/claude-code-action@"
REVIEW_JOBS = {"a1r-review", "a2-conformance", "a6-adversary"}


def _load(path):
    doc = yaml.safe_load(path.read_text())
    # YAML 1.1 reads the bare key `on` as True.
    doc["on"] = doc.pop(True, doc.get("on"))
    return doc


def _steps():
    for wf in WORKFLOWS:
        for job_id, job in _load(wf)["jobs"].items():
            for step in job.get("steps", []):
                yield wf.name, job_id, job, step


def test_workflows_found():
    assert len(WORKFLOWS) >= 8


@pytest.mark.parametrize("wf", WORKFLOWS, ids=lambda p: p.name)
def test_top_level_permissions_are_empty(wf):
    assert _load(wf).get("permissions") == {}


def test_every_action_is_sha_pinned():
    bad = [
        (wf, step["uses"])
        for wf, _, _, step in _steps()
        if "uses" in step and not re.fullmatch(r"[\w.-]+/[\w./-]+@[0-9a-f]{40}", step["uses"])
    ]
    assert bad == []


def test_no_expression_inside_a_run_body():
    # ${{ }} is substituted before bash parses the line, so attacker-chosen text (branch names,
    # labels, titles) becomes code. Values reach run: bodies through env only.
    bad = [(wf, step.get("name")) for wf, _, _, step in _steps() if "${{" in step.get("run", "")]
    assert bad == []


def test_every_charter_comes_from_the_base():
    charters = [(wf, s) for wf, _, _, s in _steps() if s.get("name", "").startswith("charter")]
    assert charters
    bad = [(wf, s["name"]) for wf, s in charters if 'git show "origin/' not in s.get("run", "")]
    assert bad == []


@pytest.mark.parametrize("job_id", sorted(REVIEW_JOBS))
def test_review_jobs_take_control_inputs_from_the_base(job_id):
    step_names, allowed, action_at = [], "", None
    for _, jid, _, step in _steps():
        if jid != job_id:
            continue
        if step.get("uses", "").startswith(ACTION):
            allowed = step["with"]["claude_args"]
            action_at = len(step_names)
        step_names.append(step.get("name", ""))
    assert "control-inputs-from-base" in step_names
    # Before the model runs, not merely before the verdict is read (#40 review).
    assert action_at is not None
    assert step_names.index("control-inputs-from-base") < action_at
    # The session posts nothing itself: a model-free step does, after it ends (#71 round 3).
    assert "Bash(bash " not in allowed
    assert "post_review_comment.sh" not in allowed


def test_embedded_python_compiles():
    # A syntax error in a heredoc would pass every text assertion here and surface only as a red
    # required check at runtime.
    heredoc = re.compile(r"python3 (?:-I )?- <<'(\w+)'\n(.*?)\n\1\n", re.DOTALL)
    blocks = 0
    for wf, _, _, step in _steps():
        for m in heredoc.finditer(step.get("run", "") + "\n"):
            compile(textwrap.dedent(m.group(2)), f"{wf}:{step.get('name')}", "exec")
            blocks += 1
    assert blocks >= 6


def test_control_inputs_cover_everything_claude_code_loads():
    for wf, job_id, _, step in _steps():
        if step.get("name") != "control-inputs-from-base":
            continue
        run = step["run"]
        # At any depth, not only the root (#40 review): Claude Code loads nested ones too.
        for needle in ("-name CLAUDE.md", "CLAUDE.local.md", "-name .mcp.json",
                       "-name .claude -type d -prune", r"(^|/)\.claude/",
                       "REVIEW-DECISIONS.md"):
            assert needle in run, (wf, job_id, needle)


INTERPRETERS = (
    "Bash(python:*)", "Bash(python3:*)", "Bash(pytest:*)", "Bash(pip:*)", "Bash(ruff:*)",
)


def _model_steps():
    for wf, job_id, job, step in _steps():
        if step.get("uses", "").startswith(ACTION):
            yield wf, job_id, job, step


def _gh_token(job, step):
    # The step's env overrides the job's, as it does in Actions; either may carry the token.
    return str({**job.get("env", {}), **step.get("env", {})}.get("GH_TOKEN", ""))


def _after_model(job_id):
    steps = [s for _, j, _, s in _steps() if j == job_id]
    (at,) = [i for i, s in enumerate(steps) if s.get("uses", "").startswith(ACTION)]
    return steps[at + 1:]


@pytest.mark.parametrize("job_id", sorted(REVIEW_JOBS))
def test_review_is_posted_by_a_model_free_step(job_id):
    after = _after_model(job_id)
    assert after[0].get("name") == "post-review"
    post = after[0]
    run = post["run"]
    # From the API at the base commit, under a fresh HOME, after the session: never a path or a
    # .git it could have reached (#79 review).
    assert "contents/.github/scripts/post_review_comment.sh?ref=${BASE_SHA}" in run
    assert "env -i PATH=/usr/bin:/bin" in run
    assert "clean gh api" in run and 'clean bash --noprofile --norc "$S"' in run
    assert "git show" not in run
    # The job's own marker, pinned; a body opening with another reviewer's is refused.
    assert post["env"]["MARKER"] == {
        "a1r-review": "## a1r-reviewer review",
        "a2-conformance": "## a2-conformance review",
        "a6-adversary": "## a6-adversary review",
    }[job_id]
    assert '!= "$MARKER"' in run
    # Everything env -i forwards is pinned in the step's own env.
    assert post["env"]["GH_TOKEN"] == "${{ github.token }}"
    assert post["env"]["GITHUB_REPOSITORY"] == "${{ github.repository }}"
    assert post["env"]["BASE_SHA"] == "${{ github.event.pull_request.base.sha }}"
    # A body carrying a credential the job holds is refused before anything is fetched or posted.
    assert post["env"]["PROVIDER_KEY"] == "${{ secrets.ANTHROPIC_API_KEY }}"
    assert post["env"]["PROVIDER_OAUTH"] == "${{ secrets.CLAUDE_CODE_OAUTH_TOKEN }}"
    assert run.index('"$BODY" == *"$CRED"*') < run.index("clean gh api")
    for cred in ('"$PROVIDER_KEY"', '"$PROVIDER_OAUTH"', '"$GH_TOKEN"'):
        assert cred in run.split("for CRED in", 1)[1].split(";", 1)[0]
    # Posted on failure too (a turn-capped review is still the Chief's to read), never when
    # cancelled.
    assert "!cancelled()" in post["if"] and "skipped" in post["if"]


@pytest.mark.parametrize("job_id", sorted(REVIEW_JOBS))
def test_steps_after_the_model_run_pinned_and_isolated(job_id):
    # Anything the session planted on PATH, or in the checkout that `python3 -` would import from,
    # must not run with the job's token after it.
    for step in _after_model(job_id):
        env = step.get("env", {})
        assert env.get("PATH") == "/usr/bin:/bin", step.get("name")
        # $GITHUB_ENV is writable by the session; a step's own env wins over it.
        assert all(env.get(k) == "" for k in ("BASH_ENV", "ENV", "LD_PRELOAD")), step.get("name")
        assert "python3 - " not in step.get("run", ""), step.get("name")


@pytest.mark.parametrize("wf", WORKFLOWS, ids=lambda p: p.name)
def test_no_heredoc_python_reads_the_working_directory(wf):
    # `python3 -` puts the working directory first on sys.path, and in a PR job that is the tree
    # under review; -I leaves it off. labels-sync is the one exception: it runs only on main's own
    # tree (push to main, dispatch), and it needs the user-site pyyaml that -I would hide.
    assert "python3 - <<" not in wf.read_text() or wf.name == "labels-sync.yml"
    if wf.name == "labels-sync.yml":
        assert "pull_request" not in str(_load(wf)["on"])


def test_no_action_step_echoes_the_session_to_the_log():
    # file_advisory.sh list, the review bodies and every tool result reach the log only if the
    # action is told to show its full output; the logs of this repository are public.
    for wf, job_id, _, step in _model_steps():
        assert str(step["with"].get("show_full_output", "false")).lower() == "false", (wf, job_id)


def test_forge_token_sessions_run_no_interpreter():
    # A model step holding the forge token as GH_TOKEN must not also hold an interpreter: with one,
    # a narrowed gh grant is narrow only on paper (Egzos/egzos#71 review, finding 1).
    inspected = set()
    for wf, job_id, job, step in _model_steps():
        if "forge" not in _gh_token(job, step):
            continue
        if "Bash(git:*)" in step["with"].get("claude_args", ""):
            continue  # builders push code by design; their reach is bounded by ownership and review
        inspected.add(job_id)
        args = step["with"]["claude_args"]
        assert not any(i in args for i in INTERPRETERS), (wf, job_id)
        # A script grant is an interpreter too once the session can rewrite the script: never both
        # (#71 review, round 3, finding 1).
        if "Bash(bash " in args:
            tools = re.search(r'--allowedTools "([^"]*)"', args).group(1).split(",")
            assert not {"Write", "Edit", "MultiEdit", "NotebookEdit"} & set(tools), (wf, job_id)
    # Never vacuous: a renamed token step or a token moved to the job still reaches the sweep.
    assert "a6-adversary-nightly" in inspected


def test_every_model_session_denies_the_process_environment():
    # The provider credential lives in the session's own environment. Read(//proc/**) denies Read,
    # Grep and Glob there, which closes it for the review sessions (their Bash is gh pr only). The
    # builders keep the deny but hold interpreters, so it does not close them (RD-005).
    seen = 0
    for wf, job_id, _, step in _model_steps():
        assert '--disallowedTools "Read(//proc/**)"' in step["with"]["claude_args"], (wf, job_id)
        seen += 1
    assert seen >= 4


def test_a6_pr_mode_disclosure_phrase_matches_the_charter():
    # The one sentence a6 may post on a security-class finding must read the same in the workflow
    # prompt and the charter, so the two cannot drift apart in the tree (platform#42 a6 review).
    charter = (ROOT / ".claude" / "agents" / "a6-adversary.md").read_text()
    (phrase,) = set(re.findall(r'"(security-class finding — awaiting [^"]+)"', charter))
    (step,) = [s for _, j, _, s in _model_steps() if j == "a6-adversary"]
    assert phrase in step["with"]["prompt"]


def test_verdict_requires_exactly_one_result_record():
    for job_id in sorted(REVIEW_JOBS):
        assert "if len(results) == 1 else None" in _verdict(job_id)


def test_builders_can_keep_their_pr_body_current():
    # CLAUDE.md requires the template filled completely and Herald distills the body, so a builder
    # that revises a PR must be able to revise its body (#93). Reviewers stay without it.
    seen = 0
    for wf, job_id, _, step in _model_steps():
        args = step["with"].get("claude_args", "")
        if "Bash(gh pr create:*)" in args:
            assert "Bash(gh pr edit:*)" in args, (wf.name, job_id)
            seen += 1
        else:
            assert "gh pr edit" not in args, (wf.name, job_id)
    assert seen >= 2


def _job(job_id):
    for wf in WORKFLOWS:
        jobs = _load(wf)["jobs"]
        if job_id in jobs:
            return jobs[job_id]
    raise KeyError(job_id)


def test_a6_suite_runs_in_a_job_holding_no_token():
    # A process one step starts outlives the step, so step order inside the job that mints the
    # forge token separates nothing: the suite runs in a job of its own (RD-005, #41 review).
    suite = _job("a6-adversary-suite")
    assert suite["permissions"] == {"contents": "read"}
    blob = str(suite)
    assert "secrets." not in blob and "create-github-app-token" not in blob
    assert "GH_TOKEN" not in blob
    (run,) = [s["run"] for s in suite["steps"] if s.get("id") == "suite"]
    # The output delimiter is not guessable from the suite's own text.
    assert "openssl rand" in run
    # The log line is pytest's own last line, not the first match anywhere in captured output.
    assert 'tail -n 2 "$OUT" | head -n 1' in run
    assert "::warning::" in run and "::error::" in run
    nightly = _job("a6-adversary-nightly")
    assert nightly["needs"] == "a6-adversary-suite"
    assert "!cancelled()" in nightly["if"]
    names = [s.get("name") or s.get("id") for s in nightly["steps"]]
    assert "adversarial-suite" not in names
    assert names.index("suite-result") < names.index("forge")
    (model,) = [s for s in nightly["steps"] if s.get("uses", "").startswith(ACTION)]
    assert "/tmp/adversarial-suite.txt" in model["with"]["prompt"]


@pytest.mark.parametrize("job_id", sorted(REVIEW_JOBS))
def test_review_sessions_never_execute_the_tree(job_id):
    # Code in the tree under review, run inside the review job, could rewrite the controls restored
    # from the base before the model uses them. The tests check runs the suites; the reviewer reads
    # its result (Egzos/egzos#71 review, finding 1 of the last round).
    (args,) = [s["with"]["claude_args"] for _, j, _, s in _model_steps() if j == job_id]
    assert not any(i in args for i in INTERPRETERS)
    assert "Bash(gh pr checks:*)" in args
    # gh pr checks resolves each check's workflow run, an Actions resource (#41 review).
    perms = _job(job_id)["permissions"]
    assert {perms.get(k) for k in ("checks", "statuses", "actions")} == {"read"}


@pytest.mark.parametrize("job_id", ["a2-conformance", "a6-adversary"])
def test_not_applicable_waits_for_a_successful_scope(job_id):
    (cond,) = [
        s["if"] for _, j, _, s in _steps() if j == job_id and s.get("name") == "not-applicable"
    ]
    assert "steps.scope.outcome == 'success'" in cond


def test_a2_scope_fails_closed_when_git_fails():
    # A git failure must not read as "no UI paths changed" and early-pass the check (#23).
    (run,) = [
        s["run"] for _, j, _, s in _steps() if j == "a2-conformance" and s.get("id") == "scope"
    ]
    assert 'if ! CHANGED=$(git diff --name-only "origin/${BASE_REF}...HEAD"' in run
    assert "|| true" not in run
    assert "2>/dev/null" not in run


REVIEW_TOOLS = {
    "Read", "Write", "Grep", "Glob", "StructuredOutput",
    "Bash(gh pr view:*)", "Bash(gh pr diff:*)", "Bash(gh pr checks:*)",
}


@pytest.mark.parametrize("job_id", sorted(REVIEW_JOBS))
def test_review_sessions_hold_exactly_the_review_tools(job_id):
    # An allowlist, not a denylist of interpreters: Bash(node:*), Bash(sh ...) or a widened
    # Bash(gh:*) would each pass a denylist (#79 review).
    (args,) = [s["with"]["claude_args"] for _, j, _, s in _model_steps() if j == job_id]
    tools = re.search(r'--allowedTools "([^"]*)"', args).group(1).split(",")
    assert set(tools) == REVIEW_TOOLS


def test_the_tests_check_runs_what_rd005_relies_on():
    # RD-005 half 2 is accepted only while `tests` runs this; an echo would keep every other test
    # green (Egzos/egzos-platform#41 review).
    runs = [s.get("run", "").strip() for s in _job("tests")["steps"]]
    # Bound to the invocation itself, so an echo of the command does not satisfy it.
    assert "ruff check ." in runs and "pytest -q" in runs


def _verdict(job_id):
    (run,) = [s["run"] for _, j, _, s in _steps() if j == job_id and s.get("name") == "Verdict"]
    return run


@pytest.mark.parametrize("job_id", sorted(REVIEW_JOBS))
def test_verdict_fails_closed(job_id):
    run = _verdict(job_id)
    assert 'get("verdict", "pass")' not in run
    assert "format(**f)" not in run


def test_a6_verdict_prints_no_finding_prose():
    # The log is public; a6's summary, paths and notes live in its comment and advisories (F15).
    run = _verdict("a6-adversary")
    assert 'f.get("note"' not in run and 'f.get("path"' not in run
    assert 'print("Summary' not in run


EXEC_FILE_EXPR = "${{ steps.review.outputs.execution_file }}"


def test_structured_output_never_reaches_a_step_env():
    # GitHub prints a step's env in its log. Review output carries notes and paths, so every
    # Verdict reads it from the execution file (Egzos/egzos#79, Egzos/egzos-platform#42).
    seen = 0
    for wf in WORKFLOWS:
        for job_id, job in _load(wf)["jobs"].items():
            for s in job.get("steps", []):
                where = (wf.name, job_id, s.get("name"))
                assert "outputs.structured_output" not in json.dumps(s.get("env", {})), where
                if s.get("name") == "Verdict":
                    assert s["env"]["EXEC_FILE"] == EXEC_FILE_EXPR, where
                    seen += 1
    assert seen == len(REVIEW_JOBS)


def test_turn_budget_is_one_number_where_it_is_diagnosed():
    # diagnose-failure compares num_turns with MAX_TURNS; a job whose --max-turns is a second,
    # hand-synced literal can misdiagnose the ceiling (#53 item 3).
    for wf in WORKFLOWS:
        doc = _load(wf)
        for job_id, job in doc["jobs"].items():
            steps = job.get("steps", [])
            if not any(s.get("name") == "diagnose-failure" for s in steps):
                continue
            assert "MAX_TURNS" in doc.get("env", {}), (wf.name, job_id)
            args = [s["with"]["claude_args"] for s in steps if s.get("uses", "").startswith(ACTION)]
            assert args and all("--max-turns ${{ env.MAX_TURNS }}" in a for a in args), job_id


def test_no_model_step_holds_raw_gh_api():
    bad = [
        (wf, job_id)
        for wf, job_id, _, step in _steps()
        if step.get("uses", "").startswith(ACTION)
        and "Bash(gh api:*)" in step["with"].get("claude_args", "")
    ]
    assert bad == []


def test_core_queue_wip_cap_cannot_read_zero_while_a_pr_is_open():
    # #22: the default `gh pr list` page is 30, and two dispatches for one agent raced.
    job = _load(ROOT / ".github" / "workflows" / "core-queue.yml")["jobs"]["core-queue"]
    group = job["concurrency"]["group"]
    assert "inputs.agent" in group and "github.event.label.name" in group
    assert job["concurrency"]["cancel-in-progress"] is False
    (wip,) = [s["run"] for s in job["steps"] if s.get("name") == "wip-check"]
    assert "--limit" in wip
    assert "isDraft" in wip  # a killed run's own draft resumes rather than blocks (RD-004)
