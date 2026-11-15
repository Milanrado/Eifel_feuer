/* Eifel Fire Radar: static app, no build step.
 *
 * Everything (dates, numbers, file names) comes from the data folder:
 *   series_meta.js    window.NISAR_SERIES    radar scenes (forest_watch_api/scripts/gcov_change.py)
 *   stable.js         window.NISAR_STABLE    optional, weather-steadied radar layers (scripts/make_stable.py)
 *   damage.js         window.NISAR_DAMAGE    optional, lasting damage area (scripts/make_damage.py)
 *   moisture_meta.js  window.NISAR_MOISTURE  optional, soil moisture scenes (scripts/sme2_layers.py)
 * Nothing in here is hard-coded data.
 */
(function () {
  "use strict";

  // ======================================================================= helpers
  const $ = (id) => document.getElementById(id);
  const MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];
  const dayNum = (d) => Date.UTC(+d.slice(0, 4), +d.slice(5, 7) - 1, +d.slice(8, 10)) / 864e5;
  const fmtDate = (d) => `${+d.slice(8, 10)} ${MONTHS[+d.slice(5, 7) - 1]}`;
  const fmtDateLong = (d) => `${fmtDate(d)} ${d.slice(0, 4)}`;
  // large numbers (hectares of a big fire) get thousands separators and no decimals: 19,401
  const fmtNum = (x, digits = 1) => (x == null ? "n/a"
    : (Math.abs(x) >= 1000 ? Math.round(x).toLocaleString("en-US") : x.toFixed(digits)).replace("-", "−"));
  const esc = (s) => String(s).replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));
  const clamp01 = (x) => Math.min(1, Math.max(0, x));
  const DB_HELP = `Scientists count echo strength in decibels (dB). One rule is enough: 3 dB less means half the echo,
    3 dB more means double.`;

  // ----------------------------------------------------------------------- colour
  // Display palettes (style, not data): dark = low, bright = high.
  const PALETTES = {
    viridis: ["#440154", "#472d7b", "#3b528b", "#2c728e", "#21918c", "#28ae80", "#5ec962", "#addc30", "#fde725"],
    inferno: ["#000004", "#1b0c41", "#4a0c6b", "#781c6d", "#a52c60", "#cf4446", "#ed6925", "#fb9b06", "#f7d13d", "#fcffa4"],
    veg: ["#7a3b0a", "#b8792c", "#e3c878", "#f4f1b5", "#a6d96a", "#3fa34d", "#0b6b2e", "#00441b"],
    change: ["#ffffff", "#fde0dc", "#f7a8a2", "#e5484d", "#b3202c", "#6b0f1a"],   // no change -> strong loss
    moist: ["#8c510a", "#d8b365", "#f6e8c3", "#c7eae5", "#5ab4ac", "#2171b5", "#08306b"],
  };
  const hex2rgb = (h) => [1, 3, 5].map((i) => parseInt(h.slice(i, i + 2), 16) / 255);
  function palColor(stops, u) {
    const x = clamp01(u) * (stops.length - 1);
    const i = Math.min(stops.length - 2, Math.floor(x));
    const a = hex2rgb(stops[i]), b = hex2rgb(stops[i + 1]);
    return a.map((v, k) => v + (b[k] - v) * (x - i));
  }
  const cssRamp = (stops) => `linear-gradient(90deg,${stops.join(",")})`;

  /* The layer PNGs are grey values. They are coloured in the browser with SVG filters: a colour
   * matrix picks the source channel, a lookup table maps it to a colour. Unlike a canvas, this
   * also works when the page is opened from file://. */
  const FILTER_STEPS = 256;
  const madeFilters = new Set();
  let filterDefs = null;
  function newFilter(id, inner) {
    if (!filterDefs) {
      const svg = document.createElementNS("http://www.w3.org/2000/svg", "svg");
      svg.setAttribute("width", "0"); svg.setAttribute("height", "0");
      svg.setAttribute("aria-hidden", "true");
      svg.style.position = "absolute";
      filterDefs = document.createElementNS("http://www.w3.org/2000/svg", "defs");
      svg.appendChild(filterDefs);
      document.body.appendChild(svg);
    }
    const f = document.createElementNS("http://www.w3.org/2000/svg", "filter");
    f.setAttribute("id", id);
    f.setAttribute("color-interpolation-filters", "sRGB");
    f.setAttribute("x", "0"); f.setAttribute("y", "0"); f.setAttribute("width", "100%"); f.setAttribute("height", "100%");
    f.innerHTML = inner;
    filterDefs.appendChild(f);
    madeFilters.add(id);
    return `url(#${id})`;
  }
  /** Plain colour matrix: rows = 3 output channels, each [fromR, fromG, fromB, constant]. */
  function matrixFilter(id, rows) {
    if (madeFilters.has(id)) return `url(#${id})`;
    const v = rows.map((r) => `${r[0].toFixed(3)} ${r[1].toFixed(3)} ${r[2].toFixed(3)} 0 ${r[3].toFixed(3)}`).join(" ");
    return newFilter(id, `<feColorMatrix type="matrix" values="${v} 0 0 0 1 0"/>`);
  }
  /** fn(v) -> [r, g, b, a] for v in 0..1. matrixRow: 5 numbers that compute v from R G B A 1. */
  function tableFilter(id, matrixRow, fn, useAlphaTable) {
    if (madeFilters.has(id)) return `url(#${id})`;
    const t = [[], [], [], []];
    for (let i = 0; i < FILTER_STEPS; i++) {
      const c = fn(i / (FILTER_STEPS - 1));
      for (let k = 0; k < 4; k++) t[k].push((c[k] == null ? 1 : clamp01(c[k])).toFixed(3));
    }
    const row = matrixRow.join(" ");
    const alphaRow = useAlphaTable ? row : "0 0 0 1 0";
    return newFilter(id, `<feColorMatrix type="matrix" values="${row} ${row} ${row} ${alphaRow}"/>
      <feComponentTransfer>
        <feFuncR type="table" tableValues="${t[0].join(" ")}"/>
        <feFuncG type="table" tableValues="${t[1].join(" ")}"/>
        <feFuncB type="table" tableValues="${t[2].join(" ")}"/>
        ${useAlphaTable ? `<feFuncA type="table" tableValues="${t[3].join(" ")}"/>` : ""}
      </feComponentTransfer>`);
  }

  /** Load a classic <script> (works from file://, unlike fetch). */
  function loadScript(src) {
    return new Promise((resolve, reject) => {
      const s = document.createElement("script");
      s.src = src;
      s.onload = resolve;
      s.onerror = () => { s.remove(); reject(new Error("missing " + src)); };
      document.head.appendChild(s);
    });
  }

  // ======================================================================= boot
  /* Every region is one data folder (gcov_change.py series). The data arrive as <script> globals,
   * so each load is captured into the region object right away, before the next region overwrites it. */
  async function boot() {
    const regions = [];
    for (const r of window.REGIONS || []) {
      let dir = null;
      for (const d of r.dirs || []) {
        try {
          window.NISAR_SERIES = null;
          await loadScript(`${d}/series_meta.js`);
          if (window.NISAR_SERIES) { dir = d; break; }
        } catch (e) { /* try the next folder */ }
      }
      if (!dir) continue;                       // region not built yet: simply not offered
      // optional extras: each one simply switches a feature on
      window.NISAR_STABLE = window.NISAR_DAMAGE = window.NISAR_MOISTURE = window.NISAR_VEGETATION = window.NISAR_CARBON = null;
      for (const f of ["stable.js", "damage.js", "moisture_meta.js", "vegetation.js", "carbon.js"]) {
        try { await loadScript(`${dir}/${f}`); } catch (e) { /* not there: fine */ }
      }
      let perimeter = null;                     // fetch() only works over http(s), not from file://
      if (r.perimeter) {
        try {
          const resp = await fetch(r.perimeter);
          if (resp.ok) perimeter = await resp.json();
        } catch (e) { /* no perimeter */ }
      }
      regions.push(Object.assign({}, r, { dir, data: {
        META: window.NISAR_SERIES, STABLE: window.NISAR_STABLE || null, VEG: window.NISAR_VEGETATION || null, CARBON: window.NISAR_CARBON || null,
        DAMAGE: window.NISAR_DAMAGE || null, MOIST: window.NISAR_MOISTURE || null, PERIMETER: perimeter,
      } }));
    }
    if (!regions.length) {
      const box = $("load-error");
      box.innerHTML = "<strong>No data found.</strong> Expected <code>series_meta.js</code> in one of: " +
        esc((window.REGIONS || []).flatMap((r) => r.dirs || []).join(", ")) + ". Run <code>gcov_change.py series</code> first.";
      box.hidden = false;
      return;
    }
    // arrows etc. go to the running instance (regions swap the instance, the listener stays)
    document.addEventListener("keydown", (e) => { if (app && app.onKey) app.onKey(e); });
    const want = (location.hash.match(/r=([\w-]+)/) || [])[1];
    openRegion(regions, regions.find((r) => r.id === want) || regions[0], false);
  }

  let app = null;                               // the running instance: { map, onKey }
  function openRegion(regions, region, setHash) {
    if (app) { app.map.remove(); app = null; }  // tears down the old map and all its listeners
    if (setHash) { try { history.replaceState(null, "", "#r=" + region.id); } catch (e) { /* file:// quirks */ } }
    init(region, regions, (r) => openRegion(regions, r, true));
  }

  // ======================================================================= app
  function init(REGION, REGIONS, switchRegion) {
    const DIR = REGION.dir;
    const RID = REGION.id;
    const { META, DAMAGE, MOIST, PERIMETER, STABLE, VEG, CARBON } = REGION.data;
    const radar = META.scenes;
    const N = radar.length;
    const baseIdx = Math.max(0, radar.findIndex((s) => s.date === META.baseline));
    const base = radar[baseIdx];
    const last = radar[N - 1];
    const [W, S, E, Nn] = META.bbox;
    const bounds = L.latLngBounds([[S, W], [Nn, E]]);
    const DBR = META.db_range;
    const THR = META.threshold_db;
    const fireStart = dayNum(META.fire.start), fireEnd = dayNum(META.fire.end);
    const firstPostIdx = Math.max(0, radar.findIndex((s) => dayNum(s.date) > fireEnd));
    const url = (file) => `${DIR}/${file}`;
    // Dual-pol radar vegetation index from the HH-HV ratio in dB: 4*HV / (HH + HV), linear power.
    const rviOf = (ratioDb) => { const q = Math.pow(10, -ratioDb / 10); return (4 * q) / (1 + q); };

    // Two kinds of scenes, each with its own dates: radar (always) and soil moisture (if exported).
    const moist = MOIST && MOIST.scenes && MOIST.scenes.length ? MOIST : null;
    const SETS = {
      radar: { scenes: radar, bounds },
      moisture: moist ? {
        scenes: moist.scenes,
        bounds: L.latLngBounds([[moist.bbox[1], moist.bbox[0]], [moist.bbox[3], moist.bbox[2]]]),
      } : null,
    };

    /* Radar layers read the steadied images when they exist (red = HH, green = HV, blue = HH - HV): scene-wide
     * wet/dry shifts and one-off flickers are taken out, so forest and buildings do not seem to come and go
     * with the weather. Without them the raw images are used (HV in its own grey file, the rest in the composite). */
    const steady = STABLE && radar.every((s) => STABLE.files[s.date]);
    const radarFile = (s, raw) => (steady ? STABLE.files[s.date] : raw);

    /* band: which PNG channel holds the value (0 = red, 2 = blue), the range it encodes (enc), and the
     * display stretch (range). The stretch is a display choice so the palette is not wasted on empty range.
     * Names say what a layer means; the radar terms (HV, HH, RVI, SME2) are explained under "About". */
    /* Moisture colour stretch: the product range (0 to 0.6 m3/m3) leaves typical summer values in the pale middle
     * of the palette. The display spans the region's scene medians +/- 0.15 instead, inside the product range. */
    const MOIST_STRETCH = moist ? (() => {
      const med = moist.scenes.map((s) => s.median_m3_m3).filter((v) => v != null);
      const r = moist.range;
      if (!med.length) return r;
      const lo = Math.max(r[0], Math.floor((Math.min(...med) - 0.15) * 20) / 20);
      const hi = Math.min(r[1], Math.ceil((Math.max(...med) + 0.15) * 20) / 20);
      return hi - lo >= 0.1 ? [lo, hi] : r;
    })() : null;

    const LAYERS = [
      { id: "forest", set: "radar", name: "Forest", sub: "Where trees stand", file: (s) => radarFile(s, s.hv),
        band: { chan: steady ? 1 : 0, enc: DBR.HV, range: [-22, -8], pal: "viridis" }, lo: "open land", hi: "dense forest",
        text: "The radar pulse bounces between branches and part of it comes back. More trees, stronger echo. Burned or cleared forest turns dark. Trees do not grow in weeks, so the map never shows more forest than before the fire." },
      /* Change: every place against ITSELF before the fire (the forest image of the date shown minus the one of the
       * last date before the fire). Land that was already open stays white instead of looking "burned". */
      { id: "change", set: "radar", change: true, name: "Change", sub: `Forest echo since ${fmtDate(base.date)}`,
        file: (s) => radarFile(s, s.hv),
        band: { range: [-META.diff_range_db, 0], pal: "change" }, lo: "no change", hi: `strong loss (−${META.diff_range_db} dB)`,
        text: `Each place is compared with itself: its forest echo on the date shown against ${fmtDateLong(base.date)}, the last image before the fire. White means unchanged (or stronger), so land that was already open before the fire stays white. The redder, the more of the canopy echo is gone; ${THR} dB less, about ${Math.round((1 - Math.pow(10, -THR / 10)) * 100)} %, is where "loss" starts.` },
      { id: "surface", set: "radar", name: "Ground and buildings", sub: "Hard and rough surfaces", file: (s) => radarFile(s, s.composite),
        band: { chan: 0, enc: DBR.HH, range: [-17, -1], pal: "inferno" }, lo: "smooth ground", hi: "rough ground, buildings",
        text: "Smooth ground mirrors the radar pulse away and stays dark. Walls and rough or wet ground send it back and glow." },
      { id: "vegetation", set: "radar", name: "Vegetation", sub: "How much plant cover", file: (s) => radarFile(s, s.composite),
        // one fixed scale in every region (more contrast than starting at the burned forest, which was tried and dropped);
        // with vegetation.js (scripts/make_vegetation.py) buildings are painted in a neutral grey off the scale
        band: { chan: 2, enc: DBR.ratio, range: [0.2, 1.2], pal: "veg", value: rviOf }, lo: "bare", hi: "lush",
        text: "Compares the echo from plants with the echo from the ground. Green means a lot of woody vegetation, brown means little."
          + (VEG && VEG.buildings ? " Buildings are not on the scale: they are grey." : "") },
      { id: "moisture", set: "moisture", name: "Moisture", sub: "Water in the soil", file: (s) => s.file,
        band: moist ? { chan: 0, enc: moist.range, range: MOIST_STRETCH, pal: "moist" } : null,
        lo: moist ? `dry (${MOIST_STRETCH[0].toFixed(2)})` : "dry", hi: moist ? `wet (${MOIST_STRETCH[1].toFixed(2)} m³/m³)` : "wet",
        text: "How much water the top soil holds. Dry soil and dry plants burn more easily." + (moist && /all valid/.test(moist.quality || "")
          ? " The map also shows values the product does not mark as reliable, mostly under forest, where the satellite sees the trees more than the soil."
          : " Under dense forest the satellite cannot measure it, so there are gaps.") },
      // only used by the Learn tour, not offered as a layer
      { id: "composite", set: "radar", hidden: true, name: "Colour composite", file: (s) => radarFile(s, s.composite) },
    ];
    const layerById = (id) => LAYERS.find((l) => l.id === id);

    const state = {
      mode: "explore",
      layer: "forest",
      idx: N - 1,            // the date shown: index into the scenes of the current layer
      cmp: false,            // compare with a second date
      ref: baseIdx,          // the date to compare with
      swipe: 0.55,           // compare line position, fraction of the map width
      open: window.innerWidth > 760,   // left card expanded (starts closed on phones, where it would hide the map)
      carbonOpen: false,     // right carbon card: details folded in (the number for the date is always shown)
      photosOpen: false,     // wildfire photos card (top-right, when the region has photos)
      step: 0,               // Learn step
      loss: false,           // Learn only: show strong loss instead of the layer
      outline: false,        // Learn only: outline of the lasting damage
    };
    const curSet = () => SETS[layerById(state.layer).set];
    const scenes = () => curSet().scenes;
    const nearest = (list, date) => list.reduce((b, s, i) =>
      (Math.abs(dayNum(s.date) - dayNum(date)) < Math.abs(dayNum(list[b].date) - dayNum(date)) ? i : b), 0);
    const comparing = () => state.cmp && !state.loss && !layerById(state.layer).change && scenes().length > 1;

    // ------------------------------------------------------------------- filters
    /* Colour composite (Learn): HH (red channel) and HV (green channel) are mixed so that three typical
     * surfaces land on three easy colours. The anchors are typical channel values in this area. */
    const COMP_ANCHORS = [[0.86, 0.76], [0.44, 0.31], [1.0, 0.74]];   // forest, fields, buildings: [HH, HV] in 0..1
    const COMP_COLOURS = ["#2e8b3d", "#f2d94e", "#8e3fc4"];           // forest green, fields yellow, buildings purple
    function compositeFilter() {
      const [[h1, v1], [h2, v2], [h3, v3]] = COMP_ANCHORS;
      const det = h1 * (v2 - v3) - h2 * (v1 - v3) + h3 * (v1 - v2);
      const inv = [
        [(v2 - v3) / det, (h3 - h2) / det, (h2 * v3 - h3 * v2) / det],
        [(v3 - v1) / det, (h1 - h3) / det, (h3 * v1 - h1 * v3) / det],
        [(v1 - v2) / det, (h2 - h1) / det, (h1 * v2 - h2 * v1) / det],
      ];
      const cols = COMP_COLOURS.map(hex2rgb);
      return matrixFilter("f-comp-" + RID, [0, 1, 2].map((k) => {
        const m = [0, 1, 2].map((j) => cols[0][k] * inv[0][j] + cols[1][k] * inv[1][j] + cols[2][k] * inv[2][j]);
        return [m[0], m[1], 0, m[2]];
      }));
    }
    function filterFor(layer) {
      if (!layer.band) return compositeFilter();
      const b = layer.band;
      const row = [0, 0, 0, 0, 0]; row[b.chan] = 1;
      return tableFilter(`f-${RID}-${layer.id}`, row, (v) => {
        const x = b.enc[0] + v * (b.enc[1] - b.enc[0]);
        const val = b.value ? b.value(x) : x;
        return palColor(PALETTES[b.pal], (val - b.range[0]) / (b.range[1] - b.range[0]));
      }, false);
    }
    /* Strong loss (Learn): the later forest image at full strength, the inverted earlier one on top at 50 %.
     * That mix is v = 0.5 + (later - earlier) / 2 in grey levels; a table marks drops beyond the threshold. */
    const changeOf = (v) => (v - 0.5) * 2 * (DBR.HV[1] - DBR.HV[0]);
    const lossFilter = () => tableFilter("f-loss-" + RID, [1, 0, 0, 0, 0], (v) => {
      const d = changeOf(v);
      const c = hex2rgb(d <= -2 * THR ? "#7a0019" : "#e5484d");
      return [c[0], c[1], c[2], d <= -THR ? 1 : 0];
    }, true);

    // ------------------------------------------------------------------- map
    const map = L.map("map", { zoomSnap: 0.25, zoomControl: false, minZoom: 5, maxZoom: 18 });
    app = { map, onKey: null };
    L.control.zoom({ position: "bottomright" }).addTo(map);
    L.control.scale({ position: "bottomright", imperial: false, maxWidth: 140 }).addTo(map);   // sits above the zoom buttons
    L.tileLayer("https://tile.openstreetmap.org/{z}/{x}/{y}.png", {
      maxZoom: 19,
      attribution: '© <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors',
    }).addTo(map);
    map.attributionControl.addAttribution("NISAR, NASA/ISRO via ASF DAAC");

    // keep the data clear of the floating cards
    const padding = () => ({
      paddingTopLeft: [state.open && window.innerWidth > 760 ? $("panel").offsetWidth + 32 : 16, 16],
      // the carbon card on the right takes room too, when it is shown and open
      paddingBottomRight: [CARBON && state.mode === "explore" && window.innerWidth > 760 ? 280 + 32 : 16, 130],
    });
    map.fitBounds(bounds, padding());
    // Until the user moves the map (or Learn flies somewhere), keep the whole study area in view when
    // the window size changes. This also repairs a first layout that happened in a hidden or tiny tab.
    let untouched = true;
    map.getContainer().onpointerdown = () => { untouched = false; };
    map.getContainer().onwheel = () => { untouched = false; };
    map.on("resize", () => { if (untouched) map.fitBounds(bounds, padding()); });
    window.addEventListener("load", () => { map.invalidateSize(); if (untouched) map.fitBounds(bounds, padding()); }, { once: true });

    // Two panes: the earlier date below, the later date above; the compare line clips the upper pane.
    map.createPane("beforePane").style.zIndex = 410;
    const afterPane = map.createPane("afterPane");
    afterPane.style.zIndex = 420;
    map.createPane("topPane").style.zIndex = 450;

    const beforeOverlay = L.imageOverlay(url(base.hv), bounds, { pane: "beforePane", opacity: 0.9, alt: "" }).addTo(map);
    const afterOverlay = L.imageOverlay(url(base.hv), bounds, { pane: "afterPane", opacity: 0.9, alt: "" }).addTo(map);

    const [IW, IH] = META.image_size;
    const invert = tableFilter("f-invert-" + RID, [1, 0, 0, 0, 0], (v) => [1 - v, 1 - v, 1 - v], false);
    const lossSvg = document.createElementNS("http://www.w3.org/2000/svg", "svg");
    lossSvg.setAttribute("viewBox", `0 0 ${IW} ${IH}`);
    lossSvg.setAttribute("preserveAspectRatio", "none");
    lossSvg.innerHTML = `<g filter="${lossFilter()}">
        <image href="${url(last.hv)}" width="${IW}" height="${IH}" preserveAspectRatio="none"/>
        <image href="${url(base.hv)}" width="${IW}" height="${IH}" preserveAspectRatio="none" opacity="0.5" filter="${invert}"/>
      </g>`;
    const lossOverlay = L.svgOverlay(lossSvg, bounds, { pane: "afterPane" });

    /* Change layer: same mixing trick as the loss view, on the forest channel of the images the layers use.
     * The table maps the difference to white (no change) ... dark red (diff_range_db or more lost). */
    const FCH = [0, 0, 0, 0, 0]; FCH[steady ? 1 : 0] = 1;
    const invertForest = tableFilter("f-invf-" + RID, FCH, (v) => [1 - v, 1 - v, 1 - v], false);
    const changeFilter = tableFilter("f-change-" + RID, FCH, (v) => {
      const d = changeOf(v);
      return palColor(PALETTES.change, -d / META.diff_range_db);
    }, false);
    const changeSvg = document.createElementNS("http://www.w3.org/2000/svg", "svg");
    changeSvg.setAttribute("viewBox", `0 0 ${IW} ${IH}`);
    changeSvg.setAttribute("preserveAspectRatio", "none");
    changeSvg.innerHTML = `<g filter="${changeFilter}">
        <image class="later" href="${url(radarFile(base, base.hv))}" width="${IW}" height="${IH}" preserveAspectRatio="none"/>
        <image href="${url(radarFile(base, base.hv))}" width="${IW}" height="${IH}" preserveAspectRatio="none" opacity="0.5" filter="${invertForest}"/>
      </g>`;
    changeSvg.style.opacity = "0.9";
    const changeOverlay = L.svgOverlay(changeSvg, bounds, { pane: "afterPane" });
    // open water (vegetation.js): the layer colours mean nothing there, so it is painted blue-grey on every layer
    const waterOverlay = VEG && VEG.water
      ? L.imageOverlay(url(VEG.water), bounds, { pane: "topPane", interactive: false, alt: "" }).addTo(map) : null;
    const buildingsOverlay = VEG && VEG.buildings
      ? L.imageOverlay(url(VEG.buildings), bounds, { pane: "topPane", interactive: false, alt: "" }) : null;
    const outlineOverlay = DAMAGE && DAMAGE.outline
      ? L.imageOverlay(url(DAMAGE.outline), bounds, { pane: "topPane", interactive: false, alt: "" }) : null;

    if (PERIMETER) {
      L.geoJSON(PERIMETER, { pane: "topPane", interactive: false,
        style: { color: "#e5484d", weight: 2, dashArray: "6 4", fill: false } }).addTo(map);
    }

    // ------------------------------------------------------------------- wildfire photos (top-right button & card)
    const hasPhotos = !!(REGION.photos && REGION.photos.items && REGION.photos.items.length);
    const photoCard = $("photo-card");
    if (hasPhotos) {
      const ph = REGION.photos, items = ph.items;
      let pIdx = 0;
      $("photos-count").textContent = items.length;
      photoCard.innerHTML = `
        <div class="photo-card-head">
          <span class="photo-card-title">${esc(ph.title || "Wildfire photos")}</span>
          <span class="photo-card-count"></span>
          <button type="button" class="photo-close" aria-label="Close photos">×</button>
        </div>
        <div class="photo-card-stage">
          <a class="photo-link" target="_blank" rel="noopener" title="Open full size">
            <img class="photo-img" alt=""/>
          </a>
          ${items.length > 1 ? `
            <button type="button" class="photo-nav photo-nav-prev" aria-label="Previous photo">‹</button>
            <button type="button" class="photo-nav photo-nav-next" aria-label="Next photo">›</button>` : ""}
        </div>
        <div class="photo-card-foot">
          <div class="photo-card-meta">
            <p class="photo-card-cap"></p>
            <p class="photo-card-credit" hidden></p>
          </div>
          ${items.length > 1 ? `<div class="dots photo-dots">${items.map(() => "<span></span>").join("")}</div>` : ""}
        </div>`;
      const imgEl = photoCard.querySelector(".photo-img");
      const linkEl = photoCard.querySelector(".photo-link");
      const capEl = photoCard.querySelector(".photo-card-cap");
      const credEl = photoCard.querySelector(".photo-card-credit");
      const cntEl = photoCard.querySelector(".photo-card-count");
      const dotEls = photoCard.querySelectorAll(".photo-dots span");
      const showPhoto = (k) => {
        pIdx = (k + items.length) % items.length;
        const it = items[pIdx];
        imgEl.src = it.src;
        imgEl.alt = it.caption || ph.title || "Wildfire photo";
        linkEl.href = it.src;
        capEl.textContent = it.caption || "";
        credEl.hidden = !it.credit;
        credEl.innerHTML = it.credit
          ? (it.creditUrl ? `Photo: <a href="${esc(it.creditUrl)}" target="_blank" rel="noopener">${esc(it.credit)}</a>` : `Photo: ${esc(it.credit)}`)
          : "";
        cntEl.textContent = items.length > 1 ? `${pIdx + 1} / ${items.length}` : "";
        dotEls.forEach((d, i) => d.classList.toggle("on", i === pIdx));
      };
      if (items.length > 1) {
        photoCard.querySelector(".photo-nav-prev").onclick = () => showPhoto(pIdx - 1);
        photoCard.querySelector(".photo-nav-next").onclick = () => showPhoto(pIdx + 1);
      }
      photoCard.querySelector(".photo-close").onclick = () => { state.photosOpen = false; render(); };
      showPhoto(0);
    } else {
      photoCard.innerHTML = "";
    }
    $("photos-btn").onclick = () => { state.photosOpen = !state.photosOpen; render(); };

    // ------------------------------------------------------------------- compare line
    const swipe = $("swipe");
    const swipeHandle = $("swipe-handle");
    const stage = $("stage");
    function updateClip() {
      if (!comparing()) { afterPane.style.clipPath = ""; return; }
      const x = state.swipe * map.getSize().x;
      const p = map.containerPointToLayerPoint([x, 0]);   // pane coordinates
      const BIG = 1e6;
      afterPane.style.clipPath = `polygon(${p.x}px ${-BIG}px, ${BIG}px ${-BIG}px, ${BIG}px ${BIG}px, ${p.x}px ${BIG}px)`;
      swipe.style.left = `${state.swipe * 100}%`;
      swipeHandle.setAttribute("aria-valuenow", Math.round(state.swipe * 100));
    }
    map.on("move zoom zoomend viewreset resize", updateClip);
    function setSwipe(frac) { state.swipe = Math.min(0.97, Math.max(0.03, frac)); updateClip(); }
    swipeHandle.onpointerdown = (e) => {
      e.preventDefault();
      swipeHandle.setPointerCapture(e.pointerId);
      stage.classList.add("dragging");
      const move = (ev) => { const r = stage.getBoundingClientRect(); setSwipe((ev.clientX - r.left) / r.width); };
      const up = () => {
        stage.classList.remove("dragging");
        swipeHandle.removeEventListener("pointermove", move);
        swipeHandle.removeEventListener("pointerup", up);
        swipeHandle.removeEventListener("pointercancel", up);
      };
      swipeHandle.addEventListener("pointermove", move);
      swipeHandle.addEventListener("pointerup", up);
      swipeHandle.addEventListener("pointercancel", up);
    };
    swipeHandle.onkeydown = (e) => {
      if (e.key !== "ArrowLeft" && e.key !== "ArrowRight") return;
      e.preventDefault();
      e.stopPropagation();
      setSwipe(state.swipe + (e.key === "ArrowLeft" ? -0.05 : 0.05));
    };

    // ------------------------------------------------------------------- region switch (header)
    const regEl = $("regions");
    regEl.hidden = REGIONS.length < 2;
    regEl.innerHTML = REGIONS.map((r) => `<button type="button" aria-pressed="${r.id === RID}"
        title="${esc(r.title || r.name)}">${esc(r.name)}</button>`).join("");
    regEl.querySelectorAll("button").forEach((b, i) => {
      b.onclick = () => { if (REGIONS[i].id !== RID) switchRegion(REGIONS[i]); };
    });

    // ------------------------------------------------------------------- left card
    $("panel-toggle").onclick = () => { state.open = !state.open; render(); };
    $("carbon-toggle").onclick = () => { state.carbonOpen = !state.carbonOpen; render(); };
    $("layers").onclick = (e) => {
      const b = e.target.closest(".layer");
      if (b && !b.disabled) setLayer(b.dataset.id);
    };
    /** Switch layer. Layers with other dates (moisture) keep the nearest date. */
    function setLayer(id) {
      const old = scenes();
      const dShown = old[state.idx].date, dRef = old[state.ref] ? old[state.ref].date : META.baseline;
      state.layer = id;
      const now = scenes();
      if (now !== old) {
        state.idx = nearest(now, dShown);
        state.ref = nearest(now, dRef);
        buildStops();
      }
      render();
    }
    let panelKey = "";
    function renderPanel() {
      const layer = layerById(state.layer);
      const learn = state.mode === "learn";
      $("panel").classList.toggle("is-learn", learn);
      $("panel-toggle").setAttribute("aria-expanded", String(state.open));
      $("panel-title").textContent = learn ? `Learn · ${state.step + 1} of ${STEPS.length}` : "Layers";
      $("panel-mini").innerHTML = learn || !layer.band ? ""
        : `<i style="background:${cssRamp(PALETTES[layer.band.pal])}"></i>${esc(layer.name)}`;
      $("layers").hidden = learn;
      $("carbon-card").hidden = learn || !CARBON;
      $("learn").hidden = !learn;
      if (learn || panelKey === state.layer) return;      // rebuild the list only when the choice changed
      panelKey = state.layer;
      $("layers").innerHTML = LAYERS.filter((l) => !l.hidden).map((l) => {
        const ok = !!SETS[l.set], sel = l.id === state.layer;
        return `<button type="button" class="layer" role="radio" aria-checked="${sel}" data-id="${l.id}" ${ok ? "" : "disabled"}>
            <span class="layer-dot"></span><span class="layer-name">${esc(l.name)}</span>
            <span class="layer-sub">${ok ? esc(l.sub) : "No data yet"}</span>
          </button>` + (sel ? `<div class="layer-detail">
            <div class="ramp" style="background:${cssRamp(PALETTES[l.band.pal])}"></div>
            <div class="ramp-labels"><span>${esc(l.lo)}</span><span>${esc(l.hi)}</span></div>
            ${l.id === "vegetation" && buildingsOverlay ? `<div class="key"><i style="background:${VEG.buildings_colour}"></i>Buildings, not on the scale</div>` : ""}
            ${waterOverlay ? `<div class="key"><i style="background:${VEG.water_colour}"></i>Water, not on the scale</div>` : ""}
            <p>${esc(l.text)}</p>
          </div>` : "");
      }).join("");
    }

    // ------------------------------------------------------------------- compare: one button, one date
    $("cmp-btn").onclick = () => { state.cmp = !state.cmp; render(); };
    $("cmp-date").onchange = (e) => { state.ref = +e.target.value; render(); };

    // ------------------------------------------------------------------- time line
    const allDates = radar.concat(moist ? moist.scenes : []).map((s) => dayNum(s.date));
    const t0 = Math.min(...allDates);
    const span = Math.max(1, Math.max(...allDates) - t0);
    const pos = (date) => ((dayNum(date) - t0) / span) * 100;   // % along the line, true time spacing
    const timeline = $("timeline");
    const handle = $("tl-handle");
    const stopsEl = $("tl-stops");
    const fireL = pos(META.fire.start);
    const fireR = ((fireEnd + 1 - t0) / span) * 100;            // the end day is included
    $("tl-fire").style.left = `${fireL}%`;
    $("tl-fire").style.width = `${Math.max(0.6, fireR - fireL)}%`;
    $("tl-fire-label").textContent = "Fire";

    function buildStops() {
      const list = scenes();
      stopsEl.innerHTML = list.map((s, i) => `
        <button type="button" class="tl-stop" data-i="${i}" style="left:${pos(s.date)}%" aria-label="${fmtDateLong(s.date)}">
          <span>${fmtDate(s.date)}</span>
        </button>`).join("");
      handle.setAttribute("aria-valuemax", list.length - 1);
      $("cmp-date").innerHTML = list.map((s, i) => `<option value="${i}">${fmtDate(s.date)}</option>`).join("");
    }
    function nearestIdx(clientX) {
      const r = timeline.getBoundingClientRect();
      const pct = ((clientX - r.left) / r.width) * 100;
      let best = -1;
      scenes().forEach((s, i) => {
        if (comparing() && i === state.ref) return;          // the shown date never sits on the compared one
        if (best < 0 || Math.abs(pos(s.date) - pct) < Math.abs(pos(scenes()[best].date) - pct)) best = i;
      });
      return best;
    }
    /** Move the shown date. dir (+1 / -1) lets it step over the date it is compared with. */
    function setDate(i, dir) {
      const n = scenes().length;
      i = Math.min(n - 1, Math.max(0, i));
      if (comparing() && i === state.ref) {
        i += dir || 0;
        if (!dir || i < 0 || i > n - 1) return;
      }
      if (i === state.idx) return;
      state.idx = i;
      render();
    }
    timeline.onpointerdown = (e) => {
      if (e.button !== 0) return;
      e.preventDefault();
      timeline.setPointerCapture(e.pointerId);
      timeline.classList.add("dragging");
      setDate(nearestIdx(e.clientX));
      handle.focus({ preventScroll: true });
      const move = (ev) => setDate(nearestIdx(ev.clientX));   // magnetic: always the nearest date
      const up = () => {
        timeline.classList.remove("dragging");
        timeline.removeEventListener("pointermove", move);
        timeline.removeEventListener("pointerup", up);
        timeline.removeEventListener("pointercancel", up);
      };
      timeline.addEventListener("pointermove", move);
      timeline.addEventListener("pointerup", up);
      timeline.addEventListener("pointercancel", up);
    };
    stopsEl.onclick = (e) => {                                  // keyboard: Tab + Enter on a date
      const b = e.target.closest(".tl-stop");
      if (b && e.detail === 0) setDate(+b.dataset.i);
    };

    // ------------------------------------------------------------------- render
    const phaseText = (s) => (dayNum(s.date) < fireStart ? "before the fire" : dayNum(s.date) > fireEnd ? "after the fire" : "during the fire");
    function render() {
      const list = scenes(), set = curSet(), layer = layerById(state.layer);
      if (state.cmp && list.length > 1 && state.ref === state.idx) {      // a comparison needs two different dates
        state.ref = state.idx > 0 ? state.idx - 1 : 1;
      }
      const pair = comparing();
      const fi = Math.min(state.idx, state.ref), ti = Math.max(state.idx, state.ref);
      const cur = list[state.idx];
      const F = pair ? list[fi] : null, T = pair ? list[ti] : cur;

      // map: the shown date; while comparing: earlier date left of the line, later date right of it
      if (state.loss) {
        afterOverlay.remove(); changeOverlay.remove();
        if (!map.hasLayer(lossOverlay)) lossOverlay.addTo(map);
      } else if (layer.change) {
        afterOverlay.remove(); lossOverlay.remove();
        changeSvg.querySelector(".later").setAttribute("href", url(layer.file(cur)));
        if (!map.hasLayer(changeOverlay)) changeOverlay.addTo(map);
      } else {
        lossOverlay.remove(); changeOverlay.remove();
        if (!map.hasLayer(afterOverlay)) afterOverlay.addTo(map);
        afterOverlay.setBounds(set.bounds);
        afterOverlay.setUrl(url(layer.file(T)));
        afterOverlay.getElement().style.filter = filterFor(layer);
      }
      if (pair) {
        beforeOverlay.setBounds(set.bounds);
        beforeOverlay.setUrl(url(layer.file(F)));
        beforeOverlay.getElement().style.filter = filterFor(layer);
        $("swipe-l").textContent = fmtDate(F.date);
        $("swipe-r").textContent = fmtDate(T.date);
      }
      map.getPane("beforePane").style.display = pair ? "" : "none";
      swipe.hidden = !pair;
      updateClip();
      if (outlineOverlay) {
        if (state.outline) outlineOverlay.addTo(map); else outlineOverlay.remove();
      }
      if (buildingsOverlay) {
        if (layer.id === "vegetation" && !state.loss) buildingsOverlay.addTo(map); else buildingsOverlay.remove();
      }

      renderPanel();

      // compare & photos controls (top-right)
      const canCmp = state.mode !== "learn" && list.length >= 2 && !layer.change;
      $("compare").hidden = !hasPhotos && !canCmp;
      $("photos-btn").hidden = !hasPhotos;
      $("photos-btn").setAttribute("aria-pressed", String(hasPhotos && state.photosOpen));
      photoCard.hidden = !(hasPhotos && state.photosOpen);
      $("cmp-btn").hidden = !canCmp;
      $("cmp-btn").setAttribute("aria-pressed", String(state.cmp));
      $("cmp-with").hidden = !(canCmp && state.cmp);
      const sel = $("cmp-date");
      Array.from(sel.options).forEach((o, i) => { o.disabled = i === state.idx; });
      sel.value = state.ref;

      // time
      $("now-date").textContent = fmtDateLong(cur.date);
      $("now-note").textContent = phaseText(cur) + (pair ? ` · compared with ${fmtDate(list[state.ref].date)}` : "");
      handle.style.left = `${pos(cur.date)}%`;
      handle.setAttribute("aria-valuenow", state.idx);
      handle.setAttribute("aria-valuetext", fmtDateLong(cur.date));
      $("tl-ref").hidden = !pair;
      if (pair) $("tl-ref").style.left = `${pos(list[state.ref].date)}%`;
      if (CARBON) renderCarbon();
      stopsEl.querySelectorAll(".tl-stop").forEach((b, i) => {
        b.classList.toggle("is-sel", i === state.idx);
        b.classList.toggle("is-ref", pair && i === state.ref);
      });
    }

    // ------------------------------------------------------------------- damaged area (Learn + About)
    /* Lasting damage from scripts/make_damage.py: where the forest echo stayed low in almost every image
     * after the fire. "Normal" is the area's average echo in the images before the fire. */
    const AREA = DAMAGE ? {
      ha: DAMAGE.area_ha,
      mean: radar.map((s) => DAMAGE.mean_hv_db[s.date]),
      bounds: L.latLngBounds([[DAMAGE.bbox[1], DAMAGE.bbox[0]], [DAMAGE.bbox[3], DAMAGE.bbox[2]]]),
      // the compare line goes through the largest damaged patch (with many patches the bbox centre can be off the burn)
      focus: DAMAGE.patches && DAMAGE.patches.length ? L.latLng(DAMAGE.patches[0].center)
        : L.latLngBounds([[DAMAGE.bbox[1], DAMAGE.bbox[0]], [DAMAGE.bbox[3], DAMAGE.bbox[2]]]).getCenter(),
    } : null;
    const preIdx = radar.map((s, i) => i).filter((i) => dayNum(radar[i].date) < fireStart);
    const areaPre = AREA && preIdx.length ? preIdx.reduce((a, i) => a + AREA.mean[i], 0) / preIdx.length : null;
    const areaPct = (i) => Math.round(Math.pow(10, (AREA.mean[i] - areaPre) / 10) * 100);
    const dropIdx = AREA ? AREA.mean.findIndex((v, i) => i > baseIdx && v < areaPre - THR) : -1;
    const lossPct = (db) => Math.round((1 - Math.pow(10, -db / 10)) * 100);
    const PITCH_HA = 0.714;                    // one football pitch, 105 m x 68 m

    // ------------------------------------------------------------------- carbon (Explore card, carbon.js)
    /* Stock from NASA GEDI L4B biomass, converted with IPCC factors (scripts/make_carbon.py). The fire part uses
     * the NISAR damage area: what stood there, and the yearly uptake that is missing until the forest regrows.
     * The recovery bars are measured: the canopy echo of the damaged area per radar date, in % of before the fire. */
    const fmtCO2 = (t) => (t >= 1e6 ? `${(t / 1e6).toFixed(1)} Mt` : t >= 1e4 ? `${Math.round(t / 1e3).toLocaleString("en-US")} kt`
      : `${Math.round(t).toLocaleString("en-US")} t`);
    function renderCarbon() {
      const el = $("carbon"), now = $("carbon-now");
      if (!CARBON) { el.innerHTML = now.innerHTML = ""; return; }
      const b = CARBON.box, d = CARBON.damaged, by = CARBON.by_date || {};
      const list = scenes();
      // radar date for a shown date (moisture has its own dates: take the nearest radar date)
      const rIdx = (i) => (list === radar ? i : nearest(radar, list[i].date));
      const ri = rIdx(state.idx), rd = radar[ri];
      const at = (r) => by[radar[r].date] || { co2_t: 0, loss_ha: 0 };
      const signed = (t) => `${t < 0 ? "−" : "+"}${fmtCO2(Math.abs(t))}`;
      const near = list === radar || list[state.idx].date === rd.date ? "" : ` (nearest radar image)`;

      // ---- visible: only the number for the shown date, or the change between the two compared dates.
      // What it means (date, hectares) is the first thing in the details.
      let what;
      if (comparing()) {
        const rF = rIdx(Math.min(state.idx, state.ref)), rT = rIdx(Math.max(state.idx, state.ref));
        const dIntact = -(at(rT).co2_t - at(rF).co2_t), dHa = at(rT).loss_ha - at(rF).loss_ha;
        now.innerHTML = `<p class="c-big ${dIntact < 0 ? "loss" : ""}">${signed(dIntact)} CO₂</p>`;
        what = `<p class="c-lead">Change in forest with an intact canopy, ${fmtDate(radar[rF].date)} → ${fmtDate(radar[rT].date)}:
          ${dHa >= 0 ? "+" : "−"}${fmtNum(Math.abs(dHa))} ha where the canopy echo dropped.</p>`;
      } else {
        const lost = at(ri);
        now.innerHTML = `<p class="c-big">${fmtCO2(b.co2_t - lost.co2_t)} CO₂</p>`;
        what = `<p class="c-lead">In forest with an intact canopy on ${fmtDate(rd.date)}${near}.
          ${rd.date === CARBON.baseline ? "This is the last image before the fire, the reference."
            : `<span class="${lost.co2_t > 0 ? "loss" : ""}">${signed(-lost.co2_t)} since ${fmtDate(CARBON.baseline)}, ${fmtNum(lost.loss_ha)} ha with canopy loss.</span>`}</p>`;
      }

      // ---- details (folded): what the number means, the totals, lost uptake, recovery, sources
      $("carbon-toggle").setAttribute("aria-expanded", String(state.carbonOpen));
      $("carbon-more").textContent = state.carbonOpen ? "Less" : "Details";
      let rec = "";
      if (d && AREA) {
        rec = dayNum(rd.date) <= fireEnd
          ? `<p class="c-note">${fmtDate(rd.date)} is before the fire${dayNum(rd.date) >= fireStart ? " ends" : ""}. Move the date to see the recovery.</p>`
          : `<p class="c-note"><strong>${areaPct(ri)} %</strong> of the canopy echo before the fire on ${fmtDate(rd.date)}. 100 % means the tree crowns are back, not yet the biomass.</p>`;
      }
      el.innerHTML = `${what}
        <p class="c-note">The number above is the CO₂ stored in all trees of this area (NASA GEDI biomass) minus the CO₂ stored
          where the Change layer is red on that date: the canopy echo dropped more than ${THR} dB since ${fmtDate(CARBON.baseline)}.
          It is the stock standing there, not the emission: only part of it burns.</p>
        <div class="c-row"><span class="c-mid">${fmtCO2(b.co2_t)} CO₂</span>
          <span class="c-sub">in all trees of this area before the fire (± ${fmtCO2(b.co2_se_t)}), ${fmtNum(b.mean_agbd_t_ha)} t biomass per ha</span></div>
        ${d ? `<div class="c-row"><span class="c-mid">${fmtCO2(d.co2_t)} CO₂</span>
          <span class="c-sub">in the lasting damage area (${fmtNum(d.area_ha)} ha, low in almost every image after the fire)</span></div>
        <div class="c-row"><span class="c-mid">≈ ${fmtCO2(d.lost_uptake_co2_t_yr)} CO₂ / year</span>
          <span class="c-sub">no longer taken up there until the forest grows back</span></div>
        ${REGION.damageCaveat ? `<p class="c-note c-warn">${esc(REGION.damageCaveat)}</p>` : ""}
        <p class="c-label">Recovery: canopy echo of the damaged area, % of normal</p>
        ${AREA ? areaBars(ri) : ""}${rec}` : ""}
        <p class="c-src">Biomass: NASA GEDI (1 km, before 2026). Factors: IPCC. More under About.</p>`;
    }

    /** Bars: echo of the damaged area per date, in % of normal. */
    function areaBars(cur) {
      const w = 300, h = 128, mt = 18, mb = 20, top = 140;
      const x = (d) => 16 + (pos(d) / 100) * (w - 32);
      const y = (pc) => mt + (1 - Math.min(pc, top) / top) * (h - mt - mb);
      const fx0 = x(META.fire.start), fx1 = 16 + (fireR / 100) * (w - 32);
      const labelled = new Set([0, N - 1, cur]);
      return `<svg class="bars" viewBox="0 0 ${w} ${h}" role="img" aria-label="Radar echo of the damaged area in percent of normal: ${
          radar.map((s, i) => `${fmtDate(s.date)} ${areaPct(i)} %`).join(", ")}">
        <rect x="${fx0}" y="${mt}" width="${Math.max(2, fx1 - fx0)}" height="${h - mt - mb}" fill="#e5484d" fill-opacity="0.16"/>
        <text x="${(fx0 + fx1) / 2}" y="${mt - 6}" text-anchor="middle" style="fill:#e5484d;font-weight:700">fire</text>
        <line x1="0" x2="${w}" y1="${y(100)}" y2="${y(100)}" stroke="#9ca3af" stroke-dasharray="4 3"/>
        <text x="${w}" y="${y(100) - 4}" text-anchor="end">100 % = normal</text>
        ${radar.map((s, i) => { const pc = areaPct(i); return `
          <rect x="${x(s.date) - 7}" y="${y(pc)}" width="14" height="${h - mb - y(pc)}" rx="2" fill="${i === cur ? "#e5484d" : "#111827"}"/>
          <text x="${x(s.date)}" y="${y(pc) - 3}" text-anchor="middle" style="${i === cur ? "fill:#e5484d;font-weight:700" : ""}">${pc}</text>
          ${labelled.has(i) ? `<text x="${x(s.date)}" y="${h - 6}" text-anchor="${i === 0 ? "start" : i === N - 1 ? "end" : "middle"}">${fmtDate(s.date)}</text>` : ""}`; }).join("")}
      </svg>`;
    }

    // ------------------------------------------------------------------- learn mode
    const timeUTC = (base.time || "").slice(11, 16);
    // local time in the study areas is UTC+2 in summer: before 12 UTC reads as morning
    const daylight = +timeUTC.slice(0, 2) < 12 ? "before or around sunrise" : "in the evening";
    const SVG_RADAR = `
      <svg viewBox="0 0 300 150" role="img" aria-label="The NISAR satellite sends radio pulses through clouds and smoke to the forest and receives the echo">
        <rect x="18" y="12" width="26" height="14" fill="#111827"/><rect x="2" y="16" width="14" height="6" fill="#6b7280"/><rect x="46" y="16" width="14" height="6" fill="#6b7280"/>
        <text x="66" y="24" font-size="10" fill="#111827">NISAR satellite</text>
        <path d="M40 30 L190 112" stroke="#111827" stroke-width="1.5" stroke-dasharray="6 4"/>
        <path d="M200 106 L56 30" stroke="#e5484d" stroke-width="1.5" marker-end="url(#ah)"/>
        <defs><marker id="ah" viewBox="0 0 10 10" refX="8" refY="5" markerWidth="7" markerHeight="7" orient="auto"><path d="M0 0 L10 5 L0 10z" fill="#e5484d"/></marker></defs>
        <ellipse cx="120" cy="66" rx="40" ry="12" fill="#d1d5db"/><ellipse cx="140" cy="60" rx="26" ry="10" fill="#d1d5db"/>
        <text x="96" y="70" font-size="10" fill="#111827">clouds, smoke</text>
        <path d="M0 140 H300" stroke="#111827"/>
        ${[170, 190, 210, 230, 250].map((x) => `<path d="M${x} 140 V124" stroke="#111827"/><polygon points="${x - 9},126 ${x},104 ${x + 9},126" fill="#6b7280"/>`).join("")}
        <text x="64" y="104" font-size="10" fill="#e5484d">echo</text>
        <text x="122" y="102" font-size="10" fill="#111827" transform="rotate(29 122 102)">pulse</text>
      </svg>`;
    const SVG_HH = `
      <svg viewBox="0 0 300 130" role="img" aria-label="HH: smooth surfaces reflect the pulse away, buildings send it back">
        <defs>
          <marker id="ah-hh-b" viewBox="0 0 10 10" refX="8" refY="5" markerWidth="6" markerHeight="6" orient="auto"><path d="M0 0 L10 5 L0 10z" fill="#111827"/></marker>
          <marker id="ah-hh-r" viewBox="0 0 10 10" refX="8" refY="5" markerWidth="6" markerHeight="6" orient="auto"><path d="M0 0 L10 5 L0 10z" fill="#e5484d"/></marker>
        </defs>
        <path d="M0 110 H300" stroke="#111827"/>
        <text x="10" y="18" font-size="10">smooth field: mirrored away</text>
        <path d="M20 30 L70 110 L120 30" fill="none" stroke="#111827" stroke-width="1.5" marker-end="url(#ah-hh-b)"/>
        <text x="170" y="18" font-size="10">building: corner bounce</text>
        <rect x="230" y="60" width="40" height="50" fill="#d1d5db" stroke="#111827"/>
        <path d="M152 40 L222 110" fill="none" stroke="#111827" stroke-width="1.5"/>
        <path d="M222 110 L230 102 L160 32" fill="none" stroke="#e5484d" stroke-width="1.5" marker-end="url(#ah-hh-r)"/>
        <text x="186" y="42" font-size="10" fill="#e5484d">strong echo</text>
      </svg>`;
    const SVG_HV = `
      <svg viewBox="0 0 300 140" role="img" aria-label="HV: inside a tree crown the wave bounces many times and comes back twisted upright">
        <defs>
          <marker id="ah-hv-b" viewBox="0 0 10 10" refX="8" refY="5" markerWidth="6" markerHeight="6" orient="auto"><path d="M0 0 L10 5 L0 10z" fill="#111827"/></marker>
          <marker id="ah-hv-r" viewBox="0 0 10 10" refX="8" refY="5" markerWidth="6" markerHeight="6" orient="auto"><path d="M0 0 L10 5 L0 10z" fill="#e5484d"/></marker>
        </defs>
        <path d="M0 128 H300" stroke="#111827"/>
        <path d="M150 128 V84" stroke="#111827" stroke-width="3"/>
        <circle cx="150" cy="64" r="40" fill="#fff" stroke="#111827"/>
        <path d="M130 50 L162 70 L138 82 L168 52" fill="none" stroke="#111827"/>
        <path d="M40 16 L130 50" stroke="#111827" stroke-width="1.5" marker-end="url(#ah-hv-b)"/>
        <path d="M168 52 L262 16" stroke="#e5484d" stroke-width="1.5" marker-end="url(#ah-hv-r)"/>
        <text x="20" y="34" font-size="10">sent: H</text>
        <path d="M30 40 h18" stroke="#111827" stroke-width="2"/>
        <text x="236" y="40" font-size="10" fill="#e5484d">back: V</text>
        <path d="M228 30 v18" stroke="#e5484d" stroke-width="2"/>
        <text x="196" y="108" font-size="10">many bounces in</text>
        <text x="196" y="120" font-size="10">branches and leaves</text>
      </svg>`;
    const SVG_RVI = `
      <svg viewBox="0 0 300 106" role="img" aria-label="Vegetation index compares crown echo HV against total echo: high share gives green, low share gives brown">
        <line x1="150" x2="150" y1="10" y2="96" stroke="#d1d5db"/>
        <text x="75" y="18" font-size="10" fill="#111827" text-anchor="middle">forest: lots of crown echo</text>
        <rect x="15" y="28" width="78" height="16" fill="#3fa34d" stroke="#111827"/>
        <rect x="93" y="28" width="42" height="16" fill="#d1d5db" stroke="#111827"/>
        <text x="54" y="40" font-size="9.5" fill="#fff" font-weight="700" text-anchor="middle">HV</text>
        <text x="114" y="40" font-size="9.5" fill="#111827" text-anchor="middle">HH</text>
        <text x="75" y="58" font-size="9.5" fill="#6b7280" text-anchor="middle">crowns dominate</text>
        <rect x="25" y="70" width="100" height="22" rx="6" fill="#3fa34d"/>
        <text x="75" y="85" font-size="10" fill="#fff" font-weight="700" text-anchor="middle">high → green</text>
        <text x="225" y="18" font-size="10" fill="#111827" text-anchor="middle">bare / burned: little crown</text>
        <rect x="165" y="28" width="18" height="16" fill="#3fa34d" stroke="#111827"/>
        <rect x="183" y="28" width="102" height="16" fill="#d1d5db" stroke="#111827"/>
        <text x="234" y="40" font-size="9.5" fill="#111827" text-anchor="middle">HH</text>
        <text x="225" y="58" font-size="9.5" fill="#6b7280" text-anchor="middle">ground dominates</text>
        <rect x="175" y="70" width="100" height="22" rx="6" fill="#7a3b0a"/>
        <text x="225" y="85" font-size="10" fill="#fff" font-weight="700" text-anchor="middle">low → brown</text>
      </svg>`;
    const SVG_MOIST = `
      <svg viewBox="0 0 300 112" role="img" aria-label="Over open fields radar reads topsoil moisture clearly; over dense forest tree crowns get in the way">
        <defs>
          <marker id="ah-m-b" viewBox="0 0 10 10" refX="8" refY="5" markerWidth="6" markerHeight="6" orient="auto"><path d="M0 0 L10 5 L0 10z" fill="#111827"/></marker>
          <marker id="ah-m-bl" viewBox="0 0 10 10" refX="8" refY="5" markerWidth="6" markerHeight="6" orient="auto"><path d="M0 0 L10 5 L0 10z" fill="#2171b5"/></marker>
          <marker id="ah-m-r" viewBox="0 0 10 10" refX="8" refY="5" markerWidth="6" markerHeight="6" orient="auto"><path d="M0 0 L10 5 L0 10z" fill="#e5484d"/></marker>
        </defs>
        <line x1="150" x2="150" y1="10" y2="102" stroke="#d1d5db"/>
        <text x="75" y="18" font-size="10" fill="#111827" text-anchor="middle">open field: reaches soil</text>
        <rect x="20" y="84" width="110" height="8" fill="#8c510a" opacity="0.25"/>
        <path d="M20 84 H130" stroke="#111827"/>
        <path d="M32 30 L73 82" fill="none" stroke="#111827" stroke-width="1.5" marker-end="url(#ah-m-b)"/>
        <path d="M77 82 L118 30" fill="none" stroke="#2171b5" stroke-width="1.5" marker-end="url(#ah-m-bl)"/>
        <text x="75" y="105" font-size="9.5" fill="#2171b5" font-weight="700" text-anchor="middle">clear soil reading</text>
        <text x="225" y="18" font-size="10" fill="#111827" text-anchor="middle">forest: crowns in the way</text>
        <rect x="170" y="84" width="110" height="8" fill="#8c510a" opacity="0.25"/>
        <path d="M170 84 H280" stroke="#111827"/>
        <path d="M225 84 V66" stroke="#111827" stroke-width="3"/>
        <circle cx="225" cy="54" r="20" fill="#fff" stroke="#111827"/>
        <path d="M172 34 L204 51" fill="none" stroke="#111827" stroke-width="1.5" marker-end="url(#ah-m-b)"/>
        <path d="M204 51 L182 26" fill="none" stroke="#e5484d" stroke-width="1.5" marker-end="url(#ah-m-r)"/>
        <text x="225" y="105" font-size="9.5" fill="#e5484d" font-weight="700" text-anchor="middle">trees block soil view</text>
      </svg>`;
    const SVG_CHANGE = `
      <svg viewBox="0 0 300 112" role="img" aria-label="Change compares each spot to itself before the fire: open fields stay white, burned forest turns red">
        <defs>
          <marker id="ah-ch" viewBox="0 0 10 10" refX="8" refY="5" markerWidth="6" markerHeight="6" orient="auto"><path d="M0 0 L10 5 L0 10z" fill="#6b7280"/></marker>
        </defs>
        <line x1="150" x2="150" y1="10" y2="102" stroke="#d1d5db"/>
        <text x="75" y="18" font-size="10" fill="#111827" text-anchor="middle">open field: always low</text>
        <rect x="22" y="30" width="36" height="18" rx="3" fill="#440154" stroke="#111827"/>
        <path d="M64 39 H86" fill="none" stroke="#6b7280" stroke-width="1.5" marker-end="url(#ah-ch)"/>
        <rect x="92" y="30" width="36" height="18" rx="3" fill="#440154" stroke="#111827"/>
        <text x="40" y="60" font-size="9" fill="#6b7280" text-anchor="middle">before</text>
        <text x="110" y="60" font-size="9" fill="#6b7280" text-anchor="middle">after</text>
        <rect x="20" y="72" width="110" height="22" rx="6" fill="#fff" stroke="#111827"/>
        <text x="75" y="87" font-size="10" fill="#111827" font-weight="700" text-anchor="middle">no change → white</text>
        <text x="225" y="18" font-size="10" fill="#111827" text-anchor="middle">burned forest: echo drops</text>
        <rect x="172" y="30" width="36" height="18" rx="3" fill="#5ec962" stroke="#111827"/>
        <path d="M214 39 H236" fill="none" stroke="#6b7280" stroke-width="1.5" marker-end="url(#ah-ch)"/>
        <rect x="242" y="30" width="36" height="18" rx="3" fill="#440154" stroke="#111827"/>
        <text x="190" y="60" font-size="9" fill="#6b7280" text-anchor="middle">before</text>
        <text x="260" y="60" font-size="9" fill="#6b7280" text-anchor="middle">after</text>
        <rect x="170" y="72" width="110" height="22" rx="6" fill="#e5484d"/>
        <text x="225" y="87" font-size="10" fill="#fff" font-weight="700" text-anchor="middle">canopy loss → red</text>
      </svg>`;

    const fitAll = () => { untouched = true; map.flyToBounds(bounds, Object.assign({ duration: 0.6 }, padding())); };
    /** Fly to the damaged area; optionally put the compare line through its middle afterwards. */
    function flyArea(pad, centreLine) {
      if (!AREA) { fitAll(); return; }
      untouched = false;
      if (centreLine) {
        map.once("moveend", () => setSwipe(map.latLngToContainerPoint(AREA.focus).x / map.getSize().x));
      }
      // never fly further out than the data: a large damaged area would otherwise show half the country
      const t = AREA.bounds.pad(pad);
      const target = L.latLngBounds([[Math.max(t.getSouth(), S), Math.max(t.getWest(), W)],
                                     [Math.min(t.getNorth(), Nn), Math.min(t.getEast(), E)]]);
      map.flyToBounds(target, Object.assign({ duration: 0.8 }, padding()));
    }
    /** Learn steps set the whole map state; anything not named falls back to a plain single-date view. */
    function show(patch) {
      const before = scenes();
      Object.assign(state, { cmp: false, loss: false, outline: false }, patch);
      if (scenes() !== before) buildStops();
      render();
    }

    const STEPS = [
      {
        title: "How the satellite sees",
        body: `<p>Regular satellites work like a phone camera: they need sunlight, and clouds or
            wildfire smoke block their view.</p>
          <p>The <strong>NISAR</strong> satellite works more like a bat using echoes. It beams invisible
            radio pulses down to Earth and listens for what bounces back—even in the dark. Each wave is
            about the length of a ruler (24 cm), so it glides right past tiny smoke and cloud particles
            to reach the trees below.</p>
          <p>All ${N} snapshots come from the exact same spot in orbit (around ${esc(timeUTC)} UTC,
            ${daylight}) for a fair before-and-after comparison.</p>`,
        svg: SVG_RADAR,
        hint: `<p>This <b>HV</b> image from ${fmtDateLong(base.date)} (right before the fire) shows
          <b>twisted echoes</b>.</p>
          <p>The satellite sends a sideways wave (<b>H</b>) and listens for echoes bounced back
          upright (<b>V</b>). Only tangled tree crowns scramble the wave enough to do this—so
          <b>green to yellow</b> is forest and <b>dark purple</b> is open ground (more in Step 2).</p>`,
        apply() { show({ layer: "forest", idx: baseIdx }); fitAll(); },
      },
      {
        title: "HV: the tree-crown detector",
        body: `<p>Remember <strong>HV</strong> from Step 1—sending a sideways wave (<strong>H</strong>)
            and listening for echoes twisted upright (<strong>V</strong>)?</p>
          <p>Flat ground and walls bounce waves cleanly without twisting them. Inside a tree crown,
            though, the wave pinballs off branches and leaves pointing in every direction, scrambling
            some of the echo upright.</p>
          <p>That turns <strong>HV</strong> into a <strong>3D canopy detector</strong>. When a wildfire
            burns away the branches and foliage, less stays behind to twist the wave—so the
            <strong>HV</strong> echo drops. In Explore this is the layer "Forest".</p>`,
        svg: SVG_HV,
        hint: `<p>This is the same <b>HV</b> view from ${fmtDateLong(base.date)} (before the fire).</p>
          <p><b>Green to yellow patches</b> are dense forest crowns scrambling lots of signal back.
          <b>Dark purple blocks</b> are flat fields and meadows with no tangled branches to twist the wave.</p>`,
        apply() { show({ layer: "forest", idx: baseIdx }); fitAll(); },
      },
      {
        title: "HH: the surface echo",
        body: `<p>Unlike <strong>HV</strong> (twisted echoes), <strong>HH</strong> listens for echoes
            that come back the same way they were sent—sideways (<strong>H</strong> sent,
            <strong>H</strong> received). That makes it sensitive to solid surfaces.</p>
          <p><strong>Smooth ground</strong> acts like a mirror on the floor: a radar beam hitting it
            at an angle glances away into space, so flat fields send little back.</p>
          <p><strong>Buildings</strong> act like a bicycle reflector: the beam bounces off the ground
            into a wall and shoots straight back to the satellite as a bright flash. In Explore this is
            the layer "Ground and buildings".</p>`,
        svg: SVG_HH,
        hint: `<p>Switched to the <b>HH</b> surface view ("Ground and buildings").</p>
          <p>The <b>bright yellow spots</b> are villages and buildings bouncing strong <b>HH</b> echoes
          straight back. Smooth fields mirror most of the beam away, so they stay dark purple.</p>`,
        apply() { show({ layer: "surface", idx: baseIdx }); fitAll(); },
      },
      {
        title: "Colour composite",
        body: `<p>Two measurements, one picture. The map mixes the HH and the HV echo so that it reads like a land map:</p>
          <div class="swatches">
            <span class="sw" style="background:${COMP_COLOURS[0]}"></span><span><strong>Forest</strong>: strong echo from the crowns (HV)</span>
            <span class="sw" style="background:${COMP_COLOURS[1]}"></span><span><strong>Fields and meadows</strong>: little echo of both kinds</span>
            <span class="sw" style="background:${COMP_COLOURS[2]}"></span><span><strong>Buildings</strong>: very strong surface echo (HH)</span>
          </div>`,
        svg: "",
        hint: `Drag the line on the map: left is ${fmtDate(base.date)}, right is ${fmtDate(radar[firstPostIdx].date)}, the first image after the fire. Most of the area looks the same; the changes are local.`,
        apply() { show({ layer: "composite", cmp: true, ref: baseIdx, idx: firstPostIdx, swipe: 0.6 }); fitAll(); },
      },
      {
        title: "Vegetation: plants vs. bare ground",
        body: `<p><strong>Forest (HV)</strong> measures raw echo strength, which can still nudge up when
            everything gets wet. The <strong>Vegetation</strong> layer solves this by looking at a
            <strong>balance</strong> instead of raw brightness.</p>
          <p>It compares the twisted crown echo (<strong>HV</strong>) against the <strong>total</strong>
            echo from both plants and ground (<strong>HH + HV</strong>)—asking what share of the returning
            radar came from leaves and branches.</p>
          <p>Dense woods score high (<strong>green</strong>). Bare fields, roads, and burned forest—where
            the ground echo dominates—score low (<strong>brown</strong>). In Explore this is the layer "Vegetation".</p>`,
        svg: SVG_RVI,
        hint: `<p>Showing the <b>Vegetation</b> layer on ${fmtDateLong(last.date)} (after the fire).</p>
          <p><b>Green</b> marks lush woody cover; <b>brown</b> marks bare fields, roads, or burned canopy.${VEG
            ? ` Here <b>buildings</b> are masked in <b>grey</b> (their strong corner bounce would otherwise look like bare dirt) and <b>open water</b> in <b>blue-grey</b>.`
            : ""}</p>`,
        apply() { show({ layer: "vegetation", idx: N - 1 }); fitAll(); },
      },
    ];
    if (moist) {
      const moistIdx = nearest(moist.scenes, base.date);
      STEPS.push({
        title: "Moisture: water in the soil",
        body: `<p>Water changes how strongly soil bounces radio waves back—just as wet sand behaves
            differently from dry dust. The <strong>Moisture</strong> layer tracks how damp the top few
            centimetres of ground are.</p>
          <p><strong>Brown</strong> shows drier ground (when soil and plants dry out, fires start and
            spread more easily); <strong>blue</strong> shows wetter soil after rain.</p>
          <p><strong>Two limits:</strong> soil wetness is not the same as dry leaves or pine needles, and
            under thick forest the radar mostly bounces off tree crowns instead of reaching the dirt beneath.</p>`,
        svg: SVG_MOIST,
        hint: `<p>Showing the <b>Moisture</b> layer on ${fmtDateLong(moist.scenes[moistIdx].date)} (around the fire).</p>
          <p>Notice the larger blocky squares—soil moisture is averaged onto a coarser grid than the forest layers. ${/all valid/.test(moist.quality || "")
            ? "Readings over <b>open fields</b> are most reliable; under dense trees the satellite sees more canopy than soil."
            : "Gaps appear where thick forest hides the soil."}</p>`,
        apply() { show({ layer: "moisture", idx: moistIdx }); fitAll(); },
      });
    }
    STEPS.push({
      title: "Change: spotting only real loss",
      body: `<p>In <strong>Forest</strong>, open meadows already look dark—so it is hard to separate what
          was <em>always</em> bare from what just burned. The <strong>Change</strong> layer fixes that by
          <strong>comparing every spot only with itself</strong> before the fire (${fmtDate(base.date)}).</p>
        <p>Places that stayed the same stay <strong>white</strong>; only places that lost tree canopy
          turn <strong>red</strong>. In Explore this is the layer "Change".</p>${steady ? `
        <p>To keep rain and one-off satellite flickers from looking like fire damage, Explore also
          <strong>steadies</strong> the radar series: removing scene-wide weather shifts, smoothing across
          three passes in a row${STABLE.forest_cap ? ", and never letting Forest rise above its pre-fire level" : ""}.</p>` : ""}`,
      svg: SVG_CHANGE,
      hint: `<p>Showing the <b>Change</b> layer on ${fmtDateLong(last.date)} compared with ${fmtDateLong(base.date)}.</p>
        <p><b>White</b> means unchanged (both intact forest and meadows that were already open). <b>Red</b>
        means the tree-crown echo dropped${AREA ? "—next, Step 8 checks which drops last across multiple passes" : ""}.</p>`,
      apply() { show({ layer: "change", idx: N - 1 }); if (AREA) flyArea(1.8); else fitAll(); },
    });
    if (AREA) {
      STEPS.push({
        title: "Finding the damage",
        body: `<p>One image is not enough. Rain changes the echo everywhere, and single images are noisy.</p>
          <p>So we ask a strict question: where is the canopy echo clearly weaker than before the fire
            in at least ${DAMAGE.min_scenes} of the ${DAMAGE.post_scenes} images after it?
            That leaves <strong>${fmtNum(AREA.ha)} ha</strong>, as big as ${Math.round(AREA.ha / PITCH_HA).toLocaleString("en-US")} football pitches:
            the black outline on the map.</p>
          <p class="muted" style="margin:0">Radar echo of that area, in % of normal:</p>
          ${areaBars(N - 1)}
          <p>${DB_HELP} The threshold used here is ${THR} dB, a loss of about ${lossPct(THR)} %.</p>`,
        svg: "",
        hint: `Red is strong loss between ${fmtDate(base.date)} and ${fmtDate(last.date)}. Only the outlined area stays red from image to image.`,
        apply() { show({ layer: "forest", idx: N - 1, loss: true, outline: true }); flyArea(1.3); },
      }, {
        title: "Before and now",
        body: `<p><strong>${areaPct(N - 1) >= 90 ? "The forest echo is mostly back." : "The forest has not come back yet."}</strong>
            On ${fmtDate(last.date)} the echo of the damaged area is at ${areaPct(N - 1)} % of normal.
            Trees need years to grow back, not weeks.</p>` +
          (dropIdx > 0 ? `<p>The drop happened between ${fmtDate(radar[dropIdx - 1].date)} and ${fmtDate(radar[dropIdx].date)}.
            The radar cannot tell whether trees burned, fell or were cleared away.</p>` : "") +
          `<p>Now try it yourself in Explore: pick a layer, drag the red dot to change the date, and press
            Compare to see two dates side by side.</p>`,
        svg: "",
        hint: `Drag the line: left is ${fmtDate(base.date)}, right is ${fmtDate(last.date)}. The dark patch on the right is the damaged forest.`,
        apply() { show({ layer: "forest", cmp: true, ref: baseIdx, idx: N - 1, outline: true }); flyArea(1.0, true); },
      });
    }

    $("learn-dots").innerHTML = STEPS.map(() => "<span></span>").join("");
    function renderStep() {
      const st = STEPS[state.step];
      $("learn-step").innerHTML = `<h2>${st.title}</h2>${st.svg}${st.body}
        <div class="hint-box"><strong>On the map</strong>${st.hint}</div>`;
      $("learn-dots").querySelectorAll("span").forEach((d, i) => d.classList.toggle("on", i === state.step));
      $("learn-prev").disabled = state.step === 0;
      $("learn-next").textContent = state.step === STEPS.length - 1 ? "Explore" : "Next";
      $("panel-body").scrollTop = 0;
      st.apply();
    }
    function goStep(i) {
      if (i >= STEPS.length) { setMode("explore"); return; }
      state.step = Math.max(0, Math.min(STEPS.length - 1, i));
      renderStep();
    }
    $("learn-prev").onclick = () => goStep(state.step - 1);
    $("learn-next").onclick = () => goStep(state.step + 1);

    function setMode(mode) {
      state.mode = mode;
      if (mode === "learn") state.open = true;
      $("mode-explore").setAttribute("aria-pressed", String(mode === "explore"));
      $("mode-learn").setAttribute("aria-pressed", String(mode === "learn"));
      if (mode === "learn") { renderStep(); return; }
      // back to Explore: a plain view of the newest date
      show({ layer: layerById(state.layer).hidden ? "forest" : state.layer });
      fitAll();
    }
    $("mode-explore").onclick = () => setMode("explore");
    $("mode-learn").onclick = () => setMode("learn");

    // ------------------------------------------------------------------- about
    const dlg = $("about");
    $("open-about").onclick = () => dlg.showModal();
    $("close-about").onclick = () => dlg.close();
    dlg.onclick = (e) => { if (e.target === dlg) dlg.close(); };
    $("about-body").innerHTML = aboutHtml();

    function aboutHtml() {
      const rows = radar.map((s, i) => `<tr><td>${s.date}</td><td>${(s.time || "").slice(11, 19)}</td>
          <td>${fmtNum(s.mean_hv_db, 2)}</td><td>${AREA ? fmtNum(AREA.mean[i], 2) : "n/a"}</td></tr>`).join("");
      return `
        <p style="margin-top:14px">${REGION.about || ""} The NISAR satellite of NASA and ISRO
          passes over every 12 days and measures the ground with radar, through clouds and smoke. This map shows
          what it saw before and after. Built for the NASA Space Apps Challenge 2026, challenge "Dancing with the SARs".</p>
        <p style="margin-top:8px">Study area: ${esc(REGION.title || REGION.name)}.</p>
        ${REGION.damageCaveat ? `<p style="margin-top:8px"><strong>Note:</strong> ${esc(REGION.damageCaveat)}</p>` : ""}

        <h3>The layers</h3>
        <ul>
          <li><strong>Forest</strong> is the HV backscatter (sent horizontally, received vertically): the echo from inside tree crowns.</li>
          <li><strong>Ground and buildings</strong> is the HH backscatter: the echo from surfaces and corners.</li>
          <li><strong>Change</strong> compares every place with itself: the Forest echo of the date shown minus that of
            ${fmtDateLong(base.date)}, the last image before the fire. White is unchanged or stronger, red is weaker, full red at
            −${META.diff_range_db} dB.</li>
          <li><strong>Vegetation</strong> is the radar vegetation index RVI = 4·HV / (HH + HV). A relative index, not biomass in t/ha.${VEG
            ? ` Colour scale 0.2 to 1.2, as in every region. Buildings are grey and not on the scale: ${esc(VEG.buildings_method)} (${VEG.buildings_share_percent} % of the area, <code>scripts/make_vegetation.py</code>).
              ${REGION.buildingsCheck || ""}`
            : ""}</li>
          ${VEG && VEG.water ? `<li><strong>Water</strong> (blue-grey on every layer, ${VEG.water_share_percent} % of the area): ${esc(VEG.water_method)}.
            The layer colours mean nothing on water, so it is not coloured.</li>` : ""}
          <li><strong>Moisture</strong> is NISAR soil moisture (SME2), ${moist
            ? `${moist.scenes.length} scenes, ${esc(moist.quality || "")}. It is soil moisture, not fuel moisture.`
            : `not exported yet. Run <code>forest_watch_api/scripts/sme2_layers.py</code> with an Earthdata login.`}</li>
        </ul>

        ${CARBON ? `<h3>Carbon</h3>
        <ul>
          <li>Biomass: ${esc(CARBON.source)}. Mean above-ground biomass density of the GEDI mission years before 2026, with a
            standard error per 1 km cell; ${CARBON.gedi_cells} cells touch this area. It does not see the 2026 fire.</li>
          <li>Stock = biomass density × area of each radar pixel; carbon = ${CARBON.carbon_fraction} × biomass
            (${esc(CARBON.carbon_fraction_source)}); CO₂ = carbon × 44/12. The ± adds the cell errors as if fully correlated (an upper bound).</li>
          <li>Per date (the number on the map card): the stock in all trees minus the stock where the forest echo is more than
            ${THR} dB below ${fmtDateLong(CARBON.baseline)} on that date (${esc(CARBON.loss_rule || "")}), so the red of the Change layer.
            In compare mode the card shows the difference between the two dates. Single images are noisy: before the fire this
            already flags some hectares.</li>
          ${CARBON.damaged ? `<li>"Stood in the damaged forest" is the stock inside the lasting damage area found with NISAR. It is not the emission of
            the fire: only part of the biomass burns, the rest decays over years or is cleared.</li>
          <li>Lost uptake = damaged area × ${CARBON.growth_t_dm_ha_yr} t dry matter per ha and year × ${CARBON.carbon_fraction} × 44/12
            (${esc(CARBON.growth_source)}). A rough default for natural forest, not a measurement of this forest; plantations
            and young stands grow differently.</li>
          <li>Recovery is measured: the canopy echo (HV) of the damaged area per NISAR date. Back at 100 % means the crowns are back,
            which is not the same as the biomass being back.</li>` : ""}
          <li>Above-ground live biomass only: roots, dead wood and soil carbon are not included.</li>
        </ul>` : ""}

        <h3>Data</h3>
        <p>NISAR Level-2 GCOV (L-band), provisional products, from the Alaska Satellite Facility DAAC
          (<a href="https://search.asf.alaska.edu/">search.asf.alaska.edu</a>). Study area ${W}–${E}° E, ${S}–${Nn}° N.
          Fire window used here: ${fmtDateLong(META.fire.start)} to ${fmtDateLong(META.fire.end)}.
          Source for the fire dates: ${REGION.fireSource || '<span class="placeholder">[PLACEHOLDER: official source for the fire dates]</span>'}.</p>
        <table><thead><tr><th>Date</th><th>UTC</th><th>Mean HV dB</th><th>HV in damaged area dB</th></tr></thead><tbody>${rows}</tbody></table>
        <details><summary>Granule IDs</summary><ul>${radar.map((s) => `<li><code>${esc(s.source)}</code></li>`).join("")}
          ${moist ? moist.scenes.map((s) => `<li><code>${esc(s.source)}</code></li>`).join("") : ""}</ul></details>

        <h3>Method</h3>
        <ul>
          <li>HH and HV power inside the study box, one orbit track and flight direction. Speckle is reduced with a
            5 × 5 pixel average in linear power, then converted to dB and resampled to ${META.image_size[0]} × ${META.image_size[1]} px.</li>
          <li>The images are stored as grey values (HH ${DBR.HH.join(" to ")} dB, HV ${DBR.HV.join(" to ")} dB,
            HH − HV ${DBR.ratio.join(" to ")} dB) and coloured in the browser. Colour stretch:
            ${LAYERS.filter((l) => l.band && l.set === "radar").map((l) => `${esc(l.name)} ${l.band.range.join(" to ")}`).join(", ")}.</li>
          ${steady ? `<li>The radar layers are steadied so that weather does not look like change: for each date one
            scene-wide offset is removed (rain makes a whole scene brighter), then every pixel takes the median of three
            consecutive passes. One-off flickers disappear, changes that last for two passes or more stay
            (<code>scripts/make_stable.py</code>).</li>
            ${STABLE.forest_cap ? `<li>The Forest layer may fall but never rise above its level before the fire. Trees do not grow in
            weeks; a stronger echo on fields and meadows after rain is not new forest. The other layers keep the full signal.</li>` : ""}` : ""}
          ${DAMAGE ? `<li>Damaged area (${fmtNum(AREA.ha)} ha, shown in Learn): ${esc(DAMAGE.method)}
            (<code>scripts/make_damage.py</code>).</li>` : ""}
        </ul>

        <h3>Limits</h3>
        <ul>
          <li>Radar echo is a proxy for forest structure. It is <strong>not</strong> biomass in t/ha.</li>
          <li>Rain and soil moisture also change the echo. ${steady
            ? "The steadying removes scene-wide shifts and one-pass flickers, not every local weather effect. A change that shows in one pass only is hidden by it."
            : "Weather is not removed."}</li>
          <li>NISAR data are <strong>provisional</strong> (not fully validated). A single image is noisy: about 1 % of
            pixels pass the ${THR} dB loss threshold without any fire.</li>
          ${dropIdx > 0 && dayNum(radar[dropIdx - 1].date) > fireEnd
            ? `<li>The lasting loss first shows on ${fmtDateLong(radar[dropIdx].date)}, not in the first image after the fire window used here.
               Radar cannot tell fire from felling or clearing; an official perimeter and fire dates are needed to confirm the cause.</li>` : ""}
          <li>${PERIMETER ? "The dashed red line is the official fire perimeter (data/perimeter.geojson)."
            : "No official fire perimeter is included."}</li>
        </ul>

        <h3>Credits</h3>
        <p>NISAR, NASA/ISRO via ASF DAAC. Basemap © OpenStreetMap contributors. Map library: Leaflet.
          Team: <span class="placeholder">[PLACEHOLDER: team names]</span>.</p>
        ${hasPhotos && REGION.photos.items.some((it) => it.credit) ? `<p style="margin-top:6px">Photos: ${
          REGION.photos.items.filter((it) => it.credit).map((it) =>
            it.creditUrl ? `<a href="${esc(it.creditUrl)}" target="_blank" rel="noopener">${esc(it.credit)}</a>` : esc(it.credit)
          ).join(" · ")}</p>` : ""}
        <p class="muted" style="margin-top:6px">${esc(META.notes || "")}</p>`;
    }

    // ------------------------------------------------------------------- keyboard: arrows change the date / the step
    app.onKey = (e) => {
      if (dlg.open || (e.key !== "ArrowLeft" && e.key !== "ArrowRight")) return;
      const t = e.target;
      if (t.matches && t.matches("input, textarea, select, #swipe-handle")) return;
      if (t.closest && t.closest(".leaflet-container")) return;   // arrows pan the map there
      e.preventDefault();
      const dir = e.key === "ArrowLeft" ? -1 : 1;
      if (state.mode === "learn") goStep(state.step + dir);
      else setDate(state.idx + dir, dir);
    };

    // ------------------------------------------------------------------- go
    buildStops();
    const learnMatch = location.hash.match(/learn-(\d+)/);       // deep link for demos: #learn-3 or #r=gironde&learn-5
    if (learnMatch) {
      state.step = Math.max(0, Math.min(STEPS.length - 1, +learnMatch[1] - 1));
      setMode("learn");
    } else render();
  }

  boot();
})();
