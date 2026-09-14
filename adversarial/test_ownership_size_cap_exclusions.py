# Copyright 2026 Ali Sasanian
# SPDX-License-Identifier: Apache-2.0
"""
Size-cap exclusions vs git's rename/copy display forms — issue #18.

`compute_size` matches `size_cap.exclude` from `.github/OWNERSHIP.yml` against whatever
`parse_numstat` put in the path slot. For a rename that slot holds a display string, not
a path, so a file the Chief excluded from the cap can still be charged against it.

The display-form shapes exercised here are the ones captured from git 2.55.0 in
`test_ownership_numstat_parsing.py`; the paths are chosen to sit on the two exclusion
globs. The failure is a false OWNERSHIP failure — over-counting, never under-counting the
files these cases cover.

Non-security finding: see issue #18. The fix PR flips the `xfail_finding` markers.
"""

import re

import pytest

# Mirrors size_cap.exclude in .github/OWNERSHIP.yml, which a6-adversary may not edit.
# test_size_cap_excludes_mirror_ownership_yml below fails if the two drift apart — a
# stale mirror would let this whole file pass while testing the wrong globs.
SIZE_CAP_EXCLUDES = ["**/*.lock", "tests/fixtures/**"]


def _declared_size_cap_excludes(ownership_text):
    """Pull size_cap.exclude out of OWNERSHIP.yml by text scan.

    pyyaml is not in the `dev` extra the `tests` workflow installs, so this reads the
    two-level block directly rather than depending on a parser that may be absent.
    """
    excludes = []
    in_size_cap = False
    in_exclude = False
    for line in ownership_text.splitlines():
        if line.strip() and not line.startswith((" ", "\t")):
            in_size_cap = line.startswith("size_cap:")
            in_exclude = False
            continue
        if not in_size_cap:
            continue
        stripped = line.strip()
        if stripped.startswith("exclude:"):
            in_exclude = True
            continue
        if not in_exclude or not stripped or stripped.startswith("#"):
            continue
        item = re.match(r'-\s*"(?P<glob>.*)"\s*$', stripped)
        if item:
            excludes.append(item.group("glob"))
        else:
            in_exclude = False
    return excludes


@pytest.mark.adversarial
def test_size_cap_excludes_mirror_ownership_yml(repo_root):
    """The constant above must still say what OWNERSHIP.yml says."""
    ownership_text = (repo_root / ".github" / "OWNERSHIP.yml").read_text(encoding="utf-8")

    assert _declared_size_cap_excludes(ownership_text) == SIZE_CAP_EXCLUDES


@pytest.mark.adversarial
@pytest.mark.xfail_finding
@pytest.mark.xfail(reason="known finding — see issue #18", strict=True)
@pytest.mark.parametrize(
    "display_form",
    [
        pytest.param("vendor/{a.lock => b.lock}", id="lockfile-renamed-in-place"),
        pytest.param(
            "spec/x.json => tests/fixtures/x.json", id="fixture-moved-in-plain-form"
        ),
        pytest.param(
            "{spec => tests/fixtures}/x.json", id="fixture-moved-in-brace-form"
        ),
    ],
)
def test_renamed_excluded_file_does_not_consume_size_cap(check_ownership, display_form):
    """A file that lands on an exclusion glob is excluded however it got there.

    450/450 is under the 600-line cap as a single side but over it as added+removed,
    so an entry that should contribute nothing decides the check on its own.
    """
    entries = check_ownership.parse_numstat([f"450\t450\t{display_form}"])

    assert check_ownership.compute_size(entries, SIZE_CAP_EXCLUDES) == (0, 0)


# --------------------------------------------------------------------------------------
# Guards on behaviour that is correct today — the blast radius of the fix.
# --------------------------------------------------------------------------------------


@pytest.mark.adversarial
def test_fixture_renamed_within_its_own_directory_stays_excluded(check_ownership):
    """A fixture renamed in place is excluded today and must stay excluded.

    Issue #18 names this case and reports it as over-counting; it does not reproduce.
    `tests/fixtures/{old.json => new.json}` still begins with the two literal segments
    `tests/fixtures/`, and the glob `tests/fixtures/**` ends in `**`, so the unparsed
    display string matches by accident. The accident is load-bearing today, which is
    exactly why it needs a guard: normalising the path must keep this excluded rather
    than trade one wrong answer for another.
    """
    entries = check_ownership.parse_numstat(["450\t450\ttests/fixtures/{old.json => new.json}"])

    assert check_ownership.compute_size(entries, SIZE_CAP_EXCLUDES) == (0, 0)


@pytest.mark.adversarial
def test_file_moved_out_of_fixtures_still_counts(check_ownership):
    """Leaving an excluded directory must cost cap budget, before and after the fix.

    The exclusion follows the post-image path, so a file that lands outside
    `tests/fixtures/` is ordinary changed lines no matter where it started.
    """
    entries = check_ownership.parse_numstat(["450\t450\t{tests/fixtures => src/egzos}/x.py"])

    assert check_ownership.compute_size(entries, SIZE_CAP_EXCLUDES) == (900, 1)


# --------------------------------------------------------------------------------------
# The two halves of the check disagree about which files a PR touched.
# --------------------------------------------------------------------------------------

# Captured pairs: `git diff --numstat` and `git diff --name-only` over the same commit
# range, git 2.55.0.
CAPTURED_DIFF_PAIRS = [
    pytest.param(
        [
            "0\t0\tdeps.lock => deps2.lock",
            "0\t0\tshared/prefix/old.py => other/moved.py",
            "0\t0\ttests/fixtures/{old.json => new.json}",
        ],
        ["deps2.lock", "other/moved.py", "tests/fixtures/new.json"],
        id="plain-and-brace-forms",
    ),
    pytest.param(
        [
            "0\t0\t{a => b}/x/f.py",
            "0\t0\ttests/fixtures/{ => sub}/plain.json",
        ],
        ["b/x/f.py", "tests/fixtures/sub/plain.json"],
        id="common-suffix-and-empty-old-side",
    ),
    pytest.param(
        ["0\t0\ttests/fixtures/{with space.json => renamed space.json}"],
        ["tests/fixtures/renamed space.json"],
        id="path-with-space",
    ),
]


@pytest.mark.adversarial
@pytest.mark.xfail_finding
@pytest.mark.xfail(reason="known finding — see issue #18", strict=True)
@pytest.mark.parametrize(("numstat_lines", "name_only_lines"), CAPTURED_DIFF_PAIRS)
def test_numstat_and_name_only_agree_on_the_changed_files(
    check_ownership, numstat_lines, name_only_lines
):
    """The ownership half and the size-cap half must see one set of files.

    `--name-only` reports only the post-image path; `--numstat` reports both sides in
    one string. The checker runs ownership over the first list and the size cap over
    the second, so today a rename is one file to one half and something else to the
    other.
    """
    parsed = [path for _, _, path in check_ownership.parse_numstat(numstat_lines)]

    assert sorted(parsed) == sorted(name_only_lines)
