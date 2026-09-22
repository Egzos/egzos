# DESIGN-SOURCES.md

**Owner:** A2 (Taste)
**Status:** v1.9 (2026-09-22; supersedes v1.8) — closes the two a1r minors that v1.8's rule created rather than removed. **(1)** The v1.7 Status entry below still asserts the `#19746` correction as fact, four hundred words above the entry that withdraws it. Freezing the entry is right — it records what v1.7 said — but this file's own practice is to mark a superseded record **in place** (`#89 (v1.1 wrote #99 — corrected)`; the frozen parenthetical in the corrections log), not to rely on a later entry, and a reader scanning one Status block should not have to decide which of two contradictory sentences is current. Marked, not bumped. **(2)** v1.8 made *compare install targets, not numbers* the test before writing a correction, and this file gives three items **two textual install targets each** — so the rule applied to its own register resolves *two rows, two targets, therefore two components*, the same false positive v1.7 produced from ids. The **canonical citation form** is now stated and the test operates on the `(author, demo-slug)` pair, never on the URL string. v1.8 (2026-09-22; superseded) — **withdraws the `#19746` "correction", which was not one, and states the rule that made it look like one.** Both reviewers raised the same major: v1.7's corrections log declared `Empty · cnippet-dev` to be #19746 rather than #19745 and then said *"nothing else needed correcting"*, while four rows in the tree still read #19745. a1r framed the dichotomy exactly right — either those rows are wrong, or the two ids are different items and the entry is misattributed — and correctly declined to resolve it, because no catalogue tooling may run in a session with approval authority (§P trust rule). A2's session may, and did: **#19745 is `Empty — Default` and #19746 is `Empty — No results`. They are two demos of one component.** So no row was ever wrong, and the entry implied a defect in three that are fine. The general rule, now stated below and the actual value of this round: **a 21st.dev id identifies a demo, not a component** — so a provenance row names the component *and* the demo, and a difference between two demo ids of one component is never a correction. Also fixes, all from this round: the onion row's *not yet committed* parenthetical, this file's own Status history skipping v1.1 and v1.0, §P attributed to CLAUDE.md where it is the decisions log, and the claim that the Status block is the only pointer to this file. v1.7 (2026-09-22; superseded) — adds the provenance for the flagship **`onion-graph.md` v1.0** (egzos-platform), which is mostly *bespoke* and mostly **by finding rather than by rule**: the registry has no primitive for a concentric audience diagram, and the two items the Chief bookmarked for it turn out to be useful as structure, not as components. Two records worth having: the drag-and-drop row says **what was searched and what was not there** — every drag-and-drop item in the catalogue is a file-upload dropzone, a different problem — and the declined rows name the arc-text primitives rejected with the reason. One correction: `Empty · cnippet-dev` is **#19746**, not #19745 as the 2026-09-21 dossier recorded; caught by verifying the id before citing it, which is the only reliable moment to catch it. ***(Record — withdrawn in v1.8. The two ids are demos of one component, not two components, so there was nothing to correct; the register names the demo instead. Frozen as what v1.7 said, and marked here so a reader of this block alone is not left choosing between two sentences.)*** v1.6 (2026-09-22; superseded) — **the v1.5 commit performed, inside one diff hunk, the exact record-bump its own Status line four lines above declared must never happen.** Both reviewers caught it. The corrections-log entry naming where the Origin UI Table fix landed has now been bumped three times — `d33bdb0` wrote **v1.2**, `8299031` moved it to v1.6, `364408a` moved it to v1.7 *while explaining why that move is wrong*. Restored to **v1.2** and verified against the tree rather than reasoned about: `step-up-tap-and-pending-approval.md` at `d33bdb0` already reads `Table · Origin UI · #89 (MIT)`, so v1.2 is the revision carrying the corrected value — and, as the entry now says, the tap spec never carried #99 at all, which the old wording implied. Also closes a1r's minor 3: the tap-spec table's thirty-four rows and the lifeboat/consent rows carried **no** version in *Picked by spec*, the column v1.5 defined as the only remaining home for that fact once headings lost theirs. v1.5 (2026-09-22; superseded) — **retires the stale-heading class by deciding what a version number in this file means.** Four findings across three rounds were the same defect wearing different hats: a heading read *`search-list.md` v1.5* over thirty-one rows citing *v1.2*, the theme-seed heading read *tokens.css v0.3* while the file is at v0.6, the Status block described rows as added for *v1.0* under a v1.4 heading, and the corrections log's *fixed in v1.6* was bumped to v1.7 by a pointer sync that should never have touched it. See **Pointers and records** below: a version here is one or the other, headings carry neither, and the class cannot recur. Also adds the shadcn/ui variable-contract row (the key names are adopted from an MIT project and that is provenance), records **D-T3** in the corrections log, and gives the dashboard rows the version that picked them. v1.4 (2026-09-22; superseded) — adds the provenance rows for the flagship `permissions-dashboard.md` v1.0, including three explicit declines (Role Permissions Picker as an editable-grant pattern, Alert Dialog as a modal on a security surface, Delete Account Form's type-to-confirm). v1.3 (2026-09-22; superseded) — corrects the stale §16 pointers to §17 (§16 is the conformance checklist), moves the onion-diagram row to the spec that actually owns it, and resolves the Role Permissions Picker row (provenance with no picker). v1.2 (2026-09-21; superseded) — adds the rows for `lifeboat.md` v1.0 and `consent.md` v1.0 (none: exempt / bespoke, decided), the picks for the flagship `search-list.md` v1.0 (egzos-platform), and one correction: Origin UI's Table is registry item **#89**, not #99 as v1.1 recorded (verified against the 21st.dev search index 2026-09-21). Rows are added as each screen spec is committed. **v1.1 (2026-09-13; superseded)** — the first register with picks in it, from the tap spec's second round; it is the revision that recorded Origin UI's Table as #99, corrected in v1.2. **v1.0 (2026-09-11; superseded)** — the theme seeds and typefaces from the direction sessions, no component rows yet. *(These two were missing from this chain until v1.8, in the commit that claimed to have completed every header history — and the check could not see it, because it derives the expected set from a file's changelog entries and this Status block IS this file's changelog: the set it derives is exactly the set that is there.)*

## Purpose

This file records the provenance of every catalogue component, theme seed and typeface used in a production screen, per the inspiration canon (decisions log §P, level 4):

> DESIGN-SOURCES.md records provenance: component, registry item or URL, license, date, the spec that picked it.

A component without a row here is not merged. A2 adds rows when writing each screen spec; A4 and A5 reference them when installing or implementing. Where a licence reads *per item page*, a4s-atelier verifies it on the item's page at install time and carries the verified licence in the PR body; the Chief carries the line back here.

## Pointers and records

A version number in this file is one of exactly two things, and the difference is what it does when the target moves:

- A **pointer** names the version a reader should go and read *now*. It moves whenever the target moves, in the same commit (the Version rule, `README.md`).
- A **record** names the version in which something happened — which spec revision picked a component, which revision a correction landed in. **A record is frozen.** Bumping it destroys the only fact it carried.

Every version in the tables below is a **record**: the *Picked by spec* column names the revision that made the pick, and the corrections log names the revision that carried the fix. Neither moves, ever. Rows added later for the same screen carry their own, later version — a column with mixed versions is the file working correctly, not drift.

**Headings carry no version at all.** A heading version is neither a pointer (nobody reads a heading to find a revision) nor a record (it records nothing the rows do not), and each one became a second place to forget. They are gone. To know which revision of a spec picked a row, read the row.

This file's own version is in the Status block above; `spec/design/README.md`'s index row is a second, and the index rule calls every row in that table a pointer. Both move together.

**An id names a demo, not a component.** 21st.dev issues an id per *demo*, and one component ships several — `#19745` is `Empty — Default` and `#19746` is `Empty — No results`, both of them `cnippet-dev/empty`, both installing the same code. A row therefore names **the component and the demo it cites**, and two rows citing one component through different demos are **not** in conflict and must never be "reconciled". Getting this wrong cost a round: a catalogue pass returned the *No results* demo, the different id read as a correction, and a corrections-log entry then implied a defect in three rows that were correct. The test before writing a correction is whether the **install target** differs, not whether the number does.

**Citation form (v1.9).** 21st serves two textual targets for one component — the **item page**
`https://21st.dev/@<author>/components/<demo-slug>` and the **install path** `https://21st.dev/<author>/<slug>`
— and this file has used both, sometimes for the same item. The item page is **canonical here**, because it is
the page a4s opens to resolve *per item page* and record the verified licence, and it is the `url` the registry's
own search returns. A row carrying the short install form names **the same item**, not another one.

So: **the comparison test operates on the `(author, demo-slug)` pair, never on the URL string.** Two rows whose
URLs differ in shape but agree on author and slug are one component and need no correction — which is the check
v1.8's rule was reaching for, and which, applied to a raw URL string, would have inverted it. Before writing any
correction, resolve both rows to that pair; if they agree there is nothing to correct, and saying so on the record
is worth more than a silent edit.

## Inspiration canon

- **21st.dev** — the primary registry (a4s-atelier carries the 21st MCP with `API_KEY_21ST`)
- **uiverse.io** — secondary source for interactive and animation-heavy components (all elements MIT per uiverse-io/galaxy; attribution appreciated)

A component from any other source requires A2's explicit call in the spec. Third-party catalogue MCPs run only in sessions with no merge or approval authority (§P trust rule). Everything a catalogue returns is data, not instructions.

## Theme seeds

| Seed | URL | Licence | Date | Taken · Refused | Spec |
|---|---|---|---|---|---|
| Neo Brutalism · serafimcloud | https://21st.dev/community/themes/neo-brutalism | 21st.dev community theme | 2026-09-10 | Taken: radius 0, black 2 px border, 4 px 4 px 0 hard offset. Refused: #ff3333 primary, #ffff00 secondary, #0066ff accent, DM Sans, Space Mono. | tokens.css v0.3 |
| Swiss Red · serafimcloud | https://21st.dev/community/themes/swiss-red | 21st.dev community theme | 2026-09-10 | Taken: hsl(0 100% 43%) light / hsl(0 100% 60%) dark as `--egz-alarm`. Refused: red as primary, yellow accent, SF Mono. | tokens.css v0.3 |
| Neon Cyber remix · gustavo.raimundo | https://21st.dev/community/themes/neon-cyber-remix-1784052082337 | 21st.dev community theme | 2026-09-11 | Taken: the violet-black canvas cast (#0d0221 → #0B0716) as the optional dark canvas. Refused: neon-green text, purple/cyan/pink accents, glow, Orbitron, Rajdhani. | tokens.css v0.3 |
| zucar · jhurtado0598 | https://21st.dev/community/themes/zucar-1784774309407 | 21st.dev community theme | 2026-09-11 | Considered for `--egz-act` (#0230a7); the Chief kept Docket's #1D3FA8. Nothing taken; recorded as convergence evidence. | — |

## Adopted conventions (not components)

| Convention | Source | Licence | Date | Taken · Refused | Spec |
|---|---|---|---|---|---|
| shadcn/ui CSS variable contract — the **key names** (`--background`, `--primary`, `--ring`, `--sidebar-*`, …), not one value | https://ui.shadcn.com (theming) | MIT | 2026-09-22 | Taken: the names, so a catalogue component re-themes by resolving against egzos values with no edit. Refused: every shipped value, the five `--chart-*` hues (egzos has two colours and both are reserved), and the `calc()`-derived radius ladder, which yields negative lengths at radius 0. | tokens.css v0.6 (D-T3) |

## Typefaces

| Typeface | Source | Licence | Date | Role | Spec |
|---|---|---|---|---|---|
| IBM Plex Sans | https://github.com/IBM/plex | SIL OFL 1.1 | 2026-09-09 | UI | tokens.css v0.3 |
| IBM Plex Mono | https://github.com/IBM/plex | SIL OFL 1.1 | 2026-09-09 | ids, scopes, hashes, timestamps, labels, countdowns | tokens.css v0.3 |

## Provenance table — components

| Component | Registry item / URL | Licence | Date | Picked by spec |
|---|---|---|---|---|
| Tool Approval (pending item shape) | https://21st.dev/@starc007/components/tool-approval · #26580 | per item page | 2026-09-11 | step-up-tap-and-pending-approval.md v1.0 §17 |
| Approval Card (pending item shape) | https://21st.dev/@theshanelevine/components/approval-card · #23595 | per item page | 2026-09-11 | step-up-tap-and-pending-approval.md v1.0 §17 |
| Hold to Confirm (act enhancement only) | https://21st.dev/@ddoemonn/components/hold-to-confirm · #23527 | per item page | 2026-09-11 | step-up-tap-and-pending-approval.md v1.0 §2.3 |
| Records Table (what moves) | https://21st.dev/@theshanelevine/components/records-table · #23604 | per item page | 2026-09-11 | step-up-tap-and-pending-approval.md v1.0 §17 |
| File Diff (what moves, as diff) | https://21st.dev/@kvnkld/components/file-diff · #23584 | per item page | 2026-09-11 | step-up-tap-and-pending-approval.md v1.0 §17 |
| Avatar (resolved audience) | https://21st.dev/@originui/components/avatar · #415 | MIT (Origin UI) | 2026-09-11 | step-up-tap-and-pending-approval.md v1.0 §17 |
| Role Permissions Picker (structure reference for a capability list; **not installed**) | https://21st.dev/@cnippet-dev/components/role-permissions-picker · #24929 | per item page | 2026-09-11 · re-scoped 2026-09-22 | Reference only. Considered for the tap page's audience roles and for `consent.md` §7's capabilities block; both are **bespoke** (`consent.md` §17). Retained here as provenance for the idea, picked by no spec. |
| Compare Reveal (consequence: now vs after) | https://21st.dev/@rmahammad/components/compare-reveal · #23419 | per item page | 2026-09-11 | step-up-tap-and-pending-approval.md v1.0 §17 |
| Border Beam (presence beam — idea only, re-cut solid ink) | https://21st.dev/@larsen66/components/border-beam · #21703 | per item page | 2026-09-11 | step-up-tap-and-pending-approval.md v1.0 §2.4 |
| PDF Viewer (staged preview) | https://21st.dev/@extend-hq/components/pdf-viewer · #15406 | per item page | 2026-09-11 | step-up-tap-and-pending-approval.md v1.0 §17 |
| Interactive Folder Gallery (staging reveal) | https://21st.dev/@alexperezcedeno/components/interactive-folder-gallery · #16368 | per item page | 2026-09-11 | step-up-tap-and-pending-approval.md v1.0 §17 |
| Accordion 05 (detail sections) | https://21st.dev/@designali-in/components/accordion-05 · #8637 | per item page | 2026-09-11 | step-up-tap-and-pending-approval.md v1.0 §3.2 |
| New Items Pill (arrival) | https://21st.dev/@ddoemonn/components/new-items-pill · #23546 | per item page | 2026-09-11 | step-up-tap-and-pending-approval.md v1.0 §3.1 |
| Skeleton (loading; shimmer stripped) | https://21st.dev/@shadcn/components/skeleton · #1588 | MIT (shadcn/ui) | 2026-09-13 | step-up-tap-and-pending-approval.md v1.1 §17 |
| Table Skeleton (fallback) | https://21st.dev/@uiable/components/table-skeleton · #19969 | per item page | 2026-09-13 | step-up-tap-and-pending-approval.md v1.1 §17 |
| Empty (empty state; title/description only) | `cnippet-dev/empty`, demo **Default** · https://21st.dev/@cnippet-dev/components/cnippet-empty · #19745 | per item page | 2026-09-13 | step-up-tap-and-pending-approval.md v1.1 §17 |
| Empty State (fallback) | https://21st.dev/@serafimcloud/components/empty-state · #1435 | per item page | 2026-09-13 | step-up-tap-and-pending-approval.md v1.1 §17 |
| Table (manifest fallback) | https://21st.dev/originui/table · #89 (v1.1 wrote #99 — corrected) | MIT (Origin UI) | 2026-09-13 | step-up-tap-and-pending-approval.md v1.1 §17 |
| Avatar Stack (audience fallback) | https://21st.dev/@cnippet-dev/components/avatar-stack · #23507 | per item page | 2026-09-13 | step-up-tap-and-pending-approval.md v1.1 §17 |
| Tooltip (role tooltip) | https://21st.dev/@shadcn/components/tooltip · #1277 | MIT (shadcn/ui) | 2026-09-13 | step-up-tap-and-pending-approval.md v1.1 §17 |
| Image Comparison (consequence slider fallback) | https://21st.dev/@ibelick/components/image-comparison · #1466 | per item page | 2026-09-13 | step-up-tap-and-pending-approval.md v1.1 §17 |
| Collapsible (sections fallback) | https://21st.dev/@shadcn/components/collapsible · #847 | MIT (shadcn/ui) | 2026-09-13 | step-up-tap-and-pending-approval.md v1.1 §17 |
| Long Press Button (hold fallback) | https://21st.dev/@ddoemonn/components/long-press-button · #23538 | per item page | 2026-09-13 | step-up-tap-and-pending-approval.md v1.1 §17 |
| Button (Deny, Approve without a window; base of the two-step act) | shadcn/ui button | MIT (shadcn/ui) | 2026-09-13 | step-up-tap-and-pending-approval.md v1.1 §17 |
| Kbd (shortcut hints) | https://21st.dev/@shadcn/components/kbd · #8672 | MIT (shadcn/ui) | 2026-09-13 | step-up-tap-and-pending-approval.md v1.1 §17 |
| Kbd (fallback) | https://21st.dev/@preetsuthar17/components/kbd · #3368 | per item page | 2026-09-13 | step-up-tap-and-pending-approval.md v1.1 §17 |
| Alert (failure card structure reference only) | https://21st.dev/@sean0205/components/alert-1 · #3587 | per item page | 2026-09-13 | step-up-tap-and-pending-approval.md v1.1 §17 |
| Segmented Control (flagship queue filters) | https://21st.dev/@ddoemonn/components/segmented-control · #23552 | per item page | 2026-09-13 | step-up-tap-and-pending-approval.md v1.1 §17 |
| Animated Tabs (filters fallback; animation stripped) | https://21st.dev/@educalvolpz/components/animated-tabs · #24930 | per item page | 2026-09-13 | step-up-tap-and-pending-approval.md v1.1 §17 |
| Kbd Input Group (search within pending) | https://21st.dev/@uiable/components/kbd-input-group · #26530 | per item page | 2026-09-13 | step-up-tap-and-pending-approval.md v1.1 §17 |
| Command (search fallback) | https://21st.dev/@originui/components/command · #382 | MIT (Origin UI) | 2026-09-13 | step-up-tap-and-pending-approval.md v1.1 §17 |
| Presence block, beam, stamps, two-step act, countdown, consequence box, failure cards | **bespoke** | — | 2026-09-11 | step-up-tap-and-pending-approval.md v1.0 §§2–7, 17 |
| Onion diagram | **bespoke** | — | 2026-09-11 · re-pointed 2026-09-22 | `egzos-platform/spec/design/onion-graph.md` (committed 2026-09-22; this register carries its picks below). The tap spec §0 explicitly excludes the onion; the v1.2 row citing it was wrong. |
| Toasts, dialogs, modals | **none on these pages** (decided) | — | 2026-09-13 | step-up-tap-and-pending-approval.md v1.1 §17 |

The lifeboat (a5-dinghy) uses none of the above: tokens as CSS variables only.

## Provenance — lifeboat and consent (public, egzos)

| Surface | Components | Licence | Date | Spec |
|---|---|---|---|---|
| Lifeboat — home/search, item detail, not-found, scheme switch, pending parity | **none** (exempt — §P; plain HTML from tokens.css; decided) | — | 2026-09-21 | lifeboat.md v1.0 §17 |
| Consent page, device-code entry, login, outcomes | **none** (bespoke security surface, lifeboat-adjacent; the lifeboat shell partial imported; decided) | — | 2026-09-21 | consent.md v1.0 §17 |

## Provenance table — flagship search / list (egzos-platform)

| Component | Registry item / URL | Licence | Date | Picked by spec |
|---|---|---|---|---|
| Sidebar (app shell rail) | shadcn/ui sidebar | MIT (shadcn/ui) | 2026-09-21 | search-list.md v1.2 §17 |
| Sidebar (fallback) | https://21st.dev/uniquesonu/sidebar · #2737 | per item page | 2026-09-21 | search-list.md v1.2 §17 |
| Tree View (scope tree) | https://21st.dev/ddoemonn/tree-view · #23573 | per item page | 2026-09-21 | search-list.md v1.2 §17 |
| Tree View (fallback) | https://21st.dev/preetsuthar17/tree-view · #2771 | per item page | 2026-09-21 | search-list.md v1.2 §17 |
| File Tree (fallback 2) | https://21st.dev/edwinvakayil/file-tree · #19150 | per item page | 2026-09-21 | search-list.md v1.2 §17 |
| Command (palette; chip pickers) | https://21st.dev/@originui/components/command · #382 | MIT (Origin UI) | 2026-09-21 | search-list.md v1.2 §17 |
| Command Palette (fallback) | https://21st.dev/ddoemonn/command-palette · #23522 | per item page | 2026-09-21 | search-list.md v1.2 §17 |
| Kbd Input Group (search input) | https://21st.dev/uiable/kbd-input-group · #26530 | per item page | 2026-09-21 | search-list.md v1.2 §17 |
| Input, Popover, Badge, Checkbox, Button, Toggle Group, Resizable, Tooltip, Kbd, Context Menu, Skeleton, Collapsible, Data Table, Breadcrumb | shadcn/ui | MIT (shadcn/ui) | 2026-09-21 | search-list.md v1.2 §17 |
| Segmented Control (trust chip; scheme fallback) | https://21st.dev/ddoemonn/segmented-control · #23552 | per item page | 2026-09-21 | search-list.md v1.2 §17 |
| Table (results grid; sortable variant) | https://21st.dev/originui/table · #89 | MIT (Origin UI) | 2026-09-21 | search-list.md v1.2 §17 |
| Data Grid Table (fallback) | https://21st.dev/sean0205/data-grid-table · #4783 | per item page | 2026-09-21 | search-list.md v1.2 §17 |
| Data Table (fallback 2) | https://21st.dev/shadcn/data-table · #1050 | MIT (shadcn/ui) | 2026-09-21 | search-list.md v1.2 §17 |
| Empty (empty / no-results) | `cnippet-dev/empty`, demo **Default** · https://21st.dev/@cnippet-dev/components/cnippet-empty · #19745 | per item page | 2026-09-21 | search-list.md v1.2 §17 |
| Empty State (fallback) | https://21st.dev/@serafimcloud/components/empty-state · #1435 | per item page | 2026-09-21 | search-list.md v1.2 §17 |
| Table Skeleton (fallback) | https://21st.dev/@uiable/components/table-skeleton · #19969 | per item page | 2026-09-21 | search-list.md v1.2 §17 |
| New Items Pill (new results; arrival) | https://21st.dev/@ddoemonn/components/new-items-pill · #23546 | per item page | 2026-09-21 | search-list.md v1.2 §17 |
| Resizable (fallback) | https://21st.dev/preetsuthar17/resizable · #4424 | per item page | 2026-09-21 | search-list.md v1.2 §17 |
| Accordion 05 (detail sections) | https://21st.dev/@designali-in/components/accordion-05 · #8637 | per item page | 2026-09-21 | search-list.md v1.2 §17 |
| Breadcrumb (scope path) | https://21st.dev/originui/breadcrumb · #440 | MIT (Origin UI) | 2026-09-21 | search-list.md v1.2 §17 |
| PDF Viewer (preview) | https://21st.dev/@extend-hq/components/pdf-viewer · #15406 | per item page | 2026-09-21 | search-list.md v1.2 §17 |
| Hold to Confirm / Long Press Button (hold enhancement) | #23527 / #23538 (rows above) | per item page | 2026-09-21 | search-list.md v1.2 §17 |
| Status (session facts — structure reference only) | https://21st.dev/diceui/status · #25395 | MIT (Dice UI) | 2026-09-21 | search-list.md v1.2 §17 |
| Border Beam (window chip beam — idea only) | https://21st.dev/@larsen66/components/border-beam · #21703 | per item page | 2026-09-21 | search-list.md v1.2 §17 |
| Kbd (fallback) | https://21st.dev/@preetsuthar17/components/kbd · #3368 | per item page | 2026-09-21 | search-list.md v1.2 §17 |
| Context Menu (fallback) | https://21st.dev/cnippet-dev/context-menu · #23642 | per item page | 2026-09-21 | search-list.md v1.2 §17 |
| Alert (failure card structure reference) | https://21st.dev/@sean0205/components/alert-1 · #3587 | per item page | 2026-09-21 | search-list.md v1.2 §17 |
| Stamps, drag handle, selection bar, session facts, window chip, two-step promote, failure cards | **bespoke** | — | 2026-09-21 | search-list.md v1.2 §17 |
| Toasts, drawers/sheets, dialogs (except the command palette), avatars | **none on this screen** (decided: D-S1, D-S6) | — | 2026-09-21 | search-list.md v1.2 §17 |

## Provenance table — flagship permissions dashboard (egzos-platform)

| Component | Registry item / URL | Licence | Date | Picked by spec |
|---|---|---|---|---|
| Statistics Card (summary figures) | https://21st.dev/aghasisahakyan1/statistics-card · #8590 | per item page | 2026-09-22 | permissions-dashboard.md v1.0 §17 |
| Audit Log (token table) | https://21st.dev/corr/audit-log · #25163 | per item page | 2026-09-22 | permissions-dashboard.md v1.0 §17 |
| Interactive Logs Table (activity feed) | https://21st.dev/moumensoliman/interactive-logs-table-shadcnui · #10635 | per item page | 2026-09-22 | permissions-dashboard.md v1.0 §17 |
| Data Grid Table (token table, second fallback) | https://21st.dev/sean0205/data-grid-table · #4783 | per item page | 2026-09-22 | permissions-dashboard.md v1.0 §17 |
| Table (token table and activity fallback) | https://21st.dev/originui/table · #89 | MIT (Origin UI) | 2026-09-22 | permissions-dashboard.md v1.0 §17 |
| Command + Popover (scope picker) | https://21st.dev/@originui/components/command · #382 · shadcn/ui popover | MIT (Origin UI · shadcn/ui) | 2026-09-22 | permissions-dashboard.md v1.0 §17 |
| Segmented Control (principal and status filters) | https://21st.dev/ddoemonn/segmented-control · #23552 | per item page | 2026-09-22 | permissions-dashboard.md v1.0 §17 |
| Toggle Group, Input, Collapsible, Button, Tooltip, Skeleton | shadcn/ui | MIT (shadcn/ui) | 2026-09-22 | permissions-dashboard.md v1.0 §17 |
| Empty / Empty State (empty list) | `cnippet-dev/empty`, demo **Default** · #19745 · #1435 (rows above) | per item page | 2026-09-22 | permissions-dashboard.md v1.0 §17 |
| Table Skeleton (fallback) | #19969 (row above) | per item page | 2026-09-22 | permissions-dashboard.md v1.0 §17 |
| Avatar (principal chip fallback only — primary is a mono word) | https://21st.dev/originui/avatar · #415 | MIT (Origin UI) | 2026-09-22 | permissions-dashboard.md v1.0 §17 |
| Alert (failure card structure reference) | #3587 (row above) | per item page | 2026-09-22 | permissions-dashboard.md v1.0 §17 |
| Status stamps, capability stamps, principal chip, field list, scope list, copy control, anomaly line, revoke act, grant notice, failure cards | **bespoke** (`apps/ui-flagship/src/bespoke/**`) | — | 2026-09-22 | permissions-dashboard.md v1.0 §17 |
| Toasts, dialogs, modals, drawers | **none on this screen** (decided) | — | 2026-09-22 | permissions-dashboard.md v1.0 §17 |
| Role Permissions Picker | **declined** · https://21st.dev/cnippet-dev/role-permissions-picker · #24929 | per item page | 2026-09-22 | permissions-dashboard.md v1.0 §17 — a picker implies an editable grant; a grant changes only by revoke and a fresh mint (D-P6). Recorded as a reference of what not to build. |
| Alert Dialog | **declined** · https://21st.dev/@shadcn/components/alert-dialog · #702 | MIT (shadcn/ui) | 2026-09-22 | permissions-dashboard.md v1.0 §17 — no modal on a security surface; failures replace the body inline and the revoke act is a two-step control. |
| Delete Account Form (type-to-confirm) | **declined** · https://21st.dev/@cnippet-dev/components/delete-account-form · #25081 | per item page | 2026-09-22 | permissions-dashboard.md v1.0 §14/§17 — type-to-confirm is too heavy for a per-token act; only its irreversibility copy informed `grant.immutable` and `revoke.notice`. |

## Provenance table — flagship onion graph (egzos-platform)

The diagram is bespoke by rule (decisions log §P — `docs/build/egzos-decisions-v0.6-amendments.txt`, cited as §P elsewhere in this file; CLAUDE.md has no lettered sections: the onion *is* the product). These rows record what was
consulted, what was taken as structure rather than code, what was declined and why, and — for one
region — that the catalogue was searched and had nothing.

| Component | Registry item / URL | Licence | Date | Picked by spec |
|---|---|---|---|---|
| Rings, labels, counts, quarantine mark, focus, drop zones, outward glyph | **bespoke** (a4g; one SVG, computed radii) | — | 2026-09-22 | onion-graph.md v1.0 §17 |
| Constellation Grid — **reference only, not installed** | https://21st.dev/daiwiikharihar/constellation-grid · #23960 | per item page — n/a, no code taken | 2026-09-22 | onion-graph.md v1.0 §17 (Chief bookmark; taken: geometry-once-per-resize and the hit-testing structure. Refused: spring physics, cursor shockwaves, radar readout, colour shifting, theme detection, and canvas itself — D-O1 takes SVG) |
| Text Along Path | **declined** · https://21st.dev/danielpetho/text-along-path · #18550 | per item page | 2026-09-22 | onion-graph.md v1.0 D-O5 — arc labels are correct on the outer rings and cramped to illegibility on the inner ones; type that shrinks with radius reads as emphasis, and no ring may be emphasised |
| Text Arc Effect | **declined** · #4267 | per item page | 2026-09-22 | onion-graph.md v1.0 D-O5 — as above; the nearest static arc-text primitive, and still the wrong answer |
| Marquee Along SVG Path | **declined** · https://21st.dev/danielpetho/marquee-along-svg-path · #19091 | per item page | 2026-09-22 | onion-graph.md v1.0 D-O5 — the 2026-09-21 dossier's arc-label candidate; superseded by #18550 as the closer primitive and declined with it |
| Concentric Ring loaders | **declined** · #19931 · #28398 | per item page | 2026-09-22 | onion-graph.md v1.0 R13 — a rotating concentric ring is *this diagram spinning*, the single most misleading loading state this screen could have; the skeleton is the diagram with nothing in it |
| Segmented Control (density toggle, R12) | https://21st.dev/ddoemonn/segmented-control · #23552 | per item page — a4s verifies at install | 2026-09-22 | onion-graph.md v1.0 §17 (take: radio-group semantics, arrow-key navigation. Strip: the animated sliding thumb — a state change is instantaneous — and all colour) |
| Toggle Group (density toggle fallback) | #4720 · sean0205 | per item page | 2026-09-22 | onion-graph.md v1.0 §17 |
| Collapsible (overflow reveal fallback) | shadcn · #847 | MIT (shadcn/ui) | 2026-09-22 | onion-graph.md v1.0 §17 (take: the `aria-expanded` pairing only) |
| Alert (filter-bar structure fallback) | https://21st.dev/@sean0205/components/alert-1 · #3587 | per item page | 2026-09-22 | onion-graph.md v1.0 §17 (structure only; the bar is a `status`, never an `alert`) |
| Skeleton (loading, R13) | shadcn · #1588 | MIT (shadcn/ui) | 2026-09-22 | onion-graph.md v1.0 §17 (strip the shimmer entirely; arcs must match the final ring geometry) |
| Empty (empty-state fallback, R14) | `cnippet-dev/empty`, demo **No results** · https://21st.dev/@cnippet-dev/components/cnippet-empty · **#19746** — the same component as the three rows above, a different demo | per item page | 2026-09-22 | onion-graph.md v1.0 §17 (bespoke preferred — the rings must stay drawn behind it) |
| Container chip, count, failure card | **none new** — the scope chip and the failure card already vendored for `search-list.md` and the tap spec | — | 2026-09-22 | onion-graph.md v1.0 §17 (one chip in the product; one failure voice) |
| Keyboard *move to…* | **none on this screen** — `search-list.md` §17's command palette owns it; the onion contributes destinations | — | 2026-09-22 | onion-graph.md v1.0 §17 |
| Drag-and-drop primitive (R7) | **none exists** — searched 2026-09-22: #542, #8019, #18045, #19201, #15587 are all **file-upload** dropzones. One target, one gesture, no geometry, no proposal: a different problem, and adopting one would import an upload's mental model into a move | — | 2026-09-22 | onion-graph.md v1.0 §17 |
| Toasts, dialogs, drawers, tooltips, avatars | **none on this screen** (decided) | — | 2026-09-22 | onion-graph.md v1.0 §17 — a tooltip on a ring is the obvious reach and is refused: it puts behind a hover what the accessible name and the label already carry, and neither the keyboard nor touch has a hover |

## Corrections log
- 2026-09-22 · **Withdrawn: the `Empty · cnippet-dev` "correction" was not one.** An entry here claimed the item was **#19746** and not **#19745**, and that nothing else needed correcting. Both reviewers found four rows still reading #19745 and raised it as a major. Checked against the catalogue: **#19745 is `Empty — Default`, #19746 is `Empty — No results`, and both are demos of `cnippet-dev/empty`** — the same component, the same install. No row was wrong; the entry implied a defect in three that were fine, which is worse than the drift it thought it was fixing. The rows now name the component and the demo (see *An id names a demo, not a component*, above). **The lesson is not "verify ids" — v1.7 did verify, and still got it wrong by comparing the wrong thing.** It is: compare **install targets**, not numbers.
- 2026-09-22 · **D-T3** · the shadcn/ui bridge existed in `tokens.css` as a **comment** from v0.4 to v0.5 — twenty-five key names documented and none declared. A catalogue component resolved `--background` against the empty string, so a4s's only route to a rendering pick was to retype the block into the flagship theme: a fork by transcription, which that file's header forbids in the same breath as a fork by copy. Declared in `tokens.css` v0.6 as aliases (`var(--egz-*)`), which are scheme-independent by construction and inert where unread, so the lifeboat pays nothing. `--radius-sm/md/lg/xl` are pinned flat because shadcn derives them with `calc()` and radius 0 makes them negative — invalid, silently falling back to a rounded corner in a square system. `--chart-1…5` are refused on the record rather than omitted by accident.
- 2026-09-21 · Origin UI Table recorded as **#99** in this file at v1.1; the registry item is **#89** (`https://21st.dev/originui/table`). Corrected here in **v1.2**. The tap spec's §17 row has read #89 since that spec was first written, so nothing needed fixing there — the earlier wording of this entry implied otherwise and is corrected with it. *(This line is a **record**. Its version is frozen at v1.2. Three separate pointer syncs have moved it — to v1.6, then v1.7 — and each destroyed the only fact it carries; the third did so in the same commit that declared records frozen. If a sweep ever wants to move it again, the sweep is wrong.)*

## Considered and declined (on the record)

Lime Haze, Slate Linen (hazard-yellow dark) — declined 2026-09-10: no yellow. Liquid Metal Button #10443, Pearl Button #5815 — declined for controls 2026-09-11: gloss contradicts the flat structure. Circular Split Roll #26061 — deferred to the triage-flow spec (flagship). Constellation Grid #23960, Marquee Along SVG Path #19091 — deferred to the onion-graph spec (flagship). Radial Orbital Timeline #1820, Orbiting Circles with Globe #18043, Synapse Network #8073, Retro Grid #9294, Glitch Text #19111, macOS Dock #18014 — anti-references. Themes "Claude", "Vercel", Matrix Green, Neon Cyber (original), Candyland, Graphite Mono — anti-references.
