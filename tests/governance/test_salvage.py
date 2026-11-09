# Copyright 2026 Ali Sasanian
# SPDX-License-Identifier: LicenseRef-PolyForm-Strict-1.0.0
"""No builder run's work is ever lost (the Chief, 2026-11-09).

Every job that runs a builder session ends the session before the job's own limit and
then runs `salvage`, which commits what the session wrote, pushes it to the issue's branch
and opens the draft PR the next run resumes from. This pins the wiring on every builder job
and runs the salvage script itself against a throwaway repository.
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
PUSH_URL = 'url="https://x-access-token:${GH_TOKEN}@github.com/${REPO}.git"'
TOKEN = "${{ steps.forge.outputs.token }}"


def _jobs():
    for name, jobs in BUILDERS.items():
        wf = yaml.safe_load((WORKFLOWS / name).read_text(encoding="utf-8"))
        for job in jobs:
            yield name, job, wf["jobs"][job]


def _salvage(spec):
    return [s for s in spec["steps"] if s.get("name") == "salvage"]


@pytest.mark.parametrize(
    "name,job,spec", list(_jobs()), ids=lambda v: v if isinstance(v, str) else ""
)
def test_every_builder_session_is_followed_by_salvage(name, job, spec):
    steps = spec["steps"]
    build = [i for i, s in enumerate(steps) if "claude-code-action" in str(s.get("uses", ""))]
    assert len(build) == 1, f"{name}:{job} needs exactly one session step"
    session = steps[build[0]]
    assert session.get("id") == "build", f"{name}:{job}: the session step's id must be build"
    assert int(session["timeout-minutes"]) < int(spec["timeout-minutes"]), "session ends first"
    after = [s for s in steps[build[0] + 1:] if s.get("name") == "salvage"]
    assert len(after) == 1, f"{name}:{job} has no salvage step after the session"
    s = after[0]
    assert str(s["if"]).startswith("always()"), "salvage must run however the session ended"
    assert s["env"]["PATH"] == "/usr/bin:/bin"
    assert s["env"]["GH_TOKEN"] == TOKEN
    assert s["env"]["OUTCOME"] == "${{ steps.build.outcome }}"


def test_every_salvage_step_runs_the_same_script():
    assert len({_salvage(spec)[0]["run"] for _, _, spec in _jobs()}) == 1


SCRIPT = next(_salvage(spec)[0]["run"] for _, _, spec in _jobs())
BRANCH = "agent/a-builder/issue-7"
GH_STUB = (
    "#!/bin/bash\n"
    'echo "gh $*" >> {log}\n'
    "[ \"$1 $2\" = 'pr create' ] && echo https://x/pull/42\n"
    "exit 0\n"
)


def _sh(cmd, cwd):
    done = subprocess.run(cmd, cwd=cwd, shell=True, check=True, capture_output=True, text=True)
    return done.stdout.strip()


def _run(setup, outcome):
    d = tempfile.mkdtemp()
    try:
        remote, work, stub = f"{d}/remote.git", f"{d}/work", f"{d}/stub"
        os.mkdir(stub)
        _sh(f"git init -q --bare {remote} && git init -q -b main {work}", d)
        _sh(
            "git config user.email t@t && git config user.name t && echo base > a.txt"
            " && git add . && git commit -qm base"
            f" && git remote add origin {remote} && git push -q origin main && git fetch -q origin",
            work,
        )
        with open(f"{stub}/gh", "w") as fh:
            fh.write(GH_STUB.format(log=f"{d}/gh.log"))
        os.chmod(f"{stub}/gh", 0o755)
        setup(work)
        script = SCRIPT.replace(PUSH_URL, f'url="{remote}"')
        assert script != SCRIPT, "the push URL line moved; update this test with it"
        env = {
            "PATH": f"{stub}:/usr/bin:/bin", "HOME": d, "AGENT": "a-builder", "ISSUE": "7",
            "OUTCOME": outcome, "REPO": "o/r", "RUN_ID": "99", "RUN_URL": "https://run",
            "DEFAULT_BRANCH": "main", "GH_TOKEN": "t",
        }
        done = subprocess.run(
            ["bash", "-c", script], cwd=work, capture_output=True, text=True, env=env
        )
        assert done.returncode == 0, done.stderr
        listed = _sh("git branch --format='%(refname:short)'", remote)
        branches = [b for b in listed.split("\n") if b]
        log_path = pathlib.Path(f"{d}/gh.log")
        log = log_path.read_text() if log_path.exists() else ""
        files = {
            b: set(_sh(f"git ls-tree -r --name-only {b}", remote).split("\n")) for b in branches
        }
        return files, log
    finally:
        shutil.rmtree(d)


def test_uncommitted_work_on_main_is_saved_to_the_issue_branch_with_a_draft():
    files, log = _run(
        lambda w: _sh("mkdir -p src && echo w > src/new.ts && echo c > a.txt", w), "failure"
    )
    assert "src/new.ts" in files[BRANCH]
    assert "pr create --repo o/r --draft" in log
    assert "issue comment 7" in log


def test_unpushed_commits_and_uncommitted_work_are_both_saved():
    def setup(w):
        _sh(f"git checkout -qb {BRANCH} && echo 1 > c1.ts && git add . && git commit -qm c1", w)
        _sh("echo 2 > c2.ts", w)

    files, _ = _run(setup, "failure")
    assert {"c1.ts", "c2.ts"} <= files[BRANCH]


def test_a_credential_shaped_change_is_left_out():
    def setup(w):
        _sh("printf 'T=ghs_%s\\n' $(printf 'a%.0s' $(seq 1 36)) > leak.sh", w)
        _sh("echo ok > keep.ts", w)

    files, _ = _run(setup, "failure")
    assert "keep.ts" in files[BRANCH]
    assert "leak.sh" not in files[BRANCH]


def test_github_and_claude_paths_are_never_staged():
    def setup(w):
        _sh("mkdir -p .github/workflows .claude && echo x > .github/workflows/x.yml", w)
        _sh("echo y > .claude/y.md && echo ok > keep.ts", w)

    files, _ = _run(setup, "failure")
    assert "keep.ts" in files[BRANCH]
    assert not any(f.startswith((".github/", ".claude/")) for f in files[BRANCH])


def test_a_successful_session_is_pushed_but_never_added_to():
    def setup(w):
        _sh(f"git checkout -qb {BRANCH} && echo d > done.ts && git add . && git commit -qm d", w)
        _sh("echo j > junk.tmp", w)

    files, log = _run(setup, "success")
    assert "done.ts" in files[BRANCH]
    assert "junk.tmp" not in files[BRANCH]
    assert "issue comment" not in log


def test_a_diverged_remote_branch_gets_the_work_on_a_salvage_branch():
    def setup(w):
        _sh(f"git checkout -qb {BRANCH} && echo r > r.ts && git add . && git commit -qm r", w)
        _sh(f"git push -q origin {BRANCH}", w)
        _sh("git reset -q --hard origin/main && echo m > mine.ts", w)

    files, _ = _run(setup, "failure")
    assert "mine.ts" in files[f"{BRANCH}-salvage-99"]


def test_a_run_that_wrote_nothing_pushes_nothing():
    files, log = _run(lambda w: None, "failure")
    assert BRANCH not in files
    assert "pr create" not in log
