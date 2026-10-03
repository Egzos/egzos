# Copyright 2026 Ali Sasanian
# SPDX-License-Identifier: Apache-2.0
"""
The trust engine (a3-trust body 1): statuses, the pending queue, promotion, quarantine with
derived_from propagation, and THE CONDITIONAL GATE (v0.4 §2): compute the audience delta of a
move. Zero delta = instant + silently logged (audience_delta:none). Nonzero = a proposal parked
in pending naming people AND agents with roles plus the inheritance blast radius. Approval is
bound to a manifest hash (item ids + target + audience snapshot) and executes only if it still
matches — TOCTOU closed (v0.4 §5).

Human-only acts (approve-from-pending, confirming a publish) demand the interactive principal.
No capability reaches them: a maximally granted client can only PROPOSE.
"""

from __future__ import annotations

import hashlib
from typing import Any

from egzos._ids import ulid
from egzos.backends.base import Backend
from egzos.ledger import Ledger
from egzos.model import RING_RANK, ContextItem, Node, Token, canonical, now_iso
from egzos.store.nodes import NodeService


class TrustError(Exception):
    pass


class HumanOnly(TrustError):
    """Raised when a client principal attempts a human-only act."""


class TrustEngine:
    def __init__(self, backend: Backend, ledger: Ledger, nodes: NodeService):
        self.backend = backend
        self.ledger = ledger
        self.nodes = nodes

    # -- coverage & audience -----------------------------------------------------------------
    def covers(self, token: Token, node: Node) -> bool:
        """Grants bind to container ids; coverage is computed at check time down the path."""
        if token.revoked:
            return False
        if "*" in token.scopes:
            return True
        ancestor_ids = {n.id for n in self.nodes.ancestors(node)}
        return any(s in ancestor_ids for s in token.scopes)

    def audience(self, node: Node) -> list[dict[str, Any]]:
        """Who can see `node`: every live token whose coverage reaches it — people AND agents."""
        out = []
        for t in self.backend.list_tokens():
            if self.covers(t, node):
                out.append(
                    {
                        "token": t.id,
                        "owner": t.owner,
                        "client": t.client,
                        "principal": t.principal,
                        "role": _role_name(t.capabilities),
                    }
                )
        return sorted(out, key=lambda a: a["token"])

    def blast_radius(self, node: Node) -> int:
        """Inheritance consequence: how many descendants (current) inherit what lands here."""
        count = 0
        stack = [node.id]
        while stack:
            pid = stack.pop()
            kids = self.backend.list_nodes(parent=pid)
            count += len(kids)
            stack.extend(k.id for k in kids)
        return count

    @staticmethod
    def manifest_hash(item_ids: list[str], target: str, audience: list[dict[str, Any]]) -> str:
        return hashlib.sha256(
            canonical({"items": sorted(item_ids), "target": target, "audience": audience}).encode()
        ).hexdigest()

    # -- pending -------------------------------------------------------------------------------
    def pending(self) -> dict[str, Any]:
        items = [i for i in self._all_items() if i.status == "unverified"]
        proposals = self.backend.list_proposals(status="open")
        return {"items": items, "proposals": proposals}

    def _all_items(self) -> list[ContextItem]:
        scopes = [n.id for n in self.backend.list_nodes()]
        return self.backend.query(scopes)

    # -- promotion / quarantine ------------------------------------------------------------------
    def promote(self, item: ContextItem, *, token: Token, actor: str) -> ContextItem:
        self._human_only(token, "approve.pending")
        if item.status == "quarantined":
            raise TrustError("quarantined items are not promoted; lift the quarantine deliberately")
        node = self.backend.get_node(item.scope)
        audience = self.audience(node) if node else []
        manifest = self.manifest_hash([item.id], item.scope, audience)
        item.trust = {"status": "verified", "promoted_at": now_iso(), "manifest": manifest}
        item.provenance["approved_by"] = actor
        item.lifecycle["updated_at"] = now_iso()
        item.lifecycle["version"] = int(item.lifecycle.get("version", 1)) + 1
        self.backend.put(item)
        self.ledger.append(
            "approval.promote",
            actor=actor,
            principal=token.principal,
            subject=item.id,
            scope=item.scope,
            manifest=manifest,
            audience=[a["client"] for a in audience],
        )
        return item

    def quarantine(self, item: ContextItem, *, token: Token, actor: str, reason: str) -> list[str]:
        if not token.has("curate"):
            raise TrustError("quarantine needs `curate`")
        affected = [item.id]
        item.trust = {"status": "quarantined", "reason": reason, "at": now_iso()}
        self.backend.put(item)
        # propagates immediately to descendants via derived_from (v0.3 §5)
        for other in self._all_items():
            if other.provenance.get("derived_from") == item.id and other.status != "quarantined":
                other.trust = {
                    "status": "quarantined",
                    "reason": f"derived from {item.id}",
                    "at": now_iso(),
                }
                self.backend.put(other)
                affected.append(other.id)
        self.ledger.append(
            "trust.quarantine",
            actor=actor,
            principal=token.principal,
            subject=item.id,
            scope=item.scope,
            reason=reason,
            affected=affected,
        )
        return affected

    # -- the gate ------------------------------------------------------------------------------
    def move(self, item: ContextItem, to: Node, *, token: Token, actor: str) -> dict[str, Any]:
        """cp/mv landing at a different audience halts at the gate (v0.3 §5). Inward = instant."""
        frm = self.backend.get_node(item.scope)
        if frm is None:
            raise TrustError("item's scope no longer exists")
        before = self.audience(frm)
        after = self.audience(to)
        delta = [a for a in after if a["token"] not in {b["token"] for b in before}]
        outward = RING_RANK.get(to.type, -1) > RING_RANK.get(frm.type, -1)

        if not delta:
            # Zero audience delta (true solo — counting agents) → instant, silently logged.
            need = "organize"
            if not token.has(need):
                return self._park(item, frm, to, token, actor, delta, reason=f"missing `{need}`")
            self._do_move(item, to, actor, token.principal)
            self.ledger.append(
                "gate.pass.silent",
                actor=actor,
                principal=token.principal,
                subject=item.id,
                scope=to.id,
                audience_delta="none",
                from_=frm.id,
                outward=outward,
            )
            return {"moved": True, "gate": "silent", "audience_delta": []}

        # Nonzero delta: this is a publish. Park it — even for the interactive owner the gate shows
        # the RESOLVED audience; the confirm is a separate human act (`trust approve`).
        return self._park(item, frm, to, token, actor, delta, reason="audience widens")

    def _park(
        self,
        item: ContextItem,
        frm: Node,
        to: Node,
        token: Token,
        actor: str,
        delta: list[dict[str, Any]],
        *,
        reason: str,
    ) -> dict[str, Any]:
        audience = self.audience(to)
        proposal = {
            "id": ulid(),
            "status": "open",
            "kind": "move",
            "items": [item.id],
            "from": frm.id,
            "to": to.id,
            "from_path": self.nodes.path(frm),
            "to_path": self.nodes.path(to),
            "audience": audience,
            "audience_delta": delta,
            "blast_radius": self.blast_radius(to),
            "manifest": self.manifest_hash([item.id], to.id, audience),
            "proposed_by": {"actor": actor, "principal": token.principal, "client": token.client},
            "reason": reason,
            "created_at": now_iso(),
        }
        self.backend.put_proposal(proposal)
        self.ledger.append(
            "gate.propose",
            actor=actor,
            principal=token.principal,
            subject=proposal["id"],
            scope=to.id,
            items=[item.id],
            audience_delta=[d["client"] for d in delta],
            reason=reason,
        )
        return {"moved": False, "gate": "pending", "proposal": proposal}

    def execute(self, proposal_id: str, *, token: Token, actor: str) -> dict[str, Any]:
        self._human_only(token, "gate.confirm")
        p = self.backend.get_proposal(proposal_id)
        if not p or p["status"] != "open":
            raise TrustError("no open proposal with that id")
        to = self.backend.get_node(p["to"])
        if not to:
            raise TrustError("target scope no longer exists")
        # Manifest binding: execute only if items + target + audience still match what was approved.
        current = self.manifest_hash(p["items"], p["to"], self.audience(to))
        if current != p["manifest"]:
            p["status"] = "stale"
            self.backend.put_proposal(p)
            self.ledger.append(
                "approval.deny",
                actor=actor,
                principal=token.principal,
                subject=p["id"],
                reason="manifest changed since proposal (TOCTOU)",
                stale=True,
            )
            raise TrustError("manifest changed since the proposal was made — re-propose")
        for item_id in p["items"]:
            item = self.backend.get(item_id)
            if item:
                self._do_move(item, to, actor, token.principal)
                # Trust-on-copy: human-run keeps status; the human confirm is the promotion.
        p["status"] = "executed"
        p["executed_at"] = now_iso()
        p["approved_by"] = actor
        self.backend.put_proposal(p)
        self.ledger.append(
            "approval.execute",
            actor=actor,
            principal=token.principal,
            subject=p["id"],
            scope=to.id,
            items=p["items"],
            manifest=p["manifest"],
        )
        return p

    def deny(self, proposal_id: str, *, token: Token, actor: str) -> dict[str, Any]:
        self._human_only(token, "gate.confirm")
        p = self.backend.get_proposal(proposal_id)
        if not p or p["status"] != "open":
            raise TrustError("no open proposal with that id")
        p["status"] = "denied"
        self.backend.put_proposal(p)
        self.ledger.append("approval.deny", actor=actor, principal=token.principal, subject=p["id"])
        return p

    # -- internals -------------------------------------------------------------------------------
    def _do_move(self, item: ContextItem, to: Node, actor: str, principal: str) -> None:
        frm = item.scope
        item.scope = to.id
        item.visibility["ring"] = to.type
        item.lifecycle["updated_at"] = now_iso()
        self.backend.put(item)
        self.ledger.append(
            "item.move", actor=actor, principal=principal, subject=item.id, scope=to.id, from_=frm
        )

    @staticmethod
    def _human_only(token: Token, act: str) -> None:
        if token.principal != "interactive":
            raise HumanOnly(f"{act} is a human-only act; a client principal can only propose")


def _role_name(capabilities: list[str]) -> str:
    caps = set(capabilities)
    if "admin" in caps:
        return "admin"
    if "curate" in caps:
        return "curator"
    if "publish" in caps:
        return "operator"
    if "remember" in caps:
        return "contributor"
    return "reader"
