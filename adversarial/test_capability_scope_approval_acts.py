# Copyright 2026 Ali Sasanian
# SPDX-License-Identifier: LicenseRef-PolyForm-Strict-1.0.0
"""Standing target #4 (proposal-target probing), issue #131.

`TrustEngine.promote` / `.execute` / `.deny` and `authz.presence.build_act` gate on the deciding
token's *principal* alone (`token.principal == "interactive"`), never on whether its capability
scope covers the item's or proposal's node — unlike `.move` and `.quarantine`, which both call
`self.covers(token, node)` before acting.

Not reachable through any shipped CLI or MCP surface today: `container.init()` is the only caller
that mints `principal="interactive"`, and it always mints `scopes=["*"]` for the single owner.
This is filed as a contract gap, not a security advisory, for exactly that reason (see #131's
reachability note) — it becomes reachable the moment a second interactive principal exists
(Phase 2 login/device-code, or a future contractor/external principal class). Each test mints that
second token directly via `Auth.mint` with `by_principal="interactive"`: the owner's own act, no
privilege escalation required to build the repro.
"""

from __future__ import annotations

import pytest

from egzos.authz import presence
from egzos.container import OWNER, Container
from egzos.trust import TrustError

pytestmark = pytest.mark.adversarial


@pytest.fixture()
def box(tmp_path):
    c = Container(tmp_path / "home")
    c.init()
    return c


def _second_interactive(c: Container, scope_node_id: str, *, client: str):
    """A second `principal="interactive"` token, narrowly scoped — minted by the owner's own act,
    exactly as #131 describes it: `by_principal="interactive"`, no escalation needed."""
    return c.auth.mint(
        principal="interactive", owner=OWNER, client=client, role="admin",
        scopes=[scope_node_id], actor=OWNER, by_principal="interactive",
    )


def _parked_proposal(c: Container):
    """A pending move proposal, plus a second interactive token scoped to neither end of it.

    The org/src/dst/bystander-client shape mirrors test_mvp_boundaries.py's
    test_the_engine_records_a_quarantine_refusal: a client scoped to `dst` only widens the
    audience, so the move parks (gate.propose) instead of landing silent.
    """
    owner = c.auth.interactive_token()
    root = c.nodes.user_root()
    org = c.nodes.create("org", "o", root, token=owner, actor=OWNER, principal="interactive")
    src = c.nodes.create("project", "a", org, token=owner, actor=OWNER, principal="interactive")
    dst = c.nodes.create("project", "b", org, token=owner, actor=OWNER, principal="interactive")
    c.auth.mint(principal="client", owner=OWNER, client="bystander", role="curator",
                scopes=[dst.id], actor=OWNER, by_principal="interactive")
    item = c.store.add(body="n", scope=src, token=owner, actor=OWNER, principal="interactive")
    result = c.trust.move(item, dst, token=owner, actor=OWNER)
    assert result["gate"] == "pending"  # the fixture actually parks; a silent pass proves nothing
    atk = c.nodes.create("project", "atk", root, token=owner, actor=OWNER, principal="interactive")
    attacker = _second_interactive(c, atk.id, client="attacker-device")
    return result["proposal"]["id"], attacker


def test_promote_refuses_a_token_that_does_not_cover_the_item(box):
    owner = box.auth.interactive_token()
    root = box.nodes.user_root()
    mine = box.nodes.create("project", "mine", root, token=owner, actor=OWNER,
                            principal="interactive")
    theirs = box.nodes.create("project", "theirs", root, token=owner, actor=OWNER,
                              principal="interactive")
    item = box.store.add(body="not yours", scope=theirs, token=owner, actor=OWNER,
                         principal="interactive")
    second = _second_interactive(box, mine.id, client="second-device")

    with pytest.raises(TrustError):
        box.trust.promote(item, token=second, actor="second-device")


def test_execute_refuses_a_token_that_covers_neither_end_of_the_proposal(box):
    pid, attacker = _parked_proposal(box)
    with pytest.raises(TrustError):
        box.trust.execute(pid, token=attacker, actor="attacker-device")


def test_deny_refuses_a_token_that_covers_neither_end_of_the_proposal(box):
    pid, attacker = _parked_proposal(box)
    with pytest.raises(TrustError):
        box.trust.deny(pid, token=attacker, actor="attacker-device")


def test_build_act_refuses_a_ref_the_deciding_token_does_not_cover(box):
    pid, attacker = _parked_proposal(box)
    assert presence.build_act(box, pid, token=attacker) is None
