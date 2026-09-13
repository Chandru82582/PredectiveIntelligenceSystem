"""
Model Context Protocol (MCP) Server for Telecom Italia Milan Predictive Intelligence System.

Exposes thin tool wrappers over backend REST endpoints to Claude and MCP clients.
Hard Rule: Contains ZERO business logic. It does not compute, aggregate, threshold,
or interpret anything. All analytical logic resides strictly in backend endpoints.
Includes strict input validation and basic security constraints.
"""

import argparse
import logging
import os
import re
import sys
from pathlib import Path

# Ensure project root is on sys.path regardless of execution working directory
_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from datetime import datetime
from typing import Any, Dict, Literal, Optional
from urllib.parse import urlparse

import httpx
from mcp.server.mcpserver import MCPServer
from pydantic import Field

logger = logging.getLogger("telecom_mcp_server")

# Default configuration from environment (fallback defaults)
DEFAULT_BASE_URL = os.getenv("TELECOM_API_URL", os.getenv("API_BASE_URL", "http://localhost:8000"))
DEFAULT_API_KEY = os.getenv("TELECOM_API_KEY", os.getenv("API_KEY", ""))
DEFAULT_TIMEOUT = float(os.getenv("TELECOM_API_TIMEOUT", "15.0"))

# Security and input validation regex patterns
_DATE_REGEX = re.compile(r"^\d{4}-\d{2}-\d{2}$")
_ISO_TIMESTAMP_REGEX = re.compile(
    r"^\d{4}-\d{2}-\d{2}(?:[T ]\d{2}:\d{2}(?::\d{2}(?:\.\d+)?)?)?(?:Z|[+-]\d{2}:?\d{2})?$"
)
_VALID_SEVERITIES = {"HIGH", "MEDIUM", "LOW"}


def _validate_base_url(url: str) -> str:
    """Security constraint: Validate URL scheme and host to prevent SSRF and protocol misuse."""
    if not url or not isinstance(url, str):
        raise ValueError("Base URL must be a non-empty string.")
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https"):
        raise ValueError(f"Security constraint violated: URL scheme '{parsed.scheme}' not allowed (must be http or https).")
    if not parsed.netloc:
        raise ValueError(f"Security constraint violated: Invalid base URL host '{url}'.")
    return url.rstrip("/")


def _validate_grid_id(grid_id: Any) -> int:
    """Validate grid cell ID is an integer within the 100x100 Milan lattice (1 to 10,000)."""
    if not isinstance(grid_id, int) or isinstance(grid_id, bool):
        try:
            grid_id = int(grid_id)
        except (ValueError, TypeError):
            raise ValueError(f"Invalid grid_id: '{grid_id}'. Must be an integer.")
    if grid_id < 1 or grid_id > 10000:
        raise ValueError(f"Grid ID {grid_id} out of bounds (must be between 1 and 10000).")
    return grid_id


def _validate_limit(limit: Any, min_val: int = 1, max_val: int = 1000) -> int:
    """Validate pagination/result limit within acceptable bounds to prevent resource exhaustion."""
    if not isinstance(limit, int) or isinstance(limit, bool):
        try:
            limit = int(limit)
        except (ValueError, TypeError):
            raise ValueError(f"Invalid limit: '{limit}'. Must be an integer.")
    if limit < min_val or limit > max_val:
        raise ValueError(f"Limit {limit} out of bounds (must be between {min_val} and {max_val}).")
    return limit


def _validate_severity(severity: Optional[str]) -> Optional[str]:
    """Validate severity filter against strict whitelist."""
    if severity is None:
        return None
    if not isinstance(severity, str):
        raise ValueError(f"Invalid severity type: {type(severity).__name__}. Must be a string.")
    normalized = severity.strip().upper()
    if normalized not in _VALID_SEVERITIES:
        raise ValueError(f"Invalid severity '{severity}'. Must be one of: {', '.join(sorted(_VALID_SEVERITIES))}.")
    return normalized


def _validate_iso_timestamp(timestamp: Optional[str]) -> Optional[str]:
    """Validate ISO-8601 operational timestamp format and restrict string length."""
    if timestamp is None:
        return None
    if not isinstance(timestamp, str):
        raise ValueError(f"Invalid as_of timestamp type: {type(timestamp).__name__}. Must be an ISO-8601 string.")
    trimmed = timestamp.strip()
    if len(trimmed) > 50:
        raise ValueError("Invalid as_of timestamp: string length exceeds 50 characters.")
    if not _ISO_TIMESTAMP_REGEX.match(trimmed):
        raise ValueError(f"Invalid as_of format: '{timestamp}'. Expected ISO-8601 format (e.g. '2013-11-07T23:00:00').")
    return trimmed


def _validate_date(date_str: Optional[str]) -> Optional[str]:
    """Validate target calendar date string (YYYY-MM-DD)."""
    if date_str is None:
        return None
    if not isinstance(date_str, str):
        raise ValueError(f"Invalid date type: {type(date_str).__name__}. Must be a string.")
    trimmed = date_str.strip()
    if not _DATE_REGEX.match(trimmed):
        raise ValueError(f"Invalid date format: '{date_str}'. Expected 'YYYY-MM-DD'.")
    try:
        datetime.strptime(trimmed, "%Y-%m-%d")
    except ValueError as e:
        raise ValueError(f"Invalid calendar date '{date_str}': {e}")
    return trimmed


def _validate_hour(hour: Optional[int]) -> Optional[int]:
    """Validate target hour is within 0 to 23."""
    if hour is None:
        return None
    if not isinstance(hour, int) or isinstance(hour, bool):
        try:
            hour = int(hour)
        except (ValueError, TypeError):
            raise ValueError(f"Invalid hour: '{hour}'. Must be an integer.")
    if hour < 0 or hour > 23:
        raise ValueError(f"Hour {hour} out of bounds (must be between 0 and 23).")
    return hour


class TelecomMCPServer(MCPServer):
    """
    Model Context Protocol (MCP) Server wrapping the Telecom Analytics REST API.

    Adheres strictly to the Thin Wrapper pattern:
    - Zero calculations, zero aggregations, zero thresholds, zero business interpretations.
    - Pure parameter forwarding to underlying backend REST endpoints.
    - Input validation and security bounds checking on all incoming parameters.
    """

    def __init__(
        self,
        name: str = "telecom-predictive-intelligence",
        base_url: Optional[str] = None,
        api_key: Optional[str] = None,
        timeout: float = DEFAULT_TIMEOUT,
        client: Optional[httpx.AsyncClient] = None,
        **kwargs: Any,
    ):
        super().__init__(
            name=name,
            title="Telecom Italia Milan Predictive Intelligence MCP Server",
            description="MCP tool interface exposing Milan telecom telemetry and analytics endpoints to Claude.",
            **kwargs,
        )

        raw_url = base_url or DEFAULT_BASE_URL
        self.base_url = _validate_base_url(raw_url)
        self.api_key = api_key if api_key is not None else DEFAULT_API_KEY
        self.timeout = timeout

        self.headers = {
            "User-Agent": "Telecom-MCP-Server/1.0",
            "Accept": "application/json",
        }
        if self.api_key:
            self.headers["X-API-Key"] = self.api_key

        # Injected or internal httpx client
        self._client = client

        # Register the 7 thin tool wrappers
        self._register_tools()

    async def _execute_get(self, path: str, params: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """
        Pure HTTP GET forwarder.
        Dispatches request to backend, returning raw response payload without any alteration.
        """
        query_params = {k: str(v) for k, v in params.items() if v is not None} if params else None
        url = f"{self.base_url}/{path.lstrip('/')}"

        should_close = False
        client = self._client
        if client is None:
            client = httpx.AsyncClient(headers=self.headers, timeout=self.timeout)
            should_close = True

        try:
            response = await client.get(url, params=query_params)
            response.raise_for_status()
            return response.json()
        except httpx.HTTPStatusError as exc:
            logger.error(f"Backend API error {exc.response.status_code} for {path}: {exc.response.text}")
            try:
                err_json = exc.response.json()
                detail = err_json.get("detail", exc.response.text)
            except Exception:
                detail = exc.response.text or str(exc)
            return {
                "error": True,
                "status_code": exc.response.status_code,
                "detail": detail,
            }
        except httpx.RequestError as exc:
            logger.error(f"Backend connection error for {path}: {exc}")
            return {
                "error": True,
                "status_code": 503,
                "detail": f"Failed to connect to Telecom backend API at {self.base_url}: {str(exc)}",
            }
        finally:
            if should_close:
                await client.aclose()

    def _register_tools(self) -> None:
        """Register the 7 thin tool wrappers over existing endpoints."""

        # 1. network_summary -> GET /network/summary
        @self.tool(
            name="network_summary",
            description="Retrieve high-level network summary metrics (total network activity, active grid cells count, peak hour, top grid cell ID, and effective operational timestamp).",
        )
        async def network_summary(
            as_of: Optional[str] = Field(
                default=None,
                description="Optional operational timestamp in ISO-8601 format (e.g. '2013-11-07T23:00:00'). Defaults to latest available data timestamp.",
            ),
        ) -> Dict[str, Any]:
            validated_as_of = _validate_iso_timestamp(as_of)
            params = {"as_of": validated_as_of} if validated_as_of else None
            return await self._execute_get("/network/summary", params=params)

        # 2. grid_activity -> GET /network/grid/{grid_id}
        @self.tool(
            name="grid_activity",
            description="Retrieve 24-hour activity timeseries for a specific grid cell (total activity, sms in/out, call in/out, internet traffic).",
        )
        async def grid_activity(
            grid_id: int = Field(
                ...,
                ge=1,
                le=10000,
                description="Grid cell identifier (integer between 1 and 10000).",
            ),
            as_of: Optional[str] = Field(
                default=None,
                description="Optional operational timestamp in ISO-8601 format.",
            ),
            date: Optional[str] = Field(
                default=None,
                description="Optional target date in 'YYYY-MM-DD' format.",
            ),
            hour: Optional[int] = Field(
                default=None,
                ge=0,
                le=23,
                description="Optional target hour integer (0 to 23).",
            ),
        ) -> Dict[str, Any]:
            v_grid_id = _validate_grid_id(grid_id)
            v_as_of = _validate_iso_timestamp(as_of)
            v_date = _validate_date(date)
            v_hour = _validate_hour(hour)

            params = {}
            if v_as_of is not None:
                params["as_of"] = v_as_of
            if v_date is not None:
                params["date"] = v_date
            if v_hour is not None:
                params["hour"] = v_hour

            return await self._execute_get(f"/network/grid/{v_grid_id}", params=params or None)

        # 3. grid_features -> GET /network/grid/{grid_id}/features
        @self.tool(
            name="grid_features",
            description="Retrieve engineered ML telemetry features for a specific grid cell (e.g. rolling averages, lag metrics, activity ratios).",
        )
        async def grid_features(
            grid_id: int = Field(
                ...,
                ge=1,
                le=10000,
                description="Grid cell identifier (integer between 1 and 10000).",
            ),
            as_of: Optional[str] = Field(
                default=None,
                description="Optional operational timestamp in ISO-8601 format.",
            ),
        ) -> Dict[str, Any]:
            v_grid_id = _validate_grid_id(grid_id)
            v_as_of = _validate_iso_timestamp(as_of)
            params = {"as_of": v_as_of} if v_as_of else None
            return await self._execute_get(f"/network/grid/{v_grid_id}/features", params=params)

        # 4. grid_location -> GET /network/grid/{grid_id}/location
        @self.tool(
            name="grid_location",
            description="Retrieve spatial coordinates (lat/lon centroid), polygon boundary coordinates, and operations sector label for a specific grid cell.",
        )
        async def grid_location(
            grid_id: int = Field(
                ...,
                ge=1,
                le=10000,
                description="Grid cell identifier (integer between 1 and 10000).",
            ),
        ) -> Dict[str, Any]:
            v_grid_id = _validate_grid_id(grid_id)
            return await self._execute_get(f"/network/grid/{v_grid_id}/location")

        # 5. hotspots -> GET /network/hotspots
        @self.tool(
            name="hotspots",
            description="Retrieve the leaderboard of network grid cells with the highest activity volume for the operational hour.",
        )
        async def hotspots(
            limit: int = Field(
                default=10,
                ge=1,
                le=1000,
                description="Maximum number of hotspot cells to return (1 to 1000, default: 10).",
            ),
            severity: Optional[Literal["HIGH", "MEDIUM", "LOW"]] = Field(
                default="HIGH",
                description="Severity filter: 'HIGH', 'MEDIUM', or 'LOW'.",
            ),
            as_of: Optional[str] = Field(
                default=None,
                description="Optional operational timestamp in ISO-8601 format.",
            ),
        ) -> Dict[str, Any]:
            v_limit = _validate_limit(limit)
            v_severity = _validate_severity(severity) or "HIGH"
            v_as_of = _validate_iso_timestamp(as_of)

            params = {
                "limit": v_limit,
                "severity": v_severity,
            }
            if v_as_of:
                params["as_of"] = v_as_of

            return await self._execute_get("/network/hotspots", params=params)

        # 6. alerts -> GET /network/alerts
        @self.tool(
            name="alerts",
            description="Retrieve active threshold and anomaly rule alerts for network grid cells.",
        )
        async def alerts(
            limit: int = Field(
                default=50,
                ge=1,
                le=1000,
                description="Maximum number of alerts to return (1 to 1000, default: 50).",
            ),
            severity: Optional[Literal["HIGH", "MEDIUM", "LOW"]] = Field(
                default=None,
                description="Optional severity filter: 'HIGH', 'MEDIUM', or 'LOW'.",
            ),
            as_of: Optional[str] = Field(
                default=None,
                description="Optional operational timestamp in ISO-8601 format.",
            ),
        ) -> Dict[str, Any]:
            v_limit = _validate_limit(limit)
            v_severity = _validate_severity(severity)
            v_as_of = _validate_iso_timestamp(as_of)

            params: Dict[str, Any] = {"limit": v_limit}
            if v_severity:
                params["severity"] = v_severity
            if v_as_of:
                params["as_of"] = v_as_of

            return await self._execute_get("/network/alerts", params=params)

        # 7. pipeline_status -> GET /pipeline/status
        @self.tool(
            name="pipeline_status",
            description="Retrieve ETL data ingestion pipeline health, audit log summary, staleness in minutes, and rejected batch details.",
        )
        async def pipeline_status() -> Dict[str, Any]:
            return await self._execute_get("/pipeline/status")


# Singleton instance for quick execution and imports
server = TelecomMCPServer()


def main():
    """CLI entrypoint for running the Telecom MCP Server."""
    parser = argparse.ArgumentParser(
        description="Telecom Italia Milan Predictive Intelligence MCP Server"
    )
    parser.add_argument(
        "--transport",
        choices=["stdio", "sse", "streamable-http"],
        default="stdio",
        help="Transport mechanism to run the MCP server (default: stdio)",
    )
    parser.add_argument(
        "--host",
        default="127.0.0.1",
        help="Host address for SSE or streamable-http transports (default: 127.0.0.1)",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=8001,
        help="Port number for SSE or streamable-http transports (default: 8001)",
    )
    parser.add_argument(
        "--api-url",
        default=None,
        help=f"Base URL for backend REST API (default: {DEFAULT_BASE_URL})",
    )
    parser.add_argument(
        "--api-key",
        default=None,
        help="API Key for X-API-Key header authentication",
    )
    args = parser.parse_args()

    mcp_instance = TelecomMCPServer(
        base_url=args.api_url,
        api_key=args.api_key,
    )

    if args.transport == "stdio":
        mcp_instance.run(transport="stdio")
    else:
        mcp_instance.run(transport=args.transport, host=args.host, port=args.port)


if __name__ == "__main__":
    main()
