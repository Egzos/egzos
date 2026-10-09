# Copyright 2026 Ali Sasanian
# SPDX-License-Identifier: Apache-2.0
"""Control-plane invariants over .github/workflows/*.yml (#44 item 2).

Each of these was established by a fix and, until now, held only as long as the next reviewer
remembered it. Parsing the workflow files moves them into the required `tests` check.
"""

import json
import os
import re
import subprocess
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
                       "-name .claude -prune", r"(^|/)\.claude/",
                       "REVIEW-DECISIONS.md"):
            assert needle in run, (wf, job_id, needle)


@pytest.mark.parametrize("job_id", sorted(REVIEW_JOBS))
def test_control_inputs_cleanup_removes_every_kind_of_entry(job_id, tmp_path):
    # Runs the step's own find|xargs against a tree holding each shape a PR could plant: a nested
    # .claude directory, a .claude symlink to a PR-chosen directory, a .claude regular file, and
    # nested CLAUDE.md / CLAUDE.local.md / .mcp.json, one of them a symlink (platform#46).
    (step,) = [s for _, j, _, s in _steps()
               if j == job_id and s.get("name") == "control-inputs-from-base"]
    pattern = r"(find \. -path \./\.git -prune.*?xargs -0 -r rm -rf --)"
    cmd = re.search(pattern, step["run"], re.DOTALL)
    assert cmd, job_id
    root = tmp_path / "tree"
    (root / "payload" / "agents").mkdir(parents=True)
    (root / "payload" / "settings.json").write_text("{}")
    (root / "a" / "b").mkdir(parents=True)
    (root / "a" / "b" / ".claude").symlink_to(root / "payload")
    (root / "c" / ".claude" / "agents").mkdir(parents=True)
    (root / "d").mkdir()
    (root / "d" / ".claude").write_text("x")
    (root / "e").mkdir()
    (root / "e" / "CLAUDE.md").symlink_to(root / "payload" / "settings.json")
    (root / "e" / "CLAUDE.local.md").write_text("x")
    (root / "e" / ".mcp.json").write_text("{}")
    (root / "keep.txt").write_text("x")
    subprocess.run(["bash", "-c", cmd.group(1)], cwd=root, check=True)
    for gone in ("a/b/.claude", "c/.claude", "d/.claude", "e/CLAUDE.md", "e/CLAUDE.local.md",
                 "e/.mcp.json"):
        assert not os.path.lexists(root / gone), (job_id, gone)
    assert (root / "keep.txt").exists()
    # rm removes a symlink, never its target: a `.claude -> /tmp` must not take the charter with it.
    assert (root / "payload" / "settings.json").exists()


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
            # The grant is used: the body is revised before the PR is marked ready (#99), and
            # `gh pr edit` never retargets the base or touches labels.
            prompt = " ".join(step["with"]["prompt"].split())
            assert "rewrite the PR body with `gh pr edit --body-file`" in prompt, (wf.name, job_id)
            assert "never `--base`, `--add-label` or `--remove-label`" in prompt, (wf.name, job_id)
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
    # The detail leaves the job as an artifact, never as a job output or a step env, which the
    # run log prints.
    assert "outputs" not in suite and "GITHUB_OUTPUT" not in run
    (up,) = [s for s in suite["steps"] if s.get("uses", "").startswith("actions/upload-artifact@")]
    assert up["with"]["retention-days"] == 1
    # The log line is pytest's own last line, not the first match anywhere in captured output.
    assert 'tail -n 2 "$OUT" | head -n 1' in run
    assert "::warning::" in run and "::error::" in run
    nightly = _job("a6-adversary-nightly")
    assert nightly["needs"] == "a6-adversary-suite"
    assert "!cancelled()" in nightly["if"]
    names = [s.get("name") or s.get("id") for s in nightly["steps"]]
    assert "adversarial-suite" not in names
    assert names.index("suite-result") < names.index("forge")
    assert "needs." not in str(nightly["steps"])
    (down,) = [s for s in nightly["steps"]
               if s.get("uses", "").startswith("actions/download-artifact@")]
    assert down["with"] == {"name": up["with"]["name"], "path": "/tmp"}
    (model,) = [s for s in nightly["steps"] if s.get("uses", "").startswith(ACTION)]
    assert "/tmp/adversarial-suite.txt" in model["with"]["prompt"]


def test_nightly_integration_session_executes_nothing():
    # Drift F22: the suites run in a job holding no token; the session that holds the issue-write
    # token reads their result and runs no interpreter. F21: it carries the reviewers' diagnosis.
    suite = _job("integration-suite")
    assert suite["permissions"] == {"contents": "read"}
    blob = str(suite)
    assert "secrets." not in blob and "GH_TOKEN" not in blob and "outputs" not in suite
    nightly = _job("nightly-integration")
    assert nightly["needs"] == "integration-suite"
    assert "!cancelled()" in nightly["if"]
    (step,) = [s for _, j, _, s in _model_steps() if j == "nightly-integration"]
    assert not any(i in step["with"]["claude_args"] for i in INTERPRETERS)
    assert "/tmp/suite/suite.txt" in step["with"]["prompt"]
    names = [s.get("name") or s.get("uses", "") for s in nightly["steps"]]
    assert "diagnose-failure" in names and "diagnose-timeout" in names
    assert "pip install" not in str(nightly["steps"])
    # The charter is appended to that session's system prompt, so it must not claim the session
    # runs the suites (#105 review): the wording and the tool list move together.
    charter = " ".join((ROOT / ".claude" / "agents" / "a1r-reviewer.md").read_text().split())
    assert "run the suites" not in charter and "runs the suites" not in charter
    assert "execute nothing" in charter

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


def _fake_gh(tmp_path, routes):
    """A `gh` that serves `routes` (endpoint substring -> JSON value) and applies the caller's own
    --jq filter with jq, so a test exercises the workflow's real filter, not a pre-shaped answer."""
    fake = tmp_path / "bin"
    fake.mkdir()
    cases = []
    for i, (needle, value) in enumerate(routes):
        data = tmp_path / f"route{i}.json"
        data.write_text(json.dumps(value))
        cases.append(f'  *"{needle}"*) data="{data}" ;;\n')
    (fake / "gh").write_text(
        "#!/bin/bash\n"
        'expr=""; ep=""\n'
        'while [[ $# -gt 0 ]]; do case "$1" in\n'
        '  --jq) expr="$2"; shift 2 ;;\n'
        '  api|--paginate) shift ;;\n'
        '  *) ep="$1"; shift ;;\n'
        "esac; done\n"
        'case "$ep" in\n' + "".join(cases) + "  *) exit 1 ;;\nesac\n"
        'jq -r "$expr" "$data"\n'
    )
    (fake / "gh").chmod(0o755)
    return fake


def _label_events(pairs, label="security"):
    out = [{"event": "referenced", "actor": {"login": "x"}},
           {"event": "labeled", "actor": {"login": "egzos-forge[bot]"}, "label": {"name": "other"}}]
    for pair in pairs:
        event, login = pair.split(" ", 1)
        out.append({"event": event, "actor": {"login": login}, "label": {"name": label}})
    out.append({"event": "unlabeled", "actor": {"login": "Gond-ul"}, "label": {"name": "other"}})
    return out


def _a6_scope_run():
    (run,) = [s["run"] for _, j, _, s in _steps() if j == "a6-adversary" and s.get("id") == "scope"]
    (env,) = [s["env"] for _, j, _, s in _steps() if j == "a6-adversary" and s.get("id") == "scope"]
    return run, env


def test_security_label_removers_equal_the_size_exception_approvers():
    _, env = _a6_scope_run()
    ownership = yaml.safe_load((ROOT / ".github" / "OWNERSHIP.yml").read_text())
    assert json.loads(env["SECURITY_LABEL_REMOVERS"]) == ownership["size_exception_approvers"]


@pytest.mark.parametrize(
    ("has_label", "events", "applicable"),
    [
        ("true", [], "true"),
        ("false", [], "false"),
        # A builder's `gh pr edit --remove-label security` does not take the PR out of scope.
        ("false", ["labeled Gond-ul", "unlabeled egzos-forge[bot]"], "true"),
        ("false", ["labeled egzos-forge[bot]", "unlabeled github-actions[bot]"], "true"),
        # Only an approver's removal does, and only while it is the latest label event.
        ("false", ["labeled egzos-forge[bot]", "unlabeled Gond-ul"], "false"),
        ("false", ["labeled Gond-ul", "unlabeled chief-proxy[bot]"], "false"),
        ("false", ["unlabeled Gond-ul", "labeled x", "unlabeled egzos-forge[bot]"], "true"),
        # A latest event that is a labeling, even by an approver, is never an exemption.
        ("false", ["labeled Gond-ul"], "true"),
        # A login that merely contains an approver's name is not that approver.
        ("false", ["labeled Gond-ul", "unlabeled Gond-ul-bot"], "true"),
    ],
)
def test_a6_security_label_is_sticky(tmp_path, has_label, events, applicable):
    # Drift F23 / Egzos/egzos-platform#48: builders hold `gh pr edit --remove-label`.
    run, env = _a6_scope_run()
    fake = _fake_gh(tmp_path, [("issues/1/events", _label_events(events))])
    out = tmp_path / "out"
    proc_env = {
        "PATH": f"{fake}:/usr/bin:/bin",
        "HAS_SECURITY": has_label,
        "ACTOR": "egzos-forge[bot]",
        "REPO": "o/r",
        "PR": "1",
        "SECURITY_LABEL_REMOVERS": env["SECURITY_LABEL_REMOVERS"],
        "GITHUB_OUTPUT": str(out),
    }
    subprocess.run(["bash", "-c", run], env=proc_env, check=True, capture_output=True)
    assert out.read_text().strip() == f"applicable={applicable}"


def test_a6_scope_fails_closed_when_the_event_lookup_fails(tmp_path):
    run, env = _a6_scope_run()
    fake = tmp_path / "bin"
    fake.mkdir()
    (fake / "gh").write_text("#!/bin/bash\nexit 1\n")
    (fake / "gh").chmod(0o755)
    out = tmp_path / "out"
    proc = subprocess.run(
        ["bash", "-c", run],
        env={"PATH": f"{fake}:/usr/bin:/bin", "HAS_SECURITY": "false", "ACTOR": "x",
             "REPO": "o/r", "PR": "1", "GITHUB_OUTPUT": str(out),
             "SECURITY_LABEL_REMOVERS": env["SECURITY_LABEL_REMOVERS"]},
        capture_output=True,
    )
    assert proc.returncode != 0
    assert not out.exists() or "applicable=false" not in out.read_text()


REQUIRED_CHECKS = ("ownership", "tests", "a1r-review", "a2-conformance", "a6-adversary")


@pytest.mark.parametrize("job_id", REQUIRED_CHECKS)
def test_required_checks_fail_off_the_default_branch(job_id, tmp_path):
    # A run against another base says nothing about a merge into the default branch, and a
    # retarget with `gh pr edit --base` re-runs nothing (#99).
    first = _job(job_id)["steps"][0]
    assert first["name"] == "base-is-default-branch"
    assert first["if"] == "github.event_name == 'pull_request'"
    for base, code in (("main", 0), ("agent/x/y", 1), ("", 1)):
        proc = subprocess.run(
            ["bash", "-c", first["run"]],
            env={"PATH": "/usr/bin:/bin", "BASE_REF": base, "DEFAULT_BRANCH": "main"},
            capture_output=True,
        )
        assert proc.returncode == code, base


def test_pr_template_marks_author_claims_apart_from_ci():
    # Herald distils these fields to the Chief's phone, where a ticked box and a green check look
    # alike: author-supplied fields say so, and no box restates what a required check decides (#21).
    text = (ROOT / ".github" / "PULL_REQUEST_TEMPLATE.md").read_text()
    headings = re.findall(r"^## (.+)$", text, re.MULTILINE)
    assert "Checks (author's claims)" in headings
    assert "Risk (author's rating)" in headings
    assert "Checks" not in headings and "Risk" not in headings
    assert "not a CI result" in text
    boxes = re.findall(r"^- \[ \] (.+)$", text, re.MULTILINE)
    assert not any(("owned paths" in b) or ("size cap" in b) for b in boxes)


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
    # gh pr list under the default token: a private repository refuses it without this scope, and
    # a refused list fails the step, so no builder dispatches at all.
    assert job["permissions"].get("pull-requests") == "read"


def test_a6_dispatch_can_name_the_pr_whose_finding_awaits_an_advisory():
    # #123: a PR-mode security finding sits in code that is not on main, so a dispatch may name the
    # PR. Its unmerged diff is attacker-written text on a public repository, so it is read in a job
    # of its own whose session can file an advisory and nothing else, and only after a gate has
    # checked the number is digits and the PR carries the `security` label.
    wf = _load(ROOT / ".github" / "workflows" / "a6-adversary.yml")
    on = wf.get("on", wf.get(True))
    assert on["workflow_dispatch"]["inputs"]["pr"]["required"] is False
    job = wf["jobs"]["a6-adversary-pr-advisory"]
    assert "workflow_dispatch" in job["if"] and "inputs.pr != ''" in job["if"]
    assert job["permissions"] == {"contents": "read", "pull-requests": "read"}
    steps = job["steps"]
    names = [s.get("name") or s.get("id") or s.get("uses", "") for s in steps]
    gate = names.index("pr-input")
    model = next(i for i, s in enumerate(steps) if s.get("uses", "").startswith(ACTION))
    assert gate < names.index("forge") < model
    run = steps[gate]["run"]
    assert "^[0-9]+$" in run and 'index("security")' in run
    assert steps[gate]["env"]["PR"] == "${{ inputs.pr }}"
    args = steps[model]["with"]["claude_args"]
    tools = re.search(r'--allowedTools "([^"]*)"', args).group(1).split(",")
    assert set(tools) == {
        "Read", "Grep", "Glob", "Bash(gh pr view:*)", "Bash(gh pr diff:*)",
        "Bash(bash .github/scripts/file_advisory.sh:*)",
    }
    assert "inputs.pr" in steps[model]["with"]["prompt"]
    # The sweep of main reads no named PR: the untrusted diff never reaches its issue verbs. A
    # dispatch naming a PR runs neither the suite nor the sweep (#177 review).
    sweep = wf["jobs"]["a6-adversary-nightly"]["steps"]
    assert "inputs.pr" not in str(sweep)
    for name in ("a6-adversary-suite", "a6-adversary-nightly"):
        assert "inputs.pr == ''" in wf["jobs"][name]["if"], name


def test_a6_forge_tokens_are_minted_with_only_what_each_session_reaches():
    # The App's grant is wider than either a6 session needs; the token each one holds is narrowed
    # at mint, so GitHub enforces the boundary and not the tool list alone (#177 review).
    wf = _load(ROOT / ".github" / "workflows" / "a6-adversary.yml")
    want = {
        "a6-adversary-nightly": {
            "permission-contents": "read", "permission-issues": "write",
            "permission-pull-requests": "read", "permission-repository-advisories": "write",
        },
        "a6-adversary-pr-advisory": {
            "permission-contents": "read", "permission-pull-requests": "read",
            "permission-repository-advisories": "write",
        },
    }
    for job_id, perms in want.items():
        (mint,) = [s for s in wf["jobs"][job_id]["steps"] if s.get("id") == "forge"]
        got = {k: v for k, v in mint["with"].items() if k.startswith("permission-")}
        assert got == perms, job_id
