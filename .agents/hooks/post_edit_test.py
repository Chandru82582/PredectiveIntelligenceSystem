"""
PostToolUse Hook: Spark & ML Regression Guard.

Enforces Requirement 1:
After any edit under spark/ or ml/, run the grain and leakage tests automatically:
  1. (grid_id, timestamp) duplicate check
  2. ML2 feature leakage boundary test
These silent and expensive failures must never wait for CI.

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

from common import (
    log_hook_outcome,
    run_grain_duplicate_check,
    run_ml2_leakage_test,
)

SPARK_ML_PATTERNS = [
    "spark/",
    "/spark",
    "ml/",
    "/ml",
    "cleaner_spark",
    "preprocessor",
]


def is_spark_or_ml_edit(filepath: str) -> bool:
    """Returns True if edited file path is under spark/ or ml/."""
    if not filepath:
        return False
    norm = filepath.replace("\\", "/").lower()
    return any(p in norm for p in SPARK_ML_PATTERNS)


def handle_post_tool_use(payload: dict, force_fail: bool = False, force_pass: bool = False) -> dict:
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

    if not is_spark_or_ml_edit(target_file) and not (force_fail or force_pass):
        log_hook_outcome(
            hook_name="spark-ml-regression-guard",
            event_type="PostToolUse",
            target_file=target_file,
            decision="SKIP",
            details=f"File outside spark/ and ml/ scope; automated regression tests skipped. Tool: {tool_name}",
            extra={"tool_name": tool_name},
        )
        return {}

    # Run the two critical regression tests
    grain_passed, grain_meta = run_grain_duplicate_check(simulate_duplicate=force_fail)
    leakage_passed, leakage_meta = run_ml2_leakage_test(simulate_leakage=force_fail)

    overall_passed = grain_passed and leakage_passed and not force_fail

    summary = (
        f"Grain Check: {'PASS' if grain_passed else 'FAIL'} ({grain_meta.get('message')}) | "
        f"ML2 Feature Leakage Test: {'PASS' if leakage_passed else 'FAIL'} ({leakage_meta.get('message')})"
    )

    decision = "PASS" if overall_passed else "FAIL"

    log_hook_outcome(
        hook_name="spark-ml-regression-guard",
        event_type="PostToolUse",
        target_file=target_file or "ml/simulated_target.py",
        decision=decision,
        details=summary,
        extra={
            "tool_name": tool_name,
            "grain_check": grain_meta,
            "ml2_leakage_test": leakage_meta,
        },
    )

    if not overall_passed:
        # Emit detailed failure trace to stderr so it surfaces in Antigravity agent output
        sys.stderr.write(
            f"\n[SPARK-ML REGRESSION GUARD FAILED]\n"
            f"Target: {target_file}\n"
            f"1. Grain Duplicate Check: {'PASS' if grain_passed else 'FAIL'}\n"
            f"   -> {grain_meta.get('message')}\n"
            f"2. ML2 Feature Leakage Test: {'PASS' if leakage_passed else 'FAIL'}\n"
            f"   -> {leakage_meta.get('message')}\n"
            f"Action Required: Revert or fix future-looking feature leakage or grain duplicates.\n\n"
        )
    else:
        sys.stderr.write(
            f"\n[SPARK-ML REGRESSION GUARD PASSED]\n"
            f"Target: {target_file}\n"
            f"1. Grain Duplicate Check: PASS\n"
            f"2. ML2 Feature Leakage Test: PASS (Features strictly invariant to t+1)\n\n"
        )

    # PostToolUse contract expects empty JSON object on stdout
    return {}


def main():
    force_pass = "--test-pass" in sys.argv
    force_fail = "--test-fail" in sys.argv

    # Support CLI invocation
    if force_pass or force_fail or "--file" in sys.argv:
        target = "ml/preprocessor.py"
        if "--file" in sys.argv:
            idx = sys.argv.index("--file")
            if idx + 1 < len(sys.argv):
                target = sys.argv[idx + 1]

        test_payload = {
            "toolCall": {
                "name": "replace_file_content",
                "args": {"TargetFile": target},
            },
            "stepIdx": 1,
        }
        res = handle_post_tool_use(test_payload, force_fail=force_fail, force_pass=force_pass)
        print(json.dumps(res))
        return

    # Standard stdin execution mode via Antigravity hook engine
    try:
        raw_input = sys.stdin.read()
        payload = json.loads(raw_input) if raw_input.strip() else {}
    except Exception:
        payload = {}

    response = handle_post_tool_use(payload)
    print(json.dumps(response))


if __name__ == "__main__":
    main()
