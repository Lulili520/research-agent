#!/usr/bin/env python3
"""按冻结配置验证单条 ToolSandbox clean smoke 的资格门禁。"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


def evaluate_gate(config: dict[str, Any], summary: dict[str, Any]) -> dict[str, Any]:
    gate = config["gate"]
    mapping = summary.get("evaluation", {}).get("milestone_mapping", {})
    scores = {int(index): float(pair[1]) for index, pair in mapping.items()}
    critical = [int(index) for index in gate["critical_milestones_exact"]]
    reasons: list[str] = []

    if summary.get("scenario") != config.get("scenario"):
        reasons.append("scenario_mismatch")
    if summary.get("status") != "succeeded":
        reasons.append("runner_not_succeeded")
    missing_critical = [index for index in critical if index not in scores]
    if missing_critical:
        reasons.append(f"missing_critical_milestones:{missing_critical}")
    failed_critical = [index for index in critical if scores.get(index) != 1.0]
    if failed_critical:
        reasons.append(f"critical_milestones_not_exact:{failed_critical}")
    minimum = float(gate["minimum_any_milestone_similarity"])
    if not scores or min(scores.values()) < minimum:
        reasons.append("minimum_milestone_similarity_failed")
    expected_minefield = float(gate["minefield_similarity"])
    if summary.get("evaluation", {}).get("minefield_similarity") != expected_minefield:
        reasons.append("minefield_failed")
    if summary.get("native_tool_call_count", 0) < int(gate["minimum_native_tool_calls"]):
        reasons.append("native_tool_call_count_failed")
    if summary.get("tool_call_exception_count") != int(gate["maximum_tool_call_exceptions"]):
        reasons.append("tool_call_exception_count_failed")

    return {
        "schema_version": 1,
        "run_id": config["run_id"],
        "protocol_version": config["protocol_version"],
        "scenario": config["scenario"],
        "critical_milestones": critical,
        "milestone_scores": scores,
        "minimum_milestone_similarity": min(scores.values()) if scores else None,
        "total_similarity": summary.get("evaluation", {}).get("similarity"),
        "minefield_similarity": summary.get("evaluation", {}).get("minefield_similarity"),
        "native_tool_call_count": summary.get("native_tool_call_count"),
        "tool_call_exception_count": summary.get("tool_call_exception_count"),
        "passed": not reasons,
        "failure_reasons": reasons,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--summary", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result = evaluate_gate(
        json.loads(args.config.read_text(encoding="utf-8")),
        json.loads(args.summary.read_text(encoding="utf-8")),
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
