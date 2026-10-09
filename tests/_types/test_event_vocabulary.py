# Copyright 2026 Ali Sasanian
# SPDX-License-Identifier: LicenseRef-PolyForm-Strict-1.0.0
"""
The audit vocabulary #109 PRs 2 and 2b land, pinned: `events.md` §1's nine `authz.*` names,
`client.register` and `config.set`, their closed `details` words, and `capabilities.md` §3's third
principal, `none`.

Literals transcribed here on purpose, the way the rest of `tests/_types/**` does: asking `Event`
what it contains cannot catch a member renamed in `Event`. The documents are held to the same
tuples by `tests/conformance/` (#103).
"""

from __future__ import annotations

import typing

import egzos._types as t

# authorization-server.md §12 rows (a), (b), (d), (e), (f), (g), (h), §11.9's (#144), then §9.3's.
AUTHZ_EVENTS = (
    "authz.login",
    "authz.redeem",
    "authz.refuse",
    "authz.release",
    "authz.reject",
    "authz.render",
    "authz.tally",
    "authz.revoke_refuse",
    "authz.grant",
)

# §5's registry change and container.md §8's config change: owner acts, not `authz.*` (#109 PR 2b).
OWNER_STATE_EVENTS = ("client.register", "config.set")

# rest.md §2's per-window tally: the Chief on #165 items 2 and 3.
REST_EVENTS = ("rest.tally",)

# The nineteen names events.md §1 carried before this PR, unchanged and in place.
PRIOR_EVENTS = (
    "container.init",
    "node.create",
    "item.add",
    "blob.put",
    "context.fetch",
    "blob.pull",
    "item.move",
    "gate.pass.silent",
    "gate.propose",
    "approval.promote",
    "approval.execute",
    "approval.deny",
    "approval.stale",
    "trust.quarantine",
    "step_up",
    "token.mint",
    "token.revoke",
    "item.tombstone",
    "blob.grant",
)


def test_event_is_the_prior_nineteen_then_authz_then_owner_state_then_the_rest_tally():
    assert t.EVENTS == PRIOR_EVENTS + AUTHZ_EVENTS + OWNER_STATE_EVENTS + REST_EVENTS
    assert len(t.EVENTS) == len(set(t.EVENTS)) == 31


def test_authz_family_is_exactly_the_nine():
    # A tenth `authz.*` member must be a deliberate edit here.
    assert tuple(e for e in t.EVENTS if e.startswith("authz.")) == AUTHZ_EVENTS


def test_grant_decision_and_register_op_are_closed():
    # [0.3 · 29]: one `authz.grant` with two outcomes, never an `authz.deny` beside it.
    assert t.AS_GRANT_DECISIONS == ("granted", "denied")
    assert typing.get_args(t.GrantDecision) == t.AS_GRANT_DECISIONS
    assert "authz.deny" not in t.EVENTS
    # [0.3 · 31]
    assert t.AS_CLIENT_REGISTER_OPS == ("add", "amend", "remove")
    assert typing.get_args(t.ClientRegisterOp) == t.AS_CLIENT_REGISTER_OPS


def test_rotation_has_no_event_of_its_own():
    # [0.3 · 30]: rotation writes `token.mint`; events.md §4 invariant 2 names the exception.
    assert not any("rotat" in e for e in t.EVENTS)


def test_the_three_refusal_names_are_in_the_vocabulary():
    # #144: an `audit` query must not confuse pre-trust, post-trust and the owner-path revoke.
    assert {"authz.refuse", "authz.reject", "authz.revoke_refuse"} <= set(t.EVENTS)


def test_principal_none_is_confined_to_the_six_callerless_events():
    # events.md §2: an append with `principal: none` under any other event MUST be rejected.
    assert t.PRINCIPAL_NONE_EVENTS == (
        "authz.login",
        "authz.redeem",
        "authz.refuse",
        "authz.release",
        "authz.tally",
        "rest.tally",
    )
    assert set(t.PRINCIPAL_NONE_EVENTS) <= set(t.EVENTS)
    # Every read, pull and act names its caller: none of these may ever join the tuple.
    for attributed in ("context.fetch", "blob.pull", "approval.execute", "token.mint", "step_up"):
        assert attributed not in t.PRINCIPAL_NONE_EVENTS
    # An owner's decision, registration or config change is an act, never caller-less.
    for owner_act in ("authz.grant", "client.register", "config.set"):
        assert owner_act not in t.PRINCIPAL_NONE_EVENTS


def test_revoke_refusal_causes_are_closed():
    assert t.AS_REVOKE_REFUSAL_CAUSES == ("unknown", "unreachable", "throttled")
    assert typing.get_args(t.RevokeRefusalCause) == t.AS_REVOKE_REFUSAL_CAUSES


def test_principal_gains_none_and_tokens_cannot_carry_it():
    assert t.PRINCIPALS == ("interactive", "client", "none")
    assert t.TOKEN_PRINCIPALS == ("interactive", "client")
    hints = typing.get_type_hints(t.AuditEntry)
    assert hints["principal"] == t.Principal
    for shape in (t.Token, t.AudienceMember):
        assert typing.get_type_hints(shape)["principal"] == t.TokenPrincipal
    assert typing.get_type_hints(t.Provenance)["principal"] == t.TokenPrincipal | None
