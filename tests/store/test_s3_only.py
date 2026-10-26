# Copyright 2026 Ali Sasanian
# SPDX-License-Identifier: LicenseRef-PolyForm-Strict-1.0.0
"""What an S3 service does with the calls the object store makes, checked when `EGZOS_TEST_S3`
names one (Supabase Storage's S3 endpoint, locally), past the harness on purpose: CopyObject copies
whole, HeadObject gives an ETag, PutObject over a key overwrites, `put` never relies on a
create-only write, and the region and path-style addressing reach the prefix (storage.md §3.7,
§4). Each test works under a prefix of its own, emptied after it (`s3_root`). An error from the
service is never put in an assertion's text."""

from __future__ import annotations

import hashlib
import os
import secrets

import opendal
import pytest

from egzos.binding import object_store

#: Past one multipart part (5 MiB) and odd-sized, so a copy cut at a part would show.
DATA = secrets.token_bytes(7 * 2**20 + 13)


def test_copy_object_copies_whole(s3_root):
    op = object_store(s3_root).op
    op.write("src", DATA)
    op.copy("src", "dst")  # a HEAD for the ETag, then CopyObject with x-amz-copy-source-if-match
    assert op.stat("dst").content_length == len(DATA)
    assert hashlib.sha256(op.read("dst")).digest() == hashlib.sha256(DATA).digest()


def test_head_object_gives_an_etag(s3_root):
    op = object_store(s3_root).op
    op.write("key", b"bytes")
    assert op.stat("key").etag  # without one, OpenDAL refuses to copy, and promote with it


def test_put_object_over_an_existing_key_overwrites(s3_root):
    op = object_store(s3_root).op
    op.write("key", b"one")
    op.write("key", b"two")
    assert op.read("key") == b"two"


def test_put_asks_exists_and_never_sends_a_create_only_write(s3_root):
    store = object_store(s3_root)
    assert not store.create_only and not store.op.capability().write_with_if_not_exists
    asked, op = [], store.op

    class Seen:
        def __getattr__(self, name):
            asked.append(name)
            return getattr(op, name)

    store.op = Seen()
    sha = store.put(b"bytes")
    store.put(b"bytes")  # already there: asked, never written again
    store.op = op
    assert asked == ["exists", "write", "exists"] and store.get(sha) == b"bytes"


def test_the_region_signs_and_path_style_addressing_reaches_the_prefix(s3_root, monkeypatch):
    object_store(s3_root).op.write("key", b"bytes")  # the region named, path-style: it works
    parent, _, tail = s3_root["prefix"].rpartition("/")
    assert object_store({**s3_root, "prefix": parent}).op.read(f"{tail}/key") == b"bytes"
    named = os.environ["EGZOS_BLOBS_S3_REGION"]
    monkeypatch.setenv("EGZOS_BLOBS_S3_REGION", next(
        r for r in ("eu-west-2", "ap-south-1") if r != named))
    with pytest.raises(opendal.exceptions.PermissionDenied):  # signed for another region
        object_store(s3_root).op.read("key")
