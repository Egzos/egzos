# Copyright 2026 Ali Sasanian
# SPDX-License-Identifier: Apache-2.0
"""§7's grant vocabulary and §11.5's clamp: two forms, refused whole, never narrowed."""

from __future__ import annotations

import pytest

from egzos._types import (
    AS_GRANT_LIFETIME_DEFAULT_SECONDS,
    AS_GRANT_LIFETIME_MAX_SECONDS,
    CAPABILITIES,
    ROLE_BUNDLES,
)
from egzos.authz.grant import Grant, ScopeVocabularyError, clamp_grant_lifetime, parse_scope


def test_two_forms_expand_to_capabilities_and_bare_node_ids():
    grant = parse_scope("remember node:project:alpha fetch node:user:self")
    assert grant == Grant(("fetch", "remember"), ("project:alpha", "user:self"))


def test_node_star_becomes_the_owner_grant_without_its_prefix():
    assert parse_scope("fetch node:*").scopes == ("*",)


def test_admin_is_the_capability_never_the_bundle():
    assert parse_scope("admin node:*").capabilities == ("admin",)
    assert len(ROLE_BUNDLES["admin"]) == len(CAPABILITIES)  # the bundle it is NOT expanded to


def test_every_capability_is_accepted_and_ordered_as_the_contract_lists_them():
    grant = parse_scope(" ".join(reversed(CAPABILITIES)) + " node:x")
    assert grant.capabilities == CAPABILITIES


def test_duplicates_collapse():
    assert parse_scope("fetch fetch node:a node:a") == Grant(("fetch",), ("a",))


@pytest.mark.parametrize("bundle", [b for b in ROLE_BUNDLES if b not in CAPABILITIES])
def test_role_bundles_are_refused(bundle):
    with pytest.raises(ScopeVocabularyError):
        parse_scope(f"{bundle} node:*")


@pytest.mark.parametrize(
    "value",
    [
        None,
        "",
        " ",
        "fetch  node:a",  # doubled delimiter
        " fetch node:a",
        "fetch node:a ",
        "fetch\tnode:a",
        "fetch\nnode:a",
        "fetch node:",
        "fetch node:a\x00",
        "fetch openid",
        "fetch principal:interactive",  # §10.3: no principal parameter in any spelling
        "interactive node:*",
        "FETCH node:*",
        "fetch nodes:*",
        "fetch node:a " + "x" * 5000,
    ],
)
def test_anything_else_refuses_the_whole_value_never_narrowed(value):
    with pytest.raises(ScopeVocabularyError) as err:
        parse_scope(value)
    assert str(err.value) == "invalid_scope"


def test_non_string_scope_is_refused():
    with pytest.raises(ScopeVocabularyError):
        parse_scope(["fetch", "node:a"])  # type: ignore[arg-type]


def test_grant_lifetime_defaults_and_clamps_never_refuses_for_length():
    assert clamp_grant_lifetime(None) == AS_GRANT_LIFETIME_DEFAULT_SECONDS
    assert clamp_grant_lifetime(60) == 60
    assert clamp_grant_lifetime(AS_GRANT_LIFETIME_MAX_SECONDS) == AS_GRANT_LIFETIME_MAX_SECONDS
    assert clamp_grant_lifetime(10**12) == AS_GRANT_LIFETIME_MAX_SECONDS


@pytest.mark.parametrize("bad", [0, -1, True, 1.5, "3600"])
def test_a_value_that_is_not_a_lifetime_is_malformed_not_clamped(bad):
    with pytest.raises(ValueError):
        clamp_grant_lifetime(bad)
