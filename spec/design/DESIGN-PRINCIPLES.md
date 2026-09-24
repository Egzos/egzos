# DESIGN-PRINCIPLES.md

**Owner:** A2 (Taste)
**Status:** v1.6 (2026-09-23) — **Dates corrected — 1 revision in this file said `2026-09-22` and was written on the 23rd.** A revision's date is a claim about the world, not a serial number, and the corpus kept writing yesterday's date after midnight UTC: **34 dates across 13 files**, plus 11 headers that disagreed with their own newest changelog entry. The tell was a changelog that ran **backwards** — eight files each held exactly one `2026-09-23` entry wedged inside a run of `2026-09-22` ones, which reads as a single typo and is the exact reverse: that lone entry was the only one dated right, and every entry after it inherited the day before. Correcting it by clamping the outlier to its neighbours — the obvious repair — would have overwritten the one good date in each file with the error. So it was settled on evidence instead: a version that did not exist at the branch's last commit dated on or before 2026-09-22 (`6fa85751` in `Egzos/egzos`, `20768120` in `Egzos/egzos-platform`) was written on the 23rd, and each file's boundary version was read from the raw blob at that commit. This file and `DESIGN-SOURCES.md` state their history as `**Status:** v1.5 (date) — …` rather than as changelog entries, which is the third time these two have sat outside a sweep that assumed the screen-spec header shape (see blind spots 2 and 7 in the audit). Both forms are read now. Four checks now guard this — a header against its own newest entry, a changelog that must run forward, a version the chain names but nothing can date, and an index row's date against the header — each made to fail on purpose before its green was believed. No region, state, copy string, pick or law changed. v1.5 (2026-09-23) — principle 11's 44 px rule now says the thing that makes it hold: **the minimum is the hit target, not the ink.** A width audit across all seven mocks measured 448 spec surfaces at every width the specs declare and found **no overflow anywhere** — and one finding repeated in six of seven specs: every *text-shaped* control renders at 21–33 px. `Exit triage`, `Back`, `Return to pending`, `Close window now`, `Retry`, `Collapse rail` and the four rail entries. Each of those specs' §12 dutifully says *targets ≥ 44 px*, and each mock broke it the same way, because a control with no box has nothing to remind anyone. The corpus had already met this and fixed it **once, locally**: `permissions-dashboard.md` **D-P13** made the `token id` row 44 px so its *Copy* control could be, observing that *an inline control in a 20 px field row renders at 17 px and silently breaks §12*. That is not special to that row — it is what a text-shaped control does everywhere, so D-P13's observation is promoted to the law it always was. No new rule; an existing one given its right scope. v1.4 (2026-09-22) — the history chain gave **v1.1 no date at all**, only the drafting range it was written across, where the other five files in this directory carry the date the revision landed: **v1.1 landed 2026-09-13**, the day principle 13 was added. Raised by a1r as the second instance of the `tokens.css` header defect — the two artefacts here that are not screen specs sat outside both header sweeps, so *every header history* was false for exactly the files no screen spec resembles. v1.3 (2026-09-22) — principle 12 corrected for `tokens.css` v0.6 (**D-T3**): it said the flagship *maps it into Tailwind and the shadcn bridge*, which was true while the bridge was a comment and is now the instruction to commit the fork D-T3 removed. The bridge ships **inside** the file; the flagship maps the `--egz-*` layer and inherits the bridge untouched. A builder reading the old sentence would have authored twenty-five lines this file forbids them to author. v1.2 (2026-09-22) — principle 5's type colour corrected: it specified black type on the signing control, which measures 2.33:1 on `--egz-act` in light and fails WCAG 2.2 AA, contradicting principle 11 and the tokens' own `--egz-act-on`. Raised by a2-conformance on PR #45. v1.1 (2026-09-13) — drafted from the direction sessions of 2026-09-09 → 2026-09-13 (Docket v2, bound; principle 13 added 2026-09-13). Supersedes the Phase 0.0 stub. The first section is carried verbatim from the decisions log (§P) and is locked; the second section is the direction's own principles, binding once the Chief commits this file.

---

## Decided principles (carried from decisions log §P, 2026-09-03)

These are locked; they require a contract-change-equivalent escalation to revise.

**Inspiration flows through the tokens, never around them.**
A catalogue component enters the product only after being re-themed to the egzos design tokens.
The tokens file is the identity; a component that bypasses it is not an egzos component.

**Catalogue for chrome, bespoke for the differentiators.**
Nav, tables, dialogs, forms, command palette, empty states, toasts, and other commodity UI come
from the catalogue (shadcn/ui + 21st.dev picks). The onion graph, the drag-drop gate, the triage
flow, and the permissions matrix are bespoke — they are the product; nav and tables are commodity.

**Security surfaces stay bespoke and A6-reviewed.**
The pending-review flow, the step-up tap, the consent screen, and the drag-drop gate are security
surfaces even when assembled from catalogue primitives. A stock dialog wrapping the step-up flow
is still a security surface. A6 reviews every commit to these paths.

**The lifeboat is exempt.**
The server-rendered lifeboat UI (A5; FastAPI + Jinja + htmx) consumes tokens as CSS variables and
uses no React components. It need not be visually polished; its mandate is functional parity on
the pending flow, never lagging the flagship functionally. Gitk-ugly stands.

**Every pick has provenance.**
Every component used in a production screen is named in the spec that introduced it (registry item
+ license, or `bespoke`) and recorded in `DESIGN-SOURCES.md`. A component without provenance is
not merged.

---

## Principles of the direction (Docket v2, bound 2026-09-11)

**1. egzos is a record.**
Every read, move, approval and denial is an audit event, so the interface looks like the instrument that keeps records: paper, ink, hairlines, stamps. A screen should print, screenshot and read in a PR diff exactly as it renders. Light is the record; dark is the same record at night — one token set re-valued, never a second design. Two dark canvases (neutral, violet-black cast) are a user setting, not two identities.

**2. Two colours.**
Blue (`--egz-act`) asks a human to do something only a human may do. Swiss Red (`--egz-alarm`) reports that something failed. Nothing else is coloured. A screen with neither is a screen where nothing needs you. Deny is a human decision and is set in ink. There is no yellow, lime, amber or acid anywhere and therefore no "warning" tier: the world is fine, or it failed.

**3. Weight is structure, not colour.**
Radius 0; 2 px ink borders; a 4 px hard offset that collapses when pressed — that collapse is the click. Weight lives on the containers that matter (frame, open item, consequence, presence, acts) and never on rows: inside tables and lists there are only hairlines, so the workhorse view stays dense.

**4. Trust is a shape.**
Verified is a solid stamp; unverified an outline; staged a dashed outline; quarantined a red outline with the word. Trust reads without colour and survives print, the lifeboat and colour-blindness; the only time trust takes a colour is when something went wrong.

**5. The human act is the plainest thing on the page.**
The control that signs is flat blue with its type in **`--egz-act-on`** — white by day, black at night, which is what the tokens carry and what the specs assert at ≥ 4.5:1 in all three canvases (black on the light blue measures 2.33:1 and fails AA; principle 11 is not a mode), deliberate by construction (two presses; hold is an enhancement), never glossy, never animated, never focused by default, never pressed before the container answers. Everything decorative stays away from it.

**6. Motion means presence, arrival or reveal — and nothing else.**
A beam travelling the frame while a window is open (presence); a pill or a ring step when a proposal lands (arrival); a section expanding or staged files fanning out (reveal). State changes are instantaneous. Every motion has a still equivalent under reduced-motion. The lifeboat does not move.

**7. Search is the home; the onion is a lens.**
Search-and-list is the workhorse and is designed first. The onion is a surveyor's diagram — concentric hairlines, centre private, rim public, nothing shaded — so distance can never be misread as rank. Tree coverage is never drawn on it. Red appears on it exactly once: a hollow mark on a ring that holds a quarantined item.

**8. The gate is a filing.**
A cross-audience move has a reference, a manifest, a named audience, a consequence clause and a signature line. Its weight comes from formality: the name of the contractor in the table, in ink, where you have to read it.

**9. Silence-not-errors and unverified-by-default are design rules, not just API rules.**
No count, empty state, layout, copy or route reveals what the viewer cannot see; every count is viewer-scoped. Trust status renders honestly on every item, before and after an act.

**10. Copy is plain, canonical and rendered verbatim.**
Titles are sentences. Labels are lowercase mono with a dot separator. Canonical strings live in the spec that owns the screen; the lifeboat renders them verbatim and the flagship may not paraphrase them. Everything an agent says is quoted, attributed in mono, escaped, and never interpreted.

**11. Accessibility is the baseline, not a mode.**
WCAG 2.2 AA; contrast verified per canvas; full keyboard operation; visible 2 px focus; live regions announce time at intervals, never every second; colour never carries meaning alone.

**Hit targets are ≥ 44 px — and the 44 px is the *target*, not the ink.** It binds every control a person must hit: acts, ghost acts, rail entries, `+ N more`, *Retry*, *Copy*, pagination, toggles and tree twisties. A ghost act is underlined text about 21 px tall, and its **padded target** must still reach 44; a control inside a dense row needs the row to give it the height, which is why `permissions-dashboard.md` **D-P13** makes the `token id` row 44 px rather than shrinking the control inside it. The rule is written this way because the other way does not work: every spec in this set already said *targets ≥ 44 px on acts*, and when the surfaces were measured, **six of seven had text-shaped controls at 21–33 px**. A control with a box reminds you of its height; a control that is just text does not, and that is precisely where the rule is lost. If a control's rendered box is smaller than 44 px, pad the target — never the type.

**12. Both UIs, one tokens file.**
`spec/design/tokens.css` is A2's one code artifact. The lifeboat consumes it as CSS variables; the flagship maps the `--egz-*` layer into its Tailwind theme. **The shadcn bridge is not something the flagship authors — it ships declared in the file** (v0.6, D-T3), so a catalogue component re-themes by resolving against egzos values with no edit anywhere. Retyping the bridge into the platform theme is a fork by transcription, which counts as a fork. The platform consumes; it never forks. A pick that needs a key the file does not declare is a `design-gap` against the file — never a literal in the component.

**13. The spec is exhaustive; a gap is a defect.**
Every screen spec names every region and every state that can apply to it — empty, loading, ready, waiting, confirming, in-flight, approved, denied, expired, invalid, lapsed, quota, quarantined, unreachable, offline, error, stale, partial — with verbatim copy, colour, focus and screen-reader behaviour, the audit event, and the lifeboat-vs-flagship difference. Every component pick names a primary and a fallback, what to take and what to strip, who installs it, and its licence status. One test fixture exists per state, and conformance checks for them. Every gap becomes a round-trip issue later; every decision made in the studio is one the builders never have to guess at. *(Chief, 2026-09-13.)*

---

## Sources and anti-references

Direction seeds (see `DESIGN-SOURCES.md`): Neo Brutalism — structure only; Swiss Red — the alarm only. Declined on the record: neon/acid palettes (yellow makes trust harder); the terracotta-on-warm-white and neutral-Geist defaults (the two most-remixed registry themes: generic); sci-fi and hacker faces (Orbitron, VT323); glow; orbital spectacle for the onion; glossy controls.
