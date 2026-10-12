# Copyright 2026 Ali Sasanian
# SPDX-License-Identifier: LicenseRef-PolyForm-Strict-1.0.0
"""
AS metadata discovery (authorization-server.md §6): RFC 8414's document, served unauthenticated.

Exactly the ten `AS_METADATA_FIELDS`, no more and no fewer. Nothing container-specific — no node
id, no client name, no owner — and the `node:` scope form is not advertised ([0.3 · 28]).
`registration_endpoint` is absent, not null ([0.3 · 10]).

The endpoint paths are this implementation's: the contract fixes `/authorize` and `/device` by
name and leaves the other three to the document a client reads them from, which is this one.
`rest.md` §1 keeps them out of the door's `/v1/` prefix.
"""

from __future__ import annotations

from typing import Any

from egzos._types import AS_METADATA_CLOSED_VALUES, CAPABILITIES

AUTHORIZE_PATH = "/authorize"
TOKEN_PATH = "/token"
DEVICE_AUTHORIZATION_PATH = "/device_authorization"
REVOCATION_PATH = "/revoke"
#: The device-code entry page (§11.8), RFC 8628's `verification_uri`. Not a metadata field.
DEVICE_ENTRY_PATH = "/device"
#: The login page (§11.7; consent.md §2.1 names the path). Not a metadata field either: it sits
#: here so every path the AS serves is fixed in one module, which the router and §11.7's
#: `continue` allowlist both read.
LOGIN_PATH = "/login"


def document(issuer: str) -> dict[str, Any]:
    """The metadata document for a container whose origin is `issuer` (scheme, host, port; no
    path, query or fragment — RFC 8414 §2's identifier, which every token's `iss` repeats)."""
    issuer = issuer.rstrip("/")
    return {
        "issuer": issuer,
        "authorization_endpoint": issuer + AUTHORIZE_PATH,
        "token_endpoint": issuer + TOKEN_PATH,
        "device_authorization_endpoint": issuer + DEVICE_AUTHORIZATION_PATH,
        "revocation_endpoint": issuer + REVOCATION_PATH,
        **{field: list(values) for field, values in AS_METADATA_CLOSED_VALUES.items()},
        "scopes_supported": list(CAPABILITIES),
    }
