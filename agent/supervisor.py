"""
Supervisor Agent Module for Telecom Italia Milan Predictive Intelligence System.

Coordinates multi-agent investigations across 4 specialist subagents:
1. Data Pipeline Agent (ETL, freshness, audit log, grain uniqueness)
2. Network Analysis Agent (telemetry, baseline, traffic surges, hotspots)
3. ML Analysis Agent (predictive scoring, rolling features, anomaly consensus)
4. API Agent (REST API contract verification, latency benchmarks)

Uses the same Anthropic API key across all agents, delegates tasks,
collects specialist findings, and produces one unified, comprehensive NOC report.
"""

import os
import json
import logging
from typing import Dict, Any, List, Optional
from datetime import datetime, timezone
from sqlalchemy.orm import Session
from dotenv import load_dotenv
import anthropic

from agent.specialists import (
    BaseSpecialistAgent,
    DataPipelineAgent,
    NetworkAnalysisAgent,
    MLAnalysisAgent,
    APIAgent,
    SpecialistFinding,
    create_specialist_registry
)
from agent.skills import match_skills_for_prompt
from agent.slash_commands import is_slash_command, handle_slash_command

logger = logging.getLogger(__name__)

# Load Anthropic API Key from environment (shared across all agents)
load_dotenv()
_SHARED_API_KEY = os.getenv("ANTHROPIC_API_KEY")
_SHARED_CLIENT = anthropic.Anthropic(api_key=_SHARED_API_KEY) if _SHARED_API_KEY else None


class SupervisorAgent:
    """
    Lead NOC Operations Commander / Supervisor Agent.
    Coordinates investigations, delegates to specialists, and synthesizes findings into a single combined report.
    """

    def __init__(self, db: Session, client: Optional[anthropic.Anthropic] = None):
        self.db = db
        # Use provided client or shared singleton initialized with ANTHROPIC_API_KEY
        self.client = client or _SHARED_CLIENT
        self.specialists = create_specialist_registry(client=self.client)

    def get_specialist_registry_metadata(self) -> List[Dict[str, Any]]:
        """Returns metadata for all registered specialist subagents."""
        return [s.to_metadata() for s in self.specialists.values()]

    def route_query(
        self,
        query: str,
        grid_id: Optional[int] = None,
        force_specialists: Optional[List[str]] = None
    ) -> List[str]:
        """
        Determines which specialist subagents must be dispatched based on the query.
        """
        if force_specialists:
            return [k for k in force_specialists if k in self.specialists]

        clean_q = query.strip().lower()

        # 1. Slash command routing
        if clean_q.startswith("/check-pipeline") or clean_q.startswith("/network-health"):
            return ["data_pipeline"]
        if clean_q.startswith("/explain-grid"):
            return ["network_analysis", "ml_analysis", "data_pipeline"]
        if clean_q.startswith("/review-anomaly"):
            return ["ml_analysis", "network_analysis"]
        if clean_q.startswith("/test-api"):
            return ["api_agent"]

        # 2. Keyword-based specialist selection
        selected = set()

        pipeline_terms = ["pipeline", "etl", "ingest", "stale", "audit", "reject", "duplicate", "grain"]
        network_terms = ["traffic", "telemetry", "baseline", "surge", "hotspot", "sector", "activity", "cell", "grid"]
        ml_terms = ["model", "predict", "lightgbm", "probability", "classifier", "feature", "growth", "risk"]
        api_terms = ["api", "endpoint", "rest", "latency", "test-api", "benchmark", "http"]

        for t in pipeline_terms:
            if t in clean_q:
                selected.add("data_pipeline")
        for t in network_terms:
            if t in clean_q:
                selected.add("network_analysis")
        for t in ml_terms:
            if t in clean_q:
                selected.add("ml_analysis")
        for t in api_terms:
            if t in clean_q:
                selected.add("api_agent")

        # 3. If "all", "full", "comprehensive", or "system", invoke all specialists
        full_terms = ["all", "full", "comprehensive", "deep dive", "everything", "system overview", "fleet health"]
        if any(term in clean_q for term in full_terms):
            return ["data_pipeline", "network_analysis", "ml_analysis", "api_agent"]

        # 4. Default: If a target grid is known, dispatch core trio (Pipeline integrity + Network telemetry + ML inference)
        if not selected:
            if grid_id is not None:
                return ["data_pipeline", "network_analysis", "ml_analysis"]
            else:
                return ["data_pipeline", "network_analysis"]

        return list(selected)

    def investigate(
        self,
        user_message: str,
        grid_id: Optional[int] = None,
        grid_evidence: Optional[Dict[str, Any]] = None,
        chat_history: Optional[List[Dict[str, Any]]] = None,
        force_specialists: Optional[List[str]] = None
    ) -> Dict[str, Any]:
        """
        Executes the parent investigation workflow:
        1. Determines required specialist subagents.
        2. Dispatches tasks to each specialist using their restricted tools.
        3. Collects structured specialist findings.
        4. Synthesizes findings into ONE cohesive, combined NOC report.
        """
        clean_msg = user_message.strip()
        target_grid = grid_id or (grid_evidence.get("grid_id") if grid_evidence else 4365)

        # 1. Check if user ran a direct slash command with dedicated handler
        # For slash commands, we still execute specialists and wrap with supervisor report
        chosen_subagents = self.route_query(clean_msg, grid_id=target_grid, force_specialists=force_specialists)

        # 2. Execute each specialist subagent
        specialist_findings: Dict[str, SpecialistFinding] = {}
        for agent_key in chosen_subagents:
            specialist = self.specialists.get(agent_key)
            if specialist:
                try:
                    finding = specialist.investigate(
                        query=clean_msg,
                        db=self.db,
                        grid_id=target_grid,
                        evidence=grid_evidence,
                        client=self.client
                    )
                    specialist_findings[agent_key] = finding
                except Exception as e:
                    logger.error(f"Error executing specialist {agent_key}: {e}")
                    specialist_findings[agent_key] = SpecialistFinding(
                        agent_key=agent_key,
                        agent_name=specialist.name,
                        agent_role=specialist.role,
                        status="FAIL",
                        summary=f"Specialist encountered an execution error: {str(e)}",
                        metrics={"error": str(e)},
                        tools_called=[]
                    )

        # 3. Match relevant skills for documentation and telemetry
        matched_skills = match_skills_for_prompt(user_message)
        skills_used = [s["name"] for s in matched_skills]
        if not skills_used:
            skills_map = {
                "data_pipeline": "pipeline-troubleshooting",
                "network_analysis": "network-anomaly-analysis",
                "ml_analysis": "network-anomaly-analysis",
                "api_agent": "api-review"
            }
            for k in chosen_subagents:
                sk = skills_map.get(k)
                if sk and sk not in skills_used:
                    skills_used.append(sk)

        # 4. Synthesize ONE Combined Report
        combined_report = self._synthesize_combined_report(
            user_message=clean_msg,
            grid_id=target_grid,
            grid_evidence=grid_evidence,
            findings=specialist_findings,
            skills_used=skills_used
        )

        return {
            "reply": combined_report,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "subagents_called": chosen_subagents,
            "active_agent": "supervisor",
            "specialist_reports": {
                k: {
                    "name": f.agent_name,
                    "role": f.agent_role,
                    "status": f.status,
                    "summary": f.summary,
                    "metrics": f.metrics,
                    "tools_called": f.tools_called,
                    "finding_html": f.finding_html
                }
                for k, f in specialist_findings.items()
            },
            "skill_used": skills_used[0] if skills_used else None,
            "skills_used": skills_used
        }

    def _synthesize_combined_report(
        self,
        user_message: str,
        grid_id: Optional[int],
        grid_evidence: Optional[Dict[str, Any]],
        findings: Dict[str, SpecialistFinding],
        skills_used: List[str]
    ) -> str:
        """
        Combines and cross-correlates findings from all invoked specialists
        into a unified, authoritative NOC investigation document.
        """
        # Determine overall investigation severity
        statuses = [f.status for f in findings.values()]
        if "CRITICAL" in statuses or "FAIL" in statuses:
            overall_status = "CRITICAL"
            overall_color = "rose"
            verdict_badge = "CRITICAL ATTENTION REQUIRED"
        elif "ATTENTION" in statuses:
            overall_status = "ATTENTION"
            overall_color = "amber"
            verdict_badge = "ELEVATED ACTIVITY / DEGRADATION"
        else:
            overall_status = "HEALTHY"
            overall_color = "emerald"
            verdict_badge = "ALL SYSTEMS NOMINAL"

        # Build Cross-Correlation Insights
        cross_correlations = []

        has_pipe = "data_pipeline" in findings
        has_net = "network_analysis" in findings
        has_ml = "ml_analysis" in findings
        has_api = "api_agent" in findings

        if has_pipe and has_net:
            p_stat = findings["data_pipeline"].status
            if p_stat == "HEALTHY":
                cross_correlations.append(
                    "<strong>Data Trustworthiness:</strong> Ingestion pipeline is confirmed healthy with 0 duplicate grains, verifying that cell telemetry reflects true recorded activity."
                )
            else:
                cross_correlations.append(
                    "<strong>Data Trust Warning:</strong> Pipeline rejections or grain discrepancies detected. Treat instantaneous cell surges with caution until ingestion stabilizes."
                )

        if has_net and has_ml:
            net_metrics = findings["network_analysis"].metrics
            ml_metrics = findings["ml_analysis"].metrics
            surge_r = net_metrics.get("surge_ratio", 1.0)
            ml_prob = ml_metrics.get("anomaly_probability", 0.0)
            consensus = ml_metrics.get("consensus", "")

            if surge_r >= 1.5 and ml_prob >= 0.5:
                cross_correlations.append(
                    f"<strong>Telemetry & ML Convergence:</strong> 24h baseline multiple ({surge_r}x) strongly corroborates LightGBM high-activity probability ({(ml_prob*100):.1f}%). Both models confirm elevated demand."
                )
            elif surge_r >= 1.5 and ml_prob < 0.5:
                cross_correlations.append(
                    f"<strong>Model Divergence:</strong> Telemetry shows instantaneous spike ({surge_r}x), but LightGBM suppressed risk ({(ml_prob*100):.1f}%) due to regular recurring historical cycle."
                )
            else:
                cross_correlations.append(
                    f"<strong>Nominal Fleet Activity:</strong> Telemetry baseline ({surge_r}x) and LightGBM inference ({(ml_prob*100):.1f}%) both reflect nominal traffic load."
                )

        if has_api:
            api_metrics = findings["api_agent"].metrics
            failed_count = api_metrics.get("failed", 0)
            if failed_count == 0:
                cross_correlations.append(
                    f"<strong>API Layer Stability:</strong> All {api_metrics.get('total_endpoints_tested', 12)} platform endpoints validated with zero HTTP contract failures."
                )
            else:
                cross_correlations.append(
                    f"<strong>API Regression Alert:</strong> {failed_count} endpoints failed validation, indicating backend service degradation."
                )

        if not cross_correlations:
            cross_correlations.append("Specialist telemetry aggregated. No multi-tier discrepancies observed.")

        # Prescribed NOC Next Checks
        next_checks = [
            f"Monitor Cell #{grid_id} across the next hourly window for traffic stabilization.",
            "Verify adjacent lattice cells in the sector to determine if demand is localized or cluster-wide.",
            "Cross-reference modal distribution (Internet vs Voice/SMS) to isolate service driver."
        ]

        # Specialist findings HTML cards
        specialist_cards_html = "\n".join(f.finding_html for f in findings.values())

        # Subagent badges list
        agent_names_badges = " ".join([
            f'<span class="inline-flex items-center px-2 py-0.5 rounded text-[11px] font-mono font-medium bg-slate-800 text-cyan-300 border border-slate-700">{f.agent_name}</span>'
            for f in findings.values()
        ])

        report_html = f"""
<div class="noc-report space-y-4 font-sans text-slate-100">
  <!-- 1. Executive Operational Header -->
  <div class="rounded-xl border border-{overall_color}-500/40 bg-gradient-to-r from-{overall_color}-950/40 via-slate-900/60 to-slate-950 p-4 shadow-lg">
    <div class="flex flex-wrap items-center justify-between gap-2 border-b border-slate-800 pb-2 mb-3">
      <div class="flex items-center gap-2">
        <span class="flex h-2.5 w-2.5 rounded-full bg-{overall_color}-400 animate-pulse"></span>
        <h3 class="font-mono text-xs font-bold tracking-wider uppercase text-slate-200">
          SUPERVISOR INVESTIGATION REPORT
        </h3>
        <span class="font-mono text-[11px] px-2 py-0.5 rounded bg-slate-800 text-slate-300 border border-slate-700">
          Cell #{grid_id}
        </span>
      </div>
      <span class="px-2.5 py-1 rounded-md text-[11px] font-mono font-bold tracking-wider uppercase bg-{overall_color}-500/20 text-{overall_color}-300 border border-{overall_color}-500/30">
        {verdict_badge}
      </span>
    </div>
    
    <div class="text-xs text-slate-300 mb-2">
      <strong>Active Investigation Request:</strong> "{user_message}"
    </div>
    <div class="flex flex-wrap items-center gap-1.5 pt-1">
      <span class="text-[11px] text-slate-400 font-mono">Specialists Invoked:</span>
      {agent_names_badges}
    </div>
  </div>

  <!-- 2. Specialist Subagent Diagnostic Breakdown -->
  <div class="space-y-2.5">
    <div class="text-xs font-mono font-semibold uppercase tracking-wider text-slate-400 flex items-center gap-1.5">
      <span>⚡</span> Specialist Diagnostic Evidence
    </div>
    <div class="grid grid-cols-1 gap-2.5">
      {specialist_cards_html}
    </div>
  </div>

  <!-- 3. Cross-Correlated Insights -->
  <div class="rounded-lg border border-indigo-500/30 bg-indigo-500/10 p-3.5 space-y-2">
    <div class="text-xs font-mono font-bold text-indigo-300 uppercase tracking-wider flex items-center gap-1.5">
      <span>🔗</span> Cross-Correlated Intelligence
    </div>
    <ul class="text-xs text-slate-300 space-y-1.5 list-disc list-inside">
      {"".join(f"<li>{item}</li>" for item in cross_correlations)}
    </ul>
  </div>

  <!-- 4. Prescribed NOC Action Plan -->
  <div class="rounded-lg border border-slate-800 bg-slate-900/50 p-3.5 space-y-2">
    <div class="text-xs font-mono font-bold text-cyan-400 uppercase tracking-wider flex items-center gap-1.5">
      <span>🛡️</span> Prescribed NOC Next Steps
    </div>
    <ol class="text-xs text-slate-300 space-y-1.5 list-decimal list-inside font-sans">
      {"".join(f"<li>{step}</li>" for step in next_checks)}
    </ol>
  </div>
</div>
"""
        return report_html.strip()
