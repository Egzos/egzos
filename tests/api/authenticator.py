# Copyright 2026 Ali Sasanian
# SPDX-License-Identifier: LicenseRef-PolyForm-Strict-1.0.0
"""A software WebAuthn authenticator for tests: what a phone's Face ID or a laptop's Touch ID does,
minus the hardware. It answers creation and request options as a browser hands them to the
authenticator, with user verification, so the container's `webauthn` library verifies the result
exactly as it would a real one."""

from __future__ import annotations

import base64
import hashlib
import json
import secrets
from urllib.parse import urlsplit

import cbor2
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import ec

UP, UV, AT = 0x01, 0x04, 0x40


def b64(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode()


class SoftAuthenticator:
    def __init__(self, origin: str, *, verify_user: bool = True):
        self.origin = origin
        self.rp_id = urlsplit(origin).hostname
        self.key = ec.generate_private_key(ec.SECP256R1())
        self.credential_id = secrets.token_bytes(16)
        self.counter = 0
        self.verify_user = verify_user

    def _flags(self, extra: int = 0) -> bytes:
        return bytes([UP | (UV if self.verify_user else 0) | extra])

    def _client_data(self, kind: str, challenge: str) -> bytes:
        return json.dumps({"type": kind, "challenge": challenge, "origin": self.origin,
                           "crossOrigin": False}).encode()

    def create(self, options: dict) -> dict:
        """navigator.credentials.create(), with `none` attestation."""
        assert options["rp"]["id"] == self.rp_id
        numbers = self.key.public_key().public_numbers()
        cose = cbor2.dumps({1: 2, 3: -7, -1: 1, -2: numbers.x.to_bytes(32, "big"),
                            -3: numbers.y.to_bytes(32, "big")})
        auth_data = (
            hashlib.sha256(self.rp_id.encode()).digest() + self._flags(AT)
            + self.counter.to_bytes(4, "big") + bytes(16)
            + len(self.credential_id).to_bytes(2, "big") + self.credential_id + cose
        )
        attestation = cbor2.dumps({"fmt": "none", "attStmt": {}, "authData": auth_data})
        client_data = self._client_data("webauthn.create", options["challenge"])
        return {
            "id": b64(self.credential_id), "rawId": b64(self.credential_id), "type": "public-key",
            "response": {"clientDataJSON": b64(client_data),
                         "attestationObject": b64(attestation)},
        }

    def get(self, options: dict) -> dict:
        """navigator.credentials.get(): an assertion over the request's challenge."""
        assert options["rpId"] == self.rp_id
        self.counter += 1
        auth_data = (hashlib.sha256(self.rp_id.encode()).digest() + self._flags()
                     + self.counter.to_bytes(4, "big"))
        client_data = self._client_data("webauthn.get", options["challenge"])
        signature = self.key.sign(auth_data + hashlib.sha256(client_data).digest(),
                                  ec.ECDSA(hashes.SHA256()))
        return {
            "id": b64(self.credential_id), "rawId": b64(self.credential_id), "type": "public-key",
            "response": {"clientDataJSON": b64(client_data), "authenticatorData": b64(auth_data),
                         "signature": b64(signature), "userHandle": None},
        }
