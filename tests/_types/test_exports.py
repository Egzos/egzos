# Copyright 2026 Ali Sasanian
# SPDX-License-Identifier: LicenseRef-PolyForm-Strict-1.0.0
"""
`_types.py`'s export surface, pinned.

`__all__` is explicit and was exhaustive until a round added five public names and listed none of
them (#104, a1r round 1). Every other test here imports the module as `t` and so bypasses `__all__`
entirely, which is why the suite stayed green. This test reads the module's public namespace and
asserts the list covers it, so the next omission fails here rather than in whichever module first
writes `from egzos._types import *`.
"""

from __future__ import annotations

import egzos._types as t

# Names the module imports for its own use — present in its namespace, not part of its surface.
IMPORTED = {
    "annotations",
    "Any",
    "Iterable",
    "Iterator",
    "Literal",
    "NotRequired",
    "Protocol",
    "TypedDict",
    "get_args",
}


def _public_names() -> set[str]:
    return {name for name in vars(t) if not name.startswith("_")} - IMPORTED


def test_all_names_every_public_definition_and_nothing_else():
    assert set(t.__all__) == _public_names()


def test_all_has_no_duplicates():
    assert len(t.__all__) == len(set(t.__all__))
