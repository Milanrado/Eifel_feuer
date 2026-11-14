"""Pairing logic for /api/nisar/change (no network, no HDF5 needed)."""
from app.services import moisture


def feat(row, col, v):
    return {"type": "Feature", "geometry": {"type": "Point", "coordinates": [6.4, 50.7]},
            "properties": {"pixel_row": row, "pixel_col": col, "soil_moisture_m3_m3": v}}


def test_pairing(monkeypatch):
    data = {
        "before": {"features": [feat(1, 1, 0.2), feat(1, 2, 0.2), feat(2, 2, 0.3)]},
        "after": {"features": [feat(1, 1, 0.3), feat(1, 2, 0.1), feat(9, 9, 0.5)]},
    }
    monkeypatch.setattr(moisture, "moisture_geojson", lambda gid, bbox, max_points=0: data[gid])
    out = moisture.moisture_change("before", "after", (6.37, 50.72, 6.45, 50.77))
    s = out["summary"]
    assert s["paired_pixel_count"] == 2
    assert s["pixels_increased"] == 1 and s["pixels_decreased"] == 1
    assert s["pixels_before_only"] == 1 and s["pixels_after_only"] == 1
