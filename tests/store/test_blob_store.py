# Copyright 2026 Ali Sasanian
# SPDX-License-Identifier: LicenseRef-PolyForm-Strict-1.0.0
"""`BlobStore` (storage.md §4) on every blob store: content-addressed, staged apart, and staging
unaddressable until `promote`. `staged` is the harness's test-only probe (`conftest.py`): no
`BlobStore` reader may see staging, so the suite looks there from outside the Protocol."""

from __future__ import annotations

import hashlib

import pytest

DATA, OTHER = b"some bytes", b"other bytes"
SHA, OTHER_SHA = (hashlib.sha256(b).hexdigest() for b in (DATA, OTHER))


def test_put_is_idempotent_and_addresses_by_sha256(blobs):
    assert blobs.put(DATA) == SHA
    assert blobs.put(DATA) == SHA
    assert blobs.get(SHA) == DATA and blobs.exists(SHA) is True


def test_staged_bytes_are_unaddressable_until_promoted(blobs, staged):
    assert blobs.stage(DATA) == SHA
    assert staged(blobs, SHA) == DATA
    assert blobs.get(SHA) is None and blobs.exists(SHA) is False
    assert blobs.promote(SHA) is True
    assert blobs.get(SHA) == DATA and blobs.exists(SHA) is True
    assert staged(blobs, SHA) is None


def test_stage_never_dedups_against_promoted_bytes(blobs, staged):
    """[0.3 · 41]: staging bytes that are already promoted writes them to staging like any other."""
    blobs.put(DATA)
    assert blobs.stage(DATA) == SHA
    assert staged(blobs, SHA) == DATA
    assert blobs.promote(SHA) is True and staged(blobs, SHA) is None  # [0.3 · 43]: it was staged


def test_promote_is_false_for_missing_and_for_already_promoted_bytes(blobs):
    """[0.3 · 43]: an approval that promoted nothing does not look like one that did."""
    assert blobs.promote(SHA) is False
    blobs.put(DATA)
    assert blobs.promote(SHA) is False
    assert blobs.get(SHA) == DATA
    blobs.stage(OTHER)
    assert blobs.promote(OTHER_SHA) is True
    assert blobs.promote(OTHER_SHA) is False


def test_discard_deletes_staged_bytes_only(blobs, staged):
    """[0.3 · 44]: `discard` never touches promoted bytes."""
    blobs.put(DATA)
    blobs.stage(DATA)
    assert blobs.discard(SHA) is True
    assert staged(blobs, SHA) is None and blobs.get(SHA) == DATA
    assert blobs.discard(SHA) is False
    assert blobs.discard(OTHER_SHA) is False


@pytest.mark.parametrize("name", ["", SHA[:-1], SHA + "0", SHA.upper(), "g" * 64, SHA + "\n",
                                  "sha256/" + SHA, "../staging/" + SHA, "../sha256/" + SHA])
def test_a_name_that_is_not_a_digest_is_refused(blobs, staged, name):
    """`get` and `exists` answer it as absent (§5); the internal writers refuse it outright."""
    blobs.put(DATA)
    blobs.stage(DATA)
    assert blobs.get(name) is None and blobs.exists(name) is False
    with pytest.raises(ValueError):
        blobs.promote(name)
    with pytest.raises(ValueError):
        blobs.discard(name)
    assert blobs.get(SHA) == DATA and staged(blobs, SHA) == DATA
