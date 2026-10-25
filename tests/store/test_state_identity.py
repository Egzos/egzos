# Copyright 2026 Ali Sasanian
# SPDX-License-Identifier: LicenseRef-PolyForm-Strict-1.0.0
"""`IdentityState` and `ConfigState` (storage.md §3.2) on every backend: the method sets, their
signatures against the Protocols, and what the store keeps."""

from __future__ import annotations

import inspect

import pytest

from egzos._types import ConfigState, IdentityState

IDENTITY_STATE = frozenset({
    "put_user_grant", "get_user_grant", "list_user_grants",
    "put_agent_registration", "get_agent_registration", "list_agent_registrations",
})
CONFIG_STATE = frozenset({"get_config", "put_config"})


def _methods(protocol) -> set[str]:
    return {n for n, _ in inspect.getmembers(protocol, inspect.isfunction) if n[0] != "_"}


@pytest.mark.parametrize(("protocol", "names"), [(IdentityState, IDENTITY_STATE),
                                                  (ConfigState, CONFIG_STATE)])
def test_the_protocols_are_pinned_and_the_backend_matches_them(protocol, names, backend_class):
    assert _methods(protocol) == names
    for name in names:
        expected = list(inspect.signature(getattr(protocol, name)).parameters)
        assert list(inspect.signature(getattr(backend_class, name)).parameters) == expected, name


def _grant(sub="alice", **over):
    return {"sub": sub, "name": sub, "capabilities": ["fetch"], "scopes": ["*"],
            "created_at": "2026-10-23T00:00:00Z", "revoked": False, **over}


def _registration(client_id="agent", sub="alice", **over):
    return {"client_id": client_id, "sub": sub, "name": "an agent", "capabilities": ["fetch"],
            "scopes": ["*"], "created_at": "2026-10-23T00:00:00Z", "revoked": False, **over}


def test_a_revoked_grant_is_kept_and_reads_back(backend):
    backend.put_user_grant(_grant())
    backend.put_user_grant(_grant(revoked=True))
    assert backend.get_user_grant("alice")["revoked"] is True
    assert [g["sub"] for g in backend.list_user_grants()] == ["alice"]
    assert backend.get_user_grant("nobody") is None


def test_registrations_are_keyed_on_client_and_user(backend):
    backend.put_agent_registration(_registration(sub="alice"))
    backend.put_agent_registration(_registration(sub="bob"))
    backend.put_agent_registration(_registration(client_id="other"))
    assert backend.get_agent_registration("agent", "bob")["sub"] == "bob"
    assert backend.get_agent_registration("agent", "carol") is None
    mine = backend.list_agent_registrations(client_id="agent")
    assert [r["sub"] for r in mine] == ["alice", "bob"]
    assert len(backend.list_agent_registrations()) == 3


def test_config_absence_is_absence_and_an_empty_value_is_a_value(backend):
    assert backend.get_config() == {}
    backend.put_config("identity.browser_origins", "")
    backend.put_config("identity.issuer", None)
    assert backend.get_config() == {"identity.browser_origins": "", "identity.issuer": None}


def test_the_records_survive_a_restart(make_backend):
    make_backend().put_user_grant(_grant())
    assert make_backend().get_user_grant("alice")["sub"] == "alice"
