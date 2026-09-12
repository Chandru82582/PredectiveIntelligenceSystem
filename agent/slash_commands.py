import re
import html
from typing import Optional, Dict, Any, Tuple
from sqlalchemy.orm import Session

from agent.tools import execute_tool

SLASH_COMMAND_DEFINITIONS = [
    {
        "command": "/check-pipeline",
        "syntax": "/check-pipeline",
        "description": "Call GET /pipeline/status and summarize health, naming any rejected rows or staleness",
        "requires_grid": False
    },
    {
        "command": "/explain-grid",
        "syntax": "/explain-grid [grid_id]",
        "description": "Produce 4-section report (SEVERITY / EVIDENCE / INTERPRETATION / NEXT CHECKS)",
        "requires_grid": True
    },
    {
        "command": "/review-anomaly",
        "syntax": "/review-anomaly [grid_id]",
        "description": "Compare rule alert, classifier output & anomaly score and explain any disagreement",
        "requires_grid": True
    },
    {
        "command": "/test-api",
        "syntax": "/test-api",
        "description": "Run the API test suite and summarize failures",
        "requires_grid": False
    },
    {
        "command": "/network-health",
        "syntax": "/network-health",
        "description": "Run grain duplicate check on hourly_grid_summary and report pass or fail",
        "requires_grid": False
    }
]


def is_slash_command(message: str) -> bool:
    """Returns True if the message starts with a slash command."""
    if not message:
        return False
    trimmed = message.strip()
    return trimmed.startswith("/")


def parse_slash_command(message: str) -> Tuple[str, Optional[int]]:
    """
    Parses a slash command and optional integer grid_id argument.
    e.g. '/explain-grid 4365' -> ('/explain-grid', 4365)
    e.g. '/check-pipeline' -> ('/check-pipeline', None)
    """
    parts = message.strip().split()
    cmd = parts[0].lower() if parts else ""
    grid_id = None
    if len(parts) > 1:
        # Check if second part is a grid number
        m = re.search(r"\d+", parts[1])
        if m:
            try:
                grid_id = int(m.group(0))
            except ValueError:
                grid_id = None
    return cmd, grid_id


def handle_slash_command(
    message: str,
    db: Session,
    active_grid_id: Optional[int] = None,
    context_evidence: Optional[Dict[str, Any]] = None
) -> Optional[str]:
    """
    Dispatches a project slash command to its dedicated executor and returns
    a richly formatted HTML response adhering to the dark NOC dashboard design system.
    """
    cmd, parsed_grid = parse_slash_command(message)
    target_grid = parsed_grid or active_grid_id or 4365

    if cmd == "/check-pipeline":
        return execute_check_pipeline(db)
    elif cmd == "/explain-grid":
        return execute_explain_grid(target_grid, db, context_evidence)
    elif cmd == "/review-anomaly":
        return execute_review_anomaly(target_grid, db)
    elif cmd == "/test-api":
        return execute_test_api(db)
    elif cmd == "/network-health":
        return execute_network_health(db)
    return None


# ---------------------------------------------------------------------------
# Command 1: /check-pipeline
# ---------------------------------------------------------------------------
def execute_check_pipeline(db: Session) -> str:
    res = execute_tool("get_pipeline_status", {}, db)
    status = res.get("status", "UNKNOWN")
    trustworthy = res.get("trustworthy", False)
    last_ingest = res.get("last_ingestion", "Unknown")
    total_runs = res.get("total_runs", 0)
    accepted_count = res.get("accepted_count", 0)
    rejected_count = res.get("rejected_count", 0)
    staleness_summary = res.get("staleness_summary", "Nominal")
    rejected_rows = res.get("rejected_rows", [])

    if status == "HEALTHY":
        badge = '<span class="px-2.5 py-0.5 rounded-full text-xs font-bold font-mono border border-emerald-500/30 bg-emerald-500/15 text-emerald-400">HEALTHY</span>'
    elif status == "DEGRADED":
        badge = '<span class="px-2.5 py-0.5 rounded-full text-xs font-bold font-mono border border-amber-500/30 bg-amber-500/15 text-amber-400">DEGRADED</span>'
    else:
        badge = '<span class="px-2.5 py-0.5 rounded-full text-xs font-bold font-mono border border-rose-500/30 bg-rose-500/15 text-rose-400">STALE / UNTRUSTED</span>'

    rejected_html = ""
    if rejected_rows:
        rows_items = []
        for r in rejected_rows:
            fname = html.escape(r.get("filename", "unknown"))
            ts = html.escape(r.get("processed_at", ""))
            reason = html.escape(r.get("reason", "Unknown error"))
            rows_items.append(f"""
              <li class="border-b border-slate-800/80 pb-2 last:border-0 last:pb-0">
                <div class="flex items-center justify-between text-[11px] font-mono mb-1">
                  <span class="text-rose-400 font-semibold">{fname}</span>
                  <span class="text-slate-500">{ts}</span>
                </div>
                <div class="text-[11px] font-mono text-slate-400 leading-normal pl-2 border-l-2 border-rose-500/40">{reason}</div>
              </li>
            """)
        rejected_html = f"""
        <div class="rounded-lg border border-rose-500/30 bg-rose-950/20 p-3.5 space-y-2">
          <div class="text-xs font-semibold uppercase tracking-wider text-rose-400 flex items-center gap-1.5">
            <span>⚠️</span> Rejected Ingestion Rows ({len(rejected_rows)} recent instances)
          </div>
          <ul class="space-y-2 list-none p-0 m-0">
            {''.join(rows_items)}
          </ul>
        </div>
        """
    else:
        rejected_html = """
        <div class="rounded-lg border border-slate-800 bg-slate-900/50 p-3 text-xs text-slate-400 flex items-center gap-2 font-mono">
          <span class="text-emerald-400">✓</span> No rejected ingestion files recorded in recent audit trail.
        </div>
        """

    return f"""<div class="noc-report space-y-3.5 font-sans">
  <div class="flex items-center justify-between border-b border-slate-800 pb-2.5">
    <div class="flex items-center gap-2">
      <span class="text-xs uppercase tracking-wider font-semibold text-slate-400">Pipeline Status:</span>
      {badge}
      <span class="text-[11px] font-mono text-slate-500">({'Trustworthy' if trustworthy else 'Audit Required'})</span>
    </div>
    <div class="text-[11px] font-mono text-cyan-400">GET /pipeline/status</div>
  </div>

  <div class="rounded-lg border border-slate-800 bg-slate-900/50 p-3.5">
    <div class="text-xs font-semibold uppercase tracking-wider text-cyan-400 mb-2.5 flex items-center gap-1.5">
      <span>📊</span> Ingestion Telemetry & Staleness
    </div>
    <div class="grid grid-cols-2 gap-2 sm:grid-cols-4">
      <div class="rounded border border-slate-800 bg-slate-950/60 p-2">
        <div class="text-[10px] uppercase font-mono text-slate-500">Last Ingest</div>
        <div class="font-mono text-xs font-semibold text-slate-300 truncate" title="{last_ingest}">{last_ingest[:19] if len(last_ingest)>=19 else last_ingest}</div>
      </div>
      <div class="rounded border border-slate-800 bg-slate-950/60 p-2">
        <div class="text-[10px] uppercase font-mono text-slate-500">Staleness</div>
        <div class="font-mono text-xs font-semibold text-emerald-400">{'Up to Date' if not res.get('is_stale') else 'Stale'}</div>
      </div>
      <div class="rounded border border-slate-800 bg-slate-950/60 p-2">
        <div class="text-[10px] uppercase font-mono text-slate-500">Accepted Files</div>
        <div class="font-mono text-xs font-semibold text-emerald-400">{accepted_count} / {total_runs}</div>
      </div>
      <div class="rounded border border-slate-800 bg-slate-950/60 p-2">
        <div class="text-[10px] uppercase font-mono text-slate-500">Rejected Files</div>
        <div class="font-mono text-xs font-semibold { 'text-rose-400' if rejected_count > 0 else 'text-slate-400' }">{rejected_count}</div>
      </div>
    </div>
    <div class="mt-2.5 text-[11px] font-mono text-slate-400">
      <strong>Ingestion Note:</strong> {staleness_summary}
    </div>
  </div>

  {rejected_html}

  <div class="text-[10px] font-mono text-slate-500 flex items-center justify-between border-t border-slate-800/60 pt-2">
    <span>Data Pipeline: Verified via get_pipeline_status()</span>
    <span>Source: flow/logs/audit_log.json + DB loaded_at</span>
  </div>
</div>"""


# ---------------------------------------------------------------------------
# Command 2: /explain-grid [grid_id]
# ---------------------------------------------------------------------------
def execute_explain_grid(grid_id: int, db: Session, context_evidence: Optional[Dict[str, Any]] = None) -> str:
    act = execute_tool("get_grid_activity", {"grid_id": grid_id}, db)
    feat = execute_tool("get_grid_features", {"grid_id": grid_id}, db)
    anom = execute_tool("get_anomaly_score", {"grid_id": grid_id}, db)
    loc = execute_tool("get_grid_location", {"grid_id": grid_id}, db)

    curr_act = act.get("current_activity", 0.0)
    baseline_act = act.get("24h_baseline", feat.get("baseline", 0.0))
    growth = feat.get("activity_growth", 0.0)
    peak_ratio = feat.get("peak_ratio", 1.0)
    score = anom.get("score", 0.0)
    risk_label = anom.get("direction", "NORMAL")
    sector = loc.get("sector", "Milan Metropolitan")
    lat = loc.get("latitude", "45.46")
    lon = loc.get("longitude", "9.19")

    # Determine Severity Badge
    if score >= 0.70 or risk_label == "HIGH_ACTIVITY_RISK":
        severity_badge = '<span class="px-2.5 py-0.5 rounded-full text-xs font-bold font-mono border border-rose-500/30 bg-rose-500/15 text-rose-400">HIGH</span>'
        severity_color = "rose"
    elif score >= 0.40 or growth > 0.30:
        severity_badge = '<span class="px-2.5 py-0.5 rounded-full text-xs font-bold font-mono border border-amber-500/30 bg-amber-500/15 text-amber-400">ATTENTION</span>'
        severity_color = "amber"
    else:
        severity_badge = '<span class="px-2.5 py-0.5 rounded-full text-xs font-bold font-mono border border-emerald-500/30 bg-emerald-500/15 text-emerald-400">NORMAL</span>'
        severity_color = "emerald"

    # Section 3: Interpretation
    if score >= 0.50:
        interp = (
            f"Cell #{grid_id} exhibits an elevated next-hour activity surge probability ({score*100:.1f}%) with an activity growth rate "
            f"of {growth:+.1%}. Current activity ({curr_act:.1f}) is tracking at {peak_ratio:.2f}x its within-day baseline ({baseline_act:.1f}). "
            f"This profile is characteristic of an active temporal cluster in the {sector} sector. "
            f"<strong>Note:</strong> Measures reflect proportional activity units, not physical link congestion or call drops."
        )
        checks = [
            f"Cross-reference telemetry with adjacent cells in sector {sector} to check for localized geographic cluster.",
            "Verify whether current demand aligns with weekly diurnal peak hours (see weekly peak dial).",
            "Monitor next rolling 1-hour window for baseline reversion vs persistent load elevation."
        ]
    else:
        interp = (
            f"Cell #{grid_id} in {sector} operates within expected nominal parameters. "
            f"Current telemetry ({curr_act:.1f}) closely aligns with the 24-hour moving baseline ({baseline_act:.1f}), "
            f"and ML anomaly risk remains low ({score*100:.1f}%). No uncharacteristic demand surge detected."
        )
        checks = [
            "Maintain standard automated telemetry monitoring.",
            "Inspect trailing 24h modality breakdown to confirm balance across SMS, Voice, and Data."
        ]

    checks_html = "".join([f"<li>{c}</li>" for c in checks])

    return f"""<div class="noc-report space-y-3.5 font-sans">
  <!-- SECTION 1: SEVERITY -->
  <div class="flex items-center justify-between border-b border-slate-800 pb-2.5">
    <div class="flex items-center gap-2">
      <span class="text-xs uppercase tracking-wider font-semibold text-slate-400">Severity:</span>
      {severity_badge}
      <span class="text-xs font-mono text-cyan-400 font-semibold">Grid #{grid_id} ({sector})</span>
    </div>
    <div class="text-[11px] font-mono text-slate-500">Coordinates: {lat}°N, {lon}°E</div>
  </div>

  <!-- SECTION 2: EVIDENCE -->
  <div class="rounded-lg border border-slate-800 bg-slate-900/50 p-3.5">
    <div class="text-xs font-semibold uppercase tracking-wider text-cyan-400 mb-2.5 flex items-center gap-1.5">
      <span>📊</span> Telemetry Evidence
    </div>
    <div class="grid grid-cols-2 gap-2 sm:grid-cols-3">
      <div class="rounded border border-slate-800 bg-slate-950/60 p-2">
        <div class="text-[10px] uppercase font-mono text-slate-500">Current Activity</div>
        <div class="font-mono text-sm font-semibold text-cyan-300">{curr_act:.1f}</div>
      </div>
      <div class="rounded border border-slate-800 bg-slate-950/60 p-2">
        <div class="text-[10px] uppercase font-mono text-slate-500">24h Baseline</div>
        <div class="font-mono text-sm font-semibold text-slate-300">{baseline_act:.1f}</div>
      </div>
      <div class="rounded border border-slate-800 bg-slate-950/60 p-2">
        <div class="text-[10px] uppercase font-mono text-slate-500">Activity Growth</div>
        <div class="font-mono text-sm font-semibold { 'text-amber-400' if growth > 0.2 else 'text-slate-300' }">{growth:+.1%}</div>
      </div>
      <div class="rounded border border-slate-800 bg-slate-950/60 p-2">
        <div class="text-[10px] uppercase font-mono text-slate-500">Peak Ratio</div>
        <div class="font-mono text-sm font-semibold text-slate-300">{peak_ratio:.2f}x</div>
      </div>
      <div class="rounded border border-slate-800 bg-slate-950/60 p-2">
        <div class="text-[10px] uppercase font-mono text-slate-500">ML Anomaly Score</div>
        <div class="font-mono text-sm font-semibold { 'text-rose-400' if score >= 0.5 else 'text-emerald-400' }">{score*100:.1f}%</div>
      </div>
      <div class="rounded border border-slate-800 bg-slate-950/60 p-2">
        <div class="text-[10px] uppercase font-mono text-slate-500">Sector / Location</div>
        <div class="font-mono text-xs font-semibold text-cyan-300 truncate" title="{sector}">{sector}</div>
      </div>
    </div>
  </div>

  <!-- SECTION 3: OPERATIONAL INTERPRETATION -->
  <div class="rounded-lg border border-slate-800 bg-slate-900/50 p-3.5">
    <div class="text-xs font-semibold uppercase tracking-wider text-cyan-400 mb-2 flex items-center gap-1.5">
      <span>🔍</span> Operational Interpretation
    </div>
    <div class="text-xs text-slate-300 leading-relaxed space-y-1.5">
      <p>{interp}</p>
    </div>
  </div>

  <!-- SECTION 4: RECOMMENDED NEXT CHECKS -->
  <div class="rounded-lg border border-slate-800 bg-slate-900/50 p-3.5">
    <div class="text-xs font-semibold uppercase tracking-wider text-cyan-400 mb-2 flex items-center gap-1.5">
      <span>🛠️</span> Recommended Next Checks
    </div>
    <ul class="list-disc list-inside text-xs text-slate-300 space-y-1">
      {checks_html}
    </ul>
  </div>

  <div class="text-[10px] font-mono text-slate-500 flex items-center justify-between border-t border-slate-800/60 pt-2">
    <span>Data Pipeline: Verified via get_grid_activity(), get_grid_features(), get_anomaly_score()</span>
    <span>Operational Target: Cell #{grid_id}</span>
  </div>
</div>"""


# ---------------------------------------------------------------------------
# Command 3: /review-anomaly [grid_id]
# ---------------------------------------------------------------------------
def execute_review_anomaly(grid_id: int, db: Session) -> str:
    res = execute_tool("review_grid_anomaly", {"grid_id": grid_id}, db)
    consensus = res.get("consensus", "UNKNOWN")
    rule_alerts = res.get("rule_alerts", [])
    classifier = res.get("classifier", {})
    verdict = res.get("verdict", "")

    score = classifier.get("score", 0.0)
    risk_label = classifier.get("risk_label", "NORMAL")
    threshold = classifier.get("threshold", 0.50)

    if consensus.startswith("FULL_AGREEMENT"):
        agreement_badge = '<span class="px-2.5 py-0.5 rounded-full text-xs font-bold font-mono border border-emerald-500/30 bg-emerald-500/15 text-emerald-400">CONSENSUS (AGREEMENT)</span>'
    else:
        agreement_badge = '<span class="px-2.5 py-0.5 rounded-full text-xs font-bold font-mono border border-amber-500/30 bg-amber-500/15 text-amber-400">DISAGREEMENT DETECTED</span>'

    rule_str = ", ".join([f"{a.get('type')}" for a in rule_alerts]) if rule_alerts else "None (Nominal)"
    classifier_str = f"{risk_label} ({score*100:.1f}%, threshold: {threshold*100:.0f}%)"

    return f"""<div class="noc-report space-y-3.5 font-sans">
  <div class="flex items-center justify-between border-b border-slate-800 pb-2.5">
    <div class="flex items-center gap-2">
      <span class="text-xs uppercase tracking-wider font-semibold text-slate-400">Anomaly Review:</span>
      {agreement_badge}
      <span class="text-xs font-mono text-cyan-400">Cell #{grid_id}</span>
    </div>
    <div class="text-[11px] font-mono text-slate-500">Sensor Comparison</div>
  </div>

  <div class="rounded-lg border border-slate-800 bg-slate-900/50 p-3.5">
    <div class="text-xs font-semibold uppercase tracking-wider text-cyan-400 mb-2.5 flex items-center gap-1.5">
      <span>⚖️</span> Rule Alert vs Classifier Output Matrix
    </div>
    <div class="grid grid-cols-1 gap-2 sm:grid-cols-2">
      <div class="rounded border border-slate-800 bg-slate-950/60 p-3">
        <div class="text-[10px] uppercase font-mono text-slate-500 mb-1">Rule Engine Alert</div>
        <div class="font-mono text-sm font-semibold { 'text-amber-400' if rule_alerts else 'text-slate-300' }">{rule_str}</div>
        <div class="text-[11px] text-slate-400 mt-1">Instantaneous ratio against within-day leave-one-out median.</div>
      </div>
      <div class="rounded border border-slate-800 bg-slate-950/60 p-3">
        <div class="text-[10px] uppercase font-mono text-slate-500 mb-1">LightGBM Classifier & Score</div>
        <div class="font-mono text-sm font-semibold { 'text-rose-400' if score >= threshold else 'text-slate-300' }">{classifier_str}</div>
        <div class="text-[11px] text-slate-400 mt-1">Multi-hour rolling lags, peak ratios, and temporal trend.</div>
      </div>
    </div>
  </div>

  <div class="rounded-lg border border-slate-800 bg-slate-900/50 p-3.5">
    <div class="text-xs font-semibold uppercase tracking-wider text-cyan-400 mb-1.5 flex items-center gap-1.5">
      <span>🔍</span> Operational Disagreement / Consensus Analysis
    </div>
    <div class="text-xs text-slate-300 leading-relaxed space-y-1.5">
      <p>{verdict}</p>
      { "<p><strong>NOC Interpretation:</strong> When the rule engine and ML model disagree, the LightGBM classifier accounts for trailing 24h variances and diurnal rhythms, preventing false dispatches caused by transient short-lived spikes.</p>" if "DISAGREEMENT" in consensus else "<p><strong>NOC Interpretation:</strong> Both heuristic threshold rules and predictive gradient-boosted trees corroborate the cell status, giving high operational confidence.</p>" }
    </div>
  </div>

  <div class="text-[10px] font-mono text-slate-500 flex items-center justify-between border-t border-slate-800/60 pt-2">
    <span>Sensors: AlertAnalyzer + LightGBM v2 Classifier</span>
    <span>Operational Action: { 'Dispatch Level-1 Monitoring' if score >= 0.5 or rule_alerts else 'Routine Automated Telemetry' }</span>
  </div>
</div>"""


# ---------------------------------------------------------------------------
# Command 4: /test-api
# ---------------------------------------------------------------------------
def _check_claude_api_connection() -> dict:
    """
    Performs a minimal ping to the Anthropic API to verify key validity and connectivity.
    Returns a dict with: connected (bool), model (str), latency_ms (float), error (str|None).
    """
    import os
    import time as _time
    try:
        import anthropic as _anthropic
    except ImportError:
        return {"connected": False, "model": "N/A", "latency_ms": 0.0, "error": "anthropic package not installed"}

    api_key = os.getenv("ANTHROPIC_API_KEY")
    if not api_key:
        return {"connected": False, "model": "N/A", "latency_ms": 0.0, "error": "ANTHROPIC_API_KEY not set in environment"}

    model = "claude-haiku-4-5-20251001"
    t0 = _time.monotonic()
    try:
        _client = _anthropic.Anthropic(api_key=api_key)
        _client.messages.create(
            model=model,
            max_tokens=8,
            messages=[{"role": "user", "content": "ping"}]
        )
        latency_ms = round((_time.monotonic() - t0) * 1000, 1)
        return {"connected": True, "model": model, "latency_ms": latency_ms, "error": None}
    except Exception as exc:
        latency_ms = round((_time.monotonic() - t0) * 1000, 1)
        return {"connected": False, "model": model, "latency_ms": latency_ms, "error": str(exc)[:300]}


def execute_test_api(db: Session) -> str:
    # ── 1. Claude API connectivity check ──────────────────────────────────
    claude_check = _check_claude_api_connection()
    claude_connected = claude_check["connected"]
    claude_model = html.escape(claude_check["model"])
    claude_latency = claude_check["latency_ms"]
    claude_error = html.escape(claude_check["error"] or "")

    if claude_connected:
        claude_badge = '<span class="px-2.5 py-0.5 rounded-full text-xs font-bold font-mono border border-emerald-500/30 bg-emerald-500/15 text-emerald-400">CONNECTED</span>'
        claude_detail_html = f'<span class="text-emerald-400">✓</span> Model <code class="font-mono text-cyan-300">{claude_model}</code> responded in <span class="text-cyan-400 font-semibold">{claude_latency} ms</span>'
    else:
        claude_badge = '<span class="px-2.5 py-0.5 rounded-full text-xs font-bold font-mono border border-rose-500/30 bg-rose-500/15 text-rose-400">UNREACHABLE</span>'
        claude_detail_html = f'<span class="text-rose-400">✗</span> <span class="text-slate-300">{claude_error or "Connection failed"}</span>'

    # ── 2. REST endpoint test suite ────────────────────────────────────────
    res = execute_tool("run_api_test_suite", {}, db)
    duration_s = res.get("duration_seconds", 0.0)
    tests = list(res.get("tests", []))

    # Add Claude API Gateway Connection check into the endpoints list
    claude_test_item = {
        "name": "Claude LLM API Gateway",
        "endpoint": "POST https://api.anthropic.com/v1/messages",
        "status": "PASS" if claude_connected else "FAIL",
        "status_code": 200 if claude_connected else (401 if "401" in claude_error else 500),
        "duration_ms": claude_latency,
        "error": None if claude_connected else f"Claude API authentication/connection error: {claude_error}"
    }
    tests.append(claude_test_item)

    total = len(tests)
    passed = sum(1 for t in tests if t.get("status") == "PASS")
    failed = sum(1 for t in tests if t.get("status") == "FAIL")
    errors = sum(1 for t in tests if t.get("status") == "ERROR")
    duration_s = round(duration_s + (claude_latency / 1000.0), 2)

    is_all_passed = (failed == 0 and errors == 0 and total > 0)

    if is_all_passed:
        status_badge = '<span class="px-2.5 py-0.5 rounded-full text-xs font-bold font-mono border border-emerald-500/30 bg-emerald-500/15 text-emerald-400">ALL PASSED</span>'
    else:
        status_badge = f'<span class="px-2.5 py-0.5 rounded-full text-xs font-bold font-mono border border-rose-500/30 bg-rose-500/15 text-rose-400">{failed + errors} FAILURES</span>'

    # Build tests summary table
    rows_html = []
    for t in tests:
        name = html.escape(t.get("name", ""))
        endpoint = html.escape(t.get("endpoint", ""))
        status = t.get("status", "PASS")
        dur_ms = t.get("duration_ms", 0.0)
        
        status_badge_row = (
            '<span class="text-emerald-400 font-semibold font-mono">PASS</span>'
            if status == "PASS" else
            '<span class="text-rose-400 font-semibold font-mono">FAIL</span>'
        )
        rows_html.append(f"""
          <tr class="border-b border-slate-800/60 hover:bg-slate-800/30">
            <td class="py-1.5 px-2 text-slate-300 font-mono text-xs">{name}</td>
            <td class="py-1.5 px-2 text-cyan-400 font-mono text-[11px]">{endpoint}</td>
            <td class="py-1.5 px-2">{status_badge_row}</td>
            <td class="py-1.5 px-2 text-slate-400 font-mono text-[11px] text-right">{dur_ms:.1f}ms</td>
          </tr>
        """)

    failure_details = ""
    failures = [t for t in tests if t.get("status") != "PASS"]
    if failures:
        f_items = []
        for f in failures:
            err = html.escape(f.get("error", "Unknown error"))
            f_items.append(f"""
              <div class="border-b border-slate-800 pb-2 last:border-0 last:pb-0">
                <div class="font-mono text-rose-400 font-bold text-xs">{f.get('name')}: {f.get('endpoint')}</div>
                <div class="text-[11px] font-mono text-slate-400 pl-2 mt-1 border-l-2 border-rose-500/40">{err}</div>
              </div>
            """)
        failure_details = f"""
        <div class="rounded-lg border border-rose-500/30 bg-rose-950/20 p-3.5 space-y-2">
          <div class="text-xs font-semibold uppercase tracking-wider text-rose-400">Failed Tests Breakdown</div>
          {''.join(f_items)}
        </div>
        """

    return f"""<div class="noc-report space-y-3.5 font-sans">
  <div class="flex items-center justify-between border-b border-slate-800 pb-2.5">
    <div class="flex items-center gap-2">
      <span class="text-xs uppercase tracking-wider font-semibold text-slate-400">API Test Suite:</span>
      {status_badge}
    </div>
    <div class="text-[11px] font-mono text-slate-500">Duration: {duration_s:.2f}s</div>
  </div>

  <!-- Claude API Connection Card -->
  <div class="rounded-lg border {'border-emerald-500/30 bg-emerald-950/20' if claude_connected else 'border-rose-500/30 bg-rose-950/20'} p-3 flex items-center justify-between">
    <div class="flex items-center gap-2">
      <span class="text-xs uppercase tracking-wider font-semibold text-slate-400">Claude API:</span>
      {claude_badge}
    </div>
    <div class="text-xs font-mono">{claude_detail_html}</div>
  </div>

  <!-- Horizontal 4-box KPI Grid -->
  <div class="noc-kpi-grid flex flex-row gap-2 w-full" style="display: flex; flex-direction: row; gap: 8px; width: 100%;">
    <div class="flex-1 rounded border border-slate-800 bg-slate-900/50 p-2 text-center" style="flex: 1; min-width: 0; text-align: center;">
      <div class="text-[10px] uppercase font-mono text-slate-500">Total</div>
      <div class="font-mono text-base font-semibold text-slate-200">{total}</div>
    </div>
    <div class="flex-1 rounded border border-slate-800 bg-slate-900/50 p-2 text-center" style="flex: 1; min-width: 0; text-align: center;">
      <div class="text-[10px] uppercase font-mono text-slate-500">Passed</div>
      <div class="font-mono text-base font-semibold text-emerald-400">{passed}</div>
    </div>
    <div class="flex-1 rounded border border-slate-800 bg-slate-900/50 p-2 text-center" style="flex: 1; min-width: 0; text-align: center;">
      <div class="text-[10px] uppercase font-mono text-slate-500">Failed</div>
      <div class="font-mono text-base font-semibold { 'text-rose-400' if failed > 0 else 'text-slate-400' }">{failed}</div>
    </div>
    <div class="flex-1 rounded border border-slate-800 bg-slate-900/50 p-2 text-center" style="flex: 1; min-width: 0; text-align: center;">
      <div class="text-[10px] uppercase font-mono text-slate-500">Errors</div>
      <div class="font-mono text-base font-semibold { 'text-amber-400' if errors > 0 else 'text-slate-400' }">{errors}</div>
    </div>
  </div>

  <div class="rounded-lg border border-slate-800 bg-slate-900/50 p-3.5 overflow-x-auto">
    <div class="text-xs font-semibold uppercase tracking-wider text-cyan-400 mb-2 flex items-center gap-1.5">
      <span>📋</span> Endpoint Test Execution Log
    </div>
    <table class="w-full text-left font-mono text-xs">
      <thead>
        <tr class="border-b border-slate-800 text-slate-400 text-[11px]">
          <th class="py-1 px-2">Test Case</th>
          <th class="py-1 px-2">Target Endpoint</th>
          <th class="py-1 px-2">Result</th>
          <th class="py-1 px-2 text-right">Latency</th>
        </tr>
      </thead>
      <tbody>
        {''.join(rows_html)}
      </tbody>
    </table>
  </div>

  {failure_details}

  <div class="text-[10px] font-mono text-slate-500 flex items-center justify-between border-t border-slate-800/60 pt-2">
    <span>Runner: FastAPI TestClient + Anthropic Client</span>
    <span>Suite Status: {'PASS' if is_all_passed else 'ACTION_REQUIRED'}</span>
  </div>
</div>"""


# ---------------------------------------------------------------------------
# Command 5: /network-health
# ---------------------------------------------------------------------------
def execute_network_health(db: Session) -> str:
    res = execute_tool("check_grain_duplicates", {}, db)
    status = res.get("status", "FAIL")
    target_date = res.get("target_date", "")
    total_checked = res.get("total_records_checked", 0)
    dup_grains_count = res.get("duplicate_grains_found", 0)
    duplicates = res.get("duplicates", [])
    explanation = res.get("explanation", "")

    if status == "PASS":
        status_badge = '<span class="px-2.5 py-0.5 rounded-full text-xs font-bold font-mono border border-emerald-500/30 bg-emerald-500/15 text-emerald-400">PASS (GRAIN INTACT)</span>'
    else:
        status_badge = '<span class="px-2.5 py-0.5 rounded-full text-xs font-bold font-mono border border-rose-500/30 bg-rose-500/15 text-rose-400">FAIL (GRAIN DUPLICATES DETECTED)</span>'

    dup_rows_html = ""
    if duplicates:
        rows = []
        for d in duplicates[:10]:
            rows.append(f"""
              <tr class="border-b border-slate-800/60 font-mono text-xs">
                <td class="py-1 px-2 text-slate-300">{d.get('date')}</td>
                <td class="py-1 px-2 text-slate-300">{d.get('hour'):02d}:00</td>
                <td class="py-1 px-2 text-cyan-400 font-semibold">#{d.get('grid_id')}</td>
                <td class="py-1 px-2 text-rose-400 font-bold text-right">{d.get('duplicate_count')}x</td>
              </tr>
            """)
        dup_rows_html = f"""
        <div class="rounded-lg border border-slate-800 bg-slate-900/50 p-3.5 overflow-x-auto">
          <div class="text-xs font-semibold uppercase tracking-wider text-rose-400 mb-2 flex items-center gap-1.5">
            <span>⚠️</span> Duplicate Grain Samples (Date, Hour, Grid)
          </div>
          <table class="w-full text-left font-mono text-xs">
            <thead>
              <tr class="border-b border-slate-800 text-slate-400 text-[11px]">
                <th class="py-1 px-2">Date</th>
                <th class="py-1 px-2">Hour</th>
                <th class="py-1 px-2">Grid ID</th>
                <th class="py-1 px-2 text-right">Duplicates</th>
              </tr>
            </thead>
            <tbody>
              {''.join(rows)}
            </tbody>
          </table>
        </div>
        """

    return f"""<div class="noc-report space-y-3.5 font-sans">
  <div class="flex items-center justify-between border-b border-slate-800 pb-2.5">
    <div class="flex items-center gap-2">
      <span class="text-xs uppercase tracking-wider font-semibold text-slate-400">Grain Health:</span>
      {status_badge}
    </div>
    <div class="text-[11px] font-mono text-slate-500">Target Date: {target_date}</div>
  </div>

  <div class="rounded-lg border border-slate-800 bg-slate-900/50 p-3.5">
    <div class="text-xs font-semibold uppercase tracking-wider text-cyan-400 mb-2.5 flex items-center gap-1.5">
      <span>📐</span> Core Analytics Grain Invariant
    </div>
    <p class="text-xs text-slate-300 leading-relaxed m-0">
      The platform enforces <strong>exactly one record per grid cell per 1-hour timestamp</strong>: <code>(date, hour, grid_id)</code>.
      All 10-minute intervals and country codes within each hour must be aggregated.
    </p>
    <div class="grid grid-cols-2 gap-2 sm:grid-cols-3 mt-3">
      <div class="rounded border border-slate-800 bg-slate-950/60 p-2">
        <div class="text-[10px] uppercase font-mono text-slate-500">Records Checked</div>
        <div class="font-mono text-sm font-semibold text-slate-200">{total_checked:,}</div>
      </div>
      <div class="rounded border border-slate-800 bg-slate-950/60 p-2">
        <div class="text-[10px] uppercase font-mono text-slate-500">Duplicate Grains</div>
        <div class="font-mono text-sm font-semibold { 'text-rose-400' if dup_grains_count > 0 else 'text-emerald-400' }">{dup_grains_count}</div>
      </div>
      <div class="rounded border border-slate-800 bg-slate-950/60 p-2">
        <div class="text-[10px] uppercase font-mono text-slate-500">Invariant Status</div>
        <div class="font-mono text-xs font-semibold { 'text-emerald-400' if status == 'PASS' else 'text-rose-400' }">{status}</div>
      </div>
    </div>
  </div>

  {dup_rows_html}

  <div class="rounded-lg border border-slate-800 bg-slate-900/50 p-3.5">
    <div class="text-xs font-semibold uppercase tracking-wider text-cyan-400 mb-1.5 flex items-center gap-1.5">
      <span>🛠️</span> Engineering Root Cause & Remediation
    </div>
    <div class="text-xs text-slate-300 leading-relaxed space-y-1.5">
      <p>{explanation}</p>
      { "<p><strong>Remediation:</strong> Multiple Spark ETL batch runs inserted records into <code>hourly_grid_summary</code> without upsert (<code>ON DUPLICATE KEY UPDATE</code>). Recommend deduplicating on <code>(date, hour, grid_id)</code> keeping the most recent <code>loaded_at</code> timestamp.</p>" if status == "FAIL" else "<p><strong>Remediation:</strong> None required. Invariant intact.</p>" }
    </div>
  </div>

  <div class="text-[10px] font-mono text-slate-500 flex items-center justify-between border-t border-slate-800/60 pt-2">
    <span>Audit Table: hourly_grid_summary</span>
    <span>Rule: Grain Uniqueness (CLAUDE.md Invariant #1)</span>
  </div>
</div>"""
