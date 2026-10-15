# Copyright 2026 Ali Sasanian
# SPDX-License-Identifier: LicenseRef-PolyForm-Strict-1.0.0
"""§7.1's `reaches` for `/authorize`'s post-trust tier (authz/reach.py)."""

from __future__ import annotations

from typing import Any

import pytest

from egzos._types import GENESIS_HASH
from egzos.authz import grant, posttrust, pretrust, reach, screen
from egzos.ledger import Ledger
from egzos.model import Node, Token
from egzos.store.nodes import NodeService
from egzos.trust import TrustEngine

ROOT = "01JROOT0000000000000000000"
PROJECT = "01JPROJECT0000000000000000"
THREAD = "01JTHREAD00000000000000000"
OTHER = "01JOTHER000000000000000000"
UNKNOWN = "01JUNKNOWN0000000000000000"
CLIENT = "01JCLIENT00000000000000000"


class Nodes:
    """Just enough backend for `NodeService.ancestors` and `TrustEngine.covers`: a node read by
    id that answers `None` for an unknown one, recording every id it was asked about."""

    def __init__(self) -> None:
        self.nodes = {
            ROOT: Node(id=ROOT, type="root", name="", parent=None),
            PROJECT: Node(id=PROJECT, type="project", name="p", parent=ROOT),
            THREAD: Node(id=THREAD, type="thread", name="t", parent=PROJECT),
            OTHER: Node(id=OTHER, type="project", name="o", parent=ROOT),
        }
        self.asked: list[str] = []

    def get_node(self, node_id: str) -> Node | None:
        self.asked.append(node_id)
        return self.nodes.get(node_id)


def _token(scopes: list[str], **kw: Any) -> Token:
    return Token(
        id="01JTOKEN000000000000000000",
        principal="interactive",
        owner="owner",
        client="cli",
        capabilities=["fetch"],
        scopes=scopes,
        **kw,
    )


@pytest.fixture
def nodes() -> Nodes:
    return Nodes()


def _reaches(token: Token, nodes: Nodes) -> Any:
    trust = TrustEngine(nodes, None, NodeService(nodes, None))  # type: ignore[arg-type]
    return reach.reacher(token, nodes.get_node, trust.covers)


def test_covered_node_and_its_descendants_reach(nodes: Nodes) -> None:
    reaches = _reaches(_token([PROJECT]), nodes)
    assert reaches(PROJECT) is True
    assert reaches(THREAD) is True


def test_unknown_and_unreachable_are_one_false(nodes: Nodes) -> None:
    reaches = _reaches(_token([PROJECT]), nodes)
    assert reaches(OTHER) is False  # exists, not covered
    assert reaches(ROOT) is False  # an ancestor is not covered by its descendant
    assert reaches(UNKNOWN) is False  # does not exist: same answer, nothing raised


def test_owner_token_reaches_every_node_that_exists_and_the_whole_container(nodes: Nodes) -> None:
    reaches = _reaches(_token(["*"]), nodes)
    assert all(reaches(n) is True for n in (ROOT, PROJECT, THREAD, OTHER))
    assert reaches("*") is True
    assert reaches(UNKNOWN) is False


def test_star_needs_the_whole_container_token(nodes: Nodes) -> None:
    assert _reaches(_token([ROOT]), nodes)("*") is False
    assert "*" not in nodes.asked  # `*` is never read as a node id


@pytest.mark.parametrize(
    "token",
    [
        _token(["*"], revoked=True),
        _token(["*"], expires_at="2000-01-01T00:00:00+00:00"),
        _token(["*"], expires_at="not a time"),
    ],
)
def test_a_token_that_is_not_live_reaches_nothing(nodes: Nodes, token: Token) -> None:
    reaches = _reaches(token, nodes)
    assert reaches("*") is False
    assert reaches(PROJECT) is False
    assert nodes.asked == []


@pytest.mark.parametrize("node_id", ["", None, 7, b"01JPROJECT0000000000000000", ["x"]])
def test_an_id_that_is_not_a_nonempty_string_is_false_and_unread(
    nodes: Nodes, node_id: Any
) -> None:
    assert _reaches(_token(["*"]), nodes)(node_id) is False
    assert nodes.asked == []


@pytest.mark.parametrize("prefixed", ["node:" + PROJECT, "node:*"])
def test_a_prefixed_id_is_not_a_node(nodes: Nodes, prefixed: str) -> None:
    # The prefix is stripped at `grant.offer`; what reaches here is a bare id or nothing.
    assert _reaches(_token(["*"]), nodes)(prefixed) is False


@pytest.mark.parametrize("answer", [1, "yes", None, object()])
def test_only_a_true_from_covers_reaches(nodes: Nodes, answer: Any) -> None:
    reaches = reach.reacher(_token(["*"]), nodes.get_node, lambda t, n: answer)
    assert reaches(PROJECT) is False


def test_an_outage_in_the_read_surfaces(nodes: Nodes) -> None:
    def down(node_id: str) -> Node | None:
        raise OSError("backend down")

    reaches = reach.reacher(_token([PROJECT]), down, lambda t, n: True)
    with pytest.raises(OSError):
        reaches(PROJECT)


# --- through `posttrust.judge` ---------------------------------------------------------------


class Chain:
    """Just enough backend for the real `Ledger`, so its event and principal guards run."""

    def __init__(self) -> None:
        self.entries: list[dict[str, Any]] = []

    def audit_last(self) -> dict[str, Any] | None:
        return self.entries[-1] if self.entries else None

    def audit_append(self, entry: dict[str, Any]) -> dict[str, Any]:
        assert entry["prev_hash"] == (self.entries[-1]["hash"] if self.entries else GENESIS_HASH)
        self.entries.append(entry)
        return entry


def _admitted(scope: str) -> pretrust.Admitted:
    entry = screen.ClientEntry(
        client_id=CLIENT,
        client_name="egzos.io",
        client_type="browser",
        redirect_uris=("https://egzos.io/connect/callback",),
        registered_at="2026-10-13T09:00:00Z",
    )
    return pretrust.Admitted(
        client=entry,
        redirect_uri="https://egzos.io/connect/callback",
        code_challenge="E9Melhoa2OwvFrEMTJguCHaoeK1t8URWbuGJSstw-cM",
        state=None,
        scope=scope,
        key="k" * 64,
    )


def _judged(nodes: Nodes, scope: str) -> tuple[Any, dict[str, Any]]:
    chain = Chain()
    out = posttrust.judge(
        _admitted(scope),
        Ledger(chain),  # type: ignore[arg-type]
        actor="owner",
        reaches=_reaches(_token([PROJECT]), nodes),
    )
    return out, chain.entries[-1]


def test_judge_answers_unknown_exactly_as_unreachable(nodes: Nodes) -> None:
    unknown, unknown_entry = _judged(nodes, "fetch node:" + UNKNOWN)
    unreachable, unreachable_entry = _judged(nodes, "fetch node:" + OTHER)
    assert unknown == unreachable == posttrust.Rejected("access_denied")
    strip = ("ts", "hash", "prev_hash", "id", "seq")
    assert {k: v for k, v in unknown_entry.items() if k not in strip} == {
        k: v for k, v in unreachable_entry.items() if k not in strip
    }
    assert unknown_entry["event"] == "authz.reject"
    assert unknown_entry["details"]["cause"] == "scope"


def test_judge_renders_a_covered_node(nodes: Nodes) -> None:
    offer, entry = _judged(nodes, "fetch node:" + THREAD)
    assert isinstance(offer, grant.Offer)
    assert offer.scopes == (THREAD,)
    assert entry["event"] == "authz.render"
