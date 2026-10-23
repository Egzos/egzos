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

import contextlib
import hashlib
import hmac
import os
import secrets
import time
from collections.abc import Callable
from contextlib import AbstractContextManager, nullcontext
from pathlib import Path
from typing import Any

from egzos._types import AS_THROTTLE_RATES, AS_THROTTLE_WINDOW_SECONDS, ThrottleState
from egzos.ledger import Ledger

SURFACE = "rest"
RATE = AS_THROTTLE_RATES[SURFACE]
WINDOW_SECONDS = AS_THROTTLE_WINDOW_SECONDS
GLOBAL = "g"
#: How long a closed window's counters are kept after it closes: an hour. Older rows are forgotten,
#: so a sweep from many addresses cannot grow the table without bound.
KEEP_WINDOWS = 12
KEY_FILE = "throttle.key"
KEY_BYTES = 32
#: How many key names a container tries, `throttle.key` first, passing over short ones.
KEY_SLOTS = 4

_REFUSED = "!refused"
_ADMITTED_401 = "!401"
_CLOSED = "!closed"


def throttle_key(home: Path) -> bytes:
    """The per-container secret behind every `window_key` and source bucket: 32 bytes, 0600,
    created once. It is written whole to a private file and linked into place, first writer wins,
    so no reader ever sees a half-written key. A key file is never rewritten: a short one, left
    by a crash under earlier code, is passed over for the next name, which every process reaches
    the same way, so every process reads the same key. Should all `KEY_SLOTS` names be short, it
    raises and the door does not start: it fails closed, never on an empty key."""
    for slot in range(KEY_SLOTS):
        path = Path(home) / (KEY_FILE if slot == 0 else f"{KEY_FILE}.{slot}")
        try:
            data = path.read_bytes()
        except FileNotFoundError:
            data = _create(path)
        if len(data) == KEY_BYTES:
            return data
    raise RuntimeError("the throttle key cannot be read")


def _create(path: Path) -> bytes:
    """Link a whole new key at `path` unless another process got there first; either way, return
    the key that is there now."""
    tmp = path.with_name(f".{KEY_FILE}.{secrets.token_hex(8)}")
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    try:
        with os.fdopen(fd, "wb") as fh:
            fh.write(secrets.token_bytes(KEY_BYTES))
            fh.flush()
            os.fsync(fh.fileno())
        with contextlib.suppress(FileExistsError):
            os.link(tmp, path)
    finally:
        with contextlib.suppress(FileNotFoundError):
            os.unlink(tmp)
    return path.read_bytes()


class Throttle:
    def __init__(
        self,
        state: ThrottleState,
        ledger: Ledger,
        key: bytes,
        *,
        clock: Callable[[], float] = time.time,
        atomic: Callable[[], AbstractContextManager[Any]] = nullcontext,
    ):
        self.state = state
        self.ledger = ledger
        self._key = key
        self._clock = clock
        # A window's claim and its entries are one transaction: an append that fails rolls the
        # claim back, so the next pass closes the window again and its record is never lost.
        self._atomic = atomic

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
        """Append the releases and the tally of every closed window not yet closed, however long
        ago it closed, then forget the counters of windows closed more than `KEEP_WINDOWS` ago.
        Safe from any process at any time: one claim per window, so each appends once."""
        current = self._window()
        for key in self.state.throttle_windows(SURFACE):
            try:
                w = int(key)
            except ValueError:
                continue
            if w >= current:
                continue
            if not self.state.throttle_count(SURFACE, _CLOSED, key):
                with self._atomic():
                    # The claim and the entries land together: a failed append rolls the claim
                    # back, and the next pass closes the window again (a6 on #288).
                    if self.state.throttle_incr(SURFACE, _CLOSED, key) == 1:
                        self._close(w)
            if w < current - KEEP_WINDOWS:
                self.state.throttle_forget(SURFACE, key)

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
