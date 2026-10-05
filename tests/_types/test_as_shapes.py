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

import pytest

import egzos._types as t

# authorization-server.md §11.1's table: the AS-internal `client_type` literal, and the kind word
# `consent.md` renders beside the client name (its `kind.*` copy keys). Transcribed from the two
# documents, never read back from the module under test.
CONSENT_KIND_ROWS = [
    ("browser", "browser"),
    ("cli", "device"),
    ("mcp", "mcp"),
]

# authorization-server.md §6's table, in order. Ten rows, all unconditional: [0.3 · 10] removed
# `registration_endpoint` from the document and [0.3 · 11] made `revocation_endpoint` a row like
# any other.
AS_METADATA_FIELDS = (
    "issuer", "authorization_endpoint", "token_endpoint", "device_authorization_endpoint",
    "revocation_endpoint", "response_types_supported",
    "grant_types_supported", "code_challenge_methods_supported",
    "token_endpoint_auth_methods_supported", "scopes_supported",
)


def test_metadata_surface_is_exactly_the_contracts():
    """§6: a mismatch is a conformance failure, not a documentation bug."""
    assert t.AS_METADATA_FIELDS == AS_METADATA_FIELDS
    assert t.AS_METADATA_ENDPOINT == "/.well-known/oauth-authorization-server"


def test_no_metadata_row_is_conditional_and_registration_is_absent():
    """§6: the field set is closed in BOTH directions, and nothing in it is optional.

    [0.3 · 11] decided the RFC 7009 endpoint exists, so `revocation_endpoint` is unconditional;
    [0.3 · 10] decided there is no open dynamic client registration, so `registration_endpoint` is
    absent from the document — not present-and-null, which would tell a reader the container
    considered the question. `AS_METADATA_CONDITIONAL_FIELDS` is gone rather than empty: an empty
    constant is a place for a later field to be quietly added, which is what this test pins.
    """
    assert not hasattr(t, "AS_METADATA_CONDITIONAL_FIELDS")
    assert "AS_METADATA_CONDITIONAL_FIELDS" not in t.__all__
    assert "registration_endpoint" not in AS_METADATA_FIELDS
    assert "revocation_endpoint" in AS_METADATA_FIELDS
    assert len(AS_METADATA_FIELDS) == 10


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


@pytest.mark.parametrize(("client_type", "kind"), CONSENT_KIND_ROWS)
def test_each_client_type_renders_its_contracted_kind_word(client_type, kind):
    """Forward, one row at a time: §11.1's table, with `cli` rendering as `device`."""
    assert t.CONSENT_KIND_FROM_CLIENT_TYPE[client_type] == kind


@pytest.mark.parametrize(("client_type", "kind"), CONSENT_KIND_ROWS)
def test_each_kind_word_is_rendered_by_exactly_one_client_type(client_type, kind):
    """Reverse, one row at a time: no kind word is unreachable, none has two sources."""
    assert [c for c, k in t.CONSENT_KIND_FROM_CLIENT_TYPE.items() if k == kind] == [client_type]


def test_the_kind_mapping_spans_both_vocabularies_exactly():
    """§11.1 binds `AS_CLIENT_TYPES` to `consent.md`'s rendered kinds; neither side may grow alone.

    A fourth client type with no kind word is a client the consent page cannot render, and a kind
    word no client type produces is a copy key nothing emits.
    """
    assert set(t.CONSENT_KIND_FROM_CLIENT_TYPE) == set(t.AS_CLIENT_TYPES)
    assert set(t.CONSENT_KIND_FROM_CLIENT_TYPE.values()) == set(t.CONSENT_KINDS)
    assert t.CONSENT_KINDS == ("browser", "device", "mcp")


def test_cli_is_the_one_row_where_the_two_vocabularies_differ():
    """The reason the mapping is named rather than left to prose (#10 F25).

    Two rows are identities, so a surface that re-derives the kind from the literal agrees on
    `browser` and `mcp` and emits `kind.cli` — a copy key that does not exist — on the third.
    """
    differing = {c for c, k in t.CONSENT_KIND_FROM_CLIENT_TYPE.items() if c != k}
    assert differing == {"cli"}
    assert "cli" not in t.CONSENT_KINDS
    assert "device" not in t.AS_CLIENT_TYPES


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
    """§5's four keys plus §11.1's `registered_at`, and §3's device response without the URI.

    [0.3 · 21] does not issue `verification_uri_complete`: the key is absent from the response
    entirely, so the shape must not carry it even as `NotRequired`. An optional key is a key an
    implementation may populate, and the decision was that none may.
    """
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
    assert "verification_uri_complete" not in hints
    assert set(hints) == {
        "device_code",
        "user_code",
        "verification_uri",
        "expires_in",
        "interval",
    }
    # Every key is required: RFC 8628 names all five, and none is conditional here.
    assert not any(h == NotRequired[str] for h in hints.values())


def test_the_two_decided_lifetimes():
    """§2's 60 s code ([0.3 · 16]) and §9.3's 1 h access token ([0.3 · 17]).

    Both are contract values rather than defaults a deployment may raise, so they are pinned as
    literals here: a config key that moved either would have to change this test to land.
    """
    assert t.AS_CODE_LIFETIME_SECONDS == 60
    assert t.AS_ACCESS_TOKEN_LIFETIME_SECONDS == 3600
    # The code is far shorter-lived than the token it is exchanged for; a code outliving its token
    # would invert the two risks §2 and §9.3 bound.
    assert t.AS_CODE_LIFETIME_SECONDS < t.AS_ACCESS_TOKEN_LIFETIME_SECONDS


def test_the_consent_screen_reads_one_client_entry_and_nothing_more():
    """§11.1: a keyed read of one entry, never a listing — §7's enumeration rule at the registry.

    The five names are written out on BOTH sides of the first assertion's intent: the constant is a
    literal in `_types`, and this test compares it to a literal here — that literal pin, plus
    `test_the_registration_and_device_shapes`'s own `==` on `ClientRegistration`, is what catches a
    field silently added to the registration: either test's literal goes stale and fails, so the
    field cannot reach the consent screen by inheritance without one of them noticing. The second
    assertion here holds the constant against `ClientRegistration` with `<=`, not `==`, for a
    narrower purpose: the read-set must never reach beyond what the registration carries, but the
    registration is free to carry a field the consent screen does not read — `client_secret` is
    refused entry today by the assertion below, and a future reserved confidential-client type
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


def test_the_error_redirect_carries_exactly_two_fields_and_never_a_description():
    """§11.6: `{error, state}` and nothing else — `error_description`/`error_uri` are MUST NOT.

    Written out rather than derived, the same reason `AS_CLIENT_REGISTRY_READ_FIELDS` is: this is
    Part B's one closed vocabulary that shipped with no constant behind it until this round, even
    though the surfaces, the registry read and all four cause tuples got one. The permitted and
    forbidden sets are asserted disjoint so a future edit cannot satisfy one by breaking the other.
    """
    assert t.AS_AUTHORIZE_ERROR_REDIRECT_FIELDS == {"error", "state"}
    assert t.AS_AUTHORIZE_ERROR_REDIRECT_FORBIDDEN_FIELDS == {"error_description", "error_uri"}
    assert not t.AS_AUTHORIZE_ERROR_REDIRECT_FIELDS & t.AS_AUTHORIZE_ERROR_REDIRECT_FORBIDDEN_FIELDS
    # §7's convergence: the field removed rather than constrained is a description, never a code.
    assert "error" in t.AS_AUTHORIZE_ERROR_REDIRECT_FIELDS
    assert "error_description" not in t.AS_AUTHORIZE_ERROR_REDIRECT_FIELDS


def test_the_throttle_surfaces_are_five_closed_words():
    """§12.1 rule 5 and §12.2: the release entry's `surface`, and what `actor` carries.

    Written out rather than derived, because the point of the vocabulary is that it is closed: a
    fifth surface reaching the chain should break a test, not append quietly. `tap` is here because
    `consent.md`'s D-C6 throttles the tap page unconditionally, as the fourth surface, independent
    of whether §10.5's `[LEAN]` is taken — `[LEAN]` picks which channel the tap rides, not
    whether the word is used. `revoke` is §9.2's owner path ([0.3 · 11]); `actor` is [0.3 · 34].
    """
    assert t.AS_THROTTLE_SURFACES == ("login", "device", "authorize", "tap", "revoke")
    assert len(set(t.AS_THROTTLE_SURFACES)) == len(t.AS_THROTTLE_SURFACES)
    # §12.2: the caller's network identifier is never the actor, so no surface is one.
    assert not any(s in {"ip", "remote_addr", "caller"} for s in t.AS_THROTTLE_SURFACES)


def test_the_pre_token_cause_vocabularies_are_closed_per_row():
    """§12's table, rows (a), (b), (d) and (f) — four closed `details.cause` vocabularies.

    Written out rather than derived, for the same reason
    `test_the_throttle_surfaces_are_five_closed_words` is: a cause arriving at one of these rows
    that is not in its tuple should break a test, not append quietly. #61's own history has an
    instance: a seventh cause, `token_presented`, arrived at row (d) with nothing to catch it,
    caught only by hand on a later reading of the table. `throttled` recurs across (a), (b) and (d)
    on purpose: §11.0 substep 2 gives each surface its own uniform failure, one throttle per
    surface, so the word is not shared state between the tuples, only the same English word used
    three times.
    """
    assert t.AS_LOGIN_CAUSES == ("wrong", "unknown", "throttled")
    assert t.AS_DEVICE_REDEMPTION_CAUSES == ("invalid", "expired", "used", "malformed", "throttled")
    assert t.AS_AUTHORIZE_PRETRUST_CAUSES == (
        "unknown_client",
        "redirect_mismatch",
        "malformed",
        "missing_pkce",
        "throttled",
        "replayed",
        "token_presented",
    )
    # Row (f): two causes, not three — `expiry` is clamped (§11.5), never rejected for that reason
    # alone, so it is not a closed cause here even though `consent.md` names it as one of three.
    assert t.AS_AUTHORIZE_POSTTRUST_CAUSES == ("vocabulary", "scope")
    assert "expiry" not in t.AS_AUTHORIZE_POSTTRUST_CAUSES
    for causes in (
        t.AS_LOGIN_CAUSES,
        t.AS_DEVICE_REDEMPTION_CAUSES,
        t.AS_AUTHORIZE_PRETRUST_CAUSES,
        t.AS_AUTHORIZE_POSTTRUST_CAUSES,
    ):
        assert len(set(causes)) == len(causes)
    # §12.1 rule 7: no cause is a credential, a `user_code`, a token value or a `code_verifier`.
    all_causes = {
        *t.AS_LOGIN_CAUSES,
        *t.AS_DEVICE_REDEMPTION_CAUSES,
        *t.AS_AUTHORIZE_PRETRUST_CAUSES,
        *t.AS_AUTHORIZE_POSTTRUST_CAUSES,
    }
    assert not any(c in {"token", "user_code", "code_verifier"} for c in all_causes)


def test_the_part_b_numbers_are_the_freeze_records():
    """§10.1, §11.5, §11.7 and §11.8's numbers, each transcribed from the #31 record's item."""
    day = 24 * 3600
    assert (t.AS_SESSION_IDLE_SECONDS, t.AS_SESSION_ABSOLUTE_SECONDS) == (1800, 28800)  # item 13
    assert t.AS_GRANT_LIFETIME_DEFAULT_SECONDS == 30 * day  # item 18
    assert t.AS_GRANT_LIFETIME_MAX_SECONDS == 90 * day  # item 18
    assert t.AS_CONTINUE_MAX_BYTES == 2048  # item 25


def test_the_user_code_is_eight_of_rfc_8628s_twenty_consonants():
    """§11.8 ([0.3 · 20]): RFC 8628 §6.1's alphabet, written out, and D-C4's eight characters."""
    assert t.AS_USER_CODE_ALPHABET == "BCDFGHJKLMNPQRSTVWXZ"
    assert len(set(t.AS_USER_CODE_ALPHABET)) == len(t.AS_USER_CODE_ALPHABET) == 20
    assert not set(t.AS_USER_CODE_ALPHABET) & set("AEIOUY0123456789")
    assert t.AS_USER_CODE_LENGTH == 8
