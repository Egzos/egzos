# Copyright 2026 Ali Sasanian
# SPDX-License-Identifier: Apache-2.0
"""
events.md §2: `principal: none` is for an entry with no caller to name, and only the five
`PRINCIPAL_NONE_EVENTS` may carry it — a read, a pull or an act is never unattributed (#150).
"""

from __future__ import annotations

from pathlib import Path

import pytest

from egzos._types import EVENTS, PRINCIPAL_NONE_EVENTS
from egzos.container import Container


@pytest.fixture()
def box(tmp_path: Path) -> Container:
    c = Container(tmp_path / "home")
    c.init()
    return c


@pytest.mark.parametrize("event", ["context.fetch", "blob.pull", "approval.execute"])
def test_an_unattributed_read_pull_or_act_is_refused_and_lands_nothing(box: Container, event: str):
    head = box.ledger.tail(1)
    with pytest.raises(ValueError, match="cannot be unattributed"):
        box.ledger.append(event, actor="authorize", principal="none", subject="x")
    assert box.ledger.tail(1) == head


def test_every_event_outside_the_five_refuses_none(box: Container):
    refused = []
    for event in EVENTS:
        if event in PRINCIPAL_NONE_EVENTS:
            continue
        with pytest.raises(ValueError):
            box.ledger.append(event, actor="authorize", principal="none")
        refused.append(event)
    assert refused and len(refused) == len(EVENTS) - len(PRINCIPAL_NONE_EVENTS)


@pytest.mark.parametrize("event", PRINCIPAL_NONE_EVENTS)
def test_the_five_caller_less_events_accept_none(box: Container, event: str):
    entry = box.ledger.append(event, actor="authorize", principal="none")
    assert (entry["event"], entry["principal"]) == (event, "none")
    assert box.ledger.tail(1)[-1]["hash"] == entry["hash"]


def test_the_refusal_has_the_unknown_event_shape(box: Container):
    with pytest.raises(ValueError) as unknown:
        box.ledger.append("no.such.event", actor="authorize", principal="interactive")
    with pytest.raises(ValueError) as unattributed:
        box.ledger.append("context.fetch", actor="authorize", principal="none")
    assert type(unknown.value) is type(unattributed.value)


def test_model_reexports_the_token_principals():
    from egzos import model

    assert "TOKEN_PRINCIPALS" in model.__all__
    assert set(model.TOKEN_PRINCIPALS) == {"interactive", "client"}
    assert "none" not in model.TOKEN_PRINCIPALS


@pytest.mark.parametrize("principal", ["interactive", "client"])
@pytest.mark.parametrize("event", PRINCIPAL_NONE_EVENTS)
def test_the_five_carry_none_and_nothing_else(box: Container, event: str, principal: str):
    # events.md §2's converse, [0.3 · 34] (#159): a principal that varied within one of these
    # events would tell a reader which cause a uniform page had.
    head = box.ledger.tail(1)
    with pytest.raises(ValueError, match="carries no caller"):
        box.ledger.append(event, actor="authorize", principal=principal)
    assert box.ledger.tail(1) == head
