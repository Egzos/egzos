# Copyright 2026 Ali Sasanian
# SPDX-License-Identifier: Apache-2.0
"""file_advisory.sh against a stub `gh`: update appends and never replaces the filed body."""

import json
import os
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / ".github" / "scripts" / "file_advisory.sh"
GHSA = "GHSA-2c3f-4g5h-6j7m"

FILED = {
    "ghsa_id": GHSA,
    "state": "draft",
    "summary": "s",
    "description": "ORIGINAL REPRO",
    # The read shape: GET carries fields and nulls a PATCH body does not take back.
    "vulnerabilities": [{
        "package": {"ecosystem": "other", "name": "egzos", "purl": None},
        "vulnerable_version_range": "< 0.1",
        "patched_versions": None,
        "vulnerable_functions": [],
        "cvss": None,
    }],
}

STUB = """#!/usr/bin/env bash
# Records every call; answers GET with the filed advisory, PATCH/POST with the id.
printf '%s\\n' "$*" >> "$STUB_DIR/calls"
if [[ "$*" == *"-X PATCH"* || "$*" == *"-X POST"* ]]; then
  cat > "$STUB_DIR/sent.json"
  echo "$GHSA"
else
  cat "$STUB_DIR/filed.json"
fi
"""


@pytest.fixture
def stub(tmp_path):
    bindir = tmp_path / "bin"
    bindir.mkdir()
    gh = bindir / "gh"
    gh.write_text(STUB)
    gh.chmod(0o755)
    (tmp_path / "filed.json").write_text(json.dumps(FILED))
    env = {
        **os.environ,
        "PATH": f"{bindir}:{os.environ['PATH']}",
        "STUB_DIR": str(tmp_path),
        "GHSA": GHSA,
        "GITHUB_REPOSITORY": "Egzos/x",
        "GH_TOKEN": "t",
    }
    return tmp_path, env


def _run(env, *args):
    return subprocess.run(
        ["bash", str(SCRIPT), *args], capture_output=True, text=True, env=env, check=False
    )


def test_update_appends_and_keeps_the_filed_reproduction(stub):
    d, env = stub
    new = d / "new.json"
    new.write_text(json.dumps({
        "description": "second vector",
        "vulnerabilities": [{"package": {"ecosystem": "other", "name": "egzos-platform"}}],
    }))
    res = _run(env, "update", GHSA, str(new))
    assert res.returncode == 0, res.stderr
    assert res.stdout.strip() == GHSA
    sent = json.loads((d / "sent.json").read_text())
    assert sent["description"].startswith("ORIGINAL REPRO\n\n### Update ")
    assert sent["description"].endswith("second vector")
    assert {v["package"]["name"] for v in sent["vulnerabilities"]} == {"egzos", "egzos-platform"}
    assert set(sent) == {"description", "vulnerabilities"}
    writable = {"package", "vulnerable_version_range", "patched_versions", "vulnerable_functions"}
    for v in sent["vulnerabilities"]:
        assert set(v) <= writable, v
        assert set(v["package"]) == {"ecosystem", "name"}
        assert None not in v.values()
    (filed,) = [v for v in sent["vulnerabilities"] if v["package"]["name"] == "egzos"]
    assert filed["vulnerable_version_range"] == "< 0.1"


def test_update_without_a_description_is_refused(stub):
    d, env = stub
    new = d / "new.json"
    new.write_text(json.dumps({"severity": "high"}))
    res = _run(env, "update", GHSA, str(new))
    assert res.returncode == 2
    assert not (d / "sent.json").exists()


def test_update_rejects_a_malformed_id(stub):
    d, env = stub
    new = d / "new.json"
    new.write_text(json.dumps({"description": "x"}))
    assert _run(env, "update", "GHSA-nope", str(new)).returncode == 2


def test_create_sends_the_file_and_prints_only_the_id(stub):
    d, env = stub
    body = d / "a.json"
    body.write_text(json.dumps({"summary": "s", "description": "REPRO"}))
    res = _run(env, "create", str(body))
    assert res.returncode == 0
    assert res.stdout.strip() == GHSA
    assert "REPRO" not in res.stdout + res.stderr


def test_unknown_verb_is_refused(stub):
    _, env = stub
    assert _run(env, "delete", GHSA).returncode == 2
