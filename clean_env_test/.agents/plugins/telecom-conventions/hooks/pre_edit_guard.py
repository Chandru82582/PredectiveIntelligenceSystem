"""
PreToolUse Hook: Airflow & Pipeline Configuration Guard.

Enforces Requirement 2:
Before any edit to airflow/ or pipeline configuration, require an explicit confirmation.
Logs every hook outcome persistently to hooks.log.
"""

import os
import sys
import json
from pathlib import Path

# Add hook dir to sys.path
_HOOKS_DIR = Path(__file__).resolve().parent
if str(_HOOKS_DIR) not in sys.path:
    sys.path.insert(0, str(_HOOKS_DIR))

from common import log_hook_outcome

# Patterns identifying airflow or pipeline configuration
PIPELINE_GUARD_PATTERNS = [
    "airflow",
    "dag",
    "pipeline",
    "sql_ingestion",
    "telecom_pipeline",
    "ingestion_dag",
]


def is_airflow_or_pipeline_config(filepath: str) -> bool:
    """Returns True if target filepath matches airflow or pipeline configuration."""
    if not filepath:
        return False
    norm = filepath.replace("\\", "/").lower()
    return any(pattern in norm for pattern in PIPELINE_GUARD_PATTERNS)


def handle_pre_tool_use(payload: dict) -> dict:
    tool_call = payload.get("toolCall", {})
    tool_name = tool_call.get("name", "")
    args = tool_call.get("args", {})
    target_file = (
        args.get("TargetFile")
        or args.get("targetFile")
        or args.get("file")
        or args.get("path")
        or ""
    )

    if is_airflow_or_pipeline_config(target_file):
        decision = "force_ask"
        reason = (
            f"Explicit confirmation required: Target '{target_file}' is an Airflow DAG or "
            f"core pipeline configuration file. Operator sign-off is required before editing."
        )
        log_hook_outcome(
            hook_name="airflow-pipeline-guard",
            event_type="PreToolUse",
            target_file=target_file,
            decision=decision,
            details=f"Blocked automatic edit; prompted operator for explicit confirmation. Tool: {tool_name}",
            extra={"tool_name": tool_name},
        )
        return {
            "decision": decision,
            "reason": reason,
        }
    else:
        decision = "allow"
        log_hook_outcome(
            hook_name="airflow-pipeline-guard",
            event_type="PreToolUse",
            target_file=target_file,
            decision=decision,
            details=f"File outside protected pipeline configuration scope; edit allowed. Tool: {tool_name}",
            extra={"tool_name": tool_name},
        )
        return {
            "decision": decision,
        }


def main():
    # Support direct CLI invocation for testing and verification
    if len(sys.argv) > 1 and sys.argv[1] in ("--file", "-f"):
        test_file = sys.argv[2] if len(sys.argv) > 2 else "flow/airflow_home/dags/ingestion_dag.py"
        test_payload = {
            "toolCall": {
                "name": "replace_file_content",
                "args": {"TargetFile": test_file},
            },
            "stepIdx": 1,
        }
        res = handle_pre_tool_use(test_payload)
        print(json.dumps(res, indent=2))
        return

    # Standard stdin execution mode via Antigravity hook engine
    try:
        raw_input = sys.stdin.read()
        payload = json.loads(raw_input) if raw_input.strip() else {}
    except Exception as e:
        payload = {}

    response = handle_pre_tool_use(payload)
    print(json.dumps(response))


if __name__ == "__main__":
    main()
