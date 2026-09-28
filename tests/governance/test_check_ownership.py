# Copyright 2026 Ali Sasanian
# SPDX-License-Identifier: Apache-2.0
"""Unit tests for .github/scripts/check_ownership.py, the executable half of `ownership`.

Diff records are captured from a real `git diff --numstat -z` in a throwaway repository,
never hand-written, so a test passes only if the parser handles what git actually emits.
"""

import importlib.util
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / ".github" / "scripts" / "check_ownership.py"

_spec = importlib.util.spec_from_file_location("check_ownership", SCRIPT)
co = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(co)


def _git(repo, *args):
    return subprocess.run(
        ["git", "-C", str(repo), *args], check=True, capture_output=True, text=True
    ).stdout


@pytest.fixture
def repo(tmp_path):
    r = tmp_path / "r"
    r.mkdir()
    _git(r, "init", "-q", "-b", "main")
    _git(r, "config", "user.email", "t@example.invalid")
    _git(r, "config", "user.name", "t")
    _git(r, "config", "commit.gpgsign", "false")
    return r


def _write(repo, rel, text):
    p = repo / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text)


def _commit(repo, msg):
    _git(repo, "add", "-A")
    _git(repo, "commit", "-q", "-m", msg)


def _branch_diff(repo, mutate):
    """Commit a base, run `mutate` on a branch, return the raw -z numstat base...HEAD."""
    _git(repo, "checkout", "-q", "-b", "pr")
    mutate(repo)
    _commit(repo, "change")
    return _git(repo, "diff", "--numstat", "-z", "main...HEAD")


# ---------------------------------------------------------------------------
# Glob matching
# ---------------------------------------------------------------------------

@pytest.mark.parametrize(
    ("pattern", "path", "expected"),
    [
        ("a/**", "a/x", True),
        ("a/**", "a/x/y/z", True),
        ("a/*", "a/x/y", False),
        ("**/*.lock", "p/q/f.lock", True),
        ("**/*.lock", "f.lock", True),
        ("CLAUDE.md", "CLAUDE.md", True),
        ("CLAUDE.md", "docs/CLAUDE.md", False),
        ("src/**/x.py", "src/x.py", True),
    ],
)
def test_path_matches_glob(pattern, path, expected):
    assert co.path_matches_glob(pattern, path) is expected


# ---------------------------------------------------------------------------
# parse_numstat_z on real git output
# ---------------------------------------------------------------------------

def test_plain_and_binary_entries(repo):
    _write(repo, "a.txt", "1\n2\n")
    (repo / "b.bin").write_bytes(b"\x00\x01")
    _commit(repo, "base")

    def mutate(r):
        _write(r, "a.txt", "1\n2\n3\n")
        (r / "b.bin").write_bytes(b"\x00\x02")
        _write(r, "new dir/space name.txt", "x\n")

    raw = _branch_diff(repo, mutate)
    got = {e[2]: e for e in co.parse_numstat_z(raw)}
    assert got["a.txt"] == (1, 0, "a.txt", None)
    assert got["b.bin"] == (0, 0, "b.bin", None)
    assert got["new dir/space name.txt"] == (1, 0, "new dir/space name.txt", None)


def test_rename_yields_both_sides(repo):
    _write(repo, "docs/build/REVIEW-DECISIONS.md", "".join(f"line {i}\n" for i in range(40)))
    _commit(repo, "base")

    def mutate(r):
        (r / "spec").mkdir()
        _git(r, "mv", "docs/build/REVIEW-DECISIONS.md", "spec/rd.md")

    raw = _branch_diff(repo, mutate)
    assert co.parse_numstat_z(raw) == [(0, 0, "spec/rd.md", "docs/build/REVIEW-DECISIONS.md")]


def test_literal_arrow_filename_is_one_path(repo):
    _write(repo, "notes/a => b.txt", "x\n")
    _commit(repo, "base")

    def mutate(r):
        _write(r, "notes/a => b.txt", "x\ny\n")

    raw = _branch_diff(repo, mutate)
    assert co.parse_numstat_z(raw) == [(1, 0, "notes/a => b.txt", None)]


@pytest.mark.parametrize(
    "raw",
    [
        "3\t1\n",                        # two fields, no path
        "3\t1\tok.txt\0garbage\0",       # a record with no tabs mid-stream
        "3\t1\t\0only-old\0",            # rename missing its new path
        "3\t1\t\0\0new\0",               # rename with an empty old path
        "x\t1\tbad.txt\0",               # non-integer count
        "-\t4\thalf-binary.txt\0",       # one binary column, one text column
    ],
)
def test_unparseable_records_raise(raw):
    with pytest.raises(co.UnparseableNumstat):
        co.parse_numstat_z(raw)


def test_empty_diff_is_empty():
    assert co.parse_numstat_z("") == []


# ---------------------------------------------------------------------------
# parse_numstat (--numstat test path)
# ---------------------------------------------------------------------------

@pytest.mark.parametrize(
    "line",
    [
        "10\t2\tdocs/build/REVIEW-DECISIONS.md => spec/rd.md",
        "10\t2\tdocs/{a.md => b.md}",
    ],
)
def test_numstat_path_refuses_rename_display_strings(line):
    with pytest.raises(co.UnparseableNumstat):
        co.parse_numstat([line])


def test_numstat_path_plain_lines():
    assert co.parse_numstat(["1\t2\ta.py", "", "-\t-\tb.bin"]) == [(1, 2, "a.py"), (0, 0, "b.bin")]


# ---------------------------------------------------------------------------
# Size cap
# ---------------------------------------------------------------------------

def test_size_cap_charges_post_image_and_honours_excludes():
    entries = [
        (10, 5, "src/x.py", None),
        (100, 0, "uv.lock", None),
        (7, 0, "tests/fixtures/f.json", "src/f.json"),
        (1, 1, "src/moved.py", "tests/fixtures/moved.py"),
    ]
    assert co.compute_size(entries, ["**/*.lock", "tests/fixtures/**"]) == (17, 2)


# ---------------------------------------------------------------------------
# Labels and the size-exception waiver
# ---------------------------------------------------------------------------

def test_labels_json_does_not_split_on_commas():
    assert co.parse_labels_json('["x,size-exception"]') == {"x,size-exception"}


@pytest.mark.parametrize("raw", ["x,y", '{"a": 1}', "[1, 2]"])
def test_labels_json_rejects_non_arrays(raw):
    with pytest.raises(ValueError):
        co.parse_labels_json(raw)


@pytest.mark.parametrize(
    ("labels", "applier", "expected"),
    [
        ({"size-exception"}, "Gond-ul", True),
        ({"size-exception"}, "chief-proxy[bot]", True),
        ({"size-exception"}, "egzos-forge[bot]", False),
        ({"size-exception"}, "", False),
        (set(), "Gond-ul", False),
    ],
)
def test_size_exception_needs_an_approver(labels, applier, expected):
    approvers = ["Gond-ul", "chief-proxy[bot]"]
    assert co.size_exception_waives(labels, applier, approvers) is expected


# ---------------------------------------------------------------------------
# main(), end to end against a real repository
# ---------------------------------------------------------------------------

OWNERSHIP = {
    "branch_prefix": "agent/",
    "size_cap": {"lines": 50, "files": 30, "exclude": ["**/*.lock"]},
    "size_exception_approvers": ["Gond-ul"],
    "chief_only": ["docs/build/REVIEW-DECISIONS.md", ".github/OWNERSHIP.yml"],
    "governance_paths": [".github/**"],
    "agents": {
        "a1p-planner": {"paths": ["docs/**", "spec/**"], "exclusive": []},
        "a6-adversary": {"paths": ["adversarial/**"], "exclusive": ["adversarial/**"]},
        # The real overlap shape: one agent's paths contain another's exclusive tree.
        "a4s-atelier": {"paths": ["apps/**"], "exclusive": []},
        "a4g-atelier": {"paths": ["apps/bespoke/**"], "exclusive": ["apps/bespoke/**"]},
    },
}


def _run_main(repo, branch, env_extra=None):
    own = repo.parent / "OWNERSHIP.yml"
    own.write_text(json.dumps(OWNERSHIP))  # JSON is YAML
    env = {k: v for k, v in os.environ.items() if k not in ("PR_LABELS_JSON",
                                                            "SIZE_EXCEPTION_APPLIER")}
    env.update(env_extra or {})
    return subprocess.run(
        [sys.executable, str(SCRIPT), "--base", "main", "--head", "HEAD",
         "--branch", branch, "--ownership", str(own)],
        cwd=repo, capture_output=True, text=True, env=env, check=False,
    )


def test_main_fails_a_chief_only_rename_source(repo):
    _write(repo, "docs/build/REVIEW-DECISIONS.md", "".join(f"l{i}\n" for i in range(40)))
    _commit(repo, "base")
    _branch_diff(repo, lambda r: _git(r, "mv", "docs/build/REVIEW-DECISIONS.md", "docs/rd.md"))
    res = _run_main(repo, "agent/a1p-planner/x")
    assert res.returncode == 1
    assert "docs/build/REVIEW-DECISIONS.md" in res.stdout
    assert "moved to docs/rd.md" in res.stdout


def test_main_fails_another_agents_exclusive_path(repo):
    # a4s owns apps/**, which contains a4g's exclusive apps/bespoke/**: the path is owned, so only
    # the exclusive rule can fail it.
    _write(repo, "apps/bespoke/g.tsx", "x\n")
    _commit(repo, "base")
    _branch_diff(repo, lambda r: _write(r, "apps/bespoke/g.tsx", "y\n"))
    res = _run_main(repo, "agent/a4s-atelier/x")
    assert res.returncode == 1
    assert "exclusive to a4g-atelier" in res.stdout
    assert "not in a4s-atelier's owned paths" not in res.stdout


def test_main_passes_owned_change(repo):
    _write(repo, "docs/a.md", "x\n")
    _commit(repo, "base")
    _branch_diff(repo, lambda r: _write(r, "docs/a.md", "y\n"))
    res = _run_main(repo, "agent/a1p-planner/x")
    assert res.returncode == 0, res.stdout


def _oversize(repo):
    _write(repo, "docs/a.md", "x\n")
    _commit(repo, "base")
    _branch_diff(repo, lambda r: _write(r, "docs/a.md", "".join(f"{i}\n" for i in range(80))))


def test_main_size_cap_fails_agent_branch(repo):
    _oversize(repo)
    assert _run_main(repo, "agent/a1p-planner/x").returncode == 1


def test_main_size_exception_from_approver_waives(repo):
    _oversize(repo)
    res = _run_main(repo, "agent/a1p-planner/x", {
        "PR_LABELS_JSON": '["size-exception"]', "SIZE_EXCEPTION_APPLIER": "Gond-ul"})
    assert res.returncode == 0, res.stdout


def test_main_size_exception_from_forge_does_not_waive(repo):
    _oversize(repo)
    res = _run_main(repo, "agent/a1p-planner/x", {
        "PR_LABELS_JSON": '["size-exception"]', "SIZE_EXCEPTION_APPLIER": "egzos-forge[bot]"})
    assert res.returncode == 1
    assert "not in size_exception_approvers" in res.stdout


def test_main_size_cap_warns_on_human_branch(repo):
    _oversize(repo)
    res = _run_main(repo, "chief/x")
    assert res.returncode == 0
    assert "::warning::SIZE" in res.stdout


def test_main_fails_closed_on_malformed_labels(repo):
    _write(repo, "docs/a.md", "x\n")
    _commit(repo, "base")
    _branch_diff(repo, lambda r: _write(r, "docs/a.md", "y\n"))
    res = _run_main(repo, "agent/a1p-planner/x", {"PR_LABELS_JSON": "size-exception"})
    assert res.returncode == 1


def test_main_fails_closed_on_unparseable_numstat_file(repo, tmp_path):
    own = tmp_path / "OWNERSHIP.yml"
    own.write_text(json.dumps(OWNERSHIP))
    ns = tmp_path / "ns.txt"
    ns.write_text("10\t2\tdocs/build/REVIEW-DECISIONS.md => spec/rd.md\n")
    res = subprocess.run(
        [sys.executable, str(SCRIPT), "--base", "x", "--branch", "agent/a1p-planner/x",
         "--ownership", str(own), "--numstat", str(ns)],
        capture_output=True, text=True, check=False,
    )
    assert res.returncode == 1
    assert "unparseable" in res.stdout
