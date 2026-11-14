# Eifel Fire Radar

NASA Space Apps 2026 · Challenge "Dancing with the SARs"

We knew wildfires from Canada. In August 2026 one burned at our doorstep, in the Hürtgenwald
near Aachen. Radar sees through smoke and clouds, so we use NISAR L-band radar to show what
the fire changed in the forest canopy, and how honest that signal is.

Eifel Fire Radar is a static web map (no backend, no build step):

- **Explore**: a full-screen map with three controls.
  - *Layers* (left card, can be folded away): **Forest**, **Ground and buildings**, **Vegetation**
    and **Moisture**. The names say what a layer means; the radar terms (HV, HH, RVI, SME2) are
    explained under *About*.
  - *Compare* (button on the map): pick a second date and drag the line between the two.
  - *Time* (bottom): one handle that snaps to the acquisitions, with the fire window marked.
- **Learn**: 6 short steps: how radar sees, HH, HV, the colour composite, finding the damage,
  before and now.
- **About**: layers, sources, method, scene table and limits.

## Open it

Double-click `app/index.html`. It works from `file://` because all data are loaded with
`<script>` tags. Only the OpenStreetMap tiles and the Inter font need internet.

Optional local server (needed only for the official fire perimeter, see below):

```bash
cd app
python3 -m http.server 8000
# open http://localhost:8000
```

`index.html#learn-3` opens Learn step 3. Arrow keys ← → change the date (Explore) or the step (Learn).

## Files

```
app/
  index.html, style.css, app.js     the app (vanilla JS, commented)
  lib/leaflet.js, lib/leaflet.css   Leaflet 1.9.4, vendored
  layers_series_all/                data
    hv_<date>.png, composite_<date>.png   grey radar images per date (coloured in the browser)
    series_meta.js                  window.NISAR_SERIES (dates, ranges, statistics)
    stable_<date>.png, stable.js    weather-steadied radar images; the layers use these
    damage.js, damage_outline.png   optional: lasting damage area (used by Learn and About)
    moisture_<date>.png, moisture_meta.js   optional: soil moisture, switches the Moisture layer on
  data/perimeter.geojson            optional, not included
forest_watch_api/scripts/
  gcov_change.py                    NISAR GCOV -> radar PNG layers + metadata
  make_stable.py                    radar PNGs -> steadied layers (stable_<date>.png, stable.js)
  make_damage.py                    radar PNGs -> damage.js + outline
  sme2_layers.py                    NISAR SME2 soil moisture -> moisture PNGs + metadata
  make_grid.py                      PNGs -> series_grid.js (not used by the current app)
```

## How the data were made

1. `gcov_change.py series` reads 9 NISAR L2 GCOV granules (provisional), track 144, ascending,
   all at about 04:20 UTC. Only the bounding box 6.37–6.45° E, 50.72–50.77° N is read.
2. HH and HV power are averaged over 5 × 5 pixels in linear units (less speckle), converted to dB
   and resampled to a 900 × 889 px lon/lat grid. The composite PNG stores HH in red and HH − HV
   in blue; the app reads "Ground and buildings" and "Vegetation" (RVI = 4·HV / (HH + HV)) from it.
3. `make_stable.py` steadies the images so that weather does not look like change. In the raw
   images the area brighter than −3 dB in HH jumps from 2.6 % (11 Aug) to 13.5 % (23 Aug), and
   "forest" (HV above −12 dB) from 43 % to 57 %: rain, not buildings or trees. The script removes
   one scene-wide offset per date and band, then takes the pixel-wise median of three consecutive
   passes. After that both shares stay within about 2 percentage points over all dates. One-off
   flickers disappear; changes that last two passes or more stay.
   The Forest layer has one more rule: a pixel may fall but never rise above its level before the
   fire. Trees do not grow in weeks; without the rule, fields that get wetter or overgrown after
   the fire (10 to 19 % of the open land rises by more than 1 dB) read as "more forest".
   Rerun after new radar layers:

   ```bash
   python forest_watch_api/scripts/make_stable.py          # needs numpy, Pillow
   ```
4. `make_damage.py` marks the pixels whose HV is more than 1.5 dB below the pre-fire median in at
   least 4 of the 5 post-fire scenes and keeps connected patches of at least 1 ha: 16.4 ha.
   Rerun it after new radar layers:

   ```bash
   python forest_watch_api/scripts/make_damage.py          # needs numpy, Pillow
   ```
5. **Moisture is not exported yet.** It comes from NISAR SME2 soil moisture and needs an Earthdata
   login in `forest_watch_api/.env` (same as the API). Inside `forest_watch_api/`:

   ```bash
   python scripts/sme2_layers.py search --start 2026-06-20 --end 2026-10-15
   python scripts/sme2_layers.py build --granules $(cat scripts/sme2_granules_track144.txt)
   ```

   `scripts/sme2_granules_track144.txt` lists the 9 SME2 granules of track 144 found by the search:
   the same dates as the radar images.

   Until then the Moisture layer is shown greyed out ("No data yet"). The script was only tested
   with a synthetic SME2 file, not with a real granule.

## Limits

- HV change is a proxy for loss of canopy structure, **not** biomass in t/ha.
- Rain and soil moisture also change L-band backscatter. All scenes share one track and
  direction, but weather is not removed. On 23 Aug most of the area got *brighter* in HV
  (mean +1.3 dB). We have not checked this against rain data.
- NISAR GCOV data are **provisional** (not fully validated).
- Noise floor: about 1 % of pixels exceed 1.5 dB without any fire, and single scenes flag tens of
  hectares. That is why the damaged area uses "low in 4 of 5 post-fire scenes".
- The lasting loss first shows on 4 Sep, not in the first scene after the fire window used here
  (23 Aug). Radar cannot tell fire from felling or clearing.
- Soil moisture (SME2) is not fuel moisture, and dense forest is often not recommended by the
  product, so the Moisture layer has gaps.
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
