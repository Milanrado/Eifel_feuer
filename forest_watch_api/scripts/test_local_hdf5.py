"""Smoke-test the moisture endpoint against a local NISAR HDF5 file."""
from __future__ import annotations

import argparse
import json

from app.services.moisture import moisture_geojson


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--granule-id", required=True)
    parser.add_argument(
        "--bbox", required=True,
        help="WGS84 west,south,east,north; e.g. 6.37,50.72,6.45,50.77",
    )
    args = parser.parse_args()
    bbox = tuple(float(part) for part in args.bbox.split(","))
    if len(bbox) != 4:
        raise SystemExit("--bbox must contain four comma-separated numbers")
    result = moisture_geojson(args.granule_id, bbox, max_points=1000)
    print(json.dumps(result["summary"], indent=2))
    print("GeoJSON features:", len(result["features"]))


if __name__ == "__main__":
    main()
