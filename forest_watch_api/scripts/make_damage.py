"""Find the area where the forest echo dropped and STAYED low after the fire.

Why: the loss area of the first post-fire scene alone is close to the noise level
(single scenes flag tens of hectares from moisture and speckle). Lasting damage is
what shows up again and again. A pixel counts as damaged when its HV is more than
`threshold_db` below the median of all pre-fire scenes in at least MIN_SCENES of the
post-fire scenes. Only connected patches of at least MIN_PATCH_HA are kept.

Writes into the layer folder:
  damage.js           window.NISAR_DAMAGE (area, bounding box, grid cells, mean HV per date)
  damage_outline.png  outline of the damaged area, drawn on the map

Usage:  python forest_watch_api/scripts/make_damage.py [layer_dir]      (default: app/layers_series_all)
Needs:  pillow, numpy
"""
import json
import re
import sys
from pathlib import Path

import numpy as np
from PIL import Image

MIN_PATCH_HA = 1.0

DEFAULT_DIR = Path(__file__).resolve().parents[2] / "app" / "layers_series_all"
layer_dir = Path(sys.argv[1]) if len(sys.argv) > 1 else DEFAULT_DIR
meta = json.loads((layer_dir / "series_meta.json").read_text(encoding="utf-8"))
thr = meta["threshold_db"]
lo, hi = meta["db_range"]["HV"]
W, S, E, N = meta["bbox"]
cell_ha = meta["cell_area_ha"]

scenes = meta["scenes"]
pre = [s for s in scenes if s["date"] < meta["fire"]["start"]]
post = [s for s in scenes if s["date"] > meta["fire"]["end"]]
MIN_SCENES = max(2, len(post) - 1)          # "all but one" of the post-fire scenes


def hv_db(s):
    g = np.asarray(Image.open(layer_dir / s["hv"]).convert("L")).astype(float)
    return lo + g / 255 * (hi - lo)


hv = {s["date"]: hv_db(s) for s in scenes}
pre_median = np.median([hv[s["date"]] for s in pre], axis=0)
hits = sum(((hv[s["date"]] - pre_median) < -thr).astype(int) for s in post)
mask = hits >= MIN_SCENES
H, Wd = mask.shape

# connected patches (4-neighbourhood), keep the big ones
label = np.zeros(mask.shape, int)
patches = []
for y, x in zip(*np.nonzero(mask)):
    if label[y, x]:
        continue
    n = len(patches) + 1
    stack, pix = [(y, x)], []
    label[y, x] = n
    while stack:
        a, b = stack.pop()
        pix.append((a, b))
        for u, v in ((a + 1, b), (a - 1, b), (a, b + 1), (a, b - 1)):
            if 0 <= u < H and 0 <= v < Wd and mask[u, v] and not label[u, v]:
                label[u, v] = n
                stack.append((u, v))
    patches.append(np.array(pix))
big = [p for p in patches if len(p) * cell_ha >= MIN_PATCH_HA]
big.sort(key=len, reverse=True)
keep = np.zeros(mask.shape, bool)
for p in big:
    keep[p[:, 0], p[:, 1]] = True
if not keep.any():
    sys.exit("no lasting damage patch of at least %.1f ha found" % MIN_PATCH_HA)

lat = lambda row: N - (row + 0.5) / H * (N - S)
lng = lambda col: W + (col + 0.5) / Wd * (E - W)
ys, xs = np.nonzero(keep)

# the same cell grid as series_grid.js, so the point chart can use it
grid_js = layer_dir / "series_grid.js"
m = re.search(r'"width":(\d+),"height":(\d+)', grid_js.read_text(encoding="utf-8")) if grid_js.exists() else None
gw, gh = (int(m.group(1)), int(m.group(2))) if m else (80, round(80 * H / Wd))
cells = {}
for y, x in zip(ys, xs):
    key = (int(y * gh // H), int(x * gw // Wd))
    cells[key] = cells.get(key, 0) + 1

out = {
    "method": f"HV more than {thr} dB below the pre-fire median in at least {MIN_SCENES} of {len(post)} post-fire scenes, "
              f"connected patches of at least {MIN_PATCH_HA} ha",
    "threshold_db": thr, "min_scenes": MIN_SCENES, "post_scenes": len(post), "pre_scenes": len(pre),
    "area_ha": round(float(keep.sum() * cell_ha), 1),
    "patches": [{"area_ha": round(float(len(p) * cell_ha), 1),
                 "center": [round(float(lat(p[:, 0].mean())), 5), round(float(lng(p[:, 1].mean())), 5)]} for p in big],
    "bbox": [round(float(lng(xs.min())), 5), round(float(lat(ys.max())), 5), round(float(lng(xs.max())), 5), round(float(lat(ys.min())), 5)],
    "center": [round(float(lat(ys.mean())), 5), round(float(lng(xs.mean())), 5)],
    "width": gw, "height": gh,
    "cells": [[r, c, n] for (r, c), n in sorted(cells.items())],
    "mean_hv_db": {d: round(float(a[keep].mean()), 2) for d, a in hv.items()},
    "mean_hv_rest_db": {d: round(float(a[~keep].mean()), 2) for d, a in hv.items()},
    "outline": "damage_outline.png",
}
(layer_dir / "damage.js").write_text("window.NISAR_DAMAGE = " + json.dumps(out, separators=(",", ":")) + ";\n", encoding="utf-8")


def grow(a, n):
    for _ in range(n):
        b = a.copy()
        b[1:, :] |= a[:-1, :]; b[:-1, :] |= a[1:, :]; b[:, 1:] |= a[:, :-1]; b[:, :-1] |= a[:, 1:]
        a = b
    return a


# outline just outside the area: 2 px black line with a 1 px white edge so it reads on any colour
g1, g3, g4 = grow(keep, 1), grow(keep, 3), grow(keep, 4)
rgba = np.zeros((H, Wd, 4), np.uint8)
rgba[g4 & ~g3] = (255, 255, 255, 255)
rgba[g3 & ~g1] = (0, 0, 0, 255)
Image.fromarray(rgba).save(layer_dir / "damage_outline.png")

print(f"lasting damage: {out['area_ha']} ha in {len(big)} patch(es): {[p['area_ha'] for p in out['patches']]}")
print("mean HV inside per date:", out["mean_hv_db"])
