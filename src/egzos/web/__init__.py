# Copyright 2026 Ali Sasanian
# SPDX-License-Identifier: Apache-2.0
"""
The lifeboat (`egzos web`), built to spec/design/lifeboat.md §0: server-rendered, in-process with
the container, FastAPI + Jinja + htmx, no JS toolchain, tokens as CSS variables only. The app is
`egzos.web.app`; this module launches it on loopback.

The URL opened at launch carries a per-launch key, and the key works ONCE: the first browser to
open it gets the session (an HttpOnly cookie, a different value) and the key is dead, so a copy
read later from the launcher's argv or a terminal opens nothing. It is printed only when no
browser was opened AND stdout is a terminal: an agent's shell tool is not a terminal. To reopen
the lifeboat after closing the browser, restart `egzos web`.
`tokens.css` (spec/design/tokens.css, vendored byte-for-byte) lives in this package.
"""

from __future__ import annotations

import threading
import time
import webbrowser

from egzos.authz.presence import is_terminal
from egzos.container import Container

DEFAULT_PORT = 7425


def _launch(url: str, open_browser: bool, opener=None, terminal=None) -> bool:
    """Open the browser on the keyed URL; print the key only to a person at a terminal."""
    if open_browser and (opener or webbrowser.open)(url):
        print("Opened in your browser.", flush=True)
        return True
    if terminal if terminal is not None else is_terminal():
        print(f"Open this in your browser (it carries this session's key):\n  {url}", flush=True)
    else:
        print(
            "No browser was opened and this is not a terminal, so the session key is not printed. "
            "Run `egzos web` from a terminal on this machine.",
            flush=True,
        )
    return False


def serve_web(container: Container, port: int = DEFAULT_PORT, open_browser: bool = True) -> None:
    import uvicorn

    from egzos.web.app import Lifeboat, create_app

    token = container.require_token()
    if token.principal != "interactive":
        raise PermissionError("the lifeboat is the owner's; a client principal cannot open it")
    host = "127.0.0.1"
    boat = Lifeboat(container, host=f"{host}:{port}")
    app = create_app(boat, f"http://{host}:{port}")
    url = f"http://{host}:{port}/?k={boat.key}"
    print(f"egzos web on http://{host}:{port} — loopback only. Ctrl-C to stop.", flush=True)

    def launch_when_up() -> None:
        time.sleep(0.5)
        _launch(url, open_browser)

    threading.Thread(target=launch_when_up, daemon=True).start()
    uvicorn.run(app, host=host, port=port, log_level="warning", access_log=False)
