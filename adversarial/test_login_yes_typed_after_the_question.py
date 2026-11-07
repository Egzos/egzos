# Copyright 2026 Ali Sasanian
# SPDX-License-Identifier: LicenseRef-PolyForm-Strict-1.0.0
"""Standing target: `egzos login` keeps a sign-in only on a yes typed at the terminal after its
question shows (identity.md §3a; v0.7 §AH). Nothing that comes in with the paste answers it,
however the terminal hands the paste over. The terminal is a real pty; the provider and the
cloud are played, and no store on this machine is touched."""

from __future__ import annotations

import base64
import io
import os
import select
import time
from urllib.parse import parse_qsl, urlencode, urlsplit

import jwt
import pytest

from egzos.cli import main, signin

termios = pytest.importorskip("termios")
pytestmark = pytest.mark.adversarial

ORIGIN, CLIENT = "https://cloud.example", "c-1"


def _request(url, form=None):
    """The provider's token endpoint (a POST) and the cloud's metadata (a GET), both in order."""
    claims = {"iss": signin.ISSUER, "client_id": CLIENT, "sub": "u-2",
              "exp": int(time.time()) + 3600}
    if form:
        return {"access_token": jwt.encode(claims, "k" * 32), "refresh_token": "r"}
    return {"resource": ORIGIN, "authorization_servers": [signin.ISSUER]}


def test_nothing_in_the_pasted_line_answers_the_question(tmp_path, monkeypatch, request):
    monkeypatch.setenv("EGZOS_HOME", str(home := tmp_path / ".egzos"))
    monkeypatch.setenv("EGZOS_SITE", "http://127.0.0.1:9")
    monkeypatch.delenv("EGZOS_TOKEN", raising=False)
    assert main(["init"]) == 0
    master, slave = os.openpty()
    request.addfinalizer(lambda: [os.close(fd) for fd in (master, slave)])
    attrs = termios.tcgetattr(slave)
    attrs[3] = attrs[3] & ~termios.ECHO | termios.ICANON | termios.IEXTEN
    termios.tcsetattr(slave, termios.TCSANOW, attrs)
    held = attrs[6][termios.VLNEXT]

    def page(url):  # the page's token, pasted with a yes in the same line
        state = dict(parse_qsl(urlsplit(url).query))["state"].encode()
        triple = urlencode({"origin": ORIGIN, "client_id": CLIENT, "issuer": signin.ISSUER})
        b64 = base64.urlsafe_b64encode(triple.encode()).rstrip(b"=")
        os.write(master, b"k1.%s.%s%s\ny\n" % (state, b64, held))
        return True

    drop = signin._drop_typed_ahead

    def drop_then_no():  # if the question is asked, the person at the terminal says no
        drop()
        os.write(master, b"n\n")

    monkeypatch.setattr(signin, "_request", _request)
    monkeypatch.setattr(signin, "_open", page)
    monkeypatch.setattr(signin, "_at_terminal", lambda: True)
    monkeypatch.setattr(signin, "_drop_typed_ahead", drop_then_no)
    monkeypatch.setattr(signin, "_vault", lambda account, secret: False)  # a file, in tmp_path
    monkeypatch.setattr("sys.stdin", io.TextIOWrapper(
        io.BufferedReader(io.FileIO(slave, "r", closefd=False))))  # as Python opens a terminal
    assert main(["--json", "login", "--paste"]) == 1
    assert sorted(p.name for p in home.glob("login.*")) == []
    assert not select.select([slave], [], [], 0)[0]  # and nothing left for the shell to run
