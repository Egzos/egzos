# Copyright 2026 Ali Sasanian
# SPDX-License-Identifier: LicenseRef-PolyForm-Strict-1.0.0
"""identity.md §5, rest.md §4.2–§4.3 (v0.7 §AJ): a terminal's token concludes no confirm, with
either proof, whatever `confirm.allow_button` says and whatever credentials the person has; its
first leg offers no assertion. A person's own sign-in is unaffected. And the act's own check may
refuse a proof that would confirm, `registered`, on the same record."""

from __future__ import annotations

import pytest

from egzos.confirm import REASONS
from egzos.container import OWNER, Container

KW = {"actor": OWNER, "principal": "interactive"}
BOB = "bob-sub"
ORIGIN = "https://egzos.io"
ACT = {"act": "promote", "subject": "item-1", "destination": None, "delta": []}


@pytest.fixture
def box(tmp_path):
    c = Container(tmp_path / "home")
    c.owner = c.init()
    c.set_config("identity.client_id", "box", token=c.owner)
    c.identity.grant_user(BOB, name="bob", role="admin", scopes=["*"], **KW)
    c.backend.put_agent_registration({
        "client_id": "t1", "sub": BOB, "kind": "terminal", "name": "a laptop",
        "created_at": "2026-11-14T00:00:00Z", "revoked": False})
    return c


def _credential(c):
    """A credential Bob registered on egzos.io: enough for the first leg to list it."""
    c.backend.put_credential({
        "id": "01J00000000000000000000000", "person": f"user:{BOB}", "credential_id": "Y3JlZA",
        "public_key": "a2V5", "sign_count": 0, "rp_id": "egzos.io", "name": "phone",
        "created_at": "2026-11-14T00:00:00Z", "last_used": None, "removed": False})


def _step_ups(c):
    return [e for e in c.ledger.tail(1000) if e["event"] == "step_up"]


def test_the_closed_reasons_name_a_terminal_and_a_registered_client():
    assert REASONS == ("stale", "spent", "foreign", "mismatch", "assertion", "button_off",
                       "delta_changed", "terminal", "not_fresh", "registered")


@pytest.mark.parametrize("proof", [{"proof": "button"},
                                   {"proof": "biometric", "assertion": {"id": "Y3JlZA"}}])
@pytest.mark.parametrize("credential", [False, True])
def test_a_terminals_token_concludes_no_confirm(box, proof, credential):
    if credential:
        _credential(box)
    terminal = box.identity._terminal("t1", BOB)
    first = box.confirm.issue(terminal, **ACT, newly=[], origin=ORIGIN)
    assert first["webauthn"] is None  # no assertion is offered, and no credential listed
    presented = {"challenge": first["challenge"], **proof}
    assert box.confirm.conclude(terminal, presented, **ACT, origin=ORIGIN) == "terminal"
    (step_up,) = _step_ups(box)
    assert (step_up["actor"], step_up["principal"]) == (f"user:{BOB}", "interactive")
    assert step_up["details"] == {"via": "confirm", "act": "promote", "proof": proof["proof"],
                                  "outcome": "refused", "reason": "terminal", "terminal": "t1"}
    # The challenge is spent whatever was decided: presented again, it is still refused.
    assert box.confirm.conclude(terminal, presented, **ACT, origin=ORIGIN) == "terminal"


def test_a_terminal_cannot_spend_the_browsers_challenge_into_a_confirm(box):
    person = box.identity._person(BOB, "box")
    terminal = box.identity._terminal("t1", BOB)
    first = box.confirm.issue(person, **ACT, newly=[])
    presented = {"challenge": first["challenge"], "proof": "button"}
    assert box.confirm.conclude(terminal, presented, **ACT) == "terminal"
    assert box.confirm.conclude(person, presented, **ACT) == "spent"


def test_the_browser_cannot_conclude_a_challenge_issued_to_a_terminal(box):
    """rest.md §6: a challenge issued to a terminal's token is that terminal's alone, so the
    person's own sign-in presenting it concludes refused, `foreign`, and the act does not land."""
    person = box.identity._person(BOB, "box")
    terminal = box.identity._terminal("t1", BOB)
    first = box.confirm.issue(terminal, **ACT, newly=[])
    presented = {"challenge": first["challenge"], "proof": "button"}
    assert box.confirm.conclude(person, presented, **ACT) == "foreign"
    (step_up,) = _step_ups(box)
    assert (step_up["actor"], step_up["principal"]) == (f"user:{BOB}", "interactive")
    assert step_up["details"] == {"via": "confirm", "act": "promote", "proof": "button",
                                  "outcome": "refused", "reason": "foreign"}
    # The challenge is spent whatever was decided.
    assert box.confirm.conclude(person, presented, **ACT) == "spent"


def test_a_persons_own_sign_in_is_unaffected(box):
    person = box.identity._person(BOB, "box")
    first = box.confirm.issue(person, **ACT, newly=[])
    assert first["webauthn"] is None  # no credential yet: only the button is possible
    assert box.confirm.conclude(person, {"challenge": first["challenge"], "proof": "button"},
                                **ACT) is None
    (step_up,) = _step_ups(box)
    assert step_up["details"]["outcome"] == "confirmed" and "terminal" not in step_up["details"]
    _credential(box)
    assert box.confirm.issue(person, **ACT, newly=[], origin=ORIGIN)["webauthn"] is not None


def test_the_acts_own_check_refuses_a_proof_that_would_confirm(box):
    person = box.identity._person(BOB, "box")
    first = box.confirm.issue(person, **ACT, newly=[])
    presented = {"challenge": first["challenge"], "proof": "button"}
    assert box.confirm.conclude(person, presented, **ACT, refusal="registered") == "registered"
    (step_up,) = _step_ups(box)
    assert (step_up["details"]["outcome"], step_up["details"]["reason"]) == ("refused",
                                                                             "registered")
    # A proof that fails on its own is refused for its own reason, and the challenge is spent.
    assert box.confirm.conclude(person, presented, **ACT, refusal="registered") == "spent"
    with pytest.raises(ValueError):
        box.confirm.conclude(person, presented, **ACT, refusal="nope")


def test_a_terminals_token_registers_no_confirm_credential(box):
    terminal = box.identity._terminal("t1", BOB)
    with pytest.raises(PermissionError):
        box.confirm.begin_registration(terminal, origin=ORIGIN, name="phone")
    with pytest.raises(PermissionError):
        box.confirm.finish_registration(terminal, origin=ORIGIN, challenge_id="x",
                                        attestation={}, presented={"proof": "button"},
                                        name="phone", fresh=True, owner_surface=False)
    assert _step_ups(box) == []
