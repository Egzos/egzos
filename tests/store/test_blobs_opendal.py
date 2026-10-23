# Copyright 2026 Ali Sasanian
# SPDX-License-Identifier: LicenseRef-PolyForm-Strict-1.0.0
"""storage.md §4 on an object store: the blob store behind OpenDAL, held to the same rules on an
operator with no disk under it (OpenDAL's in-memory service standing in for S3)."""

from __future__ import annotations

import hashlib

import opendal
import pytest
from fastapi.testclient import TestClient

from egzos.container import OWNER, Container
from egzos.store.blobs import BLOBS_URL_ENV, BlobStore

KW = {"actor": OWNER, "principal": "interactive"}


@pytest.fixture
def store():
    return BlobStore(operator=opendal.Operator("memory"))


def test_put_dedups_and_get_reads_back(store):
    sha = store.put(b"bytes")
    assert sha == hashlib.sha256(b"bytes").hexdigest()
    assert store.put(b"bytes") == sha and store.get(sha) == b"bytes" and store.exists(sha)
    assert store.root is None


def test_staged_bytes_are_unaddressable_until_promoted(store):
    sha = store.stage(b"cold")
    assert store.get(sha) is None and not store.exists(sha)
    assert store.promote(sha) is True
    assert store.get(sha) == b"cold"
    assert store.promote(sha) is False  # nothing staged there now


def test_discard_deletes_staged_bytes_and_never_promoted_ones(store):
    kept = store.put(b"kept")
    assert store.discard(kept) is False and store.get(kept) == b"kept"
    staged = store.stage(b"gone")
    assert store.discard(staged) is True and store.discard(staged) is False
    assert store.promote(staged) is False


@pytest.mark.parametrize("bad", ["../x", "sha256/" + "0" * 64, "A" * 64, ""])
def test_no_path_is_built_from_a_value_that_is_not_a_digest(store, bad):
    assert store.get(bad) is None and store.exists(bad) is False
    with pytest.raises(ValueError):
        store.promote(bad)
    with pytest.raises(ValueError):
        store.discard(bad)


def test_one_root_or_one_operator(tmp_path):
    with pytest.raises(ValueError):
        BlobStore()
    with pytest.raises(ValueError):
        BlobStore(tmp_path, operator=opendal.Operator("memory"))


def test_a_container_keeps_its_files_where_the_url_says(tmp_path, monkeypatch):
    from egzos.api.app import create_app

    monkeypatch.setenv(BLOBS_URL_ENV, "memory://")
    c = Container(tmp_path)
    owner = c.init()
    assert c.blobs.root is None and not (tmp_path / "blobs").exists()
    door = TestClient(create_app(c))
    h = {"Authorization": f"Bearer {owner.secret}"}
    p = c.nodes.create("project", "files", c.nodes.user_root(), token=owner, **KW)
    data = b"%PDF-1.7 not really" * 10
    sha = hashlib.sha256(data).hexdigest()
    uid = door.post("/v1/uploads", headers=h, json={
        "scope": p.id, "name": "a.pdf", "mime": "application/pdf", "size": len(data),
        "sha256": sha}).json()["upload"]
    assert door.put(f"/v1/uploads/{uid}", headers=h, content=data).status_code == 200
    item = door.post("/v1/items", headers=h, json={"kind": "artifact", "upload": uid}).json()
    assert item["item"]["content"]["sha256"] == sha
    assert c.blobs.get(sha) == data
