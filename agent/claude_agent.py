import os
import json
import logging
from typing import Dict, Any, List, Optional
from datetime import datetime, timezone
import anthropic
from dotenv import load_dotenv
from sqlalchemy.orm import Session
from sqlalchemy import func
import sys
from pathlib import Path

_THIS_DIR = Path(__file__).resolve().parent
_ROOT = _THIS_DIR.parent if _THIS_DIR.name == "agent" else _THIS_DIR
_BACKEND = _ROOT / "backend"
_ML = _ROOT / "ml"

for _p in [str(_ROOT), str(_BACKEND), str(_ML), str(_THIS_DIR)]:
    if _p not in sys.path:
        sys.path.insert(0, _p)

from database import HourlyGridSummary
from agent.prompts import build_noc_system_prompt
from agent.tools import NOC_TOOLS, execute_tool
from agent.slash_commands import is_slash_command, handle_slash_command

# Load Claude API Key from .env
load_dotenv()
_API_KEY = os.getenv("ANTHROPIC_API_KEY")
client = anthropic.Anthropic(api_key=_API_KEY) if _API_KEY else None

logger = logging.getLogger(__name__)


SLASH_COMMAND_TO_SKILL = {
    "/check-pipeline": "pipeline-troubleshooting",
    "/explain-grid": "network-anomaly-analysis",
    "/review-anomaly": "network-anomaly-analysis",
    "/network-health": "telecom-data-quality",
    "/test-api": "api-review"
}


class ClaudeNOCAgent:
    """
    Autonomous NOC AI Agent.
    Supports both direct project slash command execution and multi-turn Claude tool calling.
    """
    def __init__(self, db: Session):
        self.model = "claude-haiku-4-5-20251001"
        self.db = db
        from agent.supervisor import SupervisorAgent
        self.supervisor = SupervisorAgent(db=self.db, client=client)

    def _execute_tool(self, tool_name: str, tool_args: dict) -> dict:
        """Execute a tool call using the modular tools engine."""
        return execute_tool(tool_name, tool_args, self.db)

    def build_system_prompt(
        self,
        target_grid_id: Optional[int] = None,
        evidence_data: Optional[Dict[str, Any]] = None,
        user_message: Optional[str] = None
    ) -> str:
        """Constructs a dynamic system prompt incorporating current DB pipeline status, target context, and matched skills."""
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
            pipeline_info=pipeline_info,
            user_message=user_message
        )

    def chat(
        self,
        user_message: str,
        chat_history: List[Dict] = None,
        context_evidence: str = "",
        grid_id: Optional[int] = None,
        grid_evidence: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        Main chat loop handling:
        1. Direct fast dispatch of project slash commands (/check-pipeline, /explain-grid, etc.) with subagent tracking.
        2. Parent supervisor investigation task coordinating the 4 specialist subagents and synthesizing findings.
        Returns a dict with 'reply', 'skill_used', 'skills_used', 'subagents_called', 'active_agent', and 'specialist_reports'.
        """
        messages = chat_history or []

        # Parse evidence context if provided as string and grid_evidence not yet set
        parsed_evidence = grid_evidence
        if not parsed_evidence and context_evidence:
            try:
                parsed_evidence = json.loads(context_evidence)
            except Exception:
                parsed_evidence = None

        target_grid = grid_id
        if target_grid is None and parsed_evidence and isinstance(parsed_evidence, dict) and "grid_id" in parsed_evidence:
            target_grid = parsed_evidence["grid_id"]

        clean_msg = user_message.strip()

        # Check if the user message is a project slash command
        if is_slash_command(clean_msg):
            cmd_key = clean_msg.split()[0].lower()
            cmd_skill = SLASH_COMMAND_TO_SKILL.get(cmd_key)
            slash_result = handle_slash_command(
                clean_msg,
                db=self.db,
                active_grid_id=target_grid,
                context_evidence=parsed_evidence
            )
            if slash_result:
                subagent_map = {
                    "/check-pipeline": ["data_pipeline"],
                    "/network-health": ["data_pipeline"],
                    "/explain-grid": ["network_analysis", "ml_analysis", "data_pipeline"],
                    "/review-anomaly": ["ml_analysis", "network_analysis"],
                    "/test-api": ["api_agent"]
                }
                subagents_called = subagent_map.get(cmd_key, ["data_pipeline", "network_analysis"])
                return {
                    "reply": slash_result,
                    "skill_used": cmd_skill,
                    "skills_used": [cmd_skill] if cmd_skill else [],
                    "subagents_called": subagents_called,
                    "active_agent": "supervisor"
                }

        # For general queries, execute the parent Supervisor investigation task across specialist subagents
        return self.supervisor.investigate(
            user_message=clean_msg,
            grid_id=target_grid,
            grid_evidence=parsed_evidence,
            chat_history=chat_history
        )

        dynamic_system_prompt = self.build_system_prompt(
            target_grid_id=target_grid,
            evidence_data=parsed_evidence,
            user_message=user_message
        )

        # Inject context evidence into prompt if provided
        llm_user_message = user_message
        if context_evidence:
            llm_user_message = f"Evidence Context:\n{context_evidence}\n\nUser Query: {user_message}"

        messages.append({"role": "user", "content": llm_user_message})

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
                        if block.name == "read_skill_runbook" and isinstance(block.input, dict):
                            s_name = block.input.get("skill_name")
                            if s_name and s_name not in active_skills:
                                active_skills.append(s_name)

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
                text_parts = [block.text for block in response.content if hasattr(block, "text") and block.text]
                final_text = "\n".join(text_parts) if text_parts else ""
                unique_skills = list(dict.fromkeys(active_skills))
                return {
                    "reply": final_text,
                    "skill_used": unique_skills[0] if unique_skills else None,
                    "skills_used": unique_skills
                }
