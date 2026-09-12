from fastapi import FastAPI, Depends, HTTPException, Query, Header, APIRouter, Response, UploadFile, File
from sqlalchemy.orm import sessionmaker, Session, declarative_base
from auth import verify_api_key
from datetime import datetime, date, timedelta, timezone
from typing import List, Optional
from sqlalchemy import  Column, Integer, Float, Date, DateTime, String, Index, func
from database import HourlyGridSummary, EnrichedSpatialHourly, GridSummary, DailySummary, get_db
from schemas import (
    GridFeaturesResponse, AlertResponse, Alert, HotspotResponse, Hotspot,
    GridActivityResponse, GridActivity, NetworkSummaryResponse,
    GridGeography, GridGeographyResponse, DailyPeak, WeeklyPeakResponse,
    ModalityHour, ModalityResponse, GridListItem, GridListResponse,
    PredictionResponse,
    HourlyGridRecord, HourlyGridRecordsResponse,
    SpatialHourlyRecord, SpatialHourlyRecordsResponse,
    GridSummaryRecord, GridSummaryRecordsResponse,
    DailySummaryRecord, DailySummaryRecordsResponse,
    AuditLogEntry, AuditLogResponse,
)
import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

import pandas as pd
from rules import AlertAnalyzer
from ml import get_predictor, list_available_models, DEFAULT_MODEL_NAME
import math
import json
import re
import time
import threading
import uuid

from agent import ClaudeNOCAgent, execute_tool
from schemas import ChatRequest, ChatResponse, SaveChatHistoryRequest, ChatHistoryResponse, ChatMessage

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
    active_grids = len({r.grid_id for r in records if r.total_activity > 0})
    
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
    severity: str = Query("HIGH", pattern="^(HIGH|MEDIUM|LOW)$"),
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
        Hotspot(grid_id=r.grid_id, total_activity=r.total_activity, severity=severity, timestamp=effective_time)
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
    ).order_by(HourlyGridSummary.total_activity.desc()).limit(limit * 2).all()

    seen_gids = set()
    unique_rows = []
    for r in rows:
        if r.grid_id not in seen_gids:
            seen_gids.add(r.grid_id)
            unique_rows.append(r)
            if len(unique_rows) >= limit:
                break

    vals = sorted(r.total_activity for r in unique_rows)

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

    grids = [GridListItem(grid_id=r.grid_id, total_activity=r.total_activity, severity=severity_for(r.total_activity)) for r in unique_rows]
    return GridListResponse(as_of=effective_time, total=len(grids), grids=grids)


# =====================================================================
# PREDICTION ENDPOINT — serves the trained LightGBM "next-hour high
# activity" classifier (DataAnalysis/models/lgbm_high_activity_v1.joblib)
# via ml_model.py, which mirrors DataAnalysis/preprocessor.py's feature
# engineering so training and serving stay identical.
# =====================================================================

# Rolling/lag features need >=24 prior hourly rows (see ml_model.py); this
# lookback pulls extra margin so a few missing hours in the source data
# don't push the effective history below that requirement.
_PREDICTION_LOOKBACK_HOURS = 95


@router.get("/predict/models")
def get_available_models():
    """Returns all trained LightGBM models available in /ml/models directory."""
    models = list_available_models()
    return {
        "models": models,
        "default": DEFAULT_MODEL_NAME if DEFAULT_MODEL_NAME in models else (models[0] if models else "")
    }


@router.get("/predict/grid/{grid_id}", response_model=PredictionResponse)
def predict_grid_activity(
    grid_id: int,
    as_of: Optional[datetime] = None,
    model_name: Optional[str] = Query(None, description="Optional model filename from /ml/models"),
    db: Session = Depends(get_db),
):
    """Predicts whether `grid_id` is likely to enter a high-activity state
    (>=1.5x its within-day baseline) in the hour *following* `as_of`, using
    its trailing hourly history up to and including `as_of`."""
    validate_grid_id(grid_id)
    effective_time = resolve_as_of(db, as_of)
    start_time = effective_time - timedelta(hours=_PREDICTION_LOOKBACK_HOURS)

    query = db.query(HourlyGridSummary).filter(
        HourlyGridSummary.grid_id == grid_id,
        HourlyGridSummary.date >= start_time.date(),
        HourlyGridSummary.date <= effective_time.date(),
    )
    df = pd.read_sql(query.statement, query.session.bind)
    if df.empty:
        raise HTTPException(status_code=404, detail="No data found for grid")

    df["timestamp"] = pd.to_datetime(df["date"]) + pd.to_timedelta(df["hour"], unit="h")
    df = df[(df["timestamp"] >= start_time) & (df["timestamp"] <= effective_time)].sort_values("timestamp")
    if df.empty:
        raise HTTPException(status_code=404, detail="No data found in requested window")

    # Map hourly_grid_summary's columns onto the raw schema DataPreprocessor expects.
    raw_df = pd.DataFrame({
        "timestamp": df["timestamp"],
        "grid_id": df["grid_id"],
        "sms_in_count": df["sms_in"],
        "sms_out_count": df["sms_out"],
        "call_in_count": df["call_in"],
        "call_out_count": df["call_out"],
        "internet_usage": df["internet_activity"],
        "total_sms": df["sms_in"] + df["sms_out"],
        "total_calls": df["call_in"] + df["call_out"],
        "total_activity": df["total_activity"],
    })

    model_name_str = model_name if isinstance(model_name, str) and model_name.strip() else None
    predictor = get_predictor(model_name=model_name_str)
    result = predictor.predict_latest(raw_df)

    if result is None:
        raise HTTPException(
            status_code=422,
            detail=(
                f"Not enough trailing history to compute a prediction for grid {grid_id} "
                f"(need at least {predictor.MIN_HISTORY_HOURS}h of prior hourly data)."
            ),
        )

    return PredictionResponse(
        grid_id=grid_id,
        as_of=effective_time,
        feature_timestamp=result["feature_timestamp"],
        probability=float(result["probability"]),
        prediction=int(result["prediction"]),
        risk_label=result["risk_label"],
        threshold=predictor.threshold,
        model_name=predictor.model_name,
        data_points_used=len(df),
        features={col: float(result[col]) for col in predictor.feature_columns if col != "grid_id"},
    )


MATRIX_CACHE_FILE = Path(__file__).resolve().parent / "grid_matrix_cache.json"

@router.get("/predict/matrix")
@router.get("/grid/matrix")
def get_prediction_matrix(db: Session = Depends(get_db)):
    """Returns the precomputed 100x100 predictive grid matrix with model predictions,
    probabilities, and telemetry across all 10,000 grids."""
    if MATRIX_CACHE_FILE.exists():
        try:
            with open(MATRIX_CACHE_FILE, "r", encoding="utf-8") as f:
                content = f.read()
            return Response(content=content, media_type="application/json")
        except Exception as e:
            print(f"Error reading grid_matrix_cache.json: {e}")
    raise HTTPException(status_code=503, detail="Grid matrix cache is not ready.")


# =====================================================================
# DATA EXPLORER ENDPOINTS — filterable/paginated raw rows off each
# backing table, for the "Data" page. One endpoint per table rather than
# one generic endpoint so each gets typed filters/columns that actually
# make sense for it (e.g. `hour` doesn't exist on daily_summary).
# =====================================================================

_MAX_PAGE_SIZE = 500


def _validate_sort(sort_by: str, sort_dir: str, allowed: set, model):
    if sort_by not in allowed:
        raise HTTPException(status_code=400, detail=f"sort_by must be one of: {sorted(allowed)}")
    if sort_dir not in ("asc", "desc"):
        raise HTTPException(status_code=400, detail="sort_dir must be 'asc' or 'desc'")
    col = getattr(model, sort_by)
    return col.desc() if sort_dir == "desc" else col.asc()


def _paginate(query, page: int, page_size: int):
    total = query.count()
    rows = query.offset((page - 1) * page_size).limit(page_size).all()
    return total, rows


_HOURLY_SORT_COLUMNS = {"date", "hour", "grid_id", "total_activity", "sms_in", "sms_out", "call_in", "call_out", "internet_activity"}


@router.get("/data/hourly", response_model=HourlyGridRecordsResponse)
def get_hourly_data(
    grid_id: Optional[int] = None,
    date_from: Optional[date] = None,
    date_to: Optional[date] = None,
    hour_min: Optional[int] = Query(None, ge=0, le=23),
    hour_max: Optional[int] = Query(None, ge=0, le=23),
    min_activity: Optional[float] = None,
    max_activity: Optional[float] = None,
    sort_by: str = "date",
    sort_dir: str = "desc",
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=_MAX_PAGE_SIZE),
    db: Session = Depends(get_db),
):
    """Raw hourly_grid_summary rows — the finest-grained table available,
    one row per (date, hour, grid_id)."""
    query = db.query(HourlyGridSummary)
    if grid_id is not None:
        query = query.filter(HourlyGridSummary.grid_id == grid_id)
    if date_from is not None:
        query = query.filter(HourlyGridSummary.date >= date_from)
    if date_to is not None:
        query = query.filter(HourlyGridSummary.date <= date_to)
    if hour_min is not None:
        query = query.filter(HourlyGridSummary.hour >= hour_min)
    if hour_max is not None:
        query = query.filter(HourlyGridSummary.hour <= hour_max)
    if min_activity is not None:
        query = query.filter(HourlyGridSummary.total_activity >= min_activity)
    if max_activity is not None:
        query = query.filter(HourlyGridSummary.total_activity <= max_activity)

    order = _validate_sort(sort_by, sort_dir, _HOURLY_SORT_COLUMNS, HourlyGridSummary)
    query = query.order_by(order, HourlyGridSummary.id.asc())

    total, rows = _paginate(query, page, page_size)
    records = [
        HourlyGridRecord(
            id=r.id, date=r.date, hour=r.hour, grid_id=r.grid_id,
            sms_in=r.sms_in, sms_out=r.sms_out, call_in=r.call_in, call_out=r.call_out,
            internet_activity=r.internet_activity, total_activity=r.total_activity,
            record_count=r.record_count, loaded_at=r.loaded_at,
        )
        for r in rows
    ]
    return HourlyGridRecordsResponse(total=total, page=page, page_size=page_size, records=records)


_SPATIAL_SORT_COLUMNS = {"date", "hour", "grid_id", "total_activity", "sms_in", "sms_out", "call_in", "call_out", "internet_activity"}


@router.get("/data/spatial", response_model=SpatialHourlyRecordsResponse)
def get_spatial_data(
    grid_id: Optional[int] = None,
    date_from: Optional[date] = None,
    date_to: Optional[date] = None,
    hour_min: Optional[int] = Query(None, ge=0, le=23),
    hour_max: Optional[int] = Query(None, ge=0, le=23),
    min_activity: Optional[float] = None,
    max_activity: Optional[float] = None,
    has_geometry: Optional[bool] = None,
    sort_by: str = "date",
    sort_dir: str = "desc",
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=_MAX_PAGE_SIZE),
    db: Session = Depends(get_db),
):
    """enriched_spatial_hourly rows (activity + geometry provenance). The
    raw `geometry` payload is large/opaque, so this only reports whether
    each row carries real geometry — see /network/grid/{grid_id}/geography
    for the parsed lat/lon."""
    query = db.query(EnrichedSpatialHourly)
    if grid_id is not None:
        query = query.filter(EnrichedSpatialHourly.grid_id == grid_id)
    if date_from is not None:
        query = query.filter(EnrichedSpatialHourly.date >= date_from)
    if date_to is not None:
        query = query.filter(EnrichedSpatialHourly.date <= date_to)
    if hour_min is not None:
        query = query.filter(EnrichedSpatialHourly.hour >= hour_min)
    if hour_max is not None:
        query = query.filter(EnrichedSpatialHourly.hour <= hour_max)
    if min_activity is not None:
        query = query.filter(EnrichedSpatialHourly.total_activity >= min_activity)
    if max_activity is not None:
        query = query.filter(EnrichedSpatialHourly.total_activity <= max_activity)
    if has_geometry is not None:
        query = query.filter(EnrichedSpatialHourly.geometry.isnot(None) if has_geometry else EnrichedSpatialHourly.geometry.is_(None))

    order = _validate_sort(sort_by, sort_dir, _SPATIAL_SORT_COLUMNS, EnrichedSpatialHourly)
    query = query.order_by(order, EnrichedSpatialHourly.id.asc())

    total, rows = _paginate(query, page, page_size)
    records = [
        SpatialHourlyRecord(
            id=r.id, date=r.date, hour=r.hour, grid_id=r.grid_id,
            sms_in=r.sms_in, sms_out=r.sms_out, call_in=r.call_in, call_out=r.call_out,
            internet_activity=r.internet_activity, total_activity=r.total_activity,
            has_geometry=bool(r.geometry), loaded_at=r.loaded_at,
        )
        for r in rows
    ]
    return SpatialHourlyRecordsResponse(total=total, page=page, page_size=page_size, records=records)


_GRID_SUMMARY_SORT_COLUMNS = {"date", "grid_id", "total_activity", "total_sms", "total_calls", "internet_usage", "active_hours"}


@router.get("/data/grid-summary", response_model=GridSummaryRecordsResponse)
def get_grid_summary_data(
    grid_id: Optional[int] = None,
    date_from: Optional[date] = None,
    date_to: Optional[date] = None,
    min_activity: Optional[float] = None,
    max_activity: Optional[float] = None,
    sort_by: str = "date",
    sort_dir: str = "desc",
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=_MAX_PAGE_SIZE),
    db: Session = Depends(get_db),
):
    """grid_summary rows — per-day, per-grid rollup."""
    query = db.query(GridSummary)
    if grid_id is not None:
        query = query.filter(GridSummary.grid_id == grid_id)
    if date_from is not None:
        query = query.filter(GridSummary.date >= date_from)
    if date_to is not None:
        query = query.filter(GridSummary.date <= date_to)
    if min_activity is not None:
        query = query.filter(GridSummary.total_activity >= min_activity)
    if max_activity is not None:
        query = query.filter(GridSummary.total_activity <= max_activity)

    order = _validate_sort(sort_by, sort_dir, _GRID_SUMMARY_SORT_COLUMNS, GridSummary)
    query = query.order_by(order, GridSummary.id.asc())

    total, rows = _paginate(query, page, page_size)
    records = [
        GridSummaryRecord(
            id=r.id, date=r.date, grid_id=r.grid_id, total_sms=r.total_sms, total_calls=r.total_calls,
            internet_usage=r.internet_usage, total_activity=r.total_activity, active_hours=r.active_hours,
            loaded_at=r.loaded_at,
        )
        for r in rows
    ]
    return GridSummaryRecordsResponse(total=total, page=page, page_size=page_size, records=records)


_DAILY_SUMMARY_SORT_COLUMNS = {"date", "total_activity", "total_sms", "total_calls", "internet_usage", "active_grids", "total_records"}


@router.get("/data/daily-summary", response_model=DailySummaryRecordsResponse)
def get_daily_summary_data(
    date_from: Optional[date] = None,
    date_to: Optional[date] = None,
    min_activity: Optional[float] = None,
    max_activity: Optional[float] = None,
    sort_by: str = "date",
    sort_dir: str = "desc",
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=_MAX_PAGE_SIZE),
    db: Session = Depends(get_db),
):
    """daily_summary rows — network-wide per-day rollup."""
    query = db.query(DailySummary)
    if date_from is not None:
        query = query.filter(DailySummary.date >= date_from)
    if date_to is not None:
        query = query.filter(DailySummary.date <= date_to)
    if min_activity is not None:
        query = query.filter(DailySummary.total_activity >= min_activity)
    if max_activity is not None:
        query = query.filter(DailySummary.total_activity <= max_activity)

    order = _validate_sort(sort_by, sort_dir, _DAILY_SUMMARY_SORT_COLUMNS, DailySummary)
    query = query.order_by(order, DailySummary.id.asc())

    total, rows = _paginate(query, page, page_size)
    records = [
        DailySummaryRecord(
            id=r.id, date=r.date, total_sms=r.total_sms, total_calls=r.total_calls,
            internet_usage=r.internet_usage, total_activity=r.total_activity,
            active_grids=r.active_grids, total_records=r.total_records, loaded_at=r.loaded_at,
        )
        for r in rows
    ]
    return DailySummaryRecordsResponse(total=total, page=page, page_size=page_size, records=records)


# =====================================================================
# QUALITY CHECK — the Spark pipeline's file-ingestion audit trail
# (flow/logs/audit_log.json, one JSON object per line), surfaced as a
# filterable/paginated table alongside the DB-backed ones above. Read
# straight off disk (mtime-cached) since this isn't in the database.
# =====================================================================

_AUDIT_LOG_PATH = Path(__file__).resolve().parent.parent / "flow" / "logs" / "audit_log.json"
_audit_log_cache = {"mtime": None, "rows": []}


def _load_audit_log_rows():
    try:
        mtime = _AUDIT_LOG_PATH.stat().st_mtime
    except OSError:
        return []
    if _audit_log_cache["mtime"] == mtime:
        return _audit_log_cache["rows"]

    rows = []
    with open(_AUDIT_LOG_PATH, "r", encoding="utf-8") as f:
        for i, line in enumerate(f, start=1):
            line = line.strip()
            if not line:
                continue
            try:
                entry = json.loads(line)
            except json.JSONDecodeError:
                continue
            entry["id"] = i
            rows.append(entry)

    _audit_log_cache["mtime"] = mtime
    _audit_log_cache["rows"] = rows
    return rows


def _audit_sort_value(row: dict, key: str):
    value = row.get(key)
    if value is not None:
        return value
    if key == "id":
        return 0
    if key == "duration_seconds":
        return -1.0
    if key == "row_count":
        return 0
    return ""


_AUDIT_LOG_SORT_COLUMNS = {"id", "processed_at", "filename", "status", "row_count", "duration_seconds", "reason"}


@router.get("/data/audit-log", response_model=AuditLogResponse)
def get_audit_log_data(
    status: Optional[str] = None,
    filename: Optional[str] = None,
    date_from: Optional[date] = None,
    date_to: Optional[date] = None,
    sort_by: str = "processed_at",
    sort_dir: str = "desc",
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=_MAX_PAGE_SIZE),
):
    """Pipeline ingestion quality-check log — one row per file processing
    attempt (ACCEPTED/REJECTED), with the rejection reason when it failed."""
    rows = _load_audit_log_rows()

    if status:
        rows = [r for r in rows if (r.get("status") or "").upper() == status.upper()]
    if filename:
        needle = filename.lower()
        rows = [r for r in rows if needle in (r.get("filename") or "").lower()]
    if date_from is not None or date_to is not None:
        def _in_range(r):
            ts = r.get("processed_at")
            if not ts:
                return False
            d = datetime.fromisoformat(ts).date()
            if date_from is not None and d < date_from:
                return False
            if date_to is not None and d > date_to:
                return False
            return True
        rows = [r for r in rows if _in_range(r)]

    if sort_by not in _AUDIT_LOG_SORT_COLUMNS:
        raise HTTPException(status_code=400, detail=f"sort_by must be one of: {sorted(_AUDIT_LOG_SORT_COLUMNS)}")
    if sort_dir not in ("asc", "desc"):
        raise HTTPException(status_code=400, detail="sort_dir must be 'asc' or 'desc'")
    rows = sorted(rows, key=lambda r: _audit_sort_value(r, sort_by), reverse=(sort_dir == "desc"))

    total = len(rows)
    start = (page - 1) * page_size
    page_rows = rows[start:start + page_size]

    records = [
        AuditLogEntry(
            id=r["id"],
            filename=r.get("filename") or "",
            status=r.get("status") or "",
            row_count=r.get("row_count") or 0,
            reason=r.get("reason") or r.get("error_message"),
            duration_seconds=r.get("duration_seconds"),
            processed_at=r.get("processed_at"),
        )
        for r in page_rows
    ]

    return AuditLogResponse(total=total, page=page, page_size=page_size, records=records)



CHAT_HISTORY_FILE = Path(__file__).resolve().parent / "chat_history.json"
_chat_history_lock = threading.Lock()


def _load_all_chat_histories() -> dict:
    if not CHAT_HISTORY_FILE.exists():
        return {}
    with _chat_history_lock:
        for attempt in range(3):
            try:
                with open(CHAT_HISTORY_FILE, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    return data if isinstance(data, dict) else {}
            except (PermissionError, OSError) as pe:
                if attempt < 2:
                    time.sleep(0.05 * (attempt + 1))
                    continue
                print(f"Warning: Failed to load chat history from {CHAT_HISTORY_FILE}: {pe}")
                return {}
            except Exception as e:
                print(f"Warning: Failed to load chat history from {CHAT_HISTORY_FILE}: {e}")
                return {}
    return {}


def _save_all_chat_histories(data: dict) -> None:
    with _chat_history_lock:
        temp_file = CHAT_HISTORY_FILE.parent / f"chat_history_{uuid.uuid4().hex[:8]}.tmp"
        try:
            with open(temp_file, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
            
            # Windows file locking retry loop for atomic file replacement
            for attempt in range(5):
                try:
                    temp_file.replace(CHAT_HISTORY_FILE)
                    break
                except (PermissionError, OSError):
                    if attempt < 4:
                        time.sleep(0.05 * (attempt + 1))
                    else:
                        raise
        except Exception as e:
            print(f"Warning: Failed to save chat history to {CHAT_HISTORY_FILE}: {e}")
        finally:
            if temp_file.exists():
                try:
                    temp_file.unlink()
                except Exception:
                    pass


# ---------------------------------------------------------------------------
# NOC Assistant AI Endpoint & JSON File Persistence
# ---------------------------------------------------------------------------
@router.post("/chat", response_model=ChatResponse)
def chat_with_agent(request: ChatRequest, db: Session = Depends(get_db)):
    """
    Passes a user query and NOC evidence context to the Claude AI agent.
    The agent can trigger database tools automatically before responding.
    Automatically persists the conversation into chat_history.json.
    """
    try:
        agent = ClaudeNOCAgent(db=db)
        
        # Convert Pydantic chat history to the format Anthropic expects
        formatted_history = []
        if request.chat_history:
            for msg in request.chat_history:
                formatted_history.append({"role": msg.role, "content": msg.content})
        
        # Format evidence as a JSON string if provided
        evidence_str = ""
        if request.grid_evidence:
            evidence_str = json.dumps(request.grid_evidence, indent=2)

        # Automatically resolve grid_id if known
        grid_id = request.grid_id
        if grid_id is None and request.grid_evidence and "grid_id" in request.grid_evidence:
            grid_id = request.grid_evidence["grid_id"]

        # Get response from Claude with dynamic system prompt context
        chat_output = agent.chat(
            user_message=request.message,
            chat_history=formatted_history,
            context_evidence=evidence_str,
            grid_id=grid_id,
            grid_evidence=request.grid_evidence
        )

        if isinstance(chat_output, dict):
            reply = chat_output.get("reply", "")
            skill_used = chat_output.get("skill_used")
            skills_used = chat_output.get("skills_used") or ([skill_used] if skill_used else [])
            subagents_called = chat_output.get("subagents_called")
            active_agent = chat_output.get("active_agent") or "supervisor"
            specialist_reports = chat_output.get("specialist_reports")
        else:
            reply = str(chat_output)
            skill_used = None
            skills_used = []
            subagents_called = None
            active_agent = None
            specialist_reports = None
        
        reply_ts = datetime.now(timezone.utc).isoformat()

        if grid_id is not None:
            try:
                histories = _load_all_chat_histories()
                grid_key = str(grid_id)
                grid_msgs = list(histories.get(grid_key, []))
                
                # If grid_msgs is empty and client provided previous chat_history, initialize with it
                if not grid_msgs and request.chat_history:
                    grid_msgs = [
                        {
                            "role": m.role,
                            "content": m.content,
                            "timestamp": m.timestamp,
                            "skill_used": getattr(m, "skill_used", None),
                            "skills_used": getattr(m, "skills_used", None),
                            "subagents_called": getattr(m, "subagents_called", None),
                            "specialist_reports": getattr(m, "specialist_reports", None)
                        }
                        for m in request.chat_history
                    ]
                
                grid_msgs.append({
                    "role": "user",
                    "content": request.message,
                    "timestamp": reply_ts
                })
                grid_msgs.append({
                    "role": "assistant",
                    "content": reply,
                    "timestamp": reply_ts,
                    "skill_used": skill_used,
                    "skills_used": skills_used,
                    "subagents_called": subagents_called,
                    "specialist_reports": specialist_reports
                })
                histories[grid_key] = grid_msgs
                _save_all_chat_histories(histories)
            except Exception as hist_err:
                print(f"Warning: Failed to auto-persist chat history: {hist_err}")

        return ChatResponse(
            reply=reply,
            timestamp=reply_ts,
            skill_used=skill_used,
            skills_used=skills_used,
            subagents_called=subagents_called,
            active_agent=active_agent,
            specialist_reports=specialist_reports
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/agents/specialists")
def get_specialist_agents(db: Session = Depends(get_db)):
    """Returns definitions, responsibilities, and restricted toolsets of all specialist subagents."""
    from agent.supervisor import SupervisorAgent
    sup = SupervisorAgent(db=db)
    return {
        "supervisor": {
            "name": "Supervisor Agent",
            "role": "Lead NOC Operations Commander",
            "responsibility": "Coordinates multi-agent investigations, delegates tasks to specialist subagents, and synthesizes multi-tier telemetry and predictions into unified reports.",
            "subagents": ["data_pipeline", "network_analysis", "ml_analysis", "api_agent"]
        },
        "specialists": sup.get_specialist_registry_metadata()
    }


@router.get("/chat/history", response_model=ChatHistoryResponse)
def get_chat_history(grid_id: Optional[int] = Query(None)):
    """
    Load chat history from the backend chat_history.json file.
    If grid_id is specified, returns messages for that grid cell.
    If grid_id is omitted, returns all stored grid chats.
    """
    histories = _load_all_chat_histories()
    if grid_id is not None:
        grid_key = str(grid_id)
        raw_msgs = histories.get(grid_key, [])
        return ChatHistoryResponse(grid_id=grid_id, messages=raw_msgs)
    return ChatHistoryResponse(histories=histories)


@router.post("/chat/history")
def save_chat_history(payload: SaveChatHistoryRequest):
    """
    Save or update chat messages for a specific grid in chat_history.json.
    """
    histories = _load_all_chat_histories()
    grid_key = str(payload.grid_id)
    histories[grid_key] = [
        {
            "role": msg.role,
            "content": msg.content,
            "timestamp": msg.timestamp,
            "skill_used": msg.skill_used,
            "skills_used": msg.skills_used,
        }
        for msg in payload.messages
    ]
    _save_all_chat_histories(histories)
    return {"status": "success", "grid_id": payload.grid_id, "count": len(payload.messages)}


@router.delete("/chat/history")
def clear_chat_history(grid_id: Optional[int] = Query(None)):
    """
    Clear chat history for a specific grid or clear all from chat_history.json.
    """
    histories = _load_all_chat_histories()
    if grid_id is not None:
        grid_key = str(grid_id)
        if grid_key in histories:
            del histories[grid_key]
            _save_all_chat_histories(histories)
        return {"status": "cleared", "grid_id": grid_id}
    else:
        _save_all_chat_histories({})
        return {"status": "all_cleared"}


# =====================================================================
# PIPELINE STATUS, NETWORK GRAIN HEALTH & DIAGNOSTIC ENDPOINTS
# Backing project slash commands: /check-pipeline, /network-health, /test-api, /review-anomaly
# =====================================================================

@router.get("/pipeline/status")
def get_pipeline_status_endpoint(db: Session = Depends(get_db)):
    """
    Returns pipeline ingestion health, audit log summary, staleness,
    and any rejected files/rows. Backs the /check-pipeline slash command.
    """
    from agent.tools import execute_tool
    return execute_tool("get_pipeline_status", {}, db)


@router.get("/pipeline/network-health")
def get_network_health_endpoint(
    target_date: Optional[str] = Query(None, alias="date"),
    db: Session = Depends(get_db)
):
    """
    Runs the grain duplicate check on hourly_grid_summary to verify that
    analytics grain (date, hour, grid_id) is exactly 1 row per cell-hour.
    Backs the /network-health slash command.
    """
    from agent.tools import execute_tool
    args = {"date": target_date} if target_date else {}
    return execute_tool("check_grain_duplicates", args, db)


@router.post("/pipeline/test-api")
def run_pipeline_test_api_endpoint(db: Session = Depends(get_db)):
    """
    Executes the FastAPI API test suite and returns pass/fail metrics.
    Backs the /test-api slash command.
    """
    from agent.tools import execute_tool
    return execute_tool("run_api_test_suite", {}, db)


@router.get("/network/grid/{grid_id}/review-anomaly")
def review_grid_anomaly_endpoint(
    grid_id: int,
    db: Session = Depends(get_db)
):
    """
    Compares the rule alert, classifier output and anomaly score for a grid,
    evaluating agreement/disagreement. Backs the /review-anomaly slash command.
    """
    validate_grid_id(grid_id)
    from agent.tools import execute_tool
    return execute_tool("review_grid_anomaly", {"grid_id": grid_id}, db)


# =====================================================================
# PIPELINE TRACKER — Upload, DAG Status, Logs, History
# Powers the live Pipeline Tracker view in the React frontend.
# =====================================================================

import glob as _glob
import fnmatch as _fnmatch

# Resolve paths relative to the project root (same logic as ingestion_dag.py)
_FLOW_ROOT   = Path(__file__).resolve().parent.parent / "flow"
_LANDING_DIR  = _FLOW_ROOT / "data" / "landing"
_PROCESSING_DIR = _FLOW_ROOT / "data" / "processing"
_STAGING_DIR  = _FLOW_ROOT / "data" / "_staging"
_RAW_DIR      = _FLOW_ROOT / "data" / "raw"
_REJECTED_DIR = _FLOW_ROOT / "data" / "rejected"
_LOG_DIR      = _FLOW_ROOT / "logs"
_AUDIT_LOG    = _LOG_DIR / "audit_log.json"
_PIPELINE_LOG = _LOG_DIR / "telecom_pipeline.log"
_FILE_PATTERN = "sms-call-internet-mi-*.csv"

# Ensure landing dir exists
_LANDING_DIR.mkdir(parents=True, exist_ok=True)


def _scan_dir_for_pattern(directory: Path, pattern: str = _FILE_PATTERN) -> list:
    """Return list of matching filenames in a directory."""
    if not directory.exists():
        return []
    return [p.name for p in directory.iterdir() if _fnmatch.fnmatch(p.name, pattern)]


def _infer_dag_stage() -> dict:
    """
    Infer current DAG execution stage by scanning file locations.
    Returns a dict with keys: stage, active_files, progress_pct, stage_label.
    """
    landing   = _scan_dir_for_pattern(_LANDING_DIR)
    processing = _scan_dir_for_pattern(_PROCESSING_DIR)
    staging_clean = list((_STAGING_DIR / "clean").glob("*")) if (_STAGING_DIR / "clean").exists() else []
    staging_mysql = list((_STAGING_DIR / "mysql").glob("*")) if (_STAGING_DIR / "mysql").exists() else []

    if staging_mysql:
        stage = "mysql_ingesting"
        label = "MySQL Ingest"
        pct   = 85
        active = [p.name for p in staging_mysql]
    elif staging_clean:
        stage = "spark_processing"
        label = "Spark Process"
        pct   = 65
        active = [p.name for p in staging_clean]
    elif processing:
        stage = "validating"
        label = "Validate"
        pct   = 40
        active = processing
    elif landing:
        stage = "ingesting"
        label = "Ingest"
        pct   = 20
        active = landing
    else:
        stage = "idle"
        label = "Idle — Waiting for Files"
        pct   = 0
        active = []

    return {
        "stage": stage,
        "stage_label": label,
        "progress_pct": pct,
        "active_files": active,
        "landing_count": len(landing),
        "processing_count": len(processing),
    }


@router.post("/pipeline/upload")
async def upload_pipeline_files(
    files: list[UploadFile] = File(...),
):
    """
    Accept one or more CSV files, validate filename against the DAG pattern
    `sms-call-internet-mi-*.csv`, and write accepted files to the landing zone.
    Returns per-file results so the frontend can show granular status.
    """
    results = []
    for upload in files:
        filename = upload.filename or ""
        if not _fnmatch.fnmatch(filename, _FILE_PATTERN):
            results.append({
                "filename": filename,
                "status": "rejected",
                "reason": f"Filename must match pattern '{_FILE_PATTERN}'. "
                          f"Expected format: sms-call-internet-mi-YYYY-MM-DD.csv",
            })
            continue

        dest = _LANDING_DIR / filename
        try:
            content = await upload.read()
            if len(content) == 0:
                results.append({"filename": filename, "status": "rejected", "reason": "File is empty."})
                continue
            dest.write_bytes(content)
            results.append({
                "filename": filename,
                "status": "accepted",
                "size_bytes": len(content),
                "destination": str(dest),
            })
        except Exception as exc:
            results.append({"filename": filename, "status": "error", "reason": str(exc)})

    accepted = sum(1 for r in results if r["status"] == "accepted")
    return {"uploaded": len(files), "accepted": accepted, "files": results}


@router.get("/pipeline/dag/status")
def get_dag_status():
    """
    Infer the current Airflow DAG execution stage by scanning file locations
    across landing / processing / _staging / raw directories.  No Airflow
    REST API credentials required.
    """
    return _infer_dag_stage()


@router.get("/pipeline/dag/logs")
def get_dag_logs(lines: int = Query(200, ge=10, le=2000)):
    """
    Return the last `lines` lines of the pipeline log file so the frontend
    can display a live task log terminal.
    """
    log_lines = []
    if _PIPELINE_LOG.exists():
        try:
            with open(_PIPELINE_LOG, "r", encoding="utf-8", errors="replace") as fh:
                all_lines = fh.readlines()
                log_lines = [l.rstrip("\n") for l in all_lines[-lines:]]
        except Exception as exc:
            log_lines = [f"[error reading log] {exc}"]
    else:
        log_lines = ["[pipeline log not found — DAG has not run yet]"]

    return {
        "log_file": str(_PIPELINE_LOG),
        "lines": log_lines,
        "total_lines": len(log_lines),
    }


@router.get("/pipeline/history")
def get_pipeline_history(limit: int = Query(100, ge=1, le=500)):
    """
    Read the audit_log.json (newline-delimited JSON) and return processed file
    history sorted newest-first.  Used by the History side-panel in the UI.
    """
    entries = []
    if _AUDIT_LOG.exists():
        try:
            with open(_AUDIT_LOG, "r", encoding="utf-8", errors="replace") as fh:
                for raw_line in fh:
                    line = raw_line.strip()
                    if not line:
                        continue
                    try:
                        entries.append(json.loads(line))
                    except json.JSONDecodeError:
                        pass
        except Exception as exc:
            return {"entries": [], "error": str(exc)}

    # Sort newest first, then cap
    entries.sort(key=lambda e: e.get("processed_at", ""), reverse=True)
    return {"entries": entries[:limit], "total": len(entries)}
