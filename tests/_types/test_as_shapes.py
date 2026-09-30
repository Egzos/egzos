# Copyright 2026 Ali Sasanian
# SPDX-License-Identifier: Apache-2.0
"""
The authorization-server shapes, pinned.

`spec/contracts/authorization-server.md` has no running shape, so unlike `test_container_shapes.py`
these tests cannot transcribe observed behaviour. They pin what the document makes normative and an
edit could quietly widen: the closed metadata field set, the closed advertised values, and the
registration shape §5's exact-match rule hangs on. Written out, never read back from the module.
"""

from __future__ import annotations

from typing import NotRequired, get_type_hints, is_typeddict

import egzos._types as t

# authorization-server.md §6's table, in order.
AS_METADATA_FIELDS = (
    "issuer", "authorization_endpoint", "token_endpoint", "device_authorization_endpoint",
    "revocation_endpoint", "registration_endpoint", "response_types_supported",
    "grant_types_supported", "code_challenge_methods_supported",
    "token_endpoint_auth_methods_supported", "scopes_supported",
)


def test_metadata_surface_is_exactly_the_contracts():
    """§6: a mismatch is a conformance failure, not a documentation bug."""
    assert t.AS_METADATA_FIELDS == AS_METADATA_FIELDS
    assert t.AS_METADATA_ENDPOINT == "/.well-known/oauth-authorization-server"


def test_only_the_two_open_endpoints_are_conditional():
    """§6: advertising an endpoint the container does not implement is non-conforming.

    `revocation_endpoint` is conditional because §9 leaves the endpoint's existence `[OPEN->0.3]`
    (§K answers revocation with `token rm`, an owner path); `registration_endpoint` because §5
    leaves dynamic registration open. The other nine rows are unconditional.
    """
    assert t.AS_METADATA_CONDITIONAL_FIELDS == {"revocation_endpoint", "registration_endpoint"}
    # Conditional means "a row of the table that may be omitted", never "a row not in the table".
    assert t.AS_METADATA_CONDITIONAL_FIELDS <= set(AS_METADATA_FIELDS)
    unconditional = [f for f in AS_METADATA_FIELDS if f not in t.AS_METADATA_CONDITIONAL_FIELDS]
    assert len(unconditional) == 9
    assert "issuer" in unconditional and "token_endpoint" in unconditional


def test_plain_is_never_advertised_and_code_is_the_only_response_type():
    """§2: `S256` only, no downgrade path; the implicit and password grants do not exist here."""
    v = t.AS_METADATA_CLOSED_VALUES
    assert v["code_challenge_methods_supported"] == ("S256",)
    assert v["response_types_supported"] == ("code",)
    assert v["grant_types_supported"] == (
        "authorization_code",
        "refresh_token",
        "urn:ietf:params:oauth:grant-type:device_code",
    )
    assert not {"implicit", "password"} & set(v["grant_types_supported"])
    # §1: three client types, all public — so `none` is the only token-endpoint auth method.
    assert v["token_endpoint_auth_methods_supported"] == ("none",)
    assert t.AS_CLIENT_TYPES == ("browser", "cli", "mcp")
    assert "client_secret" not in t.ClientRegistration.__annotations__


def test_the_scope_vocabulary_is_the_six_names_plus_the_node_form():
    """§7: no scope string that is not a node id, no capability that is not one of the six.

    The two forms are a bare capability name and `node:<node-id>`. A third form arriving is the
    "second, parallel permission system" §7 exists to forbid, so the forms are written out here.
    """
    assert t.CAPABILITIES == ("fetch", "remember", "organize", "publish", "curate", "admin")
    assert t.AS_SCOPE_NODE_PREFIX == "node:"
    assert t.AS_SCOPE_ALL_NODES == t.AS_SCOPE_NODE_PREFIX + "*"
    # §7 consequence 3: `node:*` is the owner's grant — `capabilities.md` §5's `["*"]`.
    assert t.AS_SCOPE_ALL_NODES.removeprefix(t.AS_SCOPE_NODE_PREFIX) == "*"
    # §7 consequence 1: bundle names are never scope strings. Four of the five would be a silent
    # widening if an implementation accepted them as bare names; `admin` is covered below.
    bundles_that_are_not_capabilities = set(t.ROLE_BUNDLES) - set(t.CAPABILITIES)
    assert bundles_that_are_not_capabilities == {"reader", "contributor", "operator", "curator"}
    # The claim, written out so it can fail: none of the four is a bare capability name, and none is
    # spelled in the node form either — the two forms of a `scope` value are all there is. The names
    # are literals on purpose; `bundles_that_are_not_capabilities & set(CAPABILITIES)` cannot state
    # the first claim, because the difference above has already removed anything that would break
    # it.
    assert not {"reader", "contributor", "operator", "curator"} & set(t.CAPABILITIES)
    assert not any(b.startswith(t.AS_SCOPE_NODE_PREFIX) for b in t.ROLE_BUNDLES)


def test_admin_is_the_one_word_the_two_vocabularies_collide_on():
    """§7 consequence 2: in a `scope` value `admin` is the capability, never the all-six bundle.

    A reader who resolves the collision the other way grants five capabilities they did not mean
    to, so the collision is pinned to exactly one word — a sixth bundle named after a capability,
    or a seventh capability named after a bundle, breaks this test rather than an implementation.
    """
    assert set(t.ROLE_BUNDLES) & set(t.CAPABILITIES) == {"admin"}
    # The two meanings of the word, and the distance between them: one capability vs. all six.
    assert t.ROLE_BUNDLES["admin"] == frozenset(t.CAPABILITIES)
    assert len(t.ROLE_BUNDLES["admin"]) == 6
    assert "admin" in t.CAPABILITIES


def test_the_registration_and_device_shapes():
    """§5's four keys plus §11.1's `registered_at`, and §3's `[OPEN->0.3]` completion URI."""
    assert is_typeddict(t.ClientRegistration)
    assert is_typeddict(t.DeviceAuthorization)
    assert set(t.ClientRegistration.__annotations__) == {
        "client_id",
        "client_name",
        "client_type",
        "redirect_uris",
        "registered_at",
    }
    # `__required_keys__` cannot see through PEP 563's string annotations, so read the hints.
    hints = get_type_hints(t.DeviceAuthorization, include_extras=True)
    assert hints["verification_uri_complete"] == NotRequired[str]


def test_the_consent_screen_reads_one_client_entry_and_nothing_more():
    """§11.1: a keyed read of one entry, never a listing — §7's enumeration rule at the registry.

    The five names are written out on BOTH sides of the first assertion's intent: the constant is a
    literal in `_types`, and this test compares it to a literal here. The second assertion then
    holds the constant against `ClientRegistration` with `<=`, not `==`: the read-set must never
    reach beyond what the registration carries (a field added to the registration alone, and not to
    this literal, still fails here rather than silently reaching the consent screen by inheritance),
    but the registration is free to carry a field the consent screen does not read — `client_secret`
    is refused entry today by the assertion below, and a future reserved confidential-client type
    (§1's own `[OPEN->0.3]`) could add one without this pin demanding it be rendered. `==` would
    demand exactly that the day such a field landed. Deriving either side would make the pin a
    tautology that holds for every possible content of the registration.
    """
    assert t.AS_CLIENT_REGISTRY_READ_FIELDS == {
        "client_id",
        "client_name",
        "client_type",
        "redirect_uris",
        "registered_at",
    }
    assert t.AS_CLIENT_REGISTRY_READ_FIELDS <= set(t.ClientRegistration.__annotations__)
    # §11.3's existing-tokens read is a count and a timestamp: no id, no value, ever.
    assert not {"token_id", "token", "tokens", "client_secret"} & t.AS_CLIENT_REGISTRY_READ_FIELDS
    # A registration field carried but deliberately not rendered to the consent screen would need
    # its own assertion here, naming the field and why. None exists yet — `client_secret` is refused
    # entry to the registration itself, above, rather than admitted and then withheld.


def test_the_throttle_surfaces_are_four_closed_words():
    """§12.1 rule 5 and §12.2: the release entry's `surface`, and what `actor` carries.

    Written out rather than derived, because the point of the vocabulary is that it is closed: a
    fifth surface reaching the chain should break a test, not append quietly. `tap` is here because
    §10's `[LEAN]` may be taken; an unused word is not a wrong one.
    """
    assert t.AS_THROTTLE_SURFACES == ("login", "device", "authorize", "tap")
    assert len(set(t.AS_THROTTLE_SURFACES)) == len(t.AS_THROTTLE_SURFACES)
    # §12.2: the caller's network identifier is never the actor, so no surface is one.
    assert not any(s in {"ip", "remote_addr", "caller"} for s in t.AS_THROTTLE_SURFACES)
