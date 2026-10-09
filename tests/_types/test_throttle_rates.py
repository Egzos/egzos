# Copyright 2026 Ali Sasanian
# SPDX-License-Identifier: Apache-2.0
"""
The throttle rates, pinned: `authorization-server.md` §11.0's table and `rest.md` §2 item 7 (#141).

`rest` is the Chief's decision; the five AS surfaces are a1p-proposed until the Chief confirms them.
Literals transcribed here on purpose, the way the rest of `tests/_types/**` does: a number that
moves has to move in the contract and here together.
"""

from __future__ import annotations

import pytest

import egzos._types as t


def test_every_surface_counts_over_one_three_hundred_second_window():
    # #141: two buckets per surface over one 300 s window; row (h) and rest.tally at most 288 a day.
    assert t.AS_THROTTLE_WINDOW_SECONDS == 300
    assert 86_400 // t.AS_THROTTLE_WINDOW_SECONDS == 288


def test_every_surface_has_exactly_one_rate_pair():
    assert set(t.AS_THROTTLE_RATES) == set(t.AS_THROTTLE_SURFACES)


def test_rest_rates_are_the_chiefs():
    # The Chief on #141, 2026-10-09: 300 global, 30 per source address, per 300 s.
    assert t.AS_THROTTLE_RATES["rest"] == t.ThrottleRate(container_global=300, per_source=30)


@pytest.mark.parametrize(
    ("surface", "container_global", "per_source"),
    [
        ("login", 30, 5),
        ("device", 30, 5),
        ("tap", 60, 10),
        ("revoke", 120, 20),
        ("authorize", 300, 30),
    ],
)
def test_as_surface_rates_are_a1ps_proposal(surface, container_global, per_source):
    # §11.0's table, a1p-proposed for the Chief to confirm (#141 stays open until then).
    assert t.AS_THROTTLE_RATES[surface] == t.ThrottleRate(container_global, per_source)


def test_login_and_device_are_tightest():
    # The Chief on #141: tightest where the input is password-like or low-entropy.
    tight = {t.AS_THROTTLE_RATES["login"], t.AS_THROTTLE_RATES["device"]}
    for surface, rate in t.AS_THROTTLE_RATES.items():
        for bound in tight:
            assert rate.container_global >= bound.container_global, surface
            assert rate.per_source >= bound.per_source, surface


def test_a_source_cannot_spend_the_whole_global_budget():
    # §11.0: the per-source bucket exists so one noisy source cannot exhaust the global one.
    for surface, rate in t.AS_THROTTLE_RATES.items():
        assert 0 < rate.per_source < rate.container_global, surface


def test_the_rates_are_read_only():
    with pytest.raises(TypeError):
        t.AS_THROTTLE_RATES["login"] = t.ThrottleRate(10_000, 10_000)  # type: ignore[index]


def test_no_rate_is_a_config_key():
    # The rates are contract constants; no container-config field or wire key may loosen one.
    fields = set(t.ContainerConfig.__annotations__)
    wire_keys = set(t.CONTAINER_CONFIG_FIELD_FROM_WIRE_KEY)
    for name in fields | wire_keys:
        assert "throttle" not in name and "rate" not in name, name
