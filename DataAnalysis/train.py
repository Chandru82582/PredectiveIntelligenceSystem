import pyarrow.dataset as ds
import pandas as pd

from sklearn.metrics import (
    accuracy_score,
    classification_report,
    precision_score,
    recall_score,
)
from sklearn.tree import DecisionTreeClassifier


path = r"d:\PredectiveIntelligenceSystem\report_spark\curated_usage"


dataset = ds.dataset(
    path,
    format="parquet",
    partitioning="hive"  # reads date=YYYY-MM-DD partitions
)

table = dataset.to_table()
df = table.to_pandas()

# # # import numpy as np
# # # import pandas as pd
# # # 
# # # =========================================================================
# # # 1. PREPROCESSING & AGGREGATION
# # # =========================================================================


# # def aggregate_grid_hourly(df: pd.DataFrame) -> pd.DataFrame:
# #     """Ensures exactly one record per (grid_id, timestamp) pair."""
# #     df = df.copy()
# #     df["timestamp"] = pd.to_datetime(df["timestamp"])

# #     agg_dict = {
# #         "total_activity": "sum",
# #         "internet_usage": "sum",
# #         "total_sms": "sum",
# #         "total_calls": "sum",
# #     }
# #     for col in [
# #         "sms_in_count",
# #         "sms_out_count",
# #         "call_in_count",
# #         "call_out_count",
# #     ]:
# #         if col in df.columns:
# #             agg_dict[col] = "sum"

# #     df_agg = (
# #         df.groupby(["grid_id", "timestamp"], as_index=False)
# #         .agg(agg_dict)
# #         .sort_values(["grid_id", "timestamp"])
# #         .reset_index(drop=True)
# #     )
# #     return df_agg


# # # =========================================================================
# # # 2. TARGET CONSTRUCTION (At interval t+1)
# # # =========================================================================


# # def construct_target_and_telemetry(
# #     df: pd.DataFrame, high_threshold: float = 1.5
# # ) -> pd.DataFrame:
# #     """Computes trailing 24h baseline up to t, and sets target_t1 for interval t+1."""
# #     df = df.copy()
# #     grid_group = df.groupby("grid_id")

# #     df["baseline_24h"] = grid_group["total_activity"].transform(
# #         lambda s: s.rolling(24, min_periods=6).median()
# #     )

# #     df["future_activity_t1"] = grid_group["total_activity"].shift(-1)
# #     df["future_baseline_t1"] = grid_group["baseline_24h"].shift(-1)

# #     valid_target = df["future_activity_t1"].notna() & (
# #         df["future_baseline_t1"] > 0
# #     )
# #     df["target_t1"] = 0
# #     df.loc[
# #         valid_target
# #         & (
# #             df["future_activity_t1"]
# #             >= df["future_baseline_t1"] * high_threshold
# #         ),
# #         "target_t1",
# #     ] = 1

# #     return df


# # # =========================================================================
# # # 3. FEATURE PIPELINE (Pure Activity Trailing Signals <= t)
# # # =========================================================================


# # def build_trailing_features(
# #     df: pd.DataFrame, recent_w: int = 6, prior_w: int = 24
# # ) -> pd.DataFrame:
# #     """Constructs rolling telemetry features, omitting calendar/clock indicators."""
# #     df = df.copy()
# #     eps = 1e-6
# #     grid_group = df.groupby("grid_id")

# #     df["feature_timestamp"] = df["timestamp"]

# #     # 1. avg_activity over recent trailing window [t - recent_w + 1, t]
# #     df["avg_activity"] = grid_group["total_activity"].transform(
# #         lambda s: s.rolling(recent_w, min_periods=1).mean()
# #     )

# #     # 2. Prior baseline window mean [t - prior_w + 1, t] & activity_growth
# #     df["prior_baseline_activity"] = grid_group["total_activity"].transform(
# #         lambda s: s.rolling(prior_w, min_periods=1).mean()
# #     )
# #     df["activity_growth"] = (df["avg_activity"] + eps) / (
# #         df["prior_baseline_activity"] + eps
# #     )

# #     # 3. active_hours: count of hours in recent window with activity > 0
# #     df["active_hours"] = grid_group["total_activity"].transform(
# #         lambda s: (s > 0).rolling(recent_w, min_periods=1).sum()
# #     )

# #     # 4. peak_ratio: peak / average over recent window
# #     df["peak_activity"] = grid_group["total_activity"].transform(
# #         lambda s: s.rolling(recent_w, min_periods=1).max()
# #     )
# #     df["peak_ratio"] = (df["peak_activity"] + eps) / (df["avg_activity"] + eps)

# #     # 5. variability: Coefficient of Variation proxy (std / mean)
# #     roll_std = grid_group["total_activity"].transform(
# #         lambda s: s.rolling(recent_w, min_periods=1).std().fillna(0)
# #     )
# #     df["variability"] = roll_std / (df["avg_activity"] + eps)

# #     # 6. internet_share: internet_activity / total_activity over trailing window
# #     roll_internet = grid_group["internet_usage"].transform(
# #         lambda s: s.rolling(recent_w, min_periods=1).sum()
# #     )
# #     roll_total = grid_group["total_activity"].transform(
# #         lambda s: s.rolling(recent_w, min_periods=1).sum()
# #     )
# #     df["internet_share"] = (roll_internet + eps) / (roll_total + eps)

# #     feature_cols = [
# #         "grid_id",
# #         "feature_timestamp",
# #         "avg_activity",
# #         "activity_growth",
# #         "active_hours",
# #         "peak_ratio",
# #         "variability",
# #         "internet_share",
# #         "target_t1",
# #     ]

# #     return df[feature_cols].dropna().reset_index(drop=True)


# # # =========================================================================
# # # 4. LEAKAGE UNIT TEST
# # # =========================================================================


# # def test_leakage_boundary(agg_df: pd.DataFrame) -> None:
# #     sample_grid = agg_df["grid_id"].iloc[0]
# #     grid_data = (
# #         agg_df[agg_df["grid_id"] == sample_grid]
# #         .sort_values("timestamp")
# #         .copy()
# #         .reset_index(drop=True)
# #     )

# #     if len(grid_data) < 15:
# #         return

# #     t_idx = 10
# #     t_timestamp = grid_data["timestamp"].iloc[t_idx]

# #     df_base_target = construct_target_and_telemetry(grid_data)
# #     baseline_ft = build_trailing_features(df_base_target)

# #     row_baseline = (
# #         baseline_ft[baseline_ft["feature_timestamp"] == t_timestamp]
# #         .drop(columns=["target_t1"])
# #         .reset_index(drop=True)
# #     )

# #     perturbed_data = grid_data.copy()
# #     perturbed_data.loc[t_idx + 1, "total_activity"] += 1e6
# #     perturbed_data.loc[t_idx + 1, "internet_usage"] += 1e6

# #     df_perturbed_target = construct_target_and_telemetry(perturbed_data)
# #     perturbed_ft = build_trailing_features(df_perturbed_target)

# #     row_perturbed = (
# #         perturbed_ft[perturbed_ft["feature_timestamp"] == t_timestamp]
# #         .drop(columns=["target_t1"])
# #         .reset_index(drop=True)
# #     )

# #     pd.testing.assert_frame_equal(row_baseline, row_perturbed)
# #     print("✓ Leakage Guard Test Passed: Features at cutoff t remain invariant to t+1.")


# # # =========================================================================
# # # 5. TRAINING & EVALUATION PIPELINE
# # # =========================================================================


# # def run_training_pipeline(raw_df: pd.DataFrame, train_ratio: float = 0.8):
# #     print("[1/5] Aggregating raw telemetry...")
# #     agg_df = aggregate_grid_hourly(raw_df)

# #     print("[2/5] Running Leakage Guard Test...")
# #     test_leakage_boundary(agg_df)

# #     print("[3/5] Building forward target and signal features...")
# #     labeled_df = construct_target_and_telemetry(agg_df)
# #     feature_table = build_trailing_features(labeled_df)

# #     print("[4/5] Chronological splitting...")
# #     feature_table = feature_table.sort_values("feature_timestamp").reset_index(
# #         drop=True
# #     )

# #     split_idx = int(len(feature_table) * train_ratio)
# #     train_df = feature_table.iloc[:split_idx]
# #     test_df = feature_table.iloc[split_idx:]

# #     print("-" * 65)
# #     print(
# #         f"Train Set Window : {train_df['feature_timestamp'].min()} --> {train_df['feature_timestamp'].max()} (N={len(train_df):,})"
# #     )
# #     print(
# #         f"Test Set Window  : {test_df['feature_timestamp'].min()} --> {test_df['feature_timestamp'].max()} (N={len(test_df):,})"
# #     )
# #     print("-" * 65)

# #     # 6 telemetry features strictly
# #     features = [
# #         "avg_activity",
# #         "activity_growth",
# #         "active_hours",
# #         "peak_ratio",
# #         "variability",
# #         "internet_share",
# #     ]

# #     X_train, y_train = train_df[features], train_df["target_t1"]
# #     X_test, y_test = test_df[features], test_df["target_t1"]

# #     train_base_rate = y_train.mean()
# #     test_base_rate = y_test.mean()

# #     print(f"Train Positive Base Rate: {train_base_rate:.2%}")
# #     print(f"Test Positive Base Rate : {test_base_rate:.2%}")
# #     print("-" * 65)

# #     print("[5/5] Training Decision Tree Classifier...")
# #     model = DecisionTreeClassifier(
# #         max_depth=5,
# #         min_samples_leaf=100,
# #         class_weight="balanced",
# #         random_state=42,
# #     )
# #     model.fit(X_train, y_train)

# #     y_pred = model.predict(X_test)

# #     acc = accuracy_score(y_test, y_pred)
# #     prec = precision_score(y_test, y_pred, zero_division=0)
# #     rec = recall_score(y_test, y_pred, zero_division=0)

# #     print("\n" + "=" * 65)
# #     print("MODEL PERFORMANCE ON TEST SET")
# #     print("=" * 65)
# #     print(
# #         f"Accuracy                 : {acc:.4f}  (Baseline context: {test_base_rate:.2%})"
# #     )
# #     print(f"Precision (PPV)          : {prec:.4f}")
# #     print(f"Recall (Sensitivity)     : {rec:.4f}")
# #     print("\nClassification Report:")
# #     print(classification_report(y_test, y_pred, digits=4))

# #     print("=" * 65)
# #     print("FEATURE IMPORTANCE CHECK")
# #     print("=" * 65)
# #     importances = pd.Series(
# #         model.feature_importances_, index=features
# #     ).sort_values(ascending=False)
# #     for feat, imp in importances.items():
# #         print(f"{feat:<25}: {imp:.4f}")

# #     return model, feature_table


# # # =========================================================================
# # # 6. EXECUTE
# # # =========================================================================

# # trained_model, final_feature_table = run_training_pipeline(df)
























# # import numpy as np
# # import pandas as pd
# # from sklearn.ensemble import HistGradientBoostingClassifier
# # from sklearn.linear_model import LogisticRegression
# # from sklearn.metrics import (
# #     average_precision_score,
# #     classification_report,
# #     precision_recall_curve,
# #     roc_auc_score,
# # )
# # from sklearn.pipeline import Pipeline
# # from sklearn.preprocessing import StandardScaler

# # # =========================================================================
# # # 1. PREPROCESSING & AGGREGATION
# # # =========================================================================


# # def aggregate_grid_hourly(df: pd.DataFrame) -> pd.DataFrame:
# #     """Ensures exactly one record per (grid_id, timestamp) pair by summing sub-metrics."""
# #     df = df.copy()
# #     df["timestamp"] = pd.to_datetime(df["timestamp"])

# #     agg_dict = {
# #         "total_activity": "sum",
# #         "internet_usage": "sum",
# #         "total_sms": "sum",
# #         "total_calls": "sum",
# #     }
# #     for col in [
# #         "sms_in_count",
# #         "sms_out_count",
# #         "call_in_count",
# #         "call_out_count",
# #     ]:
# #         if col in df.columns:
# #             agg_dict[col] = "sum"

# #     df_agg = (
# #         df.groupby(["grid_id", "timestamp"], as_index=False)
# #         .agg(agg_dict)
# #         .sort_values(["grid_id", "timestamp"])
# #         .reset_index(drop=True)
# #     )
# #     return df_agg


# # # =========================================================================
# # # 2. TARGET & TRAILING FEATURE EXTRACTION
# # # =========================================================================


# # def create_feature_table(
# #     df: pd.DataFrame,
# #     high_threshold: float = 1.5,
# #     recent_w: int = 6,
# #     prior_w: int = 24,
# # ) -> pd.DataFrame:
# #     """Creates the forward target (t+1) and extracts trailing features up to t."""
# #     df = df.copy()
# #     eps = 1e-6
# #     grid_group = df.groupby("grid_id")

# #     # --- Target Calculation at t+1 ---
# #     df["baseline_24h"] = grid_group["total_activity"].transform(
# #         lambda s: s.rolling(prior_w, min_periods=6).median()
# #     )
# #     df["future_activity_t1"] = grid_group["total_activity"].shift(-1)
# #     df["future_baseline_t1"] = grid_group["baseline_24h"].shift(-1)

# #     valid_target = df["future_activity_t1"].notna() & (
# #         df["future_baseline_t1"] > 0
# #     )
# #     df["target_high_activity"] = 0
# #     df.loc[
# #         valid_target
# #         & (
# #             df["future_activity_t1"]
# #             >= df["future_baseline_t1"] * high_threshold
# #         ),
# #         "target_high_activity",
# #     ] = 1

# #     # --- Trailing Features at cutoff t ---
# #     df["feature_timestamp"] = df["timestamp"]

# #     # 1. avg_activity & activity_growth
# #     df["avg_activity"] = grid_group["total_activity"].transform(
# #         lambda s: s.rolling(recent_w, min_periods=1).mean()
# #     )
# #     df["prior_baseline_activity"] = grid_group["total_activity"].transform(
# #         lambda s: s.rolling(prior_w, min_periods=1).mean()
# #     )
# #     df["activity_growth"] = (df["avg_activity"] + eps) / (
# #         df["prior_baseline_activity"] + eps
# #     )

# #     # 2. active_hours
# #     df["active_hours"] = grid_group["total_activity"].transform(
# #         lambda s: (s > 0).rolling(recent_w, min_periods=1).sum()
# #     )

# #     # 3. peak_ratio
# #     df["peak_activity"] = grid_group["total_activity"].transform(
# #         lambda s: s.rolling(recent_w, min_periods=1).max()
# #     )
# #     df["peak_ratio"] = (df["peak_activity"] + eps) / (df["avg_activity"] + eps)

# #     # 4. variability (std / mean)
# #     roll_std = grid_group["total_activity"].transform(
# #         lambda s: s.rolling(recent_w, min_periods=1).std().fillna(0)
# #     )
# #     df["variability"] = roll_std / (df["avg_activity"] + eps)

# #     # 5. internet_share
# #     roll_internet = grid_group["internet_usage"].transform(
# #         lambda s: s.rolling(recent_w, min_periods=1).sum()
# #     )
# #     roll_total = grid_group["total_activity"].transform(
# #         lambda s: s.rolling(recent_w, min_periods=1).sum()
# #     )
# #     df["internet_share"] = (roll_internet + eps) / (roll_total + eps)

# #     feature_cols = [
# #         "grid_id",
# #         "feature_timestamp",
# #         "activity_growth",
# #         "variability",
# #         "peak_ratio",
# #         "internet_share",
# #         "avg_activity",
# #         "active_hours",
# #         "target_high_activity",
# #     ]

# #     return df[feature_cols].dropna().reset_index(drop=True)


# # # =========================================================================
# # # 3. CHRONOLOGICAL SPLIT & EVALUATION
# # # =========================================================================

# # FEATURE_COLS = [
# #     "activity_growth",
# #     "variability",
# #     "peak_ratio",
# #     "internet_share",
# #     "avg_activity",
# #     "active_hours",
# # ]
# # TARGET_COL = "target_high_activity"
# # TIMESTAMP_COL = "feature_timestamp"


# # def split_chronological(df: pd.DataFrame, train_ratio: float = 0.8):
# #     df_sorted = df.sort_values(TIMESTAMP_COL).reset_index(drop=True)

# #     split_idx = int(len(df_sorted) * train_ratio)
# #     train_df = df_sorted.iloc[:split_idx]
# #     test_df = df_sorted.iloc[split_idx:]

# #     X_train = train_df[FEATURE_COLS]
# #     y_train = train_df[TARGET_COL].astype(int)

# #     X_test = test_df[FEATURE_COLS]
# #     y_test = test_df[TARGET_COL].astype(int)

# #     print("=" * 65)
# #     print("DATA SPLIT SUMMARY")
# #     print("=" * 65)
# #     print(
# #         f"Train: {train_df[TIMESTAMP_COL].min()} -> {train_df[TIMESTAMP_COL].max()} (N={len(train_df):,})"
# #     )
# #     print(
# #         f"Test : {test_df[TIMESTAMP_COL].min()} -> {test_df[TIMESTAMP_COL].max()} (N={len(test_df):,})"
# #     )
# #     print(f"Train Base Rate (Positives): {y_train.mean():.2%}")
# #     print(f"Test Base Rate  (Positives): {y_test.mean():.2%}")
# #     print("=" * 65)

# #     return X_train, y_train, X_test, y_test


# # def evaluate_pipeline(pipeline: Pipeline, X_test: pd.DataFrame, y_test: pd.Series):
# #     y_proba = pipeline.predict_proba(X_test)[:, 1]

# #     roc_auc = roc_auc_score(y_test, y_proba)
# #     pr_auc = average_precision_score(y_test, y_proba)

# #     print("\n" + "=" * 65)
# #     print("GLOBAL PERFORMANCE METRICS")
# #     print("=" * 65)
# #     print(f"ROC-AUC : {roc_auc:.4f}")
# #     print(f"PR-AUC  : {pr_auc:.4f}")

# #     # Optimal F1 Threshold Selection
# #     precisions, recalls, thresholds = precision_recall_curve(y_test, y_proba)
# #     f1_scores = (
# #         2
# #         * (precisions * recalls)
# #         / np.clip(precisions + recalls, 1e-6, None)
# #     )
# #     best_idx = np.argmax(f1_scores[:-1])
# #     optimal_threshold = thresholds[best_idx]

# #     print("\nDefault Threshold (0.50) Report:")
# #     print(
# #         classification_report(
# #             y_test, (y_proba >= 0.50).astype(int), digits=4, zero_division=0
# #         )
# #     )

# #     print(f"Optimal F1 Threshold ({optimal_threshold:.4f}) Report:")
# #     print(
# #         classification_report(
# #             y_test,
# #             (y_proba >= optimal_threshold).astype(int),
# #             digits=4,
# #             zero_division=0,
# #         )
# #     )


# # def train_and_evaluate(
# #     raw_df: pd.DataFrame, model_type: str = "gradient_boosting"
# # ):
# #     print("[1/3] Aggregating raw telemetry...")
# #     agg_df = aggregate_grid_hourly(raw_df)

# #     print("[2/3] Engineering trailing features & forward target...")
# #     feature_table = create_feature_table(agg_df)

# #     print("[3/3] Splitting and Training...")
# #     X_train, y_train, X_test, y_test = split_chronological(feature_table)

# #     if model_type == "logistic_regression":
# #         model = LogisticRegression(
# #             class_weight="balanced", max_iter=1000, random_state=42
# #         )
# #         pipeline = Pipeline([("scaler", StandardScaler()), ("classifier", model)])
# #     else:
# #         model = HistGradientBoostingClassifier(
# #             max_iter=150,
# #             learning_rate=0.05,
# #             max_depth=5,
# #             class_weight="balanced",
# #             random_state=42,
# #         )
# #         pipeline = Pipeline([("classifier", model)])

# #     pipeline.fit(X_train, y_train)
# #     evaluate_pipeline(pipeline, X_test, y_test)

# #     return pipeline, feature_table


# # # =========================================================================
# # # 4. EXECUTION
# # # =========================================================================

# # if __name__ == "__main__":
# #     # Ensure your raw data is loaded into `df`:
# #     # df = pd.read_csv("telecom_data.csv")

# #     pipeline, feature_table = train_and_evaluate(
# #         df, model_type="gradient_boosting"
# #     )













# import numpy as np
# import pandas as pd
# from sklearn.ensemble import HistGradientBoostingClassifier
# from sklearn.linear_model import LogisticRegression
# from sklearn.metrics import (
#     average_precision_score,
#     classification_report,
#     precision_recall_curve,
#     roc_auc_score,
# )
# from sklearn.pipeline import Pipeline
# from sklearn.preprocessing import StandardScaler

# # =========================================================================
# # 1. PREPROCESSING & AGGREGATION
# # =========================================================================


# def aggregate_grid_hourly(df: pd.DataFrame) -> pd.DataFrame:
#     """Ensures exactly one record per (grid_id, timestamp) pair by summing sub-metrics."""
#     df = df.copy()
#     df["timestamp"] = pd.to_datetime(df["timestamp"])

#     agg_dict = {
#         "total_activity": "sum",
#         "internet_usage": "sum",
#         "total_sms": "sum",
#         "total_calls": "sum",
#     }
#     for col in [
#         "sms_in_count",
#         "sms_out_count",
#         "call_in_count",
#         "call_out_count",
#     ]:
#         if col in df.columns:
#             agg_dict[col] = "sum"

#     df_agg = (
#         df.groupby(["grid_id", "timestamp"], as_index=False)
#         .agg(agg_dict)
#         .sort_values(["grid_id", "timestamp"])
#         .reset_index(drop=True)
#     )
#     return df_agg


# # =========================================================================
# # 2. TARGET & TRAILING FEATURE EXTRACTION
# # =========================================================================


# def create_feature_table(
#     df: pd.DataFrame,
#     high_threshold: float = 1.5,
#     recent_w: int = 6,
#     prior_w: int = 24,
# ) -> pd.DataFrame:
#     """Creates the forward target (t+1) and extracts trailing & temporal features up to t."""
#     df = df.copy()
#     eps = 1e-6
#     grid_group = df.groupby("grid_id")

#     # --- Target Calculation at t+1 ---
#     df["baseline_24h"] = grid_group["total_activity"].transform(
#         lambda s: s.rolling(prior_w, min_periods=6).median()
#     )
#     df["future_activity_t1"] = grid_group["total_activity"].shift(-1)
#     df["future_baseline_t1"] = grid_group["baseline_24h"].shift(-1)

#     valid_target = df["future_activity_t1"].notna() & (
#         df["future_baseline_t1"] > 0
#     )
#     df["target_high_activity"] = 0
#     df.loc[
#         valid_target
#         & (
#             df["future_activity_t1"]
#             >= df["future_baseline_t1"] * high_threshold
#         ),
#         "target_high_activity",
#     ] = 1

#     # --- Cutoff Timestamp ---
#     df["feature_timestamp"] = df["timestamp"]

#     # --- Activity-Based Trailing Features (Window <= t) ---
#     df["avg_activity"] = grid_group["total_activity"].transform(
#         lambda s: s.rolling(recent_w, min_periods=1).mean()
#     )
#     df["prior_baseline_activity"] = grid_group["total_activity"].transform(
#         lambda s: s.rolling(prior_w, min_periods=1).mean()
#     )
#     df["activity_growth"] = (df["avg_activity"] + eps) / (
#         df["prior_baseline_activity"] + eps
#     )

#     df["active_hours"] = grid_group["total_activity"].transform(
#         lambda s: (s > 0).rolling(recent_w, min_periods=1).sum()
#     )

#     df["peak_activity"] = grid_group["total_activity"].transform(
#         lambda s: s.rolling(recent_w, min_periods=1).max()
#     )
#     df["peak_ratio"] = (df["peak_activity"] + eps) / (df["avg_activity"] + eps)

#     roll_std = grid_group["total_activity"].transform(
#         lambda s: s.rolling(recent_w, min_periods=1).std().fillna(0)
#     )
#     df["variability"] = roll_std / (df["avg_activity"] + eps)

#     roll_internet = grid_group["internet_usage"].transform(
#         lambda s: s.rolling(recent_w, min_periods=1).sum()
#     )
#     roll_total = grid_group["total_activity"].transform(
#         lambda s: s.rolling(recent_w, min_periods=1).sum()
#     )
#     df["internet_share"] = (roll_internet + eps) / (roll_total + eps)

#     # --- Date & Hour Features (At cutoff t) ---
#     hour = df["feature_timestamp"].dt.hour
#     day_of_week = df["feature_timestamp"].dt.dayofweek

#     df["hour"] = hour
#     df["day_of_week"] = day_of_week
#     df["is_weekend"] = day_of_week.isin([5, 6]).astype(int)

#     # Cyclical encodings for smooth periodic transitions
#     df["hour_sin"] = np.sin(2 * np.pi * hour / 24.0)
#     df["hour_cos"] = np.cos(2 * np.pi * hour / 24.0)
#     df["dow_sin"] = np.sin(2 * np.pi * day_of_week / 7.0)
#     df["dow_cos"] = np.cos(2 * np.pi * day_of_week / 7.0)

#     feature_cols = [
#         "grid_id",
#         "feature_timestamp",
#         # Activity signals
#         "activity_growth",
#         "variability",
#         "peak_ratio",
#         "internet_share",
#         "avg_activity",
#         "active_hours",
#         # Date & Hour signals
#         "hour",
#         "day_of_week",
#         "is_weekend",
#         "hour_sin",
#         "hour_cos",
#         "dow_sin",
#         "dow_cos",
#         # Target
#         "target_high_activity",
#     ]

#     return df[feature_cols].dropna().reset_index(drop=True)


# # =========================================================================
# # 3. CHRONOLOGICAL SPLIT & EVALUATION
# # =========================================================================

# FEATURE_COLS = [
#     # Activity signals
#     "activity_growth",
#     "variability",
#     "peak_ratio",
#     "internet_share",
#     "avg_activity",
#     "active_hours",
#     # Date & Hour signals
#     "hour",
#     "day_of_week",
#     "is_weekend",
#     "hour_sin",
#     "hour_cos",
#     "dow_sin",
#     "dow_cos",
# ]

# TARGET_COL = "target_high_activity"
# TIMESTAMP_COL = "feature_timestamp"


# def split_chronological(df: pd.DataFrame, train_ratio: float = 0.8):
#     df_sorted = df.sort_values(TIMESTAMP_COL).reset_index(drop=True)

#     split_idx = int(len(df_sorted) * train_ratio)
#     train_df = df_sorted.iloc[:split_idx]
#     test_df = df_sorted.iloc[split_idx:]

#     X_train = train_df[FEATURE_COLS]
#     y_train = train_df[TARGET_COL].astype(int)

#     X_test = test_df[FEATURE_COLS]
#     y_test = test_df[TARGET_COL].astype(int)

#     print("=" * 65)
#     print("DATA SPLIT SUMMARY")
#     print("=" * 65)
#     print(
#         f"Train: {train_df[TIMESTAMP_COL].min()} -> {train_df[TIMESTAMP_COL].max()} (N={len(train_df):,})"
#     )
#     print(
#         f"Test : {test_df[TIMESTAMP_COL].min()} -> {test_df[TIMESTAMP_COL].max()} (N={len(test_df):,})"
#     )
#     print(f"Train Base Rate (Positives): {y_train.mean():.2%}")
#     print(f"Test Base Rate  (Positives): {y_test.mean():.2%}")
#     print("=" * 65)

#     return X_train, y_train, X_test, y_test


# def evaluate_pipeline(pipeline: Pipeline, X_test: pd.DataFrame, y_test: pd.Series):
#     y_proba = pipeline.predict_proba(X_test)[:, 1]

#     roc_auc = roc_auc_score(y_test, y_proba)
#     pr_auc = average_precision_score(y_test, y_proba)

#     print("\n" + "=" * 65)
#     print("GLOBAL PERFORMANCE METRICS")
#     print("=" * 65)
#     print(f"ROC-AUC : {roc_auc:.4f}")
#     print(f"PR-AUC  : {pr_auc:.4f}")

#     precisions, recalls, thresholds = precision_recall_curve(y_test, y_proba)
#     f1_scores = (
#         2
#         * (precisions * recalls)
#         / np.clip(precisions + recalls, 1e-6, None)
#     )
#     best_idx = np.argmax(f1_scores[:-1])
#     optimal_threshold = thresholds[best_idx]

#     print("\nDefault Threshold (0.50) Report:")
#     print(
#         classification_report(
#             y_test, (y_proba >= 0.50).astype(int), digits=4, zero_division=0
#         )
#     )

#     print(f"Optimal F1 Threshold ({optimal_threshold:.4f}) Report:")
#     print(
#         classification_report(
#             y_test,
#             (y_proba >= optimal_threshold).astype(int),
#             digits=4,
#             zero_division=0,
#         )
#     )

#     print("=" * 65)
#     print("FEATURE IMPORTANCE CHECK")
#     print("=" * 65)
#     clf = pipeline.named_steps["classifier"]
#     if hasattr(clf, "feature_importances_"):
#         imps = pd.Series(clf.feature_importances_, index=FEATURE_COLS).sort_values(
#             ascending=False
#         )
#         for feat, imp in imps.items():
#             print(f"{feat:<20}: {imp:.4f}")


# def train_and_evaluate(
#     raw_df: pd.DataFrame, model_type: str = "gradient_boosting"
# ):
#     print("[1/3] Aggregating raw telemetry...")
#     agg_df = aggregate_grid_hourly(raw_df)

#     print("[2/3] Engineering trailing & date/hour features...")
#     feature_table = create_feature_table(agg_df)

#     print("[3/3] Chronological Splitting and Training...")
#     X_train, y_train, X_test, y_test = split_chronological(feature_table)

#     if model_type == "logistic_regression":
#         model = LogisticRegression(
#             class_weight="balanced", max_iter=1000, random_state=42
#         )
#         pipeline = Pipeline([("scaler", StandardScaler()), ("classifier", model)])
#     else:
#         model = HistGradientBoostingClassifier(
#             max_iter=150,
#             learning_rate=0.05,
#             max_depth=5,
#             class_weight="balanced",
#             random_state=42,
#         )
#         pipeline = Pipeline([("classifier", model)])

#     pipeline.fit(X_train, y_train)
#     evaluate_pipeline(pipeline, X_test, y_test)

#     return pipeline, feature_table


# # =========================================================================
# # 4. EXECUTION
# # =========================================================================

# if __name__ == "__main__":
#     # Ensure `df` is loaded:
#     # df = pd.read_csv("telecom_data.csv")
#     pipeline, feature_table = train_and_evaluate(
#         df, model_type="gradient_boosting"
#     )

















import lightgbm as lgb
import numpy as np
import pandas as pd
from sklearn.metrics import (
    average_precision_score,
    classification_report,
    precision_recall_curve,
    roc_auc_score,
)

# =========================================================================
# 1. PREPROCESSING & AGGREGATION
# =========================================================================


def aggregate_grid_hourly(df: pd.DataFrame) -> pd.DataFrame:
    """Ensures exactly one record per (grid_id, timestamp) pair."""
    df = df.copy()
    df["timestamp"] = pd.to_datetime(df["timestamp"])

    agg_dict = {
        "total_activity": "sum",
        "internet_usage": "sum",
        "total_sms": "sum",
        "total_calls": "sum",
    }
    for col in [
        "sms_in_count",
        "sms_out_count",
        "call_in_count",
        "call_out_count",
    ]:
        if col in df.columns:
            agg_dict[col] = "sum"

    df_agg = (
        df.groupby(["grid_id", "timestamp"], as_index=False)
        .agg(agg_dict)
        .sort_values(["grid_id", "timestamp"])
        .reset_index(drop=True)
    )
    return df_agg


# =========================================================================
# 2. FEATURE EXTRACTION WITH HIGH-IMPACT SIGNALS
# =========================================================================


def create_advanced_feature_table(
    df: pd.DataFrame,
    high_threshold: float = 1.5,
    recent_w: int = 6,
    prior_w: int = 24,
) -> pd.DataFrame:
    df = df.copy()
    eps = 1e-6
    grid_group = df.groupby("grid_id")

    # --- Forward Target Calculation at t+1 ---
    df["baseline_24h"] = grid_group["total_activity"].transform(
        lambda s: s.rolling(prior_w, min_periods=6).median()
    )
    df["future_activity_t1"] = grid_group["total_activity"].shift(-1)
    df["future_baseline_t1"] = grid_group["baseline_24h"].shift(-1)

    valid_target = df["future_activity_t1"].notna() & (
        df["future_baseline_t1"] > 0
    )
    df["target_high_activity"] = 0
    df.loc[
        valid_target
        & (
            df["future_activity_t1"]
            >= df["future_baseline_t1"] * high_threshold
        ),
        "target_high_activity",
    ] = 1

    # --- Cutoff Timestamp ---
    df["feature_timestamp"] = df["timestamp"]

    # 1. Base rolling signals (Trailing window <= t)
    df["avg_activity_6h"] = grid_group["total_activity"].transform(
        lambda s: s.rolling(recent_w, min_periods=1).mean()
    )
    df["prior_baseline_24h"] = grid_group["total_activity"].transform(
        lambda s: s.rolling(prior_w, min_periods=1).mean()
    )
    df["activity_growth"] = (df["avg_activity_6h"] + eps) / (
        df["prior_baseline_24h"] + eps
    )
    df["active_hours"] = grid_group["total_activity"].transform(
        lambda s: (s > 0).rolling(recent_w, min_periods=1).sum()
    )
    df["peak_activity"] = grid_group["total_activity"].transform(
        lambda s: s.rolling(recent_w, min_periods=1).max()
    )
    df["peak_ratio"] = (df["peak_activity"] + eps) / (
        df["avg_activity_6h"] + eps
    )

    roll_std = grid_group["total_activity"].transform(
        lambda s: s.rolling(recent_w, min_periods=1).std().fillna(0)
    )
    df["variability"] = roll_std / (df["avg_activity_6h"] + eps)

    # 2. Target Proxy Alignment Feature
    df["current_to_baseline_ratio"] = (df["total_activity"] + eps) / (
        df["baseline_24h"] + eps
    )

    # 3. Lags & Momentum
    df["activity_lag_1h"] = grid_group["total_activity"].shift(1)
    df["activity_lag_2h"] = grid_group["total_activity"].shift(2)
    df["activity_lag_24h"] = grid_group["total_activity"].shift(24)

    df["velocity_1h"] = df["total_activity"] - df["activity_lag_1h"]
    df["acceleration_1h"] = (
        df["total_activity"]
        - 2 * df["activity_lag_1h"]
        + df["activity_lag_2h"]
    )
    df["activity_vs_same_hour_yesterday"] = (df["total_activity"] + eps) / (
        df["activity_lag_24h"] + eps
    )

    # 4. Traffic Composition
    roll_internet = grid_group["internet_usage"].transform(
        lambda s: s.rolling(recent_w, min_periods=1).sum()
    )
    roll_total = grid_group["total_activity"].transform(
        lambda s: s.rolling(recent_w, min_periods=1).sum()
    )
    df["internet_share"] = (roll_internet + eps) / (roll_total + eps)
    df["sms_to_call_ratio"] = (df["total_sms"] + eps) / (
        df["total_calls"] + eps
    )

    # 5. Temporal Features
    hour = df["feature_timestamp"].dt.hour
    dow = df["feature_timestamp"].dt.dayofweek
    df["hour"] = hour
    df["day_of_week"] = dow
    df["is_weekend"] = dow.isin([5, 6]).astype(int)
    df["hour_sin"] = np.sin(2 * np.pi * hour / 24.0)
    df["hour_cos"] = np.cos(2 * np.pi * hour / 24.0)
    df["dow_sin"] = np.sin(2 * np.pi * dow / 7.0)
    df["dow_cos"] = np.cos(2 * np.pi * dow / 7.0)

    # Convert grid_id to category for native categorical handling in LightGBM
    df["grid_id"] = df["grid_id"].astype("category")

    return df.dropna().reset_index(drop=True)


# =========================================================================
# 3. LIGHTGBM TRAINING & EVALUATION
# =========================================================================


def train_lightgbm(feature_table: pd.DataFrame, train_ratio: float = 0.8):
    feature_table = feature_table.sort_values("feature_timestamp").reset_index(
        drop=True
    )

    train_cutoff = pd.Timestamp("2013-11-05 23:00:00")  # Nov 1-5 (Training)
    test_start   = pd.Timestamp("2013-11-06 01:00:00")  # 1-hour buffer (Nov 6-7 Test)

    train_df = df[df["timestamp"] <= train_cutoff]
    test_df  = df[df["timestamp"] >= test_start]

    print("=" * 65)
    print("DATA SPLIT SUMMARY")
    print("=" * 65)
    print(
        f"Train: {train_df['feature_timestamp'].min()} -> {train_df['feature_timestamp'].max()} (N={len(train_df):,})"
    )
    print(
        f"Test : {test_df['feature_timestamp'].min()} -> {test_df['feature_timestamp'].max()} (N={len(test_df):,})"
    )
    print(
        f"Train Base Rate (Positives): {train_df['target_high_activity'].mean():.2%}"
    )
    print(
        f"Test Base Rate  (Positives): {test_df['target_high_activity'].mean():.2%}"
    )
    print("=" * 65)

    features = [
        "grid_id",
        "activity_growth",
        "variability",
        "peak_ratio",
        "internet_share",
        "avg_activity_6h",
        "active_hours",
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

    X_train, y_train = train_df[features], train_df["target_high_activity"]
    X_test, y_test = test_df[features], test_df["target_high_activity"]

    pos_weight = (y_train == 0).sum() / max(1, (y_train == 1).sum())

    # model = lgb.LGBMClassifier(
    #     n_estimators=500,
    #     learning_rate=0.03,
    #     num_leaves=63,
    #     max_depth=7,
    #     scale_pos_weight=pos_weight,
    #     subsample=0.8,
    #     colsample_bytree=0.8,
    #     random_state=42,
    #     n_jobs=-1,
    # )
    model = lgb.LGBMClassifier(
        n_estimators=1000,
        learning_rate=0.015,  # Lower learning rate + more trees yields better generalization
        num_leaves=127,  # Allows deeper feature interactions
        max_depth=9,
        min_child_samples=50,  # Prevents overfitting on rare grid IDs
        subsample=0.7,  # Row bagging
        subsample_freq=1,
        colsample_bytree=0.7,  # Feature bagging
        scale_pos_weight=pos_weight
        * 0.7,  # Slightly downscale weight to boost precision
        force_col_wise=True,
        random_state=42,
        n_jobs=-1,
    )
    print("Training LightGBM model...")
    model.fit(
        X_train,
        y_train,
        eval_set=[(X_test, y_test)],
        callbacks=[lgb.early_stopping(stopping_rounds=30, verbose=False)],
    )

    y_proba = model.predict_proba(X_test)[:, 1]

    # Metrics
    roc_auc = roc_auc_score(y_test, y_proba)
    pr_auc = average_precision_score(y_test, y_proba)

    precisions, recalls, thresholds = precision_recall_curve(y_test, y_proba)
    f1_scores = (
        2
        * (precisions * recalls)
        / np.clip(precisions + recalls, 1e-6, None)
    )
    best_idx = np.argmax(f1_scores[:-1])
    optimal_threshold = thresholds[best_idx]

    print("\n" + "=" * 65)
    print("GLOBAL PERFORMANCE METRICS")
    print("=" * 65)
    print(f"ROC-AUC: {roc_auc:.4f} | PR-AUC: {pr_auc:.4f}")
    print(f"Optimal F1 Threshold: {optimal_threshold:.4f}")
    print("=" * 65)

    print("\nDefault Threshold (0.50) Report:")
    print(
        classification_report(
            y_test, (y_proba >= 0.50).astype(int), digits=4, zero_division=0
        )
    )

    print(f"\nOptimal F1 Threshold ({optimal_threshold:.4f}) Report:")
    print(
        classification_report(
            y_test,
            (y_proba >= optimal_threshold).astype(int),
            digits=4,
            zero_division=0,
        )
    )

    # Feature Importance
    print("=" * 65)
    print("TOP 10 FEATURE IMPORTANCES")
    print("=" * 65)
    2

    return model, feature_table


# =========================================================================
# 4. FULL RUNNER FUNCTION
# =========================================================================


def run_pipeline(raw_df: pd.DataFrame):
    print("[1/3] Aggregating raw telemetry...")
    agg_df = aggregate_grid_hourly(raw_df)

    print("[2/3] Extracting features & constructing forward target...")
    feature_table = create_advanced_feature_table(agg_df)

    print("[3/3] Training and evaluating LightGBM...")
    model, processed_table = train_lightgbm(feature_table)

    return model, processed_table


# =========================================================================
# 5. EXECUTION ENTRY POINT
# =========================================================================

if __name__ == "__main__":
    # Ensure your raw dataframe `df` is loaded:
    # df = pd.read_csv("your_data.csv")

    model, processed_feature_table = run_pipeline(df)