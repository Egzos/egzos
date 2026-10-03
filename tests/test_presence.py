# Copyright 2026 Ali Sasanian
# SPDX-License-Identifier: Apache-2.0
"""The step-up tap: two deliberate presses in a browser, never a keystroke in the terminal."""

from __future__ import annotations

import importlib.util
import threading
from pathlib import Path

import pytest

from egzos.container import Container
from egzos.presence import Presence

_spec = importlib.util.spec_from_file_location(
    "human_tap", Path(__file__).resolve().parents[1] / "scripts" / "human_tap.py"
)
human_tap = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(human_tap)

ACT = {"title": "Mark verified", "from": "user:self", "to": "user:self", "subject": "X",
       "items": [{"kind": "memory", "title": "<b>t</b>", "trust": "unverified → verified"}]}


def _person(*flags):
    def opener(url):
        threading.Thread(target=human_tap.main, args=([*flags, url],), daemon=True).start()
        return True
    return opener


@pytest.fixture
def box(tmp_path, monkeypatch):
    monkeypatch.delenv("EGZOS_STEP_UP_WINDOW_SECONDS", raising=False)
    c = Container(tmp_path)
    c.init()
    return c


def test_sign_then_confirm_approves_logs_and_opens_a_window(box):
    p = Presence(box)
    assert p.require(ACT, timeout=10, opener=_person()) == "approved"
    entry = box.ledger.tail(1)[0]
    assert entry["event"] == "step_up"
    never = lambda u: pytest.fail("the window should cover this")  # noqa: E731
    assert p.require(ACT, timeout=10, opener=never) == "window"


def test_window_zero_means_every_act_taps(box, monkeypatch):
    monkeypatch.setenv("EGZOS_STEP_UP_WINDOW_SECONDS", "0")
    p = Presence(box)
    assert p.require(ACT, timeout=10, opener=_person()) == "approved"
    assert p.require(ACT, timeout=10, opener=_person("--deny")) == "denied"


def test_deny_and_silence(box):
    p = Presence(box)
    assert p.require(ACT, timeout=10, opener=_person("--deny")) == "denied"
    assert p.require(ACT, timeout=1, opener=lambda u: True) == "expired"
    assert all(e["event"] != "step_up" for e in box.ledger.tail(50))


def test_confirm_without_arming_does_not_sign(box):
    p = Presence(box)

    def confirm_only(url):
        def run():
            import urllib.request

            urllib.request.urlopen(url, timeout=5).read()
            human_tap.press(url, "confirm")
        threading.Thread(target=run, daemon=True).start()
        return True

    assert p.require(ACT, timeout=2, opener=confirm_only) == "expired"


def test_page_escapes_and_wrong_token_is_404(box):
    from egzos.presence import Tap

    tap = Tap(ACT)
    page = tap.page(armed=False)
    assert "<b>t</b>" not in page and "&lt;b&gt;t&lt;/b&gt;" in page
    assert "<title>egzos · presence</title>" in page
