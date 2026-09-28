# Copyright 2026 Ali Sasanian
# SPDX-License-Identifier: Apache-2.0
"""Control-plane invariants over .github/workflows/*.yml (#44 item 2).

Each of these was established by a fix and, until now, held only as long as the next reviewer
remembered it. Parsing the workflow files moves them into the required `tests` check.
"""

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
    # From the base commit by SHA, into a fresh file, after the session: never a path it could
    # have rewritten.
    assert 'git show "${BASE_SHA}:.github/scripts/post_review_comment.sh"' in run
    assert "mktemp" in run
    assert post["env"]["BASE_SHA"] == "${{ github.event.pull_request.base.sha }}"
    # Posted on failure too (a turn-capped review is still the Chief's to read), never when
    # cancelled.
    assert "!cancelled()" in post["if"] and "skipped" in post["if"]


@pytest.mark.parametrize("job_id", sorted(REVIEW_JOBS))
def test_steps_after_the_model_run_pinned_and_isolated(job_id):
    # Anything the session planted on PATH, or in the checkout that `python3 -` would import from,
    # must not run with the job's token after it.
    for step in _after_model(job_id):
        assert step.get("env", {}).get("PATH") == "/usr/bin:/bin", step.get("name")
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
