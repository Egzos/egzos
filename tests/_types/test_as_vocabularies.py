# Copyright 2026 Ali Sasanian
# SPDX-License-Identifier: LicenseRef-PolyForm-Strict-1.0.0
"""
What the retired authorization server left in `_types.py`, pinned.

The AS is gone (`identity.md` §9) and with it the shapes that only it used. What stays is what a
living contract still names: the throttle surfaces the REST door releases under (`rest.md` §2 item
7) and the closed cause vocabularies `events.md` §1 cites for its `authz.*` rows. Written out, never
read back from the module.
"""

from __future__ import annotations

import egzos._types as t


def test_the_throttle_surfaces_are_six_closed_words():
    """§12.1 rule 5 and §12.2: the release entry's `surface`, and what `actor` carries.

    Written out rather than derived, because the point of the vocabulary is that it is closed: a
    fifth surface reaching the chain should break a test, not append quietly. `tap` is here because
    `consent.md`'s D-C6 throttles the tap page unconditionally, as the fourth surface, independent
    of whether §10.5's `[LEAN]` is taken — `[LEAN]` picks which channel the tap rides, not
    whether the word is used. `revoke` is §11.9's page, [0.3 · 11]; `actor` is [0.3 · 34]. `rest`
    is the REST door's, `rest.md` §2 (#165 item 3).
    """
    assert t.AS_THROTTLE_SURFACES == ("login", "device", "authorize", "tap", "revoke", "rest")
    assert len(set(t.AS_THROTTLE_SURFACES)) == len(t.AS_THROTTLE_SURFACES)
    # §12.2: the caller's network identifier is never the actor, so no surface is one.
    assert not any(s in {"ip", "remote_addr", "caller"} for s in t.AS_THROTTLE_SURFACES)


def test_the_pre_token_cause_vocabularies_are_closed_per_row():
    """§12's table, rows (a), (b), (d) and (f) — four closed `details.cause` vocabularies.

    Written out rather than derived, for the same reason
    `test_the_throttle_surfaces_are_six_closed_words` is: a cause arriving at one of these rows
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
