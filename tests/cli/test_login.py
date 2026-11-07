# Copyright 2026 Ali Sasanian
# SPDX-License-Identifier: LicenseRef-PolyForm-Strict-1.0.0
"""`egzos login` (identity.md §3a, §8): the site, provider and store played; the listener real."""

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
from keyring import backend, errors
from keyring.backends import chainer, fail, null

from egzos.cli import login, main, signin
from egzos.container import Container

SITE, ORIGIN, CLIENT, OTHER = "http://127.0.0.1:9", "https://cloud.example", "c-1", "https://x.ex"
TOKEN = "https://kvdhimpnqatnidpmzvga.supabase.co/auth/v1/oauth/token"  # the pin, as shipped
REFRESH, META = "r/1", ORIGIN + signin.METADATA  # '/' is not base64url: no state can hold it


class Memory(backend.KeyringBackend):
    """The OS credential store, held in memory: no test reaches this machine's own."""

    priority = 1

    def __init__(self): self.held = {}
    def set_password(self, service, user, secret): self.held[service, user] = secret
    def get_password(self, service, user): return self.held.get((service, user))
    def delete_password(self, service, user): del self.held[service, user]  # gone: a KeyError


class Provider:
    """The provider's token endpoint and the cloud's metadata, as `signin._request` reaches them."""

    def __init__(self): self.calls, self.claims, self.tokens, self.meta = [], {}, {}, {}

    def __call__(self, url, form=None):  # the token by POST, the metadata by GET, never otherwise
        self.calls.append((url, form))
        claims = {"iss": signin.ISSUER, "client_id": CLIENT, "sub": "u-1", "email": "me@x.ex",
                  "exp": int(time.time()) + 3600, **self.claims}
        token = {"access_token": jwt.encode(claims, "k" * 32), "refresh_token": REFRESH}
        meta = {"resource": ORIGIN, "authorization_servers": [signin.ISSUER], **self.meta}
        return {(TOKEN, False): token | self.tokens, (META, True): meta}.get((url, form is None))


class Page:
    """egzos.io's pages: the code handed back, to the loopback or as the paste token."""
    fetch = {"Sec-Fetch-Dest": "document", "Sec-Fetch-Mode": "navigate"}  # a browser navigating

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
            ("GET", hand.replace("?", "/?", 1), {}),  # another path: /oauth/callback itself alone
            ("GET", hand, {"Sec-Fetch-Dest": "image"}), ("GET", "/v1/confirm?proof=button", {}),
            ("GET", hand, self.fetch),  # a browser navigating; test 3's carry no Fetch Metadata
        ]:
            self.answers.append(_call(port, path, method, headers))


def _call(port, path, method="GET", headers=None):
    conn = http.client.HTTPConnection("127.0.0.1", port, timeout=5)
    conn.request(method, path, headers=headers or {})
    return (r := conn.getresponse()).status, r.getheader("Location"), r.read()


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


def _run(capsys, world, *argv, human=False):
    capsys.readouterr()
    code = main(list(argv) if human else ["--json", *argv])
    if world.page.thread:
        world.page.thread.join(5)
    out, err = capsys.readouterr()
    return code, out if human else json.loads(out), err


def _kept(world):
    return sorted(p.name for p in world.home.glob("login.*"))


def test_the_loopback_takes_one_checked_hand_off_and_keeps_the_login(world, capsys):
    real, bound = signin.HTTPServer, []  # the listener binds 127.0.0.1 alone: never the LAN
    world.patch(signin, "HTTPServer", lambda a, h: bound.append(a[0]) or real(a, h))
    code, out, err = _run(capsys, world, "login", "--port", "0")
    start, q = world.page.start, dict(parse_qsl(urlsplit(world.page.start).query))
    assert code == 0 and out["origin"] == ORIGIN and out["sub"] == "u-1" and "note" in out
    assert start.startswith(f"{SITE}/connect/cli?") and start not in err  # no terminal, no URL
    assert set(q) == {"challenge", "state", "port"} and set(bound) == {"127.0.0.1"}  # §3a; no LAN
    assert f"matching code {signin.matching_code(q['state'])}" in err and len(q["state"]) >= 43
    assert signin.matching_code("egzos-test-state") == "N7XOBA"  # the docstring's vector
    # a POST, another state, Host or path, an image, the confirm route: refused, and waited on
    assert world.page.answers == [(404, None, b"")] * 6 + [(302, f"{SITE}/connect/cli/done", b"")]
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
    assert record.stat().st_mode & 0o777 == 0o600 and _kept(world) == ["login.json", "login.told"]
    for secret in (REFRESH, verifier, "k1", "eyJ"):
        assert secret not in record.read_text() + err + json.dumps(out)
    assert "note" not in _run(capsys, world, "login", "--port", "0")[1]  # once, on first use
    again = dict(parse_qsl(urlsplit(world.page.start).query))  # a new state and pair each time
    assert not {again["state"], again["challenge"]} & {q["state"], q["challenge"]}


@pytest.mark.parametrize("taken", [False, True])
def test_a_terminal_that_cannot_listen_reads_the_paste(world, capsys, taken):
    with socket.socket() as busy:
        busy.bind(("127.0.0.1", 0))
        busy.listen()
        argv = ["--port", str(busy.getsockname()[1])] if taken else ["--paste"]
        code, out, err = _run(capsys, world, "login", *argv, human=True)  # as a person reads it
    head, note = out.splitlines()  # one line, and §8's note on first use
    assert (code, head, "cannot use" in err) == (0, f"signed in to {ORIGIN} as me@x.ex", taken)
    assert "allow_button" in note and all(s not in err + out for s in ("k1", "eyJ", REFRESH))
    q = dict(parse_qsl(urlsplit(world.page.start).query))
    assert sorted(q) == ["challenge", "paste", "state"] and q["paste"] == "1"  # nor any client


NOWHERE = dict.fromkeys(("code", "origin", "client_id", "issuer")) | {"nowhere": "1"}
LOOP, PASTE, BLIND = ["--port", "0"], ["--paste"], ["--paste", "--no-browser"]
LOW = type("Low", (Memory,), {"priority": 0.5})  # a store keyring does not recommend
CHAIN = type("Chain", (chainer.ChainerBackend,), {"backends": [LOW(), LOW()]})  # ranked 10
LOCKED = type("Locked", (Memory,), {"set_password": Mock(side_effect=errors.KeyringLocked)})


@pytest.mark.parametrize("argv, hand, given, said, asked", [
    (LOOP, {"issuer": OTHER}, {}, signin.FAILED, 0),  # the page names another provider
    (LOOP, {}, {"pin": OTHER}, signin.FAILED, 0),  # this container pins another provider
    (LOOP, {"origin": "http://cloud.example"}, {}, signin.FAILED, 0),  # no token's origin
    (LOOP, {"client_id": "c 1"}, {}, signin.FAILED, 0),  # no client id the provider issues
    (LOOP, NOWHERE | {"nowhere": None, "error": "1"}, {}, signin.FAILED, 0),  # failed at egzos.io
    (LOOP, {"nowhere": "1"}, {}, signin.FAILED, 0),  # a code and nowhere: no hand-off of 3's
    (LOOP, NOWHERE | {"nowhere": "2"}, {}, signin.FAILED, 0),  # nowhere is 1, or no hand-off
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
    (BLIND, {}, {"line": "k1.state.!!"}, signin.NOT_YOURS, 0),  # malformed: no base64url triple
    (BLIND, {}, {"line": ""}, signin.STOPPED, 0),
    (["--no-browser", "--port", "0"], {}, {"patch": {"WAIT_SECONDS": 0}}, signin.LATE, 0),
    (LOOP, {}, {"patch": {"_open": lambda url: False, "WAIT_SECONDS": 0}}, signin.LATE, 0),
    (LOOP, {}, {"patch": {"_open": Mock(side_effect=KeyboardInterrupt)}}, signin.STOPPED, 0),
])
def test_each_miss_is_one_line_and_keeps_nothing(world, capsys, argv, hand, given, said, asked):
    if "pin" in given:
        assert main(["config", "set", "identity.issuer", given["pin"]]) == 0
    for name, value in given.get("patch", {}).items():  # one of signin's own seams
        world.patch(signin, name, value)
    world.stdin.write(given.get("line", "") + "\n")
    world.stdin.seek(0)
    world.page.hand, world.page.fetch = hand, {}  # no Fetch Metadata: read as a document
    vars(world.provider).update(given)
    code, out, err = _run(capsys, world, "login", *argv)
    assert (code, out, len(world.provider.calls)) == (1, {"error": said}, asked)
    assert _kept(world) == [] and world.store.held == {} and REFRESH not in err
    assert err.startswith("matching code")  # before any browser: Ctrl-C there finds it shown
    tail = "nowhere=1" if said == signin.NOWHERE else "failed=1"  # the browser is told the truth
    assert world.page.answers[-1:] in ([], [(302, f"{SITE}/connect/cli/done?{tail}", b"")])
    if "--no-browser" in argv or said == signin.LATE:  # the URL printed: no browser took it
        assert f"{SITE}/connect/cli?" in err and ("on this machine" in err) is (argv != BLIND)


@pytest.mark.parametrize("store", [fail.Keyring(), null.Keyring(), LOW(), CHAIN(), LOCKED(), None])
def test_with_no_store_a_0600_file_holds_it_and_no_old_token_outlives_a_login(world, capsys, store):
    (secret := world.home / signin.SECRET).write_text("old")  # an earlier login's: none outlives it
    world.store.held = {} if store else {("egzos", f"login:{world.home.resolve()}"): "old"}
    memory, world.store = world.store, store or world.store  # None: the OS store, none issued
    world.provider.tokens = {} if store else {"refresh_token": None}
    code, out, _ = _run(capsys, world, "login", "--port", "0")
    kept = (world.home / signin.RECORD).read_text()
    assert (code, out["refresh"], REFRESH in kept + json.dumps(out)) == (0, store and "file", False)
    assert (secret.read_text(), secret.stat().st_mode & 0o777) == (REFRESH, 0o600) if store else (
        not secret.exists() and memory.held == {})
    world.patch(signin, "_write", Mock(side_effect=OSError))  # the disk fills: no login is kept
    assert _run(capsys, world, "login", "--port", "0")[0] == 1 and _kept(world) == ["login.told"]


def test_no_path_reaches_the_confirm_or_offers_the_button():  # a6 on #361; identity.md §8
    code = inspect.getsource(signin) + inspect.getsource(login)  # the command and its module
    assert not [w for w in ("/v1/", "confirm", "proof", "button") if w in code]


def test_only_this_containers_owner_signs_in_and_only_through_the_site(world, capsys, monkeypatch):
    for site in ("https://evil.example", "http://evil.example", "file:///etc"):
        monkeypatch.setenv("EGZOS_SITE", site)  # a pasted `EGZOS_SITE=… egzos login`
        assert _run(capsys, world, "login", "--port", "0")[:2] == (2, {"error": signin.BAD_SITE})
    assert main(["login", "--site", SITE]) == 2  # and no flag moves it
    assert inspect.signature(login).parameters["port"].default.default == signin.PORT  # one 7427
    monkeypatch.delenv("EGZOS_SITE")  # unset: egzos.io's stand-in while §AE holds, as shipped
    assert signin._site() == "https://egzos-site.vercel.app"
    monkeypatch.setenv("EGZOS_SITE", SITE)
    monkeypatch.setenv("EGZOS_TOKEN", Container(world.home).auth.mint(
        principal="client", owner="self", client="a", role="admin", scopes=["*"], actor="self",
        by_principal="interactive").secret)
    assert _run(capsys, world, "login", "--port", "0")[0] == 1  # a client principal
    monkeypatch.setenv("EGZOS_HOME", str(world.home.parent / "none"))
    code, out, _ = _run(capsys, world, "login")  # no container here at all
    assert code == 2 and "egzos init" in out["error"]
    assert world.page.start is None and _kept(world) == []
