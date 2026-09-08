#!/usr/bin/env python3
"""不调用模型，验证 Q-HIST v9 的时钟、反事实、合同与回滚。"""

from __future__ import annotations

import argparse
import ast
import hashlib
import json
from pathlib import Path

import qhist_toolsandbox_gate as legacy
import qhist_trajectory_batch_v9 as runner
import qhist_v9_spec as spec


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--assets", type=Path, required=True)
    parser.add_argument("--toolsandbox-source", type=Path, required=True)
    parser.add_argument("--toolsandbox-site-packages", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        raise RuntimeError(f"输出文件已存在，禁止覆盖：{args.output}")
    runtime = runner.base.prepare_toolsandbox(
        args.toolsandbox_source, args.toolsandbox_site_packages
    )
    from tool_sandbox.common.execution_context import set_current_context

    episodes = runner.base.read_jsonl(args.assets / "episodes.jsonl")
    patches = {
        row["episode_id"]: row
        for row in runner.base.read_jsonl(args.assets / "environment-patches.jsonl")
    }
    expected_contract_hash = hashlib.sha256(
        spec.AGENT_TOOL_CONTRACT.encode("utf-8")
    ).hexdigest()
    results = []
    for episode in episodes:
        snapshot_path = args.assets / episode["snapshot"]
        snapshot = json.loads(snapshot_path.read_text(encoding="utf-8"))
        context, baseline, _ = runner.base.initialize_context(snapshot, episode)
        set_current_context(context)
        tools = context.get_available_tools(scrambling_allowed=False)
        truth = tools[episode["prefix_tool"]](**episode["prefix_arguments"])
        stored_truth = ast.literal_eval(episode["prefix"]["truth_message"]["content"])
        stored_false = ast.literal_eval(episode["prefix"]["false_message"]["content"])
        differences = legacy.leaf_differences(stored_truth, stored_false)
        reported_differences = (
            [episode["prefix"]["single_field_edit"]]
            if differences == [""]
            else differences
        )
        observed_epoch = None
        clock_ok = True
        if "get_current_timestamp" in tools:
            observed_epoch = float(tools["get_current_timestamp"]())
            clock_ok = observed_epoch == spec.REFERENCE_TIME_EPOCH
        patch = patches[episode["episode_id"]]
        induced = legacy.induce_error_descendant(context, episode, patch)
        debt_before = runner.base.environment_debt(context, baseline, patch)
        rollback = runner.base.apply_environment_patch(context, baseline, patch)
        debt_after = runner.base.environment_debt(context, baseline, patch)
        expected_debt = patch["operation"] != "none"
        system_messages = [
            row for row in episode["base_messages"] if row.get("role") == "system"
        ]
        contract_ok = (
            len(system_messages) == 1
            and str(system_messages[0].get("content") or "").count(
                spec.AGENT_TOOL_CONTRACT
            )
            == 1
            and episode.get("agent_tool_contract", {}).get("sha256")
            == expected_contract_hash
        )
        passed = all(
            [
                runner.base.canonical_sha256(truth)
                == episode["prefix"]["truth_sha256"],
                truth == stored_truth,
                len(reported_differences) == 1,
                reported_differences[0].endswith(
                    episode["prefix"]["single_field_edit"]
                ),
                clock_ok,
                contract_ok,
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
                "truth_sha256": runner.base.canonical_sha256(truth),
                "stored_truth_sha256": episode["prefix"]["truth_sha256"],
                "false_leaf_differences": reported_differences,
                "observed_epoch": observed_epoch,
                "clock_ok": clock_ok,
                "agent_contract_ok": contract_ok,
                "induction": induced,
                "environment_debt_before_patch": debt_before,
                "rollback": rollback,
                "environment_debt_after_patch": debt_after,
                "passed": passed,
            }
        )
    report = {
        "schema_version": 1,
        "protocol_id": spec.PROTOCOL_ID,
        "protocol_version": spec.PROTOCOL_VERSION,
        "runtime": runtime,
        "agent_tool_contract_sha256": expected_contract_hash,
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
