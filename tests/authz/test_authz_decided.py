# Copyright 2026 Ali Sasanian
# SPDX-License-Identifier: LicenseRef-PolyForm-Strict-1.0.0
"""§11.4 a request reaches a decision exactly once; §11.0 substep 1 and the request-keyed read
(authz/decided.py)."""

from __future__ import annotations

import copy
from datetime import UTC, datetime, timedelta, timezone
from typing import Any

import pytest

from egzos._types import (
    AS_AUTHORIZE_PRETRUST_CAUSES,
    AS_THROTTLE_SURFACES,
    GENESIS_HASH,
    PRINCIPAL_NONE_EVENTS,
    DecidedRequestRecord,
)
from egzos.authz import decided, values
from egzos.ledger import Ledger

T0 = datetime(2026, 10, 13, 9, 0, 0, tzinfo=UTC)
A = "a" * 64  # a deciding session's digest
B = "b" * 64  # another live session's digest
REQUEST: dict[str, Any] = {
    "client_id": "c_egzos_io",
    "redirect_uri": "https://egzos.io/connect/callback",
    "state": "xyz",
    "code_challenge": "E9Melhoa2OwvFrEMTJguCHaoeK1t8URWbuGJSstw-cM",
}


class Decided:
    """storage.md §3.1's three decided-request methods, in memory, with rule 5's claim: `True`
    exactly once per recorded `(session_hash, request_key)`."""

    def __init__(self) -> None:
        self.rows: dict[str, DecidedRequestRecord] = {}
        self.claims: list[tuple[str, str]] = []
        self.reads: list[str] = []

    def put_decided(self, record: DecidedRequestRecord) -> None:
        self.rows[record["request_key"]] = copy.deepcopy(record)

    def get_decided(self, request_key: str) -> DecidedRequestRecord | None:
        self.reads.append(request_key)
        return copy.deepcopy(self.rows.get(request_key))

    def claim_resubmission(self, session_hash: str, request_key: str) -> bool:
        self.claims.append((session_hash, request_key))
        row = self.rows.get(request_key)
        if row is None or row["session_hash"] != session_hash or row["resubmission_seen"]:
            return False
        row["resubmission_seen"] = True
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
def state() -> Decided:
    return Decided()


@pytest.fixture
def chain() -> Chain:
    return Chain()


def _key(**over: Any) -> str:
    return decided.request_key(**{**REQUEST, **over})


def _decide(state: Decided, *, session: str = A, decision: str = "granted") -> str:
    key = _key()
    decided.record(state, key=key, session_hash=session, decision=decision, now=T0)  # type: ignore[arg-type]
    return key


def _assert_replayed(entry: dict[str, Any]) -> None:
    assert entry["event"] == "authz.refuse" and "authz.refuse" in PRINCIPAL_NONE_EVENTS
    assert entry["principal"] == "none"
    assert entry["actor"] == "authorize" and entry["actor"] in AS_THROTTLE_SURFACES
    assert entry["subject"] is None
    assert entry["details"] == {"cause": "replayed"}
    assert entry["details"]["cause"] in AS_AUTHORIZE_PRETRUST_CAUSES


# --- request_key


def test_request_key_is_a_stable_hex_digest():
    key = _key()
    assert key == _key()
    assert len(key) == 64 and int(key, 16) >= 0 and key == key.lower()


@pytest.mark.parametrize("field", ["client_id", "redirect_uri", "state", "code_challenge"])
def test_request_key_changes_with_every_field(field):
    assert _key(**{field: REQUEST[field] + "x"}) != _key()


def test_request_key_has_no_ambiguous_encoding():
    assert _key(state=None) != _key(state="")
    assert _key(state=None) != _key(state="null")
    # Moving a separator between fields is a different request, never the same digest.
    assert _key(client_id="a,b", redirect_uri="c") != _key(client_id="a", redirect_uri="b,c")
    assert _key(client_id='a"', redirect_uri="b") != _key(client_id="a", redirect_uri='"b')


def test_request_key_is_never_a_credential_digest():
    joined = "".join(str(v) for v in REQUEST.values())
    assert _key() != values.digest(joined)


def test_request_key_takes_a_lone_surrogate_without_raising():
    assert _key(state="\ud800") != _key(state="\ud801")


@pytest.mark.parametrize("field", ["client_id", "redirect_uri", "state", "code_challenge"])
def test_request_key_refuses_a_non_string(field):
    with pytest.raises(TypeError):
        _key(**{field: 7})


# --- record


@pytest.mark.parametrize("decision", ["granted", "denied"])
def test_record_binds_the_decision_to_the_deciding_session(state, decision):
    key = _decide(state, decision=decision)
    assert state.rows == {
        key: DecidedRequestRecord(
            request_key=key,
            session_hash=A,
            decision=decision,  # type: ignore[typeddict-item]
            decided_at="2026-10-13T09:00:00Z",
            resubmission_seen=False,
        )
    }


def test_record_writes_utc_from_any_aware_clock(state):
    plus2 = T0.astimezone(timezone(timedelta(hours=2)))
    decided.record(state, key=_key(), session_hash=A, decision="denied", now=plus2)  # type: ignore[arg-type]
    assert state.rows[_key()]["decided_at"] == "2026-10-13T09:00:00Z"


def test_record_defaults_to_the_current_clock(state):
    decided.record(state, key=_key(), session_hash=A, decision="granted")  # type: ignore[arg-type]
    stamp = datetime.strptime(state.rows[_key()]["decided_at"], "%Y-%m-%dT%H:%M:%SZ")
    assert abs(stamp.replace(tzinfo=UTC) - datetime.now(UTC)) < timedelta(minutes=1)


@pytest.mark.parametrize(
    "over",
    [
        {"now": datetime(2026, 10, 13, 9, 0, 0)},  # naive
        {"decision": "approved"},
        {"decision": None},
        {"key": ""},
        {"key": None},
        {"session_hash": ""},
        {"session_hash": None},
    ],
)
def test_record_refuses_a_callers_bug_and_stores_nothing(state, over):
    args: dict[str, Any] = {"key": _key(), "session_hash": A, "decision": "granted", "now": T0}
    with pytest.raises(ValueError):
        decided.record(state, **{**args, **over})  # type: ignore[arg-type]
    assert state.rows == {}


# --- §11.0 substep 1: the deciding session's first re-submission


def test_first_replay_on_the_deciding_session_appends_row_d_once(state, chain):
    key = _decide(state)
    assert decided.first_replay(state, Ledger(chain), session_hash=A, key=key)  # type: ignore[arg-type]
    (entry,) = chain.entries
    _assert_replayed(entry)


def test_first_replay_matches_once_per_decided_request(state, chain):
    key = _decide(state)
    ledger = Ledger(chain)  # type: ignore[arg-type]
    assert decided.first_replay(state, ledger, session_hash=A, key=key)  # type: ignore[arg-type]
    # The held-down back button: the second falls through to the counter (§12.1 rule 6).
    assert not decided.first_replay(state, ledger, session_hash=A, key=key)  # type: ignore[arg-type]
    assert len(chain.entries) == 1


def test_first_replay_is_keyed_on_the_deciding_session_only(state, chain):
    key = _decide(state)
    assert not decided.first_replay(state, Ledger(chain), session_hash=B, key=key)  # type: ignore[arg-type]
    assert chain.entries == []
    assert not state.rows[key]["resubmission_seen"]  # B's attempt spent nothing of A's


def test_first_replay_misses_an_undecided_request(state, chain):
    _decide(state)
    other = _key(state="another tab")
    assert not decided.first_replay(state, Ledger(chain), session_hash=A, key=other)  # type: ignore[arg-type]
    assert chain.entries == []


def test_one_session_can_decide_more_than_one_request(state, chain):
    first = _decide(state)
    second = _key(code_challenge="Q" * 43)
    decided.record(state, key=second, session_hash=A, decision="denied", now=T0)  # type: ignore[arg-type]
    ledger = Ledger(chain)  # type: ignore[arg-type]
    assert decided.first_replay(state, ledger, session_hash=A, key=first)  # type: ignore[arg-type]
    assert decided.first_replay(state, ledger, session_hash=A, key=second)  # type: ignore[arg-type]
    assert len(chain.entries) == 2


@pytest.mark.parametrize("session_hash", [None, "", 7])
def test_first_replay_without_a_session_matches_nothing_and_reads_nothing(state, chain, session_hash):
    key = _decide(state)
    assert not decided.first_replay(state, Ledger(chain), session_hash=session_hash, key=key)  # type: ignore[arg-type]
    assert state.claims == [] and chain.entries == []


@pytest.mark.parametrize("key", [None, ""])
def test_first_replay_without_a_key_reads_nothing(state, chain, key):
    _decide(state)
    assert not decided.first_replay(state, Ledger(chain), session_hash=A, key=key)  # type: ignore[arg-type]
    assert state.claims == [] and chain.entries == []


# --- the request-keyed read after the counter


def test_replayed_catches_another_session(state, chain):
    key = _decide(state)
    # Session B arrives with A's decided request: substep 1 misses, the pre-trust read does not.
    ledger = Ledger(chain)  # type: ignore[arg-type]
    assert not decided.first_replay(state, ledger, session_hash=B, key=key)  # type: ignore[arg-type]
    assert decided.replayed(state, ledger, key=key)  # type: ignore[arg-type]
    (entry,) = chain.entries
    _assert_replayed(entry)


def test_replayed_catches_the_deciding_sessions_second_resubmission(state, chain):
    key = _decide(state)
    ledger = Ledger(chain)  # type: ignore[arg-type]
    assert decided.first_replay(state, ledger, session_hash=A, key=key)  # type: ignore[arg-type]
    assert not decided.first_replay(state, ledger, session_hash=A, key=key)  # type: ignore[arg-type]
    assert decided.replayed(state, ledger, key=key)  # type: ignore[arg-type]
    assert decided.replayed(state, ledger, key=key)  # type: ignore[arg-type]
    # One entry per evaluated attempt (§12.1 rule 1), every one the same row.
    assert len(chain.entries) == 3
    for entry in chain.entries:
        _assert_replayed(entry)


@pytest.mark.parametrize("decision", ["granted", "denied"])
def test_a_denied_request_is_as_decided_as_a_granted_one(state, chain, decision):
    key = _decide(state, decision=decision)
    assert decided.replayed(state, Ledger(chain), key=key)  # type: ignore[arg-type]


def test_replayed_misses_a_fresh_request_and_appends_nothing(state, chain):
    _decide(state)
    assert not decided.replayed(state, Ledger(chain), key=_key(state="fresh"))  # type: ignore[arg-type]
    assert chain.entries == []


@pytest.mark.parametrize("key", [None, ""])
def test_replayed_without_a_key_reads_nothing(state, chain, key):
    _decide(state)
    assert not decided.replayed(state, Ledger(chain), key=key)  # type: ignore[arg-type]
    assert state.reads == [] and chain.entries == []


def test_row_d_is_uniform_whichever_read_matched(state, chain):
    key = _decide(state)
    ledger = Ledger(chain)  # type: ignore[arg-type]
    decided.first_replay(state, ledger, session_hash=A, key=key)  # type: ignore[arg-type]
    decided.replayed(state, ledger, key=key)  # type: ignore[arg-type]
    first, second = chain.entries
    strip = ("ts", "hash", "prev_hash")
    assert {k: v for k, v in first.items() if k not in strip} == {
        k: v for k, v in second.items() if k not in strip
    }


def test_row_d_carries_nothing_of_the_request(state, chain):
    key = _decide(state)
    decided.replayed(state, Ledger(chain), key=key)  # type: ignore[arg-type]
    text = repr(chain.entries)
    for value in (*REQUEST.values(), key, A):
        assert value not in text
