# Copyright 2026 Ali Sasanian
# SPDX-License-Identifier: LicenseRef-PolyForm-Strict-1.0.0
"""
Node model: ULIDs, parent pointers, computed paths, ring ranks, the inbox, the chain.

Hierarchy is wrapping added inside-out (v0.4 §2). Two roots exist from init: the personal tree
`user:self` (rooted at identity) and `global`. The inbox is the incoming bucket under the personal
root, audience zero. Resolution walks the ancestors that exist — bare thread → personal root →
global (v0.4 §2) — with the personal root slotted between org and global by default (R11).
"""

from __future__ import annotations

import unicodedata
from collections.abc import Callable

from egzos._ids import ulid
from egzos.backends.base import Backend
from egzos.ledger import Ledger
from egzos.model import BASELINE_CREATE, CONTAINER_TYPES, RING_RANK, ROOT_TYPES, Node, Token


class StructureError(Exception):
    pass


class InvalidName(StructureError):
    """A place's name outside rest.md §4.5's rule: the door's `400`, refused on every surface."""


#: rest.md §4.5: a place's name is 1 to this many Unicode scalar values.
NAME_MAX = 255
#: The characters with Unicode's Bidi_Control property (PropList.txt): ALM, LRM, RLM, the
#: embeddings and overrides, and the isolates. `unicodedata` does not expose the property.
BIDI_CONTROL = frozenset(
    "\u061c\u200e\u200f\u202a\u202b\u202c\u202d\u202e\u2066\u2067\u2068\u2069"
)
#: The general categories no name holds: controls (U+0000 and U+007F among them) and the line and
#: paragraph separators. Cf beyond Bidi_Control (a zero-width joiner, say) is left as it is.
_BARRED_CATEGORIES = frozenset({"Cc", "Zl", "Zp"})
#: How many characters of a title pure capture keeps for a thread's name (container.md [0.3 · 2]).
CAPTURE_NAME_KEEP = 40


def _barred(ch: str) -> bool:
    return unicodedata.category(ch) in _BARRED_CATEGORIES or ch in BIDI_CONTROL


def _surrogate(ch: str) -> bool:
    return "\ud800" <= ch <= "\udfff"


def valid_name(name: object) -> bool:
    """rest.md §4.5, "A name's shape": 1 to 255 scalar values, kept and compared as given, with no
    `/` or `:`, no Cc, Zl or Zp character, no Bidi_Control, no lone surrogate, and never `*`."""
    return (
        isinstance(name, str)
        and 0 < len(name) <= NAME_MAX
        and name != "*"
        and not any(ch in "/:" or _barred(ch) or _surrogate(ch) for ch in name)
    )


def capture_name(title: str, item_id: str) -> str:
    """Pure capture's thread name from a title, in rest.md §4.5's three steps: `/` and `:` become
    `-` and every Cc, Zl, Zp or Bidi_Control character is dropped; the first 40 characters are
    kept; nothing left, or only `*`, falls back to the item's id. A lone surrogate is dropped with
    the controls, so the name keeps the rule every surface keeps."""
    kept = "".join(
        "-" if ch in "/:" else ch for ch in title if not (_barred(ch) or _surrogate(ch))
    )[:CAPTURE_NAME_KEEP]
    return item_id if kept in ("", "*") else kept


class AmbiguousRef(LookupError):
    """A path tail that names more than one node the caller can see. `paths` lists only those
    nodes, so the answer tells the caller nothing it could not already see."""

    def __init__(self, paths: list[str]):
        self.paths = paths
        super().__init__("matches more than one scope: " + ", ".join(paths))


class NodeService:
    def __init__(self, backend: Backend, ledger: Ledger):
        self.backend = backend
        self.ledger = ledger
        # Trust's coverage check, wired by the container. Unwired, every token-scoped lookup
        # fails closed: a node nobody can prove coverage of is a node nobody sees.
        self.covers: Callable[[Token, Node], bool] | None = None

    def visible(self, token: Token | None, node: Node) -> bool:
        """Whether `token` may see `node`; `None` is the container itself (no principal)."""
        if token is None:
            return True
        return self.covers is not None and self.covers(token, node)

    # -- roots ---------------------------------------------------------------------------
    def ensure_roots(self, *, actor: str, principal: str) -> dict[str, Node]:
        roots: dict[str, Node] = {}
        g = self.backend.find_root("global")
        if not g:
            g = Node(id=ulid(), type="global", name="global", parent=None)
            self.backend.put_node(g)
            self.ledger.append(
                "node.create", actor=actor, principal=principal, subject=g.id, type="global"
            )
        u = self.backend.find_root("user")
        if not u:
            u = Node(id=ulid(), type="user", name="self", parent=None)
            self.backend.put_node(u)
            self.ledger.append(
                "node.create", actor=actor, principal=principal, subject=u.id, type="user"
            )
        inbox = self.inbox(u)
        if not inbox:
            inbox = Node(id=ulid(), type="inbox", name="inbox", parent=u.id)
            self.backend.put_node(inbox)
            self.ledger.append(
                "node.create", actor=actor, principal=principal, subject=inbox.id, type="inbox"
            )
        roots.update(global_=g, user=u, inbox=inbox)
        return roots

    def global_root(self) -> Node:
        return self.backend.find_root("global")  # type: ignore[return-value]

    def user_root(self) -> Node:
        return self.backend.find_root("user")  # type: ignore[return-value]

    def inbox(self, user_root: Node | None = None) -> Node | None:
        u = user_root or self.user_root()
        found = self.backend.list_nodes(parent=u.id, type="inbox")
        return found[0] if found else None

    # -- structure -----------------------------------------------------------------------
    def create(
        self, type: str, name: str, parent: Node, *, token: Token, actor: str, principal: str
    ) -> Node:
        if not valid_name(name):  # the name's shape first: a fact about the request alone
            raise InvalidName("invalid_request")
        if not self.visible(token, parent):
            raise StructureError("scope not found")  # the same answer as a parent that is absent
        if type not in CONTAINER_TYPES or type in ("inbox", "global"):
            raise StructureError(f"cannot create a container of type {type!r}")
        if type == "uxo":
            raise StructureError("uxo is undefined and is not instantiated until defined (R11)")
        # Structure-creation is a permission (v0.3 §2): threads/projects baseline, the rest admin.
        if type not in BASELINE_CREATE and not token.has("admin"):
            raise StructureError(f"creating a {type} needs admin at the parent scope")
        node = Node(id=ulid(), type=type, name=name, parent=parent.id)
        with self.backend.atomic():  # the node and its entry, together (GHSA-2478-6jv5-83ff)
            self.backend.put_node(node)
            self.ledger.append(
                "node.create",
                actor=actor,
                principal=principal,
                subject=node.id,
                scope=parent.id,
                type=type,
                name=name,
            )
        return node

    def reparent(self, node: Node, new_parent: Node) -> None:
        """Moving is a metadata update — zero bytes move (v0.4 §16)."""
        node.parent = new_parent.id
        self.backend.put_node(node)

    # -- addressing ----------------------------------------------------------------------
    def ancestors(self, node: Node) -> list[Node]:
        """node itself first, then each parent up to a root."""
        out = [node]
        seen = {node.id}
        cur = node
        while cur.parent and cur.parent not in seen:
            parent = self.backend.get_node(cur.parent)
            if not parent:
                break
            out.append(parent)
            seen.add(parent.id)
            cur = parent
        return out

    def path(self, node: Node) -> str:
        parts = []
        for n in reversed(self.ancestors(node)):
            parts.append(
                n.type if n.type in ROOT_TYPES and n.type == "global" else f"{n.type}:{n.name}"
            )
        return "/".join(parts)

    def ring_rank(self, node: Node) -> int | None:
        return RING_RANK.get(node.type)

    def chain(self, scope: Node, *, include_global: bool = True) -> list[Node]:
        """The resolution chain, innermost first. Personal root rides along in every chain;
        exo is a branch beside the org tree and never inherits inward (v0.4 §2), so an exo
        ancestor ends the tree walk there before the personal root and global are appended."""
        chain: list[Node] = []
        for n in self.ancestors(scope):
            chain.append(n)
            if n.type == "exo":
                break
        user = self.user_root()
        if user and all(n.id != user.id for n in chain):
            chain.append(user)
        if include_global:
            g = self.global_root()
            if g and all(n.id != g.id for n in chain):
                chain.append(g)
        return chain

    def resolve_ref(self, ref: str, token: Token | None = None) -> Node | None:
        """Accept a node id or a path like `project:health` / `user:self/project:health`. With a
        token, only nodes it covers exist: an uncovered node answers exactly like an absent one,
        and never makes a reference ambiguous. A tail that matches several visible nodes raises
        AmbiguousRef instead of picking one."""
        node = self.backend.get_node(ref)
        if node:
            return node if self.visible(token, node) else None
        parts = ref.strip("/").split("/")
        candidates = [
            n
            for n in self.backend.list_nodes()
            if _matches_tail(self, n, parts) and self.visible(token, n)
        ]
        if len(candidates) == 1:
            return candidates[0]
        if len(candidates) > 1:
            # Nothing is picked (the Chief's revision of freeze answer 1, 2026-10-03): any rule
            # that picks — recency of creation or of activity — can be steered by whoever writes
            # into one of the candidates. The caller names one: a longer path, or the id.
            raise AmbiguousRef(sorted(self.path(n) for n in candidates))
        return None


def _matches_tail(svc: NodeService, node: Node, parts: list[str]) -> bool:
    anc = list(reversed(svc.ancestors(node)))
    labels = [n.type if n.type == "global" else f"{n.type}:{n.name}" for n in anc]
    if len(parts) > len(labels):
        return False
    tail = labels[-len(parts) :]
    return all(p == lbl or p == lbl.split(":", 1)[-1] for p, lbl in zip(parts, tail, strict=True))
