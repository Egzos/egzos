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
import sys
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


class Keys(io.StringIO):
    """Standard input as a person types it: a line `^C` is Ctrl-C pressed there."""

    def readline(self, size=-1):
        if (line := super().readline(size)) == "^C\n":
            raise KeyboardInterrupt
        return line


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
        typed = self.stdin.read()  # what the person types after the paste: 7's answer
        self.stdin.seek(0)
        self.stdin.write((f"{sent['code']}.{sent['state']}.{b64}\n" if "code" in sent
                          else f"nowhere.{sent['state']}\n") + typed)
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
    stdin = Keys()
    w = SimpleNamespace(home=tmp_path / ".egzos", provider=Provider(), page=Page(stdin),
                        store=Memory(), stdin=stdin, patch=monkeypatch.setattr)
    monkeypatch.setattr("keyring.get_keyring", lambda: w.store)
    monkeypatch.setattr("egzos.cli.signin._request", w.provider)
    monkeypatch.setattr("egzos.cli.signin._open", w.page)
    monkeypatch.setattr("egzos.cli.signin.WAIT_SECONDS", 5)  # a lost hand-off fails, never hangs
    monkeypatch.setattr("egzos.cli.signin._at_terminal", lambda: True)  # a person at a terminal
    monkeypatch.setattr("sys.stdin", stdin)
    return w


def _run(capsys, world, *argv, human=False, typed="y"):
    capsys.readouterr()
    world.stdin.seek(0)  # what the person types this time; None: end of input, nothing typed
    world.stdin.truncate()
    world.stdin.write("" if typed is None else typed + "\n")
    world.stdin.seek(0)
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
    world.page.hand, world.page.fetch = hand, {}  # no Fetch Metadata: read as a document
    vars(world.provider).update(given)
    code, out, err = _run(capsys, world, "login", *argv, typed=given.get("line", "y"))
    assert (code, out, len(world.provider.calls)) == (1, {"error": said}, asked)
    assert _kept(world) == [] and world.store.held == {} and REFRESH not in err
    assert err.startswith("matching code")  # before any browser: Ctrl-C there finds it shown
    late = "_write" in given.get("patch", {})  # the disk fills after the yes: every check passed
    assert ("[y/N]" in err) is late  # so no miss is ever put to the person
    tail = "" if late else "?nowhere=1" if said == signin.NOWHERE else "?failed=1"  # the truth
    assert world.page.answers[-1:] in ([], [(302, f"{SITE}/connect/cli/done{tail}", b"")])
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


# -- protocol 7: asked, then kept (identity.md §3a, §8; v0.7 §AH) --------------------------------
ASKED = ("account  {}\ncloud    {}\n"
         "keep this sign-in on this machine? only if both are yours [y/N] ")  # as a person reads it
CUT = "y" + " " * 63 + "x"  # a line past the 64 characters read: what is read alone is no yes


def _held(world, memory):
    """Every trace of a sign-in here, to the byte: the files, their modes and times, the store."""
    return {p.name: (p.read_bytes(), p.stat().st_mode, p.stat().st_mtime_ns)
            for p in world.home.glob("login.*")}, dict(memory.held)


@pytest.mark.parametrize("argv", [LOOP, PASTE])
@pytest.mark.parametrize("typed", ["y", "Y", "yes", "YES", " Yes\t"])
def test_a_yes_typed_here_keeps_it_once_who_and_where_are_shown(world, capsys, argv, typed):
    code, out, err = _run(capsys, world, "login", *argv, typed=typed)
    assert (code, _kept(world), world.store.held) == (
        0, ["login.json", "login.told"], {("egzos", f"login:{world.home.resolve()}"): REFRESH})
    assert err.endswith(ASKED.format("me@x.ex", ORIGIN))  # the email, the origin, then asked
    verifier = dict(world.provider.calls[0][1])["code_verifier"]
    assert not [s for s in (REFRESH, verifier, "k1", "eyJ") if s in err + json.dumps(out)]


@pytest.mark.parametrize("store", [None, fail.Keyring()])  # the earlier one in the store, or a file
@pytest.mark.parametrize("argv", [LOOP, PASTE])
@pytest.mark.parametrize("typed", ["n", "no", "", "maybe", "ye", "yes please", "ye\u017f", CUT,
                                   None, "^C"])  # U+017F, long s: casefold would read it as "yes"
def test_anything_but_a_yes_keeps_nothing_and_an_earlier_sign_in_stays_whole(
        world, capsys, monkeypatch, store, argv, typed):
    memory, world.store = world.store, store or world.store
    assert _run(capsys, world, "login", *argv)[0] == 0  # an earlier sign-in, kept on a yes
    before = _held(world, memory)
    world.provider.claims, world.provider.tokens = {"sub": "u-2", "email": "you@x.ex"}, {
        "refresh_token": "r/2"}
    for name in ("EGZOS_YES", "EGZOS_ASSUME_YES", "YES", "CI"):  # no variable answers for anyone
        monkeypatch.setenv(name, "1")
    code, out, err = _run(capsys, world, "login", *argv, typed=typed)
    said = signin.STOPPED if typed == "^C" else signin.NOT_KEPT  # None: end of input, a no
    assert (code, out) == (1, {"error": said}) and err.count("[y/N]") == 1  # asked once
    assert err.endswith(ASKED.format("you@x.ex", ORIGIN) + "\n" * (typed in (CUT, None, "^C")))
    assert [url for url, _ in world.provider.calls] == [TOKEN, META] * 2  # checked, then asked
    assert _held(world, memory) == before and "r/2" not in err + json.dumps(out)


@pytest.mark.parametrize("email, shown", [
    ("me@x.ex", "me@x.ex"),  # the email, first
    (None, "u-1"), ("", "u-1"), (7, "u-1"),  # none, or none an id's rule holds: the sub
    ("me @x.ex", "u-1"),  # a space
    ("me@x.ex\ncloud    https://x.ex", "u-1"),  # a second cloud line forged in the claim
    ("\u202eme@x.ex", "u-1"),  # a bidi override
    ("me@x.ex\x1b[8m", "u-1"),  # an escape a terminal acts on, or answers into standard input
    ("m" * 251 + "@x.ex", "u-1"),  # 256 characters, past an id's 255
    ("m\u0435@x.ex", "m\\u0435@x.ex"),  # a look-alike letter (Cyrillic): shown as its escape
])
def test_the_account_shown_is_the_email_else_the_sub_and_reads_as_what_it_is(
        world, capsys, email, shown):
    world.provider.claims = {"email": email}
    code, out, err = _run(capsys, world, "login", "--port", "0")
    assert err.endswith(ASKED.format(shown, ORIGIN))  # no line forged, no escape run, no look-alike
    assert (code, out["email"]) == (0, None if shown == "u-1" else email)  # kept as judged


@pytest.mark.parametrize("argv", [LOOP, PASTE, BLIND])
def test_with_no_terminal_to_ask_at_nothing_starts(world, capsys, argv):
    real, bound = signin.HTTPServer, []
    world.patch(signin, "HTTPServer", lambda a, h: bound.append(a) or real(a, h))
    world.patch(signin, "_at_terminal", lambda: False)  # a pipe, a file, a script's stream
    code, out, err = _run(capsys, world, "login", *argv)
    assert (code, out, err) == (2, {"error": signin.NO_TERMINAL}, "")  # no matching code shown
    assert (bound, world.page.start, world.provider.calls) == ([], None, [])  # nothing started
    assert world.stdin.read() == "y\n" and _kept(world) == [] and world.store.held == {}


@pytest.mark.parametrize("stdin, stdout, stderr, asked", [
    (True, True, True, True),
    (False, True, True, False),  # `echo y | egzos login`: a pipe types no yes
    (True, False, True, False),  # `egzos login > file`: the CLI's own test (presence.is_terminal)
    (True, True, False, False),  # `egzos login 2>log`: the account would be shown to no one
    (None, True, True, False),  # no standard input at all
    ("closed", True, True, False),
])
def test_a_terminal_to_ask_at_is_one_on_standard_input_output_and_error(
        monkeypatch, stdin, stdout, stderr, asked):
    closed = io.StringIO()
    closed.close()
    streams = {True: SimpleNamespace(isatty=lambda: True), None: None, "closed": closed,
               False: SimpleNamespace(isatty=lambda: False)}
    monkeypatch.setattr("egzos.authz.presence.is_terminal", lambda: stdout)  # connect's seam
    monkeypatch.setattr("sys.stdin", streams[stdin])
    monkeypatch.setattr("sys.stderr", streams[stderr])
    assert signin._at_terminal() is asked


def test_no_flag_variable_or_setting_answers_for_the_person(world, capsys):
    for flag in ("--yes", "-y", "--assume-yes"):
        code, out, _ = _run(capsys, world, "login", flag)
        assert code == 2 and out["error"].startswith(f"No such option: {flag}")
    assert set(inspect.signature(login).parameters) == {"port", "paste", "no_browser"}
    assert set(inspect.signature(signin.login).parameters) == {
        "home", "issuer", "port", "paste", "browser"}
    source = inspect.getsource(signin) + inspect.getsource(login)
    reads = source.count("environ") + source.count("getenv"), source.count("config_value")
    assert reads == (2, 1)  # EGZOS_SITE, a display, the issuer pin: none of them is a yes
    code, out, _ = _run(capsys, world, "login", "--port", "0", typed=None)  # end of input: a no
    assert (code, out, _kept(world)) == (1, {"error": signin.NOT_KEPT}, [])  # nor §8's note told
    assert "note" in _run(capsys, world, "login", "--port", "0")[1]  # it waits for a kept one


def test_the_browser_is_answered_and_the_listener_gone_before_the_terminal_asks(world, capsys):
    seen = []

    class Asked(Keys):  # what the browser, the listener and the disk hold as the answer is read
        def readline(self, size=-1):
            world.page.thread.join(5)
            with pytest.raises(ConnectionRefusedError):  # closed: no one else gets in
                _call(int(dict(parse_qsl(urlsplit(world.page.start).query))["port"]), "/")
            seen.append((world.page.answers[-1], _kept(world)))
            return super().readline(size)

    world.stdin = Asked()
    world.patch("sys.stdin", world.stdin)
    assert _run(capsys, world, "login", "--port", "0")[0] == 0
    assert seen == [((302, f"{SITE}/connect/cli/done", b""), [])]  # finish here; none kept yet
    assert _kept(world) == ["login.json", "login.told"]


@pytest.mark.parametrize("argv", [LOOP, PASTE])
def test_keys_pressed_before_the_question_showed_are_dropped(world, capsys, argv):
    termios, order = pytest.importorskip("termios"), []
    read = world.stdin.readline
    world.patch(world.stdin, "fileno", lambda: 0)  # a terminal's, whose driver is played here
    world.patch(world.stdin, "readline", lambda size=-1: order.append("read") or read(size))
    world.patch(termios, "tcflush",
                lambda fd, how: order.append((fd, how, len(world.provider.calls))))
    assert _run(capsys, world, "login", *argv)[0] == 0  # after the paste and 6, before the answer
    assert order == ["read"] * (argv == PASTE) + [(0, termios.TCIFLUSH, 2), "read"]


def test_on_windows_the_keys_pressed_before_the_question_are_dropped(monkeypatch):
    keys = list("y\r")
    with monkeypatch.context() as m:  # the helper alone: no CLI run on a patched platform
        m.setattr(sys, "platform", "win32")
        m.setitem(sys.modules, "msvcrt", SimpleNamespace(kbhit=lambda: bool(keys), getwch=keys.pop))
        signin._drop_typed_ahead()
    assert keys == []


def test_a_paste_past_any_token_is_refused_so_nothing_behind_it_answers(world, capsys):
    def padded(url, page=world.page):  # the page's token right-aligned to the read, a yes behind
        page(url)
        world.stdin.write(world.stdin.getvalue().rstrip("\n").rjust(2048) + "y\n")  # over it
        world.stdin.seek(0)
        return True

    world.patch(signin, "_open", padded)
    code, out, err = _run(capsys, world, "login", "--paste", typed=None)
    assert (code, out, "[y/N]" in err) == (1, {"error": signin.NOT_YOURS}, False)
    assert world.provider.calls == [] and _kept(world) == []
