# Copyright 2026 Ali Sasanian
# SPDX-License-Identifier: Apache-2.0
"""
The shapes. Walking-skeleton versions of what spec/contracts freezes at Phase 0.2.

Every constant here is lifted from the decisions log (v0.3 §2–§5, v0.4 §2–§6, v0.5 §A,
handoff R11). Nothing is invented; where the log is silent the choice is marked SKELETON.
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from typing import Any

# --- containers -----------------------------------------------------------------------
# Ring rank is an ATTRIBUTE (UI order + outward test), not the chain (v0.4 §2).
# `enterprise` is dropped from the v0.1 vocabulary (v0.5 §A); `uxo` is undefined and never
# instantiated until defined (R11) — it keeps its slot so the ranks are stable.
CONTAINER_TYPES: tuple[str, ...] = (
    "inbox",
    "thread",
    "project",
    "team",
    "org",
    "exo",
    "uxo",
    "global",
)
RING_RANK: dict[str, int] = {t: i for i, t in enumerate(CONTAINER_TYPES)}
# Tree roots. `user` is the personal tree (user:/self) — rooted at identity, peer to org trees,
# riding along in every chain (v0.3 §2). It is not a ring.
ROOT_TYPES: tuple[str, ...] = ("user", "global")
# Structure-creation is a permission (v0.3 §2): threads/projects baseline; the rest need admin.
BASELINE_CREATE: frozenset[str] = frozenset({"thread", "project"})

# --- items -------------------------------------------------------------------------------
KINDS: tuple[str, ...] = (
    "memory",
    "preference",
    "skill",
    "artifact",
    "integration",
    "alias",
    "rule",
)
TRUST_STATUSES: tuple[str, ...] = ("unverified", "verified", "quarantined")
# Serving policy per container type (v0.3 §5): serve-unverified at thread/project (the stated
# tradeoff), verified-only from team outward. Rules are verified-only at EVERY scope (v0.4 §4).
# The personal root is verified-only (Chief, 2026-09-21, freeze decision F4): it rides along in
# every chain, so an unverified item there reaches further than any org scope. Reach → verification.
SERVING_POLICY: dict[str, str] = {
    "inbox": "serve-unverified",
    "thread": "serve-unverified",
    "project": "serve-unverified",
    "team": "verified-only",
    "org": "verified-only",
    "exo": "verified-only",
    "uxo": "verified-only",
    "global": "verified-only",
    "user": "verified-only",
}
VERIFIED_ONLY_KINDS: frozenset[str] = frozenset({"rule"})
# Small blobs inline on fetch; above the threshold the contract returns a BlobGrant descriptor
# minted by Trust (F5). The number itself is container config at 0.2; 64 KiB is the skeleton's.
INLINE_BLOB_LIMIT = 64 * 1024

# --- capabilities and principals --------------------------------------------------------
# Six capabilities are the ENTIRE vocabulary (v0.3 §5). Ordered as the ladder.
CAPABILITIES: tuple[str, ...] = ("fetch", "remember", "organize", "publish", "curate", "admin")
ROLE_BUNDLES: dict[str, frozenset[str]] = {
    "reader": frozenset({"fetch"}),
    "contributor": frozenset({"fetch", "remember"}),
    "operator": frozenset({"fetch", "remember", "organize", "publish"}),
    "curator": frozenset({"fetch", "remember", "organize", "publish", "curate"}),
    "admin": frozenset(CAPABILITIES),
}
PRINCIPALS: tuple[str, ...] = ("interactive", "client")
# Human-only acts sit OUTSIDE the capability vocabulary (v0.3 §5): no token reaches them.
HUMAN_ONLY_ACTS: tuple[str, ...] = ("gate.confirm", "yes.consume", "approve.pending")


def now_iso() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def canonical(obj: Any) -> str:
    """Canonical JSON for hashing (sorted keys, no whitespace, UTF-8 preserved)."""
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


@dataclass
class Node:
    """A container. Location is the mutable parent pointer; the path is computed."""

    id: str
    type: str
    name: str
    parent: str | None
    created_at: str = field(default_factory=now_iso)
    extra: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        d = {
            "id": self.id,
            "type": self.type,
            "name": self.name,
            "parent": self.parent,
            "created_at": self.created_at,
        }
        d.update(self.extra)
        return d

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> Node:
        known = {"id", "type", "name", "parent", "created_at"}
        return cls(
            id=d["id"],
            type=d["type"],
            name=d["name"],
            parent=d.get("parent"),
            created_at=d.get("created_at", now_iso()),
            extra={k: v for k, v in d.items() if k not in known},
        )


@dataclass
class ContextItem:
    """The atomic unit (v0.3 §3). Unknown fields survive round-trip via `extra`."""

    id: str
    kind: str
    scope: str  # node id — location, not identity
    content: dict[str, Any]
    key: str | None = None
    tags: list[str] = field(default_factory=list)
    provenance: dict[str, Any] = field(default_factory=dict)
    trust: dict[str, Any] = field(default_factory=lambda: {"status": "unverified"})
    lifecycle: dict[str, Any] = field(default_factory=dict)
    visibility: dict[str, Any] = field(default_factory=dict)
    extra: dict[str, Any] = field(default_factory=dict)

    KNOWN = (
        "id",
        "kind",
        "scope",
        "content",
        "key",
        "tags",
        "provenance",
        "trust",
        "lifecycle",
        "visibility",
    )

    @property
    def status(self) -> str:
        return self.trust.get("status", "unverified")

    def to_dict(self) -> dict[str, Any]:
        d = {k: getattr(self, k) for k in self.KNOWN}
        d.update(self.extra)
        return d

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> ContextItem:
        known = set(cls.KNOWN)
        return cls(
            id=d["id"],
            kind=d["kind"],
            scope=d["scope"],
            content=dict(d.get("content") or {}),
            key=d.get("key"),
            tags=list(d.get("tags") or []),
            provenance=dict(d.get("provenance") or {}),
            trust=dict(d.get("trust") or {"status": "unverified"}),
            lifecycle=dict(d.get("lifecycle") or {}),
            visibility=dict(d.get("visibility") or {}),
            extra={k: v for k, v in d.items() if k not in known},
        )


@dataclass
class Token:
    """Capability lives in the TOKEN, not the surface (v0.3 §5). Owner identity on every token."""

    id: str
    principal: str  # interactive | client
    owner: str
    client: str
    capabilities: list[str]
    scopes: list[str]  # node ids covered (descendants included at check time); ["*"] = everything
    created_at: str = field(default_factory=now_iso)
    last_used: str | None = None
    revoked: bool = False
    expires_at: str | None = None

    def has(self, capability: str) -> bool:
        return not self.revoked and capability in self.capabilities

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "principal": self.principal,
            "owner": self.owner,
            "client": self.client,
            "capabilities": self.capabilities,
            "scopes": self.scopes,
            "created_at": self.created_at,
            "last_used": self.last_used,
            "revoked": self.revoked,
            "expires_at": self.expires_at,
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> Token:
        return cls(
            **{
                k: d.get(k)
                for k in (
                    "id",
                    "principal",
                    "owner",
                    "client",
                    "capabilities",
                    "scopes",
                    "created_at",
                    "last_used",
                    "revoked",
                    "expires_at",
                )
            }
        )
