# Copyright 2026 Ali Sasanian
# SPDX-License-Identifier: LicenseRef-PolyForm-Strict-1.0.0
"""
`egzos login`: a terminal signs in to its person's cloud through egzos.io, the terminal holding the
PKCE verifier (identity.md §3a, §8; v0.7 §AG). egzos.io's pages are built from this protocol:

1. Start. The terminal makes a PKCE verifier (64 base64url characters), its S256 challenge
   (RFC 7636) and a `state` (32 random bytes, base64url), binds 127.0.0.1:<port> (PORT unless
   --port; when it cannot, or with --paste, the paste path), prints the matching code and opens
       <site>/connect/cli?challenge=<challenge>&state=<state>&port=<port>
   (&paste=1 in place of &port=<port> on the paste path), naming nothing else: no container, client
   or issuer. <site> is SITE; EGZOS_SITE replaces it for tests, a loopback origin only. Before
   all of it: unless standard input, output and error are each a terminal (7 shows on error and
   reads input; output is the CLI's own test) and input takes a line at a time (canonical mode;
   on Windows, line input), the terminal refuses in one line, starting nothing: on standard error
   too when output is not a terminal and error is, so the person at it reads the line.
2. Matching code: the first six characters of the RFC 4648 base32 (A-Z, 2-7) of the first five
   bytes of SHA-256 over the state's ASCII bytes; state `egzos-test-state` gives `N7XOBA`.
3. Hand-off, loopback. The page navigates its tab (top level: never a fetch, an image or a frame) to
       http://127.0.0.1:<port>/oauth/callback?code=…&state=…&origin=…&client_id=…&issuer=…
   with its record's triple (the cloud container's origin, its client_id, the issuer), or with
   ?state=…&nowhere=1 for a person egzos hosts no container for, ?state=…&error=1 for a flow that
   failed; each field once, no other. The listener takes one GET at that path with its own state and
   Host 127.0.0.1:<port>, exchanges and checks (5, 6), answers with a 302 to <site>/connect/cli/done
   (?nowhere=1, ?failed=1 for any other miss) and stops; until then anything else gets an empty 404.
   The 302 goes before the terminal asks (7), so the bare done page knows only that the checks
   passed, keeps nothing, and says exactly: "Finish in your terminal: it shows the account you
   signed in as and the cloud, and keeps this sign-in only if you type yes there. Until then,
   nothing is kept. You can close this tab."
4. Hand-off, paste (&paste=1 alone: a listening terminal reads none). The page shows one token for
   standard input, <code>.<state>.<triple>, <triple> the unpadded base64url of origin=…&client_id=…
   &issuer=… form-encoded as in 3, or nowhere.<state>, under 1000 characters (macOS: 1024 a line).
   The terminal reads it as one line at standard input's descriptor, below any buffering, as 7
   reads its answer, and refuses it whole when it is 2048 characters or more, or the read holds a
   line end before its last: never a page's token, and nothing of it answers 7. A login that
   ends before 7 drops what is left in the terminal, so no other line of a paste reaches the shell.
5. Exchange, at the pinned issuer alone (the local container's identity.issuer, else ISSUER), which
   a handed issuer must equal: POST <issuer>/oauth/token, form-encoded, as a public client: code,
   grant_type=authorization_code, redirect_uri=<site>/oauth/callback, code_verifier, client_id.
6. Checks, before anything is kept: the access token's `iss` is the pinned issuer and its
   `client_id` claim the handed one, and GET <origin>/.well-known/oauth-protected-resource names
   that issuer in `authorization_servers` and that origin as `resource`. Any miss is one line, and
   nothing is kept. The claims are read unverified: the terminal is not the resource server, and
   the container checks the signature on every request (identity.md §3).
7. Asked, then kept. Once 6 passes and the listener is closed, standard error shows
       account  <the email claim, if an id's rule holds it (identity.provider_id); else the sub>
       cloud    <origin>
       keep this sign-in on this machine? only if both are yours [y/N]
   each character of the account past ASCII shown as its escape. Keys pressed before the question
   are then dropped (a drop that fails keeps nothing), and one line is read from standard input,
   typed after the question shows (on the paste path, too: nothing pasted or typed before it
   counts). y or yes, in any case, with spaces or tabs around it, on a line ended by Enter, keeps;
   anything else (y with no Enter, an empty line, end of input or Ctrl-C) keeps nothing and leaves
   an earlier sign-in as it was. No flag, variable or setting stands in for the yes. Only then is
   it kept: the refresh token in the OS credential store through `keyring` (service `egzos`,
   account `login:<EGZOS_HOME>`), else in SECRET (0600); who and where in RECORD (0600). The
   access token stays in this process. No token is printed, logged, or put in a URL or argv.
"""

from __future__ import annotations

import base64
import contextlib
import hashlib
import json
import os
import secrets
import sys
import time
import urllib.request
import webbrowser
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import parse_qsl, urlencode, urlsplit

import jwt

from egzos.authz.values import same
from egzos.identity import ConfigError, provider_id, validate

#: egzos.io's stand-in while v0.7 §AE holds (identity.md §3a). EGZOS_SITE replaces it for tests,
#: a loopback origin only: never a flag, nor a value a pasted command could aim elsewhere.
SITE = "https://egzos-site.vercel.app"
#: The identity project's issuer: public, and the platform ships the same.
ISSUER = "https://kvdhimpnqatnidpmzvga.supabase.co/auth/v1"
PORT = 7427  # not 7420, nor the lifeboat's 7425, nor serve's 7426
CALLBACK, METADATA = "/oauth/callback", "/.well-known/oauth-protected-resource"
WAIT_SECONDS = 600  # a code's ten minutes; checked between requests, so a held connection delays it
RECORD, SECRET, SERVICE = "login.json", "login.secret", "egzos"
HANDED = {"code", "state", "origin", "client_id", "issuer"}  # protocol 3's fields, each once
#: One read of standard input takes a whole line, the longest a terminal holds (Linux: 4095 and
#: Enter; macOS: 1024), so nothing typed on it is left for the shell once egzos exits.
LINE = 4096
_STAY = urllib.request.HTTPRedirectHandler()  # every request's: a redirect is an error status,
_STAY.redirect_request = lambda *args: None  # so nothing is ever sent on to where one points

FAILED = "the sign-in did not go through — nothing was kept; run `egzos login` again"
NOWHERE = "nothing to log in to — egzos hosts no cloud for this account"
NOT_YOURS = "that is not the code this terminal's page shows — nothing was kept"
LATE = "no sign-in came back in ten minutes — nothing was kept"
STOPPED = "stopped — nothing was kept"
BAD_SITE = "EGZOS_SITE is for tests: a loopback origin such as http://127.0.0.1:8000, or unset"
NO_TERMINAL = ("`egzos login` asks at a terminal before it keeps a sign-in — run it in one, "
               "with no pipe or redirect (over SSH, `ssh -t`)")
NOT_KEPT = "nothing was kept — only y or yes keeps a sign-in; any earlier one here stays as it was"
ASK = "keep this sign-in on this machine? only if both are yours [y/N] "


class Failed(Exception):
    """A sign-in that did not land: (line,) or (line, exit code); the line is all a person reads."""


def matching_code(state: str) -> str:
    """Protocol 2."""
    return base64.b32encode(hashlib.sha256(state.encode("ascii")).digest()[:5]).decode()[:6]


def _site() -> str:
    """SITE, or for tests EGZOS_SITE as plain http, which `validate` holds to a loopback host."""
    test = os.environ.get("EGZOS_SITE")
    with contextlib.suppress(ConfigError):
        if not test or test.startswith("http://") and validate("identity.origin", test):
            return test or SITE
    raise Failed(BAD_SITE, 2)


def _at_terminal() -> bool:
    """Whether 7 can ask: standard error shows the question and standard input takes the answer,
    each a terminal, input a line at a time, and standard output is one by the CLI's own test
    (presence.is_terminal)."""
    from egzos.authz.presence import is_terminal  # here, as `connect` reads it

    try:
        return is_terminal() and sys.stdin.isatty() and sys.stderr.isatty() and _cooked()
    except Exception:  # no stream at all, a closed one, no terminal driver behind it
        return False


def _cooked() -> bool:
    """Whether standard input's terminal hands over a line at a time, as `_read` takes it: canonical
    mode (ICANON), or on Windows a console's line input."""
    if sys.platform == "win32":
        import ctypes
        import msvcrt

        mode = ctypes.c_ulong()
        handle = msvcrt.get_osfhandle(sys.stdin.fileno())
        if not ctypes.windll.kernel32.GetConsoleMode(handle, ctypes.pointer(mode)):
            return False  # NUL, a file: no console
        return bool(mode.value & 0x0002)  # ENABLE_LINE_INPUT
    import termios

    return bool(termios.tcgetattr(sys.stdin.fileno())[3] & termios.ICANON)


def _read() -> bytes:
    """One line of standard input, read at its descriptor, below Python's buffer: the terminal
    hands over one of its lines a read (`_cooked`), so a read leaves nothing in this process for a
    later one to take; what stays in the terminal is dropped at 7, or as a login that ends before
    it exits (protocol 4, 7)."""
    return os.read(sys.stdin.fileno(), LINE)


def _open(url: str) -> bool:
    """Whether a browser took it; none on a Linux with no display (a text one takes the tty)."""
    if sys.platform.startswith("linux") and not os.environ.keys() & {"DISPLAY", "WAYLAND_DISPLAY"}:
        return False
    return webbrowser.open(url)


def _request(url: str, form: dict[str, str] | None = None) -> dict[str, Any] | None:
    """GET, or POST `form`: the JSON object answered, or None (an error status, over 64 KiB)."""
    data = None if form is None else urlencode(form).encode()
    req = urllib.request.Request(url, data=data, headers={"Accept": "application/json"})
    try:
        with urllib.request.build_opener(_STAY).open(req, timeout=10) as r:  # https, loopback http
            body = r.read(64 * 1024 + 1)
        doc = json.loads(body) if len(body) <= 64 * 1024 else None
    except Exception:  # refused, cut off, not JSON, nested too deep to read: no answer
        return None
    return doc if isinstance(doc, dict) else None


def _pasted(line: str) -> dict[str, str]:
    """Protocol 4, read back into the fields of 3; {} for anything else."""
    head, _, last = line.strip().rpartition(".")
    if head == "nowhere":
        return {"state": last, "nowhere": "1"}
    code, _, state = head.rpartition(".")
    try:
        raw = base64.b64decode(last + "=" * (-len(last) % 4), b"-_", validate=True)
        triple = dict(pairs := parse_qsl(raw.decode("ascii"), keep_blank_values=True))
    except ValueError:
        return {}
    ok = code and len(pairs) == 3 and set(triple) == {"origin", "client_id", "issuer"}
    return {**triple, "code": code, "state": state} if ok else {}


class _Callback(BaseHTTPRequestHandler):
    """Protocol 3: one GET, checked and exchanged before its 302; anything else, an empty 404."""

    timeout = 5  # a connection that says nothing is dropped: it cannot hold the one thread

    def do_GET(self) -> None:
        s, url = self.server, urlsplit(self.path)
        got = dict(pairs := parse_qsl(url.query, keep_blank_values=True))
        if (url.path != CALLBACK or s.outcome is not None or self.headers.get("Host") != s.host
                or self.headers.get("Sec-Fetch-Dest", "document") != "document"
                or not same(got.get("state"), s.state)):
            return self._send(404)
        try:  # a field given twice is no hand-off: {} is a miss, never the last one read
            s.outcome, tail = s.finish(got if len(got) == len(pairs) else {}), ""
        except Exception as e:  # every miss is one line, and the browser is told the truth
            s.outcome = e if isinstance(e, Failed) else Failed(FAILED)
            tail = "?nowhere=1" if s.outcome.args[0] == NOWHERE else "?failed=1"
        self._send(302, f"{s.site}/connect/cli/done{tail}")

    def _send(self, status: int, location: str | None = None) -> None:
        self.send_response(status)
        if location:
            self.send_header("Location", location)
        self.send_header("Content-Length", "0")
        self.send_header("Cache-Control", "no-store")
        self.end_headers()

    def send_error(self, code: int, *args: Any) -> None:
        self._send(404)  # never stdlib's error page: a POST, a HEAD, a bad request get the 404

    def log_message(self, *args: Any) -> None:
        pass  # the request line carries the code: nothing is logged


def login(home: Path, issuer: str, *, port: int = PORT, paste: bool = False,
          browser: bool = True) -> dict[str, Any]:
    """Protocol 1-7: the record kept, or `Failed`."""
    if not _at_terminal():
        from egzos.authz.presence import is_terminal

        with contextlib.suppress(Exception):  # the CLI prints it on output: a pipe or a file here,
            if not is_terminal() and sys.stderr.isatty():  # so the screen is told as well
                print(NO_TERMINAL, file=sys.stderr)
        raise Failed(NO_TERMINAL, 2)
    try:
        record, refresh = _hand_off(issuer, port=port, paste=paste, browser=browser)
    except BaseException:  # what is left of a refused paste is no command for the shell either
        _drop_typed_ahead()
        raise
    if not _yes(record):  # nothing before _keep touches what an earlier sign-in kept
        raise Failed(NOT_KEPT)
    return _keep(home, record, refresh)


def _hand_off(issuer: str, *, port: int, paste: bool, browser: bool) -> tuple[dict[str, Any], Any]:
    """Protocol 1-6: who and where, and the refresh token, checked; the listener is closed on
    return, so the browser has had its 302 before 7 asks."""
    site, srv = _site(), None
    verifier, state = secrets.token_urlsafe(48), secrets.token_urlsafe(32)
    if not paste:
        try:
            srv = HTTPServer(("127.0.0.1", port), _Callback)
        except OSError:  # taken, or no loopback here: the paste path
            print(f"cannot use port {port} — the page will show a code to paste", file=sys.stderr)
    try:
        s256 = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).rstrip(b"=")
        where = {"port": srv.server_address[1]} if srv else {"paste": 1}
        url = f"{site}/connect/cli?" + urlencode(
            {"challenge": s256.decode(), "state": state, **where})
        print(f"matching code {matching_code(state)} — any code the page shows must be this one",
              file=sys.stderr)
        if not (browser and _open(url)):  # stderr: under --json, stdout carries the one payload
            here = " on this machine (none here? Ctrl-C, then `egzos login --paste`)" if srv else ""
            print(f"open this in a browser{here}:\n  {url}", file=sys.stderr)
        if srv is None:
            print("paste the code the page shows:", file=sys.stderr)
            raw = _read().removesuffix(b"\n").removesuffix(b"\r")  # Enter, or Windows' too
            if len(raw) >= 2048 or b"\n" in raw or b"\r" in raw:  # no page's token: refused
                raise Failed(NOT_YOURS)  # whole, so nothing of it is a paste or 7's answer
            line = raw.decode("ascii", "replace")
            if not same((got := _pasted(line)).get("state"), state):
                raise Failed(NOT_YOURS if line.strip() else STOPPED)
            return _finish(got, issuer=issuer, site=site, verifier=verifier)
        srv.finish = lambda got: _finish(got, issuer=issuer, site=site, verifier=verifier)
        srv.state, srv.site, srv.timeout, srv.outcome = state, site, 0.5, None
        srv.host = f"127.0.0.1:{srv.server_address[1]}"
        srv.handle_error = lambda *args: None  # a browser that hung up prints no traceback
        deadline = time.monotonic() + WAIT_SECONDS
        while srv.outcome is None and time.monotonic() < deadline:
            srv.handle_request()
        if not isinstance(srv.outcome, tuple):
            raise srv.outcome or Failed(LATE)
        return srv.outcome
    finally:
        if srv:
            srv.server_close()  # before 7 asks: no request is read while the terminal waits


def _finish(got: dict[str, str], *, issuer: str, site: str,
            verifier: str) -> tuple[dict[str, Any], Any]:
    """Protocol 5 and 6, for a hand-off that carries this terminal's state: the record and, apart
    from it (the record is printed), the refresh token. Nothing is kept here."""
    if got.keys() == {"state", "nowhere"} and got["nowhere"] == "1":
        raise Failed(NOWHERE)
    try:  # each as the door holds it (identity.md §2): https, or http on a loopback host
        origin, client_id = (validate(f"identity.{k}", got.get(k)) for k in ("origin", "client_id"))
    except ConfigError:
        raise Failed(FAILED) from None
    if got.keys() != HANDED or got["issuer"] != issuer or not got["code"]:  # validate held the rest
        raise Failed(FAILED)  # before any request: the code is never spent at another issuer
    tokens = _request(f"{issuer.rstrip('/')}/oauth/token", {
        "grant_type": "authorization_code", "code": got["code"], "client_id": client_id,
        "redirect_uri": site + CALLBACK, "code_verifier": verifier}) or {}
    try:  # read, not verified: the terminal is not the resource server; the container checks
        # the signature on every request (identity.md §3)
        claims = jwt.decode(tokens.get("access_token"), options={"verify_signature": False})
        sub, exp = provider_id(claims.get("sub")), claims.get("exp")
    except (jwt.PyJWTError, ValueError):
        raise Failed(FAILED) from None
    if (claims.get("iss") != issuer or claims.get("client_id") != client_id
            or not isinstance(exp, int | float) or not time.time() < exp < 2**40):
        raise Failed(FAILED)  # past, NaN, or beyond any date written below: not a token's exp
    meta = _request(origin + METADATA) or {}
    servers = meta.get("authorization_servers")  # a list: `in` on a string would match a part
    if meta.get("resource") != origin or not isinstance(servers, list) or issuer not in servers:
        raise Failed(FAILED)
    try:  # 7 shows it: a space or a hidden character could make another account read as yours
        email = provider_id(claims.get("email"))
    except ValueError:  # so it is held as absent, and the sub is shown
        email = None
    return {
        "origin": origin, "client_id": client_id, "issuer": issuer, "sub": sub, "email": email,
        "access_expires_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(exp)),
    }, tokens.get("refresh_token")


def account(record: dict[str, Any]) -> str:
    """The account as 7 shows it, and the CLI's line after the yes: the email an id's rule holds,
    else the sub. It is the one value from the token a person judges, so past ASCII each character
    shows as its escape: a look-alike letter cannot pass for one in their own address."""
    return (record["email"] or record["sub"]).encode("ascii", "backslashreplace").decode()


def _yes(record: dict[str, Any]) -> bool:
    """Protocol 7's question and the one line read for it, after the drop: True for y or yes, in
    any case, with spaces or tabs around it, alone on a line the person ended with Enter."""
    print(f"account  {account(record)}\ncloud    {record['origin']}\n{ASK}", end="",
          file=sys.stderr, flush=True)
    line = b""
    try:  # a drop that failed reads no line: a y typed ahead could still be there
        line = _read() if _drop_typed_ahead() else b""
    finally:  # after Ctrl-C or end of input, the next line starts on its own
        if not line.endswith(b"\n"):
            print(file=sys.stderr)
    said = line.removesuffix(b"\n").removesuffix(b"\r")  # Enter, or Windows' too
    whole = line.endswith(b"\n") and b"\n" not in said and b"\r" not in said  # one line, ended
    # as bytes, only ASCII y and yes: casefold would read "ye\u017f" as "yes"
    return whole and said.strip(b" \t").lower() in (b"y", b"yes")


def _drop_typed_ahead() -> bool:
    """Keys pressed before 7's question showed are no answer to it: a stray Enter, a y typed while
    the browser was open, a second line in a paste. Dropped, as readpassphrase(3) drops them; False
    when they could not be, and 7 then keeps nothing."""
    with contextlib.suppress(Exception):  # no terminal driver behind standard input: no drop
        if sys.platform == "win32":
            import msvcrt

            while msvcrt.kbhit():
                msvcrt.getwch()
        else:
            import termios

            termios.tcflush(sys.stdin.fileno(), termios.TCIFLUSH)
        return True
    return False


# -- where the sign-in is kept (identity.md §8) --------------------------------------------------
def _vault(account: str, secret: str | None) -> bool:
    """The token into the OS store, or out (None): True when the store then reads back exactly that.
    One ranked below 1 (fail, null, keyrings.alt's files; a chainer, by its first) keeps nothing."""
    try:
        import keyring  # MIT, maintained (v0.7 §R); here, so no other command pays to find a store

        store = keyring.get_keyring()
        store = next((b for b in getattr(store, "backends", [store]) if b.priority >= 1), None)
        if store is None:
            return secret is None
        if secret is None:
            with contextlib.suppress(Exception):  # one not there raises: the read below decides
                store.delete_password(SERVICE, account)
        else:
            store.set_password(SERVICE, account, secret)
        return store.get_password(SERVICE, account) == secret
    except Exception:  # absent, locked, no D-Bus: the file
        return False


def _write(path: Path, text: str) -> None:
    """0600 from the first byte, and replaced whole."""
    tmp = path.with_name(f".{path.name}.{secrets.token_hex(8)}")
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    try:
        with os.fdopen(fd, "w") as fh:
            fh.write(text)
        os.replace(tmp, path)
    finally:
        tmp.unlink(missing_ok=True)


def _keep(home: Path, record: dict[str, Any], refresh: Any) -> dict[str, Any]:
    """Protocol 7, after the yes; a failure here keeps no sign-in the store lets it delete."""
    refresh = refresh if isinstance(refresh, str) and refresh else None
    account, secret, path = f"login:{home.resolve()}", home / SECRET, home / RECORD
    try:
        where = None if refresh is None else "keyring" if _vault(account, refresh) else "file"
        if where == "file":
            _write(secret, refresh)
        else:
            secret.unlink(missing_ok=True)
        if where != "keyring":
            _vault(account, None)  # an earlier sign-in's token goes, where the store lets it
        record = {**record, "refresh": where}
        _write(path, json.dumps(record))
    except BaseException:
        _vault(account, None)
        secret.unlink(missing_ok=True)
        path.unlink(missing_ok=True)
        raise
    return record
