# Copyright 2026 Ali Sasanian
# SPDX-License-Identifier: LicenseRef-PolyForm-Strict-1.0.0
"""
The REST door's throttle (rest.md §2 item 7), on its own surface word, `rest`.

What counts is what a sweep looks like: every `401` the door answers, every grant redemption whose
descriptor does not verify (§6 checks 1–2, "forged"), and every attempt refused while a bucket
holds. Two buckets, both enforced: one container-global, one keyed on the transport source address
(never on a value the caller supplies). A bucket that reaches its rate holds until its window
closes, and while either holds every request gets the route's uniform failure, counted and not
evaluated, a live token included (owner lockout is accepted, the Chief on #141). A third bucket,
keyed on the token a verified descriptor names, counts only that descriptor's refusals at §6's
check 3 or later, so one held grant's replays are bounded without spending anyone else's.

No attempt appends an entry. When a window closes, each bucket that engaged appends `authz.release`
(`refused`, `refused: 0` included), and the container-global window that admitted any `401` or
forged redemption appends `rest.tally`. Both carry `principal: none` and `actor: rest`, and a
`window_key` derived from the bucket under a per-container secret: it pairs a release with its
tally, rotates with the window, and never discloses the bucket's key — a source address never
reaches the chain.
"""

from __future__ import annotations

import hashlib
import hmac
import time
from collections.abc import Callable
from contextlib import AbstractContextManager, nullcontext
from pathlib import Path
from typing import Any

from egzos._types import AS_THROTTLE_RATES, AS_THROTTLE_WINDOW_SECONDS, ThrottleState
from egzos.keys import KEY_BYTES, KEY_SLOTS, container_key
from egzos.ledger import Ledger

SURFACE = "rest"
RATE = AS_THROTTLE_RATES[SURFACE]
WINDOW_SECONDS = AS_THROTTLE_WINDOW_SECONDS
#: rest.md §2 item 7's per-token bucket: verified-descriptor refusals one token may make per window.
#: a1p's figure, the per-source rate, until the Chief sets it on #141.
PER_TOKEN = RATE.per_source
GLOBAL = "g"
#: How long a closed window's counters are kept after it closes: an hour. Older rows are forgotten,
#: so a sweep from many addresses cannot grow the table without bound.
KEEP_WINDOWS = 12
KEY_FILE = "throttle.key"
__all__ = ["KEY_BYTES", "KEY_SLOTS", "Throttle", "throttle_key"]

_REFUSED = "!refused"
_ADMITTED_401 = "!401"
_FORGED = "!forged"
_CLOSED = "!closed"


def throttle_key(home: Path) -> bytes:
    """The per-container secret behind every `window_key` and source bucket (`egzos.keys`)."""
    return container_key(home, KEY_FILE)


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

    def _token(self, token_id: str) -> str:
        return "t:" + self._digest(f"token|{token_id}")[:32]

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

    def count(self, address: str | None, *, refused: bool, forged: bool = False) -> None:
        """One counted attempt: a `401` the door admitted, a forged redemption it admitted, or an
        attempt refused while holding."""
        w = str(self._window())
        source = self._source(address)
        for bucket in (GLOBAL, source):
            self.state.throttle_incr(SURFACE, bucket, w)
            if refused:
                self.state.throttle_incr(SURFACE, bucket + _REFUSED, w)
        if not refused:
            self.state.throttle_incr(SURFACE, GLOBAL + (_FORGED if forged else _ADMITTED_401), w)

    def holds_token(self, token_id: str) -> bool:
        """Whether the per-token bucket of the token a verified descriptor names holds."""
        w = str(self._window())
        return self.state.throttle_count(SURFACE, self._token(token_id), w) >= PER_TOKEN

    def count_token(self, token_id: str, *, refused: bool) -> None:
        """One verified-descriptor refusal, or one attempt refused while its token's bucket held."""
        w = str(self._window())
        bucket = self._token(token_id)
        self.state.throttle_incr(SURFACE, bucket, w)
        if refused:
            self.state.throttle_incr(SURFACE, bucket + _REFUSED, w)

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
            rate = (RATE.container_global if bucket == GLOBAL
                    else PER_TOKEN if bucket.startswith("t:") else RATE.per_source)
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
        forged = counts.get(GLOBAL + _FORGED, 0)
        if admitted or forged:
            self.ledger.append(
                "rest.tally",
                actor=SURFACE,
                principal="none",
                unauthorized=admitted,
                forged=forged,
                window_key=self.window_key(GLOBAL, w),
            )
