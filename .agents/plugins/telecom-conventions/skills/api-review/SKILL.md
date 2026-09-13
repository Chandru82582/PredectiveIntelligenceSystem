---
name: api-review
description: >-
  Execute and evaluate the backend REST API test suite, validating endpoints, response latencies, and schema contracts.
  Use this skill whenever someone asks to run API tests, check API health, review test failures, or runs /test-api.
---

# API Review Skill

## 1. Activation Triggers
Activate this skill whenever the user or operator:
- Runs or requests the backend API test suite (e.g., "/test-api", "run the API test suite").
- Asks whether specific REST API endpoints are functional, returning errors, or experiencing latency spikes.
- Diagnoses failures in FastAPI routes, query parameter handling (such as `as_of` or `model_name`), or response schema mismatches.

---

## 2. Required Evidence Checklist
Before reporting on API status, the agent **MUST** verify:
1. **Suite Execution Summary**: Total tests executed, Passed count, Failed count, Error count, Total duration in seconds.
2. **Endpoint Latency Breakdown**: Latency in milliseconds for each endpoint in the test catalog.
3. **HTTP Status Codes**: Verified status code for each test (e.g. `200 OK`, `404`, `422`).
4. **Failure Error Traces**: Specific HTTP error response body or Python assertion exception for any failing test.
5. **Contract Conformance**: Compliance of JSON output with Pydantic response models in `backend/schemas.py`.

---

## 3. Standard Response Format

### Section 1: TEST SUITE VERDICT
- **Overall Verdict**: `ALL PASSED` (100% pass rate) or `FAILURES DETECTED`.
- **KPI Summary**: Total tests, passed, failed, errors, total runtime in seconds.

### Section 2: ENDPOINT EXECUTION TABLE
| Test Name | Endpoint | Status | Latency |
|---|---|---|---|
| Health / Network Summary | `GET /network/summary` | PASS | 12.9 ms |
| Pipeline Status Telemetry | `GET /pipeline/status` | PASS | 4.4 ms |
| Network Grain Health Check | `GET /pipeline/network-health` | PASS | 2.6 ms |
| Available ML Models Catalog | `GET /predict/models` | PASS | 8.3 ms |
| LightGBM High-Activity Prediction | `GET /predict/grid/4365` | PASS | 1.6 ms |
| Anomaly Review | `GET /network/grid/4365/review-anomaly` | PASS | 105.8 ms |

### Section 3: FAILURE INVESTIGATION (IF ANY)
- For each failing endpoint:
  - Exact request parameters or payload used.
  - Received HTTP status code and response payload.
  - Root cause analysis (e.g., missing database table, invalid Pydantic model field, unhandled `None` query parameter).

### Section 4: REMEDIATION & NEXT CHECKS
- Immediate code/configuration fixes needed in `backend/routes.py` or database migrations.
- Follow-up command to verify the fix: `python test_api.py`.
