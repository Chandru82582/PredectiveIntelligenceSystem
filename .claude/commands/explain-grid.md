---
description: Given a grid_id, gather activity, features, anomaly score and location, then produce the four-section SEVERITY / EVIDENCE / INTERPRETATION / NEXT CHECKS response
---

# /explain-grid [grid_id]

Given a `grid_id` (defaults to active cell or 4365):
1. Gathers:
   - Historical activity and 24h baseline via `get_grid_activity(grid_id)`
   - Rolling features, growth rate, peak ratio via `get_grid_features(grid_id)`
   - LightGBM anomaly probability score and risk label via `get_anomaly_score(grid_id)`
   - Centroid coordinates and sector via `get_grid_location(grid_id)`
2. Produces the four-section HTML response:
   - **SEVERITY**: Status badge (`NORMAL`, `ATTENTION`, `HIGH`) and Cell ID.
   - **EVIDENCE**: Telemetry card grid (Current Activity, Baseline, Growth, Peak Ratio, Anomaly Score %, Sector).
   - **INTERPRETATION**: Operational hypothesis distinguishing transient volume spikes from baseline shifts without claiming congestion.
   - **NEXT CHECKS**: Actionable operator checklist.
