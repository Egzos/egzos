# Copyright 2026 Ali Sasanian
# SPDX-License-Identifier: Apache-2.0
"""`adversarial/` stays in pytest's `testpaths`, and the `tests` check still runs it (#81, #87).

The adversarial suite runs at all only because `[tool.pytest.ini_options].testpaths` in
pyproject.toml names `adversarial`, and because the required `tests` check invokes `pytest` with no
path of its own. Drop that entry — or give the CI invocation an explicit path, an `--ignore`, or a
`-m`/`-k` expression that deselects the suite — and every attack test stops being collected
*silently*: the suite still goes green, with fewer tests in it, which is the one failure shape a
green check cannot show.

No test under `adversarial/` can catch that: it would go uncollected along with its own directory,
and the child process in `adversarial/test_xfail_finding_contract.py` would exit 5 rather than 0
(#80). The guard therefore lives here, under `tests/`, which `testpaths` collects as a separate
entry.

What `_findings()` reads is one thing only: the argument list of every pytest invocation on a
`run:` line in .github/workflows/tests.yml (backslash continuations joined first, so an exclusion
parked on a second line is still seen). Within that list it catches

* a collection target that is not the adversarial suite (`pytest tests`), path-normalised so
  `./adversarial` and `adversarial/` count as the suite;
* `--ignore`, `--ignore-glob` or `--deselect` naming the suite, in the `=`-joined and
  separate-token forms and path-normalised the same way;
* a `-m` or `-k` expression that names the suite — `-m 'not adversarial'` deselects it, `-m
  adversarial` deselects everything else, and `adversarial` is a registered marker in
  pyproject.toml, so both are live vectors. The quoted, escaped (`-m not\\ adversarial`) and
  attached (`-k'not adversarial'`) forms all reduce to the same token under `shlex`; the wholly
  unquoted `-m not adversarial` does not, and is caught instead by its bare `not` — the shell split
  the expression and the suite name is landing as a collection target.

Deliberately out of scope, so the invariant above is not read wider than it is:

* an expression that deselects the suite without naming it — `-m 'not slow'`, or a `-k` keyword
  that happens to match every adversarial test id. Deciding that needs pytest's own collection.
* `PYTEST_ADDOPTS` (or any other pytest env var) set in the workflow's `env:`, and argument
  indirection through a shell variable (`pytest $PYTEST_ARGS`).
* `addopts` in `[tool.pytest.ini_options]`, and a `conftest.py` collection hook: deselection from
  outside tests.yml entirely.

The reciprocal gap is real and named rather than papered over: nothing in this file can prove
`tests` is still in `testpaths`, because this file would be uncollected with it. That half belongs
under `adversarial/`, which is a6-adversary's exclusive path — filed as #84.
"""

import os
import re
import shlex
import tomllib
from pathlib import Path, PurePosixPath

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[2]
PYPROJECT = ROOT / "pyproject.toml"
TESTS_WORKFLOW = ROOT / ".github" / "workflows" / "tests.yml"

SUITE = "adversarial"

# pytest's default collection patterns; `python_files` is not overridden in pyproject.toml, which
# test_adversarial_holds_tests_pytest_would_collect asserts rather than assumes.
COLLECTED_GLOBS = ("test_*.py", "*_test.py")

# Options that consume the *next* token as their value. Without this, a value that happens to name
# a real path (`--cov src`) reads as a collection target and this module fails for nothing. An
# option not listed here fails the same way: loud and one line from fixed, which is the safe
# direction for a guard whose other failure mode is silence.
VALUE_FLAGS = frozenset(
    {
        "-c", "-k", "-m", "-n", "-o", "-p", "-r", "-W",
        "--basetemp", "--confcutdir", "--cov", "--cov-config", "--cov-report",
        "--deselect", "--dist", "--doctest-glob", "--ignore", "--ignore-glob",
        "--import-mode", "--junitxml", "--log-file", "--maxfail", "--override-ini",
        "--rootdir", "--tb", "--timeout",
    }
)
EXCLUDE_FLAGS = frozenset({"--ignore", "--ignore-glob", "--deselect"})
EXPR_FLAGS = frozenset({"-m", "-k"})
# A whole expression that is one bare operator means the rest of it was left unquoted and the shell
# split it off: `-m not adversarial` hands pytest the markexpr `not` and the suite as a path.
DANGLING_OPERATORS = frozenset({"not", "and", "or"})


def _ini_options():
    with PYPROJECT.open("rb") as fh:
        return tomllib.load(fh)["tool"]["pytest"]["ini_options"]


def _testpaths():
    return _ini_options()["testpaths"]


def test_adversarial_is_in_testpaths():
    assert SUITE in _testpaths()


def test_every_testpath_is_a_real_directory():
    # A testpath naming a directory that no longer exists (a rename, a move) is a collection error
    # at best and a silently smaller suite at worst.
    missing = [p for p in _testpaths() if not (ROOT / p).is_dir()]
    assert missing == []


def test_adversarial_holds_tests_pytest_would_collect():
    # COLLECTED_GLOBS is only the right question while the default patterns are in force.
    assert "python_files" not in _ini_options()
    # `adversarial` in testpaths is vacuous if nothing inside it matches a collection pattern.
    # rglob, not glob: a test in adversarial/<subdir>/ is collected and counts here too.
    found = [p.name for g in COLLECTED_GLOBS for p in (ROOT / SUITE).rglob(g)]
    assert found != []


def _command_lines(body):
    """A `run:` body split into commands, with backslash continuations joined into one line."""
    lines, pending = [], ""
    for raw in body.splitlines():
        line = raw.rstrip()
        if line.endswith("\\"):
            pending += line[:-1] + " "
            continue
        lines.append(pending + line)
        pending = ""
    if pending:
        lines.append(pending)
    return lines


def _pytest_invocations(workflow_path=TESTS_WORKFLOW):
    """Every command in `workflow_path` that invokes pytest, as (line, tokens)."""
    # Sibling parser: tests/governance/test_workflows.py::_load/_steps walks the same files. It
    # also un-does YAML 1.1 reading the bare key `on` as True; this copy reads only `jobs`, so it
    # does not need to. Keep them in step by hand — a shared fixture in tests/conftest.py would
    # cross the ownership boundary and is a `contract-change` proposal, not a drive-by refactor.
    doc = yaml.safe_load(workflow_path.read_text())
    for job in doc["jobs"].values():
        for step in job.get("steps", []):
            for line in _command_lines(step.get("run", "")):
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


def _option(args, i):
    """The argument at args[i] as (name, value, tokens consumed); value is "" when it takes none.

    A positional argument comes back as its own name with no value, so the caller tells the two
    apart by the leading dash.
    """
    token = args[i]
    if not token.startswith("-"):
        return token, "", 1
    name, sep, attached = token.partition("=")
    if sep:  # --ignore=adversarial
        return name, attached, 1
    if not token.startswith("--") and len(token) > 2:  # -k'not adversarial' -> -knot adversarial
        return token[:2], token[2:], 1
    if name in VALUE_FLAGS and i + 1 < len(args):  # --ignore adversarial, -m 'not adversarial'
        return name, args[i + 1], 2
    return name, "", 1


def _names_adversarial(value):
    """True when `value`, as a path, is the adversarial suite or something inside it."""
    path = PurePosixPath(os.path.normpath(value))
    if path.is_absolute():
        try:
            path = path.relative_to(PurePosixPath(os.path.normpath(ROOT)))
        except ValueError:
            return False
    return path.parts[:1] == (SUITE,)


def _findings(workflow_path=TESTS_WORKFLOW):
    """Every way `workflow_path`'s pytest invocations stop running the adversarial suite."""
    invocations = list(_pytest_invocations(workflow_path))
    if not invocations:
        return [f"no pytest invocation found in {workflow_path.name}"]
    findings, expr = [], re.compile(rf"\b{SUITE}\b")
    for line, tokens in invocations:
        args = _after_pytest(tokens)
        targets, i = [], 0
        while i < len(args):
            name, value, consumed = _option(args, i)
            i += consumed
            if not name.startswith("-"):
                targets.append(name)
            elif name in EXCLUDE_FLAGS and _names_adversarial(value):
                findings.append(f"{name} excludes the {SUITE} suite: {line}")
            elif name in EXPR_FLAGS and expr.search(value):
                findings.append(f"{name} expression names the {SUITE} suite: {line}")
            elif name in EXPR_FLAGS and value.strip() in DANGLING_OPERATORS:
                findings.append(f"{name} expression is the bare operator {value!r}: {line}")
        # Only an argument naming something real in the checkout is a collection target. No target
        # of its own means `testpaths` governs, which the tests above pin; with a target, the
        # invocation has to name the suite itself.
        collected = [t for t in targets if (ROOT / t).exists()]
        if collected and not any(_names_adversarial(t) for t in collected):
            findings.append(f"collection targets exclude the {SUITE} suite: {line}")
    return findings


def test_the_tests_check_collects_adversarial():
    assert _findings() == []


# The mutation check, run as a test rather than by hand: every form below is applied to an isolated
# copy of the real tests.yml, and the guard above has to see it. A guard for a silent failure that
# is itself silently broken buys nothing.
BASELINE_RUN = "        run: pytest -q\n"

DESELECTIONS = [
    "        run: pytest -q -m 'not adversarial'\n",
    '        run: pytest -q -m "not adversarial"\n',
    "        run: pytest -q -m'not adversarial'\n",
    "        run: pytest -q -m not\\ adversarial\n",
    # Left unquoted, the shell splits the expression: -m takes `not` and the suite name lands as a
    # collection target, so the target rule alone reads this invocation as healthy.
    "        run: pytest -q -m not adversarial\n",
    "        run: pytest -q -k not adversarial\n",
    "        run: pytest -q -m adversarial\n",
    "        run: pytest -q -k 'not adversarial'\n",
    '        run: pytest -q -k "not adversarial"\n',
    "        run: pytest -q -k'not adversarial'\n",
    "        run: pytest -q --ignore=adversarial\n",
    "        run: pytest -q --ignore=./adversarial\n",
    "        run: pytest -q --ignore adversarial/\n",
    "        run: pytest -q --ignore ./adversarial/\n",
    "        run: pytest -q --ignore-glob 'adversarial/*'\n",
    "        run: pytest -q --deselect adversarial/test_xfail_finding_contract.py\n",
    "        run: pytest -q tests\n",
    "        run: pytest -q tests/ src\n",
    "        run: |\n          pytest -q \\\n            --ignore adversarial\n",
]

ACCEPTED = [
    BASELINE_RUN,
    "        run: pytest -q --cov src\n",  # a flag value that is a real path, not a target
    "        run: pytest -q --cov=src -o addopts=\n",
    "        run: pytest -q adversarial tests\n",
    "        run: pytest -q ./adversarial\n",
    "        run: pytest -q -k 'not slow'\n",
]


def _mutated(tmp_path, run_line):
    text = TESTS_WORKFLOW.read_text()
    assert text.count(BASELINE_RUN) == 1, "the pytest step moved; update BASELINE_RUN"
    path = tmp_path / "tests.yml"
    path.write_text(text.replace(BASELINE_RUN, run_line))
    return path


@pytest.mark.parametrize("run_line", DESELECTIONS, ids=lambda s: s.strip().replace("\n", " "))
def test_a_deselecting_invocation_is_caught(tmp_path, run_line):
    assert _findings(_mutated(tmp_path, run_line)) != []


@pytest.mark.parametrize("run_line", ACCEPTED, ids=lambda s: s.strip().replace("\n", " "))
def test_an_invocation_that_still_runs_adversarial_passes(tmp_path, run_line):
    assert _findings(_mutated(tmp_path, run_line)) == []
