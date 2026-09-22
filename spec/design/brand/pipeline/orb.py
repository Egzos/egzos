#!/usr/bin/env python3
# Copyright 2026 Ali Sasanian
# SPDX-License-Identifier: Apache-2.0
"""egzos · Direction D · Orb — one analytic geometry, every rendering derived from it.

Geometry (world, y up, z toward the viewer, unit sphere at the origin):
  W = { x < 0, y > 0, z > 0 }  — the quarter-wedge of the upper hemisphere, front-left (the Chief's sketch)
  solids:  "orb"   = sphere − W   (the record with the slice out: pending)
           "whole" = sphere        (merged)
           "slice" = sphere ∩ W    (the proposal — the missing piece alone)
Faces:  0 = sphere body · 1 = wall (plane x=0, outward normal −x) · 2 = floor (y=0, +y) · 3 = back wall (z=0, +z)
Camera: orthographic at azimuth AZ (toward −x, the viewer's left) and elevation EL, looking at the origin.
Light:  Lambert from the upper-left-front with an ambient floor; each texture treatment quantises it.

All vector output is drawn in the 64-unit viewBox the other marks use (sphere radius 27, centre 32,32).
Colours are `currentColor` for ink and `var(--egz-canvas)` for paper unless overridden.
"""
import math, numpy as np

AZ = math.radians(-35.0)
EL = math.radians(25.0)
LIGHT = np.array([-0.45, 0.75, 0.55]); LIGHT /= np.linalg.norm(LIGHT)
CX, CY, RAD = 32.0, 32.0, 27.0

def _rot():
    view = np.array([math.sin(AZ) * math.cos(EL), math.sin(EL), math.cos(AZ) * math.cos(EL)])
    right = np.cross([0.0, 1.0, 0.0], view); right /= np.linalg.norm(right)
    up = np.cross(view, right)
    return np.vstack([right, up, view])

R = _rot(); VIEW = R[2]

def in_wedge(p):
    return (p[..., 0] < 0) & (p[..., 1] > 0) & (p[..., 2] > 0)

# ───────────────────────────── ray-cast ─────────────────────────────
def raycast(n=512, margin=1.06, solid="orb"):
    """Orthographic ray-cast → face id (−1 bg, 0 body, 1 wall, 2 floor, 3 back wall), shade [0,1], hit points."""
    lin = np.linspace(-margin, margin, n)
    u, v = np.meshgrid(lin, -lin)
    o = np.stack([u, v, np.full_like(u, 4.0)], -1) @ R            # camera → world
    d = R.T @ np.array([0.0, 0.0, -1.0])
    b = o @ d; c = (o * o).sum(-1) - 1.0
    disc = b * b - c; hit = disc > 0
    sq = np.sqrt(np.clip(disc, 0, None)); t1 = -b - sq; t2 = -b + sq
    p1 = o + t1[..., None] * d
    face = np.full(u.shape, -1, dtype=int); pts = np.zeros(o.shape); normal = np.zeros(o.shape)
    w1 = in_wedge(p1)
    if solid == "whole":
        body = hit
    elif solid == "slice":
        body = hit & w1
    else:
        body = hit & ~w1
    face[body] = 0; pts[body] = p1[body]; normal[body] = p1[body]
    if solid == "orb":
        ent = hit & w1
        tbest = np.full(u.shape, np.inf); fbest = np.full(u.shape, -1)
        for ax, fid in ((0, 1), (1, 2), (2, 3)):
            if abs(d[ax]) < 1e-12: continue
            t = -o[..., ax] / d[ax]
            ok = ent & (t > t1) & (t < t2) & (t < tbest)
            tbest[ok] = t[ok]; fbest[ok] = fid
        cut = ent & (fbest >= 0)
        pc = o + tbest[..., None] * d
        face[cut] = fbest[cut]; pts[cut] = pc[cut]
        for ax, fid, sgn in ((0, 1, -1.0), (1, 2, 1.0), (2, 3, 1.0)):
            m = cut & (fbest == fid); nrm = np.zeros(3); nrm[ax] = sgn; normal[m] = nrm
    shade = np.clip(normal @ LIGHT, 0, 1)
    shade = 0.18 + 0.82 * shade
    shade[face < 0] = 0
    return face, shade, pts

def project(p):
    c = p @ R.T
    return c[..., 0], -c[..., 1]

def visible_body(p):
    return (p @ VIEW) > 0

def _uv(u, v):
    return CX + u * RAD, CY + v * RAD

def _poly(us, vs, keep):
    frags, cur = [], []
    for i in range(len(us)):
        if keep[i]:
            x, y = _uv(us[i], vs[i]); cur.append(f"{x:.1f} {y:.1f}")
        elif cur:
            frags.append(cur); cur = []
    if cur: frags.append(cur)
    return " ".join("M" + " L".join(f) for f in frags if len(f) > 1)

# ───────────────────────────── analytic curves ─────────────────────────────
def silhouette_path(solid="orb"):
    a = np.linspace(0, 2 * math.pi, 480, endpoint=False)
    e1 = np.cross(VIEW, [0, 1, 0]); e1 /= np.linalg.norm(e1); e2 = np.cross(VIEW, e1)
    p = np.outer(np.cos(a), e1) + np.outer(np.sin(a), e2)
    u, v = project(p)
    keep = np.ones(len(a), bool) if solid == "whole" else (in_wedge(p) if solid == "slice" else ~in_wedge(p))
    return _poly(u, v, keep)

def _arc(fid, n=72):
    a = np.linspace(0, math.pi / 2, n)
    if fid == 1:   return np.stack([np.zeros_like(a), np.cos(a), np.sin(a)], -1)
    elif fid == 2: return np.stack([-np.sin(a), np.zeros_like(a), np.cos(a)], -1)
    else:          return np.stack([-np.sin(a), np.cos(a), np.zeros_like(a)], -1)

def cut_edges_paths(creases=True, arcs=True):
    out = []
    if arcs:
        for fid in (1, 2, 3):
            u, v = project(_arc(fid)); out.append(_poly(u, v, np.ones(len(u), bool)))
    if creases:
        t = np.linspace(0, 1, 2)
        for p in (np.stack([np.zeros_like(t), t, np.zeros_like(t)], -1), np.stack([np.zeros_like(t), np.zeros_like(t), t], -1),
                  np.stack([-t, np.zeros_like(t), np.zeros_like(t)], -1)):
            u, v = project(p); out.append(_poly(u, v, np.ones(2, bool)))
    return " ".join(out)

def face_polygon(fid, n=90):
    p = np.vstack([np.zeros((1, 3)), _arc(fid, n)])
    u, v = project(p)
    return "M" + " L".join(f"{x:.2f} {y:.2f}" for x, y in zip(*_uv(u, v))) + " Z"

def slice_polygon():
    """Image-space outline of the slice alone: the ghost arc of the silhouette + the three face arcs' outer sides."""
    return _mask_path(raycast(512, margin=1.0, solid="slice")[0] == 0, 512, 1.0)

def _mask_path(mask, n, margin, tol=0.08):
    """Trace a binary mask into a smooth SVG polygon with matplotlib's marching squares, then simplify."""
    import matplotlib; matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    fig = plt.figure(); ax = fig.add_subplot()
    cs = ax.contour(mask.astype(float), levels=[0.5])
    paths = []
    if hasattr(cs, "allsegs"):
        paths = [np.asarray(seg) for seg in cs.allsegs[0]]
    else:
        for p in cs.get_paths():
            for poly in p.to_polygons(closed_only=False):
                paths.append(np.asarray(poly))
    plt.close(fig)
    scale = 2 * margin * RAD / (n - 1)
    out = []
    for seg in paths:
        if len(seg) < 8: continue
        pts = _simplify(seg, tol / scale)
        d = "M" + " L".join(f"{CX - margin*RAD + x*scale:.2f} {CY - margin*RAD + y*scale:.2f}" for x, y in pts) + " Z"
        out.append(d)
    return "".join(out)

def _simplify(pts, eps):
    """Douglas–Peucker."""
    pts = np.asarray(pts)
    if len(pts) < 3: return pts
    def dp(lo, hi, keep):
        a, b = pts[lo], pts[hi]
        if hi - lo < 2: return
        ab = b - a; L = np.hypot(*ab) or 1e-9
        d = np.abs(np.cross(ab, pts[lo+1:hi] - a)) / L
        i = np.argmax(d)
        if d[i] > eps:
            k = lo + 1 + i; keep[k] = True; dp(lo, k, keep); dp(k, hi, keep)
    keep = np.zeros(len(pts), bool); keep[0] = keep[-1] = True
    # closed loops: first == last, so anchor the point farthest from the start before recursing
    far = int(np.argmax(np.hypot(*(pts - pts[0]).T)))
    if far not in (0, len(pts) - 1):
        keep[far] = True; dp(0, far, keep); dp(far, len(pts) - 1, keep)
    else:
        dp(0, len(pts) - 1, keep)
    return pts[keep]

def body_region_path(solid="orb"):
    return _mask_path(raycast(512, margin=1.0, solid=solid)[0] == 0, 512, 1.0)

# ───────────────────────────── vector treatments ─────────────────────────────
def flat_svg_inner(ink="currentColor", paper="var(--egz-canvas)", stroke=3.0, solid="orb", creases=True):
    """Two-tone form for ≤ 24 px: body solid ink; cut faces paper; creases so the notch reads as a cut."""
    out = [f'<path d="{body_region_path(solid)}" fill="{ink}"/>']
    if solid == "orb":
        for fid in (1, 2, 3):
            out.append(f'<path d="{face_polygon(fid)}" fill="{paper}"/>')
        if creases:
            out.append(f'<path d="{cut_edges_paths(arcs=False)}" fill="none" stroke="{ink}" stroke-width="{stroke}" stroke-linecap="butt" stroke-linejoin="miter"/>')
    return "\n".join(out)

def _hatch_paths(gap=0.13):
    hatch = []
    for fid in (1, 2, 3):
        for c in np.arange(-1.0, 1.0, gap):
            s = np.linspace(-1.2, 1.2, 96); r2 = math.sqrt(2)
            if fid == 1:   p = np.stack([np.zeros_like(s), (s + c) / r2, (s - c) / r2], -1)
            elif fid == 2: p = np.stack([-(s + c) / r2, np.zeros_like(s), (s - c) / r2], -1)
            else:          p = np.stack([-(s + c) / r2, (s - c) / r2, np.zeros_like(s)], -1)
            inside = (p * p).sum(-1) < 0.99
            if fid == 1: inside &= (p[..., 1] > 0) & (p[..., 2] > 0)
            if fid == 2: inside &= (p[..., 0] < 0) & (p[..., 2] > 0)
            if fid == 3: inside &= (p[..., 0] < 0) & (p[..., 1] > 0)
            u, v = project(p); d = _poly(u, v, inside)
            if d: hatch.append(d)
    return " ".join(hatch)

def _latitude_paths(step_deg=10, solid="orb"):
    lat = []
    for deg in range(-90 + step_deg, 90, step_deg):
        y = math.sin(math.radians(deg)); r = math.cos(math.radians(deg))
        a = np.linspace(0, 2 * math.pi, 240, endpoint=False)
        p = np.stack([r * np.cos(a), np.full_like(a, y), r * np.sin(a)], -1)
        keep = visible_body(p)
        if solid == "orb": keep &= ~in_wedge(p)
        if solid == "slice": keep &= in_wedge(p)
        u, v = project(p); d = _poly(u, v, keep)
        if d: lat.append(d)
    return " ".join(lat)

def contour_svg_inner(ink="currentColor", paper="var(--egz-canvas)", step_deg=10, hair=0.9, edge=2.2, solid="orb"):
    """Surveyor's orb: latitude hairlines on the body; 45° hairline hatch on the cut faces; ink edges."""
    out = []
    if solid == "orb":
        for fid in (1, 2, 3): out.append(f'<path d="{face_polygon(fid)}" fill="{paper}"/>')
        out.append(f'<path d="{_hatch_paths()}" fill="none" stroke="{ink}" stroke-width="{hair}"/>')
    out.append(f'<path d="{_latitude_paths(step_deg, solid)}" fill="none" stroke="{ink}" stroke-width="{hair}"/>')
    if solid == "orb":
        out.append(f'<path d="{cut_edges_paths()}" fill="none" stroke="{ink}" stroke-width="{edge}" stroke-linejoin="miter"/>')
    out.append(f'<path d="{silhouette_path(solid)}" fill="none" stroke="{ink}" stroke-width="{edge}"/>')
    return "\n".join(out)

BAYER8 = np.array([[0, 48, 12, 60, 3, 51, 15, 63], [32, 16, 44, 28, 35, 19, 47, 31], [8, 56, 4, 52, 11, 59, 7, 55],
                   [40, 24, 36, 20, 43, 27, 39, 23], [2, 50, 14, 62, 1, 49, 13, 61], [34, 18, 46, 30, 33, 17, 45, 29],
                   [10, 58, 6, 54, 9, 57, 5, 53], [42, 26, 38, 22, 41, 25, 37, 21]]) / 64.0

def field(cells, ss=4, solid="orb", margin=1.0):
    n = cells * ss
    face, shade, _ = raycast(n, margin=margin, solid=solid)
    f = face.reshape(cells, ss, cells, ss); s = shade.reshape(cells, ss, cells, ss)
    body_cov = (f == 0).mean((1, 3)); cut_cov = (f > 0).mean((1, 3))
    body_shade = np.where(body_cov > 0, (s * (f == 0)).sum((1, 3)) / np.maximum((f == 0).sum((1, 3)), 1), 0)
    return body_cov, cut_cov, body_shade

def _line_mask(cells, margin=1.0, thick=1.0):
    """Rasterise the creases and cut arcs onto a cells×cells grid (True where a line passes)."""
    m = np.zeros((cells, cells), bool)
    segs = []
    for fid in (1, 2, 3):
        u, v = project(_arc(fid, 400)); segs.append(np.stack([u, v], -1))
    t = np.linspace(0, 1, 200)
    for p in (np.stack([np.zeros_like(t), t, np.zeros_like(t)], -1), np.stack([np.zeros_like(t), np.zeros_like(t), t], -1),
              np.stack([-t, np.zeros_like(t), np.zeros_like(t)], -1)):
        u, v = project(p); segs.append(np.stack([u, v], -1))
    for s in segs:
        col = ((s[:, 0] + margin) / (2 * margin) * cells).astype(int); row = ((s[:, 1] + margin) / (2 * margin) * cells).astype(int)
        ok = (col >= 0) & (col < cells) & (row >= 0) & (row < cells)
        m[row[ok], col[ok]] = True
    return m

def dither_grid(cells, ss=4, gamma=1.0, solid="orb", creases=False):
    """Binary ink grid: body dithered by shade, limb kept, optional creases; plus a cut-face mask."""
    body_cov, cut_cov, body_shade = field(cells, ss=ss, solid=solid)
    ink_level = (1.0 - body_shade) ** gamma
    tile = np.tile(BAYER8, (cells // 8 + 1, cells // 8 + 1))[:cells, :cells]
    inside = body_cov >= 0.5
    ink = inside & (ink_level > tile)
    pad = np.pad(body_cov, 1)
    edge = inside & ((pad[:-2, 1:-1] < 0.5) | (pad[2:, 1:-1] < 0.5) | (pad[1:-1, :-2] < 0.5) | (pad[1:-1, 2:] < 0.5))
    ink |= edge
    if creases and solid == "orb":
        ink |= _line_mask(cells)
    return ink, cut_cov >= 0.5

def dither_svg_inner(cells=64, ink="currentColor", paper="var(--egz-canvas)", edges=True, solid="orb"):
    grid, cut = dither_grid(cells, solid=solid)
    scale = 2 * RAD / cells
    parts = []
    for r in range(cells):
        row = grid[r]
        if not row.any(): continue
        d = np.diff(np.concatenate([[0], row.astype(int), [0]]))
        for s, e in zip(np.where(d == 1)[0], np.where(d == -1)[0]):
            x = CX - RAD + s * scale; y = CY - RAD + r * scale
            parts.append(f"M{x:.2f} {y:.2f}h{(e - s) * scale:.2f}v{scale + 0.02:.2f}h{-(e - s) * scale:.2f}Z")
    out = [f'<path d="{"".join(parts)}" fill="{ink}" shape-rendering="crispEdges"/>']
    if edges and solid == "orb":
        out.append(f'<path d="{cut_edges_paths()}" fill="none" stroke="{ink}" stroke-width="{max(1.2, scale*0.9):.2f}" stroke-linejoin="miter"/>')
    return "\n".join(out)

def halftone_svg_inner(cells=24, ink="currentColor", paper="var(--egz-canvas)", edge=2.0, solid="orb"):
    body_cov, cut_cov, body_shade = field(cells, ss=4, solid=solid)
    scale = 2 * RAD / cells
    out = []
    if solid == "orb":
        for fid in (1, 2, 3): out.append(f'<path d="{face_polygon(fid)}" fill="{paper}"/>')
    dots = []
    for r in range(cells):
        for c in range(cells):
            if body_cov[r, c] < 0.35: continue
            lvl = 1.0 - body_shade[r, c]; rad = scale * 0.62 * math.sqrt(max(lvl, 0.06))
            x = CX - RAD + (c + 0.5) * scale; y = CY - RAD + (r + 0.5) * scale
            dots.append(f'<circle cx="{x:.2f}" cy="{y:.2f}" r="{rad:.2f}"/>')
    cid = f"orb-clip-{solid}"
    out.append(f'<clipPath id="{cid}"><path d="{body_region_path(solid)}"/></clipPath>')
    out.append(f'<g fill="{ink}" clip-path="url(#{cid})">{"".join(dots)}</g>')
    if solid == "orb":
        out.append(f'<path d="{cut_edges_paths()}" fill="none" stroke="{ink}" stroke-width="{edge}" stroke-linejoin="miter"/>')
    out.append(f'<path d="{silhouette_path(solid)}" fill="none" stroke="{ink}" stroke-width="{edge}"/>')
    return "\n".join(out)

# ───────────────────────────── terminal ─────────────────────────────
BLOCKS = {(0, 0): " ", (1, 0): "▀", (0, 1): "▄", (1, 1): "█"}
ASCII_RAMP = " .:-=+*#%@"

def terminal(rows=16, mode="blocks", gamma=1.0, solid="orb", faces="paper", creases=True):
    """Text art. Cells are 1:2. blocks: half-blocks over a (2·rows)² dither field, creases in ink, cut faces empty
    (or '░' when faces='shade'); braille: 2×4 dots per cell; ascii: one level per cell from the shade."""
    if mode == "blocks":
        H = rows * 2
        grid, cut = dither_grid(H, gamma=gamma, solid=solid, creases=creases)
        lines = []
        for r in range(rows):
            top, bot = grid[2 * r], grid[2 * r + 1]
            ctop, cbot = cut[2 * r], cut[2 * r + 1]
            line = ""
            for c in range(H):
                ch = BLOCKS[(int(top[c]), int(bot[c]))]
                if ch == " " and faces == "shade" and ctop[c] and cbot[c]:
                    ch = "░"
                line += ch
            lines.append(line.rstrip())
        return "\n".join(lines)
    if mode == "braille":
        H = rows * 4
        grid, cut = dither_grid(H, gamma=gamma, solid=solid, creases=creases)
        bits = [(0, 0, 0x01), (1, 0, 0x02), (2, 0, 0x04), (0, 1, 0x08), (1, 1, 0x10), (2, 1, 0x20), (3, 0, 0x40), (3, 1, 0x80)]
        lines = []
        for r in range(rows):
            line = ""
            for c in range(rows * 2):
                v = 0
                for dy, dx, b in bits:
                    if grid[4 * r + dy, 2 * c + dx]: v |= b
                line += chr(0x2800 + v)
            lines.append(line.rstrip("⠀"))
        return "\n".join(lines)
    if mode == "ascii":
        body_cov, cut_cov, body_shade = field(rows * 2, ss=3, solid=solid)
        lines = []
        for r in range(rows):
            line = ""
            for c in range(rows * 2):
                cov = body_cov[2 * r:2 * r + 2, c].mean(); sh = body_shade[2 * r:2 * r + 2, c].mean()
                line += " " if cov < 0.5 else ASCII_RAMP[min(9, int((1.0 - sh) * 9 + 0.5))]
            lines.append(line.rstrip())
        return "\n".join(lines)
    raise ValueError(mode)

if __name__ == "__main__":
    print(terminal(8)); print(); print(terminal(16))
