from __future__ import annotations

import os
from pathlib import Path
from dotenv import load_dotenv

# Load .env from the project root when running locally.
PROJECT_ROOT = Path(__file__).resolve().parents[1]
load_dotenv(PROJECT_ROOT / ".env")


def env_int(name: str, default: int) -> int:
    raw = os.getenv(name)
    if not raw:
        return default
    try:
        return int(raw)
    except ValueError as exc:
        raise RuntimeError(f"Environment variable {name} must be an integer") from exc


EARTHDATA_USERNAME = os.getenv("EARTHDATA_USERNAME", "").strip()
EARTHDATA_PASSWORD = os.getenv("EARTHDATA_PASSWORD", "").strip()
NISAR_LOCAL_FILE = os.getenv("NISAR_LOCAL_FILE", "").strip()
NISAR_LOCAL_GRANULE_ID = os.getenv("NISAR_LOCAL_GRANULE_ID", "").strip()
NISAR_STREAM_BLOCK_SIZE = max(256 * 1024, env_int("NISAR_STREAM_BLOCK_SIZE", 2 * 1024 * 1024))
CORS_ORIGINS = [
    item.strip()
    for item in os.getenv("CORS_ORIGINS", "http://localhost:5173").split(",")
    if item.strip()
]
