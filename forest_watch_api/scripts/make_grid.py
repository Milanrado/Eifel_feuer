"""Downsample the HV series PNGs into a small dB grid the static web app can read.

Browsers block canvas pixel reads of local files (file://), so the app cannot sample
the PNGs on click. This script does it once offline and writes a plain JS file:

    window.NISAR_GRID = {width, height, bbox, dates: {"YYYY-MM-DD": [[dB or null, ...], ...]}}

Rows run north -> south, columns west -> east (same orientation as the PNGs).
Grey value 0..255 is mapped back linearly to db_range.HV, so values are clipped to
that range (the PNG was clipped too). Cells with no valid pixel become null.

Usage (from the project root):
    python3 forest_watch_api/scripts/make_grid.py                # auto-picks the folder
    python3 forest_watch_api/scripts/make_grid.py --dir app/layers_series_all --cols 80
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
from PIL import Image

ROOT = Path(__file__).resolve().parents[2]
CANDIDATES = ["app/layers_series_all", "app/layers_series"]


def pick_dir(arg: str | None) -> Path:
    if arg:
        return Path(arg)
    for c in CANDIDATES:
        if (ROOT / c / "series_meta.json").is_file():
            return ROOT / c
    raise SystemExit("No series_meta.json found in " + ", ".join(CANDIDATES))


def block_mean_db(png: Path, lo: float, hi: float, cols: int) -> list[list[float | None]]:
    """Average valid pixels per block (in linear power, like the pipeline's multilook)."""
    rgba = np.asarray(Image.open(png).convert("RGBA")).astype("float32")
    grey, alpha = rgba[..., 0], rgba[..., 3]
    db = lo + grey / 255.0 * (hi - lo)
    valid = alpha > 0
    h, w = db.shape
    rows = max(1, round(cols * h / w))
    # block edges in pixel indices
    ye = np.linspace(0, h, rows + 1).round().astype(int)
    xe = np.linspace(0, w, cols + 1).round().astype(int)
    out: list[list[float | None]] = []
    for r in range(rows):
        line: list[float | None] = []
        for c in range(cols):
            blk = db[ye[r]:ye[r + 1], xe[c]:xe[c + 1]]
            ok = valid[ye[r]:ye[r + 1], xe[c]:xe[c + 1]]
            if ok.sum() == 0:
                line.append(None)
                continue
            power = 10.0 ** (blk[ok] / 10.0)
            line.append(round(float(10.0 * np.log10(power.mean())), 2))
        out.append(line)
    return out


def burn_mask_cells(png: Path, diff_range: float, threshold: float, cols: int, rows: int):
    """Rebuild the pipeline's burn mask (HV drop > threshold) from the diff PNG.

    save_diff() blends white -> red with t = diff / diff_range, so for red pixels
    |t| = (255 - G) / 249. Returns (pixel_count, {(row, col): pixels}) on the grid.
    """
    rgba = np.asarray(Image.open(png).convert("RGBA")).astype("float32")
    r, g, b, a = rgba[..., 0], rgba[..., 1], rgba[..., 2], rgba[..., 3]
    drop_db = (255.0 - g) / 249.0 * diff_range
    mask = (a > 0) & (r > b) & (drop_db > threshold)
    h, w = mask.shape
    ys, xs = np.nonzero(mask)
    cells: dict[tuple[int, int], int] = {}
    for y, x in zip(ys, xs):
        key = (min(rows - 1, int(y * rows / h)), min(cols - 1, int(x * cols / w)))
        cells[key] = cells.get(key, 0) + 1
    return int(mask.sum()), cells


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--dir", help="folder with series_meta.json and hv_<date>.png")
    ap.add_argument("--cols", type=int, default=80, help="grid columns (rows follow the aspect ratio)")
    args = ap.parse_args()

    folder = pick_dir(args.dir)
    meta = json.loads((folder / "series_meta.json").read_text())
    lo, hi = meta["db_range"]["HV"]

    dates = {}
    for scene in meta["scenes"]:
        dates[scene["date"]] = block_mean_db(folder / scene["hv"], lo, hi, args.cols)
        print(f"{scene['date']}  {len(dates[scene['date']])} rows")

    first = next(iter(dates.values()))
    rows, cols = len(first), len(first[0])

    # Burn mask on the grid, so the app can say "this point is inside the burn mask"
    # and fly to the largest patch. Derived from the diff PNG of meta.burn_mask_from.
    mask_scene = next(s for s in meta["scenes"] if s["date"] == meta["burn_mask_from"])
    n_px, cells = burn_mask_cells(folder / mask_scene["diff"], meta["diff_range_db"],
                                  meta["threshold_db"], cols, rows)
    print(f"burn mask: {n_px} px = {n_px * meta['cell_area_ha']:.1f} ha (meta says {meta['burn_mask_area_ha']} ha)")
    focus = None
    if cells:
        (fr, fc), _ = max(cells.items(), key=lambda kv: kv[1])
        w, s, e, n = meta["bbox"]
        focus = [round(n - (fr + 0.5) / rows * (n - s), 5), round(w + (fc + 0.5) / cols * (e - w), 5)]

    grid = {
        "width": cols,
        "height": rows,
        "bbox": meta["bbox"],
        "db_range": [lo, hi],
        "note": "HV dB, block mean of the hv_<date>.png greyscale, clipped to db_range",
        "burn_cells": [[r, c, k] for (r, c), k in sorted(cells.items())],  # [row, col, pixels]
        "burn_focus_latlng": focus,  # centre of the cell with most burn-mask pixels
        "dates": dates,
    }
    out = folder / "series_grid.js"
    out.write_text("window.NISAR_GRID = " + json.dumps(grid, separators=(",", ":")) + ";\n")
    print(f"Wrote {grid['width']}x{grid['height']} grid for {len(dates)} dates to {out}")


if __name__ == "__main__":
    main()
