from __future__ import annotations

import sys
from functools import lru_cache
from pathlib import Path
from typing import Optional, List, Dict, Any

import numpy as np
import pandas as pd

ML_DIR = Path(__file__).resolve().parent
ROOT_DIR = ML_DIR.parent
TRAINED_MODELS_DIR = ML_DIR / "models"

for p in [str(ROOT_DIR), str(ML_DIR)]:
    if p not in sys.path:
        sys.path.insert(0, p)

try:
    from ml.preprocessor import DataPreprocessor
except ImportError:
    from preprocessor import DataPreprocessor

DEFAULT_MODEL_NAME = "lgbm_high_activity_v2.joblib"


def list_available_models() -> List[str]:
    """Scans /ml/models directory and returns all available model filenames."""
    if not TRAINED_MODELS_DIR.exists():
        return [DEFAULT_MODEL_NAME]
    
    models = [f.name for f in TRAINED_MODELS_DIR.glob("*.joblib")]
    if not models:
        # Check fallback
        fallback = ROOT_DIR / "DataAnalysis" / "models"
        if fallback.exists():
            models = [f.name for f in fallback.glob("*.joblib")]
    
    # Sort with v2 first as default preference
    models.sort(key=lambda m: (0 if "v2" in m else 1, m))
    return models if models else [DEFAULT_MODEL_NAME]


class HighActivityPredictor:
    """Predicts whether a grid's *next* hour will be 'high activity'
    (>= 1.5x its within-day baseline), given its trailing hourly history."""

    MIN_HISTORY_HOURS = 24

    def __init__(self, model_name: Optional[str] = None):
        import joblib

        chosen_name = model_name if (isinstance(model_name, str) and model_name.strip()) else DEFAULT_MODEL_NAME
        model_path = TRAINED_MODELS_DIR / chosen_name

        if not model_path.exists():
            # Fallback to DataAnalysis/models
            fallback_path = ROOT_DIR / "DataAnalysis" / "models" / chosen_name
            if fallback_path.exists():
                model_path = fallback_path
            else:
                # If chosen name not found, try default
                default_path = TRAINED_MODELS_DIR / DEFAULT_MODEL_NAME
                if default_path.exists():
                    model_path = default_path
                else:
                    raise FileNotFoundError(f"Model file not found: {chosen_name} in {TRAINED_MODELS_DIR}")

        self.model_name = model_path.name
        bundle = joblib.load(model_path)
        self.model = bundle["model"]
        self.threshold = float(bundle.get("optimal_threshold", 0.50))
        self.feature_columns = list(bundle["features"])
        self.metrics = bundle.get("metrics", {})
        self.high_activity_multiplier = float(bundle.get("high_threshold", 1.5))
        self.preprocessor = DataPreprocessor()

    def predict_from_raw(self, raw_df: pd.DataFrame) -> pd.DataFrame:
        """Runs the full preprocessing + prediction pipeline."""
        features = self.preprocessor.transform(raw_df, dropna=True)
        if features.empty:
            return features

        features = features.copy()
        # Handle models (such as v1) expecting grid_id or active_hours
        if "active_hours" in self.feature_columns and "active_hours" not in features.columns:
            features["active_hours"] = 6
        if "grid_id" in self.feature_columns and "grid_id" not in features.columns:
            grid_vals = (
                raw_df["grid_id"].iloc[-len(features):].astype(str).values
                if "grid_id" in raw_df.columns
                else ["1"] * len(features)
            )
            if hasattr(self.model, "booster_") and getattr(self.model.booster_, "pandas_categorical", None):
                cats = self.model.booster_.pandas_categorical[0]
                features["grid_id"] = pd.Categorical(grid_vals, categories=cats)
            else:
                features["grid_id"] = pd.Categorical(grid_vals)

        for col in self.feature_columns:
            if col not in features.columns:
                features[col] = 0.0

        X = features[self.feature_columns].copy()
        proba = self.model.predict_proba(X)[:, 1]
        features["probability"] = proba
        features["prediction"] = (proba >= self.threshold).astype(int)
        features["risk_label"] = np.where(
            features["prediction"] == 1, "HIGH_ACTIVITY_RISK", "NORMAL"
        )
        return features

    def predict_latest(self, raw_df: pd.DataFrame) -> Optional[dict]:
        """Returns just the most recent valid row (by `feature_timestamp`) as a dict."""
        result = self.predict_from_raw(raw_df)
        if result.empty:
            return None
        latest = result.sort_values("feature_timestamp").iloc[-1].to_dict()
        latest["model_name"] = self.model_name
        return latest


@lru_cache(maxsize=16)
def get_predictor(model_name: Optional[str] = None) -> HighActivityPredictor:
    """Cached predictor instance per model filename."""
    return HighActivityPredictor(model_name=model_name)
