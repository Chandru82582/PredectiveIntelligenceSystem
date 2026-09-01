
# Star Schema Implementation: Milan Telecom Grid Activity

## Overview

This directory contains a complete star schema implementation for analyzing network activity across the Milan geographic grid. The schema supports drill-down analysis, hourly trends, hotspot detection, and ML feature extraction.

**Key Features:**
- ✅ Minimal schema (3 tables: 1 fact, 2 dimensions)
- ✅ No geometry repetition in fact rows (reference-based design)
- ✅ Static grid reference loaded once (10,000 grids)
- ✅ Supports all required query patterns

---

## Schema Design

### Tables

#### `dim_grid` (10,000 rows)
- **grid_id**: PK, unique grid cell identifier (1-10000)
- **centroid_lat**: Latitude of grid polygon centroid
- **centroid_lon**: Longitude of grid polygon centroid
- **geometry_ref**: Reference pointer to full geometry (e.g., `milano_polygon_00001`)
- **loaded_at**: Timestamp of load

**Notes:**
- Full Polygon geometry NOT stored here
- Centroids calculated from milano-grid.geojson
- Static reference, loaded once

#### `dim_time` (168 rows expected)
- **time_id**: PK, auto-incremented surrogate key
- **full_date**: Date (YYYY-MM-DD)
- **hour**: Hour of day (0-23)
- **day_of_week**: Day of week (1-7, Monday-Sunday)
- **is_weekend**: Boolean (1=Sat/Sun, 0=weekday)
- **loaded_at**: Timestamp of load

**Notes:**
- Grain: One row per distinct (date, hour) combination
- Supports time-based drill-down and aggregations
- 7 days × 24 hours = 168 rows (for Nov 1-7, 2013)

#### `fact_network_activity` (Activity Grain)
- **grid_id**: FK → dim_grid
- **time_id**: FK → dim_time
- **sms_in**: Incoming SMS count (activity measure)
- **sms_out**: Outgoing SMS count (activity measure)
- **call_in**: Incoming call count (activity measure)
- **call_out**: Outgoing call count (activity measure)
- **internet_activity**: Internet usage volume (activity measure)
- **total_activity**: Aggregate measure (sms_in + sms_out + call_in + call_out + internet)
- **loaded_at**: Timestamp of load

**Notes:**
- Grain: One row per (grid_id, time_id) combination
- Sparse population (only observed combinations loaded)
- All measures normalized to 0 if NULL (data quality rule)
- PK: (grid_id, time_id)

---

## File Structure

```
sql_ingestion/
├── 01_ddl_create_schema.sql        # SQLite schema definition
├── 02_load_dim_grid.py             # Load dim_grid from milano-grid.geojson
├── 03_load_activity_data.py        # Load fact_network_activity from parquet
├── 04_mysql_ingestion.py           # MySQL/SQLite ingestion handler
├── 04_validation_queries.sql       # Validation & bonus queries
├── 05_mysql_create_tables.sql      # MySQL production tables
├── quickstart.py                    # Quick-start initialization script
└── README.md                        # This file
```

---

## MySQL Integration & Airflow Deployment

### Overview

The `04_mysql_ingestion.py` module provides production-ready database ingestion capabilities:

- **Dual Database Support**: SQLite (development) and MySQL (production)
- **Connection Pooling**: Efficient connection management for concurrent loads
- **Batch Ingestion**: Optimized bulk loading with configurable batch sizes
- **Airflow Integration**: Pre-built Airflow task for orchestrated pipelines
- **Error Handling**: Graceful error logging and recovery

### Architecture

```
Spark Processing (telecom_pipeline.py)
         ↓
    Parquet Output (dated partitions)
         ↓
  MySQL Ingestion Task (Airflow)
         ↓
    MySQL/SQLite Tables
         ↓
  Analytics & Reporting
```

### Airflow DAG Integration

The ingestion DAG (`flow/airflow_home/dags/ingestion_dag.py`) has been enhanced with:

#### 1. **Enhanced File Sensor**
- Checks `data/landing` directory for new CSV files
- **Poll interval**: 5 minutes (configurable)
- **Timeout**: 24 hours
- Starts immediately upon DAG trigger

**Configuration:**
```python
wait_for_files = PythonSensor(
    task_id="wait_for_milano_files",
    python_callable=_files_waiting,
    poke_interval=300,        # Check every 5 minutes
    timeout=60 * 60 * 24,     # Max 24 hours
    mode="reschedule",        # Free worker between checks
    soft_fail=False           # Explicit fail on timeout
)
```

#### 2. **Task Dependencies**

Pipeline execution order with automatic triggering:

```
wait_for_files
    ↓
ingest          (move files, read CSV → Parquet)
    ↓
validate        (quality checks, split clean/quarantine)
    ↓
spark_process   (aggregate, enrich, final warehouse write)
    ↓
mysql_ingest    (load aggregates into MySQL tables)
```

Each task waits for the previous to complete. The sensor runs independently and triggers the entire pipeline once data arrives.

#### 3. **MySQL Ingestion Task** (New)

Automatically loads Spark outputs into MySQL tables:

```python
@task
def mysql_ingest(spark_summary: Dict[str, List[str]]) -> Dict[str, Any]:
    """Load processed data into MySQL analytical tables."""
    ingestion = MySQLDataIngestion(
        use_sqlite=True,  # Change to False for MySQL
        sqlite_path="sql_ingestion/telecom_analytics.db"
    )
    stats = ingestion.ingest_from_parquet(parquet_dirs)
    return {"status": "SUCCESS", "rows_ingested": stats}
```

**Features:**
- Automatic parquet directory detection
- Batch loading (1000 rows default)
- Comprehensive logging and audit trail
- Error recovery and partial success handling

---

## MySQL Production Deployment

### Setup Steps

#### Step 1: Create MySQL Database

```sql
CREATE DATABASE telecom_analytics CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
USE telecom_analytics;
```

#### Step 2: Create Tables

```bash
mysql -u root -p telecom_analytics < 05_mysql_create_tables.sql
```

#### Step 3: Configure Airflow DAG

Modify `ingestion_dag.py` to enable MySQL (instead of SQLite):

```python
# In mysql_ingest task, change:
ingestion = MySQLDataIngestion(
    host='your-mysql-host',
    user='mysql_user',
    password='mysql_password',
    database='telecom_analytics',
    port=3306,
    use_sqlite=False  # Enable MySQL
)
```

#### Step 4: Deploy DAG

```bash
# Copy DAG to Airflow dags folder
cp ingestion_dag.py ~/airflow/dags/

# Trigger DAG or wait for schedule
airflow dags trigger telecom_landing_ingestion
```

### MySQL Table Schema

**Production tables** (defined in `05_mysql_create_tables.sql`):

| Table | Rows | Description |
|-------|------|-------------|
| `curated_usage` | ~1.6M | Clean activity records |
| `quarantine` | ~50K | Rejected records |
| `hourly_grid_summary` | ~1.7M | Hourly aggregates by grid |
| `daily_summary` | 7 | Daily totals |
| `grid_summary` | ~50K | Daily per-grid aggregates |
| `enriched_spatial_hourly` | ~1.7M | Hourly with geometry refs |
| `audit_log` | 1000+ | Load tracking |

**All tables include:**
- `loaded_at` timestamp
- Optimized indexes for common queries
- FOREIGN KEY constraints (optional, for referential integrity)

---

## Module Reference: MySQLDataIngestion

### Basic Usage

```python
from mysql_ingestion import MySQLDataIngestion
from pathlib import Path

# Initialize
ingestion = MySQLDataIngestion(
    host='localhost',
    user='root',
    password='password',
    database='telecom_analytics',
    use_sqlite=False,  # MySQL mode
    port=3306
)

# Define parquet sources
parquet_dirs = {
    'curated_usage': Path('report_spark/curated_usage'),
    'hourly_grid_summary': Path('report_spark/hourly_grid_summary'),
    'daily_summary': Path('report_spark/daily_summary'),
    # ... etc
}

# Ingest
stats = ingestion.ingest_from_parquet(parquet_dirs, batch_size=1000)

# Returns:
# {
#     'curated_usage': 1600000,
#     'hourly_grid_summary': 1700000,
#     'daily_summary': 7,
#     # ...
#     'errors': [...]
# }
```

### Connection Pooling

```python
# Create pool
pool = MySQLConnectionPool(
    host='localhost',
    pool_size=5,  # Concurrent connections
    use_sqlite=False
)

# Use connections
with pool.get_connection() as conn:
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM hourly_grid_summary LIMIT 1")
    result = cursor.fetchone()
```

### Error Handling

```python
try:
    stats = ingestion.ingest_from_parquet(parquet_dirs)
except Exception as e:
    logger.error(f"Ingestion failed: {e}")
    # Graceful degradation
    # Partial data may have been loaded
```

---

## Airflow Deployment Checklist

- [ ] MySQL database created
- [ ] Tables created via `05_mysql_create_tables.sql`
- [ ] DAG copied to `~/airflow/dags/`
- [ ] `mysql_ingestion.py` in `sql_ingestion/` directory
- [ ] DAG configuration updated (host, credentials if needed)
- [ ] Test data placed in `data/landing/`
- [ ] Airflow scheduler started
- [ ] DAG unpaused and triggered
- [ ] Audit log and tables populated

### Testing

```bash
# Trigger DAG manually
airflow dags trigger telecom_landing_ingestion

# Monitor execution
airflow dags list-runs --dag-id telecom_landing_ingestion

# View task logs
airflow tasks logs telecom_landing_ingestion mysql_ingest

# Verify data
mysql -u root -p -e "SELECT COUNT(*) FROM telecom_analytics.hourly_grid_summary;"
```

---

## File Sensor Behavior

### Timeline Example

```
09:00 - DAG triggered
09:00 - Sensor checks landing/ → No files → Waits
09:05 - Sensor checks landing/ → No files → Waits
09:10 - Sensor checks landing/ → No files → Waits
09:15 - Sensor checks landing/ → Files found! ✓ Continue
09:15 - ingest task starts
09:20 - ingest completes
09:20 - validate task starts
09:25 - validate completes
09:25 - spark_process task starts
09:45 - spark_process completes
09:45 - mysql_ingest task starts
09:50 - mysql_ingest completes
09:50 - DAG finishes (SUCCESS)
```

### Timeout Behavior

If no data appears after 24 hours:
- Sensor times out
- DAG marked as FAILED
- ingest task skipped
- Entire pipeline halted

**To adjust timeout:**
```python
timeout=60 * 60 * 24,  # Change 24 to desired hours
```

---

## Troubleshooting

### Issue: "MySQLDataIngestion not available"

**Cause**: `mysql_ingestion.py` not found in path

**Solution**:
```bash
# Verify file exists
ls -la sql_ingestion/04_mysql_ingestion.py

# Verify path in DAG
cat flow/airflow_home/dags/ingestion_dag.py | grep "sql_ingestion_path"
```

### Issue: "MySQL connection refused"

**Cause**: Database not running or credentials incorrect

**Solution**:
```bash
# Test MySQL connection
mysql -h localhost -u root -p -e "SELECT 1;"

# Update DAG credentials
vi flow/airflow_home/dags/ingestion_dag.py
# Edit MySQLDataIngestion initialization
```

### Issue: "No parquet directories found"

**Cause**: Spark output structure differs from expected

**Solution**:
```python
# In mysql_ingest task, log actual output structure
import os
output_base = RAW_PATH / "processed_parquet"
print(f"Contents of {output_base}:")
for item in os.listdir(output_base):
    print(f"  - {item}")
```

### Issue: "Sensor waits forever"

**Cause**: Landing directory path incorrect

**Solution**:
```bash
# Verify landing path
ls -la d:/PredectiveIntelligenceSystem/flow/data/landing/

# Check DAG configuration
echo "LANDING_PATH=$LANDING_PATH"
```

---

## Performance Tuning

### Batch Size

Larger batches = faster inserts, higher memory:

```python
stats = ingestion.ingest_from_parquet(
    parquet_dirs,
    batch_size=5000  # Increase for faster loads (default: 1000)
)
```

### Connection Pool Size

More connections = concurrent inserts, higher MySQL load:

```python
pool = MySQLConnectionPool(
    pool_size=10  # Increase for parallel loads (default: 5)
)
```

### Indexes

Add indexes for common queries:

```sql
-- For hotspot detection
CREATE INDEX idx_activity ON hourly_grid_summary(total_activity DESC);

-- For time-series
CREATE INDEX idx_date_hour ON hourly_grid_summary(date, hour);

-- For drill-down
CREATE INDEX idx_grid_time ON hourly_grid_summary(grid_id, date, hour);
```

---

## Next Steps

1. **Production Deployment**
   - Set up MySQL database
   - Configure Airflow DAG with credentials
   - Deploy and test

2. **Advanced Queries**
   - Hotspot detection
   - Anomaly detection
   - Time-series forecasting

3. **Visualization**
   - Connect Tableau/Grafana
   - Build geographic heatmaps
   - Real-time dashboards

---

## Summary

**Files included:**

### Step 1: Create Database Schema

```bash
# Using SQLite
sqlite3 telecom_analytics.db < 01_ddl_create_schema.sql

# Or with MySQL/MariaDB
mysql -u user -p database < 01_ddl_create_schema.sql
```

**Output:** Empty tables with proper indexes and constraints.

---

### Step 2: Load Static Grid Reference

```bash
cd sql_ingestion
python 02_load_dim_grid.py
```

**Expected Output:**
```
✓ Successfully loaded 10000 grids into dim_grid
  - All 10,000 Milan grid cells loaded
  - Centroids calculated from polygon geometry
  - No geometry duplication (reference-only design)
```

**Verification:**
```sql
SELECT COUNT(*) as grid_count FROM dim_grid;
-- Expected: 10000

SELECT COUNT(DISTINCT centroid_lat, centroid_lon) FROM dim_grid;
-- Expected: 10000 (all unique centroids)
```

---

### Step 3: Load Activity Data

```bash
cd sql_ingestion
python 03_load_activity_data.py
```

**Expected Output:**
```
✓ Successfully loaded 1,680,000 activity records
✓ Populated dim_time with 168 time periods (7 days × 24 hours)
✓ Covered 7,250 unique grids (observed activity, sparse)
✓ Covered 7 unique dates (Nov 1-7, 2013)
```

**Verification:**
```sql
SELECT COUNT(*) FROM fact_network_activity;
-- Expected: ~1.68M (varies based on observed grids)

SELECT COUNT(*) FROM dim_time;
-- Expected: 168

SELECT COUNT(DISTINCT grid_id) FROM fact_network_activity;
-- Expected: ~7,250 (only observed grids)
```

---

### Step 4: Validate Schema Integrity

```bash
# Run all three validation queries
sqlite3 telecom_analytics.db < 04_validation_queries.sql

# Or specific validation:
sqlite3 telecom_analytics.db "SELECT * FROM dim_grid LIMIT 5;"
sqlite3 telecom_analytics.db "SELECT * FROM dim_time LIMIT 5;"
```

---

## Validation Queries

### Query 1: Grid Dimension Completeness

**Purpose:** Verify grid_id coverage, null handling, and coordinate ranges

**Expected Results:**
- grid_count = 10,000
- null_centroids = 0
- null_geometry_refs = 0
- Latitude range: ~45.35-45.55 (Milan area)
- Longitude range: ~9.00-9.25 (Milan area)

```sql
SELECT * FROM dim_grid WHERE centroid_lat IS NULL;
-- Should return 0 rows
```

---

### Query 2: Time Dimension Coverage

**Purpose:** Verify complete temporal coverage with no gaps or duplicates

**Expected Results:**
- unique_dates = 7
- total_time_periods = 168
- duplicate_time_keys = 0
- invalid_hours = 0

```sql
SELECT DISTINCT full_date FROM dim_time ORDER BY full_date;
-- Should show 7 consecutive dates: Nov 1-7, 2013
```

---

### Query 3: Fact Table Aggregates & Integrity

**Purpose:** Verify referential integrity, data quality, and activity volume

**Expected Results:**
- fact_record_count > 0 (e.g., ~1.68M)
- orphaned_grid_refs = 0
- orphaned_time_refs = 0
- anomalies (negative values) = 0
- total_activity_volume > 0

```sql
SELECT SUM(total_activity) FROM fact_network_activity;
-- Should be > 0
```

---

## Usage Examples

### Drill-Down: Top 10 Hotspots

```sql
SELECT 
    g.grid_id,
    g.centroid_lat,
    g.centroid_lon,
    SUM(f.total_activity) as activity_sum
FROM fact_network_activity f
JOIN dim_grid g ON f.grid_id = g.grid_id
GROUP BY g.grid_id, g.centroid_lat, g.centroid_lon
ORDER BY activity_sum DESC
LIMIT 10;
```

### Hourly Trends

```sql
SELECT 
    t.hour,
    SUM(f.total_activity) as hourly_total,
    COUNT(DISTINCT f.grid_id) as active_grids
FROM fact_network_activity f
JOIN dim_time t ON f.time_id = t.time_id
GROUP BY t.hour
ORDER BY t.hour;
```

### Weekend vs. Weekday

```sql
SELECT 
    CASE WHEN t.is_weekend = 1 THEN 'Weekend' ELSE 'Weekday' END as period_type,
    SUM(f.total_activity) as total_activity,
    AVG(f.total_activity) as avg_activity
FROM fact_network_activity f
JOIN dim_time t ON f.time_id = t.time_id
GROUP BY t.is_weekend;
```

### ML Feature Extraction: Hourly Activity by Grid

```sql
SELECT 
    f.grid_id,
    t.hour,
    AVG(f.sms_in) as avg_sms_in,
    AVG(f.sms_out) as avg_sms_out,
    AVG(f.call_in) as avg_call_in,
    AVG(f.call_out) as avg_call_out,
    AVG(f.internet_activity) as avg_internet,
    AVG(f.total_activity) as avg_total
FROM fact_network_activity f
JOIN dim_time t ON f.time_id = t.time_id
GROUP BY f.grid_id, t.hour;
```

---

## Database Compatibility

### Supported Databases

| Database | Status | Notes |
|----------|--------|-------|
| SQLite   | ✅ Recommended | File-based, zero config, perfect for analytics |
| MySQL/MariaDB | ✅ Supported | Use AUTO_INCREMENT, InnoDB |
| PostgreSQL | ✅ Supported | Use SERIAL for time_id |
| DuckDB | ✅ Supported | Fast columnar OLAP queries |

### SQL Dialect Adjustments

**MySQL/MariaDB:**
- Change `DECIMAL(12, 8)` to `DECIMAL(12, 8)` ✓
- Change `CONCAT(...)` to `CONCAT(...)` ✓
- Change `LPAD(...)` syntax ✓

**PostgreSQL:**
```sql
-- Use SERIAL instead of INT AUTO_INCREMENT
time_id SERIAL PRIMARY KEY,

-- Use || for string concatenation
CONCAT(full_date, '_', LPAD(hour, 2, '0'))
-- becomes
full_date || '_' || TO_CHAR(hour, '09')
```

---

## Performance Considerations

### Indexes

The schema includes indexes optimized for:
- **Time-based queries**: `idx_dim_time_date`, `idx_dim_time_hour`
- **Grid-based queries**: `idx_dim_grid_coords`, `idx_fact_grid_id`
- **Hotspot detection**: `idx_fact_total_activity`

### Query Optimization Tips

1. **Always join through dimensions** - lets database use indexes effectively
2. **Filter on time first** - reduces fact table scan (time is most selective)
3. **Use analytical functions** for window-based trends
4. **Materialize common aggregations** if querying very large datasets

### Expected Query Times (SQLite, ~1.68M fact rows)

| Query Type | Time | Notes |
|-----------|------|-------|
| Top 10 hotspots | <100ms | Simple aggregation with index |
| Hourly trends | 100-200ms | Group by time dimension |
| Grid drill-down | 50-100ms | Single grid + time filter |
| Full activity sum | 200-500ms | Table scan, no filter |

---

## Troubleshooting

### Issue: "No grids loaded"

```bash
# Verify GeoJSON file exists
ls -la ../data/milano-grid.geojson

# Check for file read errors
python 02_load_dim_grid.py 2>&1 | head -20
```

### Issue: "Orphaned references"

```sql
-- Find grids in facts not in dim_grid
SELECT COUNT(*) FROM fact_network_activity f
WHERE NOT EXISTS (SELECT 1 FROM dim_grid g WHERE g.grid_id = f.grid_id);

-- Find times in facts not in dim_time
SELECT COUNT(*) FROM fact_network_activity f
WHERE NOT EXISTS (SELECT 1 FROM dim_time t WHERE t.time_id = f.time_id);
```

### Issue: "Duplicate time records"

```sql
-- Check for duplicates
SELECT full_date, hour, COUNT(*) FROM dim_time
GROUP BY full_date, hour
HAVING COUNT(*) > 1;
```

---

## Maintenance

### Incremental Loads

To add new dates to the system:

1. Place new parquet files in `report_spark/hourly_grid_summary/date=YYYY-MM-DD/`
2. Run `03_load_activity_data.py` again
3. Script will skip existing dates and load only new data

```python
# The script handles duplicates:
UNIQUE KEY unique_date_hour (full_date, hour)
```

### Refreshing Data

To rebuild from scratch:

```bash
# Delete database
rm telecom_analytics.db

# Recreate
sqlite3 telecom_analytics.db < 01_ddl_create_schema.sql
python 02_load_dim_grid.py
python 03_load_activity_data.py
```

---

## Technical Notes

### Geometry Handling

**Why not store full polygon in facts?**
- Storage: 10,000 grids × 1.68M facts = 16.8B geometry strings (massive)
- Query performance: Geometry parsing overhead on every join
- Solution: Store centroid in dim_grid, use geometry_ref for lookups

**How to retrieve full geometry?**
```python
# Join with GeoJSON in application layer
import json
with open('data/milano-grid.geojson') as f:
    grid_data = json.load(f)
    grid_geometries = {f['properties']['cellId']: f['geometry'] 
                       for f in grid_data['features']}
```

### Sparse vs. Dense Population

**Current approach: Sparse (only observed grids)**
- fact_network_activity: ~1.68M rows (7,250 grids × 168 hours)
- Storage efficient, realistic data

**Alternative: Dense (all grids, all hours)**
- Would be: 10,000 grids × 168 hours = 1.68M rows
- Requires data imputation (0s or nulls for missing grids)
- Better for certain ML workflows

To convert to dense:
```sql
-- Add missing grid-time combinations with 0 activity
INSERT INTO fact_network_activity 
SELECT g.grid_id, t.time_id, 0, 0, 0, 0, 0, 0
FROM dim_grid g
CROSS JOIN dim_time t
WHERE NOT EXISTS (
    SELECT 1 FROM fact_network_activity f
    WHERE f.grid_id = g.grid_id AND f.time_id = t.time_id
);
```

---

## Summary

**Files included:**
- [x] `01_ddl_create_schema.sql` - SQLite star schema
- [x] `02_load_dim_grid.py` - Grid reference loader
- [x] `03_load_activity_data.py` - Parquet to SQLite loader
- [x] `04_mysql_ingestion.py` - MySQL/SQLite ingestion handler ⭐ NEW
- [x] `04_validation_queries.sql` - Validation queries
- [x] `05_mysql_create_tables.sql` - MySQL production tables ⭐ NEW
- [x] `quickstart.py` - Quick-start script
- [x] `README.md` - Complete documentation

**Next steps:**
1. For SQLite development: Run `quickstart.py`
2. For MySQL production: Run `05_mysql_create_tables.sql` then configure Airflow DAG
3. Airflow DAG enhanced with file sensor (5-min check) and mysql_ingest task

---

## Questions?

Refer to sections:
- **MySQL setup**: See "MySQL Production Deployment"
- **Airflow integration**: See "Airflow DAG Integration"
- **Module usage**: See "Module Reference: MySQLDataIngestion"
- **Troubleshooting**: See "Troubleshooting"

