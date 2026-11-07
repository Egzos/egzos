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


@pytest.mark.parametrize("pasted", [
    lambda token: token + b"\x16\ny\n",  # the page's token, and a yes held in its line by ^V
    lambda token: b"k1.not-it.e30\necho PWNED\n",  # a stale one: none of it reaches the shell
    pytest.param(lambda token: b"k" * 3000 + b"\n", marks=pytest.mark.skipif(  # 2048 or more
        os.uname().sysname != "Linux", reason="a line of 3001 bytes: macOS holds 1024")),
])
def test_nothing_in_the_pasted_line_answers_the_question(
        tmp_path, monkeypatch, request, capsys, pasted):
    monkeypatch.setenv("EGZOS_HOME", str(home := tmp_path / ".egzos"))
    monkeypatch.setenv("EGZOS_SITE", "http://127.0.0.1:9")
    monkeypatch.delenv("EGZOS_TOKEN", raising=False)
    assert main(["init"]) == 0
    master, slave = os.openpty()
    request.addfinalizer(lambda: [os.close(fd) for fd in (master, slave)])
    attrs = termios.tcgetattr(slave)
    attrs[3] = attrs[3] & ~termios.ECHO | termios.ICANON | termios.IEXTEN
    attrs[6][termios.VLNEXT] = b"\x16"  # ^V: the key after it is taken as it is, Enter too
    termios.tcsetattr(slave, termios.TCSANOW, attrs)

    def page(url):  # what the person pastes at the terminal's prompt
        state = dict(parse_qsl(urlsplit(url).query))["state"].encode()
        triple = urlencode({"origin": ORIGIN, "client_id": CLIENT, "issuer": signin.ISSUER})
        b64 = base64.urlsafe_b64encode(triple.encode()).rstrip(b"=")
        os.write(master, pasted(b"k1.%s.%s" % (state, b64)))
        return True

    drop = signin._drop_typed_ahead

    def drop_then_no():  # if the question is asked, the person at the terminal says no
        dropped = drop()
        if "[y/N]" in capsys.readouterr().err:  # only when asked: not as a refused paste ends
            os.write(master, b"n\n")
        return dropped

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
