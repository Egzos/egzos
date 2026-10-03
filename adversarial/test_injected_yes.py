# Copyright 2026 Ali Sasanian
# SPDX-License-Identifier: Apache-2.0
"""Standing target: an injected `--yes` / `echo y` cannot complete a human-only act.

An agent with a shell can run the CLI as the user and type into it. Approving still needs two
presses on a loopback page; typing `y` into the terminal, or answering nothing, approves nothing.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys

import pytest

pytestmark = pytest.mark.adversarial


def _egzos(home, *args, stdin="", env_extra=None):
    env = {k: v for k, v in os.environ.items() if k != "EGZOS_TOKEN"}
    env.update({"EGZOS_HOME": str(home), "BROWSER": "true", "EGZOS_TAP_TIMEOUT_SECONDS": "2"})
    env.update(env_extra or {})
    return subprocess.run([sys.executable, "-m", "egzos.cli", *args], input=stdin,
                          capture_output=True, text=True, env=env, timeout=60)


def test_typing_yes_into_the_terminal_does_not_approve(tmp_path):
    assert _egzos(tmp_path, "init").returncode == 0
    added = json.loads(_egzos(tmp_path, "--json", "add", "injected").stdout)
    r = _egzos(tmp_path, "trust", "approve", added["id"], stdin="y\nyes\n" * 20)
    assert r.returncode != 0 and "not approved" in (r.stdout + r.stderr)
    items = json.loads(_egzos(tmp_path, "--json", "ls", "--inbox").stdout)
    assert [i["trust"]["status"] for i in items if i["id"] == added["id"]] == ["unverified"]


def test_a_client_token_cannot_approve(tmp_path):
    assert _egzos(tmp_path, "init").returncode == 0
    added = json.loads(_egzos(tmp_path, "--json", "add", "x").stdout)
    secret = json.loads(_egzos(tmp_path, "--json", "token", "create", "--client", "bot",
                               "--role", "curator").stdout)["secret"]
    r = _egzos(tmp_path, "trust", "approve", added["id"], env_extra={"EGZOS_TOKEN": secret})
    assert r.returncode != 0 and "human-only" in (r.stdout + r.stderr)
