from __future__ import annotations

from datetime import date
from typing import Any


def _as_int(value: Any) -> int | None:
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return int(value)
    return None


def _extract_size_bytes(raw: Any) -> int | None:
    """ASF NISAR records may expose bytes as a nested filename->metadata mapping."""
    if isinstance(raw, (int, float)):
        return int(raw)
    if isinstance(raw, dict):
        for item in raw.values():
            if isinstance(item, dict) and isinstance(item.get("bytes"), (int, float)):
                return int(item["bytes"])
    return None


def _serialize_product(product: Any) -> dict[str, Any]:
    props = getattr(product, "properties", {}) or {}
    granule_id = (
        props.get("fileID")
        or props.get("sceneName")
        or props.get("granuleName")
        or getattr(product, "name", None)
    )
    maturity = props.get("dataMaturity")
    collection_name = props.get("collectionName") or ""
    if not maturity:
        for candidate in ("VALIDATED", "PROVISIONAL", "BETA"):
            if candidate in collection_name.upper():
                maturity = candidate
                break

    path_number = props.get("pathNumber")
    try:
        path_number = int(path_number) if path_number is not None else None
    except (TypeError, ValueError):
        path_number = None

    return {
        "granule_id": granule_id,
        "start_time": props.get("startTime"),
        "stop_time": props.get("stopTime"),
        "processing_level": props.get("processingLevel"),
        "data_maturity": maturity,
        "direction": props.get("flightDirection"),
        "path_number": path_number,
        "size_bytes": _extract_size_bytes(props.get("bytes")),
        "platform": props.get("platform"),
        "sensor": props.get("sensor"),
        "frame_coverage": props.get("frameCoverage"),
        "collection_name": collection_name or None,
    }


def search_nisar_scenes(
    bbox: tuple[float, float, float, float],
    start: date,
    end: date,
    data_maturity: str | None,
    direction: str | None,
    max_results: int,
) -> list[dict[str, Any]]:
    """Search the ASF catalog using the official asf_search Python package."""
    try:
        import asf_search as asf
    except ImportError as exc:  # pragma: no cover - depends on deployment environment
        raise RuntimeError(
            "asf-search is not installed. Run: pip install -r requirements.txt"
        ) from exc

    west, south, east, north = bbox
    wkt = (
        f"POLYGON(({west} {south}, {east} {south}, {east} {north}, "
        f"{west} {north}, {west} {south}))"
    )
    params: dict[str, Any] = {
        "dataset": "NISAR",
        "processingLevel": "SME2",
        "intersectsWith": wkt,
        "start": f"{start.isoformat()}T00:00:00Z",
        "end": f"{end.isoformat()}T23:59:59Z",
        "maxResults": max_results,
    }
    if data_maturity:
        params["dataMaturity"] = data_maturity

    # `asf_search` uses flightDirection as an ASF search parameter.
    if direction:
        params["flightDirection"] = direction

    results = asf.search(**params)
    scenes = [_serialize_product(product) for product in results]
    return [scene for scene in scenes if scene.get("granule_id")]


def get_nisar_access_url(granule_id: str) -> str:
    """Resolve the HTTPS data URL for a specific NISAR granule via ASF."""
    try:
        import asf_search as asf
    except ImportError as exc:  # pragma: no cover
        raise RuntimeError("asf-search is not installed") from exc

    results = asf.search(dataset="NISAR", granule_list=[granule_id])
    if not results:
        raise LookupError(f"Granule not found in ASF: {granule_id}")

    urls = results[0].get_urls()
    if not urls:
        raise LookupError(f"ASF returned no data URL for granule: {granule_id}")

    https_urls = [url for url in urls if isinstance(url, str) and url.startswith("https://")]
    if not https_urls:
        raise LookupError("ASF did not return an HTTPS URL for this granule")
    return https_urls[0]
