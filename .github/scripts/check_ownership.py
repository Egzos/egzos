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
        --labels "<comma-separated PR labels>" \\
        [--ownership .github/OWNERSHIP.yml] \\
        [--changed-files /path/to/list.txt]  # one file per line; skips git \\
        [--numstat /path/to/numstat.txt]      # git diff --numstat output; skips git
"""

import argparse
import fnmatch
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

def git_changed_files(base, head):
    """Return list of files changed between base and head (three-dot diff)."""
    result = subprocess.run(
        ["git", "diff", "--name-only", "{0}...{1}".format(base, head)],
        capture_output=True, text=True, check=True,
    )
    return [f for f in result.stdout.splitlines() if f.strip()]


def git_numstat(base, head):
    """Return raw lines from git diff --numstat (base...head)."""
    result = subprocess.run(
        ["git", "diff", "--numstat", "{0}...{1}".format(base, head)],
        capture_output=True, text=True, check=True,
    )
    return result.stdout.splitlines()


def parse_numstat(lines):
    """Parse numstat lines into list of (added, removed, path) tuples.

    Binary files have '-' in both columns; we skip them (no line count impact).
    """
    entries = []
    for line in lines:
        line = line.strip()
        if not line:
            continue
        parts = line.split("\t", 2)
        if len(parts) < 3:
            continue
        added_s, removed_s, path = parts
        if added_s == "-" or removed_s == "-":
            entries.append((0, 0, path))  # binary — counts as a file but no lines
        else:
            try:
                entries.append((int(added_s), int(removed_s), path))
            except ValueError:
                entries.append((0, 0, path))
    return entries

# ---------------------------------------------------------------------------
# Size cap
# ---------------------------------------------------------------------------

def compute_size(numstat_entries, exclude_globs):
    """Return (total_lines_changed, file_count) excluding excluded paths."""
    total_lines = 0
    file_count = 0
    for added, removed, path in numstat_entries:
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
    parser.add_argument("--labels", default="", help="Comma-separated PR label names")
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
    with open(args.ownership, "r") as fh:
        ownership = yaml.safe_load(fh)

    branch_prefix = ownership.get("branch_prefix", "agent/")
    size_cap = ownership.get("size_cap", {})
    cap_lines = size_cap.get("lines", 600)
    cap_files = size_cap.get("files", 30)
    cap_exclude = size_cap.get("exclude", [])

    # Schema variant: egzos has governance_paths; platform has chief_only
    governance_paths = ownership.get("governance_paths", [])
    chief_only = ownership.get("chief_only", [])

    agents_cfg = ownership.get("agents", {})

    labels_set = set(
        label.strip() for label in args.labels.split(",") if label.strip()
    )

    # ---- Determine changed files and numstat ---------------------------------
    if args.changed_files:
        with open(args.changed_files, "r") as fh:
            changed = [f.strip() for f in fh.read().splitlines() if f.strip()]
    else:
        changed = git_changed_files(args.base, args.head)

    if args.numstat:
        with open(args.numstat, "r") as fh:
            ns_lines = fh.read().splitlines()
    else:
        ns_lines = git_numstat(args.base, args.head)

    numstat_entries = parse_numstat(ns_lines)

    # ---- Determine if human or agent branch ----------------------------------
    branch = args.branch
    is_agent_branch = branch.startswith(branch_prefix)

    failures = []
    notices = []

    if is_agent_branch:
        # Extract agent name: second segment of agent/<name>/...
        segments = branch[len(branch_prefix):].split("/")
        agent_name = segments[0] if segments else ""

        if agent_name not in agents_cfg:
            print("::error::Unknown agent '{}' — branch '{}' is not in OWNERSHIP.yml".format(
                agent_name, branch
            ))
            sys.exit(1)

        agent_cfg = agents_cfg[agent_name]
        agent_paths = agent_cfg.get("paths", [])
        agent_exclusive = agent_cfg.get("exclusive", [])
    else:
        agent_name = None
        agent_paths = []
        agent_exclusive = []
        print("Human branch '{}' — Chief owns everything.".format(branch))

    # ---- Print changed files table header -----------------------------------
    print("")
    print("{:<60} {:<10} {:<10}".format("File", "Status", "Note"))
    print("-" * 90)

    # ---- Check each changed file --------------------------------------------
    for path in changed:
        status = "OK"
        notes_for_file = []

        # -- governance_paths notices (egzos schema) --------------------------
        if matches_any(governance_paths, path):
            notices.append(path)
            notes_for_file.append("governance path")

        # -- chief_only check (platform schema) --------------------------------
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
                failures.append((path, "not in {}'s owned paths".format(agent_name)))
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
                            "exclusive to {} — {} may not touch this".format(
                                other_name, agent_name
                            ),
                        ))
                        status = "FAIL"
                        notes_for_file.append("exclusive:{}" .format(other_name))
                        break

        note_str = "; ".join(notes_for_file) if notes_for_file else ""
        print("{:<60} {:<10} {:<10}".format(path[:58], status, note_str[:30]))

    print("-" * 90)

    # ---- Emit governance ::notice:: annotations ------------------------------
    for gpath in notices:
        print("::notice::governance path touched: {}".format(gpath))

    # ---- Size cap -----------------------------------------------------------
    total_lines, file_count = compute_size(numstat_entries, cap_exclude)

    print("")
    print("Size cap: {}/{} lines changed, {}/{} files changed (excludes: {})".format(
        total_lines, cap_lines, file_count, cap_files, ", ".join(cap_exclude) if cap_exclude else "none"
    ))

    if "size-exception" in labels_set:
        print("size-exception label present — cap waived by Chief.")
    else:
        if total_lines > cap_lines:
            failures.append((
                "(size cap)",
                "{} changed lines exceeds cap of {} — split the work or ask the Chief for size-exception".format(
                    total_lines, cap_lines
                ),
            ))
        if file_count > cap_files:
            failures.append((
                "(size cap)",
                "{} changed files exceeds cap of {} — split the work or ask the Chief for size-exception".format(
                    file_count, cap_files
                ),
            ))

    # ---- Emit ::error:: for every failure and exit --------------------------
    print("")
    if failures:
        print("OWNERSHIP CHECK FAILED:")
        for path, reason in failures:
            print("::error::OWNERSHIP: {} — {}".format(path, reason))
        sys.exit(1)
    else:
        print("Ownership check passed.")
        sys.exit(0)


if __name__ == "__main__":
    main()
