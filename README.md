
# Telecom Activity Intelligence

## What's new on the backend (`backend/`)

Your original `routes.py` covered network summary, grid timeseries, hotspots,
alerts, and grid features — enough for KPIs and the confidence-band chart,
but not enough to drive the map, the week view, or the diverging in/out bars
the brief calls for. Added to `database.py` / `schemas.py` / `routes.py`:

| Endpoint                                              | Why it was missing                                                                                                                                                                                                                                                                                                                                                                                                     |
| ----------------------------------------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `GET /network/grid/{grid_id}/geography`             | No lat/lon existed anywhere in the API. Reads the real polygon + centroid from`enriched_spatial_hourly.geometry` when populated, otherwise derives both deterministically from `grid_id` over a bounding box calibrated against a real sample cell (45.3529–45.5649°N, 9.0115–9.3115°E, ~235m cells). Cached in-process — geometry never changes, so it's resolved at most once per grid per server lifetime. |
| `GET /network/grids/geography?grid_ids=...`         | Bulk version of the above, and only queries the DB for grid_ids not already cached.                                                                                                                                                                                                                                                                                                                                    |
| `GET /network/grid/{grid_id}/weekly-peak`           | Powers`PeakHourDial`'s Week View — per-day peak hour over the trailing 7 days plus drift vs. the average.                                                                                                                                                                                                                                                                                                           |
| `GET /network/grid/{grid_id}/modality?hours=&date=` | Raw`sms_in/out` / `call_in/out` for the diverging bar chart (the existing timeseries endpoint only exposes combined totals). Also accepts a `date` override for historical analysis.                                                                                                                                                                                                                             |
| `GET /network/grids`                                | Flat list of active grids with a computed severity band, for the quick cell switcher.                                                                                                                                                                                                                                                                                                                                  |

None of the existing endpoints or response shapes were changed — additive only.

### Prediction endpoint (`backend/ml_model.py`, `routes.py`, `schemas.py`)

| Endpoint                          | What it does                                                                                                                                                                                                                                                                                    |
| ---------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| `GET /predict/grid/{grid_id}`    | Predicts whether the grid is likely to enter a high-activity state (>=1.5x its within-day baseline) in the hour *after* `as_of`, using the trained LightGBM classifier in `DataAnalysis/models/lgbm_high_activity_v1.joblib`. Returns the predicted probability, thresholded risk label, and the engineered feature values used. Requires >=24h of trailing hourly history for the grid; returns `422` if there isn't enough. |

`ml_model.py` loads `DataAnalysis/preprocessor.py` directly from its file path (so `DataAnalysis` doesn't need to be an importable package) and reuses it verbatim, so the features fed to the model at serving time are identical to training. The route pulls trailing history straight from `hourly_grid_summary`, maps it onto the raw schema `DataPreprocessor` expects, and hands it off — no separate feature store needed.

One subtlety worth flagging: the model bundle's `grid_categories` are the *string* form of `grid_id` (that's how the training notebook happened to encode it before casting to `category`), and LightGBM bakes those exact codes into its trained splits. `DataPreprocessor` on its own produces an int-keyed categorical, so `ml_model.py` re-encodes `grid_id` against the bundle's string categories right before calling `predict_proba` — skipping this step still runs without error, it just silently drops all grid-specific signal (verified empirically: same input, different `grid_id` encoding, meaningfully different predicted probability).

### Data Explorer endpoints (`backend/routes.py`, `schemas.py`)

One filterable, paginated, sortable endpoint per backing table rather than a single generic one, so each gets the filters that actually make sense for it (`hour` doesn't exist on `daily_summary`, for instance):

| Endpoint                 | Backing table              |
| ------------------------- | --------------------------- |
| `GET /data/hourly`       | `hourly_grid_summary` — finest granularity, one row per (date, hour, grid_id) |
| `GET /data/spatial`      | `enriched_spatial_hourly` — activity + geometry provenance (`has_geometry` flag; the raw geometry payload itself isn't exposed here — see `/network/grid/{id}/geography` for parsed lat/lon) |
| `GET /data/grid-summary` | `grid_summary` — per-day, per-grid rollup |
| `GET /data/daily-summary`| `daily_summary` — network-wide per-day rollup |
| `GET /data/audit-log`   | `flow/logs/audit_log.json` — the Spark pipeline's file-ingestion quality-check trail (not a DB table; read straight off disk, mtime-cached) |

The four DB-backed endpoints share the same shape of filters (`grid_id`, `date_from`/`date_to`, `min_activity`/`max_activity`, plus `hour_min`/`hour_max` where applicable) and pagination/sort params (`sort_by`, `sort_dir`, `page`, `page_size`, capped at 500/page); `sort_by` is validated against a per-table allow-list server-side (400 on an unknown column) rather than trusting an arbitrary column name. `/data/audit-log` follows the same pagination/sort convention but with its own filters (`status`, `filename` substring match) since it isn't grid- or hour-shaped data.

### Why it was slow, and what was changed

Three things were making every click feel like a cold load:

1. **`resolve_as_of` re-queried `MAX(date, hour)` on nearly every request.** Now cached in-process for 30s (`_as_of_cache`) — it only moves forward once per batch ingestion anyway.
2. **Grid geometry was re-queried every time**, even though it's static reference data. Now cached per `grid_id` for the life of the process (`_geometry_cache`).
3. **Several endpoints pulled a grid's or the network's *entire* history into pandas before filtering by date in Python.** `get_grid_timeseries`, `get_grid_features`, `get_grid_modality`, and `get_alerts` now filter by date range in the SQL query itself, so only the relevant rows ever leave the database — this matters a lot once the table spans more than a few weeks.

## What's new on the frontend (`frontend/`)

- **Real basemap.** `GeographicHeatmap.jsx` now renders on `react-leaflet` with a dark CARTO tile layer underneath, actual per-cell polygons (drawn from `enriched_spatial_hourly.geometry` where available, otherwise the same computed square the backend uses as fallback), and a `leaflet.heat` thermal layer overlaid on real coordinates instead of a hand-rolled canvas projection.
- **Client-side cache** (`src/services/cache.js`), used by every function in `api.js`: live queries (no explicit date) are cached for 20s so switching tabs or grids doesn't force a full backend round trip every time; anything pinned to a specific historical date/`as_of` is cached indefinitely, since that's a fixed point in the past. Geometry lookups are permanent and deduplicated across components.
- **Date + time filter in Grid Investigator.** A date picker and an hour selector in the header together pin the "as of" moment used by the point-in-time panels (Predicted Activity Risk, Behavioral Fingerprint, Peak Hour Dial's weekly drift) to a specific hour, not just a day; the hour selector is disabled until a date is picked, and defaults to 23:00. The day-level charts (confidence band, modality, traffic dynamics) stay windowed to the full selected day regardless of the hour picked. "Latest" resets both back to the live window.
- **Predicted Activity Risk panel** (`ActivityPrediction.jsx`), new top section of Grid Investigator. Calls `GET /predict/grid/{grid_id}` and shows the model's next-hour high-activity probability against its decision threshold, plus the underlying engineered features (growth, burst ratio, variability, etc.) for transparency. Falls back to a deterministic synthetic score, same as every other panel, if the backend/model isn't reachable.
- **New "Data" page** (`views/DataExplorer.jsx`), next to Grid Investigator — a tabbed table browser over the four raw/rollup DB tables (`hourly_grid_summary`, `enriched_spatial_hourly`, `grid_summary`, `daily_summary`) plus a **Quality Check** tab over the pipeline's ingestion audit log (`flow/logs/audit_log.json`, via `GET /data/audit-log`) — filenames, ACCEPTED/REJECTED status, row counts, duration, and the failure reason (truncated with a hover tooltip for the full text) for rejected files. Each tab has its own filter bar (grid_id, date range, hour range where applicable, activity range, geometry presence for the spatial table, status/filename for Quality Check), click-to-sort columns, and pagination, all kept independent per tab. Clicking a `grid_id` in any row jumps straight to that grid in Grid Investigator, same as the map/leaderboard.
- **Hotspots Leaderboard and Anomaly Feed now show the date/time each entry reflects**, not just the grid_id — `Hotspot` gained a `timestamp` field (the hour the ranking was computed for) and `AnomalyFeed` now renders each alert's existing `timestamp`, which the UI wasn't displaying before.
- **Reordered by analysis priority**, not file-structure order:
  - *Network Overview*: KPIs → **Anomaly Feed + Hotspots Leaderboard** (what needs attention, and where) → **Geographic Map** (spatial context) → **Peak Hour Dial** (temporal/scheduling — lowest urgency during triage).
  - *Grid Investigator*: **Predicted Activity Risk** (what's about to happen) → **Confidence Band** (is this abnormal right now?) → **Modality Decomposition + Traffic Dynamics** (breakdown once an anomaly is known) → **Behavioral Fingerprint** (classification) → **Peak Hour Dial** (maintenance-window planning, least urgent).

## Running it

```bash
# backend
cd backend
pip install fastapi uvicorn sqlalchemy pandas mysql-connector-python lightgbm scikit-learn joblib
uvicorn main:app --reload --port 8000

# frontend
cd frontend
npm install
cp .env.example .env   # point VITE_API_BASE_URL at your backend
npm run dev
```

If the backend isn't reachable, every call in `src/services/api.js` falls
back to deterministic synthetic data (including a computed grid square for
the map) so the dashboard never renders blank — a small amber "synthetic
fallback data" badge appears in the Grid Investigator header, and the
header's sync indicator turns amber, when this happens.
