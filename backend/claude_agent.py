import os
import json
import logging
from typing import Dict, Any, List, Optional
from datetime import datetime, timezone
import pandas as pd
import anthropic
from dotenv import load_dotenv
from sqlalchemy.orm import Session
from sqlalchemy import func

from database import HourlyGridSummary, EnrichedSpatialHourly
from ml_model import get_predictor

# Load Claude API Key from .env
load_dotenv()
client = anthropic.Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))

logger = logging.getLogger(__name__)


def build_noc_system_prompt(
    target_grid_id: Optional[int] = None,
    evidence_data: Optional[Dict[str, Any]] = None,
    pipeline_info: Optional[Dict[str, Any]] = None,
    current_time_utc: Optional[str] = None
) -> str:
    """
    Dynamically builds the NOC AI Agent system prompt.
    Injects runtime operational context (pipeline status, target cell, operational clock)
    and instructs Claude with full autonomy over which HTML report sections to display.
    """
    timestamp_str = current_time_utc or datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
    
    # Resolve pipeline telemetry state
    pipeline_state_str = "Verified & Online"
    if pipeline_info:
        status_val = pipeline_info.get("status", "Online")
        trustworthy = pipeline_info.get("trustworthy", True)
        last_ingest = pipeline_info.get("last_ingestion", "Unknown")
        trust_badge = "TRUSTED" if trustworthy else "UNTRUSTED"
        pipeline_state_str = f"{status_val} ({trust_badge}) | Ingestion: {last_ingest}"
    
    # Resolve operational target context
    if target_grid_id is not None:
        target_context = f"- ACTIVE TARGET CELL: Grid #{target_grid_id}\n- OPERATIONAL FOCUS: Targeted Cell Diagnostics & Performance Anomaly Triage"
        if evidence_data:
            current_act = evidence_data.get("current_activity")
            baseline_act = evidence_data.get("baseline_activity")
            growth = evidence_data.get("activity_growth")
            peak_r = evidence_data.get("peak_ratio")
            anom_score = evidence_data.get("anomaly_score")
            direction = evidence_data.get("direction", "NORMAL")
            rules = evidence_data.get("rule_alerts", [])
            
            target_context += (
                f"\n- PRE-LOADED CONTEXT SNAPSHOT:\n"
                f"  * Current Activity: {current_act if current_act is not None else 'N/A'}\n"
                f"  * Baseline Activity: {baseline_act if baseline_act is not None else 'N/A'}\n"
                f"  * Activity Growth: {growth if growth is not None else 'N/A'}\n"
                f"  * Peak Ratio: {peak_r if peak_r is not None else 'N/A'}\n"
                f"  * ML Anomaly Score: {f'{anom_score*100:.1f}%' if isinstance(anom_score, (int, float)) else 'N/A'} ({direction})\n"
                f"  * Active Rule Alerts: {', '.join(rules) if rules else 'None'}"
            )
    else:
        target_context = "- ACTIVE TARGET: None (Global / Fleet-Wide)\n- OPERATIONAL FOCUS: Network-Wide Monitoring, Cross-Cell Triage & General NOC Inquiry"

    return f"""You are an expert AI assisting a Telecom Network Operations Centre (NOC).

=== RUNTIME OPERATIONAL CONTEXT ===
- SYSTEM CLOCK: {timestamp_str}
- DATA PIPELINE: {pipeline_state_str}
{target_context}

=== CRITICAL FORMATTING REQUIREMENTS ===
1. Format your entire response in clean, semantic, valid HTML elements ready for direct rendering in the web dashboard UI.
2. Wrap your response in an outer wrapper: <div class="noc-report space-y-3.5 font-sans"> ... </div>.
3. DO NOT wrap the output in markdown code blocks (do NOT use ```html or ```). Output raw HTML elements directly.
4. Ensure all HTML tags are strictly valid, balanced, and properly closed.
5. Use Tailwind CSS styling classes matching the dark NOC theme (slate/cyan/emerald/amber/rose/sky/violet).
6. Do NOT use Markdown formatting inside the HTML (use <strong> instead of **, <ul><li> instead of -, <code> instead of `).

=== DYNAMIC SECTION DISPLAY DIRECTIVE (MODEL AUTONOMY) ===
You have COMPLETE AUTONOMY to decide which sections to display and how to arrange them.
DO NOT rigidly force every section into every response.
Selectively choose ONLY the sections that directly address the user's inquiry, provide operational value, and have real supporting data.
Omit sections that are not relevant, redundant, or lack meaningful data (e.g., do NOT show empty telemetry cards with placeholder values, and omit recommended troubleshooting checks for normal operations or informational questions).

Modular Section Building Blocks (select and compose as appropriate):

1. SEVERITY / STATUS HEADER:
   - When to display: Assessing cell health, anomaly risks, incident triage, or when explicit severity categorization is needed.
   - When to omit: Conceptual questions, metric definitions, casual inquiries, or tool descriptions.
   - Structure:
     <div class="flex items-center justify-between border-b border-slate-800 pb-2.5">
       <div class="flex items-center gap-2">
         <span class="text-xs uppercase tracking-wider font-semibold text-slate-400">Severity:</span>
         <!-- Output ONE matching badge: -->
         <!-- NORMAL: <span class="px-2.5 py-0.5 rounded-full text-xs font-bold font-mono border border-emerald-500/30 bg-emerald-500/15 text-emerald-400">NORMAL</span> -->
         <!-- ATTENTION: <span class="px-2.5 py-0.5 rounded-full text-xs font-bold font-mono border border-amber-500/30 bg-amber-500/15 text-amber-400">ATTENTION</span> -->
         <!-- HIGH: <span class="px-2.5 py-0.5 rounded-full text-xs font-bold font-mono border border-rose-500/30 bg-rose-500/15 text-rose-400">HIGH</span> -->
         <!-- INFO: <span class="px-2.5 py-0.5 rounded-full text-xs font-bold font-mono border border-cyan-500/30 bg-cyan-500/15 text-cyan-400">INFO</span> -->
       </div>
       <div class="text-[11px] font-mono text-slate-500">
         Pipeline: Verified
       </div>
     </div>

2. EXECUTIVE SUMMARY / QUICK TAKEAWAY:
   - When to display: Providing a crisp 1-2 sentence high-level finding, quick status check, or shift handover takeaway.
   - Structure:
     <div class="rounded-lg border border-slate-800 bg-slate-900/50 p-3">
       <p class="text-xs text-slate-300 leading-relaxed m-0">[Concise high-level finding or status summary]</p>
     </div>

3. TELEMETRY EVIDENCE GRID:
   - When to display: When specific metrics, baselines, growth rates, peak ratios, or ML anomaly scores are pertinent.
   - Flexibility: Include ONLY metric cards that are relevant (e.g. 2, 3, 4, or 6 cards). Do not display empty or invented metrics.
   - Structure:
     <div class="rounded-lg border border-slate-800 bg-slate-900/50 p-3.5">
       <div class="text-xs font-semibold uppercase tracking-wider text-cyan-400 mb-2.5 flex items-center gap-1.5">
         <span>📊</span> Telemetry Evidence
       </div>
       <div class="grid grid-cols-2 gap-2 sm:grid-cols-3">
         <!-- Selectively include relevant cards: -->
         <div class="rounded border border-slate-800 bg-slate-950/60 p-2">
           <div class="text-[10px] uppercase font-mono text-slate-500">Current Activity</div>
           <div class="font-mono text-sm font-semibold text-cyan-300">[value]</div>
         </div>
         <div class="rounded border border-slate-800 bg-slate-950/60 p-2">
           <div class="text-[10px] uppercase font-mono text-slate-500">Baseline Activity</div>
           <div class="font-mono text-sm font-semibold text-slate-300">[value]</div>
         </div>
         <div class="rounded border border-slate-800 bg-slate-950/60 p-2">
           <div class="text-[10px] uppercase font-mono text-slate-500">Activity Growth</div>
           <div class="font-mono text-sm font-semibold text-slate-300">[value]</div>
         </div>
         <div class="rounded border border-slate-800 bg-slate-950/60 p-2">
           <div class="text-[10px] uppercase font-mono text-slate-500">Peak Ratio</div>
           <div class="font-mono text-sm font-semibold text-slate-300">[value]</div>
         </div>
         <div class="rounded border border-slate-800 bg-slate-950/60 p-2">
           <div class="text-[10px] uppercase font-mono text-slate-500">Anomaly Score</div>
           <div class="font-mono text-sm font-semibold text-amber-400">[value]%</div>
         </div>
         <div class="rounded border border-slate-800 bg-slate-950/60 p-2">
           <div class="text-[10px] uppercase font-mono text-slate-500">Rule Alerts</div>
           <div class="font-mono text-xs font-semibold text-amber-400">[rules or None]</div>
         </div>
       </div>
     </div>

4. OPERATIONAL INTERPRETATION & HYPOTHESES:
   - When to display: Diagnosing anomalies, explaining traffic dynamics, distinguishing transient spikes from baseline shifts, or evaluating root causes.
   - Structure:
     <div class="rounded-lg border border-slate-800 bg-slate-900/50 p-3.5">
       <div class="text-xs font-semibold uppercase tracking-wider text-cyan-400 mb-2 flex items-center gap-1.5">
         <span>🔍</span> Operational Interpretation
       </div>
       <div class="text-xs text-slate-300 leading-relaxed space-y-1.5">
         <p>[Operational diagnosis. Explicitly label inferences as hypotheses.]</p>
       </div>
     </div>

5. RECOMMENDED NEXT CHECKS / ACTION ITEMS:
   - When to display: Actionable remediation, field verification, neighbor cell checks, or threshold inspections are warranted (typically ATTENTION / HIGH severity, or when the user asks for triage steps).
   - When to omit: Normal network operations, purely informational queries, or simple definitions.
   - Structure:
     <div class="rounded-lg border border-slate-800 bg-slate-900/50 p-3.5">
       <div class="text-xs font-semibold uppercase tracking-wider text-cyan-400 mb-2 flex items-center gap-1.5">
         <span>🛠️</span> Recommended Next Checks
       </div>
       <ul class="list-disc list-inside text-xs text-slate-300 space-y-1">
         <li>[Specific actionable check 1]</li>
         <li>[Specific actionable check 2]</li>
       </ul>
     </div>

6. COMPARATIVE / DATA TABLE:
   - When to display: Comparing multiple cells, displaying hotspot rankings, or comparing time windows.
   - Structure:
     <div class="rounded-lg border border-slate-800 bg-slate-900/50 p-3.5 overflow-x-auto">
       <div class="text-xs font-semibold uppercase tracking-wider text-cyan-400 mb-2 flex items-center gap-1.5">
         <span>📋</span> Comparative Analysis
       </div>
       <table class="w-full text-xs font-mono text-left">
         <thead>
           <tr class="border-b border-slate-800 text-slate-400">
             <th class="py-1 px-2">Grid ID</th>
             <th class="py-1 px-2">Activity</th>
             <th class="py-1 px-2">Risk</th>
             <th class="py-1 px-2">Anomaly %</th>
           </tr>
         </thead>
         <tbody class="divide-y divide-slate-800/60">
           <!-- Rows -->
         </tbody>
       </table>
     </div>

7. DIAGNOSTIC ALERT / NOTICE BANNER:
   - When to display: Telemetry pipeline is unverified/stale, data is incomplete, or a tool returned an error or caveat.
   - Structure:
     <div class="rounded-lg border border-amber-500/30 bg-amber-500/10 p-3 text-xs font-mono text-amber-300 flex items-start gap-2">
       <span class="text-amber-400 font-bold">⚠️</span>
       <div><strong>Notice:</strong> [Description of caveat, missing data, or tool failure]</div>
     </div>

8. DIRECT EXPLANATORY / CONVERSATIONAL BLOCK:
   - When to display: Direct answers to questions, technical definitions (e.g. "What is peak ratio?"), formula explanations, or conversational dialogue.
   - Structure:
     <div class="rounded-lg border border-slate-800 bg-slate-900/50 p-3.5">
       <div class="text-xs font-semibold uppercase tracking-wider text-cyan-400 mb-1.5 flex items-center gap-1.5">
         <span>💡</span> [Topic or Header]
       </div>
       <div class="text-xs text-slate-300 leading-relaxed space-y-2">
         <p>[Clear, direct technical response]</p>
       </div>
     </div>

9. AUDIT TRAIL / TOOL CITATIONS:
   - When to display: Citing tools executed, pipeline status verification, or data provenance.
   - Structure:
     <div class="text-[10px] font-mono text-slate-500 flex items-center justify-between border-t border-slate-800/60 pt-2">
       <span>Data Pipeline: Verified via get_pipeline_status()</span>
       <span>Sources: [Tools called or Context Evidence]</span>
     </div>

=== DECISION HEURISTICS FOR COMMON SCENARIOS ===
- Full Triage / Anomaly Audit: Severity Header + (optional Summary) + Telemetry Grid (relevant cards) + Operational Interpretation + Recommended Checks + Audit Trail.
- Quick Cell Health Check: Severity Header + Executive Summary + (optional key metric cards).
- Conceptual / Metric Definition: Direct Explanatory Block (omit severity, blank telemetry, and next checks).
- Multi-Cell / Hotspot Comparison: Comparative Table + Operational Interpretation + (optional Next Checks).
- Follow-up Query: Address the user's specific question directly, choosing only the section(s) relevant to the follow-up.
- Missing Data / Tool Failure: Diagnostic Alert Banner + Operational Interpretation of what is missing.

=== NOC ENGINEERING RULES ===
- Only output valid HTML. Do not use Markdown inside HTML.
- These are telecom activity measures, not call counts, message counts, or Megabytes.
- Do NOT claim congestion; we have no capacity or utilization data.
- If evidence is insufficient to reach a conclusion or severity, state what additional data is needed.
- Never invent a number that is not in the evidence or tool results.
- ALWAYS call a tool for any factual network claim if data is not already provided in context.
- Before reporting a situation as fact, call get_pipeline_status() and note whether data is trustworthy.
- Cite which tool produced each figure in the audit trail.
- If a tool fails, say which one failed and what you therefore cannot conclude. Do not substitute an estimate."""


# Default NOC System Prompt for backwards compatibility
NOC_SYSTEM_PROMPT = build_noc_system_prompt()

# Define the tools available to Claude
NOC_TOOLS = [
    {
        "name": "get_pipeline_status",
        "description": "Check if the underlying data pipeline is trustworthy and up-to-date.",
        "input_schema": {"type": "object", "properties": {}}
    },
    {
        "name": "get_network_summary",
        "description": "Get high-level network health, total activity, and active grids.",
        "input_schema": {
            "type": "object",
            "properties": {"as_of": {"type": "string", "description": "ISO timestamp"}}
        }
    },
    {
        "name": "get_grid_activity",
        "description": "Fetch historical time-series activity data for a specific geographical grid.",
        "input_schema": {
            "type": "object",
            "properties": {
                "grid_id": {"type": "integer"},
                "as_of": {"type": "string", "description": "ISO timestamp"}
            },
            "required": ["grid_id"]
        }
    },
    {
        "name": "get_hotspots",
        "description": "Get a list of geographical grids experiencing the highest traffic.",
        "input_schema": {
            "type": "object",
            "properties": {
                "limit": {"type": "integer"},
                "severity": {"type": "string", "enum": ["NORMAL", "ATTENTION", "HIGH"]},
                "as_of": {"type": "string"}
            }
        }
    },
    {
        "name": "get_grid_features",
        "description": "Get ML engineered features (growth, variability, peak ratio) for a grid.",
        "input_schema": {
            "type": "object",
            "properties": {"grid_id": {"type": "integer"}},
            "required": ["grid_id"]
        }
    },
    {
        "name": "get_anomaly_score",
        "description": "Get the LightGBM probability score and prediction label for a grid.",
        "input_schema": {
            "type": "object",
            "properties": {
                "grid_id": {"type": "integer"},
                "as_of": {"type": "string"}
            },
            "required": ["grid_id"]
        }
    },
    {
        "name": "get_grid_location",
        "description": "Get the geographical coordinates (lat/lon) for a grid.",
        "input_schema": {
            "type": "object",
            "properties": {"grid_id": {"type": "integer"}},
            "required": ["grid_id"]
        }
    }
]

class ClaudeNOCAgent:
    def __init__(self, db: Session):
        self.model = "claude-haiku-4-5-20251001"
        self.db = db
        
    def _execute_tool(self, tool_name: str, tool_args: dict) -> dict:
        """Map tool calls from Claude to actual internal Python functions."""
        try:
            if tool_name == "get_pipeline_status":
                latest_record = self.db.query(func.max(HourlyGridSummary.loaded_at)).scalar()
                return {
                    "status": "Online", 
                    "trustworthy": True, 
                    "last_ingestion": latest_record.isoformat() if latest_record else "Unknown"
                }
                
            elif tool_name == "get_grid_activity":
                grid_id = tool_args["grid_id"]
                records = self.db.query(HourlyGridSummary).filter(HourlyGridSummary.grid_id == grid_id).order_by(HourlyGridSummary.date.desc(), HourlyGridSummary.hour.desc()).limit(24).all()
                if not records:
                    return {"error": "No activity found for this grid."}
                
                avg_baseline = sum(r.total_activity for r in records) / len(records)
                return {
                    "grid_id": grid_id, 
                    "current_activity": records[0].total_activity, 
                    "24h_baseline": avg_baseline
                }
                
            elif tool_name == "get_anomaly_score":
                grid_id = tool_args["grid_id"]
                try:
                    from routes import predict_grid_activity
                    pred = predict_grid_activity(grid_id=grid_id, db=self.db)
                    return {
                        "grid_id": grid_id,
                        "score": float(pred.probability),
                        "direction": pred.risk_label,
                        "threshold": pred.threshold
                    }
                except Exception as e:
                    logger.warning(f"predict_grid_activity fallback for grid {grid_id}: {e}")

                # Direct fallback with chronological sort and sufficient history
                records = self.db.query(HourlyGridSummary).filter(HourlyGridSummary.grid_id == grid_id).order_by(HourlyGridSummary.date.desc(), HourlyGridSummary.hour.desc()).limit(95).all()
                if not records:
                    return {"error": "Insufficient data to calculate anomaly score."}
                
                df = pd.DataFrame([{
                    "timestamp": pd.to_datetime(f"{r.date} {r.hour:02d}:00:00"),
                    "grid_id": r.grid_id,
                    "country_code": 0, # Default if missing
                    "sms_in_count": r.sms_in,
                    "sms_out_count": r.sms_out,
                    "call_in_count": r.call_in,
                    "call_out_count": r.call_out,
                    "internet_usage": r.internet_activity,
                    "total_sms": r.sms_in + r.sms_out,
                    "total_calls": r.call_in + r.call_out,
                    "total_activity": r.total_activity
                } for r in records]).sort_values("timestamp").reset_index(drop=True)
                
                predictor = get_predictor()
                pred_result = predictor.predict_latest(df)
                
                if pred_result:
                    return {
                        "grid_id": grid_id, 
                        "score": float(pred_result.get("probability", 0.0)), 
                        "direction": pred_result.get("risk_label", "NORMAL")
                    }
                return {"error": "Failed to calculate anomaly score."}

            elif tool_name == "get_grid_location":
                grid_id = tool_args["grid_id"]
                loc = self.db.query(EnrichedSpatialHourly.geometry).filter(EnrichedSpatialHourly.grid_id == grid_id).first()
                return {"grid_id": grid_id, "geometry": loc[0] if loc else "Unknown"}
            
            elif tool_name in ["get_network_summary", "get_hotspots", "get_grid_features"]:
                # Returning simplified summaries for tool limits
                return {"info": f"{tool_name} successfully executed but details are omitted in this basic DB implementation. Use standard evidence."}
                
            else:
                return {"error": f"Tool {tool_name} not implemented."}
        except Exception as e:
            logger.error(f"Tool {tool_name} failed: {str(e)}")
            return {"error": f"Tool failed: {str(e)}"}

    def build_system_prompt(self, target_grid_id: Optional[int] = None, evidence_data: Optional[Dict[str, Any]] = None) -> str:
        """Constructs a dynamic system prompt incorporating current DB pipeline status and target context."""
        pipeline_info = {"status": "Online", "trustworthy": True, "last_ingestion": "Unknown"}
        try:
            latest_record = self.db.query(func.max(HourlyGridSummary.loaded_at)).scalar()
            if latest_record:
                pipeline_info["last_ingestion"] = latest_record.isoformat()
        except Exception as e:
            logger.warning(f"Could not query pipeline status for prompt: {e}")
            
        return build_noc_system_prompt(
            target_grid_id=target_grid_id,
            evidence_data=evidence_data,
            pipeline_info=pipeline_info
        )

    def chat(
        self,
        user_message: str,
        chat_history: List[Dict] = None,
        context_evidence: str = "",
        grid_id: Optional[int] = None,
        grid_evidence: Optional[Dict[str, Any]] = None
    ) -> str:
        """Main chat loop handling dynamic prompt generation and multi-turn tool calling."""
        messages = chat_history or []
        
        # Parse evidence context if provided as string and grid_evidence not yet set
        parsed_evidence = grid_evidence
        if not parsed_evidence and context_evidence:
            try:
                parsed_evidence = json.loads(context_evidence)
            except Exception:
                parsed_evidence = None

        # Determine target grid_id if not explicitly provided
        target_grid = grid_id
        if target_grid is None and parsed_evidence and isinstance(parsed_evidence, dict) and "grid_id" in parsed_evidence:
            target_grid = parsed_evidence["grid_id"]

        # Build dynamic system prompt based on active runtime context
        dynamic_system_prompt = self.build_system_prompt(target_grid_id=target_grid, evidence_data=parsed_evidence)

        # Inject the current grid evidence if provided
        if context_evidence:
            user_message = f"Evidence Context:\n{context_evidence}\n\nUser Query: {user_message}"
            
        messages.append({"role": "user", "content": user_message})

        while True:
            response = client.messages.create(
                model=self.model,
                max_tokens=2048,
                system=dynamic_system_prompt,
                tools=NOC_TOOLS,
                messages=messages
            )

            if response.stop_reason == "tool_use":
                messages.append({"role": "assistant", "content": response.content})
                
                # Execute all tools Claude requested
                for block in response.content:
                    if block.type == "tool_use":
                        tool_result = self._execute_tool(block.name, block.input)
                        messages.append({
                            "role": "user",
                            "content": [{
                                "type": "tool_result",
                                "tool_use_id": block.id,
                                "content": json.dumps(tool_result)
                            }]
                        })
            else:
                # Agent provided final response
                text_parts = [block.text for block in response.content if hasattr(block, "text") and block.text]
                return "\n".join(text_parts) if text_parts else ""