import logging
from pathlib import Path
import json
import numpy as np
import pandas as pd


class UsageProcessor:
    """
    Processes telecom usage data through two layers:

    1. Canonical layer
       - Standardized column names
       - Country code retained
       - Blank activity measures converted to 0
       - Invalid records rejected

    2. Grid/hour analytics layer
       - Country-code rows aggregated first
       - One record per grid/hour
       - country_code removed
       - Operational KPIs calculated only after aggregation
    """

    COLUMN_MAPPING = {
        'datetime': 'timestamp',
        'CellID': 'grid_id',
        'countrycode': 'country_code',
        'smsin': 'sms_in_count',
        'smsout': 'sms_out_count',
        'callin': 'call_in_count',
        'callout': 'call_out_count',
        'internet': 'internet_usage'
    }

    ACTIVITY_COLUMNS = [
        'sms_in_count',
        'sms_out_count',
        'call_in_count',
        'call_out_count',
        'internet_usage'
    ]

    REQUIRED_COLUMNS = [
        'timestamp',
        'grid_id',
        'country_code',
        *ACTIVITY_COLUMNS
    ]

    # Alert thresholds (module-level constants instead of magic numbers
    # buried inside alert_report)
    HIGH_THRESHOLD = 1.5
    DROP_THRESHOLD = 0.5
    SPIKE_THRESHOLD = 2.0
    FLOOR_PERCENTILE = 0.10

    def __init__(self, data, logger=None, log_dir=None):
        """
        Parameters
        ----------
        data : pandas.DataFrame or str/path
            Input DataFrame or CSV file path.

        logger : logging.Logger, optional
            Existing logger. If not supplied, a class logger is created.

        log_dir : str or Path, optional
            Where the default log file should live. Defaults to a
            "logs" folder next to this module, NOT the process's
            current working directory (see note below).
        """

        self.data = data
        self.canonical_df = None
        self.analytics_df = None

        self.null_activity_count = {}

        if logger:
            self.logger = logger
        else:
            # NOTE ON THE "LOGGER DOESN'T APPEND" ISSUE
            # ------------------------------------------
            # The previous version used Path("logs"), a path relative to
            # the current working directory. Depending on *where* the
            # script/notebook was launched from, that resolves to a
            # different physical folder each time, so it looks like the
            # logger is "not appending" -- it is actually appending fine,
            # but to a different file every time. Anchoring the path to
            # this module's own location (or an explicit log_dir) makes
            # the target file deterministic.
            #
            # Two smaller bugs are fixed alongside it:
            #  1. `if not self.logger.handlers` only checks "does this
            #     logger have *any* handler", not "does it already have
            #     *this file's* handler". Re-instantiating the class in
            #     the same process after some other code touched the
            #     logger name could either skip attaching the file
            #     handler or (in other orderings) attach a duplicate one.
            #     We instead check for a FileHandler pointing at this
            #     exact file.
            #  2. `propagate` was left at its default (True), so records
            #     also bubble up to the root logger. If anything else in
            #     the process attaches a handler to root, every line gets
            #     logged twice. We set propagate = False.

            self.logger = logging.getLogger(f"{__name__}.{self.__class__.__name__}")
            self.logger.setLevel(logging.INFO)
            self.logger.propagate = False

            resolved_log_dir = (
                Path(log_dir) if log_dir
                else Path(__file__).resolve().parent / "logs"
            )
            resolved_log_dir.mkdir(parents=True, exist_ok=True)
            log_file = resolved_log_dir / "usage_processor.log"

            has_this_file_handler = any(
                isinstance(handler, logging.FileHandler)
                and Path(handler.baseFilename) == log_file
                for handler in self.logger.handlers
            )

            if not has_this_file_handler:
                file_handler = logging.FileHandler(
                    log_file,
                    mode="a",
                    encoding="utf-8"
                )

                formatter = logging.Formatter(
                    "%(asctime)s | %(name)s | %(levelname)s | %(message)s"
                )

                file_handler.setFormatter(formatter)
                self.logger.addHandler(file_handler)

    # ---------------------------------------------------------
    # 1. LOAD DATA
    # ---------------------------------------------------------

    def load_data(self):
        """
        Load data from either a DataFrame or CSV file.
        """

        try:
            if isinstance(self.data, pd.DataFrame):

                self.logger.info("Loading data from DataFrame.")

                self.canonical_df = self.data.copy()

            elif isinstance(self.data, (str, Path)):

                self.logger.info("Loading data from CSV: %s", self.data)

                self.canonical_df = pd.read_csv(self.data)

            else:
                raise TypeError(
                    "Input must be a pandas DataFrame "
                    "or a CSV file path."
                )

            self.logger.info(
                "Loaded %d rows and %d columns.",
                len(self.canonical_df),
                len(self.canonical_df.columns)
            )

            return self.canonical_df

        except Exception as exc:

            self.logger.exception("Failed to load usage data.")

            raise RuntimeError(
                f"Failed to load usage data: {exc}"
            ) from exc

    # ---------------------------------------------------------
    # 2. CLEAN DATA
    # ---------------------------------------------------------

    def clean_data(self):
        """
        Apply curated-layer data quality rules.

        Rules:
        - Standardize column names.
        - Blank activity measures -> 0.
        - Report number of nulls handled.
        - Reject missing timestamp.
        - Reject missing grid_id.
        - Reject negative activity values.
        - Remove exact duplicate rows.
        """

        if self.canonical_df is None:
            raise RuntimeError(
                "Data has not been loaded. Call load_data() first."
            )

        try:

            self.canonical_df = self.canonical_df.rename(
                columns=self.COLUMN_MAPPING
            )

            self.logger.info("Column names standardized.")

            missing_columns = [
                column
                for column in self.REQUIRED_COLUMNS
                if column not in self.canonical_df.columns
            ]

            if missing_columns:
                raise ValueError(
                    f"Missing required columns: {missing_columns}"
                )

            self.canonical_df['timestamp'] = pd.to_datetime(
                self.canonical_df['timestamp'],
                errors='coerce'
            )

            missing_timestamp = self.canonical_df['timestamp'].isna().sum()

            if missing_timestamp > 0:
                raise ValueError(
                    f"Rejected {missing_timestamp} rows "
                    "because timestamp is missing or invalid."
                )

            missing_grid = self.canonical_df['grid_id'].isna().sum()

            if missing_grid > 0:
                raise ValueError(
                    f"Rejected {missing_grid} rows "
                    "because grid_id is missing."
                )

            for column in self.ACTIVITY_COLUMNS:
                self.canonical_df[column] = pd.to_numeric(
                    self.canonical_df[column],
                    errors='coerce'
                )

            # -----------------------------------------------------
            # Curated-layer rule: blank activity measures -> 0
            # -----------------------------------------------------

            self.null_activity_count = {}
            total_nulls_handled = 0

            for column in self.ACTIVITY_COLUMNS:

                null_count = self.canonical_df[column].isna().sum()
                self.null_activity_count[column] = int(null_count)
                total_nulls_handled += null_count

                if null_count > 0:
                    self.canonical_df[column] = (
                        self.canonical_df[column].fillna(0)
                    )

                    self.logger.info(
                        "Curated-layer rule: converted %d "
                        "blank values to 0 in %s.",
                        null_count,
                        column
                    )

            self.logger.info(
                "Total blank activity values handled: %d",
                total_nulls_handled
            )

            # -----------------------------------------------------
            # Reject negative activity values
            # -----------------------------------------------------

            negative_counts = {}

            for column in self.ACTIVITY_COLUMNS:
                negative_count = (self.canonical_df[column] < 0).sum()
                if negative_count > 0:
                    negative_counts[column] = int(negative_count)

            if negative_counts:
                raise ValueError(
                    "Negative activity values detected. "
                    f"Rows rejected by column: {negative_counts}"
                )

            # -----------------------------------------------------
            # Remove exact duplicate rows
            # -----------------------------------------------------

            duplicate_count = self.canonical_df.duplicated().sum()

            if duplicate_count > 0:
                self.logger.info(
                    "Removing %d exact duplicate rows.",
                    duplicate_count
                )

                self.canonical_df = (
                    self.canonical_df
                    .drop_duplicates()
                    .reset_index(drop=True)
                )

            self.logger.info(
                "Cleaning completed successfully. Canonical rows: %d",
                len(self.canonical_df)
            )

            return self.canonical_df

        except Exception as exc:

            self.logger.exception("Data cleaning failed.")

            raise RuntimeError(f"Data cleaning failed: {exc}") from exc

    # ---------------------------------------------------------
    # 3. DERIVE TIME FEATURES
    # ---------------------------------------------------------

    def derive_time_features(self):
        """
        Derive date, hour and hour-level timestamp.

        hour_timestamp represents the beginning of each hour and is
        used by the analytics layer.
        """

        if self.canonical_df is None:
            raise RuntimeError(
                "Data has not been cleaned. Call clean_data() first."
            )

        try:

            self.canonical_df['day_name'] = (
                self.canonical_df['timestamp'].dt.day_name()
            )

            self.canonical_df['date'] = (
                self.canonical_df['timestamp'].dt.date
            )

            self.canonical_df['hour'] = (
                self.canonical_df['timestamp'].dt.hour
            )

            self.canonical_df['hour_timestamp'] = (
                self.canonical_df['timestamp'].dt.floor('h')
            )

            self.logger.info(
                "Derived date, day_name, hour and hour_timestamp."
            )

            return self.canonical_df

        except Exception as exc:

            self.logger.exception("Failed to derive time features.")

            raise RuntimeError(
                f"Failed to derive time features: {exc}"
            ) from exc

    # ---------------------------------------------------------
    # 4. AGGREGATE TO GRID/HOUR
    # ---------------------------------------------------------

    def aggregate_to_grid_time(self):
        """
        Aggregate country-code rows BEFORE calculating operational KPIs.

        Multiple country_code records belonging to the same
        grid_id + hour_timestamp are combined into ONE grid/hour record.
        country_code is deliberately excluded from the resulting
        analytics DataFrame.
        """

        if self.canonical_df is None:
            raise RuntimeError(
                "Data has not been prepared. "
                "Call clean_data() and derive_time_features() first."
            )

        try:

            self.logger.info("Aggregating country-code rows to grid/hour.")

            self.analytics_df = (
                self.canonical_df
                .groupby(['hour_timestamp', 'grid_id'], as_index=False)
                .agg(
                    sms_in_count=('sms_in_count', 'sum'),
                    sms_out_count=('sms_out_count', 'sum'),
                    call_in_count=('call_in_count', 'sum'),
                    call_out_count=('call_out_count', 'sum'),
                    internet_usage=('internet_usage', 'sum')
                )
            )

            self.logger.info(
                "Grid/hour aggregation completed. Output rows: %d",
                len(self.analytics_df)
            )

            return self.analytics_df

        except Exception as exc:

            self.logger.exception("Grid/hour aggregation failed.")

            raise RuntimeError(
                f"Grid/hour aggregation failed: {exc}"
            ) from exc

    # ---------------------------------------------------------
    # 5. COMPUTE KPIs
    # ---------------------------------------------------------

    def compute_kpis(self):
        """
        Compute operational KPIs from the grid/hour analytics layer.

        KPIs are calculated only AFTER country-code rows have been
        aggregated to one grid/hour record.

        Creates:
            total_sms
            total_calls
            total_activity
        """

        if self.analytics_df is None:
            raise RuntimeError(
                "Grid/hour aggregation has not been performed. "
                "Call aggregate_to_grid_time() first."
            )

        try:

            self.logger.info("Computing operational KPIs.")

            self.analytics_df['total_sms'] = (
                self.analytics_df['sms_in_count']
                + self.analytics_df['sms_out_count']
            )

            self.analytics_df['total_calls'] = (
                self.analytics_df['call_in_count']
                + self.analytics_df['call_out_count']
            )

            self.analytics_df['total_activity'] = (
                self.analytics_df['total_sms']
                + self.analytics_df['total_calls']
                + self.analytics_df['internet_usage']
            )

            self.logger.info("KPIs computed successfully.")

            return self.analytics_df

        except Exception as exc:

            self.logger.exception("Failed to compute KPIs.")

            raise RuntimeError(f"Failed to compute KPIs: {exc}") from exc

    def derive_activity_features(self):
        """
        Backward-compatible alias for compute_kpis().

        The original file had two methods (derive_activity_features and
        compute_kpis) that did the exact same calculation, and process()
        called both back-to-back -- harmless but wasted work and a
        maintenance trap (a fix applied to one could silently not apply
        to the other). This keeps the old method name working for any
        external callers without computing the same columns twice.
        """
        return self.compute_kpis()

    # ---------------------------------------------------------
    # 6. EXPORT SUMMARIES
    # ---------------------------------------------------------

    def export_summary(self, output_dir=".\\report"):
        """
        Export daily, grid-level, and alert summaries.

        Creates:
            daily_summary_<date>.csv
            grid_summary_<date>.csv
            activity_alerts_<date>.json
        """

        if self.analytics_df is None:
            raise RuntimeError(
                "Analytics data is not available. "
                "Run aggregate_to_grid_time() first."
            )

        try:

            self.logger.info("Creating summary exports.")

            output_dir = Path(output_dir)
            output_dir.mkdir(parents=True, exist_ok=True)

            date = self.analytics_df["hour_timestamp"].dt.date.iloc[0]

            # =====================================================
            # DAILY SUMMARY
            # =====================================================

            daily_summary = (
                self.analytics_df
                .assign(date=self.analytics_df['hour_timestamp'].dt.date)
                .groupby('date', as_index=False)
                .agg(
                    total_sms=('total_sms', 'sum'),
                    total_calls=('total_calls', 'sum'),
                    internet_usage=('internet_usage', 'sum'),
                    total_activity=('total_activity', 'sum'),
                    active_grids=('grid_id', 'nunique')
                )
            )

            daily_path = output_dir / f"daily_summary_{date}.csv"
            daily_summary.to_csv(daily_path, index=False)

            self.logger.info("Daily summary exported: %s", daily_path)

            # =====================================================
            # GRID SUMMARY
            # =====================================================

            grid_summary = (
                self.analytics_df
                .groupby('grid_id', as_index=False)
                .agg(
                    total_sms=('total_sms', 'sum'),
                    total_calls=('total_calls', 'sum'),
                    internet_usage=('internet_usage', 'sum'),
                    total_activity=('total_activity', 'sum'),
                    active_hours=('hour_timestamp', 'nunique')
                )
            )

            grid_path = output_dir / f"grid_summary_{date}.csv"
            grid_summary.to_csv(grid_path, index=False)

            self.logger.info("Grid summary exported: %s", grid_path)

            # =====================================================
            # ACTIVITY ALERT REPORT
            # =====================================================

            alert_df = self.alert_report()

            alert_path = output_dir / f"activity_alerts_{date}.json"

            with open(alert_path, "w", encoding="utf-8") as file:
                json.dump(
                    alert_df.to_dict(orient="records"),
                    file,
                    indent=4,
                    default=str
                )

            self.logger.info("Activity alert report exported: %s", alert_path)

            self.logger.info("Summary export completed successfully.")

            return {
                "daily_summary": daily_summary,
                "grid_summary": grid_summary,
                "alert_report": alert_df,
                "daily_path": daily_path,
                "grid_path": grid_path,
                "alert_path": alert_path
            }

        except Exception as exc:

            self.logger.exception("Failed to export summaries.")

            raise RuntimeError(
                f"Failed to export summaries: {exc}"
            ) from exc

    # ---------------------------------------------------------
    # 7. ACTIVITY ALERTS  (this is the part that was slow)
    # ---------------------------------------------------------

    @staticmethod
    def _leave_one_out_median(values: np.ndarray) -> np.ndarray:
        """
        Vectorized "leave-one-out" median.

        For an array of n values, returns an array of n medians, where
        result[i] is the median of all values EXCEPT values[i].

        Why this replaces the old approach
        -----------------------------------
        The original code did, for every (grid_id, date) group:

            for index in indices:
                other_values = values.drop(index)      # copies the Series
                df.loc[index, "baseline_activity"] = other_values.median()

        `Series.drop` and `DataFrame.loc` scalar writes both carry heavy
        per-call overhead in pandas. Doing that once per ROW, for every
        group, is what made alert_report() slow -- it's effectively
        O(rows_per_group) pandas operations PER ROW, so cost grows
        quadratically with how many hours of data a single grid/day has,
        multiplied by however many grid/day groups exist.

        This function computes the same leave-one-out medians for an
        entire group in one shot using plain numpy: sort the group once,
        then for each element work out where it would land in the
        (n-1)-length "everyone but me" sorted array using index
        arithmetic, no dropping/copying/looping-with-pandas required.
        """

        n = values.shape[0]
        result = np.full(n, np.nan)

        if n < 2:
            return result

        order = np.argsort(values, kind="mergesort")
        sorted_vals = values[order]

        # rank[i] = position of values[i] within the sorted group
        rank = np.empty(n, dtype=np.int64)
        rank[order] = np.arange(n)

        m = n - 1  # size of the array after removing one element

        if m % 2 == 1:
            r = m // 2
            pos = np.where(rank <= r, r + 1, r)
            result = sorted_vals[pos]
        else:
            r1, r2 = m // 2 - 1, m // 2
            pos1 = np.where(rank <= r1, r1 + 1, r1)
            pos2 = np.where(rank <= r2, r2 + 1, r2)
            result = (sorted_vals[pos1] + sorted_vals[pos2]) / 2.0

        return result

    def alert_report(self):
        """
        Generate activity alerts for each grid and hour.

        Baseline:
            Median total_activity for the same grid and day, excluding
            the current hour.

        Rules:
            HIGH_ACTIVITY  -> current >= 1.5 * baseline
            ACTIVITY_SPIKE -> current >= 2.0 * previous hour
            ACTIVITY_DROP  -> current <= 0.5 * baseline

        Activity floor:
            10th percentile of daily grid activity totals.
        """

        if self.analytics_df is None:
            raise RuntimeError(
                "Analytics data is not available. "
                "Run aggregate_to_grid_time() first."
            )

        try:
            self.logger.info("Generating activity alerts.")

            df = self.analytics_df.copy()

            df["date"] = df["hour_timestamp"].dt.date

            df = df.sort_values(
                ["grid_id", "hour_timestamp"]
            ).reset_index(drop=True)

            # -------------------------------------------------------
            # Previous hour activity (already vectorized, unchanged)
            # -------------------------------------------------------

            df["previous_activity"] = (
                df.groupby("grid_id")["total_activity"].shift(1)
            )

            # -------------------------------------------------------
            # Daily total activity for each grid (already vectorized)
            # -------------------------------------------------------

            df["daily_total"] = (
                df.groupby(["grid_id", "date"])["total_activity"]
                .transform("sum")
            )

            # -------------------------------------------------------
            # Activity floor
            # -------------------------------------------------------

            activity_floor = df["daily_total"].quantile(self.FLOOR_PERCENTILE)

            self.logger.info(
                "Activity floor: %.2f (10th percentile of daily grid totals).",
                activity_floor
            )

            # -------------------------------------------------------
            # Within-day leave-one-out median baseline (VECTORIZED)
            # -------------------------------------------------------

            df["baseline_activity"] = (
                df.groupby(["grid_id", "date"])["total_activity"]
                .transform(
                    lambda s: self._leave_one_out_median(
                        s.to_numpy(dtype=float)
                    )
                )
            )

            # -------------------------------------------------------
            # Apply activity floor
            # -------------------------------------------------------

            df = df[df["daily_total"] >= activity_floor].copy()

            # -------------------------------------------------------
            # Generate alerts (VECTORIZED, no iterrows())
            # -------------------------------------------------------
            #
            # The original loop called df.iterrows() -- which builds a
            # new pandas Series for every single row -- and re-evaluated
            # all three alert conditions per row via slow attribute
            # lookups. Instead, pull each column out as a numpy array
            # once, compute all three boolean masks over the whole
            # array at once, and only loop (in plain Python, for the
            # f-string "reason" text) over the rows that actually
            # triggered an alert -- normally a small fraction of rows.

            valid = df["baseline_activity"].notna().to_numpy()

            current = df["total_activity"].to_numpy(dtype=float)
            baseline = df["baseline_activity"].to_numpy(dtype=float)
            previous = df["previous_activity"].to_numpy(dtype=float)
            grid_id = df["grid_id"].to_numpy()
            timestamp = df["hour_timestamp"].to_numpy()

            with np.errstate(invalid="ignore", divide="ignore"):
                ratio_to_baseline = np.where(valid, current / baseline, np.nan)

                high_mask = valid & (current >= baseline * self.HIGH_THRESHOLD)
                drop_mask = valid & (current <= baseline * self.DROP_THRESHOLD)
                spike_mask = (
                    valid
                    & ~np.isnan(previous)
                    & (previous > 0)
                    & (current >= previous * self.SPIKE_THRESHOLD)
                )

            def _build(mask, alert_type, reason_of):
                idx = np.flatnonzero(mask)
                return [
                    {
                        "grid_id": grid_id[i],
                        "timestamp": timestamp[i],
                        "alert_type": alert_type,
                        "current_activity": current[i],
                        "baseline_activity": baseline[i],
                        "reason": reason_of(i),
                    }
                    for i in idx
                ]

            alerts = []

            alerts += _build(
                high_mask,
                "HIGH_ACTIVITY",
                lambda i: (
                    f"Current activity ({current[i]:.2f}) is "
                    f"{ratio_to_baseline[i]:.2f}x the within-day baseline "
                    f"({baseline[i]:.2f})."
                )
            )

            alerts += _build(
                spike_mask,
                "ACTIVITY_SPIKE",
                lambda i: (
                    f"Activity increased sharply from {previous[i]:.2f} "
                    f"to {current[i]:.2f}."
                )
            )

            alerts += _build(
                drop_mask,
                "ACTIVITY_DROP",
                lambda i: (
                    f"Current activity ({current[i]:.2f}) is "
                    f"{ratio_to_baseline[i]:.2f}x the within-day baseline "
                    f"({baseline[i]:.2f})."
                )
            )

            alert_df = pd.DataFrame(
                alerts,
                columns=[
                    "grid_id",
                    "timestamp",
                    "alert_type",
                    "current_activity",
                    "baseline_activity",
                    "reason"
                ]
            )

            if not alert_df.empty:
                alert_df = alert_df.sort_values(
                    ["timestamp", "grid_id"]
                ).reset_index(drop=True)

            self.logger.info(
                "Activity alert generation completed. Alerts generated: %d",
                len(alert_df)
            )

            return alert_df

        except Exception as exc:

            self.logger.exception("Failed to generate activity alerts.")

            raise RuntimeError(
                f"Failed to generate activity alerts: {exc}"
            ) from exc

    # ---------------------------------------------------------
    # OPTIONAL: RUN COMPLETE PIPELINE
    # ---------------------------------------------------------

    def process(self):
        """
        Run the complete processing pipeline.
        """

        self.logger.info("Starting UsageProcessor pipeline.")

        self.load_data()
        self.clean_data()
        self.derive_time_features()
        self.aggregate_to_grid_time()
        self.compute_kpis()
        self.export_summary()

        self.logger.info("UsageProcessor pipeline completed successfully.")

        return self.analytics_df

    # ---------------------------------------------------------
    # NULL REPORT
    # ---------------------------------------------------------

    def get_null_activity_report(self):
        """
        Return the number of blank activity values handled by the
        curated-layer rule.
        """

        return pd.DataFrame(
            [
                {'column': column, 'nulls_handled': count}
                for column, count in self.null_activity_count.items()
            ]
        )