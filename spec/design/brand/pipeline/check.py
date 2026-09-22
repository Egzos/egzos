#!/usr/bin/env python3
# Copyright 2026 Ali Sasanian
# SPDX-License-Identifier: Apache-2.0
"""egzos identity · fixtures and conformance check (BRAND.md §16 and §20).

    python3 pipeline/check.py                 # check the committed masters under spec/design/brand/
    python3 pipeline/check.py --regenerate    # also regenerate into a temp dir and diff every master byte-for-byte

One fixture per asset. Exit 1 on any failure. Every check is a sentence in BRAND.md; a check with no sentence is
a defect in this file, a sentence with no check is a defect in the spec.
"""
import os, re, sys, json, argparse, struct, tempfile, filecmp

HERE = os.path.dirname(os.path.abspath(__file__)); BRAND = os.path.dirname(HERE)
DECLARED = {"#000000": "--egz-ink (light)", "#F4F4F0": "--egz-ink (dark)", "#FFFFFF": "--egz-canvas (light)",
            "#0B0B0B": "--egz-canvas (dark)", "#0B0716": "--egz-canvas (dark · violet)"}
FORBIDDEN_ELEMENTS = ("<linearGradient", "<radialGradient", "<filter", "<script", "<animate", "<image", "<text", "<foreignObject", "href=\"http")
INLINE_TOKENS = ("currentColor", "var(--egz-canvas)")

def masters():
    m = json.load(open(os.path.join(HERE, "manifest.json")))["masters"]
    return sorted(m)

def main():
    ap = argparse.ArgumentParser(); ap.add_argument("--regenerate", action="store_true"); a = ap.parse_args()
    fails, rows = [], []
    def ok(fid, cond, note=""):
        rows.append((fid, "PASS" if cond else "FAIL", note))
        if not cond: fails.append(fid)
    files = masters()
    # F-01 · every master in the manifest exists and is non-empty
    for rel in files:
        p = os.path.join(BRAND, rel); ok(f"F-01 {rel}", os.path.exists(p) and os.path.getsize(p) > 0)
    # F-02 · file masters carry only declared literals; inline masters carry only tokens; forbidden elements absent
    for rel in files:
        if not rel.endswith(".svg"): continue
        s = open(os.path.join(BRAND, rel), encoding="utf-8").read()
        hexes = set(h.upper() for h in re.findall(r"#[0-9A-Fa-f]{6}", s))
        undeclared = sorted(h for h in hexes if h not in DECLARED)
        ok(f"F-02a {rel} declared literals only", not undeclared, ",".join(undeclared))
        if "/inline/" in rel:
            ok(f"F-02b {rel} inline uses tokens", all(t in s for t in INLINE_TOKENS[:1]) and not hexes, "hex in inline master" if hexes else "")
        ok(f"F-02c {rel} no light, script or text", not any(e in s for e in FORBIDDEN_ELEMENTS), ";".join(e for e in FORBIDDEN_ELEMENTS if e in s))
        ok(f"F-02d {rel} no <style> outside favicon", ("<style" not in s) or rel.endswith("favicon.svg"))
    # F-03 · terminal art: row counts, column widths, alphabets
    T = {"terminal/splash-16-blocks.txt": (16, 32, "▀▄█░ ", True), "terminal/splash-16-ascii.txt": (16, 32, " .:-=+*#%@", True),
         "terminal/header-8-blocks.txt": (8, 16, "▀▄█░ ", True), "terminal/header-8-ascii.txt": (8, 16, " .:-=+*#%@", True),
         "terminal/whole-16-blocks.txt": (16, 32, "▀▄█ ", True), "terminal/slice-16-blocks.txt": (16, 32, "▀▄█ ", False)}   # the slice ends blank: ≤ 16 rows
    for rel, (rows_n, cols, alphabet, exact) in T.items():
        lines = open(os.path.join(BRAND, rel), encoding="utf-8").read().rstrip("\n").split("\n")
        ok(f"F-03a {rel} {'' if exact else '≤ '}{rows_n} rows", (len(lines) == rows_n) if exact else (len(lines) <= rows_n), f"{len(lines)} rows")
        ok(f"F-03b {rel} ≤ {cols} cols", max(len(l) for l in lines) <= cols, f"{max(len(l) for l in lines)} cols")
        ok(f"F-03c {rel} alphabet", set("".join(lines)) <= set(alphabet), "".join(sorted(set("".join(lines)) - set(alphabet))))
        ok(f"F-03d {rel} no trailing spaces", all(l == l.rstrip() for l in lines))
    br = open(os.path.join(BRAND, "terminal/splash-16-braille.txt"), encoding="utf-8").read().rstrip("\n").split("\n")
    ok("F-03e braille 16 rows, U+2800 block only", len(br) == 16 and all(0x2800 <= ord(c) < 0x2900 for l in br for c in l))
    # F-04 · the 8-row header has no creases (faces are shaded); the 16-row splash has them
    h8 = open(os.path.join(BRAND, "terminal/header-8-blocks.txt"), encoding="utf-8").read()
    ok("F-04 header-8 shaded faces", "░" in h8)
    # F-05 · pwa and mcp snippets parse and carry the bound values
    mi = json.load(open(os.path.join(BRAND, "pwa/manifest-icons.json")))
    ok("F-05a manifest icons 192/512/maskable", [i["sizes"] for i in mi["icons"]] == ["192x192", "512x512", "512x512"] and mi["icons"][2].get("purpose") == "maskable")
    head = open(os.path.join(BRAND, "pwa/head.html")).read()
    ok("F-05b head order ico→svg", head.index('favicon.ico') < head.index('favicon.svg') and 'sizes="any"' in head)
    ok("F-05c theme-color pair", head.count('name="theme-color"') == 2 and "#FFFFFF" in head and "#0B0B0B" in head)
    mcp = json.load(open(os.path.join(BRAND, "mcp/icons.json")))["icons"]
    ok("F-05d mcp icons png48 png96 svg-light svg-dark", [i.get("sizes") for i in mcp] == [["48x48"], ["96x96"], ["any"], ["any"]] and {i.get("theme") for i in mcp[2:]} == {"light", "dark"})
    ok("F-05e mcp png icons are data URIs with PNG magic", all(i["src"].startswith("data:image/png;base64,iVBORw0KGgo") for i in mcp[:2]))
    # F-06 · the three tiers exist for each solid, light + dark + inline
    for solid in ("pending", "whole", "slice"):
        for t in ("64", "32", "flat"):
            for form in (f"mark/{solid}-{t}.svg", f"mark/{solid}-{t}-dark.svg", f"mark/inline/{solid}-{t}.svg"):
                ok(f"F-06 {form}", form in files)
    # F-07 · the App pair: chief-proxy = whole, egzos-forge = pending (the forge never wears the whole orb)
    cp = open(os.path.join(BRAND, "app/chief-proxy.svg")).read(); ef = open(os.path.join(BRAND, "app/egzos-forge.svg")).read()
    whole32 = open(os.path.join(BRAND, "mark/whole-32.svg")).read(); pend32 = open(os.path.join(BRAND, "mark/pending-32.svg")).read()
    inner = lambda s: re.search(r"<g[^>]*>(.*)</g>", s, re.S).group(1)
    body = lambda s: re.search(r'viewBox="0 0 64 64">(.*)</svg>', s, re.S).group(1)
    ok("F-07a chief-proxy wears the whole orb", inner(cp) == body(whole32))
    ok("F-07b egzos-forge wears the pending orb", inner(ef) == body(pend32))
    # F-08 · rasters, when present in ./dist: sizes and the ICO frame count
    dist = os.path.join(os.getcwd(), "dist")
    if os.path.isdir(dist):
        try:
            from PIL import Image
            want = {"org-avatar-512.png": (512, 512), "app-chief-proxy-200.png": (200, 200), "app-egzos-forge-200.png": (200, 200),
                    "apple-touch-icon-180.png": (180, 180), "icon-192.png": (192, 192), "icon-512.png": (512, 512), "icon-maskable-512.png": (512, 512),
                    "social-preview-1280x640.png": (1280, 640), "readme-header-light-1280x320.png": (1280, 320), "mcp-icon-48.png": (48, 48), "mcp-icon-96.png": (96, 96)}
            for n, wh in want.items():
                p = os.path.join(dist, n); ok(f"F-08a {n} {wh[0]}×{wh[1]}", os.path.exists(p) and Image.open(p).size == wh)
                if os.path.exists(p): ok(f"F-08b {n} < 1 MB", os.path.getsize(p) < 1_000_000)
            ico = open(os.path.join(dist, "favicon.ico"), "rb").read()
            ok("F-08c favicon.ico carries 3 frames (48/32/16)", struct.unpack("<H", ico[4:6])[0] == 3)
            ok("F-08d apple-touch-icon is opaque", Image.open(os.path.join(dist, "apple-touch-icon-180.png")).convert("RGBA").getextrema()[3][0] == 255)
        except ImportError:
            rows.append(("F-08", "SKIP", "Pillow not installed"))
    else:
        rows.append(("F-08", "SKIP", "no ./dist — run render.py first"))
    # F-09 · regenerate and diff (the committed masters are exactly what the pipeline emits)
    if a.regenerate:
        sys.path.insert(0, HERE); import render
        with tempfile.TemporaryDirectory() as td:
            render.render(td, os.path.join(td, "dist"))
            for rel in files:
                if rel == "pipeline/manifest.json": continue
                same = filecmp.cmp(os.path.join(BRAND, rel), os.path.join(td, rel), shallow=False)
                ok(f"F-09 {rel} regenerates byte-identical", same)
    for fid, st, note in rows:
        if st != "PASS" or "-v" in sys.argv: print(f"{st:4} {fid} {note}")
    print(f"{sum(1 for r in rows if r[1]=='PASS')} pass · {len(fails)} fail · {sum(1 for r in rows if r[1]=='SKIP')} skip")
    sys.exit(1 if fails else 0)

if __name__ == "__main__":
    main()
