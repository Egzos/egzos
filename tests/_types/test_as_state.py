# Copyright 2026 Ali Sasanian
# SPDX-License-Identifier: Apache-2.0
"""
The authorization server's state, pinned — storage.md §3.1, a DRAFT binding on #173.

Two properties are what the section is for, and these tests fail if either moves: the method
groups (a single-use object gains a plain getter, or `ContainerState` silently absorbs a group
that #173 placed beside it), and the hash rule (a method or record that carries a
credential value instead of its sha256). Method sets are written out, not derived, for the same
reason `test_storage_protocols.py` gives.
"""

from __future__ import annotations

import inspect
import typing

import egzos._types as t

# `storage.md` §3's frozen fourteen, as `test_storage_protocols.py` pins them.
CONTAINER_STATE = frozenset(
    {
        "put_node", "get_node", "list_nodes", "find_root",
        "put_token", "get_token", "list_tokens",
        "put_proposal", "get_proposal", "list_proposals",
        "audit_append", "audit_last", "audit_iter", "audit_tail",
    }
)

AS_STATE = frozenset(
    {
        "put_client", "get_client", "remove_client",
        "put_code", "consume_code",
        "put_device", "poll_device", "get_device_by_user_code", "decide_device",
        "consume_device",
        "put_refresh", "redeem_refresh", "family_of_token", "revoke_family",
        "put_decided", "get_decided", "claim_resubmission",
    }
)

AS_GATE_STATE = frozenset(
    {
        "put_session", "get_session", "touch_session", "end_session",
        "throttle_incr", "throttle_count",
    }
)

RECORDS = (
    t.AuthorizationCodeRecord,
    t.DeviceAuthorizationRecord,
    t.RefreshRecord,
    t.DecidedRequestRecord,
    t.SessionRecord,
)

# The credential values storage.md §3.1 names. None may appear as a parameter or a record field.
CREDENTIAL_VALUE_NAMES = frozenset(
    {
        "code", "device_code", "user_code", "refresh_token", "refresh", "session", "session_id",
        "secret", "value", "token",
    }
)


def _methods(protocol: type) -> frozenset[str]:
    """The methods a Protocol declares in its own body."""
    return frozenset(
        name for name, value in vars(protocol).items()
        if not name.startswith("_") and callable(value)
    )


def test_as_state_method_set():
    assert _methods(t.ASState) == AS_STATE


def test_as_gate_state_method_set():
    assert _methods(t.ASGateState) == AS_GATE_STATE


def test_container_state_is_untouched_and_disjoint():
    """The frozen fourteen stay fourteen; #173's partition is answered beside them, not in them."""
    assert _methods(t.ContainerState) == CONTAINER_STATE
    assert not (AS_STATE & CONTAINER_STATE)
    assert not (AS_GATE_STATE & CONTAINER_STATE)
    assert not (AS_STATE & AS_GATE_STATE)


def test_single_use_objects_have_no_plain_getter():
    """§2: a code is spent on the first redemption attempt — `consume_code` is its only read."""
    assert not {"get_code", "get_refresh"} & AS_STATE


def test_device_record_is_never_rewritten_whole():
    """§3.1 rule 2: a poll is its own atomic write, so it cannot overwrite a concurrent decision.

    The read-modify-write shape (`get_device` then `put_device`) is what let one authorization be
    decided twice; it must not come back as a getter or an update method.
    """
    device = {name for name in AS_STATE if name.endswith("_device")}
    assert device == {"put_device", "poll_device", "decide_device", "consume_device"}
    params = list(inspect.signature(t.ASState.poll_device).parameters)
    assert params == ["self", "device_code_hash", "at"]
    hints = typing.get_type_hints(t.ASState.poll_device)
    assert hints["return"] == t.DeviceAuthorizationRecord | None


def test_no_client_listing():
    """§11.1 / §7.1: one keyed read, no enumeration of the registry."""
    assert not {name for name in AS_STATE if name.startswith("list_")}


def test_no_method_takes_a_credential_value():
    for protocol in (t.ASState, t.ASGateState):
        for name in _methods(protocol):
            params = set(inspect.signature(getattr(protocol, name)).parameters) - {"self"}
            assert not params & CREDENTIAL_VALUE_NAMES, (protocol.__name__, name, params)
            for p in params:
                if p in {"code_hash", "device_code_hash", "user_code_hash", "refresh_hash",
                         "session_hash"}:
                    assert typing.get_type_hints(getattr(protocol, name))[p] is str


def test_no_record_carries_a_credential_value():
    for record in RECORDS:
        fields = set(typing.get_type_hints(record))
        assert not fields & CREDENTIAL_VALUE_NAMES, (record.__name__, fields)


def test_records_key_on_hashes():
    assert "code_hash" in t.AuthorizationCodeRecord.__annotations__
    device = set(t.DeviceAuthorizationRecord.__annotations__)
    assert {"device_code_hash", "user_code_hash"} <= device
    assert "refresh_hash" in t.RefreshRecord.__annotations__
    assert "session_hash" in t.SessionRecord.__annotations__


def test_refresh_record_survives_redemption():
    """§9.2 clause 2: reuse is detected, so a redeemed link is kept and marked, not deleted."""
    hints = typing.get_type_hints(t.RefreshRecord)
    assert hints["redeemed_at"] == str | None
    assert "family_id" in hints and "access_token_id" in hints


def test_grant_is_capabilities_and_node_ids():
    """§7: nothing else rides a grant beyond its principal and its clamped expiry."""
    assert set(t.ASGrant.__annotations__) == {
        "capabilities", "scopes", "principal", "grant_expires_at"
    }


def test_throttle_names_no_rate_or_window_length():
    """#141's rates are Trust's constants: the store counts and is never told a rate or a window."""
    for name in ("throttle_incr", "throttle_count"):
        params = list(inspect.signature(getattr(t.ASGateState, name)).parameters)
        assert params == ["self", "surface", "bucket_key", "window_key"]


def test_device_record_carries_the_request_it_approves():
    """§3 mitigations 2–3: `/device` names the grant, and approval grants that request only, so the
    request is stored at insert. Neither field is in a later method's reach (storage.md §3.1)."""
    hints = typing.get_type_hints(t.DeviceAuthorizationRecord)
    assert hints["requested"] is t.DeviceRequest
    assert set(t.DeviceRequest.__annotations__) == {"capabilities", "scopes"}
    assert set(t.DeviceRequest.__annotations__) < set(t.ASGrant.__annotations__)
    params = list(inspect.signature(t.ASState.put_device).parameters)
    assert params == ["self", "record"]
    for name in ("poll_device", "decide_device", "consume_device"):
        params = inspect.signature(getattr(t.ASState, name)).parameters
        assert not set(params) & {"requested", "requester_hint", "record"}, name


def test_requester_hint_is_bounded_and_never_a_key():
    """§11.8: client-supplied, unverified, bounded; no method looks a record up by it."""
    assert typing.get_type_hints(t.DeviceAuthorizationRecord)["requester_hint"] == str | None
    assert t.AS_REQUESTER_HINT_MAX_CHARS == 64
    for protocol in (t.ASState, t.ASGateState):
        for name in _methods(protocol):
            assert "requester_hint" not in inspect.signature(getattr(protocol, name)).parameters


def test_device_decisions():
    assert typing.get_args(t.DeviceDecision) == ("pending", "granted", "denied")


def test_as_state_contracts_are_exported_and_apart_from_the_frozen_set():
    assert t.AS_STATE_CONTRACTS == ("ASState", "ASGateState")
    assert not set(t.AS_STATE_CONTRACTS) & set(t.STORAGE_CONTRACTS)
    for name in t.AS_STATE_CONTRACTS + tuple(r.__name__ for r in RECORDS) + ("DeviceRequest",):
        assert name in t.__all__
