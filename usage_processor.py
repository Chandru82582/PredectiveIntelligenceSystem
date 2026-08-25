import logging
from pathlib import Path

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

    def __init__(self, data, logger=None):
        """
        Parameters
        ----------
        data : pandas.DataFrame or str/path
            Input DataFrame or CSV file path.

        logger : logging.Logger, optional
            Existing logger. If not supplied, a class logger is created.
        """

        self.data = data
        self.canonical_df = None
        self.analytics_df = None

        self.null_activity_count = {}

        self.logger = logger or logging.getLogger(
            self.__class__.__name__
        )

    # ---------------------------------------------------------
    # 1. LOAD DATA
    # ---------------------------------------------------------

    def load_data(self):
        """
        Load data from either a DataFrame or CSV file.
        """

        try:
            if isinstance(self.data, pd.DataFrame):

                self.logger.info(
                    "Loading data from DataFrame."
                )

                self.canonical_df = self.data.copy()

            elif isinstance(self.data, (str, Path)):

                self.logger.info(
                    "Loading data from CSV: %s",
                    self.data
                )

                self.canonical_df = pd.read_csv(
                    self.data
                )

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

            self.logger.exception(
                "Failed to load usage data."
            )

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
                "Data has not been loaded. "
                "Call load_data() first."
            )

        try:

            # ---------------------------------------------
            # Standardize column names
            # ---------------------------------------------

            self.canonical_df = self.canonical_df.rename(
                columns=self.COLUMN_MAPPING
            )

            self.logger.info(
                "Column names standardized."
            )

            # ---------------------------------------------
            # Validate required columns
            # ---------------------------------------------

            missing_columns = [
                column
                for column in self.REQUIRED_COLUMNS
                if column not in self.canonical_df.columns
            ]

            if missing_columns:
                raise ValueError(
                    "Missing required columns: "
                    f"{missing_columns}"
                )

            # ---------------------------------------------
            # Convert timestamp
            # ---------------------------------------------

            self.canonical_df['timestamp'] = pd.to_datetime(
                self.canonical_df['timestamp'],
                errors='coerce'
            )

            # ---------------------------------------------
            # Reject missing timestamp
            # ---------------------------------------------

            missing_timestamp = (
                self.canonical_df['timestamp'].isna().sum()
            )

            if missing_timestamp > 0:

                raise ValueError(
                    f"Rejected {missing_timestamp} rows "
                    "because timestamp is missing or invalid."
                )

            # ---------------------------------------------
            # Reject missing grid_id
            # ---------------------------------------------

            missing_grid = (
                self.canonical_df['grid_id'].isna().sum()
            )

            if missing_grid > 0:

                raise ValueError(
                    f"Rejected {missing_grid} rows "
                    "because grid_id is missing."
                )

            # ---------------------------------------------
            # Convert activity columns to numeric
            # ---------------------------------------------

            for column in self.ACTIVITY_COLUMNS:

                self.canonical_df[column] = pd.to_numeric(
                    self.canonical_df[column],
                    errors='coerce'
                )

            # ---------------------------------------------
            # Curated-layer rule:
            # blank activity measures -> 0
            # ---------------------------------------------

            self.null_activity_count = {}

            total_nulls_handled = 0

            for column in self.ACTIVITY_COLUMNS:

                null_count = (
                    self.canonical_df[column]
                    .isna()
                    .sum()
                )

                self.null_activity_count[column] = int(
                    null_count
                )

                total_nulls_handled += null_count

                if null_count > 0:

                    self.canonical_df[column] = (
                        self.canonical_df[column]
                        .fillna(0)
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

            # ---------------------------------------------
            # Reject negative activity values
            # ---------------------------------------------

            negative_counts = {}

            for column in self.ACTIVITY_COLUMNS:

                negative_count = (
                    self.canonical_df[column] < 0
                ).sum()

                if negative_count > 0:

                    negative_counts[column] = int(
                        negative_count
                    )

            if negative_counts:

                raise ValueError(
                    "Negative activity values detected. "
                    f"Rows rejected by column: "
                    f"{negative_counts}"
                )

            # ---------------------------------------------
            # Remove exact duplicate rows
            # ---------------------------------------------

            duplicate_count = (
                self.canonical_df
                .duplicated()
                .sum()
            )

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
                "Cleaning completed successfully. "
                "Canonical rows: %d",
                len(self.canonical_df)
            )

            return self.canonical_df

        except Exception as exc:

            self.logger.exception(
                "Data cleaning failed."
            )

            raise RuntimeError(
                f"Data cleaning failed: {exc}"
            ) from exc

    # ---------------------------------------------------------
    # 3. DERIVE TIME FEATURES
    # ---------------------------------------------------------

    def derive_time_features(self):
        """
        Derive date, hour and hour-level timestamp.

        hour_timestamp represents the beginning of
        each hour and is used by the analytics layer.
        """

        if self.canonical_df is None:
            raise RuntimeError(
                "Data has not been cleaned. "
                "Call clean_data() first."
            )

        try:

            self.canonical_df['day_name'] = (
                self.canonical_df['timestamp']
                .dt.day_name()
            )

            self.canonical_df['date'] = (
                self.canonical_df['timestamp']
                .dt.date
            )

            self.canonical_df['hour'] = (
                self.canonical_df['timestamp']
                .dt.hour
            )

            # Beginning of the hour
            self.canonical_df['hour_timestamp'] = (
                self.canonical_df['timestamp']
                .dt.floor('h')
            )

            self.logger.info(
                "Derived date, day_name, hour and "
                "hour_timestamp."
            )

            return self.canonical_df

        except Exception as exc:

            self.logger.exception(
                "Failed to derive time features."
            )

            raise RuntimeError(
                f"Failed to derive time features: {exc}"
            ) from exc

    # ---------------------------------------------------------
    # 4. AGGREGATE TO GRID/HOUR
    # ---------------------------------------------------------

    def aggregate_to_grid_time(self):
        """
        Aggregate country-code rows BEFORE calculating
        operational KPIs.

        Multiple country_code records belonging to the same:

            grid_id + hour_timestamp

        are combined into ONE grid/hour record.

        country_code is deliberately excluded from the
        resulting analytics DataFrame.
        """

        if self.canonical_df is None:
            raise RuntimeError(
                "Data has not been prepared. "
                "Call clean_data() and derive_time_features() first."
            )

        try:

            self.logger.info(
                "Aggregating country-code rows to grid/hour."
            )

            self.analytics_df = (
                self.canonical_df
                .groupby(
                    [
                        'hour_timestamp',
                        'grid_id'
                    ],
                    as_index=False
                )
                .agg(
                    sms_in_count=(
                        'sms_in_count',
                        'sum'
                    ),
                    sms_out_count=(
                        'sms_out_count',
                        'sum'
                    ),
                    call_in_count=(
                        'call_in_count',
                        'sum'
                    ),
                    call_out_count=(
                        'call_out_count',
                        'sum'
                    ),
                    internet_usage=(
                        'internet_usage',
                        'sum'
                    )
                )
            )

            self.logger.info(
                "Grid/hour aggregation completed. "
                "Output rows: %d",
                len(self.analytics_df)
            )

            return self.analytics_df

        except Exception as exc:

            self.logger.exception(
                "Grid/hour aggregation failed."
            )

            raise RuntimeError(
                f"Grid/hour aggregation failed: {exc}"
            ) from exc

    # ---------------------------------------------------------
    # 5. DERIVE ACTIVITY FEATURES
    # ---------------------------------------------------------

    def derive_activity_features(self):
        """
        Calculate operational KPIs AFTER grid/hour aggregation.

        Creates:
        - total_sms
        - total_calls
        - total_activity
        """

        if self.analytics_df is None:
            raise RuntimeError(
                "Grid/hour aggregation has not been performed. "
                "Call aggregate_to_grid_time() first."
            )

        try:

            self.logger.info(
                "Deriving operational activity features."
            )

            self.analytics_df['total_sms'] = (
                self.analytics_df['sms_in_count']
                +
                self.analytics_df['sms_out_count']
            )

            self.analytics_df['total_calls'] = (
                self.analytics_df['call_in_count']
                +
                self.analytics_df['call_out_count']
            )

            self.analytics_df['total_activity'] = (
                self.analytics_df['total_sms']
                +
                self.analytics_df['total_calls']
                +
                self.analytics_df['internet_usage']
            )

            self.logger.info(
                "Activity features derived successfully."
            )

            return self.analytics_df

        except Exception as exc:

            self.logger.exception(
                "Failed to derive activity features."
            )

            raise RuntimeError(
                f"Failed to derive activity features: {exc}"
            ) from exc

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
    
                self.logger.info(
                    "Computing operational KPIs."
                )
    
                # -----------------------------
                # SMS KPI
                # -----------------------------
                self.analytics_df['total_sms'] = (
                    self.analytics_df['sms_in_count']
                    +
                    self.analytics_df['sms_out_count']
                )
    
                # -----------------------------
                # Call KPI
                # -----------------------------
                self.analytics_df['total_calls'] = (
                    self.analytics_df['call_in_count']
                    +
                    self.analytics_df['call_out_count']
                )
    
                # -----------------------------
                # Overall activity KPI
                # -----------------------------
                self.analytics_df['total_activity'] = (
                    self.analytics_df['total_sms']
                    +
                    self.analytics_df['total_calls']
                    +
                    self.analytics_df['internet_usage']
                )
    
                self.logger.info(
                    "KPIs computed successfully."
                )
    
                return self.analytics_df
    
            except Exception as exc:
    
                self.logger.exception(
                    "Failed to compute KPIs."
                )
    
                raise RuntimeError(
                    f"Failed to compute KPIs: {exc}"
                ) from exc
    
    def export_summary(self, output_dir="."):
        """
        Export daily and grid-level summaries.

        Creates:
            daily_summary.csv
            grid_summary.csv

        Parameters
        ----------
        output_dir : str
            Directory where summary CSV files will be written.
        """

        if self.analytics_df is None:
            raise RuntimeError(
                "Analytics data is not available. "
                "Run aggregate_to_grid_time() first."
            )

        try:

            self.logger.info(
                "Creating summary exports."
            )

            output_dir = Path(output_dir)
            output_dir.mkdir(
                parents=True,
                exist_ok=True
            )

            # =====================================================
            # DAILY SUMMARY
            # =====================================================

            daily_summary = (
                self.analytics_df
                .assign(
                    date=self.analytics_df[
                        'hour_timestamp'
                    ].dt.date
                )
                .groupby('date', as_index=False)
                .agg(
                    total_sms=(
                        'total_sms',
                        'sum'
                    ),
                    total_calls=(
                        'total_calls',
                        'sum'
                    ),
                    internet_usage=(
                        'internet_usage',
                        'sum'
                    ),
                    total_activity=(
                        'total_activity',
                        'sum'
                    ),
                    active_grids=(
                        'grid_id',
                        'nunique'
                    )
                )
            )

            daily_path = (
                output_dir /
                "daily_summary.csv"
            )

            daily_summary.to_csv(
                daily_path,
                index=False
            )

            self.logger.info(
                "Daily summary exported: %s",
                daily_path
            )

            # =====================================================
            # GRID SUMMARY
            # =====================================================

            grid_summary = (
                self.analytics_df
                .groupby('grid_id', as_index=False)
                .agg(
                    total_sms=(
                        'total_sms',
                        'sum'
                    ),
                    total_calls=(
                        'total_calls',
                        'sum'
                    ),
                    internet_usage=(
                        'internet_usage',
                        'sum'
                    ),
                    total_activity=(
                        'total_activity',
                        'sum'
                    ),
                    active_hours=(
                        'hour_timestamp',
                        'nunique'
                    )
                )
            )

            grid_path = (
                output_dir /
                "grid_summary.csv"
            )

            grid_summary.to_csv(
                grid_path,
                index=False
            )

            self.logger.info(
                "Grid summary exported: %s",
                grid_path
            )

            self.logger.info(
                "Summary export completed successfully."
            )

            return {
                "daily_summary": daily_summary,
                "grid_summary": grid_summary,
                "daily_path": daily_path,
                "grid_path": grid_path
            }

        except Exception as exc:

            self.logger.exception(
                "Failed to export summaries."
            )

            raise RuntimeError(
                f"Failed to export summaries: {exc}"
            ) from exc
    # ---------------------------------------------------------
    # OPTIONAL: RUN COMPLETE PIPELINE
    # ---------------------------------------------------------

    def process(self):
        """
        Run the complete processing pipeline.
        """

        self.logger.info(
            "Starting UsageProcessor pipeline."
        )

        self.load_data()
        self.clean_data()
        self.derive_time_features()
        self.aggregate_to_grid_time()
        self.derive_activity_features()
        self.compute_kpis()
        self.export_summary()

        self.logger.info(
            "UsageProcessor pipeline completed successfully."
        )

        return self.analytics_df

    # ---------------------------------------------------------
    # NULL REPORT
    # ---------------------------------------------------------

    def get_null_activity_report(self):
        """
        Return the number of blank activity values handled
        by the curated-layer rule.
        """

        return pd.DataFrame(
            [
                {
                    'column': column,
                    'nulls_handled': count
                }
                for column, count
                in self.null_activity_count.items()
            ]
        )

    