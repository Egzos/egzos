# Copyright 2026 Ali Sasanian
# SPDX-License-Identifier: LicenseRef-PolyForm-Strict-1.0.0
"""The device authorization endpoint's request and response, RFC 8628 §3.1–§3.2
(authz/device_authorization.py)."""

from __future__ import annotations

import copy
from datetime import UTC, datetime
from typing import Any

import pytest

from egzos._types import ClientRegistration, DeviceAuthorizationRecord
from egzos.authz import device, device_authorization, values
from egzos.authz.token_endpoint import HEADERS

T0 = datetime(2026, 10, 13, 9, 0, 0, tzinfo=UTC)
FORM = "application/x-www-form-urlencoded"
KEY = b"k" * 32  # a fixture device-code key; provisioning the real one is #143's
ISSUER = "https://box.example/"
CLI = "egzos-cli"
BROWSER = "egzos.io"
MCP = "claude-ai"
KEYS = {"device_code", "user_code", "verification_uri", "expires_in", "interval"}


def _client(client_id: str, client_type: Any) -> ClientRegistration:
    return ClientRegistration(
        client_id=client_id,
        client_name=client_id,
        client_type=client_type,
        redirect_uris=[] if client_type == "cli" else ["https://egzos.io/connect/callback"],
        registered_at="2026-10-01T09:00:00Z",
    )


class State:
    """storage.md §3.1's client and device methods the endpoint reaches, in memory."""

    def __init__(self) -> None:
        self.clients: dict[str, Any] = {
            CLI: _client(CLI, "cli"),
            BROWSER: _client(BROWSER, "browser"),
            MCP: _client(MCP, "mcp"),
        }
        self.devices: dict[str, DeviceAuthorizationRecord] = {}
        self.client_reads = 0

    def get_client(self, client_id: str) -> Any:
        self.client_reads += 1
        return copy.deepcopy(self.clients.get(client_id))

    def put_device(self, record: DeviceAuthorizationRecord) -> None:
        self.devices.setdefault(record["device_code_hash"], copy.deepcopy(record))

    def get_device_by_user_code(self, user_code_hash: str) -> DeviceAuthorizationRecord | None:
        for row in self.devices.values():
            if row["user_code_hash"] == user_code_hash:
                return copy.deepcopy(row)
        return None


@pytest.fixture
def state() -> State:
    return State()


def _post(
    state: State,
    params: list[tuple[str, Any]],
    *,
    content_type: str | None = FORM,
    authorization: str | None = None,
    now: datetime = T0,
) -> device_authorization.Answer:
    return device_authorization.respond(
        state,  # type: ignore[arg-type]
        params,
        content_type=content_type,
        authorization=authorization,
        key=KEY,
        issuer=ISSUER,
        now=now,
    )


def _ok(**over: str) -> list[tuple[str, str]]:
    return list({"client_id": CLI, "scope": "fetch remember node:*", **over}.items())


def test_a_cli_client_gets_exactly_the_five_keys(state: State):
    answer = _post(state, _ok())
    assert answer.status == 200
    assert set(answer.body) == KEYS  # [0.3 · 21]: no `verification_uri_complete`, not even null
    assert answer.body["verification_uri"] == "https://box.example/device"
    assert answer.body["expires_in"] == device.DEVICE_CODE_LIFETIME_SECONDS
    assert answer.body["interval"] == device.POLL_INTERVAL_SECONDS
    (record,) = state.devices.values()
    assert record["device_code_hash"] == values.digest(answer.body["device_code"])
    assert record["client_id"] == CLI and record["decision"] == "pending"
    assert record["requested"] == {"capabilities": ["fetch", "remember"], "scopes": ["*"]}


def test_the_requester_hint_is_not_read_from_the_request(state: State):
    # #253: the contract names no parameter for it, so no client string reaches the page.
    params = _ok() + [("requester_hint", "ali-laptop"), ("device_name", "ali-laptop")]
    assert _post(state, params).status == 200
    (record,) = state.devices.values()
    assert record["requester_hint"] is None


def test_verification_uri_comes_from_the_issuer_never_the_request(state: State):
    params = _ok() + [("verification_uri", "https://evil.example/device")]
    assert _post(state, params).body["verification_uri"] == "https://box.example/device"


def test_the_response_headers_are_no_store():
    assert HEADERS["Cache-Control"] == "no-store"


def test_each_request_is_its_own_pending_authorization(state: State):
    first, second = _post(state, _ok()), _post(state, _ok())
    assert first.body["device_code"] != second.body["device_code"]
    assert len(state.devices) == 2  # §3 mitigation 3: a second request is a second approval


# --- refusals: the first failing check is the answer, and nothing is stored -----------------------


def _refused(state: State, answer: device_authorization.Answer, word: str) -> None:
    assert (answer.status, answer.body) == (400, {"error": word})
    assert state.devices == {}


@pytest.mark.parametrize("content_type", [None, "application/json", "text/plain", ""])
def test_a_body_that_is_not_a_form_is_invalid_request(state: State, content_type: Any):
    _refused(state, _post(state, _ok(), content_type=content_type), "invalid_request")
    assert state.client_reads == 0


def test_a_form_content_type_with_parameters_is_accepted(state: State):
    content_type = "Application/X-WWW-Form-Urlencoded; charset=utf-8"
    assert _post(state, _ok(), content_type=content_type).status == 200


@pytest.mark.parametrize(
    "params",
    [
        _ok() + [("client_id", CLI)],
        _ok() + [("scope", "fetch")],
        _ok() + [("unknown", "a"), ("unknown", "b")],
        [("client_id", CLI), ("scope", 7)],
        [("client_id", CLI, "extra")],
        ["client_id=egzos-cli"],
    ],
)
def test_a_malformed_form_is_invalid_request(state: State, params: Any):
    _refused(state, _post(state, params), "invalid_request")
    assert state.client_reads == 0


@pytest.mark.parametrize(
    "extra", [("client_secret", "s"), ("client_assertion", "a"), ("client_assertion_type", "t")]
)
def test_client_authentication_is_refused_never_checked(state: State, extra: tuple[str, str]):
    _refused(state, _post(state, _ok() + [extra]), "invalid_request")
    assert state.client_reads == 0


def test_an_authorization_header_is_refused(state: State):
    _refused(state, _post(state, _ok(), authorization="Basic ZTpz"), "invalid_request")
    assert state.client_reads == 0


@pytest.mark.parametrize("authorization", ["", "   "])
def test_a_blank_authorization_header_is_no_attempt(state: State, authorization: str):
    assert _post(state, _ok(), authorization=authorization).status == 200


@pytest.mark.parametrize("params", [[("scope", "fetch")], [("client_id", ""), ("scope", "fetch")]])
def test_a_missing_client_id_is_invalid_request(state: State, params: list[tuple[str, str]]):
    _refused(state, _post(state, params), "invalid_request")
    assert state.client_reads == 0


@pytest.mark.parametrize("client_id", ["nobody", BROWSER, MCP])
def test_an_unknown_or_non_cli_client_is_one_invalid_client(state: State, client_id: str):
    _refused(state, _post(state, _ok(client_id=client_id)), "invalid_client")
    assert state.client_reads == 1  # one registry read on every path that reaches it


@pytest.mark.parametrize(
    "entry",
    [
        "not a dict",
        {**_client(CLI, "cli"), "client_type": ["cli"]},
        {**_client(CLI, "cli"), "client_id": "someone-else"},
        {**_client(CLI, "cli"), "redirect_uris": None},
    ],
)
def test_a_malformed_registry_entry_is_invalid_client(state: State, entry: Any):
    state.clients[CLI] = entry
    _refused(state, _post(state, _ok()), "invalid_client")


@pytest.mark.parametrize(
    "scope",
    [None, "reader", "fetch  remember", "fetch\tremember", "node:", "node:node:a", "write"],
)
def test_a_scope_section_7_cannot_expand_is_invalid_scope(state: State, scope: str | None):
    params = [("client_id", CLI)] + ([("scope", scope)] if scope is not None else [])
    _refused(state, _post(state, params), "invalid_scope")


def test_a_node_scope_is_not_looked_up(state: State):
    # §7.1: no owner is present here, so a known and an unknown node answer alike: both stored.
    assert _post(state, _ok(scope="node:01JUNKNOWNNODE fetch")).status == 200
    (record,) = state.devices.values()
    assert record["requested"]["scopes"] == ["01JUNKNOWNNODE"]


def test_the_client_check_runs_before_the_scope_check(state: State):
    _refused(state, _post(state, _ok(client_id=BROWSER, scope="reader")), "invalid_client")


def test_a_naive_clock_raises_before_anything_is_stored(state: State):
    with pytest.raises(ValueError):
        _post(state, _ok(), now=datetime(2026, 10, 13, 9, 0, 0))
    assert state.devices == {}
