"""NISAR GCOV (L-band backscatter) before/after change -> web-ready layers.

Turns two GCOV granules into small PNG layers plus meta.json / meta.js that a static
web app can load without a server:

    hh_before.png, hh_after.png         grey, HH backscatter (surface)
    hv_before.png, hv_after.png         grey, HV backscatter (canopy structure)
    composite_before.png / _after.png   R = HH, G = HV, B = HH - HV (dB)
    diff_hv.png                         HV after - before; red = loss, blue = gain
    meta.json / meta.js                 corners, dates, dB ranges, statistics

Usage (run from the project root, Earthdata login in .env for remote granules):

    python scripts/gcov_change.py search --bbox 6.37 50.72 6.45 50.77 \
        --start 2026-08-01 --end 2026-08-31
    python scripts/gcov_change.py build --bbox 6.37 50.72 6.45 50.77 \
        --before <granule_id or local .h5> --after <granule_id or local .h5> \
        --out ../app/layers

Leave NISAR_LOCAL_FILE empty in .env when you pass two different granules.
HV change is a proxy for canopy loss, not biomass in t/ha. Rain and soil moisture also
change backscatter, so compare scenes of the same track and flight direction.
"""
from __future__ import annotations

import argparse
import json
import math
import re
import sys
from contextlib import contextmanager
from pathlib import Path

import h5py
import numpy as np
from PIL import Image
from pyproj import Transformer
from scipy.ndimage import uniform_filter

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

GRID = "/science/LSAR/GCOV/grids/frequencyA"
ID_TIME = "/science/LSAR/identification/zeroDopplerStartTime"

DB_RANGE = {"HH": (-20.0, 0.0), "HV": (-25.0, -5.0), "RATIO": (0.0, 15.0)}


# ----------------------------------------------------------------------------- search
def cmd_search(args: argparse.Namespace) -> None:
    import asf_search as asf

    west, south, east, north = args.bbox
    wkt = (
        f"POLYGON(({west} {south}, {east} {south}, {east} {north}, "
        f"{west} {north}, {west} {south}))"
    )
    params = {
        "dataset": "NISAR",
        "processingLevel": "GCOV",
        "intersectsWith": wkt,
        "start": f"{args.start}T00:00:00Z",
        "end": f"{args.end}T23:59:59Z",
        "maxResults": 100,
    }
    if args.direction:
        params["flightDirection"] = args.direction
    rows = []
    for product in asf.search(**params):
        p = getattr(product, "properties", {}) or {}
        rows.append(
            (
                p.get("startTime", ""),
                p.get("flightDirection", ""),
                p.get("pathNumber", ""),
                p.get("dataMaturity", ""),
                p.get("fileID") or p.get("sceneName") or "",
            )
        )
    rows.sort()
    print("start_time | direction | track | maturity | granule_id")
    for row in rows:
        print(" | ".join(str(x) for x in row))
    print(f"{len(rows)} granules. Pick two with the same track and direction.")


# ----------------------------------------------------------------------------- reading
@contextmanager
def open_source(src: str):
    """A local .h5 path, or an ASF granule id (streamed like the API does)."""
    path = Path(src).expanduser()
    if path.is_file():
        with h5py.File(path, "r") as h5:
            yield h5
    else:
        from app.services.moisture import open_granule_hdf5

        with open_granule_hdf5(src) as h5:
            yield h5


def find_epsg(h5: h5py.File) -> int:
    node = h5[f"{GRID}/projection"]
    for key in ("epsg_code", "epsg"):
        if key in node.attrs:
            return int(np.asarray(node.attrs[key]).ravel()[0])
    return int(np.asarray(node[()]).ravel()[0])


def read_time(h5: h5py.File) -> str | None:
    try:
        value = h5[ID_TIME][()]
        return value.decode() if isinstance(value, bytes) else str(value)
    except Exception:
        return None


def read_window(h5: h5py.File, bbox, pols=("HH", "HV")) -> dict:
    """Read only the bbox window of the HHHH / HVHV bands (HDF5 hyperslab)."""
    missing = [p for p in (f"{GRID}/xCoordinates", f"{GRID}/yCoordinates") if p not in h5]
    if missing or any(f"{GRID}/{p}{p}" not in h5 for p in pols):
        raise ValueError(
            f"Unexpected GCOV layout. Keys under {GRID}: "
            f"{list(h5[GRID].keys()) if GRID in h5 else 'grid not found'}"
        )
    epsg = find_epsg(h5)
    xs_all = h5[f"{GRID}/xCoordinates"][:].astype("float64")
    ys_all = h5[f"{GRID}/yCoordinates"][:].astype("float64")
    to_src = Transformer.from_crs("EPSG:4326", f"EPSG:{epsg}", always_xy=True)
    west, south, east, north = bbox
    cx, cy = to_src.transform([west, west, east, east], [south, north, south, north])
    pad = 200.0
    cols = np.flatnonzero((xs_all >= min(cx) - pad) & (xs_all <= max(cx) + pad))
    rows = np.flatnonzero((ys_all >= min(cy) - pad) & (ys_all <= max(cy) + pad))
    if cols.size == 0 or rows.size == 0:
        raise ValueError("The bbox does not intersect this granule.")
    r0, r1 = int(rows.min()), int(rows.max()) + 1
    c0, c1 = int(cols.min()), int(cols.max()) + 1
    data = {p: h5[f"{GRID}/{p}{p}"][r0:r1, c0:c1].astype("float32") for p in pols}
    return {"epsg": epsg, "xs": xs_all[c0:c1], "ys": ys_all[r0:r1], "data": data}


# ----------------------------------------------------------------------------- processing
def to_db(power: np.ndarray, looks: int) -> np.ndarray:
    """Linear power -> dB, averaged over looks x looks pixels in linear units (less speckle)."""
    a = np.where(np.isfinite(power) & (power > 0), power, np.nan).astype("float32")
    valid = np.isfinite(a)
    if looks > 1:
        num = uniform_filter(np.nan_to_num(a), size=looks)
        den = uniform_filter(valid.astype("float32"), size=looks)
        a = np.where(den > 0.5, num / np.maximum(den, 1e-6), np.nan)
    with np.errstate(divide="ignore", invalid="ignore"):
        return (10.0 * np.log10(a)).astype("float32")


def make_lonlat_grid(bbox, width: int):
    west, south, east, north = bbox
    mid_lat = 0.5 * (south + north)
    height = max(2, round(width * (north - south) / ((east - west) * math.cos(math.radians(mid_lat)))))
    lons = np.linspace(west, east, width)
    lats = np.linspace(north, south, height)
    return lons, lats


def resample(arr: np.ndarray, win: dict, lons: np.ndarray, lats: np.ndarray) -> np.ndarray:
    """Nearest-neighbour sampling of a projected array onto a regular lon/lat grid."""
    to_src = Transformer.from_crs("EPSG:4326", f"EPSG:{win['epsg']}", always_xy=True)
    lon2d, lat2d = np.meshgrid(lons, lats)
    x, y = to_src.transform(lon2d, lat2d)
    xs, ys = win["xs"], win["ys"]
    dx, dy = xs[1] - xs[0], ys[1] - ys[0]
    col = np.rint((x - xs[0]) / dx).astype(int)
    row = np.rint((y - ys[0]) / dy).astype(int)
    inside = (col >= 0) & (col < arr.shape[1]) & (row >= 0) & (row < arr.shape[0])
    out = np.full(lon2d.shape, np.nan, dtype="float32")
    out[inside] = arr[row[inside], col[inside]]
    return out


# ----------------------------------------------------------------------------- images
def _scale(db: np.ndarray, lo: float, hi: float) -> np.ndarray:
    return np.clip((db - lo) / (hi - lo), 0.0, 1.0)


def save_gray(db: np.ndarray, rng, path: Path) -> None:
    g = (255 * _scale(db, *rng)).astype("uint8")
    a = np.where(np.isfinite(db), 255, 0).astype("uint8")
    Image.fromarray(np.dstack([g, g, g, a]), "RGBA").save(path, optimize=True)


def save_composite(hh: np.ndarray, hv: np.ndarray, path: Path) -> None:
    ratio = hh - hv
    r = (255 * _scale(hh, *DB_RANGE["HH"])).astype("uint8")
    g = (255 * _scale(hv, *DB_RANGE["HV"])).astype("uint8")
    b = (255 * _scale(ratio, *DB_RANGE["RATIO"])).astype("uint8")
    a = np.where(np.isfinite(hh) & np.isfinite(hv), 255, 0).astype("uint8")
    Image.fromarray(np.dstack([r, g, b, a]), "RGBA").save(path, optimize=True)


def save_diff(diff: np.ndarray, vmax: float, path: Path) -> None:
    """Red = HV loss, blue = HV gain. Small changes stay transparent."""
    t = np.clip(np.nan_to_num(diff) / vmax, -1.0, 1.0)
    red = np.array([227, 6, 19], dtype="float32")
    blue = np.array([30, 90, 200], dtype="float32")
    white = np.array([255, 255, 255], dtype="float32")
    rgb = np.where(
        (t < 0)[..., None],
        white + (-t)[..., None] * (red - white),
        white + t[..., None] * (blue - white),
    )
    alpha = np.where(np.isfinite(diff), 255 * np.clip(np.abs(t) * 1.5, 0, 1), 0)
    out = np.dstack([rgb, alpha]).astype("uint8")
    Image.fromarray(out, "RGBA").save(path, optimize=True)


# ----------------------------------------------------------------------------- build
def cmd_build(args: argparse.Namespace) -> None:
    bbox = tuple(args.bbox)
    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)
    lons, lats = make_lonlat_grid(bbox, args.width)

    scenes: dict[str, dict] = {}
    for label, src in (("before", args.before), ("after", args.after)):
        print(f"[{label}] reading {src}")
        with open_source(src) as h5:
            win = read_window(h5, bbox)
            when = read_time(h5)
        layers = {pol: resample(to_db(win["data"][pol], args.looks), win, lons, lats) for pol in ("HH", "HV")}
        scenes[label] = {"source": src, "time": when, "epsg": win["epsg"], **layers}

    for label in ("before", "after"):
        s = scenes[label]
        save_gray(s["HH"], DB_RANGE["HH"], out_dir / f"hh_{label}.png")
        save_gray(s["HV"], DB_RANGE["HV"], out_dir / f"hv_{label}.png")
        save_composite(s["HH"], s["HV"], out_dir / f"composite_{label}.png")

    diff = scenes["after"]["HV"] - scenes["before"]["HV"]
    save_diff(diff, args.diff_range, out_dir / "diff_hv.png")

    west, south, east, north = bbox
    cell_m_x = (east - west) / (args.width - 1) * 111320.0 * math.cos(math.radians(0.5 * (south + north)))
    cell_m_y = (north - south) / (len(lats) - 1) * 110574.0
    cell_ha = cell_m_x * cell_m_y / 10000.0
    valid = np.isfinite(diff)
    loss = valid & (diff < -args.threshold)
    meta = {
        "bbox": list(bbox),
        "coordinates": [[west, north], [east, north], [east, south], [west, south]],
        "image_size": [int(args.width), int(len(lats))],
        "before": {"source": scenes["before"]["source"], "time": scenes["before"]["time"]},
        "after": {"source": scenes["after"]["source"], "time": scenes["after"]["time"]},
        "db_range": {"HH": DB_RANGE["HH"], "HV": DB_RANGE["HV"], "ratio": DB_RANGE["RATIO"]},
        "diff_range_db": args.diff_range,
        "stats": {
            "threshold_db": args.threshold,
            "valid_pixels": int(valid.sum()),
            "loss_pixels": int(loss.sum()),
            "loss_area_ha": round(float(loss.sum() * cell_ha), 1),
            "loss_share_percent": round(100.0 * float(loss.sum()) / max(1, int(valid.sum())), 2),
            "mean_hv_before_db": round(float(np.nanmean(scenes["before"]["HV"])), 2),
            "mean_hv_after_db": round(float(np.nanmean(scenes["after"]["HV"])), 2),
            "mean_diff_db": round(float(np.nanmean(diff)), 2),
            "cell_area_ha": round(cell_ha, 3),
        },
        "notes": (
            "HV change is a proxy for canopy structure loss, not biomass in t/ha. "
            "Rain and soil moisture also change L-band backscatter. NISAR GCOV is PROVISIONAL."
        ),
    }
    (out_dir / "meta.json").write_text(json.dumps(meta, indent=2))
    (out_dir / "meta.js").write_text("window.NISAR_META = " + json.dumps(meta) + ";\n")
    print(json.dumps(meta["stats"], indent=2))
    print(f"Wrote layers to {out_dir.resolve()}")


# ----------------------------------------------------------------------------- series
def scene_date(src: str, h5_time: str | None) -> str:
    """YYYY-MM-DD from the granule id / file name, else from the file's start time."""
    match = re.search(r"(\d{8})T\d{6}", Path(src).name)
    if match:
        d = match.group(1)
        return f"{d[:4]}-{d[4:6]}-{d[6:]}"
    if h5_time:
        return h5_time[:10]
    raise ValueError(f"Cannot find an acquisition date for {src}")


def safe_mean(a: np.ndarray) -> float | None:
    a = a[np.isfinite(a)]
    return round(float(a.mean()), 2) if a.size else None


def cmd_series(args: argparse.Namespace) -> None:
    """Many acquisitions of ONE track -> one HV image and one change image per date."""
    bbox = tuple(args.bbox)
    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)
    lons, lats = make_lonlat_grid(bbox, args.width)

    scenes: list[dict] = []
    for src in args.granules:
        print(f"[{len(scenes) + 1}/{len(args.granules)}] reading {src}")
        with open_source(src) as h5:
            win = read_window(h5, bbox)
            when = read_time(h5)
        layers = {pol: resample(to_db(win["data"][pol], args.looks), win, lons, lats) for pol in ("HH", "HV")}
        scenes.append({"source": src, "date": scene_date(src, when), "time": when, **layers})
    scenes.sort(key=lambda s: s["date"])

    pre = [s for s in scenes if s["date"] < args.fire_start]
    post = [s for s in scenes if s["date"] > args.fire_end]
    if not pre or not post:
        raise SystemExit("Need at least one granule before --fire-start and one after --fire-end.")
    baseline, first_post = pre[-1], post[0]

    west, south, east, north = bbox
    cell_m_x = (east - west) / (args.width - 1) * 111320.0 * math.cos(math.radians(0.5 * (south + north)))
    cell_m_y = (north - south) / (len(lats) - 1) * 110574.0
    cell_ha = cell_m_x * cell_m_y / 10000.0

    # Burn mask: where HV dropped most between the last pre-fire scene and the first post-fire scene.
    burn = np.isfinite(first_post["HV"] - baseline["HV"]) & ((first_post["HV"] - baseline["HV"]) < -args.threshold)

    entries = []
    for s in scenes:
        d = s["date"]
        diff = s["HV"] - baseline["HV"]
        save_gray(s["HV"], DB_RANGE["HV"], out_dir / f"hv_{d}.png")
        save_composite(s["HH"], s["HV"], out_dir / f"composite_{d}.png")
        save_diff(diff, args.diff_range, out_dir / f"diff_hv_{d}.png")
        valid = np.isfinite(diff)
        loss = valid & (diff < -args.threshold)
        role = (
            "baseline" if s is baseline
            else "pre" if d < args.fire_start
            else "post" if d > args.fire_end
            else "during"
        )
        entries.append({
            "date": d,
            "time": s["time"],
            "source": s["source"],
            "role": role,
            "hv": f"hv_{d}.png",
            "composite": f"composite_{d}.png",
            "diff": f"diff_hv_{d}.png",
            "mean_hv_db": safe_mean(s["HV"]),
            "mean_hv_in_burn_mask_db": safe_mean(s["HV"][burn]),
            "mean_diff_db": safe_mean(diff),
            "loss_area_ha": round(float(loss.sum() * cell_ha), 1),
            "loss_share_percent": round(100.0 * float(loss.sum()) / max(1, int(valid.sum())), 2),
        })

    meta = {
        "bbox": list(bbox),
        "coordinates": [[west, north], [east, north], [east, south], [west, south]],
        "image_size": [int(args.width), int(len(lats))],
        "db_range": {"HH": DB_RANGE["HH"], "HV": DB_RANGE["HV"], "ratio": DB_RANGE["RATIO"]},
        "diff_range_db": args.diff_range,
        "threshold_db": args.threshold,
        "fire": {"start": args.fire_start, "end": args.fire_end},
        "baseline": baseline["date"],
        "burn_mask_from": first_post["date"],
        "burn_mask_area_ha": round(float(burn.sum() * cell_ha), 1),
        "cell_area_ha": round(cell_ha, 4),
        "scenes": entries,
        "notes": (
            "HV change is a proxy for canopy structure loss, not biomass in t/ha. All scenes are the same "
            "track and direction. Rain and soil moisture also change L-band backscatter. NISAR GCOV is PROVISIONAL."
        ),
    }
    (out_dir / "series_meta.json").write_text(json.dumps(meta, indent=2))
    (out_dir / "series_meta.js").write_text("window.NISAR_SERIES = " + json.dumps(meta) + ";\n")
    print("date        role      loss_ha  hv_in_burn_dB")
    for e in entries:
        print(f"{e['date']}  {e['role']:<9} {e['loss_area_ha']:>7}  {e['mean_hv_in_burn_mask_db']}")
    print(f"Wrote {len(entries)} dates to {out_dir.resolve()}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="cmd", required=True)

    ps = sub.add_parser("search", help="list GCOV granules over a bbox")
    ps.add_argument("--bbox", type=float, nargs=4, required=True, metavar=("W", "S", "E", "N"))
    ps.add_argument("--start", required=True)
    ps.add_argument("--end", required=True)
    ps.add_argument("--direction", choices=["ASCENDING", "DESCENDING"])
    ps.set_defaults(func=cmd_search)

    pb = sub.add_parser("build", help="make PNG layers from two granules")
    pb.add_argument("--bbox", type=float, nargs=4, required=True, metavar=("W", "S", "E", "N"))
    pb.add_argument("--before", required=True, help="granule id or local .h5")
    pb.add_argument("--after", required=True, help="granule id or local .h5")
    pb.add_argument("--out", default="../app/layers")
    pb.add_argument("--width", type=int, default=900, help="output image width in pixels")
    pb.add_argument("--looks", type=int, default=5, help="boxcar multilook size against speckle")
    pb.add_argument("--threshold", type=float, default=1.5, help="HV drop in dB counted as loss")
    pb.add_argument("--diff-range", type=float, default=6.0, help="dB at which the diff colour saturates")
    pb.set_defaults(func=cmd_build)

    pr = sub.add_parser("series", help="time series: one HV image and one change image per date")
    pr.add_argument("--bbox", type=float, nargs=4, required=True, metavar=("W", "S", "E", "N"))
    pr.add_argument("--granules", nargs="+", required=True, help="granule ids or local .h5 files, same track")
    pr.add_argument("--fire-start", default="2026-08-14", help="YYYY-MM-DD")
    pr.add_argument("--fire-end", default="2026-08-20", help="YYYY-MM-DD")
    pr.add_argument("--out", default="../app/layers_series")
    pr.add_argument("--width", type=int, default=900)
    pr.add_argument("--looks", type=int, default=5)
    pr.add_argument("--threshold", type=float, default=1.5)
    pr.add_argument("--diff-range", type=float, default=6.0)
    pr.set_defaults(func=cmd_series)

    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
