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


def test_proposal_spells_the_wire_key_from_exactly_once():
    """`from` is a Python keyword; the contract names the mapping so nobody invents a third."""
    assert t.PROPOSAL_WIRE_KEY_FROM == "from"
    assert "from_" in t.Proposal.__annotations__
    assert "from" not in t.Proposal.__annotations__


def test_stale_is_a_proposal_status():
    """The TOCTOU close needs somewhere to record a refused approval (container.md §6)."""
    assert t.PROPOSAL_STATUSES == ("open", "executed", "denied", "stale")
