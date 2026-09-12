from pydantic import BaseModel, Field
from datetime import datetime, date, timedelta
from typing import Dict, List, Optional, Any



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
    timestamp: datetime  # the hour this ranking reflects (shared by every hotspot in a response)

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
    polygon: Optional[List[List[float]]] = None  # [[lat, lon], ...] ring, real or computed square

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

class PredictionResponse(BaseModel):
    grid_id: int
    as_of: datetime
    feature_timestamp: datetime  # timestamp the prediction's trailing features were computed as-of
    probability: float  # model's predicted probability that the *next* hour is high-activity
    prediction: int  # 1 = high-activity risk, 0 = normal (probability thresholded at `threshold`)
    risk_label: str  # "HIGH_ACTIVITY_RISK" or "NORMAL"
    threshold: float  # decision threshold used (model's F1-optimal threshold)
    model_name: Optional[str] = None  # name of the model artifact used
    data_points_used: int  # trailing hourly rows available for this grid in the lookback window
    features: Dict[str, float]  # the engineered feature values fed to the model

# =====================================================================
# DATA EXPLORER — raw/near-raw rows straight off each backing table, for
# the "Data" page's filterable tables.
# =====================================================================

class HourlyGridRecord(BaseModel):
    id: int
    date: date
    hour: int
    grid_id: int
    sms_in: float
    sms_out: float
    call_in: float
    call_out: float
    internet_activity: float
    total_activity: float
    record_count: int
    loaded_at: datetime

class HourlyGridRecordsResponse(BaseModel):
    total: int
    page: int
    page_size: int
    records: List[HourlyGridRecord]

class SpatialHourlyRecord(BaseModel):
    id: int
    date: date
    hour: int
    grid_id: int
    sms_in: float
    sms_out: float
    call_in: float
    call_out: float
    internet_activity: float
    total_activity: float
    has_geometry: bool
    loaded_at: datetime

class SpatialHourlyRecordsResponse(BaseModel):
    total: int
    page: int
    page_size: int
    records: List[SpatialHourlyRecord]

class GridSummaryRecord(BaseModel):
    id: int
    date: date
    grid_id: int
    total_sms: float
    total_calls: float
    internet_usage: float
    total_activity: float
    active_hours: int
    loaded_at: datetime

class GridSummaryRecordsResponse(BaseModel):
    total: int
    page: int
    page_size: int
    records: List[GridSummaryRecord]

class DailySummaryRecord(BaseModel):
    id: int
    date: date
    total_sms: float
    total_calls: float
    internet_usage: float
    total_activity: float
    active_grids: int
    total_records: int
    loaded_at: datetime

class DailySummaryRecordsResponse(BaseModel):
    total: int
    page: int
    page_size: int
    records: List[DailySummaryRecord]

class AuditLogEntry(BaseModel):
    id: int  # 1-indexed line number in flow/logs/audit_log.json, used as a stable row key
    filename: str
    status: str  # "ACCEPTED" or "REJECTED"
    row_count: int
    reason: Optional[str] = None
    processed_at: Optional[datetime] = None
    duration_seconds: Optional[float] = None  # absent on some REJECTED entries (failed before completion)

class AuditLogResponse(BaseModel):
    total: int
    page: int
    page_size: int
    records: List[AuditLogEntry]



#claude endpoints

class ChatMessage(BaseModel):
    role: str
    content: str
    timestamp: Optional[str] = None
    skill_used: Optional[str] = None
    skills_used: Optional[List[str]] = None
    subagents_called: Optional[List[str]] = None
    specialist_reports: Optional[Dict[str, Any]] = None

class ChatRequest(BaseModel):
    grid_id: Optional[int] = None
    message: str
    chat_history: Optional[List[ChatMessage]] = []
    grid_evidence: Optional[Dict] = None

class ChatResponse(BaseModel):
    reply: str
    timestamp: Optional[str] = None
    skill_used: Optional[str] = None
    skills_used: Optional[List[str]] = None
    subagents_called: Optional[List[str]] = None
    active_agent: Optional[str] = None
    specialist_reports: Optional[Dict[str, Any]] = None

class SaveChatHistoryRequest(BaseModel):
    grid_id: int
    messages: List[ChatMessage]

class ChatHistoryResponse(BaseModel):
    grid_id: Optional[int] = None
    messages: Optional[List[ChatMessage]] = None
    histories: Optional[Dict[str, List[ChatMessage]]] = None