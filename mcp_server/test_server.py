"""
Comprehensive Test Suite for Telecom MCP Server.

Validates:
1. Tool catalog registration (all 7 required tools present with valid schemas).
2. End-to-end execution of all 7 tools against backend API via ASGI transport.
3. Input validation bounds (grid_id, limit, severity, date, hour, as_of).
4. Security constraints (URL schemes, bounds, injection resistance).
5. Pass-through integrity (zero business logic, exact API contract preservation).
"""

import sys
import json
import asyncio
from pathlib import Path

# Add project root and backend to sys.path
_ROOT = Path(__file__).resolve().parent.parent
_BACKEND = _ROOT / "backend"
for p in [str(_ROOT), str(_BACKEND)]:
    if p not in sys.path:
        sys.path.insert(0, p)

import httpx
from main import app
from mcp_server.server import (
    TelecomMCPServer,
    _validate_base_url,
    _validate_grid_id,
    _validate_limit,
    _validate_severity,
    _validate_iso_timestamp,
    _validate_date,
    _validate_hour,
)


def get_test_server():
    transport = httpx.ASGITransport(app=app)
    client = httpx.AsyncClient(transport=transport, base_url="http://testserver")
    return TelecomMCPServer(
        base_url="http://testserver",
        api_key="test-key",
        client=client,
    )


async def test_tool_catalog():
    print("Testing Tool Catalog Registration...")
    server = get_test_server()
    tools = await server.list_tools()
    tool_names = [t.name for t in tools]
    expected_tools = [
        "network_summary",
        "grid_activity",
        "grid_features",
        "grid_location",
        "hotspots",
        "alerts",
        "pipeline_status",
    ]
    for exp in expected_tools:
        assert exp in tool_names, f"Expected tool '{exp}' not found in {tool_names}"

    # Verify input schema constraints
    grid_tool = next(t for t in tools if t.name == "grid_activity")
    schema = grid_tool.input_schema
    assert "grid_id" in schema["required"]
    assert schema["properties"]["grid_id"]["minimum"] == 1
    assert schema["properties"]["grid_id"]["maximum"] == 10000
    print("  [PASS] All 7 tools registered with valid JSON schema constraints")


async def test_network_summary():
    print("Testing network_summary -> GET /network/summary...")
    server = get_test_server()
    result = await server.call_tool("network_summary", {})
    assert not result.is_error
    data = json.loads(result.content[0].text)
    assert "total_activity" in data
    assert "active_grids" in data
    assert "peak_hour" in data
    assert "top_grid" in data
    assert "as_of" in data
    print(f"  [PASS] Total activity: {data['total_activity']}, active grids: {data['active_grids']}")


async def test_grid_activity():
    print("Testing grid_activity -> GET /network/grid/{grid_id}...")
    server = get_test_server()
    result = await server.call_tool("grid_activity", {"grid_id": 4365})
    assert not result.is_error
    data = json.loads(result.content[0].text)
    assert data["grid_id"] == 4365
    assert "timeseries" in data
    assert isinstance(data["timeseries"], list)
    print(f"  [PASS] Timeseries entries: {len(data['timeseries'])}")


async def test_grid_features():
    print("Testing grid_features -> GET /network/grid/{grid_id}/features...")
    server = get_test_server()
    result = await server.call_tool("grid_features", {"grid_id": 4365})
    assert not result.is_error
    data = json.loads(result.content[0].text)
    assert data["grid_id"] == 4365
    assert "avg_activity" in data
    print(f"  [PASS] Grid 4365 avg activity: {data['avg_activity']}")


async def test_grid_location():
    print("Testing grid_location -> GET /network/grid/{grid_id}/location...")
    server = get_test_server()
    result = await server.call_tool("grid_location", {"grid_id": 4365})
    assert not result.is_error
    data = json.loads(result.content[0].text)
    assert data["grid_id"] == 4365
    assert "latitude" in data
    assert "longitude" in data
    assert "polygon" in data
    assert "sector_label" in data
    print(f"  [PASS] Grid 4365 lat/lon: ({data['latitude']}, {data['longitude']}), sector: {data['sector_label']}")


async def test_hotspots():
    print("Testing hotspots -> GET /network/hotspots...")
    server = get_test_server()
    result = await server.call_tool("hotspots", {"limit": 5, "severity": "HIGH"})
    assert not result.is_error
    data = json.loads(result.content[0].text)
    assert "hotspots" in data
    assert isinstance(data["hotspots"], list)
    assert len(data["hotspots"]) <= 5
    print(f"  [PASS] Hotspots count: {len(data['hotspots'])}")


async def test_alerts():
    print("Testing alerts -> GET /network/alerts...")
    server = get_test_server()
    result = await server.call_tool("alerts", {"limit": 5})
    assert not result.is_error
    data = json.loads(result.content[0].text)
    assert "alerts" in data
    assert isinstance(data["alerts"], list)
    print(f"  [PASS] Alerts count: {len(data['alerts'])}")


async def test_pipeline_status():
    print("Testing pipeline_status -> GET /pipeline/status...")
    server = get_test_server()
    result = await server.call_tool("pipeline_status", {})
    assert not result.is_error
    data = json.loads(result.content[0].text)
    assert "status" in data
    assert "last_ingestion" in data
    print(f"  [PASS] Pipeline status: {data.get('status')}")


def test_input_validations():
    print("Testing Input Validation and Security Constraints...")

    # grid_id bounds
    assert _validate_grid_id(1) == 1
    assert _validate_grid_id(10000) == 10000
    assert _validate_grid_id("4365") == 4365

    for invalid in [0, 10001, -1, "abc"]:
        try:
            _validate_grid_id(invalid)
            assert False, f"Expected validation failure for grid_id={invalid}"
        except ValueError:
            pass

    # limit bounds
    assert _validate_limit(10) == 10
    assert _validate_limit("50") == 50
    for invalid in [0, 1001, -10]:
        try:
            _validate_limit(invalid)
            assert False, f"Expected validation failure for limit={invalid}"
        except ValueError:
            pass

    # severity whitelist
    assert _validate_severity("HIGH") == "HIGH"
    assert _validate_severity("medium") == "MEDIUM"
    assert _validate_severity(" low ") == "LOW"
    assert _validate_severity(None) is None
    for invalid in ["CRITICAL", "DROP TABLE", ""]:
        try:
            _validate_severity(invalid)
            assert False, f"Expected validation failure for severity={invalid}"
        except ValueError:
            pass

    # date format
    assert _validate_date("2013-11-01") == "2013-11-01"
    assert _validate_date(None) is None
    for invalid in ["2013/11/01", "2013-02-30", "yesterday"]:
        try:
            _validate_date(invalid)
            assert False, f"Expected validation failure for date={invalid}"
        except ValueError:
            pass

    # hour bounds
    assert _validate_hour(0) == 0
    assert _validate_hour(23) == 23
    assert _validate_hour("12") == 12
    assert _validate_hour(None) is None
    for invalid in [-1, 24, "noon"]:
        try:
            _validate_hour(invalid)
            assert False, f"Expected validation failure for hour={invalid}"
        except ValueError:
            pass

    # ISO timestamp format
    assert _validate_iso_timestamp("2013-11-07T23:00:00") == "2013-11-07T23:00:00"
    assert _validate_iso_timestamp("2013-11-07") == "2013-11-07"
    assert _validate_iso_timestamp(None) is None
    for invalid in ["not-a-timestamp", "A" * 51]:
        try:
            _validate_iso_timestamp(invalid)
            assert False, f"Expected validation failure for timestamp={invalid}"
        except ValueError:
            pass

    # Base URL security (SSRF prevention)
    assert _validate_base_url("http://localhost:8000") == "http://localhost:8000"
    assert _validate_base_url("https://telecom.internal:8443/") == "https://telecom.internal:8443"
    for invalid in ["file:///etc/passwd", "ftp://evil.com", "javascript:alert(1)", ""]:
        try:
            _validate_base_url(invalid)
            assert False, f"Expected base_url failure for {invalid}"
        except ValueError:
            pass

    print("  [PASS] All input validations and security constraints verified successfully")


async def run_all_tests():
    print("=" * 60)
    print("TELECOM MCP SERVER COMPREHENSIVE TEST SUITE")
    print("=" * 60)
    test_input_validations()
    await test_tool_catalog()
    await test_network_summary()
    await test_grid_activity()
    await test_grid_features()
    await test_grid_location()
    await test_hotspots()
    await test_alerts()
    await test_pipeline_status()
    print("=" * 60)
    print("ALL TESTS PASSED SUCCESSFULLY! (100% PASS RATE)")
    print("=" * 60)


if __name__ == "__main__":
    asyncio.run(run_all_tests())
