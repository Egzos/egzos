# Copyright 2026 Ali Sasanian
# SPDX-License-Identifier: LicenseRef-PolyForm-Strict-1.0.0
"""
`SqliteBackend`'s `ASState` — clients, codes, decided requests, device authorizations and refresh
chains (storage.md §3.1, draft binding on #173; issue #262 slices 2-3).

Every atomicity claim is checked with **two `SqliteBackend` instances on one file** (two
connections), per the issue's instruction, not two calls on one connection.
"""

from __future__ import annotations

import inspect
import threading

import pytest

from egzos._types import (
    ASGrant,
    ASState,
    AuthorizationCodeRecord,
    ClientRegistration,
    DecidedRequestRecord,
    DeviceAuthorizationRecord,
    RefreshRecord,
)
from egzos.backends.sqlite import SqliteBackend
from egzos.model import Token

#: Every method `ASState` declares, grouped as storage.md §3.1 groups them.
AS_STATE_CLIENTS = frozenset({"put_client", "get_client", "remove_client"})
AS_STATE_CODES = frozenset({"put_code", "consume_code"})
AS_STATE_DEVICES = frozenset(
    {"put_device", "poll_device", "get_device_by_user_code", "decide_device", "consume_device"}
)
AS_STATE_REFRESH = frozenset({"put_refresh", "redeem_refresh", "family_of_token", "revoke_family"})
AS_STATE_DECIDED = frozenset({"put_decided", "get_decided", "claim_resubmission"})
SLICE_METHODS = (
    AS_STATE_CLIENTS | AS_STATE_CODES | AS_STATE_DEVICES | AS_STATE_REFRESH | AS_STATE_DECIDED
)

CLIENT_ID = "client-1"
CODE_HASH = "c" * 64
SESSION_HASH = "a" * 64
REQUEST_KEY = "r" * 64
DEVICE_CODE_HASH = "d" * 64
USER_CODE_HASH = "u" * 64
REFRESH_HASH = "f" * 64
FAMILY_ID = "family-1"
ACCESS_TOKEN_ID = "token-1"


def _client(**over: object) -> ClientRegistration:
    base: dict[str, object] = {
        "client_id": CLIENT_ID,
        "client_name": "Test Client",
        "client_type": "browser",
        "redirect_uris": ["http://127.0.0.1/callback"],
        "registered_at": "2026-10-12T09:00:00Z",
    }
    base.update(over)
    return base  # type: ignore[return-value]


def _grant(**over: object) -> ASGrant:
    base: dict[str, object] = {
        "capabilities": ["fetch"],
        "scopes": ["fetch"],
        "principal": "interactive",
        "grant_expires_at": "2026-11-11T09:00:00Z",
    }
    base.update(over)
    return base  # type: ignore[return-value]


def _code(**over: object) -> AuthorizationCodeRecord:
    base: dict[str, object] = {
        "code_hash": CODE_HASH,
        "client_id": CLIENT_ID,
        "redirect_uri": "http://127.0.0.1/callback",
        "code_challenge": "challenge",
        "session_hash": SESSION_HASH,
        "grant": _grant(),
        "expires_at": "2026-10-12T09:01:00Z",
    }
    base.update(over)
    return base  # type: ignore[return-value]


def _decided(**over: object) -> DecidedRequestRecord:
    base: dict[str, object] = {
        "request_key": REQUEST_KEY,
        "session_hash": SESSION_HASH,
        "decision": "granted",
        "decided_at": "2026-10-12T09:00:00Z",
        "resubmission_seen": False,
    }
    base.update(over)
    return base  # type: ignore[return-value]


def _device(**over: object) -> DeviceAuthorizationRecord:
    base: dict[str, object] = {
        "device_code_hash": DEVICE_CODE_HASH,
        "user_code_hash": USER_CODE_HASH,
        "client_id": CLIENT_ID,
        "requested": {"capabilities": ["fetch"], "scopes": ["fetch"]},
        "requester_hint": "ali-laptop",
        "decision": "pending",
        "grant": None,
        "expires_at": "2026-10-12T09:05:00Z",
        "last_polled_at": None,
    }
    base.update(over)
    return base  # type: ignore[return-value]


def _token(token_id: str = ACCESS_TOKEN_ID) -> Token:
    return Token(
        id=token_id, principal="interactive", owner="ali", client=CLIENT_ID,
        capabilities=["fetch"], scopes=["*"],
    )


def _refresh(**over: object) -> RefreshRecord:
    base: dict[str, object] = {
        "refresh_hash": REFRESH_HASH,
        "family_id": FAMILY_ID,
        "client_id": CLIENT_ID,
        "access_token_id": ACCESS_TOKEN_ID,
        "grant": _grant(),
        "redeemed_at": None,
        "revoked": False,
    }
    base.update(over)
    return base  # type: ignore[return-value]


@pytest.fixture
def backend(tmp_path):
    return SqliteBackend(tmp_path / "container.db")


def test_method_set_matches_the_protocol():
    """`SqliteBackend` offers every method this slice adds, with no renaming."""
    for name in SLICE_METHODS:
        assert callable(getattr(SqliteBackend, name, None)), name


def test_sqlite_backend_conforms_to_as_state_signatures():
    """Each method's own parameter names match `ASState`'s, so a caller typed against the
    Protocol calls `SqliteBackend` with the same keywords."""
    for name in SLICE_METHODS:
        protocol_params = list(inspect.signature(getattr(ASState, name)).parameters)
        backend_params = list(inspect.signature(getattr(SqliteBackend, name)).parameters)
        assert backend_params == protocol_params, name


# -- clients ----------------------------------------------------------------------------------


def test_put_then_get_client(backend: SqliteBackend):
    backend.put_client(_client())
    assert backend.get_client(CLIENT_ID) == _client()


def test_get_client_is_none_for_an_absent_id(backend: SqliteBackend):
    assert backend.get_client("unknown") is None


def test_put_client_amends_an_existing_entry(backend: SqliteBackend):
    """§5: `put_client` is add AND amend — a second put on the same `client_id` replaces the
    entry whole, it does not merge or refuse."""
    backend.put_client(_client())
    backend.put_client(_client(client_name="Renamed", redirect_uris=["http://127.0.0.1/cb2"]))
    record = backend.get_client(CLIENT_ID)
    assert record["client_name"] == "Renamed"
    assert record["redirect_uris"] == ["http://127.0.0.1/cb2"]


def test_remove_client_true_then_false(backend: SqliteBackend):
    backend.put_client(_client())
    assert backend.remove_client(CLIENT_ID) is True
    assert backend.remove_client(CLIENT_ID) is False
    assert backend.get_client(CLIENT_ID) is None


def test_remove_client_is_false_for_an_absent_id(backend: SqliteBackend):
    assert backend.remove_client("unknown") is False


def test_a_client_survives_a_restart(tmp_path):
    """One substrate: a reopened backend on the same path finds the registration intact."""
    path = tmp_path / "container.db"
    SqliteBackend(path).put_client(_client())
    reopened = SqliteBackend(path)
    assert reopened.get_client(CLIENT_ID) == _client()


# -- codes --------------------------------------------------------------------------------------


def test_put_then_consume_code(backend: SqliteBackend):
    backend.put_code(_code())
    assert backend.consume_code(CODE_HASH) == _code()


def test_consume_code_is_none_for_an_absent_hash(backend: SqliteBackend):
    assert backend.consume_code("unknown") is None


def test_consume_code_spends_the_code(backend: SqliteBackend):
    """§3.1 rule 1: the code is spent on the first redemption attempt; every later call misses."""
    backend.put_code(_code())
    assert backend.consume_code(CODE_HASH) is not None
    assert backend.consume_code(CODE_HASH) is None


def test_consume_code_does_not_judge_expiry(backend: SqliteBackend):
    """§3.1 rule 1: `consume_code` never looks at `expires_at` — Trust re-checks what it gets
    back. An already-expired record is still returned, not silently dropped."""
    backend.put_code(_code(expires_at="2000-01-01T00:00:00Z"))
    record = backend.consume_code(CODE_HASH)
    assert record is not None
    assert record["expires_at"] == "2000-01-01T00:00:00Z"


def test_a_code_survives_a_restart(tmp_path):
    path = tmp_path / "container.db"
    SqliteBackend(path).put_code(_code())
    reopened = SqliteBackend(path)
    assert reopened.consume_code(CODE_HASH) == _code()


def test_consume_code_is_atomic_across_two_connections(tmp_path):
    """Of two concurrent `consume_code` calls on the same `code_hash`, exactly one observes the
    record before the other's delete — the loser gets `None`, never a torn or duplicated read."""
    path = tmp_path / "container.db"
    a = SqliteBackend(path)
    a.put_code(_code())
    b = SqliteBackend(path)

    results: list[AuthorizationCodeRecord | None] = []
    lock = threading.Lock()
    barrier = threading.Barrier(2)

    def consume(conn: SqliteBackend) -> None:
        barrier.wait()
        record = conn.consume_code(CODE_HASH)
        with lock:
            results.append(record)

    t1 = threading.Thread(target=consume, args=(a,))
    t2 = threading.Thread(target=consume, args=(b,))
    t1.start()
    t2.start()
    t1.join()
    t2.join()

    winners = [r for r in results if r is not None]
    losers = [r for r in results if r is None]
    assert len(winners) == 1
    assert len(losers) == 1
    assert winners[0] == _code()
    assert a.consume_code(CODE_HASH) is None  # spent either way


# -- device authorizations ---------------------------------------------------------------------


def test_put_then_get_device_by_user_code(backend: SqliteBackend):
    backend.put_device(_device())
    assert backend.get_device_by_user_code(USER_CODE_HASH) == _device()


def test_get_device_by_user_code_is_none_for_an_absent_hash(backend: SqliteBackend):
    assert backend.get_device_by_user_code("unknown") is None


def test_put_device_is_insert_only(backend: SqliteBackend):
    """§3.1 rule 2: a put on an existing `device_code_hash` changes nothing."""
    backend.put_device(_device())
    backend.put_device(_device(client_id="other-client"))
    assert backend.get_device_by_user_code(USER_CODE_HASH)["client_id"] == CLIENT_ID


def test_a_device_survives_a_restart(tmp_path):
    path = tmp_path / "container.db"
    SqliteBackend(path).put_device(_device())
    reopened = SqliteBackend(path)
    assert reopened.get_device_by_user_code(USER_CODE_HASH) == _device()


def test_poll_device_sets_last_polled_at_and_returns_the_prior_record(backend: SqliteBackend):
    backend.put_device(_device())
    prior = backend.poll_device(DEVICE_CODE_HASH, "2026-10-12T09:01:00Z")
    assert prior == _device()  # as it stood BEFORE the call
    assert backend.get_device_by_user_code(USER_CODE_HASH)["last_polled_at"] == (
        "2026-10-12T09:01:00Z"
    )


def test_poll_device_is_none_for_an_absent_hash(backend: SqliteBackend):
    assert backend.poll_device("unknown", "2026-10-12T09:01:00Z") is None


def test_decide_device_moves_pending_to_decided_once(backend: SqliteBackend):
    backend.put_device(_device())
    grant = _grant()
    assert backend.decide_device(DEVICE_CODE_HASH, grant) is True
    record = backend.get_device_by_user_code(USER_CODE_HASH)
    assert record["decision"] == "granted"
    assert record["grant"] == grant
    assert backend.decide_device(DEVICE_CODE_HASH, grant) is False  # already decided


def test_decide_device_denied_for_a_none_grant(backend: SqliteBackend):
    backend.put_device(_device())
    assert backend.decide_device(DEVICE_CODE_HASH, None) is True
    record = backend.get_device_by_user_code(USER_CODE_HASH)
    assert record["decision"] == "denied"
    assert record["grant"] is None


def test_decide_device_is_false_for_an_absent_hash(backend: SqliteBackend):
    assert backend.decide_device("unknown", _grant()) is False


def test_decide_device_sets_only_decision_and_grant(backend: SqliteBackend):
    backend.put_device(_device())
    backend.decide_device(DEVICE_CODE_HASH, _grant())
    record = backend.get_device_by_user_code(USER_CODE_HASH)
    assert record["requested"] == _device()["requested"]
    assert record["requester_hint"] == _device()["requester_hint"]
    assert record["last_polled_at"] is None


def test_consume_device_is_none_while_pending(backend: SqliteBackend):
    backend.put_device(_device())
    assert backend.consume_device(DEVICE_CODE_HASH) is None
    assert backend.get_device_by_user_code(USER_CODE_HASH) is not None  # a poll spends nothing


def test_consume_device_spends_a_decided_record_once(backend: SqliteBackend):
    backend.put_device(_device())
    backend.decide_device(DEVICE_CODE_HASH, _grant())
    record = backend.consume_device(DEVICE_CODE_HASH)
    assert record is not None
    assert record["decision"] == "granted"
    assert backend.consume_device(DEVICE_CODE_HASH) is None
    assert backend.get_device_by_user_code(USER_CODE_HASH) is None


def test_consume_device_is_none_for_an_absent_hash(backend: SqliteBackend):
    assert backend.consume_device("unknown") is None


def test_put_device_is_atomic_across_two_connections(tmp_path):
    """Of two concurrent `put_device` calls on the same `device_code_hash`, the first insert
    wins and the second changes nothing — never a torn or duplicated row."""
    path = tmp_path / "container.db"
    a = SqliteBackend(path)
    b = SqliteBackend(path)

    barrier = threading.Barrier(2)

    def put(conn: SqliteBackend, client_id: str) -> None:
        barrier.wait()
        conn.put_device(_device(client_id=client_id))

    t1 = threading.Thread(target=put, args=(a, "client-a"))
    t2 = threading.Thread(target=put, args=(b, "client-b"))
    t1.start()
    t2.start()
    t1.join()
    t2.join()

    record = a.get_device_by_user_code(USER_CODE_HASH)
    assert record["client_id"] in ("client-a", "client-b")  # exactly one insert survives


def test_poll_device_is_atomic_across_two_connections(tmp_path):
    """Of two concurrent `poll_device` calls on the same key, exactly one observes the record
    as it stood before either call (`last_polled_at` still `None`) — the other's write cannot
    be torn into the first's read, so the loser sees the winner's stamp, never a half-write."""
    path = tmp_path / "container.db"
    a = SqliteBackend(path)
    a.put_device(_device())
    b = SqliteBackend(path)

    results: list[DeviceAuthorizationRecord | None] = []
    lock = threading.Lock()
    barrier = threading.Barrier(2)

    def poll(conn: SqliteBackend, at: str) -> None:
        barrier.wait()
        prior = conn.poll_device(DEVICE_CODE_HASH, at)
        with lock:
            results.append(prior)

    t1 = threading.Thread(target=poll, args=(a, "2026-10-12T09:01:00Z"))
    t2 = threading.Thread(target=poll, args=(b, "2026-10-12T09:02:00Z"))
    t1.start()
    t2.start()
    t1.join()
    t2.join()

    first = [r for r in results if r["last_polled_at"] is None]
    second = [r for r in results if r["last_polled_at"] is not None]
    assert len(first) == 1
    assert len(second) == 1
    assert second[0]["last_polled_at"] in ("2026-10-12T09:01:00Z", "2026-10-12T09:02:00Z")
    record = a.get_device_by_user_code(USER_CODE_HASH)
    assert record["last_polled_at"] in ("2026-10-12T09:01:00Z", "2026-10-12T09:02:00Z")


def test_decide_device_is_atomic_across_two_connections(tmp_path):
    """Of two concurrent `decide_device` calls on the same pending record, exactly one moves it
    out of pending — one approval, one request (§3 mitigation 3)."""
    path = tmp_path / "container.db"
    a = SqliteBackend(path)
    a.put_device(_device())
    b = SqliteBackend(path)

    results: list[bool] = []
    lock = threading.Lock()
    barrier = threading.Barrier(2)

    def decide(conn: SqliteBackend, grant: ASGrant | None) -> None:
        barrier.wait()
        result = conn.decide_device(DEVICE_CODE_HASH, grant)
        with lock:
            results.append(result)

    t1 = threading.Thread(target=decide, args=(a, _grant()))
    t2 = threading.Thread(target=decide, args=(b, None))
    t1.start()
    t2.start()
    t1.join()
    t2.join()

    assert sorted(results) == [False, True]


def test_consume_device_is_atomic_across_two_connections(tmp_path):
    """Of two concurrent `consume_device` calls on the same decided record, exactly one spends
    it and the other finds it already gone."""
    path = tmp_path / "container.db"
    a = SqliteBackend(path)
    a.put_device(_device())
    a.decide_device(DEVICE_CODE_HASH, _grant())
    b = SqliteBackend(path)

    results: list[DeviceAuthorizationRecord | None] = []
    lock = threading.Lock()
    barrier = threading.Barrier(2)

    def consume(conn: SqliteBackend) -> None:
        barrier.wait()
        record = conn.consume_device(DEVICE_CODE_HASH)
        with lock:
            results.append(record)

    t1 = threading.Thread(target=consume, args=(a,))
    t2 = threading.Thread(target=consume, args=(b,))
    t1.start()
    t2.start()
    t1.join()
    t2.join()

    winners = [r for r in results if r is not None]
    losers = [r for r in results if r is None]
    assert len(winners) == 1
    assert len(losers) == 1


# -- refresh chains -----------------------------------------------------------------------------


def test_put_then_redeem_refresh(backend: SqliteBackend):
    backend.put_refresh(_refresh())
    assert backend.redeem_refresh(REFRESH_HASH) == _refresh()


def test_put_refresh_does_not_reset_redeemed_at(backend: SqliteBackend):
    """A second put on an existing `refresh_hash` changes nothing, like `put_device`: it can
    never reset `redeemed_at` and silence reuse detection."""
    backend.put_refresh(_refresh())
    backend.redeem_refresh(REFRESH_HASH)
    backend.put_refresh(_refresh(redeemed_at=None))
    record = backend.redeem_refresh(REFRESH_HASH)
    assert record["redeemed_at"] is not None


def test_put_refresh_does_not_un_revoke_an_existing_record(backend: SqliteBackend):
    """A second put on an existing `refresh_hash` can never un-revoke the row either."""
    backend.put_refresh(_refresh(revoked=True))
    backend.put_refresh(_refresh(revoked=False))
    assert backend.family_of_token(ACCESS_TOKEN_ID) is None


def test_redeem_refresh_is_none_for_an_absent_hash(backend: SqliteBackend):
    assert backend.redeem_refresh("unknown") is None


def test_redeem_refresh_marks_the_record_redeemed(backend: SqliteBackend):
    backend.put_refresh(_refresh())
    backend.redeem_refresh(REFRESH_HASH)
    record = backend.redeem_refresh(REFRESH_HASH)
    assert record["redeemed_at"] is not None  # visible reuse, never collapsed to None


def test_redeem_refresh_keeps_the_first_redeemed_at(backend: SqliteBackend):
    """A second redemption attempt reports reuse but does not overwrite the original stamp."""
    backend.put_refresh(_refresh())
    first = backend.redeem_refresh(REFRESH_HASH)
    assert first["redeemed_at"] is None
    second = backend.redeem_refresh(REFRESH_HASH)
    third = backend.redeem_refresh(REFRESH_HASH)
    assert second["redeemed_at"] is not None
    assert second["redeemed_at"] == third["redeemed_at"]


def test_a_refresh_record_survives_a_restart(tmp_path):
    path = tmp_path / "container.db"
    SqliteBackend(path).put_refresh(_refresh())
    reopened = SqliteBackend(path)
    assert reopened.redeem_refresh(REFRESH_HASH) == _refresh()


def test_redeem_refresh_is_atomic_across_two_connections(tmp_path):
    """Of two concurrent `redeem_refresh` calls on the same key, exactly one observes the record
    with `redeemed_at` still `None` — the loser's return already carries the winner's stamp,
    which is reuse, correctly detected rather than torn."""
    path = tmp_path / "container.db"
    a = SqliteBackend(path)
    a.put_refresh(_refresh())
    b = SqliteBackend(path)

    results: list[RefreshRecord] = []
    lock = threading.Lock()
    barrier = threading.Barrier(2)

    def redeem(conn: SqliteBackend) -> None:
        barrier.wait()
        record = conn.redeem_refresh(REFRESH_HASH)
        with lock:
            results.append(record)

    t1 = threading.Thread(target=redeem, args=(a,))
    t2 = threading.Thread(target=redeem, args=(b,))
    t1.start()
    t2.start()
    t1.join()
    t2.join()

    fresh = [r for r in results if r["redeemed_at"] is None]
    reused = [r for r in results if r["redeemed_at"] is not None]
    assert len(fresh) == 1
    assert len(reused) == 1


def test_family_of_token_is_none_for_an_absent_token(backend: SqliteBackend):
    assert backend.family_of_token("unknown") is None


def test_family_of_token_finds_the_family(backend: SqliteBackend):
    backend.put_refresh(_refresh())
    assert backend.family_of_token(ACCESS_TOKEN_ID) == FAMILY_ID


def test_family_of_token_is_none_for_a_revoked_family(backend: SqliteBackend):
    """Silence-not-errors: a revoked family reads as `None`, like any other plain getter."""
    backend.put_token(_token())
    backend.put_refresh(_refresh())
    backend.revoke_family(FAMILY_ID)
    assert backend.family_of_token(ACCESS_TOKEN_ID) is None


def test_revoke_family_revokes_the_refresh_record_and_its_token(backend: SqliteBackend):
    backend.put_token(_token())
    backend.put_refresh(_refresh())
    revoked_ids = backend.revoke_family(FAMILY_ID)
    assert revoked_ids == [ACCESS_TOKEN_ID]
    assert backend.get_token(ACCESS_TOKEN_ID).revoked is True
    assert backend.redeem_refresh(REFRESH_HASH)["revoked"] is True


def test_revoke_family_is_idempotent_a_second_call_returns_nothing(
    backend: SqliteBackend,
):
    """Until #214 items 4/5 are answered: a family already revoked returns `[]`, so a replayed
    reuse never double-fires `token.revoke` for the same token."""
    backend.put_token(_token())
    backend.put_refresh(_refresh())
    assert backend.revoke_family(FAMILY_ID) == [ACCESS_TOKEN_ID]
    assert backend.revoke_family(FAMILY_ID) == []


def test_revoke_family_does_not_return_a_token_already_revoked_on_its_own(
    backend: SqliteBackend,
):
    """A token first revoked on its own (`authz/revoke.py::_revoke` leaves the refresh row
    unrevoked) must not come back when its family is later revoked for reuse, or Trust would
    write a second `token.revoke` for it, which §9.2 forbids ("written once")."""
    token = _token()
    backend.put_token(token)
    backend.put_refresh(_refresh())
    token.revoked = True
    backend.put_token(token)

    assert backend.revoke_family(FAMILY_ID) == []
    assert backend.get_token(ACCESS_TOKEN_ID).revoked is True
    assert backend.redeem_refresh(REFRESH_HASH)["revoked"] is True


def test_revoke_family_does_not_return_an_id_whose_token_is_absent(backend: SqliteBackend):
    """An id whose `Token` is absent (`get_token` -> `None`) must not be returned either, so a
    caller cannot be told a token was revoked when none such exists."""
    backend.put_refresh(_refresh())
    assert backend.revoke_family(FAMILY_ID) == []
    assert backend.redeem_refresh(REFRESH_HASH)["revoked"] is True


def test_revoke_family_is_empty_for_an_unknown_family(backend: SqliteBackend):
    assert backend.revoke_family("unknown") == []


def test_revoke_family_only_touches_its_own_family(backend: SqliteBackend):
    other_token = "token-2"
    backend.put_token(_token())
    backend.put_token(_token(other_token))
    backend.put_refresh(_refresh())
    backend.put_refresh(
        _refresh(refresh_hash="g" * 64, family_id="family-2", access_token_id=other_token)
    )
    assert backend.revoke_family(FAMILY_ID) == [ACCESS_TOKEN_ID]
    assert backend.get_token(other_token).revoked is False


def test_revoke_family_is_atomic_across_two_connections(tmp_path):
    """Of two concurrent `revoke_family` calls on the same family, exactly one observes the
    unrevoked records and does the revoking; the other finds the family already gone and
    returns `[]`, never double-revoking the token."""
    path = tmp_path / "container.db"
    a = SqliteBackend(path)
    a.put_token(_token())
    a.put_refresh(_refresh())
    b = SqliteBackend(path)

    results: list[list[str]] = []
    lock = threading.Lock()
    barrier = threading.Barrier(2)

    def revoke(conn: SqliteBackend) -> None:
        barrier.wait()
        ids = conn.revoke_family(FAMILY_ID)
        with lock:
            results.append(ids)

    t1 = threading.Thread(target=revoke, args=(a,))
    t2 = threading.Thread(target=revoke, args=(b,))
    t1.start()
    t2.start()
    t1.join()
    t2.join()

    winners = [r for r in results if r == [ACCESS_TOKEN_ID]]
    losers = [r for r in results if r == []]
    assert len(winners) == 1
    assert len(losers) == 1
    assert a.get_token(ACCESS_TOKEN_ID).revoked is True


# -- decided requests ---------------------------------------------------------------------------


def test_put_then_get_decided(backend: SqliteBackend):
    backend.put_decided(_decided())
    assert backend.get_decided(REQUEST_KEY) == _decided()


def test_get_decided_is_none_for_an_absent_key(backend: SqliteBackend):
    assert backend.get_decided("unknown") is None


def test_put_decided_is_insert_only(backend: SqliteBackend):
    """#226: a put on an existing `request_key` changes nothing."""
    backend.put_decided(_decided())
    backend.put_decided(_decided(decision="denied"))
    assert backend.get_decided(REQUEST_KEY)["decision"] == "granted"


def test_a_decided_request_survives_a_restart(tmp_path):
    path = tmp_path / "container.db"
    SqliteBackend(path).put_decided(_decided())
    reopened = SqliteBackend(path)
    assert reopened.get_decided(REQUEST_KEY) == _decided()


def test_claim_resubmission_true_once_then_false(backend: SqliteBackend):
    backend.put_decided(_decided())
    assert backend.claim_resubmission(SESSION_HASH, REQUEST_KEY) is True
    assert backend.claim_resubmission(SESSION_HASH, REQUEST_KEY) is False


def test_claim_resubmission_sets_resubmission_seen(backend: SqliteBackend):
    backend.put_decided(_decided())
    backend.claim_resubmission(SESSION_HASH, REQUEST_KEY)
    assert backend.get_decided(REQUEST_KEY)["resubmission_seen"] is True


def test_claim_resubmission_is_false_for_an_unrecorded_request_key(backend: SqliteBackend):
    assert backend.claim_resubmission(SESSION_HASH, "unknown") is False


def test_claim_resubmission_is_false_for_a_mismatched_session(backend: SqliteBackend):
    """§11.0 substep 1: the claim is per deciding session — another session's claim misses."""
    backend.put_decided(_decided())
    assert backend.claim_resubmission("b" * 64, REQUEST_KEY) is False
    # and the real session can still claim it afterwards
    assert backend.claim_resubmission(SESSION_HASH, REQUEST_KEY) is True


def test_claim_resubmission_is_atomic_across_two_connections(tmp_path):
    """Of two concurrent claims on the same `(session_hash, request_key)`, exactly one observes
    `resubmission_seen` as still unset."""
    path = tmp_path / "container.db"
    a = SqliteBackend(path)
    a.put_decided(_decided())
    b = SqliteBackend(path)

    results: list[bool] = []
    lock = threading.Lock()
    barrier = threading.Barrier(2)

    def claim(conn: SqliteBackend) -> None:
        barrier.wait()
        result = conn.claim_resubmission(SESSION_HASH, REQUEST_KEY)
        with lock:
            results.append(result)

    t1 = threading.Thread(target=claim, args=(a,))
    t2 = threading.Thread(target=claim, args=(b,))
    t1.start()
    t2.start()
    t1.join()
    t2.join()

    assert sorted(results) == [False, True]
    assert a.get_decided(REQUEST_KEY)["resubmission_seen"] is True
