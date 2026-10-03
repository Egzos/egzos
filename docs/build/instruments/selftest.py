#!/usr/bin/env python3
# Copyright 2026 Ali Sasanian
# SPDX-License-Identifier: Apache-2.0
"""A check that cannot fail is not a check. This makes every audit check fail on purpose.

For each check id in ``audit_specs.py`` it copies ``spec/design`` to a temporary directory,
applies one mutation that should trip exactly that check, runs the audit on the copy, and asserts
(1) the run exits non-zero and (2) the expected id appears in its output. It also asserts the
unmutated tree is CLEAN first, so a mutation cannot pass by riding a pre-existing failure.

Every mutation asserts its anchor occurs exactly once before editing — a mutation that silently
edits nothing would be a passing test of nothing, which is the failure this file exists to catch.

Usage: ``python3 docs/build/instruments/selftest.py [spec/design]``. Exit 1 on any miss.
"""

from __future__ import annotations

import re
import shutil
import subprocess
import sys
import tempfile
from collections.abc import Callable
from pathlib import Path

import check_keys

HERE = Path(__file__).resolve().parent
AUDIT = HERE / "audit_specs.py"
TAP = "step-up-tap-and-pending-approval.md"


def edit(root: Path, rel: str, old: str, new: str, count: int = 1) -> None:
    p = root / rel
    s = p.read_text(encoding="utf-8")
    n = s.count(old)
    if n != count:
        raise SystemExit(f"selftest: anchor for {rel} occurs {n}× (expected {count}): {old[:80]!r}")
    p.write_text(s.replace(old, new), encoding="utf-8")


def re_edit(root: Path, rel: str, pattern: str, repl: str) -> None:
    p = root / rel
    s = p.read_text(encoding="utf-8")
    new, n = re.subn(pattern, repl, s, count=1, flags=re.MULTILINE)
    if n != 1:
        raise SystemExit(f"selftest: pattern for {rel} did not match once: {pattern!r}")
    p.write_text(new, encoding="utf-8")


def header_version(root: Path, rel: str) -> str:
    m = re.search(r"\*\*Version:\*\* (\d+\.\d+)", (root / rel).read_text(encoding="utf-8"))
    assert m, rel
    return m.group(1)


def bump(v: str) -> str:
    maj, mi = v.split(".")
    return f"{maj}.{int(mi) + 1}"


# ── mutations: (check id, description, function) ─────────────────────────────────────────────
def m_header(r: Path) -> None:
    re_edit(
        r,
        "consent.md",
        r"^\*\*Spec:\*\* `spec/design/consent.md` · \*\*Version:\*\*",
        "**Spec:** `spec/design/consent.md` · Version:",
    )


def m_changelog(r: Path) -> None:
    v = header_version(r, "consent.md")
    edit(r, "consent.md", f"**Version:** {v} ·", f"**Version:** {bump(v)} ·")
    edit(r, "README.md", f"| `consent.md` | {v} |", f"| `consent.md` | {bump(v)} |")


def m_date(r: Path) -> None:
    re_edit(
        r,
        "lifeboat.md",
        r"^(\*\*Spec:\*\* `spec/design/lifeboat.md` .* \*\*Date:\*\* )\d{4}-\d{2}-\d{2}",
        r"\g<1>2030-01-01",
    )
    re_edit(
        r, "README.md", r"^(\| `lifeboat\.md` \| \d+\.\d+ \| )\d{4}-\d{2}-\d{2}", r"\g<1>2030-01-01"
    )


def m_history(r: Path) -> None:
    text = (r / TAP).read_text(encoding="utf-8")
    hist = re.search(r"\*\*Date:\*\* \d{4}-\d{2}-\d{2} \((v\d+\.\d+) · ", text)
    assert hist, "tap history"
    edit(r, TAP, f"({hist.group(1)} · ", "(")


def m_sameday(r: Path) -> None:
    edit(
        r,
        "tokens.css",
        "v0.4: 2026-09-22 · v0.3: 2026-09-11)",
        "v0.4: same day · v0.3: 2026-09-11)",
    )


def m_chain(r: Path) -> None:
    text = (r / "DESIGN-SOURCES.md").read_text(encoding="utf-8")
    m = re.search(r"v(\d+\.\d+) \((\d{4}-\d{2}-\d{2}); supersedes v(\d+\.\d+)\)", text)
    assert m, "sources chain"
    edit(
        r,
        "DESIGN-SOURCES.md",
        m.group(0),
        f"v{m.group(1)} ({m.group(2)}; supersedes v{bump(m.group(3))})",
    )


def m_index(r: Path) -> None:
    v = header_version(r, "lifeboat.md")
    edit(r, "README.md", f"| `lifeboat.md` | {v} |", f"| `lifeboat.md` | {bump(v)} |")


def m_decision(r: Path) -> None:
    edit(r, "consent.md", "## 0. Scope\n", "## 0. Scope\n\nSee also D-C40.\n")


def m_historyonly(r: Path) -> None:
    # Move the D-C6 statement out of the decisions block and into the changelog region.
    p = r / "consent.md"
    lines = p.read_text(encoding="utf-8").splitlines(keepends=True)
    idx = [i for i, ln in enumerate(lines) if ln.startswith("- **D-C6 · ")]
    assert len(idx) == 1, "D-C6 definition"
    stated = lines.pop(idx[0])
    first = next(i for i, ln in enumerate(lines) if ln.startswith("**Changelog"))
    lines.insert(first + 1, "\n" + stated.removeprefix("- "))
    p.write_text("".join(lines), encoding="utf-8")


def m_veto(r: Path) -> None:
    re_edit(r, "lifeboat.md", r"veto window on D-L1–D-L4", "veto window on D-L1–D-L3")


def m_cite(r: Path) -> None:
    edit(r, TAP, "## 0. Scope\n", "## 0. Scope\n\nSee `consent.md` D-C40.\n")


def m_pointer(r: Path) -> None:
    edit(
        r,
        "consent.md",
        "**Principles:** `DESIGN-PRINCIPLES.md` v1.6",
        "**Principles:** `DESIGN-PRINCIPLES.md` v1.5",
    )


def m_reference(r: Path) -> None:
    edit(
        r,
        "lifeboat.md",
        "**Tokens:** `spec/design/tokens.css` (the token file;",
        "**Tokens:** `spec/design/tokens.css` v0.12 (the token file;",
    )


def m_recheck(r: Path) -> None:
    edit(
        r,
        "consent.md",
        "## 19. Relationship to the flagship and the lifeboat\n",
        "## 19. Relationship to the flagship and the lifeboat\nSee the tap spec v1.2 §19.\n",
    )


def m_key(r: Path) -> None:
    edit(r, "consent.md", "## 0. Scope\n", "## 0. Scope\n\nRenders §13 `nope.key` here.\n")


def m_identity(r: Path) -> None:
    re_edit(
        r,
        "lifeboat.md",
        r"^\| shell\.viewer \| `you · <user> · principal: interactive · present since",
        "| shell.viewer | `you · <user> · principal: interactive · here since",
    )


def m_event(r: Path) -> None:
    text = check_keys_section(r / "consent.md", 4)
    row = next(ln for ln in text.splitlines() if ln.startswith("| already signed in |"))
    cells = row[1:-1].split("|")
    cells[-1] = " (none) "
    edit(r, "consent.md", row, "|" + "|".join(cells) + "|")


def m_table(r: Path) -> None:
    text = check_keys_section(r / "consent.md", 4)
    row = next(ln for ln in text.splitlines() if ln.startswith("| already signed in |"))
    edit(r, "consent.md", row, row.rsplit("|", 2)[0] + "|")


def m_literal(r: Path) -> None:
    edit(r, "consent.md", "## 6. Colour law\n", "## 6. Colour law\nAct blue is #1D3FA8 by day.\n")


def m_record(r: Path) -> None:
    # The banner and a commentary line quoting the old banner both carry it; move both.
    edit(r, "tokens.css", "v0.3: 2026-09-11)", "v0.3: 2026-09-12)", count=2)


def check_keys_section(path: Path, n: int) -> str:
    return check_keys.section(path.read_text(encoding="utf-8"), n)


MUTATIONS: list[tuple[str, str, Callable[[Path], None]]] = [
    ("HEADER", "consent header loses its **Version:** marker", m_header),
    ("CHANGELOG", "consent header and index bumped with no changelog entry", m_changelog),
    ("DATE", "lifeboat header and index dated 2030 while the changelog is not", m_date),
    ("HISTORY", "tap history parenthetical drops its newest version", m_history),
    ("SAMEDAY", "tokens.css `same day` moved across a date boundary", m_sameday),
    ("CHAIN", "DESIGN-SOURCES `supersedes` names the wrong predecessor", m_chain),
    ("INDEX", "index row for lifeboat bumped, header not", m_index),
    ("DECISION", "consent cites D-C40, which nothing states", m_decision),
    ("HISTORYONLY", "D-C6 stated only inside a changelog entry", m_historyonly),
    ("VETO", "lifeboat §21 offers D-L1–D-L3 while D-L4 exists", m_veto),
    ("CITE", "tap spec cites consent D-C40", m_cite),
    ("POINTER", "consent's Principles: pin at v1.5", m_pointer),
    ("REFERENCE", "lifeboat's Tokens: pin carries a version", m_reference),
    ("RECHECK", "consent prose cites the tap spec at v1.2 in pointer shape", m_recheck),
    ("KEY", "consent renders §13 `nope.key`", m_key),
    (
        "IDENTITY",
        "lifeboat shell.viewer string changed under the tap spec's identity claim",
        m_identity,
    ),
    ("EVENT", "a consent R2 event cell reads `(none)`", m_event),
    ("TABLE", "a consent R2 row loses a column", m_table),
    ("LITERAL", "consent §6 states #1D3FA8", m_literal),
    ("RECORD", "tokens.css v0.3's date moved", m_record),
]


def run_audit(root: Path) -> tuple[int, str]:
    proc = subprocess.run([sys.executable, str(AUDIT), str(root)], capture_output=True, text=True)
    return proc.returncode, proc.stdout + proc.stderr


def main(argv: list[str] | None = None) -> int:
    root = Path(argv[0] if argv else (sys.argv[1] if len(sys.argv) > 1 else "spec/design"))
    contracts = root.parent / "contracts"
    code, out = run_audit(root)
    if code != 0:
        print(out)
        print("selftest: the unmutated tree is not CLEAN — fix the tree before trusting mutants")
        return 1
    print(f"clean tree: {out.strip().splitlines()[-1]}")
    misses = 0
    for check, desc, fn in MUTATIONS:
        with tempfile.TemporaryDirectory() as td:
            tmp = Path(td) / "design"
            shutil.copytree(root, tmp)
            if contracts.is_dir():
                shutil.copytree(contracts, Path(td) / "contracts")
            fn(tmp)
            code, out = run_audit(tmp)
            fired = code != 0 and (f"FAIL {check}:" in out or f"WARN {check}:" in out)
            if check == "RECHECK":  # a warning: the run stays green, the id must still appear
                fired = f"WARN {check}:" in out
            print(f"{'ok  ' if fired else 'MISS'} {check:<11} {desc}")
            if not fired:
                misses += 1
                print("     audit output was:\n     " + out.strip().replace("\n", "\n     "))
    print("SELFTEST CLEAN" if not misses else f"SELFTEST: {misses} check(s) did not fire")
    return 1 if misses else 0


if __name__ == "__main__":
    sys.exit(main())
