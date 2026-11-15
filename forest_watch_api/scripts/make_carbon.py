"""Carbon stored in the trees of one study area, from NASA GEDI L4B biomass, plus what the fire changed.

Why: radar backscatter tells WHERE the forest changed, not HOW MUCH biomass stands there (HV change is not
biomass in t/ha). GEDI L4B (lidar from the ISS, 1 km grid, mean of the mission years before 2026) gives the
above-ground biomass density (AGBD, Mg/ha = t/ha) with a standard error. This script combines both:

  stored in the box          sum of AGBD over the radar pixels of the box
  stored in the damaged area the same, only inside the lasting damage area (rule of make_damage.py)
  lost uptake per year       damaged area x IPCC default growth rate: the forest that would have grown there
  per date                   stock in the places whose forest echo is more than threshold_db below the last image
                             before the fire on that date (the red of the app's Change layer, same images). The app
                             shows "CO2 in forest with an intact canopy" = box stock minus this, and the difference
                             between two dates in compare mode. It is the stock standing where the canopy echo
                             dropped, not biomass measured by radar and not the emission of the fire.

Conversions (IPCC): carbon = 0.47 x dry biomass (2006 Guidelines, Vol. 4, Ch. 4, Table 4.3, not changed by the
2019 Refinement); CO2 = carbon x 44/12. Growth: 2.3 t dry matter per ha and year, above-ground net biomass growth
of natural temperate oceanic forest in Europe (2019 Refinement, Vol. 4, Ch. 4, Table 4.9 (Updated), p. 4.37; no
uncertainty given there, the IPCC Tier 1 default applies).

Honest limits (also shown in the app): above-ground live biomass only (no roots, dead wood, soil); "stored in the
damaged area" is the stock that stood there, NOT the emission of the fire (only part of it burns); GEDI is a
1 km product from before 2026 and does not see the fire; the uncertainty adds the per-cell standard errors as if
they were fully correlated (an upper bound).

GEDI L4B v2.1 (ORNL DAAC, doi:10.3334/ORNLDAAC/2299) is a set of global cloud-optimised GeoTIFFs. Only the tiles
under the box are fetched with HTTP range requests and the Earthdata login from .env (same as the radar data),
decoded with a small built-in TIFF/LZW reader (no GDAL needed).

Usage (inside forest_watch_api/):  python scripts/make_carbon.py ../app/layers_series_gironde
Writes carbon.js (window.NISAR_CARBON) into the layer folder.
Needs: numpy, scipy, pyproj, fsspec, aiohttp (already used by the radar scripts)
"""
from __future__ import annotations

import json
import struct
import sys
from pathlib import Path

import numpy as np
from PIL import Image
from pyproj import Transformer
from scipy import ndimage

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

GEDI = "https://data.ornldaac.earthdata.nasa.gov/protected/gedi/GEDI_L4B_Gridded_Biomass_V2_1/data/"
MU = GEDI + "GEDI04_B_MW019MW223_02_002_02_R01000M_MU.tif"     # mean AGBD, Mg/ha
SE = GEDI + "GEDI04_B_MW019MW223_02_002_02_R01000M_SE.tif"     # standard error of the mean, Mg/ha
CARBON_FRACTION = 0.47          # IPCC 2006 Vol. 4 Ch. 4 Table 4.3, default
CO2_PER_C = 44.0 / 12.0
GROWTH_T_DM_HA_YR = 2.3         # IPCC 2019 Refinement Vol. 4 Ch. 4 Table 4.9 (Updated): temperate oceanic, Europe
MIN_PATCH_HA = 1.0              # damage rule, same as make_damage.py


# ----------------------------------------------------------------------------- tiny cloud-optimised GeoTIFF reader
def lzw_decode(data: bytes) -> bytes:
    """TIFF LZW (MSB first, 9..12 bit codes, early change)."""
    out = bytearray()
    table = [bytes([i]) for i in range(256)] + [b"", b""]
    bits, nbits, pos, prev = 0, 0, 0, None
    width = 9
    n = len(data)
    while True:
        while nbits < width:
            if pos >= n:
                return bytes(out)
            bits = (bits << 8) | data[pos]
            pos += 1
            nbits += 8
        code = (bits >> (nbits - width)) & ((1 << width) - 1)
        nbits -= width
        if code == 256:                       # clear
            table = table[:258]
            width, prev = 9, None
            continue
        if code == 257:                       # end of information
            return bytes(out)
        if prev is None:
            entry = table[code]
        elif code < len(table):
            entry = table[code]
            table.append(prev + entry[:1])
        else:
            entry = prev + prev[:1]
            table.append(entry)
        out += entry
        prev = entry
        if len(table) + 1 >= (1 << width) and width < 12:   # early change
            width += 1


class Cog:
    """Reads single tiles of a tiled, LZW-compressed, float32 GeoTIFF over HTTP (fsspec + Earthdata login)."""

    def __init__(self, f):
        self.f = f
        head = f.read(8)
        self.bo = "<" if head[:2] == b"II" else ">"
        if struct.unpack(self.bo + "H", head[2:4])[0] != 42:
            raise ValueError("BigTIFF is not supported by this small reader")
        f.seek(struct.unpack(self.bo + "I", head[4:8])[0])
        n = struct.unpack(self.bo + "H", f.read(2))[0]
        entries = [struct.unpack(self.bo + "HHI4s", f.read(12)) for _ in range(n)]
        size = {1: 1, 2: 1, 3: 2, 4: 4, 12: 8}
        fmt = {1: "B", 2: "s", 3: "H", 4: "I", 12: "d"}
        self.tags = {}
        for tag, typ, cnt, raw in entries:
            nbytes = size[typ] * cnt
            if nbytes > 4:
                f.seek(struct.unpack(self.bo + "I", raw)[0])
                raw = f.read(nbytes)
            if typ == 2:
                self.tags[tag] = raw[:cnt].rstrip(b"\0").decode()
            else:
                vals = struct.unpack(self.bo + fmt[typ] * cnt, raw[:nbytes])
                self.tags[tag] = vals[0] if cnt == 1 else vals
        t = self.tags
        if t[259] != 5 or t[339] != 3 or t[258] != 32 or t.get(317, 1) != 1:
            raise ValueError("expected LZW, float32, no predictor")
        self.width, self.height, self.tw, self.th = t[256], t[257], t[322], t[323]
        self.res_x, self.res_y = t[33550][0], t[33550][1]
        self.x0, self.y0 = t[33922][3], t[33922][4]                 # upper-left corner (pixel is area)
        self.nodata = float(t[42113]) if 42113 in t else None
        self.tiles_across = -(-self.width // self.tw)
        keys = t[34735]
        self.epsg = next((keys[4 + 4 * i + 3] for i in range(keys[3]) if keys[4 + 4 * i] == 3072), None)
        self._cache = {}

    def tile(self, tr: int, tc: int) -> np.ndarray:
        key = (tr, tc)
        if key not in self._cache:
            i = tr * self.tiles_across + tc
            off, cnt = self.tags[324][i], self.tags[325][i]
            if cnt == 0:
                arr = np.full((self.th, self.tw), np.nan, np.float32)
            else:
                self.f.seek(off)
                raw = lzw_decode(self.f.read(cnt))
                arr = np.frombuffer(raw[: self.tw * self.th * 4], dtype=self.bo + "f4").reshape(self.th, self.tw).astype(np.float32)
                if self.nodata is not None:
                    arr = np.where(arr == self.nodata, np.nan, arr)
            self._cache[key] = arr
        return self._cache[key]

    def sample(self, x: np.ndarray, y: np.ndarray) -> np.ndarray:
        """Value of the cell under each projected point (nearest cell)."""
        col = np.floor((x - self.x0) / self.res_x).astype(int)
        row = np.floor((self.y0 - y) / self.res_y).astype(int)
        out = np.full(x.shape, np.nan, np.float32)
        ok = (col >= 0) & (col < self.width) & (row >= 0) & (row < self.height)
        tr, tc = row // self.th, col // self.tw
        for a, b in set(zip(tr[ok].ravel().tolist(), tc[ok].ravel().tolist())):
            m = ok & (tr == a) & (tc == b)
            out[m] = self.tile(a, b)[row[m] - a * self.th, col[m] - b * self.tw]
        return out, row, col


def open_remote(url: str):
    import aiohttp
    import fsspec
    from app.config import EARTHDATA_PASSWORD, EARTHDATA_USERNAME

    if not EARTHDATA_USERNAME or not EARTHDATA_PASSWORD:
        sys.exit("Set EARTHDATA_USERNAME and EARTHDATA_PASSWORD in forest_watch_api/.env")
    fs = fsspec.filesystem("https", client_kwargs={"auth": aiohttp.BasicAuth(EARTHDATA_USERNAME, EARTHDATA_PASSWORD)})
    return fs.open(url, "rb", block_size=1 << 18, cache_type="blockcache")


# ----------------------------------------------------------------------------- main
def main() -> None:
    if len(sys.argv) < 2:
        sys.exit(__doc__)
    layer_dir = Path(sys.argv[1])
    meta = json.loads((layer_dir / "series_meta.json").read_text(encoding="utf-8"))
    west, south, east, north = meta["bbox"]
    width, height = meta["image_size"]
    cell_ha = meta["cell_area_ha"]

    # the radar pixel grid of the series (same as gcov_change.make_lonlat_grid)
    lons, lats = np.linspace(west, east, width), np.linspace(north, south, height)
    lon2d, lat2d = np.meshgrid(lons, lats)

    # lasting damage area, same rule as make_damage.py
    rng = meta["db_range"]["HV"]
    scenes = meta["scenes"]
    pre = [s for s in scenes if s["date"] < meta["fire"]["start"]]
    post = [s for s in scenes if s["date"] > meta["fire"]["end"]]
    hv = {s["date"]: rng[0] + np.asarray(Image.open(layer_dir / s["hv"]).convert("L")).astype(float) / 255 * (rng[1] - rng[0])
          for s in scenes}
    pre_median = np.median([hv[s["date"]] for s in pre], axis=0)
    hits = sum(((hv[s["date"]] - pre_median) < -meta["threshold_db"]).astype(int) for s in post)
    lab, n = ndimage.label(hits >= max(2, len(post) - 1))
    sizes = ndimage.sum(lab > 0, lab, range(1, n + 1))
    damaged = np.isin(lab, 1 + np.flatnonzero(sizes * cell_ha >= MIN_PATCH_HA))

    # forest echo per date as the app's Change layer reads it: steadied forest channel when stable.js exists
    steady = (layer_dir / "stable.js").exists()
    def forest_db(s):
        if steady:
            a = np.asarray(Image.open(layer_dir / f"stable_{s['date']}.png").convert("RGBA")).astype(float)[..., 1]
        else:
            a = np.asarray(Image.open(layer_dir / s["hv"]).convert("L")).astype(float)
        return rng[0] + a / 255 * (rng[1] - rng[0])
    base_scene = next(s for s in scenes if s["date"] == meta["baseline"])
    base_forest = forest_db(base_scene)
    loss_by_date = {s["date"]: (forest_db(s) - base_forest) < -meta["threshold_db"] for s in scenes}

    with open_remote(MU) as fmu, open_remote(SE) as fse:
        mu, se = Cog(fmu), Cog(fse)
        if mu.epsg != 6933:
            sys.exit(f"unexpected projection EPSG:{mu.epsg}, expected 6933 (EASE-Grid 2.0)")
        x, y = Transformer.from_crs("EPSG:4326", "EPSG:6933", always_xy=True).transform(lon2d, lat2d)
        agbd, row, col = mu.sample(x, y)
        agbd_se, _, _ = se.sample(x, y)

    valid = np.isfinite(agbd)
    cells = len(set(zip(row[valid].ravel().tolist(), col[valid].ravel().tolist())))

    def stock(mask):
        m = mask & valid
        t = float(np.nansum(agbd[m]) * cell_ha)
        e = float(np.nansum(agbd_se[m]) * cell_ha)          # fully correlated: upper bound
        co2 = lambda v: v * CARBON_FRACTION * CO2_PER_C
        return {"area_ha": round(float(mask.sum() * cell_ha), 1), "covered_percent": round(100 * float(m.sum()) / max(1, int(mask.sum())), 1),
                "agb_t": round(t), "agb_se_t": round(e), "co2_t": round(co2(t)), "co2_se_t": round(co2(e)),
                "mean_agbd_t_ha": round(t / max(1e-9, float(m.sum()) * cell_ha), 1)}

    box = stock(np.ones_like(valid))
    by_date = {}
    for date, m in loss_by_date.items():
        st = stock(m)
        by_date[date] = {"loss_ha": st["area_ha"], "co2_t": st["co2_t"], "co2_se_t": st["co2_se_t"]}
    out = {
        "source": "NASA GEDI L4B Gridded Aboveground Biomass Density v2.1 (1 km), ORNL DAAC, doi:10.3334/ORNLDAAC/2299",
        "gedi_cells": cells,
        "box": box,
        "baseline": meta["baseline"],
        "loss_rule": f"forest echo more than {meta['threshold_db']} dB below {meta['baseline']} "
                     f"({'steadied images, as in the Change layer' if steady else 'raw HV images'})",
        "by_date": by_date,
        "carbon_fraction": CARBON_FRACTION,
        "co2_per_c": round(CO2_PER_C, 4),
        "growth_t_dm_ha_yr": GROWTH_T_DM_HA_YR,
        "growth_source": "IPCC 2019 Refinement, Vol. 4, Ch. 4, Table 4.9 (Updated): above-ground net biomass growth, "
                         "natural forest, temperate oceanic, Europe, 2.3 t d.m./ha/yr (no uncertainty given; Tier 1 default applies)",
        "carbon_fraction_source": "IPCC 2006 Guidelines, Vol. 4, Ch. 4, Table 4.3 (default 0.47; not changed in 2019)",
    }
    if damaged.any():
        d = stock(damaged)
        d["lost_uptake_co2_t_yr"] = round(d["area_ha"] * GROWTH_T_DM_HA_YR * CARBON_FRACTION * CO2_PER_C)
        out["damaged"] = d
    (layer_dir / "carbon.js").write_text("window.NISAR_CARBON = " + json.dumps(out) + ";\n", encoding="utf-8")
    print(json.dumps(out, indent=2))


if __name__ == "__main__":
    main()
