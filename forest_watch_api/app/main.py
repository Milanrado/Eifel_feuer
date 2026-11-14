from __future__ import annotations

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

from app.config import CORS_ORIGINS
from app.models import MoistureChangeRequest, MoistureRequest, NisarSearchRequest
from app.services.asf_client import search_nisar_scenes
from app.services.moisture import moisture_change, moisture_geojson

app = FastAPI(
    title="FOREST WATCH API",
    version="0.3.0",
    description=(
        "NISAR SME2 scene discovery, spatially subsetted soil-moisture access and "
        "before/after change analysis for the Forest Watch hackathon prototype (NISAR data only)."
    ),
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=CORS_ORIGINS,
    allow_credentials=False,
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["*"],
)


@app.get("/health")
def health():
    return {"status": "ok", "service": "forest-watch-api", "version": app.version}


@app.post("/api/nisar/search")
def search_nisar(request: NisarSearchRequest):
    """Find NISAR SME2 granules intersecting a WGS84 bounding box."""
    try:
        scenes = search_nisar_scenes(
            bbox=request.bbox,
            start=request.start,
            end=request.end,
            data_maturity=request.data_maturity,
            direction=request.direction,
            max_results=request.max_results,
        )
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"ASF search failed: {exc}") from exc

    return {
        "count": len(scenes),
        "query": request.model_dump(mode="json"),
        "scenes": scenes,
    }


@app.post("/api/nisar/moisture")
def get_moisture(request: MoistureRequest):
    """Stream one NISAR SME2 granule and return a bounded GeoJSON subset."""
    try:
        return moisture_geojson(
            granule_id=request.granule_id,
            bbox=request.bbox,
            max_points=request.max_points,
            include_unrecommended=request.include_unrecommended,
        )
    except PermissionError as exc:
        raise HTTPException(status_code=401, detail=str(exc)) from exc
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"NISAR data access failed: {exc}") from exc


@app.post("/api/nisar/change")
def nisar_change(request: MoistureChangeRequest):
    """Pixel-paired soil-moisture change between two NISAR SME2 granules (before/after)."""
    try:
        return moisture_change(
            granule_before=request.granule_before,
            granule_after=request.granule_after,
            bbox=request.bbox,
            max_points=request.max_points,
        )
    except PermissionError as exc:
        raise HTTPException(status_code=401, detail=str(exc)) from exc
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"NISAR data access failed: {exc}") from exc
