# Copyright 2026 Ali Sasanian
# SPDX-License-Identifier: LicenseRef-PolyForm-Strict-1.0.0
"""What only the object store (`egzos.store.objects`) does, past the harness on purpose: how
`promote` moves bytes on each service, the address checked on `get`, `put`'s dedup without a
create-only write, and no part-written blob when a write fails. `test_blob_store.py` runs the
contract itself on it. An `fs` operator with rename turned off stands in for s3, which has none."""

from __future__ import annotations

import hashlib
import signal
import subprocess
import sys
from pathlib import Path

import opendal
import pytest
from opendal.layers import CapabilityOverrideLayer

from egzos.store.objects import ObjectBlobStore, fs_operator

DATA = b"some bytes"
SHA = hashlib.sha256(DATA).hexdigest()


def _without(op: opendal.Operator, capability: str) -> opendal.Operator:
    return op.layer(CapabilityOverrideLayer(f"{capability}=false"))


@pytest.fixture
def root(tmp_path: Path) -> Path:
    return tmp_path / "blobs"


@pytest.mark.parametrize(("make", "by"), [
    (lambda root: opendal.Operator("memory"), "read+write+delete"),
    (fs_operator, "rename"),
    (lambda root: _without(fs_operator(root), "rename"), "copy+delete"),
])
def test_promote_moves_bytes_the_way_the_service_can(root, make, by):
    blobs = ObjectBlobStore(make(root))
    assert blobs.promotes_by == by
    blobs.put(DATA)
    blobs.stage(DATA)
    assert blobs.promote(SHA) is True  # decided by the staged bytes, promoted ones there or not
    assert blobs.promote(SHA) is False and blobs.discard(SHA) is False
    assert blobs.get(SHA) == DATA


@pytest.mark.parametrize(("off", "same_file"), [(None, True), ("rename", False)])
def test_on_a_directory_rename_keeps_the_staged_file_and_copy_writes_another(root, off, same_file):
    op = fs_operator(root)
    blobs = ObjectBlobStore(op if off is None else _without(op, off))
    blobs.stage(DATA)
    staged = (root / "staging" / SHA).stat().st_ino
    assert blobs.promote(SHA) is True
    assert ((root / "sha256" / SHA).stat().st_ino == staged) is same_file


def test_a_promote_cut_short_after_its_copy_is_finished_by_a_retry(root):
    """§4: a crash between the copy and the delete leaves a staged copy; promote copies again."""
    op = _without(fs_operator(root), "rename")
    blobs = ObjectBlobStore(op)
    blobs.stage(DATA)
    op.copy(f"staging/{SHA}", f"sha256/{SHA}")  # copied, then the crash
    assert blobs.promote(SHA) is True and blobs.discard(SHA) is False
    assert blobs.get(SHA) == DATA


@pytest.mark.parametrize("make", [lambda root: opendal.Operator("memory"), fs_operator])
def test_get_answers_none_for_bytes_that_do_not_hash_to_their_address(root, make):
    op = make(root)
    op.write(f"sha256/{SHA}", b"substituted")
    assert ObjectBlobStore(op).get(SHA) is None


@pytest.mark.parametrize(("off", "create_only"), [(None, True),
                                                  ("write_with_if_not_exists", False)])
def test_put_dedups_with_or_without_a_create_only_write(root, off, create_only):
    """Supabase's S3 lists no If-None-Match, so its operator is to report no create-only write,
    and `put` then asks `exists` first."""
    op = fs_operator(root)
    blobs = ObjectBlobStore(op if off is None else _without(op, off))
    assert blobs.create_only is create_only
    op.write(f"sha256/{SHA}", b"already here")
    assert blobs.put(DATA) == SHA and op.read(f"sha256/{SHA}") == b"already here"
    other = blobs.put(b"other bytes")
    assert blobs.get(other) == b"other bytes"


@pytest.mark.parametrize("write", ["put", "stage"])
def test_a_write_that_fails_part_way_leaves_no_object(root, write):
    """Past a 1 MiB file-size limit a write of 2 MiB fails half-done, and nothing is left at its
    key; a plain `fs` operator, without `fs_operator`'s temporary names, leaves the first 1 MiB."""
    resource = pytest.importorskip("resource")
    assert signal.getsignal(signal.SIGXFSZ) is signal.SIG_IGN  # EFBIG, not a killed process
    blobs, data = ObjectBlobStore(fs_operator(root)), b"z" * (2 << 20)
    soft, hard = resource.getrlimit(resource.RLIMIT_FSIZE)
    resource.setrlimit(resource.RLIMIT_FSIZE, (1 << 20, hard))
    try:
        with pytest.raises(opendal.exceptions.Unexpected, match="too large"):
            getattr(blobs, write)(data)
    finally:
        resource.setrlimit(resource.RLIMIT_FSIZE, (soft, hard))
    sha = hashlib.sha256(data).hexdigest()
    assert not blobs.op.exists(f"sha256/{sha}") and not blobs.op.exists(f"staging/{sha}")


def test_only_a_synchronous_operator_is_taken():
    with pytest.raises(TypeError):
        ObjectBlobStore(opendal.AsyncOperator("memory"))


def test_it_imports_without_opendal_and_names_the_extra_when_used(monkeypatch, root):
    code = "import sys; sys.modules['opendal'] = None; import egzos.store.objects"
    subprocess.run([sys.executable, "-c", code], check=True)
    monkeypatch.setitem(sys.modules, "opendal", None)
    with pytest.raises(ImportError, match=r"egzos\[objects\]"):
        fs_operator(root)
