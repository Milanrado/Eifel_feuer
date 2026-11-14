"""NISAR SME2 soil moisture -> static map layers for the app ("Moisture" layer).

Uses the same access path as the API (app/services/moisture.py): a local .h5 file, or an ASF
granule id that is streamed with your Earthdata login from .env. Only the bbox window is read.

  search   list SME2 granules over the study area
  build    write one grey PNG per date plus moisture_meta.js / .json into the app's layer folder

Examples (run inside forest_watch_api/):
  python scripts/sme2_layers.py search --start 2026-06-20 --end 2026-10-15
  python scripts/sme2_layers.py build --granules <id or .h5> <id or .h5> ...

The PNGs follow the convention of the radar layers: grey value 0..255 maps linearly to RANGE
(m3/m3), alpha 0 where there is no usable value. The app colours them in the browser.
By default only pixels that the product marks as recommended are kept (retrievalQualityFlag bit 0 = 0);
dense forest is often not recommended, so expect gaps. SME2 is soil moisture, not fuel moisture,
and PROVISIONAL data are not fully validated.
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import date
from pathlib import Path

import numpy as np
from PIL import Image
from pyproj import Transformer

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from gcov_change import make_lonlat_grid, open_source, read_time, scene_date  # noqa: E402

GRID = "/science/LSAR/SME2/grids"
RANGE = (0.0, 0.6)          # m3/m3 shown from dry to wet
FILL = -9999.0
DEFAULT_OUT = ROOT.parent / "app" / "layers_series_all"


def default_bbox(out: Path):
    """The study box of the radar series, so both data sets cover the same area."""
    meta = out / "series_meta.json"
    if meta.is_file():
        return json.loads(meta.read_text(encoding="utf-8"))["bbox"]
    return None


def cmd_search(args: argparse.Namespace) -> None:
    from app.services.asf_client import search_nisar_scenes

    bbox = args.bbox or default_bbox(Path(args.out))
    if not bbox:
        sys.exit("Give --bbox W S E N (no series_meta.json found to take it from).")
    scenes = search_nisar_scenes(tuple(bbox), date.fromisoformat(args.start), date.fromisoformat(args.end),
                                 args.maturity, args.direction, 200)
    for s in sorted(scenes, key=lambda s: s.get("start_time") or ""):
        print(s.get("start_time"), s.get("direction"), s.get("path_number"), s.get("data_maturity"), s["granule_id"])
    print(f"{len(scenes)} SME2 granule(s). Pass the ids of ONE track and direction to `build`.")


def read_moisture(h5, bbox, include_unrecommended: bool) -> dict:
    """Read the bbox window of soil moisture (EPSG:6933) and mask unusable pixels with NaN."""
    need = [f"{GRID}/{n}" for n in ("xCoordinates", "yCoordinates", "soilMoisture", "retrievalQualityFlag")]
    missing = [p for p in need if p not in h5]
    if missing:
        raise ValueError(f"Not an SME2 granule, missing: {missing}")
    xs_all = h5[f"{GRID}/xCoordinates"][:].astype("float64")
    ys_all = h5[f"{GRID}/yCoordinates"][:].astype("float64")
    west, south, east, north = bbox
    to_ease = Transformer.from_crs("EPSG:4326", "EPSG:6933", always_xy=True)
    cx, cy = to_ease.transform([west, west, east, east], [south, north, south, north])
    step = float(np.nanmedian(np.abs(np.diff(xs_all)))) if xs_all.size > 1 else 200.0
    cols = np.flatnonzero((xs_all >= min(cx) - step) & (xs_all <= max(cx) + step))
    rows = np.flatnonzero((ys_all >= min(cy) - step) & (ys_all <= max(cy) + step))
    if cols.size < 2 or rows.size < 2:
        raise ValueError("The bbox does not intersect this granule.")
    r0, r1, c0, c1 = int(rows.min()), int(rows.max()) + 1, int(cols.min()), int(cols.max()) + 1
    sm = h5[f"{GRID}/soilMoisture"][r0:r1, c0:c1].astype("float32")
    q = h5[f"{GRID}/retrievalQualityFlag"][r0:r1, c0:c1].astype("int32")
    valid = np.isfinite(sm) & (sm != FILL) & (q != -9999) & (q >= 0)
    recommended = valid & ((q & 1) == 0)
    keep = valid if include_unrecommended else recommended
    return {
        "xs": xs_all[c0:c1], "ys": ys_all[r0:r1], "spacing_m": round(step, 1),
        "sm": np.where(keep, sm, np.nan).astype("float32"),
        "valid": int(valid.sum()), "recommended": int(recommended.sum()),
    }


def to_lonlat(win: dict, lons: np.ndarray, lats: np.ndarray) -> np.ndarray:
    """Nearest-neighbour sampling onto a regular lon/lat grid (keeps the product's blocky pixels honest)."""
    to_ease = Transformer.from_crs("EPSG:4326", "EPSG:6933", always_xy=True)
    lon2d, lat2d = np.meshgrid(lons, lats)
    x, y = to_ease.transform(lon2d, lat2d)
    xs, ys = win["xs"], win["ys"]
    col = np.rint((x - xs[0]) / (xs[1] - xs[0])).astype(int)
    row = np.rint((y - ys[0]) / (ys[1] - ys[0])).astype(int)
    arr = win["sm"]
    inside = (col >= 0) & (col < arr.shape[1]) & (row >= 0) & (row < arr.shape[0])
    out = np.full(lon2d.shape, np.nan, dtype="float32")
    out[inside] = arr[row[inside], col[inside]]
    return out


def cmd_build(args: argparse.Namespace) -> None:
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    bbox = args.bbox or default_bbox(out)
    if not bbox:
        sys.exit("Give --bbox W S E N (no series_meta.json found to take it from).")
    west, south, east, north = bbox
    lons, lats = make_lonlat_grid(bbox, args.width)

    scenes = {}
    spacing = None
    for src in args.granules:
        with open_source(src) as h5:
            time = read_time(h5)
            win = read_moisture(h5, bbox, args.include_unrecommended)
        day = scene_date(src, time)
        if day in scenes:
            print(f"skip {src}: {day} is already covered (pass one track and direction only)")
            continue
        grid = to_lonlat(win, lons, lats)
        ok = np.isfinite(grid)
        if not ok.any():
            print(f"skip {src}: no usable pixels in the bbox on {day}")
            continue
        g = (255 * np.clip((np.nan_to_num(grid) - RANGE[0]) / (RANGE[1] - RANGE[0]), 0, 1)).astype("uint8")
        a = np.where(ok, 255, 0).astype("uint8")
        name = f"moisture_{day}.png"
        Image.fromarray(np.dstack([g, g, g, a]), "RGBA").save(out / name, optimize=True)
        vals = win["sm"][np.isfinite(win["sm"])]
        spacing = win["spacing_m"]
        scenes[day] = {
            "date": day, "time": time, "source": Path(src).stem if Path(src).is_file() else src, "file": name,
            "mean_m3_m3": round(float(vals.mean()), 3), "median_m3_m3": round(float(np.median(vals)), 3),
            "recommended_share_percent": round(100 * win["recommended"] / win["valid"], 1) if win["valid"] else None,
            "covered_share_percent": round(100 * float(ok.mean()), 1),
        }
        print(f"{day}: mean {scenes[day]['mean_m3_m3']} m3/m3, map covered {scenes[day]['covered_share_percent']} %")
    if not scenes:
        sys.exit("No scene produced a layer.")

    meta = {
        "bbox": [west, south, east, north],
        "image_size": [int(lons.size), int(lats.size)],
        "unit": "m3/m3",
        "range": list(RANGE),
        "pixel_spacing_m": spacing,
        "quality": "all valid pixels" if args.include_unrecommended else "recommended pixels only",
        "scenes": [scenes[d] for d in sorted(scenes)],
        "notes": "NISAR SME2 soil moisture, PROVISIONAL. Soil moisture is not fuel moisture; rain between "
                 "acquisitions changes it. Dense forest is often not recommended by the product, so there are gaps.",
    }
    (out / "moisture_meta.json").write_text(json.dumps(meta, indent=2), encoding="utf-8")
    (out / "moisture_meta.js").write_text("window.NISAR_MOISTURE = " + json.dumps(meta, separators=(",", ":")) + ";\n",
                                          encoding="utf-8")
    print(f"wrote {len(scenes)} layer(s) and moisture_meta.js to {out}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="cmd", required=True)

    ps = sub.add_parser("search", help="list SME2 granules over the study area")
    ps.add_argument("--bbox", type=float, nargs=4, metavar=("W", "S", "E", "N"), help="default: bbox of the radar series")
    ps.add_argument("--start", required=True)
    ps.add_argument("--end", required=True)
    ps.add_argument("--direction", choices=["ASCENDING", "DESCENDING"])
    ps.add_argument("--maturity", default=None, help="e.g. PROVISIONAL")
    ps.add_argument("--out", default=str(DEFAULT_OUT), help="layer folder (only used to find the default bbox)")
    ps.set_defaults(func=cmd_search)

    pb = sub.add_parser("build", help="write moisture PNGs and moisture_meta.js")
    pb.add_argument("--granules", nargs="+", required=True, help="granule ids or local .h5 files, one track and direction")
    pb.add_argument("--bbox", type=float, nargs=4, metavar=("W", "S", "E", "N"), help="default: bbox of the radar series")
    pb.add_argument("--out", default=str(DEFAULT_OUT))
    pb.add_argument("--width", type=int, default=300, help="output image width in pixels")
    pb.add_argument("--include-unrecommended", action="store_true", help="also keep pixels the product does not recommend")
    pb.set_defaults(func=cmd_build)

    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
