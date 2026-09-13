# Telecom Italia Milan Predictive Intelligence MCP Server

Model Context Protocol (MCP) server providing Claude and external LLM agents with standardized tool access to the Milan Telecommunications Predictive Intelligence platform.

## Architecture & Zero Business Logic Invariant

This MCP server follows the **Thin Wrapper Pattern**:
- **Zero Business Logic**: Does not compute, aggregate, threshold, or interpret metrics. All calculations, spatial joins, and anomalies are handled exclusively by backend REST endpoints.
- **Strict Validation & Security Constraints**: Validates input bounds (`grid_id` within 1–10,000, `limit` within 1–1,000, `severity` whitelist, ISO-8601 formatting, date/hour limits, URL scheme/SSRF protection).
- **Transport Flexibility**: Supports `stdio` (default for Claude Desktop / Claude Code) as well as `sse` and `streamable-http`.

---

## Exposed MCP Tools

| Tool Name | Backend Endpoint | Description | Key Parameters |
|---|---|---|---|
| `network_summary` | `GET /network/summary` | High-level network activity metrics, active grids count, peak hour, and top grid cell. | `as_of` (optional ISO-8601 string) |
| `grid_activity` | `GET /network/grid/{grid_id}` | 24-hour activity timeseries for a specific grid cell (total, sms, calls, internet). | `grid_id` (1–10,000), `as_of`, `date`, `hour` |
| `grid_features` | `GET /network/grid/{grid_id}/features` | Engineered ML telemetry features (rolling averages, lag metrics, activity ratios). | `grid_id` (1–10,000), `as_of` |
| `grid_location` | `GET /network/grid/{grid_id}/location` | Spatial coordinates (lat/lon centroid), polygon ring boundaries, and ops sector label. | `grid_id` (1–10,000) |
| `hotspots` | `GET /network/hotspots` | Leaderboard of grid cells with highest activity volume. | `limit` (1–1,000, default: 10), `severity` (HIGH/MEDIUM/LOW), `as_of` |
| `alerts` | `GET /network/alerts` | Active threshold and rule-based anomaly alerts. | `limit` (1–1,000, default: 50), `severity` (HIGH/MEDIUM/LOW), `as_of` |
| `pipeline_status` | `GET /pipeline/status` | ETL ingestion pipeline status, staleness in minutes, and rejected batch details. | *(None)* |

---

## Claude Desktop Configuration

Add the server to your `claude_desktop_config.json`:

```json
{
  "mcpServers": {
    "telecom-intelligence": {
      "command": "python",
      "args": [
        "D:\\PredectiveIntelligenceSystem\\mcp_server\\server.py"
      ],
      "env": {
        "PYTHONPATH": "D:\\PredectiveIntelligenceSystem",
        "TELECOM_API_URL": "http://localhost:8000",
        "TELECOM_API_KEY": "secret-key-change-in-production"
      }
    }
  }
}
```

---

## Running the Server Directly

### Standard I/O (Default)
```bash
python -m mcp_server.server
```

### Server-Sent Events (SSE)
```bash
python -m mcp_server.server --transport sse --host 127.0.0.1 --port 8001
```

---

## Running the Test Suite

```bash
python mcp_server/test_server.py
```
