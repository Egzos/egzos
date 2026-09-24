#!/usr/bin/env python3
# Copyright 2026 Ali Sasanian
# SPDX-License-Identifier: Apache-2.0
"""egzos identity · render pipeline — one geometry → every master and export BRAND.md binds.

This is a DESIGN TOOL, not production code: nothing under src/ imports it. It regenerates the committed
masters under spec/design/brand/ and the rasters the platforms upload or vendor. Builders do not need to
run it — they copy committed masters (SVG, TXT, JSON) into their own trees; only the rasters (PNG, ICO) are
produced here because binary files are not committed to this directory.

    python3 pipeline/render.py --fetch-fonts          # once: pinned IBM Plex release zips → pipeline/fonts/
    python3 pipeline/render.py                        # masters → spec/design/brand/** · rasters → dist/
    python3 pipeline/render.py --out /tmp/brand       # regenerate elsewhere (check.py uses this)

Requires: python ≥ 3.9, numpy, matplotlib (contour tracing), fonttools, resvg-py, Pillow.
Colours: an export is a fixed file and cannot read CSS variables, so file masters carry the tokens.css values
as DECLARED LITERALS (BRAND.md §6 lists each with its token). Inline masters (mark/inline/**, wordmark/inline,
lockup/inline) carry `currentColor` and `var(--egz-canvas)` instead and are the only form used inside the two UIs.
"""
import os, sys, io, json, base64, hashlib, zipfile, argparse, urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
BRAND = os.path.dirname(HERE)
sys.path.insert(0, HERE)
import orb as O                                   # noqa: E402
from outline import outline, metrics              # noqa: E402

# ── declared literals · tokens.css v0.8 (values unchanged since v0.3) ─────────────────────────────
INK = {"light": "#000000", "dark": "#F4F4F0"}                       # --egz-ink
CANVAS = {"light": "#FFFFFF", "dark": "#0B0B0B", "violet": "#0B0716"}  # --egz-canvas
# --egz-shadow-ink equals --egz-ink in both schemes; the badge offset uses INK.
LABEL = "personal context layer · mcp-first · cli-first · your container is the home"   # copy key brand.tagline
URL_LINE = "github.com/Egzos/egzos"                                                      # copy key brand.social.url
LICENCE_LINE = "apache-2.0 · open core"                                                  # copy key brand.social.licence

# ── fonts · pinned IBM Plex releases (OFL-1.1) ────────────────────────────────────────────────────
FONTS_DIR = os.path.join(HERE, "fonts")
FONT_RELEASES = {
    "ibm-plex-mono.zip": ("https://github.com/IBM/plex/releases/download/%40ibm%2Fplex-mono%401.1.0/ibm-plex-mono.zip",
                          "4bfc936d0e1fd19db6327a3786eabdbc3dc0d464500576f6458f6706df68d26c",
                          ["ibm-plex-mono/fonts/complete/ttf/IBMPlexMono-SemiBold.ttf", "ibm-plex-mono/fonts/complete/ttf/IBMPlexMono-Regular.ttf"]),
}
WORDMARK_FONT = os.path.join(FONTS_DIR, "IBMPlexMono-SemiBold.ttf")   # IBM Plex Mono SemiBold 2.004
LABEL_FONT = os.path.join(FONTS_DIR, "IBMPlexMono-Regular.ttf")       # IBM Plex Mono Regular 2.004
XMLNS = 'xmlns="http://www.w3.org/2000/svg"'
SPHERE = 54 / 64        # the sphere spans 54 of the mark's 64-unit box
WORD = "egzos"          # D1 · lowercase, always

def fetch_fonts():
    os.makedirs(FONTS_DIR, exist_ok=True)
    for name, (url, sha, members) in FONT_RELEASES.items():
        zp = os.path.join(FONTS_DIR, name)
        if not os.path.exists(zp):
            print("fetching", url); urllib.request.urlretrieve(url, zp)
        got = hashlib.sha256(open(zp, "rb").read()).hexdigest()
        if got != sha:
            raise SystemExit(f"{name}: sha256 {got} != pinned {sha}")
        with zipfile.ZipFile(zp) as z:
            for m in members:
                open(os.path.join(FONTS_DIR, os.path.basename(m)), "wb").write(z.read(m))
    print("fonts ready:", sorted(f for f in os.listdir(FONTS_DIR) if f.endswith(".ttf")))

def need_fonts():
    if not (os.path.exists(WORDMARK_FONT) and os.path.exists(LABEL_FONT)):
        raise SystemExit("fonts missing — run: python3 pipeline/render.py --fetch-fonts")

# ── the mark ──────────────────────────────────────────────────────────────────────────────────────
def tier(sphere_px):
    """The size law (BRAND.md §3): flat below a 48 px sphere · 32-cell field 48–159 px (cells ≥ 1.5 px) · 64-cell field from 160 px (cells ≥ 2.5 px)."""
    return "flat" if sphere_px < 48 else ("32" if sphere_px < 160 else "64")

def mark_inner(solid, tier_id, ink, paper):
    if tier_id == "flat":
        return O.flat_svg_inner(ink, paper, solid=solid, stroke=3.0)
    return O.dither_svg_inner(int(tier_id), ink, paper, solid=solid)

def M(solid, box_px, ink, paper):
    return mark_inner(solid, tier(box_px * SPHERE), ink, paper)

def svg64(inner, extra=""):
    return f'<svg {XMLNS} width="64" height="64" viewBox="0 0 64 64"{extra}>{inner}</svg>'

def favicon_svg():
    inner = mark_inner("orb", "flat", "currentColor", "var(--p)")
    return (f'<svg {XMLNS} width="64" height="64" viewBox="0 0 64 64"><style>:root{{color:{INK["light"]};--p:{CANVAS["light"]}}}'
            f'@media (prefers-color-scheme: dark){{:root{{color:{INK["dark"]};--p:{CANVAS["dark"]}}}}}</style>{inner}</svg>')

# ── wordmark & lockups ────────────────────────────────────────────────────────────────────────────
def wm(F):
    d, adv = outline(WORD, WORDMARK_FONT, size=F)
    m = metrics(WORDMARK_FONT, size=F)
    return d, adv, m["ascender"], -m["descender"]

def label(text, F):
    return outline(text, LABEL_FONT, size=F)

def wordmark_svg(ink, F=100):
    d, adv, asc, desc = wm(F)
    return (f'<svg {XMLNS} width="{adv:.2f}" height="{asc+desc:.2f}" viewBox="0 0 {adv:.2f} {asc+desc:.2f}">'
            f'<path transform="translate(0 {asc:.2f})" d="{d}" fill="{ink}"/></svg>')

def lockup_svg(ink, paper, F=100, stacked=False, box_px=None):
    """Horizontal: box = ascender height, gap = 0.36 box. Stacked: box = 1.5 asc, gap = 0.45 asc (BRAND.md §4)."""
    d, adv, asc, desc = wm(F)
    box = asc; gap = box * 0.36
    if not stacked:
        W, H = box + gap + adv, asc + desc
        return (f'<svg {XMLNS} width="{W:.2f}" height="{H:.2f}" viewBox="0 0 {W:.2f} {H:.2f}">'
                f'<g transform="scale({box/64:.5f})">{M("orb", box_px or box, ink, paper)}</g>'
                f'<path transform="translate({box+gap:.2f} {asc:.2f})" d="{d}" fill="{ink}"/></svg>')
    box2 = asc * 1.5; gap2 = asc * 0.45
    W, H = max(adv, box2), box2 + gap2 + asc + desc
    return (f'<svg {XMLNS} width="{W:.2f}" height="{H:.2f}" viewBox="0 0 {W:.2f} {H:.2f}">'
            f'<g transform="translate({(W-box2)/2:.2f} 0) scale({box2/64:.5f})">{M("orb", box_px or box2, ink, paper)}</g>'
            f'<path transform="translate({(W-adv)/2:.2f} {box2+gap2+asc:.2f})" d="{d}" fill="{ink}"/></svg>')

# ── placements ────────────────────────────────────────────────────────────────────────────────────
def badge_inner(scheme, canvas, px):
    """The badge: canvas card, 2.5-unit border, 4-unit-class hard offset (--egz-bw / --egz-off in a 64 box), mark at 56%."""
    ink = INK["light" if scheme == "light" else "dark"]; cv = CANVAS[canvas or scheme]
    return (f'<rect x="5" y="5" width="56" height="56" fill="{ink}"/>'
            f'<rect x="1.25" y="1.25" width="53.5" height="53.5" fill="{cv}" stroke="{ink}" stroke-width="2.5"/>'
            f'<g transform="translate(10 10) scale(0.5625)">{M("orb", px * 0.5625, ink, cv)}</g>')

def badge_svg(scheme="light", canvas=None, px=512):
    return svg64(badge_inner(scheme, canvas, px))

def app_svg(solid, px=200):
    """GitHub App avatar. GitHub crops to a circle and shows it at 20 px in timelines; the white record is baked in."""
    return svg64(f'<rect width="64" height="64" fill="{CANVAS["light"]}"/>'
                 f'<g transform="translate(12 12) scale(0.625)">{M(solid, px * 0.625, INK["light"], CANVAS["light"])}</g>')

def maskable_svg(scheme="light", px=512):
    ink, cv = INK["light" if scheme == "light" else "dark"], CANVAS[scheme]
    return svg64(f'<rect width="64" height="64" fill="{cv}"/><g transform="translate(13.44 13.44) scale(0.58)">{M("orb", px * 0.58, ink, cv)}</g>')

def touch_svg(px=180):
    return svg64(f'<rect width="64" height="64" fill="{CANVAS["light"]}"/><g transform="translate(6 6) scale(0.8125)">{badge_inner("light", None, px * 0.8125)}</g>')

def readme_header_svg(scheme):
    ink, cv = INK[scheme], CANVAS[scheme]
    F = 96; d, adv, asc, desc = wm(F); box = asc; gap = box * 0.36
    x0, y0 = 72, 160 - (asc + desc) / 2
    ld, ladv = label(LABEL, 22)
    return (f'<svg {XMLNS} width="1280" height="320" viewBox="0 0 1280 320" role="img" aria-label="egzos">'
            f'<rect x="8" y="8" width="1272" height="312" fill="{ink}"/>'
            f'<rect x="1" y="1" width="1270" height="310" fill="{cv}" stroke="{ink}" stroke-width="2"/>'
            f'<g transform="translate({x0} {y0:.2f}) scale({box/64:.5f})">{M("orb", box, ink, cv)}</g>'
            f'<path transform="translate({x0+box+gap:.2f} {y0+asc:.2f})" d="{d}" fill="{ink}"/>'
            f'<path transform="translate({1200-ladv:.2f} 268)" d="{ld}" fill="{ink}"/></svg>')

def social_svg():
    ink, cv = INK["light"], CANVAS["light"]
    F = 150; d, adv, asc, desc = wm(F); box = asc; gap = box * 0.36; W = box + gap + adv
    x0 = (1280 - W) / 2; y0 = 300 - (asc + desc) / 2
    ld, ladv = label(LABEL, 24); gd, _ = label(URL_LINE, 22); ad, aadv = label(LICENCE_LINE, 22)
    return (f'<svg {XMLNS} width="1280" height="640" viewBox="0 0 1280 640"><rect width="1280" height="640" fill="{cv}"/>'
            f'<rect x="40" y="40" width="1208" height="568" fill="{ink}"/>'
            f'<rect x="33" y="33" width="1206" height="566" fill="{cv}" stroke="{ink}" stroke-width="2.5"/>'
            f'<g transform="translate({x0:.2f} {y0:.2f}) scale({box/64:.5f})">{M("orb", box, ink, cv)}</g>'
            f'<path transform="translate({x0+box+gap:.2f} {y0+asc:.2f})" d="{d}" fill="{ink}"/>'
            f'<path transform="translate({640-ladv/2:.2f} 448)" d="{ld}" fill="{ink}"/>'
            f'<path transform="translate(72 560)" d="{gd}" fill="{ink}"/>'
            f'<path transform="translate({1208-aadv:.2f} 560)" d="{ad}" fill="{ink}"/></svg>')

HEAD_HTML = """<!-- egzos · favicon set · BRAND.md §8.4 · order matters: .ico first with sizes="any", then the SVG -->
<link rel="icon" href="/favicon.ico" sizes="any">
<link rel="icon" href="/favicon.svg" type="image/svg+xml">
<link rel="apple-touch-icon" href="/apple-touch-icon.png">
<link rel="manifest" href="/manifest.webmanifest">
<meta name="theme-color" media="(prefers-color-scheme: light)" content="#FFFFFF">
<meta name="theme-color" media="(prefers-color-scheme: dark)" content="#0B0B0B">
"""

MANIFEST_ICONS = {
    "icons": [
        {"src": "/icon-192.png", "sizes": "192x192", "type": "image/png"},
        {"src": "/icon-512.png", "sizes": "512x512", "type": "image/png"},
        {"src": "/icon-maskable-512.png", "sizes": "512x512", "type": "image/png", "purpose": "maskable"},
    ],
    "background_color": "#FFFFFF",
    "theme_color": "#FFFFFF",
}

# ── raster ────────────────────────────────────────────────────────────────────────────────────────
def png(svg, w, h=None):
    import resvg_py
    return bytes(resvg_py.svg_to_bytes(svg_string=svg, width=w, height=h or w))

def datauri(mime, data):
    return f"data:{mime};base64," + base64.b64encode(data).decode()

# ── emit ──────────────────────────────────────────────────────────────────────────────────────────
def render(out=BRAND, dist=None):
    need_fonts()
    dist = os.path.abspath(dist or os.path.join(os.getcwd(), "dist"))   # rasters never land inside spec/design/brand
    def put(rel, text):
        p = os.path.join(out, rel); os.makedirs(os.path.dirname(p), exist_ok=True)
        open(p, "w", encoding="utf-8").write(text if text.endswith("\n") else text + "\n")
    L, D, CL, CD = INK["light"], INK["dark"], CANVAS["light"], CANVAS["dark"]
    masters = {}
    # marks · three solids × three tiers × light/dark files + inline
    # (file stem, solid name) — the published stem stays "pending" because BRAND.md, pwa/head.html
    # and the icon manifests reference mark/pending-*.svg; the solid orb.py builds is "orb".
    for stem, solid in (("pending", "orb"), ("whole", "whole"), ("slice", "slice")):
        for t in ("64", "32", "flat"):
            masters[f"mark/{stem}-{t}.svg"] = svg64(mark_inner(solid, t, L, CL))
            masters[f"mark/{stem}-{t}-dark.svg"] = svg64(mark_inner(solid, t, D, CD))
            masters[f"mark/inline/{stem}-{t}.svg"] = svg64(mark_inner(solid, t, "currentColor", "var(--egz-canvas)"))
    masters["mark/favicon.svg"] = favicon_svg()
    # wordmark & lockups
    masters["wordmark/wordmark.svg"] = wordmark_svg(L); masters["wordmark/wordmark-dark.svg"] = wordmark_svg(D)
    masters["wordmark/inline/wordmark.svg"] = wordmark_svg("currentColor")
    masters["lockup/horizontal.svg"] = lockup_svg(L, CL); masters["lockup/horizontal-dark.svg"] = lockup_svg(D, CD)
    masters["lockup/stacked.svg"] = lockup_svg(L, CL, stacked=True); masters["lockup/stacked-dark.svg"] = lockup_svg(D, CD, stacked=True)
    masters["lockup/inline/horizontal.svg"] = lockup_svg("currentColor", "var(--egz-canvas)")
    masters["lockup/inline/stacked.svg"] = lockup_svg("currentColor", "var(--egz-canvas)", stacked=True)
    masters["lockup/inline/horizontal-nav.svg"] = lockup_svg("currentColor", "var(--egz-canvas)", box_px=22)   # the 22 px nav lockup: flat mark
    # placements
    masters["badge/badge-light.svg"] = badge_svg("light"); masters["badge/badge-dark.svg"] = badge_svg("dark")
    masters["badge/badge-dark-violet.svg"] = badge_svg("dark", "violet")
    masters["app/chief-proxy.svg"] = app_svg("whole"); masters["app/egzos-forge.svg"] = app_svg("orb")
    masters["pwa/maskable-light.svg"] = maskable_svg("light"); masters["pwa/maskable-dark.svg"] = maskable_svg("dark")
    masters["pwa/apple-touch-icon.svg"] = touch_svg()
    masters["pwa/head.html"] = HEAD_HTML
    masters["pwa/manifest-icons.json"] = json.dumps(MANIFEST_ICONS, indent=2)
    masters["banner/readme-header-light.svg"] = readme_header_svg("light"); masters["banner/readme-header-dark.svg"] = readme_header_svg("dark")
    masters["banner/social-preview.svg"] = social_svg()
    # terminal
    masters["terminal/splash-16-blocks.txt"] = O.terminal(16, "blocks", faces="shade", creases=True)
    masters["terminal/splash-16-braille.txt"] = O.terminal(16, "braille")
    masters["terminal/splash-16-ascii.txt"] = O.terminal(16, "ascii")
    masters["terminal/header-8-blocks.txt"] = O.terminal(8, "blocks", faces="shade", creases=False)
    masters["terminal/header-8-ascii.txt"] = O.terminal(8, "ascii")
    masters["terminal/whole-16-blocks.txt"] = O.terminal(16, "blocks", solid="whole")
    masters["terminal/slice-16-blocks.txt"] = O.terminal(16, "blocks", solid="slice")
    # rasters
    os.makedirs(dist, exist_ok=True)
    small = svg64(mark_inner("orb", "flat", L, CL))
    rasters = {
        "org-avatar-512.png": (masters["badge/badge-light.svg"], 512),
        "org-avatar-dark-512.png": (masters["badge/badge-dark.svg"], 512),
        "app-chief-proxy-200.png": (masters["app/chief-proxy.svg"], 200),
        "app-egzos-forge-200.png": (masters["app/egzos-forge.svg"], 200),
        "apple-touch-icon-180.png": (masters["pwa/apple-touch-icon.svg"], 180),
        "icon-192.png": (badge_svg("light", px=192), 192),
        "icon-512.png": (masters["badge/badge-light.svg"], 512),
        "icon-maskable-512.png": (masters["pwa/maskable-light.svg"], 512),
        "favicon-16.png": (small, 16), "favicon-32.png": (small, 32), "favicon-48.png": (small, 48),
        "mcp-icon-48.png": (svg64(M("orb", 48, L, CL)), 48),
        "mcp-icon-96.png": (svg64(M("orb", 96, L, CL)), 96),
        "readme-header-light-1280x320.png": (masters["banner/readme-header-light.svg"], 1280, 320),
        "readme-header-dark-1280x320.png": (masters["banner/readme-header-dark.svg"], 1280, 320),
        "social-preview-1280x640.png": (masters["banner/social-preview.svg"], 1280, 640),
    }
    sizes = {}
    blobs = {}
    for name, spec in rasters.items():
        data = png(spec[0], spec[1], spec[2] if len(spec) > 2 else None)
        open(os.path.join(dist, name), "wb").write(data); sizes[name] = len(data); blobs[name] = data
    from PIL import Image
    frames = [Image.open(io.BytesIO(png(small, s))).convert("RGBA") for s in (48, 32, 16)]   # base frame largest: Pillow drops sizes above it
    frames[0].save(os.path.join(dist, "favicon.ico"), format="ICO", sizes=[(48, 48), (32, 32), (16, 16)], append_images=frames[1:])
    sizes["favicon.ico"] = os.path.getsize(os.path.join(dist, "favicon.ico"))
    # MCP Implementation.icons (spec 2026-07-28): png MUST, svg SHOULD; theme-tagged svg pair
    masters["mcp/icons.json"] = json.dumps({"icons": [
        {"src": datauri("image/png", blobs["mcp-icon-48.png"]), "mimeType": "image/png", "sizes": ["48x48"]},
        {"src": datauri("image/png", blobs["mcp-icon-96.png"]), "mimeType": "image/png", "sizes": ["96x96"]},
        {"src": datauri("image/svg+xml", masters["mark/pending-32.svg"].encode()), "mimeType": "image/svg+xml", "sizes": ["any"], "theme": "light"},
        {"src": datauri("image/svg+xml", masters["mark/pending-32-dark.svg"].encode()), "mimeType": "image/svg+xml", "sizes": ["any"], "theme": "dark"},
    ]}, indent=2)
    for rel, text in masters.items():
        put(rel, text)
    manifest = {"masters": sorted(masters), "rasters": sorted(sizes)}
    put("pipeline/manifest.json", json.dumps(manifest, indent=1))
    manifest["dist"] = dist
    return manifest

if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--fetch-fonts", action="store_true"); ap.add_argument("--out", default=BRAND); ap.add_argument("--dist", default=None)
    a = ap.parse_args()
    if a.fetch_fonts:
        fetch_fonts(); sys.exit(0)
    m = render(os.path.abspath(a.out), a.dist)
    print(f"{len(m['masters'])} masters → {a.out}\n{len(m['rasters'])} rasters → {m['dist']}")
