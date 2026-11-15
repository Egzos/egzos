# Copyright 2026 Ali Sasanian
# SPDX-License-Identifier: LicenseRef-PolyForm-Strict-1.0.0
"""This package's command is `egzoscore`. `egzos` is the command line for a cloud, a different
program, so nothing here tells a person to run one of this program's verbs under that name."""

from __future__ import annotations

import re
import tomllib
from pathlib import Path

import pytest
import typer.main

from egzos.cli import app, main

ROOT = Path(__file__).resolve().parent.parent
#: The verbs that exist in both programs, or only in the other, are not this program's to name.
OTHER_PROGRAMS = {"whoami", "login", "logout"}


def _verbs() -> set[str]:
    return set(typer.main.get_command(app).commands) - OTHER_PROGRAMS  # type: ignore[attr-defined]


def _tells_to_run_this_program(line: str, verbs: set[str]) -> bool:
    """A line that names `egzos <verb>` for a verb of this program, or the old distribution's
    extras (`egzos[objects]`), and does not speak of a cloud (`cloud:`)."""
    if "cloud:" in line:
        return False
    alt = "|".join(sorted(map(re.escape, verbs)))
    return bool(re.search(rf"(?<![\w.\-/])egzos (?:{alt})\b|(?<![\w.\-/])egzos\[", line))


def test_this_programs_verbs_are_read_from_the_app():
    assert {"init", "serve", "web", "link", "connect", "token", "audit", "config"} <= _verbs()
    assert not OTHER_PROGRAMS & _verbs()


@pytest.mark.parametrize(
    "line",
    [
        "run `egzos init`",
        "stop egzos web, run `egzos web --no-open`",
        "(`egzos config set identity.origin https://…`)",
        'pip install "egzos[objects]"',
        "`egzos trust approve 4` to confirm",
    ],
)
def test_the_guard_fires_on_the_old_command(line):
    assert _tells_to_run_this_program(line, _verbs())


@pytest.mark.parametrize(
    "line",
    [
        "run `egzoscore init`",
        'pip install "egzoscore[objects]"',
        "sign in with `egzos login`, and `egzos logout` ends it",
        "`egzos whoami` says who is signed in",
        "`egzos ls cloud:`",
        "`egzos ls cloud:notes` lists the cloud",
        "from egzos.store import find",
        "the `.egzos` directory, EGZOS_HOME, egzos.io and egzos-platform",
        "egzos is your context layer",
    ],
)
def test_the_guard_leaves_the_other_program_and_the_name_alone(line):
    assert not _tells_to_run_this_program(line, _verbs())


def test_no_line_under_src_tells_a_person_to_run_this_program_as_egzos():
    verbs = _verbs()
    found = []
    for path in sorted((ROOT / "src").rglob("*")):
        if not path.is_file() or "__pycache__" in path.parts:
            continue
        try:
            lines = path.read_text(encoding="utf-8").splitlines()
        except UnicodeDecodeError:
            continue
        found += [
            f"{path.relative_to(ROOT)}:{n}: {line.strip()}"
            for n, line in enumerate(lines, 1)
            if _tells_to_run_this_program(line, verbs)
        ]
    assert found == []


def test_the_package_installs_the_command_egzoscore_and_no_other():
    project = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))["project"]
    assert project["name"] == "egzoscore"
    assert project["scripts"] == {"egzoscore": "egzos.cli:main"}


def test_usage_and_help_name_the_program_egzoscore(capsys):
    assert main(["no-such-verb"]) == 2
    assert "Try 'egzoscore --help'." in capsys.readouterr().err
    assert main(["--help"]) == 0
    out = capsys.readouterr().out
    assert "Usage: egzoscore" in out and "Usage: egzos " not in out
