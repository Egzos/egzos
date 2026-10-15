# Copyright 2026 Ali Sasanian
# SPDX-License-Identifier: LicenseRef-PolyForm-Strict-1.0.0
"""§11.8 `/device`'s two acts: row (b) `authz.redeem` and §9.3's `authz.grant`
(authz/device_entry.py)."""

from __future__ import annotations

import copy
import json
from datetime import UTC, datetime, timedelta, timezone
from typing import Any

import pytest

from egzos._types import (
    AS_DEVICE_REDEMPTION_CAUSES,
    AS_GRANT_DECISIONS,
    GENESIS_HASH,
    PRINCIPAL_NONE_EVENTS,
    ASGrant,
    DeviceAuthorizationRecord,
)
from egzos.authz import device, device_entry
from egzos.ledger import Ledger

T0 = datetime(2026, 10, 13, 9, 0, 0, tzinfo=UTC)
LATER = T0 + timedelta(seconds=30)
KEY = b"k" * 32  # a fixture key; provisioning the real one is #143's
CLIENT = "egzos-cli"
OWNER = "owner"
HINT = "ali-laptop"


class Devices:
    """storage.md §3.1's device methods, in memory: insert-only put, decide once. Like
    `test_authz_device.Devices`, the getter also returns expired and decided records (#214)."""

    def __init__(self) -> None:
        self.rows: dict[str, DeviceAuthorizationRecord] = {}
        self.lookups = 0

    def put_device(self, record: DeviceAuthorizationRecord) -> None:
        self.rows.setdefault(record["device_code_hash"], copy.deepcopy(record))

    def get_device_by_user_code(self, user_code_hash: str) -> DeviceAuthorizationRecord | None:
        self.lookups += 1
        for row in self.rows.values():
            if row["user_code_hash"] == user_code_hash:
                return copy.deepcopy(row)
        return None

    def decide_device(self, device_code_hash: str, grant: ASGrant | None) -> bool:
        row = self.rows.get(device_code_hash)
        if row is None or row["decision"] != "pending":
            return False
        row["decision"] = "granted" if grant is not None else "denied"
        row["grant"] = copy.deepcopy(grant)
        return True


class Chain:
    """Just enough backend for the real `Ledger`, so its event and principal guards run."""

    def __init__(self) -> None:
        self.entries: list[dict[str, Any]] = []

    def audit_last(self) -> dict[str, Any] | None:
        return self.entries[-1] if self.entries else None

    def audit_append(self, entry: dict[str, Any]) -> dict[str, Any]:
        assert entry["prev_hash"] == (self.entries[-1]["hash"] if self.entries else GENESIS_HASH)
        self.entries.append(entry)
        return entry


@pytest.fixture
def state() -> Devices:
    return Devices()


@pytest.fixture
def chain() -> Chain:
    return Chain()


def _issue(state: Devices, scope: str = "remember fetch node:*") -> str:
    response = device.authorize(
        state,  # type: ignore[arg-type]
        key=KEY,
        client_id=CLIENT,
        scope=scope,
        requester_hint=HINT,
        verification_uri="https://box.example/device",
        now=T0,
    )
    return response["user_code"]


def _redeem(state: Devices, chain: Chain, user_code: Any, *, now: datetime = LATER) -> Any:
    return device_entry.redeem(
        state,  # type: ignore[arg-type]
        Ledger(chain),  # type: ignore[arg-type]
        key=KEY,
        user_code=user_code,
        now=now,
    )


def _decide(state: Devices, chain: Chain, user_code: Any, **over: Any) -> bool:
    args: dict[str, Any] = {"key": KEY, "approve": True, "actor": OWNER, "now": LATER}
    return device_entry.decide(
        state,  # type: ignore[arg-type]
        Ledger(chain),  # type: ignore[arg-type]
        user_code=user_code,
        **{**args, **over},
    )


def _row(state: Devices) -> DeviceAuthorizationRecord:
    (row,) = state.rows.values()
    return row


# --- redeem: row (b) -----------------------------------------------------------------------------


def test_a_pending_code_is_found_and_appends_once(state: Devices, chain: Chain):
    shown = _issue(state)
    record = _redeem(state, chain, shown.lower().replace("-", ""))  # RFC 8628 §6.1 matching
    assert record is not None and record["client_id"] == CLIENT
    assert record["requester_hint"] == HINT  # for the screen, as untrusted data
    (entry,) = chain.entries
    assert entry["event"] == "authz.redeem"
    assert (entry["actor"], entry["principal"]) == ("device", "none")
    assert entry["details"] == {"outcome": "found"}


def _failed(chain: Chain, cause: str) -> None:
    (entry,) = chain.entries
    assert entry["event"] == "authz.redeem"
    assert (entry["actor"], entry["principal"]) == ("device", "none")
    assert entry["details"] == {"outcome": "failed", "cause": cause}


def test_an_unknown_code_fails_as_invalid(state: Devices, chain: Chain):
    shown = _issue(state)
    unknown = "BCDF-GHJK" if shown != "BCDF-GHJK" else "BCDF-GHJL"
    assert _redeem(state, chain, unknown) is None
    _failed(chain, "invalid")


def test_a_decided_code_fails_as_used_approved_or_denied(state: Devices, chain: Chain):
    for approve in (True, False):
        shown = _issue(state)
        assert device.decide(state, key=KEY, user_code=shown, approve=approve, now=LATER)  # type: ignore[arg-type]
        assert _redeem(state, chain, shown) is None
        assert chain.entries[-1]["details"] == {"outcome": "failed", "cause": "used"}
    assert len(chain.entries) == 2


def test_an_expired_code_fails_as_expired(state: Devices, chain: Chain):
    shown = _issue(state)
    late = T0 + timedelta(seconds=device.DEVICE_CODE_LIFETIME_SECONDS)
    assert _redeem(state, chain, shown, now=late) is None
    assert chain.entries[-1]["details"] == {"outcome": "failed", "cause": "expired"}


@pytest.mark.parametrize("code", [None, "", 42, "BCDF-GHJK-L", "aeio-uaei"])
def test_a_malformed_entry_costs_the_same_one_read(state: Devices, chain: Chain, code: Any):
    assert _redeem(state, chain, code) is None
    assert state.lookups == 1  # one timing class with an unknown code (§11.8)
    assert chain.entries[-1]["details"] == {"outcome": "failed", "cause": "malformed"}


def test_row_b_never_carries_the_code_the_hint_or_the_client(state: Devices, chain: Chain):
    shown = _issue(state)
    _redeem(state, chain, shown)
    _redeem(state, chain, "BCDF-BCDF")
    text = json.dumps(chain.entries)
    for secret in (shown, shown.replace("-", ""), "BCDF-BCDF", "BCDFBCDF", HINT, CLIENT):
        assert secret not in text  # §12.1 rule 7
    for entry in chain.entries:
        assert entry["event"] in PRINCIPAL_NONE_EVENTS
        assert entry["details"].get("cause") in (None, *AS_DEVICE_REDEMPTION_CAUSES)


def test_redeem_refuses_a_naive_clock_before_anything(state: Devices, chain: Chain):
    shown = _issue(state)
    reads = state.lookups
    with pytest.raises(ValueError):
        _redeem(state, chain, shown, now=datetime(2026, 10, 13, 9, 0, 30))
    assert state.lookups == reads and chain.entries == []


def test_redeem_takes_another_offset_as_the_same_instant(state: Devices, chain: Chain):
    shown = _issue(state)
    elsewhere = LATER.astimezone(timezone(timedelta(hours=3, minutes=30)))
    assert _redeem(state, chain, shown, now=elsewhere) is not None


# --- decide: §9.3 rows 3 and 4 -------------------------------------------------------------------


@pytest.mark.parametrize("approve", [True, False])
def test_a_decision_appends_one_authz_grant_with_the_request(
    state: Devices, chain: Chain, approve: bool
):
    shown = _issue(state)
    assert _decide(state, chain, shown, approve=approve)
    (entry,) = chain.entries
    assert entry["event"] == "authz.grant"
    assert (entry["actor"], entry["principal"]) == (OWNER, "interactive")
    decision = "granted" if approve else "denied"
    assert decision in AS_GRANT_DECISIONS
    assert entry["details"] == {
        "client_id": CLIENT,
        "decision": decision,
        "scopes": ["*"],  # requested, prefix stripped (§7), on a deny too ([0.3 · 29])
        "capabilities": ["fetch", "remember"],
    }
    assert entry["details"]["capabilities"] == _row(state)["requested"]["capabilities"]
    assert _row(state)["decision"] == decision


def test_anything_but_true_denies(state: Devices, chain: Chain):
    shown = _issue(state)
    assert _decide(state, chain, shown, approve="yes")
    assert chain.entries[-1]["details"]["decision"] == "denied"
    assert _row(state)["grant"] is None


def test_the_stored_grant_is_the_request_unchanged_and_client(state: Devices, chain: Chain):
    shown = _issue(state, "fetch node:01J0000000000000000000000A")
    assert _decide(state, chain, shown, lifetime_seconds=3600)
    stored = _row(state)["grant"]
    assert stored is not None
    assert stored["capabilities"] == ["fetch"]
    assert stored["scopes"] == ["01J0000000000000000000000A"]
    assert stored["principal"] == "client"  # §10.3
    assert stored["grant_expires_at"] == "2026-10-13T10:00:30Z"


def test_a_decision_happens_once_and_the_second_appends_nothing(state: Devices, chain: Chain):
    shown = _issue(state)
    assert _decide(state, chain, shown)
    assert not _decide(state, chain, shown, approve=False)
    assert [e["event"] for e in chain.entries] == ["authz.grant"]
    assert _row(state)["decision"] == "granted"


def test_a_lost_race_appends_nothing(state: Devices, chain: Chain, monkeypatch: Any):
    shown = _issue(state)
    monkeypatch.setattr(device, "decide", lambda *a, **k: False)  # another POST decided first
    assert not _decide(state, chain, shown)
    assert chain.entries == []


@pytest.mark.parametrize("code", [None, "", "BCDF-BCDF", "not a code"])
def test_no_pending_record_is_no_decision(state: Devices, chain: Chain, code: Any):
    _issue(state)
    assert not _decide(state, chain, code)
    assert chain.entries == [] and _row(state)["decision"] == "pending"


def test_an_expired_authorization_cannot_be_decided(state: Devices, chain: Chain):
    shown = _issue(state)
    late = T0 + timedelta(seconds=device.DEVICE_CODE_LIFETIME_SECONDS)
    assert not _decide(state, chain, shown, now=late)
    assert chain.entries == [] and _row(state)["decision"] == "pending"


@pytest.mark.parametrize("lifetime", [0, -1, True, 1.5, "3600", [3600]])
def test_a_malformed_lifetime_is_refused_before_the_lookup(
    state: Devices, chain: Chain, lifetime: Any
):
    shown = _issue(state)
    reads = state.lookups
    assert not _decide(state, chain, shown, lifetime_seconds=lifetime)
    assert state.lookups == reads  # #213's review: validated before `enter`'s lookup
    assert chain.entries == [] and _row(state)["decision"] == "pending"


@pytest.mark.parametrize("lifetime", [0, -1, True, 1.5, "3600", [3600]])
def test_a_malformed_lifetime_never_starves_a_deny(state: Devices, chain: Chain, lifetime: Any):
    shown = _issue(state)
    assert _decide(state, chain, shown, approve=False, lifetime_seconds=lifetime)
    assert _row(state)["decision"] == "denied" and _row(state)["grant"] is None
    (entry,) = chain.entries
    assert entry["event"] == "authz.grant" and entry["details"]["decision"] == "denied"


def test_a_huge_lifetime_is_clamped_not_refused(state: Devices, chain: Chain):
    shown = _issue(state)
    assert _decide(state, chain, shown, lifetime_seconds=10**100)
    stored = _row(state)["grant"]
    assert stored is not None and stored["grant_expires_at"] == "2027-01-11T09:00:30Z"


@pytest.mark.parametrize("actor", ["", None, 7])
def test_decide_needs_the_session_owner(state: Devices, chain: Chain, actor: Any):
    shown = _issue(state)
    reads = state.lookups
    with pytest.raises(ValueError):
        _decide(state, chain, shown, actor=actor)
    assert state.lookups == reads and chain.entries == []


def test_decide_refuses_a_naive_clock_before_anything(state: Devices, chain: Chain):
    shown = _issue(state)
    reads = state.lookups
    with pytest.raises(ValueError):
        _decide(state, chain, shown, now=datetime(2026, 10, 13, 9, 0, 30))
    assert state.lookups == reads and chain.entries == []
