# Copyright 2026 Ali Sasanian
# SPDX-License-Identifier: LicenseRef-PolyForm-Strict-1.0.0
"""§9.2 / §9.3 the mint, the code and device exchanges and refresh rotation (authz/tokens.py)."""

from __future__ import annotations

import copy
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest

from egzos._types import (
    AS_ACCESS_TOKEN_LIFETIME_SECONDS,
    GENESIS_HASH,
    ASGrant,
    AuthorizationCodeRecord,
    DeviceAuthorizationRecord,
    RefreshRecord,
)
from egzos.auth import token_id_of
from egzos.authz import codes, device, pkce, tokens, values
from egzos.ledger import Ledger
from egzos.model import Token

T0 = datetime(2026, 10, 12, 9, 0, 0, tzinfo=UTC)
CLIENT = "egzos.io"
OWNER = "ali"
VERIFIER = "v" * 43
REDIRECT = "https://egzos.io/connect/callback"
GRANT = ASGrant(
    capabilities=["fetch", "remember"],
    scopes=["*"],
    principal="interactive",
    grant_expires_at="2026-11-11T09:00:00Z",
)


class State:
    """storage.md §3.1's code and refresh methods plus `ContainerState`'s tokens, in memory, with
    rules 1, 3 and 4: consume spends, `redeem_refresh` returns the prior record, and
    `revoke_family` revokes the records and the `Token`s they name in one step."""

    def __init__(self) -> None:
        self.tokens: dict[str, Token] = {}
        self.refresh: dict[str, RefreshRecord] = {}
        self.codes: dict[str, AuthorizationCodeRecord] = {}
        self.devices: dict[str, DeviceAuthorizationRecord] = {}

    def put_token(self, token: Token) -> None:
        self.tokens[token.id] = copy.deepcopy(token)

    def get_token(self, token_id: str) -> Token | None:
        return copy.deepcopy(self.tokens.get(token_id))

    def put_refresh(self, record: RefreshRecord) -> None:
        self.refresh[record["refresh_hash"]] = copy.deepcopy(record)

    def redeem_refresh(self, refresh_hash: str) -> RefreshRecord | None:
        row = self.refresh.get(refresh_hash)
        if row is None:
            return None
        prior = copy.deepcopy(row)
        row["redeemed_at"] = row["redeemed_at"] or "2026-10-12T09:00:00Z"
        return prior

    def revoke_family(self, family_id: str) -> list[str]:
        ids = []
        for row in self.refresh.values():
            if row["family_id"] == family_id:
                row["revoked"] = True
                self.tokens[row["access_token_id"]].revoked = True
                ids.append(row["access_token_id"])
        return ids

    def put_code(self, record: AuthorizationCodeRecord) -> None:
        self.codes[record["code_hash"]] = record

    def consume_code(self, code_hash: str) -> AuthorizationCodeRecord | None:
        return self.codes.pop(code_hash, None)

    # §3.1 rule 2's device methods, as `test_authz_device.Devices` has them (its #214 note applies)
    def put_device(self, record: DeviceAuthorizationRecord) -> None:
        self.devices.setdefault(record["device_code_hash"], copy.deepcopy(record))

    def poll_device(self, device_code_hash: str, at: str) -> DeviceAuthorizationRecord | None:
        row = self.devices.get(device_code_hash)
        if row is None:
            return None
        prior = copy.deepcopy(row)
        row["last_polled_at"] = at
        return prior

    def get_device_by_user_code(self, user_code_hash: str) -> DeviceAuthorizationRecord | None:
        for row in self.devices.values():
            if row["user_code_hash"] == user_code_hash:
                return copy.deepcopy(row)
        return None

    def decide_device(self, device_code_hash: str, grant: ASGrant | None) -> bool:
        row = self.devices.get(device_code_hash)
        if row is None or row["decision"] != "pending":
            return False
        row["decision"] = "granted" if grant is not None else "denied"
        row["grant"] = copy.deepcopy(grant)
        return True

    def consume_device(self, device_code_hash: str) -> DeviceAuthorizationRecord | None:
        row = self.devices.get(device_code_hash)
        if row is None or row["decision"] == "pending":
            return None
        return self.devices.pop(device_code_hash)


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
def state() -> State:
    return State()


@pytest.fixture
def chain() -> Chain:
    return Chain()


def _ledger(chain: Chain) -> Ledger:
    return Ledger(chain)  # type: ignore[arg-type]


def _mint(state: State, chain: Chain, **over: Any) -> tokens.Issued | None:
    args: dict[str, Any] = {"grant": GRANT, "client_id": CLIENT, "owner": OWNER, "now": T0}
    return tokens.mint(state, _ledger(chain), **{**args, **over})  # type: ignore[arg-type]


def _refresh(state: State, chain: Chain, value: str | None, **over: Any) -> tokens.Issued | None:
    args: dict[str, Any] = {"client_id": CLIENT, "now": T0 + timedelta(minutes=50)}
    return tokens.refresh(state, _ledger(chain), refresh_token=value, **{**args, **over})  # type: ignore[arg-type]


def _events(chain: Chain) -> list[str]:
    return [e["event"] for e in chain.entries]


# --- mint ----------------------------------------------------------------------------------


def test_mint_issues_a_token_carrying_the_grant_and_an_hour(state, chain):
    issued = _mint(state, chain)
    assert issued is not None
    token = state.tokens[issued.token.id]
    assert (token.principal, token.owner, token.client) == ("interactive", OWNER, CLIENT)
    assert (token.capabilities, token.scopes) == (["fetch", "remember"], ["*"])
    assert token.expires_at == "2026-10-12T10:00:00Z"
    assert issued.expires_in == AS_ACCESS_TOKEN_LIFETIME_SECONDS == 3600
    assert token_id_of(issued.access_token) == token.id
    assert token.secret_hash == values.digest(issued.access_token)


def test_mint_stores_digests_and_appends_token_mint_with_the_family(state, chain):
    issued = _mint(state, chain)
    assert issued is not None
    (record,) = state.refresh.values()
    assert record["refresh_hash"] == values.digest(issued.refresh_token)
    assert record["family_id"] == issued.family_id and record["access_token_id"] == issued.token.id
    assert record["redeemed_at"] is None and record["revoked"] is False
    assert record["grant"] == GRANT
    (entry,) = chain.entries
    assert entry["event"] == "token.mint" and entry["subject"] == issued.token.id
    assert (entry["actor"], entry["principal"]) == (CLIENT, "client")
    assert entry["details"]["family_id"] == issued.family_id
    for secret in (issued.access_token, issued.refresh_token):
        assert secret not in repr(state.tokens) + repr(state.refresh) + repr(chain.entries)


def test_each_mint_starts_its_own_family(state, chain):
    a, b = _mint(state, chain), _mint(state, chain)
    assert a is not None and b is not None and a.family_id != b.family_id
    assert a.refresh_token != b.refresh_token and a.access_token != b.access_token


def test_the_access_token_never_outlives_its_grant(state, chain):
    soon = {**GRANT, "grant_expires_at": "2026-10-12T09:20:00Z"}
    issued = _mint(state, chain, grant=soon)
    assert issued is not None
    assert issued.token.expires_at == "2026-10-12T09:20:00Z" and issued.expires_in == 1200


@pytest.mark.parametrize(
    "over",
    [
        {"grant": {**GRANT, "grant_expires_at": "2026-10-12T09:00:00Z"}},  # expired at T0
        {"grant": {**GRANT, "grant_expires_at": "next month"}},
        {"grant": {**GRANT, "grant_expires_at": None}},
        {"grant": {**GRANT, "principal": "none"}},
        {"grant": {**GRANT, "principal": "owner"}},
        {"grant": {**GRANT, "capabilities": ["fetch", "root"]}},
        {"grant": {**GRANT, "capabilities": "fetch"}},
        {"grant": {**GRANT, "scopes": "*"}},
        {"grant": {**GRANT, "scopes": [None]}},
        {"now": datetime(2026, 10, 12, 9, 0, 0)},  # naive
    ],
)
def test_mint_refuses_and_stores_nothing(state, chain, over):
    assert _mint(state, chain, **over) is None
    assert not state.tokens and not state.refresh and not chain.entries


# --- the code exchange ----------------------------------------------------------------------


def _exchange(state: State, chain: Chain, code: str, verifier: str) -> tokens.Issued | None:
    return tokens.exchange_code(
        state,  # type: ignore[arg-type]
        _ledger(chain),
        code=code,
        client_id=CLIENT,
        redirect_uri=REDIRECT,
        code_verifier=verifier,
        owner=OWNER,
        now=T0 + timedelta(seconds=5),
    )


def _code(state: State) -> str:
    return codes.issue(
        state,  # type: ignore[arg-type]
        client_id=CLIENT,
        redirect_uri=REDIRECT,
        code_challenge=pkce.s256(VERIFIER),
        session_hash="s" * 64,
        grant=GRANT,
        now=T0,
    )


def test_exchange_code_mints_once_and_appends_token_mint(state, chain):
    code = _code(state)
    issued = _exchange(state, chain, code, VERIFIER)
    assert issued is not None and issued.token.principal == "interactive"
    assert _exchange(state, chain, code, VERIFIER) is None
    assert _events(chain) == ["token.mint"]
    assert chain.entries[0]["details"]["family_id"] == issued.family_id


def test_exchange_code_with_a_wrong_verifier_mints_nothing(state, chain):
    assert _exchange(state, chain, _code(state), "w" * 43) is None
    assert not state.tokens and not state.refresh and not chain.entries


# --- the device exchange --------------------------------------------------------------------

KEY = b"k" * 32  # a fixture device-code key; provisioning the real one is #143's
CLI = "egzos-cli"


def _pending(state: State) -> tuple[str, str]:
    """A pending device authorization issued at T0: (device_code, user_code)."""
    response = device.authorize(
        state,  # type: ignore[arg-type]
        key=KEY,
        client_id=CLI,
        scope="fetch remember node:*",
        requester_hint=None,
        verification_uri="https://box.example/device",
        now=T0,
    )
    return response["device_code"], response["user_code"]


def _decided(state: State, *, approve: bool = True) -> str:
    device_code, user_code = _pending(state)
    assert device.decide(
        state,  # type: ignore[arg-type]
        key=KEY,
        user_code=user_code,
        approve=approve,
        now=T0 + timedelta(seconds=30),
    )
    return device_code


def _exchange_device(
    state: State, chain: Chain, device_code: str | None, **over: Any
) -> tokens.Issued | str:
    args: dict[str, Any] = {"client_id": CLI, "owner": OWNER, "now": T0 + timedelta(seconds=60)}
    return tokens.exchange_device(
        state,  # type: ignore[arg-type]
        _ledger(chain),
        device_code=device_code,
        **{**args, **over},
    )


def test_exchange_device_mints_a_client_token_once(state, chain):
    device_code = _decided(state)
    issued = _exchange_device(state, chain, device_code)
    assert isinstance(issued, tokens.Issued)
    token = state.tokens[issued.token.id]
    assert (token.principal, token.owner, token.client) == ("client", OWNER, CLI)
    assert (token.capabilities, token.scopes) == (["fetch", "remember"], ["*"])
    assert _events(chain) == ["token.mint"]
    assert chain.entries[0]["details"]["family_id"] == issued.family_id
    later = T0 + timedelta(seconds=120)
    assert _exchange_device(state, chain, device_code, now=later) == "invalid_grant"
    assert _events(chain) == ["token.mint"] and len(state.tokens) == 1


def test_a_pending_authorization_mints_nothing_and_stays_pending(state, chain):
    device_code, _ = _pending(state)
    assert _exchange_device(state, chain, device_code) == "authorization_pending"
    assert not state.tokens and not state.refresh and not chain.entries
    assert len(state.devices) == 1


def test_a_denied_authorization_mints_nothing(state, chain):
    device_code = _decided(state, approve=False)
    assert _exchange_device(state, chain, device_code) == "access_denied"
    assert not state.tokens and not state.refresh and not chain.entries
    assert not state.devices  # spent


@pytest.mark.parametrize(
    "over",
    [
        {"client_id": "egzos.io"},
        {"client_id": None},
        {"device_code": "unknown-device-code"},
        {"device_code": None},
        {"now": datetime(2026, 10, 12, 9, 1, 0)},  # naive
    ],
)
def test_exchange_device_refusals_are_invalid_grant_and_mint_nothing(state, chain, over):
    args = {"device_code": _decided(state), **over}
    assert _exchange_device(state, chain, **args) == "invalid_grant"
    assert not state.tokens and not state.refresh and not chain.entries


@pytest.mark.parametrize(
    "tampered",
    [
        {"principal": "interactive"},  # §10.3: only §2's browser flow mints this
        {"principal": "owner"},
        {"grant_expires_at": "2026-10-12T09:00:30Z"},  # expired before the exchange
    ],
)
def test_a_stored_grant_the_device_flow_may_not_mint_is_spent_and_refused(state, chain, tampered):
    device_code = _decided(state)
    (row,) = state.devices.values()
    row["grant"] = {**row["grant"], **tampered}  # type: ignore[typeddict-item]
    assert _exchange_device(state, chain, device_code) == "invalid_grant"
    assert not state.tokens and not state.refresh and not chain.entries
    assert not state.devices  # spent: a retry cannot mint either


# --- refresh rotation ------------------------------------------------------------------------


def test_refresh_rotates_within_the_family_and_appends_only_the_mint(state, chain):
    first = _mint(state, chain)
    assert first is not None
    second = _refresh(state, chain, first.refresh_token)
    assert second is not None
    assert second.family_id == first.family_id
    assert second.refresh_token != first.refresh_token
    assert second.access_token != first.access_token
    assert second.token.owner == OWNER
    assert _events(chain) == ["token.mint", "token.mint"]  # rotation has no event of its own
    assert chain.entries[1]["details"]["family_id"] == first.family_id
    assert state.refresh[values.digest(first.refresh_token)]["redeemed_at"] is not None


def test_rotation_neither_widens_the_grant_nor_upgrades_the_principal(state, chain):
    narrow = ASGrant(
        capabilities=["fetch"],
        scopes=["01J0000000000000000000000A"],
        principal="client",
        grant_expires_at="2026-11-11T09:00:00Z",
    )
    first = _mint(state, chain, grant=narrow)
    assert first is not None
    second = _refresh(state, chain, first.refresh_token)
    assert second is not None
    assert second.token.principal == "client"
    assert (second.token.capabilities, second.token.scopes) == (["fetch"], narrow["scopes"])
    assert state.refresh[values.digest(second.refresh_token)]["grant"] == narrow


def test_reuse_revokes_the_whole_family_and_writes_token_revoke(state, chain):
    first = _mint(state, chain)
    assert first is not None
    second = _refresh(state, chain, first.refresh_token)
    assert second is not None
    bystander = _mint(state, chain)  # another family: untouched
    assert bystander is not None
    assert _refresh(state, chain, first.refresh_token) is None  # replay: race or theft
    assert state.tokens[first.token.id].revoked and state.tokens[second.token.id].revoked
    assert not state.tokens[bystander.token.id].revoked
    revokes = [e for e in chain.entries if e["event"] == "token.revoke"]
    assert {e["subject"] for e in revokes} == {first.token.id, second.token.id}
    assert all(e["details"]["family_id"] == first.family_id for e in revokes)
    assert all(e["principal"] == "client" for e in revokes)
    # the thief's newest value is dead too, and a revoked family appends nothing more
    before = len(chain.entries)
    assert _refresh(state, chain, second.refresh_token) is None
    assert len(chain.entries) == before


@pytest.mark.parametrize("client_id", ["other", None, "égzos.io"])
def test_another_clients_refresh_is_refused_and_spent(state, chain, client_id):
    first = _mint(state, chain)
    assert first is not None
    assert _refresh(state, chain, first.refresh_token, client_id=client_id) is None
    assert _events(chain) == ["token.mint"]
    # spent by that attempt: the holder's own retry is reuse, and the family goes
    assert _refresh(state, chain, first.refresh_token) is None
    assert state.tokens[first.token.id].revoked


def test_refresh_after_the_grant_expires_is_refused(state, chain):
    first = _mint(state, chain)
    assert first is not None
    late = datetime(2026, 11, 11, 9, 0, 0, tzinfo=UTC)
    assert _refresh(state, chain, first.refresh_token, now=late) is None
    assert _events(chain) == ["token.mint"]


@pytest.mark.parametrize("value", [None, "", 7, "unknown-refresh-value"])
def test_unknown_and_malformed_refresh_values_are_refused_alike(state, chain, value):
    assert _mint(state, chain) is not None
    assert _refresh(state, chain, value) is None
    assert _events(chain) == ["token.mint"]


def test_refresh_with_a_naive_clock_spends_nothing(state, chain):
    first = _mint(state, chain)
    assert first is not None
    assert _refresh(state, chain, first.refresh_token, now=datetime(2026, 10, 12, 9, 50)) is None
    assert state.refresh[values.digest(first.refresh_token)]["redeemed_at"] is None


def test_refresh_whose_token_record_is_gone_is_refused(state, chain):
    first = _mint(state, chain)
    assert first is not None
    del state.tokens[first.token.id]
    assert _refresh(state, chain, first.refresh_token) is None
    assert _events(chain) == ["token.mint"]
