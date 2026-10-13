# Copyright 2026 Ali Sasanian
# SPDX-License-Identifier: LicenseRef-PolyForm-Strict-1.0.0
"""§7's grant vocabulary, §11.5's clamp and §11.2's offer: two forms, refused whole, never
narrowed, and minted as rendered."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta, timezone

import pytest

from egzos._types import (
    AS_GRANT_LIFETIME_DEFAULT_SECONDS,
    AS_GRANT_LIFETIME_MAX_SECONDS,
    CAPABILITIES,
    ROLE_BUNDLES,
    ASGrant,
)
from egzos.authz.grant import (
    Grant,
    Offer,
    ScopeVocabularyError,
    clamp_grant_lifetime,
    offer,
    parse_scope,
)


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
        "fetch node:node:a",  # no ULID carries the prefix; it never reaches an `Offer`
        "fetch node:node:*",
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


# --- §11.2 the offer: rendered and minted as one value

NOW = datetime(2026, 10, 13, 12, 0, 0, tzinfo=UTC)


def test_the_offer_carries_the_expansion_not_the_request_string():
    made = offer("remember node:* fetch", client_type="browser", lifetime_seconds=None)
    assert made == Offer(
        ("fetch", "remember"), ("*",), "interactive", AS_GRANT_LIFETIME_DEFAULT_SECONDS
    )


def test_the_offer_holds_the_lifetime_clamped_as_the_screen_renders_it():
    made = offer("fetch node:a", client_type="browser", lifetime_seconds=10**9)
    assert made.lifetime_seconds == AS_GRANT_LIFETIME_MAX_SECONDS


@pytest.mark.parametrize(
    ("client_type", "principal"),
    [("browser", "interactive"), ("cli", "client"), ("mcp", "client")],
)
def test_only_a_browser_client_is_offered_interactive(client_type, principal):
    made = offer("fetch node:a", client_type=client_type, lifetime_seconds=None)
    assert made.principal == principal


@pytest.mark.parametrize("bad", [None, "", "Browser", "confidential", ["browser"], {"browser": 1}])
def test_a_client_type_outside_the_three_is_refused_not_defaulted(bad):
    with pytest.raises(ValueError):
        offer("fetch node:a", client_type=bad, lifetime_seconds=None)  # type: ignore[arg-type]


def test_the_offer_refuses_vocabulary_before_anything_is_rendered():
    with pytest.raises(ScopeVocabularyError):
        offer("reader node:*", client_type="browser", lifetime_seconds=None)


def test_the_offer_refuses_a_malformed_lifetime():
    with pytest.raises(ValueError):
        offer("fetch node:a", client_type="browser", lifetime_seconds=0)


def test_the_decided_grant_is_what_the_offer_rendered_and_nothing_more():
    made = offer("admin fetch node:a node:b", client_type="browser", lifetime_seconds=3600)
    decided = made.decided(NOW)
    assert decided == ASGrant(
        capabilities=["fetch", "admin"],
        scopes=["a", "b"],
        principal="interactive",
        grant_expires_at="2026-10-13T13:00:00Z",
    )
    assert set(decided) == set(ASGrant.__annotations__)


def test_the_grant_expiry_counts_from_the_decision_in_utc():
    made = offer("fetch node:a", client_type="cli", lifetime_seconds=60)
    plus_two = NOW.astimezone(timezone(timedelta(hours=2)))
    assert made.decided(plus_two)["grant_expires_at"] == "2026-10-13T12:01:00Z"


@pytest.mark.parametrize(
    "fields",
    [
        (("fetch",), ("a",), "interactive", AS_GRANT_LIFETIME_MAX_SECONDS + 1),
        (("fetch",), ("a",), "interactive", 0),
        (("fetch",), ("a",), "interactive", True),
        (("fetch",), ("a",), "interactive", 60.0),
        (("reader",), ("a",), "interactive", 60),
        (("fetch",), ("",), "interactive", 60),
        (("fetch",), (None,), "interactive", 60),
        (("fetch",), ("a",), "owner", 60),
        # a1r minor 1 on #233: mutable fields, prefixed ids and duplicates.
        (["fetch"], ("a",), "interactive", 60),
        (("fetch",), ["a"], "interactive", 60),
        (("fetch",), ("node:a",), "interactive", 60),
        (("fetch",), ("node:*",), "interactive", 60),
        (("fetch", "fetch"), ("a",), "interactive", 60),
        (("fetch",), ("a", "a"), "interactive", 60),
        (("fetch",), ("a b",), "interactive", 60),
        (("fetch",), ("a\x00",), "interactive", 60),
        ((["fetch"],), ("a",), "interactive", 60),
        (("fetch",), ("a",), ["interactive"], 60),
    ],
)
def test_an_offer_built_directly_still_holds_only_what_the_contract_allows(fields):
    with pytest.raises(ValueError):
        Offer(*fields)


def test_an_offer_built_directly_from_the_contract_shapes_is_accepted():
    built = Offer(("fetch", "admin"), ("*", "01J0000000000000000000000A"), "client", 60)
    assert built.decided(NOW)["scopes"] == ["*", "01J0000000000000000000000A"]
    assert Offer((), (), "interactive", AS_GRANT_LIFETIME_MAX_SECONDS).decided(NOW) is not None


def test_a_naive_clock_decides_nothing():
    made = offer("fetch node:a", client_type="browser", lifetime_seconds=None)
    assert made.decided(datetime(2026, 10, 13, 12, 0, 0)) is None


def test_the_decided_lists_are_copies_the_offer_does_not_share():
    made = offer("fetch node:a", client_type="browser", lifetime_seconds=None)
    first = made.decided(NOW)
    first["capabilities"].append("admin")
    first["scopes"].append("*")
    assert made.decided(NOW)["capabilities"] == ["fetch"]
    assert made.decided(NOW)["scopes"] == ["a"]
