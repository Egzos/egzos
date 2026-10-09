# Copyright 2026 Ali Sasanian
# SPDX-License-Identifier: Apache-2.0
"""§5.1–§5.2: exact string match, the loopback port exception, and `localhost` refused."""

from __future__ import annotations

import pytest

from egzos.authz.redirects import RedirectURIRefused, check_registrable, match_any, matches

CB = "https://egzos.io/cb"


@pytest.mark.parametrize(
    "requested",
    [
        "https://egzos.io/cb/x",  # path prefix
        "https://egzos.io/cbx",  # string prefix
        "https://egzos.io/cb/",  # trailing slash
        "https://egzos.io/cb?x=1",  # query
        "https://egzos.io/cb#f",  # fragment
        "http://egzos.io/cb",  # scheme downgrade
        "https://EGZOS.io/cb",  # host case
        "https://egzos.io:443/cb",  # default port spelled out
        "https://evil.egzos.io/cb",
        "https://egzos.io/CB",
        "",
    ],
)
def test_https_matches_byte_for_byte_and_nothing_else(requested):
    assert matches(CB, CB)
    assert not matches(requested, CB)


@pytest.mark.parametrize(
    ("registered", "requested"),
    [
        ("http://127.0.0.1/cb", "http://127.0.0.1:8731/cb"),
        ("http://127.0.0.1:9000/cb", "http://127.0.0.1:8731/cb"),
        ("http://127.0.0.1:9000/cb", "http://127.0.0.1/cb"),
        ("http://[::1]/cb?a=1", "http://[::1]:5173/cb?a=1"),
        ("http://127.0.0.1", "http://127.0.0.1:1"),
    ],
)
def test_loopback_ignores_the_port_only(registered, requested):
    assert matches(requested, registered)


@pytest.mark.parametrize(
    ("registered", "requested"),
    [
        ("http://127.0.0.1/cb", "http://127.0.0.1:8731/cb/"),  # path still exact
        ("http://127.0.0.1/cb", "http://127.0.0.1:8731/cb?x"),  # query still exact
        ("http://127.0.0.1/cb", "http://[::1]:8731/cb"),  # host still exact
        ("http://127.0.0.1/cb", "https://127.0.0.1:8731/cb"),  # scheme still exact
        ("http://127.0.0.1/cb", "http://127.0.0.1.evil.com/cb"),
        ("http://127.0.0.1/cb", "http://127.0.0.1:80@evil.com/cb"),
        ("http://127.0.0.1/cb", "http://127.0.0.1:/cb"),
        ("http://127.0.0.1/cb", "http://127.0.0.1:8x/cb"),
        ("http://127.0.0.1/cb", "http://127.0.0.2:8731/cb"),
        ("http://localhost/cb", "http://localhost:8731/cb"),  # the name gets no exception
        ("https://egzos.io/cb", "http://127.0.0.1/cb"),
    ],
)
def test_loopback_exception_bounded_to_the_port(registered, requested):
    assert not matches(requested, registered)


def test_non_strings_never_match():
    assert not matches(None, CB)  # type: ignore[arg-type]


def test_match_any_compares_against_the_whole_allowlist():
    allow = ["https://a.example/cb", "http://127.0.0.1/cb"]
    assert match_any("http://127.0.0.1:4000/cb", allow)
    assert match_any("https://a.example/cb", allow)
    assert not match_any("https://a.example/cb2", allow)
    assert not match_any(CB, [])


@pytest.mark.parametrize(
    "uri",
    [CB, "https://egzos.io/cb?client=web", "http://127.0.0.1/cb", "http://[::1]:5173/cb",
     "http://127.0.0.1"],
)
def test_registrable(uri):
    assert check_registrable(uri) == uri


@pytest.mark.parametrize(
    "uri",
    [
        "http://localhost/cb",
        "http://LOCALHOST:5173/cb",
        "https://localhost/cb",
        "https://app.localhost/cb",
        "http://egzos.io/cb",  # http off loopback
        "http://127.0.0.2/cb",
        "https://egzos.io/cb#frag",
        "https://user:pw@egzos.io/cb",
        "https://egzos.io@evil.com/cb",
        "https:///cb",
        "/cb",
        "egzos.io/cb",
        "javascript:alert(1)",
        "https://egzos.io/c b",
        "https://egzos.io\\cb",
        "https://egzos.io:99999/cb",
        "https://egzos.io/\x00",
        "",
        None,
    ],
)
def test_refused_at_registration(uri):
    with pytest.raises(RedirectURIRefused):
        check_registrable(uri)
