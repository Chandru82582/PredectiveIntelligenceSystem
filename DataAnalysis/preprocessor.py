"""
preprocessor.py
================

Reusable preprocessing / feature-engineering module that mirrors the
pipeline built in `featuring.ipynb`, so the exact same features fed to the
trained LightGBM model during training can be reproduced at prediction
time.

Usage
-----
    from preprocessor import DataPreprocessor

    pre = DataPreprocessor()
    X = pre.transform(raw_df)          # raw_df = new/incoming records
    preds = model.predict(X[pre.FEATURE_COLUMNS])

`raw_df` must contain (at minimum) the same raw columns produced by the
Spark job that generated `curated_usage`:

    timestamp, grid_id, country_code, sms_in_count, sms_out_count,
    call_in_count, call_out_count, internet_usage, total_sms,
    total_calls, total_activity

(`hour`, `day_of_week`, `date`, `input_file_name` are ignored/recomputed
if present — they are not required.)

IMPORTANT — history requirement
--------------------------------
The engineered features rely on rolling windows per `grid_id`:
    * 6-hour rolling windows  (avg_activity_6h, active_hours, peak_activity,
      variability, internet_share)
    * 24-hour rolling windows (prior_baseline_24h, baseline_24h, activity_lag_24h)

To produce valid (non-NaN) features for the *most recent* timestamp of a
grid, you must supply at least the previous 24 hourly records for that
grid_id (more is fine — extra history only improves the rolling stats).
Rows that still contain NaNs after feature engineering (i.e. not enough
history) are dropped by `transform()` by default; set
`dropna=False` if you'd rather inspect/handle them yourself.

Categorical consistency
------------------------
`grid_id` is treated as a LightGBM categorical feature. To make sure the
category codes seen at inference match what the model was trained on,
pass the list of grid ids used during training via `grid_id_categories`
(e.g. `sorted(train_df["grid_id"].unique())`, saved alongside the model).
If not provided, categories are inferred from the input data, which is
fine as long as you always feed the preprocessor a similarly complete set
of grid_ids (not recommended for single-grid, single-row inference).
"""

from __future__ import annotations

from typing import Iterable, Optional

import numpy as np
import pandas as pd

# Small constant used throughout the original notebook to avoid
# division-by-zero when computing ratios.
EPS = 1e-6

# Sums applied when collapsing multiple `country_code` rows into a single
# grid_id + timestamp record (matches `agg_dict` in the notebook).
_AGG_DICT = {
    "total_activity": "sum",
    "internet_usage": "sum",
    "total_sms": "sum",
    "total_calls": "sum",
    "sms_in_count": "sum",
    "sms_out_count": "sum",
    "call_in_count": "sum",
    "call_out_count": "sum",
}

# Final feature order expected by the trained LightGBM model.
FEATURE_COLUMNS = [
    "activity_growth",
    "variability",
    "peak_ratio",
    "internet_share",
    "avg_activity_6h",
    "current_to_baseline_ratio",
    "velocity_1h",
    "acceleration_1h",
    "activity_vs_same_hour_yesterday",
    "sms_to_call_ratio",
    "hour",
    "day_of_week",
    "is_weekend",
    "hour_sin",
    "hour_cos",
    "dow_sin",
    "dow_cos",
]

_REQUIRED_RAW_COLUMNS = [
    "timestamp",
    "grid_id",
    "total_activity",
    "internet_usage",
    "total_sms",
    "total_calls",
    "sms_in_count",
    "sms_out_count",
    "call_in_count",
    "call_out_count",
]


class DataPreprocessor:
    """Reproduces the feature engineering pipeline from featuring.ipynb."""

    FEATURE_COLUMNS = FEATURE_COLUMNS

    def __init__(self, grid_id_categories: Optional[Iterable] = None):
        """
        Parameters
        ----------
        grid_id_categories:
            Optional iterable of the grid_id values seen during training
            (e.g. `sorted(train_df["grid_id"].unique())`). If given, the
            `grid_id` column is encoded as a pandas Categorical with these
            exact categories, guaranteeing the same category codes the
            model was trained with. If omitted, categories are inferred
            from whatever grid_ids are present in the data being
            transformed.
        """
        self.grid_id_categories = (
            sorted(set(grid_id_categories)) if grid_id_categories is not None else None
        )

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------
    def transform(self, raw_df: pd.DataFrame, dropna: bool = True) -> pd.DataFrame:
        """
        Run the full preprocessing/feature-engineering pipeline.

        Parameters
        ----------
        raw_df:
            Raw records as described in the module docstring. May contain
            several rows per (grid_id, timestamp) if multiple
            `country_code`s are present — these are summed together, just
            like in training.
        dropna:
            If True (default), rows that still contain NaN feature values
            (typically the first ~24h of each grid_id's history, where
            rolling/lag windows aren't fully populated) are dropped.

        Returns
        -------
        A DataFrame containing `feature_timestamp`, `grid_id` plus every
        column in `FEATURE_COLUMNS`, ready to be indexed with
        `df[FEATURE_COLUMNS]` and passed to `model.predict(...)`.
        """
        df = self._validate_and_clean(raw_df)
        df_agg = self._aggregate(df)
        df_feat = self._engineer_features(df_agg)

        if dropna:
            df_feat = df_feat.dropna(subset=FEATURE_COLUMNS).reset_index(drop=True)

        return df_feat

    # ------------------------------------------------------------------
    # Internal steps
    # ------------------------------------------------------------------
    def _validate_and_clean(self, raw_df: pd.DataFrame) -> pd.DataFrame:
        missing = [c for c in _REQUIRED_RAW_COLUMNS if c not in raw_df.columns]
        if missing:
            raise ValueError(
                f"Input data is missing required column(s): {missing}. "
                f"Expected at least: {_REQUIRED_RAW_COLUMNS}"
            )

        df = raw_df.copy()

        # Timestamp -> datetime
        df["timestamp"] = pd.to_datetime(df["timestamp"])

        # grid_id -> int (matches `df["grid_id"] = df["grid_id"].astype(int)`)
        df["grid_id"] = df["grid_id"].astype(int)

        # Drop columns that aren't used downstream, if present.
        df = df.drop(columns=["input_file_name"], errors="ignore")

        return df

    def _aggregate(self, df: pd.DataFrame) -> pd.DataFrame:
        """Collapse (grid_id, timestamp, country_code) rows into a single
        (grid_id, timestamp) row via summation, matching the notebook's
        `df_agg` construction."""
        df_agg = (
            df.groupby(["grid_id", "timestamp"], as_index=False)
            .agg(_AGG_DICT)
            .sort_values(["grid_id", "timestamp"])
            .reset_index(drop=True)
        )
        return df_agg

    def _engineer_features(self, df_agg: pd.DataFrame) -> pd.DataFrame:
        df_agg = df_agg.copy()
        grid_group = df_agg.groupby("grid_id")

        # --- Baseline (used for current_to_baseline_ratio) ---
        df_agg["baseline_24h"] = grid_group["total_activity"].transform(
            lambda s: s.rolling(24, min_periods=6).median()
        )

        df_agg["feature_timestamp"] = df_agg["timestamp"]

        # --- Short/long-term rolling activity stats ---
        df_agg["avg_activity_6h"] = grid_group["total_activity"].transform(
            lambda s: s.rolling(6, min_periods=1).mean()
        )
        df_agg["prior_baseline_24h"] = grid_group["total_activity"].transform(
            lambda s: s.rolling(24, min_periods=1).mean()
        )

        df_agg["activity_growth"] = (df_agg["avg_activity_6h"] + EPS) / (
            df_agg["prior_baseline_24h"] + EPS
        )

        # df_agg["active_hours"] = grid_group["total_activity"].transform(
        #     lambda s: (s > 0).rolling(6, min_periods=1).sum()
        # )

        df_agg["peak_activity"] = grid_group["total_activity"].transform(
            lambda s: s.rolling(6, min_periods=1).max()
        )
        df_agg["peak_ratio"] = (df_agg["peak_activity"] + EPS) / (
            df_agg["avg_activity_6h"] + EPS
        )

        roll_std = grid_group["total_activity"].transform(
            lambda s: s.rolling(6, min_periods=1).std().fillna(0)
        )
        df_agg["variability"] = roll_std / (df_agg["avg_activity_6h"] + EPS)

        df_agg["current_to_baseline_ratio"] = (df_agg["total_activity"] + EPS) / (
            df_agg["baseline_24h"] + EPS
        )

        # --- Lags & momentum ---
        df_agg["activity_lag_1h"] = grid_group["total_activity"].shift(1)
        df_agg["activity_lag_2h"] = grid_group["total_activity"].shift(2)
        df_agg["activity_lag_24h"] = grid_group["total_activity"].shift(24)

        df_agg["velocity_1h"] = df_agg["total_activity"] - df_agg["activity_lag_1h"]
        df_agg["acceleration_1h"] = (
            df_agg["total_activity"]
            - 2 * df_agg["activity_lag_1h"]
            + df_agg["activity_lag_2h"]
        )
        df_agg["activity_vs_same_hour_yesterday"] = (df_agg["total_activity"] + EPS) / (
            df_agg["activity_lag_24h"] + EPS
        )

        # --- Traffic composition ---
        roll_internet = grid_group["internet_usage"].transform(
            lambda s: s.rolling(6, min_periods=1).sum()
        )
        roll_total = grid_group["total_activity"].transform(
            lambda s: s.rolling(6, min_periods=1).sum()
        )
        df_agg["internet_share"] = (roll_internet + EPS) / (roll_total + EPS)
        df_agg["sms_to_call_ratio"] = (df_agg["total_sms"] + EPS) / (
            df_agg["total_calls"] + EPS
        )

        # --- Temporal features ---
        hour = df_agg["feature_timestamp"].dt.hour
        dow = df_agg["feature_timestamp"].dt.dayofweek
        df_agg["hour"] = hour
        df_agg["day_of_week"] = dow
        df_agg["is_weekend"] = dow.isin([5, 6]).astype(int)
        df_agg["hour_sin"] = np.sin(2 * np.pi * hour / 24.0)
        df_agg["hour_cos"] = np.cos(2 * np.pi * hour / 24.0)
        df_agg["dow_sin"] = np.sin(2 * np.pi * dow / 7.0)
        df_agg["dow_cos"] = np.cos(2 * np.pi * dow / 7.0)

        # # --- grid_id as categorical (consistent with training encoding) ---
        # if self.grid_id_categories is not None:
        #     df_agg["grid_id"] = pd.Categorical(
        #         df_agg["grid_id"], categories=self.grid_id_categories
        #     )
        # else:
        #     df_agg["grid_id"] = df_agg["grid_id"].astype("category")
        df_agg = df_agg.drop(columns = ["grid_id"])

        return df_agg


if __name__ == "__main__":
    # Minimal smoke test / usage example with synthetic data.
    rng = pd.date_range("2024-01-01", periods=48, freq="h")
    demo = pd.DataFrame(
        {
            "timestamp": list(rng) * 1,
            "grid_id": [1] * 48,
            "country_code": [0] * 48,
            "sms_in_count": np.random.rand(48),
            "sms_out_count": np.random.rand(48),
            "call_in_count": np.random.rand(48),
            "call_out_count": np.random.rand(48),
            "internet_usage": np.random.rand(48) * 10,
            "total_sms": np.random.rand(48),
            "total_calls": np.random.rand(48),
            "total_activity": np.random.rand(48) * 10,
        }
    )

    pre = DataPreprocessor()
    features = pre.transform(demo)
    print(features[["feature_timestamp"] + FEATURE_COLUMNS].tail())