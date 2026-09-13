---
description: Run the API test suite and summarize failures
---

# /test-api

Executes the backend FastAPI test suite:
1. Runs `run_api_test_suite()` in `backend/test_api.py` covering health, pipeline status, grain health, cell timeseries, engineered features, classifier prediction, alerts, hotspots, and chat endpoints.
2. Summarizes total tests, passed, failed, errors, and execution latency.
3. If failures occur, reports the failing endpoint, HTTP status code, and assertion error details.
