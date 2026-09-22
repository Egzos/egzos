# spec/design/

Design specs and system artifacts for the open-core surfaces. This directory is public from Phase 0.

## What lives here (egzos/spec/design)

Per R10 (decisions log §N), the following are public open-core surfaces. Every file below arrived through the Chief's hands; the commit is the approval act.

| file | version | date | what it binds |
|---|---|---|---|
| `tokens.css` | 0.7 | 2026-09-22 | The ONE code artifact A2 ships: `--egz-*` CSS variables for light, dark-neutral and dark-violet schemes; colour law (two colours), structure (radius 0, 2 px, 4 px offset), type, motion tokens. **The shadcn/ui bridge is declared here, not documented** (v0.6, D-T3), with the source-order requirement that makes the flat radius pins actually win stated in the file (v0.7): a catalogue component re-themes by resolving against egzos values, and nothing is retyped into the platform theme. The Tailwind mapping stays a comment — it is config a4s writes, not CSS. The lifeboat consumes this file as CSS variables; the flagship maps it — never forks it, by copy or by transcription. |
| `DESIGN-PRINCIPLES.md` | 1.3 | 2026-09-22 | The five decided §P principles verbatim, the thirteen principles of the bound direction (Docket v2), incl. principle 13: the spec is exhaustive; a gap is a defect. |
| `DESIGN-SOURCES.md` | 1.7 | 2026-09-22 | Provenance: theme seeds, typefaces, adopted conventions, every catalogue component picked by a spec (registry item · licence · date · the spec revision that picked it), the bespoke and none-on-this-screen decisions, considered-and-declined, corrections log. Versions in its tables are **records, not pointers** — see its *Pointers and records* section. |
| `step-up-tap-and-pending-approval.md` | 1.11 | 2026-09-22 | The step-up tap page and the pending-approval page (lifeboat and flagship). Consumers: a3-trust, a5-dinghy, a4s/a4g, a2-conformance, a6-adversary. |
| `lifeboat.md` | 1.6 | 2026-09-22 | The lifeboat (`egzos web`): home/search, item detail, uniform not-found, scheme switch, pending parity rule. Consumer: a5-dinghy. |
| `consent.md` | 1.7 | 2026-09-22 | The authorization server's pages: `/login`, `/device`, `/authorize` (consent in `token ls` vocabulary), outcomes, the uniform failure page. Consumer: a3-trust. |

**Version rule.** A file's own header is authoritative; this table is the index a builder checks first, and it is bumped in the same commit as the file.

**Pointers move with the file they point at — all of them.** A commit that bumps a file's version bumps, in the same commit: this index's row, every sibling's **Provenance:** pointer, and **every sibling's `Siblings:` / `Tokens:` / `Shell:` pointer aimed at it.** This clause was `Provenance:`-only for four revisions and the gap produced five instances of the same stale-pointer finding on one PR — the last of which resolved a reader to the one version of a file that could *not* answer the question it was sent there to ask. A reader must never have to guess whether a version gap is meaningful, so the rule now covers every pointer, not just the one that first drifted.

**A version is a pointer or a record; only pointers move.** A **pointer** names the version a reader should go and read *now* — every header pin above and every row in the table. A **record** names the version in which something happened: which spec revision picked a component, which revision carried a correction, what a changelog entry says about the past. **A record is frozen**; bumping one destroys the only fact it carried, and a sync that touches one is the sync being wrong, not the record. `DESIGN-SOURCES.md` is records throughout except its own Status line — its *Pointers and records* section states this for that file. Headings carry neither and therefore carry no version.

**Across the repository boundary, a pointer is a pin to what the spec was written against.** A flagship spec in `Egzos/egzos-platform` cannot be bumped by a commit in this repository, so *same commit* is unachievable there and demanding it would make every cross-repo pin permanently non-conforming. The rule for a cross-repo pin: it is re-pinned at the **next commit to the consuming repository's `spec/design/`** — not merely the next commit that happens to touch that one file, which is a promise with no date — and at that moment **the claim that turns on the pin is re-checked and the re-check stated in the changelog** — for example a §5 parenthetical asserting *`tokens.css` vX carries no size scale* must be re-verified against the new version, not merely renumbered. Between the two commits the pin is a truthful record of what the spec was written against, not drift. Within this repository the synchronous rule stands, and a stale pointer here is a defect.

Direction: **Docket v2** (bound 2026-09-11) — a record: paper and ink, IBM Plex Sans + Mono, radius 0, 2 px ink borders, a 4 px hard offset that collapses on press; two colours only (`--egz-act` for the human act, `--egz-alarm` Swiss Red for failures; no yellow anywhere); trust is a shape; motion law B (presence, arrival, reveal — nothing else); light is the record, dark is the same tokens re-valued with two user-selectable canvases.

## How to read a spec

Every spec has the same shape: §0 scope · §1 vocabulary (contract words; the fixed state vocabulary) · §2–3 the pages · **§4 regions × states** (every region, every applicable state, verbatim copy, colour, a11y, audit event, lifeboat/flagship difference) · §5 constants, formats, layout, print · §6–9 colour, structure, type, motion laws · §10 silence-not-errors · §11 unverified-by-default · §12 accessibility + keyboard map · **§13 canonical copy** (rendered verbatim; never paraphrased) · **§14 what the spec needs from the contract** (`[OPEN→a1p]` / `[GAP→a1p]` are raised, never invented) · §15 A6 review notes · §16 a2-conformance checklist · **§17 component picks** (primary + fallback + take/strip + installer + licence; or *none*) · §18 URLs and HTML patterns · §19 relationship to the other UI · **§20 test fixtures, one per state** · §21 non-goals and open items.

A state not listed for a region cannot occur there. If a builder meets a case a spec does not answer, that is a defect in the spec: file a `design-gap` issue quoting the section and take the next item. Never improvise.

## What lives in egzos-platform/spec/design

Flagship screen specs live in the sibling `Egzos/egzos-platform/spec/design` — closed product, closed specs, in build order: search/list (the app shell), permissions dashboard, pending review with previews, onion graph, drag-drop gate, triage flow, permissions matrix, step-up integration. Each names every component as a registry item (licence noted) or `bespoke`, and its picks are recorded here in `DESIGN-SOURCES.md`.

## How specs arrive

A2 (studio mode on Hyperagent) runs direction sessions with the Chief → produces direction boards with tradeoffs → the Chief picks → A2 writes the binding spec, exhaustive → the Chief commits it to this directory. The commit IS the approval. Decisions A2 takes inside a spec are listed in its header with the rejected alternative and the cost, and the Chief may veto by editing before commit. Agents build from committed specs only.
