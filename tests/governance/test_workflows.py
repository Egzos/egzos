# Copyright 2026 Ali Sasanian
# SPDX-License-Identifier: Apache-2.0
"""Control-plane invariants over .github/workflows/*.yml (#44 item 2).

Each of these was established by a fix and, until now, held only as long as the next reviewer
remembered it. Parsing the workflow files moves them into the required `tests` check.
"""

import re
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
    step_names, allowed = [], ""
    for _, jid, _, step in _steps():
        if jid != job_id:
            continue
        step_names.append(step.get("name", ""))
        if step.get("uses", "").startswith(ACTION):
            allowed = step["with"]["claude_args"]
    assert "control-inputs-from-base" in step_names
    assert step_names.index("control-inputs-from-base") < step_names.index("Verdict")
    assert "Bash(bash /tmp/post_review_comment.sh:*)" in allowed
    assert ".github/scripts/post_review_comment.sh" not in allowed


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
