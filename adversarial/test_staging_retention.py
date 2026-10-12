# Copyright 2026 Ali Sasanian
# SPDX-License-Identifier: LicenseRef-PolyForm-Strict-1.0.0
"""Standing target: staging abuse (R11, `blobs_staging_retention_days`, container.md §8).

The step-up tap's own denial copy (`egzos.authz.presence.TAP_COPY["outcome.denied"]`) promises an
owner: "Logged. Staged bytes kept 30 days cold." `BlobStore.stage()` already keeps a staged blob
out of `get()`/`exists()`, which is the half of that promise this file confirms still holds.

Issue #196 originally also flagged `egzos.store.items.Store.add()` calling `BlobStore.put()`
directly (never `stage()`) as a bypass. Per a1r's review of the first cut of this file
(storage.md §4 [0.3 · 41]: "the skeleton's one `put` path (`Store.add` with a file,
`store/items.py`)"), that is the contracted `put` path, not a defect — staging is for
agent-proposed artifacts awaiting approval, a path still `TODO(a1p)` (#42) and not yet reachable
to attack. That xfail is withdrawn here rather than carried as a finding against intended
behavior.

The real gap stands: nothing in `src/` reads `blobs_staging_retention_days` to purge anything
under `staging/`, and `storage.md` [0.3 · 44] names a purge "after `blobs.staging_retention_days`"
without naming its shape — no method, trigger, clock or audit event to call. That question is
#198 (a1p, `contract-change`). The purge xfail lands here once #198 settles the shape; #196 stays
open until then.
"""

from __future__ import annotations

import pytest

from egzos.container import Container

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
