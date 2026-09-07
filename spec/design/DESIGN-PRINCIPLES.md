# DESIGN-PRINCIPLES.md

**Owner:** A2 (Taste)
**Status:** Stub — A2 writes this from the direction sessions (Phase 3). The principles below are the
seed from the decisions log (§P); they are already decided and carried forward here. `TODO(a2)` marks
principles A2 will elaborate or add from the direction sessions.

---

## Decided principles (carried from decisions log §P, 2026-09-03)

These are locked; they require a contract-change-equivalent escalation to revise.

**Inspiration flows through the tokens, never around them.**
A catalogue component enters the product only after being re-themed to the egzos design tokens.
The tokens file is the identity; a component that bypasses it is not an egzos component.
*(Carried from §P: "identity guardrail: inspiration flows THROUGH the tokens, never around them.")*

**Catalogue for chrome, bespoke for the differentiators.**
Nav, tables, dialogs, forms, command palette, empty states, toasts, and other commodity UI come
from the catalogue (shadcn/ui + 21st.dev picks). The onion graph, the drag-drop gate, the triage
flow, and the permissions matrix are bespoke — they are the product; nav and tables are commodity.
*(Carried from §P: "catalogue for primitives and chrome … bespoke on A4g for the differentiators.")*

**Security surfaces stay bespoke and A6-reviewed.**
The pending-review flow, the step-up tap, the consent screen, and the drag-drop gate are security
surfaces even when assembled from catalogue primitives. A stock dialog wrapping the step-up flow
is still a security surface. A6 reviews every commit to these paths.
*(Carried from §P: "security-surface flows … stay bespoke and A6-reviewed.")*

**The lifeboat is exempt.**
The server-rendered lifeboat UI (A5; FastAPI + Jinja + htmx) consumes tokens as CSS variables and
uses no React components. It need not be visually polished; its mandate is functional parity on
the pending flow, never lagging the flagship functionally. Gitk-ugly stands.
*(Carried from §P: "lifeboat EXEMPT — gitk-ugly stands.")*

**Every pick has provenance.**
Every component used in a production screen is named in the spec that introduced it (registry item
+ license, or `bespoke`) and recorded in `DESIGN-SOURCES.md`. A component without provenance is
not merged.
*(Carried from §P: "every pick has provenance.")*

---

## TODO(a2): principles to be elaborated in Phase 3

- Interaction grammar: how the gate feels, drag-drop physics, triage flow, the onion reads.
- Information architecture for both UIs.
- Spacing, type scale, and motion — derived from the tokens file A2 ships.
- Accessibility baseline (WCAG target, keyboard nav, focus management).
- Error and empty states — voice and visual treatment.
- Mobile / responsive posture for the lifeboat.
- Any additional principles surfaced in the direction sessions.
