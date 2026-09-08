#!/usr/bin/env python3
"""不调用模型，验证 Q-HIST v8 的 ToolSandbox 时钟、反事实与回滚。"""

from __future__ import annotations

import argparse
import ast
import copy
import json
from pathlib import Path
from typing import Any

from qhist_trajectory_batch import (
    REFERENCE_TIME_EPOCH,
    apply_environment_patch,
    canonical_sha256,
    environment_debt,
    initialize_context,
    prepare_toolsandbox,
    read_jsonl,
)


def leaf_differences(left: Any, right: Any, path: str = "") -> list[str]:
    if isinstance(left, dict) and isinstance(right, dict):
        keys = set(left) | set(right)
        differences: list[str] = []
        for key in sorted(keys):
            differences.extend(
                leaf_differences(
                    left.get(key), right.get(key), f"{path}.{key}" if path else key
                )
            )
        return differences
    if isinstance(left, list) and isinstance(right, list):
        differences = []
        for index in range(max(len(left), len(right))):
            lvalue = left[index] if index < len(left) else None
            rvalue = right[index] if index < len(right) else None
            differences.extend(
                leaf_differences(lvalue, rvalue, f"{path}[{index}]")
            )
        return differences
    return [] if left == right else [path]


def induce_error_descendant(context, episode: dict[str, Any], patch: dict[str, Any]):
    from tool_sandbox.common.execution_context import set_current_context

    set_current_context(context)
    tools = context.get_available_tools(scrambling_allowed=False)
    operation = patch["operation"]
    outcome: dict[str, Any] = {"operation": operation}
    if operation == "remove_rows_added_after_baseline":
        tools["set_cellular_service_status"](on=True)
        false_phone = patch["predicate"]["recipient_phone_number"]
        tools["send_message_with_phone_number"](
            phone_number=false_phone,
            content="Q-HIST rollback audit probe",
        )
        outcome["induced"] = True
    elif operation == "restore_baseline_row_if_missing_or_changed":
        tools["remove_reminder"](
            reminder_id=patch["key"]["reminder_id"]
        )
        outcome["induced"] = True
    elif operation == "none":
        try:
            tools["set_wifi_status"](on=True)
            outcome["expected_rejection"] = False
        except Exception as error:
            outcome["expected_rejection"] = True
            outcome["rejection_type"] = type(error).__name__
        outcome["induced"] = False
    else:
        raise ValueError(operation)
    return outcome


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--assets", type=Path, required=True)
    parser.add_argument("--toolsandbox-source", type=Path, required=True)
    parser.add_argument("--toolsandbox-site-packages", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        raise RuntimeError(f"输出文件已存在，禁止覆盖：{args.output}")
    runtime = prepare_toolsandbox(
        args.toolsandbox_source, args.toolsandbox_site_packages
    )
    from tool_sandbox.common.execution_context import set_current_context

    episodes = read_jsonl(args.assets / "episodes.jsonl")
    patches = {
        row["episode_id"]: row
        for row in read_jsonl(args.assets / "environment-patches.jsonl")
    }
    results: list[dict[str, Any]] = []
    for episode in episodes:
        snapshot_path = args.assets / episode["snapshot"]
        snapshot = json.loads(snapshot_path.read_text(encoding="utf-8"))
        context, baseline, _ = initialize_context(snapshot, episode)
        set_current_context(context)
        tools = context.get_available_tools(scrambling_allowed=False)
        truth = tools[episode["prefix_tool"]](**episode["prefix_arguments"])
        stored_truth = ast.literal_eval(episode["prefix"]["truth_message"]["content"])
        stored_false = ast.literal_eval(episode["prefix"]["false_message"]["content"])
        differences = leaf_differences(stored_truth, stored_false)
        # 标量工具 observation 没有可写入路径的容器键；其唯一返回字段由
        # 冻结 single_field_edit 命名。
        reported_differences = (
            [episode["prefix"]["single_field_edit"]]
            if differences == [""]
            else differences
        )
        clock_ok = True
        observed_epoch = None
        if "get_current_timestamp" in tools:
            observed_epoch = float(tools["get_current_timestamp"]())
            clock_ok = observed_epoch == REFERENCE_TIME_EPOCH
        patch = patches[episode["episode_id"]]
        induced = induce_error_descendant(context, episode, patch)
        debt_before = environment_debt(context, baseline, patch)
        rollback = apply_environment_patch(context, baseline, patch)
        debt_after = environment_debt(context, baseline, patch)
        expected_debt = patch["operation"] != "none"
        passed = all(
            [
                canonical_sha256(truth) == episode["prefix"]["truth_sha256"],
                truth == stored_truth,
                len(reported_differences) == 1,
                reported_differences[0].endswith(
                    episode["prefix"]["single_field_edit"]
                ),
                clock_ok,
                debt_before == expected_debt,
                debt_after is False,
                (
                    induced.get("expected_rejection") is True
                    if patch["operation"] == "none"
                    else True
                ),
            ]
        )
        results.append(
            {
                "episode_id": episode["episode_id"],
                "scenario": episode["scenario"],
                "truth_sha256": canonical_sha256(truth),
                "stored_truth_sha256": episode["prefix"]["truth_sha256"],
                "false_leaf_differences": reported_differences,
                "observed_epoch": observed_epoch,
                "clock_ok": clock_ok,
                "induction": induced,
                "environment_debt_before_patch": debt_before,
                "rollback": rollback,
                "environment_debt_after_patch": debt_after,
                "passed": passed,
            }
        )
    report = {
        "schema_version": 1,
        "protocol_id": "QHIST-EXP",
        "protocol_version": 8,
        "runtime": runtime,
        "episodes": results,
        "passed_episodes": sum(row["passed"] for row in results),
        "expected_episodes": len(results),
        "passed": bool(results) and all(row["passed"] for row in results),
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(report, ensure_ascii=False, indent=2, default=str) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(report, ensure_ascii=False, indent=2, default=str))
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
