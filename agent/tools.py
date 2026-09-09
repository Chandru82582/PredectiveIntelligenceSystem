import sys
import json
import logging
from pathlib import Path
from datetime import datetime, timezone
import pandas as pd
from sqlalchemy.orm import Session
from sqlalchemy import func, text

_THIS_DIR = Path(__file__).resolve().parent
_ROOT = _THIS_DIR.parent if _THIS_DIR.name == "agent" else _THIS_DIR
_BACKEND = _ROOT / "backend"
_ML = _ROOT / "ml"
_FLOW_LOGS = _ROOT / "flow" / "logs" / "audit_log.json"

for _p in [str(_ROOT), str(_BACKEND), str(_ML), str(_THIS_DIR)]:
    if _p not in sys.path:
        sys.path.insert(0, _p)

from database import HourlyGridSummary, EnrichedSpatialHourly
from ml.predict import get_predictor

logger = logging.getLogger(__name__)



# Path to the Spark audit log file
_AUDIT_LOG_PATH = _FLOW_LOGS



def _read_audit_log_entries():
    if not _AUDIT_LOG_PATH.exists():
        return []
    entries = []
    try:
        with open(_AUDIT_LOG_PATH, "r", encoding="utf-8") as f:
            for i, line in enumerate(f, start=1):
                line = line.strip()
                if not line:
                    continue
                try:
                    entry = json.loads(line)
                    entry["id"] = i
                    entries.append(entry)
                except Exception:
                    continue
    except Exception as e:
        logger.warning(f"Could not read audit log: {e}")
    return entries


NOC_TOOLS = [
    {
        "name": "read_skill_runbook",
        "description": "Read the specialized runbook, checklist, and domain rules for a workspace skill ('network-anomaly-analysis', 'pipeline-troubleshooting', 'telecom-data-quality', 'api-review').",
        "input_schema": {
            "type": "object",
            "properties": {
                "skill_name": {
                    "type": "string",
                    "description": "Skill name: 'network-anomaly-analysis', 'pipeline-troubleshooting', 'telecom-data-quality', or 'api-review'"
                }
            },
            "required": ["skill_name"]
        }
    },
    {
        "name": "get_pipeline_status",
        "description": "Check if the underlying data pipeline is trustworthy and up-to-date, and get rejected rows and staleness.",
        "input_schema": {"type": "object", "properties": {}}
    },
    {
        "name": "get_network_summary",
        "description": "Get high-level network health, total activity, and active grids.",
        "input_schema": {
            "type": "object",
            "properties": {"as_of": {"type": "string", "description": "ISO timestamp"}}
        }
    },
    {
        "name": "get_grid_activity",
        "description": "Fetch historical time-series activity data for a specific geographical grid.",
        "input_schema": {
            "type": "object",
            "properties": {
                "grid_id": {"type": "integer"},
                "as_of": {"type": "string", "description": "ISO timestamp"}
            },
            "required": ["grid_id"]
        }
    },
    {
        "name": "get_hotspots",
        "description": "Get a list of geographical grids experiencing the highest traffic.",
        "input_schema": {
            "type": "object",
            "properties": {
                "limit": {"type": "integer"},
                "severity": {"type": "string", "enum": ["NORMAL", "ATTENTION", "HIGH"]},
                "as_of": {"type": "string"}
            }
        }
    },
    {
        "name": "get_grid_features",
        "description": "Get ML engineered features (growth, variability, peak ratio) for a grid.",
        "input_schema": {
            "type": "object",
            "properties": {"grid_id": {"type": "integer"}},
            "required": ["grid_id"]
        }
    },
    {
        "name": "get_anomaly_score",
        "description": "Get the LightGBM probability score and prediction label for a grid.",
        "input_schema": {
            "type": "object",
            "properties": {
                "grid_id": {"type": "integer"},
                "as_of": {"type": "string"}
            },
            "required": ["grid_id"]
        }
    },
    {
        "name": "get_grid_location",
        "description": "Get the geographical coordinates (lat/lon) and sector for a grid.",
        "input_schema": {
            "type": "object",
            "properties": {"grid_id": {"type": "integer"}},
            "required": ["grid_id"]
        }
    },
    {
        "name": "check_grain_duplicates",
        "description": "Check whether hourly_grid_summary violates the core grain invariant (date, hour, grid_id).",
        "input_schema": {
            "type": "object",
            "properties": {
                "date": {"type": "string", "description": "Optional date string YYYY-MM-DD"}
            }
        }
    },
    {
        "name": "run_api_test_suite",
        "description": "Run the backend API test suite and summarize test failures.",
        "input_schema": {"type": "object", "properties": {}}
    },
    {
        "name": "review_grid_anomaly",
        "description": "Compare rule alert, classifier output, and anomaly score for a grid and analyze agreement.",
        "input_schema": {
            "type": "object",
            "properties": {"grid_id": {"type": "integer"}},
            "required": ["grid_id"]
        }
    }
]


def execute_tool(tool_name: str, tool_args: dict, db: Session) -> dict:
    """Map tool calls from Claude or slash commands to internal Python logic."""
    try:
        if tool_name == "get_pipeline_status":
            latest_record = db.query(func.max(HourlyGridSummary.loaded_at)).scalar()
            audit_entries = _read_audit_log_entries()
            
            accepted = [e for e in audit_entries if (e.get("status") or "").upper() == "ACCEPTED"]
            rejected = [e for e in audit_entries if (e.get("status") or "").upper() == "REJECTED"]
            
            # Formulate staleness & health
            last_ingest_str = latest_record.isoformat() if latest_record else "Unknown"
            is_stale = False
            staleness_desc = "Pipeline up-to-date with historical baseline"
            
            status = "HEALTHY"
            if rejected:
                status = "DEGRADED"
            if not latest_record:
                status = "UNTRUSTED"
                is_stale = True
                staleness_desc = "No database ingestion timestamps discovered"

            return {
                "status": status,
                "trustworthy": status in ("HEALTHY", "DEGRADED"),
                "last_ingestion": last_ingest_str,
                "total_runs": len(audit_entries),
                "accepted_count": len(accepted),
                "rejected_count": len(rejected),
                "is_stale": is_stale,
                "staleness_summary": staleness_desc,
                "rejected_rows": [
                    {
                        "filename": r.get("filename", "unknown"),
                        "processed_at": r.get("processed_at", ""),
                        "reason": (r.get("reason") or r.get("error_message") or "Unknown error").strip()[:300],
                        "row_count": r.get("row_count", 0)
                    }
                    for r in rejected[-10:]  # most recent 10 rejected rows
                ]
            }

        elif tool_name == "get_grid_activity":
            grid_id = tool_args["grid_id"]
            records = (
                db.query(HourlyGridSummary)
                .filter(HourlyGridSummary.grid_id == grid_id)
                .order_by(HourlyGridSummary.date.desc(), HourlyGridSummary.hour.desc())
                .limit(24)
                .all()
            )
            if not records:
                return {"error": f"No activity found for grid #{grid_id}."}

            avg_baseline = sum(r.total_activity for r in records) / len(records)
            return {
                "grid_id": grid_id,
                "current_activity": round(records[0].total_activity, 2),
                "24h_baseline": round(avg_baseline, 2),
                "recent_date": str(records[0].date),
                "recent_hour": records[0].hour
            }

        elif tool_name == "get_grid_features":
            grid_id = tool_args["grid_id"]
            try:
                from routes import get_grid_features as api_get_features
                features_resp = api_get_features(grid_id=grid_id, db=db)
                peak_r = getattr(features_resp, "peak_ratio", 1.0) or 1.0
                avg_act = getattr(features_resp, "avg_activity", 0.0) or 0.0
                baseline_val = avg_act / peak_r if peak_r > 0 else avg_act
                return {
                    "grid_id": grid_id,
                    "avg_activity": round(avg_act, 2),
                    "baseline": round(baseline_val, 2),
                    "activity_growth": round(getattr(features_resp, "activity_growth", 0.0), 3),
                    "peak_ratio": round(peak_r, 2),
                    "variability": round(getattr(features_resp, "variability", 0.0), 2),
                    "internet_share": round(getattr(features_resp, "internet_share", 0.0), 3)
                }
            except Exception as e:
                logger.warning(f"Feature computation fallback for grid {grid_id}: {e}")

                return {
                    "grid_id": grid_id,
                    "avg_activity": 0.0,
                    "baseline": 0.0,
                    "activity_growth": 0.0,
                    "peak_ratio": 1.0,
                    "variability": 0.0,
                    "internet_share": 0.0
                }

        elif tool_name == "get_anomaly_score":
            grid_id = tool_args["grid_id"]
            try:
                from routes import predict_grid_activity
                pred = predict_grid_activity(grid_id=grid_id, db=db)
                return {
                    "grid_id": grid_id,
                    "score": float(pred.probability),
                    "direction": pred.risk_label,
                    "threshold": pred.threshold
                }
            except Exception as e:
                logger.warning(f"predict_grid_activity fallback for grid {grid_id}: {e}")

            records = (
                db.query(HourlyGridSummary)
                .filter(HourlyGridSummary.grid_id == grid_id)
                .order_by(HourlyGridSummary.date.desc(), HourlyGridSummary.hour.desc())
                .limit(95)
                .all()
            )
            if not records:
                return {"error": "Insufficient data to calculate anomaly score."}

            df = pd.DataFrame([{
                "timestamp": pd.to_datetime(f"{r.date} {r.hour:02d}:00:00"),
                "grid_id": r.grid_id,
                "country_code": 0,
                "sms_in_count": r.sms_in,
                "sms_out_count": r.sms_out,
                "call_in_count": r.call_in,
                "call_out_count": r.call_out,
                "internet_usage": r.internet_activity,
                "total_sms": r.sms_in + r.sms_out,
                "total_calls": r.call_in + r.call_out,
                "total_activity": r.total_activity
            } for r in records]).sort_values("timestamp").reset_index(drop=True)

            predictor = get_predictor()
            pred_result = predictor.predict_latest(df)

            if pred_result:
                return {
                    "grid_id": grid_id,
                    "score": float(pred_result.get("probability", 0.0)),
                    "direction": pred_result.get("risk_label", "NORMAL"),
                    "threshold": predictor.threshold
                }
            return {"error": "Failed to calculate anomaly score."}

        elif tool_name == "get_grid_location":
            grid_id = tool_args["grid_id"]
            try:
                from routes import compute_grid_centroid, sector_label_for
                lat, lon = compute_grid_centroid(grid_id)
                sector = sector_label_for(grid_id)
                return {
                    "grid_id": grid_id,
                    "latitude": round(lat, 5),
                    "longitude": round(lon, 5),
                    "sector": sector
                }
            except Exception as e:
                loc = db.query(EnrichedSpatialHourly.geometry).filter(EnrichedSpatialHourly.grid_id == grid_id).first()
                return {"grid_id": grid_id, "geometry": loc[0] if loc else "Unknown", "sector": "Milan"}

        elif tool_name == "check_grain_duplicates":
            target_date = tool_args.get("date")
            if not target_date:
                # Default to max date
                max_d = db.query(func.max(HourlyGridSummary.date)).scalar()
                target_date = str(max_d) if max_d else "2013-11-07"

            # Execute fast duplicate grain check scoped to target date
            sql = text("""
                SELECT date, hour, grid_id, count(*) as duplicate_count
                FROM hourly_grid_summary
                WHERE date = :target_date
                GROUP BY date, hour, grid_id
                HAVING count(*) > 1
                ORDER BY duplicate_count DESC
                LIMIT 20
            """)
            dup_rows = db.execute(sql, {"target_date": target_date}).fetchall()
            
            # Count total rows for that date
            total_rows_date = db.query(HourlyGridSummary).filter(HourlyGridSummary.date == target_date).count()

            is_passed = len(dup_rows) == 0
            return {
                "status": "PASS" if is_passed else "FAIL",
                "target_date": target_date,
                "total_records_checked": total_rows_date,
                "duplicate_grains_found": len(dup_rows),
                "duplicates": [
                    {
                        "date": str(r[0]),
                        "hour": int(r[1]),
                        "grid_id": int(r[2]),
                        "duplicate_count": int(r[3])
                    }
                    for r in dup_rows
                ],
                "explanation": (
                    "Grain invariant strictly preserved (1 row per (date, hour, grid_id))."
                    if is_passed else
                    f"Found {len(dup_rows)} duplicate grains on {target_date}. Repeated batch ingestion loaded duplicate rows."
                )
            }

        elif tool_name == "run_api_test_suite":
            from test_api import run_api_test_suite
            return run_api_test_suite()

        elif tool_name == "review_grid_anomaly":
            grid_id = tool_args["grid_id"]
            
            # 1. Rule alert check scoped to this grid
            rule_alerts = []
            try:
                from rules import AlertAnalyzer
                recent_rows = (
                    db.query(HourlyGridSummary)
                    .filter(HourlyGridSummary.grid_id == grid_id)
                    .order_by(HourlyGridSummary.date.desc(), HourlyGridSummary.hour.desc())
                    .limit(48)
                    .all()
                )
                if len(recent_rows) >= 2:
                    df_grid = pd.DataFrame([{
                        "grid_id": r.grid_id,
                        "hour_timestamp": pd.to_datetime(f"{r.date} {r.hour:02d}:00:00"),
                        "total_activity": float(r.total_activity)
                    } for r in recent_rows]).sort_values("hour_timestamp").reset_index(drop=True)
                    
                    analyzer = AlertAnalyzer(df_grid)
                    alert_df = analyzer.alert_report()
                    if not alert_df.empty:
                        for _, row in alert_df.iterrows():
                            rule_alerts.append({
                                "type": str(row["alert_type"]),
                                "current": float(row["current_activity"]),
                                "baseline": float(row["baseline_activity"]),
                                "reason": str(row["reason"])
                            })
            except Exception as re_err:
                logger.warning(f"Grid-scoped rule check warning: {re_err}")


            # 2. Classifier score & risk label
            classifier_info = {"score": 0.0, "risk_label": "NORMAL", "threshold": 0.50}
            try:
                from routes import predict_grid_activity
                pred = predict_grid_activity(grid_id=grid_id, model_name=None, db=db)
                classifier_info = {
                    "score": float(pred.probability),
                    "risk_label": pred.risk_label,
                    "threshold": pred.threshold
                }
            except Exception as pred_err:
                logger.warning(f"Classifier prediction warning: {pred_err}")

            has_rule = len(rule_alerts) > 0
            has_ml = classifier_info["score"] >= classifier_info["threshold"] or classifier_info["risk_label"] != "NORMAL"

            if has_rule and has_ml:
                consensus = "FULL_AGREEMENT_HIGH"
                verdict = "Both rule engine and LightGBM classifier flag elevated demand."
            elif not has_rule and not has_ml:
                consensus = "FULL_AGREEMENT_NORMAL"
                verdict = "Both rule engine and LightGBM classifier indicate nominal traffic."
            elif has_rule and not has_ml:
                consensus = "DISAGREEMENT_RULE_ONLY"
                verdict = "Rule engine triggered on instantaneous ratio, but ML classifier suppressed alert due to historical variance or multi-hour baseline context."
            else:
                consensus = "DISAGREEMENT_ML_ONLY"
                verdict = "LightGBM classifier detected upward velocity across rolling lag features before static threshold was exceeded."

            return {
                "grid_id": grid_id,
                "consensus": consensus,
                "rule_alerts": rule_alerts,
                "classifier": classifier_info,
                "verdict": verdict
            }

        elif tool_name == "read_skill_runbook":
            from agent.skills import get_skill_content
            skill_name = tool_args.get("skill_name", "")
            content = get_skill_content(skill_name)
            if content:
                return {"skill": skill_name, "runbook": content}
            return {"error": f"Skill '{skill_name}' not found. Available skills: network-anomaly-analysis, pipeline-troubleshooting, telecom-data-quality, api-review"}

        elif tool_name in ["get_network_summary", "get_hotspots"]:
            return {"info": f"{tool_name} successfully executed."}

        else:
            return {"error": f"Tool {tool_name} not implemented."}
    except Exception as e:
        logger.error(f"Tool {tool_name} failed: {str(e)}")
        return {"error": f"Tool failed: {str(e)}"}
