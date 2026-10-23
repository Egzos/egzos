# Copyright 2026 Ali Sasanian
# SPDX-License-Identifier: LicenseRef-PolyForm-Strict-1.0.0
"""
Blob store — content-addressed (sha256), with a staging prefix invisible to resolution (v0.3 §5).
Lives inside the store module on the Store/Vault seam (v0.5 §D, R5): no back-references into
nodes, resolver or items, so it moves to Vault whole at Phase 5.

The bytes sit behind Apache OpenDAL (v0.7 §S, bought): one library for the local disk, S3 and
Supabase Storage's S3 endpoint alike. A local container's operator is the filesystem under its
home (`blobs/`, the layout it always had); a cloud's is the one `EGZOS_BLOBS_URL` names.

Signed URLs are NOT minted here. Artifact download IS fetch: issuance passes Trust's capability
check (a3-store charter). The skeleton serves small blobs inline and records every pull.
"""

from __future__ import annotations

import hashlib
import os
import re
from pathlib import Path
from typing import Any

import opendal

#: A cloud container's blob store: an OpenDAL URI, e.g. `s3://bucket/egzos?region=…&endpoint=…`.
#: Credentials come from the store's own environment (`AWS_ACCESS_KEY_ID`, …), never the URI.
BLOBS_URL_ENV = "EGZOS_BLOBS_URL"


def open_blobs(home: Path) -> BlobStore:
    """The container's blob store: `EGZOS_BLOBS_URL`'s, else the disk under its home."""
    url = os.environ.get(BLOBS_URL_ENV)
    if url:
        return BlobStore(operator=opendal.Operator.from_uri(url))
    return BlobStore(Path(home) / "blobs")


class BlobStore:
    def __init__(self, root: Path | None = None, *, operator: Any = None):
        if (root is None) == (operator is None):
            raise ValueError("a blob store has a root on disk or an operator, one of them")
        #: The local root, where there is one; None for an object store.
        self.root = Path(root) if root is not None else None
        if self.root is not None:
            (self.root / "sha256").mkdir(parents=True, exist_ok=True)
            (self.root / "staging").mkdir(parents=True, exist_ok=True)
            operator = opendal.Operator("fs", root=str(self.root))
        self.op = operator

    @staticmethod
    def digest(data: bytes) -> str:
        return hashlib.sha256(data).hexdigest()

    def put(self, data: bytes) -> str:
        sha = self.digest(data)
        path = f"sha256/{sha}"
        if not self.op.exists(path):  # dedup by construction
            self.op.write(path, data)
        return sha

    def stage(self, data: bytes) -> str:
        sha = self.digest(data)
        self.op.write(f"staging/{sha}", data)
        return sha

    def promote(self, sha: str) -> bool:
        """approve → blob moves from staging to the real store (v0.3 §5). True if staged bytes
        moved; False if nothing was staged there, missing and already promoted alike ([0.3 · 43]):
        the internal caller's to know, never an external surface's."""
        _check(sha)
        src = f"staging/{sha}"
        if not self.op.exists(src):
            return False
        dst = f"sha256/{sha}"
        able = self.op.capability()
        if able.rename:
            self.op.rename(src, dst)
        else:
            # An object store has no rename: copied (or read and written), then the staged copy
            # deleted, so a failure between the two leaves the bytes in both places, never neither.
            if able.copy:
                self.op.copy(src, dst)
            else:
                self.op.write(dst, bytes(self.op.read(src)))
            self.op.delete(src)
        return True

    def get(self, sha: str) -> bytes | None:
        if not _is_digest(sha):
            return None  # never a path built from a value that is not a digest
        try:
            return bytes(self.op.read(f"sha256/{sha}"))
        except opendal.exceptions.NotFound:
            return None

    def exists(self, sha: str) -> bool:
        if not _is_digest(sha):
            return False
        return self.op.exists(f"sha256/{sha}")

    def discard(self, sha: str) -> bool:
        """Delete STAGED bytes, never promoted ones ([0.3 · 44]): an orphan's discard or a staged
        item's tombstone (rest.md §4.4). True if there were staged bytes to delete."""
        _check(sha)
        path = f"staging/{sha}"
        if not self.op.exists(path):
            return False
        self.op.delete(path)
        return True


_DIGEST = re.compile(r"[0-9a-f]{64}")


def _is_digest(sha: object) -> bool:
    """A blob name is a lowercase sha256 hex digest and nothing else, so no caller-supplied value
    can become a path component (`..`, `/`, a drive) under the store's root."""
    return isinstance(sha, str) and _DIGEST.fullmatch(sha) is not None


def _check(sha: object) -> None:
    if not _is_digest(sha):
        raise ValueError("not a sha256 digest")
