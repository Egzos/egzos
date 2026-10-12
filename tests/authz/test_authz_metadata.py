# Copyright 2026 Ali Sasanian
# SPDX-License-Identifier: LicenseRef-PolyForm-Strict-1.0.0
"""§6: the metadata document is exactly ten fields, and nothing container-specific."""

from __future__ import annotations

from egzos._types import AS_METADATA_CLOSED_VALUES, AS_METADATA_FIELDS, CAPABILITIES
from egzos.authz import metadata

ISSUER = "https://box.example:8443"


def test_metadata_emits_exactly_the_ten_fields():
    doc = metadata.document(ISSUER + "/")
    assert set(doc) == set(AS_METADATA_FIELDS)
    assert len(doc) == 10
    assert "registration_endpoint" not in doc
    assert doc["issuer"] == ISSUER
    for field, closed in AS_METADATA_CLOSED_VALUES.items():
        assert doc[field] == list(closed)
    assert doc["scopes_supported"] == list(CAPABILITIES)
    assert not any("node:" in s for s in doc["scopes_supported"])
    assert "plain" not in doc["code_challenge_methods_supported"]


def test_metadata_endpoints_live_at_the_issuer_and_outside_the_door_prefix():
    doc = metadata.document(ISSUER)
    endpoints = [v for k, v in doc.items() if k.endswith("_endpoint")]
    assert len(endpoints) == 4 and len(set(endpoints)) == 4
    for url in endpoints:
        assert url.startswith(ISSUER + "/") and not url.startswith(ISSUER + "/v1/")
    assert doc["authorization_endpoint"] == ISSUER + "/authorize"
    assert metadata.DEVICE_ENTRY_PATH not in {u[len(ISSUER) :] for u in endpoints}
