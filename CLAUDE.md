# Task: build a static map app for the NASA Space Apps challenge "Dancing with the SARs"

## Context
Team of 4 students, 48h hackathon (ends Sunday). We visualise a real forest fire near Aachen
(Hürtgenwald / Hohes Venn region, fire 14-20 Aug 2026) using L-band radar from NISAR (NASA-ISRO).
Judged on: Impact, Creativity, Validity (science + usability), Relevance (NASA data as core),
Presentation (storytelling). The result must be uploadable to GitHub and run without a backend.

Story: "We knew wildfires from Canada. In 2026 one burned at our doorstep. Radar sees through smoke and
clouds, so we can measure what the fire changed in the forest canopy."

## Data (already processed, do not re-download anything)
Folder: app/layers_series_all/ (fall back to app/layers_series/ or app/layers/ if missing).
Created by forest_watch_api/scripts/gcov_change.py (command `series`) from NISAR GCOV, track 144 ascending,
9 dates (24 Jun - 10 Oct 2026), baseline = 11 Aug (last scene before the fire).
Files per date YYYY-MM-DD: hv_<date>.png (HV backscatter, grey, bright = dense canopy),
composite_<date>.png (R=HH, G=HV, B=HH-HV in dB), diff_hv_<date>.png (HV minus baseline; red = loss,
blue = gain, transparent where little change). All PNGs are RGBA, same size, in lon/lat (EPSG:4326),
transparent where there is no data.
series_meta.js sets window.NISAR_SERIES = {
  bbox [w,s,e,n], coordinates [[w,n],[e,n],[e,s],[w,s]], image_size [w,h],
  db_range {HH:[lo,hi], HV:[lo,hi], ratio:[lo,hi]}  (grey value 0..255 maps linearly to lo..hi dB),
  diff_range_db, threshold_db, fire {start,end}, baseline (date), burn_mask_from (date),
  burn_mask_area_ha, cell_area_ha, notes,
  scenes: [{date, time, source, role: pre|baseline|during|post, hv, composite, diff,
            mean_hv_db, mean_hv_in_burn_mask_db, mean_diff_db, loss_area_ha, loss_share_percent}] }
Read series_meta.js first and build everything from it, never hard-code dates or numbers.

## Step 0 (small script)
Browsers block canvas pixel reads of local files, so write forest_watch_api/scripts/make_grid.py:
read the hv_*.png of the series plus series_meta.json, downsample to about 80 columns, convert grey
value back to dB with db_range, null where alpha = 0, and write app/<folder>/series_grid.js
(window.NISAR_GRID = {width, height, dates: {date: [[...rows...]]}}). Run it. Clicking a map point later
reads this grid, not the PNGs.

## Step 1: app (vanilla HTML/CSS/JS, no build step, no framework)
Files: app/index.html, app/style.css, app/app.js, app/lib/ (vendored libraries, no CDN except basemap tiles).
- Map: Leaflet (vendored in lib/), OpenStreetMap tiles with attribution, L.imageOverlay with
  meta.coordinates bounds. Prefer Leaflet because MapLibre cannot load local image files from file://.
  Data comes in via <script src="layers/series_meta.js"> style tags, not fetch().
- Must work by double-clicking index.html; if something truly needs a server, document
  `python3 -m http.server 8000` in README.
- EXPLORE mode: left panel with (01) layer radio buttons: HV, composite, change map; (02) display options:
  before/after compare checkbox, opacity range; (03) selected point: click on map -> small SVG line chart
  of HV dB over all dates from the grid, with the fire window marked.
  Compare slider (draggable handle on the map): left shows the baseline HV, right shows the chosen date;
  implement by clipping the right overlay with CSS clip-path updated on slider drag, map move and zoom.
  Bottom time slider: horizontal line with one stop per scene, handle snaps magnetically to the nearest
  date (an <input type=range min=0 max=N-1 step=1> styled, or custom with pointer events), labels show date and
  role (pre-fire / before / post-fire), fire window 14-20 Aug marked in red. Arrow keys work.
  Info card: loss_area_ha of the chosen date and burn_mask_area_ha, legend with dB scale and plain-language text.
- LEARN mode (5 steps, Back/Next buttons and arrow keys, each step sets layer and map view):
  1 how radar sees (active sensor, works at night, through smoke and clouds), 2 HH = surface,
  3 HV = canopy (tangled structure scatters V echo), 4 colour composite and legend, 5 what changed (diff).
  Each step: heading, 2-3 sentences, one small inline SVG diagram where useful, an "On the map" hint.
- Header: title "Eifel Fire Radar", subtitle "NISAR L-band · Hürtgenwald, August 2026", Explore/Learn switch,
  Reset view, "Data & method" dialog (sources, method, limits).
- Footer credit: "NISAR GCOV, NASA/ISRO via ASF DAAC. Basemap © OpenStreetMap contributors".

## Design: Swiss style, clean
White background, black text and 1px black rules, ONE accent red #E30613 (only for active state, "after",
fire window, loss), grey #5F5F5F for secondary text, font Inter (Google Fonts link ok) with weight/size for hierarchy,
no rounded corners, no shadows, no gradients, no emoji, numbered section labels (01, 02, 03) in small caps.
Touch targets >= 44px, text contrast >= 4.5:1, real <button>, <label>, <input>. UI language: English.
Radar layers stay greyscale; info boxes on the map are white with a black border.

## Honest limits (show them in the "Data & method" dialog)
- HV change is a proxy for canopy structure loss, NOT biomass in t/ha.
- Rain and soil moisture also change L-band backscatter. Compare same track and direction only (done).
- NISAR GCOV data are PROVISIONAL (not fully validated). Noise floor: roughly 1% of pixels exceed the
  1.5 dB threshold even without a fire.
- We do not claim causes beyond what the data show. Official fire perimeter not included unless
  app/data/perimeter.geojson exists; then add it as an optional dashed red line, otherwise omit the toggle.

## How to work
1. Read the files in app/ and forest_watch_api/scripts first, then make a short plan.
2. Do Step 0, then the Explore mode end to end (map, compare slider, time slider, legend, chart). Test it in a browser.
3. Then Learn mode, then README.md (what it is, how to open, how data were made, limits, data sources).
4. Never invent data or numbers. Missing facts become visible [PLACEHOLDER] text.
5. Keep code simple and commented; ask me before adding libraries or changing the data pipeline.
6. Do not commit or push. Never read or print .env.