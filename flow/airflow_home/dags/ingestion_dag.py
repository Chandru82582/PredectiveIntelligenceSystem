import os
import sys
import json
import glob
import shutil
import logging
from pathlib import Path
from datetime import datetime, timedelta
from typing import Any, Dict, List

import pendulum
from dotenv import load_dotenv
from airflow.decorators import dag, task
from airflow.sensors.python import PythonSensor

# Setup logging
logger = logging.getLogger(__name__)

# --- Correctly resolve Project Root for Imports ---
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

# Import the PySpark pipeline
from spark.telecom_pipeline import TelecomPipeline

# --- Absolute path for dotenv ---
env_path = PROJECT_ROOT / ".env.airflow"
load_dotenv(dotenv_path=env_path)

FILE_GLOB_PATTERN = "sms-call-internet-mi-*.csv"

def _get_path(env_var: str, default_val: str) -> Path:
    """Translate a Windows path (D:\...) to its WSL equivalent (/mnt/d/...) when running on Linux."""
    val = os.getenv(env_var, default_val)
    if sys.platform == "linux" and val[:2].lower() == "d:":
        val = "/mnt/d/" + val[2:].lstrip("\\/").replace("\\", "/")
    return Path(val)

LANDING_PATH = _get_path("LANDING_PATH", "d:/PredectiveIntelligenceSystem/flow/data/landing")
PROCESSING_PATH = _get_path("PROCESSING_PATH", "d:/PredectiveIntelligenceSystem/flow/data/processing")
RAW_PATH = _get_path("RAW_PATH", "d:/PredectiveIntelligenceSystem/flow/data/raw")
REJECTED_PATH = _get_path("REJECTED_PATH", "d:/PredectiveIntelligenceSystem/flow/data/rejected")
STAGING_PATH = _get_path("STAGING_PATH", "d:/PredectiveIntelligenceSystem/flow/data/_staging")
LOG_DIR = _get_path("AIRFLOW_LOGS", "d:/PredectiveIntelligenceSystem/flow/logs")
AUDIT_LOG_PATH = LOG_DIR / "audit_log.json"
REFERENCE_PATH = _get_path("REFERENCE_PATH", "d:/PredectiveIntelligenceSystem/flow/data/reference")
os.environ["AIRFLOW_HOME"] = _get_path("AIRFLOW_HOME", "d:/PredectiveIntelligenceSystem/flow/airflow_home").as_posix()

for _p in (LANDING_PATH, PROCESSING_PATH, RAW_PATH, REJECTED_PATH, STAGING_PATH, LOG_DIR):
    _p.mkdir(parents=True, exist_ok=True)

def _files_waiting() -> bool:
    pattern = str(LANDING_PATH / FILE_GLOB_PATTERN)
    matches = glob.glob(pattern)
    file_count = len(matches)
    print(f"[sensor] polling {pattern}")
    print(f"[sensor] -> {file_count} file(s) found")
    if file_count > 0:
        print("[sensor] Data detected! Proceeding with pipeline...")
        for f in matches:
            print(f"[sensor]    - {Path(f).name}")
    else:
        print("[sensor] No data in landing zone. Will check again in 5 minutes...")
    return file_count > 0

def _new_pipeline() -> TelecomPipeline:
    pipeline = TelecomPipeline(
        input_path=str(LANDING_PATH),
        output_path=str(RAW_PATH / "processed_parquet"),
        reference_path=str(REFERENCE_PATH / "milano-grid.geojson"),
        log_dir=str(LOG_DIR),
    )
    pipeline.create_spark_session()
    return pipeline

def _append_audit(entry: Dict[str, Any]) -> None:
    with open(AUDIT_LOG_PATH, "a") as f:
        f.write(json.dumps(entry) + "\n")

def _reject_now(file_path: Path, reason: str, row_count: int = 0) -> None:
    target = REJECTED_PATH / file_path.name
    if target.exists():
        target.unlink()
    shutil.move(str(file_path), str(target))
    _append_audit({
        "filename": file_path.name,
        "status": "REJECTED",
        "row_count": row_count,
        "reason": reason,
        "processed_at": datetime.now().isoformat(),
    })

def _staging_dirs(file_stem: str) -> Dict[str, Path]:
    return {
        "raw": STAGING_PATH / "raw" / file_stem,
        "clean": STAGING_PATH / "clean" / file_stem,
        "quarantine": STAGING_PATH / "quarantine" / file_stem,
    }

@dag(
    dag_id="telecom_landing_ingestion",
    description="Watches the landing zone for Milano telecom CSVs; ingest -> validate -> spark_process.",
    schedule="@hourly",
    start_date=pendulum.datetime(2024, 1, 1, tz="UTC"),
    catchup=False,
    max_active_runs=1,
    default_args={
        "owner": "airflow",
        "retries": 1,
        "retry_delay": timedelta(minutes=2),
    },
    tags=["telecom", "spark", "etl"],
)
def telecom_landing_ingestion():

    wait_for_files = PythonSensor(
        task_id="wait_for_milano_files",
        python_callable=_files_waiting,
        poke_interval=300,
        timeout=60 * 60 * 24,
        mode="reschedule",
        soft_fail=False,
        pool="default_pool",
        pool_slots=1
    )

    @task
    def ingest() -> List[Dict[str, Any]]:
        pattern = str(LANDING_PATH / FILE_GLOB_PATTERN)
        discovered = sorted(glob.glob(pattern))
        if not discovered:
            print("[ingest] nothing to do")
            return []

        pipeline = _new_pipeline()
        results: List[Dict[str, Any]] = []

        try:
            for src in discovered:
                src_path = Path(src)
                held_path = PROCESSING_PATH / src_path.name
                if held_path.exists():
                    held_path.unlink()
                shutil.move(str(src_path), str(held_path))

                print(f"[ingest] reading {held_path.name}")
                try:
                    raw_df = pipeline.read_raw(input_path=str(held_path))
                    row_count = raw_df.count()

                    if row_count == 0:
                        _reject_now(held_path, "File contained zero rows.", row_count=0)
                        results.append({"filename": held_path.name, "status": "REJECTED"})
                        continue

                    stage = _staging_dirs(held_path.stem)
                    raw_df.write.mode("overwrite").parquet(str(stage["raw"]))

                    print(f"[ingest] {held_path.name}: {row_count} rows -> staged")
                    results.append({
                        "filename": held_path.name,
                        "status": "INGESTED",
                        "row_count": row_count,
                        "staging_raw": str(stage["raw"]),
                    })

                except Exception as exc:
                    print(f"[ingest] FAILED on {held_path.name}: {exc}")
                    _reject_now(held_path, f"Ingest error: {exc}")
                    results.append({"filename": held_path.name, "status": "REJECTED"})
        finally:
            pipeline.spark.stop()

        return results

    @task
    def validate(ingest_results: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        pending = [r for r in ingest_results if r.get("status") == "INGESTED"]
        if not pending:
            print("[validate] nothing to do")
            return []

        pipeline = _new_pipeline()
        results: List[Dict[str, Any]] = []

        try:
            for item in pending:
                filename = item["filename"]
                print(f"[validate] checking {filename}")
                try:
                    raw_df = pipeline.spark.read.parquet(item["staging_raw"])
                    clean_df, quarantine_df, metrics = pipeline.clean(raw_df)
                    clean_df.cache()

                    clean_rows = clean_df.count()
                    rejected_rows = quarantine_df.count()

                    if clean_rows == 0:
                        held_path = PROCESSING_PATH / filename
                        _reject_now(
                            held_path,
                            f"All {rejected_rows} rows failed quality checks.",
                            row_count=rejected_rows,
                        )
                        results.append({"filename": filename, "status": "REJECTED"})
                        continue

                    stage = _staging_dirs(Path(filename).stem)
                    clean_df.write.mode("overwrite").parquet(str(stage["clean"]))
                    quarantine_df.write.mode("overwrite").parquet(str(stage["quarantine"]))
                    clean_df.unpersist()

                    print(
                        f"[validate] {filename}: clean={clean_rows} "
                        f"rejected={rejected_rows} nulls_handled={metrics['nulls_handled']}"
                    )
                    results.append({
                        "filename": filename,
                        "status": "VALIDATED",
                        "clean_rows": clean_rows,
                        "rejected_rows": rejected_rows,
                        "nulls_handled": metrics["nulls_handled"],
                        "staging_clean": str(stage["clean"]),
                        "staging_quarantine": str(stage["quarantine"]),
                    })

                except Exception as exc:
                    print(f"[validate] FAILED on {filename}: {exc}")
                    held_path = PROCESSING_PATH / filename
                    _reject_now(held_path, f"Validation error: {exc}")
                    results.append({"filename": filename, "status": "REJECTED"})
        finally:
            pipeline.spark.stop()

        return results

    @task
    def spark_process(validate_results: List[Dict[str, Any]]) -> Dict[str, List[str]]:
        pending = [r for r in validate_results if r.get("status") == "VALIDATED"]
        summary = {"accepted": [], "rejected": [], "errors": []}
        if not pending:
            print("[spark_process] nothing to do")
            return summary

        pipeline = _new_pipeline()

        try:
            for item in pending:
                filename = item["filename"]
                started_at = datetime.now()
                print(f"[spark_process] finalizing {filename}")
                held_path = PROCESSING_PATH / filename

                try:
                    clean_df = pipeline.spark.read.parquet(item["staging_clean"])
                    quarantine_df = pipeline.spark.read.parquet(item["staging_quarantine"])

                    aggregates = pipeline.aggregate(clean_df)
                    enriched_df, grid_ref_df = pipeline.enrich(aggregates["hourly_grid_summary"])

                    # Original DataFrames for Parquet writing (includes all metadata columns)
                    datasets = {
                        "curated_usage": clean_df,
                        "quarantine": quarantine_df,
                        "hourly_grid_summary": aggregates["hourly_grid_summary"],
                        "daily_summary": aggregates["daily_summary"],
                        "grid_summary": aggregates["grid_summary"],
                        "enriched_spatial_hourly": enriched_df,
                    }

                    # Write to local Parquet for archival
                    pipeline.write_outputs(datasets=datasets)
                    pipeline.write_outputs({"grid_reference": grid_ref_df})

                    # EXACT schema alignment for MySQL JDBC (Drop input_file_name, drop record_count from spatial, order columns)
                    mysql_datasets = {
                        "curated_usage": clean_df.select(
                            "timestamp", "grid_id", "country_code", "sms_in_count", "sms_out_count", 
                            "call_in_count", "call_out_count", "internet_usage", "date", "hour", 
                            "day_of_week", "total_sms", "total_calls", "total_activity"
                        ),
                        "quarantine": quarantine_df.select(
                            "timestamp", "grid_id", "country_code", "sms_in_count", "sms_out_count", 
                            "call_in_count", "call_out_count", "internet_usage", "date", "quarantine_reason"
                        ),
                        "hourly_grid_summary": aggregates["hourly_grid_summary"].select(
                            "date", "hour", "grid_id", "sms_in", "sms_out", "call_in", 
                            "call_out", "internet_activity", "total_activity", "record_count"
                        ),
                        "daily_summary": aggregates["daily_summary"].select(
                            "date", "total_sms", "total_calls", "internet_usage", 
                            "total_activity", "active_grids", "total_records"
                        ),
                        "grid_summary": aggregates["grid_summary"].select(
                            "date", "grid_id", "total_sms", "total_calls", 
                            "internet_usage", "total_activity", "active_hours"
                        ),
                        "enriched_spatial_hourly": enriched_df.select(
                            "date", "hour", "grid_id", "sms_in", "sms_out", 
                            "call_in", "call_out", "internet_activity", "total_activity", "geometry"
                        )
                    }

                    # High-speed push directly to MySQL
                    for table_name, df in mysql_datasets.items():
                        pipeline.write_to_mysql(df, table_name=table_name)

                    target = RAW_PATH / filename
                    if target.exists():
                        target.unlink()
                    shutil.move(str(held_path), str(target))

                    duration = (datetime.now() - started_at).total_seconds()
                    _append_audit({
                        "filename": filename,
                        "status": "ACCEPTED",
                        "row_count": item["clean_rows"],
                        "processed_at": datetime.now().isoformat(),
                        "duration_seconds": duration,
                    })
                    summary["accepted"].append(filename)

                except Exception as exc:
                    print(f"[spark_process] FAILED on {filename}: {exc}")
                    _reject_now(held_path, f"Final processing error: {exc}")
                    summary["errors"].append(filename)

                finally:
                    for stage_dir in _staging_dirs(Path(filename).stem).values():
                        shutil.rmtree(stage_dir, ignore_errors=True)
        finally:
            pipeline.spark.stop()

        return summary

    ingest_results = ingest()
    validate_results = validate(ingest_results)
    process_summary = spark_process(validate_results)

    wait_for_files >> ingest_results >> validate_results >> process_summary


telecom_landing_ingestion()