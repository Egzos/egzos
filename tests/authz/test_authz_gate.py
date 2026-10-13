# Copyright 2026 Ali Sasanian
# SPDX-License-Identifier: LicenseRef-PolyForm-Strict-1.0.0
"""§11.0 substep 3, `/authorize`'s session check, and row (d) `token_presented` (authz/gate.py)."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any
from urllib.parse import parse_qsl, urlsplit

import pytest

from egzos import auth
from egzos._types import AS_SESSION_IDLE_SECONDS, GENESIS_HASH, SessionRecord
from egzos.authz import continuation, gate, pretrust, sessions
from egzos.ledger import Ledger

T0 = datetime(2026, 10, 13, 9, 0, 0, tzinfo=UTC)
QUERY = (
    "response_type=code&client_id=01JCLIENT00000000000000000"
    "&redirect_uri=https%3A%2F%2Fegzos.io%2Fconnect%2Fcallback&state=a%26b%3Dc"
    "&code_challenge=E9Melhoa2OwvFrEMTJguCHaoeK1t8URWbuGJSstw-cM&code_challenge_method=S256"
    "&scope=read%20node%3A%2A"
)


class Sessions:
    """storage.md §3.1's four session methods, in memory, counting every call."""

    def __init__(self) -> None:
        self.rows: dict[str, SessionRecord] = {}
        self.calls: list[str] = []

    def put_session(self, record: SessionRecord) -> None:
        self.rows[record["session_hash"]] = record

    def get_session(self, session_hash: str) -> SessionRecord | None:
        self.calls.append("get")
        row = self.rows.get(session_hash)
        return None if row is None else SessionRecord(**row)

    def touch_session(self, session_hash: str, at: str) -> bool:
        self.calls.append("touch")
        if session_hash not in self.rows:
            return False
        self.rows[session_hash]["last_seen_at"] = at
        return True

    def end_session(self, session_hash: str) -> bool:
        self.calls.append("end")
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
def store() -> Sessions:
    return Sessions()


@pytest.fixture
def chain() -> Chain:
    return Chain()


def _check(store: Sessions, chain: Chain, **kw: Any) -> Any:
    kw.setdefault("session", None)
    kw.setdefault("authorization", None)
    kw.setdefault("query", QUERY)
    kw.setdefault("now", T0)
    return gate.check(store, Ledger(chain), **kw)  # type: ignore[arg-type]


def _token_presented(chain: Chain) -> None:
    assert len(chain.entries) == 1
    entry = chain.entries[0]
    assert entry["event"] == "authz.refuse"
    assert entry["actor"] == "authorize"
    assert entry["principal"] == "none"
    assert entry["details"] == {"cause": "token_presented"}
    assert entry.get("subject") is None


# --- a live session goes on to the pre-trust tier


def test_a_live_session_proceeds_and_appends_nothing(store: Sessions, chain: Chain) -> None:
    value = sessions.establish(store, now=T0)  # type: ignore[arg-type]
    out = _check(store, chain, session=value, now=T0 + timedelta(minutes=5))
    assert out == gate.Session(next(iter(store.rows)))
    assert chain.entries == []
    # The idle clock restarted: this is one of §11's page requests (§10.2).
    assert store.calls == ["get", "touch"]


@pytest.mark.parametrize("authorization", ["Bearer egz_x_y", "Basic Zm9vOmJhcg==", "anything"])
def test_a_session_beside_a_credential_is_decided_on_the_session(
    store: Sessions, chain: Chain, authorization: str
) -> None:
    value = sessions.establish(store, now=T0)  # type: ignore[arg-type]
    out = _check(store, chain, session=value, authorization=authorization)
    assert isinstance(out, gate.Session)
    assert chain.entries == []  # `token_presented` never fires beside a session


# --- a credential in place of a session is refused, never redirected


@pytest.mark.parametrize("authorization", ["Bearer egz_x_y", "Basic Zm9vOmJhcg==", "x", " Bearer "])
def test_a_credential_with_no_session_is_refused_with_row_d(
    store: Sessions, chain: Chain, authorization: str
) -> None:
    assert _check(store, chain, authorization=authorization) == gate.Refused()
    _token_presented(chain)
    # §5.3's page, the same status and line as every pre-trust refusal.
    assert (pretrust.STATUS, pretrust.COPY) == (400, "This request can't be completed.")


def test_the_credential_is_never_validated(store: Sessions, chain: Chain) -> None:
    """A live token, a forged one and garbage get the same answer and the same entry, and the
    answer touches no store a `Token` lives in: `gate` holds no token store to ask."""
    live = auth.new_secret("01JTOKEN000000000000000000")
    forged = "egz_" + "0" * 26 + "_" + "A" * 43
    answers = []
    for value in (live, forged, "not-a-token"):
        trail = Chain()
        answers.append(_check(store, trail, authorization=f"Bearer {value}"))
        _token_presented(trail)
        assert value not in repr(trail.entries)
    assert answers == [gate.Refused()] * 3
    assert store.calls == []  # no session offered, so not even the session store was read


def test_a_credential_with_an_ended_session_is_refused(store: Sessions, chain: Chain) -> None:
    value = sessions.establish(store, now=T0)  # type: ignore[arg-type]
    later = T0 + timedelta(seconds=AS_SESSION_IDLE_SECONDS)
    out = _check(store, chain, session=value, authorization="Bearer egz_x_y", now=later)
    assert out == gate.Refused()
    _token_presented(chain)


@pytest.mark.parametrize("authorization", [None, "", "   ", b"Bearer x", 7])
def test_no_credential_is_not_a_presented_one(authorization: Any) -> None:
    assert gate.presents_credential(authorization) is False


# --- neither: a 303 to /login carrying the request in `continue`


def test_no_session_and_no_credential_is_a_303_to_login(store: Sessions, chain: Chain) -> None:
    out = _check(store, chain)
    assert isinstance(out, gate.ToLogin)
    assert gate.REDIRECT_STATUS == 303
    parts = urlsplit(out.location)
    assert (parts.scheme, parts.netloc, parts.path, parts.fragment) == ("", "", "/login", "")
    assert chain.entries == []  # the 303 appends nothing (§11.0)
    assert store.calls == []  # and reads nothing


def test_the_login_resumes_the_request_exactly_as_received(store: Sessions, chain: Chain) -> None:
    """After the framework's one decode of `continue`, D-C5 carries `/authorize` and its query,
    still percent-encoded, to the login's 303 (§11.7)."""
    out = _check(store, chain)
    pairs = parse_qsl(urlsplit(out.location).query, keep_blank_values=True)
    assert pairs == [("continue", f"/authorize?{QUERY}")]
    assert continuation.resolve(pairs[0][1]) == f"/authorize?{QUERY}"


def test_the_location_is_header_safe(store: Sessions, chain: Chain) -> None:
    out = _check(store, chain, query="a=%0D%0ASet-Cookie:x&b=\r\nLocation: //evil")
    assert all(0x21 <= ord(c) <= 0x7E for c in out.location)
    assert out.location.count("?") == 1
    assert "&" not in out.location and "#" not in out.location


def test_the_location_does_not_depend_on_what_the_request_names(
    store: Sessions, chain: Chain
) -> None:
    """Registered or not, well-formed or not: the status and the path are one (§10.2)."""
    for query in (QUERY, "client_id=nobody", "response_type=token", "", None):
        out = _check(store, chain, query=query)
        assert isinstance(out, gate.ToLogin)
        assert urlsplit(out.location).path == "/login"
    assert chain.entries == [] and store.calls == []


@pytest.mark.parametrize("query", [None, "", 7])
def test_an_empty_query_resumes_the_bare_path(query: Any) -> None:
    assert gate.login_location(query) == "/login?continue=%2Fauthorize"


def test_a_query_with_no_utf8_form_resumes_the_bare_path() -> None:
    assert gate.login_location("state=\ud800") == "/login?continue=%2Fauthorize"


@pytest.mark.parametrize("value", ["", "unknown", None])
def test_an_unknown_or_absent_session_is_no_session(
    store: Sessions, chain: Chain, value: str | None
) -> None:
    assert isinstance(_check(store, chain, session=value), gate.ToLogin)
    assert chain.entries == []


def test_an_ended_session_is_no_session(store: Sessions, chain: Chain) -> None:
    value = sessions.establish(store, now=T0)  # type: ignore[arg-type]
    later = T0 + timedelta(seconds=AS_SESSION_IDLE_SECONDS)
    assert isinstance(_check(store, chain, session=value, now=later), gate.ToLogin)
    assert store.rows == {}


# --- the clock


def test_a_naive_clock_raises_before_anything_is_read(store: Sessions, chain: Chain) -> None:
    with pytest.raises(ValueError):
        _check(store, chain, session="x", authorization="Bearer y", now=datetime(2026, 10, 13))
    assert store.calls == [] and chain.entries == []


def test_the_wall_clock_is_the_default(store: Sessions, chain: Chain) -> None:
    value = sessions.establish(store)  # type: ignore[arg-type]
    assert isinstance(_check(store, chain, session=value, now=None), gate.Session)
