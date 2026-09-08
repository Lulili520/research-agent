#!/usr/bin/env python3
"""不调用模型，审计 Q-HIST v10 的真值、单错误链、oracle 与回滚。"""

from __future__ import annotations

import argparse
import ast
import hashlib
import json
from pathlib import Path
from typing import Any

import qhist_toolsandbox_gate as legacy
import qhist_trajectory_batch_v10 as runner
import qhist_v10_spec as spec


def induce_error(context: Any, episode: dict[str, Any], patch: dict[str, Any]) -> dict[str, Any]:
    from tool_sandbox.common.execution_context import set_current_context

    set_current_context(context)
    tools = context.get_available_tools(scrambling_allowed=False)
    kind = episode["error_kind"]
    outcome: dict[str, Any] = {"error_kind": kind, "operation": patch["operation"]}
    if kind == "contact-phone-substitution":
        tools["set_cellular_service_status"](on=True)
        tools["send_message_with_phone_number"](
            phone_number=patch["predicate"]["recipient_phone_number"],
            content="How's the new album coming along.",
        )
        outcome["induced"] = True
    elif kind == "relative-time-shift":
        tools["add_reminder"](
            content=patch["predicate"]["content"],
            reminder_timestamp=patch["predicate"]["reminder_timestamp"],
        )
        outcome["induced"] = True
    elif kind == "boolean-negation-cellular":
        try:
            tools["set_cellular_service_status"](on=True)
            outcome["expected_rejection"] = False
        except Exception as error:
            outcome["expected_rejection"] = True
            outcome["rejection_type"] = type(error).__name__
        outcome["induced"] = False
    else:
        raise ValueError(kind)
    return outcome


def execute_oracle(
    context: Any, environment: Any, predicate: dict[str, Any], episode_id: str
) -> list[dict[str, Any]]:
    """经正式 ExecutionEnvironment 执行 oracle，使官方 evaluator 可见轨迹。"""

    oracle = predicate["oracle_action"]
    actions = oracle.get("ordered_actions") or [oracle]
    records = []
    for index, frozen in enumerate(actions, 1):
        action = {
            "name": frozen["tool"],
            "arguments": dict(frozen.get("arguments_contains") or {}),
        }
        _, _, execution = runner.base.execute_actions(
            context,
            environment,
            [action],
            f"oracle_{episode_id.lower().replace('-', '_')}_{index}",
        )
        if len(execution) != 1 or execution[0].get("exception") is not None:
            raise RuntimeError(
                f"{episode_id} oracle 第 {index} 步执行失败：{execution!r}"
            )
        records.append(
            {
                "tool": frozen["tool"],
                "content": execution[0].get("content"),
                "tool_trace": execution[0].get("tool_trace"),
            }
        )
    return records


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
    from tool_sandbox.common.execution_context import get_current_context, set_current_context

    episodes = runner.base.read_jsonl(args.assets / "episodes.jsonl")
    predicates = {
        row["episode_id"]: row
        for row in runner.base.read_jsonl(args.assets / "predicates.jsonl")
    }
    patches = {
        row["episode_id"]: row
        for row in runner.base.read_jsonl(args.assets / "environment-patches.jsonl")
    }
    expected_contract_hash = hashlib.sha256(
        spec.AGENT_TOOL_CONTRACT.encode("utf-8")
    ).hexdigest()
    results = []
    for episode in episodes:
        predicate = predicates[episode["episode_id"]]
        patch = patches[episode["episode_id"]]
        snapshot_path = args.assets / episode["snapshot"]
        snapshot = json.loads(snapshot_path.read_text(encoding="utf-8"))
        context, baseline, _ = runner.base.initialize_context(snapshot, episode)
        set_current_context(context)
        tools = context.get_available_tools(scrambling_allowed=False)
        truth = tools[episode["prefix_tool"]](**episode["prefix_arguments"])
        stored_truth = ast.literal_eval(episode["prefix"]["truth_message"]["content"])
        stored_false = ast.literal_eval(episode["prefix"]["false_message"]["content"])
        differences = legacy.leaf_differences(stored_truth, stored_false)
        single_observation_edit = len(differences) == 1
        if differences == [""]:
            single_observation_edit = True
        observed_epoch = None
        clock_ok = True
        if "get_current_timestamp" in tools:
            observed_epoch = float(tools["get_current_timestamp"]())
            clock_ok = observed_epoch == spec.REFERENCE_TIME_EPOCH

        induced = induce_error(context, episode, patch)
        debt_before = runner.base.environment_debt(context, baseline, patch)
        rollback = runner.base.apply_environment_patch(context, baseline, patch)
        debt_after = runner.base.environment_debt(context, baseline, patch)
        expected_debt = patch["operation"] != "none"

        oracle_context, _, oracle_environment = runner.base.initialize_context(
            snapshot, episode
        )
        # 与正式 N 分支相同：先写入真实工具观测与正确承诺，再执行冻结 oracle。
        # 否则官方 evaluator 看不到属于任务路径的 prefix 工具调用，会低估可达性。
        runner.add_exogenous_prefix(oracle_context, episode, use_truth=True)
        oracle_actions = execute_oracle(
            oracle_context, oracle_environment, predicate, episode["episode_id"]
        )
        if predicate.get("oracle_completion_message"):
            runner.base.add_prose_action(
                oracle_context, str(predicate["oracle_completion_message"])
            )
        set_current_context(oracle_context)
        oracle_evaluation = episode["scenario"]
        # 使用与正式轨迹相同的官方 scenario evaluator，而不是自建成功标签。
        from tool_sandbox.common.tool_discovery import ToolBackend
        from tool_sandbox.scenarios import named_scenarios

        scenario = named_scenarios(preferred_tool_backend=ToolBackend.DEFAULT)[
            oracle_evaluation
        ]
        evaluation = scenario.evaluation.evaluate(
            execution_context=get_current_context(), max_turn_count=scenario.max_messages
        )

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
        truth_commitment = episode["prefix"]["truth_commitment_message"]["content"]
        false_commitment = episode["prefix"]["false_commitment_message"]["content"]
        commitment_ok = all(
            [
                truth_commitment != false_commitment,
                str(predicate["oracle_value"]).lower() in truth_commitment.lower(),
                str(predicate["false_value"]).lower() in false_commitment.lower(),
                hashlib.sha256(truth_commitment.encode("utf-8")).hexdigest()
                == episode["prefix"]["truth_commitment_sha256"],
                hashlib.sha256(false_commitment.encode("utf-8")).hexdigest()
                == episode["prefix"]["false_commitment_sha256"],
                episode["prefix"].get("semantic_error_count") == 1,
            ]
        )
        screen = episode.get("construct_screen") or {}
        screen_ok = all(
            screen.get(field) is True
            for field in (
                "complete_single_turn_intent",
                "programmatic_truth",
                "unique_error_action",
                "unique_oracle_action_or_ordered_path",
                "single_semantic_error_chain",
            )
        ) and screen.get("target_model_output_used_for_selection") is False

        verification_context, _, _ = runner.base.initialize_context(snapshot, episode)
        set_current_context(verification_context)
        verification_tools = verification_context.get_available_tools(
            scrambling_allowed=False
        )
        verification_records = []
        for frozen in predicate.get("verification_actions", []):
            observed = verification_tools[frozen["tool"]](
                **dict(frozen.get("arguments_contains") or {})
            )
            verification_records.append(
                {
                    "tool": frozen["tool"],
                    "observed": observed,
                    "expected": frozen.get("expected_result"),
                    "passed": (
                        "expected_result" in frozen
                        and observed == frozen["expected_result"]
                    ),
                }
            )
        verification_truth_ok = bool(verification_records) and all(
            row["passed"] for row in verification_records
        )
        passed = all(
            [
                runner.base.canonical_sha256(truth)
                == episode["prefix"]["truth_sha256"],
                truth == stored_truth,
                single_observation_edit,
                clock_ok,
                contract_ok,
                commitment_ok,
                screen_ok,
                verification_truth_ok,
                debt_before == expected_debt,
                debt_after is False,
                (
                    induced.get("expected_rejection") is True
                    if patch["operation"] == "none"
                    else True
                ),
                float(evaluation.similarity) >= 1.0 - 1e-12,
            ]
        )
        results.append(
            {
                "episode_id": episode["episode_id"],
                "scenario": episode["scenario"],
                "truth_sha256": runner.base.canonical_sha256(truth),
                "stored_truth_sha256": episode["prefix"]["truth_sha256"],
                "false_leaf_differences": differences,
                "single_observation_edit": single_observation_edit,
                "observed_epoch": observed_epoch,
                "clock_ok": clock_ok,
                "agent_contract_ok": contract_ok,
                "commitment_chain_ok": commitment_ok,
                "construct_screen_ok": screen_ok,
                "verification_truth_ok": verification_truth_ok,
                "verification_records": verification_records,
                "induction": induced,
                "environment_debt_before_patch": debt_before,
                "rollback": rollback,
                "environment_debt_after_patch": debt_after,
                "oracle_actions": oracle_actions,
                "official_oracle_similarity": float(evaluation.similarity),
                "official_oracle_complete": (
                    float(evaluation.similarity) >= 1.0 - 1e-12
                ),
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
