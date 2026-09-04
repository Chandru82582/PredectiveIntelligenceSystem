
# NOC Telemetry Dashboard

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

### Why it was slow, and what was changed

Three things were making every click feel like a cold load:

1. **`resolve_as_of` re-queried `MAX(date, hour)` on nearly every request.** Now cached in-process for 30s (`_as_of_cache`) — it only moves forward once per batch ingestion anyway.
2. **Grid geometry was re-queried every time**, even though it's static reference data. Now cached per `grid_id` for the life of the process (`_geometry_cache`).
3. **Several endpoints pulled a grid's or the network's *entire* history into pandas before filtering by date in Python.** `get_grid_timeseries`, `get_grid_features`, `get_grid_modality`, and `get_alerts` now filter by date range in the SQL query itself, so only the relevant rows ever leave the database — this matters a lot once the table spans more than a few weeks.

## What's new on the frontend (`frontend/`)

- **Real basemap.** `GeographicHeatmap.jsx` now renders on `react-leaflet` with a dark CARTO tile layer underneath, actual per-cell polygons (drawn from `enriched_spatial_hourly.geometry` where available, otherwise the same computed square the backend uses as fallback), and a `leaflet.heat` thermal layer overlaid on real coordinates instead of a hand-rolled canvas projection.
- **Client-side cache** (`src/services/cache.js`), used by every function in `api.js`: live queries (no explicit date) are cached for 20s so switching tabs or grids doesn't force a full backend round trip every time; anything pinned to a specific historical date/`as_of` is cached indefinitely, since that's a fixed point in the past. Geometry lookups are permanent and deduplicated across components.
- **Date filter in Grid Investigator.** A date picker in the header lets you pin the whole view (confidence band, modality, fingerprint, weekly ribbon) to a specific day via the backend's `date`/`as_of` params; "Latest" resets to the live window.
- **Reordered by analysis priority**, not file-structure order:
  - *Network Overview*: KPIs → **Anomaly Feed + Hotspots Leaderboard** (what needs attention, and where) → **Geographic Map** (spatial context) → **Peak Hour Dial** (temporal/scheduling — lowest urgency during triage).
  - *Grid Investigator*: **Confidence Band** (is this abnormal right now?) → **Modality Decomposition + Traffic Dynamics** (breakdown once an anomaly is known) → **Behavioral Fingerprint** (classification) → **Peak Hour Dial** (maintenance-window planning, least urgent).

## Running it

```bash
# backend
cd backend
pip install fastapi uvicorn sqlalchemy pandas mysql-connector-python
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
