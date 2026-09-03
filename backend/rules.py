import logging
import numpy as np
import pandas as pd
import math

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class AlertAnalyzer:
    """Encapsulates the vectorized pandas/numpy alert logic provided."""
    
    HIGH_THRESHOLD = 1.5
    DROP_THRESHOLD = 0.5
    SPIKE_THRESHOLD = 2.0
    FLOOR_PERCENTILE = 0.10

    def __init__(self, analytics_df: pd.DataFrame):
        self.analytics_df = analytics_df
        self.logger = logging.getLogger(self.__class__.__name__)

    def _leave_one_out_median(self, values: np.ndarray) -> np.ndarray:
        """Vectorized 'leave-one-out' median logic provided by user."""
        n = values.shape[0]
        result = np.full(n, np.nan)
        if n < 2: return result

        order = np.argsort(values, kind="mergesort")
        sorted_vals = values[order]
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
        if self.analytics_df is None or self.analytics_df.empty:
            return pd.DataFrame()

        try:
            df = self.analytics_df.copy()
            # Expecting 'hour_timestamp' to be datetime
            df["date"] = df["hour_timestamp"].dt.date
            df = df.sort_values(["grid_id", "hour_timestamp"]).reset_index(drop=True)

            df["previous_activity"] = df.groupby("grid_id")["total_activity"].shift(1)
            df["daily_total"] = df.groupby(["grid_id", "date"])["total_activity"].transform("sum")
            
            activity_floor = df["daily_total"].quantile(self.FLOOR_PERCENTILE)
            if pd.isna(activity_floor):
                activity_floor = 0.0

            df["baseline_activity"] = (
                df.groupby(["grid_id", "date"])["total_activity"]
                .transform(lambda s: self._leave_one_out_median(s.to_numpy(dtype=float)))
            )

            # Apply floor filter
            df = df[df["daily_total"] >= activity_floor].copy()
            if df.empty:
                return pd.DataFrame()

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
                    valid & ~np.isnan(previous) & (previous > 0)
                    & (current >= previous * self.SPIKE_THRESHOLD)
                )

            def _build(mask, alert_type, reason_of):
                idx = np.flatnonzero(mask)
                return [{
                    "grid_id": grid_id[i], "timestamp": timestamp[i],
                    "alert_type": alert_type, "current_activity": current[i],
                    "baseline_activity": baseline[i], "reason": reason_of(i)
                } for i in idx]

            alerts = []
            alerts += _build(high_mask, "HIGH_ACTIVITY", lambda i: (
                f"Current activity ({current[i]:.2f}) is {ratio_to_baseline[i]:.2f}x "
                f"the within-day baseline ({baseline[i]:.2f})."
            ))
            alerts += _build(spike_mask, "ACTIVITY_SPIKE", lambda i: (
                f"Activity increased sharply from {previous[i]:.2f} to {current[i]:.2f}."
            ))
            alerts += _build(drop_mask, "ACTIVITY_DROP", lambda i: (
                f"Current activity ({current[i]:.2f}) is {ratio_to_baseline[i]:.2f}x "
                f"the within-day baseline ({baseline[i]:.2f})."
            ))

            alert_df = pd.DataFrame(alerts, columns=[
                "grid_id", "timestamp", "alert_type", 
                "current_activity", "baseline_activity", "reason"
            ])

            if not alert_df.empty:
                alert_df = alert_df.sort_values(["timestamp", "grid_id"]).reset_index(drop=True)
            return alert_df

        except Exception as exc:
            self.logger.exception("Failed to generate activity alerts.")
            raise RuntimeError(f"Failed to generate activity alerts: {exc}") from exc

