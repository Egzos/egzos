# Copyright 2026 Ali Sasanian
# SPDX-License-Identifier: LicenseRef-PolyForm-Strict-1.0.0
"""§5 / §9.3 row 6 client registration, amendment and removal (authz/clients.py)."""

from __future__ import annotations

import copy
from datetime import UTC, datetime
from typing import Any

import pytest

from egzos._types import AS_CLIENT_REGISTRY_READ_FIELDS, GENESIS_HASH, ClientRegistration
from egzos.authz import clients
from egzos.ledger import Ledger
from egzos.model import Token

T0 = datetime(2026, 10, 13, 9, 0, 0, tzinfo=UTC)
OWNER_ACTOR = "ali"
CB = "https://egzos.io/connect/callback"
DEV = "http://127.0.0.1/cb"


def _token(**over: Any) -> Token:
    args: dict[str, Any] = {
        "id": "01J" + "0" * 23,
        "principal": "interactive",
        "owner": OWNER_ACTOR,
        "client": "cli",
        "capabilities": ["fetch", "remember", "organize", "publish", "curate", "admin"],
        "scopes": ["*"],
    }
    return Token(**{**args, **over})


class Clients:
    """storage.md §3.1's client methods, in memory."""

    def __init__(self) -> None:
        self.rows: dict[str, ClientRegistration] = {}

    def put_client(self, registration: ClientRegistration) -> None:
        self.rows[registration["client_id"]] = copy.deepcopy(registration)

    def get_client(self, client_id: str) -> ClientRegistration | None:
        return copy.deepcopy(self.rows.get(client_id))

    def remove_client(self, client_id: str) -> bool:
        return self.rows.pop(client_id, None) is not None


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
def state() -> Clients:
    return Clients()


@pytest.fixture
def chain() -> Chain:
    return Chain()


def _register(state: Clients, chain: Chain, **over: Any) -> ClientRegistration:
    args: dict[str, Any] = {
        "by": _token(),
        "actor": OWNER_ACTOR,
        "client_name": "egzos.io",
        "client_type": "browser",
        "redirect_uris": [CB, DEV],
        "now": T0,
    }
    return clients.register(state, Ledger(chain), **{**args, **over})  # type: ignore[arg-type]


def _details(entry: dict[str, Any]) -> dict[str, Any]:
    return {k: entry["details"][k] for k in ("client_id", "op", "redirect_uris")}


# --- register ------------------------------------------------------------------------------


def test_register_stores_the_entry_and_appends_add(state: Clients, chain: Chain) -> None:
    entry = _register(state, chain)
    assert set(entry) == AS_CLIENT_REGISTRY_READ_FIELDS
    assert state.rows[entry["client_id"]] == entry
    assert entry["registered_at"] == "2026-10-13T09:00:00Z"
    assert entry["redirect_uris"] == [CB, DEV]
    [row] = chain.entries
    assert row["event"] == "client.register" and row["principal"] == "interactive"
    assert row["actor"] == OWNER_ACTOR and row["subject"] == entry["client_id"]
    assert _details(row) == {
        "client_id": entry["client_id"],
        "op": "add",
        "redirect_uris": [CB, DEV],
    }


def test_register_mints_a_fresh_client_id_every_time(state: Clients, chain: Chain) -> None:
    a, b = _register(state, chain), _register(state, chain)
    assert a["client_id"] != b["client_id"]
    assert len(state.rows) == 2


def test_register_drops_an_exact_duplicate_uri(state: Clients, chain: Chain) -> None:
    entry = _register(state, chain, redirect_uris=[CB, CB, DEV])
    assert entry["redirect_uris"] == [CB, DEV]


def test_register_admits_an_empty_allowlist_for_a_device_client(
    state: Clients, chain: Chain
) -> None:
    entry = _register(state, chain, client_type="cli", redirect_uris=[])
    assert entry["redirect_uris"] == [] and entry["client_type"] == "cli"


@pytest.mark.parametrize(
    "uri",
    [
        "http://localhost:5173/cb",
        "http://LOCALHOST/cb",
        "https://localhost./cb",
        "https://app.localhost/cb",
        "http://egzos.io/cb",
        "https://egzos.io/cb#frag",
        "https://user@egzos.io/cb",
        "/relative/cb",
        "",
    ],
)
def test_register_refuses_an_unsafe_redirect_uri_and_stores_nothing(
    state: Clients, chain: Chain, uri: str
) -> None:
    with pytest.raises(clients.ClientRefused):
        _register(state, chain, redirect_uris=[CB, uri])
    assert state.rows == {} and chain.entries == []


@pytest.mark.parametrize(
    "over",
    [
        {"client_type": "confidential"},
        {"client_type": "web"},
        {"client_name": ""},
        {"client_name": "   "},
        {"client_name": None},
        {"redirect_uris": CB},
        {"redirect_uris": None},
        {"redirect_uris": [None]},
    ],
)
def test_register_refuses_a_malformed_entry(
    state: Clients, chain: Chain, over: dict[str, Any]
) -> None:
    with pytest.raises(clients.ClientRefused):
        _register(state, chain, **over)
    assert state.rows == {} and chain.entries == []


@pytest.mark.parametrize(
    "by",
    [
        _token(principal="client"),
        _token(capabilities=["fetch", "remember", "organize", "publish", "curate"]),
        _token(scopes=["01J" + "1" * 23]),
        _token(revoked=True),
        _token(expires_at="2000-01-01T00:00:00Z"),
        None,
    ],
)
def test_only_the_owner_registers(state: Clients, chain: Chain, by: Token | None) -> None:
    """[0.3 · 10]: no open registration. A client token, a non-admin, a scoped token and a dead
    token are all refused, before anything is stored or appended."""
    with pytest.raises(clients.ClientRefused, match="owner's act"):
        _register(state, chain, by=by)
    assert state.rows == {} and chain.entries == []


# --- amend ---------------------------------------------------------------------------------


def test_amend_replaces_the_allowlist_and_appends_it_whole(state: Clients, chain: Chain) -> None:
    entry = _register(state, chain)
    out = clients.amend(
        state,  # type: ignore[arg-type]
        Ledger(chain),  # type: ignore[arg-type]
        by=_token(),
        actor=OWNER_ACTOR,
        client_id=entry["client_id"],
        redirect_uris=["https://fork.example/cb"],
    )
    assert out["redirect_uris"] == ["https://fork.example/cb"]
    assert out["client_type"] == "browser" and out["registered_at"] == entry["registered_at"]
    assert state.rows[entry["client_id"]] == out
    assert _details(chain.entries[-1]) == {
        "client_id": entry["client_id"],
        "op": "amend",
        "redirect_uris": ["https://fork.example/cb"],
    }


def test_amend_renames_and_appends_even_with_the_allowlist_unchanged(
    state: Clients, chain: Chain
) -> None:
    entry = _register(state, chain)
    out = clients.amend(
        state,  # type: ignore[arg-type]
        Ledger(chain),  # type: ignore[arg-type]
        by=_token(),
        actor=OWNER_ACTOR,
        client_id=entry["client_id"],
        client_name="flagship",
    )
    assert out["client_name"] == "flagship" and out["redirect_uris"] == [CB, DEV]
    assert [e["details"]["op"] for e in chain.entries] == ["add", "amend"]
    assert chain.entries[-1]["details"]["redirect_uris"] == [CB, DEV]


def test_amend_takes_no_client_type(state: Clients, chain: Chain) -> None:
    entry = _register(state, chain, client_type="cli", redirect_uris=[])
    with pytest.raises(TypeError):
        clients.amend(  # type: ignore[call-arg]
            state,  # type: ignore[arg-type]
            Ledger(chain),  # type: ignore[arg-type]
            by=_token(),
            actor=OWNER_ACTOR,
            client_id=entry["client_id"],
            client_type="browser",
        )
    assert state.rows[entry["client_id"]]["client_type"] == "cli"


def test_amend_refuses_an_unsafe_uri_and_leaves_the_entry(state: Clients, chain: Chain) -> None:
    entry = _register(state, chain)
    with pytest.raises(clients.ClientRefused):
        clients.amend(
            state,  # type: ignore[arg-type]
            Ledger(chain),  # type: ignore[arg-type]
            by=_token(),
            actor=OWNER_ACTOR,
            client_id=entry["client_id"],
            redirect_uris=["http://localhost/cb"],
        )
    assert state.rows[entry["client_id"]] == entry
    assert len(chain.entries) == 1


@pytest.mark.parametrize("client_id", ["01J" + "9" * 23, None])
def test_amend_refuses_an_unknown_client(state: Clients, chain: Chain, client_id: Any) -> None:
    with pytest.raises(clients.ClientRefused, match="no such client"):
        clients.amend(
            state,  # type: ignore[arg-type]
            Ledger(chain),  # type: ignore[arg-type]
            by=_token(),
            actor=OWNER_ACTOR,
            client_id=client_id,
            client_name="x",
        )
    assert state.rows == {} and chain.entries == []


def test_amend_is_the_owners_act(state: Clients, chain: Chain) -> None:
    entry = _register(state, chain)
    with pytest.raises(clients.ClientRefused, match="owner's act"):
        clients.amend(
            state,  # type: ignore[arg-type]
            Ledger(chain),  # type: ignore[arg-type]
            by=_token(principal="client"),
            actor=OWNER_ACTOR,
            client_id=entry["client_id"],
            redirect_uris=["https://evil.example/cb"],
        )
    assert state.rows[entry["client_id"]] == entry and len(chain.entries) == 1


# --- remove --------------------------------------------------------------------------------


def test_remove_deletes_and_appends_an_empty_allowlist(state: Clients, chain: Chain) -> None:
    entry = _register(state, chain)
    clients.remove(
        state,  # type: ignore[arg-type]
        Ledger(chain),  # type: ignore[arg-type]
        by=_token(),
        actor=OWNER_ACTOR,
        client_id=entry["client_id"],
    )
    assert state.rows == {}
    assert _details(chain.entries[-1]) == {
        "client_id": entry["client_id"],
        "op": "remove",
        "redirect_uris": [],
    }


@pytest.mark.parametrize("client_id", ["01J" + "9" * 23, None])
def test_remove_refuses_an_unknown_client(state: Clients, chain: Chain, client_id: Any) -> None:
    with pytest.raises(clients.ClientRefused, match="no such client"):
        clients.remove(
            state,  # type: ignore[arg-type]
            Ledger(chain),  # type: ignore[arg-type]
            by=_token(),
            actor=OWNER_ACTOR,
            client_id=client_id,
        )
    assert chain.entries == []


def test_remove_is_the_owners_act(state: Clients, chain: Chain) -> None:
    entry = _register(state, chain)
    with pytest.raises(clients.ClientRefused, match="owner's act"):
        clients.remove(
            state,  # type: ignore[arg-type]
            Ledger(chain),  # type: ignore[arg-type]
            by=_token(capabilities=["fetch"]),
            actor=OWNER_ACTOR,
            client_id=entry["client_id"],
        )
    assert entry["client_id"] in state.rows and len(chain.entries) == 1
