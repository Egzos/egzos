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
# Records every call; answers GET with the filed advisory, PATCH/POST with the id, and keeps the
# body it was sent, from --input's file or from stdin.
printf '%s\\n' "$*" >> "$STUB_DIR/calls"
input=""
args=("$@")
for ((i = 0; i < ${#args[@]}; i++)); do
  [[ "${args[i]}" == "--input" ]] && input="${args[i+1]}"
done
if [[ "$*" == *"-X PATCH"* || "$*" == *"-X POST"* ]]; then
  if [[ -n "$input" && "$input" != "-" ]]; then cat "$input"; else cat; fi > "$STUB_DIR/sent.json"
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


def _run(env, *args, stdin=None):
    return subprocess.run(
        ["bash", str(SCRIPT), *args], input=stdin, capture_output=True, text=True, env=env,
        check=False,
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


def _nulls(v):
    if isinstance(v, dict):
        return any(_nulls(x) for x in v.values())
    if isinstance(v, list):
        return any(_nulls(x) for x in v)
    return v is None


def test_update_drops_an_empty_package_rather_than_sending_nulls(stub):
    # A new vulnerability with no package must not become {"package": {"ecosystem": null, ...}}
    # (#41 review, minor 3).
    d, env = stub
    new = d / "new.json"
    new.write_text(json.dumps(
        {"description": "x", "vulnerabilities": [{"vulnerable_version_range": "< 2"}]}
    ))
    res = _run(env, "update", GHSA, str(new))
    assert res.returncode == 0, res.stderr
    sent = json.loads((d / "sent.json").read_text())
    assert not _nulls(sent)
    assert {"vulnerable_version_range": "< 2"} in sent["vulnerabilities"]


def test_update_drops_a_package_without_an_ecosystem(stub):
    # The API requires ecosystem whenever package is present (platform#42 review).
    d, env = stub
    new = d / "new.json"
    new.write_text(json.dumps(
        {"description": "x", "vulnerabilities": [{"package": {"name": "egzos"}}]}
    ))
    res = _run(env, "update", GHSA, str(new))
    assert res.returncode == 0, res.stderr
    sent = json.loads((d / "sent.json").read_text())
    assert all("ecosystem" in v["package"] for v in sent["vulnerabilities"] if "package" in v)


def test_update_keeps_an_ecosystem_only_package(stub):
    # name is optional in the advisory API; this repository's own code publishes no package
    # (platform#42 review).
    d, env = stub
    new = d / "new.json"
    new.write_text(json.dumps(
        {"description": "x", "vulnerabilities": [{"package": {"ecosystem": "other"}}]}
    ))
    res = _run(env, "update", GHSA, str(new))
    assert res.returncode == 0, res.stderr
    sent = json.loads((d / "sent.json").read_text())
    assert {"package": {"ecosystem": "other"}} in sent["vulnerabilities"]


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


def test_create_takes_the_body_on_stdin(stub):
    # The sweep's session holds no write tool, so `-` is how it hands over a body (#71 round 3).
    d, env = stub
    res = _run(env, "create", "-", stdin=json.dumps({"summary": "s", "description": "REPRO"}))
    assert res.returncode == 0, res.stderr
    assert res.stdout.strip() == GHSA
    assert "REPRO" not in res.stdout + res.stderr
    assert json.loads((d / "sent.json").read_text())["description"] == "REPRO"


def test_update_takes_the_body_on_stdin_and_still_appends(stub):
    d, env = stub
    res = _run(env, "update", GHSA, "-", stdin=json.dumps({"description": "third vector"}))
    assert res.returncode == 0, res.stderr
    sent = json.loads((d / "sent.json").read_text())
    assert sent["description"].startswith("ORIGINAL REPRO\n\n### Update ")
    assert sent["description"].endswith("third vector")


@pytest.mark.parametrize("stdin", ["", "not json", "[1, 2]"])
def test_stdin_body_must_be_a_json_object(stub, stdin):
    d, env = stub
    assert _run(env, "create", "-", stdin=stdin).returncode == 2
    assert not (d / "sent.json").exists()


def test_unknown_verb_is_refused(stub):
    _, env = stub
    assert _run(env, "delete", GHSA).returncode == 2


def test_create_sends_only_the_advisory_fields(stub):
    # #177 review: create is reachable from a session that read an unmerged diff. The endpoint also
    # takes credits, collaborating users and teams and a private fork; none of them may pass, or an
    # injected body could add an outside account to a private advisory.
    d, env = stub
    body = {
        "summary": "s",
        "description": "REPRO",
        "severity": "high",
        "cvss_vector_string": "CVSS:3.1/AV:N/AC:L/PR:N/UI:R/S:U/C:H/I:N/A:N",
        "cwe_ids": ["CWE-601"],
        "vulnerabilities": [{
            "package": {"ecosystem": "other", "name": "egzos", "purl": "x"},
            "vulnerable_version_range": "< 0.2",
            "cvss": None,
        }],
        "credits": [{"login": "outsider", "type": "reporter"}],
        "collaborating_users": ["outsider"],
        "collaborating_teams": ["outsiders"],
        "start_private_fork": True,
        "cve_id": "CVE-0000-0000",
    }
    r = _run(env, "create", "-", stdin=json.dumps(body))
    assert r.returncode == 0, r.stderr
    sent = json.loads((d / "sent.json").read_text())
    assert set(sent) == {
        "summary", "description", "severity", "cvss_vector_string", "cwe_ids", "vulnerabilities",
    }
    assert sent["vulnerabilities"] == [{
        "package": {"ecosystem": "other", "name": "egzos"},
        "vulnerable_version_range": "< 0.2",
    }]


def test_create_refuses_a_body_without_summary_and_description(stub):
    d, env = stub
    r = _run(env, "create", "-", stdin=json.dumps({"summary": "s"}))
    assert r.returncode == 2
    assert "summary and description" in r.stderr
    # Refused before any API call, not merely exited 2.
    assert not (d / "sent.json").exists() and not (d / "calls").exists()


def test_create_and_update_cut_a_vulnerability_to_the_same_fields(stub):
    # One WRITABLE filter serves both verbs (#181 review): one vulnerability, one shape sent.
    d, env = stub
    vuln = {
        "package": {"ecosystem": "other", "name": "egzos", "purl": "x"},
        "vulnerable_version_range": "< 0.3",
        "cvss": {"score": 9},
        "extra": True,
    }
    body = {"summary": "s", "description": "d", "vulnerabilities": [vuln]}
    assert _run(env, "create", "-", stdin=json.dumps(body)).returncode == 0
    created = json.loads((d / "sent.json").read_text())["vulnerabilities"]
    (d / "filed.json").write_text(json.dumps({**FILED, "vulnerabilities": []}))
    assert _run(env, "update", GHSA, "-", stdin=json.dumps(body)).returncode == 0
    updated = json.loads((d / "sent.json").read_text())["vulnerabilities"]
    assert created == updated == [{
        "package": {"ecosystem": "other", "name": "egzos"},
        "vulnerable_version_range": "< 0.3",
    }]
