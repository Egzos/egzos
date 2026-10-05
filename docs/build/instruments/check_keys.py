#!/usr/bin/env python3
# Copyright 2026 Ali Sasanian
# SPDX-License-Identifier: Apache-2.0
"""Copy keys: does every key a spec renders resolve to a row in an owning §13?

Every spec's §16 checks copy *by key, verbatim*, so a key must name exactly one string. Two
defect classes have shipped against that rule and both are checked here:

  KEY       a key referenced in §2–§4 (or anywhere as ``§13 `key` ``) with no §13 row — a builder
            reading it files a design-gap for a label the set already has under another name.
  IDENTITY  a §13 row claiming its string is *identical to* another spec's key while the two
            strings differ — the claim shipped three wordings under one key before it was checked.

What is NOT a copy key, and is excluded by rule rather than by list where a rule exists:
  * a filename (``consent.md``, ``tokens.css``, ``pipeline/check.py``);
  * an audit event, read from ``spec/contracts/events.md`` §1 when that file is present
    (fallback: the eighteen names drafted 2026-09-21);
  * a human-only act (``gate.confirm`` · ``approve.pending`` · ``yes.consume``);
  * a name a §14 table raises to the contract (its first column, and any dotted token on a §14
    line carrying ``[GAP→a1p]``) — ``tap.redeem_attempt``, ``window.closed`` and their kind;
  * a contract field path under ``details.`` · ``visibility.`` · ``trust.`` · ``provenance.`` ·
    ``node.`` · ``policy.`` · ``content.`` — the container's words, rendered as data, never as copy.

Blind spot, recorded: §13 rows are parsed for *every* dotted token they mention, so a §13 cell
that names a key in prose without defining it would make that key resolve. No row does this
today; the IDENTITY check is the one place prose mentions another key, and it is verified.

Usage: ``python3 check_keys.py [spec/design] [--contracts spec/contracts]``; also imported by
``audit_specs.py``, which reports its findings under the same ids.
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

ACTS = {"gate.confirm", "approve.pending", "yes.consume"}
FIELD_PREFIXES = (
    "details.",
    "visibility.",
    "trust.",
    "provenance.",
    "node.",
    "policy.",
    "content.",
)
FILE_SUFFIXES = (".md", ".css", ".py", ".json", ".svg", ".html", ".yml", ".yaml", ".txt")
EVENTS_FALLBACK = {
    "container.init",
    "node.create",
    "item.add",
    "blob.put",
    "context.fetch",
    "blob.pull",
    "item.move",
    "gate.pass.silent",
    "gate.propose",
    "approval.promote",
    "approval.execute",
    "approval.deny",
    "trust.quarantine",
    "step_up",
    "token.mint",
    "token.revoke",
    "item.tombstone",
    "blob.grant",
}
DOTTED = re.compile(r"`([a-z][a-z_]*(?:\.[a-z][a-z_]*)+)`")
EXPLICIT = re.compile(r"§13 `([a-z][a-z_]*(?:\.[a-z][a-z_]*)+)`")
INLINE_KEY = re.compile(r"(?:^|[ ·(]) ?([a-z][a-z_]*(?:\.[a-z][a-z_]*)+) `([^`]*)`")
IDENTICAL = re.compile(r"identical to `([^`]+)` §13 `([a-z][a-z_.]*)`")


def section(text: str, n: int) -> str:
    """Text of ``## n.`` (or ``## §n``) up to the next ``## `` heading; empty if absent."""
    m = re.search(rf"^## (?:§)?{n}\b.*$", text, re.MULTILINE)
    if not m:
        return ""
    rest = text[m.end() :]
    nxt = re.search(r"^## ", rest, re.MULTILINE)
    return rest[: nxt.start()] if nxt else rest


def table_rows(block: str) -> list[list[str]]:
    """Cells of every data row in a Markdown block (header and separator rows excluded)."""
    rows = []
    for line in block.splitlines():
        s = line.strip()
        if not s.startswith("|") or re.fullmatch(r"\|(?:\s*:?-+:?\s*\|)+", s):
            continue
        cells = [c.strip() for c in s[1:-1].split("|")] if s.endswith("|") else None
        if cells is None:
            cells = [c.strip() for c in s[1:].split("|")]
        rows.append(cells)
    return rows


def events_from_contract(contracts: Path | None) -> set[str]:
    path = (contracts / "events.md") if contracts else None
    if not path or not path.is_file():
        return set(EVENTS_FALLBACK)
    block = section(path.read_text(encoding="utf-8"), 1)
    names = {c[0].strip("` ") for c in table_rows(block) if c and c[0].startswith("`")}
    return names or set(EVENTS_FALLBACK)


def keys_of_13(text: str) -> dict[str, str]:
    """key → canonical string, from §13's rows (first column, plus inline ``· other.key `s` ``)."""
    out: dict[str, str] = {}
    for cells in table_rows(section(text, 13)):
        if len(cells) < 2 or cells[0] in ("key", ""):
            continue
        key = cells[0].strip("`")
        first = re.search(r"`([^`]*)`", cells[1])
        out[key] = first.group(1) if first else cells[1]
        for k, s in INLINE_KEY.findall(cells[1]):
            out.setdefault(k, s)
    return out


def raised_names(text: str) -> set[str]:
    """Names a §14 table raises to the contract: first column, and dotted tokens on GAP lines."""
    names: set[str] = set()
    sec = section(text, 14)
    for cells in table_rows(sec):
        if cells and cells[0].startswith("`"):
            names.update(DOTTED.findall(cells[0]))
    for line in sec.splitlines():
        if "[GAP→a1p]" in line or "[OPEN→a1p]" in line:
            names.update(DOTTED.findall(line))
    return names


def is_excluded(token: str, events: set[str], raised: set[str]) -> bool:
    return (
        token.endswith(FILE_SUFFIXES)
        or token in events
        or token in ACTS
        or token in raised
        or token.startswith(FIELD_PREFIXES)
    )


def check_file(path: Path, events: set[str]) -> list[tuple[str, str]]:
    """(check id, message) findings for one spec; empty when clean."""
    text = path.read_text(encoding="utf-8")
    keys = keys_of_13(text)
    if not keys:
        return []  # no §13 — not a screen spec; nothing to resolve against
    raised = raised_names(text)
    found: list[tuple[str, str]] = []
    rendered = "".join(section(text, n) for n in (2, 3, 4))
    for tok in sorted(set(DOTTED.findall(rendered))):
        if tok not in keys and not is_excluded(tok, events, raised):
            found.append(("KEY", f"{path.name}: `{tok}` is rendered in §2–§4 and has no §13 row"))
    for tok in sorted(set(EXPLICIT.findall(text))):
        if tok not in keys:
            found.append(("KEY", f"{path.name}: `§13 `{tok}`` is cited and has no §13 row"))
    return found


def check_identity(paths: list[Path]) -> list[tuple[str, str]]:
    """Verify every ``identical to `other.md` §13 `key` `` claim across the set."""
    by_name = {p.name: keys_of_13(p.read_text(encoding="utf-8")) for p in paths}
    found: list[tuple[str, str]] = []
    for p in paths:
        text = p.read_text(encoding="utf-8")
        for cells in table_rows(section(text, 13)):
            if len(cells) < 2:
                continue
            for other, key in IDENTICAL.findall(cells[1]):
                mine = by_name[p.name].get(cells[0].strip("`"))
                theirs = by_name.get(Path(other).name, {}).get(key)
                if theirs is None:
                    found.append(
                        (
                            "IDENTITY",
                            f"{p.name}: claims identity with `{other}` §13 "
                            f"`{key}`, which that file does not define",
                        )
                    )
                elif mine != theirs:
                    found.append(
                        (
                            "IDENTITY",
                            f"{p.name} `{cells[0]}` claims identity with "
                            f"`{other}` `{key}` but the strings differ:\n"
                            f"    {mine!r}\n    {theirs!r}",
                        )
                    )
    return found


def spec_files(root: Path) -> list[Path]:
    files = sorted(p for p in root.glob("*.md") if p.name != "README.md")
    brand = root / "brand" / "BRAND.md"
    if brand.is_file():
        files.append(brand)
    return files


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("root", nargs="?", default="spec/design", type=Path)
    ap.add_argument(
        "--contracts", type=Path, default=None, help="spec/contracts (default: <root>/../contracts)"
    )
    args = ap.parse_args(argv)
    contracts = args.contracts or (args.root.parent / "contracts")
    events = events_from_contract(contracts)
    files = spec_files(args.root)
    findings: list[tuple[str, str]] = []
    for p in files:
        findings.extend(check_file(p, events))
    findings.extend(check_identity(files))
    for check, msg in findings:
        print(f"FAIL {check}: {msg}")
    n_keys = sum(len(keys_of_13(p.read_text(encoding="utf-8"))) for p in files)
    if n_keys < 50:
        print(
            f"FAIL GUARD: only {n_keys} §13 keys found across {len(files)} files — "
            "the extractor is not seeing the tables it claims to check"
        )
        return 1
    print(
        "CLEAN" if not findings else f"{len(findings)} FAILURE(S)",
        f"— {n_keys} keys across {len(files)} files",
    )
    return 1 if findings else 0


if __name__ == "__main__":
    sys.exit(main())
