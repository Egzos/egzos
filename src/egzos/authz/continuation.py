# Copyright 2026 Ali Sasanian
# SPDX-License-Identifier: Apache-2.0
"""
`continue` (authorization-server.md §11.7; `spec/design/consent.md` D-C5).

An allowlist, never a validator. In D-C5's order:

1. reject, unparsed, any value that does not begin with exactly one `/`, begins `//` or `/\\`,
   contains a backslash, or contains a control character — and (§11.7, [0.3 · 25]) any value over
   `AS_CONTINUE_MAX_BYTES` as received;
2. compare the parsed PATH only, exactly, against `/authorize` · `/device` · `/pending` ·
   `/pending/<id>` · `/` · `/items/<id>`, `<id>` being RFC 3986 unreserved characters, not `.` or
   `..`, with no percent-encoding;
3. carry the query verbatim — still percent-encoded, never decoded — to `/authorize` and `/` only,
   and drop it for the rest; always drop the fragment;
4. anything failing a step is the container's root, silently.

The same function runs on the GET and again on the POST (§11.7, [0.3 · 26]): a form field is
caller-controlled whatever put it there.

`value` is measured at one layer: the `continue` query parameter (or form field) as the framework
hands it over after its single decode of that parameter — so `%2F` in the raw request arrives here
as `/`, and anything still percent-encoded inside it (`%252F` arriving as `%2F`) stays encoded. The
caller neither decodes it again nor passes the raw, undecoded request string.
"""

from __future__ import annotations

import re

from egzos._types import AS_CONTINUE_MAX_BYTES

ROOT = "/"

_ID = r"(?!\.{1,2}$)[A-Za-z0-9\-._~]+"
_PATTERNS = re.compile(rf"/authorize|/device|/pending|/pending/{_ID}|/|/items/{_ID}")
_CARRIES_QUERY = frozenset({"/authorize", "/"})
# Printable ASCII without the space. Step 1 names control characters; everything else outside this
# set fails closed too, since a value that is written to `Location` verbatim has no business
# carrying a byte a header cannot.
_ALLOWED = re.compile(r"[\x21-\x7e]*")


def resolve(value: str | None) -> str:
    """The relative reference a successful login 303s to: an allowlisted path, with its query
    where step 3 carries one, or `/` when the value fails any step."""
    if not isinstance(value, str) or len(value.encode("utf-8")) > AS_CONTINUE_MAX_BYTES:
        return ROOT
    # Step 1, before anything is parsed.
    if not value.startswith("/") or value.startswith(("//", "/\\")) or "\\" in value:
        return ROOT
    if not _ALLOWED.fullmatch(value):
        return ROOT
    # Step 2: the path component of a reference with no scheme and no authority — guaranteed by
    # the leading single `/` above — split by hand so nothing is decoded or normalised.
    rest, _, _fragment = value.partition("#")
    path, sep, query = rest.partition("?")
    if not _PATTERNS.fullmatch(path):
        return ROOT
    # Step 3.
    if sep and path in _CARRIES_QUERY:
        return f"{path}?{query}"
    return path
