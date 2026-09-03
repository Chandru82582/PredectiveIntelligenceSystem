from fastapi import FastAPI, Depends, HTTPException, Query, Header, APIRouter
from sqlalchemy.orm import sessionmaker, Session, declarative_base
from auth import verify_api_key
from datetime import datetime, date, timedelta
from typing import List, Optional
from sqlalchemy import  Column, Integer, Float, Date, DateTime, String, Index, func
from database import HourlyGridSummary, get_db
from schemas import GridFeaturesResponse, AlertResponse, Alert, HotspotResponse, Hotspot, GridActivityResponse, GridActivity, NetworkSummaryResponse
import pandas as pd
from rules import AlertAnalyzer
import math

router = APIRouter(dependencies=[Depends(verify_api_key)])

def resolve_as_of(db: Session, provided_as_of: Optional[datetime] = None) -> datetime:
    """Resolves dynamic 'as_of' date, defaulting to max DB timestamp."""
    if provided_as_of:
        return provided_as_of
    
    # Query latest date and hour together to reflect the true MAX(timestamp) in the analytics layer
    result = db.query(HourlyGridSummary.date, HourlyGridSummary.hour).order_by(
        HourlyGridSummary.date.desc(), HourlyGridSummary.hour.desc()
    ).first()
    if not result or not result[0]:
        # Fallback if DB is completely empty
        return datetime.utcnow()
    
    max_date, max_hour = result
    # Construct a datetime from the correlated max date and hour
    return datetime(max_date.year, max_date.month, max_date.day, max_hour)


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
    
    # Using Pandas for easy filtering and grouping across day boundaries
    query = db.query(HourlyGridSummary).filter(HourlyGridSummary.grid_id == grid_id)
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
    
    # Load into dataframe for the provided rule engine
    query = db.query(
        HourlyGridSummary.grid_id, 
        HourlyGridSummary.date, 
        HourlyGridSummary.hour, 
        HourlyGridSummary.total_activity
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
    
    query = db.query(HourlyGridSummary).filter(HourlyGridSummary.grid_id == grid_id)
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
