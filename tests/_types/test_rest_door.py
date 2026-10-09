# Copyright 2026 Ali Sasanian
# SPDX-License-Identifier: Apache-2.0
"""
The REST door's answers from the Chief on #165, pinned: `rest.md` §6's grant lifetime, and §2's
throttle surface and per-window tally.

Literals transcribed here on purpose, the way the rest of `tests/_types/**` does.
"""

from __future__ import annotations

import egzos._types as t


def test_a_blob_grant_lives_three_hundred_seconds():
    # rest.md §6: a fixed contract lifetime of 300 seconds from the mint (#165 item 1, option (a)).
    assert t.BLOB_GRANT_LIFETIME_SECONDS == 300


def test_the_grant_lifetime_is_not_a_config_key():
    # "The lifetime is not configurable": no container-config field or wire key may carry it.
    fields = set(t.ContainerConfig.__annotations__)
    wire_keys = set(t.CONTAINER_CONFIG_FIELD_FROM_WIRE_KEY)
    for name in fields | wire_keys:
        assert "grant" not in name, f"`{name}` would make the grant lifetime configurable"


def test_the_rest_door_is_its_own_throttle_surface():
    # #165 item 3: one surface word for the 401 sweep and descriptor redemption, never an AS page's.
    assert "rest" in t.AS_THROTTLE_SURFACES
    assert t.AS_THROTTLE_SURFACES.index("rest") == len(t.AS_THROTTLE_SURFACES) - 1


def test_the_rest_tally_is_callerless_and_nothing_else_at_the_door_is():
    # #165 item 2: a descriptor that does not verify names no caller, so its trace is a tally under
    # `principal: none`. A pull or a read at the door still names its token (rest.md §4).
    assert "rest.tally" in t.EVENTS
    assert "rest.tally" in t.PRINCIPAL_NONE_EVENTS
    assert [e for e in t.EVENTS if e.startswith("rest.")] == ["rest.tally"]
    for attributed in ("blob.pull", "blob.grant", "context.fetch"):
        assert attributed not in t.PRINCIPAL_NONE_EVENTS
