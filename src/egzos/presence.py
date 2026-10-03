# Copyright 2026 Ali Sasanian
# SPDX-License-Identifier: Apache-2.0
"""
The step-up tap, MVP cut (spec/design/step-up-tap-and-pending-approval.md §2, lifeboat baseline).

A human-only act started from the CLI does not happen on the CLI's say-so: the terminal is where an
agent, or an injected `--yes` / `echo y`, would type. The container opens a one-shot page on
loopback at `/tap/<token>` (an opaque single-use token, no parameters, no-referrer, no-store), shows
what moves and who will see it, and waits for a decision: *Sign and approve* then *Confirm
signature* within 10 s, *Approve without a window* then the same confirm, or *Deny* (one press).
The lifeboat's own approve acts use the same rule (`web/`), so neither surface completes on one
request.

Every presence check is one `step_up` entry, whatever its outcome (`approved`, `denied`, `expired`,
`unavailable`, or `window` when an open window covered it), with the source → destination ring pair.
A signature opens a window for that ring pair (`step_up.window_seconds`, default 300 s; `0` means
no window, every act taps). The window is read back from the chain, never from a side file, and
*Close window now* (`egzos trust close-window`) appends the entry that ends every open window.

The page opens in the browser. Its URL is printed only when no browser could be opened AND stdout is
a terminal: an agent's shell tool is not a terminal, so it never receives a URL it could press.

Residuals, named: a process running as the user that drives a browser, fakes a terminal, or appends
to the chain directly can do what the user can — a shell running as the user is the user. The URL
travels in the browser launcher's argv, readable by other local users on a shared host. The window
is not yet bounded to the manifest's shape (K items of kinds …). OS-backed presence (WebAuthn /
platform authenticator) is the stronger tier the spec names for later.
"""

from __future__ import annotations

import html
import os
import secrets
import sys
import threading
import time
import webbrowser
from datetime import UTC, datetime
from http.server import BaseHTTPRequestHandler, HTTPServer
from typing import Any
from urllib.parse import parse_qs

from egzos.container import OWNER, Container

DEFAULT_WINDOW_SECONDS = 300
ARM_SECONDS = 10


def window_seconds() -> int:
    """`step_up.window_seconds` (container.md §8). `0` is a value: no window, every act taps."""
    raw = os.environ.get("EGZOS_STEP_UP_WINDOW_SECONDS")
    if raw is None or raw == "":
        return DEFAULT_WINDOW_SECONDS
    return max(0, int(raw))


def is_terminal() -> bool:
    """Whether a printed URL would reach a person at a terminal rather than a program's pipe."""
    try:
        return sys.stdout.isatty()
    except (AttributeError, ValueError):
        return False


def _now() -> float:
    return time.time()


def _iso(ts: float) -> str:
    return datetime.fromtimestamp(ts, UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def arm_deadline() -> float:
    """When a first press made now stops counting as the first of two."""
    return _now() + ARM_SECONDS


def armed(deadline: float) -> bool:
    return deadline > _now()


def pair_of(act: dict[str, Any]) -> tuple[str, str]:
    """The source → destination RING pair (types, not paths) a window is keyed on."""
    pair = act.get("pair") or (act["from"], act["to"])
    return (pair[0], pair[1])


def window_note(seconds: int, frm: str, to: str, esc=html.escape) -> str:
    if not seconds:
        return "Approving is a human-only act. Signing proves you are here. No window opens."
    span = f"{seconds // 60}-minute" if seconds >= 60 else f"{seconds}-second"
    return (
        "Approving is a human-only act. Signing proves you are here and opens a "
        f"{span} window for <code>{esc(frm)} → {esc(to)}</code>. "
        "Close it early at any time: <code>egzos trust close-window</code>."
    )


# The page consumes the design tokens (spec/design/tokens.css, vendored at egzos/web/tokens.css) as
# CSS variables, inlined because the page's CSP loads nothing; the scheme follows tokens.css's own
# rule (data-scheme, else prefers-color-scheme). No literal colour lives here.
TAP_STYLE = """
body{margin:0;background:var(--egz-canvas);color:var(--egz-ink);font-family:var(--egz-font-ui);
 line-height:var(--egz-lh)}
main{max-width:720px;margin:32px auto;padding:0 16px}
.ref{font-family:var(--egz-font-mono);text-transform:uppercase;
 letter-spacing:var(--egz-tracking-caps);font-size:.8rem}
.box{border:var(--egz-bw) solid var(--egz-rule);padding:16px;margin:16px 0}
table{width:100%;border-collapse:collapse}
td{padding:6px 4px;border-bottom:var(--egz-hair) solid var(--egz-rule-soft)}
button{min-height:44px;padding:0 16px;border:var(--egz-bw) solid var(--egz-rule);
 background:var(--egz-canvas);color:var(--egz-ink);font:inherit;cursor:pointer;margin:0 8px 8px 0}
button.act{background:var(--egz-act);color:var(--egz-act-on);border-color:var(--egz-act)}
button.ghost{border-color:transparent;text-decoration:underline}
button:focus-visible{outline:var(--egz-focus);outline-offset:3px}
.note{border:var(--egz-bw) solid var(--egz-act);padding:12px}
"""


def _tokens_css() -> str:
    from importlib import resources

    return resources.files("egzos.web").joinpath("tokens.css").read_text(encoding="utf-8")


class Presence:
    def __init__(self, container: Container):
        self.c = container

    # -- windows, read back from the chain ---------------------------------------------------------
    def _recent_step_ups(self, seconds: int) -> list[dict[str, Any]]:
        """`step_up` entries newer than `seconds` ago, newest first. Pages back through the tail
        until it is older than that, so a busy chain cannot hide a window or a close."""
        since = _iso(_now() - seconds - 1)
        n = 256
        while True:
            rows = self.c.ledger.tail(n)
            if len(rows) < n or not rows or rows[0]["ts"] < since:
                break
            n *= 4
        return [r for r in reversed(rows) if r["ts"] >= since and r["event"] == "step_up"]

    def window_open(self, pair: tuple[str, str]) -> bool:
        seconds = window_seconds()
        if seconds == 0:
            return False
        now = _iso(_now())
        for e in self._recent_step_ups(seconds):
            d = e.get("details") or {}
            if d.get("outcome") == "closed":
                return False  # Close window now ends every window opened before it
            if (
                d.get("outcome") == "approved"
                and d.get("pair") == list(pair)
                and (d.get("window_closes") or "") > now
            ):
                return True
        return False

    def close_windows(self, *, actor: str = OWNER) -> None:
        self.c.ledger.append(
            "step_up", actor=actor, principal="interactive", via="close", outcome="closed"
        )

    def record(
        self,
        act: dict[str, Any],
        *,
        via: str,
        outcome: str,
        windowed: bool = False,
        actor: str = OWNER,
    ) -> None:
        """One `step_up` per presence check, whatever the outcome."""
        closes = None
        seconds = window_seconds()
        if outcome == "approved" and windowed and seconds:
            closes = _iso(_now() + seconds)
        self.c.ledger.append(
            "step_up",
            actor=actor,
            principal="interactive",
            subject=act.get("subject"),
            via=via,
            outcome=outcome,
            pair=list(pair_of(act)),
            window_closes=closes,
        )

    # -- the tap ----------------------------------------------------------------------------------
    def require(self, act: dict[str, Any], *, timeout: float | None = None, opener=None) -> str:
        """Ask for presence. Returns "window", "approved", "denied", "expired" or "unavailable"."""
        if timeout is None:
            timeout = float(os.environ.get("EGZOS_TAP_TIMEOUT_SECONDS") or 180)
        if self.window_open(pair_of(act)):
            self.record(act, via="window", outcome="window")
            return "window"
        tap = Tap(act)
        httpd = HTTPServer(("127.0.0.1", 0), tap.handler())
        url = f"http://127.0.0.1:{httpd.server_address[1]}/tap/{tap.token}"
        # The opener runs on its own thread: some browsers' launchers wait for the browser, and the
        # page cannot be served until this thread starts answering requests below.
        result: list[bool] = []
        launcher = threading.Thread(
            target=lambda: result.append(bool((opener or webbrowser.open)(url))), daemon=True
        )
        launcher.start()
        launcher.join(2.0)
        opened = result[0] if result else True
        if opened:
            print("A presence check opened in your browser. Decide there.", flush=True)
        elif is_terminal():
            print(f"Open this to decide (it works once):\n  {url}", flush=True)
        else:
            httpd.server_close()
            print(
                "No browser could be opened and this is not a terminal, so the presence check "
                "cannot be shown. Run the command from a terminal on this machine.",
                flush=True,
            )
            self.record(act, via="tap", outcome="unavailable")
            return "unavailable"
        httpd.timeout = 1.0
        deadline = _now() + timeout
        while tap.outcome is None and _now() < deadline:
            httpd.handle_request()
        httpd.server_close()
        outcome = tap.outcome or "expired"
        self.record(act, via="tap", outcome=outcome, windowed=tap.windowed)
        return outcome


class Tap:
    """One page, one decision. The token is single-use: after a decision every request is refused."""

    def __init__(self, act: dict[str, Any]):
        self.act = act
        self.token = secrets.token_urlsafe(32)
        self.outcome: str | None = None
        self.windowed = True
        self.armed_until = 0.0
        self.armed_mode = "window"

    def page(self, armed: bool, note: str = "") -> str:
        a = self.act
        e = lambda v: html.escape(str(v), quote=True)  # noqa: E731
        rows = "".join(
            f"<tr><td>{e(r.get('kind', ''))}</td><td>{e(r.get('title', ''))}</td>"
            f"<td>{e(r.get('trust', ''))}</td></tr>"
            for r in a.get("items", [])
        )
        who = ", ".join(e(w) for w in a.get("audience", [])) or "no one new"
        seconds = window_seconds()
        frm, to = pair_of(a)
        presence = window_note(seconds, frm, to, esc=e)
        if armed:
            acts = "<button name=step value=confirm class=act>Confirm signature</button>"
        else:
            acts = "<button name=step value=arm class=act>Sign and approve</button>"
        acts += "<button name=step value=deny>Deny</button>"
        if seconds and not armed:
            acts += "<button name=step value=arm_once class=ghost>Approve without a window</button>"
        return f"""<!doctype html><html lang=en><head><meta charset=utf-8>
<meta name=viewport content="width=device-width,initial-scale=1"><title>egzos · presence</title>
<style>{_tokens_css()}{TAP_STYLE}</style></head><body><main>
<p class=ref>{e(a.get('ref', 'act'))} · {e(a.get('filed', ''))}</p>
<h1>{e(a['title'])}</h1>
<p><span class=ref>{e(a.get('requester', 'you'))} states:</span> “{e(a.get('reason') or '(no reason given)')}”</p>
<h2>What moves</h2><table>{rows}</table>
<h2>Who will see it</h2><p>{who}</p>
<div class=box><p>{presence}</p>
{f'<p class=note>{e(note)}</p>' if note else ''}
<form method=post>{acts}</form></div>
</main></body></html>"""

    def handler(self):
        tap = self

        class Handler(BaseHTTPRequestHandler):
            server_version = "egzos"
            sys_version = ""

            def log_message(self, *args):
                return

            def _send(self, status: int, body: str) -> None:
                data = body.encode()
                self.send_response(status)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.send_header("Content-Length", str(len(data)))
                self.send_header("Cache-Control", "no-store")
                self.send_header("Referrer-Policy", "no-referrer")
                self.send_header("X-Frame-Options", "DENY")
                self.send_header(
                    "Content-Security-Policy",
                    "default-src 'none'; style-src 'unsafe-inline'; form-action 'self'; "
                    "frame-ancestors 'none'; base-uri 'none'",
                )
                self.end_headers()
                self.wfile.write(data)

            def _ok_path(self) -> bool:
                return (
                    tap.outcome is None
                    and self.path.startswith("/tap/")
                    and secrets.compare_digest(self.path[len("/tap/"):], tap.token)
                )

            def do_GET(self):  # noqa: N802
                if not self._ok_path():
                    return self._send(404, "<p>Nothing here.</p>")
                self._send(200, tap.page(armed=armed(tap.armed_until)))

            def do_POST(self):  # noqa: N802
                if not self._ok_path():
                    return self._send(404, "<p>Nothing here.</p>")
                host = self.headers.get("Host", "")
                origin = self.headers.get("Origin")
                if origin is not None and origin != f"http://{host}":
                    return self._send(403, "<p>Refused.</p>")
                length = min(int(self.headers.get("Content-Length") or 0), 4096)
                step = parse_qs(self.rfile.read(length).decode()).get("step", [""])[0]
                if step == "deny":
                    tap.outcome = "denied"
                    return self._send(200, "<p>Denied. You can close this tab.</p>")
                if step in ("arm", "arm_once"):
                    tap.armed_until = arm_deadline()
                    tap.armed_mode = "once" if step == "arm_once" else "window"
                    return self._send(200, tap.page(armed=True, note="Press again within 10 s to sign."))
                if step == "confirm" and armed(tap.armed_until):
                    tap.windowed = tap.armed_mode == "window"
                    tap.outcome = "approved"
                    return self._send(200, "<p>Signed. Approved. You can close this tab.</p>")
                tap.armed_until = 0.0
                return self._send(200, tap.page(armed=False, note="Not signed. Press Sign and approve, then Confirm."))

        return Handler
