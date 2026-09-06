# DESIGN-SOURCES.md

**Owner:** A2 (Taste)
**Status:** Stub — rows are added as components are selected during the design track (Phase 3+).

## Purpose

This file records the provenance of every catalogue component used in a production screen, per the
inspiration canon (decisions log §P, level 4):

> DESIGN-SOURCES.md records provenance: component, registry item or URL, license, date, the spec
> that picked it.

A component without a row here is not merged. A2 fills this file when writing each screen spec;
A4 and A5 reference it when installing or implementing.

## Inspiration canon

The approved sources, in order of preference:

- **21st.dev** — the primary registry (a4s-atelier carries the 21st MCP with `API_KEY_21ST`)
- **uiverse.io** — secondary source for interactive and animation-heavy components

A component from any other source requires A2's explicit call in the spec. Third-party catalogue
MCPs run only in sessions with no merge or approval authority (§P trust rule).

## Provenance table

| Component | Registry item / URL | License | Date | Picked by spec |
|---|---|---|---|---|
| *example row — replace when first component is chosen* | *e.g. 21st.dev/r/some-component* | *MIT* | *YYYY-MM-DD* | *spec/design/lifeboat.md* |

`TODO(a2)`: Populate this table as each screen spec is committed. One row per component per
screen if the same component appears in multiple specs with different configurations.
