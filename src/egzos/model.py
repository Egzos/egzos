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
from datetime import UTC, datetime
from typing import Any

# --- vocabularies -------------------------------------------------------------------------
# Imported from the contract types, never restated: a second copy is a copy that drifts.
from egzos._types import (
    CAPABILITIES,
    CONTAINER_TYPES,
    HUMAN_ONLY_ACTS,
    KINDS,
    PRINCIPALS,
    RING_RANK,
    ROLE_BUNDLES,
    ROOT_TYPES,
    SERVING_POLICY,
    TRUST_STATUSES,
    VERIFIED_ONLY_KINDS,
)

__all__ = [
    "BASELINE_CREATE",
    "CAPABILITIES",
    "CONTAINER_TYPES",
    "HUMAN_ONLY_ACTS",
    "INLINE_BLOB_LIMIT",
    "KINDS",
    "PRINCIPALS",
    "RING_RANK",
    "ROLE_BUNDLES",
    "ROOT_TYPES",
    "SERVING_POLICY",
    "TRUST_STATUSES",
    "VERIFIED_ONLY_KINDS",
    "ContextItem",
    "Node",
    "Token",
    "canonical",
    "now_iso",
]

# Structure-creation is a permission (v0.3 §2): threads/projects baseline; the rest need admin.
BASELINE_CREATE: frozenset[str] = frozenset({"thread", "project"})
# Small blobs inline on fetch; above the threshold the contract returns a BlobGrant descriptor
# minted by Trust (F5). The number itself is container config at 0.2; 64 KiB is the skeleton's.
INLINE_BLOB_LIMIT = 64 * 1024


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
    # sha256 of the bearer value; the value itself is shown once at mint and never stored.
    secret_hash: str | None = None
    # The bearer value, present only on the object `Auth.mint` returns. Never serialised.
    secret: str | None = field(default=None, repr=False, compare=False)

    @property
    def live(self) -> bool:
        """Not revoked and not past `expires_at` (null means no expiry, capabilities.md §5)."""
        if self.revoked:
            return False
        if self.expires_at is None:
            return True
        try:
            until = datetime.fromisoformat(self.expires_at)
        except ValueError:
            return False  # an expiry nobody can read fails closed
        if until.tzinfo is None:
            until = until.replace(tzinfo=UTC)
        return datetime.now(UTC) < until

    def has(self, capability: str) -> bool:
        return self.live and capability in self.capabilities

    def to_dict(self, *, with_secret_hash: bool = False) -> dict[str, Any]:
        """The token's public view. `secret_hash` is credential-derived: only the backend's own
        row carries it (`with_secret_hash=True`); no output a caller sees does."""
        d = {
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
        if with_secret_hash:
            d["secret_hash"] = self.secret_hash
        return d

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
                    "secret_hash",
                )
            }
        )
