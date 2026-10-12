# Copyright 2026 Ali Sasanian
# SPDX-License-Identifier: LicenseRef-PolyForm-Strict-1.0.0
"""§2: PKCE is mandatory, `S256` only, verified before anything is issued."""

from __future__ import annotations

import pytest

from egzos.authz import pkce

# RFC 7636 Appendix B's worked example.
VERIFIER = "dBjftJeZ4CVP-mB92K27uhbUJU1p1r_wW1gFWFOEjXk"
CHALLENGE = "E9Melhoa2OwvFrEMTJguCHaoeK1t8URWbuGJSstw-cM"


def test_rfc_7636_example_verifies():
    assert pkce.s256(VERIFIER) == CHALLENGE
    assert pkce.check_challenge(CHALLENGE, "S256") == CHALLENGE
    assert pkce.verify(VERIFIER, CHALLENGE)


@pytest.mark.parametrize(
    ("challenge", "method"),
    # `[CHALLENGE]` is a repeated parameter, which is not a challenge.
    [(None, None), ("", "S256"), ([CHALLENGE], "S256"), (CHALLENGE, None), (CHALLENGE, "plain")]
    + [(CHALLENGE, "s256")],
)
def test_missing_challenge_and_plain_are_missing_pkce_never_malformed(challenge, method):
    with pytest.raises(pkce.MissingPKCE):
        pkce.check_challenge(challenge, method)


@pytest.mark.parametrize("challenge", [CHALLENGE[:-1], CHALLENGE + "A", CHALLENGE[:-1] + "="])
def test_a_challenge_no_sha256_digest_could_be_is_malformed(challenge):
    with pytest.raises(pkce.MalformedPKCE):
        pkce.check_challenge(challenge, "S256")


@pytest.mark.parametrize(
    "verifier",
    [None, "", VERIFIER[:-1] + "x", VERIFIER[:42], "a" * 129, VERIFIER + " ", CHALLENGE],
)
def test_wrong_missing_or_malformed_verifier_fails(verifier):
    assert not pkce.verify(verifier, CHALLENGE)
