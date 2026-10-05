# Copyright 2026 Ali Sasanian
# SPDX-License-Identifier: Apache-2.0
"""
The lifeboat (`egzos web`), built to spec/design/lifeboat.md §0: server-rendered, in-process with
the container, FastAPI + Jinja + htmx, no JS toolchain, tokens as CSS variables only. The app is
`egzos.web.app`; this module launches it on loopback.

The URL opened at launch carries a per-launch key, and the key works ONCE: the first browser to
open it is handed to this launch's own host, `<random>.localhost`, and gets the session there (an
HttpOnly, host-only cookie, a different value); the key is dead, so a copy read later from the
launcher's argv or a terminal opens nothing. The session lives on the random host because a
browser does not isolate cookies by port: a cookie for 127.0.0.1 would reach every other server
on 127.0.0.1 the owner's browser visits. The label is minted in this process and never printed.
`*.localhost` resolves to loopback in Chromium and Firefox (RFC 6761); the launch output says what
to do when the browser does not (`LOCALHOST_HINT`). The keyed URL is printed only when no
browser was opened AND stdout is a terminal: an agent's shell tool is not a terminal. To reopen
the lifeboat after closing the browser, restart `egzos web`.
`tokens.css` (spec/design/tokens.css, vendored byte-for-byte) lives in this package.
"""

from __future__ import annotations

import secrets
import threading
import time
import webbrowser

from egzos.authz.presence import is_terminal
from egzos.container import Container

DEFAULT_PORT = 7425
# a1r minor on #127: the key is spent once the launch host hands off, so a browser that cannot
# resolve the session host must be told what to do instead of being left on a dead page.
LOCALHOST_HINT = (
    "The session moves to a private *.localhost address. If that page does not load, this "
    "browser does not resolve *.localhost: stop egzos web, run `egzos web --no-open`, and open "
    "the printed link in Chromium or Firefox."
)


def _launch(url: str, open_browser: bool, opener=None, terminal=None) -> bool:
    """Open the browser on the keyed URL; print the key only to a person at a terminal."""
    if open_browser and (opener or webbrowser.open)(url):
        print("Opened in your browser.", flush=True)
        print(LOCALHOST_HINT, flush=True)
        return True
    if terminal if terminal is not None else is_terminal():
        print(f"Open this in your browser (it carries this session's key):\n  {url}", flush=True)
        print(LOCALHOST_HINT, flush=True)
    else:
        print(
            "No browser was opened and this is not a terminal, so the session key is not printed. "
            "Run `egzos web` from a terminal on this machine.",
            flush=True,
        )
    return False


def lifeboat_for(container: Container, port: int):
    """The lifeboat, its app and its launch URL. The launch URL is on 127.0.0.1 and carries only
    the single-use key; the session host's random label never leaves this process except in the
    redirect that hands the redeemed launch to it."""
    from egzos.web.app import Lifeboat, create_app

    label = secrets.token_hex(10)
    boat = Lifeboat(container, host=f"{label}.localhost:{port}", launch_host=f"127.0.0.1:{port}")
    return boat, create_app(boat, f"http://{boat.host}"), f"http://127.0.0.1:{port}/?k={boat.key}"


def serve_web(container: Container, port: int = DEFAULT_PORT, open_browser: bool = True) -> None:
    import uvicorn

    token = container.require_token()
    if token.principal != "interactive":
        raise PermissionError("the lifeboat is the owner's; a client principal cannot open it")
    host = "127.0.0.1"
    _boat, app, url = lifeboat_for(container, port)
    print(f"egzos web on http://{host}:{port} — loopback only. Ctrl-C to stop.", flush=True)

    def launch_when_up() -> None:
        time.sleep(0.5)
        _launch(url, open_browser)

    threading.Thread(target=launch_when_up, daemon=True).start()
    uvicorn.run(app, host=host, port=port, log_level="warning", access_log=False)
