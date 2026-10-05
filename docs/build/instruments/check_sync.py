#!/usr/bin/env python3
# Copyright 2026 Ali Sasanian
# SPDX-License-Identifier: Apache-2.0
"""Is the local tree what the branch holds? Compared by git blob SHA, nothing else.

Two ways this comparison has been done wrong before, both recorded here so they stay wrong:
  * by file size — a one-character edit (``2.6`` → ``2.7``) is the same byte count;
  * by the ``/contents/<dir>?ref=<branch>`` listing — it is cached and lags a push, so it
    reports drift right after a correct push and agreement right after a wrong one.

This script fetches the branch, resolves it to a commit, reads blob SHAs from the tree at that
commit, and hashes the local files with ``git hash-object``. Run it inside a clone.

Usage: ``python3 docs/build/instruments/check_sync.py --branch chief/instruments [PATH ...]``
Default paths: ``spec/design`` and ``docs/build/instruments``. Exit 1 on any DRIFT or MISSING.
"""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path


def git(*args: str) -> str:
    return subprocess.run(["git", *args], check=True, capture_output=True, text=True).stdout


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--remote", default="origin")
    ap.add_argument("--branch", required=True)
    ap.add_argument("paths", nargs="*", default=["spec/design", "docs/build/instruments"])
    args = ap.parse_args(argv)

    git("fetch", "--quiet", args.remote, args.branch)
    head = git("rev-parse", "FETCH_HEAD").strip()
    remote: dict[str, str] = {}
    for line in git("ls-tree", "-r", "FETCH_HEAD", *args.paths).splitlines():
        meta, path = line.split("\t", 1)
        remote[path] = meta.split()[2]

    root = Path(git("rev-parse", "--show-toplevel").strip())
    local: dict[str, str] = {}
    for base in args.paths:
        target = root / base
        # A path may name one file as well as a directory; rglob on a file yields nothing, and
        # the remote side would then report it MISSING locally when it is in sync (found by
        # this instrument on its own first push).
        candidates = [target] if target.is_file() else sorted(target.rglob("*"))
        for p in candidates:
            if p.is_file() and ".git" not in p.parts and "__pycache__" not in p.parts:
                rel = p.relative_to(root).as_posix()
                local[rel] = git("hash-object", str(p)).strip()

    bad = 0
    for path in sorted(set(remote) | set(local)):
        r, lo = remote.get(path), local.get(path)
        if r == lo:
            print(f"SYNC    {path}")
        elif r is None:
            print(f"MISSING {path} — local only (not on {args.branch})")
            bad += 1
        elif lo is None:
            print(f"MISSING {path} — on {args.branch} only (not local)")
            bad += 1
        else:
            print(f"DRIFT   {path} remote={r[:12]} local={lo[:12]}")
            bad += 1
    print(f"{'IN SYNC' if not bad else f'{bad} DIFFERENCE(S)'} with {args.branch} at {head[:12]}")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
