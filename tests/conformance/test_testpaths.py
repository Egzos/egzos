# Copyright 2026 Ali Sasanian
# SPDX-License-Identifier: Apache-2.0
"""`adversarial/` stays in pytest's `testpaths`, and the `tests` check still honours it (#81).

The adversarial suite runs at all only because `[tool.pytest.ini_options].testpaths` in
pyproject.toml names `adversarial`, and because the required `tests` check invokes `pytest` with no
path of its own. Drop that entry — or give the CI invocation an explicit path — and every attack
test stops being collected *silently*: the suite still goes green, with fewer tests in it, which is
the one failure shape a green check cannot show.

No test under `adversarial/` can catch that: it would go uncollected along with its own directory,
and the child process in `adversarial/test_xfail_finding_contract.py` would exit 5 rather than 0
(#80). The guard therefore lives here, under `tests/`, which `testpaths` collects as a separate
entry.

The reciprocal gap is real and named rather than papered over: nothing in this file can prove
`tests` is still in `testpaths`, because this file would be uncollected with it. That half belongs
under `adversarial/`, which is a6-adversary's exclusive path.
"""

import re
import shlex
import tomllib
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]
PYPROJECT = ROOT / "pyproject.toml"
TESTS_WORKFLOW = ROOT / ".github" / "workflows" / "tests.yml"

# pytest's default collection patterns; `python_files` is not overridden in pyproject.toml.
COLLECTED_GLOBS = ("test_*.py", "*_test.py")


def _testpaths():
    with PYPROJECT.open("rb") as fh:
        return tomllib.load(fh)["tool"]["pytest"]["ini_options"]["testpaths"]


def test_adversarial_is_in_testpaths():
    assert "adversarial" in _testpaths()


def test_every_testpath_is_a_real_directory():
    # A testpath naming a directory that no longer exists (a rename, a move) is a collection error
    # at best and a silently smaller suite at worst.
    missing = [p for p in _testpaths() if not (ROOT / p).is_dir()]
    assert missing == []


def test_adversarial_holds_tests_pytest_would_collect():
    # `adversarial` in testpaths is vacuous if nothing inside it matches a collection pattern.
    found = [p.name for g in COLLECTED_GLOBS for p in (ROOT / "adversarial").glob(g)]
    assert found != []


def _pytest_invocations():
    """Every `run:` line in .github/workflows/tests.yml that invokes pytest, as (line, tokens)."""
    doc = yaml.safe_load(TESTS_WORKFLOW.read_text())
    for job in doc["jobs"].values():
        for step in job.get("steps", []):
            for line in step.get("run", "").splitlines():
                try:
                    tokens = shlex.split(line, comments=True)
                except ValueError:  # an unbalanced quote in a heredoc body, not a command
                    continue
                if any(Path(t).name == "pytest" for t in tokens):
                    yield line, tokens


def _after_pytest(tokens):
    for i, t in enumerate(tokens):
        if Path(t).name == "pytest":
            return tokens[i + 1 :]
    return []


def test_the_tests_check_collects_adversarial():
    invocations = list(_pytest_invocations())
    assert invocations, f"no pytest invocation found in {TESTS_WORKFLOW.name}"
    for line, tokens in invocations:
        # Only arguments that name something real in the checkout are collection targets; a value
        # like the `-k` expression's is not.
        targets = [t for t in _after_pytest(tokens) if (ROOT / t).exists()]
        # No target of its own means `testpaths` governs, which the tests above pin. With a target,
        # the invocation has to name `adversarial` itself.
        assert not targets or any(t.split("/")[0] == "adversarial" for t in targets), line
        assert not re.search(r"--(?:ignore|deselect)[= ]\s*adversarial", line), line
