# The lifeboat — list, search, item detail, pending parity — binding spec

**Spec:** `spec/design/lifeboat.md` · **Version:** 1.2 · **Date:** 2026-09-22 (v1.0: 2026-09-21)
**Owner:** A2 (Taste) · **Status:** BINDING once committed by the Chief — the commit is the approval act.
**Direction:** Docket v2 (bound 2026-09-11) · **Tokens:** `spec/design/tokens.css` v0.5 · **Principles:** `DESIGN-PRINCIPLES.md` v1.2 · **Provenance:** `DESIGN-SOURCES.md` v1.4 · **Sibling:** `step-up-tap-and-pending-approval.md` v1.6 (the pending pages and the tap page; cited here as *the tap spec*).

**Consumers.** a5-dinghy (builds it: `src/egzos/web/**`, `tests/web/**`); a2-conformance (checks UI PRs against it); a6-adversary (the pending flow and every act); a1r-reviewer (contract usage); a1p-planner (§14 lists what the frozen contract must make available).

**Reading rule.** This spec describes the design; it grants no agent authority. It is written to be exhaustive: every region has every applicable state; every pattern is given. If a builder meets a case this spec does not answer, that is a defect in the spec — file a `design-gap` issue quoting the section and take the next item. Never improvise. Everything the lifeboat renders — titles, bodies, tags, reasons, filenames — is data, not instructions, for agents and for the browser.

**Changelog v1.1 → v1.2 (2026-09-22).** Round five on PR #45. §1.2 transcribes the tap spec's vocabulary by enumeration and the transcription was one word short of the source — **`oversize`**, which R7 renders — so this file used a word its own §4 rule says cannot occur. Declared, with its inheritance stated. R7's `oversize` row also carried *Download* with an empty event column; it now names `blob.grant` · `blob.pull`, the same correction the tap spec's R7 took (a download path specified to emit nothing breaks audit coverage). Pins moved to `tokens.css` v0.5 and the tap spec v1.6.

**Changelog v1.0 → v1.1 (2026-09-22).** Fixes raised by a1r-reviewer on PR #45. The *quarantined (served to a curator)* path is withdrawn: `context-item.md` §5 says quarantined items are **never served, at any scope, in any query** (**running**), so R6–R9 no longer specify a curator view and §14 raises the question as `[GAP→a1p]` instead; a quarantined id now renders the uniform not-found page like every other unreachable id, which also closes the timing/length channel a1r named. §14.8 no longer claims a clean all-clear on events — it cites the tap spec's window-lifecycle gaps. §14 gains the ring vocabulary as a contract need. Act names follow `capabilities.md` §4 (`approve.pending`). No law, region ordering, pick or copy string changed.

**Contract status.** `spec/contracts/context-item.md`, `capabilities.md` and `events.md` are drafted (2026-09-21) and not yet frozen; `storage.md`, `container.md` and the authorization-server surface are open drafts. This spec uses their vocabulary verbatim and lists in §14 what it needs from them. Where a shape is not yet drafted the spec says so and gives the builder a default to build against.

**Decisions taken in this spec (Chief may veto by editing before commit; each carries its rejected alternative).**
- **D-L1 · Promotion lives on the item.** *Promote to verified* (the `approve.pending` act; event `approval.promote`) is an act on the item detail page, not a third kind of row in the pending queue. Rejected: listing every unverified item in pending — every agent write would land in the queue, drowning the proposals that actually asked for a human, and turning "pending" from *an agent asked* into *a backlog*. Cost of the choice: promotion is found by search (`trust:unverified`), not by a queue count.
- **D-L2 · The lifeboat speaks the CLI's `find` grammar.** One grammar, learned once; the search box is a text field whose contents are passed to the contract's find surface verbatim. Rejected: a lifeboat-only simplified grammar (two grammars to document; drift). Cost: the grammar is a1p's to freeze (§14.1); until then the box accepts free text and the prefixes in §2.2.
- **D-L3 · Home is search with recent items already listed.** `/` renders the search box and the viewer's most recently updated items. Rejected: an empty search box (a blank first screen for the one user who has nothing but the container). Cost: the first render costs one viewer-scoped list read (`context.fetch`, audited like any read).

---

## 0. Scope

The lifeboat is the open core's own UI (`egzos web`): server-rendered, in-process with the container, FastAPI + Jinja + htmx, no JS toolchain, no catalogue components, tokens as CSS variables only. Its mandate is *list, search, pending* — a user with nothing but the container still has hands. It is exempt from catalogue polish (gitk-ugly stands) but not from the laws: two colours, structure not colour, trust as a shape, silence-not-errors, unverified-by-default, exhaustive states, canonical copy.

Pages in this spec: **home / search** (`/`), **item detail** (`/items/<id>`), the **uniform not-found page**, the **scheme switch**. The **pending pages** (`/pending`, `/pending/<id>`) and the **tap page** (`/tap/<token>`) are owned by the tap spec; §11 here fixes the *parity rule* and the lifeboat-specific deltas.

Not covered: the consent page (`consent.md`), moves (CLI `mv` in v0.1; no drag in the lifeboat), quarantine lifting (CLI `curate`), the audit view (CLI `audit`), token management (CLI `token`), the onion graph, the flagship app shell.

## 1. Vocabulary

### 1.1 Domain (contract vocabulary; binding as used here)
- **Item** — a ContextItem: `id` (ULID) · `kind` · `scope` (node id — a location, not an identity) · `key` · `content` · `tags` · `provenance {actor, principal, client, derived_from, imported_from, approved_by}` · `trust {status, …}` · `lifecycle {created_at, updated_at, version, tombstoned?}` · `visibility {ring}`.
- **Kinds** — exactly `memory · preference · skill · artifact · integration · alias · rule`. Rules serve verified-only at every scope.
- **Trust status** — exactly `unverified | verified | quarantined`. Writes land unverified, human and agent alike. Promotion is human-only. Quarantined items are never served in any query; quarantine propagates along `derived_from`.
- **Scope path** — the node id rendered as `ring:name` (`project:atlas`), with its ring from `visibility.ring`. Rings: thread → project → team → org → enterprise → exo → uxo → global (uxo undefined; the list must render an unknown ring name verbatim).
- **Auto-title** — every item carries `content.auto_title` and `content.title_engine`; the lifeboat shows the title and, in meta, the engine (`titled by <engine>`), so a degraded title can be told from an embedding-backed one.
- **Blob grant** — above `blobs.inline_max_bytes` (default 64 KiB) a fetch of an artifact carries a `BlobGrant` descriptor, minted by Trust (`blob.grant`), redeemed at the REST door (`blob.pull`). The lifeboat never receives bytes on the item; `text/*` at or below the threshold arrives `inline`.
- **Viewer** — the interactive principal whose session renders the page. Every list, count and search is viewer-scoped.

### 1.2 States (the same words as the tap spec §1.2; two added)
`empty · loading · ready · waiting · confirming · in-flight · approved · denied · expired · invalid · lapsed · quota · quarantined · unreachable · offline · error · stale · partial` as defined there, plus:

| state | meaning |
|---|---|
| `no-results` | a query returned nothing for this viewer (distinct copy from `empty`; identical shape) |
| `tombstoned` | the item was deleted; it renders as the uniform not-found page |
| `oversize` | an artifact exceeds the deployment's preview limit: metadata and *Download*, no inline render. **Inherited from the tap spec §1.2, which declares it** (v1.5); listed here because R7 renders it and §4's rule is that an unlisted state cannot occur |

Lifeboat notes: `loading` does not occur — the server renders complete pages; `offline` does not occur — the lifeboat *is* the container; `unreachable` does not occur — in-process; store or grant failures are `error`. `stale` occurs only as *next request shows the new state*. Colour of a state is fixed: **red** = `quarantined`, `quota`, `lapsed`, `error`; **ink** = everything else.

## 2. Home / search (`/`)

### 2.1 Information architecture
Single column, max 1180 px, page frame `--egz-off-lg`. Top to bottom: **shell** (§4 R1) · **search** (R2) · **results header** (R3) · **results list** (R4) · **pagination** (R5). No sidebar, no onion, no drag. The page is a GET: `/?q=<query>&cursor=<opaque>`; an empty `q` lists recent items.

### 2.2 The search box
`<form role="search" method="get" action="/">` with one text input, labelled *Search*, placeholder `kind:rule scope:project:atlas vendor`, and a *Search* button (ink). The contents go to the contract's find surface verbatim (D-L2). Prefixes the UI documents under the box as mono hints (§13 `search.hints`): `kind:` · `scope:` · `trust:` · `tag:` · `key:` · `ring:`; free text searches title and body. Results are viewer-scoped; a prefix naming a scope the viewer cannot see behaves exactly like a scope that does not exist (`no-results`). A grammar error is the viewer's own mistake and may be named (§13 `search.invalid`) — it never names a scope, id or count.

### 2.3 Results header
`Recent · N items` when `q` is empty; `Results · N` for a query; `N` is the viewer-scoped total when the contract provides one, otherwise the header shows `Results` with no number (never an estimate). Sort: `updated_at` descending; a query's relevance order is the contract's when it returns one, shown as `sorted by relevance` in the header.

### 2.4 Result row
One `<li>` per item, a link to `/items/<id>`. Anatomy, left to right, wrapping below 700 px: **kind** (mono caps) · **title** (`auto_title`, or `key` if titled empty, else `(untitled)`; one line, ellipsis) · **scope path** (mono, `project:atlas`) · **stamp** (trust word, §7 shape) · **age** (`4 min ago`). Second line (13 px, `--egz-ink-3`): `agent:<actor>` or `<handle>` · `v<version>` · tags as mono words with `#`. Rows carry hairlines only.

## 3. Item detail (`/items/<id>`)

### 3.1 Sections in order
**header** (reference, title, scope path, stamp) · **content** · **provenance** · **trust** · **lifecycle** · **tags and key** · **acts**. Everything renders on one page; sections longer than one viewport get a `Show all` reveal (§5 constants) implemented as a re-render with `?full=1` — no JS required.

### 3.2 Header
Reference line, mono caps: `ITEM 01J7Q4N8 … M3KD · memory · v3`. Title as `<h1>`: the `auto_title` (sentence case as stored; never re-cased), max 2 lines. Under it: `in project:atlas · ring project` (the scope path is a link to `/?q=scope:project:atlas`) · `titled by <engine>` · the trust stamp.

### 3.3 Content
- **Text kinds** (`memory, preference, skill, integration, alias, rule`): `content.body` in a `<pre class="body">` with `white-space: pre-wrap` — escaped, never rendered as HTML or Markdown, never interpreted. Above 4 000 characters: first 4 000 + `…` + *Show all*.
- **Artifact**: a metadata table `filename · size · mime · sha256` (§5 formats), then: `inline` present → the bytes in `<pre>` (they are `text/*` by contract); `image/*` → `<img>` from the grant URL inside a 2 px frame, max-height 60 vh; `application/pdf` → `<object>` from the grant URL with *Download* inside as fallback; anything else → *Download* only. The grant is minted for this render (`blob.grant`) and redeemed on use (`blob.pull`); the line `served by grant · expires HH:MM:SS` sits under the frame.
- Quarantined item: no body, no preview, no download; the trust section carries the red stamp, `reason` and `at`.

### 3.4 Provenance · trust · lifecycle · tags
Three `<dl>` blocks. Provenance: `actor` · `principal` (`interactive` / `client`) · `client` · `derived_from` (a link to `/items/<id>` — see R8 for when the link is absent) · `imported_from` · `approved_by`. Nulls render `—`, never blank. Trust: `status` as the stamp plus, for verified, `promoted HH:MM:SS · manifest sha256 <prefix…>`; for quarantined, `quarantined HH:MM:SS · <reason>` (the reason is data: escaped, max 480 chars, *Show all*). Lifecycle: `created` · `updated` · `version`. Tags as mono `#tag` words; `key` in mono or `—`.

### 3.5 Acts
- **Promote to verified** — present only when `trust.status = unverified` and the viewer is `principal: interactive`. The human-only act `approve.pending` (`capabilities.md` §4; event `approval.promote`): the two-step control of the tap spec §2.3 (*Promote to verified* → *Confirm promotion*, 10 s arm), and when the container requires presence it opens `/tap/<token>` as a page and returns to `/items/<id>` on completion. Outcome renders in place: *Promoted at HH:MM:SS by <user>. Served as verified from now on.* Event `approval.promote`. Nothing about this act may be batched, remembered or defaulted.
- **Download** — artifacts; ghost; `blob.pull`.
- There is no *Delete*, *Move*, *Edit*, *Lift quarantine* in the lifeboat v0.1 (CLI). No screen may imply they exist here.

## 4. Regions × states — the matrix

Each region lists every state that can apply to it. A state not listed for a region cannot occur there (if it does, the spec is wrong: file `design-gap`). Copy is verbatim (§13). "Event" is the drafted taxonomy name (`spec/contracts/events.md`).

### R1 · Shell (container line, viewer line, nav, `<title>`)
| state | renders | colour | a11y | event |
|---|---|---|---|---|
| ready | `egzos · container <name> · <host:port>` · `you · <user> · principal: interactive · present since HH:MM (UTC−07:00)` · nav `search` · `pending · N` (N viewer-scoped; when N = 0 the word `pending` alone) · scheme switch (R10) | ink | `<header>`; nav is `<nav aria-label="egzos">`; current page `aria-current="page"` | — |
| ready (window open) | after the viewer line: `window open · <source> → <destination> · closes HH:MM:SS` (text only; no beam in the lifeboat) | ink | `role="status"` | — |
| ready (window lapsed, undismissed) | same line, red: `presence lapsed at HH:MM:SS` until the next act or next tap | red text | `role="status"` | — |
| error | shell renders; body replaced by R12 error card | red card | `role="alert"` | — |

### R2 · Search box
| state | renders | colour | a11y | event |
|---|---|---|---|---|
| ready (no query) | empty input, hints line | ink | `<form role="search">`, `<label for>` *Search* | — |
| ready (query) | input pre-filled with `q` verbatim (escaped); hints line; a *Clear* link to `/` | ink | — | — |
| invalid (grammar) | input pre-filled; under it in ink-2: *That query isn't valid. Check the prefixes below.*; results area shows nothing | ink | `aria-describedby` → the message; `role="status"` | — |
| in-flight | does not occur (full page GET) | — | — | — |

### R3 · Results header
| state | renders | colour | a11y |
|---|---|---|---|
| ready (recent) | `Recent · N items` | ink | `<h2>` |
| ready (query, counted) | `Results · N` (+ `· sorted by relevance` when the contract says so) | ink | `<h2>` |
| ready (query, uncounted) | `Results` | ink | — |
| empty / no-results | header without a number | ink | — |
| partial | header shows the total when known; the list shows the page | ink | — |

### R4 · Results list and rows
| state | renders | colour | a11y | event |
|---|---|---|---|---|
| ready | `<ul>` of rows per §2.4 | ink | list semantics; each row one link | `context.fetch` (list read) |
| empty (no query, nothing fetchable) | *Nothing here yet. Items you can fetch will appear here.* | ink | — | `context.fetch` |
| no-results (query) | *No results.* — identical layout, status and timing whether the query named a real scope or not | ink | `role="status"` | `context.fetch` |
| partial | 50 rows + R5 | ink | — | — |
| row · unverified / verified | stamp outline / solid | ink | stamp text is the word | — |
| row · quarantined | **does not occur** — quarantined items are never served in a query; if received, the row is omitted and a `design-gap` is filed | — | — | — |
| row · tombstoned | does not occur (not served) | — | — | — |
| row · long title | one line, ellipsis; full title in `title` attribute | ink | — | — |
| row · unknown ring | ring word rendered verbatim (the onion grows) | ink | — | — |
| error | list hidden; R12 card | red | — | — |

### R5 · Pagination
| state | renders | a11y |
|---|---|---|
| partial | one link *Next 50* → `/?q=…&cursor=<opaque>`; no page numbers, no total pages | `<nav aria-label="More results">`, ≥ 44 px |
| ready (last page) | no link | — |
| invalid cursor | renders the first page (never an error that reveals the cursor's contents) | — |

### R6 · Detail header
| state | renders | colour | a11y | event |
|---|---|---|---|---|
| ready | reference · `<h1>` title · scope path link · `titled by <engine>` · stamp | ink | `<main>`; `<h1>` first focus | `context.fetch` |
| ready (untitled) | `<h1>` is `key`, else `(untitled)` in ink-3 | ink | — | — |
| ready (unknown kind) | cannot occur (kind is a closed enum); if received, the uniform not-found page | — | — | — |
| tombstoned / not-found / not-yours | the **uniform not-found page** (R12) — identical status, length class and timing | ink | — | (no event that distinguishes) |
| quarantined | **does not occur** — quarantined items are never served, at any scope, in any query (`context-item.md` §5, **running**). A request for a quarantined id renders the **uniform not-found page** (R12), indistinguishable in status, length class and timing class from not-found, not-yours and tombstoned. Reserved pending §14.9 `[GAP→a1p]`: if the freeze gives `curate` a read path to a quarantined item, this row and R7–R9's reserved rows become live in a spec revision — never by a builder's choice | ink | — | (no event that distinguishes) |

### R7 · Content
| state | renders | colour | a11y | event |
|---|---|---|---|---|
| ready (text, ≤ 4 000 chars) | `<pre class="body">` | ink | `aria-label="Body"` | — |
| partial (text, > 4 000) | first 4 000 + `…` + *Show all* (→ `?full=1`) | ink | link, `aria-expanded` semantics via the re-render | — |
| ready (artifact, inline) | metadata table + `<pre>` of the inline bytes | ink | — | — |
| ready (artifact, image) | metadata + `<img>` in frame + *Download* + grant line | ink | `alt` = filename | `blob.grant` on render; `blob.pull` on load |
| ready (artifact, pdf) | metadata + `<object>` in frame + *Download* inside | ink | — | `blob.grant`; `blob.pull` on load |
| ready (artifact, other) | metadata + *Download* | ink | — | `blob.grant`; `blob.pull` on click |
| error (grant) | metadata + *Download unavailable.* (no button) | ink-3 | `role="status"` | — |
| oversize (> deployment preview limit) | metadata + `<size> exceeds the preview limit (<limit>).` + *Download* | ink-3 | — | `blob.grant` · `blob.pull` on download (tap spec R7, same reasoning: the bytes are served, so the pull is audited) |
| quarantined | **reserved, does not occur** (R6). If §14.9 resolves in favour of a `curate` read path, this renders *Content withheld: this item is quarantined.* — no body, preview or download | red | `role="status"` | — |
| empty (body empty string) | `(empty)` in ink-3 | ink | — | — |

### R8 · Provenance · trust · lifecycle · tags
| state | renders | colour | a11y |
|---|---|---|---|
| ready | three `<dl>`; nulls as `—` | ink | `<dt>`/`<dd>` pairs |
| ready (derived_from visible) | id as a link to `/items/<id>` | ink | — |
| ready (derived_from not visible or tombstoned) | id as plain mono text, **no link, no note** — identical for both cases | ink | — |
| ready (verified) | stamp solid; `promoted HH:MM:SS · manifest sha256 <prefix…>` · `approved_by <handle>` | ink | — |
| ready (unverified) | stamp outline; no promotion line | ink | — |
| quarantined | **reserved, does not occur** (R6). If §14.9 resolves in favour of a `curate` read path, this renders the red stamp with `quarantined HH:MM:SS · <reason>` (escaped; > 480 chars → *Show all*) | red | `role="status"` |
| ready (no tags) | `—` | ink-3 | — |

### R9 · Acts (detail)
| state | Promote to verified | Download | a11y |
|---|---|---|---|
| ready (unverified, interactive) | enabled, `--egz-act` | per kind | ≥ 44 px; focus order Promote → Download |
| ready (verified) | absent | per kind | — |
| ready (client principal) | cannot occur — the lifeboat is served to interactive sessions only (§14.6); if it does, absent | — | — |
| confirming | replaced in place by *Confirm promotion* for 10 s | enabled | `aria-live` *Press again to confirm.* |
| in-flight | *Promoting…* pressed, disabled | disabled | `aria-busy` |
| presence required | the container answers *step-up required* → the page redirects to `/tap/<token>`; on return, the outcome renders | — | focus to the outcome |
| approved (promoted) | acts replaced by *Promoted at HH:MM:SS by <user>. Served as verified from now on.* | — | `role="status"` |
| lapsed (window expired mid-act) | red line *Presence lapsed at HH:MM:SS. Nothing changed. Sign again to continue.*; acts return un-armed | enabled | `role="status"` |
| invalid (item changed under the act: version mismatch) | *This item changed. Reload to see it.*; acts disabled until reload | — | `role="status"` |
| error (act failed) | reverts to ready; red line *That didn't go through. Nothing changed. Try again.* | enabled | `role="status"` |
| quarantined | **reserved, does not occur** (R6); if live, no acts | — | — |

### R10 · Scheme switch
| state | renders | a11y |
|---|---|---|
| ready | `<form method="post" action="/prefs">` with three buttons `light` · `dark · neutral` · `dark · violet`; current one pressed (offset collapsed) | `aria-pressed`; ≥ 44 px |
| after post | 303 back to the referring page; cookie `egz-scheme` ∈ {light, dark-neutral, dark-violet}; `<html data-scheme data-canvas>` set server-side | — |
| no cookie | `<html>` without `data-scheme` → tokens.css `prefers-color-scheme` fallback | — |
| invalid cookie value | treated as no cookie | — |

### R11 · Pending pages and tap page (parity)
Owned by the tap spec (§3, §4 R1–R12, §18). The lifeboat renders them exactly as that spec's *L* column says. Lifeboat-specific deltas, binding here:

| flagship capability (tap spec) | lifeboat equivalent | rule |
|---|---|---|
| new items pill (arrival) | re-render on next request | parity by refresh; no motion |
| local countdown + beam | `closes HH:MM:SS` text; fragment refresh every 15 s via htmx | no client clock |
| hold-to-confirm enhancement | not offered | two-step baseline only |
| segmented filters, search within pending | not offered in v0.1 | parity is *functional*: every proposal reachable and actionable, not every affordance |
| PDF Viewer component | `<object>` + *Download* | — |
| consequence slider, staging folder reveal | static text and list | — |
| skew note `(container clock)` | not needed (server time only) | — |

**Parity rule.** When the flagship gains a *pending capability* (a new act, a new state, a new kind of proposal), a5-dinghy receives a pending-parity issue and the tap spec's L column is revised first. Parity is functional, never visual.

### R12 · Global failures and the uniform not-found page
| state | renders | colour | a11y |
|---|---|---|---|
| error (store, grant service, template) | card `error` · *Something went wrong on the container. Nothing changed. Try again.* + *Retry* (a link to the same URL) | red 2 px + red offset | `role="alert"`; never a code, path or exception text |
| not-found / not-yours / tombstoned / quarantined / unknown id format | **one page**: heading *Nothing here.*, body empty, nav intact; same status code, same length class, same timing class for all **five** | ink | `<h1>` |
| quota (viewing an item written by an agent at quota) | does not occur on these pages (quota gates new proposals; see the tap spec R12) | — | — |
| unreachable / offline | do not occur (in-process) | — | — |

## 5. Interaction constants, formats, layout, print

**Constants.** Results page size **50** · body cut **4 000 chars** · reason cut **480 chars** · title max **2 lines** (detail) / **1 line** (row) · preview max height **60 vh** · two-step arm **10 s** · pending fragment refresh **15 s** · all durations from `tokens.css` (the lifeboat uses only `--egz-motion-state`, which is 0).

**Formats.** As the tap spec §5: `HH:MM:SS` 24-hour local, zone once in the viewer line; ages `just now` · `N min ago` · `N h ago` · `N d ago`; sizes `2.4 MB` (binary, one decimal); ids `01J7Q4N8 … M3KD` with the full id in `title` and in a `<code>` for copy; hashes `sha256 9f3c…e1a7`; principals `agent:<name>` / handles; kinds and rings lowercase mono. Versions `v3`. Counts are integers, never rounded, never "many".

**Layout.** Max 1180 px centred; single column; below 700 px the row wraps to two lines and the `<dl>` blocks stack. Spacing from `--egz-sp-*` only: section gap `--egz-sp-5`; block padding `--egz-sp-4 --egz-sp-5`. The page frame carries `--egz-off-lg`; the content frame, state cards and acts `--egz-off`; rows and `<dl>` none.

**Print.** Records print: acts omitted; `<pre>` bodies print in full (the cut is a screen affordance — print ignores `?full`); the reference, scope path, stamps and provenance print; red states print red; footer `printed HH:MM:SS · <container>`. No page prints a count of what the viewer cannot see.

**Language.** en-US; strings from §13 only, one place in the codebase (`src/egzos/web/strings.py` or equivalent — a5's call).

## 6. Colour law
Two colours. **`--egz-act`** only on *Promote to verified* / *Confirm promotion*, keyboard focus, and the scope-path link's underline on hover. **`--egz-alarm`** only for `quarantined`, `lapsed`, `error`, `quota`. Everything else is ink on canvas. No yellow, lime, amber or acid anywhere; no warning tier.

## 7. Structure law
As the tap spec §7. Stamps: `verified` solid ink fill, `unverified` ink outline, `quarantined` red outline with red text; the word is always the content. Rows: hairlines only. The search box is a 2 px ink field with no offset; its button carries the offset. Pressed = translate by the offset, offset removed. Disabled = ink-3 text, `--egz-rule-soft` border, no offset.

## 8. Type
IBM Plex Sans (UI) and IBM Plex Mono (ids, kinds, scope paths, principals, hashes, timestamps, tags, versions, hints). Scale as the tap spec §8. `<pre class="body">` is mono at `--egz-fs-3`, `--egz-lh`, pre-wrap.

## 9. Motion law
**The lifeboat has no motion** beyond the pressed offset. No transitions, no skeleton shimmer, no fades on htmx swaps (`hx-swap="outerHTML"` with no `settle` class animation).

## 10. Silence-not-errors — on these pages
- Every count (`N items`, `Results · N`, `pending · N`) is viewer-scoped. Never "N hidden", never a lock icon, never "access denied", never a disabled row.
- `no-results` for a query naming an invisible scope is identical — shape, status, timing — to a query naming a non-existent scope.
- Not-found, not-yours, tombstoned and malformed ids render one page (R12).
- `derived_from` and `imported_from` ids the viewer cannot open render as plain text with no link and no explanation.
- `error` never carries a code, id, path or message from the container.
- Search queries never appear in a `Referer`: every lifeboat page sends `Referrer-Policy: no-referrer`.

## 11. Unverified-by-default — on these pages
Every row and every detail carries the trust stamp. Promotion is the only path from outline to solid and it is a human act with presence. The serving policy (rules verified-only; other kinds per container policy) is the contract's; the lifeboat shows what it is served and never filters trust client-side.

## 12. Accessibility

### 12.1 Baseline
WCAG 2.2 AA; contrast per the tap spec §12.1 in all three canvases; focus ring `--egz-focus` offset 3 px; hit targets ≥ 44 px on acts, pagination and the scheme switch. Landmarks: `<header>` (shell), `<nav aria-label="egzos">`, `<form role="search">`, `<main>`, `<nav aria-label="More results">`. `<h1>` is the item title on detail and *Search* (visually the box's label) on home. Red states carry `role="status"` or `role="alert"` (R12). No icon-only controls; every stamp carries its word. Works with JS disabled (htmx is an enhancement).

### 12.2 Keyboard map
| key | where | does |
|---|---|---|
| Tab / Shift+Tab | everywhere | shell nav → search → rows → pagination (home); heading → scope link → content → provenance links → acts (detail) |
| Enter | search input | submits the query |
| Enter / Space | result row | opens the item; focus lands on its `<h1>` |
| Enter / Space | *Show all*, *Next 50*, scope path | follows the link (re-render) |
| Enter / Space | *Promote to verified* | arms (→ *Confirm promotion*); second press promotes |
| Escape | while confirming | disarms; focus stays |
| Enter / Space | scheme switch button | posts the preference |
| / (optional) | home | focuses the search input; never the only way |

## 13. Copy — canonical strings (complete)
| key | string |
|---|---|
| shell.container | `egzos · container <name> · <host:port>` |
| shell.viewer | `you · <user> · principal: interactive · present since HH:MM (UTC−07:00)` |
| shell.window | `window open · <source> → <destination> · closes HH:MM:SS` |
| shell.lapsed | `presence lapsed at HH:MM:SS` |
| nav.search | `search` |
| nav.pending | `pending · N` / `pending` |
| search.label | `Search` |
| search.placeholder | `kind:rule scope:project:atlas vendor` |
| search.button | `Search` |
| search.clear | `Clear` |
| search.hints | `kind: · scope: · trust: · tag: · key: · ring: — free text searches titles and bodies` |
| search.invalid | `That query isn't valid. Check the prefixes below.` |
| results.recent | `Recent · N items` |
| results.count | `Results · N` |
| results.uncounted | `Results` |
| results.relevance | `sorted by relevance` |
| results.empty | `Nothing here yet. Items you can fetch will appear here.` |
| results.none | `No results.` |
| results.next | `Next 50` |
| row.untitled | `(untitled)` |
| row.meta | `<actor> · v<version>` |
| item.ref | `ITEM <id> · <kind> · v<version>` |
| item.scope | `in <scope> · ring <ring>` |
| item.titled | `titled by <engine>` |
| section.content | `content` |
| section.provenance | `provenance` |
| section.trust | `trust` |
| section.lifecycle | `lifecycle` |
| section.tags | `tags and key` |
| content.more | `Show all` |
| content.empty | `(empty)` |
| content.grant | `served by grant · expires HH:MM:SS` |
| content.download | `Download` |
| content.unavailable | `Download unavailable.` |
| content.oversize | `<size> exceeds the preview limit (<limit>).` |
| content.quarantined | `Content withheld: this item is quarantined.` |
| meta.filename | `filename` · meta.size `size` · meta.mime `type` · meta.sha `sha256` |
| prov.actor | `actor` · prov.principal `principal` · prov.client `client` · prov.derived `derived from` · prov.imported `imported from` · prov.approved `approved by` |
| prov.null | `—` |
| trust.promoted | `promoted HH:MM:SS · manifest sha256 <prefix…>` |
| trust.quarantined | `quarantined HH:MM:SS · <reason>` |
| life.created | `created` · life.updated `updated` · life.version `version` |
| act.promote | `Promote to verified` |
| act.promote.confirm | `Confirm promotion` |
| act.promote.sr | `Press again to confirm.` |
| act.promote.inflight | `Promoting…` |
| act.promoted | `Promoted at HH:MM:SS by <user>. Served as verified from now on.` |
| act.lapsed | `Presence lapsed at HH:MM:SS. Nothing changed. Sign again to continue.` |
| act.invalid | `This item changed. Reload to see it.` |
| act.error | `That didn't go through. Nothing changed. Try again.` |
| scheme.light | `light` · scheme.darkNeutral `dark · neutral` · scheme.darkViolet `dark · violet` |
| notfound.title | `Nothing here.` |
| fail.error | `Something went wrong on the container. Nothing changed. Try again.` |
| fail.retry | `Retry` |
| print.footer | `printed HH:MM:SS · <container>` |
| title.home | `egzos · search` · title.item `egzos · item` · title.notfound `egzos` |

A5 renders these verbatim. `<title>` never carries an item title, id, scope or count. New strings require a spec revision.

## 14. What this spec needs from the container contract (inputs to the freeze)
1. **Find** (`storage.md` / `container.md`): a viewer-scoped query surface taking the CLI's `find` grammar verbatim (D-L2) — free text plus at least the prefixes `kind:`, `scope:`, `trust:`, `tag:`, `key:`, `ring:` — returning items, an opaque cursor, an optional viewer-scoped total, and whether the order is relevance. **[OPEN→a1p]** the grammar itself; the UI renders whatever the CLI accepts.
2. **Recent** (D-L3): the same surface with an empty query ordered by `updated_at` desc.
3. **Item read**: the full ContextItem for an id the viewer covers with `fetch`; **one uniform failure** for not-found / not-covered / tombstoned / malformed (status, shape and timing indistinguishable).
4. **Blob grant** for an interactive viewer rendering an artifact; the deployment's preview size limit; `blob.grant` and `blob.pull` audited separately (F5).
5. **Promote** (`approval.promote`): an act taking the item id and `lifecycle.version` (optimistic — mismatch → `invalid`), refusing non-interactive principals, and either completing or answering *step-up required* with a tap token (the tap spec §14.3); outcome and timestamps from the container's clock.
6. **The lifeboat's viewer identity.** Phase 4 (lifeboat) precedes Phase 5 (the authorization server). **[OPEN→a1p]**: how `egzos web` establishes `principal: interactive` before the AS exists. Default this spec is written against: the lifeboat binds to localhost and serves the owner's interactive session; presence for human-only acts still goes through the tap page. The spec does not change when the AS lands — only the login does.
7. **Scheme preference** is UI-local (a cookie); no contract need.
8. **Events used**: `context.fetch` (list and detail reads), `blob.grant`, `blob.pull`, `approval.promote` (the `approve.pending` act), `step_up` (reserved). Every event this spec's **own** surfaces need exists in the drafted taxonomy — but R1 renders `window open · … closes HH:MM:SS` and `presence lapsed at HH:MM:SS`, and R9 has a `lapsed` state, so this spec inherits the window-lifecycle gaps the tap spec raises in its §14.5: `window.opened` / `window.closed` / `window.expired` are **[GAP→a1p]** there on audit-coverage grounds, and they bind here too. Not an all-clear.
9. **[GAP→a1p] Quarantined reads.** `context-item.md` §5 says quarantined items are never served, at any scope, in any query (**running**), and this spec renders the uniform not-found page for them (R6, R12). The freeze must settle whether `curate` opens a read path to a quarantined item — an owner inspecting their own container has a real need to see *why* something stopped serving — and if so, what uniform failure every other viewer gets, so the difference is not an enumeration signal. Until settled, no curator view exists in the lifeboat and lifting quarantine stays CLI (§3.5).
10. **Ring vocabulary.** §1.1 renders rings `thread → project → team → org → enterprise → exo → uxo → global`. The only enumeration in `spec/contracts/**` today is `capabilities.md` §1's `structure_floor` ∈ `{thread, project, team, org, exo}`; ring ranks belong to `container.md`, which is not drafted yet. The UI renders an unknown ring word verbatim and never sorts on a hard-coded list — **[OPEN→a1p]** the authoritative ring order and set.

## 15. A6 review notes — the attack surface of these pages
Body, title, tags, reasons, filenames rendered unescaped or as Markdown/HTML (all are data: `<pre>` and text nodes only) · htmx processing `hx-*` attributes that arrive inside item content (content must never be swapped in as HTML; `htmx.config.allowScriptTags = false`, `selfRequestsOnly = true`; the only swapped fragments are server templates) · grant URLs leaking via `Referer`, history or logs (no-referrer; single-use; short expiry; never in `<title>`) · not-found vs not-yours distinguishable by status, length or timing · `derived_from` links as an enumeration oracle · search reflecting `q` unescaped · a cookie value written into `data-scheme` unvalidated · *Promote* reachable without two presses, or without presence when the container requires it · optimistic outcome text before the container answers · version-mismatch races on promote · `Next 50` cursors that encode scope or count in the clear · the pending pages deviating from the tap spec's L column · any "remember", bulk or default-approve affordance · red used for anything but the red states.

## 16. a2-conformance checklist
Tokens only (no literal colours, radii, weights, durations) · exactly two colours, mapped per §6 · no yellow family · radius 0 · offsets only on §7 containers; hairlines in lists · no motion, no shimmer, no transitions · every string from §13 by key, verbatim · **every region renders every state in §4 and a fixture exists per state (§20)** · red paired with words · two-step act present; no hold · counts viewer-scoped · uniform not-found page · `Referrer-Policy: no-referrer` on every page · htmx only for the patterns in §18; pages work with JS disabled · no catalogue components; tokens as CSS variables only · print stylesheet per §5 · pending pages match the tap spec's L column.

## 17. Component picks
**None.** The lifeboat is exempt from the catalogue (§P). Every region is plain semantic HTML styled from `tokens.css`. Reference for structure only — not installed, not copied: the tap spec §17 for the two-step act and the stamps. DESIGN-SOURCES.md carries one row: *lifeboat — none (exempt; decided)*.

## 18. Pages, URLs and HTML/htmx patterns (a5-dinghy)

**URLs.** `/` (home; `?q=`, `?cursor=`) · `/items/<id>` (`?full=1`) · `/prefs` (POST, scheme) · `/pending`, `/pending/<id>`, `/tap/<token>` (tap spec §18). `<title>` per §13. Every response: `Referrer-Policy: no-referrer`, `Cache-Control: no-store`, `X-Content-Type-Options: nosniff`, a CSP that allows only self and inline styles from the one stylesheet.

**Patterns.** Semantic HTML; one stylesheet importing `tokens.css`; no component library, bundler or motion.
- Shell: `<header><p class="shell">egzos · container home · localhost:7420</p><p class="viewer">you · ali · principal: interactive · present since 21:29 (UTC−07:00)</p><nav aria-label="egzos"><a href="/" aria-current="page">search</a><a href="/pending">pending · 3</a></nav><form class="scheme" method="post" action="/prefs">…</form></header>`.
- Search: `<form role="search" method="get" action="/"><label for="q">Search</label><input id="q" name="q" value="…"><button>Search</button><p class="hints">kind: · scope: · …</p></form>`.
- Results: `<h2>Recent <span>· 47 items</span></h2><ul class="rows"><li><a href="/items/<id>"><span class="kind">memory</span><span class="title">…</span><code class="scope">project:atlas</code><span class="stamp stamp--unverified">unverified</span><time datetime="…">4 min ago</time></a><p class="meta">agent:claude-code · v3 · <code>#vendors</code></p></li></ul><nav aria-label="More results"><a href="/?q=…&cursor=…">Next 50</a></nav>`.
- Detail: `<main><p class="ref">ITEM 01J7Q4N8 … M3KD · memory · v3</p><h1>…</h1><p class="where">in <a href="/?q=scope:project:atlas"><code>project:atlas</code></a> · ring project · titled by <code>embed-v1</code> <span class="stamp stamp--unverified">unverified</span></p><section><h2>content</h2><pre class="body">…</pre></section><section><h2>provenance</h2><dl>…</dl></section>…<section class="acts"><form method="post" action="/items/<id>/promote">…</form></section></main>`.
- Two-step act (no JS): the first POST re-renders the page with the button as *Confirm promotion* and a hidden `arm` token valid 10 s; the second POST promotes; a *step-up required* answer redirects (303) to `/tap/<token>` with `return=/items/<id>`. With htmx: `hx-post` on the form, `hx-target` the acts block, `hx-swap="outerHTML"`.
- Artifact: `<table class="meta">…</table><figure class="frame"><object data="<grant-url>" type="application/pdf"><a href="<grant-url>" download>Download</a></object><figcaption>served by grant · expires 21:41:12</figcaption></figure>`.
- Uniform not-found: `<main><h1>Nothing here.</h1></main>` with the shell intact.
- Failure: `<section role="alert" class="card card--alarm"><p class="kind">error</p><p>Something went wrong on the container. Nothing changed. Try again.</p><a href="…">Retry</a></section>`.
- htmx (optional, only these): the pending window fragment (tap spec §18); the acts block swap. `htmx.config.allowScriptTags=false; htmx.config.selfRequestsOnly=true; htmx.config.defaultSwapStyle='outerHTML'`.

## 19. Relationship to the flagship
The flagship's search/list spec (egzos-platform) owns the app shell, command palette, filters, dense grid, drag and the onion. The lifeboat and the flagship are both clients of the same contract surfaces (§14) and render the same stamps, the same copy laws and the same silence; they share `tokens.css` and nothing else. When the flagship's search gains a capability that changes what a *pending* proposal can do, parity applies (R11); search and list capabilities do not require parity.

## 20. Test fixtures required (one per state; conformance checks their presence)
Home: recent ready (12 rows) · recent empty · query ready (counted) · query ready (uncounted, relevance) · no-results · partial (51 rows, Next 50) · invalid cursor · invalid grammar · long title row · unknown ring row · each kind once (7 rows) · each stamp once (verified, unverified). Detail: text ready · text partial (4 001 chars) · text empty · untitled · artifact inline · artifact image · artifact pdf · artifact other · grant error · oversize · verified (with promotion line) · unverified (with act) · quarantined id (renders the uniform not-found page; asserted identical to the other four causes) · derived_from visible · derived_from not visible · no tags. Acts: ready · confirming · in-flight · step-up redirect · promoted · lapsed · invalid (version) · error. Shell: ready · window open · window lapsed · pending 0 / pending 3. Scheme: no cookie · light · dark-neutral · dark-violet · invalid cookie. Global: error card · uniform not-found (**five** causes — not-found, not-yours, tombstoned, quarantined, malformed id — one fixture each, asserted identical in status, length class and timing class). Print: detail ready. Schemes: every fixture in light, dark-neutral, dark-violet.

## 21. Non-goals and open items
Moves, quarantine lifting, token management, audit view (CLI in v0.1) · filters as controls (query prefixes only) · saved searches · the onion · a conversational surface (not in the decisions log) · localisation beyond en-US · **[OPEN→a1p]** the find grammar (§14.1) and the lifeboat's pre-AS login (§14.6) · **[OPEN→CHIEF]** veto window on D-L1–D-L3 before commit.
