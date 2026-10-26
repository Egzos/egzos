# Copyright 2026 Ali Sasanian
# SPDX-License-Identifier: LicenseRef-PolyForm-Strict-1.0.0
"""
Blob store on an object store, through OpenDAL (v0.7 §S): the directory store's surface and
refusals (storage.md §4) over a synchronous `opendal.Operator`, whose root is the blob root, with
`sha256/<hash>` and `staging/<hash>` under it. Using it needs `pip install "egzos[objects]"`;
importing this module does not.

What each method relies on is read from `capability()`, never assumed:
- `promote` copies where the service can (an S3-style store: one server-side copy, whole or not
  at all), else reads and writes (memory, a test fake, cannot), and never renames, so a block that
  rolls back keeps the staged copy. Its delete, as `discard`'s, waits for the act's COMMIT
  (`defer`, §3.6); a crash before it leaves a staged copy a retried `promote` or the next open's
  sweep removes (§4).
- A blob is written as whole bytes in one `write`, never through `open(..., "wb")`, whose exit
  commits what was written so far. On a directory, an `fs_operator` writes to a temporary name on
  the root's own filesystem and renames it into place, so no blob is ever seen part-written.
- `put` dedups by a create-only write where the service reports one, else asks `exists` first;
  an operator layered with `CapabilityOverrideLayer("write_with_if_not_exists=false")` takes the
  second way. `discard` asks `exists` first: `delete` is silent on a missing key.
- `get` re-hashes what it read, so a store can lose bytes but never substitute them; `promote`
  does not yet (§4, a1p), as that would read every staged object before moving it.

Like the directory store it issues nothing: a URL is `grant_url`'s rendering of Trust's grant.
"""

from __future__ import annotations

import contextlib
from collections.abc import Callable
from pathlib import Path
from typing import TYPE_CHECKING, Any

from egzos.store.blobs import GRANT_QUERY, BlobStore, _check, _is_digest, grant_url

if TYPE_CHECKING:
    import opendal

__all__ = ["GRANT_QUERY", "ObjectBlobStore", "fs_operator", "grant_url"]


def _opendal() -> Any:
    """OpenDAL, or an ImportError that names the extra installing it."""
    try:
        import opendal
    except ImportError as e:
        raise ImportError('an object store needs OpenDAL: pip install "egzos[objects]"') from e
    return opendal


def fs_operator(root: Path) -> opendal.Operator:
    """A directory as an object store. Each write goes to a temporary name in `<root>/.tmp`, so on
    the root's own filesystem, and is renamed into place: without it a write lands in place, and a
    failed one leaves a truncated blob. A failed write may leave its temporary file behind."""
    root = Path(root).absolute()
    return _opendal().Operator("fs", root=str(root), atomic_write_dir=str(root / ".tmp"))


class ObjectBlobStore:
    """`BlobStore` (storage.md §4) on an opendal `Operator`, whose root is the blob root."""

    digest = staticmethod(BlobStore.digest)  # one definition of a content address

    def __init__(self, op: opendal.Operator):
        opendal = _opendal()
        if not isinstance(op, opendal.Operator):  # an AsyncOperator answers with coroutines
            raise TypeError("ObjectBlobStore takes a synchronous opendal.Operator")
        self.op = op
        self._missing = opendal.exceptions.NotFound
        self._taken = opendal.exceptions.ConditionNotMatch
        can = op.capability()
        self.create_only = bool(can.write_with_if_not_exists)
        self.promotes_by = "copy+delete" if can.copy else "read+write+delete"
        self.defer: Callable[[str], object] = self._unstage  # as the directory store's

    def put(self, data: bytes) -> str:
        sha = self.digest(data)
        key = f"sha256/{sha}"
        if self.create_only:
            with contextlib.suppress(self._taken):  # already there: dedup by construction
                self.op.write(key, data, if_not_exists=True)
        elif not self.op.exists(key):
            self.op.write(key, data)
        return sha

    def stage(self, data: bytes) -> str:
        sha = self.digest(data)
        self.op.write(f"staging/{sha}", data)  # never deduped against promoted bytes [0.3 · 41]
        return sha

    def promote(self, sha: str) -> bool:
        """The directory store's `promote` ([0.3 · 43]), decided by the staged bytes alone: any
        promoted copy is replaced, and `False` means nothing was staged at that address."""
        _check(sha)
        src, dst = f"staging/{sha}", f"sha256/{sha}"
        if self.promotes_by == "read+write+delete":
            try:
                data = self.op.read(src)
            except self._missing:
                return False
            self.op.write(dst, data)
        elif not self.op.exists(src):
            return False
        else:
            self.op.copy(src, dst)
        self.defer(sha)  # after the COMMIT, a re-check, then the delete
        return True

    def get(self, sha: str) -> bytes | None:
        if not _is_digest(sha):
            return None  # never a key built from a value that is not a digest
        try:
            data = self.op.read(f"sha256/{sha}")
        except self._missing:
            return None
        return data if self.digest(data) == sha else None  # lost, never substituted (§4)

    def exists(self, sha: str) -> bool:
        return _is_digest(sha) and self.op.exists(f"sha256/{sha}")

    def discard(self, sha: str) -> bool:
        """Delete STAGED bytes, never promoted ones ([0.3 · 44]); True if there were any. The
        delete waits for the act's COMMIT (`defer`)."""
        _check(sha)
        if not self.op.exists(f"staging/{sha}"):
            return False
        self.defer(sha)
        return True

    def _unstage(self, sha: str) -> bool:
        """Delete the bytes staged at `sha` now, True if there were any: what `defer` runs."""
        _check(sha)
        key = f"staging/{sha}"
        if not self.op.exists(key):
            return False
        self.op.delete(key)
        return True

    def _staged_names(self) -> list[str]:
        """Every address staged here, for the open-time sweep alone (storage.md §4): the store's
        own listing, no `BlobStore` method and no reader's."""
        names = (entry.path.rpartition("/")[2] for entry in self.op.list("staging/"))
        return sorted(name for name in names if _is_digest(name))
