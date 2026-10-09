# Copyright 2026 Ali Sasanian
# SPDX-License-Identifier: Apache-2.0
"""
PKCE, mandatory for every client, `S256` only (authorization-server.md §2).

There is no `plain`, no downgrade and no configuration that turns any of this off. A request with
no challenge, or with `plain`, is not one this AS recognises: it never reaches the redirectable
tier and is row (d) cause `missing_pkce` — never `malformed` (§5.3 clause 1).
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import re

S256 = "S256"

# RFC 7636 §4.1: a verifier is 43–128 characters of the unreserved set. §4.2: an S256 challenge is
# the unpadded base64url of a SHA-256 digest, so exactly 43 characters.
_VERIFIER = re.compile(r"[A-Za-z0-9\-._~]{43,128}")
_CHALLENGE = re.compile(r"[A-Za-z0-9\-_]{43}")


class MissingPKCE(ValueError):
    """No challenge, or a method other than `S256` (row (d) cause `missing_pkce`)."""


class MalformedPKCE(ValueError):
    """An `S256` challenge no SHA-256 digest could encode to (row (d) cause `malformed`)."""


def check_challenge(challenge: str | None, method: str | None) -> str:
    """Admit an authorization request's PKCE pair, returning the challenge to bind the code to.

    The method is compared exactly: `s256` is not `S256`, and an absent method is not a default."""
    if not challenge or method != S256:
        raise MissingPKCE("missing_pkce")
    if not _CHALLENGE.fullmatch(challenge):
        raise MalformedPKCE("malformed")
    return challenge


def s256(verifier: str) -> str:
    digest = hashlib.sha256(verifier.encode("ascii")).digest()
    return base64.urlsafe_b64encode(digest).rstrip(b"=").decode("ascii")


def verify(verifier: str | None, challenge: str) -> bool:
    """§2: the token request's `code_verifier` against the stored challenge, before anything is
    issued. A missing or malformed verifier is a failed verification, never a skipped one."""
    if not isinstance(verifier, str) or not _VERIFIER.fullmatch(verifier):
        return False
    return hmac.compare_digest(s256(verifier), challenge)
