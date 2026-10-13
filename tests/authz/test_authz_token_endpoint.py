# Copyright 2026 Ali Sasanian
# SPDX-License-Identifier: LicenseRef-PolyForm-Strict-1.0.0
"""The token endpoint's request and response, RFC 6749 §3.2 and §5 (authz/token_endpoint.py)."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from test_authz_tokens import Chain, State  # the fakes `tokens` is tested with: one, not two

from egzos._types import AS_METADATA_CLOSED_VALUES, ASGrant
from egzos.auth import token_id_of
from egzos.authz import codes, device, pkce, token_endpoint
from egzos.authz.token_endpoint import CODE_GRANT, DEVICE_GRANT, REFRESH_GRANT
from egzos.ledger import Ledger

T0 = datetime(2026, 10, 12, 9, 0, 0, tzinfo=UTC)
FORM = "application/x-www-form-urlencoded"
OWNER = "self"
CLIENT = "egzos.io"
CLI = "egzos-cli"
REDIRECT = "https://egzos.io/connect/callback"
VERIFIER = "v" * 43
KEY = b"k" * 32  # a fixture device-code key; provisioning the real one is #143's
GRANT = ASGrant(
    capabilities=["fetch", "remember"],
    scopes=["*"],
    principal="interactive",
    grant_expires_at="2026-11-11T09:00:00Z",
)


@pytest.fixture
def state() -> State:
    return State()


@pytest.fixture
def chain() -> Chain:
    return Chain()


def _post(
    state: State,
    chain: Chain,
    params: list[tuple[str, str]],
    *,
    content_type: str | None = FORM,
    authorization: str | None = None,
    now: datetime = T0 + timedelta(seconds=5),
) -> token_endpoint.Answer:
    return token_endpoint.respond(
        state,  # type: ignore[arg-type]
        Ledger(chain),  # type: ignore[arg-type]
        params,
        content_type=content_type,
        authorization=authorization,
        owner=OWNER,
        now=now,
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


def _code_form(code: str, **over: str) -> list[tuple[str, str]]:
    fields = {
        "grant_type": CODE_GRANT,
        "code": code,
        "client_id": CLIENT,
        "redirect_uri": REDIRECT,
        "code_verifier": VERIFIER,
        **over,
    }
    return list(fields.items())


def _redeemed(state: State, chain: Chain) -> dict[str, Any]:
    answer = _post(state, chain, _code_form(_code(state)))
    assert answer.status == 200
    return answer.body


# --- the authorization_code grant ------------------------------------------------------------


def test_the_code_grant_answers_rfc_6749_5_1_and_mints_for_the_container_owner(state, chain):
    body = _redeemed(state, chain)
    assert set(body) == {"access_token", "token_type", "expires_in", "refresh_token"}
    assert body["token_type"] == "Bearer" and body["expires_in"] == 3600
    token = state.tokens[token_id_of(body["access_token"])]
    assert (token.owner, token.client, token.principal) == (OWNER, CLIENT, "interactive")
    assert [e["event"] for e in chain.entries] == ["token.mint"]


def test_owner_comes_from_the_container_never_the_form(state, chain):
    answer = _post(state, chain, [*_code_form(_code(state)), ("owner", "mallory")])
    assert answer.status == 200
    (token,) = state.tokens.values()
    assert token.owner == OWNER


def test_a_principal_parameter_is_ignored_and_upgrades_nothing(state, chain):
    grant = {**GRANT, "principal": "client"}
    code = codes.issue(
        state,  # type: ignore[arg-type]
        client_id=CLIENT,
        redirect_uri=REDIRECT,
        code_challenge=pkce.s256(VERIFIER),
        session_hash="s" * 64,
        grant=grant,  # type: ignore[arg-type]
        now=T0,
    )
    assert _post(state, chain, [*_code_form(code), ("principal", "interactive")]).status == 200
    (token,) = state.tokens.values()
    assert token.principal == "client"


@pytest.mark.parametrize(
    "over",
    [
        {"code_verifier": "w" * 43},
        {"code_verifier": ""},  # omitted
        {"client_id": "fork.example"},
        {"redirect_uri": REDIRECT + "/"},
        {"redirect_uri": ""},
    ],
)
def test_a_code_with_any_binding_wrong_is_invalid_grant_and_spent(state, chain, over):
    code = _code(state)
    answer = _post(state, chain, _code_form(code, **over))
    assert (answer.status, answer.body) == (400, {"error": "invalid_grant"})
    # §2: the first attempt spends the code, so the right request afterwards finds nothing.
    again = _post(state, chain, _code_form(code))
    assert again.body == {"error": "invalid_grant"}
    assert not state.tokens and not chain.entries


@pytest.mark.parametrize("code", ["", "not-a-code", "é" * 8, "\udc80"])
def test_unknown_missing_and_odd_codes_are_one_invalid_grant(state, chain, code):
    answer = _post(state, chain, _code_form(code))
    assert (answer.status, answer.body) == (400, {"error": "invalid_grant"})
    assert not chain.entries


def test_an_expired_code_is_refused_like_an_unknown_one(state, chain):
    answer = _post(state, chain, _code_form(_code(state)), now=T0 + timedelta(seconds=60))
    assert answer.body == _post(state, chain, _code_form("unknown")).body


def test_a_second_redemption_is_invalid_grant(state, chain):
    code = _code(state)
    assert _post(state, chain, _code_form(code)).status == 200
    assert _post(state, chain, _code_form(code)).body == {"error": "invalid_grant"}
    assert [e["event"] for e in chain.entries] == ["token.mint"]


# --- the refresh_token grant -----------------------------------------------------------------


def _refresh_form(value: str, **over: str) -> list[tuple[str, str]]:
    fields = {"grant_type": REFRESH_GRANT, "refresh_token": value, "client_id": CLIENT, **over}
    return list(fields.items())


def test_refresh_rotates_and_answers_a_new_pair(state, chain):
    first = _redeemed(state, chain)
    answer = _post(state, chain, _refresh_form(first["refresh_token"]))
    assert answer.status == 200
    assert answer.body["refresh_token"] != first["refresh_token"]
    assert answer.body["access_token"] != first["access_token"]
    assert [e["event"] for e in chain.entries] == ["token.mint", "token.mint"]


def test_refresh_reuse_is_invalid_grant_and_revokes_the_family(state, chain):
    first = _redeemed(state, chain)
    assert _post(state, chain, _refresh_form(first["refresh_token"])).status == 200
    reused = _post(state, chain, _refresh_form(first["refresh_token"]))
    assert reused.body == {"error": "invalid_grant"}
    assert all(t.revoked for t in state.tokens.values())
    assert [e["event"] for e in chain.entries][-2:] == ["token.revoke", "token.revoke"]


@pytest.mark.parametrize("scope", ["fetch", "fetch remember node:*", "admin"])
def test_a_scope_on_refresh_is_invalid_scope_and_spends_nothing(state, chain, scope):
    first = _redeemed(state, chain)
    answer = _post(state, chain, _refresh_form(first["refresh_token"], scope=scope))
    assert (answer.status, answer.body) == (400, {"error": "invalid_scope"})
    # Nothing was spent: the same refresh token still rotates once.
    assert _post(state, chain, _refresh_form(first["refresh_token"])).status == 200


@pytest.mark.parametrize(
    "over", [{"client_id": "fork.example"}, {"client_id": ""}, {"refresh_token": "nope"}]
)
def test_refresh_refusals_are_one_invalid_grant(state, chain, over):
    first = _redeemed(state, chain)
    fields = dict(_refresh_form(first["refresh_token"]))
    fields.update(over)
    answer = _post(state, chain, list(fields.items()))
    assert (answer.status, answer.body) == (400, {"error": "invalid_grant"})


# --- the device_code grant -------------------------------------------------------------------


def _device(state: State, *, approve: bool | None) -> str:
    response = device.authorize(
        state,  # type: ignore[arg-type]
        key=KEY,
        client_id=CLI,
        scope="fetch remember node:*",
        requester_hint=None,
        verification_uri="https://box.example/device",
        now=T0,
    )
    if approve is not None:
        assert device.decide(
            state,  # type: ignore[arg-type]
            key=KEY,
            user_code=response["user_code"],
            approve=approve,
            now=T0 + timedelta(seconds=30),
        )
    return response["device_code"]


def _device_form(value: str, client_id: str = CLI) -> list[tuple[str, str]]:
    return [("grant_type", DEVICE_GRANT), ("device_code", value), ("client_id", client_id)]


def test_the_device_grant_mints_a_client_token_for_the_container_owner(state, chain):
    code = _device(state, approve=True)
    answer = _post(state, chain, _device_form(code), now=T0 + timedelta(seconds=60))
    assert answer.status == 200 and answer.body["token_type"] == "Bearer"
    token = state.tokens[token_id_of(answer.body["access_token"])]
    assert (token.owner, token.client, token.principal) == (OWNER, CLI, "client")


@pytest.mark.parametrize(
    ("approve", "client_id", "word"),
    [
        (None, CLI, "authorization_pending"),
        (False, CLI, "access_denied"),
        (True, "other-cli", "invalid_grant"),
    ],
)
def test_the_device_grant_answers_rfc_8628_words(state, chain, approve, client_id, word):
    code = _device(state, approve=approve)
    answer = _post(state, chain, _device_form(code, client_id), now=T0 + timedelta(seconds=60))
    assert (answer.status, answer.body) == (400, {"error": word})
    assert not chain.entries


def test_the_device_grant_says_slow_down_and_expired_token(state, chain):
    code = _device(state, approve=None)
    at = T0 + timedelta(seconds=60)
    assert _post(state, chain, _device_form(code), now=at).body["error"] == "authorization_pending"
    assert _post(state, chain, _device_form(code), now=at).body["error"] == "slow_down"
    late = T0 + timedelta(seconds=device.DEVICE_CODE_LIFETIME_SECONDS)
    assert _post(state, chain, _device_form(code), now=late).body["error"] == "expired_token"


# --- the request's shape ---------------------------------------------------------------------


def test_grants_are_exactly_the_metadata_grant_types():
    assert token_endpoint.GRANTS == tuple(AS_METADATA_CLOSED_VALUES["grant_types_supported"])


@pytest.mark.parametrize(
    "grant_type", ["password", "client_credentials", "implicit", "token", "AUTHORIZATION_CODE"]
)
def test_any_other_grant_type_is_unsupported(state, chain, grant_type):
    answer = _post(state, chain, [("grant_type", grant_type), ("client_id", CLIENT)])
    assert (answer.status, answer.body) == (400, {"error": "unsupported_grant_type"})


@pytest.mark.parametrize(
    "content_type", [None, "", "application/json", "multipart/form-data", "text/plain"]
)
def test_a_body_that_is_not_a_form_is_invalid_request_and_spends_nothing(
    state, chain, content_type
):
    code = _code(state)
    answer = _post(state, chain, _code_form(code), content_type=content_type)
    assert (answer.status, answer.body) == (400, {"error": "invalid_request"})
    assert _post(state, chain, _code_form(code)).status == 200


def test_a_form_content_type_with_parameters_is_a_form(state, chain):
    answer = _post(
        state, chain, _code_form(_code(state)), content_type=FORM.upper() + "; charset=UTF-8"
    )
    assert answer.status == 200


@pytest.mark.parametrize(
    "params",
    [
        [],
        [("grant_type", "")],  # empty is omitted
        [("client_id", CLIENT)],
        [("grant_type", CODE_GRANT), ("grant_type", CODE_GRANT)],
        [("grant_type", CODE_GRANT), ("code", ""), ("code", "x")],
        [("grant_type", CODE_GRANT), ("extra", "a"), ("extra", "b")],
        [("grant_type", CODE_GRANT, "x")],
        [("grant_type", None)],
        [["grant_type", CODE_GRANT]],
    ],
)
def test_malformed_forms_are_invalid_request(state, chain, params):
    answer = _post(state, chain, params)
    assert (answer.status, answer.body) == (400, {"error": "invalid_request"})
    assert not chain.entries


@pytest.mark.parametrize(
    ("extra", "authorization"),
    [
        ([("client_secret", "x")], None),
        ([("client_assertion", "x")], None),
        ([("client_assertion_type", "x")], None),
        ([], "Basic x"),
        ([], "Bearer x"),
    ],
)
def test_client_authentication_is_refused_never_checked(state, chain, extra, authorization):
    code = _code(state)
    answer = _post(state, chain, [*_code_form(code), *extra], authorization=authorization)
    assert (answer.status, answer.body) == (400, {"error": "invalid_request"})
    assert not state.tokens and not chain.entries
    assert _post(state, chain, _code_form(code)).status == 200  # the code was not spent


def test_a_blank_authorization_header_is_no_attempt(state, chain):
    assert _post(state, chain, _code_form(_code(state)), authorization="  ").status == 200


def test_no_answer_carries_a_description_uri_or_scope(state, chain):
    answers = [
        _post(state, chain, []),
        _post(state, chain, [("grant_type", "password")]),
        _post(state, chain, _code_form("unknown")),
        _post(state, chain, _code_form(_code(state))),
    ]
    for answer in answers:
        assert not {"error_description", "error_uri", "scope"} & answer.body.keys()


def test_every_answer_is_uncacheable():
    assert token_endpoint.HEADERS == {"Cache-Control": "no-store", "Pragma": "no-cache"}
