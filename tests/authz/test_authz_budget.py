# Copyright 2026 Ali Sasanian
# SPDX-License-Identifier: LicenseRef-PolyForm-Strict-1.0.0
"""One time budget per response, §5.3 clause 2, §7.1 and §9.2 (authz/budget.py)."""

from __future__ import annotations

import math
from typing import Any

import pytest

from egzos.authz import budget


class Clock:
    """A monotonic clock the test moves by hand, and a `sleep` that moves it."""

    def __init__(self, at: float = 100.0) -> None:
        self.at = at
        self.slept: list[float] = []

    def __call__(self) -> float:
        return self.at

    def sleep(self, seconds: float) -> None:
        self.slept.append(seconds)
        self.at += seconds


def _budget(clock: Clock, seconds: float = budget.BUDGET_SECONDS) -> budget.Budget:
    return budget.Budget(seconds, clock=clock, sleep=clock.sleep)


def test_the_floor_is_one_named_positive_constant() -> None:
    assert isinstance(budget.BUDGET_SECONDS, float)
    assert 0 < budget.BUDGET_SECONDS < 1


@pytest.mark.parametrize("work", [0.0, 0.001, 0.05, 0.2499])
def test_every_path_under_the_floor_is_sent_at_the_floor(work: float) -> None:
    clock = Clock()
    b = _budget(clock)
    clock.at += work
    b.settle()
    assert clock.at == pytest.approx(100.0 + budget.BUDGET_SECONDS)


def test_a_fast_and_a_slow_path_end_together() -> None:
    # The registry read present or absent, the append made or not: one finish time.
    ends = []
    for work in (0.0004, 0.19):
        clock = Clock()
        b = _budget(clock)
        clock.at += work
        b.settle()
        ends.append(clock.at)
    assert ends[0] == pytest.approx(ends[1])


@pytest.mark.parametrize(("work", "steps"), [(0.25, 1), (0.26, 2), (0.6, 3), (1.0, 4)])
def test_an_overrun_is_padded_to_the_next_whole_step(work: float, steps: int) -> None:
    clock = Clock()
    b = _budget(clock)
    clock.at += work
    b.settle()
    assert clock.at == pytest.approx(100.0 + steps * budget.BUDGET_SECONDS)


def test_settle_does_not_sleep_on_a_step_boundary() -> None:
    clock = Clock()
    b = _budget(clock, 0.5)
    clock.at += 1.0
    b.settle()
    assert clock.slept == []


def test_remaining_is_never_negative_and_a_clock_behind_the_start_counts_as_none_elapsed() -> None:
    clock = Clock()
    b = _budget(clock)
    clock.at -= 5.0
    assert b.remaining() == pytest.approx(budget.BUDGET_SECONDS)
    clock.at += 5.0 + budget.BUDGET_SECONDS
    assert b.remaining() == 0.0


def test_remaining_does_not_sleep() -> None:
    clock = Clock()
    b = _budget(clock)
    assert b.remaining() == pytest.approx(budget.BUDGET_SECONDS)
    assert clock.slept == []


def test_the_default_clock_is_monotonic_and_settle_really_waits() -> None:
    b = budget.Budget(0.01)
    b.settle()
    assert b.remaining() == pytest.approx(0.01, abs=0.01)


@pytest.mark.parametrize("seconds", [0, -1, math.inf, math.nan])
def test_a_budget_that_is_not_positive_and_finite_is_refused(seconds: float) -> None:
    with pytest.raises(ValueError):
        budget.Budget(seconds)


@pytest.mark.parametrize("seconds", ["0.25", None, True])
def test_a_budget_that_is_not_a_number_is_refused(seconds: Any) -> None:
    with pytest.raises(TypeError):
        budget.Budget(seconds)
