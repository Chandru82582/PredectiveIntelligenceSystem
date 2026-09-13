---
name: telecom-data-quality
description: >-
  Audit telecom dataset invariants, grain uniqueness, spatial joins, and telemetry integrity.
  Use this skill whenever someone asks to verify data quality, run grain checks (e.g. /network-health),
  audit schema constraints, or check for duplicate rows in hourly_grid_summary.
---

# Telecom Data Quality Skill

## 1. Activation Triggers
Activate this skill whenever the user or operator:
- Runs or requests a grain duplicate audit (e.g., "/network-health").
- Asks whether `hourly_grid_summary` or `enriched_spatial_hourly` satisfies the composite grain invariant.
- Inquires about data anomalies such as missing grid cells, null timestamps, negative activity values, or spatial join mismatches with GeoJSON.
- Verifies integrity of country-code aggregations or rolling 10-minute to 1-hour slot rollups.

---

## 2. Required Evidence Checklist
Before reporting on data quality, the agent **MUST** verify:
1. **Grain Duplicate Count**: Count of records violating the unique grain constraint `(date, hour, grid_id)`.
2. **Duplicate Grain Examples**: Specific `(date, hour, grid_id)` keys that appear $>1$ time with their corresponding `loaded_at` timestamps.
3. **Record Count & Coverage**: Number of distinct grids active (out of 10,000 spatial cells) and total hourly records for the audit window.
4. **Value Range Invariants**: Check that `total_activity >= 0`, `internet_activity >= 0`, `total_sms >= 0`, and `total_calls >= 0`.
5. **Spatial Join Integrity**: Verify spatial features join on `properties.cellId` (1–10,000), not feature array index.

---

## 3. Non-Negotiable Data Quality Rules

1. **Analytics Grain Invariant**:
   - **Exactly one row per grid cell per 1-hour window after country-code aggregation**:  
     Composite primary key: `(date, hour, grid_id)`.
   - Repeated ETL loads without `UPSERT` / `ON DUPLICATE KEY UPDATE` will cause duplicate grains with differing `loaded_at`.
2. **Dimensionless Proportionality**:
   - Activity measures must be non-negative real numbers.
   - Never represent or compute ratios using counts or byte denominators.
3. **Spatial Key Integrity**:
   - Joined GeoJSON features must match `grid_id == properties.cellId`.
   - Never use 0-indexed feature IDs.

---

## 4. Standard Response Format

### Section 1: INTEGRITY STATUS
- **Status Badge**: `PASS` (zero grain duplicates, full constraint compliance) or `FAIL (GRAIN DUPLICATES DETECTED)`.
- **Target Table**: `hourly_grid_summary`.
- **Audit Scope**: Date inspected (or full 7-day dataset).

### Section 2: EVIDENCE & METRICS
- **Inspected Rows**: Total records scanned.
- **Duplicate Grain Violations**: Count of distinct `(date, hour, grid_id)` combinations with `count > 1`.
- **Sample Violations Table**:
  | Grid ID | Date | Hour | Instance Count | Distinct Loaded At Timestamps |
  |---|---|---|---|---|
  | 4 | 2013-11-01 | 00:00 | 3 | 2026-03-01 10:15:02, 2026-03-01 10:15:03, 2026-03-01 10:15:04 |

### Section 3: ROOT CAUSE ANALYSIS
- Explain why duplicate grains occurred:
  - Repeated batch ingestion without idempotent deduplication (e.g., executing PySpark batch inserts multiple times without clearing or upserting previous partitions).
  - Unsynchronized parallel workers inserting overlapping country-code fragments.

### Section 4: REMEDIATION SCRIPT / STEPS
- Provide the exact SQL deduplication statement:
  ```sql
  -- Keep the latest loaded record per grain:
  DELETE t1 FROM hourly_grid_summary t1
  INNER JOIN hourly_grid_summary t2 
  WHERE t1.date = t2.date 
    AND t1.hour = t2.hour 
    AND t1.grid_id = t2.grid_id 
    AND t1.loaded_at < t2.loaded_at;
  ```
- Recommend adding a `UNIQUE(date, hour, grid_id)` constraint to enforce future idempotency.
