# Eifel Fire Radar

NASA Space Apps 2026 · Challenge "Dancing with the SARs"

We knew wildfires from Canada. In August 2026 one burned at our doorstep, in the Hürtgenwald
near Aachen. Radar sees through smoke and clouds, so we use NISAR L-band radar to show what
the fire changed in the forest canopy, and how honest that signal is.

Eifel Fire Radar is a static web map (no backend, no build step):

- **Explore**: switch between HV backscatter, colour composite and change map. A compare slider
  shows the baseline next to any date. The time slider snaps to the 9 acquisitions (24 Jun to
  10 Oct 2026), with the fire window marked. Click a point to see its HV history as a chart.
- **Learn**: 5 short steps: how radar sees, HH, HV, the colour composite, and what changed.
- **Data & method**: sources, processing steps, all scene statistics and the limits.

## Open it

Double-click `app/index.html`. It works from `file://` because all data are loaded with
`<script>` tags. Only the OpenStreetMap tiles and the Inter font need internet.

Optional local server (needed only for the official fire perimeter, see below):

```bash
cd app
python3 -m http.server 8000
# open http://localhost:8000
```

Deep links for the demo: `index.html#learn-3` opens Learn step 3;
`index.html#layer=diff&date=2026-09-28&compare=0` opens the change map of 28 Sep.
Arrow keys ← → change the date (Explore) or the step (Learn).

## Files

```
app/
  index.html, style.css, app.js     the app (vanilla JS, commented)
  lib/leaflet.js, lib/leaflet.css   Leaflet 1.9.4, vendored
  layers_series_all/                data: one HV, composite and change PNG per date
    series_meta.js                  window.NISAR_SERIES (dates, ranges, statistics)
    series_grid.js                  window.NISAR_GRID (dB grid for the point chart)
  data/perimeter.geojson            optional, not included
forest_watch_api/scripts/
  gcov_change.py                    NISAR GCOV -> PNG layers + metadata
  make_grid.py                      PNGs -> series_grid.js
```

## How the data were made

1. `gcov_change.py series` reads 9 NISAR L2 GCOV granules (provisional), track 144, ascending,
   all at about 04:20 UTC. Only the bounding box 6.37–6.45° E, 50.72–50.77° N is read.
2. HH and HV power are averaged over 5 × 5 pixels in linear units (less speckle), converted to dB
   and resampled to a 900 × 889 px lon/lat grid.
3. Baseline = 11 Aug 2026, the last scene before the fire (14–20 Aug). For every date:
   change = HV(date) − HV(baseline). "Loss" = drop larger than 1.5 dB.
   Burn mask = loss area in the first post-fire scene (23 Aug): 3.4 ha.
4. `make_grid.py` downsamples the HV PNGs to an 80 × 79 cell grid (about 70 m cells) and rebuilds
   the burn mask from the change PNG (checked: 3.4 ha, the same as the metadata). Browsers do not
   allow pixel reads of local files, so the chart reads this grid.

Rebuild the grid after new data:

```bash
python3 forest_watch_api/scripts/make_grid.py          # needs numpy, Pillow
```

## Limits

- HV change is a proxy for loss of canopy structure, **not** biomass in t/ha.
- Rain and soil moisture also change L-band backscatter. All scenes share one track and
  direction, but weather is not removed. On 23 Aug most of the area got *brighter* in HV
  (mean +1.3 dB). We have not checked this against rain data.
- NISAR GCOV data are **provisional** (not fully validated).
- Noise floor: about 1 % of pixels exceed 1.5 dB without any fire. Pre-fire scenes already show
  up to 24.9 ha of "loss", and 28 Sep shows 122.5 ha, much more than the 3.4 ha burn mask.
  Red on the change map means "look here", not "burned".
- We do not claim causes beyond what the data show.
- The official fire perimeter is not included. If `app/data/perimeter.geojson` exists, the app
  shows it as a dashed red line with a toggle (needs the local server, `fetch` is blocked on file://).

## Data sources

- NISAR Level-2 GCOV, NASA/ISRO, distributed by the Alaska Satellite Facility DAAC
  (https://search.asf.alaska.edu/). Granule IDs are listed in the app ("Data & method").
- Basemap © OpenStreetMap contributors.
- Leaflet (BSD-2-Clause), Inter font (SIL Open Font License, via Google Fonts).
- Fire dates: [PLACEHOLDER: official source for the 14–20 Aug 2026 fire]

## Team

[PLACEHOLDER: team names]
