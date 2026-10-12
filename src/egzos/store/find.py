# Copyright 2026 Ali Sasanian
# SPDX-License-Identifier: LicenseRef-PolyForm-Strict-1.0.0
"""
The find grammar, one implementation for the CLI's `find` and the lifeboat's search (lifeboat.md
§2.2, D-L2: "the UI renders whatever the CLI accepts").

A query is free text plus `prefix:value` words. Prefixes: `kind:` · `scope:` · `trust:` · `tag:` ·
`key:` · `ring:`. Free text matches titles and bodies. A prefix the grammar does not know, an empty
value, or a kind / trust word outside its closed vocabulary is the viewer's own mistake and raises
QueryError — it never names a scope, id or count. A `scope:` the viewer cannot see behaves exactly
like one that does not exist: no results (silence-not-errors).

The grammar itself is the contract's to freeze (`lifeboat.md` §14.1, [OPEN→a1p]); this is the
running answer until it does.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from egzos.model import KINDS, TRUST_STATUSES, ContextItem, Node, Token
from egzos.store.nodes import AmbiguousRef

PREFIXES = ("kind", "scope", "trust", "tag", "key", "ring")
_WORD = re.compile(r"^([a-z]+):(.*)$")


class QueryError(ValueError):
    """The query's grammar is wrong. The message is the viewer's to read and names nothing."""


@dataclass
class Query:
    text: list[str] = field(default_factory=list)
    kinds: list[str] = field(default_factory=list)
    scope: str | None = None
    trust: str | None = None
    tags: list[str] = field(default_factory=list)
    key: str | None = None
    ring: str | None = None

    @property
    def empty(self) -> bool:
        return not any(
            (self.text, self.kinds, self.scope, self.trust, self.tags, self.key, self.ring)
        )


def parse(q: str) -> Query:
    out = Query()
    for word in (q or "").split():
        m = _WORD.match(word)
        if not m:
            out.text.append(word)
            continue
        name, value = m.group(1), m.group(2)
        if name not in PREFIXES or not value:
            raise QueryError("invalid query")
        if name == "kind":
            if value not in KINDS:
                raise QueryError("invalid query")
            out.kinds.append(value)
        elif name == "trust":
            if value not in TRUST_STATUSES:
                raise QueryError("invalid query")
            out.trust = value
        elif name == "tag":
            out.tags.append(value.lstrip("#"))
        elif name == "scope":
            out.scope = value
        elif name == "key":
            out.key = value
        elif name == "ring":
            out.ring = value
    return out


def shown(container, token: Token, item: ContextItem, node: Node) -> bool:
    """Whether a covered, live item is shown to `token`: search's predicate, and the lifeboat item
    page's. The trust labels are the curator's view, the interactive principal holding `curate`;
    any other token (a browser UI's interactive grant without it included) is served by policy."""
    curator = token.principal == "interactive" and token.has("curate")
    return curator or bool(container.resolver.serve(item, node))


def find(container, token: Token, q: str | Query) -> list[tuple[Node, ContextItem]]:
    """Every item the token covers that matches, newest first. Quarantined items are never served
    in any query. A client principal is served under the serving policy; the interactive owner sees
    every covered item with its trust label (the labels and the promotion queue are the control)."""
    query = parse(q) if isinstance(q, str) else q
    c = container
    nodes = [n for n in c.backend.list_nodes() if c.trust.covers(token, n)]
    if query.scope is not None:
        try:
            roots = [c.nodes.resolve_ref(query.scope, token)]
        except AmbiguousRef as e:
            # A search picks no one match: it covers every scope the tail names that this token
            # can see, so no write anywhere can steer which one is searched.
            roots = [c.nodes.resolve_ref(path, token) for path in e.paths]
        root_ids = {r.id for r in roots if r is not None}
        if not root_ids:
            return []  # absent and uncovered answer alike
        nodes = [n for n in nodes if root_ids & {a.id for a in c.nodes.ancestors(n)}]
    if query.ring is not None:
        nodes = [n for n in nodes if n.type == query.ring]
    text = " ".join(query.text) or None
    hits: list[tuple[Node, ContextItem]] = []
    for n in nodes:
        for item in c.backend.query([n.id], kinds=query.kinds or None, key=query.key, text=text):
            if item.status == "quarantined":
                continue
            if query.trust and item.status != query.trust:
                continue
            if query.tags and not set(query.tags) <= set(item.tags or []):
                continue
            if shown(c, token, item, n):
                hits.append((n, item))
    hits.sort(key=lambda t: (t[1].lifecycle.get("updated_at", ""), t[1].id), reverse=True)
    return hits
