# Copyright 2026 Ali Sasanian
# SPDX-License-Identifier: LicenseRef-PolyForm-Strict-1.0.0
"""gh_issue.sh against a stub `gh`: bodies come from the scoped directory only, never carry a
credential, and each verb reaches one endpoint with fixed fields."""

import os
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / ".github" / "scripts" / "gh_issue.sh"

STUB = """#!/usr/bin/env bash
# A read (no -X) answers with the target issue's kind and labels, as the script's --jq shapes them;
# a write records its arguments one per line, and the body file gh would have read.
if [[ "$*" != *"-X "* ]]; then
  echo "${STUB_TARGET:-issue ,drift,}"
  exit 0
fi
printf '%s\\n' "$@" > "$STUB_DIR/args"
for a in "$@"; do
  [[ "$a" == body=@* ]] && cp "${a#body=@}" "$STUB_DIR/sent"
done
echo 7
"""


@pytest.fixture
def stub(tmp_path):
    bindir = tmp_path / "bin"
    bindir.mkdir()
    (bindir / "gh").write_text(STUB)
    (bindir / "gh").chmod(0o755)
    out = tmp_path / "out"
    out.mkdir()
    env = {
        **os.environ,
        "PATH": f"{bindir}:{os.environ['PATH']}",
        "STUB_DIR": str(tmp_path),
        "GITHUB_REPOSITORY": "Egzos/x",
        "GH_TOKEN": "ghs_forge_token_value",
        "AGENT_OUT_DIR": str(out),
    }
    return tmp_path, out, env


def _run(env, *args):
    return subprocess.run(
        ["bash", str(SCRIPT), *args], capture_output=True, text=True, env=env, check=False,
    )


def _args(tmp):
    return (tmp / "args").read_text().splitlines()


def test_create_posts_the_title_the_body_file_and_checked_labels(stub):
    tmp, out, env = stub
    (out / "b.md").write_text("finding\nsecond line\n")
    r = _run(env, "create", "adversarial: a finding", str(out / "b.md"), "agent:a6-adversary")
    assert r.returncode == 0, r.stderr
    assert r.stdout.strip() == "7"
    args = _args(tmp)
    assert args[:3] == ["api", "-X", "POST"] and "repos/Egzos/x/issues" in args
    assert "title=adversarial: a finding" in args and "labels[]=agent:a6-adversary" in args
    assert (tmp / "sent").read_text() == "finding\nsecond line\n"


@pytest.mark.parametrize(("verb", "method", "path"), [
    ("comment", "POST", "repos/Egzos/x/issues/12/comments"),
    ("edit", "PATCH", "repos/Egzos/x/issues/12"),
])
def test_comment_and_edit_reach_one_issue(stub, verb, method, path):
    tmp, out, env = stub
    (out / "b.md").write_text("body")
    r = _run(env, verb, "12", str(out / "b.md"))
    assert r.returncode == 0, r.stderr
    args = _args(tmp)
    assert args[1:3] == ["-X", method] and path in args


def test_a_body_file_outside_the_scoped_directory_is_refused(stub, tmp_path_factory):
    tmp, out, env = stub
    outside = tmp_path_factory.mktemp("elsewhere") / "b.md"
    outside.write_text("anything on the runner")
    (out / "link.md").symlink_to(outside)
    for path in (str(outside), str(out / "link.md"), "/proc/self/environ", f"{out}/../bin/gh"):
        r = _run(env, "comment", "12", path)
        assert r.returncode == 2 and "must be a non-empty file in" in r.stderr, path
    assert not (tmp / "args").exists()


def test_a_body_carrying_a_credential_is_refused(stub):
    tmp, out, env = stub
    (out / "b.md").write_text("see ghs_forge_token_value here")
    r = _run(env, "create", "t", str(out / "b.md"))
    assert r.returncode == 2 and "credential" in r.stderr
    assert not (tmp / "args").exists()


@pytest.mark.parametrize("args", [
    ("comment", "12; rm -rf /", "b.md"),
    ("edit", "-1", "b.md"),
    ("create", "two\nlines", "b.md"),
    ("create", "", "b.md"),
    ("create", "t", "b.md", "Bad Label"),
    ("create", "t", "b.md", "--body-file"),
    ("comment", "12"),
    ("view", "12", "b.md"),
])
def test_malformed_calls_are_refused_before_gh(stub, args):
    tmp, out, env = stub
    (out / "b.md").write_text("body")
    resolved = [str(out / a) if a == "b.md" else a for a in args]
    r = _run(env, *resolved)
    assert r.returncode == 2
    assert not (tmp / "args").exists()


@pytest.mark.parametrize(("verb", "target", "refusal"), [
    ("comment", "pr ,drift,", "is not an issue"),
    ("edit", "pr ,drift,", "is not an issue"),
    ("edit", "issue ,agent:a6-adversary,", "does not carry the drift label"),
    ("edit", "issue ,drifting,", "does not carry the drift label"),
])
def test_comment_and_edit_reach_issues_only_and_edit_the_drift_report_only(
    stub, verb, target, refusal,
):
    tmp, out, env = stub
    (out / "b.md").write_text("body")
    r = _run({**env, "STUB_TARGET": target}, verb, "12", str(out / "b.md"))
    assert r.returncode == 2 and refusal in r.stderr
    assert not (tmp / "args").exists()


def test_a_title_carrying_a_credential_is_refused(stub):
    tmp, out, env = stub
    (out / "b.md").write_text("body")
    r = _run(env, "create", f"leak {env['GH_TOKEN']}", str(out / "b.md"))
    assert r.returncode == 2 and "title carries a credential" in r.stderr
    assert not (tmp / "args").exists()
