# DESIGN-PRINCIPLES.md

**Owner:** A2 (Taste)
**Status:** v1.1 — drafted from the direction sessions of 2026-09-09 → 2026-09-13 (Docket v2, bound; principle 13 added 2026-09-13). Supersedes the Phase 0.0 stub. The first section is carried verbatim from the decisions log (§P) and is locked; the second section is the direction's own principles, binding once the Chief commits this file.

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
The control that signs is flat blue with black type, deliberate by construction (two presses; hold is an enhancement), never glossy, never animated, never focused by default, never pressed before the container answers. Everything decorative stays away from it.

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
WCAG 2.2 AA; contrast verified per canvas; full keyboard operation; visible 2 px focus; hit targets ≥ 44 px on acts; live regions announce time at intervals, never every second; colour never carries meaning alone.

**12. Both UIs, one tokens file.**
`spec/design/tokens.css` is A2's one code artifact. The lifeboat consumes it as CSS variables; the flagship maps it into Tailwind and the shadcn bridge. The platform consumes; it never forks.

**13. The spec is exhaustive; a gap is a defect.**
Every screen spec names every region and every state that can apply to it — empty, loading, ready, waiting, confirming, in-flight, approved, denied, expired, invalid, lapsed, quota, quarantined, unreachable, offline, error, stale, partial — with verbatim copy, colour, focus and screen-reader behaviour, the audit event, and the lifeboat-vs-flagship difference. Every component pick names a primary and a fallback, what to take and what to strip, who installs it, and its licence status. One test fixture exists per state, and conformance checks for them. Every gap becomes a round-trip issue later; every decision made in the studio is one the builders never have to guess at. *(Chief, 2026-09-13.)*

---

## Sources and anti-references

Direction seeds (see `DESIGN-SOURCES.md`): Neo Brutalism — structure only; Swiss Red — the alarm only. Declined on the record: neon/acid palettes (yellow makes trust harder); the terracotta-on-warm-white and neutral-Geist defaults (the two most-remixed registry themes: generic); sci-fi and hacker faces (Orbitron, VT323); glow; orbital spectacle for the onion; glossy controls.
