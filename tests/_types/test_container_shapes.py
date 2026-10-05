# Copyright 2026 Ali Sasanian
# SPDX-License-Identifier: Apache-2.0
"""
The container shapes, pinned.

`spec/contracts/container.md` fixes ring rank, the roots, the serving policy and F2's structure
floor. Each is a number or mapping that other clauses read — ring rank is compared by the gate, the
serving policy decides what leaves the container — so a silent edit changes behaviour no other test
would notice. The expected values are transcribed from `chief/walking-skeleton` (`model.py`), the
source the contract was drafted from, and are written out rather than derived from the module under
test: a test that asks the code what it contains cannot notice the code changing.
"""

from __future__ import annotations

from typing import is_typeddict

import pytest

import egzos._types as t

# `model.CONTAINER_TYPES`, verbatim — declaration order IS ring rank.
RING_RANK = {
    "inbox": 0,
    "thread": 1,
    "project": 2,
    "team": 3,
    "org": 4,
    "exo": 5,
    "uxo": 6,
    "global": 7,
}

# `model.SERVING_POLICY`, verbatim — nine entries: eight container types plus the `user` root.
SERVING_POLICY = {
    "inbox": "serve-unverified",
    "thread": "serve-unverified",
    "project": "serve-unverified",
    "team": "verified-only",
    "org": "verified-only",
    "exo": "verified-only",
    "uxo": "verified-only",
    "global": "verified-only",
    "user": "verified-only",
}

# container.md §8's table, one row per entry: the canonical dotted wire key, and the
# `ContainerConfig` field that must hold its value. Transcribed from the contract, not read back
# from the module — a mapping asked what it maps cannot notice itself changing.
CONFIG_WIRE_ROWS = [
    ("chain.personal_root", "chain_personal_root"),
    ("org.policy.sovereign_chain", "org_policy_sovereign_chain"),
    ("node.policy.structure_floor", "node_policy_structure_floor"),
    ("blobs.inline_max_bytes", "blobs_inline_max_bytes"),
    ("blobs.staging_retention_days", "blobs_staging_retention_days"),
    ("step_up.window_seconds", "step_up_window_seconds"),
]

# `model.BASELINE_CREATE` — what the default floor must reproduce (v0.3 §2).
BASELINE_CREATE = {"thread", "project"}
# Types that exist from `init` or are not instantiated at all (container.md §1, §7).
NEVER_CREATED = {"inbox", "global", "uxo"}


def test_ring_ranks_are_exactly_the_skeletons():
    assert t.RING_RANK == RING_RANK
    assert t.CONTAINER_TYPES == tuple(RING_RANK)


def test_enterprise_is_omitted_from_the_vocabulary():
    """v0.5 §A. Absent, not merely unused — a reader expecting it finds the contract's sentence."""
    assert "enterprise" not in t.CONTAINER_TYPES
    assert "enterprise" not in t.RING_RANK


def test_uxo_keeps_its_slot_so_the_ranks_around_it_stay_stable():
    """R11: undefined, never instantiated. Reclaiming 6 would move `global` (container.md §1)."""
    assert t.RING_RANK["uxo"] == 6
    assert t.RING_RANK["global"] == 7


def test_the_personal_root_is_a_root_and_not_a_ring():
    """`user` rides along in every chain and has no ring rank at all (container.md §2)."""
    assert t.ROOT_TYPES == ("user", "global")
    assert "user" not in t.CONTAINER_TYPES
    assert "user" not in t.RING_RANK
    assert "global" in t.RING_RANK  # the other root IS a ring


def test_serving_policy_is_exactly_the_skeletons():
    assert t.SERVING_POLICY == SERVING_POLICY


def test_the_personal_root_is_verified_only():
    """F4. It reaches further than any org scope, so reach implies verification."""
    assert t.SERVING_POLICY["user"] == "verified-only"


def test_serve_unverified_is_exactly_inbox_thread_project():
    served = {k for k, v in t.SERVING_POLICY.items() if v == "serve-unverified"}
    assert served == {"inbox", "thread", "project"}


def test_rules_are_verified_only_where_the_table_says_serve_unverified():
    """The kind invariant OVERRIDES the policy table; it is not a row in it (container.md §4)."""
    assert t.VERIFIED_ONLY_KINDS == frozenset({"rule"})
    assert t.SERVING_POLICY["inbox"] == "serve-unverified"


def test_structure_is_a_floor_and_not_a_seventh_capability():
    """F2 — the clause that keeps `token ls` six columns wide."""
    assert t.STRUCTURE_FLOORS == ("thread", "project", "team", "org", "exo")
    assert "structure" not in t.CAPABILITIES
    assert len(t.CAPABILITIES) == 6


def test_the_default_floor_reproduces_the_baseline_sentence():
    """Default floor `project`: at or below is baseline, strictly above needs `admin` (v0.3 §2)."""
    floor = t.CONTAINER_CONFIG_DEFAULTS["node_policy_structure_floor"]
    assert floor == "project"
    baseline = {
        name
        for name, rank in t.RING_RANK.items()
        if rank <= t.RING_RANK[floor] and name not in NEVER_CREATED
    }
    assert baseline == BASELINE_CREATE


def test_container_config_defaults_cover_every_key_and_are_the_skeletons_constants():
    assert set(t.CONTAINER_CONFIG_DEFAULTS) == set(t.ContainerConfig.__annotations__)
    assert t.CONTAINER_CONFIG_DEFAULTS == {
        "chain_personal_root": "between",
        "org_policy_sovereign_chain": "allow",
        "node_policy_structure_floor": "project",
        "blobs_inline_max_bytes": 65536,
        "blobs_staging_retention_days": 30,
        "step_up_window_seconds": 300,
    }


def test_node_and_proposal_are_real_shapes_not_the_provisional_aliases():
    """`storage.md` §3's signatures referenced both before they existed; issue #28 replaced them."""
    assert is_typeddict(t.Node)
    assert is_typeddict(t.Proposal)


def test_resolved_item_is_the_envelope_and_shadowed_by_never_touches_the_item():
    """F10 (container.md §4): `shadowed_by` is a property of the resolution, never of the item.

    The envelope is exactly `{item, layer, layer_type, shadowed_by}`. The item's trust status is
    deliberately NOT restated on it — it has one home, `item["trust"]["status"]`, and a second
    spelling nested outside the first is the copy a resolver could snapshot stale and serve a
    quarantined item under. The last two assertions are what the contract paragraph was written to
    earn: the next hand to add `shadowed_by` to `ContextItem` breaks a running clause here, loudly.
    """
    assert is_typeddict(t.ResolvedItem)
    assert set(t.ResolvedItem.__annotations__) == {"item", "layer", "layer_type", "shadowed_by"}
    assert "trust" not in t.ResolvedItem.__annotations__
    assert "shadowed_by" not in t.ContextItem.__annotations__
    assert "shadowed_by" not in t.CONTEXT_ITEM_FIELDS


def test_proposal_spells_the_wire_key_from_exactly_once():
    """`from` is a Python keyword; the contract names the mapping so nobody invents a third."""
    assert t.PROPOSAL_WIRE_KEY_FROM == "from"
    assert "from_" in t.Proposal.__annotations__
    assert "from" not in t.Proposal.__annotations__


def test_stale_is_a_proposal_status():
    """The TOCTOU close needs somewhere to record a refused approval (container.md §6)."""
    assert t.PROPOSAL_STATUSES == ("open", "executed", "denied", "stale")


@pytest.mark.parametrize(("wire_key", "field"), CONFIG_WIRE_ROWS)
def test_each_config_row_maps_its_wire_key_to_its_field(wire_key, field):
    """Forward, one row at a time: §8's dotted name reaches the field that holds its value."""
    assert t.CONTAINER_CONFIG_FIELD_FROM_WIRE_KEY[wire_key] == field


@pytest.mark.parametrize(("wire_key", "field"), CONFIG_WIRE_ROWS)
def test_each_config_field_is_reached_by_exactly_one_wire_key(wire_key, field):
    """Reverse, one row at a time: no field is unreachable, none has two spellings."""
    assert [k for k, v in t.CONTAINER_CONFIG_FIELD_FROM_WIRE_KEY.items() if v == field] == [
        wire_key
    ]


def test_the_wire_mapping_covers_the_config_object_and_nothing_else():
    """A row the mapping omits is a key §8 promises a deployment may set and a loader drops."""
    assert set(t.CONTAINER_CONFIG_FIELD_FROM_WIRE_KEY) == {k for k, _ in CONFIG_WIRE_ROWS}
    assert set(t.CONTAINER_CONFIG_FIELD_FROM_WIRE_KEY.values()) == set(
        t.ContainerConfig.__annotations__
    )


def test_no_config_wire_key_is_spelled_the_same_as_its_field():
    """Every row differs, so a loader that skips the mapping fails on all six, never on some.

    Unlike `CONSENT_KIND_FROM_CLIENT_TYPE`, where two of three rows are identities and the bug can
    hide, this mapping has no row that works by accident.
    """
    for wire_key, field in t.CONTAINER_CONFIG_FIELD_FROM_WIRE_KEY.items():
        assert "." in wire_key, wire_key
        assert "." not in field, field
        assert wire_key != field


def test_a_zero_step_up_window_survives_a_load_that_uses_the_mapping():
    """Decision 2 (#102): `0` is a value. Absence is tested by absence, never by truthiness.

    The second assertion is the bug this constant exists to prevent, written out: the deployment
    that asked for the strictest setting in the table gets served the default it refused.
    """
    wire = {"step_up.window_seconds": 0}
    loaded = dict(t.CONTAINER_CONFIG_DEFAULTS)
    for wire_key, field in t.CONTAINER_CONFIG_FIELD_FROM_WIRE_KEY.items():
        if wire_key in wire:  # `in`, not `or` — the whole of the clause
            loaded[field] = wire[wire_key]
    assert loaded["step_up_window_seconds"] == 0

    truthy = wire["step_up.window_seconds"] or t.CONTAINER_CONFIG_DEFAULTS["step_up_window_seconds"]
    assert truthy == 300
