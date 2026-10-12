# Copyright 2026 Ali Sasanian
# SPDX-License-Identifier: LicenseRef-PolyForm-Strict-1.0.0
"""
Adversarial test configuration — owned by a6-adversary.

Markers are registered in pyproject.toml [tool.pytest.ini_options].
"""

import re

import pytest

_ISSUE_RE = re.compile(r"#\d+")


def pytest_collection_modifyitems(items):
    """Enforce the xfail_finding pairing documented in adversarial/README.md.

    ``xfail_finding`` is registered as a plain pytest marker: it attaches metadata and has no
    effect on its own. Left unpaired, a finding test either hard-fails the required ``tests``
    check (no companion xfail — the finding blocks every PR until someone notices) or, if a
    later edit drops the companion xfail while leaving xfail_finding behind, starts silently
    passing with no ``strict=True`` guard left to catch the regression (issue #20). Both are
    quiet failures, so the pairing is enforced here instead of left as a convention.
    """
    errors = []
    for item in items:
        if item.get_closest_marker("xfail_finding") is None:
            continue
        xfail_marker = item.get_closest_marker("xfail")
        if xfail_marker is None:
            errors.append(
                f"{item.nodeid}: @pytest.mark.xfail_finding requires a paired "
                "@pytest.mark.xfail(reason=..., strict=True) — see adversarial/README.md"
            )
            continue
        if xfail_marker.kwargs.get("strict") is not True:
            errors.append(
                f"{item.nodeid}: xfail_finding's companion xfail marker must set "
                "strict=True — see adversarial/README.md"
            )
        reason = xfail_marker.kwargs.get("reason") or ""
        if not _ISSUE_RE.search(reason):
            errors.append(
                f"{item.nodeid}: xfail_finding's xfail reason must name the public issue "
                "(e.g. 'see issue #123') to keep the marker bound to its finding"
            )
    if errors:
        raise pytest.UsageError(
            "xfail_finding contract violated:\n" + "\n".join(f"  - {e}" for e in errors)
        )
