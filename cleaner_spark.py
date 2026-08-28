import os
import logging
from pathlib import Path
from functools import reduce
from dotenv import load_dotenv

from pyspark.sql import SparkSession
from pyspark.sql.types import (
    StructType,
    StructField,
    StringType,
    DoubleType,
)
from pyspark.sql import functions as F


class UsageProcessor:

    # Raw CSV header -> canonical column name (single-pass projection)
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

    def __init__(self, input_dir, output_dir=".\\report_spark", log_dir=None):
        self.input_dir = Path(input_dir)
        self.output_dir = Path(output_dir)

        self.spark = None
        self.raw_df = None

        # ---------------------------------------------------------
        # Logging Setup
        # ---------------------------------------------------------
        self.logger = logging.getLogger(f"{__name__}.{self.__class__.__name__}")
        self.logger.setLevel(logging.INFO)
        self.logger.propagate = False

        resolved_log_dir = (
            Path(log_dir) if log_dir
            else Path(__file__).resolve().parent / "logs"
        )
        resolved_log_dir.mkdir(parents=True, exist_ok=True)
        log_file = resolved_log_dir / "usage_processor_spark.log"

        if not any(
            isinstance(h, logging.FileHandler) and Path(h.baseFilename) == log_file
            for h in self.logger.handlers
        ):
            file_handler = logging.FileHandler(log_file, mode="a", encoding="utf-8")
            formatter = logging.Formatter(
                "%(asctime)s | %(name)s | %(levelname)s | %(message)s"
            )
            file_handler.setFormatter(formatter)
            self.logger.addHandler(file_handler)

    # =========================================================
    # 1. SPARK SESSION MANAGEMENT
    # =========================================================

    def create_spark_session(self):
        """Creates or gets an optimized Spark Session with dynamic overwrite enabled."""
        load_dotenv()

        hadoop_home = os.getenv("HADOOP_HOME")
        if hadoop_home:
            os.environ["HADOOP_HOME"] = hadoop_home
            os.environ["PATH"] = os.environ["PATH"] + os.pathsep + os.path.join(hadoop_home, "bin")

        self.spark = (
            SparkSession.builder
            .appName("TelecomUsageProcessor")
            .master("local[*]")
            .config("spark.sql.sources.partitionOverwriteMode", "dynamic")
            .config("spark.sql.shuffle.partitions", "8")  # Tuned for local/constrained memory
            .getOrCreate()
        )
        self.spark.sparkContext.setLogLevel("WARN")
        self.logger.info("SparkSession initialized successfully.")
        return self.spark

    # =========================================================
    # 2. SCHEMA DEFINITION
    # =========================================================

    @staticmethod
    def get_manual_schema():
        """Supplies explicit schema to avoid costly inferSchema scans."""
        return StructType([
            StructField("datetime", StringType(), True),
            StructField("CellID", StringType(), True),
            StructField("countrycode", StringType(), True),
            StructField("smsin", DoubleType(), True),
            StructField("smsout", DoubleType(), True),
            StructField("callin", DoubleType(), True),
            StructField("callout", DoubleType(), True),
            StructField("internet", DoubleType(), True),
        ])

    # =========================================================
    # 3. DATA INGESTION & CANONICALIZATION
    # =========================================================

    def load_and_standardize_data(self, input_path=None):
        """Loads CSVs, attaches file metadata, casts types, and applies canonical schema."""
        if self.spark is None:
            self.create_spark_session()

        target_path = Path(input_path or self.input_dir)

        if target_path.is_file():
            if target_path.suffix.lower() != ".csv":
                raise ValueError("Input file must be a CSV file.")
            read_path = [str(target_path)]
        elif target_path.is_dir():
            csv_files = [str(f) for f in target_path.glob("sms-call-internet-mi-*.csv")]
            if not csv_files:
                # Fallback to all CSVs if standard naming pattern is not matched
                csv_files = [str(f) for f in target_path.glob("*.csv")]
            if not csv_files:
                raise FileNotFoundError(f"No CSV files found in {target_path}")
            read_path = csv_files
        else:
            raise FileNotFoundError(f"Path does not exist: {target_path}")

        self.logger.info("Found %d CSV files to process.", len(read_path))

        raw_df = (
            self.spark.read
            .option("header", True)
            .schema(self.get_manual_schema())
            .csv(read_path)
            .withColumn("input_file_name", F.input_file_name())
        )

        select_exprs = [
            F.to_timestamp(F.col("datetime")).alias("timestamp")
            if raw == "datetime" else F.col(raw).alias(canonical)
            for raw, canonical in self.COLUMN_MAPPING.items()
        ]
        select_exprs.append(F.col("input_file_name"))

        return raw_df.select(*select_exprs)

    # =========================================================
    # 4. DATA QUALITY, QUARANTINE & FEATURE ENGINEERING
    # =========================================================

    def split_and_curate(self, df):
        """
        Splits data into curated and quarantined records without multi-pass caching,
        and adds derived temporal and activity metrics.
        """
        # Temporal fallback column used for partitioning even invalid timestamps
        df = df.withColumn(
            "date", 
            F.coalesce(F.to_date("timestamp"), F.lit("1970-01-01"))
        )

        missing_grid = F.col("grid_id").isNull() | (F.trim(F.col("grid_id")) == "")
        missing_timestamp = F.col("timestamp").isNull()

        # Combine negative activity conditions safely
        negative_conditions = [
            (F.col(col).isNotNull() & (F.col(col) < 0)) 
            for col in self.ACTIVITY_COLUMNS
        ]
        negative_activity = reduce(lambda a, b: a | b, negative_conditions)

        invalid_condition = missing_grid | missing_timestamp | negative_activity

        # Quarantine DataFrame
        quarantine_df = df.filter(invalid_condition).withColumn(
            "quarantine_reason",
            F.when(missing_grid, F.lit("MISSING_GRID_ID"))
            .when(missing_timestamp, F.lit("MISSING_TIMESTAMP"))
            .when(negative_activity, F.lit("NEGATIVE_ACTIVITY"))
            .otherwise(F.lit("UNKNOWN_ERROR"))
        )

        # Curated DataFrame: Fill nulls and derive metrics
        curated_df = df.filter(~invalid_condition)

        for col_name in self.ACTIVITY_COLUMNS:
            curated_df = curated_df.withColumn(
                col_name, 
                F.coalesce(F.col(col_name), F.lit(0.0))
            )

        curated_df = (
            curated_df
            .withColumn("hour", F.hour("timestamp"))
            .withColumn("day_of_week", F.dayofweek("timestamp"))
            .withColumn("total_sms", F.col("sms_in_count") + F.col("sms_out_count"))
            .withColumn("total_calls", F.col("call_in_count") + F.col("call_out_count"))
            .withColumn(
                "total_activity",
                F.col("total_sms") + F.col("total_calls") + F.col("internet_usage"),
            )
        )

        return curated_df, quarantine_df

    # =========================================================
    # 5. CADENCE VERIFICATION
    # =========================================================

    def verify_hourly_cadence(self, df):
        """Lightweight non-shuffling hourly completeness check."""
        stats = (
            df.select("timestamp")
            .distinct()
            .agg(
                F.min("timestamp").alias("min_ts"),
                F.max("timestamp").alias("max_ts"),
                F.count("timestamp").alias("distinct_count"),
            )
            .collect()[0]
        )

        if stats["min_ts"] is None or stats["max_ts"] is None:
            self.logger.warning("No timestamps available for cadence verification.")
            return False

        expected_hours = int((stats["max_ts"] - stats["min_ts"]).total_seconds() // 3600) + 1
        is_valid = expected_hours == stats["distinct_count"]

        if is_valid:
            self.logger.info("Hourly cadence verified: %d contiguous hours.", expected_hours)
        else:
            self.logger.warning(
                "Hourly cadence anomaly: Expected %d hours, found %d.",
                expected_hours,
                stats["distinct_count"],
            )

        return is_valid

    # =========================================================
    # 6. EXPORTING SEGREGATED PARTITIONS
    # =========================================================

    def save_partitioned_parquet(self, df, path_name):
        """Writes dataframe partitioned Hive-style by 'date'."""
        target_path = self.output_dir / path_name
        self.output_dir.mkdir(parents=True, exist_ok=True)

        (
            df
            .repartition("date")
            .write
            .mode("overwrite")
            .partitionBy("date")
            .parquet(str(target_path))
        )
        self.logger.info("Persisted segregated Parquet at: %s", target_path)

    def generate_and_save_summaries(self, curated_parquet_path):
        """
        Reads from curated Parquet storage to compute downstream aggregations.
        Keeps system memory load tiny by avoiding raw CSV rescans.
        """
        curated_df = self.spark.read.parquet(str(curated_parquet_path))

        # Daily Summary (Partitioned by date)
        daily_summary = (
            curated_df
            .groupBy("date")
            .agg(
                F.sum("total_sms").alias("total_sms"),
                F.sum("total_calls").alias("total_calls"),
                F.sum("internet_usage").alias("internet_usage"),
                F.sum("total_activity").alias("total_activity"),
                F.countDistinct("grid_id").alias("active_grids"),
            )
        )
        self.save_partitioned_parquet(daily_summary, "daily_summary")

        # Grid Summary (Segregated by date)
        grid_summary = (
            curated_df
            .groupBy("date", "grid_id")
            .agg(
                F.sum("total_sms").alias("total_sms"),
                F.sum("total_calls").alias("total_calls"),
                F.sum("internet_usage").alias("internet_usage"),
                F.sum("total_activity").alias("total_activity"),
                F.countDistinct("timestamp").alias("active_hours"),
            )
        )
        self.save_partitioned_parquet(grid_summary, "grid_summary")

    # =========================================================
    # 7. MAIN ORCHESTRATION PIPELINE
    # =========================================================

    def process_spark(self):
        """Executes end-to-end memory-efficient processing."""
        self.logger.info("Pipeline execution started.")

        # 1. Read & Standardize
        raw_df = self.load_and_standardize_data()

        # 2. Quality checks & Feature derivation
        curated_df, quarantine_df = self.split_and_curate(raw_df)

        # 3. Export Curated & Quarantine directly (Storage acting as checkpoint)
        curated_path = self.output_dir / "curated_usage"
        self.save_partitioned_parquet(curated_df, "curated_usage")
        self.save_partitioned_parquet(quarantine_df, "quarantine")

        # 4. Cadence check on saved records
        saved_curated_df = self.spark.read.parquet(str(curated_path))
        self.verify_hourly_cadence(saved_curated_df)

        # 5. Summaries generation
        self.generate_and_save_summaries(curated_path)

        self.logger.info("Pipeline execution completed successfully.")


if __name__ == "__main__":
    processor = UsageProcessor(
        input_dir="./data/raw_usage",
        output_dir="./report_spark"
    )
    processor.process_spark()