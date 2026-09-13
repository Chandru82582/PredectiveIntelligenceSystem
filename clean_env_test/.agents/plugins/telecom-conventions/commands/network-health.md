---
description: Run the grain duplicate check on hourly_grid_summary and report pass or fail
---

# /network-health

Audits the core analytics grain invariant on `hourly_grid_summary`:
1. Executes duplicate grain detection on `(date, hour, grid_id)`.
2. Verifies that exactly one record exists per cell per 1-hour timestamp after country-code aggregation.
3. Reports `PASS` (grain intact) or `FAIL` (grain duplicates detected).
4. Outputs inspected record count, duplicate grain count, sample duplicates table, and root-cause remediation guidance.
