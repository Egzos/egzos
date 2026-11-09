# Copyright 2026 Ali Sasanian
# SPDX-License-Identifier: LicenseRef-PolyForm-Strict-1.0.0
"""No builder run's work is ever lost (the Chief, 2026-11-09).

Every job that runs a builder session ends the session before the job's own limit and then runs `salvage`, which
commits what the session wrote, pushes it to the issue's branch and opens the draft PR the next run resumes from.
This pins the wiring on every builder job and runs the salvage script itself against a throwaway repository.
"""
import os
import pathlib
import shutil
import subprocess
import tempfile

import pytest
import yaml

ROOT = pathlib.Path(__file__).resolve().parents[2]
WORKFLOWS = ROOT / ".github" / "workflows"
BUILDERS = {
    "core-queue.yml": ["core-queue"],
    "a1p-planner.yml": ["a1p-planner"],
}


def _jobs():
    for name, jobs in BUILDERS.items():
        wf = yaml.safe_load((WORKFLOWS / name).read_text(encoding="utf-8"))
        for job in jobs:
            yield name, job, wf["jobs"][job]


@pytest.mark.parametrize("name,job,spec", list(_jobs()), ids=lambda v: v if isinstance(v, str) else "")
def test_every_builder_session_is_followed_by_salvage(name, job, spec):
    steps = spec["steps"]
    build = [i for i, s in enumerate(steps) if "anthropics/claude-code-action" in str(s.get("uses", ""))]
    assert len(build) == 1 and steps[build[0]].get("id") == "build", f"{name}:{job} needs one session step with id build"
    assert int(steps[build[0]]["timeout-minutes"]) < int(spec["timeout-minutes"]), "the session must end before the job does"
    after = [s for s in steps[build[0] + 1:] if s.get("name") == "salvage"]
    assert len(after) == 1, f"{name}:{job} has no salvage step after the session"
    s = after[0]
    assert str(s["if"]).startswith("always()"), "salvage must run however the session ended"
    assert s["env"]["PATH"] == "/usr/bin:/bin" and s["env"]["GH_TOKEN"] == "${{ steps.forge.outputs.token }}"
    assert s["env"]["OUTCOME"] == "${{ steps.build.outcome }}"


def test_every_salvage_step_runs_the_same_script():
    scripts = {next(s["run"] for s in spec["steps"] if s.get("name") == "salvage") for _, _, spec in _jobs()}
    assert len(scripts) == 1


SCRIPT = next(s["run"] for _, _, spec in _jobs() for s in spec["steps"] if s.get("name") == "salvage")
BRANCH = "agent/a-builder/issue-7"


def _sh(cmd, cwd):
    return subprocess.run(cmd, cwd=cwd, shell=True, check=True, capture_output=True, text=True).stdout.strip()


def _run(setup, outcome):
    d = tempfile.mkdtemp()
    try:
        remote, work, stub = f"{d}/remote.git", f"{d}/work", f"{d}/stub"
        os.mkdir(stub)
        _sh(f"git init -q --bare {remote} && git init -q -b main {work}", d)
        _sh("git config user.email t@t && git config user.name t && echo base > a.txt && git add . && git commit -qm base"
            f" && git remote add origin {remote} && git push -q origin main && git fetch -q origin", work)
        with open(f"{stub}/gh", "w") as fh:
            fh.write(f"#!/bin/bash\necho \"gh $*\" >> {d}/gh.log\n[ \"$1 $2\" = 'pr create' ] && echo https://x/pull/42\nexit 0\n")
        os.chmod(f"{stub}/gh", 0o755)
        setup(work)
        script = SCRIPT.replace('url="https://x-access-token:${GH_TOKEN}@github.com/${REPO}.git"', f'url="{remote}"')
        assert script != SCRIPT, "the push URL line moved; update this test with it"
        env = {"PATH": f"{stub}:/usr/bin:/bin", "HOME": d, "AGENT": "a-builder", "ISSUE": "7", "OUTCOME": outcome,
               "REPO": "o/r", "RUN_ID": "99", "RUN_URL": "https://run", "DEFAULT_BRANCH": "main", "GH_TOKEN": "t"}
        done = subprocess.run(["bash", "-c", script], cwd=work, capture_output=True, text=True, env=env)
        assert done.returncode == 0, done.stderr
        branches = _sh("git branch --format='%(refname:short)'", remote).split("\n")
        log = pathlib.Path(f"{d}/gh.log").read_text() if os.path.exists(f"{d}/gh.log") else ""
        files = {b: set(_sh(f"git ls-tree -r --name-only {b}", remote).split("\n")) for b in branches if b}
        return files, log
    finally:
        shutil.rmtree(d)


def test_uncommitted_work_on_main_is_saved_to_the_issue_branch_with_a_draft():
    files, log = _run(lambda w: _sh("mkdir -p src && echo w > src/new.ts && echo c > a.txt", w), "failure")
    assert "src/new.ts" in files[BRANCH] and "pr create --repo o/r --draft" in log and "issue comment 7" in log


def test_unpushed_commits_and_uncommitted_work_are_both_saved():
    files, _ = _run(lambda w: _sh(f"git checkout -qb {BRANCH} && echo 1 > c1.ts && git add . && git commit -qm c1 && echo 2 > c2.ts", w), "failure")
    assert {"c1.ts", "c2.ts"} <= files[BRANCH]


def test_a_credential_shaped_change_is_left_out():
    files, _ = _run(lambda w: _sh("printf 'T=ghs_%s\\n' $(printf 'a%.0s' $(seq 1 36)) > leak.sh && echo ok > keep.ts", w), "failure")
    assert "keep.ts" in files[BRANCH] and "leak.sh" not in files[BRANCH]


def test_github_and_claude_paths_are_never_staged():
    files, _ = _run(lambda w: _sh("mkdir -p .github/workflows .claude && echo x > .github/workflows/x.yml && echo y > .claude/y.md && echo ok > keep.ts", w), "failure")
    assert "keep.ts" in files[BRANCH] and not any(f.startswith((".github/", ".claude/")) for f in files[BRANCH])


def test_a_successful_session_is_pushed_but_never_added_to():
    files, log = _run(lambda w: _sh(f"git checkout -qb {BRANCH} && echo d > done.ts && git add . && git commit -qm d && echo j > junk.tmp", w), "success")
    assert "done.ts" in files[BRANCH] and "junk.tmp" not in files[BRANCH] and "issue comment" not in log


def test_a_diverged_remote_branch_gets_the_work_on_a_salvage_branch():
    def setup(w):
        _sh(f"git checkout -qb {BRANCH} && echo r > r.ts && git add . && git commit -qm r && git push -q origin {BRANCH}", w)
        _sh("git reset -q --hard origin/main && echo m > mine.ts", w)
    files, _ = _run(setup, "failure")
    assert "mine.ts" in files[f"{BRANCH}-salvage-99"]


def test_a_run_that_wrote_nothing_pushes_nothing():
    files, log = _run(lambda w: None, "failure")
    assert BRANCH not in files and "pr create" not in log
