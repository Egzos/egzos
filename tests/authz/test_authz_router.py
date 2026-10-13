# Copyright 2026 Ali Sasanian
# SPDX-License-Identifier: LicenseRef-PolyForm-Strict-1.0.0
"""The AS router: metadata discovery and the token endpoint over HTTP (authz/router.py)."""

from __future__ import annotations

from datetime import UTC, datetime
from urllib.parse import urlsplit

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from test_authz_tokens import Chain, State  # the fakes `tokens` is tested with: one, not two

from egzos._types import AS_METADATA_FIELDS, ASGrant
from egzos.auth import token_id_of
from egzos.authz import codes, metadata, pkce, router
from egzos.ledger import Ledger

ISSUER = "https://box.example:8443"
FORM = {"content-type": "application/x-www-form-urlencoded"}
OWNER = "self"
CLIENT = "egzos.io"
REDIRECT = "https://egzos.io/connect/callback"
VERIFIER = "v" * 43
GRANT = ASGrant(
    capabilities=["fetch"],
    scopes=["*"],
    principal="interactive",
    grant_expires_at="2099-01-01T00:00:00Z",
)

@pytest.fixture
def state() -> State:
    return State()


@pytest.fixture
def chain() -> Chain:
    return Chain()


def _routes(state: State, chain: Chain, issuer: object = ISSUER) -> router.APIRouter:
    ledger = Ledger(chain)  # type: ignore[arg-type]
    return router._build(state=state, ledger=ledger, issuer=issuer, owner=OWNER)  # type: ignore[arg-type]


@pytest.fixture
def client(state: State, chain: Chain) -> TestClient:
    app = FastAPI()
    app.include_router(_routes(state, chain))
    return TestClient(app, base_url=ISSUER)


def _code(state: State) -> str:
    return codes.issue(
        state,  # type: ignore[arg-type]
        client_id=CLIENT,
        redirect_uri=REDIRECT,
        code_challenge=pkce.s256(VERIFIER),
        session_hash="s" * 64,
        grant=GRANT,
        now=datetime.now(UTC),
    )


def _code_form(code: str) -> dict[str, str]:
    return {
        "grant_type": "authorization_code",
        "code": code,
        "client_id": CLIENT,
        "redirect_uri": REDIRECT,
        "code_verifier": VERIFIER,
    }


# --- §6 metadata ------------------------------------------------------------------------------


def test_metadata_is_served_unauthenticated_with_exactly_the_ten_fields(client):
    answer = client.get(router.METADATA_PATH)
    assert answer.status_code == 200
    assert answer.headers["content-type"].startswith("application/json")
    body = answer.json()
    assert set(body) == set(AS_METADATA_FIELDS)
    assert body == metadata.document(ISSUER)


def test_every_advertised_endpoint_answers_or_is_held_by_name(client):
    body = client.get(router.METADATA_PATH).json()
    endpoints = [value for key, value in body.items() if key.endswith("_endpoint")]
    assert len(endpoints) == 4
    served = []
    for url in endpoints:
        path = urlsplit(url).path
        status = client.post(path).status_code
        if path in router.HELD:
            assert status == 404, f"{path} is served now: lift its hold"
        else:
            assert status != 404
            served.append(path)
    assert served == [metadata.TOKEN_PATH]
    assert set(router.HELD) == {urlsplit(url).path for url in endpoints} - set(served)
    assert all(router.HELD.values())  # each hold names its question


def test_the_mount_entry_refuses_to_build_while_an_endpoint_is_held(state, chain):
    assert router.HELD
    with pytest.raises(RuntimeError, match="does not serve yet"):
        router.router(state=state, ledger=Ledger(chain), issuer=ISSUER, owner=OWNER)  # type: ignore[arg-type]


def test_the_mount_entry_builds_once_no_endpoint_is_held(state, chain, monkeypatch):
    monkeypatch.setattr(router, "HELD", {})
    routes = router.router(state=state, ledger=Ledger(chain), issuer=ISSUER, owner=OWNER)  # type: ignore[arg-type]
    assert {route.path for route in routes.routes} >= {router.METADATA_PATH, metadata.TOKEN_PATH}


def test_held_cannot_be_edited_at_run_time():
    with pytest.raises(TypeError):
        router.HELD[metadata.TOKEN_PATH] = "x"  # type: ignore[index]


def test_a_trailing_slash_on_the_issuer_is_dropped(state, chain):
    app = FastAPI()
    app.include_router(_routes(state, chain, ISSUER + "/"))
    assert TestClient(app).get(router.METADATA_PATH).json()["issuer"] == ISSUER


@pytest.mark.parametrize(
    "issuer",
    [
        "box.example",
        "ftp://box.example",
        "https://",
        "https://box.example/as",
        "https://box.example?x=1",
        "https://box.example#f",
        "https://user@box.example",
        "https://box.example:abc",
        "https://box.example:",
        "https://box.example:0",
        "https://box.example:65536",
        "https://:8443",
    ],
)
def test_an_issuer_that_is_not_an_origin_is_refused(state, chain, issuer):
    with pytest.raises(ValueError):
        _routes(state, chain, issuer)


@pytest.mark.parametrize(
    "issuer", ["https://box.example", "https://box.example:8443", "http://127.0.0.1:8080"]
)
def test_an_origin_with_or_without_a_port_is_accepted(state, chain, issuer):
    app = FastAPI()
    app.include_router(_routes(state, chain, issuer))
    assert TestClient(app).get(router.METADATA_PATH).json()["issuer"] == issuer


def test_an_issuer_that_is_not_a_string_is_refused(state, chain):
    with pytest.raises(TypeError):
        _routes(state, chain, b"https://x")


# --- /token -----------------------------------------------------------------------------------


def test_a_code_redeems_over_http_for_the_container_owner(client, state, chain):
    form = {**_code_form(_code(state)), "owner": "mallory"}
    answer = client.post(metadata.TOKEN_PATH, data=form)
    assert answer.status_code == 200
    assert answer.headers["cache-control"] == "no-store"
    assert answer.headers["pragma"] == "no-cache"
    body = answer.json()
    assert set(body) == {"access_token", "token_type", "expires_in", "refresh_token"}
    token = state.tokens[token_id_of(body["access_token"])]
    assert (token.owner, token.client, token.principal) == (OWNER, CLIENT, "interactive")
    assert [e["event"] for e in chain.entries] == ["token.mint"]


def test_a_second_redemption_over_http_is_invalid_grant(client, state):
    form = _code_form(_code(state))
    assert client.post(metadata.TOKEN_PATH, data=form).status_code == 200
    answer = client.post(metadata.TOKEN_PATH, data=form)
    assert (answer.status_code, answer.json()) == (400, {"error": "invalid_grant"})
    assert answer.headers["cache-control"] == "no-store"


def test_the_authorization_header_reaches_the_endpoint_and_is_refused(client, state, chain):
    code = _code(state)
    answer = client.post(
        metadata.TOKEN_PATH, data=_code_form(code), headers={"Authorization": "Basic eDp5"}
    )
    assert (answer.status_code, answer.json()) == (400, {"error": "invalid_request"})
    assert chain.entries == []
    # Client authentication is refused before the grant: the code is still live.
    assert client.post(metadata.TOKEN_PATH, data=_code_form(code)).status_code == 200


def test_a_json_body_is_invalid_request(client, state, chain):
    answer = client.post(metadata.TOKEN_PATH, json=_code_form(_code(state)))
    assert (answer.status_code, answer.json()) == (400, {"error": "invalid_request"})
    assert chain.entries == []


@pytest.mark.parametrize(
    "body",
    [
        b"grant_type=authorization_code&grant_type=refresh_token",  # a repeat
        b"grant_type=authorization_code&code=&code=x",  # a blank value still counts as a repeat
        "grant_type=authorization_code&code=é".encode(),  # not ASCII
        b"grant_type=authorization_code&code=%ff",  # a percent-escape that is not UTF-8
        b"&".join(b"p%d=1" % n for n in range(router.MAX_FIELDS + 1)),  # too many pairs
        b"code=" + b"x" * router.MAX_BODY_BYTES,  # over the cap
    ],
)
def test_a_body_that_does_not_decode_is_invalid_request(client, chain, body):
    answer = client.post(metadata.TOKEN_PATH, content=body, headers=FORM)
    assert (answer.status_code, answer.json()) == (400, {"error": "invalid_request"})
    assert answer.headers["cache-control"] == "no-store"
    assert chain.entries == []


def test_an_unknown_grant_type_is_unsupported(client):
    answer = client.post(metadata.TOKEN_PATH, data={"grant_type": "password"})
    assert (answer.status_code, answer.json()) == (400, {"error": "unsupported_grant_type"})


def test_token_is_post_only(client):
    assert client.get(metadata.TOKEN_PATH).status_code == 405


@pytest.mark.parametrize("failure", [RuntimeError("store down"), KeyError("x"), OSError("disk")])
def test_a_failure_under_token_is_one_no_store_server_error(state, chain, monkeypatch, failure):
    def respond(*args, **kwargs):
        raise failure

    monkeypatch.setattr(router.token_endpoint, "respond", respond)
    app = FastAPI()
    app.include_router(_routes(state, chain))
    answer = TestClient(app, raise_server_exceptions=True).post(
        metadata.TOKEN_PATH, data=_code_form(_code(state))
    )
    assert (answer.status_code, answer.json()) == (500, {"error": "server_error"})
    assert answer.headers["cache-control"] == "no-store"
    assert answer.headers["pragma"] == "no-cache"
    assert str(failure.args[0]) not in answer.text
    assert chain.entries == []
