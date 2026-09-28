# Copyright 2026 Ali Sasanian
# SPDX-License-Identifier: Apache-2.0
"""
The authorization-server shapes, pinned.

`spec/contracts/authorization-server.md` has no running shape, so unlike `test_container_shapes.py`
these tests cannot transcribe observed behaviour. They pin what the document makes normative and an
edit could quietly widen: the closed metadata field set, the closed advertised values, and the
registration shape §5's exact-match rule hangs on. Written out, never read back from the module.
"""

from __future__ import annotations

from typing import NotRequired, get_type_hints, is_typeddict

import egzos._types as t

# authorization-server.md §6's table, in order.
AS_METADATA_FIELDS = (
    "issuer", "authorization_endpoint", "token_endpoint", "device_authorization_endpoint",
    "revocation_endpoint", "registration_endpoint", "response_types_supported",
    "grant_types_supported", "code_challenge_methods_supported",
    "token_endpoint_auth_methods_supported", "scopes_supported",
)


def test_metadata_surface_is_exactly_the_contracts():
    """§6: a mismatch is a conformance failure, not a documentation bug."""
    assert t.AS_METADATA_FIELDS == AS_METADATA_FIELDS
    assert t.AS_METADATA_ENDPOINT == "/.well-known/oauth-authorization-server"


def test_only_the_two_open_endpoints_are_conditional():
    """§6: advertising an endpoint the container does not implement is non-conforming.

    `revocation_endpoint` is conditional because §9 leaves the endpoint's existence `[OPEN->0.3]`
    (§K answers revocation with `token rm`, an owner path); `registration_endpoint` because §5
    leaves dynamic registration open. The other nine rows are unconditional.
    """
    assert t.AS_METADATA_CONDITIONAL_FIELDS == {"revocation_endpoint", "registration_endpoint"}
    # Conditional means "a row of the table that may be omitted", never "a row not in the table".
    assert t.AS_METADATA_CONDITIONAL_FIELDS <= set(AS_METADATA_FIELDS)
    unconditional = [f for f in AS_METADATA_FIELDS if f not in t.AS_METADATA_CONDITIONAL_FIELDS]
    assert len(unconditional) == 9
    assert "issuer" in unconditional and "token_endpoint" in unconditional


def test_plain_is_never_advertised_and_code_is_the_only_response_type():
    """§2: `S256` only, no downgrade path; the implicit and password grants do not exist here."""
    v = t.AS_METADATA_CLOSED_VALUES
    assert v["code_challenge_methods_supported"] == ("S256",)
    assert v["response_types_supported"] == ("code",)
    assert v["grant_types_supported"] == (
        "authorization_code",
        "refresh_token",
        "urn:ietf:params:oauth:grant-type:device_code",
    )
    assert not {"implicit", "password"} & set(v["grant_types_supported"])
    # §1: three client types, all public — so `none` is the only token-endpoint auth method.
    assert v["token_endpoint_auth_methods_supported"] == ("none",)
    assert t.AS_CLIENT_TYPES == ("browser", "cli", "mcp")
    assert "client_secret" not in t.ClientRegistration.__annotations__


def test_the_registration_and_device_shapes():
    """§5's four keys, and §3's response with `verification_uri_complete` left `[OPEN->0.3]`."""
    assert is_typeddict(t.ClientRegistration)
    assert is_typeddict(t.DeviceAuthorization)
    assert set(t.ClientRegistration.__annotations__) == {
        "client_id",
        "client_name",
        "client_type",
        "redirect_uris",
    }
    # `__required_keys__` cannot see through PEP 563's string annotations, so read the hints.
    hints = get_type_hints(t.DeviceAuthorization, include_extras=True)
    assert hints["verification_uri_complete"] == NotRequired[str]
