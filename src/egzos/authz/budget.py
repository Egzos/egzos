# Copyright 2026 Ali Sasanian
# SPDX-License-Identifier: LicenseRef-PolyForm-Strict-1.0.0
"""
One time budget per response (authorization-server.md §5.3 clause 2, §7.1, §9.2).

Three surfaces owe responses that converge in time as well as in bytes:

- §5.3 clause 2 (MUST): the pre-trust page, whether or not §11.1's keyed registry read happened,
  and whether or not the attempt appended (§12.1 rule 3's asymmetry).
- §7.1 (MUST): the post-trust `access_denied` for an unknown node, an unreachable one, and the
  owner declining. `reach` answers an unknown id before the coverage walk a known one needs.
- §9.2: the revocation response for an unknown or revoked id, which returns before the digest a
  live one computes.

The router starts a `Budget` when the request arrives, before any read, and settles it after the
work and before it sends the response, on every path of the surface, an exception included. A
response is then sent no earlier than `BUDGET_SECONDS` after the request arrived, whichever path
produced it, so the differences above sit under the floor.

Work that overruns the floor is padded up to the next whole multiple of it. An overrun is then
seen only in steps of `BUDGET_SECONDS`, never as the continuous duration of the slower path.

§5.3 clause 2's third difference (an early `throttled` or `token_presented` exit, a SHOULD) is the
caller's choice of whether to start a `Budget` on that path; this module does not decide it.

The floor is this implementation's choice and no contract value, kept here as one named constant
with no config key, like the throttle rates were before #141. The clock is monotonic, so a wall
clock step neither shortens nor stretches a pad.
"""

from __future__ import annotations

import math
import time
from collections.abc import Callable

#: The floor every padded response is held to, in seconds. It sits well above the slowest path
#: these surfaces take on an ordinary container: one registry read, one ancestor walk, one append.
BUDGET_SECONDS = 0.25


class Budget:
    """A response's time budget, started when the request arrives."""

    def __init__(
        self,
        seconds: float = BUDGET_SECONDS,
        *,
        clock: Callable[[], float] = time.monotonic,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        if not isinstance(seconds, int | float) or isinstance(seconds, bool):
            raise TypeError("Budget needs a number of seconds")
        if not math.isfinite(seconds) or seconds <= 0:
            raise ValueError("Budget needs a positive, finite number of seconds")
        self.seconds = float(seconds)
        self._clock = clock
        self._sleep = sleep
        self._start = clock()

    def remaining(self) -> float:
        """Seconds left until the response may be sent: up to the floor, or, past it, up to the
        next whole multiple of it. Never negative. An async router awaits this instead of
        calling `settle`, which blocks."""
        elapsed = max(self._clock() - self._start, 0.0)
        steps = max(math.ceil(elapsed / self.seconds), 1)
        return max(steps * self.seconds - elapsed, 0.0)

    def settle(self) -> None:
        """Wait out `remaining()`."""
        left = self.remaining()
        if left > 0:
            self._sleep(left)
