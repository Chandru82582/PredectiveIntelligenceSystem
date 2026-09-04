from fastapi import FastAPI, Depends, HTTPException, Query, Header, APIRouter
from sqlalchemy.orm import sessionmaker, Session, declarative_base
from auth import verify_api_key
from datetime import datetime, date, timedelta
from typing import List, Optional
from sqlalchemy import  Column, Integer, Float, Date, DateTime, String, Index, func
from database import HourlyGridSummary, EnrichedSpatialHourly, get_db
from schemas import (
    GridFeaturesResponse, AlertResponse, Alert, HotspotResponse, Hotspot,
    GridActivityResponse, GridActivity, NetworkSummaryResponse,
    GridGeography, GridGeographyResponse, DailyPeak, WeeklyPeakResponse,
    ModalityHour, ModalityResponse, GridListItem, GridListResponse,
)
import pandas as pd
from rules import AlertAnalyzer
import math
import json
import re
import time

router = APIRouter(dependencies=[Depends(verify_api_key)])

# ---------------------------------------------------------------------------
# Lightweight in-process TTL cache
# ---------------------------------------------------------------------------
# Every request was re-querying MAX(date, hour) to resolve `as_of`, and every
# geometry lookup was hitting `enriched_spatial_hourly` again even though
# grid geometry never changes and `as_of` only moves forward once per batch
# ingestion. This was the main source of "every click re-syncs slowly" —
# caching these two things cuts most of the redundant round trips without
# touching response shapes.
_AS_OF_TTL_SECONDS = 30
_as_of_cache = {"value": None, "expires": 0.0}
_geometry_cache = {}  # grid_id -> {"latitude", "longitude", "sector_label", "source", "polygon"}


def _cached_resolve_as_of(db: Session) -> datetime:
    now = time.monotonic()
    if _as_of_cache["value"] is not None and now < _as_of_cache["expires"]:
        return _as_of_cache["value"]
    result = db.query(HourlyGridSummary.date, HourlyGridSummary.hour).order_by(
        HourlyGridSummary.date.desc(), HourlyGridSummary.hour.desc()
    ).first()
    value = datetime.utcnow() if not result or not result[0] else datetime(result[0].year, result[0].month, result[0].day, result[1])
    _as_of_cache["value"] = value
    _as_of_cache["expires"] = now + _AS_OF_TTL_SECONDS
    return value

# ---------------------------------------------------------------------------
# Milan grid geometry
# ---------------------------------------------------------------------------
# The `enriched_spatial_hourly.geometry` column *may* carry real per-cell
# geometry (GeoJSON or WKT) from the Spark spatial join. Where it doesn't
# (or the table isn't populated yet), we fall back to a deterministic
# centroid/square computed from grid_id. Bounding box and cell step below
# are calibrated against a real sample cell from that column (~235m square
# cells, 100x100 lattice), so computed and real geometry line up closely.
MILAN_LAT_MIN, MILAN_LAT_MAX = 45.3529, 45.5649
MILAN_LON_MIN, MILAN_LON_MAX = 9.0115, 9.3115
GRID_DIM = 100  # 100 x 100 = 10,000 cells, matching the 1-10000 grid_id range
LAT_STEP = (MILAN_LAT_MAX - MILAN_LAT_MIN) / GRID_DIM
LON_STEP = (MILAN_LON_MAX - MILAN_LON_MIN) / GRID_DIM


def compute_grid_centroid(grid_id: int):
    idx = grid_id - 1
    col = idx % GRID_DIM
    row = idx // GRID_DIM
    lon = MILAN_LON_MIN + (col + 0.5) * LON_STEP
    lat = MILAN_LAT_MIN + (row + 0.5) * LAT_STEP
    return round(lat, 6), round(lon, 6)


def compute_grid_polygon(grid_id: int):
    """[lat, lon] ring for a computed cell, matching the real geometry's
    footprint so the map can draw a consistent square regardless of source."""
    lat, lon = compute_grid_centroid(grid_id)
    dlat, dlon = LAT_STEP / 2, LON_STEP / 2
    return [
        [round(lat - dlat, 6), round(lon - dlon, 6)],
        [round(lat - dlat, 6), round(lon + dlon, 6)],
        [round(lat + dlat, 6), round(lon + dlon, 6)],
        [round(lat + dlat, 6), round(lon - dlon, 6)],
    ]


def sector_label_for(grid_id: int) -> str:
    """Internal ops label (not a real place name) so the UI can group cells."""
    idx = grid_id - 1
    row, col = idx // GRID_DIM, idx % GRID_DIM
    zone_row = min(row // (GRID_DIM // 4), 3)
    zone_col = min(col // (GRID_DIM // 4), 3)
    return f"Sector {'ABCD'[zone_row]}{zone_col + 1}"


_WKT_POINT_RE = re.compile(r"POINT\s*\(\s*([-\d.]+)\s+([-\d.]+)\s*\)", re.IGNORECASE)


def parse_geometry_centroid(geom_str: str):
    """Best-effort centroid extraction from a stored geometry string.
    Supports GeoJSON Point/Polygon and WKT POINT. Returns None on failure
    so callers can fall back to the computed grid centroid."""
    if not geom_str:
        return None
    try:
        geo = json.loads(geom_str)
        gtype = geo.get("type")
        coords = geo.get("coordinates")
        if gtype == "Point" and coords:
            lon, lat = coords[0], coords[1]
            return round(lat, 6), round(lon, 6)
        if gtype == "Polygon" and coords:
            ring = coords[0]
            lons = [c[0] for c in ring]
            lats = [c[1] for c in ring]
            return round(sum(lats) / len(lats), 6), round(sum(lons) / len(lons), 6)
    except (json.JSONDecodeError, TypeError, AttributeError, IndexError, KeyError):
        pass
    match = _WKT_POINT_RE.search(geom_str)
    if match:
        lon, lat = float(match.group(1)), float(match.group(2))
        return round(lat, 6), round(lon, 6)
    return None


def parse_geometry_polygon(geom_str: str):
    """Extract a [lat, lon]-ordered ring (Leaflet convention) from a stored
    GeoJSON Polygon, e.g. {"type":"Polygon","coordinates":[[[lon,lat],...]]}.
    Returns None if the geometry isn't a polygon or fails to parse."""
    if not geom_str:
        return None
    try:
        geo = json.loads(geom_str)
        if geo.get("type") == "Polygon" and geo.get("coordinates"):
            ring = geo["coordinates"][0]
            return [[round(c[1], 6), round(c[0], 6)] for c in ring]
    except (json.JSONDecodeError, TypeError, AttributeError, IndexError, KeyError):
        pass
    return None


def _resolve_geography(db: Session, grid_id: int) -> dict:
    """Cached geography lookup — grid geometry is static reference data, so
    once resolved for a grid_id it never needs to be queried again."""
    if grid_id in _geometry_cache:
        return _geometry_cache[grid_id]

    record = (
        db.query(EnrichedSpatialHourly.geometry)
        .filter(EnrichedSpatialHourly.grid_id == grid_id, EnrichedSpatialHourly.geometry.isnot(None))
        .first()
    )
    lat = lon = polygon = None
    source = "computed"
    if record and record[0]:
        centroid = parse_geometry_centroid(record[0])
        polygon = parse_geometry_polygon(record[0])
        if centroid:
            lat, lon = centroid
            source = "geometry"
    if lat is None:
        lat, lon = compute_grid_centroid(grid_id)
    if polygon is None:
        polygon = compute_grid_polygon(grid_id)

    result = {"latitude": lat, "longitude": lon, "sector_label": sector_label_for(grid_id), "source": source, "polygon": polygon}
    _geometry_cache[grid_id] = result
    return result

def resolve_as_of(db: Session, provided_as_of: Optional[datetime] = None) -> datetime:
    """Resolves dynamic 'as_of' date, defaulting to max DB timestamp (cached
    for _AS_OF_TTL_SECONDS since this is queried on almost every request)."""
    if provided_as_of:
        return provided_as_of
    return _cached_resolve_as_of(db)


def validate_grid_id(grid_id: int):
    """Ensure grid_id follows the 1-10000 boundary constraints."""
    if grid_id < 1 or grid_id > 10000:
        raise HTTPException(status_code=404, detail=f"Grid ID {grid_id} not found or out of bounds (1-10000).")

@router.get("/network/summary", response_model=NetworkSummaryResponse)
def get_network_summary(as_of: Optional[datetime] = None, db: Session = Depends(get_db)):
    effective_time = resolve_as_of(db, as_of)
    d, h = effective_time.date(), effective_time.hour
    
    records = db.query(HourlyGridSummary).filter(
        HourlyGridSummary.date == d, HourlyGridSummary.hour == h
    ).all()
    
    total_act = sum(r.total_activity for r in records)
    active_grids = len([r for r in records if r.total_activity > 0])
    
    # Peak hour across the current day
    day_records = db.query(
        HourlyGridSummary.hour, func.sum(HourlyGridSummary.total_activity).label("hr_total")
    ).filter(HourlyGridSummary.date == d).group_by(HourlyGridSummary.hour).all()
    
    peak_hour = max(day_records, key=lambda x: x[1])[0] if day_records else h

    # Top grid query matching:
    # SELECT grid_id FROM hourly_grid_summary WHERE total_activity = (SELECT MAX(total_activity) FROM hourly_grid_summary);
    top_grid_subquery = db.query(func.max(HourlyGridSummary.total_activity)).scalar_subquery()
    top_grid_record = db.query(HourlyGridSummary.grid_id).filter(
        HourlyGridSummary.total_activity == top_grid_subquery
    ).first()
    top_grid = top_grid_record[0] if top_grid_record else 0

    return NetworkSummaryResponse(
        total_activity=total_act,
        active_grids=active_grids,
        peak_hour=peak_hour,
        top_grid=top_grid,
        as_of=effective_time
    )

@router.get("/network/grid/{grid_id}", response_model=GridActivityResponse)
def get_grid_timeseries(
    grid_id: int, 
    as_of: Optional[datetime] = None, 
    date: Optional[date] = None,
    hour: Optional[int] = None,
    db: Session = Depends(get_db)
):
    validate_grid_id(grid_id)
    effective_time = resolve_as_of(db, as_of)
    
    # Calculate 24-hour lookback window based on requirements
    start_time = effective_time - timedelta(hours=23)
    
    # Filter by date range in SQL rather than pulling the grid's entire
    # history into pandas — on a multi-month table this is the difference
    # between scanning a few hundred rows and the whole table every click.
    sql_start_date = date if date is not None else start_time.date()
    sql_end_date = date if date is not None else effective_time.date()
    query = db.query(HourlyGridSummary).filter(
        HourlyGridSummary.grid_id == grid_id,
        HourlyGridSummary.date >= sql_start_date,
        HourlyGridSummary.date <= sql_end_date,
    )
    df = pd.read_sql(query.statement, query.session.bind)
    
    if df.empty:
        raise HTTPException(status_code=404, detail="No data found for grid")
    
    df["timestamp"] = pd.to_datetime(df["date"]) + pd.to_timedelta(df["hour"], unit='h')
    
    # Handle optional date/hour filters, otherwise use default trailing 24h window
    if date is not None:
        mask = df["date"] == date
        if hour is not None:
            mask &= (df["hour"] == hour)
        df = df[mask]
    else:
        df = df[(df["timestamp"] >= start_time) & (df["timestamp"] <= effective_time)]
        
    df = df.sort_values("timestamp")
    
    timeseries = []
    for _, row in df.iterrows():
        timeseries.append(GridActivity(
            timestamp=row["timestamp"],
            sms_activity=row["sms_in"] + row["sms_out"],
            call_activity=row["call_in"] + row["call_out"],
            internet_activity=row["internet_activity"],
            total_activity=row["total_activity"]
        ))
        
    return GridActivityResponse(grid_id=grid_id, as_of=effective_time, timeseries=timeseries)

@router.get("/network/hotspots", response_model=HotspotResponse)
def get_hotspots(
    limit: int = 10,
    severity: str = Query("HIGH", regex="^(HIGH|MEDIUM|LOW)$"),
    as_of: Optional[datetime] = None,
    db: Session = Depends(get_db)
):
    effective_time = resolve_as_of(db, as_of)
    d, h = effective_time.date(), effective_time.hour
    
    # A generic interpretation of "hotspot" based on top activity for the hour
    records = db.query(HourlyGridSummary).filter(
        HourlyGridSummary.date == d, HourlyGridSummary.hour == h
    ).order_by(HourlyGridSummary.total_activity.desc()).limit(limit).all()
    
    hotspots = [
        Hotspot(grid_id=r.grid_id, total_activity=r.total_activity, severity=severity) 
        for r in records
    ]
    return HotspotResponse(as_of=effective_time, hotspots=hotspots)

@router.get("/network/alerts", response_model=AlertResponse)
def get_alerts(
    limit: int = Query(50, ge=1, le=1000),
    severity: Optional[str] = None,
    as_of: Optional[datetime] = None,
    db: Session = Depends(get_db)
):
    effective_time = resolve_as_of(db, as_of)
    
    # Extract trailing 48 hours to ensure baseline logic works across days
    start_time = effective_time - timedelta(hours=48)
    
    # Load into dataframe for the provided rule engine — filtered by date
    # in SQL first so we don't pull every grid's entire history every call.
    query = db.query(
        HourlyGridSummary.grid_id, 
        HourlyGridSummary.date, 
        HourlyGridSummary.hour, 
        HourlyGridSummary.total_activity
    ).filter(
        HourlyGridSummary.date >= start_time.date(),
        HourlyGridSummary.date <= effective_time.date(),
    )
    df = pd.read_sql(query.statement, query.session.bind)
    if df.empty:
        return AlertResponse(as_of=effective_time, alerts=[])
        
    df["hour_timestamp"] = pd.to_datetime(df["date"]) + pd.to_timedelta(df["hour"], unit='h')
    df = df[(df["hour_timestamp"] >= start_time) & (df["hour_timestamp"] <= effective_time)]
    
    analyzer = AlertAnalyzer(df)
    alert_df = analyzer.alert_report()
    
    if alert_df.empty:
        return AlertResponse(as_of=effective_time, alerts=[])
    
    # Filter by time to match exactly the requested `as_of` unless we want historical
    # We will return the alerts for the effective timestamp window
    latest_alerts = alert_df[alert_df["timestamp"] == effective_time]
    
    if severity:
        # Pseudo severity mapping from alert type
        sev_map = {"HIGH": "HIGH_ACTIVITY", "MEDIUM": "ACTIVITY_SPIKE", "LOW": "ACTIVITY_DROP"}
        target_type = sev_map.get(severity.upper())
        if target_type:
            latest_alerts = latest_alerts[latest_alerts["alert_type"] == target_type]
            
    latest_alerts = latest_alerts.head(limit)
    
    alerts = []
    for _, row in latest_alerts.iterrows():
        alerts.append(Alert(
            grid_id=row["grid_id"],
            timestamp=row["timestamp"],
            alert_type=row["alert_type"],
            current_activity=row["current_activity"],
            baseline_activity=row["baseline_activity"],
            reason=row["reason"]
        ))
        
    return AlertResponse(as_of=effective_time, alerts=alerts)

@router.get("/network/grid/{grid_id}/features", response_model=GridFeaturesResponse)
def get_grid_features(
    grid_id: int, 
    as_of: Optional[datetime] = None, 
    db: Session = Depends(get_db)
):
    validate_grid_id(grid_id)
    effective_time = resolve_as_of(db, as_of)
    start_time = effective_time - timedelta(hours=48) # 2 days of data for features
    
    query = db.query(HourlyGridSummary).filter(
        HourlyGridSummary.grid_id == grid_id,
        HourlyGridSummary.date >= start_time.date(),
        HourlyGridSummary.date <= effective_time.date(),
    )
    df = pd.read_sql(query.statement, query.session.bind)
    
    if df.empty:
        raise HTTPException(status_code=404, detail="Grid feature data not found")
        
    df["timestamp"] = pd.to_datetime(df["date"]) + pd.to_timedelta(df["hour"], unit='h')
    df = df[(df["timestamp"] >= start_time) & (df["timestamp"] <= effective_time)]
    
    if df.empty:
        raise HTTPException(status_code=404, detail="Grid feature data not found for time window")
        
    avg_activity = df["total_activity"].mean()
    active_hours = int((df["total_activity"] > 0).sum())
    max_act = df["total_activity"].max()
    peak_ratio = (max_act / avg_activity) if avg_activity > 0 else 0.0
    variability = df["total_activity"].std()
    
    if math.isnan(variability):
        variability = 0.0
        
    total_sum = df["total_activity"].sum()
    internet_sum = df["internet_activity"].sum()
    internet_share = (internet_sum / total_sum) if total_sum > 0 else 0.0
    
    # Activity Growth: Last 12 hrs vs Prev 12 hrs
    mid_point = effective_time - timedelta(hours=12)
    recent_avg = df[df["timestamp"] > mid_point]["total_activity"].mean()
    past_avg = df[df["timestamp"] <= mid_point]["total_activity"].mean()
    
    if pd.isna(recent_avg): recent_avg = 0
    if pd.isna(past_avg) or past_avg == 0:
        activity_growth = 0.0
    else:
        activity_growth = float((recent_avg - past_avg) / past_avg)
    
    return GridFeaturesResponse(
        grid_id=grid_id,
        avg_activity=float(avg_activity),
        activity_growth=activity_growth,
        active_hours=active_hours,
        peak_ratio=float(peak_ratio),
        variability=float(variability),
        internet_share=float(internet_share),
        feature_timestamp=effective_time,
        data_quality="HIGH" if len(df) > 12 else "LOW"
    )

# =====================================================================
# NEW ENDPOINTS — added to support the spatial map, week-view dial,
# directional (in/out) modality charts, and the cell quick-switcher.
# None of this data was previously exposed by the API.
# =====================================================================

@router.get("/network/grid/{grid_id}/geography", response_model=GridGeography)
def get_grid_geography(grid_id: int, db: Session = Depends(get_db)):
    """Single-cell lat/lon centroid + real/derived polygon + ops sector
    label. Cached in-process since grid geometry is static reference data —
    repeated navigation to the same grid no longer re-queries the DB."""
    validate_grid_id(grid_id)
    geo = _resolve_geography(db, grid_id)
    return GridGeography(grid_id=grid_id, **geo)


@router.get("/network/grids/geography", response_model=GridGeographyResponse)
def get_grids_geography(
    grid_ids: Optional[str] = Query(None, description="Comma-separated grid_id list; omit for all grids active at as_of"),
    as_of: Optional[datetime] = None,
    db: Session = Depends(get_db),
):
    """Bulk lat/lon + polygon lookup, used to plot the heatmap and hotspot
    cards in one call. Per-grid results are cached, so only grids not yet
    seen this process lifetime trigger a DB lookup."""
    effective_time = resolve_as_of(db, as_of)

    if grid_ids:
        try:
            ids = [int(g) for g in grid_ids.split(",") if g.strip()]
        except ValueError:
            raise HTTPException(status_code=400, detail="grid_ids must be a comma-separated list of integers")
    else:
        d, h = effective_time.date(), effective_time.hour
        rows = db.query(HourlyGridSummary.grid_id).filter(
            HourlyGridSummary.date == d, HourlyGridSummary.hour == h
        ).all()
        ids = [r[0] for r in rows]

    # Only hit the DB for grid_ids we haven't resolved before.
    uncached = [gid for gid in ids if gid not in _geometry_cache]
    if uncached:
        geo_rows = db.query(EnrichedSpatialHourly.grid_id, EnrichedSpatialHourly.geometry).filter(
            EnrichedSpatialHourly.grid_id.in_(uncached), EnrichedSpatialHourly.geometry.isnot(None)
        ).all()
        geom_by_id = {}
        for gid, geom in geo_rows:
            if gid not in geom_by_id and geom:
                geom_by_id[gid] = geom
        for gid in uncached:
            geom = geom_by_id.get(gid)
            lat = lon = polygon = None
            source = "computed"
            if geom:
                centroid = parse_geometry_centroid(geom)
                polygon = parse_geometry_polygon(geom)
                if centroid:
                    lat, lon = centroid
                    source = "geometry"
            if lat is None:
                lat, lon = compute_grid_centroid(gid)
            if polygon is None:
                polygon = compute_grid_polygon(gid)
            _geometry_cache[gid] = {"latitude": lat, "longitude": lon, "sector_label": sector_label_for(gid), "source": source, "polygon": polygon}

    grids = [GridGeography(grid_id=gid, **_geometry_cache[gid]) for gid in ids]
    return GridGeographyResponse(as_of=effective_time, grids=grids)


@router.get("/network/grid/{grid_id}/weekly-peak", response_model=WeeklyPeakResponse)
def get_weekly_peak(grid_id: int, as_of: Optional[datetime] = None, db: Session = Depends(get_db)):
    """Trailing 7-day peak-hour-per-day series for the Peak Hour Dial's
    'Week View' horizon ribbon, including drift vs the trailing average."""
    validate_grid_id(grid_id)
    effective_time = resolve_as_of(db, as_of)
    start_date = effective_time.date() - timedelta(days=6)

    query = db.query(HourlyGridSummary).filter(
        HourlyGridSummary.grid_id == grid_id,
        HourlyGridSummary.date >= start_date,
        HourlyGridSummary.date <= effective_time.date(),
    )
    df = pd.read_sql(query.statement, query.session.bind)
    if df.empty:
        raise HTTPException(status_code=404, detail="No data found for grid in trailing 7-day window")

    daily = []
    for d, group in df.groupby("date"):
        hour_totals = group.groupby("hour")["total_activity"].sum()
        if hour_totals.empty:
            continue
        daily.append({
            "date": d,
            "day_of_week": pd.Timestamp(d).dayofweek,
            "peak_hour": int(hour_totals.idxmax()),
            "peak_activity": float(hour_totals.max()),
        })
    if not daily:
        raise HTTPException(status_code=404, detail="No peak-hour data available for this window")

    daily.sort(key=lambda x: x["date"])
    avg_peak_hour = sum(x["peak_hour"] for x in daily) / len(daily)

    days = [
        DailyPeak(
            date=x["date"], day_of_week=x["day_of_week"], peak_hour=x["peak_hour"],
            peak_activity=x["peak_activity"], delta_hours=round(x["peak_hour"] - avg_peak_hour, 2),
        )
        for x in daily
    ]
    return WeeklyPeakResponse(grid_id=grid_id, as_of=effective_time, trailing_avg_peak_hour=round(avg_peak_hour, 2), days=days)


@router.get("/network/grid/{grid_id}/modality", response_model=ModalityResponse)
def get_grid_modality(
    grid_id: int,
    as_of: Optional[datetime] = None,
    date: Optional[date] = None,
    hours: int = Query(24, ge=1, le=168, description="Trailing window size in hours (ignored when `date` is set)"),
    db: Session = Depends(get_db),
):
    """Directional sms_in/sms_out/call_in/call_out breakdown per hour.
    /network/grid/{grid_id} only exposes combined sms/call totals, which
    is enough for the stacked modality area but not for the diverging
    inbound-vs-outbound bar chart — this fills that gap. Accepts the same
    `date` override as the timeseries endpoint for historical analysis."""
    validate_grid_id(grid_id)
    effective_time = resolve_as_of(db, as_of)
    start_time = effective_time - timedelta(hours=hours - 1)

    sql_start_date = date if date is not None else start_time.date()
    sql_end_date = date if date is not None else effective_time.date()
    query = db.query(HourlyGridSummary).filter(
        HourlyGridSummary.grid_id == grid_id,
        HourlyGridSummary.date >= sql_start_date,
        HourlyGridSummary.date <= sql_end_date,
    )
    df = pd.read_sql(query.statement, query.session.bind)
    if df.empty:
        raise HTTPException(status_code=404, detail="No data found for grid")

    df["timestamp"] = pd.to_datetime(df["date"]) + pd.to_timedelta(df["hour"], unit="h")
    if date is not None:
        df = df[df["date"] == date].sort_values("timestamp")
    else:
        df = df[(df["timestamp"] >= start_time) & (df["timestamp"] <= effective_time)].sort_values("timestamp")
    if df.empty:
        raise HTTPException(status_code=404, detail="No data found in requested window")

    hours_out = [
        ModalityHour(
            timestamp=row["timestamp"], sms_in=row["sms_in"], sms_out=row["sms_out"],
            call_in=row["call_in"], call_out=row["call_out"], internet_activity=row["internet_activity"],
        )
        for _, row in df.iterrows()
    ]
    return ModalityResponse(grid_id=grid_id, as_of=effective_time, hours=hours_out)


@router.get("/network/grids", response_model=GridListResponse)
def list_grids(
    as_of: Optional[datetime] = None,
    limit: int = Query(500, ge=1, le=10000),
    db: Session = Depends(get_db),
):
    """Flat list of active grids with a computed severity band, used for
    the App-level cell quick-switcher / search box."""
    effective_time = resolve_as_of(db, as_of)
    d, h = effective_time.date(), effective_time.hour

    rows = db.query(HourlyGridSummary).filter(
        HourlyGridSummary.date == d, HourlyGridSummary.hour == h
    ).order_by(HourlyGridSummary.total_activity.desc()).limit(limit).all()

    vals = sorted(r.total_activity for r in rows)

    def severity_for(v: float) -> str:
        if not vals:
            return "NORMAL"
        p75 = vals[int(len(vals) * 0.75)] if len(vals) > 3 else max(vals)
        p45 = vals[int(len(vals) * 0.45)] if len(vals) > 3 else 0
        if v > p75:
            return "HIGH"
        if v > p45:
            return "MEDIUM"
        return "NORMAL"

    grids = [GridListItem(grid_id=r.grid_id, total_activity=r.total_activity, severity=severity_for(r.total_activity)) for r in rows]
    return GridListResponse(as_of=effective_time, total=len(grids), grids=grids)
