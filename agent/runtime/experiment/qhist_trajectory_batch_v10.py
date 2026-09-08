#!/usr/bin/env python3
"""在单一冻结精度下执行 Q-HIST v10 轨迹并保存逐边界证据。"""

from __future__ import annotations

import copy
import ast
import hashlib
import json
import time
from collections import Counter
from typing import Any

import qhist_trajectory_batch_v9 as v9
import qhist_v10_spec as spec

base = v9.base


def predicate_matches(
    candidate: dict[str, Any], predicate: dict[str, Any], environment: dict[str, Any]
) -> bool:
    return base.action_matches(candidate, predicate, environment)


def is_error_action(
    candidate: dict[str, Any],
    predicate: dict[str, Any],
    environment_before_reply: dict[str, Any],
    preceding_actions_in_reply: list[dict[str, Any]],
) -> bool:
    if not predicate_matches(candidate, predicate, environment_before_reply):
        return False
    blocker = predicate.get("unless_preceded_by")
    if blocker and any(
        predicate_matches(action, blocker, environment_before_reply)
        for action in preceding_actions_in_reply
    ):
        return False
    return True


def oracle_progress(
    successful_actions: list[dict[str, Any]], predicate: dict[str, Any]
) -> tuple[bool, int]:
    ordered = predicate.get("ordered_actions")
    if ordered:
        cursor = 0
        for candidate in successful_actions:
            if cursor < len(ordered) and predicate_matches(
                candidate, ordered[cursor], {}
            ):
                cursor += 1
        return cursor == len(ordered), cursor
    return (
        any(predicate_matches(candidate, predicate, {}) for candidate in successful_actions),
        int(any(predicate_matches(candidate, predicate, {}) for candidate in successful_actions)),
    )


def successful_truth_verification(
    candidate: dict[str, Any],
    execution_record: dict[str, Any] | None,
    predicate: dict[str, Any],
) -> bool:
    """只有工具成功且返回冻结真值时，才视为完成真值核验。"""

    if execution_record is None or execution_record.get("exception") is not None:
        return False
    if not predicate_matches(candidate, predicate, {}):
        return False
    if "expected_result" not in predicate:
        return False
    try:
        observed = ast.literal_eval(str(execution_record.get("content") or ""))
    except (SyntaxError, ValueError):
        return False
    return observed == predicate["expected_result"]


def add_exogenous_prefix(context: Any, episode: dict[str, Any], use_truth: bool) -> None:
    from tool_sandbox.common.execution_context import DatabaseNamespace, RoleType

    base.add_synthetic_prefix(context, episode, use_truth=use_truth)
    commitment = (
        episode["prefix"]["truth_commitment_message"]
        if use_truth
        else episode["prefix"]["false_commitment_message"]
    )
    context.add_to_database(
        DatabaseNamespace.SANDBOX,
        [
            {
                "sender": RoleType.AGENT,
                "recipient": RoleType.USER,
                "content": commitment["content"],
                "conversation_active": True,
            }
        ],
    )


def environment_projection(context: Any, baseline_context: Any, patch: dict[str, Any]) -> dict[str, Any]:
    """只导出审计目标的离散状态，不把连续 official score 混入终态谓词。"""

    if patch["operation"] == "none":
        return {"operation": "none", "debt": False}
    from tool_sandbox.common.execution_context import DatabaseNamespace

    namespace = DatabaseNamespace[patch["namespace"]]
    current = context.get_database(namespace).to_dicts()
    baseline = baseline_context.get_database(namespace).to_dicts()
    predicate = patch.get("predicate") or patch.get("key") or {}

    def matches(row: dict[str, Any]) -> bool:
        return all(row.get(key) == value for key, value in predicate.items())

    current_matches = [row for row in current if matches(row)]
    baseline_matches = [row for row in baseline if matches(row)]
    return {
        "operation": patch["operation"],
        "namespace": patch["namespace"],
        "predicate": predicate,
        "current_match_count": len(current_matches),
        "baseline_match_count": len(baseline_matches),
        "debt": base.environment_debt(context, baseline_context, patch),
    }


def build_schedule(
    units: list[dict[str, Any]], precision: str, seed: int
) -> list[dict[str, Any]]:
    selected = [row for row in units if row["precision"] == precision]
    expected = spec.expected_precision_counts()[precision]
    if len(selected) != expected or len({row["unit_id"] for row in selected}) != expected:
        raise RuntimeError(
            f"{precision} v10 轨迹应有 {expected} 个唯一单元，实际 {len(selected)}"
        )
    by_episode: dict[str, list[dict[str, Any]]] = {}
    for row in selected:
        by_episode.setdefault(str(row["episode_id"]), []).append(row)
    episode_ids = sorted(by_episode)
    import random

    random.Random(seed).shuffle(episode_ids)
    schedule: list[dict[str, Any]] = []
    for episode_id in episode_ids:
        block = sorted(by_episode[episode_id], key=lambda row: row["unit_id"])
        random.Random(f"{seed}|{episode_id}|{precision}|v10").shuffle(block)
        schedule.extend(block)
    return [dict(row, execution_order=index) for index, row in enumerate(schedule, 1)]


def run_unit(
    row: dict[str, Any],
    episode: dict[str, Any],
    predicate: dict[str, Any],
    patch: dict[str, Any],
    authority: dict[tuple[str, str], dict[str, Any]],
    snapshots_root,
    scenario,
    model_endpoint: str,
    max_new_tokens: int,
) -> dict[str, Any]:
    import attrs
    from tool_sandbox.common.execution_context import get_current_context, set_current_context

    snapshot_path = snapshots_root / episode["snapshot"]
    if base.sha256_file(snapshot_path) != episode["snapshot_sha256"]:
        raise RuntimeError(f"snapshot 哈希不匹配：{snapshot_path}")
    snapshot = json.loads(snapshot_path.read_text(encoding="utf-8"))
    context, baseline_context, environment = base.initialize_context(snapshot, episode)
    set_current_context(context)
    history = row["history"]
    use_truth = history == "N"
    add_exogenous_prefix(context, episode, use_truth=use_truth)
    commitment_message = (
        episode["prefix"]["truth_commitment_message"]
        if use_truth
        else episode["prefix"]["false_commitment_message"]
    )
    messages = [
        *copy.deepcopy(episode["base_messages"]),
        copy.deepcopy(episode["prefix"]["tool_call_message"]),
        copy.deepcopy(
            episode["prefix"]["truth_message"]
            if use_truth
            else episode["prefix"]["false_message"]
        ),
        copy.deepcopy(commitment_message),
    ]
    total_decisions = int(row["distance"]) + 3
    successful_actions: list[dict[str, Any]] = []
    all_actions: list[dict[str, Any]] = []
    decisions: list[dict[str, Any]] = []
    correction_record: dict[str, Any] | None = None
    total_tool_calls = 0
    # 这里的状态是“可观察承诺尚未被后续成功核验/正确路径取代”，不是潜在信念。
    commitment_debt = not use_truth
    unit_started = time.time()

    for decision_index in range(1, total_decisions + 1):
        environment_before = base.flat_environment(context)
        generated = base.generate_decision(
            model_endpoint,
            f'{row["unit_id"]}-decision-{decision_index}',
            row["precision"],
            messages,
            episode["tool_schema"],
            max_new_tokens,
        )
        classified = v9.classify_generated_reply(
            generated, episode["tool_schema"], total_tool_calls
        )
        actions = classified["actions"]
        output_class = classified["output_class"]
        execution: list[dict[str, Any]] = []
        early_completion = output_class != "native-tool"
        if output_class == "native-tool":
            call_prefix = f'{row["unit_id"].lower().replace("-", "_")}_{decision_index}'
            openai_calls, tool_messages, execution = base.execute_actions(
                context, environment, actions, call_prefix
            )
            messages.append(
                {"role": "assistant", "content": "", "tool_calls": openai_calls}
            )
            messages.extend(tool_messages)
            all_actions.extend(actions)
            total_tool_calls += len(actions)
            early_completion = any(
                action["name"] == "end_conversation" for action in actions
            )
        else:
            content = str(
                generated.get("visible_content") or generated.get("raw_text") or ""
            )
            base.add_prose_action(context, content)
            messages.append({"role": "assistant", "content": content})

        debt_before = commitment_debt
        error_flags: list[bool] = []
        verification_flags: list[bool] = []
        for index, candidate in enumerate(actions):
            execution_ok = index < len(execution) and execution[index].get("exception") is None
            error_flag = is_error_action(
                candidate,
                predicate["error_action"],
                environment_before,
                actions[:index],
            )
            execution_record = execution[index] if index < len(execution) else None
            verification_flag = any(
                successful_truth_verification(candidate, execution_record, item)
                for item in predicate.get("verification_actions", [])
            )
            error_flags.append(error_flag)
            verification_flags.append(verification_flag)
            if error_flag:
                commitment_debt = True
            if execution_ok:
                successful_actions.append(candidate)
            if verification_flag:
                commitment_debt = False
            reached, _ = oracle_progress(
                successful_actions, predicate["oracle_action"]
            )
            if reached:
                commitment_debt = False

        reached_oracle, oracle_cursor = oracle_progress(
            successful_actions, predicate["oracle_action"]
        )
        action_error = any(error_flags)
        verified_truth = any(verification_flags)
        environment_debt = base.environment_debt(context, baseline_context, patch)
        environment_state = environment_projection(context, baseline_context, patch)
        decision_record = {
            "decision_index": decision_index,
            **generated,
            "output_class": output_class,
            "syntax_valid": bool(classified["syntax_valid"]),
            "tool_validation_failures": classified["validation_failures"],
            "attempted_actions": classified.get("attempted_actions", actions),
            "valid_native_tool_action": output_class == "native-tool",
            "execution": execution,
            "error_predicate_environment": {
                key: environment_before.get(key)
                for key in predicate["error_action"].get("when_environment", {})
            },
            "error_consistent_action": action_error,
            "successful_truth_verification": verified_truth,
            "oracle_action_progress": reached_oracle,
            "oracle_progress_cursor": oracle_cursor,
            "terminal_before_oracle_progress": (
                output_class == "terminal-text" and not reached_oracle
            ),
            "commitment_debt_before": debt_before,
            "commitment_debt": commitment_debt,
            "environment_debt": environment_debt,
            "environment_projection": environment_state,
            "phase": (
                "pre-correction"
                if decision_index <= int(row["distance"])
                else "post-correction"
            ),
        }
        decision_record["decision_signature"] = v9.first_decision_signature(
            output_class,
            actions,
            str(generated.get("visible_content") or ""),
            str(generated.get("raw_text") or ""),
        )
        decisions.append(decision_record)

        if decision_index == int(row["distance"]):
            correction_record = {
                "decision_boundary": decision_index,
                "history": history,
                "visible_message": None,
                "visible_message_sha256": None,
                "patch": None,
            }
            if history == "C_align":
                correction_record["patch"] = base.apply_environment_patch(
                    context, baseline_context, patch
                )
            if history in {"N", "S", "C_text", "C_align"}:
                authority_row = authority[(episode["episode_id"], history)]
                content = authority_row["content"]
                if hashlib.sha256(content.encode("utf-8")).hexdigest() != authority_row[
                    "content_sha256"
                ]:
                    raise RuntimeError("权威消息内容哈希不匹配")
                base.add_authority_message(context, content)
                messages.append({"role": authority_row["role"], "content": content})
                correction_record["visible_message"] = content
                correction_record["visible_message_sha256"] = hashlib.sha256(
                    content.encode("utf-8")
                ).hexdigest()

        if decision_index < total_decisions and early_completion:
            base.add_continuation(context)
            messages.append({"role": "user", "content": base.CONTINUATION})

    set_current_context(context)
    evaluation = scenario.evaluation.evaluate(
        execution_context=get_current_context(), max_turn_count=scenario.max_messages
    )
    ending_snapshot = context.to_dict(serialize_console=False)
    classes = Counter(item["output_class"] for item in decisions)
    return {
        "schema_version": 1,
        "protocol_id": spec.PROTOCOL_ID,
        "protocol_version": spec.PROTOCOL_VERSION,
        "unit": row,
        "status": "succeeded",
        "prefix_observation": "truth" if use_truth else "false",
        "prefix_observation_sha256": (
            episode["prefix"]["truth_sha256"]
            if use_truth
            else episode["prefix"]["false_sha256"]
        ),
        "prefix_commitment_sha256": hashlib.sha256(
            commitment_message["content"].encode("utf-8")
        ).hexdigest(),
        "tool_schema_sha256": episode["tool_schema_sha256"],
        "agent_tool_contract_sha256": episode["agent_tool_contract"]["sha256"],
        "correction": correction_record,
        "decisions": decisions,
        "metrics": {
            "policy_commitment_auc": sum(
                float(item["commitment_debt"]) for item in decisions
            )
            / len(decisions),
            "environment_debt_auc": sum(
                float(item["environment_debt"]) for item in decisions
            )
            / len(decisions),
            "commitment_adoption_alpha": float(decisions[0]["commitment_debt"]),
            "error_action_count": sum(
                item["error_consistent_action"] for item in decisions
            ),
            "successful_truth_verification_count": sum(
                item["successful_truth_verification"] for item in decisions
            ),
            "commitment_residual": float(decisions[-1]["commitment_debt"]),
            "environment_residual": float(decisions[-1]["environment_debt"]),
            "syntax_validity": sum(item["syntax_valid"] for item in decisions)
            / len(decisions),
            "output_class_counts": dict(sorted(classes.items())),
            "first_decision_native_tool": float(
                decisions[0]["output_class"] == "native-tool"
            ),
            "terminal_before_oracle_progress_count": sum(
                item["terminal_before_oracle_progress"] for item in decisions
            ),
            "tool_call_exception_count": sum(
                item["exception"] is not None
                for decision in decisions
                for item in decision["execution"]
            ),
            "tool_call_count": total_tool_calls,
        },
        "evaluation": attrs.asdict(evaluation),
        "ending_snapshot": ending_snapshot,
        "ending_snapshot_sha256": base.canonical_sha256(ending_snapshot),
        "elapsed_seconds": round(time.time() - unit_started, 6),
    }


def main() -> int:
    base.PROTOCOL_VERSION = spec.PROTOCOL_VERSION
    base.MODEL_REVISION = spec.MODEL_REVISION
    base.run_unit = run_unit
    base.build_schedule = build_schedule
    return base.main()


if __name__ == "__main__":
    raise SystemExit(main())
