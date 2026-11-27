# Copyright 2026 Ali Sasanian
# SPDX-License-Identifier: LicenseRef-PolyForm-Strict-1.0.0
"""The places a caller may list (rest.md §4.1 item 5): `GET /v1/scopes` and `egzos_places` read
them here, so the two answer alike and append the same read. The caller has already been checked
for `fetch` and the node for coverage; this lists covered places and nothing else."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from egzos.model import Node, Token

if TYPE_CHECKING:
    from egzos.container import Container


def place(c: Container, node: Node) -> dict[str, Any]:
    """§4.1's `<node>`: the persisted node plus its computed path."""
    return {**node.to_dict(), "path": c.nodes.path(node)}


def _read(c: Container, token: Token, at: Node | None, out: list[dict[str, Any]]) -> None:
    c.ledger.append("context.fetch", actor=token.owner, principal=token.principal,
                    subject=at.id if at else None, scope=at.id if at else None,
                    client=token.client, items=[], layers=[], nodes=[n["id"] for n in out],
                    withheld=0)


def children(c: Container, token: Token, node: Node) -> list[dict[str, Any]]:
    """The places directly inside `node` that `token` covers, sorted by path, as one read."""
    inside = [n for n in c.backend.list_nodes(parent=node.id) if c.trust.covers(token, n)]
    out = sorted((place(c, n) for n in inside), key=lambda n: n["path"])
    _read(c, token, node, out)
    return out


def _given(c: Container, token: Token, node: Node) -> dict[str, Any]:
    """A place the token was given, its `parent` null where the token does not cover it: a node
    above what was given is served by no read."""
    shown = place(c, node)
    above = c.backend.get_node(node.parent) if node.parent else None
    if above is None or not c.trust.covers(token, above):
        shown["parent"] = None
    return shown


def granted(c: Container, token: Token) -> list[dict[str, Any]]:
    """Every place a narrower token's grant or registration names, each that exists and it
    covers, sorted by path, as one read (rest.md §4.1 item 5, `egzos_places`)."""
    named = {s: c.backend.get_node(s) for s in token.scopes if s != "*"}
    out = sorted((_given(c, token, n) for n in named.values() if n and c.trust.covers(token, n)),
                 key=lambda n: n["path"])
    _read(c, token, None, out)
    return out
