# Copyright 2026 Ali Sasanian
# SPDX-License-Identifier: LicenseRef-PolyForm-Strict-1.0.0
"""
Blob store — content-addressed (sha256), with a staging prefix invisible to resolution (v0.3 §5).
Lives inside the store module on the Store/Vault seam (v0.5 §D, R5): no back-references into
nodes, resolver or items, so it moves to Vault whole at Phase 5.

Signed URLs are NOT minted here. Artifact download IS fetch: issuance passes Trust's capability
check (a3-store charter). Store only renders the `BlobGrant` Trust minted into its URL
(`grant_url`), and decides nothing (F5, storage.md §4).
"""

from __future__ import annotations

import hashlib
import re
from pathlib import Path
from urllib.parse import urlencode

from egzos._types import BlobGrant


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

    def promote(self, sha: str) -> bool:
        """approve → blob moves from staging to the real store (v0.3 §5). True if staged bytes
        moved; False if nothing was staged there, missing and already promoted alike ([0.3 · 43]):
        the internal caller's to know, never an external surface's."""
        _check(sha)
        src = self.root / "staging" / sha
        if not src.exists():
            return False
        (self.root / "sha256" / sha).write_bytes(src.read_bytes())
        src.unlink()
        return True

    def get(self, sha: str) -> bytes | None:
        if not _is_digest(sha):
            return None  # never a path built from a value that is not a digest
        path = self.root / "sha256" / sha
        return path.read_bytes() if path.exists() else None

    def exists(self, sha: str) -> bool:
        if not _is_digest(sha):
            return False
        return (self.root / "sha256" / sha).exists()

    def discard(self, sha: str) -> bool:
        """Delete STAGED bytes, never promoted ones ([0.3 · 44]): an orphan's discard or a staged
        item's tombstone (rest.md §4.4). True if there were staged bytes to delete."""
        _check(sha)
        path = self.root / "staging" / sha
        if path.exists():
            path.unlink()
            return True
        return False


#: rest.md §6: a grant's fields in its URL's query, in this order; `sha256` is the path's.
GRANT_QUERY = ("item", "token", "expires_at", "sig")


def grant_url(grant: BlobGrant) -> str:
    """rest.md §6's URL for a grant, its four other fields in the query, each value encoded."""
    query = urlencode([(k, grant[k]) for k in GRANT_QUERY], safe=":")
    return f"/v1/blobs/{grant['sha256']}?{query}"


_DIGEST = re.compile(r"[0-9a-f]{64}")


def _is_digest(sha: object) -> bool:
    """A blob name is a lowercase sha256 hex digest and nothing else, so no caller-supplied value
    can become a path component (`..`, `/`, a drive) under the store's root."""
    return isinstance(sha, str) and _DIGEST.fullmatch(sha) is not None


def _check(sha: object) -> None:
    if not _is_digest(sha):
        raise ValueError("not a sha256 digest")
