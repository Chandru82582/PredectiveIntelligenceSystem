"""
Model Context Protocol (MCP) Server for Telecom Italia Milan Predictive Intelligence System.

Exposes thin tool wrappers over backend REST endpoints to Claude and MCP clients.
Contains zero business logic, strictly adhering to the MCP contract specification.
"""

from mcp_server.server import TelecomMCPServer, server, main

__all__ = ["TelecomMCPServer", "server", "main"]
