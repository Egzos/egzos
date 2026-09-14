# Copyright 2026 Ali Sasanian
# SPDX-License-Identifier: Apache-2.0
"""
`parse_numstat` vs git's rename/copy display forms — issue #18.

`git diff --numstat` does not emit a plain path in the third column for a rename or a
copy. Rename detection is on by default (`diff.renames` since git 2.9) and
`ownership-check.yml` passes no `--no-renames`, so the display forms below reach
`parse_numstat` on any PR that renames or moves a file. The parser takes the column
verbatim, so the string it hands to the size-cap exclusion globs is not a path.

Every string in `RENAME_FORMS` was captured from `git diff --numstat` on git 2.55.0
against a scratch repository; none is hand-written.

Non-security finding: see issue #18 for why it is public. The fix PR flips the
`xfail_finding` markers below from strict-xfail to passing.
"""

import pytest

# (numstat display form, the new path it denotes).
#
# git's pprint_rename() emits the plain `old => new` form when the two paths share no
# directory-boundary prefix or suffix, and brace-wraps only the differing middle
# otherwise — which yields a common prefix, a common suffix, both, or an empty side.
RENAME_FORMS = [
    pytest.param("deps.lock => deps2.lock", "deps2.lock", id="plain-form-same-dir"),
    pytest.param(
        "shared/prefix/old.py => other/moved.py",
        "other/moved.py",
        id="plain-form-across-trees",
    ),
    pytest.param(
        "tests/fixtures/{old.json => new.json}",
        "tests/fixtures/new.json",
        id="brace-common-prefix",
    ),
    pytest.param("{a => b}/x/f.py", "b/x/f.py", id="brace-common-suffix"),
    pytest.param(
        "b/x/{f.py => renamed_and_edited.py}",
        "b/x/renamed_and_edited.py",
        id="brace-common-prefix-with-edit",
    ),
    pytest.param(
        "tests/fixtures/{ => sub}/plain.json",
        "tests/fixtures/sub/plain.json",
        id="brace-empty-old-side",
    ),
    pytest.param(
        "tests/fixtures/{sub => }/plain.json",
        "tests/fixtures/plain.json",
        id="brace-empty-new-side",
    ),
    pytest.param(
        "tests/fixtures/{with space.json => renamed space.json}",
        "tests/fixtures/renamed space.json",
        id="brace-path-with-space",
    ),
]


@pytest.mark.adversarial
@pytest.mark.xfail_finding
@pytest.mark.xfail(reason="known finding — see issue #18", strict=True)
@pytest.mark.parametrize(("display_form", "new_path"), RENAME_FORMS)
def test_parse_numstat_normalises_rename_form_to_new_path(
    check_ownership, display_form, new_path
):
    """Every rename/copy display form must reduce to the post-image path.

    The post-image path is what `git diff --name-only` reports for the same entry and
    what the ownership half of the check already works with, so it is the only choice
    that keeps the two halves talking about the same files.
    """
    entries = check_ownership.parse_numstat([f"10\t2\t{display_form}"])

    assert len(entries) == 1
    assert entries[0][2] == new_path


@pytest.mark.adversarial
@pytest.mark.xfail_finding
@pytest.mark.xfail(reason="known finding — see issue #18", strict=True)
def test_parse_numstat_preserves_counts_while_normalising(check_ownership):
    """Normalising the path must not disturb the added/removed columns.

    A rename carrying an edit reports real counts; the size cap depends on them.
    """
    entries = check_ownership.parse_numstat(["5\t0\tb/x/{f.py => renamed_and_edited.py}"])

    assert entries == [(5, 0, "b/x/renamed_and_edited.py")]


# --------------------------------------------------------------------------------------
# Guards on behaviour that is correct today. These pass now and must keep passing after
# the fix — they are the blast radius of any change to parse_numstat.
# --------------------------------------------------------------------------------------


@pytest.mark.adversarial
def test_parse_numstat_leaves_a_plain_path_alone(check_ownership):
    """A non-rename entry is already a path and must survive untouched."""
    entries = check_ownership.parse_numstat(["12\t3\tsrc/egzos/store/node.py"])

    assert entries == [(12, 3, "src/egzos/store/node.py")]


@pytest.mark.adversarial
def test_parse_numstat_counts_a_binary_entry_as_zero_lines(check_ownership):
    """Binary files report `-` in both columns and contribute no lines, only a file."""
    entries = check_ownership.parse_numstat(["-\t-\ttests/fixtures/blob.bin"])

    assert entries == [(0, 0, "tests/fixtures/blob.bin")]


@pytest.mark.adversarial
def test_parse_numstat_does_not_mangle_a_literal_arrow_in_a_filename(check_ownership):
    """A filename may legitimately contain ` => `, and git does not quote it.

    `=`, `>` and space are printable ASCII, so `core.quotePath` leaves them bare: a
    merely-modified file named `notes/a => b.txt` reaches `parse_numstat` as a plain
    path that is indistinguishable, in the un-suffixed display form, from a rename of
    `notes/a` to `b.txt`.

    This is the case that decides the shape of the fix. A normaliser that splits the
    display string on ` => ` will silently rewrite this path and trip this guard;
    `git diff --numstat -z` (renames emit three NUL-separated fields, plain entries
    two) or `--no-renames` resolves it without guessing. Issue #18's acceptance
    criteria leave that choice open — this test is the argument for making it.
    """
    entries = check_ownership.parse_numstat(["7\t1\tnotes/a => b.txt"])

    assert entries == [(7, 1, "notes/a => b.txt")], (
        "a plain path containing ' => ' was rewritten — the display-string form is "
        "ambiguous; use `--numstat -z` or `--no-renames` instead of parsing it"
    )
