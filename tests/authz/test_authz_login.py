# Copyright 2026 Ali Sasanian
# SPDX-License-Identifier: LicenseRef-PolyForm-Strict-1.0.0
"""§11.7 the login's evaluated attempt and §12 row (a) `authz.login` (authz/login.py)."""

from __future__ import annotations

import hashlib
import hmac
import json
from datetime import UTC, datetime, timedelta, timezone
from typing import Any

import pytest

from egzos._types import (
    AS_LOGIN_CAUSES,
    AS_THROTTLE_SURFACES,
    GENESIS_HASH,
    PRINCIPAL_NONE_EVENTS,
    SessionRecord,
)
from egzos.authz import login, sessions, values
from egzos.ledger import Ledger

T0 = datetime(2026, 10, 13, 9, 0, 0, tzinfo=UTC)
# A fixture secret, generated for this file and used nowhere else: #143 holds the real one's
# provisioning, so the test supplies its own behind `LoginSecret`.
SECRET = "fixture-container-secret-not-a-credential"


class Secret:
    """A `LoginSecret` over a digest, compared in constant time, recording every call."""

    def __init__(self, secret: str = SECRET) -> None:
        self._digest = hashlib.sha256(secret.encode()).digest()
        self.calls: list[str] = []

    def verify(self, presented: str) -> bool:
        self.calls.append(presented)
        given = hashlib.sha256(presented.encode()).digest()
        return bool(presented) and hmac.compare_digest(given, self._digest)


class Sessions:
    """storage.md §3.1's session methods, in memory."""

    def __init__(self) -> None:
        self.rows: dict[str, SessionRecord] = {}

    def put_session(self, record: SessionRecord) -> None:
        self.rows[record["session_hash"]] = record

    def get_session(self, session_hash: str) -> SessionRecord | None:
        row = self.rows.get(session_hash)
        return None if row is None else SessionRecord(**row)

    def touch_session(self, session_hash: str, at: str) -> bool:
        if session_hash not in self.rows:
            return False
        self.rows[session_hash]["last_seen_at"] = at
        return True

    def end_session(self, session_hash: str) -> bool:
        return self.rows.pop(session_hash, None) is not None


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
def gate() -> Sessions:
    return Sessions()


@pytest.fixture
def chain() -> Chain:
    return Chain()


def _attempt(
    gate: Sessions,
    chain: Chain,
    credential: Any,
    *,
    continue_value: str | None = "/",
    secret: Any = None,
    now: datetime = T0,
) -> login.Login:
    return login.attempt(
        gate,  # type: ignore[arg-type]
        Ledger(chain),  # type: ignore[arg-type]
        secret or Secret(),
        credential=credential,
        continue_value=continue_value,
        now=now,
    )


def _row_a(entry: dict[str, Any]) -> dict[str, Any]:
    assert entry["event"] == "authz.login" and "authz.login" in PRINCIPAL_NONE_EVENTS
    assert entry["principal"] == "none"
    assert entry["actor"] == "login" and entry["actor"] in AS_THROTTLE_SURFACES
    assert entry["subject"] is None and entry["scope"] is None
    details: dict[str, Any] = entry["details"]
    return details


# --- established


def test_the_secret_establishes_a_session_and_appends_once(gate, chain):
    answer = _attempt(gate, chain, SECRET, continue_value="/pending")
    assert answer.location == "/pending"
    assert isinstance(answer.session, str) and answer.session
    assert sessions.resolve(gate, answer.session, now=T0) == values.digest(answer.session)  # type: ignore[arg-type]
    (entry,) = chain.entries
    assert _row_a(entry) == {"outcome": "established"}


def test_the_login_mints_no_token(gate, chain):
    answer = _attempt(gate, chain, SECRET)
    assert {e["event"] for e in chain.entries} == {"authz.login"}
    (record,) = gate.rows.values()
    assert set(record) == {"session_hash", "created_at", "last_seen_at"}
    assert answer.session not in repr(gate.rows)


def test_continue_carries_the_authorize_query_untouched(gate, chain):
    resume = "/authorize?client_id=c&redirect_uri=https%3A%2F%2Fegzos.io%2Fcb&state=s%20x"
    assert _attempt(gate, chain, SECRET, continue_value=resume).location == resume


@pytest.mark.parametrize(
    "value",
    [None, "", "//evil.example/x", "/\\x", "/%2F%2Fx", "/items/a/b", "/elsewhere", "https://e.x/"],
)
def test_a_continue_failing_d_c5_lands_on_root_with_the_session(gate, chain, value):
    answer = _attempt(gate, chain, SECRET, continue_value=value)
    assert answer.location == "/"
    assert answer.session is not None
    (entry,) = chain.entries
    assert _row_a(entry) == {"outcome": "established"}


# --- failed


@pytest.mark.parametrize(
    "credential",
    [
        "wrong",
        SECRET + " ",
        SECRET.upper(),
        "",
        None,
        7,
        b"bytes",
        "\ud800",
        SECRET + "x" * 2048,
    ],
)
def test_every_other_credential_fails_alike(gate, chain, credential):
    answer = _attempt(gate, chain, credential, continue_value="/authorize?state=s")
    assert answer == login.Login(None, None)
    assert gate.rows == {}
    (entry,) = chain.entries
    details = _row_a(entry)
    assert details == {"outcome": "failed", "cause": "wrong"}
    assert details["cause"] in AS_LOGIN_CAUSES


@pytest.mark.parametrize("credential", ["wrong", "", None, 7, "\ud800", "x" * 4096])
def test_every_evaluated_attempt_reaches_the_verifier(gate, chain, credential):
    # One timing class: an absent or oversized credential costs the verifier call a wrong one does.
    secret = Secret()
    _attempt(gate, chain, credential, secret=secret)
    assert secret.calls == (["wrong"] if credential == "wrong" else [""])


def test_a_secret_at_the_length_bound_is_verified():
    secret_value = "s" * 1024
    gate, chain = Sessions(), Chain()
    answer = _attempt(gate, chain, secret_value, secret=Secret(secret_value))
    assert answer.session is not None


class Lenient:
    """A verifier that breaks its contract by accepting the empty string."""

    def verify(self, presented: str) -> bool:
        return True


def test_an_empty_credential_never_establishes_whatever_the_verifier_says(gate, chain):
    assert _attempt(gate, chain, "", secret=Lenient()) == login.Login(None, None)
    assert _attempt(gate, chain, None, secret=Lenient()) == login.Login(None, None)
    assert gate.rows == {}


class Truthy:
    """A verifier returning a truthy non-bool: only `True` verifies."""

    def verify(self, presented: str) -> Any:
        return "yes"


def test_only_true_verifies(gate, chain):
    assert _attempt(gate, chain, SECRET, secret=Truthy()) == login.Login(None, None)


# --- what the chain never holds


def test_the_chain_never_holds_the_credential_or_continue(gate, chain):
    _attempt(gate, chain, SECRET, continue_value="/authorize?state=marker-continue")
    _attempt(gate, chain, "marker-wrong-credential", continue_value="/items/marker-item")
    text = json.dumps(chain.entries)
    for marker in (SECRET, "marker-wrong-credential", "marker-continue", "marker-item"):
        assert marker not in text
    assert [_row_a(e)["outcome"] for e in chain.entries] == ["established", "failed"]


def test_unknown_is_never_emitted(gate, chain):
    for credential in (SECRET, "wrong", None):
        _attempt(gate, chain, credential)
    assert all(e["details"].get("cause") != "unknown" for e in chain.entries)


# --- the clock


def test_a_naive_clock_raises_before_anything_happens(gate, chain):
    secret = Secret()
    with pytest.raises(ValueError):
        _attempt(gate, chain, SECRET, secret=secret, now=datetime(2026, 10, 13, 9, 0, 0))
    assert secret.calls == [] and gate.rows == {} and chain.entries == []


def test_an_aware_clock_in_another_zone_is_accepted(gate, chain):
    east = T0.astimezone(timezone(timedelta(hours=3, minutes=30)))
    answer = _attempt(gate, chain, SECRET, now=east)
    (record,) = gate.rows.values()
    assert record["created_at"] == "2026-10-13T09:00:00Z"
    assert answer.session is not None


def test_the_default_clock_is_now(gate, chain):
    answer = login.attempt(
        gate,  # type: ignore[arg-type]
        Ledger(chain),  # type: ignore[arg-type]
        Secret(),
        credential=SECRET,
        continue_value="/",
    )
    assert sessions.resolve(gate, answer.session) is not None  # type: ignore[arg-type]


class Broken:
    def verify(self, presented: str) -> bool:
        raise RuntimeError("no secret provisioned")


def test_a_verifier_failure_establishes_nothing_and_appends_nothing(gate, chain):
    with pytest.raises(RuntimeError):
        _attempt(gate, chain, SECRET, secret=Broken())
    assert gate.rows == {} and chain.entries == []
