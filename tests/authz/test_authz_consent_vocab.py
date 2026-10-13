# Copyright 2026 Ali Sasanian
# SPDX-License-Identifier: LicenseRef-PolyForm-Strict-1.0.0
"""The consent screen's vocabulary in authz/pages.py: D-C1's table and consent.md §5's formats."""

from __future__ import annotations

import pytest

from egzos._types import CAPABILITIES
from egzos.authz import pages, presence
from egzos.authz.grant import Offer, offer

ATLAS = {"n1": pages.ScopeLabel("project", "atlas")}


def mcp(scope: str) -> Offer:
    return offer(scope, client_type="mcp", lifetime_seconds=None)


# --- D-C1 -------------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("ring", "flagged", "wide"),
    [
        ("inbox", False, False),
        ("thread", False, False),
        ("project", False, False),
        ("team", False, False),
        ("org", True, True),
        ("exo", True, True),
        ("uxo", True, True),
        ("global", True, True),
        ("user", False, True),  # the personal root has no ring rank and reaches everything personal
        ("moon", False, True),  # an unknown ring word: wide, not flagged (#259)
    ],
)
def test_a_scope_labels_ring_rows(ring: str, flagged: bool, wide: bool) -> None:
    label = pages.ScopeLabel(ring, "x")
    assert (label.flagged, label.wide, label.ref) == (flagged, wide, f"{ring}:x")
    assert pages.is_wide(mcp("fetch node:n1"), {"n1": label}) is wide


def test_a_narrow_grant_is_a_client_reader_on_a_project() -> None:
    assert pages.is_wide(mcp("fetch remember organize publish node:n1"), ATLAS) is False


@pytest.mark.parametrize("cap", ["curate", "admin"])
def test_curate_or_admin_is_wide(cap: str) -> None:
    assert pages.is_wide(mcp(f"fetch {cap} node:n1"), ATLAS) is True


def test_the_whole_container_is_wide_and_needs_no_label() -> None:
    assert pages.is_wide(mcp("fetch node:*"), {}) is True


def test_an_interactive_principal_is_wide() -> None:
    browser = offer("fetch node:n1", client_type="browser", lifetime_seconds=None)
    assert browser.principal == "interactive"
    assert pages.is_wide(browser, ATLAS) is True


def test_one_wide_scope_among_narrow_ones_makes_the_grant_wide() -> None:
    labels = {**ATLAS, "n2": pages.ScopeLabel("org", "acme")}
    assert pages.is_wide(mcp("fetch node:n1 node:n2"), labels) is True


def test_a_granted_id_with_no_label_is_refused_not_read_as_narrow() -> None:
    with pytest.raises(ValueError):
        pages.is_wide(mcp("fetch node:n1 node:n2"), ATLAS)
    with pytest.raises(ValueError):
        pages.is_wide(mcp("fetch node:n1"), {"n1": ("project", "atlas")})  # type: ignore[dict-item]
    with pytest.raises(TypeError):
        pages.is_wide("fetch node:n1", ATLAS)  # type: ignore[arg-type]


def test_a_scope_label_is_two_strings() -> None:
    with pytest.raises(TypeError):
        pages.ScopeLabel("project", None)  # type: ignore[arg-type]
    with pytest.raises(TypeError):
        pages.ScopeLabel(1, "atlas")  # type: ignore[arg-type]


# --- §5's formats -----------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("seconds", "left"),
    [
        (90 * 86400, "90 d"),
        (86400 * 2 + 5, "2 d"),
        (86400, "1 d"),
        (86399, "23 h"),
        (3600 * 5, "5 h"),
        (3599, "59 min"),
        (180, "3 min"),
        (30, "1 min"),
    ],
)
def test_countdown(seconds: int, left: str) -> None:
    assert pages.countdown(seconds) == left


@pytest.mark.parametrize("seconds", [0, -1, True, 1.5, "60", None])
def test_countdown_refuses_what_is_not_a_lifetime(seconds: object) -> None:
    with pytest.raises(ValueError):
        pages.countdown(seconds)  # type: ignore[arg-type]


def test_cut_name() -> None:
    assert pages.cut_name("Claude") == "Claude"
    assert pages.cut_name("N" * 64) == "N" * 64
    assert pages.cut_name("N" * 65) == "N" * 64 + "…"


def test_short_id() -> None:
    assert pages.short_id("cli_01J7ABCDEFGH9KQ2") == "cli_01J7 … 9KQ2"
    assert pages.short_id("cli_01J7ABCD") == "cli_01J7ABCD"


@pytest.mark.parametrize(
    ("uri", "shown", "local"),
    [
        ("https://claude.ai/cb?x=1#f", "https://claude.ai", False),
        ("https://box.example:8443/a/b", "https://box.example:8443", False),
        ("http://127.0.0.1:8731/cb", "http://127.0.0.1:8731", True),
        ("http://127.0.0.1/cb", "http://127.0.0.1", True),
        ("http://[::1]:5173/cb", "http://[::1]:5173", True),
        ("http://127.0.0.2:80/cb", "http://127.0.0.2:80", False),
        ("https://user@agent.example/cb", "https://agent.example", False),
    ],
)
def test_origin_is_scheme_host_and_port_only(uri: str, shown: str, local: bool) -> None:
    assert pages.origin(uri) == (shown, local)


@pytest.mark.parametrize(
    ("caps", "line"),
    [
        (("fetch",), "role · reader"),
        (("fetch", "remember"), "role · contributor"),
        (("fetch", "remember", "organize", "publish"), "role · operator"),
        (("fetch", "remember", "organize", "publish", "curate"), "role · curator"),
        (CAPABILITIES, "role · admin"),
        (("fetch", "publish"), "custom set"),
        (("admin",), "custom set"),  # `admin` alone is the capability, not the bundle
    ],
)
def test_role_line(caps: tuple[str, ...], line: str) -> None:
    assert pages.role_line(caps) == line


def test_whole_container_is_section_2_3s_string() -> None:
    assert pages.WHOLE_CONTAINER == "whole container"
    assert pages.WHOLE_CONTAINER not in pages.COPY.values()  # not a §13 key: #259


def test_the_stylesheet_head_is_presences_public_tokens_css() -> None:
    assert pages.css() == presence.tokens_css() + pages.STYLE
    assert presence.tap_css() == presence.tokens_css() + presence.TAP_STYLE
