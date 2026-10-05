#!/usr/bin/env python3
# Copyright 2026 Ali Sasanian
# SPDX-License-Identifier: Apache-2.0
"""A2's pre-push audit of spec/design, read as text. Every expectation is derived from the tree.

There is no registry of versions in this file. The index table in ``spec/design/README.md`` is
the registry, each file's own newest changelog entry is its own version claim, and the check is
that the two agree with the header between them. The original of this instrument carried a
registry imported from a sibling script; the two copies of one fact drifted within an hour.

Checks, by id (the selftest mutates a copy of the tree once per id and asserts each fires):

  HEADER      a spec header, Status line or tokens.css banner that does not parse
  CHANGELOG   header version ≠ the newest ``Changelog vA → vB (date)``; entries not contiguous;
              a changelog that does not run forward in time
  DATE        header date ≠ the newest changelog's date (a date is a claim about the world)
  HISTORY     the header's history parenthetical does not list exactly the changelog's versions,
              newest → oldest, each resolving to a date that agrees with its entry
  SAMEDAY     ``same day`` anywhere but the run adjacent to the header date — it is a pointer at
              the header date, and across a boundary it re-dates every version it covers
  CHAIN       a Status chain (DESIGN-PRINCIPLES, DESIGN-SOURCES) that skips a version, runs
              backwards, or whose ``supersedes vX`` names the wrong predecessor
  INDEX       an index row whose version or date ≠ the file's header; a spec with no row; a row
              with no file
  DECISION    a decision id of the file's own series referenced in binding text but never stated
              in the decision form (``**D-Xn · ``) outside the changelog region
  HISTORYONLY a decision stated in the decision form only inside the changelog region —
              history is record, and no binding-text audit reads it
  VETO        the §21 veto window does not offer the whole series (``D-X1 … D-Xn`` must reach the
              highest id defined or referenced); an unlisted decision is an unoffered veto
  CITE        a decision of another file's series cited here and not defined there
  POINTER     the ``Principles:`` pin ≠ DESIGN-PRINCIPLES.md's version (the one versioned header
              pin left in this repository)
  REFERENCE   a ``Tokens:`` / ``Provenance:`` / ``Siblings:`` pin with a version directly after
              its filename — these are references by the Version rule and carry none
  RECHECK     (warning) a pointer-shaped citation — ``file.md vX`` or ``the tap spec vX`` — in
              binding prose at a version that is not the file's current one. The audit cannot
              tell a record written in pointer shape from a stale pointer; a person re-checks the
              claim, or rewrites the record claim-first so no sweep can match it
  KEY         a rendered copy key with no §13 row (see check_keys.py)
  IDENTITY    an ``identical to`` claim between two §13 strings that differ (see check_keys.py)
  EVENT       a §4 event cell that is neither ``—``, a taxonomy name, nor a raised ``[GAP→a1p]``
              / ``[OPEN→…]`` — the third value D-T8 was raised to abolish
  TABLE       a §4 row whose cell count ≠ its header's (a cell containing ``|``, or a lost column)
  LITERAL     a hex colour, ``font-weight:`` or size / weight pair in spec prose outside the token
              file, the brand file and the provenance register
  RECORD      a frozen record no longer present verbatim (the dates a sweep has eaten before)
  SERIES      (info) decision series cited here whose owner is not in this tree — the flagship's;
              verified only with the closed tree present
  GUARD       the audit found too little to be looking at the right directory

The changelog REGION is history: from the first ``**Changelog`` line to the first following line
that opens the decisions block, a ``**Why`` paragraph, a ``---`` rule or a ``## `` heading.
Entries span paragraphs, so a line-prefix test is not enough — that is how a continuation
paragraph once passed for binding prose. BRAND.md's region is its ``§23 Changelog``.

What this audit does not see, recorded so nobody mistakes its green for coverage:
  * rendered pixels — overflow, hit targets, contrast, motion: the render instruments' job;
  * a literal duration in prose (``10 s``, ``700 ms``) — D-T2 makes interaction timeouts spec
    constants on purpose, and the gloss beside ``--egz-t-hold`` is deliberate; not checked;
  * whether a record written in pointer shape is a record — it can only list it (RECHECK); and a
    bare-word citation (``lifeboat v1.4``, ``consent v1.5``) is not matched at all, because the
    same words name product versions (``the lifeboat v0.1``);
  * tokens.css's commentary, which is history throughout and is excluded from RECHECK;
  * BRAND.md offers its decisions (S1–S9) in a header table, not a §21 range; the table is the
    veto window there and the range rule is not applied to it;
  * the flagship's decision series (S, P, R, O, G, Q, M, U) — cited from here, defined in
    ``Egzos/egzos-platform``; counted, not verified, without that tree.

Usage: ``python3 docs/build/instruments/audit_specs.py [spec/design] [--contracts spec/contracts]``
Exit 1 on any FAIL. Warnings and info never fail the run.
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

import check_keys

DATE = r"\d{4}-\d{2}-\d{2}"
VER = r"\d+\.\d+"
SCREEN_HEADER = re.compile(
    rf"^\*\*Spec:\*\* `([^`]+)` · \*\*Version:\*\* ({VER}) · \*\*Date:\*\* ({DATE}) \((.*)\)\s*$"
)
STATUS_BRAND = re.compile(rf"^\*\*Status:\*\* v({VER}) · ({DATE}) \((.*?)\)", re.MULTILINE)
STATUS_CHAIN = re.compile(rf"v({VER}) \(({DATE})(?:; (supersedes v({VER})|superseded))?\)")
TOKENS_HEADER = re.compile(
    rf"^ \* egzos design tokens · v({VER}) · ({DATE}) \((.*)\)\s*$", re.MULTILINE
)
CHANGELOG = re.compile(rf"^\*\*Changelog v({VER}) → v({VER})(?: \(({DATE})\))?\.\*\*", re.MULTILINE)
BRAND_LOG = re.compile(rf"^- \*\*v({VER}) · ({DATE})\*\*", re.MULTILINE)
INDEX_ROW = re.compile(rf"^\| `([^`]+)` \| ({VER}) \| ({DATE}) \|", re.MULTILINE)
DECISION_DEF = re.compile(r"^(?:- )?\*\*D-([A-Z]+)(\d+)([a-z]?) · ")
DECISION_HEAD = re.compile(r"\*\*D-([A-Z]+)(\d+)([a-z]?) · ")
DECISION_REF = re.compile(r"\bD-([A-Z]+)(\d+)([a-z]?)\b")
VETO = re.compile(r"veto window on \*{0,2}D-([A-Z]+)1\*{0,2}\s*(?:…|–|-)\s*\*{0,2}D-\1(\d+)")
PRINCIPLES_PIN = re.compile(rf"\*\*Principles:\*\* `DESIGN-PRINCIPLES\.md` v({VER})")
REFERENCE_PIN = re.compile(
    rf"\*\*(Tokens|Provenance|Siblings|Public siblings):\*\* `[^`]+` \*{{0,2}}v{VER}\b"
)
CITE_FILE = re.compile(rf"`([A-Za-z/.-]+\.(?:md|css))` \*{{0,2}}v({VER})\b")
CITE_WORD = re.compile(rf"\b(?:the )?(tap spec|lifeboat spec|consent spec)\*{{0,2}} v({VER})\b")
WORD_TO_FILE = {
    "tap spec": "step-up-tap-and-pending-approval.md",
    "lifeboat spec": "lifeboat.md",
    "consent spec": "consent.md",
}
REGION_END = re.compile(r"^(?:\*\*Decisions|\*\*Why|---$|## )")
HEX = re.compile(r"(?<![\w#])#(?:[0-9a-fA-F]{6}|[0-9a-fA-F]{3})\b")
WEIGHT = re.compile(r"font-weight:\s*\d{3}|\b\d{2} / [4-9]00\b")
EVENT_OK = ("[GAP→a1p]", "[OPEN→a1p]", "[OPEN→0.3]")
NO_LITERAL = {"tokens.css", "BRAND.md", "DESIGN-SOURCES.md"}
NO_RECHECK = {"tokens.css", "DESIGN-SOURCES.md"}

# Frozen records: facts a sweep has eaten before. Asserted verbatim; a sweep that moves one is
# the sweep being wrong. Each entry names the file and the exact text that must be present.
RECORDS = (
    (
        "step-up-tap-and-pending-approval.md",
        "v1.2: 2026-09-21 · v1.1: 2026-09-13 · v1.0: 2026-09-11",
    ),
    ("lifeboat.md", "v1.0: 2026-09-21"),
    ("consent.md", "v1.0: 2026-09-21"),
    ("tokens.css", "v0.3: 2026-09-11"),
    ("DESIGN-PRINCIPLES.md", "v1.1 (2026-09-13)"),
    ("DESIGN-SOURCES.md", "v1.1 (2026-09-13; superseded)"),
    ("DESIGN-SOURCES.md", "v1.0 (2026-09-11; superseded)"),
    ("DESIGN-SOURCES.md", "#89 (v1.1 wrote #99 — corrected)"),
    ("BRAND.md", "v1.0: 2026-09-22"),
)


class Audit:
    def __init__(self, root: Path, contracts: Path) -> None:
        self.root = root
        self.contracts = contracts
        self.findings: list[tuple[str, str, str]] = []  # (level, check, message)
        self.current: dict[str, tuple[str, str]] = {}  # file name → (version, date)
        self.owners: dict[str, str] = {}  # decision series → file name
        self.texts: dict[str, str] = {}
        self.history_lines: dict[str, set[int]] = {}  # file name → 0-based changelog lines

    def fail(self, check: str, msg: str) -> None:
        self.findings.append(("FAIL", check, msg))

    def warn(self, check: str, msg: str) -> None:
        self.findings.append(("WARN", check, msg))

    def info(self, check: str, msg: str) -> None:
        self.findings.append(("INFO", check, msg))

    # ── discovery ────────────────────────────────────────────────────────────────────────────
    def files(self) -> list[Path]:
        out = sorted(p for p in self.root.glob("*.md") if p.name != "README.md")
        out += sorted(self.root.glob("*.css"))
        brand = self.root / "brand" / "BRAND.md"
        if brand.is_file():
            out.append(brand)
        return out

    def index_rows(self) -> dict[str, tuple[str, str]]:
        text = (self.root / "README.md").read_text(encoding="utf-8")
        return {m.group(1): (m.group(2), m.group(3)) for m in INDEX_ROW.finditer(text)}

    def mark_history(self, name: str, text: str) -> None:
        """Record which lines are the changelog region (history, never binding text)."""
        lines = text.splitlines()
        marked: set[int] = set()
        if name == "BRAND.md":
            start = next((i for i, ln in enumerate(lines) if ln.startswith("## §23")), None)
            if start is not None:
                marked = set(range(start, len(lines)))
        else:
            start = next((i for i, ln in enumerate(lines) if ln.startswith("**Changelog")), None)
            if start is not None:
                end = next(
                    (i for i in range(start + 1, len(lines)) if REGION_END.match(lines[i])),
                    len(lines),
                )
                marked = set(range(start, end))
        self.history_lines[name] = marked

    def binding_lines(self, name: str) -> list[str]:
        hist = self.history_lines.get(name, set())
        return [ln for i, ln in enumerate(self.texts[name].splitlines()) if i not in hist]

    def history_only_lines(self, name: str) -> list[str]:
        hist = self.history_lines.get(name, set())
        return [ln for i, ln in enumerate(self.texts[name].splitlines()) if i in hist]

    # ── headers and histories ────────────────────────────────────────────────────────────────
    def read_header(self, path: Path, text: str) -> None:
        """Set self.current[path.name] from the file's own header; run the history checks."""
        name = path.name
        lines = text.splitlines()
        if name == "tokens.css":
            m = TOKENS_HEADER.search(text)
            if not m:
                return self.fail("HEADER", f"{name}: banner line not parseable")
            self.current[name] = (m.group(1), m.group(2))
            # The banner carries the history; the changelog is prose commentary. Only the
            # history's own rules apply: dated runs, `same day` scoped, newest first.
            self.history_items(name, m.group(3), m.group(2), None)
            return None
        if name == "BRAND.md":
            m = STATUS_BRAND.search(text)
            if not m:
                return self.fail("HEADER", f"{name}: Status line not parseable")
            self.current[name] = (m.group(1), m.group(2))
            log = BRAND_LOG.findall(text)
            if not log:
                return self.fail("CHANGELOG", f"{name}: §23 has no `- **vX · date**` entries")
            if log[0] != (m.group(1), m.group(2)):
                self.fail(
                    "CHANGELOG",
                    f"{name}: Status says v{m.group(1)} · {m.group(2)} but the newest §23 "
                    f"entry is v{log[0][0]} · {log[0][1]}",
                )
            self.history_items(name, m.group(3), m.group(2), [(v, d) for v, d in log[1:]])
            return None
        if name in ("DESIGN-PRINCIPLES.md", "DESIGN-SOURCES.md"):
            status = next((ln for ln in lines if ln.startswith("**Status:**")), "")
            chain = STATUS_CHAIN.findall(status)
            if not chain:
                return self.fail("HEADER", f"{name}: Status chain not parseable")
            self.current[name] = (chain[0][0], chain[0][1])
            self.status_chain(name, chain)
            return None
        head = lines[2] if len(lines) > 2 else ""
        m = SCREEN_HEADER.match(head)
        if not m:
            return self.fail(
                "HEADER",
                f"{name}: line 3 is not `**Spec:** … **Version:** … **Date:** … (history)`",
            )
        if m.group(1) != f"spec/design/{name}":
            self.fail("HEADER", f"{name}: header names `{m.group(1)}`")
        ver, date, hist = m.group(2), m.group(3), m.group(4)
        self.current[name] = (ver, date)
        entries = CHANGELOG.findall(text)  # newest first, as written
        if not entries:
            return self.fail("CHANGELOG", f"{name}: no changelog entries")
        if entries[0][1] != ver:
            self.fail(
                "CHANGELOG",
                f"{name}: header is v{ver}, newest changelog is "
                f"v{entries[0][0]} → v{entries[0][1]}",
            )
        if entries[0][2] and entries[0][2] != date:
            self.fail(
                "DATE", f"{name}: header dated {date}, newest changelog dated {entries[0][2]}"
            )
        for i in range(len(entries) - 1):
            a, b, d = entries[i]
            na, nb, nd = entries[i + 1]
            if a != nb:
                self.fail(
                    "CHANGELOG",
                    f"{name}: entries v{a} → v{b} and v{na} → v{nb} are not contiguous",
                )
            if d and nd and d < nd:
                self.fail("CHANGELOG", f"{name}: changelog runs backwards at v{b} ({d} after {nd})")
        expected: list[tuple[str, str | None]] = [(b, d or None) for _a, b, d in entries[1:]]
        expected.append((entries[-1][0], None))  # the oldest version has no entry of its own
        self.history_items(name, hist, date, expected)
        return None

    def history_items(
        self,
        name: str,
        hist: str,
        header_date: str,
        expected: list[tuple[str, str | None]] | None,
    ) -> None:
        """Parse ``v1.3 · v1.2: 2026-09-22 · v1.1 · v1.0: 2026-09-21`` and check it."""
        versions: list[str] = []
        dated: dict[str, str] = {}
        run: list[str] = []
        first_run = True
        for item in (h.strip() for h in hist.split("·")):
            m = re.fullmatch(rf"v({VER})(?:: ({DATE}|same day))?", item)
            if not m:
                return self.fail("HISTORY", f"{name}: history item {item!r} not parseable")
            versions.append(m.group(1))
            run.append(m.group(1))
            if m.group(2):
                d = m.group(2)
                if d == "same day":
                    if not first_run:
                        self.fail(
                            "SAMEDAY",
                            f"{name}: `same day` on v{m.group(1)} is not adjacent to the header "
                            f"date — it points at the header and re-dates the run when the "
                            f"header moves",
                        )
                    d = header_date
                for v in run:
                    dated[v] = d
                run = []
                first_run = False
        if run:
            self.fail("HISTORY", f"{name}: versions {run} end the history with no date")
        for i in range(len(versions) - 1):
            if dated.get(versions[i], "") < dated.get(versions[i + 1], ""):
                self.fail("HISTORY", f"{name}: history runs backwards at v{versions[i]}")
        if expected is None:
            return None
        if versions != [v for v, _ in expected]:
            self.fail(
                "HISTORY",
                f"{name}: history lists {versions}; the changelog derives "
                f"{[v for v, _ in expected]}",
            )
        for v, d in expected:
            if d and v in dated and dated[v] != d:
                self.fail(
                    "HISTORY", f"{name}: history dates v{v} {dated[v]}; its changelog says {d}"
                )
        return None

    def status_chain(self, name: str, chain: list[tuple[str, str, str, str]]) -> None:
        for i in range(len(chain) - 1):
            v, d, _rel, sup = chain[i]
            nv, nd = chain[i + 1][0], chain[i + 1][1]
            if sup and sup != nv:
                self.fail(
                    "CHAIN", f"{name}: v{v} says it supersedes v{sup}; the next entry is v{nv}"
                )
            maj, mi = (int(x) for x in v.split("."))
            nmaj, nmi = (int(x) for x in nv.split("."))
            if not ((maj == nmaj and mi == nmi + 1) or (maj == nmaj + 1 and mi == 0)):
                self.fail("CHAIN", f"{name}: v{v} is followed by v{nv} — a version is skipped")
            if d < nd:
                self.fail("CHAIN", f"{name}: v{v} ({d}) is dated before v{nv} ({nd})")
        versions = [c[0] for c in chain]
        if len(set(versions)) != len(versions):
            self.fail("CHAIN", f"{name}: a version appears twice in the Status chain")

    # ── index ────────────────────────────────────────────────────────────────────────────────
    def check_index(self) -> None:
        rows = self.index_rows()
        if not rows:
            return self.fail("INDEX", "README.md: no index rows parsed")
        for key, (ver, date) in rows.items():
            if not (self.root / key).is_file():
                self.fail("INDEX", f"README.md: row `{key}` names a file that does not exist")
                continue
            name = Path(key).name
            if name in self.current and self.current[name] != (ver, date):
                cv, cd = self.current[name]
                self.fail(
                    "INDEX",
                    f"README.md: row `{key}` says {ver} · {date}; the header says {cv} · {cd}",
                )
        for p in self.files():
            key = p.relative_to(self.root).as_posix()
            if key not in rows:
                self.fail("INDEX", f"README.md: `{key}` has no index row")
        return None

    # ── decisions ────────────────────────────────────────────────────────────────────────────
    def check_decisions(self) -> None:
        defined: dict[str, set[str]] = {}
        for name, text in self.texts.items():
            for m in VETO.finditer(text):
                self.owners[m.group(1)] = name
            ids = set()
            for ln in self.binding_lines(name):
                d = DECISION_DEF.match(ln)
                if d:
                    ids.add(f"{d.group(1)}{d.group(2)}{d.group(3)}")
            defined[name] = ids
        unowned: dict[str, set[str]] = {}
        for name in self.texts:
            if name == "DESIGN-SOURCES.md":
                continue  # a register of records; it cites decisions by the version that took them
            binding = "\n".join(self.binding_lines(name))
            for s, n, suf in set(DECISION_REF.findall(binding)):
                ident = f"{s}{n}{suf}"
                owner = self.owners.get(s)
                if owner is None:
                    unowned.setdefault(s, set()).add(ident)
                elif ident not in defined[owner]:
                    check = "DECISION" if owner == name else "CITE"
                    self.fail(
                        check,
                        f"{name}: D-{ident} is referenced; {owner} never states it in the "
                        f"decision form outside its changelog",
                    )
            history = "\n".join(self.history_only_lines(name))
            for s, n, suf in set(DECISION_HEAD.findall(history)):
                ident = f"{s}{n}{suf}"
                owner = self.owners.get(s)
                if owner and ident not in defined[owner]:
                    self.fail(
                        "HISTORYONLY", f"{name}: D-{ident} is stated only inside the changelog"
                    )
        for s, owner in self.owners.items():
            text = self.texts[owner]
            top = max(int(m.group(2)) for m in VETO.finditer(text) if m.group(1) == s)
            nums = {
                int(re.match(r"\d+", i[len(s) :]).group())  # type: ignore[union-attr]
                for i in defined[owner]
                if i.startswith(s) and i[len(s)].isdigit()
            }
            binding = "\n".join(self.binding_lines(owner))
            nums |= {int(n) for ss, n, _ in DECISION_REF.findall(binding) if ss == s}
            if nums and max(nums) != top:
                self.fail(
                    "VETO",
                    f"{owner}: §21 offers D-{s}1 … D-{s}{top}; the file defines or references "
                    f"up to D-{s}{max(nums)}",
                )
        for s, ids in sorted(unowned.items()):
            self.info(
                "SERIES",
                f"D-{s} ({len(ids)} id(s) cited) is owned outside this tree — verified only "
                f"with Egzos/egzos-platform present",
            )

    # ── pointers ─────────────────────────────────────────────────────────────────────────────
    def check_pointers(self, name: str, text: str) -> None:
        principles = self.current.get("DESIGN-PRINCIPLES.md", ("?", ""))[0]
        for m in PRINCIPLES_PIN.finditer(text):
            if m.group(1) != principles:
                self.fail(
                    "POINTER",
                    f"{name}: Principles: pin says v{m.group(1)}; DESIGN-PRINCIPLES.md is "
                    f"v{principles}",
                )
        header = "\n".join(text.splitlines()[:8])
        for m in REFERENCE_PIN.finditer(header):
            self.fail("REFERENCE", f"{name}: `{m.group(1)}:` is a reference and carries a version")
        if name in NO_RECHECK:
            return
        hist = self.history_lines.get(name, set())
        for i, ln in enumerate(text.splitlines()):
            if i in hist or i < 8 or DECISION_DEF.match(ln):
                continue
            cites = [(Path(f).name, v) for f, v in CITE_FILE.findall(ln)]
            cites += [(WORD_TO_FILE[w], v) for w, v in CITE_WORD.findall(ln)]
            for target, v in cites:
                cur = self.current.get(target)
                if cur and cur[0] != v:
                    self.warn(
                        "RECHECK",
                        f"{name}:{i + 1} cites {target} v{v} in pointer shape; the file is "
                        f"v{cur[0]} — re-check the claim or write it claim-first",
                    )

    # ── §4 event column ──────────────────────────────────────────────────────────────────────
    def check_events(self, name: str, text: str, events: set[str]) -> None:
        sec4 = check_keys.section(text, 4)
        if not sec4:
            return
        header: list[str] | None = None
        region = ""
        for ln in sec4.splitlines():
            s = ln.strip()
            if s.startswith("### "):
                region, header = s[4:].split(" · ")[0], None
                continue
            if not s.startswith("|") or re.fullmatch(r"\|(?:\s*:?-+:?\s*\|)+", s):
                continue
            cells = [c.strip() for c in s[1:-1].split("|")]
            if header is None:
                header = cells
                continue
            if len(cells) != len(header):
                self.fail(
                    "TABLE",
                    f"{name} {region}: a row has {len(cells)} cells, its header {len(header)} — "
                    f"`{cells[0][:50]}`",
                )
                continue
            if "event" not in header:
                continue
            cell = cells[header.index("event")]
            ok = (
                cell.startswith(("—", "**—**", "`—`"))
                or any(f"`{e}`" in cell for e in events)
                or any(k in cell for k in EVENT_OK)
            )
            if not ok:
                self.fail(
                    "EVENT",
                    f"{name} {region} `{cells[0][:40]}`: event cell `{cell[:60]}` is neither — "
                    f"nor a taxonomy name nor a raised gap",
                )

    # ── literals and records ─────────────────────────────────────────────────────────────────
    def check_literals(self, name: str, text: str) -> None:
        if name in NO_LITERAL:
            return
        hist = self.history_lines.get(name, set())
        for i, ln in enumerate(text.splitlines()):
            if i in hist or "declared literal" in ln:
                continue
            hexes = [h for h in HEX.findall(ln) if not re.fullmatch(r"#\d+", h)]
            if hexes:
                self.fail("LITERAL", f"{name}:{i + 1} colour literal {hexes[:3]} in prose")
            w = WEIGHT.search(ln)
            if w:
                self.fail("LITERAL", f"{name}:{i + 1} weight literal `{w.group()}` in prose")

    def check_records(self) -> None:
        for name, literal in RECORDS:
            text = self.texts.get(name)
            if text is not None and literal not in text:
                self.fail("RECORD", f"{name}: frozen record {literal!r} is no longer present")

    # ── run ──────────────────────────────────────────────────────────────────────────────────
    def run(self) -> int:
        files = self.files()
        if len(files) < 4:
            self.fail("GUARD", f"only {len(files)} spec files under {self.root} — wrong directory?")
        for p in files:
            self.texts[p.name] = p.read_text(encoding="utf-8")
            self.mark_history(p.name, self.texts[p.name])
        for p in files:
            self.read_header(p, self.texts[p.name])
        self.check_index()
        self.check_decisions()
        events = check_keys.events_from_contract(self.contracts)
        for p in files:
            text = self.texts[p.name]
            self.check_pointers(p.name, text)
            self.check_events(p.name, text, events)
            self.check_literals(p.name, text)
        self.check_records()
        key_files = [p for p in files if p.suffix == ".md"]
        for p in key_files:
            for check, msg in check_keys.check_file(p, events):
                self.fail(check, msg)
        for check, msg in check_keys.check_identity(key_files):
            self.fail(check, msg)
        order = {"FAIL": 0, "WARN": 1, "INFO": 2}
        for level, check, msg in sorted(self.findings, key=lambda f: (order[f[0]], f[1])):
            print(f"{level} {check}: {msg}")
        fails = sum(1 for f in self.findings if f[0] == "FAIL")
        warns = sum(1 for f in self.findings if f[0] == "WARN")
        summary = "CLEAN" if not fails else f"{fails} FAILURE(S)"
        print(f"{summary} — {len(files)} files · {warns} warning(s) to re-check by hand")
        return 1 if fails else 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("root", nargs="?", default="spec/design", type=Path)
    ap.add_argument(
        "--contracts", type=Path, default=None, help="spec/contracts (default: <root>/../contracts)"
    )
    args = ap.parse_args(argv)
    contracts = args.contracts or (args.root.parent / "contracts")
    return Audit(args.root, contracts).run()


if __name__ == "__main__":
    sys.exit(main())
