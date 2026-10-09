# Copyright 2026 Ali Sasanian
# SPDX-License-Identifier: LicenseRef-PolyForm-Strict-1.0.0
"""Standing target: staging abuse (R11, `blobs_staging_retention_days`, container.md §8).

The step-up tap's own denial copy (`egzos.authz.presence.TAP_COPY["outcome.denied"]`) promises an
owner: "Logged. Staged bytes kept 30 days cold." `BlobStore.stage()` already keeps a staged blob
out of `get()`/`exists()`, which is the half of that promise this file confirms still holds. The
other half does not: `egzos.store.items.Store.add()` — the only path that writes blob content —
calls `BlobStore.put()` directly, so every attachment lands permanently under `sha256/` and never
passes through `staging/` at all, and nothing in `src/` reads `blobs_staging_retention_days` to
purge anything. See issue #196.
"""

from __future__ import annotations

import pytest

from egzos.container import OWNER, Container

pytestmark = pytest.mark.adversarial


@pytest.fixture()
def box(tmp_path):
    c = Container(tmp_path / "home")
    c.init()
    return c


def test_a_staged_blob_stays_unreachable_until_promoted(box):
    sha = box.blobs.stage(b"cold until promoted")
    assert (box.blobs.root / "staging" / sha).exists()
    assert box.blobs.get(sha) is None
    assert box.blobs.exists(sha) is False
    box.blobs.promote(sha)
    assert box.blobs.get(sha) == b"cold until promoted"
    assert not (box.blobs.root / "staging" / sha).exists()


@pytest.mark.xfail_finding
@pytest.mark.xfail(
    strict=True,
    reason="#196: store.add() with file content bypasses staging entirely, so the "
    "30-day-cold purge promised by blobs_staging_retention_days has nothing to apply to",
)
def test_store_add_never_stages_a_file_attachment(box, tmp_path):
    f = tmp_path / "attachment.txt"
    f.write_text("unverified attachment content")
    owner = box.auth.interactive_token()

    item = box.store.add(file=f, token=owner, actor=OWNER, principal="interactive")
    sha = item.content["sha256"]

    # The product's own copy promises staged bytes stay cold and invisible to resolution until
    # promoted. add()'s only blob-writing call is BlobStore.put(), so the bytes land straight in
    # the permanent sha256/ prefix and staging/ is never touched for this write at all.
    assert (box.blobs.root / "staging" / sha).exists()
    assert not (box.blobs.root / "sha256" / sha).exists()
