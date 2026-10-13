# Copyright 2026 Ali Sasanian
# SPDX-License-Identifier: LicenseRef-PolyForm-Strict-1.0.0
"""§10.1–§10.2 the interactive session: not a token, two clocks, judged by Trust
(authz/sessions.py)."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from egzos import auth
from egzos._types import AS_SESSION_ABSOLUTE_SECONDS, AS_SESSION_IDLE_SECONDS, SessionRecord
from egzos.authz import sessions, values

T0 = datetime(2026, 10, 13, 9, 0, 0, tzinfo=UTC)
IDLE = timedelta(seconds=AS_SESSION_IDLE_SECONDS)
ABSOLUTE = timedelta(seconds=AS_SESSION_ABSOLUTE_SECONDS)


class Sessions:
    """storage.md §3.1's four session methods, in memory. The getter does not judge the clocks:
    the store holds them and Trust reads them, as `SessionRecord`'s docstring says."""

    def __init__(self) -> None:
        self.rows: dict[str, SessionRecord] = {}
        self.ended: list[str] = []
        self.touches: list[tuple[str, str]] = []

    def put_session(self, record: SessionRecord) -> None:
        self.rows[record["session_hash"]] = record

    def get_session(self, session_hash: str) -> SessionRecord | None:
        row = self.rows.get(session_hash)
        return None if row is None else SessionRecord(**row)  # a copy, as a real read is

    def touch_session(self, session_hash: str, at: str) -> bool:
        self.touches.append((session_hash, at))
        if session_hash not in self.rows:
            return False
        self.rows[session_hash]["last_seen_at"] = at
        return True

    def end_session(self, session_hash: str) -> bool:
        self.ended.append(session_hash)
        return self.rows.pop(session_hash, None) is not None


def test_the_contract_clocks():
    assert AS_SESSION_IDLE_SECONDS == 30 * 60
    assert AS_SESSION_ABSOLUTE_SECONDS == 8 * 3600


def test_establish_stores_the_digest_never_the_value():
    gate = Sessions()
    value = sessions.establish(gate, now=T0)  # type: ignore[arg-type]
    (record,) = gate.rows.values()
    assert record == SessionRecord(
        session_hash=values.digest(value),
        created_at="2026-10-13T09:00:00Z",
        last_seen_at="2026-10-13T09:00:00Z",
    )
    assert value not in repr(gate.rows)


def test_a_session_is_not_a_token():
    gate = Sessions()
    value = sessions.establish(gate, now=T0)  # type: ignore[arg-type]
    assert auth.token_id_of(value) is None  # not `auth`'s bearer format, so no `Token` lookup
    (record,) = gate.rows.values()
    assert set(record) == {"session_hash", "created_at", "last_seen_at"}  # no capability, scope, id


def test_establish_values_are_distinct():
    gate = Sessions()
    assert len({sessions.establish(gate, now=T0) for _ in range(64)}) == 64  # type: ignore[arg-type]
    assert len(gate.rows) == 64


def test_establish_refuses_a_naive_clock_and_stores_nothing():
    gate = Sessions()
    with pytest.raises(ValueError):
        sessions.establish(gate, now=datetime(2026, 10, 13, 9, 0, 0))  # type: ignore[arg-type]
    assert gate.rows == {}


def test_establish_defaults_to_the_wall_clock():
    gate = Sessions()
    value = sessions.establish(gate)  # type: ignore[arg-type]
    assert sessions.resolve(gate, value) == values.digest(value)  # type: ignore[arg-type]


def test_resolve_a_live_session_returns_its_hash_and_restarts_the_idle_clock():
    gate = Sessions()
    value = sessions.establish(gate, now=T0)  # type: ignore[arg-type]
    at = T0 + timedelta(minutes=10)
    assert sessions.resolve(gate, value, now=at) == values.digest(value)  # type: ignore[arg-type]
    (record,) = gate.rows.values()
    assert record["last_seen_at"] == "2026-10-13T09:10:00Z"
    assert record["created_at"] == "2026-10-13T09:00:00Z"  # the absolute clock is not touched


def test_idle_clock_ends_the_session_at_thirty_minutes():
    gate = Sessions()
    value = sessions.establish(gate, now=T0)  # type: ignore[arg-type]
    just_before = T0 + IDLE - timedelta(seconds=1)
    assert sessions.resolve(gate, value, now=just_before) is not None  # type: ignore[arg-type]
    assert sessions.resolve(gate, value, now=just_before + IDLE) is None  # type: ignore[arg-type]
    assert gate.rows == {}  # ended in the store, not only refused
    assert gate.ended == [values.digest(value)]
    # and it stays ended: a later request does not find it
    assert sessions.resolve(gate, value, now=just_before + IDLE) is None  # type: ignore[arg-type]


def test_idle_clock_ends_exactly_at_the_bound():
    gate = Sessions()
    value = sessions.establish(gate, now=T0)  # type: ignore[arg-type]
    assert sessions.resolve(gate, value, now=T0 + IDLE) is None  # type: ignore[arg-type]


def test_page_loads_cannot_extend_past_the_absolute_clock():
    gate = Sessions()
    value = sessions.establish(gate, now=T0)  # type: ignore[arg-type]
    at = T0
    while at + timedelta(minutes=20) < T0 + ABSOLUTE:
        at += timedelta(minutes=20)
        assert sessions.resolve(gate, value, now=at) is not None  # type: ignore[arg-type]
    assert sessions.resolve(gate, value, now=T0 + ABSOLUTE) is None  # type: ignore[arg-type]
    assert gate.rows == {}


def test_unknown_empty_and_non_string_values_are_none():
    gate = Sessions()
    sessions.establish(gate, now=T0)  # type: ignore[arg-type]
    for value in (None, "", 42, values.new_value(), "egz_01ABC_" + "x" * 43):
        assert sessions.resolve(gate, value, now=T0) is None  # type: ignore[arg-type]
    assert len(gate.rows) == 1 and gate.ended == [] and gate.touches == []


def test_a_naive_clock_resolves_nothing_and_ends_nothing():
    gate = Sessions()
    value = sessions.establish(gate, now=T0)  # type: ignore[arg-type]
    naive = datetime(2026, 10, 13, 9, 5, 0)
    assert sessions.resolve(gate, value, now=naive) is None  # type: ignore[arg-type]
    assert len(gate.rows) == 1 and gate.ended == [] and gate.touches == []


@pytest.mark.parametrize(
    "field,stored",
    [
        ("created_at", "not a time"),
        ("last_seen_at", "2026-10-13 09:00:00"),
        ("created_at", None),
        ("last_seen_at", 0),
    ],
)
def test_an_unreadable_clock_fails_closed_and_ends_the_session(field, stored):
    gate = Sessions()
    value = sessions.establish(gate, now=T0)  # type: ignore[arg-type]
    gate.rows[values.digest(value)][field] = stored  # type: ignore[literal-required]
    assert sessions.resolve(gate, value, now=T0) is None  # type: ignore[arg-type]
    assert gate.rows == {}


def test_a_missing_clock_field_fails_closed():
    gate = Sessions()
    value = sessions.establish(gate, now=T0)  # type: ignore[arg-type]
    del gate.rows[values.digest(value)]["created_at"]  # type: ignore[misc]
    assert sessions.resolve(gate, value, now=T0) is None  # type: ignore[arg-type]


@pytest.mark.parametrize("field", ["created_at", "last_seen_at"])
def test_a_clock_stepped_backwards_refuses_and_keeps_the_session(field):
    gate = Sessions()
    value = sessions.establish(gate, now=T0)  # type: ignore[arg-type]
    gate.rows[values.digest(value)][field] = "2026-10-13T10:00:00Z"  # type: ignore[literal-required]
    assert sessions.resolve(gate, value, now=T0) is None  # type: ignore[arg-type]
    assert len(gate.rows) == 1 and gate.ended == [] and gate.touches == []


def test_after_a_backwards_step_the_session_is_judged_on_its_stamps_again():
    gate = Sessions()
    value = sessions.establish(gate, now=T0 + timedelta(hours=1))  # type: ignore[arg-type]
    assert sessions.resolve(gate, value, now=T0) is None  # type: ignore[arg-type]
    later = T0 + timedelta(hours=1, seconds=1)
    assert sessions.resolve(gate, value, now=later) == values.digest(value)  # type: ignore[arg-type]


def test_just_beyond_the_skew_is_refused_and_ends_nothing():
    gate = Sessions()
    value = sessions.establish(gate, now=T0 + timedelta(seconds=3))  # type: ignore[arg-type]
    assert sessions.resolve(gate, value, now=T0) is None  # type: ignore[arg-type]
    assert len(gate.rows) == 1 and gate.ended == []


def test_two_requests_racing_on_one_session_both_stay_signed_in():
    gate = Sessions()
    value = sessions.establish(gate, now=T0)  # type: ignore[arg-type]
    session_hash = values.digest(value)
    b_now = T0 + timedelta(minutes=5, microseconds=500_000)  # B reads its clock first
    a_now = T0 + timedelta(minutes=5, seconds=1, microseconds=200_000)  # A reads later
    assert sessions.resolve(gate, value, now=a_now) == session_hash  # type: ignore[arg-type]
    # B now reads A's stamp, a second after B's own `now`: judged live, not signed out
    assert sessions.resolve(gate, value, now=b_now) == session_hash  # type: ignore[arg-type]
    assert gate.ended == []
    # and B's earlier `now` never moves the idle clock back
    assert gate.rows[session_hash]["last_seen_at"] == "2026-10-13T09:05:01Z"


def test_the_skew_cannot_stretch_the_idle_clock():
    gate = Sessions()
    value = sessions.establish(gate, now=T0)  # type: ignore[arg-type]
    gate.rows[values.digest(value)]["last_seen_at"] = "2026-10-13T09:00:02Z"
    assert sessions.resolve(gate, value, now=T0 + timedelta(seconds=2) + IDLE) is None  # type: ignore[arg-type]
    assert gate.rows == {}


def test_a_session_ended_between_read_and_touch_is_not_live():
    gate = Sessions()
    value = sessions.establish(gate, now=T0)  # type: ignore[arg-type]
    touch = gate.touch_session

    def racing_touch(session_hash: str, at: str) -> bool:
        gate.end_session(session_hash)  # a sign-out in another request lands first
        return touch(session_hash, at)

    gate.touch_session = racing_touch  # type: ignore[method-assign]
    assert sessions.resolve(gate, value, now=T0) is None  # type: ignore[arg-type]


def test_end_signs_out_and_the_answer_is_the_same_for_any_value():
    gate = Sessions()
    value = sessions.establish(gate, now=T0)  # type: ignore[arg-type]
    assert sessions.end(gate, value) is None  # type: ignore[arg-type,func-returns-value]
    assert sessions.resolve(gate, value, now=T0) is None  # type: ignore[arg-type]
    for other in (value, values.new_value(), "", None):
        assert sessions.end(gate, other) is None  # type: ignore[arg-type,func-returns-value]
    # the empty and non-string values reach no store call; the rest are the same call
    assert gate.ended[:2] == [values.digest(value)] * 2 and len(gate.ended) == 3
