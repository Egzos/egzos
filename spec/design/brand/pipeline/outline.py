#!/usr/bin/env python3
# Copyright 2026 Ali Sasanian
# SPDX-License-Identifier: Apache-2.0
"""Outline a string into SVG path data using a TTF (IBM Plex), so wordmarks never depend on
installed fonts. Pure fontTools. Units: the returned path is in font units scaled to `size` px,
baseline at y=0 (SVG y-down), origin at x=0. Applies kerning from GPOS pair adjustments where
present (simple pair lookups only) and an optional uniform tracking in em.

    from outline import outline
    d, advance = outline("egzos", "fonts/IBMPlexSans-Medium.ttf", size=64, tracking=0)
"""
from fontTools.ttLib import TTFont
from fontTools.pens.svgPathPen import SVGPathPen
from fontTools.pens.transformPen import TransformPen
from functools import lru_cache


@lru_cache(maxsize=None)
def _font(path):
    return TTFont(path)


def _kerning(font):
    """Return dict[(left_glyph, right_glyph)] -> xAdvance adjustment (font units) from GPOS PairPos."""
    kern = {}
    if "GPOS" not in font:
        return kern
    gpos = font["GPOS"].table
    for lookup in gpos.LookupList.Lookup:
        subtables = lookup.SubTable
        for st in subtables:
            if getattr(st, "LookupType", lookup.LookupType) == 9:  # extension
                st = st.ExtSubTable
            if st.__class__.__name__ != "PairPos" and getattr(st, "Format", None) is None:
                continue
            if not hasattr(st, "Coverage"):
                continue
            if st.Format == 1:
                firsts = st.Coverage.glyphs
                for i, ps in enumerate(st.PairSet):
                    for pvr in ps.PairValueRecord:
                        v1 = pvr.Value1
                        if v1 is not None and getattr(v1, "XAdvance", 0):
                            kern[(firsts[i], pvr.SecondGlyph)] = v1.XAdvance
            elif st.Format == 2:
                firsts = st.Coverage.glyphs
                cd1 = st.ClassDef1.classDefs
                cd2 = st.ClassDef2.classDefs
                # invert class maps
                by_c2 = {}
                for g, c in cd2.items():
                    by_c2.setdefault(c, []).append(g)
                for g1 in firsts:
                    c1 = cd1.get(g1, 0)
                    rec1 = st.Class1Record[c1]
                    for c2, rec2 in enumerate(rec1.Class2Record):
                        v1 = rec2.Value1
                        if v1 is not None and getattr(v1, "XAdvance", 0):
                            for g2 in by_c2.get(c2, []):
                                kern.setdefault((g1, g2), v1.XAdvance)
    return kern


def outline(text, font_path, size=64, tracking=0.0, kern=True):
    font = _font(font_path)
    upem = font["head"].unitsPerEm
    scale = size / upem
    cmap = font.getBestCmap()
    glyphset = font.getGlyphSet()
    hmtx = font["hmtx"]
    kerning = _kerning(font) if kern else {}
    names = [cmap[ord(ch)] for ch in text]
    x = 0.0
    parts = []
    for i, gname in enumerate(names):
        pen = SVGPathPen(glyphset)
        # flip y (font y-up -> SVG y-down) and translate to current x
        tpen = TransformPen(pen, (scale, 0, 0, -scale, x, 0))
        glyphset[gname].draw(tpen)
        d = pen.getCommands()
        if d:
            parts.append(d)
        adv = hmtx[gname][0]
        x += adv * scale
        if i + 1 < len(names):
            x += kerning.get((gname, names[i + 1]), 0) * scale
            x += tracking * size
    return " ".join(parts), x


def metrics(font_path, size=64):
    font = _font(font_path)
    upem = font["head"].unitsPerEm
    s = size / upem
    os2 = font["OS/2"]
    return {
        "ascender": font["hhea"].ascent * s,
        "descender": font["hhea"].descent * s,
        "xHeight": getattr(os2, "sxHeight", 0) * s,
        "capHeight": getattr(os2, "sCapHeight", 0) * s,
    }


if __name__ == "__main__":
    import sys
    d, adv = outline(sys.argv[1], sys.argv[2], size=float(sys.argv[3]) if len(sys.argv) > 3 else 64)
    print(f"advance={adv:.2f}")
    print(d[:400], "...")
