# Copyright 2026 Ali Sasanian
# SPDX-License-Identifier: LicenseRef-PolyForm-Strict-1.0.0
"""
The `reaches` that `/authorize`'s post-trust tier asks (authorization-server.md §7.1, §11.2).

`posttrust.judge` takes `reaches(node_id) -> bool`. `reacher` builds it from the viewer's `Token`,
a read of one node by id, and Trust's coverage check (`TrustEngine.covers`, computed down the path
at check time, `capabilities.md` §5). The answer is `True` only when the token is live and covers
that node, or, for `*`, when the token is live and is itself the whole container's.

Every other answer is `False`, with one shape: an id that does not exist, an id the token does not
cover, an empty or non-string id, and a token that is not live. Nothing here raises a not-found.
The node is read by id through a getter that answers `None` for an unknown id. It is never
resolved through `NodeService.resolve_ref` (a name or path is not a node id, and ids stay
opaque), and never through `store/items`, whose not-found is a `StoreError("scope not found")`
that is not a `LookupError` and would surface past `posttrust._reached` as an error. So an
unknown node and an unreachable one reach `judge` as the same `False`, and row (f) records both
as `cause: scope` (§7.1).

Anything else the read or the coverage check raises (an outage, a bug) is not caught here. It
surfaces through `judge` with nothing appended, and the `/authorize` boundary answers it with the
uniform failure.

An unknown id returns before the coverage walk, and a known one walks its ancestors, so the two
differ in time. §7.1's one time budget is owed at the response, not here (`budget`).
"""

from __future__ import annotations

from collections.abc import Callable

from egzos._types import AS_SCOPE_ALL_NODES, AS_SCOPE_NODE_PREFIX
from egzos.model import Node, Token

#: `Token.scopes`' spelling of the whole container (`capabilities.md` §5): `node:*` stripped of
#: its prefix at mint (§7 consequence 3).
_ALL = AS_SCOPE_ALL_NODES.removeprefix(AS_SCOPE_NODE_PREFIX)


def reacher(
    token: Token,
    get_node: Callable[[str], Node | None],
    covers: Callable[[Token, Node], bool],
) -> Callable[[str], bool]:
    """The viewer's `reaches` for `posttrust.judge`.

    `get_node(node_id)` reads one node by its id and answers `None` for an id that does not exist
    (`Backend.get_node`). `covers(token, node)` is Trust's coverage check. Only a `True` from it
    reaches: any other value is `False`."""

    def reaches(node_id: str) -> bool:
        if not isinstance(node_id, str) or not node_id or not token.live:
            return False
        if node_id == _ALL:
            return _ALL in token.scopes
        node = get_node(node_id)
        if node is None:
            return False
        return covers(token, node) is True

    return reaches
