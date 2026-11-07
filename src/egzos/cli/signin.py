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
   or issuer. <site> is SITE; EGZOS_SITE replaces it for tests, a loopback origin only.
2. Matching code: the first six characters of the RFC 4648 base32 (A-Z, 2-7) of the first five
   bytes of SHA-256 over the state's ASCII bytes; state `egzos-test-state` gives `N7XOBA`.
3. Hand-off, loopback. The page navigates its tab (top level: never a fetch, an image or a frame) to
       http://127.0.0.1:<port>/oauth/callback?code=…&state=…&origin=…&client_id=…&issuer=…
   with its record's triple (the cloud container's origin, its client_id, the issuer), or with
   ?state=…&nowhere=1 for a person egzos hosts no container for, ?state=…&error=1 for a flow that
   failed; each field once, no other. The listener takes one GET at that path with its own state and
   Host 127.0.0.1:<port>, exchanges and checks (5, 6), answers with a 302 to <site>/connect/cli/done
   (?nowhere=1, ?failed=1 for any other miss) and stops; until then anything else gets an empty 404.
4. Hand-off, paste (&paste=1 alone: a listening terminal reads none). The page shows one token for
   standard input, <code>.<state>.<triple>, <triple> the unpadded base64url of origin=…&client_id=…
   &issuer=… form-encoded as in 3, or nowhere.<state>, under 1000 characters (macOS: 1024 a line).
5. Exchange, at the pinned issuer alone (the local container's identity.issuer, else ISSUER), which
   a handed issuer must equal: POST <issuer>/oauth/token, form-encoded, as a public client: code,
   grant_type=authorization_code, redirect_uri=<site>/oauth/callback, code_verifier, client_id.
6. Checks, before anything is kept: the access token's `iss` is the pinned issuer and its
   `client_id` claim the handed one, and GET <origin>/.well-known/oauth-protected-resource names
   that issuer in `authorization_servers` and that origin as `resource`. Any miss is one line, and
   nothing is kept. The claims are read unverified: the terminal is not the resource server, and
   the container checks the signature on every request (identity.md §3).
7. Kept: the refresh token in the OS credential store through `keyring` (service `egzos`, account
   `login:<EGZOS_HOME>`), else in SECRET (0600); who and where in RECORD (0600). The access token
   stays in this process. No token is printed, logged, or put in a URL or argv.
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
_STAY = urllib.request.HTTPRedirectHandler()  # every request's: a redirect is an error status,
_STAY.redirect_request = lambda *args: None  # so nothing is ever sent on to where one points

FAILED = "the sign-in did not go through — nothing was kept; run `egzos login` again"
NOWHERE = "nothing to log in to — egzos hosts no cloud for this account"
NOT_YOURS = "that is not the code this terminal's page shows — nothing was kept"
LATE = "no sign-in came back in ten minutes — nothing was kept"
STOPPED = "stopped — nothing was kept"
BAD_SITE = "EGZOS_SITE is for tests: a loopback origin such as http://127.0.0.1:8000, or unset"


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
            line = sys.stdin.readline(2048)
            if not same((got := _pasted(line)).get("state"), state):
                raise Failed(NOT_YOURS if line.strip() else STOPPED)
            return _finish(home, got, issuer=issuer, site=site, verifier=verifier)
        srv.finish = lambda got: _finish(home, got, issuer=issuer, site=site, verifier=verifier)
        srv.state, srv.site, srv.timeout, srv.outcome = state, site, 0.5, None
        srv.host = f"127.0.0.1:{srv.server_address[1]}"
        srv.handle_error = lambda *args: None  # a browser that hung up prints no traceback
        deadline = time.monotonic() + WAIT_SECONDS
        while srv.outcome is None and time.monotonic() < deadline:
            srv.handle_request()
        if not isinstance(srv.outcome, dict):
            raise srv.outcome or Failed(LATE)
        return srv.outcome
    finally:
        if srv:
            srv.server_close()


def _finish(home: Path, got: dict[str, str], *, issuer: str, site: str,
            verifier: str) -> dict[str, Any]:
    """Protocol 5-7, for a hand-off that carries this terminal's state."""
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
    return _keep(home, {
        "origin": origin, "client_id": client_id, "issuer": issuer, "sub": sub,
        "email": claims["email"] if isinstance(claims.get("email"), str) else None,
        "access_expires_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(exp))},
        tokens.get("refresh_token"))


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
    """Protocol 7, after the checks; a failure here keeps no sign-in the store lets it delete."""
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
