# BRAND.md — the egzos identity

**Owner:** A2 (Taste)
**Status:** v1.0 · 2026-09-22 · binding on commit. Direction **D · Orb, dither** — picked by the Chief on 2026-09-22 from direction board v0.2 (four marks; studio artifact, not a repo deliverable) after a first board of three the same day. This file, the masters under `spec/design/brand/**` and the pipeline under `pipeline/` are one deliverable: the masters are what the pipeline emits, byte for byte (`pipeline/check.py --regenerate`).
**Tokens:** `tokens.css` v0.8 — a cross-PR pin: v0.8 is on PR #45 and not yet on `main`; every value this file bakes as a literal (§6) is unchanged since v0.3, which is the claim the pin turns on, re-checked here on 2026-09-22 and to be re-checked in the commit that lands after #45 merges.
**Siblings:** `DESIGN-PRINCIPLES.md` (principle 7 is the one this file must not contradict; §2.3) · `lifeboat.md` · `step-up-tap-and-pending-approval.md` · `consent.md` (each decides *whether* it places the mark; this file decides *which file* and *how large*; §19). **Provenance:** `DESIGN-SOURCES.md` (reference; rows in §22, to be appended after #45 merges — that file is on #45's branch).
**Consumers:** the Chief (GitHub uploads — org avatar, social preview, two App avatars, App badge colour; §8) · a5-dinghy (lifeboat favicon set and header mark) · a3-doorman (CLI splash, MCP icons) · a4s-atelier (flagship nav lockup, favicon set, PWA icons; catalogue: none) · a2-conformance (§16, `pipeline/check.py`) · a6-adversary (§15).
**Source:** the Chief's ink sketch of 2026-09-22 — a sphere with a quarter of its upper hemisphere removed, drawn from above-left; and, beside it, the onion. Reacted to and rebuilt as geometry with fixed numbers (§2), not vectorised.

**Decisions taken by the Chief (board v0.2, 2026-09-22)** — each with the rejected alternative and its cost, so the record shows what was given up:

| id | decision | rejected | cost of the pick |
|---|---|---|---|
| D0 | the mark is **D · Orb** — the onion as a cutaway sphere | A · Survey (rings), B · Stamp (diagonal square), C · Letter (the Plex `e`) | the only illusionistic object in a flat system; a generated mark (§2.4); 16 px is its weakest size |
| D-T | texture is **dither** — a Bayer 8×8 ordered field on the Lambert shade | contour (latitude hairlines + hatched faces), halftone (45° dot screen) | forbids anti-aliasing on the body field; fixes two field densities and a flat tier (§3) |
| D1 | **lowercase, always**: `egzos` | `Egzos` at sentence starts and as the org name | copy-editors will want to capitalise it; this file is the answer |
| D2 | **ink only** — no colour in any mark | `--egz-act` on the human element (the pending slice) | the identity has no colour to be recognised by; recognition rides on shape and the hard offset |
| D3 | the marks are **excluded from Apache-2.0** — `TRADEMARKS.md` at the repository root | marks fully Apache-2.0 with the code | a one-page policy the Chief owns; a sentence in `CONTRIBUTING.md` points at it |
| D4 | assets live in **`spec/design/brand/`** (A2's tree; no `OWNERSHIP.yml` change) | a top-level `brand/` (Chief-only `OWNERSHIP.yml` edit) | consumers copy rendered exports through their own PRs; the masters stay A2-owned |
| D5 | GitHub App avatars are **identity variants**: chief-proxy wears the whole orb, egzos-forge the orb with the slice out | no App avatars | both Apps get a white (#FFFFFF) badge background set by the Chief in each App's settings |
| D6 | the org avatar is **one file, the light record**, on both GitHub themes | a dark card | the dark badge master is used only where egzos controls the canvas |
| D7 | terminal art prints on **bare `egzos` only**; `--help` and `--version` stay text | (b) the 8-row header beside `--help`; (c) also on `--version` | a3-doorman gains a TTY / locale / opt-out check and ships one text asset |

**Decisions taken by A2 inside this file (studio, 2026-09-22)** — the Chief may veto any by editing before commit:

| id | decision | rejected | why |
|---|---|---|---|
| S1 | the size law: **flat below a 48 px sphere · 32-cell field 48–159 px · 64-cell field from 160 px** | one field at every size; flat everywhere | a 32-cell field under 48 px puts cells below 1.5 px and the field becomes grey mush; the board's 40 px figure was loosened to 48 after the 48 px MCP icon and the 48 px ICO frame aliased |
| S2 | in dither tiers the cut faces are **transparent** (the canvas shows through); in the flat tier they are **canvas-filled** | paint the faces in every tier | a dither mark sits on its canvas and never on imagery (§6.4), so transparency is exact there; the flat form must survive on an unknown background (favicon.ico in a browser tab), so it carries its own paper |
| S3 | the render pipeline is **committed** under `pipeline/` as a design tool | masters only | a generated mark that cannot be regenerated is a mark nobody can maintain; `check.py --regenerate` is the conformance test |
| S4 | two master forms: **file masters** with declared literals (for `<img>`, uploads, README) and **inline masters** with `currentColor` / `var(--egz-canvas)` (for the two UIs) | one form | a file cannot read CSS variables; a UI must not carry literals (principle 12) |
| S5 | rasters (PNG, ICO) are **not committed** here; `render.py` reproduces them and builders vendor what they need through their own PRs | commit PNGs under `spec/design/brand/` | binaries do not travel the Chief's current push path, and `spec/` holds the record, not the bytes |
| S6 | the README header is the **SVG master via `<picture>`**, not a PNG | PNG header | GitHub renders repository SVGs; text is outlined so sanitisation cannot break it (§18) |
| S7 | `mcp/icons.json` is **offered** ready for `Implementation.icons`; a3-doorman decides whether the MCP door advertises it | binding the doorman | the field is metadata, not contract; the door's `initialize` response is a3-doorman's |
| S8 | the 8-row terminal header is **reserved for image-less markdown** (the PyPI README, a code block anywhere images cannot load) | print it beside `--help` (D7 b) | PyPI can load images only by absolute URL; a fenced block of half-blocks is the mark with no hosting at all |
| S9 | the App badge background is **baked white into the file and set as the App's hex colour** | transparent file, GitHub default background | GitHub fills behind transparency with the App's hex field; baking it makes the file self-describing and the setting a belt-and-braces |

---

## §0 Scope

This file binds the egzos identity: the mark and its three states, the size and texture laws, the wordmark and lockups, the colour law for identity assets, every placement the identity has today (GitHub, browser, PWA, terminal, MCP, PyPI, the two UIs), the terminal rendering and where it prints, the canonical copy, the misuse table, the file tree, the pipeline, the a2-conformance checklist and one fixture per asset.

It does not bind: the onion graph screen (a flagship spec; §2.3), the CLI's help text or grammar (§9.5; egzos#41), whether a given page carries the mark (that page's spec; §19), egzos.io marketing surfaces (the platform repository), OS file-type icons for `.xmb` archives (§21).

## §1 Vocabulary

- **the orb** — the mark: a sphere with a quarter of its upper hemisphere removed. Three **solids**: **whole** (the record, merged), **pending** (the orb with the slice out — the symbol), **slice** (the missing quarter alone — the proposal). These are the mark's *names for its own states*; they are figurative and bind nothing in the container contract (§14). In particular *pending* here is not the trust status `unverified`, and *whole* is not `verified`; the mark says nothing about trust status.
- **tier** — which rendering of the mark a given display size gets: **64** (a 64-cell dither field), **32** (a 32-cell field), **flat** (the two-tone form). §3.
- **field** — the dithered body: a grid of square cells, each ink or empty.
- **file master / inline master** — §6.3. A file master carries declared literals and is used where a fixed file is required; an inline master carries tokens and is the only form used inside the lifeboat or the flagship.
- **badge** — the mark on a canvas card with a 2.5-unit border and a 5-unit hard offset in the 64-unit box: the shape egzos uploads wherever a square avatar is asked for. §7.
- **lockup** — the mark and the wordmark together; horizontal or stacked. §4.
- **the record** — the light scheme (ink on white). **The record at night** — the dark scheme. Both from `tokens.css`.
- **box** — the 64-unit square every mark is drawn in. The sphere spans 54 of the 64 units; *sphere px* = *box px* × 54/64.

## §2 The mark

### §2.1 Geometry (all of it)

Fixed numbers in `pipeline/orb.py`. World: unit sphere at the origin, *y* up, *z* toward the viewer. The spec's solid vocabulary (`whole · pending · slice`) maps to the geometry module's (`whole · orb · slice`): `pending` is the published stem for the `orb` solid, bridged by the `(stem, solid)` pairs in `render.py`.

| constant | value | meaning |
|---|---|---|
| wedge **W** | `{ x < 0, y > 0, z > 0 }` | the removed quarter of the upper hemisphere: front-left, as sketched |
| solids | `pending = sphere − W` · `whole = sphere` · `slice = sphere ∩ W` | §1 |
| camera | orthographic · azimuth **−35°** (toward −x, the viewer's left) · elevation **+25°** | the sketch's perspective; the camera looks at the origin |
| view vector | (−0.5198, 0.4226, 0.7424) | derived; unit vector from the origin toward the camera |
| light | (−0.4355, 0.7259, 0.5323) | unit vector; upper-left-front |
| shade | `0.18 + 0.82 · max(0, n · light)` | Lambert with an ambient floor so the dark limb still carries ink |
| cut faces | wall `x = 0` (outward normal −x) · floor `y = 0` (+y) · back wall `z = 0` (+z) | shaded by the same rule; **never drawn as a field** (§3.2) |
| box | 64 × 64 · sphere centre (32, 32) · radius **27** (spans 5 … 59) | every master |
| creases | the three axis segments from the centre to the surface: +y, +z, −x | ink strokes; §3.3 |
| cut arcs | the three quarter-circles where the cut planes meet the sphere | ink strokes; §3.2 |

### §2.2 What it depicts

The onion — the audience radius the product draws — as a solid, with one slice out. The slice is an item pending a human's disposition: a proposal at the gate, or waiting in the pending queue. Merged, the record is whole. The three solids therefore carry *agents propose, humans dispose* without a caption, and give the two GitHub App identities their avatars (D5): the human's proxy wears the whole record; the agents' forge wears the record with the slice still out.

### §2.3 What it is not — principle 7

`DESIGN-PRINCIPLES.md` principle 7: *the onion is a surveyor's diagram — concentric hairlines, centre private, rim public, nothing shaded.* That is the in-product onion screen. **The brand orb is a different drawing.** It is shaded (by quantisation, §3), it is a solid, and it appears only in the placements of §8. The onion graph never inherits the orb's field, its camera or its cut; the orb never appears as a live diagram, never carries ring labels, item marks or the quarantine mark, and is never used where the onion screen's semantics (distance = audience, never rank) could be read into it. The avatar is not a diagram. A screen that shows the orb *as* the onion is a defect against both files.

### §2.4 How it is made

The mark is generated: `pipeline/orb.py` ray-casts the geometry into a face and shade buffer; every rendering — the vector fields, the flat form, the terminal text — derives from that buffer, so they are one object, never three drawings. Changing the mark is changing a number in §2.1 and regenerating; there is no hand-drawn source. This is the cost the Chief accepted in D0 and the reason the pipeline is committed (S3).

## §3 The size law and the texture law

### §3.1 Tiers

| tier | sphere px | box px (× 64/54) | cell size | file suffix | where it lands (§8) |
|---|---|---|---|---|---|
| **64** | ≥ 160 | ≥ 190 | ≥ 2.5 px | `-64` | org avatar 512, icon-512, maskable 512 |
| **32** | 48 – 159 | 57 – 189 | 1.5 – 5 px | `-32` | App avatars 200, apple-touch 180, icon-192, MCP 96, README header, social preview, horizontal lockups at F ≥ 56 |
| **flat** | < 48 | < 57 | — | `-flat` | favicon (svg and every ICO frame), MCP 48, lifeboat header 20, nav lockup 22, minimum-size uses |

A consumer that renders a master at a size outside its tier is non-conforming, with one accepted exception: a **single uploaded file GitHub displays at many sizes** (the org avatar, the App avatars) is the tier of its *uploaded* size; GitHub's downsampling to 20 px turns the field into tone, and that tone — a grey sphere with a lighter notch — is the intended small-size read of a dither (§8.1).

### §3.2 Dither (tiers 64 and 32)

- The body is a field of *N × N* square cells over the 54-unit sphere box (*N* = 64 or 32), supersampled 4 × 4; a cell belongs to the body when ≥ 50 % of its samples hit the body.
- A body cell is **ink** when `1 − shade > Bayer8(row mod 8, col mod 8) / 64`, the standard 8×8 ordered-dither matrix; otherwise empty.
- Every body cell on the **silhouette** is ink regardless of threshold, so the limb never breaks.
- The field is emitted as run-length `<path>` rectangles with `shape-rendering="crispEdges"`. **Anti-aliasing the field is forbidden**: a rasteriser that smooths it has produced a grey sphere, not the mark.
- The **cut faces carry no field** and no fill (S2): they are transparent, and the canvas shows through. The **cut arcs** and **creases** are ink strokes: 1.2 units in the 64 tier, 1.52 in the 32 tier (`max(1.2, 0.9 × cell)`), butt caps, miter joins.
- In dark schemes the same rectangles are drawn in the dark ink; nothing else changes (§6.2).

### §3.3 Flat (tier flat)

- The visible body is one filled region in ink (traced from the 512-sample mask by marching squares and simplified with Douglas–Peucker at 0.08 units).
- The three cut faces are filled with the **canvas colour** (paper), and the three **creases** are drawn in ink at 3.0 units so the notch reads as a cut into a solid — not as a mouth (Pac-Man) or a missing bite. The cut arcs are implied by the face fills and are not stroked.
- Below **12 px** (box) the mark is not placed; it is a dot there.

### §3.4 Forbidden treatments — this is the whole list, and it is closed

gradient (linear, radial, mesh) · specular highlight · glow, bloom or outer shadow · blur · drop shadow other than the badge's hard offset · transparency ramps · any colour (D2; §6) · anti-aliased body field · a second light · a different camera, wedge, or wedge size · rotation or mirroring · perspective (the camera is orthographic) · 3-D-renderer output of any kind in place of the pipeline's · motion of any kind, including the slice returning to the sphere (motion law B: state changes are instantaneous; identity assets do not move) · a wireframe globe (latitude + longitude) · the slice as a 2-D pie wedge · a live onion diagram standing in for the mark (§2.3) · the orb drawn on top of imagery (§6.4) · text inside the mark.

## §4 Wordmark and lockups

### §4.1 Wordmark

- The word is **`egzos`**, lowercase, always (D1) — in prose, at sentence starts, in titles, in the org name where a human writes it (the GitHub slug `Egzos` is a slug, not the wordmark).
- Face: **IBM Plex Mono SemiBold** (version 2.004, release `@ibm/plex-mono@1.1.0`, OFL-1.1). The command's register: egzos is CLI-first. Default kerning and tracking; nothing adjusted.
- **Outlined.** Every wordmark master is glyph outlines, not `<text>`: no placement depends on an installed font, and GitHub's SVG sanitiser (which strips styles and blocks web fonts) cannot alter it.
- Proportions at font size *F*, as measured from the face by `pipeline/outline.py` (`hhea` ascent/descent, OS/2 `sxHeight`, advance at 1000 units/em): ascender 1.025 F · descender 0.275 F · x-height 0.516 F · advance of `egzos` 3.00 F.
- Minimum: **F = 14 px** alone; in a lockup the lockup minimum governs.

### §4.2 Lockups

| lockup | construction (F = font size of the wordmark) | minimum | file |
|---|---|---|---|
| **horizontal** | mark box = ascender height (1.025 F), left; gap 0.36 × box; wordmark baseline-aligned so the box top meets the ascender line | F = 16 (box 16.4 px → flat tier) | `lockup/horizontal*.svg` |
| **stacked** | mark box = 1.5 × ascender, centred; gap 0.45 × ascender; wordmark centred beneath | F = 20 | `lockup/stacked*.svg` |
| **nav** | the horizontal lockup at **F = 22** with the flat mark (the flagship app-shell lockup) | fixed size | `lockup/inline/horizontal-nav.svg` |

The mark in a lockup takes the tier of its own box (§3.1): flat below a 57 px box (horizontal F < 56), 32-field above. Lockup masters are emitted at F = 100 (32-field) and the nav lockup at F = 22 (flat); a consumer that needs another F regenerates through the pipeline rather than scaling the F = 100 master into the flat range.

### §4.3 Clear space

- **Symbol alone:** clear space ≥ 0.25 × sphere diameter on every side. The badge (§7) provides ≈ 0.34.
- **Lockups:** clear space ≥ 0.5 × the mark box on every side.
- Nothing enters the clear space: no text, rule, other mark or edge of a container. The badge's own card and offset are part of the mark and do not count.

### §4.4 Never

stretch or condense · kern, track or letter-space · set in any other weight or face · mixed case or capitals · replace the wordmark's `e` with the mark · the mark to the right of the wordmark · the wordmark on two lines · wordmark alone below F = 14 · lockup with a wordmark in `--egz-ink-2`/`-3` (the wordmark is always full ink).

## §5 Constants and formats

| constant | value |
|---|---|
| sizes (px) that exist | 12 · 16 · 20 · 22 (nav) · 24 · 32 · 48 · 64 · 96 · 128 · 180 · 192 · 200 · 460 (GitHub's render of the org avatar) · 512 · 1280 × 320 · 1280 × 640 |
| badge | box 64 · card outer 0…56 (`x=1.25 y=1.25 w=53.5 h=53.5`, stroke 2.5) · offset rect 5…61 (offset 5 = 2 × border, mirroring `--egz-bw : --egz-off` = 2 px : 4 px) · mark at `translate(10 10) scale(0.5625)` (36-unit box, centred on the card) |
| App avatar | box 64 · white square · mark at `translate(12 12) scale(0.625)` — GitHub crops to a circle; the 40-unit mark box sits inside the 64-unit inscribed circle's 45-unit safe square |
| maskable icon | box 64 · canvas square · mark at `translate(13.44 13.44) scale(0.58)` — the 37-unit mark sits inside the 80 %-diameter safe circle (radius 40 % = 25.6 units) |
| apple-touch-icon | box 64 · canvas square · the badge at `translate(6 6) scale(0.8125)`; opaque (iOS rounds the corners) |
| README header | 1280 × 320 · frame rect 1…1271 × 1…311 stroke 2, offset rect 8…1280 × 8…320 · mark box 98.4 px at (72, 97.6) · wordmark F = 96 · tagline F = 22 right-aligned at x = 1200, baseline 268 |
| social preview | 1280 × 640 · canvas fill · card 33…1239 × 33…599 stroke 2.5, offset 40…1248 × 40…608 · lockup F = 150 centred at y = 300 · tagline F = 24 centred, baseline 448 · url F = 22 at (72, 560) · licence line F = 22 right-aligned at 1208, baseline 560 |
| terminal cell | 1 : 2 (width : height); half-blocks give two field rows per text row; a splash of *r* rows is a (2r)² field → 2r columns |
| files | SVG 1.1, `xmlns` only, no `<style>` except `mark/favicon.svg`, no `<text>`, `<script>`, `<filter>`, `<image>`, gradients or external references · TXT UTF-8, LF, no trailing spaces, one trailing newline · JSON 2-space |
| pipeline | Python ≥ 3.9 · numpy ≥ 2.0, < 3 · matplotlib (marching squares only) · fonttools · resvg-py 0.3.2 · Pillow 11 — pinned in `pipeline/requirements.txt` |
| print | the record prints as drawn; a dither field prints as dots; below a 4 mm sphere (48 px at 300 dpi) the flat form is used |

## §6 Colour law for identity assets

### §6.1 Two colours, neither of them here

Identity assets are **ink on canvas**, in both schemes. `--egz-act` means *a human is asked to act here* and `--egz-alarm` means *something failed*; a mark asks nothing and reports nothing, so neither colour appears in any master, ever (D2). The pending slice is the one place the temptation is real — it does ask you — and it is refused for exactly that reason: a blue slice would teach that blue is brand.

### §6.2 Declared literals (file masters)

A file master is a fixed file and cannot read a CSS variable, so it carries these values, each a `tokens.css` value and nothing else. `pipeline/check.py` F-02a fails any other hex.

| literal | token | scheme | used in |
|---|---|---|---|
| `#000000` | `--egz-ink` (= `--egz-shadow-ink`) | light | ink field, strokes, wordmark, badge border and offset, App-avatar mark |
| `#FFFFFF` | `--egz-canvas` | light | flat-tier cut faces, badge card, App-avatar square, README/social canvas, apple-touch canvas |
| `#F4F4F0` | `--egz-ink` (= `--egz-shadow-ink`) | dark | dark file masters |
| `#0B0B0B` | `--egz-canvas` | dark · neutral | dark flat faces, dark badge card, README dark header, maskable dark |
| `#0B0716` | `--egz-canvas` | dark · violet | `badge/badge-dark-violet.svg` only |

`--egz-paper` is not used by any identity asset: the badge card is canvas, not paper, so the mark never sits on the secondary surface.

### §6.3 Inline masters (the two UIs)

`mark/inline/**`, `wordmark/inline/**`, `lockup/inline/**` use `currentColor` for ink and `var(--egz-canvas)` for the flat-tier faces, and no hex at all (F-02b). The lifeboat includes them as Jinja partials; the flagship inlines them as SVG in JSX. Both therefore re-value with the scheme and the violet canvas for free, and neither carries a literal — principle 12 holds. **A UI that loads a file master by `<img>` for an in-product placement is non-conforming**; file masters are for the `<head>` (favicon set), uploads, README and other people's pages.

### §6.4 Backgrounds

A mark sits on `--egz-canvas` (light, dark-neutral or dark-violet), on GitHub's own light or dark chrome (as an uploaded file), or on the white of a third party's page. **Never on imagery, a gradient, a pattern or `--egz-paper`.** The dither field has transparent cut faces and transparent surroundings and depends on a flat canvas to read.

### §6.5 Which scheme where (D6)

| surface | scheme | why |
|---|---|---|
| GitHub org avatar, App avatars, social preview | **light, always** — one file each | GitHub shows one file on both its themes; a white card with a black offset reads on GitHub's dark chrome; a black card on its light chrome is a black square |
| README header | `<picture>` pair — light and dark | GitHub switches the source with the viewer's theme (§18) |
| favicon.svg | scheme-adaptive in the file (`prefers-color-scheme` inside the SVG) | the one master allowed a `<style>` |
| favicon.ico, ICO frames, apple-touch-icon | light | formats without a scheme; the tab and home screen supply their own backgrounds |
| PWA icons | light; `maskable-dark.svg` exists for a platform that lets the manifest declare a dark icon — none binds it today | the manifest has one icon set |
| lifeboat, flagship in-product | inline masters → whatever scheme and canvas `<html>` carries | principle 1: dark is the same tokens re-valued |
| terminal | monochrome by construction; the terminal's own foreground and background | §9 |

## §7 Structure: the badge

The badge is the record's frame token geometry in the mark's box — border : offset = 2.5 : 5 units, the same 1 : 2 as `--egz-bw : --egz-off` — with the mark at 56 % of the box, centred on the card. It is the shape egzos uploads wherever a square avatar is asked for, and it is what makes a dithered sphere read as *egzos* at 20 px: the offset is the identity's one structural gesture, and it survives every crop GitHub applies (square, rounded, circle). Radius is 0 everywhere; a platform that rounds the corners does so on top of a square file, and the file is not pre-rounded to meet it.

## §8 Placements × contexts — the inventory

Every placement the identity has today. A placement not listed here does not exist; a consumer that needs one files a `design-gap` issue quoting this section. Columns: the master · the export (if a raster) · pixel size · scheme · tier (§3.1) · who places it and how · what a viewer sees at the small end · fixture (§20).

### §8.1 GitHub (the Chief, by hand, in the GitHub UI)

| placement | master → export | size | scheme | tier | how | small-end read | fixture |
|---|---|---|---|---|---|---|---|
| **organization avatar** (Egzos) | `badge/badge-light.svg` → `org-avatar-512.png` | 512 × 512 (GitHub: PNG/JPG/GIF, < 1 MB, < 3000², "about 500 × 500") | light | 64 | Org → Settings → Profile → upload | at 20 px in a timeline the field becomes tone: a grey sphere, a lighter notch, the black offset — accepted (§3.1) | F-08a/b |
| **repository social preview** (egzos; and egzos-platform when it exists) | `banner/social-preview.svg` → `social-preview-1280x640.png` | 1280 × 640 (GitHub: ≥ 640 × 320, best 1280 × 640, < 1 MB) | light | 32 | Repo → Settings → Social preview → upload | link cards crop nothing at 2 : 1 | F-08a/b |
| **chief-proxy App avatar** | `app/chief-proxy.svg` → `app-chief-proxy-200.png` | 200 × 200 (GitHub: recommended 200 × 200, < 1 MB) | light | 32 | Developer settings → the App → Display information → upload; **Badge background colour `#FFFFFF`** | a white disc with a grey whole sphere — the human's proxy | F-07a · F-08a |
| **egzos-forge App avatar** | `app/egzos-forge.svg` → `app-egzos-forge-200.png` | 200 × 200 | light | 32 | same, on the forge App; badge colour `#FFFFFF` | a white disc with a notched sphere — the agents' forge | F-07b · F-08a |
| **README header** | `banner/readme-header-light.svg` + `banner/readme-header-dark.svg` | 1280 × 320, scales to the README column | pair | 32 | `<picture>` under the H1 (§18.1); SVG masters referenced by relative path, no PNG | — | F-01 · F-02c/d |
| GitHub Marketplace listing (not planned) | would be the App avatar files | ≥ 200 × 200 | light | 32 | not a placement today; listed so nobody invents one | — | — |

GitHub does not document per-surface corner rounding for avatars; the badge is designed to survive square, rounded and circular crops and no assumption is made.

### §8.2 Browser and PWA (a5-dinghy for the lifeboat, a4s-atelier for the flagship; both vendor the files through their own PRs after running `render.py`)

| placement | master → export | size | scheme | tier | how | fixture |
|---|---|---|---|---|---|---|
| **favicon.svg** | `mark/favicon.svg` | any (a 64 box) | adaptive | flat | `<link rel="icon" type="image/svg+xml">` — Chrome 80+, Firefox 41+, Safari 26+ | F-02d |
| **favicon.ico** | `mark/pending-flat.svg` → `favicon.ico` (48 · 32 · 16 frames) | 48/32/16 | light | flat | `<link rel="icon" href="/favicon.ico" sizes="any">` **first**, then the SVG (§18.2) | F-08c |
| **apple-touch-icon** | `pwa/apple-touch-icon.svg` → `apple-touch-icon-180.png` | 180 × 180, opaque | light | 32 | `<link rel="apple-touch-icon">`; one size, no `-precomposed`, no `sizes` list | F-08a/d |
| **PWA icon 192 / 512** | `badge/badge-light.svg` → `icon-192.png`, `icon-512.png` | 192 · 512 | light | 32 · 64 | `manifest.webmanifest` icons (§18.3) | F-05a · F-08a |
| **PWA maskable 512** | `pwa/maskable-light.svg` → `icon-maskable-512.png` | 512, full-bleed canvas, mark inside the 80 % circle | light | 64 | `"purpose": "maskable"` as its own entry — never `"any maskable"` | F-05a · F-08a |
| **theme-color** | — | — | pair | — | two `<meta name="theme-color">` with `media` (§18.2): `#FFFFFF` light, `#0B0B0B` dark | F-05c |
| Safari `mask-icon` | none | — | — | — | Apple's page is archived and Safari 26 takes the SVG favicon; **none on this surface** | — |

### §8.3 In-product (inline masters only; §6.3)

| placement | master | size | tier | who | note | fixture |
|---|---|---|---|---|---|---|
| **lifeboat header mark** | `mark/inline/pending-flat.svg` | 20 px box | flat | a5-dinghy | **if** `lifeboat.md` places a mark in its header (that spec decides; §19); `aria-hidden="true"` beside the visible word `egzos`, or `role="img" aria-label="egzos"` when the word is absent | F-06 |
| **flagship app-shell lockup** | `lockup/inline/horizontal-nav.svg` | F = 22 (28.6 px tall · 96.7 px wide) | flat | a4s-atelier | the search-list app shell's brand slot (`search-list.md`, platform repo); `role="img" aria-label="egzos"`; never a link target larger than the lockup's own box | F-06 |
| **larger in-product marks** (empty states, about, sign-in) | `mark/inline/pending-32.svg` / `-64.svg` by §3.1 | ≥ 57 px box | 32 · 64 | either | only where a screen spec places one; none does today | F-06 |
| **the proposal glyph** | `mark/inline/slice-*.svg` | by §3.1 | any | — | **reserved**: a later revision of `step-up-tap-and-pending-approval.md` may adopt the slice as the pending-item glyph; until it does, the slice appears nowhere in-product (§21) | F-06 |
| tap page · consent page | — | — | — | a3-trust | those specs bind their own headers; if they place a mark it is `mark/inline/pending-flat.svg` at ≤ 24 px and nothing else (§19) | — |

### §8.4 Terminal, MCP, PyPI (a3-doorman)

| placement | master | how | fixture |
|---|---|---|---|
| **bare `egzos` splash** | `terminal/splash-16-blocks.txt` (UTF-8 TTY) · `terminal/splash-16-ascii.txt` (other TTY) | §9; the text asset is shipped in the wheel and byte-identical to the master | F-03 · F-04 |
| **MCP `Implementation.icons`** | `mcp/icons.json` | four entries — PNG 48, PNG 96 (`image/png`, MUST-support types), SVG `any` light, SVG `any` dark (`theme` field) — as `data:` URIs; offered, a3-doorman decides (S7) | F-05d/e |
| **PyPI project README** | `terminal/header-8-blocks.txt` in a fenced code block **or** the README header by **absolute** URL (PyPI allows `http(s)` only, and `<picture>` is in its allow-list) | S8; PyPI has no logo slot and gives no size guidance | F-03 |
| **docs site** (when one exists) | `banner/readme-header-*.svg`, the favicon set | as §8.1/§8.2 | — |

## §9 The terminal

### §9.1 Why it is a first-class placement

egzos is CLI-first; the terminal is the mark's home ground. The same shade buffer that makes the dither field makes the text art, so what the CLI prints *is* the mark, not an approximation of it. The art is monochrome by construction — it uses the terminal's own foreground on its own background — so it lands on light and dark terminals alike and has no colour to get wrong.

### §9.2 Alphabets

| alphabet | file(s) | cell | glyphs | when |
|---|---|---|---|---|
| **half-blocks** (primary) | `splash-16-blocks.txt`, `header-8-blocks.txt`, `whole-16-blocks.txt`, `slice-16-blocks.txt` | 1 : 2, two field rows per text row | `▀ ▄ █` U+2580/2584/2588, `░` U+2591 for the shaded cut faces, space | UTF-8 terminals; every mono face in common use carries the block elements (IBM Plex Mono does) |
| **braille** (secondary) | `splash-16-braille.txt` | 2 × 4 dots per cell | U+2800–28FF | highest resolution; **font-dependent** — many mono faces (Plex Mono among them) lack the block and fall back; offered, never the default |
| **ASCII** (fallback) | `splash-16-ascii.txt`, `header-8-ascii.txt` | 1 : 2 | ` .:-=+*#%@` (a 10-step ramp from the shade) | non-UTF-8 locales |

### §9.3 Sizes

| size | rows × cols | field | creases | faces | use |
|---|---|---|---|---|---|
| **splash** | 16 × 32 | 32² | yes | `░` | bare `egzos` (D7) |
| **header** | 8 × 16 | 16² | **no** — a one-cell crease in a sixteen-cell field swallows the faces | `░` | image-less markdown (S8) |
| whole · slice | 16 × 32 | 32² | — | — | the other two solids, for documentation of the family; the slice ends blank and is ≤ 16 rows |

### §9.4 Where it prints — the ladder (D7)

Evaluated in order; the first row that matches decides.

| condition | output |
|---|---|
| any argument at all — `--help`, `--version`, a subcommand, an option | **no art**; text only, ever |
| `EGZOS_NO_ART` is set (any value) | no art |
| stdout is not a TTY (piped, redirected, captured) | no art |
| `TERM` is `dumb` or unset | no art |
| TTY, but the locale's encoding is not UTF-8 | `splash-16-ascii.txt`, then the usage text |
| TTY, UTF-8 | `splash-16-blocks.txt`, then the usage text |

No escape sequences, no colour, no cursor movement, no clearing: the art is written once with `print`. `NO_COLOR` is honoured trivially (there is no colour). The art never goes to stderr.

### §9.5 What this file does not bind

The **usage text** that follows the splash, its wording, and the CLI grammar are a3-doorman's and the subject of egzos#41 (whether the CLI grammar is a Phase 0.2 freeze artifact). Board v0.2 mocked a usage block beside the art; that mock is illustration, not copy, and no string from it is in §13. This file binds the art, the ladder, and that the shipped asset is byte-identical to the master (§16).

## §10 Silence-not-errors

Not applicable and stated so: identity assets are static files that carry no user data, no counts, no names and no state of any container. Nothing here can reveal what a viewer cannot see. No placement in §8 varies with the viewer.

## §11 Unverified-by-default

Not applicable and stated so, with one guard: the mark's own state names — *whole*, *pending*, *slice* — are not trust statuses and must not be rendered as if they were. No screen may show a `verified` item with the whole orb and an `unverified` one with the cut orb, or use the slice for `quarantined`. Trust is a shape of its own (principle 4: solid · outline · dashed · red outline) and the orb is not in that set.

## §12 Accessibility

- Contrast: ink on canvas is 21 : 1 (light) and 17.6 : 1 (dark-neutral); the dither field is decorative and never sits under text.
- Every in-product mark is either `aria-hidden="true"` beside the visible word, or `role="img"` with `aria-label` from §13 — never both, never unlabelled.
- Alt text for every `<img>` and `<picture>` from §13. The README header's alt names the product and what it is; the social preview needs none (no alt attribute exists on a link card).
- The mark never carries meaning alone in a UI (WCAG 1.4.1): whole/pending/slice differences are never the sole indication of anything.
- Terminal art is preceded and followed by a blank line and is skipped when stdout is not a TTY, so screen readers driving a shell through a pipe never meet it; a user on a TTY may set `EGZOS_NO_ART`.
- No motion anywhere (§3.4), so no `prefers-reduced-motion` case exists.

## §13 Canonical copy

Rendered verbatim wherever the key is used; never paraphrased. Keys are lowercase mono with a dot separator.

| key | string | used by |
|---|---|---|
| `brand.name` | `egzos` | everywhere the name is written |
| `brand.tagline` | `personal context layer · mcp-first · cli-first · your container is the home` | README header, social preview (outlined) |
| `brand.social.url` | `github.com/Egzos/egzos` | social preview |
| `brand.social.licence` | `apache-2.0 · open core` | social preview |
| `brand.alt.mark` | `egzos` | `aria-label` of any lone in-product mark or lockup |
| `brand.alt.header` | `egzos — personal context layer` | README `<img alt>` |
| `brand.alt.app.chief` | `chief-proxy` | the App's display name (GitHub renders it beside the avatar; the avatar itself has no alt) |
| `brand.alt.app.forge` | `egzos-forge` | as above |
| `brand.term.optout` | `EGZOS_NO_ART` | the environment variable of §9.4 |
| `brand.file.splash` | `splash-16-blocks.txt` · `splash-16-ascii.txt` | the two shipped text assets |

## §14 What this file needs from the container contract

**Nothing.** No placement reads, writes or displays a container item, token, node, capability or event; no audit event is emitted by an identity asset, and none is needed — stated per the standing rule that every region touching user data names its event or says none exists: **none exists, because none touches user data.**

Two adjacencies, neither a contract term:

- `[OPEN→egzos#41]` — the usage text around the splash belongs to the CLI grammar, whose freeze status is the open question in egzos#41. This file's ladder (§9.4) holds whichever way that resolves.
- MCP `Implementation.icons` (MCP spec 2026-07-28) is metadata on the door's `initialize` result; a3-doorman decides whether to advertise it (S7). Not raised to a1p: it does not touch the contract vocabulary.

## §15 A6 review notes

- **The forge never wears the whole orb.** `app/egzos-forge.svg` is the pending solid by construction and F-07b fails otherwise. An agent identity wearing the merged mark would claim, in every bot comment, a state only the human's proxy has.
- **Uploads are the Chief's.** The org avatar, social preview and both App avatars are set in the GitHub UI by the Chief; no App identity holds the permission to change an avatar, and none of this repository's workflows touches them. A change of avatar is therefore a Chief action by construction.
- **No network in the build.** `render.py --fetch-fonts` downloads two pinned release zips (sha256 in the script) — once, on a designer's machine. Nothing in CI fetches fonts or runs the pipeline; builders copy committed masters. CI runs only `pipeline/check.py` on its default path — stdlib only, no fonts, no numpy, no network — through `tests/conformance/test_brand_pipeline.py`; F-08 and F-09 stay on a designer's machine. A CI job that ran `--fetch-fonts` would be a supply-chain surface this file does not open.
- **SVG hygiene.** No master contains `<script>`, `<filter>`, `<image>`, gradients, external references or `<text>`; only `mark/favicon.svg` carries a `<style>`, and it is served from egzos's own origin (F-02c/d). README masters are pure paths and survive GitHub's sanitiser without loss.
- **Data URIs in `mcp/icons.json`** are PNG and SVG bytes generated here (F-05e checks the PNG magic); a client is told by the MCP spec to validate MIME by magic bytes and treat the declared type as advisory — the file is built to pass that.
- **The terminal art is inert:** plain characters, no escape sequences, written only to a TTY, suppressed by `EGZOS_NO_ART` — it cannot be used to smuggle control sequences into a log or a pipe.
- **Trade dress is a trust signal.** `TRADEMARKS.md` exists because a fork wearing the mark would promise this repository's trust posture on the Chief's behalf. Not a technical control; recorded so the reviewer knows it is deliberate.

## §16 a2-conformance checklist

1. Every file in `pipeline/manifest.json` exists and is non-empty (F-01), and every SVG master parses as XML (F-01b).
2. Every hex literal in a file master is one of the five declared in §6.2, and inline masters carry none (F-02a/b).
3. No master contains a forbidden element (§3.4, §5 *files*) and only `mark/favicon.svg` has a `<style>` (F-02c/d).
4. Terminal masters have the bound row counts, column widths, alphabets and no trailing spaces (F-03); the 8-row header is shaded and crease-free (F-04).
5. `pwa/manifest-icons.json`, `pwa/head.html` and `mcp/icons.json` carry exactly the bound entries and order (F-05).
6. All three solids exist in all three tiers as light, dark and inline masters (F-06).
7. `app/chief-proxy.svg` is the whole orb and `app/egzos-forge.svg` is the pending orb (F-07).
8. When rasters are present: bound pixel sizes, < 1 MB, three ICO frames, opaque apple-touch-icon (F-08).
9. `pipeline/check.py --regenerate` reproduces every master byte for byte (F-09) — the committed masters are what the pipeline emits and nothing was hand-edited.
10. A UI PR that places the mark uses an inline master (§6.3), at a size inside its tier (§3.1), with the labelling of §12 and a string from §13.
11. A UI PR that ships the favicon set or PWA icons vendors rasters whose sha256 match a `render.py` run from the committed pipeline, and its `<head>` order and `manifest` entries match §18.
12. The CLI PR that ships the splash ships `splash-16-blocks.txt` and `splash-16-ascii.txt` byte-identical to the masters and implements the §9.4 ladder in that order.
13. No placement outside §8 exists; no colour outside §6; no treatment inside §3.4 or §4.4; the onion screen carries none of the orb's rendering (§2.3).
14. Every string rendered near a mark is a §13 key; for the outlined strings in the masters, the pipeline's copy constants equal §13 verbatim (F-10).

## §17 Component picks

**None on this surface.** The identity is bespoke geometry (`pipeline/orb.py`, A2 studio). No catalogue item is installed, so there is nothing for a4s to vendor and nothing for a4g to compose. Anti-reference recorded: Paper Shaders *dithering* (21st.dev · `paper-design/dithering` · Apache-2.0) — a WebGL surface, not an identity; the orb's field is a deterministic Bayer threshold on a fixed geometry, not a shader, and no consumer may substitute one for the other. Typeface: IBM Plex Mono (OFL-1.1) — outlined, so no font file ships with any asset.

## §18 URLs and HTML patterns

### §18.1 README header

```html
<picture>
  <source media="(prefers-color-scheme: dark)" srcset="spec/design/brand/banner/readme-header-dark.svg">
  <img alt="egzos — personal context layer" src="spec/design/brand/banner/readme-header-light.svg" width="1280">
</picture>
```

Relative paths resolve per branch on GitHub. The `<picture>` form is GitHub's current mechanism (GA 2022-08-15); the `#gh-dark-mode-only` fragment form is legacy and not used.

### §18.2 `<head>` (both UIs) — `pwa/head.html`, verbatim

```html
<link rel="icon" href="/favicon.ico" sizes="any">
<link rel="icon" href="/favicon.svg" type="image/svg+xml">
<link rel="apple-touch-icon" href="/apple-touch-icon.png">
<link rel="manifest" href="/manifest.webmanifest">
<meta name="theme-color" media="(prefers-color-scheme: light)" content="#FFFFFF">
<meta name="theme-color" media="(prefers-color-scheme: dark)" content="#0B0B0B">
```

The ICO comes first with `sizes="any"` so browsers that prefer it take it and SVG-capable browsers take the SVG.

### §18.3 Manifest icons — `pwa/manifest-icons.json`, verbatim

```json
{"icons": [
  {"src": "/icon-192.png", "sizes": "192x192", "type": "image/png"},
  {"src": "/icon-512.png", "sizes": "512x512", "type": "image/png"},
  {"src": "/icon-maskable-512.png", "sizes": "512x512", "type": "image/png", "purpose": "maskable"}
], "background_color": "#FFFFFF", "theme_color": "#FFFFFF"}
```

### §18.4 PyPI README

Either the 8-row header in a fenced block (no image hosting needed) or the light README header by absolute URL (`https://raw.githubusercontent.com/Egzos/egzos/main/spec/design/brand/banner/readme-header-light.svg`); `<picture>` with absolute URLs is also accepted by PyPI's renderer.

## §19 Relationship to the other UI

The two UIs share one identity and differ only in form: the lifeboat includes inline masters as Jinja partials with tokens as CSS variables and no components; the flagship inlines the same SVG in JSX and maps the tokens through Tailwind. Neither redraws anything. Whether a given page carries the mark at all is that page's spec's decision — `lifeboat.md` for the lifeboat header, `search-list.md` (platform) for the app shell, the tap and consent specs for the container's pages; this file decides which file, which tier and which label once they do. The lifeboat has no motion; the flagship has none here either.

## §20 Test fixtures — one per asset (`pipeline/check.py`)

| id | fixture | asserts |
|---|---|---|
| F-01 | every manifest master | exists, non-empty |
| F-01b | every SVG | parses with stdlib `xml.etree.ElementTree` |
| F-02a | every SVG | only the five declared literals |
| F-02b | every inline SVG | tier-aware: `currentColor` and no hex in all; `var(--egz-canvas)` required on `mark/inline/pending-flat.svg` and `lockup/inline/horizontal-nav.svg` (flat faces are paper), absent from the `-32` / `-64` stems (dither faces are transparent); neither required nor banned on `whole-flat` / `slice-flat` (no cut face) |
| F-02c | every SVG | no gradient, filter, script, animate, image, text, foreignObject, external href |
| F-02d | every SVG | no `<style>` except `mark/favicon.svg` |
| F-03a–d | each terminal TXT | rows (16 · 8; slice ≤ 16), ≤ cols (32 · 16), alphabet, no trailing spaces |
| F-03e | `splash-16-braille.txt` | 16 rows, U+2800 block only |
| F-04 | `header-8-blocks.txt` | shaded faces present |
| F-05a–e | `pwa/*.json`, `pwa/head.html`, `mcp/icons.json` | bound entries, order, theme-color pair, PNG magic |
| F-06 | 27 mark masters | three solids × three tiers × light / dark / inline |
| F-07a/b | the two App masters | chief-proxy = whole-32 body · egzos-forge = pending-32 body |
| F-08a–d | rasters in `./dist` | pixel sizes, < 1 MB, ICO frame count 3, apple-touch opaque |
| F-09 | every master | regenerates byte-identical (`--regenerate`) |
| F-10 | `render.py` `LABEL` · `URL_LINE` · `LICENCE_LINE` | equal §13 `brand.tagline` · `brand.social.url` · `brand.social.licence` verbatim (parsed from this file) |

Run: `python3 pipeline/render.py --fetch-fonts` (once) · `python3 pipeline/render.py` · `python3 pipeline/check.py --regenerate`. 415 checks on 2026-09-24, all passing (391 without `./dist`). The default path — `python3 pipeline/check.py`, no fonts, no third-party package — runs 331 checks with F-08 skipped, and is what CI runs (`tests/conformance/test_brand_pipeline.py`).

## §21 Non-goals and open items

- **Struck from the set:** directions A · Survey, B · Stamp, C · Letter; textures contour and halftone. They exist on the board as record and must not be revived as "variants".
- **Reserved:** the slice as the pending-item glyph — a later revision of `step-up-tap-and-pending-approval.md`, not this file.
- **Owed after PR #45 merges:** the `spec/design/README.md` index row for this file and the §22 rows into `DESIGN-SOURCES.md`; both files are rewritten on #45's branch and are not touched here to avoid a conflict (D14: branches base on `main`, never on a PR).
- **`TRADEMARKS.md`** is the Chief's document (D3); A2's draft accompanies this file for his edit.
- Not bound here: OS file-type icons for `.xmb` archives; egzos.io marketing surfaces; a docs-site theme; any animated form of the mark (there is none; §3.4).
- **Later:** if a platform lets a manifest declare a dark icon set, `pwa/maskable-dark.svg` and `badge/badge-dark.svg` are the masters; no consumer binds them today.

## §22 Provenance — rows for `DESIGN-SOURCES.md` (to append after #45)

Typefaces table:

| Typeface | Source | Licence | Date | Role | Spec |
|---|---|---|---|---|---|
| IBM Plex Mono SemiBold 2.004 | github.com/IBM/plex · release `@ibm/plex-mono@1.1.0` · sha256 `4bfc936d…d26c` | OFL-1.1 (outlines; Reserved Font Name untouched, no font file shipped) | 2026-09-22 | the wordmark, outlined | `BRAND.md` picked it at v1.0 |
| IBM Plex Mono Regular 2.004 | same release | OFL-1.1 | 2026-09-22 | tagline and social lines, outlined | `BRAND.md` picked it at v1.0 |

Adopted conventions table:

| Convention | Source | Licence | Date | Taken · Refused | Spec |
|---|---|---|---|---|---|
| Bayer 8×8 ordered dither | Bayer (1973), standard matrix | public domain | 2026-09-22 | taken: the threshold matrix · refused: any error-diffusion (non-deterministic across renderers) | `BRAND.md` at v1.0 |
| Unicode block elements / braille patterns | U+2580–259F · U+2800–28FF | — | 2026-09-22 | taken: `▀▄█░`, braille as secondary · refused: box-drawing outlines | `BRAND.md` at v1.0 |
| GitHub avatar / social preview / `<picture>` / App badge requirements | docs.github.com (profile reference; social preview; writing on GitHub; App badge) | — | 2026-09-22 | taken as constraints in §8 | `BRAND.md` at v1.0 |
| Favicon set, maskable safe zone, theme-color | web.dev (adaptive favicon; maskable icon), MDN (manifest icons; theme-color), caniuse (SVG favicon) | — | 2026-09-22 | taken: ICO-then-SVG order, 80 % safe circle, separate maskable entry · refused: `mask-icon` (archived) | `BRAND.md` at v1.0 |
| MCP `Implementation.icons` | modelcontextprotocol.io · specification 2026-07-28 | — | 2026-09-22 | taken: PNG MUST + SVG SHOULD, `theme` tags, data URIs | `BRAND.md` at v1.0 |

Considered and declined:

| Item | Registry item / URL | Licence | Date | Why declined | Spec |
|---|---|---|---|---|---|
| Paper Shaders · *dithering* | 21st.dev · `paper-design/dithering` | Apache-2.0 | 2026-09-22 | a WebGL surface, not an identity; anti-reference for §17 | `BRAND.md` at v1.0 |

Tools (pipeline, not shipped): resvg-py 0.3.2 (MPL-2.0) · fonttools 4.60 (MIT) · numpy ≥ 2.0, < 3 (BSD-3; pinned in `pipeline/requirements.txt`) · matplotlib 3.9 (PSF-based) · Pillow 11 (MIT-CMU).

## §23 Changelog

- **v1.0 · 2026-09-22** — first binding revision. Direction D · Orb, dither (Chief, board v0.2). Studio decisions S1–S9. 59 masters, 17 rasters, 415 fixtures passing (331 on the font-free default path CI runs). Owed: index row and provenance rows after PR #45 merges (§21).
