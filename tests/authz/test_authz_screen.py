# Copyright 2026 Ali Sasanian
# SPDX-License-Identifier: LicenseRef-PolyForm-Strict-1.0.0
"""§11.1 client-registry read and §11.3 existing-tokens read (authz/screen.py)."""

from __future__ import annotations

import copy
import dataclasses
from typing import Any

import pytest

from egzos._types import AS_CLIENT_REGISTRY_READ_FIELDS, CONSENT_KINDS
from egzos.authz import screen
from egzos.model import Token

VIEWER = "ali"
CLIENT = "01JCLIENT00000000000000000"
OTHER = "01JOTHER000000000000000000"
CB = "https://egzos.io/connect/callback"
NOTHING = screen.ExistingTokens(live=0, latest_created_at=None)


def _entry(**over: Any) -> dict[str, Any]:
    base: dict[str, Any] = {
        "client_id": CLIENT,
        "client_name": "egzos.io",
        "client_type": "browser",
        "redirect_uris": [CB],
        "registered_at": "2026-10-13T09:00:00Z",
    }
    return {**base, **over}


class Registry:
    """storage.md §3.1's one keyed client read, counting its calls. No listing exists."""

    def __init__(self, *entries: dict[str, Any]) -> None:
        self.rows = {e["client_id"]: e for e in entries}
        self.reads: list[str] = []

    def get_client(self, client_id: str) -> Any:
        self.reads.append(client_id)
        return copy.deepcopy(self.rows.get(client_id))


class Raw:
    """A store that hands back whatever it holds, malformed or not, and without copying."""

    def __init__(self, value: Any) -> None:
        self.value = value

    def get_client(self, client_id: str) -> Any:
        return self.value


class Listing:
    def __init__(self, *tokens: Token) -> None:
        self.tokens = list(tokens)

    def list_tokens(self) -> list[Token]:
        return list(self.tokens)


def _read(state: Any, client_id: Any = CLIENT) -> screen.ClientEntry | None:
    return screen.client_entry(state, client_id)


def _count(*tokens: Token, viewer: Any = VIEWER, client_id: Any = CLIENT) -> screen.ExistingTokens:
    return screen.existing_tokens(Listing(*tokens), viewer=viewer, client_id=client_id)


def _token(n: int, **over: Any) -> Token:
    args: dict[str, Any] = {
        "id": f"01J{n:023d}",
        "principal": "interactive",
        "owner": VIEWER,
        "client": CLIENT,
        "capabilities": ["fetch"],
        "scopes": ["*"],
        "created_at": f"2026-10-0{n}T09:00:00Z",
        "expires_at": "2999-01-01T00:00:00Z",
    }
    return Token(**{**args, **over})


# --- §11.1 ------------------------------------------------------------------------------------


def test_entry_carries_exactly_the_registry_read_fields() -> None:
    fields = {f.name for f in dataclasses.fields(screen.ClientEntry)}
    assert fields == AS_CLIENT_REGISTRY_READ_FIELDS


def test_registered_client_is_read_once_by_its_id() -> None:
    reg = Registry(_entry())
    want = screen.ClientEntry(CLIENT, "egzos.io", "browser", (CB,), "2026-10-13T09:00:00Z")
    assert _read(reg) == want
    assert reg.reads == [CLIENT]


@pytest.mark.parametrize(("client_type", "kind"), [("browser", "browser"), ("cli", "device")])
def test_kind_is_the_named_mapping_never_the_literal(client_type: str, kind: str) -> None:
    got = _read(Registry(_entry(client_type=client_type)))
    assert got is not None and got.kind == kind and got.kind in CONSENT_KINDS


def test_every_client_type_renders_a_consent_kind_and_cli_is_never_one() -> None:
    entries = [_read(Registry(_entry(client_type=t))) for t in ("browser", "cli", "mcp")]
    kinds = {e.kind for e in entries if e is not None}
    assert kinds == set(CONSENT_KINDS)
    assert "cli" not in kinds


def test_unregistered_client_is_none() -> None:
    assert _read(Registry(_entry()), OTHER) is None


@pytest.mark.parametrize("client_id", [None, "", 7, b"x"])
def test_no_usable_client_id_reads_nothing(client_id: Any) -> None:
    reg = Registry(_entry())
    assert _read(reg, client_id) is None
    assert reg.reads == []


@pytest.mark.parametrize(
    "stored",
    [
        None,
        "not a dict",
        _entry(client_id=OTHER),
        _entry(client_type="device"),
        _entry(client_type="CLI"),
        _entry(client_type=None),
        _entry(client_type=["browser"]),
        _entry(client_type={"browser": "browser"}),
        _entry(client_name=None),
        _entry(redirect_uris=CB),
        _entry(redirect_uris=[CB, 3]),
        _entry(registered_at=None),
    ],
)
def test_a_malformed_entry_is_the_same_none(stored: Any) -> None:
    assert _read(Raw(stored)) is None


def test_an_imitating_name_is_carried_as_data() -> None:
    name = "egzos (official) <b>verified</b>"
    got = _read(Registry(_entry(client_name=name, client_type="mcp")))
    assert got is not None and got.client_name == name and got.kind == "mcp"


def test_the_entry_does_not_alias_the_store() -> None:
    stored = _entry()
    got = _read(Raw(stored))
    stored["redirect_uris"].append("https://evil.example/cb")
    assert got is not None and got.redirect_uris == (CB,)


# --- §11.3 ------------------------------------------------------------------------------------


def test_counts_live_tokens_for_the_pair_and_the_latest_created_at() -> None:
    got = _count(_token(1), _token(3), _token(2))
    assert got == screen.ExistingTokens(live=3, latest_created_at="2026-10-03T09:00:00Z")


def test_answer_names_no_token() -> None:
    fields = {f.name for f in dataclasses.fields(screen.ExistingTokens)}
    assert fields == {"live", "latest_created_at"}


def test_revoked_and_expired_tokens_are_not_live() -> None:
    got = _count(
        _token(1),
        _token(2, revoked=True),
        _token(3, expires_at="2001-01-01T00:00:00Z"),
        _token(4, expires_at="not a time"),
    )
    assert got == screen.ExistingTokens(live=1, latest_created_at="2026-10-01T09:00:00Z")


def test_a_token_without_expiry_is_live() -> None:
    assert _count(_token(1, expires_at=None)).live == 1


def test_only_the_viewers_own_tokens_for_this_client_count() -> None:
    got = _count(
        _token(1, owner="someone-else"),
        _token(2, client=OTHER),
        _token(3, owner=VIEWER.upper()),
    )
    assert got == NOTHING


def test_an_unreadable_created_at_counts_but_is_never_latest() -> None:
    got = _count(_token(1, created_at="yesterday"), _token(2, created_at=None))
    assert got == screen.ExistingTokens(live=2, latest_created_at=None)


def test_latest_is_by_instant_not_by_listing_order() -> None:
    got = _count(_token(5), _token(1, created_at="2026-10-05T09:00:01Z"), _token(4))
    assert got.latest_created_at == "2026-10-05T09:00:01Z"


@pytest.mark.parametrize(
    ("viewer", "client_id"), [("", CLIENT), (None, CLIENT), (VIEWER, ""), (VIEWER, None)]
)
def test_no_viewer_or_no_client_counts_nothing(viewer: Any, client_id: Any) -> None:
    got = _count(_token(1, owner="", client=""), _token(2), viewer=viewer, client_id=client_id)
    assert got == NOTHING
