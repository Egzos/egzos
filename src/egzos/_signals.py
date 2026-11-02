# Copyright 2026 Ali Sasanian
# SPDX-License-Identifier: LicenseRef-PolyForm-Strict-1.0.0
"""How a served door takes SIGTERM (GHSA-wf2m-wg6h-v6wf).

Docker, systemd and Kubernetes stop a process with SIGTERM; a terminal stops it with SIGINT
(Ctrl-C). uvicorn drains on either, then raises the signal again under the handler it found. Under
SIGTERM's default handler that ends the process before `uvicorn.run` returns, so the command never
closes its container (storage.md §3.7). Both doors that run uvicorn, `egzos serve --http` and
`egzos web`, run it inside `sigterm_as_sigint`, so `uvicorn.run` returns on either stop and the
close runs.
"""

from __future__ import annotations

import contextlib
import signal
import threading
from collections.abc import Iterator


@contextlib.contextmanager
def sigterm_as_sigint() -> Iterator[None]:
    """While the block runs, SIGTERM ends it as SIGINT does: KeyboardInterrupt, which `uvicorn.run`
    ends on. Only SIGTERM's default handler is replaced, and only on the main thread, the one that
    takes a signal: an ignored SIGTERM, or a handler set by whatever embeds the door, is left as it
    is. The default is put back however the block ends. A uvicorn that does not raise the signal
    again takes it itself while it serves, so this handler sees only a SIGTERM that lands during
    startup or teardown."""
    if threading.current_thread() is not threading.main_thread():
        yield
        return
    if signal.getsignal(signal.SIGTERM) is not signal.SIG_DFL:
        yield
        return
    try:
        signal.signal(signal.SIGTERM, signal.default_int_handler)
        yield
    finally:
        signal.signal(signal.SIGTERM, signal.SIG_DFL)
