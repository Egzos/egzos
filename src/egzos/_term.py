# Copyright 2026 Ali Sasanian
# SPDX-License-Identifier: LicenseRef-PolyForm-Strict-1.0.0
"""Text for a terminal: stored content is data, and a terminal treats some characters as commands.

Anything an agent wrote (a title, a body, a scope it probed) can reach the owner's terminal through
`ls`, `find`, `fetch` or an error line. Control characters there are not text: an escape sequence
can rewrite what is on screen or reach the clipboard, and bidi controls can reorder a line. So
every character that is not printable text is shown as its escape, visible and inert. Newline and
tab stay: bodies have lines.
"""

from __future__ import annotations

import json
import re

# C0 controls except tab and newline, DEL, C1 controls, the bidi / directional formatting marks,
# and surrogate code points, which no terminal or encoder takes. Written as escapes, never as the
# characters themselves.
_UNSAFE = re.compile(
    "[\x00-\x08\x0b-\x1f\x7f-\x9f\u061c\u200e\u200f\u202a-\u202e\u2066-\u2069\ud800-\udfff]"
)
_SURROGATE = re.compile("[\ud800-\udfff]")


def _escape(match: re.Match[str]) -> str:
    code = ord(match.group(0))
    return f"\\x{code:02x}" if code < 0x100 else f"\\u{code:04x}"


def _json_escape(match: re.Match[str]) -> str:
    return f"\\u{ord(match.group(0)):04x}"


def safe(text: str, *, json: bool = False) -> str:
    """`text` with every non-printing control shown as its escape. With `json` the escape is the
    JSON form, so serialised JSON stays valid (json.dumps escapes C0; this adds C1 and bidi)."""
    return _UNSAFE.sub(_json_escape if json else _escape, text)


def json_text(value: object, **options: object) -> str:
    """`value` as JSON text that keeps every character as itself but a surrogate code point, which
    is written as its six-character escape, so the text always encodes as UTF-8. A surrogate can
    sit only inside a JSON string, where the escape is valid and reads back to the same value."""
    dumped = json.dumps(value, ensure_ascii=False, **options)  # type: ignore[arg-type]
    return _SURROGATE.sub(_json_escape, dumped)


def replaced(text: str) -> str:
    """`text` with each surrogate code point replaced by U+FFFD, for a surface that draws text
    rather than escaping it."""
    return _SURROGATE.sub("\ufffd", text)
