# Copyright 2026 Ali Sasanian
# SPDX-License-Identifier: LicenseRef-PolyForm-Strict-1.0.0
"""§5.3 the pre-trust tier at `/authorize` and its row (d) entry (authz/pretrust.py)."""

from __future__ import annotations

import copy
from typing import Any

import pytest

from egzos._types import (
    AS_AUTHORIZE_PRETRUST_CAUSES,
    GENESIS_HASH,
    DecidedRequestRecord,
)
from egzos.authz import decided, pretrust
from egzos.ledger import Ledger

CLIENT = "01JCLIENT00000000000000000"
CB = "https://egzos.io/connect/callback"
DEV = "http://127.0.0.1/cb"
CHALLENGE = "E9Melhoa2OwvFrEMTJguCHaoeK1t8URWbuGJSstw-cM"
ENTRY: dict[str, Any] = {
    "client_id": CLIENT,
    "client_name": "egzos.io",
    "client_type": "browser",
    "redirect_uris": [CB, DEV],
    "registered_at": "2026-10-13T09:00:00Z",
}
REQUEST: list[tuple[str, str]] = [
    ("response_type", "code"),
    ("client_id", CLIENT),
    ("redirect_uri", CB),
    ("code_challenge", CHALLENGE),
    ("code_challenge_method", "S256"),
    ("state", "xyz"),
    ("scope", "read node:*"),
]


class State:
    """storage.md §3.1's keyed client read and decided-request read, in memory."""

    def __init__(self, *entries: dict[str, Any]) -> None:
        self.clients = {e["client_id"]: e for e in entries}
        self.decided: dict[str, DecidedRequestRecord] = {}

    def get_client(self, client_id: str) -> Any:
        return copy.deepcopy(self.clients.get(client_id))

    def put_decided(self, record: DecidedRequestRecord) -> None:
        self.decided[record["request_key"]] = copy.deepcopy(record)

    def get_decided(self, request_key: str) -> DecidedRequestRecord | None:
        return copy.deepcopy(self.decided.get(request_key))


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
    return State(ENTRY)


@pytest.fixture
def chain() -> Chain:
    return Chain()


def _with(**over: str | None) -> list[tuple[str, str]]:
    """REQUEST with parameters replaced, or dropped where the value is None."""
    out = [(k, over[k]) for k, _ in REQUEST if k in over and over[k] is not None]
    out += [(k, v) for k, v in REQUEST if k not in over]
    return out  # type: ignore[return-value]


def _admit(state: State, chain: Chain, params: Any) -> pretrust.Admitted | None:
    return pretrust.admit(state, Ledger(chain), params)  # type: ignore[arg-type]


def _decide(state: Any, key: str, decision: Any) -> None:
    decided.record(state, key=key, session_hash="a" * 64, decision=decision)


def _refused(chain: Chain, cause: str) -> None:
    assert len(chain.entries) == 1
    entry = chain.entries[0]
    assert entry["event"] == "authz.refuse"
    assert entry["actor"] == "authorize"
    assert entry["principal"] == "none"
    assert entry["details"] == {"cause": cause}
    assert entry.get("subject") is None


# --- admission


def test_a_well_formed_request_is_admitted_and_appends_nothing(state: State, chain: Chain) -> None:
    admitted = _admit(state, chain, REQUEST)
    assert admitted is not None
    assert admitted.client.client_id == CLIENT
    assert admitted.redirect_uri == CB
    assert admitted.code_challenge == CHALLENGE
    assert admitted.state == "xyz"
    assert admitted.scope == "read node:*"
    assert admitted.key == decided.request_key(
        client_id=CLIENT, redirect_uri=CB, state="xyz", code_challenge=CHALLENGE
    )
    assert chain.entries == []


def test_state_and_scope_are_optional_here(state: State, chain: Chain) -> None:
    admitted = _admit(state, chain, _with(state=None, scope=None))
    assert admitted is not None
    assert admitted.state is None and admitted.scope is None


def test_an_empty_state_is_treated_as_omitted(state: State, chain: Chain) -> None:
    admitted = _admit(state, chain, _with(state=""))
    assert admitted is not None
    assert admitted.state is None
    assert admitted.key == decided.request_key(
        client_id=CLIENT, redirect_uri=CB, state=None, code_challenge=CHALLENGE
    )
    # One request to §11.4: deciding it with `state=` replays it without `state`.
    _decide(state, admitted.key, "denied")
    assert _admit(state, chain, _with(state=None)) is None
    _refused(chain, "replayed")


def test_an_empty_scope_is_treated_as_omitted(state: State, chain: Chain) -> None:
    admitted = _admit(state, chain, _with(scope=""))
    assert admitted is not None
    assert admitted.scope is None
    assert chain.entries == []


def test_a_repeated_empty_state_is_still_malformed(state: State, chain: Chain) -> None:
    assert _admit(state, chain, _with(state="") + [("state", "")]) is None
    _refused(chain, "malformed")


def test_a_loopback_redirect_is_admitted_on_any_port(state: State, chain: Chain) -> None:
    admitted = _admit(state, chain, _with(redirect_uri="http://127.0.0.1:8731/cb"))
    assert admitted is not None
    assert admitted.redirect_uri == "http://127.0.0.1:8731/cb"


def test_an_unknown_parameter_is_ignored_even_repeated(state: State, chain: Chain) -> None:
    extra = [("principal", "interactive"), ("x", "1"), ("x", "2")]
    assert _admit(state, chain, REQUEST + extra) is not None
    assert chain.entries == []


# --- refusals, each one row (d) with its closed cause


@pytest.mark.parametrize(
    "params",
    [
        _with(response_type=None),
        _with(response_type="token"),
        _with(response_type="code id_token"),
        _with(response_type="CODE"),
        _with(client_id=None),
        _with(client_id=""),
        _with(redirect_uri=None),
        _with(redirect_uri=""),
        REQUEST + [("client_id", CLIENT)],
        REQUEST + [("redirect_uri", CB)],
        REQUEST + [("code_challenge", CHALLENGE)],
        REQUEST + [("code_challenge_method", "plain")],
        REQUEST + [("state", "xyz")],
        REQUEST + [("scope", "read")],
        REQUEST + [("response_type", "code")],
        _with(code_challenge="short"),
        _with(code_challenge=CHALLENGE + "="),
        [*REQUEST, ("client_id",)],
        [*REQUEST, ("x", 1)],
        [*REQUEST, ["x", "1"]],
    ],
)
def test_malformed(state: State, chain: Chain, params: Any) -> None:
    assert _admit(state, chain, params) is None
    _refused(chain, "malformed")


@pytest.mark.parametrize("client_id", ["01JUNKNOWN0000000000000000", CLIENT.lower(), CLIENT + " "])
def test_unknown_client(state: State, chain: Chain, client_id: str) -> None:
    assert _admit(state, chain, _with(client_id=client_id)) is None
    _refused(chain, "unknown_client")


def test_a_malformed_registry_entry_is_an_unknown_client(chain: Chain) -> None:
    broken = State({**ENTRY, "client_type": ["browser"]})
    assert _admit(broken, chain, REQUEST) is None
    _refused(chain, "unknown_client")


@pytest.mark.parametrize(
    "redirect_uri",
    [
        CB + "/",
        CB + "x",
        CB + "?a=1",
        CB + "#f",
        "https://EGZOS.io/connect/callback",
        "http://egzos.io/connect/callback",
        "http://localhost/cb",
        "http://localhost:8731/cb",
        "http://127.0.0.1:8731/cb/",
        "http://[::1]/cb",
        "https://attacker.example/cb",
    ],
)
def test_redirect_mismatch(state: State, chain: Chain, redirect_uri: str) -> None:
    assert _admit(state, chain, _with(redirect_uri=redirect_uri)) is None
    _refused(chain, "redirect_mismatch")


def test_a_client_with_no_redirect_uris_matches_nothing(chain: Chain) -> None:
    cli = State({**ENTRY, "client_type": "cli", "redirect_uris": []})
    assert _admit(cli, chain, REQUEST) is None
    _refused(chain, "redirect_mismatch")


@pytest.mark.parametrize(
    "over",
    [
        {"code_challenge": None},
        {"code_challenge": ""},
        {"code_challenge_method": None},
        {"code_challenge_method": "plain"},
        {"code_challenge_method": "s256"},
        {"code_challenge": None, "code_challenge_method": None},
    ],
)
def test_missing_pkce(state: State, chain: Chain, over: dict[str, str | None]) -> None:
    assert _admit(state, chain, _with(**over)) is None
    _refused(chain, "missing_pkce")


def test_a_decided_request_is_replayed(state: State, chain: Chain) -> None:
    first = _admit(state, chain, REQUEST)
    assert first is not None
    _decide(state, first.key, "denied")
    assert _admit(state, chain, REQUEST) is None
    _refused(chain, "replayed")


def test_a_different_state_is_a_different_request(state: State, chain: Chain) -> None:
    first = _admit(state, chain, REQUEST)
    assert first is not None
    _decide(state, first.key, "granted")
    assert _admit(state, chain, _with(state="other")) is not None
    assert chain.entries == []


# --- order: the first failing check names the cause, and only one entry is written


@pytest.mark.parametrize(
    ("over", "cause"),
    [
        ({"response_type": "token", "client_id": "nope"}, "malformed"),
        ({"client_id": "nope", "redirect_uri": "https://x/cb"}, "unknown_client"),
        ({"redirect_uri": "https://x/cb", "code_challenge": None}, "redirect_mismatch"),
        ({"code_challenge_method": "plain", "code_challenge": "short"}, "missing_pkce"),
    ],
)
def test_the_first_failing_check_names_the_cause(
    state: State, chain: Chain, over: dict[str, str | None], cause: str
) -> None:
    assert _admit(state, chain, _with(**over)) is None
    _refused(chain, cause)


def test_an_unknown_client_is_not_compared_or_pkce_checked(chain: Chain) -> None:
    # §11.1: nothing past the keyed read touches an unregistered client_id.
    empty = State()
    assert _admit(empty, chain, _with(client_id="nope")) is None
    _refused(chain, "unknown_client")


# --- refuse and the page


def test_refuse_takes_every_closed_cause_and_nothing_else(chain: Chain) -> None:
    ledger = Ledger(chain)  # type: ignore[arg-type]
    for cause in AS_AUTHORIZE_PRETRUST_CAUSES:
        pretrust.refuse(ledger, cause)
    assert [e["details"]["cause"] for e in chain.entries] == list(AS_AUTHORIZE_PRETRUST_CAUSES)
    assert {e["principal"] for e in chain.entries} == {"none"}
    for bad in ("vocabulary", "scope", "", "Malformed", None, ["malformed"]):
        with pytest.raises(ValueError):
            pretrust.refuse(ledger, bad)  # type: ignore[arg-type]
    assert len(chain.entries) == len(AS_AUTHORIZE_PRETRUST_CAUSES)


def test_the_page_is_one_status_and_one_line() -> None:
    assert pretrust.STATUS == 400
    assert pretrust.COPY == "This request can't be completed."
    assert "\n" not in pretrust.COPY
