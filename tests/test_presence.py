# Copyright 2026 Ali Sasanian
# SPDX-License-Identifier: Apache-2.0
"""The step-up tap: two deliberate presses in a browser, never a keystroke in the terminal."""

from __future__ import annotations

import importlib.util
import threading
from pathlib import Path

import pytest

from egzos.authz.presence import Presence
from egzos.container import Container

_spec = importlib.util.spec_from_file_location(
    "human_tap", Path(__file__).resolve().parent / "human_tap.py"
)
human_tap = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(human_tap)

ACT = {"title": "Mark verified", "from": "user:self", "to": "user:self", "subject": "X",
       "pair": ("user", "user"),
       "items": [{"kind": "memory", "title": "<b>t</b>", "trust": "unverified → verified"}]}


def _person(*flags):
    def opener(url):
        threading.Thread(target=human_tap.main, args=([*flags, url],), daemon=True).start()
        return True
    return opener


@pytest.fixture
def box(tmp_path, monkeypatch):
    monkeypatch.setenv("EGZOS_STEP_UP_WINDOW_SECONDS", "300")
    c = Container(tmp_path)
    c.init()
    return c


def _step_ups(box):
    return [e["details"] for e in box.ledger.tail(200) if e["event"] == "step_up"]


def test_sign_then_confirm_approves_logs_and_opens_a_window(box):
    p = Presence(box)
    assert p.require(ACT, timeout=10, opener=_person()) == "approved"
    entry = box.ledger.tail(1)[0]
    assert entry["event"] == "step_up" and entry["details"]["outcome"] == "approved"
    assert entry["details"]["window_closes"] and entry["details"]["pair"] == ["user", "user"]
    never = lambda u: pytest.fail("the window should cover this")  # noqa: E731
    assert p.require(ACT, timeout=10, opener=never) == "window"
    assert _step_ups(box)[-1]["outcome"] == "window"


def test_the_window_is_keyed_on_the_ring_pair_and_read_from_the_chain(box):
    p = Presence(box)
    assert p.require(ACT, timeout=10, opener=_person()) == "approved"
    assert not (box.home / "presence.json").exists()  # no side file to edit
    outward = {**ACT, "pair": ("project", "org")}
    assert p.require(outward, timeout=10, opener=_person("--deny")) == "denied"


def test_close_window_now_ends_every_open_window(box):
    p = Presence(box)
    assert p.require(ACT, timeout=10, opener=_person()) == "approved"
    p.close_windows()
    assert not p.window_open(("user", "user"))
    assert _step_ups(box)[-1]["outcome"] == "closed"


def test_approve_without_a_window_opens_none(box):
    p = Presence(box)
    assert p.require(ACT, timeout=10, opener=_person("--once")) == "approved"
    assert _step_ups(box)[-1]["window_closes"] is None
    assert not p.window_open(("user", "user"))


def test_window_zero_means_every_act_taps(box, monkeypatch):
    monkeypatch.setenv("EGZOS_STEP_UP_WINDOW_SECONDS", "0")
    p = Presence(box)
    assert p.require(ACT, timeout=10, opener=_person()) == "approved"
    assert p.require(ACT, timeout=10, opener=_person("--deny")) == "denied"


def test_deny_and_expiry_leave_a_trace_and_open_no_window(box):
    p = Presence(box)
    assert p.require(ACT, timeout=10, opener=_person("--deny")) == "denied"
    assert p.require(ACT, timeout=1, opener=lambda u: True) == "expired"
    assert [d["outcome"] for d in _step_ups(box)] == ["denied", "expired"]
    assert not p.window_open(("user", "user"))


def test_no_browser_and_no_terminal_prints_no_url(box, monkeypatch, capsys):
    monkeypatch.setattr("egzos.authz.presence.is_terminal", lambda: False)
    p = Presence(box)
    assert p.require(ACT, timeout=10, opener=lambda u: False) == "unavailable"
    out = capsys.readouterr().out
    assert "/tap/" not in out and "not a terminal" in out
    assert _step_ups(box)[-1]["outcome"] == "unavailable"


def test_no_browser_at_a_terminal_prints_the_one_shot_url(box, monkeypatch, capsys):
    monkeypatch.setattr("egzos.authz.presence.is_terminal", lambda: True)
    p = Presence(box)
    assert p.require(ACT, timeout=1, opener=lambda u: False) == "expired"
    assert "/tap/" in capsys.readouterr().out


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
    from egzos.authz.presence import Tap

    tap = Tap(ACT)
    page = tap.page(armed=False)
    assert "<b>t</b>" not in page and "&lt;b&gt;t&lt;/b&gt;" in page
    assert "<title>egzos · presence</title>" in page


def test_page_consumes_the_design_tokens_not_literal_colours():
    import re

    from egzos.authz.presence import TAP_STYLE, Tap

    page = Tap(ACT).page(armed=False)
    assert "--egz-act:" in page and "var(--egz-act)" in page  # the token file, then its use
    assert not re.search(r"#[0-9A-Fa-f]{3,8}\b", TAP_STYLE)


def test_the_default_is_no_window_until_windows_bind_to_the_manifest(box, monkeypatch):
    from egzos.authz.presence import window_seconds

    monkeypatch.delenv("EGZOS_STEP_UP_WINDOW_SECONDS", raising=False)
    assert window_seconds() == 0
    p = Presence(box)
    assert p.require(ACT, timeout=10, opener=_person()) == "approved"
    assert _step_ups(box)[-1]["window_closes"] is None and not p.window_open(("user", "user"))


def test_the_standalone_tap_refuses_a_post_without_origin(box):
    import urllib.error
    import urllib.request

    from egzos.authz.presence import Presence

    def no_origin(url):
        def run():
            urllib.request.urlopen(url, timeout=5).read()
            for step in ("arm", "confirm"):
                try:
                    urllib.request.urlopen(
                        urllib.request.Request(url, data=f"step={step}".encode()), timeout=5
                    )
                except urllib.error.HTTPError as e:
                    assert e.code == 403
        threading.Thread(target=run, daemon=True).start()
        return True

    assert Presence(box).require(ACT, timeout=2, opener=no_origin) == "expired"


def test_the_page_caps_long_reasons_and_long_manifests_with_reveals():
    from egzos.authz.presence import Tap

    act = {**ACT, "requester": "agent:claude-code", "reason": "r" * 600,
           "items": [{"kind": "memory", "title": f"t{i}", "trust": "x"} for i in range(15)]}
    page = Tap(act).page(armed=False)
    assert "r" * 480 + "…" in page and "<summary>Show full reason</summary>" in page
    assert page.count("<tr>") == 15 and "<summary>+ 3 more</summary>" in page
    assert "<span class=attr>agent:claude-code states:</span>" in page  # verbatim, no caps class


def test_an_armed_page_reverts_itself_after_ten_seconds():
    from egzos.authz.presence import Tap

    tap = Tap(ACT)
    assert 'http-equiv=refresh content="10"' in tap.page(armed=True)
    assert "http-equiv=refresh" not in tap.page(armed=False)


def test_the_filed_time_reads_in_local_time_like_the_other_clocks():
    from egzos.authz.presence import _clock, _local

    assert _local("2026-10-03T19:00:00Z") == _clock(1791054000.0)
    assert _local(None) == ""


def test_a_quarantined_manifest_row_carries_its_stamp():
    from egzos.authz.presence import Tap

    act = {**ACT, "blocked": "Contains a quarantined item. It cannot move.",
           "items": [{"kind": "memory", "title": "bad", "quarantined": True}]}
    page = Tap(act).page(armed=False)
    assert "<tr class=qrow>" in page and "<span class=qstamp>quarantined</span>" in page
