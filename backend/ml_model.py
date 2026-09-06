"""
ml_model.py
===========

Loads the trained LightGBM "next-hour high activity" classifier
(DataAnalysis/models/lgbm_high_activity_v1.joblib) and exposes a single
`get_predictor()` accessor used by the `/predict/*` routes.

Reuses `DataAnalysis/preprocessor.py` (loaded directly from its file path,
so DataAnalysis doesn't need to be an installed/importable package) to
guarantee the exact same feature engineering used at training time.

Categorical encoding note
--------------------------
The model bundle's `grid_categories` are the *string* representations of
grid_id (e.g. "1", "4365") — that's how `grid_id` was categorical-encoded
in the training notebook, and LightGBM bakes those exact codes into the
trained splits. `DataPreprocessor` produces an int-categorical `grid_id`
by default, so after running it we re-encode `grid_id` as a pandas
Categorical over the bundle's string categories before calling
`model.predict_proba` — otherwise every grid_id would fall outside the
categories the model was trained on and silently lose all grid-specific
signal.
"""

from __future__ import annotations

import importlib.util
from functools import lru_cache
from pathlib import Path
from typing import Optional

import numpy as np
import pandas as pd

BACKEND_DIR = Path(__file__).resolve().parent
DATA_ANALYSIS_DIR = BACKEND_DIR.parent / "DataAnalysis"
MODEL_PATH = DATA_ANALYSIS_DIR / "models" / "lgbm_high_activity_v1.joblib"


def _load_preprocessor_module():
    spec = importlib.util.spec_from_file_location(
        "_data_analysis_preprocessor", DATA_ANALYSIS_DIR / "preprocessor.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


_preprocessor_module = _load_preprocessor_module()
DataPreprocessor = _preprocessor_module.DataPreprocessor


class HighActivityPredictor:
    """Predicts whether a grid's *next* hour will be "high activity"
    (>= 1.5x its within-day baseline), given its trailing hourly history."""

    # Rolling features need >=24h of prior history to be non-NaN for the
    # most recent row; anything shorter gets dropped by the preprocessor.
    MIN_HISTORY_HOURS = 24

    def __init__(self, model_path: Path = MODEL_PATH):
        import joblib

        bundle = joblib.load(model_path)
        self.model = bundle["model"]
        self.threshold = float(bundle["optimal_threshold"])
        self.feature_columns = list(bundle["features"])
        self.grid_categories = list(bundle["grid_categories"])
        self.metrics = bundle["metrics"]
        self.high_activity_multiplier = float(bundle["high_threshold"])
        self.preprocessor = DataPreprocessor()

    def predict_from_raw(self, raw_df: pd.DataFrame) -> pd.DataFrame:
        """Runs the full preprocessing + prediction pipeline.

        `raw_df` must contain the raw columns `DataPreprocessor` expects
        (see DataAnalysis/preprocessor.py), covering a single grid_id's
        trailing hourly history.

        Returns the engineered feature table (only rows with enough
        history to be valid) with `probability`, `prediction` and
        `risk_label` columns appended. Empty if no row had enough history.
        """
        features = self.preprocessor.transform(raw_df, dropna=True)
        if features.empty:
            return features

        X = features[self.feature_columns].copy()
        X["grid_id"] = pd.Categorical(
            X["grid_id"].astype(int).astype(str), categories=self.grid_categories
        )

        proba = self.model.predict_proba(X)[:, 1]
        features = features.copy()
        features["probability"] = proba
        features["prediction"] = (proba >= self.threshold).astype(int)
        features["risk_label"] = np.where(
            features["prediction"] == 1, "HIGH_ACTIVITY_RISK", "NORMAL"
        )
        return features

    def predict_latest(self, raw_df: pd.DataFrame) -> Optional[dict]:
        """Convenience wrapper: returns just the most recent valid row (by
        `feature_timestamp`) as a dict, or None if there wasn't enough
        trailing history to produce a valid feature row at all."""
        result = self.predict_from_raw(raw_df)
        if result.empty:
            return None
        return result.sort_values("feature_timestamp").iloc[-1].to_dict()


@lru_cache(maxsize=1)
def get_predictor() -> HighActivityPredictor:
    """Process-lifetime singleton — the joblib bundle (~6MB) and the
    LightGBM booster are loaded once and reused across requests."""
    return HighActivityPredictor()
