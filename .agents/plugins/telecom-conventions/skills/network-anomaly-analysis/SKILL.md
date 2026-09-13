---
name: network-anomaly-analysis
description: >-
  Analyze network activity anomalies and predictive risk scores for telecom grid cells.
  Use this skill whenever someone asks why a grid is flagged, what an anomaly score means,
  whether an activity pattern is unusual, or asks to diagnose cell performance (e.g. /explain-grid, /review-anomaly).
---

# Network Anomaly Analysis Skill

## 1. Activation Triggers
Activate this skill whenever the user or operator:
- Asks why a specific grid or cell is flagged (e.g., "Why is Grid 4365 flagged?").
- Inquires about the meaning, threshold, or severity of an anomaly score or prediction probability (e.g., "What does an anomaly score of 0.82 mean for cell 100?").
- Asks whether a cell's current, historical, or projected activity pattern is unusual or divergent.
- Requests a triage, anomaly review, or explanation of an alert (including slash commands `/explain-grid` and `/review-anomaly`).

---

## 2. Required Evidence Checklist
Before formulating an analysis, the agent **MUST** gather or verify the following 5 pieces of evidence. If any piece is absent, the agent must explicitly state its insufficiency rather than guessing:

1. **Current Activity**: Recent aggregated activity value for the grid cell.
2. **Baseline Activity**: 24-hour rolling median / within-day diurnal baseline for that cell.
3. **ML Anomaly Score & Direction**: Model output probability ($0.0 - 1.0$) and classification label (`HIGH_ACTIVITY_RISK` vs `NORMAL`) relative to the decision threshold.
4. **Rule Alerts**: Active threshold alerts (`HIGH_ACTIVITY`, `ACTIVITY_SPIKE`, `ACTIVITY_DROP`, or `None`).
5. **Pipeline Status**: Data freshness and trust state (`HEALTHY`, `DEGRADED`, `STALE`, last ingestion timestamp).

> [!IMPORTANT]
> **Data Insufficiency Mandate**: If any required metric cannot be resolved (e.g., baseline cannot be computed due to $<24$h of trailing history, or pipeline status is unavailable), state:  
> `[INSUFFICIENT EVIDENCE: <Metric Name> is not available in the current context]`  
> **NEVER hallucinate, approximate, or fill in missing numbers.**

---

## 3. Strict Domain Invariants & Terminology Rules

1. **Dimensionless Activity Measures, NOT Counts or MB**:
   - Activity values (`total_activity`, `internet_usage`, `sms`, `calls`) are **proportional, dimensionless activity measures** normalized by Telecom Italia.
   - **NEVER** refer to these values as counts (e.g., "number of calls", "SMS count") or data volume (e.g., "megabytes", "MB", "gigabytes", "GB").
2. **NEVER Claim Network Congestion**:
   - Physical link utilization, radio bearer allocations (PRBs), and backhaul capacities are **unknown**.
   - High activity values **MUST NEVER be described as confirmed congestion**.
   - Permitted terminology: *"high activity"*, *"activity surge"*, *"volume spike"*, *"elevated demand"*, or *"activity risk"*.
3. **Grid is a Geographic Cell, NOT a Tower**:
   - A grid cell is a $200\text{m} \times 200\text{m}$ spatial area in the $100 \times 100$ Milan lattice (`Square_id` 1–10,000).
   - **NEVER** refer to a grid as a "cell tower", "base station", "eNodeB", or "antenna".
4. **`AS_OF` Temporal Anchor**:
   - The data is historical (Nov 1–7, 2013). "Now" is defined by the latest ingested timestamp or explicit `as_of` parameter, never `datetime.now()`.

---

## 4. Required Four-Section Response Format

Every anomaly analysis **MUST** strictly follow this 4-section structure:

### Section 1: SEVERITY
- **Severity Badge**:
  - `CRITICAL`: Activity ratio $\ge 2.5\times$ baseline AND ML anomaly probability $\ge 0.85$.
  - `HIGH`: Activity ratio $\ge 2.0\times$ baseline OR ML anomaly probability $\ge 0.75$ (provided pipeline is verified fresh $\le 2\text{h}$).
  - `ATTENTION`: Activity ratio between $1.5\times$ and $2.0\times$ baseline, OR disagreement between Rule alert and ML classifier.
  - `ATTENTION (UNVERIFIED_STALE)`: Pipeline staleness exceeds 4 hours. High-severity escalation is gated/suppressed until data freshness is confirmed.
  - `NORMAL`: Nominal traffic below $1.5\times$ baseline with nominal ML score.
- **Target Coordinates**: Grid ID, centroid coordinates (lat/lon), and sector label (e.g. `Sector B2`).
- **Pipeline Trust Badge**: `TRUSTED (FRESH)` or `UNVERIFIED / STALE`.

### Section 2: EVIDENCE
Present a structured markdown or HTML evidence breakdown with exact verified metrics:
- **Current Activity**: Measured value.
- **Baseline Activity**: Trailing 24h baseline.
- **Ratio to Baseline**: $Current / Baseline$ multiplier.
- **ML Anomaly Probability**: Exact probability (e.g., $78.4\%$) and decision threshold ($50.0\%$).
- **Rule Alerts**: Any rule-engine triggers (e.g., `HIGH_ACTIVITY` if $>1.5\times$ baseline).
- **Consensus**: `AGREEMENT` (both rule & ML trigger), `DISAGREEMENT_RULE_ONLY`, `DISAGREEMENT_ML_ONLY`, or `NOMINAL`.
- *(Include explicit insufficiency warning for any unverified metric).*

### Section 3: INTERPRETATION
- Analyze sensor agreement/disagreement:
  - If **Rule triggers but ML is Normal**: Explain that the rule triggered on an instantaneous spike, whereas the LightGBM classifier evaluated rolling variance, velocity, and diurnal lag and suppressed the alert.
  - If **ML triggers but Rule is Normal**: Explain that multi-hour growth velocity indicates impending surge before instantaneous threshold breach.
  - If **Both Trigger**: Correlate modality breakdown (e.g., high internet traffic share vs voice/SMS).
- Explicitly respect terminology: describe as elevated demand or activity surge, never congestion.

### Section 4: NEXT CHECKS
Provide concrete, actionable NOC operational recommendations:
1. **Adjacent Cell Correlation**: Inspect neighboring lattice cells in the sector to determine if demand is localized or geographic cluster.
2. **Modality Drift**: Check whether the surge is internet data share driven or voice/telephony burst.
3. **Pipeline Freshness Audit**: Verify ingestion logs (`flow/logs/audit_log.json`) if data staleness is suspected.
4. **Historical Recurrence**: Compare with same-hour activity from yesterday (`activity_vs_same_hour_yesterday`).

---

## 5. Execution Workflow & Tool Guidance
1. If `grid_id` is provided, call:
   - `get_grid_features(grid_id)`
   - `get_grid_prediction(grid_id, as_of, model_name)`
   - `review_grid_anomaly(grid_id)`
   - `get_grid_geography(grid_id)`
2. Check pipeline state via `get_pipeline_status()`.
3. Validate evidence completeness against Section 2 checklist.
4. Synthesize findings strictly through the 4-section format.
