import os
import sys
import json
import time
import logging
import argparse
from pathlib import Path
from functools import reduce
from datetime import datetime
from typing import Dict, Tuple, Any, Optional
from dotenv import load_dotenv

from pyspark.sql import SparkSession, DataFrame
from pyspark.sql.types import (
    StructType,
    StructField,
    StringType,
    DoubleType,
)
from pyspark.sql import functions as F


class TelecomPipeline:
    """
    Modular, memory-efficient Spark ETL pipeline for Telecom Usage Data
    and Spatial Grid Enrichment.
    """

    COLUMN_MAPPING = {
        "datetime": "timestamp",
        "CellID": "grid_id",
        "countrycode": "country_code",
        "smsin": "sms_in_count",
        "smsout": "sms_out_count",
        "callin": "call_in_count",
        "callout": "call_out_count",
        "internet": "internet_usage",
    }

    ACTIVITY_COLUMNS = [
        "sms_in_count",
        "sms_out_count",
        "call_in_count",
        "call_out_count",
        "internet_usage",
    ]

    RAW_SCHEMA = StructType([
        StructField("datetime", StringType(), True),
        StructField("CellID", StringType(), True),
        StructField("countrycode", StringType(), True),
        StructField("smsin", DoubleType(), True),
        StructField("smsout", DoubleType(), True),
        StructField("callin", DoubleType(), True),
        StructField("callout", DoubleType(), True),
        StructField("internet", DoubleType(), True),
    ])

    def __init__(
        self,
        input_path: str = "./data/",
        output_path: str = "./report_spark",
        reference_path: str = "./data/milano-grid.geojson",
        log_dir: str = "./logs",
        app_name: str = "TelecomDataPipeline",
    ):
        load_dotenv()

        hadoop_home = os.getenv("HADOOP_HOME")
        if hadoop_home:
            os.environ["HADOOP_HOME"] = hadoop_home
            os.environ["PATH"] = os.environ["PATH"] + os.pathsep + os.path.join(hadoop_home, "bin")
            
        self.input_path = Path(input_path).resolve()
        self.output_path = Path(output_path).resolve()
        self.reference_path = Path(reference_path).resolve()
        self.log_dir = Path(log_dir).resolve()
        self.app_name = app_name

        self.logger = self._configure_logger()
        self.spark: Optional[SparkSession] = None

    def _configure_logger(self) -> logging.Logger:
        """Configures multi-handler logger for console and file output."""
        self.log_dir.mkdir(parents=True, exist_ok=True)
        log_file = self.log_dir / "telecom_pipeline.log"

        logger = logging.getLogger(f"{self.__class__.__name__}")
        logger.setLevel(logging.INFO)
        logger.propagate = False

        if not any(
            isinstance(h, logging.FileHandler) and Path(h.baseFilename) == log_file
            for h in logger.handlers
        ):
            formatter = logging.Formatter(
                "%(asctime)s | %(levelname)-7s | %(name)s | %(message)s",
                datefmt="%Y-%m-%d %H:%M:%S",
            )
            file_handler = logging.FileHandler(log_file, mode="a", encoding="utf-8")
            file_handler.setFormatter(formatter)
            logger.addHandler(file_handler)

            console_handler = logging.StreamHandler(sys.stdout)
            console_handler.setFormatter(formatter)
            logger.addHandler(console_handler)

        return logger

    def create_spark_session(self) -> SparkSession:
        """Initializes SparkSession with dynamic partition overwrite and memory controls."""
        hadoop_home = os.getenv("HADOOP_HOME")
        if hadoop_home:
            os.environ["HADOOP_HOME"] = hadoop_home
            os.environ["PATH"] = os.environ["PATH"] + os.pathsep + os.path.join(hadoop_home, "bin")

        self.spark = (
            SparkSession.builder
            .appName(self.app_name)
            .master("local[*]")
            .config("spark.sql.sources.partitionOverwriteMode", "dynamic")
            .config("spark.sql.shuffle.partitions", "8")
            .config("spark.driver.memory", "8g")
            .config("spark.sql.execution.arrow.pyspark.enabled", "true")
            .getOrCreate()
        )
        self.spark.sparkContext.setLogLevel("WARN")
        return self.spark

    def read_raw(self, input_path: Optional[str] = None) -> DataFrame:
        """
        Reads raw CSV files with explicit schema, verifies file existence,
        and fails cleanly and loudly if no files are discovered.
        """
        if self.spark is None:
            self.create_spark_session()

        target = Path(input_path).resolve() if input_path else self.input_path
        self.logger.info("Scanning for input CSV files at: %s", target)

        if not target.exists():
            err_msg = f"CRITICAL: Input path does not exist: '{target}'"
            self.logger.error(err_msg)
            raise FileNotFoundError(err_msg)

        if target.is_file():
            if target.suffix.lower() != ".csv":
                err_msg = f"CRITICAL: Specified file '{target}' is not a CSV."
                self.logger.error(err_msg)
                raise ValueError(err_msg)
            target_files = [str(target)]
        elif target.is_dir():
            target_files = [str(f) for f in target.glob("sms-call-internet-mi-*.csv")]
            if not target_files:
                target_files = [str(f) for f in target.glob("*.csv")]

            if not target_files:
                err_msg = (
                    f"CRITICAL: No input CSV files found inside directory '{target}'. "
                    "Pipeline execution aborted."
                )
                self.logger.error(err_msg)
                raise FileNotFoundError(err_msg)
        else:
            err_msg = f"CRITICAL: Unrecognized path type for: '{target}'"
            self.logger.error(err_msg)
            raise FileNotFoundError(err_msg)

        self.logger.info("Discovered %d source file(s) for ingestion.", len(target_files))

        raw_df = (
            self.spark.read
            .option("header", True)
            .schema(self.RAW_SCHEMA)
            .csv(target_files)
            .withColumn("input_file_name", F.input_file_name())
        )

        select_exprs = [
            F.to_timestamp(F.col("datetime")).alias("timestamp")
            if raw == "datetime" else F.col(raw).alias(canonical)
            for raw, canonical in self.COLUMN_MAPPING.items()
        ]
        select_exprs.append(F.col("input_file_name"))

        return raw_df.select(*select_exprs)

    def clean(
        self,
        df: DataFrame
    ) -> Tuple[DataFrame, DataFrame, Dict[str, Any]]:
        """
        Validates quality rules, isolates quarantined records, fills nulls,
        and computes derived features.
        """
        self.logger.info("Executing data quality checks and quarantine isolation...")

        df_with_date = df.withColumn(
            "date",
            F.coalesce(F.to_date("timestamp"), F.lit("1970-01-01"))
        )

        missing_grid = F.col("grid_id").isNull() | (F.trim(F.col("grid_id")) == "")
        missing_timestamp = F.col("timestamp").isNull()

        negative_conditions = [
            (F.col(c).isNotNull() & (F.col(c) < 0))
            for c in self.ACTIVITY_COLUMNS
        ]
        negative_activity = reduce(lambda a, b: a | b, negative_conditions)

        invalid_condition = missing_grid | missing_timestamp | negative_activity

        quarantine_df = df_with_date.filter(invalid_condition).withColumn(
            "quarantine_reason",
            F.when(missing_grid, F.lit("MISSING_GRID_ID"))
            .when(missing_timestamp, F.lit("MISSING_TIMESTAMP"))
            .when(negative_activity, F.lit("NEGATIVE_ACTIVITY"))
            .otherwise(F.lit("DATA_ANOMALY"))
        )

        valid_df = df_with_date.filter(~invalid_condition)

        null_count_exprs = [
            F.sum(F.when(F.col(c).isNull(), 1).otherwise(0)).alias(f"nulls_{c}")
            for c in self.ACTIVITY_COLUMNS
        ]
        null_counts_row = valid_df.agg(*null_count_exprs).collect()[0].asDict()
        total_nulls_handled = sum(null_counts_row.values()) if null_counts_row else 0

        for col_name in self.ACTIVITY_COLUMNS:
            valid_df = valid_df.withColumn(
                col_name,
                F.coalesce(F.col(col_name), F.lit(0.0))
            )

        clean_df = (
            valid_df
            .withColumn("hour", F.hour("timestamp"))
            .withColumn("day_of_week", F.dayofweek("timestamp"))
            .withColumn("total_sms", F.col("sms_in_count") + F.col("sms_out_count"))
            .withColumn("total_calls", F.col("call_in_count") + F.col("call_out_count"))
            .withColumn(
                "total_activity",
                F.col("total_sms") + F.col("total_calls") + F.col("internet_usage")
            )
        )

        metrics = {
            "nulls_handled": total_nulls_handled,
            "null_details": null_counts_row
        }

        return clean_df, quarantine_df, metrics

    def aggregate(self, clean_df: DataFrame) -> Dict[str, DataFrame]:
        """
        Builds analytical aggregations:
          1. hourly_grid_summary: 1 record per (date, hour, grid_id)
          2. daily_summary: Overall daily activity
          3. grid_summary: Aggregated coverage by grid and date
        """
        self.logger.info("Computing multi-dimensional summary aggregations...")

        hourly_grid_summary = (
            clean_df
            .groupBy("date", "hour", "grid_id")
            .agg(
                F.sum("sms_in_count").alias("sms_in"),
                F.sum("sms_out_count").alias("sms_out"),
                F.sum("call_in_count").alias("call_in"),
                F.sum("call_out_count").alias("call_out"),
                F.sum("internet_usage").alias("internet_activity"),
                F.sum("total_activity").alias("total_activity"),
                F.count("timestamp").alias("record_count"),
            )
        )

        daily_summary = (
            clean_df
            .groupBy("date")
            .agg(
                F.sum("total_sms").alias("total_sms"),
                F.sum("total_calls").alias("total_calls"),
                F.sum("internet_usage").alias("internet_usage"),
                F.sum("total_activity").alias("total_activity"),
                F.countDistinct("grid_id").alias("active_grids"),
                F.count("timestamp").alias("total_records"),
            )
        )

        grid_summary = (
            clean_df
            .groupBy("date", "grid_id")
            .agg(
                F.sum("total_sms").alias("total_sms"),
                F.sum("total_calls").alias("total_calls"),
                F.sum("internet_usage").alias("internet_usage"),
                F.sum("total_activity").alias("total_activity"),
                F.countDistinct("timestamp").alias("active_hours"),
            )
        )

        return {
            "hourly_grid_summary": hourly_grid_summary,
            "daily_summary": daily_summary,
            "grid_summary": grid_summary,
        }

    def enrich(
        self,
        hourly_df: DataFrame,
        reference_path: Optional[str] = None
    ) -> Tuple[DataFrame, DataFrame]:
        """
        Loads spatial dimension reference and enriches hourly metrics
        using a broadcast join.
        """
        ref_path = Path(reference_path).resolve() if reference_path else self.reference_path
        self.logger.info("Loading spatial reference from: %s", ref_path)

        if not ref_path.exists():
            err_msg = f"CRITICAL: Spatial reference file not found at: '{ref_path}'"
            self.logger.error(err_msg)
            raise FileNotFoundError(err_msg)

        if ref_path.suffix.lower() in [".geojson", ".json"]:
            with open(ref_path, "r", encoding="utf-8") as f:
                geojson_data = json.load(f)

            grid_records = []
            for feat in geojson_data.get("features", []):
                props = feat.get("properties", {})
                cell_id = (
                    props.get("cellId")
                    or props.get("cell_id")
                    or props.get("id")
                    or feat.get("id")
                )
                geom_str = json.dumps(feat.get("geometry", {}))
                if cell_id is not None:
                    grid_records.append((str(cell_id), geom_str))

            ref_schema = StructType([
                StructField("grid_id", StringType(), False),
                StructField("geometry", StringType(), False),
            ])
            grid_ref_df = self.spark.createDataFrame(grid_records, schema=ref_schema)
        else:
            grid_ref_df = self.spark.read.parquet(str(ref_path))

        enriched_df = hourly_df.join(
            F.broadcast(grid_ref_df),
            on="grid_id",
            how="inner"
        )

        return enriched_df, grid_ref_df

    def write_outputs(
        self,
        datasets: Dict[str, DataFrame],
        output_dir: Optional[str] = None
    ) -> Dict[str, int]:
        """
        Persists datasets to Parquet format segregated by date partitions.
        Returns total row counts per output table.
        """
        out_base = Path(output_dir).resolve() if output_dir else self.output_path
        out_base.mkdir(parents=True, exist_ok=True)
        self.logger.info("Writing pipeline artifacts to base directory: %s", out_base)

        row_counts = {}

        for name, df in datasets.items():
            target_path = out_base / name
            self.logger.info("Persisting dataset '%s' to: %s", name, target_path)

            if "date" in df.columns:
                (
                    df
                    .repartition("date")
                    .write
                    .mode("overwrite")
                    .partitionBy("date")
                    .parquet(str(target_path))
                )
            else:
                (
                    df
                    .write
                    .mode("overwrite")
                    .parquet(str(target_path))
                )

            count = df.count()
            row_counts[name] = count
            self.logger.info("-> Wrote %d rows for '%s'", count, name)

        return row_counts

    def run(self) -> Dict[str, Any]:
        """Orchestrates pipeline execution with execution metrics and status logging."""
        start_time = datetime.now()
        start_perf = time.perf_counter()

        self.logger.info("=" * 70)
        self.logger.info("TELECOM PIPELINE EXECUTION STARTED")
        self.logger.info("Start Time        : %s", start_time.strftime("%Y-%m-%d %H:%M:%S"))
        self.logger.info("Input Path        : %s", self.input_path)
        self.logger.info("Output Path       : %s", self.output_path)
        self.logger.info("Reference Path    : %s", self.reference_path)
        self.logger.info("=" * 70)

        status = "FAILED"
        total_input_rows = 0
        total_rejected_rows = 0
        total_nulls_handled = 0
        output_rows_summary = {}

        try:
            # Step 1: Initialize Spark Session
            self.create_spark_session()

            # Step 2: Read raw CSVs (fails cleanly & loudly if absent)
            raw_df = self.read_raw()
            total_input_rows = raw_df.count()
            self.logger.info("Total raw rows loaded: %d", total_input_rows)

            # Step 3: Clean, quarantine, handle nulls, and derive features
            clean_df, quarantine_df, quality_metrics = self.clean(raw_df)
            total_rejected_rows = quarantine_df.count()
            total_nulls_handled = quality_metrics["nulls_handled"]

            self.logger.info("Data Quality Metrics:")
            self.logger.info("  - Clean rows      : %d", total_input_rows - total_rejected_rows)
            self.logger.info("  - Rejected rows   : %d", total_rejected_rows)
            self.logger.info("  - Nulls handled   : %d", total_nulls_handled)

            # Step 4: Analytical Aggregations
            aggregates = self.aggregate(clean_df)

            # Step 5: Spatial Enrichment
            enriched_hourly_df, grid_ref_df = self.enrich(
                hourly_df=aggregates["hourly_grid_summary"]
            )

            # Step 6: Write segregated Parquet partitions
            datasets_to_write = {
                "curated_usage": clean_df,
                "quarantine": quarantine_df,
                "hourly_grid_summary": aggregates["hourly_grid_summary"],
                "daily_summary": aggregates["daily_summary"],
                "grid_summary": aggregates["grid_summary"],
                "enriched_spatial_hourly": enriched_hourly_df,
                "grid_reference": grid_ref_df,
            }

            output_rows_summary = self.write_outputs(datasets=datasets_to_write)
            status = "SUCCESS"

        except Exception as exc:
            self.logger.exception("FATAL: Pipeline execution failed: %s", str(exc))
            raise exc

        finally:
            end_time = datetime.now()
            duration_sec = time.perf_counter() - start_perf

            if self.spark is not None:
                self.spark.stop()
                self.logger.info("Spark session closed.")

            self.logger.info("=" * 70)
            self.logger.info("PIPELINE EXECUTION SUMMARY")
            self.logger.info("=" * 70)
            self.logger.info("Final Status         : %s", status)
            self.logger.info("Start Time           : %s", start_time.strftime("%Y-%m-%d %H:%M:%S"))
            self.logger.info("End Time             : %s", end_time.strftime("%Y-%m-%d %H:%M:%S"))
            self.logger.info("Elapsed Duration     : %.2f seconds", duration_sec)
            self.logger.info("Total Input Rows     : %d", total_input_rows)
            self.logger.info("Total Rejected Rows  : %d", total_rejected_rows)
            self.logger.info("Total Nulls Handled  : %d", total_nulls_handled)
            self.logger.info("Output Row Counts    :")
            for dataset_name, count in output_rows_summary.items():
                self.logger.info("  - %-24s : %d rows", dataset_name, count)
            self.logger.info("=" * 70)

        return {
            "status": status,
            "input_rows": total_input_rows,
            "rejected_rows": total_rejected_rows,
            "nulls_handled": total_nulls_handled,
            "output_rows": output_rows_summary,
            "duration_seconds": duration_sec,
        }


def main():
    """CLI entrypoint for running the Telecom Pipeline."""
    parser = argparse.ArgumentParser(
        description="Production Telecom Usage Pipeline (ETL & Spatial Enrichment)"
    )
    parser.add_argument(
        "--input-path",
        type=str,
        default=os.getenv("TELECOM_INPUT_PATH", "./data"),
        help="Path to raw CSV input directory or file.",
    )
    parser.add_argument(
        "--output-path",
        type=str,
        default=os.getenv("TELECOM_OUTPUT_PATH", "./report_spark"),
        help="Base directory for writing output Parquet partitions.",
    )
    parser.add_argument(
        "--reference-path",
        type=str,
        default=os.getenv("TELECOM_REF_PATH", "./data/milano-grid.geojson"),
        help="Path to milano-grid.geojson or grid_reference.parquet.",
    )
    parser.add_argument(
        "--log-dir",
        type=str,
        default=os.getenv("TELECOM_LOG_DIR", "./logs"),
        help="Directory where log files are written.",
    )

    args = parser.parse_args()

    pipeline = TelecomPipeline(
        input_path=args.input_path,
        output_path=args.output_path,
        reference_path=args.reference_path,
        log_dir=args.log_dir,
    )

    try:
        pipeline.run()
    except Exception:
        sys.exit(1)


if __name__ == "__main__":
    main()