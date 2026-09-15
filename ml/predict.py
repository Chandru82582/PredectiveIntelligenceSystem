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

import re

try:
    from ml.preprocessor import DataPreprocessor
except ImportError:
    from preprocessor import DataPreprocessor


def _extract_model_version(filename: str) -> int:
    """Extracts integer version number from filenames like lgbm_high_activity_v3.joblib -> 3."""
    match = re.search(r"v(\d+)", filename, re.IGNORECASE)
    return int(match.group(1)) if match else -1


def list_available_models() -> List[str]:
    """Scans /ml/models and /DataAnalysis/models directories and returns all available
    model filenames sorted descending by version number (highest version first)."""
    dirs_to_check = [TRAINED_MODELS_DIR, ROOT_DIR / "DataAnalysis" / "models"]
    found = set()
    for d in dirs_to_check:
        if d.exists():
            for f in d.glob("*.joblib"):
                found.add(f.name)

    if not found:
        return ["lgbm_high_activity_v3.joblib"]

    # Sort descending by extracted version number (e.g. v3 > v2 > v1), then name
    return sorted(found, key=lambda m: (_extract_model_version(m), m), reverse=True)


def get_highest_available_model() -> str:
    """Returns the highest available model version filename as default."""
    models = list_available_models()
    return models[0] if models else "lgbm_high_activity_v3.joblib"


def get_default_threshold(model_name: Optional[str] = None) -> float:
    """Extracts and returns the optimal threshold stored in the model joblib bundle."""
    import joblib

    target_name = model_name or get_highest_available_model()
    path = TRAINED_MODELS_DIR / target_name
    if not path.exists():
        path = ROOT_DIR / "DataAnalysis" / "models" / target_name

    if path.exists():
        try:
            bundle = joblib.load(path)
            if isinstance(bundle, dict):
                opt = bundle.get("optimal_threshold", bundle.get("threshold"))
                if opt is not None:
                    return float(opt)
        except Exception:
            pass
    return 0.7134


DEFAULT_MODEL_NAME = get_highest_available_model()
DEFAULT_THRESHOLD = get_default_threshold()


class HighActivityPredictor:
    """Predicts whether a grid's *next* hour will be 'high activity'
    (>= 1.5x its within-day baseline), given its trailing hourly history."""

    MIN_HISTORY_HOURS = 24

    def __init__(self, model_name: Optional[str] = None, threshold: Optional[float] = None):
        import joblib

        chosen_name = (
            model_name
            if (isinstance(model_name, str) and model_name.strip())
            else get_highest_available_model()
        )
        model_path = TRAINED_MODELS_DIR / chosen_name

        if not model_path.exists():
            # Fallback to DataAnalysis/models
            fallback_path = ROOT_DIR / "DataAnalysis" / "models" / chosen_name
            if fallback_path.exists():
                model_path = fallback_path
            else:
                # If chosen name not found, try highest available model
                default_name = get_highest_available_model()
                default_path = TRAINED_MODELS_DIR / default_name
                if not default_path.exists():
                    default_path = ROOT_DIR / "DataAnalysis" / "models" / default_name
                if default_path.exists():
                    model_path = default_path
                else:
                    raise FileNotFoundError(f"Model file not found: {chosen_name} in {TRAINED_MODELS_DIR}")

        self.model_name = model_path.name
        bundle = joblib.load(model_path)
        self.model = bundle["model"]

        # Use the optimal threshold from the model's joblib bundle as default
        bundle_optimal = bundle.get("optimal_threshold", bundle.get("threshold"))
        if threshold is not None:
            self.threshold = float(threshold)
        elif bundle_optimal is not None:
            self.threshold = float(bundle_optimal)
        else:
            self.threshold = DEFAULT_THRESHOLD

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
        features["threshold"] = self.threshold
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
        latest["threshold"] = self.threshold
        latest["optimal_threshold"] = self.threshold
        return latest


@lru_cache(maxsize=32)
def get_predictor(model_name: Optional[str] = None, threshold: Optional[float] = None) -> HighActivityPredictor:
    """Cached predictor instance per model filename and threshold."""
    return HighActivityPredictor(model_name=model_name, threshold=threshold)

