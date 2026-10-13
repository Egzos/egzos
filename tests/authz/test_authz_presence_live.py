# Copyright 2026 Ali Sasanian
# SPDX-License-Identifier: LicenseRef-PolyForm-Strict-1.0.0
"""The localhost tap's path check (authz/presence.py `Tap.live`): one answer, never a raise."""

from __future__ import annotations

import pytest

from egzos.authz.presence import Tap

ACT = {"kind": "proposal", "title": "Move 1 items outward", "from": "user:self",
       "to": "user:self", "dest": "user:self", "subject": "X", "filed": "20:00:00",
       "pair": ("user", "user"),
       "items": [{"kind": "memory", "title": "t", "trust": "unverified → verified"}]}


def _tap() -> Tap:
    return Tap(ACT, decide=lambda outcome, windowed: None)


def test_the_tap_path_is_live() -> None:
    tap = _tap()
    assert tap.live(f"/tap/{tap.token}")


@pytest.mark.parametrize(
    "tail",
    ["", "x", "ñ" * 43, "\xff\xfe", "\ud800", "{token}ñ", "{token}/", "{token}?a=b"],
)
def test_any_other_path_is_not_live_and_does_not_raise(tail: str) -> None:
    # `http.server` decodes the request line as latin-1, so a path can carry non-ASCII; a bare
    # `compare_digest` on it raised instead of answering "not live".
    tap = _tap()
    assert tap.live("/tap/" + tail.format(token=tap.token)) is False


def test_a_decided_tap_is_not_live() -> None:
    tap = _tap()
    tap.outcome = "approved"
    assert tap.live(f"/tap/{tap.token}") is False
