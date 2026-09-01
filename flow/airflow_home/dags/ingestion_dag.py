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

# Setup logging
logger = logging.getLogger(__name__)


# Add sql_ingestion to path for MySQL ingestion module
PROJECT_ROOT = Path(__file__).parent.parent.parent  # Go up to project root
SQL_INGESTION_PATH = PROJECT_ROOT / "sql_ingestion"
if str(SQL_INGESTION_PATH) not in sys.path:
    sys.path.insert(0, str(SQL_INGESTION_PATH))

# Now import the module
from mysql_ingestion import MySQLDataIngestion

from airflow.decorators import dag, task
from airflow.sensors.python import PythonSensor

from spark.telecom_pipeline import TelecomPipeline  # noqa: E402

    
load_dotenv(".env.airflow")

FILE_GLOB_PATTERN = "sms-call-internet-mi-*.csv"

# print("AIRFLOW_HOME:", os.environ["AIRFLOW_HOME"])


def _get_path(env_var: str, default_val: str) -> Path:
    """Translate a Windows path (D:\\...) to its WSL equivalent (/mnt/d/...) when running on Linux."""
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


# Create every working directory at DAG *parse* time so the sensor is never
# watching a path that doesn't exist yet.
for _p in (LANDING_PATH, PROCESSING_PATH, RAW_PATH, REJECTED_PATH, STAGING_PATH, LOG_DIR):
    _p.mkdir(parents=True, exist_ok=True)


def _files_waiting() -> bool:
    """
    Check if CSV files are present in the landing directory.
    Used by the PythonSensor to trigger the pipeline when data arrives.
    """
    pattern = str(LANDING_PATH / FILE_GLOB_PATTERN)
    matches = glob.glob(pattern)
    file_count = len(matches)
    print(f"[sensor] polling {pattern}")
    print(f"[sensor] -> {file_count} file(s) found")
    if file_count > 0:
        print(f"[sensor] Data detected! Proceeding with pipeline...")
        for f in matches:
            print(f"[sensor]   - {Path(f).name}")
    else:
        print(f"[sensor] No data in landing zone. Will check again in 5 minutes...")
    return file_count > 0


def _new_pipeline() -> TelecomPipeline:
    """Every task below runs in its own process, so each gets its own
    TelecomPipeline + SparkSession. This is the trade-off for having
    ingest/validate/spark_process show up as distinct, inspectable steps
    instead of one long black-box task."""
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
    """Used when a file fails before it ever reaches spark_process — move it
    straight to rejected/ and log why, rather than dragging a dead file
    through the rest of the pipeline."""
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
    # FIX: start_date must be safely in the past, not "now". With catchup=False,
    # this makes Airflow run the most recent interval immediately on unpause,
    # instead of waiting a full hour for the first interval to complete.
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
        poke_interval=300,  # Check every 5 minutes (300 seconds)
        timeout=60 * 60 * 24,  # Give up after 24 hours
        mode="reschedule",  # frees the worker slot between pokes
        soft_fail=False,    # fail explicitly if timeout reached
        pool="default_pool",
        pool_slots=1
    )

    # ----------------------------------------------------------------- #
    # STAGE 1: ingest — move each file out of landing/, read it with
    # Spark, and checkpoint the raw DataFrame to staging parquet.
    # ----------------------------------------------------------------- #
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
                # Move immediately so a re-poke can't pick the same file up twice.
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

    # ----------------------------------------------------------------- #
    # STAGE 2: validate — reload staged raw data, run quality rules,
    # split into clean/quarantine, checkpoint clean data to staging.
    # ----------------------------------------------------------------- #
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

    # ----------------------------------------------------------------- #
    # STAGE 3: spark_process — aggregate + spatial enrichment + final
    # warehouse write, then move the original file to raw/, audit, and
    # clean up this file's staging artifacts.
    # ----------------------------------------------------------------- #
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

                    pipeline.write_outputs(datasets={
                        "curated_usage": clean_df,
                        "quarantine": quarantine_df,
                        "hourly_grid_summary": aggregates["hourly_grid_summary"],
                        "daily_summary": aggregates["daily_summary"],
                        "grid_summary": aggregates["grid_summary"],
                        "enriched_spatial_hourly": enriched_df,
                        "grid_reference": grid_ref_df,
                    })

                    target = RAW_PATH / filename
                    if target.exists():
                        target.unlink()
                    shutil.move(str(held_path), str(target))

                    duration = (datetime.now() - started_at).total_seconds()
                    _append_audit({
                        "filename": filename,
                        "status": "ACCEPTED",
                        "row_count": item["clean_rows"],
                        "reason": (
                            f"Processed successfully. clean={item['clean_rows']}, "
                            f"rejected={item['rejected_rows']}, nulls_handled={item['nulls_handled']}"
                        ),
                        "processed_at": datetime.now().isoformat(),
                        "duration_seconds": duration,
                    })
                    print(f"[spark_process] {filename}: ACCEPTED in {duration:.2f}s")
                    summary["accepted"].append(filename)

                except Exception as exc:
                    print(f"[spark_process] FAILED on {filename}: {exc}")
                    _reject_now(held_path, f"Final processing error: {exc}")
                    summary["errors"].append(filename)

                finally:
                    # Best-effort staging cleanup for this file.
                    for stage_dir in _staging_dirs(Path(filename).stem).values():
                        shutil.rmtree(stage_dir, ignore_errors=True)
        finally:
            pipeline.spark.stop()

        print(f"[spark_process] batch summary: {summary}")
        return summary

    # ----------------------------------------------------------------- #
    # STAGE 4: mysql_ingest — Load processed data from Spark outputs
    # into MySQL analytical tables (curated_usage, hourly_grid_summary,
    # daily_summary, etc.). This task depends on successful completion
    # of spark_process.
    # ----------------------------------------------------------------- #
    @task
    def mysql_ingest(spark_summary: dict) -> dict:
        """Load Spark parquet outputs to MySQL database."""
        try:
            logger.info("[mysql_ingest] Starting MySQL ingestion...")
            
            # Initialize MySQL connection
            ingestion = MySQLDataIngestion(
                host='127.0.0.1',
                user='root',
                password='root',
                database='TelecomActivity',
                port=3306
            )
            
            # Define parquet output directories (from spark_process writes)
            output_base = RAW_PATH / "processed_parquet"
            parquet_dirs = {
                'curated_usage': output_base / 'curated_usage',
                'quarantine': output_base / 'quarantine',
                'hourly_grid_summary': output_base / 'hourly_grid_summary',
                'daily_summary': output_base / 'daily_summary',
                'grid_summary': output_base / 'grid_summary',
                'enriched_spatial_hourly': output_base / 'enriched_spatial_hourly',
            }
            
            logger.info(f"[mysql_ingest] Parquet base path: {output_base}")
            
            # Verify paths exist
            existing_dirs = {
                k: v for k, v in parquet_dirs.items() 
                if v.exists()
            }
            
            if not existing_dirs:
                logger.warning("[mysql_ingest] No parquet output directories found")
                return {
                    "status": "WARNING",
                    "reason": "No output directories found",
                    "expected_path": str(output_base)
                }
            
            logger.info(f"[mysql_ingest] Found {len(existing_dirs)} directories to ingest")
            
            # Perform ingestion
            stats = ingestion.ingest_from_parquet(existing_dirs, batch_size=1000)
            
            logger.info(f"[mysql_ingest] Ingestion completed: {stats}")
            
            return {
                "status": "SUCCESS",
                "tables_ingested": list(existing_dirs.keys()),
                "total_rows": sum(stats.get(table, {}).get('rows', 0) 
                                 for table in existing_dirs.keys()),
                "stats": stats
            }
            
        except Exception as e:
            logger.error(f"[mysql_ingest] Error during ingestion: {str(e)}", exc_info=True)
            raise

    # ----------------------------------------------------------------- #
    # Task Dependencies and DAG Flow
    # ----------------------------------------------------------------- #
    # Flow: wait_for_files -> ingest -> validate -> spark_process -> mysql_ingest
    # ----------------------------------------------------------------- #
    ingest_results = ingest()
    validate_results = validate(ingest_results)
    process_summary = spark_process(validate_results)
    ingest_summary = mysql_ingest(process_summary)

    wait_for_files >> ingest_results
    ingest_results >> validate_results
    validate_results >> process_summary
    process_summary >> ingest_summary


telecom_landing_ingestion()