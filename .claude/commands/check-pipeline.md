---
description: Call GET /pipeline/status and summarize health, naming any rejected rows or staleness
---

# /check-pipeline

Calls `GET /pipeline/status` and summarizes pipeline health:
1. Queries the pipeline status endpoint or database + `flow/logs/audit_log.json`.
2. Reports overall status: `HEALTHY`, `DEGRADED`, or `STALE`.
3. Names any rejected ingestion rows with filename, timestamp, and failure reason.
4. Notes ingestion staleness against current operational clock.
