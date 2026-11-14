/**
 * OpenUI Renderer toolProvider for FOREST WATCH.
 * Keep Earthdata credentials on the Python server; this browser code calls only your API.
 */
const API_BASE = import.meta.env.VITE_FOREST_WATCH_API ?? "http://localhost:8000";

async function postJson<T>(path: string, payload: Record<string, unknown>): Promise<T> {
  const response = await fetch(`${API_BASE}${path}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });

  if (!response.ok) {
    const body = await response.json().catch(() => ({}));
    const detail = body.detail ?? `HTTP ${response.status}`;
    throw new Error(String(detail));
  }
  return response.json() as Promise<T>;
}

export const forestWatchToolProvider = {
  /** Search the ASF catalogue for NISAR SME2 scenes. */
  search_nisar: (args: {
    bbox: [number, number, number, number]; // west, south, east, north
    start: string; // YYYY-MM-DD
    end: string; // YYYY-MM-DD
    data_maturity?: "VALIDATED" | "PROVISIONAL" | "BETA";
    direction?: "ASCENDING" | "DESCENDING";
    max_results?: number;
  }) => postJson("/api/nisar/search", args),

  /** Stream a selected granule and return a sampled soil-moisture GeoJSON layer. */
  get_moisture_layer: (args: {
    granule_id: string;
    bbox: [number, number, number, number];
    max_points?: number;
    include_unrecommended?: boolean;
  }) => postJson("/api/nisar/moisture", args),

  /** Pixel-paired SME2 change between two granules. */
  get_moisture_change: (args: {
    granule_before: string;
    granule_after: string;
    bbox: [number, number, number, number];
    max_points?: number;
  }) => postJson("/api/nisar/change", args),
};
