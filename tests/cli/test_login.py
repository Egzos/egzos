# Copyright 2026 Ali Sasanian
# SPDX-License-Identifier: LicenseRef-PolyForm-Strict-1.0.0
"""`egzos login` (identity.md §3a, §8). egzos.io's pages and the provider are played, the OS
credential store is an in-memory keyring backend, and the loopback listener is real."""

from __future__ import annotations

import base64
import hashlib
import http.client
import inspect
import io
import json
import socket
import threading
import time
from types import SimpleNamespace
from unittest.mock import Mock
from urllib.parse import parse_qsl, urlencode, urlsplit

import jwt
import pytest
from keyring.backend import KeyringBackend
from keyring.backends import chainer, fail, null

from egzos.cli import login, main, signin
from egzos.container import Container

SITE, ORIGIN, CLIENT, OTHER = "http://127.0.0.1:9", "https://cloud.example", "c-1", "https://x.ex"
TOKEN, META = f"{signin.ISSUER}/oauth/token", ORIGIN + signin.METADATA
REFRESH = "r/1"  # '/' is not base64url: no random state or challenge can hold it


class Memory(KeyringBackend):
    """The OS credential store, held in memory: no test reaches this machine's own."""

    priority = 1

    def __init__(self):
        self.held = {}

    def set_password(self, service, username, password):
        self.held[service, username] = password

    def get_password(self, service, username):
        return self.held.get((service, username))

    def delete_password(self, service, username):
        del self.held[service, username]  # not there: a KeyError, as a real store raises


class Provider:
    """The provider's token endpoint and the cloud's metadata, as `signin._request` reaches them."""

    def __init__(self):
        self.calls, self.claims, self.tokens, self.meta = [], {}, {}, {}

    def __call__(self, url, form=None):
        self.calls.append((url, form))
        claims = {"iss": signin.ISSUER, "client_id": CLIENT, "sub": "u-1", "email": "me@x.ex",
                  "exp": int(time.time()) + 3600, **self.claims}
        return {TOKEN: {"access_token": jwt.encode(claims, "k" * 32), "token_type": "bearer",
                        "refresh_token": REFRESH, **self.tokens},
                META: {"resource": ORIGIN, "authorization_servers": [signin.ISSUER], **self.meta},
                }.get(url)


class Page:
    """egzos.io's pages: the code handed back, to the loopback or as the paste token."""

    def __init__(self, stdin):
        self.stdin, self.hand, self.answers, self.start, self.thread = stdin, {}, [], None, None

    def __call__(self, url):
        self.start, q = url, dict(parse_qsl(urlsplit(url).query))
        sent = {"code": "k1", "state": q["state"], "origin": ORIGIN, "client_id": CLIENT,
                "issuer": signin.ISSUER, **self.hand}
        sent = {k: v for k, v in sent.items() if v is not None}
        if "port" in q:
            self.thread = threading.Thread(target=self.loopback, args=(int(q["port"]), sent))
            self.thread.start()
            return True
        triple = urlencode({k: sent.get(k) for k in ("origin", "client_id", "issuer")}, True)
        b64 = base64.urlsafe_b64encode(triple.encode()).rstrip(b"=").decode()
        self.stdin.write(f"{sent['code']}.{sent['state']}.{b64}\n" if "code" in sent
                         else f"nowhere.{sent['state']}\n")
        self.stdin.seek(0)
        return True

    def loopback(self, port, sent):
        hand = "/oauth/callback?" + urlencode(sent, True)  # a list: the field named twice
        for method, path, headers in [
            ("POST", hand, {}), ("GET", hand.replace(sent["state"], "not-it"), {}),
            ("GET", hand, {"Host": f"rebound.example:{port}"}),
            ("GET", hand, {"Sec-Fetch-Dest": "image"}), ("GET", "/v1/confirm?proof=button", {}),
            ("GET", hand, {}),  # no Fetch Metadata (a browser before it): read as a document
        ]:
            self.answers.append(_call(port, path, method, headers))


def _call(port, path, method="GET", headers=None):
    conn = http.client.HTTPConnection("127.0.0.1", port, timeout=5)
    conn.request(method, path, headers=headers or {})
    r = conn.getresponse()
    return r.status, r.getheader("Location"), r.read()


@pytest.fixture
def world(tmp_path, monkeypatch):
    monkeypatch.setenv("EGZOS_HOME", str(tmp_path / ".egzos"))
    monkeypatch.setenv("EGZOS_SITE", SITE)
    monkeypatch.delenv("EGZOS_TOKEN", raising=False)
    monkeypatch.chdir(tmp_path)
    assert main(["init"]) == 0
    stdin = io.StringIO()
    w = SimpleNamespace(home=tmp_path / ".egzos", provider=Provider(), page=Page(stdin),
                        store=Memory(), stdin=stdin, patch=monkeypatch.setattr)
    monkeypatch.setattr("keyring.get_keyring", lambda: w.store)
    monkeypatch.setattr("egzos.cli.signin._request", w.provider)
    monkeypatch.setattr("egzos.cli.signin._open", w.page)
    monkeypatch.setattr("egzos.cli.signin.WAIT_SECONDS", 5)  # a lost hand-off fails, never hangs
    monkeypatch.setattr("sys.stdin", stdin)
    return w


def _run(capsys, world, *argv):
    capsys.readouterr()
    code = main(["--json", *argv])
    if world.page.thread:
        world.page.thread.join(5)
    out, err = capsys.readouterr()
    return code, json.loads(out), err


def _kept(world):
    return sorted(p.name for p in world.home.glob("login.*") if p.name != "login.told")


def test_the_loopback_takes_one_checked_hand_off_and_keeps_the_login(world, capsys):
    code, out, err = _run(capsys, world, "login", "--port", "0")
    start, q = world.page.start, dict(parse_qsl(urlsplit(world.page.start).query))
    assert code == 0 and out["origin"] == ORIGIN and out["sub"] == "u-1" and "note" in out
    assert start.startswith(f"{SITE}/connect/cli?") and start not in err  # no terminal, no URL
    assert set(q) == {"challenge", "state", "port"}  # never a container or a client (§3a)
    assert f"matching code {signin.matching_code(q['state'])}" in err
    assert signin.matching_code("egzos-test-state") == "N7XOBA"  # the docstring's vector
    # a POST, another state, a rebound Host, an image, the confirm route: refused, and waited on
    assert world.page.answers == [(404, None, b"")] * 5 + [(302, f"{SITE}/connect/cli/done", b"")]
    with pytest.raises(ConnectionRefusedError):  # one hand-off, then the listener is gone
        _call(int(q["port"]), "/oauth/callback?" + urlencode({"state": q["state"], "code": "k"}))
    assert [url for url, _ in world.provider.calls] == [TOKEN, META]  # the only two requests (a6)
    verifier = (form := dict(world.provider.calls[0][1])).pop("code_verifier")
    s256 = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).rstrip(b"=")
    assert s256.decode() == q["challenge"]  # S256, RFC 7636
    assert form == {"grant_type": "authorization_code", "code": "k1", "client_id": CLIENT,
                    "redirect_uri": f"{SITE}/oauth/callback"}
    assert world.store.held == {("egzos", f"login:{world.home.resolve()}"): REFRESH}
    record = world.home / signin.RECORD
    assert record.stat().st_mode & 0o777 == 0o600 and _kept(world) == ["login.json"]
    for secret in (REFRESH, verifier, "k1", "eyJ"):
        assert secret not in record.read_text() + err + json.dumps(out)
    assert "note" not in _run(capsys, world, "login", "--port", "0")[1]  # once, on first use


@pytest.mark.parametrize("taken", [False, True])
def test_a_terminal_that_cannot_listen_reads_the_paste(world, capsys, taken):
    with socket.socket() as busy:
        busy.bind(("127.0.0.1", 0))
        busy.listen()
        argv = ["--port", str(busy.getsockname()[1])] if taken else ["--paste"]
        code, out, err = _run(capsys, world, "login", *argv)
    assert code == 0 and out["origin"] == ORIGIN and ("cannot use port" in err) is taken
    q = dict(parse_qsl(urlsplit(world.page.start).query))
    assert sorted(q) == ["challenge", "paste", "state"] and q["paste"] == "1"  # nor any client


NOWHERE = dict.fromkeys(("code", "origin", "client_id", "issuer")) | {"nowhere": "1"}
LOOP, PASTE, BLIND = ["--port", "0"], ["--paste"], ["--paste", "--no-browser"]
LOW = type("Low", (Memory,), {"priority": 0.5})  # a store keyring does not recommend
CHAIN = type("Chain", (chainer.ChainerBackend,), {"backends": [LOW(), LOW()]})  # ranked 10


@pytest.mark.parametrize("argv, hand, given, said, asked", [
    (LOOP, {"issuer": OTHER}, {}, signin.FAILED, 0),  # the page names another provider
    (LOOP, {}, {"pin": OTHER}, signin.FAILED, 0),  # this container pins another provider
    (LOOP, {"origin": "http://cloud.example"}, {}, signin.FAILED, 0),  # no token's origin
    (LOOP, {"client_id": "c 1"}, {}, signin.FAILED, 0),  # no client id the provider issues
    (LOOP, {"code": None, "error": "1"}, {}, signin.FAILED, 0),  # the flow failed at egzos.io
    (LOOP, {"nowhere": "1"}, {}, signin.FAILED, 0),  # a code and nowhere: no hand-off of 3's
    (LOOP, {"origin": [OTHER, ORIGIN]}, {}, signin.FAILED, 0),  # a field twice, never the last read
    (LOOP, {}, {"claims": {"iss": OTHER}}, signin.FAILED, 1),
    (LOOP, {}, {"claims": {"client_id": "c-2"}}, signin.FAILED, 1),  # another container's client
    (LOOP, {}, {"claims": {"sub": " "}}, signin.FAILED, 1),  # no user id the provider issues
    (LOOP, {}, {"claims": {"exp": 1}}, signin.FAILED, 1),
    (PASTE, {}, {"claims": {"exp": 10**20}}, signin.FAILED, 1),  # no date: one line, no traceback
    (LOOP, {}, {"tokens": {"access_token": None}}, signin.FAILED, 1),  # the provider refused
    (LOOP, {}, {"meta": {"resource": OTHER}}, signin.FAILED, 2),
    (LOOP, {}, {"meta": {"authorization_servers": [OTHER]}}, signin.FAILED, 2),  # not the pin
    (LOOP, {}, {"meta": {"authorization_servers": f"{signin.ISSUER}/x"}}, signin.FAILED, 2),
    (LOOP, {}, {"patch": {"_write": Mock(side_effect=OSError)}}, signin.FAILED, 2),  # disk full
    (PASTE, {}, {"patch": {"_write": Mock(side_effect=OSError)}}, signin.FAILED, 2),  # pasted
    (LOOP, NOWHERE, {}, signin.NOWHERE, 0),
    (PASTE, NOWHERE, {}, signin.NOWHERE, 0),
    (PASTE, {"state": "someone-elses"}, {}, signin.NOT_YOURS, 0),  # well formed, not its state
    (PASTE, {"origin": [OTHER, ORIGIN]}, {}, signin.NOT_YOURS, 0),  # a field twice: not the page's
    (BLIND, {}, {"line": "k1.not-this-terminals-state.!!"}, signin.NOT_YOURS, 0),
    (BLIND, {}, {"line": ""}, signin.STOPPED, 0),
    (["--no-browser", "--port", "0"], {}, {"patch": {"WAIT_SECONDS": 0}}, signin.LATE, 0),
    (LOOP, {}, {"patch": {"_open": lambda url: True, "WAIT_SECONDS": 0}}, signin.LATE, 0),
    (LOOP, {}, {"patch": {"_open": Mock(side_effect=KeyboardInterrupt)}}, signin.STOPPED, 0),
])
def test_each_miss_is_one_line_and_keeps_nothing(world, capsys, argv, hand, given, said, asked):
    if "pin" in given:
        assert main(["config", "set", "identity.issuer", given["pin"]]) == 0
    for name, value in given.get("patch", {}).items():  # one of signin's own seams
        world.patch(signin, name, value)
    world.stdin.write(given.get("line", "") + "\n")
    world.stdin.seek(0)
    world.page.hand = hand
    vars(world.provider).update(given)
    code, out, err = _run(capsys, world, "login", *argv)
    assert (code, out, len(world.provider.calls)) == (1, {"error": said}, asked)
    assert _kept(world) == [] and world.store.held == {} and REFRESH not in err
    assert err.startswith("matching code")  # before any browser: Ctrl-C there finds it shown
    tail = "nowhere=1" if said == signin.NOWHERE else "failed=1"  # the browser is told the truth
    assert world.page.answers[-1:] in ([], [(302, f"{SITE}/connect/cli/done?{tail}", b"")])
    if "--no-browser" in argv:  # the URL printed, never opened: for this machine, or to paste
        assert f"{SITE}/connect/cli?" in err and ("on this machine" in err) is (argv != BLIND)


@pytest.mark.parametrize("store", [fail.Keyring(), null.Keyring(), LOW(), CHAIN(), None])
def test_with_no_usable_store_the_refresh_token_goes_to_a_0600_file(world, capsys, store):
    world.store = store or world.store  # None: the OS store, and the provider issues no refresh
    world.provider.tokens = {} if store else {"refresh_token": None}
    code, out, _ = _run(capsys, world, "login", "--port", "0")
    secret, kept = world.home / signin.SECRET, (world.home / signin.RECORD).read_text()
    assert (code, out["refresh"], REFRESH in kept + json.dumps(out)) == (0, store and "file", False)
    assert (secret.read_text(), secret.stat().st_mode & 0o777) == (REFRESH, 0o600) if store else (
        not secret.exists())


def test_no_path_reaches_the_confirm_or_offers_the_button():
    """a6 on #361: the CLI never serves or offers the step-up button (identity.md §8). The loopback
    test shows GET /v1/confirm?proof=button refused and the only two requests the login makes."""
    assert not [w for w in ("/v1/", "confirm", "proof", "button") if w in inspect.getsource(signin)]


def test_only_this_containers_owner_signs_in_and_only_through_the_site(world, capsys, monkeypatch):
    for site in ("https://evil.example", "http://evil.example", "file:///etc"):
        monkeypatch.setenv("EGZOS_SITE", site)  # a pasted `EGZOS_SITE=… egzos login`
        assert _run(capsys, world, "login", "--port", "0")[:2] == (2, {"error": signin.BAD_SITE})
    assert main(["login", "--site", SITE]) == 2  # and no flag moves it
    assert inspect.signature(login).parameters["port"].default.default == signin.PORT  # one 7427
    monkeypatch.setenv("EGZOS_SITE", SITE)
    monkeypatch.setenv("EGZOS_TOKEN", Container(world.home).auth.mint(
        principal="client", owner="self", client="a", role="admin", scopes=["*"], actor="self",
        by_principal="interactive").secret)
    assert _run(capsys, world, "login", "--port", "0")[0] == 1  # a client principal
    monkeypatch.setenv("EGZOS_HOME", str(world.home.parent / "none"))
    code, out, _ = _run(capsys, world, "login")  # no container here at all
    assert code == 2 and "egzos init" in out["error"]
    assert world.page.start is None and _kept(world) == []
