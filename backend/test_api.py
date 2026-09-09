import time
import sys
from typing import Dict, Any, List
from fastapi.testclient import TestClient
from main import app

client = TestClient(app)

DEFAULT_HEADERS = {"X-API-Key": "test-key"}


def run_api_test_suite() -> Dict[str, Any]:
    """
    Executes an in-process REST API test suite using FastAPI's TestClient.
    Returns detailed pass/fail statistics, latency, and failure traces.
    """
    test_cases = [
        {
            "name": "Health / Network Summary",
            "method": "GET",
            "endpoint": "/network/summary",
            "check": lambda res: res.status_code == 200 and "total_activity" in res.json()
        },
        {
            "name": "Pipeline Status Telemetry",
            "method": "GET",
            "endpoint": "/pipeline/status",
            "check": lambda res: res.status_code == 200 and "status" in res.json() and "last_ingestion" in res.json()
        },
        {
            "name": "Network Grain Health Check",
            "method": "GET",
            "endpoint": "/pipeline/network-health",
            "check": lambda res: res.status_code == 200 and res.json().get("status") in ("PASS", "FAIL")
        },
        {
            "name": "Grid Timeseries Activity (Cell 4365)",
            "method": "GET",
            "endpoint": "/network/grid/4365",
            "check": lambda res: res.status_code == 200 and isinstance(res.json().get("timeseries"), list)
        },

        {
            "name": "Grid Engineered Features (Cell 4365)",
            "method": "GET",
            "endpoint": "/network/grid/4365/features",
            "check": lambda res: res.status_code == 200 and "avg_activity" in res.json() and "peak_ratio" in res.json()
        },
        {
            "name": "Available ML Models Catalog",
            "method": "GET",
            "endpoint": "/predict/models",
            "check": lambda res: res.status_code == 200 and isinstance(res.json().get("models"), list) and len(res.json().get("models")) > 0
        },
        {
            "name": "LightGBM High-Activity Prediction (Cell 4365)",
            "method": "GET",
            "endpoint": "/predict/grid/4365",
            "check": lambda res: res.status_code == 200 and "probability" in res.json() and "risk_label" in res.json()
        },

        {
            "name": "Anomaly Review (Cell 4365)",
            "method": "GET",
            "endpoint": "/network/grid/4365/review-anomaly",
            "check": lambda res: res.status_code == 200 and "consensus" in res.json()
        },
        {
            "name": "Alert Engine Feed",
            "method": "GET",
            "endpoint": "/network/alerts?limit=5",
            "check": lambda res: res.status_code == 200 and "alerts" in res.json()
        },
        {
            "name": "Hotspots Leaderboard",
            "method": "GET",
            "endpoint": "/network/hotspots?limit=5",
            "check": lambda res: res.status_code == 200 and "hotspots" in res.json()
        },
        {
            "name": "Ingestion Audit Log",
            "method": "GET",
            "endpoint": "/data/audit-log?page=1&page_size=5",
            "check": lambda res: res.status_code == 200 and "records" in res.json()
        },
        {
            "name": "NOC Copilot Slash Command Execution (/check-pipeline)",
            "method": "POST",
            "endpoint": "/chat",
            "payload": {"message": "/check-pipeline", "grid_id": 4365},
            "check": lambda res: res.status_code == 200 and "noc-report" in res.json().get("reply", "")
        }
    ]

    total = len(test_cases)
    passed = 0
    failed = 0
    errors = 0
    results: List[Dict[str, Any]] = []

    suite_start = time.time()

    for tc in test_cases:
        name = tc["name"]
        method = tc["method"]
        endpoint = tc["endpoint"]
        check_fn = tc["check"]
        payload = tc.get("payload")

        t0 = time.time()
        try:
            if method == "GET":
                response = client.get(endpoint, headers=DEFAULT_HEADERS)
            elif method == "POST":
                response = client.post(endpoint, json=payload, headers=DEFAULT_HEADERS)
            else:
                raise ValueError(f"Unsupported method: {method}")

            duration_ms = (time.time() - t0) * 1000.0

            if check_fn(response):
                passed += 1
                results.append({
                    "name": name,
                    "endpoint": endpoint,
                    "status": "PASS",
                    "status_code": response.status_code,
                    "duration_ms": round(duration_ms, 2),
                    "error": None
                })
            else:
                failed += 1
                results.append({
                    "name": name,
                    "endpoint": endpoint,
                    "status": "FAIL",
                    "status_code": response.status_code,
                    "duration_ms": round(duration_ms, 2),
                    "error": f"Assertion failed. HTTP {response.status_code}: {response.text[:200]}"
                })
        except Exception as exc:
            errors += 1
            duration_ms = (time.time() - t0) * 1000.0
            results.append({
                "name": name,
                "endpoint": endpoint,
                "status": "ERROR",
                "status_code": 500,
                "duration_ms": round(duration_ms, 2),
                "error": str(exc)
            })

    total_duration_s = time.time() - suite_start

    return {
        "total": total,
        "passed": passed,
        "failed": failed,
        "errors": errors,
        "duration_seconds": round(total_duration_s, 3),
        "tests": results
    }


if __name__ == "__main__":
    report = run_api_test_suite()
    print("=" * 60)
    print("API TEST SUITE EXECUTION REPORT")
    print("=" * 60)
    print(f"Total: {report['total']} | Passed: {report['passed']} | Failed: {report['failed']} | Errors: {report['errors']}")
    print(f"Duration: {report['duration_seconds']}s\n")
    for t in report["tests"]:
        status_sym = "PASS" if t["status"] == "PASS" else "FAIL"
        print(f"[{status_sym:<4}] {t['name']:<45} {t['endpoint']:<30} ({t['duration_ms']}ms)")
        if t["error"]:
            print(f"       Error: {t['error']}")
    print("=" * 60)
    sys.exit(0 if (report["failed"] == 0 and report["errors"] == 0) else 1)

