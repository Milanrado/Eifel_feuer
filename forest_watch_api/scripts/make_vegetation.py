"""Map helpers for one study area: where the Vegetation scale starts, where buildings and water are.

Why: the Vegetation layer shows the radar vegetation index RVI = 4*HV / (HH + HV). Buildings have the lowest
RVI of all (walls and ground throw the pulse straight back in HH, little comes back in HV), so with a fixed
scale they take the bottom of the colour range and burned forest looks only "medium". This script gives the
app two things for one study area:

1. rvi_burned: the mean RVI of the lasting damage area at its lowest point after the fire. The app starts the
   Vegetation colour scale there, so burned forest gets the lowest colour, not the houses.
   The damage area is found with the same rule as make_damage.py (HV more than threshold_db below the
   pre-fire median in all but one post-fire scene, connected patches of at least 1 ha); the script checks
   that it gets the same area as damage.js.
2. buildings.png: pixels that behave like buildings in EVERY image before the fire: HH at least
   BLD_HH_DB dB and HH - HV at least BLD_RATIO_DB dB (median). Only pre-fire images are used, because burned
   forest can also give a bright HH echo (bare trunks and ground form a corner). The app paints them in a
   neutral grey that is not on the colour scale.
   Checked against OpenStreetMap buildings for the Gironde box (Le Porge / Saumos area): about 95 % of the
   marked pixels lie at an OSM building. In hilly terrain (Eifel) the same rule also marks steep slopes that
   face the satellite (about 70 %), so use it only where that check holds.
3. water.png: open water (bays, lakes). Smooth water mirrors the pulse away, so both echoes are very low in
   (almost) EVERY image: the 90th percentile over all dates of HV at most WATER_HV_DB and of HH at most WATER_HH_DB.
   Bare fields, runways and burned forest are dark only in some images (crops grow, rain roughens the soil, the
   forest was bright before the fire), so they stay out. In the Gironde the bay and the Lac de Lacanau stay below
   -21.5 dB HV and -15.7 dB HH in every image; the darkest other areas (fields, Mérignac airport) reach -20.3 dB
   HV or -15.0 dB HH at least once. Thin lines such as runways are removed, only areas of at
   least WATER_MIN_HA stay, and small gaps inside water are closed. The app paints it in a calm blue-grey on
   every layer, because the colours of the layers mean nothing on water.

Reads series_meta.json, composite_<date>.png (raw, for buildings and water), stable_<date>.png or
composite_<date>.png (whatever the app shows, for RVI) and hv_<date>.png (damage rule). Writes buildings.png,
water.png and vegetation.js (window.NISAR_VEGETATION).

Usage:  python forest_watch_api/scripts/make_vegetation.py app/layers_series_gironde
Needs:  pillow, numpy, scipy
"""
import json
import sys
from pathlib import Path

import numpy as np
from PIL import Image
from scipy import ndimage

BLD_HH_DB = -3.0        # HH at least this bright in every pre-fire image
BLD_RATIO_DB = 7.0      # and HH - HV at least this (median of the pre-fire images): surface beats volume
MIN_PATCH_HA = 1.0      # same as make_damage.py
GREY = (138, 143, 152)  # neutral, not on the brown-to-green Vegetation scale
WATER_HV_DB = -21.0     # water: HV at most this in (almost) every image (90th percentile over the dates)
WATER_HH_DB = -14.5     # and HH at most this
WATER_MIN_HA = 500.0    # only large water bodies: smaller dark patches in the Gironde were a mix of ponds and
                        # bare fields (OpenStreetMap check: 2 of 5 were water), so they are left alone
WATER_RGB = (184, 196, 206)   # calm blue-grey, on no colour scale of the app

if len(sys.argv) < 2:
    sys.exit(__doc__)
layer_dir = Path(sys.argv[1])
meta = json.loads((layer_dir / "series_meta.json").read_text(encoding="utf-8"))
rng = meta["db_range"]
scenes = meta["scenes"]
pre = [s for s in scenes if s["date"] < meta["fire"]["start"]]
post = [s for s in scenes if s["date"] > meta["fire"]["end"]]
steady = (layer_dir / "stable.js").exists()


def band(path, k, lo, hi):
    a = np.asarray(Image.open(layer_dir / path).convert("RGBA")).astype(float)
    return lo + a[..., k] / 255 * (hi - lo)


def rvi(ratio_db):
    q = 10 ** (-ratio_db / 10)      # HV / HH, linear
    return 4 * q / (1 + q)


# ---------------------------------------------------------------- 1. damage area (rule of make_damage.py)
hv = {s["date"]: band(s["hv"], 0, *rng["HV"]) for s in scenes}
pre_median = np.median([hv[s["date"]] for s in pre], axis=0)
hits = sum(((hv[s["date"]] - pre_median) < -meta["threshold_db"]).astype(int) for s in post)
mask = hits >= max(2, len(post) - 1)
lab, n = ndimage.label(mask)                       # 4-neighbourhood, like make_damage.py
sizes = ndimage.sum(mask, lab, range(1, n + 1))
keep = np.isin(lab, 1 + np.flatnonzero(sizes * meta["cell_area_ha"] >= MIN_PATCH_HA))
area_ha = round(float(keep.sum() * meta["cell_area_ha"]), 1)
dmg = layer_dir / "damage.js"
if dmg.exists():
    s = dmg.read_text(encoding="utf-8")
    ref = json.loads(s[s.index("{"): s.rindex("}") + 1])["area_ha"]
    if abs(ref - area_ha) > 0.5:
        sys.exit(f"damage area differs from damage.js: {area_ha} ha here, {ref} ha there. Rerun make_damage.py first.")

# RVI from the same images the app shows (steadied when stable.js exists)
shown = lambda s: (f"stable_{s['date']}.png" if steady else s["composite"])
rvi_post = {s["date"]: float(rvi(band(shown(s), 2, *rng["ratio"])[keep]).mean()) for s in post}
burned_date = min(rvi_post, key=rvi_post.get)
rvi_pre = float(np.mean([rvi(band(shown(s), 2, *rng["ratio"])[keep]).mean() for s in pre]))

# ---------------------------------------------------------------- 2. buildings (raw pre-fire images only)
hh_pre = np.array([band(s["composite"], 0, *rng["HH"]) for s in pre])
ratio_pre = np.array([band(s["composite"], 2, *rng["ratio"]) for s in pre])
bld = np.all(hh_pre >= BLD_HH_DB, axis=0) & (np.median(ratio_pre, axis=0) >= BLD_RATIO_DB)
rgba = np.zeros(bld.shape + (4,), np.uint8)
rgba[bld] = GREY + (255,)
Image.fromarray(rgba, "RGBA").save(layer_dir / "buildings.png", optimize=True)

# ---------------------------------------------------------------- 3. water (dark in almost every image)
hh_all = np.percentile([band(s["composite"], 0, *rng["HH"]) for s in scenes], 90, axis=0)
hv_all = np.percentile([band(s["composite"], 1, *rng["HV"]) for s in scenes], 90, axis=0)
water = (hv_all <= WATER_HV_DB) & (hh_all <= WATER_HH_DB)
water = ndimage.binary_opening(water, iterations=1)            # drop thin lines (runways, roads)
wl, wn = ndimage.label(water)
wsz = ndimage.sum(water, wl, range(1, wn + 1))
water = np.isin(wl, 1 + np.flatnonzero(wsz * meta["cell_area_ha"] >= WATER_MIN_HA))
water = ndimage.binary_closing(water, iterations=2) | water     # close small gaps (speckle, boats, buoys)
water &= ~bld
wrgba = np.zeros(water.shape + (4,), np.uint8)
wrgba[water] = WATER_RGB + (255,)
Image.fromarray(wrgba, "RGBA").save(layer_dir / "water.png", optimize=True)

out = {
    "rvi_burned": round(rvi_post[burned_date], 3),
    "rvi_burned_date": burned_date,
    "rvi_damage_area_before": round(rvi_pre, 3),
    "damage_area_ha": area_ha,
    "buildings": "buildings.png",
    "buildings_colour": "#%02x%02x%02x" % GREY,
    "buildings_share_percent": round(100 * float(bld.mean()), 2),
    "buildings_method": f"HH at least {BLD_HH_DB:g} dB in all {len(pre)} pre-fire images and HH - HV at least "
                        f"{BLD_RATIO_DB:g} dB (median): a corner echo, typical of walls on the ground",
    "water": "water.png",
    "water_colour": "#%02x%02x%02x" % WATER_RGB,
    "water_share_percent": round(100 * float(water.mean()), 2),
    "water_method": f"HV at most {WATER_HV_DB:g} dB and HH at most {WATER_HH_DB:g} dB in almost every one of the "
                    f"{len(scenes)} images (90th percentile; smooth water mirrors the pulse away), areas of at least "
                    f"{WATER_MIN_HA:g} ha",
}
(layer_dir / "vegetation.js").write_text("window.NISAR_VEGETATION = " + json.dumps(out) + ";\n", encoding="utf-8")
print(json.dumps(out, indent=2))
