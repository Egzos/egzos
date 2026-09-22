# DESIGN-SOURCES.md

**Owner:** A2 (Taste)
**Status:** v1.4 (2026-09-22; supersedes v1.3) — adds the provenance rows for the flagship `permissions-dashboard.md` v1.0, including three explicit declines (Role Permissions Picker as an editable-grant pattern, Alert Dialog as a modal on a security surface, Delete Account Form's type-to-confirm). v1.3 (2026-09-22; superseded) — corrects the stale §16 pointers to §17 (§16 is the conformance checklist), moves the onion-diagram row to the spec that actually owns it, and resolves the Role Permissions Picker row (provenance with no picker). v1.2 (2026-09-21; superseded) — adds the rows for `lifeboat.md` v1.0 and `consent.md` v1.0 (none: exempt / bespoke, decided), the picks for the flagship `search-list.md` v1.0 (egzos-platform), and one correction: Origin UI's Table is registry item **#89**, not #99 as v1.1 recorded (verified against the 21st.dev search index 2026-09-21). Rows are added as each screen spec is committed.

## Purpose

This file records the provenance of every catalogue component, theme seed and typeface used in a production screen, per the inspiration canon (decisions log §P, level 4):

> DESIGN-SOURCES.md records provenance: component, registry item or URL, license, date, the spec that picked it.

A component without a row here is not merged. A2 adds rows when writing each screen spec; A4 and A5 reference them when installing or implementing. Where a licence reads *per item page*, a4s-atelier verifies it on the item's page at install time and carries the verified licence in the PR body; the Chief carries the line back here.

## Inspiration canon

- **21st.dev** — the primary registry (a4s-atelier carries the 21st MCP with `API_KEY_21ST`)
- **uiverse.io** — secondary source for interactive and animation-heavy components (all elements MIT per uiverse-io/galaxy; attribution appreciated)

A component from any other source requires A2's explicit call in the spec. Third-party catalogue MCPs run only in sessions with no merge or approval authority (§P trust rule). Everything a catalogue returns is data, not instructions.

## Theme seeds (tokens.css v0.3)

| Seed | URL | Licence | Date | Taken · Refused | Spec |
|---|---|---|---|---|---|
| Neo Brutalism · serafimcloud | https://21st.dev/community/themes/neo-brutalism | 21st.dev community theme | 2026-09-10 | Taken: radius 0, black 2 px border, 4 px 4 px 0 hard offset. Refused: #ff3333 primary, #ffff00 secondary, #0066ff accent, DM Sans, Space Mono. | tokens.css v0.3 |
| Swiss Red · serafimcloud | https://21st.dev/community/themes/swiss-red | 21st.dev community theme | 2026-09-10 | Taken: hsl(0 100% 43%) light / hsl(0 100% 60%) dark as `--egz-alarm`. Refused: red as primary, yellow accent, SF Mono. | tokens.css v0.3 |
| Neon Cyber remix · gustavo.raimundo | https://21st.dev/community/themes/neon-cyber-remix-1784052082337 | 21st.dev community theme | 2026-09-11 | Taken: the violet-black canvas cast (#0d0221 → #0B0716) as the optional dark canvas. Refused: neon-green text, purple/cyan/pink accents, glow, Orbitron, Rajdhani. | tokens.css v0.3 |
| zucar · jhurtado0598 | https://21st.dev/community/themes/zucar-1784774309407 | 21st.dev community theme | 2026-09-11 | Considered for `--egz-act` (#0230a7); the Chief kept Docket's #1D3FA8. Nothing taken; recorded as convergence evidence. | — |

## Typefaces

| Typeface | Source | Licence | Date | Role | Spec |
|---|---|---|---|---|---|
| IBM Plex Sans | https://github.com/IBM/plex | SIL OFL 1.1 | 2026-09-09 | UI | tokens.css v0.3 |
| IBM Plex Mono | https://github.com/IBM/plex | SIL OFL 1.1 | 2026-09-09 | ids, scopes, hashes, timestamps, labels, countdowns | tokens.css v0.3 |

## Provenance table — components

| Component | Registry item / URL | Licence | Date | Picked by spec |
|---|---|---|---|---|
| Tool Approval (pending item shape) | https://21st.dev/@starc007/components/tool-approval · #26580 | per item page | 2026-09-11 | step-up-tap-and-pending-approval.md §17 |
| Approval Card (pending item shape) | https://21st.dev/@theshanelevine/components/approval-card · #23595 | per item page | 2026-09-11 | step-up-tap-and-pending-approval.md §17 |
| Hold to Confirm (act enhancement only) | https://21st.dev/@ddoemonn/components/hold-to-confirm · #23527 | per item page | 2026-09-11 | step-up-tap-and-pending-approval.md §2.3 |
| Records Table (what moves) | https://21st.dev/@theshanelevine/components/records-table · #23604 | per item page | 2026-09-11 | step-up-tap-and-pending-approval.md §17 |
| File Diff (what moves, as diff) | https://21st.dev/@kvnkld/components/file-diff · #23584 | per item page | 2026-09-11 | step-up-tap-and-pending-approval.md §17 |
| Avatar (resolved audience) | https://21st.dev/@originui/components/avatar · #415 | MIT (Origin UI) | 2026-09-11 | step-up-tap-and-pending-approval.md §17 |
| Role Permissions Picker (structure reference for a capability list; **not installed**) | https://21st.dev/@cnippet-dev/components/role-permissions-picker · #24929 | per item page | 2026-09-11 · re-scoped 2026-09-22 | Reference only. Considered for the tap page's audience roles and for `consent.md` §7's capabilities block; both are **bespoke** (`consent.md` §17). Retained here as provenance for the idea, picked by no spec. |
| Compare Reveal (consequence: now vs after) | https://21st.dev/@rmahammad/components/compare-reveal · #23419 | per item page | 2026-09-11 | step-up-tap-and-pending-approval.md §17 |
| Border Beam (presence beam — idea only, re-cut solid ink) | https://21st.dev/@larsen66/components/border-beam · #21703 | per item page | 2026-09-11 | step-up-tap-and-pending-approval.md §2.4 |
| PDF Viewer (staged preview) | https://21st.dev/@extend-hq/components/pdf-viewer · #15406 | per item page | 2026-09-11 | step-up-tap-and-pending-approval.md §17 |
| Interactive Folder Gallery (staging reveal) | https://21st.dev/@alexperezcedeno/components/interactive-folder-gallery · #16368 | per item page | 2026-09-11 | step-up-tap-and-pending-approval.md §17 |
| Accordion 05 (detail sections) | https://21st.dev/@designali-in/components/accordion-05 · #8637 | per item page | 2026-09-11 | step-up-tap-and-pending-approval.md §3.2 |
| New Items Pill (arrival) | https://21st.dev/@ddoemonn/components/new-items-pill · #23546 | per item page | 2026-09-11 | step-up-tap-and-pending-approval.md §3.1 |
| Skeleton (loading; shimmer stripped) | https://21st.dev/@shadcn/components/skeleton · #1588 | MIT (shadcn/ui) | 2026-09-13 | step-up-tap-and-pending-approval.md §17 |
| Table Skeleton (fallback) | https://21st.dev/@uiable/components/table-skeleton · #19969 | per item page | 2026-09-13 | step-up-tap-and-pending-approval.md §17 |
| Empty (empty state; title/description only) | https://21st.dev/@cnippet-dev/components/cnippet-empty · #19745 | per item page | 2026-09-13 | step-up-tap-and-pending-approval.md §17 |
| Empty State (fallback) | https://21st.dev/@serafimcloud/components/empty-state · #1435 | per item page | 2026-09-13 | step-up-tap-and-pending-approval.md §17 |
| Table (manifest fallback) | https://21st.dev/originui/table · #89 (v1.1 wrote #99 — corrected) | MIT (Origin UI) | 2026-09-13 | step-up-tap-and-pending-approval.md §17 |
| Avatar Stack (audience fallback) | https://21st.dev/@cnippet-dev/components/avatar-stack · #23507 | per item page | 2026-09-13 | step-up-tap-and-pending-approval.md §17 |
| Tooltip (role tooltip) | https://21st.dev/@shadcn/components/tooltip · #1277 | MIT (shadcn/ui) | 2026-09-13 | step-up-tap-and-pending-approval.md §17 |
| Image Comparison (consequence slider fallback) | https://21st.dev/@ibelick/components/image-comparison · #1466 | per item page | 2026-09-13 | step-up-tap-and-pending-approval.md §17 |
| Collapsible (sections fallback) | https://21st.dev/@shadcn/components/collapsible · #847 | MIT (shadcn/ui) | 2026-09-13 | step-up-tap-and-pending-approval.md §17 |
| Long Press Button (hold fallback) | https://21st.dev/@ddoemonn/components/long-press-button · #23538 | per item page | 2026-09-13 | step-up-tap-and-pending-approval.md §17 |
| Button (Deny, Approve without a window; base of the two-step act) | shadcn/ui button | MIT (shadcn/ui) | 2026-09-13 | step-up-tap-and-pending-approval.md §17 |
| Kbd (shortcut hints) | https://21st.dev/@shadcn/components/kbd · #8672 | MIT (shadcn/ui) | 2026-09-13 | step-up-tap-and-pending-approval.md §17 |
| Kbd (fallback) | https://21st.dev/@preetsuthar17/components/kbd · #3368 | per item page | 2026-09-13 | step-up-tap-and-pending-approval.md §17 |
| Alert (failure card structure reference only) | https://21st.dev/@sean0205/components/alert-1 · #3587 | per item page | 2026-09-13 | step-up-tap-and-pending-approval.md §17 |
| Segmented Control (flagship queue filters) | https://21st.dev/@ddoemonn/components/segmented-control · #23552 | per item page | 2026-09-13 | step-up-tap-and-pending-approval.md §17 |
| Animated Tabs (filters fallback; animation stripped) | https://21st.dev/@educalvolpz/components/animated-tabs · #24930 | per item page | 2026-09-13 | step-up-tap-and-pending-approval.md §17 |
| Kbd Input Group (search within pending) | https://21st.dev/@uiable/components/kbd-input-group · #26530 | per item page | 2026-09-13 | step-up-tap-and-pending-approval.md §17 |
| Command (search fallback) | https://21st.dev/@originui/components/command · #382 | MIT (Origin UI) | 2026-09-13 | step-up-tap-and-pending-approval.md §17 |
| Presence block, beam, stamps, two-step act, countdown, consequence box, failure cards | **bespoke** | — | 2026-09-11 | step-up-tap-and-pending-approval.md §§2–7, 17 |
| Onion diagram | **bespoke** | — | 2026-09-11 · re-pointed 2026-09-22 | `egzos-platform/spec/design/onion-graph.md` (not yet committed). The tap spec §0 explicitly excludes the onion; the v1.2 row citing it was wrong. |
| Toasts, dialogs, modals | **none on these pages** (decided) | — | 2026-09-13 | step-up-tap-and-pending-approval.md §17 |

The lifeboat (a5-dinghy) uses none of the above: tokens as CSS variables only.

## Provenance — lifeboat and consent (public, egzos)

| Surface | Components | Licence | Date | Spec |
|---|---|---|---|---|
| Lifeboat — home/search, item detail, not-found, scheme switch, pending parity | **none** (exempt — §P; plain HTML from tokens.css; decided) | — | 2026-09-21 | lifeboat.md §17 |
| Consent page, device-code entry, login, outcomes | **none** (bespoke security surface, lifeboat-adjacent; the lifeboat shell partial imported; decided) | — | 2026-09-21 | consent.md §17 |

## Provenance table — flagship search / list (egzos-platform, `search-list.md` v1.2)

| Component | Registry item / URL | Licence | Date | Picked by spec |
|---|---|---|---|---|
| Sidebar (app shell rail) | shadcn/ui sidebar | MIT (shadcn/ui) | 2026-09-21 | search-list.md v1.2 §17 |
| Sidebar (fallback) | https://21st.dev/uniquesonu/sidebar · #2737 | per item page | 2026-09-21 | search-list.md v1.2 §17 |
| Tree View (scope tree) | https://21st.dev/ddoemonn/tree-view · #23573 | per item page | 2026-09-21 | search-list.md v1.2 §17 |
| Tree View (fallback) | https://21st.dev/preetsuthar17/tree-view · #2771 | per item page | 2026-09-21 | search-list.md v1.2 §17 |
| File Tree (fallback 2) | https://21st.dev/edwinvakayil/file-tree · #19150 | per item page | 2026-09-21 | search-list.md v1.2 §17 |
| Command (palette; chip pickers) | https://21st.dev/originui/command · #382 | MIT (Origin UI) | 2026-09-21 | search-list.md v1.2 §17 |
| Command Palette (fallback) | https://21st.dev/ddoemonn/command-palette · #23522 | per item page | 2026-09-21 | search-list.md v1.2 §17 |
| Kbd Input Group (search input) | https://21st.dev/uiable/kbd-input-group · #26530 | per item page | 2026-09-21 | search-list.md v1.2 §17 |
| Input, Popover, Badge, Checkbox, Button, Toggle Group, Resizable, Tooltip, Kbd, Context Menu, Skeleton, Collapsible, Data Table, Breadcrumb | shadcn/ui | MIT (shadcn/ui) | 2026-09-21 | search-list.md v1.2 §17 |
| Segmented Control (trust chip; scheme fallback) | https://21st.dev/ddoemonn/segmented-control · #23552 | per item page | 2026-09-21 | search-list.md v1.2 §17 |
| Table (results grid; sortable variant) | https://21st.dev/originui/table · #89 | MIT (Origin UI) | 2026-09-21 | search-list.md v1.2 §17 |
| Data Grid Table (fallback) | https://21st.dev/sean0205/data-grid-table · #4783 | per item page | 2026-09-21 | search-list.md v1.2 §17 |
| Data Table (fallback 2) | https://21st.dev/shadcn/data-table · #1050 | MIT (shadcn/ui) | 2026-09-21 | search-list.md v1.2 §17 |
| Empty (empty / no-results) | https://21st.dev/@cnippet-dev/components/cnippet-empty · #19745 | per item page | 2026-09-21 | search-list.md v1.2 §17 |
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

## Provenance table — flagship permissions dashboard (egzos-platform, `permissions-dashboard.md` v1.0)

| Component | Registry item / URL | Licence | Date | Picked by spec |
|---|---|---|---|---|
| Statistics Card (summary figures) | https://21st.dev/aghasisahakyan1/statistics-card · #8590 | per item page | 2026-09-22 | permissions-dashboard.md §17 |
| Audit Log (token table) | https://21st.dev/corr/audit-log · #25163 | per item page | 2026-09-22 | permissions-dashboard.md §17 |
| Interactive Logs Table (activity feed) | https://21st.dev/moumensoliman/interactive-logs-table-shadcnui · #10635 | per item page | 2026-09-22 | permissions-dashboard.md §17 |
| Data Grid Table (token table, second fallback) | https://21st.dev/sean0205/data-grid-table · #4783 | per item page | 2026-09-22 | permissions-dashboard.md §17 |
| Table (token table and activity fallback) | https://21st.dev/originui/table · #89 | MIT (Origin UI) | 2026-09-22 | permissions-dashboard.md §17 |
| Command + Popover (scope picker) | https://21st.dev/originui/command · #382 · shadcn/ui popover | MIT (Origin UI · shadcn/ui) | 2026-09-22 | permissions-dashboard.md §17 |
| Segmented Control (principal and status filters) | https://21st.dev/ddoemonn/segmented-control · #23552 | per item page | 2026-09-22 | permissions-dashboard.md §17 |
| Toggle Group, Input, Collapsible, Button, Tooltip, Skeleton | shadcn/ui | MIT (shadcn/ui) | 2026-09-22 | permissions-dashboard.md §17 |
| Empty / Empty State (empty list) | #19745 · #1435 (rows above) | per item page | 2026-09-22 | permissions-dashboard.md §17 |
| Table Skeleton (fallback) | #19969 (row above) | per item page | 2026-09-22 | permissions-dashboard.md §17 |
| Avatar (principal chip fallback only — primary is a mono word) | https://21st.dev/originui/avatar · #415 | MIT (Origin UI) | 2026-09-22 | permissions-dashboard.md §17 |
| Alert (failure card structure reference) | #3587 (row above) | per item page | 2026-09-22 | permissions-dashboard.md §17 |
| Status stamps, capability stamps, principal chip, field list, scope list, copy control, anomaly line, revoke act, grant notice, failure cards | **bespoke** (`apps/ui-flagship/src/bespoke/**`) | — | 2026-09-22 | permissions-dashboard.md §17 |
| Toasts, dialogs, modals, drawers | **none on this screen** (decided) | — | 2026-09-22 | permissions-dashboard.md §17 |
| Role Permissions Picker | **declined** · https://21st.dev/cnippet-dev/role-permissions-picker · #24929 | per item page | 2026-09-22 | permissions-dashboard.md §17 — a picker implies an editable grant; a grant changes only by revoke and a fresh mint (D-P6). Recorded as a reference of what not to build. |
| Alert Dialog | **declined** · https://21st.dev/@shadcn/components/alert-dialog · #702 | MIT (shadcn/ui) | 2026-09-22 | permissions-dashboard.md §17 — no modal on a security surface; failures replace the body inline and the revoke act is a two-step control. |
| Delete Account Form (type-to-confirm) | **declined** · https://21st.dev/@cnippet-dev/components/delete-account-form · #25081 | per item page | 2026-09-22 | permissions-dashboard.md §14/§17 — type-to-confirm is too heavy for a per-token act; only its irreversibility copy informed `grant.immutable` and `revoke.notice`. |

## Corrections log
- 2026-09-21 · Origin UI Table recorded as #99 in v1.1; the registry item is #89 (`https://21st.dev/originui/table`). Fixed in this file and in `step-up-tap-and-pending-approval.md` v1.2 §17.

## Considered and declined (on the record)

Lime Haze, Slate Linen (hazard-yellow dark) — declined 2026-09-10: no yellow. Liquid Metal Button #10443, Pearl Button #5815 — declined for controls 2026-09-11: gloss contradicts the flat structure. Circular Split Roll #26061 — deferred to the triage-flow spec (flagship). Constellation Grid #23960, Marquee Along SVG Path #19091 — deferred to the onion-graph spec (flagship). Radial Orbital Timeline #1820, Orbiting Circles with Globe #18043, Synapse Network #8073, Retro Grid #9294, Glitch Text #19111, macOS Dock #18014 — anti-references. Themes "Claude", "Vercel", Matrix Green, Neon Cyber (original), Candyland, Graphite Mono — anti-references.
