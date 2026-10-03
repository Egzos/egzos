# Copyright 2026 Ali Sasanian
# SPDX-License-Identifier: Apache-2.0
"""
Blob store — content-addressed (sha256), with a staging prefix invisible to resolution (v0.3 §5).
Lives inside the store module on the Store/Vault seam (v0.5 §D, R5): no back-references into
nodes, resolver or items, so it moves to Vault whole at Phase 5.

Signed URLs are NOT minted here. Artifact download IS fetch: issuance passes Trust's capability
check (a3-store charter). The skeleton serves small blobs inline and records every pull.
"""

from __future__ import annotations

import hashlib
from pathlib import Path


class BlobStore:
    def __init__(self, root: Path):
        self.root = Path(root)
        (self.root / "sha256").mkdir(parents=True, exist_ok=True)
        (self.root / "staging").mkdir(parents=True, exist_ok=True)

    @staticmethod
    def digest(data: bytes) -> str:
        return hashlib.sha256(data).hexdigest()

    def put(self, data: bytes) -> str:
        sha = self.digest(data)
        path = self.root / "sha256" / sha
        if not path.exists():  # dedup by construction
            path.write_bytes(data)
        return sha

    def stage(self, data: bytes) -> str:
        sha = self.digest(data)
        (self.root / "staging" / sha).write_bytes(data)
        return sha

    def promote(self, sha: str) -> None:
        """approve → blob moves from staging to the real store (v0.3 §5)."""
        src = self.root / "staging" / sha
        if src.exists():
            (self.root / "sha256" / sha).write_bytes(src.read_bytes())
            src.unlink()

    def get(self, sha: str) -> bytes | None:
        path = self.root / "sha256" / sha
        return path.read_bytes() if path.exists() else None

    def exists(self, sha: str) -> bool:
        return (self.root / "sha256" / sha).exists()
