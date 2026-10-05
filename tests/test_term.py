# Copyright 2026 Ali Sasanian
# SPDX-License-Identifier: Apache-2.0
"""Terminal output shows stored text as text: controls become visible escapes, data stays intact."""

from __future__ import annotations

import json

from egzos._term import safe


def test_controls_and_bidi_marks_become_visible_escapes():
    assert safe("a\x1b[31mb\x07c\x9bd\u202ee") == "a\\x1b[31mb\\x07c\\x9bd\\u202ee"
    assert safe("line one\n\tline two") == "line one\n\tline two"  # bodies keep their lines
    assert safe("plain · “quoted” → ok") == "plain · “quoted” → ok"  # printable Unicode is text


def test_the_json_form_stays_valid_json_and_round_trips():
    value = {"title": "x\x1b]52;c;e30=\x07\x9by\u2066z"}
    out = safe(json.dumps(value, ensure_ascii=False), json=True)
    assert "\x1b" not in out and "\x9b" not in out and "\u2066" not in out
    assert json.loads(out) == value
