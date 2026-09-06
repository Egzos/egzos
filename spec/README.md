# spec/

`spec/` is a publishable artifact. It is public from Phase 0 — every file here is visible to anyone
who clones this repository, and that is intentional. The open-core trust model requires the
contracts and design surfaces to be inspectable.

## Layout

```
spec/
  contracts/   — the container contract and related schemas
  design/      — design system, principles, tokens, lifeboat spec, step-up tap + pending-approval specs
```

### contracts/

Contracts are drafted by a1p-planner from the running walking skeleton (Phase 0.2), reviewed by A6
and the Chief personally (Phase 0.3), and then frozen as law. See `contracts/README.md` for what
arrives at Phase 0.2 and the rules the freeze must honor.

**After Phase 0.3, `spec/contracts/**` is law.** Changing a frozen contract is an escalation issue
to a1p-planner, batched at phase boundaries — never a drive-by. Contract v1.1 is planned at the
Phase 5 boundary (intelligence read surface + AS metadata; reviewed by the Chief, a1p-planner,
and a6-adversary).

### design/

Design specs and principles that are open-core surfaces:

- `DESIGN-PRINCIPLES.md` — the principles both UIs obey (owner: A2; drafted from direction sessions)
- `DESIGN-SOURCES.md` — component provenance (registry item, license, date, the spec that picked it)
- The tokens file — the ONE code artifact A2 ships; consumed by both the lifeboat and the flagship
- The lifeboat spec — egzos/spec/design (public; see R10)
- The step-up tap + pending-approval page spec — public because the tap spec being public is good
  for trust (R10)

Flagship screen specs live in the private sibling `Egzos/egzos-platform/spec/design` — closed
product, closed specs (R10). The tokens file is the shared dependency across repos; the platform
consumes it, never forks it.

A2's first deliverable is the step-up tap + pending-approval page spec.

## How a contract changes

1. File a `contract-change` issue with the current text, the proposed change, and why it cannot
   wait for the phase boundary.
2. a1p-planner triages and either batches it for the next phase boundary or escalates with a reason.
3. Changes to frozen contracts require the Chief's explicit disposition — not a PR approval alone.
4. v1.1 is planned at the Phase 5 boundary; no earlier out-of-cycle version is expected.

Ambiguity about a contract clause → label `contract-change`, file the issue, and take the next item.
