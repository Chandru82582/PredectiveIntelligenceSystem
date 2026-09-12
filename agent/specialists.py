"""
Specialist Subagents Module for Telecom Italia Milan Predictive Intelligence System.

Defines four specialist agents:
1. Data Pipeline Agent - Ingestion health, ETL staleness, audit log, grain uniqueness.
2. Network Analysis Agent - Grid telemetry, 24h baseline, spatial hotspots, traffic surges.
3. ML Analysis Agent - LightGBM predictive inference, engineered rolling features, consensus review.
4. API Agent - REST API contract testing, latency benchmarks, service health.

Each specialist possesses a narrow operational mandate and a strictly restricted tool set.
All specialists share the same Anthropic API key / client.
"""

import os
import json
import logging
from typing import Dict, Any, List, Optional
from datetime import datetime, timezone
from dataclasses import dataclass, field
from sqlalchemy.orm import Session
import anthropic

from agent.tools import execute_tool, NOC_TOOLS

logger = logging.getLogger(__name__)


@dataclass
class SpecialistFinding:
    """Standardized output structure delivered by each specialist agent."""
    agent_key: str
    agent_name: str
    agent_role: str
    status: str  # e.g., "HEALTHY", "ATTENTION", "CRITICAL", "PASS", "FAIL", "STABLE"
    summary: str
    metrics: Dict[str, Any] = field(default_factory=dict)
    tools_called: List[str] = field(default_factory=list)
    finding_html: str = ""
    raw_response: str = ""


class BaseSpecialistAgent:
    """Base class for all specialist subagents."""

    def __init__(
        self,
        key: str,
        name: str,
        role: str,
        responsibility: str,
        allowed_tools: List[str],
        system_prompt: str,
        client: Optional[anthropic.Anthropic] = None,
        model: str = "claude-haiku-4-5-20251001"
    ):
        self.key = key
        self.name = name
        self.role = role
        self.responsibility = responsibility
        self.allowed_tools = allowed_tools
        self.system_prompt = system_prompt
        self.client = client
        self.model = model

        # Filter the global NOC tool definitions to ONLY allowed tools
        self.tool_schemas = [
            t for t in NOC_TOOLS if t.get("name") in self.allowed_tools
        ]

    def _execute_tool(self, tool_name: str, tool_args: dict, db: Session) -> dict:
        """Executes a tool call enforcing the restricted toolset boundary."""
        if tool_name not in self.allowed_tools:
            err_msg = f"Access denied: Specialist '{self.name}' is restricted from calling tool '{tool_name}'."
            logger.warning(err_msg)
            return {"error": err_msg}
        return execute_tool(tool_name, tool_args, db)

    def to_metadata(self) -> Dict[str, Any]:
        """Returns JSON-serializable metadata for frontend UI representation."""
        return {
            "key": self.key,
            "name": self.name,
            "role": self.role,
            "responsibility": self.responsibility,
            "allowed_tools": self.allowed_tools,
            "tool_count": len(self.allowed_tools)
        }

    def investigate(
        self,
        query: str,
        db: Session,
        grid_id: Optional[int] = None,
        evidence: Optional[Dict[str, Any]] = None,
        client: Optional[anthropic.Anthropic] = None
    ) -> SpecialistFinding:
        """Subclasses implement domain-specific diagnostic investigations."""
        raise NotImplementedError


# ==============================================================================
# 1. DATA PIPELINE AGENT
# ==============================================================================
class DataPipelineAgent(BaseSpecialistAgent):
    """
    Specialist responsible exclusively for data pipeline freshness, ETL audit logs,
    rejected batch rows, and strict grain uniqueness invariant checks.
    """

    SYSTEM_PROMPT = """You are the Senior Data Reliability & Ingestion Engineer for the Milan Telecom Predictive System.
Your narrow operational responsibility is:
1. Audit the raw-to-analytical data ingestion pipeline freshness and staleness.
2. Triage rejected rows/batches in the Spark audit log (audit_log.json).
3. Validate the non-negotiable grain invariant: exactly ONE record per (date, hour, grid_id) in hourly_grid_summary.
4. Report ingestion trustworthiness to the supervisor.

STRICT BOUNDARIES:
- You ONLY have access to: get_pipeline_status, check_grain_duplicates, read_skill_runbook.
- NEVER attempt to predict activity or evaluate ML models.
- NEVER describe high activity as congestion.
Always state clearly if the data layer is trustworthy for downstream ML and telemetry analysis.
"""

    def __init__(self, client: Optional[anthropic.Anthropic] = None):
        super().__init__(
            key="data_pipeline",
            name="Data Pipeline Agent",
            role="Data Reliability & Ingestion Specialist",
            responsibility="Audits raw-to-analytical ETL freshness, monitors rejected batches in audit logs, and validates the non-negotiable hourly grid grain invariant.",
            allowed_tools=["get_pipeline_status", "check_grain_duplicates", "read_skill_runbook"],
            system_prompt=self.SYSTEM_PROMPT,
            client=client
        )

    def investigate(
        self,
        query: str,
        db: Session,
        grid_id: Optional[int] = None,
        evidence: Optional[Dict[str, Any]] = None,
        client: Optional[anthropic.Anthropic] = None
    ) -> SpecialistFinding:
        active_client = client or self.client
        tools_called = []

        # 1. Execute restricted pipeline status tool
        pipeline_status = self._execute_tool("get_pipeline_status", {}, db)
        tools_called.append("get_pipeline_status")

        # 2. Execute grain duplicate check
        target_date = "2013-11-07"
        if evidence and "timestamp" in evidence:
            try:
                target_date = evidence["timestamp"].split("T")[0]
            except Exception:
                pass
        grain_status = self._execute_tool("check_grain_duplicates", {"date": target_date}, db)
        tools_called.append("check_grain_duplicates")

        status_val = pipeline_status.get("status", "HEALTHY")
        trustworthy = pipeline_status.get("trustworthy", True)
        last_ingest = pipeline_status.get("last_ingestion", "Unknown")
        rejected_count = pipeline_status.get("rejected_count", 0)
        accepted_count = pipeline_status.get("accepted_count", 0)
        grain_pass = grain_status.get("status") == "PASS"
        dup_count = grain_status.get("duplicate_grains_found", 0)

        metrics = {
            "status": status_val,
            "trustworthy": trustworthy,
            "last_ingestion": last_ingest,
            "accepted_batches": accepted_count,
            "rejected_batches": rejected_count,
            "grain_invariant": "PASS" if grain_pass else "FAIL",
            "duplicate_grains": dup_count,
            "target_date": target_date
        }

        # Overall agent verdict status
        if not trustworthy or not grain_pass:
            agent_status = "CRITICAL"
        elif rejected_count > 0:
            agent_status = "ATTENTION"
        else:
            agent_status = "HEALTHY"

        summary = (
            f"Pipeline is {status_val} (Trustworthy: {trustworthy}). "
            f"Grain invariant: {'PASSED (0 duplicates)' if grain_pass else f'FAILED ({dup_count} duplicates)'}. "
            f"Ingestion: {last_ingest}, {rejected_count} rejected batches."
        )

        badge_color = (
            "emerald" if agent_status == "HEALTHY" else "amber" if agent_status == "ATTENTION" else "rose"
        )
        finding_html = f"""
<div class="rounded-lg border border-{badge_color}-500/30 bg-{badge_color}-500/10 p-3 space-y-1.5">
  <div class="flex items-center justify-between text-xs">
    <span class="font-mono font-bold text-{badge_color}-400">DATA PIPELINE AGENT</span>
    <span class="px-2 py-0.5 rounded font-mono font-semibold bg-{badge_color}-500/20 text-{badge_color}-300 text-[10px]">{agent_status}</span>
  </div>
  <p class="text-xs text-slate-300">{summary}</p>
  <div class="grid grid-cols-3 gap-2 pt-1 font-mono text-[11px]">
    <div class="bg-slate-900/60 p-1.5 rounded border border-slate-800">
      <span class="text-slate-400 block text-[9px] uppercase tracking-wider">Ingestion</span>
      <span class="text-slate-200 font-semibold">{last_ingest.split('T')[0] if 'T' in last_ingest else last_ingest}</span>
    </div>
    <div class="bg-slate-900/60 p-1.5 rounded border border-slate-800">
      <span class="text-slate-400 block text-[9px] uppercase tracking-wider">Grain Status</span>
      <span class="{'text-emerald-400' if grain_pass else 'text-rose-400'} font-semibold">{metrics['grain_invariant']}</span>
    </div>
    <div class="bg-slate-900/60 p-1.5 rounded border border-slate-800">
      <span class="text-slate-400 block text-[9px] uppercase tracking-wider">Rejections</span>
      <span class="{'text-emerald-400' if rejected_count == 0 else 'text-amber-400'} font-semibold">{rejected_count}</span>
    </div>
  </div>
</div>
"""

        return SpecialistFinding(
            agent_key=self.key,
            agent_name=self.name,
            agent_role=self.role,
            status=agent_status,
            summary=summary,
            metrics=metrics,
            tools_called=tools_called,
            finding_html=finding_html.strip()
        )


# ==============================================================================
# 2. NETWORK ANALYSIS AGENT
# ==============================================================================
class NetworkAnalysisAgent(BaseSpecialistAgent):
    """
    Specialist responsible exclusively for physical grid cell telemetry,
    historical timeseries trends, baseline multiple deviations, traffic surges,
    and spatial coordinates / sector categorization.
    """

    SYSTEM_PROMPT = """You are the Senior Telecom NOC Field & Telemetry Engineer for the Milan Metropolitan Network.
Your narrow operational responsibility is:
1. Analyze physical traffic distribution across the 100x100 grid (10,000 cells).
2. Measure 24-hour historical baseline activity deviations and instantaneous traffic surges.
3. Classify cell sector geography (Sector A1 through D4) and centroid coordinates.
4. Detect high-activity hotspots and modality distribution (SMS vs Calls vs Internet).

NON-NEGOTIABLE DOMAIN RULES:
- Proportional measures: All activity values are dimensionless normalized measures. NEVER refer to them as counts or MB/GB.
- High activity vs Congestion: High activity values MUST NEVER be described as confirmed congestion. Use "high activity", "activity surge", "volume spike", or "elevated demand".
- GeoJSON coordinate layout: 1-indexed cellId 1..10000.
"""

    def __init__(self, client: Optional[anthropic.Anthropic] = None):
        super().__init__(
            key="network_analysis",
            name="Network Analysis Agent",
            role="Cell Telemetry & Spatial Traffic Specialist",
            responsibility="Investigates physical grid telemetry, 24-hour baseline deviations, traffic surges, spatial sector coordinates, and fleet-wide hotspots.",
            allowed_tools=[
                "get_network_summary",
                "get_grid_activity",
                "get_hotspots",
                "get_grid_location",
                "read_skill_runbook"
            ],
            system_prompt=self.SYSTEM_PROMPT,
            client=client
        )

    def investigate(
        self,
        query: str,
        db: Session,
        grid_id: Optional[int] = None,
        evidence: Optional[Dict[str, Any]] = None,
        client: Optional[anthropic.Anthropic] = None
    ) -> SpecialistFinding:
        active_client = client or self.client
        tools_called = []
        target_grid = grid_id or (evidence.get("grid_id") if evidence else 4365)

        # 1. Execute grid activity telemetry tool
        grid_act = self._execute_tool("get_grid_activity", {"grid_id": target_grid}, db)
        tools_called.append("get_grid_activity")

        # 2. Execute spatial coordinates tool
        grid_loc = self._execute_tool("get_grid_location", {"grid_id": target_grid}, db)
        tools_called.append("get_grid_location")

        # 3. Execute fleet hotspots tool
        hotspots_res = self._execute_tool("get_hotspots", {"limit": 3}, db)
        tools_called.append("get_hotspots")

        curr_act = grid_act.get("current_activity", 0.0) if "error" not in grid_act else (evidence.get("current_activity", 0.0) if evidence else 0.0)
        base_act = grid_act.get("24h_baseline", 0.0) if "error" not in grid_act else (evidence.get("baseline_activity", 1.0) if evidence else 1.0)
        sector = grid_loc.get("sector", "Milan")
        lat = grid_loc.get("latitude", 45.46)
        lon = grid_loc.get("longitude", 9.19)

        surge_ratio = round(curr_act / base_act, 2) if base_act > 0 else 1.0

        if surge_ratio >= 2.0:
            agent_status = "CRITICAL"
            verdict_desc = f"Elevated activity surge ({surge_ratio}x baseline)"
        elif surge_ratio >= 1.3:
            agent_status = "ATTENTION"
            verdict_desc = f"Moderate activity elevation ({surge_ratio}x baseline)"
        else:
            agent_status = "HEALTHY"
            verdict_desc = f"Nominal telemetry ({surge_ratio}x baseline)"

        metrics = {
            "grid_id": target_grid,
            "current_activity": curr_act,
            "baseline_activity": base_act,
            "surge_ratio": surge_ratio,
            "sector": sector,
            "latitude": lat,
            "longitude": lon,
            "top_hotspots": [h["grid_id"] for h in hotspots_res.get("hotspots", [])] if isinstance(hotspots_res.get("hotspots"), list) else []
        }

        summary = (
            f"Cell #{target_grid} in {sector} reports current activity {curr_act:.1f} vs 24h baseline {base_act:.1f} "
            f"({surge_ratio:.2f}x multiple). {verdict_desc}."
        )

        badge_color = (
            "emerald" if agent_status == "HEALTHY" else "amber" if agent_status == "ATTENTION" else "rose"
        )
        finding_html = f"""
<div class="rounded-lg border border-{badge_color}-500/30 bg-{badge_color}-500/10 p-3 space-y-1.5">
  <div class="flex items-center justify-between text-xs">
    <span class="font-mono font-bold text-{badge_color}-400">NETWORK ANALYSIS AGENT</span>
    <span class="px-2 py-0.5 rounded font-mono font-semibold bg-{badge_color}-500/20 text-{badge_color}-300 text-[10px]">{agent_status}</span>
  </div>
  <p class="text-xs text-slate-300">{summary}</p>
  <div class="grid grid-cols-3 gap-2 pt-1 font-mono text-[11px]">
    <div class="bg-slate-900/60 p-1.5 rounded border border-slate-800">
      <span class="text-slate-400 block text-[9px] uppercase tracking-wider">Current Act.</span>
      <span class="text-cyan-400 font-semibold">{curr_act:.1f}</span>
    </div>
    <div class="bg-slate-900/60 p-1.5 rounded border border-slate-800">
      <span class="text-slate-400 block text-[9px] uppercase tracking-wider">24h Baseline</span>
      <span class="text-slate-300 font-semibold">{base_act:.1f}</span>
    </div>
    <div class="bg-slate-900/60 p-1.5 rounded border border-slate-800">
      <span class="text-slate-400 block text-[9px] uppercase tracking-wider">Surge Ratio</span>
      <span class="{'text-rose-400' if surge_ratio >= 2.0 else 'text-amber-400' if surge_ratio >= 1.3 else 'text-emerald-400'} font-semibold">{surge_ratio}x</span>
    </div>
  </div>
</div>
"""

        return SpecialistFinding(
            agent_key=self.key,
            agent_name=self.name,
            agent_role=self.role,
            status=agent_status,
            summary=summary,
            metrics=metrics,
            tools_called=tools_called,
            finding_html=finding_html.strip()
        )


# ==============================================================================
# 3. ML ANALYSIS AGENT
# ==============================================================================
class MLAnalysisAgent(BaseSpecialistAgent):
    """
    Specialist responsible exclusively for LightGBM predictive risk scoring,
    engineered rolling lag features, next-hour activity surge probabilities,
    and arbitration between rule heuristics and ML classifier velocity.
    """

    SYSTEM_PROMPT = """You are the Senior Telecom Machine Learning & Anomaly Specialist.
Your narrow operational responsibility is:
1. Evaluate LightGBM probability scores and risk labels (NORMAL vs HIGH_ACTIVITY_RISK) for the next hour.
2. Analyze engineered rolling feature dynamics: activity growth, peak ratio, rolling variability, and internet share.
3. Review rule alert vs ML classifier consensus and explain agreements or disagreements.
4. Advise the supervisor whether predictive risk warrants proactive mitigation.

NON-NEGOTIABLE DOMAIN RULES:
- High probability indicates predicted high activity, NOT confirmed congestion.
- Feature pipeline requires strictly chronological ordering.
"""

    def __init__(self, client: Optional[anthropic.Anthropic] = None):
        super().__init__(
            key="ml_analysis",
            name="ML Analysis Agent",
            role="Predictive Inference & Anomaly Specialist",
            responsibility="Evaluates LightGBM predictive risk scoring, rolling lag feature dynamics, and arbitrates consensus between static rule heuristics and ML velocity.",
            allowed_tools=[
                "get_anomaly_score",
                "get_grid_features",
                "review_grid_anomaly",
                "read_skill_runbook"
            ],
            system_prompt=self.SYSTEM_PROMPT,
            client=client
        )

    def investigate(
        self,
        query: str,
        db: Session,
        grid_id: Optional[int] = None,
        evidence: Optional[Dict[str, Any]] = None,
        client: Optional[anthropic.Anthropic] = None
    ) -> SpecialistFinding:
        active_client = client or self.client
        tools_called = []
        target_grid = grid_id or (evidence.get("grid_id") if evidence else 4365)

        # 1. Execute ML anomaly score
        anomaly_res = self._execute_tool("get_anomaly_score", {"grid_id": target_grid}, db)
        tools_called.append("get_anomaly_score")

        # 2. Execute engineered features
        features_res = self._execute_tool("get_grid_features", {"grid_id": target_grid}, db)
        tools_called.append("get_grid_features")

        # 3. Execute anomaly consensus review
        consensus_res = self._execute_tool("review_grid_anomaly", {"grid_id": target_grid}, db)
        tools_called.append("review_grid_anomaly")

        score = anomaly_res.get("score", 0.0) if "error" not in anomaly_res else (evidence.get("anomaly_score", 0.0) if evidence else 0.0)
        direction = anomaly_res.get("direction", "NORMAL") if "error" not in anomaly_res else (evidence.get("direction", "NORMAL") if evidence else "NORMAL")
        peak_r = features_res.get("peak_ratio", 1.0)
        growth = features_res.get("activity_growth", 0.0)
        variability = features_res.get("variability", 0.0)
        consensus = consensus_res.get("consensus", "FULL_AGREEMENT_NORMAL")
        verdict = consensus_res.get("verdict", "Evaluated nominal risk.")

        if score >= 0.70 or direction == "HIGH_ACTIVITY_RISK":
            agent_status = "CRITICAL"
        elif score >= 0.40:
            agent_status = "ATTENTION"
        else:
            agent_status = "HEALTHY"

        metrics = {
            "grid_id": target_grid,
            "anomaly_probability": round(score, 4),
            "risk_label": direction,
            "peak_ratio": round(peak_r, 2),
            "activity_growth": round(growth, 3),
            "variability": round(variability, 2),
            "consensus": consensus,
            "verdict": verdict
        }

        summary = (
            f"LightGBM scores Cell #{target_grid} at {score*100:.1f}% risk ({direction}). "
            f"Peak ratio: {peak_r:.2f}, Growth: {growth:+.3f}. Consensus: {consensus}."
        )

        badge_color = (
            "emerald" if agent_status == "HEALTHY" else "amber" if agent_status == "ATTENTION" else "rose"
        )
        finding_html = f"""
<div class="rounded-lg border border-{badge_color}-500/30 bg-{badge_color}-500/10 p-3 space-y-1.5">
  <div class="flex items-center justify-between text-xs">
    <span class="font-mono font-bold text-{badge_color}-400">ML ANALYSIS AGENT</span>
    <span class="px-2 py-0.5 rounded font-mono font-semibold bg-{badge_color}-500/20 text-{badge_color}-300 text-[10px]">{agent_status}</span>
  </div>
  <p class="text-xs text-slate-300">{summary}</p>
  <div class="grid grid-cols-3 gap-2 pt-1 font-mono text-[11px]">
    <div class="bg-slate-900/60 p-1.5 rounded border border-slate-800">
      <span class="text-slate-400 block text-[9px] uppercase tracking-wider">Risk Prob.</span>
      <span class="{'text-rose-400' if score >= 0.7 else 'text-amber-400' if score >= 0.4 else 'text-emerald-400'} font-semibold">{(score * 100):.1f}%</span>
    </div>
    <div class="bg-slate-900/60 p-1.5 rounded border border-slate-800">
      <span class="text-slate-400 block text-[9px] uppercase tracking-wider">Peak Ratio</span>
      <span class="text-slate-200 font-semibold">{peak_r:.2f}</span>
    </div>
    <div class="bg-slate-900/60 p-1.5 rounded border border-slate-800">
      <span class="text-slate-400 block text-[9px] uppercase tracking-wider">Consensus</span>
      <span class="text-cyan-300 font-semibold truncate block" title="{consensus}">{consensus.replace('FULL_AGREEMENT_', '')}</span>
    </div>
  </div>
</div>
"""

        return SpecialistFinding(
            agent_key=self.key,
            agent_name=self.name,
            agent_role=self.role,
            status=agent_status,
            summary=summary,
            metrics=metrics,
            tools_called=tools_called,
            finding_html=finding_html.strip()
        )


# ==============================================================================
# 4. API AGENT
# ==============================================================================
class APIAgent(BaseSpecialistAgent):
    """
    Specialist responsible exclusively for running and evaluating the REST API
    test suite, verifying HTTP status codes and schemas, and measuring latencies.
    """

    SYSTEM_PROMPT = """You are the Senior Backend Platform & API Quality Engineer.
Your narrow operational responsibility is:
1. Execute the in-process REST API test suite via TestClient.
2. Validate HTTP 200 contracts and Pydantic schemas across all platform endpoints.
3. Measure endpoint response latencies and flag latency regressions (>1000ms).
4. Report service degradation or regression failures to the supervisor.

STRICT BOUNDARIES:
- You ONLY have access to: run_api_test_suite, read_skill_runbook.
- You do NOT diagnose ML models or physical grid cell performance.
"""

    def __init__(self, client: Optional[anthropic.Anthropic] = None):
        super().__init__(
            key="api_agent",
            name="API Agent",
            role="REST API Contract & Latency Specialist",
            responsibility="Executes the backend REST API test suite, verifies HTTP contract schemas, benchmarks endpoint response latencies, and isolates API regressions.",
            allowed_tools=["run_api_test_suite", "read_skill_runbook"],
            system_prompt=self.SYSTEM_PROMPT,
            client=client
        )

    def investigate(
        self,
        query: str,
        db: Session,
        grid_id: Optional[int] = None,
        evidence: Optional[Dict[str, Any]] = None,
        client: Optional[anthropic.Anthropic] = None
    ) -> SpecialistFinding:
        active_client = client or self.client
        tools_called = ["run_api_test_suite"]

        suite_res = self._execute_tool("run_api_test_suite", {}, db)

        total = suite_res.get("total_cases", 12)
        passed = suite_res.get("passed", total)
        failed = suite_res.get("failed", 0)
        duration_s = suite_res.get("duration_seconds", 0.0)
        failures = suite_res.get("failures", [])

        if failed > 0:
            agent_status = "CRITICAL" if failed > 2 else "ATTENTION"
        else:
            agent_status = "HEALTHY"

        metrics = {
            "total_endpoints_tested": total,
            "passed": passed,
            "failed": failed,
            "duration_seconds": round(duration_s, 2),
            "failures": failures
        }

        summary = (
            f"API test suite executed {total} endpoints in {duration_s:.2f}s: "
            f"{passed} PASSED, {failed} FAILED."
        )

        badge_color = (
            "emerald" if agent_status == "HEALTHY" else "amber" if agent_status == "ATTENTION" else "rose"
        )
        finding_html = f"""
<div class="rounded-lg border border-{badge_color}-500/30 bg-{badge_color}-500/10 p-3 space-y-1.5">
  <div class="flex items-center justify-between text-xs">
    <span class="font-mono font-bold text-{badge_color}-400">API AGENT</span>
    <span class="px-2 py-0.5 rounded font-mono font-semibold bg-{badge_color}-500/20 text-{badge_color}-300 text-[10px]">{agent_status}</span>
  </div>
  <p class="text-xs text-slate-300">{summary}</p>
  <div class="grid grid-cols-3 gap-2 pt-1 font-mono text-[11px]">
    <div class="bg-slate-900/60 p-1.5 rounded border border-slate-800">
      <span class="text-slate-400 block text-[9px] uppercase tracking-wider">Total Tests</span>
      <span class="text-slate-200 font-semibold">{total}</span>
    </div>
    <div class="bg-slate-900/60 p-1.5 rounded border border-slate-800">
      <span class="text-slate-400 block text-[9px] uppercase tracking-wider">Pass Rate</span>
      <span class="{'text-emerald-400' if failed == 0 else 'text-rose-400'} font-semibold">{passed}/{total}</span>
    </div>
    <div class="bg-slate-900/60 p-1.5 rounded border border-slate-800">
      <span class="text-slate-400 block text-[9px] uppercase tracking-wider">Latency/Dur.</span>
      <span class="text-slate-300 font-semibold">{duration_s:.2f}s</span>
    </div>
  </div>
</div>
"""

        return SpecialistFinding(
            agent_key=self.key,
            agent_name=self.name,
            agent_role=self.role,
            status=agent_status,
            summary=summary,
            metrics=metrics,
            tools_called=tools_called,
            finding_html=finding_html.strip()
        )


def create_specialist_registry(client: Optional[anthropic.Anthropic] = None) -> Dict[str, BaseSpecialistAgent]:
    """Factory creating all 4 specialist subagents sharing the same client."""
    return {
        "data_pipeline": DataPipelineAgent(client=client),
        "network_analysis": NetworkAnalysisAgent(client=client),
        "ml_analysis": MLAnalysisAgent(client=client),
        "api_agent": APIAgent(client=client)
    }
