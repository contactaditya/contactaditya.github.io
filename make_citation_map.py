#!/usr/bin/env python3
"""Regenerate citation_map_verified.png from the REGIONS array in index.html.

The map is the one claim on this page that no guard can check: prerender.js
rebuilds markup from the data arrays, but it cannot rebuild a PNG and --check
cannot inspect one. Before this script existed the image was produced by hand
and silently fell six days behind the data (Singapore, Nov 2026). Run this
whenever REGIONS changes.

    pip install geopandas matplotlib
    # country geometry, ~3 MB, sparse checkout of Natural Earth:
    #   git clone --depth 1 --filter=blob:none --sparse \
    #     https://github.com/nvkelso/natural-earth-vector.git
    #   cd natural-earth-vector && git sparse-checkout set geojson
    python3 make_citation_map.py path/to/ne_50m_admin_0_countries.geojson

50m resolution is required, not 110m: the 110m file omits Hong Kong, Macau and
Singapore entirely, all three of which are counted countries or areas.
"""
import json, re, sys, pathlib
import geopandas as gpd
import matplotlib; matplotlib.use("Agg")
import matplotlib.pyplot as plt

W, H = 3208, 1388
BG, LAND, ON, EDGE = "#f5f6f8", "#e1e4e9", "#2b3a8f", "#ffffff"
PROJ = "+proj=robin"
TINY_PX, DOT_PX = 12, 9        # a polygon smaller than its own stroke cannot render

def regions_countries(index_html):
    h = pathlib.Path(index_html).read_text(encoding="utf-8")
    block = re.search(r"REGIONS\s*=\s*\[(.*?)\n\s*\];", h, re.S).group(1)
    out = []
    for row in re.findall(r"\{(?:[^{}]|\{[^{}]*\})*\}", block):
        out += re.findall(r'"([^"]+)"',
                          re.search(r"countries:\s*\[([^\]]*)\]", row).group(1))
    return out

def main(geojson, index_html="index.html", out="citation_map_verified.png"):
    want = set(regions_countries(index_html))
    g = gpd.read_file(geojson)
    g = g[g["NAME"] != "Antarctica"].copy()

    def key(r):
        for col in ("NAME", "NAME_EN", "NAME_LONG", "ADMIN"):
            v = r.get(col)
            if isinstance(v, str) and v in want:
                return v
        return None

    g["match"] = g.apply(key, axis=1)
    matched = set(g["match"].dropna())
    missing = want - matched
    if missing:                       # fail loudly rather than ship a short map
        raise SystemExit(f"no geometry for: {sorted(missing)}")

    gg = g.to_crs(PROJ)
    b = gg.total_bounds
    pad = (b[2] - b[0]) * 0.0012
    x0, x1, y0, y1 = b[0] - pad, b[2] + pad, b[1] - pad, b[3] + pad
    sx = W / (x1 - x0)

    fig = plt.figure(figsize=(W / 100, H / 100), dpi=100)
    ax = fig.add_axes([0, 0, 1, 1]); ax.set_axis_off()
    fig.patch.set_facecolor(BG)
    gg.plot(ax=ax, color=LAND, edgecolor=EDGE, linewidth=0.6)
    sel = gg[gg["match"].notna()]
    sel.plot(ax=ax, color=ON, edgecolor=EDGE, linewidth=0.6)

    dots = []
    for _, r in sel.iterrows():
        bb = r.geometry.bounds
        if max(bb[2] - bb[0], bb[3] - bb[1]) * sx < TINY_PX:
            c = r.geometry.centroid
            dots.append(r["match"])
            ax.plot(c.x, c.y, marker="o", markersize=DOT_PX,
                    color=ON, markeredgewidth=0, zorder=5)

    ax.set_xlim(x0, x1); ax.set_ylim(y0, y1); ax.set_aspect("auto")
    fig.savefig(out, dpi=100, facecolor=BG); plt.close(fig)
    print(f"{out}: {len(want)} countries or areas shaded; dots for {dots}")

if __name__ == "__main__":
    if len(sys.argv) < 2:
        raise SystemExit(__doc__)
    main(*sys.argv[1:])
