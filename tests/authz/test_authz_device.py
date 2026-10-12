# Copyright 2026 Ali Sasanian
# SPDX-License-Identifier: LicenseRef-PolyForm-Strict-1.0.0
"""§3 / §11.8 the device-code flow: issue, enter, decide, poll (authz/device.py)."""

from __future__ import annotations

import copy
import hashlib
import inspect
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest

from egzos._types import (
    AS_GRANT_LIFETIME_DEFAULT_SECONDS,
    AS_GRANT_LIFETIME_MAX_SECONDS,
    AS_REQUESTER_HINT_MAX_CHARS,
    AS_USER_CODE_ALPHABET,
    ASGrant,
    DeviceAuthorization,
    DeviceAuthorizationRecord,
)
from egzos.authz import device, grant, values

T0 = datetime(2026, 10, 12, 9, 0, 0, tzinfo=UTC)
KEY = b"k" * 32  # a fixture key; provisioning the real one is #143's
CLIENT = "egzos-cli"
URI = "https://box.example/device"
INTERVAL = timedelta(seconds=device.POLL_INTERVAL_SECONDS)


class Devices:
    """storage.md §3.1's five device methods, in memory, with rule 2's semantics: insert-only
    put, a poll that returns the prior record, decide once, consume nothing while pending."""

    def __init__(self) -> None:
        self.rows: dict[str, DeviceAuthorizationRecord] = {}
        self.lookups: list[str] = []
        self.decided: list[tuple[str, ASGrant | None]] = []

    def put_device(self, record: DeviceAuthorizationRecord) -> None:
        self.rows.setdefault(record["device_code_hash"], copy.deepcopy(record))

    def poll_device(self, device_code_hash: str, at: str) -> DeviceAuthorizationRecord | None:
        row = self.rows.get(device_code_hash)
        if row is None:
            return None
        prior = copy.deepcopy(row)
        row["last_polled_at"] = at
        return prior

    def get_device_by_user_code(self, user_code_hash: str) -> DeviceAuthorizationRecord | None:
        self.lookups.append(user_code_hash)
        for row in self.rows.values():
            if row["user_code_hash"] == user_code_hash:
                return copy.deepcopy(row)
        return None

    def decide_device(self, device_code_hash: str, grant: ASGrant | None) -> bool:
        self.decided.append((device_code_hash, copy.deepcopy(grant)))
        row = self.rows.get(device_code_hash)
        if row is None or row["decision"] != "pending":
            return False
        row["decision"] = "granted" if grant is not None else "denied"
        row["grant"] = copy.deepcopy(grant)
        return True

    def consume_device(self, device_code_hash: str) -> DeviceAuthorizationRecord | None:
        row = self.rows.get(device_code_hash)
        if row is None or row["decision"] == "pending":
            return None
        return self.rows.pop(device_code_hash)


def _issue(state: Devices, **over: Any) -> DeviceAuthorization:
    args: dict[str, Any] = {
        "key": KEY,
        "client_id": CLIENT,
        "scope": "remember fetch node:*",
        "requester_hint": "ali-laptop",
        "verification_uri": URI,
        "now": T0,
    }
    return device.authorize(state, **{**args, **over})  # type: ignore[arg-type]


def _row(state: Devices) -> DeviceAuthorizationRecord:
    (row,) = state.rows.values()
    return row


def _decide(state: Devices, user_code: str | None, **over: Any) -> bool:
    args: dict[str, Any] = {"key": KEY, "approve": True, "now": T0 + timedelta(seconds=30)}
    return device.decide(state, user_code=user_code, **{**args, **over})  # type: ignore[arg-type]


def _poll(state: Devices, device_code: str | None, **over: Any) -> device.Poll:
    args: dict[str, Any] = {"client_id": CLIENT, "now": T0 + timedelta(seconds=60)}
    return device.poll(state, device_code=device_code, **{**args, **over})  # type: ignore[arg-type]


# --- authorize ---------------------------------------------------------------------------------


def test_the_response_is_exactly_the_five_keys():
    response = _issue(Devices())
    # [0.3 · 21]: `verification_uri_complete` is absent, not empty and not null.
    keys = {"device_code", "user_code", "verification_uri", "expires_in", "interval"}
    assert set(response) == keys
    assert response["verification_uri"] == URI
    assert response["expires_in"] == device.DEVICE_CODE_LIFETIME_SECONDS
    assert response["interval"] == device.POLL_INTERVAL_SECONDS
    shown = response["user_code"]
    assert len(shown) == 9 and shown[4] == "-"
    assert all(c in AS_USER_CODE_ALPHABET for c in shown.replace("-", ""))


def test_the_store_holds_digests_never_values():
    state = Devices()
    response = _issue(state)
    row = _row(state)
    code = response["user_code"].replace("-", "")
    assert row["device_code_hash"] == values.digest(response["device_code"])
    # Keyed, never a bare sha256: an unkeyed hash of 34.6 bits inverts by enumeration (§3.1).
    assert row["user_code_hash"] == device.user_code_hash(KEY, code)
    assert row["user_code_hash"] != hashlib.sha256(code.encode()).hexdigest()
    assert response["device_code"] not in repr(row) and code not in repr(row)
    assert row["decision"] == "pending" and row["grant"] is None
    assert row["last_polled_at"] is None and row["client_id"] == CLIENT
    assert row["expires_at"] == "2026-10-12T09:10:00Z"


def test_requested_is_the_section_7_expansion():
    state = Devices()
    _issue(state, scope="remember fetch node:n1 node:*")
    assert _row(state)["requested"] == {
        "capabilities": ["fetch", "remember"],
        "scopes": ["n1", "*"],
    }


@pytest.mark.parametrize(
    "scope", [None, "", "reader", "fetch  remember", "fetch principal:interactive", "read"]
)
def test_an_unparseable_scope_is_refused_whole_and_stores_nothing(scope):
    state = Devices()
    with pytest.raises(grant.ScopeVocabularyError):
        _issue(state, scope=scope)
    assert state.rows == {}


def test_the_requester_hint_is_truncated_never_refused():
    state = Devices()
    _issue(state, requester_hint="h" * 10_000)
    assert _row(state)["requester_hint"] == "h" * AS_REQUESTER_HINT_MAX_CHARS


@pytest.mark.parametrize("hint", [None, 42, b"bytes", ["x"]])
def test_a_hint_that_is_not_text_is_dropped(hint):
    state = Devices()
    _issue(state, requester_hint=hint)
    assert _row(state)["requester_hint"] is None


def test_issued_values_are_distinct():
    state = Devices()
    issued = [_issue(state) for _ in range(32)]
    assert len({r["device_code"] for r in issued}) == 32
    assert len(state.rows) == 32


def test_a_colliding_user_code_is_drawn_again(monkeypatch):
    state = Devices()
    taken = _issue(state)["user_code"].replace("-", "")
    draws = iter([taken, taken, "BCDFGHJK"])
    monkeypatch.setattr(values, "new_user_code", lambda: next(draws))
    assert _issue(state)["user_code"] == "BCDF-GHJK"
    assert len(state.rows) == 2


def test_no_free_user_code_stores_nothing(monkeypatch):
    state = Devices()
    taken = _issue(state)["user_code"].replace("-", "")
    monkeypatch.setattr(values, "new_user_code", lambda: taken)
    with pytest.raises(RuntimeError):
        _issue(state)
    assert len(state.rows) == 1


def test_a_naive_clock_at_issuance_stores_nothing():
    state = Devices()
    with pytest.raises(ValueError):
        _issue(state, now=datetime(2026, 10, 12, 9, 0, 0))
    assert state.rows == {}


@pytest.mark.parametrize("key", [b"", "text-key", None])
def test_the_device_code_key_must_be_bytes(key):
    state = Devices()
    with pytest.raises(ValueError):
        _issue(state, key=key)
    assert state.rows == {}


# --- enter (row (b)) ---------------------------------------------------------------------------


def _enter(state: Devices, typed: str | None, **over: Any) -> device.Entry:
    args: dict[str, Any] = {"key": KEY, "now": T0 + timedelta(seconds=30)}
    return device.enter(state, user_code=typed, **{**args, **over})  # type: ignore[arg-type]


def test_entry_matches_case_insensitively_with_the_hyphen_ignored():
    state = Devices()
    shown = _issue(state)["user_code"]
    for typed in (shown, shown.lower(), shown.replace("-", ""), shown.lower().replace("-", "")):
        entry = _enter(state, typed)
        assert entry.cause is None and entry.record is not None
        assert entry.record["device_code_hash"] == _row(state)["device_code_hash"]


@pytest.mark.parametrize(
    "typed", [None, "", "BCDF GHJK", "BCDF-GHJA", "BCDF-GHJ1", "ſCDF-GHJK", "BCDF-GHJKL", "-" * 99]
)
def test_a_malformed_code_costs_a_lookup_and_answers_malformed(typed):
    state = Devices()
    _issue(state)
    state.lookups.clear()
    entry = _enter(state, typed)
    assert entry == device.Entry(None, "malformed")
    # One keyed hash and one store read, like every other cause (§11.8: one timing class).
    assert len(state.lookups) == 1


def test_an_unknown_code_and_another_key_answer_invalid():
    state = Devices()
    shown = _issue(state)["user_code"]
    other = "BCDF-GHJK" if shown != "BCDF-GHJK" else "ZXWV-TSRQ"
    assert _enter(state, other) == device.Entry(None, "invalid")
    assert _enter(state, shown, key=b"another-key") == device.Entry(None, "invalid")


def test_an_expired_code_answers_expired():
    state = Devices()
    shown = _issue(state)["user_code"]
    late = T0 + timedelta(seconds=device.DEVICE_CODE_LIFETIME_SECONDS)
    assert _enter(state, shown, now=late) == device.Entry(None, "expired")
    _row(state)["expires_at"] = "soon"
    assert _enter(state, shown) == device.Entry(None, "expired")


@pytest.mark.parametrize("approve", [True, False])
def test_a_decided_code_is_used_whether_approved_or_denied(approve):
    state = Devices()
    shown = _issue(state)["user_code"]
    assert _decide(state, shown, approve=approve)
    assert _enter(state, shown) == device.Entry(None, "used")


def test_entry_needs_an_aware_clock():
    state = Devices()
    shown = _issue(state)["user_code"]
    with pytest.raises(ValueError):
        _enter(state, shown, now=datetime(2026, 10, 12, 9, 0, 30))


# --- decide ------------------------------------------------------------------------------------


def test_approval_grants_the_request_unchanged_as_client():
    state = Devices()
    shown = _issue(state)["user_code"]
    assert _decide(state, shown)
    row = _row(state)
    assert row["decision"] == "granted"
    assert row["grant"] == {
        "capabilities": ["fetch", "remember"],
        "scopes": ["*"],
        "principal": "client",  # §10.3: never `interactive` from the device flow
        "grant_expires_at": "2026-11-11T09:00:30Z",
    }
    assert AS_GRANT_LIFETIME_DEFAULT_SECONDS == 30 * 24 * 3600


def test_the_grant_lifetime_is_clamped_never_refused():
    state = Devices()
    shown = _issue(state)["user_code"]
    assert _decide(state, shown, lifetime_seconds=10 * AS_GRANT_LIFETIME_MAX_SECONDS)
    expires = _row(state)["grant"]["grant_expires_at"]  # type: ignore[index]
    assert expires == "2027-01-10T09:00:30Z"


def test_a_widened_grant_cannot_be_decided():
    # #176 / §3 mitigation 3: the store does not tie `decide_device`'s grant to `requested`, so
    # Trust must. `decide` takes no grant, and edits to the record a caller holds do not reach it.
    assert "grant" not in inspect.signature(device.decide).parameters
    state = Devices()
    shown = _issue(state, scope="remember node:n1")["user_code"]
    held = _enter(state, shown).record
    assert held is not None
    held["requested"]["capabilities"].append("admin")
    held["requested"]["scopes"].append("*")
    assert _decide(state, shown)
    ((_, decided),) = state.decided
    assert decided is not None
    assert decided["capabilities"] == ["remember"] and decided["scopes"] == ["n1"]


def test_denial_decides_with_no_grant():
    state = Devices()
    shown = _issue(state)["user_code"]
    assert _decide(state, shown, approve=False)
    assert _row(state)["decision"] == "denied" and _row(state)["grant"] is None


@pytest.mark.parametrize("approve", [1, "yes", None])
def test_anything_but_true_is_a_denial(approve):
    state = Devices()
    shown = _issue(state)["user_code"]
    assert _decide(state, shown, approve=approve)
    assert _row(state)["decision"] == "denied"


def test_one_approval_one_request():
    state = Devices()
    first = _issue(state)["user_code"]
    second = _issue(state)["user_code"]
    assert _decide(state, first)
    assert not _decide(state, first)  # decided exactly once
    pending = [r for r in state.rows.values() if r["decision"] == "pending"]
    assert len(pending) == 1  # the concurrent request still needs its own approval
    assert _decide(state, second, approve=False)


def test_a_late_or_unknown_code_decides_nothing():
    state = Devices()
    shown = _issue(state)["user_code"]
    late = T0 + timedelta(seconds=device.DEVICE_CODE_LIFETIME_SECONDS)
    assert not _decide(state, shown, now=late)
    assert not _decide(state, "not a code")
    assert state.decided == []
    assert _row(state)["decision"] == "pending"


# --- poll (token endpoint) ---------------------------------------------------------------------


def test_the_flow_end_to_end():
    state = Devices()
    response = _issue(state)
    dc = response["device_code"]
    assert _poll(state, dc, now=T0 + INTERVAL) == device.Poll("authorization_pending")
    assert _decide(state, response["user_code"])
    result = _poll(state, dc, now=T0 + 2 * INTERVAL)
    assert result.error is None and result.record is not None
    assert result.record["grant"] is not None and result.record["grant"]["principal"] == "client"
    # spent: the second redemption finds nothing
    assert _poll(state, dc, now=T0 + 3 * INTERVAL) == device.Poll("invalid_grant")


def test_a_denied_authorization_answers_access_denied_once():
    state = Devices()
    response = _issue(state)
    assert _decide(state, response["user_code"], approve=False)
    assert _poll(state, response["device_code"]) == device.Poll("access_denied")
    later = T0 + timedelta(seconds=60) + INTERVAL
    assert _poll(state, response["device_code"], now=later) == device.Poll("invalid_grant")


def test_polling_faster_than_the_interval_is_slow_down():
    state = Devices()
    dc = _issue(state)["device_code"]
    assert _poll(state, dc, now=T0).error == "authorization_pending"
    assert _poll(state, dc, now=T0 + INTERVAL - timedelta(seconds=1)).error == "slow_down"
    # the too-fast poll is itself the last poll
    assert _poll(state, dc, now=T0 + INTERVAL).error == "slow_down"
    assert _poll(state, dc, now=T0 + 3 * INTERVAL).error == "authorization_pending"


def test_slow_down_holds_even_once_approved():
    state = Devices()
    response = _issue(state)
    assert _poll(state, response["device_code"], now=T0).error == "authorization_pending"
    assert _decide(state, response["user_code"])
    assert _poll(state, response["device_code"], now=T0 + timedelta(seconds=1)).error == "slow_down"
    assert _poll(state, response["device_code"], now=T0 + 2 * INTERVAL).error is None


def test_an_unreadable_last_poll_fails_closed():
    state = Devices()
    dc = _issue(state)["device_code"]
    _row(state)["last_polled_at"] = "earlier"
    assert _poll(state, dc).error == "slow_down"


def test_an_expired_authorization_is_expired_token_even_if_approved():
    state = Devices()
    response = _issue(state)
    assert _decide(state, response["user_code"])
    late = T0 + timedelta(seconds=device.DEVICE_CODE_LIFETIME_SECONDS)
    assert _poll(state, response["device_code"], now=late) == device.Poll("expired_token")
    assert len(state.rows) == 1  # nothing spent


@pytest.mark.parametrize(
    "over",
    [
        {"client_id": "other-client"},
        {"client_id": "EGZOS-CLI"},
        {"client_id": None},
        {"client_id": "\ud800"},
    ],
)
def test_another_clients_poll_is_invalid_grant(over):
    state = Devices()
    response = _issue(state)
    assert _decide(state, response["user_code"])
    assert _poll(state, response["device_code"], **over) == device.Poll("invalid_grant")
    assert len(state.rows) == 1  # and spends nothing


@pytest.mark.parametrize("dc", [None, "", "not-a-device-code", "\ud800", "x" * 10_000])
def test_unknown_and_malformed_device_codes_are_invalid_grant(dc):
    state = Devices()
    _issue(state)
    assert _poll(state, dc) == device.Poll("invalid_grant")


def test_a_naive_clock_at_poll_touches_nothing():
    state = Devices()
    dc = _issue(state)["device_code"]
    assert _poll(state, dc, now=datetime(2026, 10, 12, 9, 1, 0)) == device.Poll("invalid_grant")
    assert _row(state)["last_polled_at"] is None


def test_a_concurrently_spent_authorization_is_invalid_grant():
    state = Devices()
    response = _issue(state)
    assert _decide(state, response["user_code"])
    state.consume_device = lambda _h: None  # type: ignore[method-assign]
    assert _poll(state, response["device_code"]) == device.Poll("invalid_grant")


def test_a_granted_record_without_a_grant_mints_nothing():
    state = Devices()
    response = _issue(state)
    assert _decide(state, response["user_code"])
    _row(state)["grant"] = None
    assert _poll(state, response["device_code"]) == device.Poll("access_denied")


def test_every_step_defaults_to_the_wall_clock():
    state: Any = Devices()
    response = device.authorize(
        state,
        key=KEY,
        client_id=CLIENT,
        scope="fetch",
        requester_hint=None,
        verification_uri=URI,
    )
    user_code = response["user_code"]
    assert device.enter(state, key=KEY, user_code=user_code).record is not None
    assert device.decide(state, key=KEY, user_code=user_code, approve=True)
    assert device.poll(state, device_code=response["device_code"], client_id=CLIENT).error is None
