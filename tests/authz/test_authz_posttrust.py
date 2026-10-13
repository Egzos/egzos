# Copyright 2026 Ali Sasanian
# SPDX-License-Identifier: LicenseRef-PolyForm-Strict-1.0.0
"""§7 the post-trust tier at `/authorize` and its rows (f) and (g) (authz/posttrust.py)."""

from __future__ import annotations

from typing import Any

import pytest

from egzos._types import (
    AS_AUTHORIZE_POSTTRUST_CAUSES,
    AS_GRANT_LIFETIME_DEFAULT_SECONDS,
    GENESIS_HASH,
)
from egzos.authz import grant, posttrust, pretrust, screen
from egzos.ledger import Ledger

CLIENT = "01JCLIENT00000000000000000"
OWNER = "owner"
NODE_A = "01JNODEA000000000000000000"
NODE_B = "01JNODEB000000000000000000"


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


class Reach:
    """The endpoint's coverage answer: `*` and NODE_A reach, NODE_B exists and does not, any
    other id does not exist. Records every id it was asked about."""

    def __init__(self, reachable: set[str] | None = None, *, raise_on_unknown: bool = False):
        self.reachable = {"*", NODE_A} if reachable is None else reachable
        self.raise_on_unknown = raise_on_unknown
        self.asked: list[str] = []

    def __call__(self, node: str) -> bool:
        self.asked.append(node)
        if node in self.reachable:
            return True
        if self.raise_on_unknown and node != NODE_B:
            raise KeyError(node)
        return False


@pytest.fixture
def chain() -> Chain:
    return Chain()


def _admitted(scope: str | None, client_type: str = "browser") -> pretrust.Admitted:
    entry = screen.ClientEntry(
        client_id=CLIENT,
        client_name="egzos.io",
        client_type=client_type,  # type: ignore[arg-type]
        redirect_uris=("https://egzos.io/connect/callback",),
        registered_at="2026-10-13T09:00:00Z",
    )
    return pretrust.Admitted(
        client=entry,
        redirect_uri="https://egzos.io/connect/callback",
        code_challenge="E9Melhoa2OwvFrEMTJguCHaoeK1t8URWbuGJSstw-cM",
        state="xyz",
        scope=scope,
        key="k" * 64,
    )


def _judge(chain: Chain, scope: str | None, reach: Reach | None = None, **kw: Any) -> Any:
    ledger = Ledger(chain)  # type: ignore[arg-type]
    return posttrust.judge(_admitted(scope, **kw), ledger, actor=OWNER, reaches=reach or Reach())


# --- render: row (g) ------------------------------------------------------------------------


def test_render_returns_the_offer_and_appends_row_g(chain: Chain) -> None:
    out = _judge(chain, f"fetch remember node:{NODE_A}")
    assert out == grant.Offer(
        ("fetch", "remember"), (NODE_A,), "interactive", AS_GRANT_LIFETIME_DEFAULT_SECONDS
    )
    [entry] = chain.entries
    assert entry["event"] == "authz.render"
    assert entry["principal"] == "interactive"
    assert entry["actor"] == OWNER
    assert entry["details"] == {"outcome": "rendered", "client_id": CLIENT}


def test_whole_container_is_asked_as_star(chain: Chain) -> None:
    reach = Reach()
    out = _judge(chain, "admin node:*", reach)
    assert isinstance(out, grant.Offer)
    assert out.scopes == ("*",)
    assert reach.asked == ["*"]


def test_capabilities_only_render(chain: Chain) -> None:
    reach = Reach()
    out = _judge(chain, "fetch", reach)
    assert isinstance(out, grant.Offer) and out.scopes == ()
    assert reach.asked == []


def test_non_browser_client_is_offered_client_principal(chain: Chain) -> None:
    out = _judge(chain, f"fetch node:{NODE_A}", client_type="cli")
    assert isinstance(out, grant.Offer)
    assert out.principal == "client"


# --- row (f) vocabulary: invalid_scope ------------------------------------------------------


@pytest.mark.parametrize(
    "scope",
    [None, "read", "reader node:*", "fetch  remember", "node:", "node:node:x", "principal"],
)
def test_vocabulary_is_invalid_scope(chain: Chain, scope: str | None) -> None:
    reach = Reach()
    out = _judge(chain, scope, reach)
    assert out == posttrust.Rejected("invalid_scope")
    [entry] = chain.entries
    assert entry["event"] == "authz.reject"
    assert entry["principal"] == "interactive"
    assert entry["details"] == {"outcome": "rejected", "cause": "vocabulary"}
    # Refused whole, before any node is looked at: never narrowed (§7, §11.2).
    assert reach.asked == []


# --- row (f) scope: access_denied, one answer for unknown and unreachable (§7.1) -----------


def _rejection(chain: Chain, scope: str, reach: Reach) -> tuple[Any, dict[str, Any]]:
    out = _judge(chain, scope, reach)
    [entry] = chain.entries
    return out, {k: entry[k] for k in ("event", "actor", "principal", "subject", "details")}


def test_unknown_and_unreachable_nodes_converge() -> None:
    unknown = _rejection(Chain(), "fetch node:01JNOSUCHNODE0000000000000", Reach())
    unreachable = _rejection(Chain(), f"fetch node:{NODE_B}", Reach())
    raising = _rejection(
        Chain(), "fetch node:01JNOSUCHNODE0000000000000", Reach(raise_on_unknown=True)
    )
    assert unknown == unreachable == raising
    out, entry = unknown
    assert out == posttrust.Rejected("access_denied")
    assert entry["details"] == {"outcome": "rejected", "cause": "scope"}
    assert entry["principal"] == "interactive"


def test_whole_container_the_viewer_does_not_cover_is_access_denied(chain: Chain) -> None:
    out = _judge(chain, "fetch node:*", Reach({NODE_A}))
    assert out == posttrust.Rejected("access_denied")


def test_one_unreached_node_rejects_the_whole_request(chain: Chain) -> None:
    out = _judge(chain, f"fetch node:{NODE_A} node:{NODE_B}")
    assert out == posttrust.Rejected("access_denied")
    assert [e["event"] for e in chain.entries] == ["authz.reject"]


def test_every_node_is_asked_even_after_a_failure(chain: Chain) -> None:
    reach = Reach()
    _judge(chain, f"fetch node:{NODE_B} node:{NODE_A}", reach)
    assert reach.asked == [NODE_B, NODE_A]


@pytest.mark.parametrize("answer", [1, "yes", None, [True]])
def test_only_true_reaches(chain: Chain, answer: Any) -> None:
    out = posttrust.judge(
        _admitted(f"fetch node:{NODE_A}"),
        Ledger(chain),  # type: ignore[arg-type]
        actor=OWNER,
        reaches=lambda _node: answer,
    )
    assert out == posttrust.Rejected("access_denied")


# --- shape -----------------------------------------------------------------------------------


def test_error_words_cover_the_closed_causes() -> None:
    assert set(posttrust.ERROR) == set(AS_AUTHORIZE_POSTTRUST_CAUSES)
    assert set(posttrust.ERROR.values()) == {"invalid_scope", "access_denied"}


def test_nothing_from_the_request_enters_the_chain(chain: Chain) -> None:
    for scope in ("reader", f"fetch node:{NODE_B}", f"fetch node:{NODE_A}"):
        _judge(chain, scope)
    flat = repr(chain.entries)
    for leaked in (NODE_A, NODE_B, "reader", "xyz", "E9Melhoa2Owv"):
        assert leaked not in flat


@pytest.mark.parametrize("actor", ["", None, 7])
def test_actor_is_required_and_nothing_is_appended(chain: Chain, actor: Any) -> None:
    with pytest.raises(ValueError):
        posttrust.judge(
            _admitted("fetch"),
            Ledger(chain),  # type: ignore[arg-type]
            actor=actor,
            reaches=Reach(),
        )
    assert chain.entries == []
