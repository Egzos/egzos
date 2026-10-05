# docs/build/instruments/

A2's verification instruments for `spec/design/**`. They are not governance text; they are the
tooling that reads it. A spec is not finished until it has been checked by these and, once the
render half lands, rendered and measured. Neither replaces a reviewer: they catch the classes a
reviewer reading prose cannot, and a1r-reviewer and a2-conformance catch the rest.

**Why they live here (decision (a), the Chief, 2026-09-28).** The originals ran in A2's studio
sandbox and were never in a repository. On 2026-09-24 that sandbox came up empty and every
instrument, every state mock and the local spec mirror were gone. `spec/design/README.md`
described instruments nobody could run. They are public now because the specs they check are
public, because the index already cites them, and because a reviewer who can run the audit can
verify a PR's claim that it ran. *Rejected:* a private studio repository (unverifiable from
the public tree; no rulesets, no reviewers) and Hyperagent artifacts (unversioned against the
specs they check). *Cost:* `docs/**` is a1p-planner's and haiku-mechanic's path, so every
change here is a Chief commit on a `chief/` branch — A2 is not a CI identity.

## What is here

| file | what it does | run |
|---|---|---|
| `audit_specs.py` | The pre-push **text audit**. Every expectation is derived from the tree: the index table is the registry, each file's newest changelog entry is its version claim. Twenty check ids, listed in its docstring with what each cannot see. | `python3 docs/build/instruments/audit_specs.py spec/design` |
| `check_keys.py` | **Copy keys.** Every key a spec renders in §2–§4 (or cites as ``§13 `key` ``) resolves to a §13 row; every *identical to* claim between two §13 strings is verified. Imported by the audit; runnable alone to see the key table. | `python3 docs/build/instruments/check_keys.py spec/design` |
| `check_sync.py` | **Local tree vs a branch**, by git blob SHA — never by file size (a `2.6 → 2.7` edit is the same byte count) and never by the cached `/contents` listing (it lags a push and invents drift). | `python3 docs/build/instruments/check_sync.py --branch <branch> spec/design` |
| `selftest.py` | **Makes every audit check fail on purpose.** Copies `spec/design` to a temporary directory, applies one mutation per check id, and asserts the id fires. Asserts the unmutated tree is CLEAN first. | `python3 docs/build/instruments/selftest.py spec/design` |

All four are stdlib-only Python, run from the repository root, and exit non-zero on a finding.
`ruff check .` lints them like any other file in the tree; nothing under `docs/` is collected by
`pytest`.

## The rule that governs them

**A check that cannot fail is not a check.** Every check is made to fail on purpose before its
green is believed, and `selftest.py` is where that is kept true rather than promised: adding a
check id to the audit without a mutation that trips it fails the selftest. The rule came from
two real failures recorded in the index — a guard written so it could never match, and a first
width audit that returned 357 findings by measuring surfaces at widths no spec puts them at.
A check that fires on questions nobody asked looks exactly like coverage.

Two corollaries the originals learned the hard way and this rebuild keeps:

* **Assert presence, never absence.** A self-check that asserts the old text is *gone* passes
  on a file that was never written. Every check here asserts what *must be there*.
* **Every scripted edit asserts its anchor.** A substitution that silently matches nothing
  shipped the same contradiction twice. `selftest.py`'s mutations abort if an anchor does not
  occur exactly the expected number of times.

## What the audit sees — and what it does not

The check ids, one line each (the docstring carries the full statement):

`HEADER` · `CHANGELOG` · `DATE` · `HISTORY` · `SAMEDAY` · `CHAIN` — the version a file claims,
the entry that claims it, the parenthetical that lists what came before, and whether the dates
run forward. `INDEX` — the index table agrees with every header, and nothing is missing on
either side. `DECISION` · `HISTORYONLY` · `VETO` · `CITE` · `SERIES` — every decision id cited is
stated in the decision form, outside the changelog, in the file that owns its series, and the
owner's §21 offers the whole series (an unlisted decision is an unoffered veto). `POINTER` ·
`REFERENCE` · `RECHECK` — the one versioned header pin left in this repository agrees with its
target; the reference-class pins carry no version; and a pointer-shaped citation at a stale
version is listed for a human. `KEY` · `IDENTITY` — copy keys. `EVENT` · `TABLE` — a §4 event
cell is `—`, a taxonomy name from `spec/contracts/events.md` §1, or a raised gap, and never the
third value D-T8 abolished; a row has as many cells as its header. `LITERAL` — no hex colour or
weight in spec prose. `RECORD` — nine frozen records asserted verbatim, because a sweep has eaten
each of them before.

**Not seen, so that green is not mistaken for coverage:**

* **Rendered pixels.** Overflow, hit targets under 44 px, contrast, motion. That is the render
  half — `width_audit.py`, `contrast_audit.py`, `token_audit.py`, `motion_audit.py` and the state
  mocks they measure — which was lost with the sandbox and is rebuilt in a second commit. The
  figures the index quotes (448 and 848 measurements; 12 153 text nodes) were produced by the
  lost instruments and stand as records until the rebuilt ones re-measure.
* **Literal durations in prose.** `10 s`, `15 s`, `700 ms`: D-T2 makes interaction timeouts spec
  constants deliberately, and the gloss beside `--egz-t-hold` is deliberate too. Not checked.
* **Whether a pointer-shaped citation is a record.** `` `file.md` v1.4 `` is the shape of a
  pointer *and* of a record written carelessly; the audit cannot tell them apart and only lists
  the stale ones (`RECHECK`, a warning). The Version rule's remedy is to write records
  claim-first. Bare-word forms (`lifeboat v1.4`) are not matched at all — the same words name
  product versions.
* **tokens.css's commentary.** History throughout; excluded from `RECHECK` by name, as
  `DESIGN-SOURCES.md` is from every sweep.
* **BRAND.md's veto form.** It offers S1–S9 in a header table, not a §21 range; the table is the
  veto window there and the range rule is not applied to it.
* **The flagship's decision series** (D-S, D-P, D-R, D-O, D-G, D-Q, D-M, D-U) — cited from the
  public specs, defined in `Egzos/egzos-platform`. Counted here (`SERIES`), verified only when
  the closed tree is present. The platform half is a third commit.
* **§13 over-collection.** `check_keys.py` reads every dotted token a §13 row mentions as a key,
  so a row that named a key in prose without defining it would make that key resolve. No row
  does this today; the one place prose names another key is the identity claim, and that is
  verified.

## The rebuild, honestly

The originals cannot be restored byte for byte. This set was rebuilt on 2026-10-02 from three
sources: `spec/design/README.md`'s description of what the instruments did; each spec's
changelog, which records what every check caught and the blind spot it closed; and A2's working
notes. Where the original and the rebuild are known to differ, the rebuild is the stricter one:

* the original audit imported a version registry from a sibling script and the two copies drifted
  within an hour; this one has no registry — the index table is the registry;
* the original treated a changelog *line* as history; this one treats the changelog *region*,
  because entries span paragraphs and a continuation paragraph once passed for binding prose;
* the original's history check compared version numbers; this one compares dates too, because
  thirty-four wrong dates across thirteen files once passed while every number agreed.

Blind spots found after this writing are recorded in the audit's docstring, as the originals'
were, because each one was found by shipping the defect it existed to catch.

## CI

Nothing here is wired into a required check. Wiring it is a `.github/workflows/**` change, which
only the Chief commits, and it must follow the rule PR #38 set for every control input: **the
instrument is resolved from the base ref, never from the tree under review** — a PR that could
edit the audit it is judged by is not audited. The recommended shape is one step in
`a2-conformance.yml`, after `control-inputs-from-base`, running
`git show "origin/${BASE_REF}:docs/build/instruments/audit_specs.py"` (and `check_keys.py`
beside it) against the PR's `spec/design`. It is offered as a patch on a governance issue once
this directory is on `main`.

## Ownership

A2 owns the content; the Chief commits it. Builders do not edit instruments — a builder that
believes a check is wrong files a `design-gap` issue quoting the check id and the line, exactly
as for a spec. a2-conformance may cite a check by id in a review comment.
