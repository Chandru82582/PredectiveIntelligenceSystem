---
description: Compare the rule alert, classifier output and anomaly score for a grid and explain any disagreement
---

# /review-anomaly [grid_id]

Given a `grid_id` (defaults to active cell or 4365):
1. Runs rule-based threshold evaluation using `AlertAnalyzer` on recent hourly activity for the grid.
2. Retrieves LightGBM classifier prediction, probability score, and decision threshold.
3. Compares findings in a side-by-side consensus matrix:
   - Rule Alert (`HIGH_ACTIVITY`, `ACTIVITY_SPIKE`, `ACTIVITY_DROP`, or `None`)
   - Classifier Output (`HIGH_ACTIVITY_RISK` or `NORMAL`)
   - Anomaly Probability (%)
4. Explains agreement or disagreement:
   - Evaluates whether rolling multi-hour lags and diurnal baselines suppressed an instantaneous spike or detected early velocity before a static threshold breached.
