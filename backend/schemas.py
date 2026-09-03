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
