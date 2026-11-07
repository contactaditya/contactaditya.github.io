#!/usr/bin/env python3
"""Verify citation_map_verified.png actually shades the REGIONS countries.

The map is the one published claim no other check reaches. prerender.js
rebuilds markup from the data arrays and `--check` compares it, but neither
can look at a PNG. In November 2026 the image sat six days behind the data
after Singapore entered, and measuring the render showed Hong Kong and Macau
had never been drawn at all -- each is smaller than the stroke that outlines
it. Nothing reported either.

This does NOT regenerate the map and diff the bytes. matplotlib, libpng and
freetype differ between machines, so a byte comparison would fail on a clean
checkout and a check that cries wolf gets switched off. Instead it reads the
committed image and asks the question the page actually makes a claim about:
is every counted country shaded, and is anything else shaded that should not
be?

    pip install geopandas matplotlib pillow numpy
    python3 check_citation_map.py path/to/ne_50m_admin_0_countries.geojson

Exits non-zero, naming the countries, if the image and REGIONS disagree.
"""
import sys

import numpy as np
from PIL import Image
from shapely.geometry import Point

from make_citation_map import W, H, ON, TINY_PX, load

TOL = 40            # per-pixel L1 distance that still counts as the shade colour
MIN_SAMPLES = 8     # below this a polygon is treated as a micro-state
SHADED_MIN = 0.60   # a shaded country must be mostly shade colour
UNSHADED_MAX = 0.20 # an unshaded one must be mostly not


def _rgb(h):
    h = h.lstrip("#")
    return np.array([int(h[i:i + 2], 16) for i in (0, 2, 4)])


def interior_samples(geom, x0, x1, y0, y1, step_px=6):
    """Pixel coordinates strictly inside geom, so a neighbour's fill cannot leak in."""
    sx, sy = W / (x1 - x0), H / (y1 - y0)
    inset = geom.buffer(-2.5 / sx)          # pull back from the white border stroke
    if inset.is_empty:
        return []
    bx = inset.bounds
    out = []
    xs = np.arange(bx[0], bx[2] + 1e-9, step_px / sx)
    ys = np.arange(bx[1], bx[3] + 1e-9, step_px / sy)
    for gx in xs:
        for gy in ys:
            if inset.contains(Point(gx, gy)):
                out.append((int((gx - x0) * sx), int((y1 - gy) * sy)))
    return out


def main(geojson, index_html="index.html", png="citation_map_verified.png"):
    gg, want, (x0, x1, y0, y1) = load(geojson, index_html)
    img = np.array(Image.open(png).convert("RGB")).astype(int)
    if img.shape[:2] != (H, W):
        raise SystemExit(f"{png}: expected {W}x{H}, found {img.shape[1]}x{img.shape[0]}")
    on = _rgb(ON)
    sx = W / (x1 - x0)

    def frac_on(pts):
        if not pts:
            return None
        vals = [img[y, x] for x, y in pts if 0 <= x < W and 0 <= y < H]
        if not vals:
            return None
        return float(np.mean([np.abs(v - on).sum() < TOL for v in vals]))

    bad = []
    for name, grp in gg[gg["match"].notna()].groupby("match"):
        geom = grp.geometry.union_all()
        b = geom.bounds
        tiny = max(b[2] - b[0], b[3] - b[1]) * sx < TINY_PX
        pts = interior_samples(geom, x0, x1, y0, y1)
        if tiny or len(pts) < MIN_SAMPLES:
            # too small to fill: the generator marks these with a dot instead
            c = geom.centroid
            cx, cy = int((c.x - x0) * sx), int((y1 - c.y) * (H / (y1 - y0)))
            win = img[max(0, cy - 6):cy + 7, max(0, cx - 6):cx + 7].reshape(-1, 3)
            if not len(win) or not (np.abs(win - on).sum(axis=1) < TOL).any():
                bad.append(f"{name}: counted, but no shaded dot at its position "
                           f"(too small to fill, needs the micro-state marker)")
            continue
        f = frac_on(pts)
        if f is None or f < SHADED_MIN:
            bad.append(f"{name}: counted in REGIONS, but only "
                       f"{0 if f is None else f:.0%} of its area is shaded")

    # and nothing uncounted may be shaded
    for name, grp in gg[gg["match"].isna()].groupby("NAME"):
        geom = grp.geometry.union_all()
        pts = interior_samples(geom, x0, x1, y0, y1)
        if len(pts) < MIN_SAMPLES:
            continue
        f = frac_on(pts)
        if f is not None and f > UNSHADED_MAX:
            bad.append(f"{name}: shaded on the map, but not in REGIONS "
                       f"({f:.0%} of its area)")

    if bad:
        print(f"{png} disagrees with REGIONS:")
        for b in bad:
            print("  " + b)
        print("\nRegenerate it:  python3 make_citation_map.py <ne_50m geojson>")
        raise SystemExit(1)
    print(f"{png}: all {len(want)} countries or areas shaded, nothing else is.")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        raise SystemExit(__doc__)
    main(*sys.argv[1:])
