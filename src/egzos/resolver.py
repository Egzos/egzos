# Copyright 2026 Ali Sasanian
# SPDX-License-Identifier: Apache-2.0
"""
The resolver (v0.3 §2, v0.4 §7): walk the chain innermost-first, most-specific-wins on key
conflicts, clients may see the full chain with overridden values visible.

The resolver is NEVER a security boundary. Every layer is filtered server-side here: coverage
(silence-not-errors — an uncovered layer is simply absent), serving policy per container type,
rules verified-only everywhere, quarantined never. Every fetch is an audit event.
"""

from __future__ import annotations

from typing import Any

from egzos.backends.base import Backend
from egzos.ledger import Ledger
from egzos.model import SERVING_POLICY, VERIFIED_ONLY_KINDS, ContextItem, Node, Token
from egzos.store.nodes import NodeService
from egzos.trust import TrustEngine


class Resolver:
    def __init__(self, backend: Backend, ledger: Ledger, nodes: NodeService, trust: TrustEngine):
        self.backend = backend
        self.ledger = ledger
        self.nodes = nodes
        self.trust = trust

    def serve(self, item: ContextItem, node: Node) -> bool:
        if item.status == "quarantined":
            return False
        if item.kind in VERIFIED_ONLY_KINDS:
            return item.status == "verified"
        policy = SERVING_POLICY.get(node.type, "verified-only")
        return item.status == "verified" or policy == "serve-unverified"

    def resolve(
        self,
        scope: Node,
        *,
        token: Token,
        actor: str,
        kinds: list[str] | None = None,
        key: str | None = None,
        text: str | None = None,
        include_global: bool = True,
    ) -> dict[str, Any]:
        if not token.has("fetch"):
            return {"scope": None, "chain": [], "items": []}  # silence, not an error
        chain = self.nodes.chain(scope, include_global=include_global)
        layers: list[dict[str, Any]] = []
        items: list[dict[str, Any]] = []
        seen_keys: dict[tuple[str, str], str] = {}
        withheld = 0
        for node in chain:
            if not self.trust.covers(token, node):
                continue  # honestly partial: the token never learns this layer exists
            policy = SERVING_POLICY.get(node.type, "verified-only")
            layers.append(
                {
                    "node": node.id,
                    "path": self.nodes.path(node),
                    "type": node.type,
                    "policy": policy,
                }
            )
            for item in self.backend.query([node.id], kinds=kinds, key=key, text=text):
                if not self.serve(item, node):
                    withheld += 1
                    continue
                shadowed_by = None
                if item.key:
                    k = (item.kind, item.key)
                    if k in seen_keys:
                        shadowed_by = seen_keys[k]
                    else:
                        seen_keys[k] = item.id
                items.append(
                    {
                        "item": item.to_dict(),
                        "layer": self.nodes.path(node),
                        "layer_type": node.type,
                        "trust": item.status,
                        "shadowed_by": shadowed_by,
                    }
                )
        self.ledger.append(
            "context.fetch",
            actor=actor,
            principal=token.principal,
            subject=scope.id,
            scope=scope.id,
            client=token.client,
            layers=[layer["node"] for layer in layers],
            items=[i["item"]["id"] for i in items],
            withheld=withheld,
        )
        return {
            "scope": self.nodes.path(scope),
            "chain": layers,
            "items": items,
            "withheld": withheld,
        }
