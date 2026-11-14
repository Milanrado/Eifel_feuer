"""Steady radar layers: take out what is weather, keep what lasts.

Why: the raw echo of a whole scene goes up and down with rain and soil moisture. On a map with
fixed colours that looks like forest and buildings appearing and vanishing from one pass to the
next, which did not happen. Two standard steps fix the reading without inventing anything:

1. Scene balance. For each date, the median difference to the pixel-wise median of all dates is
   subtracted (one number per date and band). This removes the scene-wide wet/dry shift.
2. Median of three passes. Each pixel takes the median of the previous, the current and the next
   date. A one-off flicker (speckle, a wet field on one morning) disappears, a change that lasts
   for two passes or more stays, on the date it first shows. The first and last date have only
   one neighbour and use the mean of the two.

3. No new forest. Trees do not grow in weeks, so the forest value of a pixel may fall but never rise
   above its level before the fire (pixel-wise median of the steadied pre-fire dates). Fields and
   meadows do get a stronger echo when they are wet or overgrown; without this rule that reads as
   "more forest". Only the forest channel is capped, the other channels keep the full signal.

Reads composite_<date>.png (red = HH, green = HV, same dB ranges as series_meta.json) and writes
stable_<date>.png (red = HH, green = forest = capped HV, blue = HH - HV, same encoding) plus stable.js
(window.NISAR_STABLE). The app uses these for its layers when stable.js exists.

Usage:  python forest_watch_api/scripts/make_stable.py [layer_dir]      (default: app/layers_series_all)
Needs:  pillow, numpy
"""
import json
import sys
from pathlib import Path

import numpy as np
from PIL import Image

DEFAULT_DIR = Path(__file__).resolve().parents[2] / "app" / "layers_series_all"
layer_dir = Path(sys.argv[1]) if len(sys.argv) > 1 else DEFAULT_DIR
meta = json.loads((layer_dir / "series_meta.json").read_text(encoding="utf-8"))
scenes = meta["scenes"]
dates = [s["date"] for s in scenes]
rng = {"HH": meta["db_range"]["HH"], "HV": meta["db_range"]["HV"], "ratio": meta["db_range"]["ratio"]}

hh, hv, alpha = {}, {}, {}
for s in scenes:
    a = np.asarray(Image.open(layer_dir / s["composite"]).convert("RGBA")).astype("float32")
    hh[s["date"]] = rng["HH"][0] + a[..., 0] / 255 * (rng["HH"][1] - rng["HH"][0])
    hv[s["date"]] = rng["HV"][0] + a[..., 1] / 255 * (rng["HV"][1] - rng["HV"][0])
    alpha[s["date"]] = a[..., 3] > 0


def balance(band):
    """Subtract each scene's median offset against the all-date median image."""
    ref = np.median([band[d] for d in dates], axis=0)
    off = {d: float(np.median((band[d] - ref)[alpha[d]])) for d in dates}
    return {d: band[d] - off[d] for d in dates}, off


def median3(band):
    out = {}
    for i, d in enumerate(dates):
        win = [band[dates[j]] for j in range(max(0, i - 1), min(len(dates), i + 2))]
        out[d] = np.median(win, axis=0) if len(win) == 3 else np.mean(win, axis=0)
    return out


hh_b, off_hh = balance(hh)
hv_b, off_hv = balance(hv)
hh_s, hv_s = median3(hh_b), median3(hv_b)

# forest channel: never above the level before the fire
pre = [d for d in dates if d < meta["fire"]["start"]] or dates[:1]
forest_ref = np.median([hv_s[d] for d in pre], axis=0)
forest = {d: np.minimum(hv_s[d], forest_ref) for d in dates}


def enc(x, lo, hi):
    return (255 * np.clip((x - lo) / (hi - lo), 0, 1)).astype("uint8")


files = {}
for d in dates:
    name = f"stable_{d}.png"
    rgba = np.dstack([enc(hh_s[d], *rng["HH"]), enc(forest[d], *rng["HV"]), enc(hh_s[d] - hv_s[d], *rng["ratio"]),
                      np.where(alpha[d], 255, 0).astype("uint8")])
    Image.fromarray(rgba, "RGBA").save(layer_dir / name, optimize=True)
    files[d] = name

out = {
    "method": "scene offset against the all-date median removed (one value per date and band), "
              "then pixel-wise median of three consecutive passes; the forest channel (green) is HV capped at "
              f"its pre-fire level (median of the {len(pre)} steadied pre-fire dates)",
    "forest_cap": True,
    "window": 3,
    "offsets_db": {"HH": {d: round(v, 2) for d, v in off_hh.items()}, "HV": {d: round(v, 2) for d, v in off_hv.items()}},
    "files": files,
}
(layer_dir / "stable.js").write_text("window.NISAR_STABLE = " + json.dumps(out, separators=(",", ":")) + ";\n", encoding="utf-8")


def share(band, limit):
    return [round(100 * float((band[d] > limit)[alpha[d]].mean()), 1) for d in dates]


print(f"wrote {len(files)} stable layers and stable.js to {layer_dir}")
print("scene offsets removed, dB   HH:", out["offsets_db"]["HH"])
print("                            HV:", out["offsets_db"]["HV"])
print("share of area with HV > -12 dB, raw   :", share(hv, -12))
print("                               steady :", share(hv_s, -12))
print("                               forest :", share(forest, -12), "(capped at the pre-fire level)")
print("share of area with HV > -10 dB, steady:", share(hv_s, -10))
print("                               forest :", share(forest, -10))
print("share of area with HH > -3 dB, raw    :", share(hh, -3))
print("                              steady  :", share(hh_s, -3))
