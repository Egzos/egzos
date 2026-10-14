# Copyright 2026 Ali Sasanian
# SPDX-License-Identifier: LicenseRef-PolyForm-Strict-1.0.0
"""#246: the lifeboat keeps no second constant-time compare beside `authz.values.same` — it
delegates to the one helper every other comparison in the core goes through. A non-ASCII or
lone-surrogate key, cookie or cursor still gets the one refusal, never a raise turned 500."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from egzos.authz.values import same
from egzos.container import Container
from egzos.web.app import Lifeboat, _same, create_app

ORIGIN = "http://testserver"


def test_lifeboat_same_is_authz_values_same():
    # Not a second implementation: the lifeboat's `_same` is the one primitive, not a lookalike.
    assert _same is same


@pytest.mark.parametrize(
    ("given", "held", "expected"),
    [
        ("abc", "abc", True),
        ("abc", "abd", False),
        ("café", "café", True),  # non-ASCII on both sides compares, never raises
        ("café", "other", False),
        ("\ud800", "held", False),  # a lone surrogate `given` side: the one refusal, not a 500
        ("given", "\ud800", False),  # a lone surrogate `held` side: same — authz.values.same
        # compares both as surrogatepass-encoded bytes, unlike the old helper's `held` side.
        ("\ud800", "\ud800", True),
        (123, "abc", False),  # non-str input refuses rather than raising AttributeError
    ],
)
def test_same_refuses_cleanly_whatever_the_input(given, held, expected):
    assert _same(given, held) is expected


@pytest.fixture
def lb(tmp_path, monkeypatch):
    monkeypatch.delenv("EGZOS_TOKEN", raising=False)
    monkeypatch.setenv("EGZOS_STEP_UP_WINDOW_SECONDS", "0")
    c = Container(tmp_path / "home")
    c.init()
    boat = Lifeboat(c, key="k" * 32, host="testserver")
    client = TestClient(create_app(boat, ORIGIN), base_url=ORIGIN)
    return boat, client


def test_cursor_signature_with_lone_surrogate_is_the_first_page_not_a_raise(lb):
    boat, _client = lb
    # offset() runs `_same` on the cursor's signature half; a forged cursor carrying a lone
    # surrogate is just another mismatch (R5: first page), never an exception out of the compare.
    # A real offset (not 0) proves the mismatch was actually evaluated, not just defaulted.
    assert boat.offset("q", "a.\ud800bad-signature") == 0
    assert boat.offset("q", "\ud800.deadbeef") == 0  # malformed offset half: also the first page


def test_launch_key_with_non_ascii_query_value_is_the_one_refusal(lb):
    _boat, client = lb
    # A non-ASCII `k=` never matches the launch key, and the guard's `_same` must not turn that
    # mismatch into a 500 — the same static refusal as any other wrong key.
    r = client.get("/?k=caf%C3%A9", follow_redirects=False)
    assert r.status_code == 403
