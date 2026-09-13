---
name: pipeline-troubleshooting
description: >-
  Troubleshoot data ingestion health, ETL pipeline staleness, rejected batches, and audit log failures.
  Use this skill whenever someone asks about pipeline health, data freshness, missing ingestion dates,
  rejected batches in audit_log.json, or runs /check-pipeline.
---

# Pipeline Troubleshooting Skill

## 1. Activation Triggers
Activate this skill whenever the user or operator:
- Asks whether the ingestion pipeline or data sync is healthy, delayed, or stale (e.g., "Is the pipeline running?", "/check-pipeline").
- Inquires why data is missing for recent hours or dates.
- Reports rejected CSV batches, schema validation failures, or parse errors in `flow/logs/audit_log.json`.
- Needs to diagnose PySpark batch failures or Airflow DAG execution issues (`ingestion_dag.py`).

---

## 2. Required Evidence Checklist
Before reporting pipeline status, the agent **MUST** gather or verify:
1. **Latest Ingestion Timestamp**: Most recent `loaded_at` or `(date, hour)` in `hourly_grid_summary`.
2. **Staleness Duration**: Time delta between operational `AS_OF` and last successful batch load.
3. **Audit Log Summary**: Total processed batches, count of `ACCEPTED` vs `REJECTED` runs from `flow/logs/audit_log.json`.
4. **Rejected Batches List**: File names, timestamps, and explicit failure reasons for any rejected runs.
5. **Database Storage Status**: Active row count and grain continuity across dates Nov 1–7, 2013.

> [!IMPORTANT]
> **Data Insufficiency Rule**: If `flow/logs/audit_log.json` cannot be read or database connection is unreachable, state:  
> `[INSUFFICIENT EVIDENCE: Pipeline audit logs unreachable; reporting database telemetry only]`  
> Do not assume or invent ingestion outcomes.

---

## 3. Standard Response Format

Troubleshooting reports must follow this 4-section layout:

### Section 1: STATUS & STALENESS
- **Health Badge**: `HEALTHY` (recent ingestion, zero rejections), `DEGRADED` (audit rejections detected or staleness $>6$h), or `STALE / OFFLINE` ($>24$h without ingest).
- **Ingestion Head**: Date & hour of latest processed batch.
- **Staleness**: Elapsed hours since last ingest.

### Section 2: INGESTION AUDIT TRAIL
Present a structured audit summary:
- **Total Ingestion Runs**: Number of batch attempts.
- **Accepted Files**: Count and total rows ingested.
- **Rejected Files**: Count of files rejected by schema/validation guards.
- **Recent Rejection Details**: Table with `Filename`, `Rejection Reason`, and `Processed At`.

### Section 3: ROOT CAUSE DIAGNOSIS
- Categorize the failure mode:
  - **Schema Violation**: Malformed column headers, unexpected delimiter, missing required fields (`Square_id`, `Country_code`).
  - **Data Corruption**: Corrupt epoch timestamps, negative activity values, or truncated lines.
  - **Resource / Lock Exhaustion**: Spark executor OOM, database connection timeout, or deadlocks.

### Section 4: RECOVERY RUNBOOK
Actionable technical steps for the data engineer:
1. **Quarantine Inspection**: Check bad records in the raw landing directory `data/`.
2. **Backfill Execution**: Re-trigger PySpark ETL for the failed date partition:
   `python flow/spark/telecom_pipeline.py --date YYYY-MM-DD`
3. **Airflow DAG Resume**: Unpause or trigger the corresponding task in `ingestion_dag`.
4. **Deduplication Audit**: Run `/network-health` after recovery to ensure no grain duplicates were created during backfill.
