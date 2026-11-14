# FOREST WATCH API

Kleines FastAPI-Backend für die Hackathon-Demo (nur NISAR-Daten). Es bietet:

1. `POST /api/nisar/search` – NISAR-SME2-Szenen über `asf_search` im ASF-Katalog finden.
2. `POST /api/nisar/moisture` – für eine ausgewählte Szene nur ein räumliches Fenster der SME2-Bodenfeuchte auslesen und als GeoJSON zurückgeben.
3. `POST /api/nisar/change` – pixelweise Änderung der Bodenfeuchte zwischen zwei Szenen (vorher/nachher).
4. `GET /health` – Health Check.

Die Daten werden nicht an OpenUI/React als komplette HDF5-Datei geliefert. Der Server streamt bei Remote-Zugriff HDF5-Bytebereiche per HTTPS und gibt eine begrenzte Zahl von GeoJSON-Punkten zurück. Für größere Produktivkarten sollte die Antwort später durch COG/Tile-Serving ersetzt werden.

## 1. Installation

Empfohlen: Python 3.11 oder 3.12.

```bash
python -m venv .venv
# Windows PowerShell:
.venv\\Scripts\\Activate.ps1
# macOS/Linux:
# source .venv/bin/activate

python -m pip install --upgrade pip
pip install -r requirements.txt
```

## 2. Konfiguration

```bash
cp .env.example .env
```

Für Remote-Streaming die Earthdata-Zugangsdaten in `.env` eintragen:

```dotenv
EARTHDATA_USERNAME=...
EARTHDATA_PASSWORD=...
```

ASF-Katalogsuche benötigt in der Regel keine Anmeldedaten; das Abrufen der NISAR-Produktdaten per Streaming benötigt Earthdata Login.

### Bereits vorhandene HDF5-Datei lokal testen

Ihr könnt eure bereits heruntergeladene Datei verwenden, ohne erneut etwas von ASF zu laden. Tragt in `.env` ein:

```dotenv
NISAR_LOCAL_FILE=./data/NISAR_L3_PR_SME2_024_167_D_063_2005_DHDH_A_20260707T185816_20260707T185851_P05023_N_F_J_001.h5
NISAR_LOCAL_GRANULE_ID=NISAR_L3_PR_SME2_024_167_D_063_2005_DHDH_A_20260707T185816_20260707T185851_P05023_N_F_J_001
```

Legt die HDF5-Datei selbst unter `data/` ab. Sie ist absichtlich nicht in diesem Codepaket enthalten.

## 3. Server starten

Im Projektordner:

```bash
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

Danach:

- Swagger UI: http://localhost:8000/docs
- Health: http://localhost:8000/health

## 4. API ausprobieren

### A. NISAR-Szenen suchen

BBox-Reihenfolge immer `west, south, east, north` in WGS84/EPSG:4326.

```bash
curl -X POST http://localhost:8000/api/nisar/search \\
  -H "Content-Type: application/json" \\
  -d '{
    "bbox": [6.37, 50.72, 6.45, 50.77],
    "start": "2026-08-01",
    "end": "2026-08-31",
    "processing_level": "SME2",
    "data_maturity": "PROVISIONAL",
    "max_results": 25
  }'
```

### B. Bodenfeuchte für eine Szene abfragen

Nehmt eine `granule_id` aus der Suchantwort:

```bash
curl -X POST http://localhost:8000/api/nisar/moisture \\
  -H "Content-Type: application/json" \\
  -d '{
    "granule_id": "NISAR_L3_PR_SME2_024_167_D_063_2005_DHDH_A_20260707T185816_20260707T185851_P05023_N_F_J_001",
    "bbox": [6.37, 50.72, 6.45, 50.77],
    "max_points": 2500,
    "include_unrecommended": false
  }'
```

Die Antwort ist ein GeoJSON `FeatureCollection` in EPSG:4326. Jede Feature-Property enthält `soil_moisture_m3_m3`, `uncertainty_m3_m3`, `retrieval_quality_flag` und `recommended`. In `summary` stehen u.a. Pixelzahlen, Mittelwert, Median und Sampling-Schritt.

## 5. OpenUI verbinden

In eurem React-Projekt die Datei `openui/forestWatchToolProvider.ts` übernehmen und im OpenUI-Renderer übergeben:

```tsx
import { Renderer } from "@openuidev/react-lang";
import { forestWatchToolProvider } from "./forestWatchToolProvider";

<Renderer
  library={library}
  response={openuiLangResponse}
  toolProvider={forestWatchToolProvider}
/>
```

Die vom LLM erzeugte OpenUI-Lang-Antwort kann `search = Query("search_nisar", {...}, fallback)` und danach `moisture = Query("get_moisture_layer", {...}, fallback)` verwenden. `openui/example-query.openui` zeigt ein minimales Suchbeispiel; `openui/forestWatchPrompt.md` enthält Hinweise für die Tool-Aufrufe. Definiert `SceneTable` bzw. eine Kartenkomponente in eurer eigenen OpenUI-Library, damit die Ergebnisse gut angezeigt werden.

Setzt in eurem Frontend `.env` beispielsweise:

```dotenv
VITE_FOREST_WATCH_API=http://localhost:8000
```

## 6. Daten- und Qualitätsnotizen

- Der NISAR-SME2-Produktpfad in der Datei ist `/science/LSAR/SME2/grids/`.
- Koordinaten im HDF5 liegen in EPSG:6933; die API transformiert den Nutzer-BBox-Ausschnitt nach EPSG:6933 und GeoJSON-Ausgabepunkte zurück nach EPSG:4326.
- `soilMoisture` und `soilMoistureUncertainty` haben die Einheit `m3/m3`.
- Das niederwertigste Bit von `retrievalQualityFlag` kennzeichnet die Empfehlung: `0` = empfohlen, `1` = nicht empfohlen. Standardmäßig gibt die API nur empfohlene Pixel als Features zurück, berechnet aber im Summary auch den Anteil empfohlener Werte.
- NISAR SME2 PROVISIONAL ist laut Produktdokumentation noch nicht vollständig kalibriert/validiert. Die Ergebnisse sind ein Prototyp und keine behördliche Waldbrandwarnung. Dichte Vegetation und weitere Bedingungen können Werte als potenziell unzuverlässig markieren.
- Soil moisture ist nicht gleich Brennstofffeuchte. Für Risikokontext sollten Wetter, Vegetationsindikatoren und offizielle DWD-Indizes separat ergänzt werden.

## 7. Endpunkte

| Methode | Pfad | Zweck |
|---|---|---|
| GET | `/health` | Betriebsstatus |
| POST | `/api/nisar/search` | Suche im ASF-Katalog |
| POST | `/api/nisar/moisture` | Gestreamter räumlicher SME2-Ausschnitt als GeoJSON |
| POST | `/api/nisar/change` | Pixelweise Bodenfeuchte-Änderung zwischen zwei Granules |

## 8. Bekannte Grenzen

- Remote-Streaming benötigt gültige Earthdata-Zugangsdaten und einen Netzwerkzugriff auf ASF.
- Das GeoJSON ist eine einfache Proof-of-Concept-Ausgabe. Für eine produktive, großflächige Karte ist ein COG-/XYZ-Tile-Endpunkt effizienter.
- ASF Suche und HDF5-Streaming werden live gegen NASA/ASF ausgeführt. Ohne Netzwerk bzw. Earthdata-Login kann nur der lokale HDF5-Modus getestet werden.

## 9. Vorher/Nachher-Vergleich

`granule_id` für beide Aufnahmen aus `/api/nisar/search` nehmen (gleiche BBox verwenden):

```bash
curl -X POST http://localhost:8000/api/nisar/change \
  -H "Content-Type: application/json" \
  -d '{
    "bbox": [6.37, 50.72, 6.45, 50.77],
    "granule_before": "<granule_id vom 11.08.>",
    "granule_after": "<granule_id vom 23.08.>"
  }'
```

Die Antwort ist ein GeoJSON mit `before_m3_m3`, `after_m3_m3`, `change_m3_m3` und `change_percent` pro Pixel. `summary` enthält gepaarte Pixelzahl, Mittelwerte vor/nach, mittlere Änderung und wie viele Pixel zu- bzw. abgenommen haben. Die Pixel werden über ihren Zeilen-/Spaltenindex im gemeinsamen EPSG:6933-Raster gepaart, nur empfohlene Pixel beider Szenen zählen.

Das ist eine beobachtete Änderung, kein Nachweis einer Brandwirkung. Die API enthält bewusst keine Wetterdaten; Regen zwischen den Aufnahmen kann den Anstieg erklären und sollte in der Präsentation als Einschränkung genannt werden.
