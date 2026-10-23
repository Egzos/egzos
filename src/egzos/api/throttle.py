# Copyright 2026 Ali Sasanian
# SPDX-License-Identifier: LicenseRef-PolyForm-Strict-1.0.0
"""
The REST door's throttle (rest.md §2 item 7), on its own surface word, `rest`.

What counts is what a sweep looks like: every `401` the door answers, and every attempt refused
while a bucket holds. Two buckets, both enforced: one container-global, one keyed on the transport
source address (never on a value the caller supplies). A bucket that reaches its rate holds until
its window closes, and while either holds every request gets the route's uniform failure, counted
and not evaluated, a live token included (owner lockout is accepted, the Chief on #141).

No attempt appends an entry. When a window closes, each bucket that engaged appends `authz.release`
(`refused`, `refused: 0` included), and the container-global window that admitted any `401` appends
`rest.tally`. Both carry `principal: none` and `actor: rest`, and a `window_key` derived from the
bucket under a per-container secret: it pairs a release with its tally, rotates with the window,
and never discloses the bucket's key — a source address never reaches the chain.
"""

from __future__ import annotations

import hashlib
import hmac
import os
import secrets
import time
from collections.abc import Callable
from pathlib import Path

from egzos._types import AS_THROTTLE_RATES, AS_THROTTLE_WINDOW_SECONDS, ThrottleState
from egzos.ledger import Ledger

SURFACE = "rest"
RATE = AS_THROTTLE_RATES[SURFACE]
WINDOW_SECONDS = AS_THROTTLE_WINDOW_SECONDS
GLOBAL = "g"
#: How many closed windows a close looks back over: a door down for longer than this loses the
#: release of a window that closed while it was down. An hour.
LOOKBACK_WINDOWS = 12

_REFUSED = "!refused"
_ADMITTED_401 = "!401"
_CLOSED = "!closed"


def throttle_key(home: Path) -> bytes:
    """The per-container secret behind every `window_key` and source bucket: created once, 0600."""
    path = Path(home) / "throttle.key"
    try:
        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    except FileExistsError:
        return path.read_bytes()
    with os.fdopen(fd, "wb") as fh:
        fh.write(secrets.token_bytes(32))
    return path.read_bytes()


class Throttle:
    def __init__(
        self,
        state: ThrottleState,
        ledger: Ledger,
        key: bytes,
        *,
        clock: Callable[[], float] = time.time,
    ):
        self.state = state
        self.ledger = ledger
        self._key = key
        self._clock = clock

    def _window(self) -> int:
        return int(self._clock() // WINDOW_SECONDS)

    def _digest(self, value: str) -> str:
        raw = value.encode("utf-8", "surrogatepass")
        return hmac.new(self._key, raw, hashlib.sha256).hexdigest()

    def _source(self, address: str | None) -> str:
        return "s:" + self._digest(f"source|{address or '-'}")[:32]

    def window_key(self, bucket: str, window: int) -> str:
        return self._digest(f"window|{bucket}|{window}")[:16]

    # -- per request ------------------------------------------------------------------------------
    def holds(self, address: str | None) -> bool:
        """Whether either bucket holds in this window. Read first, for every request."""
        w = str(self._window())
        return (
            self.state.throttle_count(SURFACE, GLOBAL, w) >= RATE.container_global
            or self.state.throttle_count(SURFACE, self._source(address), w) >= RATE.per_source
        )

    def count(self, address: str | None, *, refused: bool) -> None:
        """One counted attempt: a `401` the door admitted, or an attempt refused while holding."""
        w = str(self._window())
        source = self._source(address)
        for bucket in (GLOBAL, source):
            self.state.throttle_incr(SURFACE, bucket, w)
            if refused:
                self.state.throttle_incr(SURFACE, bucket + _REFUSED, w)
        if not refused:
            self.state.throttle_incr(SURFACE, GLOBAL + _ADMITTED_401, w)

    # -- per window -------------------------------------------------------------------------------
    def close(self) -> None:
        """Append the releases and the tally of every recently closed window not yet closed. Safe
        to call from any process at any time: one claim per window, so each appends once."""
        current = self._window()
        for w in range(current - LOOKBACK_WINDOWS, current):
            key = str(w)
            if self.state.throttle_count(SURFACE, GLOBAL, key) == 0:
                continue
            if self.state.throttle_count(SURFACE, _CLOSED, key):
                continue
            if self.state.throttle_incr(SURFACE, _CLOSED, key) != 1:
                continue  # another closer claimed it first
            self._close(w)

    def _close(self, w: int) -> None:
        counts = dict(self.state.throttle_buckets(SURFACE, str(w)))
        for bucket, total in sorted(counts.items()):
            if "!" in bucket:
                continue
            rate = RATE.container_global if bucket == GLOBAL else RATE.per_source
            if total >= rate:
                self.ledger.append(
                    "authz.release",
                    actor=SURFACE,
                    principal="none",
                    surface=SURFACE,
                    refused=counts.get(bucket + _REFUSED, 0),
                    window_key=self.window_key(bucket, w),
                )
        admitted = counts.get(GLOBAL + _ADMITTED_401, 0)
        if admitted:
            self.ledger.append(
                "rest.tally",
                actor=SURFACE,
                principal="none",
                unauthorized=admitted,
                forged=0,
                window_key=self.window_key(GLOBAL, w),
            )
