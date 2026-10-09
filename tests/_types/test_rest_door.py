# Copyright 2026 Ali Sasanian
# SPDX-License-Identifier: Apache-2.0
"""
The REST door's answers from the Chief on #165, pinned: `rest.md` §6's grant lifetime.

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
