# Copyright 2026 Ali Sasanian
# SPDX-License-Identifier: LicenseRef-PolyForm-Strict-1.0.0
"""§2 the authorization code: single use, 60 s, bound three ways (authz/codes.py)."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

import pytest

from egzos._types import AS_CODE_LIFETIME_SECONDS, ASGrant, AuthorizationCodeRecord
from egzos.authz import codes, pkce, values

T0 = datetime(2026, 10, 12, 9, 0, 0, tzinfo=UTC)
VERIFIER = "v" * 43
CHALLENGE = pkce.s256(VERIFIER)
CLIENT = "egzos.io"
REDIRECT = "https://egzos.io/connect/callback"
GRANT = ASGrant(
    capabilities=["fetch"],
    scopes=["*"],
    principal="interactive",
    grant_expires_at="2026-11-11T09:00:00Z",
)


class Codes:
    """storage.md §3.1's two code methods, in memory. `consume_code` is atomic by construction
    (one thread) and does not judge expiry or bindings, as rule 1 requires of the real store."""

    def __init__(self) -> None:
        self.rows: dict[str, AuthorizationCodeRecord] = {}
        self.consumed: list[str] = []

    def put_code(self, record: AuthorizationCodeRecord) -> None:
        self.rows[record["code_hash"]] = record

    def consume_code(self, code_hash: str) -> AuthorizationCodeRecord | None:
        self.consumed.append(code_hash)
        return self.rows.pop(code_hash, None)


def _issue(state: Codes, **over: Any) -> str:
    args: dict[str, Any] = {
        "client_id": CLIENT,
        "redirect_uri": REDIRECT,
        "code_challenge": CHALLENGE,
        "session_hash": "s" * 64,
        "grant": GRANT,
        "now": T0,
    }
    return codes.issue(state, **{**args, **over})  # type: ignore[arg-type]


def _redeem(state: Codes, code: str | None, **over: Any) -> AuthorizationCodeRecord | None:
    args: dict[str, Any] = {
        "client_id": CLIENT,
        "redirect_uri": REDIRECT,
        "code_verifier": VERIFIER,
        "now": T0 + timedelta(seconds=5),
    }
    return codes.redeem(state, code=code, **{**args, **over})  # type: ignore[arg-type]


def test_issue_stores_the_digest_never_the_value():
    state = Codes()
    code = _issue(state)
    (record,) = state.rows.values()
    assert record["code_hash"] == values.digest(code)
    assert code not in repr(record)
    assert record["expires_at"] == "2026-10-12T09:01:00Z"
    assert AS_CODE_LIFETIME_SECONDS == 60
    assert record["grant"] == GRANT and record["session_hash"] == "s" * 64


def test_issued_codes_are_distinct_values():
    state = Codes()
    assert len({_issue(state) for _ in range(64)}) == 64


def test_redeem_returns_the_record_once():
    state = Codes()
    code = _issue(state)
    record = _redeem(state, code)
    assert record is not None and record["grant"] == GRANT
    assert _redeem(state, code) is None


@pytest.mark.parametrize(
    "over",
    [
        {"client_id": "other-client"},
        {"client_id": "EGZOS.IO"},
        {"client_id": None},
        {"client_id": "égzos.io"},
        {"client_id": "\ud800"},
        {"redirect_uri": REDIRECT + "/"},
        {"redirect_uri": "https://EGZOS.io/connect/callback"},
        {"redirect_uri": None},
        {"code_verifier": "w" * 43},
        {"code_verifier": None},
        {"code_verifier": ""},
        {"code_verifier": CHALLENGE + "!"},
        {"now": T0 + timedelta(seconds=AS_CODE_LIFETIME_SECONDS)},
        {"now": T0 + timedelta(days=1)},
    ],
)
def test_a_failed_check_refuses_and_spends_the_code(over):
    state = Codes()
    code = _issue(state)
    assert _redeem(state, code, **over) is None
    # §2: invalidated on the first redemption attempt, successful or not.
    assert _redeem(state, code) is None
    assert state.rows == {}


def test_the_last_second_before_expiry_still_redeems():
    state = Codes()
    code = _issue(state)
    late = T0 + timedelta(seconds=AS_CODE_LIFETIME_SECONDS - 1)
    assert _redeem(state, code, now=late) is not None


def test_the_challenge_itself_is_not_a_verifier():
    state = Codes()
    code = _issue(state)
    assert _redeem(state, code, code_verifier=CHALLENGE) is None


@pytest.mark.parametrize("code", [None, "", "not-a-code", "\ud800", "x" * 10_000])
def test_unknown_and_malformed_codes_are_refused_the_same_way(code):
    state = Codes()
    live = _issue(state)
    assert _redeem(state, code) is None
    # an unknown code spends no other code
    assert _redeem(state, live) is not None


def test_an_unreadable_expiry_fails_closed():
    state = Codes()
    code = _issue(state)
    state.rows[values.digest(code)]["expires_at"] = "tomorrow"
    assert _redeem(state, code) is None


def test_a_naive_clock_at_redemption_fails_closed():
    # A naive `now` cannot be placed against the stored UTC expiry: refused like an expired code,
    # never a `TypeError` (a second answer shape), and the code is spent all the same.
    state = Codes()
    code = _issue(state)
    assert _redeem(state, code, now=datetime(2026, 10, 12, 9, 0, 5)) is None
    assert state.rows == {}


def test_a_naive_clock_at_issuance_stores_nothing():
    state = Codes()
    with pytest.raises(ValueError):
        _issue(state, now=datetime(2026, 10, 12, 9, 0, 0))
    assert state.rows == {}


def test_the_code_is_spent_before_any_check_runs():
    # Even a request missing every binding reaches `consume_code`: a code that survived a failed
    # attempt could be retried with a guessed verifier.
    state = Codes()
    code = _issue(state)
    assert _redeem(state, code, client_id=None, redirect_uri=None, code_verifier=None) is None
    assert state.consumed == [values.digest(code)]


def test_redeem_defaults_to_the_wall_clock():
    state = Codes()
    code = codes.issue(
        state,  # type: ignore[arg-type]
        client_id=CLIENT,
        redirect_uri=REDIRECT,
        code_challenge=CHALLENGE,
        session_hash="s" * 64,
        grant=GRANT,
    )
    record = codes.redeem(
        state,  # type: ignore[arg-type]
        code=code,
        client_id=CLIENT,
        redirect_uri=REDIRECT,
        code_verifier=VERIFIER,
    )
    assert record is not None
