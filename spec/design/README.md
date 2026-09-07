# spec/design/

Design specs and system artifacts for the open-core surfaces. This directory is public from Phase 0.

## What lives here (egzos/spec/design)

Per R10 (decisions log §N), the following are public open-core surfaces:

- `DESIGN-PRINCIPLES.md` — the principles both UIs obey; owner A2 (Taste); drafted from direction
  sessions in Phase 3; stub until then.
- `DESIGN-SOURCES.md` — component provenance table (registry item, license, date, the spec that
  picked it); owner A2; filled as components are selected.
- The tokens file — the ONE code artifact A2 ships; the identity layer consumed by both the lifeboat
  (egzos/src/egzos/web) and the flagship (egzos-platform). The platform consumes it; never forks it.
- The lifeboat spec — the server-rendered in-process UI (FastAPI + Jinja + htmx; A5's build target).
- The step-up tap + pending-approval page spec — A2's first deliverable; public because the tap spec
  being public is good for trust.

## What lives in egzos-platform/spec/design

Flagship screen specs live in the private sibling `Egzos/egzos-platform/spec/design` — closed
product, closed specs. Each screen spec names every component as a registry item (license noted)
or `bespoke`. The Chief commits approved specs; the commit is the approval act.

## A2's first deliverable

The step-up tap + pending-approval page spec. This lands in this directory (public) and drives:
- Trust's implementation of the localhost tap (egzos/src/egzos/trust)
- The lifeboat's pending-approval page (egzos/src/egzos/web)
- The flagship's corresponding screen (egzos-platform/spec/design — spec only)

## How specs arrive

A2 (studio mode on Hyperagent) runs direction sessions with the Chief → produces 2–3 direction
boards with tradeoffs → Chief picks → A2 writes the binding spec → the Chief commits it to this
directory. The commit IS the approval. Agents build from committed specs only; a missing spec is a
`design-gap` issue, not an improvisation.
