from pydantic import BaseModel, Field
from datetime import datetime, date, timedelta
from typing import List, Optional



class NetworkSummaryResponse(BaseModel):
    total_activity: float
    active_grids: int
    peak_hour: int
    top_grid: int
    as_of: datetime
    
class GridActivity(BaseModel):
    timestamp: datetime
    sms_activity: float
    call_activity: float
    internet_activity: float
    total_activity: float

class GridActivityResponse(BaseModel):
    grid_id: int
    as_of: datetime
    timeseries: List[GridActivity]

class Hotspot(BaseModel):
    grid_id: int
    total_activity: float
    severity: str

class HotspotResponse(BaseModel):
    as_of: datetime
    hotspots: List[Hotspot]

class Alert(BaseModel):
    grid_id: int
    timestamp: datetime
    alert_type: str
    current_activity: float
    baseline_activity: float
    reason: str

class AlertResponse(BaseModel):
    as_of: datetime
    alerts: List[Alert]

class GridGeography(BaseModel):
    grid_id: int
    latitude: float
    longitude: float
    sector_label: str
    source: str  # "geometry" (from enriched_spatial_hourly) or "computed" (grid-math fallback)

class GridGeographyResponse(BaseModel):
    as_of: datetime
    grids: List[GridGeography]

class DailyPeak(BaseModel):
    date: date
    day_of_week: int  # 0=Mon .. 6=Sun
    peak_hour: int
    peak_activity: float
    delta_hours: float  # peak_hour - trailing_avg_peak_hour

class WeeklyPeakResponse(BaseModel):
    grid_id: int
    as_of: datetime
    trailing_avg_peak_hour: float
    days: List[DailyPeak]

class ModalityHour(BaseModel):
    timestamp: datetime
    sms_in: float
    sms_out: float
    call_in: float
    call_out: float
    internet_activity: float

class ModalityResponse(BaseModel):
    grid_id: int
    as_of: datetime
    hours: List[ModalityHour]

class GridListItem(BaseModel):
    grid_id: int
    total_activity: float
    severity: str

class GridListResponse(BaseModel):
    as_of: datetime
    total: int
    grids: List[GridListItem]

class GridFeaturesResponse(BaseModel):
    grid_id: int
    avg_activity: float
    activity_growth: float
    active_hours: int
    peak_ratio: float
    variability: float
    internet_share: float
    feature_timestamp: datetime
    data_quality: str
