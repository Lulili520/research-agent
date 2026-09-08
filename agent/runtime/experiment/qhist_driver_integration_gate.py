#!/usr/bin/env python3
"""用固定动作代理验证 Q-HIST 轨迹驱动器；不调用任何语言模型。"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

import qhist_trajectory_batch as runner


def read_jsonl(path: Path):
    return [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--assets", type=Path, required=True)
    parser.add_argument("--rendered", type=Path, required=True)
    parser.add_argument("--toolsandbox-source", type=Path, required=True)
    parser.add_argument("--toolsandbox-site-packages", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        raise RuntimeError(f"输出文件已存在：{args.output}")
    runtime = runner.prepare_toolsandbox(
        args.toolsandbox_source, args.toolsandbox_site_packages
    )
    from tool_sandbox.common.tool_discovery import ToolBackend
    from tool_sandbox.scenarios import named_scenarios

    episodes = {row["episode_id"]: row for row in read_jsonl(args.assets / "episodes.jsonl")}
    predicates = {row["episode_id"]: row for row in read_jsonl(args.assets / "predicates.jsonl")}
    patches = {row["episode_id"]: row for row in read_jsonl(args.assets / "environment-patches.jsonl")}
    authority = {
        (row["episode_id"], row["condition"]): row
        for row in read_jsonl(args.rendered / "authority-messages.jsonl")
    }
    episode = episodes["QH-E0-01"]
    false_phone = predicates["QH-E0-01"]["false_value"]
    true_phone = predicates["QH-E0-01"]["oracle_value"]
    actions = [
        {"name": "set_cellular_service_status", "arguments": {"on": True}},
        {
            "name": "send_message_with_phone_number",
            "arguments": {
                "phone_number": false_phone,
                "content": "How's the new album coming along.",
            },
        },
        {"name": "end_conversation", "arguments": {}},
        {"name": "search_contacts", "arguments": {"name": "Fredrik Thordendal"}},
        {
            "name": "send_message_with_phone_number",
            "arguments": {
                "phone_number": true_phone,
                "content": "How's the new album coming along.",
            },
        },
        {"name": "end_conversation", "arguments": {}},
    ]
    cursor = {"value": 0}

    def fixed_generate(
        endpoint,
        request_id,
        expected_precision,
        messages,
        tools,
        max_new_tokens,
    ):
        index = cursor["value"]
        cursor["value"] += 1
        action = actions[index]
        raw = "<tool_call>\n" + json.dumps(action) + "\n</tool_call><|im_end|>"
        return {
            "request_id": request_id,
            "precision": expected_precision,
            "model_revision": runner.MODEL_REVISION,
            "raw_text": raw,
            "visible_content": raw.replace("<|im_end|>", ""),
            "parsed_actions": [action],
            "input_token_count": 1,
            "generated_token_count": 1,
            "input_ids_sha256": hashlib.sha256(request_id.encode()).hexdigest(),
            "tool_schema_sha256": runner.canonical_sha256(tools),
            "cache_evidence": {"class": "fixed-action-integration-gate"},
            "elapsed_seconds": 0.0,
        }

    runner.generate_decision = fixed_generate
    row = {
        "unit_id": "ENGINEERING-QH-E0-01-P00-C_align-d3",
        "episode_id": "QH-E0-01",
        "scenario": episode["scenario"],
        "family": episode["family"],
        "precision": "P00",
        "history": "C_align",
        "distance": 3,
        "execution_order": 1,
    }
    scenarios = named_scenarios(preferred_tool_backend=ToolBackend.DEFAULT)
    result = runner.run_unit(
        row,
        episode,
        predicates["QH-E0-01"],
        patches["QH-E0-01"],
        authority,
        args.assets,
        scenarios[episode["scenario"]],
        "fixed-action://no-model",
        256,
    )
    checks = {
        "six_decisions": len(result["decisions"]) == 6,
        "false_action_detected": result["decisions"][1][
            "error_consistent_action"
        ],
        "pre_patch_environment_debt_detected": result["decisions"][1][
            "environment_debt"
        ],
        "c_align_patch_changed_state": result["correction"]["patch"]["changed"],
        "final_environment_debt_zero": result["metrics"]["environment_residual"]
        == 0.0,
        "visible_correction_hash_matches": result["correction"][
            "visible_message_sha256"
        ]
        == authority[("QH-E0-01", "C_align")]["content_sha256"],
        "all_native_actions_valid": result["metrics"]["format_validity"] == 1.0,
    }
    report = {
        "schema_version": 1,
        "protocol_id": "QHIST-EXP",
        "protocol_version": 8,
        "runtime": runtime,
        "checks": checks,
        "passed": all(checks.values()),
        "trajectory": result,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(report, ensure_ascii=False, indent=2, default=str) + "\n",
        encoding="utf-8",
    )
    print(json.dumps({"checks": checks, "passed": report["passed"]}, indent=2))
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
