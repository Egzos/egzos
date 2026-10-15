# Copyright 2026 Ali Sasanian
# SPDX-License-Identifier: LicenseRef-PolyForm-Strict-1.0.0
"""The revocation endpoint's request and response, RFC 7009 §2.1–§2.2 and §9.2 clause 1
(authz/revocation_endpoint.py)."""

from __future__ import annotations

import copy
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest

from egzos._types import GENESIS_HASH, ASGrant, RefreshRecord
from egzos.authz import revocation_endpoint, tokens
from egzos.ledger import Ledger
from egzos.model import Token

T0 = datetime.now(UTC).replace(microsecond=0)
FORM = "application/x-www-form-urlencoded"
CLIENT = "egzos.io"
OTHER = "claude-ai"
OWNER = "ali"
GRANT = ASGrant(
    capabilities=["fetch"],
    scopes=["*"],
    principal="interactive",
    grant_expires_at=(T0 + timedelta(days=30)).strftime("%Y-%m-%dT%H:%M:%SZ"),
)
SILENT = revocation_endpoint.Answer(200, {})
INVALID = revocation_endpoint.Answer(400, {"error": "invalid_request"})


class State:
    """`ContainerState`'s tokens plus storage.md §3.1's refresh records, counting the reads."""

    def __init__(self) -> None:
        self.tokens: dict[str, Token] = {}
        self.refresh: dict[str, RefreshRecord] = {}
        self.reads = 0

    def put_token(self, token: Token) -> None:
        self.tokens[token.id] = copy.deepcopy(token)

    def get_token(self, token_id: str) -> Token | None:
        self.reads += 1
        return copy.deepcopy(self.tokens.get(token_id))

    def put_refresh(self, record: RefreshRecord) -> None:
        self.refresh[record["refresh_hash"]] = copy.deepcopy(record)

    def family_of_token(self, token_id: str) -> str | None:
        for row in self.refresh.values():
            if row["access_token_id"] == token_id and not row["revoked"]:
                return row["family_id"]
        return None


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


def _issued(state: State, client_id: str = CLIENT) -> tokens.Issued:
    issued = tokens.mint(
        state,  # type: ignore[arg-type]
        Ledger(Chain()),  # type: ignore[arg-type]
        grant=GRANT,
        client_id=client_id,
        owner=OWNER,
        now=T0,
    )
    assert issued is not None
    return issued


def _post(
    state: State,
    chain: Chain,
    params: list[tuple[str, Any]],
    *,
    content_type: str | None = FORM,
    authorization: str | None = None,
) -> revocation_endpoint.Answer:
    return revocation_endpoint.respond(
        state,  # type: ignore[arg-type]
        Ledger(chain),  # type: ignore[arg-type]
        params,
        content_type=content_type,
        authorization=authorization,
    )


# --- the silence rule (§9.2 clause 1) ---------------------------------------------------------


def test_a_live_token_is_revoked_with_one_token_revoke_carrying_its_family(state, chain):
    issued = _issued(state)
    answer = _post(state, chain, [("token", issued.access_token), ("client_id", CLIENT)])
    assert answer == SILENT
    assert state.tokens[issued.token.id].revoked is True
    assert [e["event"] for e in chain.entries] == ["token.revoke"]
    entry = chain.entries[0]
    assert entry["subject"] == issued.token.id
    assert entry["actor"] == CLIENT and entry["principal"] == "client"
    assert entry["details"]["family_id"] == issued.family_id
    assert issued.access_token not in repr(chain.entries)


@pytest.mark.parametrize(
    "value",
    [
        "egz_" + "A" * 26 + "_" + "x" * 43,  # well-formed, names no token
        "not-a-token",
        "\udcff",
        "x" * 10_000,
    ],
)
def test_an_unknown_or_malformed_token_gets_the_same_answer_and_appends_nothing(
    state, chain, value
):
    issued = _issued(state)
    assert _post(state, chain, [("token", value), ("client_id", CLIENT)]) == SILENT
    assert chain.entries == []
    assert state.tokens[issued.token.id].revoked is False


def test_an_already_revoked_token_gets_the_same_answer_and_no_second_token_revoke(state, chain):
    issued = _issued(state)
    params = [("token", issued.access_token), ("client_id", CLIENT)]
    assert _post(state, chain, params) == SILENT
    assert _post(state, chain, params) == SILENT
    assert [e["event"] for e in chain.entries] == ["token.revoke"]


def test_another_clients_token_is_left_alone_with_the_same_answer(state, chain):
    issued = _issued(state)
    assert _post(state, chain, [("token", issued.access_token), ("client_id", OTHER)]) == SILENT
    assert state.tokens[issued.token.id].revoked is False
    assert chain.entries == []


def test_a_refresh_token_value_revokes_nothing_yet_with_the_same_answer(state, chain):
    # #240: `ASState` has no read of a refresh record that does not spend it.
    issued = _issued(state)
    assert _post(state, chain, [("token", issued.refresh_token), ("client_id", CLIENT)]) == SILENT
    assert state.tokens[issued.token.id].revoked is False
    assert all(not row["revoked"] for row in state.refresh.values())
    assert chain.entries == []


@pytest.mark.parametrize("hint", ["access_token", "refresh_token", "bogus"])
def test_token_type_hint_is_never_read(state, chain, hint):
    issued = _issued(state)
    params = [("token", issued.access_token), ("token_type_hint", hint), ("client_id", CLIENT)]
    assert _post(state, chain, params) == SILENT
    assert state.tokens[issued.token.id].revoked is True


def test_an_unknown_parameter_is_ignored(state, chain):
    issued = _issued(state)
    params = [("token", issued.access_token), ("client_id", CLIENT), ("principal", "owner")]
    assert _post(state, chain, params) == SILENT
    assert state.tokens[issued.token.id].revoked is True


def test_the_answer_is_a_fresh_dict_each_time(state, chain):
    first = _post(state, chain, [("token", "a"), ("client_id", CLIENT)])
    first.body["leak"] = "x"
    assert _post(state, chain, [("token", "a"), ("client_id", CLIENT)]) == SILENT
    assert revocation_endpoint.REVOKED == SILENT


# --- invalid_request: decided before anything is read -----------------------------------------


@pytest.mark.parametrize(
    ("params", "content_type", "authorization"),
    [
        ([("token", "t"), ("client_id", CLIENT)], None, None),
        ([("token", "t"), ("client_id", CLIENT)], "application/json", None),
        ([("token", "t"), ("token", "u"), ("client_id", CLIENT)], FORM, None),
        ([("token", "t"), ("client_id", CLIENT), ("client_id", OTHER)], FORM, None),
        ([("token", "t"), ("client_id", CLIENT), ("x", "1"), ("x", "2")], FORM, None),
        ([("token", "t"), ("client_id", CLIENT, "extra")], FORM, None),
        ([("token", b"t"), ("client_id", CLIENT)], FORM, None),
        ([("token", "t"), ("client_id", CLIENT)], FORM, "Basic ZWd6b3MuaW86"),
        ([("token", "t"), ("client_id", CLIENT), ("client_secret", "s")], FORM, None),
        ([("token", "t"), ("client_id", CLIENT), ("client_assertion", "a")], FORM, None),
        ([("client_id", CLIENT)], FORM, None),
        ([("token", ""), ("client_id", CLIENT)], FORM, None),
        ([("token", "t")], FORM, None),
        ([("token", "t"), ("client_id", "")], FORM, None),
        ([], FORM, None),
    ],
)
def test_a_malformed_request_is_invalid_request_with_nothing_read_or_appended(
    state, chain, params, content_type, authorization
):
    issued = _issued(state)
    reads = state.reads
    answer = _post(state, chain, params, content_type=content_type, authorization=authorization)
    assert answer == INVALID
    assert state.reads == reads
    assert chain.entries == []
    assert state.tokens[issued.token.id].revoked is False


def test_client_authentication_is_refused_even_with_a_live_token(state, chain):
    issued = _issued(state)
    params = [("token", issued.access_token), ("client_id", CLIENT)]
    assert _post(state, chain, params, authorization="Bearer x") == INVALID
    assert state.tokens[issued.token.id].revoked is False


def test_the_form_content_type_takes_parameters_and_any_case(state, chain):
    issued = _issued(state)
    params = [("token", issued.access_token), ("client_id", CLIENT)]
    answer = _post(
        state, chain, params, content_type="Application/X-WWW-Form-Urlencoded; charset=utf-8"
    )
    assert answer == SILENT
    assert state.tokens[issued.token.id].revoked is True


def test_no_answer_carries_a_description(state, chain):
    for answer in (
        _post(state, chain, []),
        _post(state, chain, [("token", "t"), ("client_id", CLIENT)]),
    ):
        assert "error_description" not in answer.body
