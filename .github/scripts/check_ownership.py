#!/usr/bin/env python3
# Copyright 2026 Ali Sasanian
# SPDX-License-Identifier: Apache-2.0
"""
egzos path-ownership checker.

Invoked by ownership-check.yml on every pull_request.  Exits 0 (pass) or
1 (fail) and emits ::error:: / ::notice:: annotations for GitHub Actions.

Usage:
    python3 .github/scripts/check_ownership.py \\
        --base origin/<base-ref> \\
        --head HEAD \\
        --branch "<head-ref>" \\
        [--labels-json '["label", ...]']        # default: $PR_LABELS_JSON \\
        [--size-exception-applier <login>]    # default: $SIZE_EXCEPTION_APPLIER \\
        [--ownership .github/OWNERSHIP.yml] \\
        [--changed-files /path/to/list.txt]  # one file per line; skips git \\
        [--numstat /path/to/numstat.txt]      # git diff --numstat output; skips git

Renames and copies (#18, PR #19). `git diff --numstat` prints a rename as a display
string (`old => new`, `dir/{old => new}`), not a path, and `--name-only` prints only the
post-image side. Parsing the display string is ambiguous by construction — `=`, `>` and
space are unquoted, so a modified file literally named `notes/a => b.txt` is
indistinguishable from a rename. So git is asked with `-z`: a rename then arrives as
three NUL-separated fields (counts, old path, new path) and a plain entry as two, and
nothing is guessed. The size cap charges the post-image path; the ownership rules are
applied to BOTH sides, because moving a file out of a `chief_only` or `exclusive` tree is
a change to that tree.

Every record the parser cannot interpret is a failure, never a skip: a required gate that
drops a line it does not understand has let that file past the ownership rules and the size
cap without saying so (#69).

Labels arrive as a JSON array, never a comma-joined string: a label name may itself contain a
comma, so splitting on one let a label spell a second label (#44). `size-exception` lifts the
cap only when whoever last applied it is in OWNERSHIP.yml's `size_exception_approvers` — the
label's presence proves only that someone with issues: write applied it, and egzos-forge holds
issues: write (drift F18). Both values come from the environment the workflow sets, so a
workflow that passes them runs against a checker that predates them without an argument error.

RD-005's named backstop (Egzos/egzos-platform#45): on every a6 branch ($A6_BACKSTOP=true, set
by the workflow from the branch prefix, never from anything the branch names), any change under a6's
exclusive paths fails the check until `a6-cleared`, last applied by an approver, is on the PR. The
check reads no file content: a rule over content the constrained branch writes is a denylist, and a
denylist cannot be completed (Egzos/egzos-platform#50 review). What it guarantees is that nothing an
a6 branch puts under its paths reaches the default branch without the Chief's explicit clearance. It
does not keep a reproduction out of the PR's own diff or out of the PR's own test run. Both
repositories carry this checker line-identical but for the docstring's first line; the backstop is
wired only where a workflow sets $A6_BACKSTOP (egzos-platform), and is inert elsewhere rather than
dead code.
"""

import argparse
import fnmatch
import json
import os
import subprocess
import sys

try:
    import yaml
except ImportError:
    print("::error::pyyaml not found — run: pip install pyyaml")
    sys.exit(1)

# ---------------------------------------------------------------------------
# Glob matching with ** support
# ---------------------------------------------------------------------------

def _match_parts(pp, pi, fp, fi):
    """Recursive glob-segment match.  pp/fp are lists of path segments."""
    if pi >= len(pp) and fi >= len(fp):
        return True
    if pi >= len(pp):
        return False
    if pp[pi] == "**":
        pi_next = pi + 1
        if pi_next >= len(pp):
            # ** at end of pattern — matches anything remaining (including zero segments)
            return True
        # Try matching ** against 0, 1, 2, … file segments
        for new_fi in range(fi, len(fp) + 1):
            if _match_parts(pp, pi_next, fp, new_fi):
                return True
        return False
    if fi >= len(fp):
        return False
    if fnmatch.fnmatch(fp[fi], pp[pi]):
        return _match_parts(pp, pi + 1, fp, fi + 1)
    return False


def path_matches_glob(pattern, path):
    """Return True if path matches pattern.

    * matches within one path component (does not cross /).
    ** matches zero or more path components.

    Examples:
        path_matches_glob("a/**", "a/x")         -> True
        path_matches_glob("a/**", "a/x/y/z")     -> True
        path_matches_glob("a/*", "a/x/y")        -> False
        path_matches_glob("**/*.lock", "p/q/f.lock") -> True
        path_matches_glob("CLAUDE.md", "CLAUDE.md") -> True
    """
    pp = pattern.rstrip("/").split("/")
    fp = path.strip("/").split("/")
    return _match_parts(pp, 0, fp, 0)


def matches_any(globs, path):
    """Return True if path matches any of the given glob patterns."""
    for g in globs:
        if path_matches_glob(g, path):
            return True
    return False

# ---------------------------------------------------------------------------
# Git helpers
# ---------------------------------------------------------------------------

def git_numstat_z(base, head):
    """Return raw `git diff --numstat -z` output (base...head) as one string.

    With -z, git emits `<added>\\t<removed>\\t<path>\\0` for an ordinary entry and
    `<added>\\t<removed>\\t\\0<old>\\0<new>\\0` for a rename or copy — the third column
    is empty and the two paths follow as their own fields. No display string, no
    quoting, no guessing.
    """
    result = subprocess.run(
        ["git", "diff", "--numstat", "-z", f"{base}...{head}"],
        capture_output=True, text=True, check=True,
    )
    return result.stdout


class UnparseableNumstat(ValueError):
    """A numstat record the checker cannot interpret. The gate fails on it (#69)."""


def _counts(added_s, removed_s):
    """Turn the two numstat columns into ints; binary files ('-' in both) count zero lines."""
    if added_s == "-" and removed_s == "-":
        return 0, 0
    try:
        added, removed = int(added_s), int(removed_s)
    except ValueError:
        msg = f"line counts {added_s!r}/{removed_s!r} are not integers"
        raise UnparseableNumstat(msg) from None
    if added < 0 or removed < 0:
        raise UnparseableNumstat(f"negative line count {added_s!r}/{removed_s!r}")
    return added, removed


def parse_numstat_z(raw):
    """Parse `git diff --numstat -z` output.

    Returns a list of (added, removed, path, old_path) tuples. `path` is the post-image
    path; `old_path` is the pre-image path for a rename/copy and None otherwise. Raises
    UnparseableNumstat on any record it cannot interpret; the only field it skips is the
    empty one after the final NUL terminator.
    """
    entries = []
    fields = raw.split("\0")
    if fields and fields[-1] == "":
        fields.pop()
    i = 0
    while i < len(fields):
        rec = fields[i]
        parts = rec.split("\t", 2)
        if len(parts) < 3:
            raise UnparseableNumstat(f"record {i} has {len(parts)} tab-separated field(s), not 3")
        added_s, removed_s, path = parts
        added, removed = _counts(added_s, removed_s)
        if path == "":
            # Rename/copy: the next two fields are the old and new paths.
            if i + 2 >= len(fields):
                raise UnparseableNumstat(f"rename record {i} is missing its old/new path fields")
            old_path, new_path = fields[i + 1], fields[i + 2]
            if not old_path or not new_path:
                raise UnparseableNumstat(f"rename record {i} has an empty path")
            entries.append((added, removed, new_path, old_path))
            i += 3
        else:
            entries.append((added, removed, path, None))
            i += 1
    return entries


def parse_numstat(lines):
    """Parse plain (non -z) numstat lines into (added, removed, path) tuples.

    Kept for the `--numstat <file>` test path. A rename in this format is a display string
    (`old => new`, `dir/{old => new}`) that cannot be resolved safely — see the module
    docstring — so any path containing ` => ` is refused rather than matched whole, which
    had let a chief-only source pass as an owned `docs/**` string (#69). Feed renames
    through `parse_numstat_z` instead. Blank lines are skipped; any other line the parser
    cannot interpret raises UnparseableNumstat.
    """
    entries = []
    for n, line in enumerate(lines, 1):
        if not line.strip():
            continue
        parts = line.rstrip("\n").split("\t", 2)
        if len(parts) < 3:
            raise UnparseableNumstat(f"numstat line {n} has {len(parts)} tab-separated field(s)")
        added_s, removed_s, path = parts
        if " => " in path:
            raise UnparseableNumstat(
                f"numstat line {n} is a rename display string; feed renames through -z"
            )
        added, removed = _counts(added_s, removed_s)
        entries.append((added, removed, path))
    return entries


def parse_labels_json(raw):
    """Parse the PR's labels from a JSON array of names. Anything else is an error."""
    try:
        labels = json.loads(raw or "[]")
    except ValueError as exc:
        raise ValueError(f"labels are not JSON: {exc}") from None
    if not isinstance(labels, list) or not all(isinstance(x, str) for x in labels):
        raise ValueError("labels must be a JSON array of strings")
    return set(labels)


def size_exception_waives(labels_set, applier, approvers):
    """True only when `size-exception` is present AND its last applier is an approver."""
    return "size-exception" in labels_set and bool(applier) and applier in set(approvers)


def a6_cleared_waives(labels_set, applier, approvers):
    """True only when `a6-cleared` is present AND its last applier is an approver."""
    return "a6-cleared" in labels_set and bool(applier) and applier in set(approvers)


def a6_backstop_failures(changed, scope):
    """(path, reason) for every changed path under a6's exclusive globs. Content is never read."""
    return [(path, "an a6 change here lands only once the Chief applies a6-cleared")
            for path in changed if matches_any(scope, path)]

# ---------------------------------------------------------------------------
# Size cap
# ---------------------------------------------------------------------------

def compute_size(numstat_entries, exclude_globs):
    """Return (total_lines_changed, file_count) excluding excluded paths.

    Accepts 3-tuples (added, removed, path) or 4-tuples with a trailing old_path;
    the size cap follows the post-image path either way.
    """
    total_lines = 0
    file_count = 0
    for entry in numstat_entries:
        added, removed, path = entry[0], entry[1], entry[2]
        if matches_any(exclude_globs, path):
            continue
        total_lines += added + removed
        file_count += 1
    return total_lines, file_count

# ---------------------------------------------------------------------------
# Main checker
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description="egzos path-ownership checker")
    parser.add_argument("--base", required=True, help="Base ref for diff")
    parser.add_argument("--head", default="HEAD", help="Head ref (default: HEAD)")
    parser.add_argument("--branch", required=True, help="Head branch name")
    parser.add_argument(
        "--labels-json",
        dest="labels_json",
        default=os.environ.get("PR_LABELS_JSON", "[]"),
        help="JSON array of PR label names (default: $PR_LABELS_JSON)",
    )
    parser.add_argument(
        "--size-exception-applier",
        dest="size_exception_applier",
        default=os.environ.get("SIZE_EXCEPTION_APPLIER", ""),
        help="Login that last applied size-exception (default: $SIZE_EXCEPTION_APPLIER)",
    )
    parser.add_argument(
        "--a6-backstop",
        dest="a6_backstop",
        default=os.environ.get("A6_BACKSTOP", ""),
        help="'true' when the RD-005 backstop applies to this branch (default: $A6_BACKSTOP)",
    )
    parser.add_argument(
        "--a6-cleared-applier",
        dest="a6_cleared_applier",
        default=os.environ.get("A6_CLEARED_APPLIER", ""),
        help="Login that last applied a6-cleared (default: $A6_CLEARED_APPLIER)",
    )
    parser.add_argument(
        "--pr-author",
        dest="pr_author",
        default=os.environ.get("PR_AUTHOR", ""),
        help="Login that opened the PR (default: $PR_AUTHOR)",
    )
    parser.add_argument(
        "--ownership",
        default=".github/OWNERSHIP.yml",
        help="Path to OWNERSHIP.yml",
    )
    parser.add_argument(
        "--changed-files",
        dest="changed_files",
        default=None,
        help="File with newline-separated changed files (for testing, skips git)",
    )
    parser.add_argument(
        "--numstat",
        default=None,
        help="File with git diff --numstat output (for testing, skips git)",
    )
    args = parser.parse_args()

    # ---- Load OWNERSHIP.yml --------------------------------------------------
    with open(args.ownership) as fh:
        ownership = yaml.safe_load(fh)

    branch_prefix = ownership.get("branch_prefix", "agent/")
    size_cap = ownership.get("size_cap", {})
    cap_lines = size_cap.get("lines", 600)
    cap_files = size_cap.get("files", 30)
    cap_exclude = size_cap.get("exclude", [])

    # Either key, or both: governance_paths only annotates; chief_only fails agent branches.
    governance_paths = ownership.get("governance_paths", [])
    chief_only = ownership.get("chief_only", [])
    approvers = ownership.get("size_exception_approvers", [])
    # A PR opened by one of these is always judged by agent rules. The default is the forge App, so
    # a base OWNERSHIP.yml without the key still fails closed rather than open.
    agent_identities = ownership.get("agent_identities", ["egzos-forge[bot]"])

    agents_cfg = ownership.get("agents", {})

    try:
        labels_set = parse_labels_json(args.labels_json)
    except ValueError as exc:
        print(f"::error::OWNERSHIP: {exc}")
        sys.exit(1)

    # ---- Determine changed files and numstat ---------------------------------
    # One git call, -z, feeds both halves of the check so they see one set of files.
    # A rename contributes its post-image path to the size cap and BOTH of its paths
    # to the ownership rules: the source side is a change to the tree it left.
    old_path_of = {}   # post-image path -> pre-image path, for the table's Note column
    try:
        if args.numstat:
            with open(args.numstat) as fh:
                numstat_entries = parse_numstat(fh.read().splitlines())
            derived_changed = [p for _, _, p in numstat_entries]
        else:
            z_entries = parse_numstat_z(git_numstat_z(args.base, args.head))
            numstat_entries = [(a, r, p) for a, r, p, _ in z_entries]
            derived_changed = []
            for _, _, new_path, old_path in z_entries:
                derived_changed.append(new_path)
                if old_path is not None and old_path != new_path:
                    derived_changed.append(old_path)
                    old_path_of[new_path] = old_path
    except UnparseableNumstat as exc:
        print(f"::error::OWNERSHIP: unparseable diff record — {exc}. "
              "A required gate does not pass on a line it cannot read.")
        sys.exit(1)

    if args.changed_files:
        with open(args.changed_files) as fh:
            changed = [f.strip() for f in fh.read().splitlines() if f.strip()]
    else:
        seen = set()
        changed = []
        for p in derived_changed:
            if p not in seen:
                seen.add(p)
                changed.append(p)

    new_path_of = {old: new for new, old in old_path_of.items()}

    # ---- Determine if human or agent branch ----------------------------------
    branch = args.branch
    is_agent_branch = branch.startswith(branch_prefix)

    # The branch name is the agent's own choice, so it cannot be what makes a PR the Chief's: an
    # agent identity opening a PR outside the prefix would otherwise skip chief_only, every
    # per-agent rule and the hard size cap (#40 review). Its rules need the agent's name from the
    # branch, so there is nothing to judge it by here, and the check fails closed.
    if not is_agent_branch and args.pr_author in agent_identities:
        print(f"::error::OWNERSHIP: {args.pr_author} is an agent identity and opened this PR "
              f"from '{branch}', outside '{branch_prefix}'. Agent PRs must come from "
              f"'{branch_prefix}<agent>/<slug>'.")
        sys.exit(1)

    failures = []
    notices = []

    if is_agent_branch:
        # Extract agent name: second segment of agent/<name>/...
        segments = branch[len(branch_prefix):].split("/")
        agent_name = segments[0] if segments else ""

        if agent_name not in agents_cfg:
            print(f"::error::Unknown agent '{agent_name}' — "
                  f"branch '{branch}' is not in OWNERSHIP.yml")
            sys.exit(1)

        agent_cfg = agents_cfg[agent_name]
        agent_paths = agent_cfg.get("paths", [])
    else:
        agent_name = None
        agent_paths = []
        print(f"Human branch '{branch}' — Chief owns everything.")

    # ---- Print changed files table header -----------------------------------
    print()
    print("{:<60} {:<10} {:<10}".format("File", "Status", "Note"))
    print("-" * 90)

    # ---- Check each changed file --------------------------------------------
    for path in changed:
        status = "OK"
        notes_for_file = []

        if path in new_path_of:
            notes_for_file.append(f"moved to {new_path_of[path]}")
        elif path in old_path_of:
            notes_for_file.append(f"moved from {old_path_of[path]}")

        # -- governance_paths notices -----------------------------------------
        if matches_any(governance_paths, path):
            notices.append(path)
            notes_for_file.append("governance path")

        # -- chief_only check -------------------------------------------------
        if chief_only and matches_any(chief_only, path):
            if is_agent_branch:
                failures.append((path, "chief-only path — agent branches may not touch this"))
                status = "FAIL"
                notes_for_file.append("chief-only")
            else:
                notes_for_file.append("chief-only (human OK)")

        # -- agent ownership check --------------------------------------------
        if is_agent_branch and status != "FAIL":
            # File must match one of the agent's own paths
            if not matches_any(agent_paths, path):
                failures.append((path, f"not in {agent_name}'s owned paths"))
                status = "FAIL"
                notes_for_file.append("not owned")
            else:
                # File must not match another agent's exclusive glob
                for other_name, other_cfg in agents_cfg.items():
                    if other_name == agent_name:
                        continue
                    other_exclusive = other_cfg.get("exclusive", [])
                    if other_exclusive and matches_any(other_exclusive, path):
                        failures.append((
                            path,
                            f"exclusive to {other_name} — {agent_name} may not touch this",
                        ))
                        status = "FAIL"
                        notes_for_file.append(f"exclusive:{other_name}" )
                        break

        note_str = "; ".join(notes_for_file) if notes_for_file else ""
        # The note is never truncated: on a passing run this table is the only record
        # that a move happened (#59).
        print(f"{path[:58]:<60} {status:<10} {note_str}")

    print("-" * 90)

    # ---- Emit governance ::notice:: annotations ------------------------------
    for gpath in notices:
        print(f"::notice::governance path touched: {gpath}")

    # ---- RD-005 backstop on a6 branches (Egzos/egzos-platform#45) -------------
    if agent_name == "a6-adversary" and args.a6_backstop == "true":
        if a6_cleared_waives(labels_set, args.a6_cleared_applier, approvers):
            print(f"a6-cleared applied by {args.a6_cleared_applier} — backstop lifted.")
        else:
            failures.extend(a6_backstop_failures(
                changed, agents_cfg[agent_name].get("exclusive") or ["adversarial/**"]))

    # ---- Size cap -----------------------------------------------------------
    total_lines, file_count = compute_size(numstat_entries, cap_exclude)

    print()
    excl = ", ".join(cap_exclude) if cap_exclude else "none"
    print(f"Size cap: {total_lines}/{cap_lines} lines changed, "
          f"{file_count}/{cap_files} files changed (excludes: {excl})")

    # The size cap is an AGENT rule (CLAUDE.md: WIP cap, PR size cap). On a human branch the Chief
    # is the gate, so an oversized PR is a warning, never a failure — otherwise the scaffold PR
    # itself (thousands of lines, by nature) could never pass its own check.
    over_cap = []
    if total_lines > cap_lines:
        over_cap.append(f"{total_lines} changed lines exceeds cap of {cap_lines}")
    if file_count > cap_files:
        over_cap.append(f"{file_count} changed files exceeds cap of {cap_files}")

    waived = size_exception_waives(labels_set, args.size_exception_applier, approvers)
    if "size-exception" in labels_set and not waived:
        who = args.size_exception_applier or "an unknown applier"
        print(f"::warning::size-exception was applied by {who}, who is not in "
              "size_exception_approvers — the cap stands.")
    if waived:
        print(f"size-exception applied by {args.size_exception_applier} — cap waived.")
    elif over_cap and not is_agent_branch:
        for msg in over_cap:
            print(f"::warning::SIZE: {msg} — human branch, Chief's call")
    else:
        for msg in over_cap:
            failures.append((
                "(size cap)",
                f"{msg} — split the work or ask the Chief for size-exception",
            ))

    # ---- Emit ::error:: for every failure and exit --------------------------
    print()
    if failures:
        print("OWNERSHIP CHECK FAILED:")
        for path, reason in failures:
            print(f"::error::OWNERSHIP: {path} — {reason}")
        sys.exit(1)
    else:
        print("Ownership check passed.")
        sys.exit(0)


if __name__ == "__main__":
    main()
