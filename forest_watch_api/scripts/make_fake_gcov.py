"""SYNTHETIC test granules in the GCOV layout. Not real data, only for developing the app.

    python scripts/make_fake_gcov.py data/fake_before.h5 data/fake_after.h5

Then:
    python scripts/gcov_change.py build --bbox 6.37 50.72 6.45 50.77 \
        --before data/fake_before.h5 --after data/fake_after.h5 --out ../app/layers
The 'after' file has a burn scar where HV drops by about 6 dB.
"""
from __future__ import annotations

import sys
from pathlib import Path

import h5py
import numpy as np
from pyproj import Transformer

EPSG = 32632
GRID = "/science/LSAR/GCOV/grids/frequencyA"
BBOX = (6.37, 50.72, 6.45, 50.77)


def make(path: Path, burned: bool, seed: int) -> None:
    rng = np.random.default_rng(seed)
    to_utm = Transformer.from_crs("EPSG:4326", f"EPSG:{EPSG}", always_xy=True)
    cx, cy = to_utm.transform(0.5 * (BBOX[0] + BBOX[2]), 0.5 * (BBOX[1] + BBOX[3]))
    n, spacing = 500, 20.0
    xs = cx + (np.arange(n) - n / 2) * spacing
    ys = cy - (np.arange(n) - n / 2) * spacing
    xx, yy = np.meshgrid(np.arange(n), np.arange(n))

    def speckle(db_mean: float) -> np.ndarray:
        return 10 ** (db_mean / 10) * rng.gamma(4.0, 1 / 4.0, (n, n))

    hv_db = np.full((n, n), -13.0)
    hh_db = np.full((n, n), -8.0)
    lake = (xx - 120) ** 2 + (yy - 380) ** 2 < 25**2
    hv_db[lake], hh_db[lake] = -26.0, -22.0
    scar = ((xx - 260) / 90.0) ** 2 + ((yy - 230) / 70.0) ** 2 < 1.0
    if burned:
        hv_db[scar] -= 6.0
        hh_db[scar] -= 1.5
    with h5py.File(path, "w") as h5:
        g = h5.create_group(GRID)
        g["xCoordinates"], g["yCoordinates"] = xs, ys
        proj = g.create_dataset("projection", data=np.int32(EPSG))
        proj.attrs["epsg_code"] = EPSG
        g["HHHH"] = speckle_from_db(hh_db, rng)
        g["HVHV"] = speckle_from_db(hv_db, rng)
        h5.create_dataset("/science/LSAR/identification/zeroDopplerStartTime",
                          data=b"2026-08-23T18:00:00" if burned else b"2026-08-11T18:00:00")


def speckle_from_db(db: np.ndarray, rng) -> np.ndarray:
    return (10 ** (db / 10) * rng.gamma(4.0, 1 / 4.0, db.shape)).astype("float32")


if __name__ == "__main__":
    before, after = Path(sys.argv[1]), Path(sys.argv[2])
    before.parent.mkdir(parents=True, exist_ok=True)
    make(before, False, 1)
    make(after, True, 2)
    print("wrote", before, after)
