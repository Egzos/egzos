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
import yaml

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


# Every rename shape whose display form #19 captured (brace prefix, brace suffix, across trees,
# prefix-and-edit, an empty side), read from real `git diff --numstat -z` output: -z always
# carries the two paths whole, so no display form reaches the parser (#62).
@pytest.mark.parametrize(
    ("old", "new"),
    [
        ("docs/a.md", "docs/b.md"),                    # same directory: docs/{a.md => b.md}
        ("src/pkg/mod.py", "lib/pkg/mod.py"),          # common suffix: {src => lib}/pkg/mod.py
        ("src/one/deep.py", "src/two/deep.py"),        # prefix and suffix: src/{one => two}/deep.py
        ("top.md", "docs/top.md"),                     # empty side: {=> docs}/top.md
        ("docs/sub/x.md", "x.md"),                     # empty side the other way
    ],
)
def test_rename_shapes_all_yield_both_sides(repo, old, new):
    _write(repo, old, "".join(f"line {i}\n" for i in range(40)))
    _commit(repo, "base")

    def mutate(r):
        (r / new).parent.mkdir(parents=True, exist_ok=True)
        _git(r, "mv", old, new)

    raw = _branch_diff(repo, mutate)
    assert co.parse_numstat_z(raw) == [(0, 0, new, old)]


def test_rename_with_an_edit_keeps_both_sides_and_counts(repo):
    _write(repo, "src/one/deep.py", "".join(f"line {i}\n" for i in range(40)))
    _commit(repo, "base")

    def mutate(r):
        (r / "src/two").mkdir(parents=True)
        _git(r, "mv", "src/one/deep.py", "src/two/deep.py")
        with open(r / "src/two/deep.py", "a") as fh:
            fh.write("added\n")

    raw = _branch_diff(repo, mutate)
    assert co.parse_numstat_z(raw) == [(1, 0, "src/two/deep.py", "src/one/deep.py")]


def test_lock_and_fixture_renames_follow_the_post_image(repo):
    # vendor/{a.lock => b.lock} stays excluded; a file moved into tests/fixtures/ is excluded, and
    # one moved out of it counts: the size cap charges where the file lands (#62).
    for rel in ("vendor/a.lock", "src/f.json", "tests/fixtures/moved.py"):
        _write(repo, rel, "".join(f"{rel} {i}\n" for i in range(20)))
    _commit(repo, "base")

    def mutate(r):
        (r / "tests/fixtures").mkdir(parents=True, exist_ok=True)
        _git(r, "mv", "vendor/a.lock", "vendor/b.lock")
        _git(r, "mv", "src/f.json", "tests/fixtures/f.json")
        _git(r, "mv", "tests/fixtures/moved.py", "src/moved.py")
        for rel in ("vendor/b.lock", "tests/fixtures/f.json", "src/moved.py"):
            with open(r / rel, "a") as fh:
                fh.write("edit\n")

    entries = co.parse_numstat_z(_branch_diff(repo, mutate))
    assert {(n, o) for _, _, n, o in entries} == {
        ("vendor/b.lock", "vendor/a.lock"),
        ("tests/fixtures/f.json", "src/f.json"),
        ("src/moved.py", "tests/fixtures/moved.py"),
    }
    assert co.compute_size(entries, ["**/*.lock", "tests/fixtures/**"]) == (1, 1)


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
    env = {k: v for k, v in os.environ.items() if k not in ("PR_LABELS_JSON", "PR_AUTHOR",
                                                            "SIZE_EXCEPTION_APPLIER",
                                                            "A6_BACKSTOP",
                                                            "FIX_LANDED_APPLIER")}
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


def _owned_change(repo):
    _write(repo, "docs/a.md", "x\n")
    _commit(repo, "base")
    _branch_diff(repo, lambda r: _write(r, "docs/a.md", "y\n"))


def test_main_fails_forge_pr_outside_the_agent_prefix(repo):
    # The branch name is the agent's choice; without this, naming it chief/x read as the Chief's.
    # OWNERSHIP here has no agent_identities key, so this also pins the fail-closed default.
    _owned_change(repo)
    res = _run_main(repo, "chief/x", {"PR_AUTHOR": "egzos-forge[bot]"})
    assert res.returncode == 1
    assert "agent identity" in res.stdout
    assert "Human branch" not in res.stdout


def test_main_judges_forge_pr_on_agent_branch_normally(repo):
    _owned_change(repo)
    res = _run_main(repo, "agent/a1p-planner/x", {"PR_AUTHOR": "egzos-forge[bot]"})
    assert res.returncode == 0, res.stdout


@pytest.mark.parametrize("author", ["Gond-ul", ""])
def test_main_human_branch_still_passes_for_non_agent_authors(repo, author):
    _owned_change(repo)
    res = _run_main(repo, "chief/x", {"PR_AUTHOR": author})
    assert res.returncode == 0, res.stdout
    assert "Human branch" in res.stdout


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


def test_nested_claude_control_inputs_are_chief_only():
    # A builder must not be able to plant a .claude (symlink or not), CLAUDE.md or .mcp.json under
    # its own paths: reviewers' sessions would load it (Egzos/egzos-platform#46).
    chief_only = yaml.safe_load((ROOT / ".github" / "OWNERSHIP.yml").read_text())["chief_only"]
    for path in ("apps/ui-flagship/src/.claude", "adversarial/x/.claude/settings.json",
                 "src/egzos/web/CLAUDE.md", "tests/a/CLAUDE.local.md", "server/.mcp.json",
                 ".mcp.json"):
        assert co.matches_any(chief_only, path), path
    # The root CLAUDE.md and .claude/ stay a1p-planner's: a widening to `**/` would break its PRs.
    for path in ("CLAUDE.md", ".claude/agents/x.md", ".claude"):
        assert not co.matches_any(chief_only, path), path


# ---------------------------------------------------------------------------
# RD-005 backstop on every a6 branch (Egzos/egzos-platform#45)
# ---------------------------------------------------------------------------

@pytest.mark.parametrize(
    ("source", "live"),
    [
        ("def test_a():\n    assert 1\n", ["test_a"]),
        ("import pytest\n@pytest.mark.xfail(reason='r', strict=True)\ndef test_a():\n    pass\n",
         []),
        ("import pytest\n@pytest.mark.xfail\ndef test_a():\n    pass\n", []),
        # Conditional marks leave the test live whenever the condition is false.
        ("import pytest\n@pytest.mark.xfail(False, reason='r')\ndef test_a():\n    pass\n",
         ["test_a"]),
        ("import pytest\n@pytest.mark.xfail(condition=False)\ndef test_a():\n    pass\n",
         ["test_a"]),
        ("import pytest\n@pytest.mark.skipif(False, reason='xfail')\ndef test_a():\n    pass\n",
         ["test_a"]),
        ("import pytest\npytestmark = pytest.mark.xfail(reason='r')\ndef test_a():\n    pass\n",
         []),
        ("import pytest\npytestmark = [pytest.mark.xfail(strict=True)]\ndef test_a():\n    pass\n",
         []),
        ("import pytest\n@pytest.mark.xfail\nclass TestA:\n    def test_b(self):\n        pass\n",
         []),
        ("class TestA:\n    def test_b(self):\n        pass\n    def helper(self):\n        pass\n",
         ["TestA.test_b"]),
        ("def helper():\n    pass\n", []),
        ("def test_a(:\n", ["<unparseable>"]),
    ],
)
def test_non_xfail_tests(source, live):
    assert co.non_xfail_tests(source) == live


def test_security_backstop_failures_scope():
    files = {
        "adversarial/test_live.py": "def test_a():\n    pass\n",
        "adversarial/test_ok.py": "import pytest\n@pytest.mark.xfail\ndef test_a():\n    pass\n",
        "adversarial/conftest.py": "",
        "adversarial/data.json": "{}",
        "adversarial/blob.bin": None,
        "adversarial/test_latin1.py": None,
        "docs/test_elsewhere.py": "def test_a():\n    pass\n",
    }

    def mode_of(path):
        return b"100644" if path in files else None

    def text_of(path):
        assert path.endswith(".py"), path  # a binary fixture is never decoded
        return files[path]

    out = co.security_backstop_failures([*files, "adversarial/test_deleted.py"], mode_of, text_of)
    assert [p for p, _ in out] == [
        "adversarial/test_live.py", "adversarial/conftest.py", "adversarial/test_latin1.py"]


def _a6_live_test(repo):
    _write(repo, "adversarial/__init__.py", "")
    _commit(repo, "base")
    _branch_diff(repo, lambda r: _write(r, "adversarial/test_x.py", "def test_x():\n    pass\n"))


def test_main_backstop_refuses_a_live_test_on_an_a6_branch(repo):
    _a6_live_test(repo)
    res = _run_main(repo, "agent/a6-adversary/x", {"A6_BACKSTOP": "true"})
    assert res.returncode == 1
    assert "test_x is not unconditionally xfail" in res.stdout


@pytest.mark.parametrize(
    "env",
    [
        {"A6_BACKSTOP": "false"},
        {},
        {"A6_BACKSTOP": "true", "PR_LABELS_JSON": '["fix-landed"]',
         "FIX_LANDED_APPLIER": "Gond-ul"},
    ],
)
def test_main_backstop_passes_when_unset_or_after_the_fix(repo, env):
    _a6_live_test(repo)
    res = _run_main(repo, "agent/a6-adversary/x", env)
    assert res.returncode == 0, res.stdout


def test_main_backstop_waiver_needs_an_approver(repo):
    _a6_live_test(repo)
    res = _run_main(repo, "agent/a6-adversary/x", {
        "A6_BACKSTOP": "true", "PR_LABELS_JSON": '["fix-landed"]',
        "FIX_LANDED_APPLIER": "egzos-forge[bot]"})
    assert res.returncode == 1


def test_main_backstop_reads_a_renamed_test_at_its_new_path(repo):
    xfail = "import pytest\n@pytest.mark.xfail\ndef test_x():\n    pass\n"
    _write(repo, "adversarial/test_old.py", xfail)
    _commit(repo, "base")

    def mutate(r):
        _git(r, "mv", "adversarial/test_old.py", "adversarial/test_new.py")
        _write(r, "adversarial/test_new.py", "def test_x():\n    pass\n")

    _branch_diff(repo, mutate)
    res = _run_main(repo, "agent/a6-adversary/x", {"A6_BACKSTOP": "true"})
    assert res.returncode == 1
    assert "adversarial/test_new.py" in res.stdout


_PY = "import pytest\n"


@pytest.mark.parametrize(
    ("source", "live"),
    [
        # A later binding overrides an earlier xfail; one under an `if` may never run.
        (_PY + "pytestmark = pytest.mark.xfail(reason='r')\npytestmark = []\n"
               "def test_a():\n    pass\n", ["test_a"]),
        (_PY + "if True:\n    pytestmark = pytest.mark.xfail\ndef test_a():\n    pass\n",
         ["test_a"]),
        (_PY + "pytestmark = [pytest.mark.xfail]\npytestmark += []\ndef test_a():\n    pass\n",
         ["test_a"]),
        (_PY + "pytestmark = pytest.mark.xfail\nfrom os import sep as pytestmark\n"
               "def test_a():\n    pass\n", ["test_a"]),
        # pytest collects tests at any statement depth, bound by assignment, and in any
        # unittest.TestCase subclass whatever its name.
        (_PY + "try:\n    def test_a():\n        pass\nexcept ImportError:\n    pass\n",
         ["test_a"]),
        (_PY + "def _mk():\n    return lambda: None\ntest_a = _mk()\n", ["test_a"]),
        ("import unittest\nclass Foo(unittest.TestCase):\n    def test_a(self):\n        pass\n",
         ["Foo.test_a"]),
        # A function nested in a function is not collected.
        (_PY + "@pytest.mark.xfail\ndef test_a():\n    def test_inner():\n        pass\n", []),
        # raises= turns any other exception into a hard failure; run=False is the safest mark.
        (_PY + "@pytest.mark.xfail(raises=KeyError)\ndef test_a():\n    pass\n", ["test_a"]),
        (_PY + "@pytest.mark.xfail(run=False, reason='r')\ndef test_a():\n    pass\n", []),
    ],
)
def test_non_xfail_tests_is_conservative(source, live):
    assert co.non_xfail_tests(source) == live


@pytest.mark.parametrize("mode", [b"120000", b"160000"])
def test_security_backstop_refuses_links_and_submodules(mode):
    out = co.security_backstop_failures(
        ["adversarial/test_x.py", "adversarial/data"], lambda p: mode, lambda p: "")
    assert [p for p, _ in out] == ["adversarial/test_x.py", "adversarial/data"]


def test_main_backstop_passes_a_binary_fixture(repo):
    _write(repo, "adversarial/__init__.py", "")
    _commit(repo, "base")
    _branch_diff(repo, lambda r: (r / "adversarial" / "fixture.bin").write_bytes(b"\xff\xfe\x00"))
    res = _run_main(repo, "agent/a6-adversary/x", {"A6_BACKSTOP": "true"})
    assert res.returncode == 0, res.stdout + res.stderr


def test_main_backstop_refuses_a_symlink(repo):
    _write(repo, "adversarial/__init__.py", "")
    _commit(repo, "base")

    def mutate(r):
        _write(r, "adversarial/payload.txt", "def test_x():\n    pass\n")
        (r / "adversarial" / "test_x.py").symlink_to("payload.txt")

    _branch_diff(repo, mutate)
    res = _run_main(repo, "agent/a6-adversary/x", {"A6_BACKSTOP": "true"})
    assert res.returncode == 1
    assert "adversarial/test_x.py" in res.stdout and "symlink" in res.stdout


_LIVE = "def test_a():\n    pass\n"


@pytest.mark.parametrize(
    ("source", "live"),
    [
        # The mark must be the real pytest's: bound by `import pytest` and nothing else.
        ("class _M:\n    class mark:\n        xfail = staticmethod(lambda f: f)\npytest = _M\n"
         "@pytest.mark.xfail\ndef test_a():\n    pass\n", ["test_a"]),
        ("import pytest\npytest = object()\n@pytest.mark.xfail\ndef test_a():\n    pass\n",
         ["test_a"]),
        ("import pytest as pt\n@pt.mark.xfail\ndef test_a():\n    pass\n", ["test_a"]),
        ("from pytest import mark\n@mark.xfail\ndef test_a():\n    pass\n", ["test_a"]),
        ("import pytest\ntry:\n    pass\nexcept Exception as pytest:\n    pass\n"
         "@pytest.mark.xfail\ndef test_a():\n    pass\n", ["test_a"]),
        ("import pytest\nx = object()\n@x.mark.xfail\ndef test_a():\n    pass\n", ["test_a"]),
        # Names pytest collects can arrive by import or by assignment, classes included.
        ("from helpers import test_a\n", ["test_a"]),
        ("import pytest\nTestA = type('TestA', (), {})\n", ["TestA"]),
        # Run-time binding cannot be read statically, so the file is refused whole.
        ("exec('def test_a(): pass')\n", ["<unreadable: exec>"]),
        ("globals()['test_a'] = lambda: None\n", ["<unreadable: globals>"]),
        ("import sys\nsetattr(sys.modules[__name__], 'test_a', print)\n",
         ["<unreadable: modules>", "<unreadable: setattr>"]),
        ("from helpers import *\n", ["<unreadable: import *>"]),
        ("def __getattr__(name):\n    return None\n", ["<unreadable: __getattr__>"]),
        ("class Meta(type):\n    pass\nclass TestA(metaclass=Meta):\n    pass\n",
         ["<unreadable: metaclass>"]),
        ("pytest_plugins = ['x']\n", ["<unreadable: pytest_plugins>"]),
        ("import pytest\npytestmark = pytest.mark.xfail\nexec('')\n", ["<unreadable: exec>"]),
    ],
)
def test_non_xfail_tests_reads_only_what_it_can_prove(source, live):
    assert co.non_xfail_tests(source) == live


def test_security_backstop_scope_and_pytest_shadowing():
    ok = "import pytest\n@pytest.mark.xfail\ndef test_a():\n    pass\n"
    files = {"adversarial/pytest.py": "", "adversarial/_pytest/x.py": "", "other/test_a.py": _LIVE,
             "adversarial/test_ok.py": ok}
    out = co.security_backstop_failures(
        list(files), lambda p: b"100644", files.get, ["adversarial/**"])
    assert [p for p, _ in out] == ["adversarial/pytest.py", "adversarial/_pytest/x.py"]
    out = co.security_backstop_failures(list(files), lambda p: b"100644", files.get, ["other/**"])
    assert [p for p, _ in out] == ["other/test_a.py"]


def test_main_backstop_matches_paths_exactly(repo):
    # A filename holding glob characters is a name, never a pattern that could read another entry.
    _write(repo, "adversarial/__init__.py", "")
    _write(repo, "adversarial/test_ok.py", "import pytest\n@pytest.mark.xfail\ndef test_a():\n"
                                           "    pass\n")
    _commit(repo, "base")
    _branch_diff(repo, lambda r: _write(r, "adversarial/test_[ok].py", _LIVE))
    res = _run_main(repo, "agent/a6-adversary/x", {"A6_BACKSTOP": "true"})
    assert res.returncode == 1
    assert "adversarial/test_[ok].py" in res.stdout and "test_a is not" in res.stdout
