# Copyright 2026 Ali Sasanian
# SPDX-License-Identifier: LicenseRef-PolyForm-Strict-1.0.0
"""The shared digest and comparison (authz/values.py)."""

from __future__ import annotations

import pytest

from egzos import auth
from egzos.authz import values


def test_token_secrets_share_the_one_digest():
    # One function, not two copies.
    assert auth._hash is values.digest
    assert values.digest("abc") == (
        "ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad"
    )


@pytest.mark.parametrize(
    ("given", "stored", "equal"),
    [
        ("client", "client", True),
        ("client", "Client", False),
        ("ñ", "ñ", True),  # non-ASCII `str` would raise in a bare `compare_digest`
        ("ñ", "n", False),
        ("\ud800", "\ud800", True),  # a lone surrogate would raise in a bare `encode`
        ("\ud800", "x", False),
        (None, "client", False),
        ("client", None, False),
        (b"client", "client", False),
        (["client"], "client", False),
        ("", "", True),
    ],
)
def test_same_is_total_and_never_raises(given, stored, equal):
    assert values.same(given, stored) is equal


def test_every_authz_comparison_goes_through_one_helper():
    # Four private copies once existed (#241's review); a fifth must not reappear.
    from pathlib import Path

    root = Path(values.__file__).parent
    for path in root.glob("*.py"):
        if path.name == "values.py":
            continue
        assert "compare_digest" not in path.read_text(), path.name


def test_a_bearer_value_with_a_lone_surrogate_is_refused_not_raised(tmp_path):
    from egzos.container import OWNER, Container

    c = Container(tmp_path)
    c.init()
    t = c.auth.mint(principal="client", owner=OWNER, client="probe", role="reader",
                    scopes=["*"], actor=OWNER, by_principal="interactive")
    assert c.auth.use(t.secret + "\ud800") is None
    assert c.auth.use(t.secret).id == t.id
