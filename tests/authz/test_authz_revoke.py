# Copyright 2026 Ali Sasanian
# SPDX-License-Identifier: LicenseRef-PolyForm-Strict-1.0.0
"""§9.2 / §11.9 the owner path by `Token.id` and the RFC 7009 path by value (authz/revoke.py)."""

from __future__ import annotations

import copy
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest

from egzos._types import AS_REVOKE_REFUSAL_CAUSES, GENESIS_HASH, ASGrant, RefreshRecord
from egzos.auth import new_secret
from egzos.authz import revoke, tokens, values
from egzos.ledger import Ledger
from egzos.model import Token

T0 = datetime.now(UTC).replace(microsecond=0)
CLIENT = "egzos.io"
OWNER = "ali"
GRANT = ASGrant(
    capabilities=["fetch"],
    scopes=["*"],
    principal="interactive",
    grant_expires_at=(T0 + timedelta(days=30)).strftime("%Y-%m-%dT%H:%M:%SZ"),
)


class State:
    """`ContainerState`'s tokens plus storage.md §3.1's refresh records and `family_of_token`,
    which returns `None` for a revoked family as the plain getters do."""

    def __init__(self) -> None:
        self.tokens: dict[str, Token] = {}
        self.refresh: dict[str, RefreshRecord] = {}

    def put_token(self, token: Token) -> None:
        self.tokens[token.id] = copy.deepcopy(token)

    def get_token(self, token_id: str) -> Token | None:
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


def _ledger(chain: Chain) -> Ledger:
    return Ledger(chain)  # type: ignore[arg-type]


def _issued(state: State, client_id: str = CLIENT, owner: str = OWNER) -> tokens.Issued:
    args: dict[str, Any] = {"grant": GRANT, "client_id": client_id, "owner": owner, "now": T0}
    issued = tokens.mint(state, _ledger(Chain()), **args)  # type: ignore[arg-type]
    assert issued is not None
    return issued


def _script_token(state: State) -> tuple[Token, str]:
    """A `token mint` token: no refresh family."""
    token = Token(
        id="01J" + "0" * 23,
        principal="client",
        owner=OWNER,
        client="a-script",
        capabilities=["fetch"],
        scopes=["*"],
    )
    value = new_secret(token.id)
    token.secret_hash = values.digest(value)
    state.put_token(token)
    return token, value


def _by_id(state: State, chain: Chain, token_id: Any, viewer: str = OWNER) -> bool:
    return revoke.by_id(state, _ledger(chain), token_id=token_id, viewer=viewer)  # type: ignore[arg-type]


def _by_value(state: State, chain: Chain, value: Any, client_id: Any = CLIENT) -> None:
    revoke.by_value(state, _ledger(chain), token=value, client_id=client_id)  # type: ignore[arg-type]


# --- by_id: the owner path (§11.9) -----------------------------------------------------------


def test_by_id_revokes_the_token_and_appends_one_token_revoke_with_its_family(state, chain):
    issued = _issued(state)
    assert _by_id(state, chain, issued.token.id) is True
    assert state.tokens[issued.token.id].revoked is True
    (entry,) = chain.entries
    assert entry["event"] == "token.revoke"
    assert entry["subject"] == issued.token.id
    assert entry["principal"] == "interactive" and entry["actor"] == OWNER
    assert entry["details"]["family_id"] == issued.family_id


def test_by_id_on_a_token_with_no_family_carries_no_family_id(state, chain):
    token, _ = _script_token(state)
    assert _by_id(state, chain, token.id) is True
    (entry,) = chain.entries
    assert entry["event"] == "token.revoke" and "family_id" not in entry["details"]


def test_by_id_on_an_already_revoked_token_appends_nothing_more(state, chain):
    issued = _issued(state)
    assert _by_id(state, chain, issued.token.id) is True
    assert _by_id(state, chain, issued.token.id) is True
    assert [e["event"] for e in chain.entries] == ["token.revoke"]


@pytest.mark.parametrize("token_id", ["01JZZZZZZZZZZZZZZZZZZZZZZZ", "", None, 7, ["x"]])
def test_by_id_on_an_unknown_id_refuses_and_appends_cause_unknown(state, chain, token_id):
    _issued(state)
    assert _by_id(state, chain, token_id) is False
    (entry,) = chain.entries
    assert entry["event"] == "authz.revoke_refuse"
    assert entry["principal"] == "interactive" and entry["actor"] == OWNER
    assert entry["details"] == {"outcome": "refused", "cause": "unknown"}
    assert not any(t.revoked for t in state.tokens.values())


def test_by_id_on_another_owners_token_refuses_with_cause_unreachable(state, chain):
    issued = _issued(state, owner="someone-else")
    assert _by_id(state, chain, issued.token.id) is False
    (entry,) = chain.entries
    assert entry["event"] == "authz.revoke_refuse"
    assert entry["details"] == {"outcome": "refused", "cause": "unreachable"}
    assert state.tokens[issued.token.id].revoked is False


def test_unknown_and_unreachable_answer_alike_and_differ_only_in_the_cause(state):
    issued = _issued(state, owner="someone-else")
    a, b = Chain(), Chain()
    assert _by_id(state, a, "01JZZZZZZZZZZZZZZZZZZZZZZZ") == _by_id(state, b, issued.token.id)
    strip = {"hash", "prev_hash", "ts", "details"}
    assert {k: v for k, v in a.entries[0].items() if k not in strip} == {
        k: v for k, v in b.entries[0].items() if k not in strip
    }
    assert {a.entries[0]["details"]["cause"], b.entries[0]["details"]["cause"]} <= set(
        AS_REVOKE_REFUSAL_CAUSES
    )


def test_a_refusal_never_carries_the_id_it_was_asked_for(state, chain):
    issued = _issued(state, owner="someone-else")
    _by_id(state, chain, issued.token.id)
    _by_id(state, chain, "01JQQQQQQQQQQQQQQQQQQQQQQQ")
    assert issued.token.id not in repr(chain.entries)
    assert "01JQQQQQQQQQQQQQQQQQQQQQQQ" not in repr(chain.entries)


@pytest.mark.parametrize("viewer", ["", None])
def test_by_id_without_a_viewer_raises_before_reading_or_appending(state, chain, viewer):
    issued = _issued(state)
    with pytest.raises(ValueError):
        _by_id(state, chain, issued.token.id, viewer=viewer)
    assert not chain.entries and state.tokens[issued.token.id].revoked is False


# --- by_value: the RFC 7009 endpoint (§9.2 clause 1) ---------------------------------------


def test_by_value_revokes_the_holders_access_token(state, chain):
    issued = _issued(state)
    assert _by_value(state, chain, issued.access_token) is None
    assert state.tokens[issued.token.id].revoked is True
    (entry,) = chain.entries
    assert entry["event"] == "token.revoke" and entry["subject"] == issued.token.id
    assert entry["actor"] == CLIENT and entry["principal"] == "client"
    assert entry["details"]["family_id"] == issued.family_id
    assert issued.access_token not in repr(chain.entries)


def test_by_value_with_another_clients_id_revokes_nothing(state, chain):
    issued = _issued(state)
    assert _by_value(state, chain, issued.access_token, client_id="other") is None
    assert state.tokens[issued.token.id].revoked is False and not chain.entries


def test_by_value_twice_appends_one_token_revoke(state, chain):
    issued = _issued(state)
    _by_value(state, chain, issued.access_token)
    _by_value(state, chain, issued.access_token)
    assert [e["event"] for e in chain.entries] == ["token.revoke"]


def test_by_value_revokes_a_family_less_token_for_its_own_client(state, chain):
    token, value = _script_token(state)
    _by_value(state, chain, value, client_id="a-script")
    assert state.tokens[token.id].revoked is True
    assert "family_id" not in chain.entries[0]["details"]


@pytest.mark.parametrize(
    "value",
    [None, "", 7, "not-a-token", "egz_short_x", "egz_" + "0" * 26 + "_x", "\ud800"],
)
def test_by_value_on_a_malformed_or_unknown_value_does_nothing(state, chain, value):
    issued = _issued(state)
    assert _by_value(state, chain, value) is None
    assert state.tokens[issued.token.id].revoked is False and not chain.entries


def test_by_value_with_a_forged_secret_for_a_real_id_does_nothing(state, chain):
    issued = _issued(state)
    tail = "BBBB" if issued.access_token.endswith("AAAA") else "AAAA"
    forged = issued.access_token[:-4] + tail
    _by_value(state, chain, forged)
    assert state.tokens[issued.token.id].revoked is False and not chain.entries


def test_by_value_on_a_token_with_no_stored_hash_does_nothing(state, chain):
    token, value = _script_token(state)
    token.secret_hash = None
    state.put_token(token)
    _by_value(state, chain, value, client_id="a-script")
    assert state.tokens[token.id].revoked is False and not chain.entries


@pytest.mark.parametrize("client_id", [None, "", 7])
def test_by_value_without_a_client_id_does_nothing(state, chain, client_id):
    issued = _issued(state)
    _by_value(state, chain, issued.access_token, client_id=client_id)
    assert state.tokens[issued.token.id].revoked is False and not chain.entries


def test_by_value_on_a_refresh_value_revokes_nothing_yet(state, chain):
    # #240 item 2: no `ASState` read finds a refresh record without spending it.
    issued = _issued(state)
    _by_value(state, chain, issued.refresh_token)
    assert not any(t.revoked for t in state.tokens.values()) and not chain.entries
    assert all(r["redeemed_at"] is None for r in state.refresh.values())
