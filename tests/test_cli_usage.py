# Copyright 2026 Ali Sasanian
# SPDX-License-Identifier: LicenseRef-PolyForm-Strict-1.0.0
"""The CLI from the home directory, where `./.egzos` is the container itself, and usage errors:
one line and a hint, exit 2, never a traceback."""

import pytest

from egzos.cli import main


@pytest.fixture
def at_home(tmp_path, monkeypatch):
    """EGZOS_HOME at its default shape (`~/.egzos`), with the shell sitting in `~`."""
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setenv("EGZOS_HOME", str(home / ".egzos"))
    monkeypatch.chdir(home)
    assert main(["init"]) == 0
    return home


def test_add_and_ls_work_from_the_home_directory(at_home, capsys):
    assert (at_home / ".egzos").is_dir()
    assert main(["add", "first note"]) == 0
    capsys.readouterr()
    assert main(["ls", "--inbox"]) == 0
    assert "first note" in capsys.readouterr().out
    assert main(["--json", "pwd"]) == 0
    assert '"scope": null' in capsys.readouterr().out


def test_cd_refuses_where_dot_egzos_is_the_container(at_home, capsys):
    assert main(["cd", "user:self"]) != 0
    assert "is a directory" in capsys.readouterr().out
    assert (at_home / ".egzos").is_dir()
    assert main(["ls", "--inbox"]) == 0


def test_sticky_scope_still_works_in_a_project_directory(at_home, monkeypatch, capsys):
    project = at_home / "project"
    project.mkdir()
    monkeypatch.chdir(project)
    assert main(["cd", "user:self"]) == 0
    assert (project / ".egzos").is_file()
    capsys.readouterr()
    assert main(["--json", "pwd"]) == 0
    assert '"scope": null' not in capsys.readouterr().out


@pytest.mark.parametrize(
    "argv",
    [
        ["--version"],
        ["nosuchcommand"],
        ["add"],
        ["token"],
    ],
)
def test_a_usage_error_is_one_line_and_exit_2(at_home, capsys, argv):
    capsys.readouterr()
    assert main(argv) == 2
    err = capsys.readouterr().err
    assert err.startswith("Error: ") and "--help'." in err
    assert "Traceback" not in err


def test_a_usage_error_echoes_what_was_typed_inert(at_home, capsys):
    capsys.readouterr()
    assert main(["no\x1b]52;c;aGk=\x07such"]) == 2
    err = capsys.readouterr().err
    assert "\x1b" not in err and "\x07" not in err
    assert "\\x1b" in err
