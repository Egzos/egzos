# Copyright 2026 Ali Sasanian
# SPDX-License-Identifier: Apache-2.0
"""
The step-up tap, MVP cut (spec/design/step-up-tap-and-pending-approval.md §2, lifeboat baseline).

A human-only act started from the CLI does not happen on the CLI's say-so: the terminal is where an
agent, or an injected `--yes` / `echo y`, would type. The container opens a one-shot page on
loopback at `/tap/<token>` (an opaque single-use token, no parameters, no-referrer, no-store), shows
what moves and who will see it, and waits for two deliberate presses: *Sign and approve*, then
*Confirm signature* within 10 s. *Deny* is one press. Signing appends `step_up` and opens a window
for that source → destination ring pair (default 300 s; `0` means no window, every act taps).

Residual, named: anything that can drive a browser as the user can press the buttons. What this
removes is the act being completed by typing in a terminal; the page opens in the browser and its
URL is printed only when no browser could be opened.
"""

from __future__ import annotations

import html
import json
import os
import secrets
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


def _now() -> float:
    return time.time()


def _iso(ts: float) -> str:
    return datetime.fromtimestamp(ts, UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


class Presence:
    def __init__(self, container: Container):
        self.c = container
        self.path = container.home / "presence.json"

    # -- windows ----------------------------------------------------------------------------------
    def _windows(self) -> dict[str, float]:
        try:
            return json.loads(self.path.read_text())
        except (OSError, ValueError):
            return {}

    @staticmethod
    def _key(pair: tuple[str, str]) -> str:
        return f"{pair[0]}→{pair[1]}"

    def window_open(self, pair: tuple[str, str]) -> bool:
        return self._windows().get(self._key(pair), 0) > _now()

    def open_window(self, pair: tuple[str, str]) -> float | None:
        seconds = window_seconds()
        if seconds == 0:
            return None
        windows = {k: v for k, v in self._windows().items() if v > _now()}
        closes = _now() + seconds
        windows[self._key(pair)] = closes
        fd = os.open(self.path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        with os.fdopen(fd, "w") as fh:
            fh.write(json.dumps(windows))
        return closes

    # -- the tap ------------------------------------------------------------------------------------
    def require(self, act: dict[str, Any], *, timeout: float | None = None, opener=None) -> str:
        """Ask for presence. Returns "window", "approved", "denied" or "expired"."""
        if timeout is None:
            timeout = float(os.environ.get("EGZOS_TAP_TIMEOUT_SECONDS") or 180)
        pair = (act["from"], act["to"])
        if self.window_open(pair):
            self.c.ledger.append(
                "step_up", actor=OWNER, principal="interactive", subject=act.get("subject"),
                via="window", pair=list(pair),
            )
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
            print("A presence check opened in your browser. Approve or deny it there.", flush=True)
        else:
            print(f"Open this to approve or deny (it works once):\n  {url}", flush=True)
        httpd.timeout = 1.0
        deadline = _now() + timeout
        while tap.outcome is None and _now() < deadline:
            httpd.handle_request()
        httpd.server_close()
        outcome = tap.outcome or "expired"
        if outcome == "approved":
            closes = self.open_window(pair)
            self.c.ledger.append(
                "step_up", actor=OWNER, principal="interactive", subject=act.get("subject"),
                via="tap", pair=list(pair),
                window_closes=_iso(closes) if closes else None,
            )
        return outcome


class Tap:
    """One page, one decision. The token is single-use: after a decision every request is refused."""

    def __init__(self, act: dict[str, Any]):
        self.act = act
        self.token = secrets.token_urlsafe(32)
        self.outcome: str | None = None
        self.armed_until = 0.0

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
        presence = (
            "Approving is a human-only act. Signing proves you are here "
            f"and opens a {seconds // 60 or seconds}-{'minute' if seconds >= 60 else 'second'} "
            f"window for <code>{e(a['from'])} → {e(a['to'])}</code>."
            if seconds
            else "Approving is a human-only act. Signing proves you are here. No window opens."
        )
        act_button = (
            '<button name=step value=confirm class=act>Confirm signature</button>'
            if armed
            else '<button name=step value=arm class=act>Sign and approve</button>'
        )
        return f"""<!doctype html><html lang=en><head><meta charset=utf-8>
<meta name=viewport content="width=device-width,initial-scale=1"><title>egzos · presence</title>
<style>
body{{margin:0;background:#fff;color:#000;font:16px/1.5 "IBM Plex Sans",system-ui,sans-serif}}
@media (prefers-color-scheme:dark){{body{{background:#0B0B0B;color:#F4F4F0}}}}
main{{max-width:720px;margin:32px auto;padding:0 16px}}
.ref{{font-family:"IBM Plex Mono",ui-monospace,monospace;text-transform:uppercase;letter-spacing:.12em;font-size:.8rem}}
.box{{border:2px solid currentColor;padding:16px;margin:16px 0}}
table{{width:100%;border-collapse:collapse}}td{{padding:6px 4px;border-bottom:1px solid #D6D6D2}}
button{{min-height:44px;padding:0 16px;border:2px solid currentColor;background:transparent;color:inherit;font:inherit;cursor:pointer;margin-right:8px}}
button.act{{background:#1D3FA8;color:#fff;border-color:#1D3FA8}}
.note{{border:2px solid #1D3FA8;padding:12px}}
</style></head><body><main>
<p class=ref>{e(a.get('ref', 'act'))} · {e(a.get('filed', ''))}</p>
<h1>{e(a['title'])}</h1>
<p><span class=ref>{e(a.get('requester', 'you'))} states:</span> “{e(a.get('reason') or '(no reason given)')}”</p>
<h2>What moves</h2><table>{rows}</table>
<h2>Who will see it</h2><p>{who}</p>
<div class=box><p>{presence}</p>
{f'<p class=note>{e(note)}</p>' if note else ''}
<form method=post>{act_button}<button name=step value=deny>Deny</button></form></div>
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
                self._send(200, tap.page(armed=tap.armed_until > _now()))

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
                if step == "arm":
                    tap.armed_until = _now() + ARM_SECONDS
                    return self._send(200, tap.page(armed=True, note="Press again within 10 s to sign."))
                if step == "confirm" and tap.armed_until > _now():
                    tap.outcome = "approved"
                    return self._send(200, "<p>Signed. Approved. You can close this tab.</p>")
                tap.armed_until = 0.0
                return self._send(200, tap.page(armed=False, note="Not signed. Press Sign and approve, then Confirm."))

        return Handler
