from __future__ import annotations

from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterator
import math
import os

import h5py
import numpy as np
from pyproj import Transformer

from app.config import (
    EARTHDATA_PASSWORD,
    EARTHDATA_USERNAME,
    NISAR_LOCAL_FILE,
    NISAR_LOCAL_GRANULE_ID,
    NISAR_STREAM_BLOCK_SIZE,
)
from app.services.asf_client import get_nisar_access_url

GRID = "/science/LSAR/SME2/grids"


@contextmanager
def open_granule_hdf5(granule_id: str) -> Iterator[h5py.File]:
    """Open a local development granule or stream a remote ASF granule by HTTP range.

    The remote path uses fsspec's block cache and h5py's file-object driver. It does
    not explicitly download/save the complete HDF5 file to disk.
    """
    local_path = Path(NISAR_LOCAL_FILE).expanduser() if NISAR_LOCAL_FILE else None
    if local_path:
        if not local_path.is_file():
            raise FileNotFoundError(f"Configured NISAR_LOCAL_FILE does not exist: {local_path}")
        if not NISAR_LOCAL_GRANULE_ID:
            raise ValueError("Set NISAR_LOCAL_GRANULE_ID when using NISAR_LOCAL_FILE")
        if granule_id != NISAR_LOCAL_GRANULE_ID:
            raise ValueError(
                "A local NISAR file is configured, but its granule ID does not match "
                "the requested granule. Set NISAR_LOCAL_GRANULE_ID correctly or unset NISAR_LOCAL_FILE."
            )
        with h5py.File(local_path, "r") as h5:
            yield h5
        return

    if not EARTHDATA_USERNAME or not EARTHDATA_PASSWORD:
        raise PermissionError(
            "Remote NISAR streaming requires Earthdata Login. Set EARTHDATA_USERNAME "
            "and EARTHDATA_PASSWORD in your .env file."
        )

    try:
        import aiohttp
        import fsspec
    except ImportError as exc:  # pragma: no cover
        raise RuntimeError("Install fsspec[http] and aiohttp to stream NISAR data") from exc

    url = get_nisar_access_url(granule_id)
    fs = fsspec.filesystem(
        "https",
        client_kwargs={
            "auth": aiohttp.BasicAuth(EARTHDATA_USERNAME, EARTHDATA_PASSWORD)
        },
    )
    with fs.open(
        url,
        mode="rb",
        block_size=NISAR_STREAM_BLOCK_SIZE,
        cache_type="blockcache",
    ) as remote_file:
        # HDF5 makes random reads; fsspec retrieves the requested byte ranges.
        with h5py.File(remote_file, "r") as h5:
            yield h5


def _project_bbox_to_ease(bbox: tuple[float, float, float, float]) -> tuple[float, float, float, float]:
    west, south, east, north = bbox
    to_ease = Transformer.from_crs("EPSG:4326", "EPSG:6933", always_xy=True)
    corners = [
        to_ease.transform(west, south),
        to_ease.transform(west, north),
        to_ease.transform(east, south),
        to_ease.transform(east, north),
    ]
    xs = [point[0] for point in corners]
    ys = [point[1] for point in corners]
    return min(xs), min(ys), max(xs), max(ys)


def _to_float(value: Any) -> float:
    if isinstance(value, np.ndarray):
        value = value.item()
    return float(value)


def moisture_geojson(
    granule_id: str,
    bbox: tuple[float, float, float, float],
    max_points: int = 2500,
    include_unrecommended: bool = False,
) -> dict[str, Any]:
    """Read only the SME2 grid window intersecting bbox and return sampled GeoJSON.

    Pixel coordinates are in EPSG:6933. The API returns point features in WGS84,
    suitable for a first MapLibre proof of concept.
    """
    x_min, y_min, x_max, y_max = _project_bbox_to_ease(bbox)
    to_wgs84 = Transformer.from_crs("EPSG:6933", "EPSG:4326", always_xy=True)

    with open_granule_hdf5(granule_id) as h5:
        required = [
            f"{GRID}/xCoordinates",
            f"{GRID}/yCoordinates",
            f"{GRID}/soilMoisture",
            f"{GRID}/soilMoistureUncertainty",
            f"{GRID}/retrievalQualityFlag",
        ]
        missing = [path for path in required if path not in h5]
        if missing:
            raise ValueError(f"This granule is missing required SME2 variables: {missing}")

        x_coords = h5[f"{GRID}/xCoordinates"][:]
        y_coords = h5[f"{GRID}/yCoordinates"][:]

        col_idx = np.flatnonzero((x_coords >= x_min) & (x_coords <= x_max))
        row_idx = np.flatnonzero((y_coords >= y_min) & (y_coords <= y_max))
        if col_idx.size == 0 or row_idx.size == 0:
            return {
                "type": "FeatureCollection",
                "features": [],
                "summary": {
                    "granule_id": granule_id,
                    "bbox": bbox,
                    "message": "The requested bbox does not intersect this NISAR granule.",
                    "valid_pixel_count": 0,
                    "recommended_pixel_count": 0,
                    "returned_feature_count": 0,
                },
            }

        row_start, row_end = int(row_idx.min()), int(row_idx.max()) + 1
        col_start, col_end = int(col_idx.min()), int(col_idx.max()) + 1
        row_slice = slice(row_start, row_end)
        col_slice = slice(col_start, col_end)

        # HDF5 hyperslab reads: only the requested spatial window is read.
        sm = h5[f"{GRID}/soilMoisture"][row_slice, col_slice].astype(np.float32)
        uncertainty = h5[f"{GRID}/soilMoistureUncertainty"][row_slice, col_slice].astype(np.float32)
        quality = h5[f"{GRID}/retrievalQualityFlag"][row_slice, col_slice].astype(np.int32)

        fill = -9999.0
        valid = np.isfinite(sm) & (sm != fill) & (quality != -9999) & (quality >= 0)
        # SME2: least-significant bit 0 means recommended; bit 0 set means not recommended.
        recommended = valid & ((quality & 1) == 0)
        selected = valid if include_unrecommended else recommended

        valid_count = int(valid.sum())
        recommended_count = int(recommended.sum())
        selected_values = sm[selected]
        mean_value = float(np.mean(selected_values)) if selected_values.size else None
        median_value = float(np.median(selected_values)) if selected_values.size else None
        mean_uncertainty = (
            float(np.mean(uncertainty[selected & np.isfinite(uncertainty) & (uncertainty != fill)]))
            if np.any(selected & np.isfinite(uncertainty) & (uncertainty != fill))
            else None
        )

        # Keep GeoJSON response bounded for browser rendering.
        n_rows, n_cols = sm.shape
        stride = max(1, int(math.ceil(math.sqrt((n_rows * n_cols) / max_points))))
        sampled_rows = np.arange(0, n_rows, stride, dtype=int)
        sampled_cols = np.arange(0, n_cols, stride, dtype=int)
        sm_s = sm[np.ix_(sampled_rows, sampled_cols)]
        unc_s = uncertainty[np.ix_(sampled_rows, sampled_cols)]
        q_s = quality[np.ix_(sampled_rows, sampled_cols)]
        valid_s = np.isfinite(sm_s) & (sm_s != fill) & (q_s != -9999) & (q_s >= 0)
        rec_s = valid_s & ((q_s & 1) == 0)
        mask_s = valid_s if include_unrecommended else rec_s

        local_rows, local_cols = np.where(mask_s)
        abs_rows = row_start + sampled_rows[local_rows]
        abs_cols = col_start + sampled_cols[local_cols]
        xs = x_coords[abs_cols]
        ys = y_coords[abs_rows]
        lons, lats = to_wgs84.transform(xs, ys)

        features: list[dict[str, Any]] = []
        for idx in range(len(local_rows)):
            r, c = int(local_rows[idx]), int(local_cols[idx])
            features.append({
                "type": "Feature",
                "geometry": {
                    "type": "Point",
                    "coordinates": [round(float(lons[idx]), 6), round(float(lats[idx]), 6)],
                },
                "properties": {
                    "soil_moisture_m3_m3": float(sm_s[r, c]),
                    "uncertainty_m3_m3": (
                        float(unc_s[r, c])
                        if np.isfinite(unc_s[r, c]) and unc_s[r, c] != fill
                        else None
                    ),
                    "retrieval_quality_flag": int(q_s[r, c]),
                    "recommended": bool((int(q_s[r, c]) & 1) == 0),
                    "pixel_row": int(abs_rows[idx]),
                    "pixel_col": int(abs_cols[idx]),
                },
            })

        spacing_x = float(np.nanmedian(np.abs(np.diff(x_coords)))) if len(x_coords) > 1 else None
        spacing_y = float(np.nanmedian(np.abs(np.diff(y_coords)))) if len(y_coords) > 1 else None
        return {
            "type": "FeatureCollection",
            "features": features,
            "summary": {
                "granule_id": granule_id,
                "bbox": bbox,
                "crs_source": "EPSG:6933",
                "crs_output": "EPSG:4326",
                "units": "m3/m3",
                "grid_window_rows": int(sm.shape[0]),
                "grid_window_columns": int(sm.shape[1]),
                "pixel_spacing_m": {
                    "x": round(spacing_x, 2) if spacing_x else None,
                    "y": round(spacing_y, 2) if spacing_y else None,
                },
                "valid_pixel_count": valid_count,
                "recommended_pixel_count": recommended_count,
                "recommended_share_of_valid_percent": (
                    round(100 * recommended_count / valid_count, 2) if valid_count else None
                ),
                "mean_soil_moisture_m3_m3": round(mean_value, 5) if mean_value is not None else None,
                "median_soil_moisture_m3_m3": round(median_value, 5) if median_value is not None else None,
                "mean_uncertainty_m3_m3": round(mean_uncertainty, 5) if mean_uncertainty is not None else None,
                "returned_feature_count": len(features),
                "sampling_stride_pixels": stride,
                "include_unrecommended": include_unrecommended,
                "quality_rule": "retrievalQualityFlag bit 0 = 0 means recommended",
                "data_maturity_note": "SME2 PROVISIONAL values are not fully calibrated/validated; inspect QA flags.",
            },
        }


def moisture_change(
    granule_before: str,
    granule_after: str,
    bbox: tuple[float, float, float, float],
    max_points: int = 10000,
) -> dict[str, Any]:
    """Pixel-paired SME2 soil-moisture change between two granules (recommended pixels only).

    The EASE-Grid 2.0 (EPSG:6933) pixel indices are shared by all granules, so pixels are
    paired by (pixel_row, pixel_col). This describes an observed change, not its cause.
    """
    a = moisture_geojson(granule_before, bbox, max_points=max_points)
    b = moisture_geojson(granule_after, bbox, max_points=max_points)
    pa = {(f["properties"]["pixel_row"], f["properties"]["pixel_col"]): f for f in a["features"]}
    pb = {(f["properties"]["pixel_row"], f["properties"]["pixel_col"]): f for f in b["features"]}
    common = sorted(set(pa) & set(pb))
    deltas = []
    features = []
    for key in common:
        va = pa[key]["properties"]["soil_moisture_m3_m3"]
        vb = pb[key]["properties"]["soil_moisture_m3_m3"]
        d = vb - va
        deltas.append(d)
        features.append({
            "type": "Feature",
            "geometry": pb[key]["geometry"],
            "properties": {
                "before_m3_m3": va,
                "after_m3_m3": vb,
                "change_m3_m3": round(d, 5),
                "change_percent": round(100 * d / va, 2) if va else None,
            },
        })
    arr = np.array(deltas, dtype=np.float64)
    mean_a = float(np.mean([pa[k]["properties"]["soil_moisture_m3_m3"] for k in common])) if common else None
    mean_b = float(np.mean([pb[k]["properties"]["soil_moisture_m3_m3"] for k in common])) if common else None
    return {
        "type": "FeatureCollection",
        "features": features,
        "summary": {
            "granule_before": granule_before,
            "granule_after": granule_after,
            "bbox": bbox,
            "paired_pixel_count": len(common),
            "pixels_before_only": len(set(pa) - set(pb)),
            "pixels_after_only": len(set(pb) - set(pa)),
            "mean_before_m3_m3": round(mean_a, 5) if mean_a is not None else None,
            "mean_after_m3_m3": round(mean_b, 5) if mean_b is not None else None,
            "mean_change_m3_m3": round(float(arr.mean()), 5) if arr.size else None,
            "mean_change_percent": round(100 * (mean_b - mean_a) / mean_a, 2) if arr.size and mean_a else None,
            "pixels_increased": int((arr > 0).sum()),
            "pixels_decreased": int((arr < 0).sum()),
            "interpretation_note": (
                "Observed change between two SME2 acquisitions only. Rain and other weather between the dates "
                "can explain it, and this API does not include weather data. SME2 is soil moisture, not fuel moisture; "
                "PROVISIONAL data are not fully validated."
            ),
        },
    }
