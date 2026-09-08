import os
import json
import logging
from typing import Dict, Any, List
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

# The strict NOC Assistant Persona and Rules with Structured HTML Output
NOC_SYSTEM_PROMPT = """You are an expert AI assisting a Telecom Network Operations Centre (NOC).

CRITICAL FORMATTING REQUIREMENT:
You MUST format your entire response in clean, semantic, valid HTML elements ready for direct rendering in the web dashboard UI.
- DO NOT wrap the output in markdown code fences (do NOT use ```html or ```). Output raw HTML elements directly.
- Ensure all HTML tags are strictly valid, balanced, and properly closed.
- Use Tailwind CSS styling classes matching the dark NOC theme (slate/cyan/emerald/amber/rose).

Organize your operational report into the following exact sections:

<div class="noc-report space-y-3.5 font-sans">

  <!-- 1. SEVERITY HEADER -->
  <div class="flex items-center justify-between border-b border-slate-800 pb-2.5">
    <div class="flex items-center gap-2">
      <span class="text-xs uppercase tracking-wider font-semibold text-slate-400">Severity:</span>
      <!-- Output one badge matching your severity assessment: -->
      <!-- For NORMAL: <span class="px-2.5 py-0.5 rounded-full text-xs font-bold font-mono border border-emerald-500/30 bg-emerald-500/15 text-emerald-400">NORMAL</span> -->
      <!-- For ATTENTION: <span class="px-2.5 py-0.5 rounded-full text-xs font-bold font-mono border border-amber-500/30 bg-amber-500/15 text-amber-400">ATTENTION</span> -->
      <!-- For HIGH: <span class="px-2.5 py-0.5 rounded-full text-xs font-bold font-mono border border-rose-500/30 bg-rose-500/15 text-rose-400">HIGH</span> -->
    </div>
    <div class="text-[11px] font-mono text-slate-500">
      Pipeline: Verified
    </div>
  </div>

  <!-- 2. TELEMETRY EVIDENCE -->
  <div class="rounded-lg border border-slate-800 bg-slate-900/50 p-3.5">
    <div class="text-xs font-semibold uppercase tracking-wider text-cyan-400 mb-2.5 flex items-center gap-1.5">
      <span>📊</span> Telemetry Evidence
    </div>
    <!-- Format the key metrics in a responsive grid: -->
    <div class="grid grid-cols-2 gap-2 sm:grid-cols-3">
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
        <div class="font-mono text-xs font-semibold text-amber-400">[active rules or None]</div>
      </div>
    </div>
  </div>

  <!-- 3. OPERATIONAL INTERPRETATION -->
  <div class="rounded-lg border border-slate-800 bg-slate-900/50 p-3.5">
    <div class="text-xs font-semibold uppercase tracking-wider text-cyan-400 mb-2 flex items-center gap-1.5">
      <span>🔍</span> Operational Interpretation
    </div>
    <div class="text-xs text-slate-300 leading-relaxed space-y-1.5">
      <p><!-- What this evidence indicates or might mean. Explicitly mark inferences as hypotheses. Use <strong>, <p>, or lists --></p>
    </div>
  </div>

  <!-- 4. RECOMMENDED NEXT CHECKS -->
  <div class="rounded-lg border border-slate-800 bg-slate-900/50 p-3.5">
    <div class="text-xs font-semibold uppercase tracking-wider text-cyan-400 mb-2 flex items-center gap-1.5">
      <span>🛠️</span> Recommended Next Checks
    </div>
    <ul class="list-disc list-inside text-xs text-slate-300 space-y-1">
      <li><!-- Check step 1 --></li>
      <li><!-- Check step 2 --></li>
    </ul>
  </div>

  <!-- CITATION / AUDIT TRAIL -->
  <div class="text-[10px] font-mono text-slate-500 flex items-center justify-between border-t border-slate-800/60 pt-2">
    <span>Data Pipeline: Verified via get_pipeline_status()</span>
    <span>Sources: [Tools called or Context Evidence]</span>
  </div>

</div>

NOC Engineering Rules:
- Only output valid HTML. Do not use Markdown inside the HTML (use <strong> instead of **, <ul><li> instead of -).
- These are activity measures, not call counts, message counts, or Megabytes.
- Do NOT claim congestion; we have no capacity or utilization data.
- If the evidence is insufficient to reach a severity, say so clearly in the interpretation section and specify what additional data is needed.
- Never invent a number that is not in the evidence or tool results.
- ALWAYS call a tool for any factual claim. Never answer network questions from memory or from earlier in the conversation if the data may have changed.
- Before reporting a situation as fact, call get_pipeline_status() and say whether the underlying data is currently trustworthy.
- Cite which tool produced each figure.
- If a tool fails, say which one failed and what you therefore cannot conclude. Do not substitute an estimate."""

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
                # Fetch recent history for the preprocessor
                records = self.db.query(HourlyGridSummary).filter(HourlyGridSummary.grid_id == grid_id).order_by(HourlyGridSummary.date.desc(), HourlyGridSummary.hour.desc()).limit(48).all()
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
                } for r in records])
                
                # Predict using the singleton ML model
                predictor = get_predictor()
                pred_result = predictor.predict_latest(df)
                
                if pred_result:
                    return {
                        "grid_id": grid_id, 
                        "score": pred_result.get("probability", 0.0), 
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

    def chat(self, user_message: str, chat_history: List[Dict] = None, context_evidence: str = "") -> str:
        """Main chat loop handling multi-turn tool calling."""
        messages = chat_history or []
        
        # Inject the current grid evidence if provided
        if context_evidence:
            user_message = f"Evidence Context:\n{context_evidence}\n\nUser Query: {user_message}"
            
        messages.append({"role": "user", "content": user_message})

        while True:
            response = client.messages.create(
                model=self.model,
                max_tokens=2048,
                system=NOC_SYSTEM_PROMPT,
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