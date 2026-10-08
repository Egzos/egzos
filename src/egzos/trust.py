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
from egzos.model import RING_RANK, ROLE_BUNDLES, ContextItem, Node, Token, canonical, now_iso
from egzos.store.nodes import NodeService


class TrustError(Exception):
    pass


class HumanOnly(TrustError):
    """Raised when a client principal attempts a human-only act."""


# One refusal for both branches of the gate (container.md §6, capabilities.md §1).
_MOVE_REFUSED = "moving items needs `organize` (and `publish` where the audience widens)"


class TrustEngine:
    def __init__(self, backend: Backend, ledger: Ledger, nodes: NodeService):
        self.backend = backend
        self.ledger = ledger
        self.nodes = nodes

    # -- coverage & audience -----------------------------------------------------------------
    def covers(self, token: Token, node: Node) -> bool:
        """Grants bind to container ids; coverage is computed at check time down the path."""
        if not token.live:
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
        node = self.backend.get_node(item.scope)
        # Human is not enough: the human must also cover the item (#131). An uncovered item gets
        # the answer an absent one gets, before anything about it (even quarantine) is said.
        if node is None or not self.covers(token, node):
            raise TrustError("not found")
        if item.status == "quarantined":
            raise TrustError("quarantined items are not promoted; lift the quarantine deliberately")
        audience = self.audience(node) if node else []
        manifest = self.manifest_hash([item.id], item.scope, audience)
        item.trust = {"status": "verified", "promoted_at": now_iso(), "manifest": manifest}
        item.provenance["approved_by"] = actor
        item.lifecycle["updated_at"] = now_iso()
        item.lifecycle["version"] = int(item.lifecycle.get("version", 1)) + 1
        with self.backend.atomic():
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
        node = self.backend.get_node(item.scope)
        if node is None or not self.covers(token, node):
            raise TrustError("not found")  # the same answer as an item that does not exist
        if not token.has("curate"):
            raise TrustError("quarantine needs `curate`")
        affected = [item.id]
        item.trust = {"status": "quarantined", "reason": reason, "at": now_iso()}
        # The item, every derived copy and the chain entry land together, or none of them.
        with self.backend.atomic():
            self.backend.put(item)
            # propagates immediately to descendants via derived_from (v0.3 §5)
            for other in self._all_items():
                if (other.provenance.get("derived_from") == item.id
                        and other.status != "quarantined"):
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
        # The caller learns only what it may see; the chain keeps the whole propagation.
        return [
            i
            for i in affected
            if (it := self.backend.get(i))
            and (n := self.backend.get_node(it.scope))
            and self.covers(token, n)
        ]

    # -- the gate ------------------------------------------------------------------------------
    def move(self, item: ContextItem, to: Node, *, token: Token, actor: str) -> dict[str, Any]:
        """cp/mv landing at a different audience halts at the gate (v0.3 §5). Inward = instant."""
        frm = self.backend.get_node(item.scope)
        if frm is None or not self.covers(token, frm) or not self.covers(token, to):
            # Coverage lives here, not per surface: an item or target the token cannot see answers
            # exactly like one that does not exist (silence-not-errors).
            raise TrustError("not found")
        if item.status == "quarantined":
            # A quarantined item does not move, silently or by proposal (step-up spec R5).
            raise TrustError("quarantined items do not move; lift the quarantine deliberately")
        # The floor is checked BEFORE the delta (container.md §6): a token that may not move the
        # item never learns from the refusal whether the destination's audience is wider.
        if not token.has("organize"):
            raise TrustError(_MOVE_REFUSED)
        before = self.audience(frm)
        after = self.audience(to)
        delta = [a for a in after if a["token"] not in {b["token"] for b in before}]
        outward = RING_RANK.get(to.type, -1) > RING_RANK.get(frm.type, -1)

        if not delta:
            # Zero audience delta (true solo — counting agents) → instant, silently logged.
            reset = self._reset_if_agent_run(item, token.principal)
            with self.backend.atomic():  # the move and its gate entry, together
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
                    reset=[item.id] if reset else [],
                )
            return {"moved": True, "gate": "silent", "audience_delta": []}

        # Nonzero delta: this is a publish. Proposing it needs `publish` (freeze item 3). Park it —
        # even for the interactive owner the gate shows the RESOLVED audience; the confirm is a
        # separate human act (`trust approve`, behind the presence tap).
        if not token.has("publish"):
            raise TrustError(_MOVE_REFUSED)  # the floor's text: the branch is not disclosed
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
        if not p or p["status"] != "open" or not self.decides_over(token, p):
            raise TrustError("no open proposal with that id")
        # Everything the decision rests on is read under the write lock that the move takes, so
        # what is executed is exactly what was checked: the proposal still open (#118) and still
        # the decider's to decide, the target, no quarantined item, and the manifest and source
        # unchanged (approve-what-you-saw; a1r on #146 and #149). A racing decider waits on
        # BEGIN IMMEDIATE and then reads the outcome.
        stale_reason = None
        with self.backend.atomic():
            self._still_open(p["id"], token)
            to = self.backend.get_node(p["to"])
            if not to:
                raise TrustError("target scope no longer exists")
            items = [self.backend.get(x) for x in p["items"]]
            if any(i and i.status == "quarantined" for i in items):
                # Quarantined after it was parked: the manifest still matches, but a manifest
                # holding a quarantined item cannot be approved (step-up spec §11, R5). The
                # proposal stays open, because Deny still is. Which event the ENGINE writes for
                # this refusal is #125 (approval.stale means drift and a stale proposal); until
                # then the presence layer records it (step_up `closed`, reason `refused`).
                raise TrustError("Contains a quarantined item. It cannot move.")
            current = self.manifest_hash(p["items"], p["to"], self.audience(to))
            moved = [i for i in items if not i or i.scope != p["from"]]  # the source is bound too
            if current != p["manifest"] or moved:
                p["status"] = "stale"
                self.backend.put_proposal(p)
                stale_reason = (
                    "an item moved since the proposal (TOCTOU)"
                    if moved
                    else "manifest changed since proposal (TOCTOU)"
                )
                # A TOCTOU refusal is not a human "no": its own event (freeze item 39).
                self.ledger.append(
                    "approval.stale",
                    actor=actor,
                    principal=token.principal,
                    subject=p["id"],
                    reason=stale_reason,
                )
            else:
                proposer = (p.get("proposed_by") or {}).get("principal", "client")
                reset = []
                # Every move, the status and the chain entry land together: a failure on item k
                # rolls back items 1…k-1 too, so a failed approval has moved nothing.
                for item in items:
                    if item:
                        if self._reset_if_agent_run(item, proposer):
                            reset.append(item.id)
                        self._do_move(item, to, actor, token.principal)
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
                    reset=reset,
                )
        if stale_reason:
            # Raised after the transaction commits, so the stale status and its event stay.
            raise TrustError("manifest changed since the proposal was made — re-propose")
        return p

    def deny(self, proposal_id: str, *, token: Token, actor: str) -> dict[str, Any]:
        self._human_only(token, "gate.confirm")
        p = self.backend.get_proposal(proposal_id)
        if not p or p["status"] != "open" or not self.decides_over(token, p):
            raise TrustError("no open proposal with that id")
        p["status"] = "denied"
        with self.backend.atomic():
            self._still_open(p["id"], token)
            self.backend.put_proposal(p)
            self.ledger.append(
                "approval.deny", actor=actor, principal=token.principal, subject=p["id"]
            )
        return p

    def _still_open(self, proposal_id: str, token: Token) -> None:
        """Re-read the proposal under the write lock and refuse unless it is still open (#118)
        and still the decider's: the token re-read (a revoke since the pre-lock check counts) and
        its coverage of both ends re-checked against the tree as it now stands (a1r on #149).
        The checks above run before the lock, so two deciders (a lifeboat tab and a CLI `trust
        approve`) could both see it open; `atomic()` takes BEGIN IMMEDIATE, so whichever decides
        second waits here, then finds it decided and lands nothing. The answer is the one a
        missing id gets."""
        current = self.backend.get_proposal(proposal_id)
        fresh = self.backend.get_token(token.id)
        if not current or current["status"] != "open" or not fresh:
            raise TrustError("no open proposal with that id")
        if not self.decides_over(fresh, current):
            raise TrustError("no open proposal with that id")

    def decides_over(self, token: Token, proposal: dict[str, Any]) -> bool:
        """Whether `token` may decide (or see) this proposal: it covers both ends of the move,
        as `move` requires of whoever proposes one (#131). A token that does not is answered as
        if the proposal did not exist."""
        frm, to = self.backend.get_node(proposal["from"]), self.backend.get_node(proposal["to"])
        return bool(frm and to and self.covers(token, frm) and self.covers(token, to))

    # -- internals -------------------------------------------------------------------------------
    @staticmethod
    def _reset_if_agent_run(item: ContextItem, principal: str) -> bool:
        """An agent-run move lands its item unverified, on every path (silent or approved): the
        landing is a write, and writes land unverified (step-up spec §11). Whether a human-run
        move keeps a verified status is the freeze's open trust-on-copy question (#121); until it
        is settled, human-run moves keep it. The reset is recorded on the chain by the caller."""
        if principal == "interactive" or item.status != "verified":
            return False
        item.trust = {"status": "unverified"}
        return True

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
    """The largest role bundle the capabilities hold, read from `ROLE_BUNDLES` — never a second
    mapping beside it."""
    caps = set(capabilities)
    held = [role for role, bundle in ROLE_BUNDLES.items() if bundle <= caps]
    return max(held, key=lambda role: len(ROLE_BUNDLES[role]), default="reader")
