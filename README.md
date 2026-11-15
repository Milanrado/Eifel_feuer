# Eifel Fire Radar

NASA Space Apps 2026 · Challenge "Dancing with the SARs"

We knew wildfires from Canada. In August 2026 one burned at our doorstep, in the Hürtgenwald
near Aachen. Radar sees through smoke and clouds, so we use NISAR L-band radar to show what
the fire changed in the forest canopy, and how honest that signal is.

Two study areas, switchable in the header:

- **Hürtgenwald** (Eifel, Germany): the fire at our doorstep, 14–20 Aug 2026, NISAR track 144.
- **Monthermé** (Ardennes, France): in the same August week a fire burned about 95 ha of steep
  forest at Monthermé, in the wooded border country between France and Belgium (15–17 Aug 2026,
  contained per the prefecture on 16 Aug). Seen by NISAR track 66, an evening orbit — including
  one image taken on 17 August at 18:49 UTC, while the last embers were still being watched:
  radar does not care about smoke or darkness.

- **Gironde** (west of Bordeaux, France): the Saumos fire, 22 Jul – 1 Aug 2026, about 42,000 ha
  (39,000 ha of forest, per ONF). NISAR track 95, descending, about 19:08 UTC; box
  −1.1957 to −0.6416° E, 44.6092–45.0121° N, about 44 × 45 km.

Eifel Fire Radar is a static web map (no backend, no build step):

- **Explore**: a full-screen map with three controls.
  - *Layers* (left card, can be folded away): **Forest**, **Change**, **Ground and buildings**,
    **Vegetation** and **Moisture**. *Change* compares every place with itself (forest echo of the
    date shown minus the last image before the fire), so land that was already open before the fire
    stays white and only real loss turns red. The names say what a layer means; the radar terms (HV, HH, RVI, SME2) are
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
  layers_series_all/                data, Hürtgenwald (the Monthermé data in layers_series_fr/ have the same layout)
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
   The Monthermé series was built the same way from 11 granules of track 66, descending,
   about 18:49 UTC, box 4.70–4.82° E, 49.86–49.95° N. The box is centred on the hamlets the press
   names at the fire's edge (Les Woieries, Les Hauts-Buttés, see
   [ici.fr](https://www.ici.fr/grand-est/ardennes-08/montherme/massif-de-montherme-un-important-feu-de-foret-se-declare-visible-jusqu-a-charleville-mezieres-7805183)).
   Monthermé sits at the eastern edge of the
   swath of the ascending track 173, where the image border wanders from pass to pass, so the
   stable descending track is used instead. From `forest_watch_api/`:

   ```bash
   # macOS: if Python reports an SSL certificate error, point it at certifi first:
   #   export SSL_CERT_FILE=$(.venv/bin/python3 -c "import certifi; print(certifi.where())")
   python scripts/gcov_change.py series \
     --bbox 4.70 49.86 4.82 49.95 \
     --granules $(cat scripts/gcov_granules_track66_montherme.txt) \
     --fire-start 2026-08-15 --fire-end 2026-08-17 \
     --out ../app/layers_series_fr
   python scripts/make_stable.py ../app/layers_series_fr
   python scripts/make_damage.py ../app/layers_series_fr
   ```

   The Gironde series uses the same scripts on 12 granules of track 95
   (`scripts/gcov_granules_track95_gironde.txt`); one granule takes about a minute to stream:

   ```bash
   python scripts/gcov_change.py series \
     --bbox -1.1957 44.6092 -0.6416 45.0121 \
     --granules $(cat scripts/gcov_granules_track95_gironde.txt) \
     --fire-start 2026-07-22 --fire-end 2026-08-01 \
     --width 1000 \
     --out ../app/layers_series_gironde
   python scripts/make_stable.py ../app/layers_series_gironde
   python scripts/make_damage.py ../app/layers_series_gironde
   python scripts/make_vegetation.py ../app/layers_series_gironde   # Gironde only: buildings, water, Vegetation scale
   ```

   `make_vegetation.py` (Gironde only) starts the Vegetation colour scale at the burned forest
   instead of at the buildings, which have the lowest vegetation index of all, and paints buildings
   in a neutral grey off the scale. A pixel counts as a building when HH is at least −3 dB in every
   pre-fire image and HH − HV at least 7 dB. Against OpenStreetMap buildings around Le Porge and
   Saumos about 95 % of these pixels lie at a building. In the hilly Eifel the same rule also marks
   steep slopes facing the satellite (only about 70 % hits), so it is not used there.
   It also marks open water (Bassin d'Arcachon, Lac de Lacanau) in a blue-grey on every layer: HV at
   most −21 dB and HH at most −14.5 dB in almost every image, areas of at least 500 ha. Smaller dark
   areas were a mix of ponds and bare fields (OpenStreetMap check: 2 of 5 were water), so they are
   left out.

   The box is about 44 km wide, so 1000 px gives about 44 m pixels: coarser than the 20 m of the
   data, but plenty for a 42,000 ha fire and small enough for the web (about 30 MB).

   The 17 Aug scene was taken during the fire (role "during"): it is shown on the timeline but,
   by construction, is used neither as "before" nor as "after" by the damage test. The Meuse
   river crosses the box; water mirrors the pulse away and simply reads as "open land".
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
5. **Moisture** comes from NISAR SME2 soil moisture (same tracks and dates as the radar images) and
   needs an Earthdata login in `forest_watch_api/.env`. Inside `forest_watch_api/`:

   ```bash
   python scripts/sme2_layers.py build --include-unrecommended --out ../app/layers_series_all    --granules $(cat scripts/sme2_granules_track144.txt)
   python scripts/sme2_layers.py build --include-unrecommended --out ../app/layers_series_fr     --granules $(cat scripts/sme2_granules_track66_montherme.txt)
   python scripts/sme2_layers.py build --include-unrecommended --out ../app/layers_series_gironde --granules $(cat scripts/sme2_granules_track95_gironde.txt)
   ```

   The layers keep all valid pixels (`--include-unrecommended`), so the map is filled: Hürtgenwald 99 %
   of the box (9 dates), Monthermé 98–99 % (10 dates), Gironde 87–88 % (11 dates; the rest is water and
   towns). Most of these pixels are **not** marked as recommended by the product, mainly under forest,
   where the satellite sees the trees more than the soil. With recommended pixels only the layer
   covered just 17–18 %, 0.2 % and 12–13 %. The app says this in the layer text and under About.
   The colours span the region's scene medians ± 0.15 m³/m³ (inside the product range 0–0.6), so
   typical values are not lost in the pale middle of the palette.

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
- Fire dates Hürtgenwald: [PLACEHOLDER: official source for the 14–20 Aug 2026 fire]
- Fire dates Gironde (Saumos):
  [Feux de Forêt](https://feuxdeforet.fr/en/gironde-33/saumos-22-07-2026-4367/) (start 22 Jul, fixed 1 Aug 2026),
  area from [ONF](https://www.onf.fr/vivre-la-foret/enjeux-foret/feux-foret/+/2dae::incendies-en-gironde-et-dans-les-landes-les-forestiers-de-lonf-au-coeur-de-la-crise.html).
- Fire dates Monthermé: Préfecture des Ardennes via
  [franceinfo, 16 Aug 2026](https://www.franceinfo.fr/faits-divers/incendie/le-feu-de-foret-dans-les-ardennes-est-desormais-circonscrit-selon-la-prefecture_8150165.html),
  [L'Avenir, 18 Aug 2026](https://www.lavenir.net/actu/monde/2026/08/18/feux-de-foret-pres-de-la-frontiere-franco-belge-lincendie-dans-une-foret-des-ardennes-desormais-fixe-XH2JJ5G2TJD7FGA7PIXPW5IEEI/) and
  [Matélé, 17 Aug 2026](https://www.matele.be/incendie-a-montherme-france-100-hectares-sont-deja-partis-en-fumee) (95 ha after ground survey).

## Team

[PLACEHOLDER: team names]
