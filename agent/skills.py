import os
import re
import logging
from pathlib import Path
from typing import Dict, Any, List, Optional

logger = logging.getLogger(__name__)

_THIS_DIR = Path(__file__).resolve().parent
_ROOT = _THIS_DIR.parent if _THIS_DIR.name == "agent" else _THIS_DIR
_SKILLS_DIR = _THIS_DIR / "runbooks"
if not _SKILLS_DIR.exists():
    _SKILLS_DIR = _ROOT / ".agents" / "skills"



def _parse_skill_file(skill_path: Path) -> Optional[Dict[str, Any]]:
    """Parses a SKILL.md file with YAML frontmatter."""
    try:
        content = skill_path.read_text(encoding="utf-8")
        match = re.match(r"^---\s*\n(.*?)\n---\s*\n(.*)$", content, re.DOTALL)
        if not match:
            return None
        
        frontmatter_raw, body = match.groups()
        meta = {}
        for line in frontmatter_raw.split("\n"):
            if ":" in line:
                key, val = line.split(":", 1)
                meta[key.strip()] = val.strip().strip(">-\n ")

        name = meta.get("name", skill_path.parent.name)
        description = meta.get("description", "")

        return {
            "name": name,
            "description": description,
            "path": str(skill_path),
            "body": body.strip(),
            "raw": content
        }
    except Exception as e:
        logger.warning(f"Error parsing skill at {skill_path}: {e}")
        return None


def get_all_skills() -> Dict[str, Dict[str, Any]]:
    """Discovers and parses all skills in .agents/skills/."""
    skills = {}
    if not _SKILLS_DIR.exists():
        return skills

    for child in _SKILLS_DIR.iterdir():
        if child.is_dir():
            skill_md = child / "SKILL.md"
            if skill_md.exists():
                parsed = _parse_skill_file(skill_md)
                if parsed:
                    skills[parsed["name"]] = parsed
    return skills


def get_skill_content(skill_name: str) -> Optional[str]:
    """Returns the full instructions body of a specific skill."""
    skills = get_all_skills()
    if skill_name in skills:
        return skills[skill_name]["body"]
    return None


def match_skills_for_prompt(user_message: str) -> List[Dict[str, Any]]:
    """
    Identifies relevant skills based on user message keywords and intent.
    Returns matched skills to inject their specialized runbooks into the context.
    """
    msg_lower = user_message.lower()
    skills = get_all_skills()
    matched = []

    # Matching triggers
    triggers = {
        "network-anomaly-analysis": [
            "flagged", "anomaly", "score", "unusual", "spike", "drop",
            "explain-grid", "review-anomaly", "congestion", "why is cell", "why is grid", "severity"
        ],
        "pipeline-troubleshooting": [
            "pipeline", "ingestion", "stale", "freshness", "audit_log",
            "check-pipeline", "sync", "rejected", "etl"
        ],
        "telecom-data-quality": [
            "duplicate", "grain", "network-health", "data quality", "geojson",
            "null", "invariants", "hourly_grid_summary"
        ],
        "api-review": [
            "test-api", "api test", "latency", "status_code", "test suite", "endpoints"
        ]
    }

    for skill_name, keywords in triggers.items():
        if skill_name in skills:
            if any(kw in msg_lower for kw in keywords):
                matched.append(skills[skill_name])

    return matched
