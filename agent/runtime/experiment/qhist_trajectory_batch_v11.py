#!/usr/bin/env python3
"""执行 Q-HIST v11：共享错误 trunk 后分叉，并保存 F/V/G/B/E/T 证据。"""

from __future__ import annotations

import argparse
import ast
import copy
import gc
import hashlib
import json
import os
import random
import re
import sys
import time
import traceback
import uuid
from collections import Counter
from pathlib import Path
from typing import Any

import qhist_trajectory_batch_v10 as previous
import qhist_v11_spec as spec


v9 = previous.v9
base = previous.base
UUID_RE = re.compile(
    r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-"
    r"[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$"
)


class DeterministicUUID4:
    """为一个冻结逻辑段生成可复现 UUID；precision 与 repeat 不进入 key。"""

    def __init__(self, logical_key: str):
        self.logical_key = logical_key
        self.counter = 0

    def __call__(self) -> uuid.UUID:
        self.counter += 1
        return uuid.uuid5(
            uuid.NAMESPACE_URL,
            f"QHIST-v11|{self.logical_key}|{self.counter}",
        )


def install_uuid_provider(provider: DeterministicUUID4) -> None:
    import tool_sandbox.tools.contact as contact
    import tool_sandbox.tools.messaging as messaging
    import tool_sandbox.tools.reminder as reminder

    contact.uuid4 = provider
    messaging.uuid4 = provider
    reminder.uuid4 = provider


def logical_segment_key(
    episode_id: str, distance: int, history: str, phase: str
) -> str:
    return f"{episode_id}|d{distance}|{history}|{phase}"


def stable_call_prefix(logical_key: str, decision_index: int) -> str:
    digest = hashlib.sha256(logical_key.encode("utf-8")).hexdigest()[:16]
    return f"q11_{digest}_{decision_index}"


def predicate_matches(
    candidate: dict[str, Any],
    predicate: dict[str, Any],
    environment: dict[str, Any] | None = None,
    bindings: dict[str, Any] | None = None,
) -> bool:
    if not base.action_matches(candidate, predicate, environment or {}):
        return False
    binding_rule = predicate.get("binding_argument")
    if binding_rule:
        argument = str(binding_rule["argument"])
        binding = str(binding_rule["binding"])
        if binding not in (bindings or {}):
            return False
        if (candidate.get("arguments") or {}).get(argument) != (bindings or {})[binding]:
            return False
    return True


def is_error_action(
    candidate: dict[str, Any],
    predicate: dict[str, Any],
    environment_before_reply: dict[str, Any],
    preceding_actions_in_reply: list[dict[str, Any]],
    preceding_execution_records: list[dict[str, Any]],
    bindings: dict[str, Any],
) -> bool:
    if not predicate_matches(
        candidate, predicate, environment_before_reply, bindings
    ):
        return False
    blocker = predicate.get("unless_preceded_by")
    if blocker:
        for index, action in enumerate(preceding_actions_in_reply):
            record = (
                preceding_execution_records[index]
                if index < len(preceding_execution_records)
                else None
            )
            if (
                predicate_matches(
                    action, blocker, environment_before_reply, bindings
                )
                and record is not None
                and record.get("exception") is None
            ):
                return False
    return True


def successful_truth_verification(
    candidate: dict[str, Any],
    execution_record: dict[str, Any] | None,
    predicate: dict[str, Any],
) -> bool:
    if execution_record is None or execution_record.get("exception") is not None:
        return False
    if not predicate_matches(candidate, predicate):
        return False
    if "expected_result" not in predicate:
        return False
    try:
        observed = ast.literal_eval(str(execution_record.get("content") or ""))
    except (SyntaxError, ValueError):
        return False
    return observed == predicate["expected_result"]


def successful_frozen_action(
    candidate: dict[str, Any],
    execution_record: dict[str, Any] | None,
    predicates: list[dict[str, Any]],
    bindings: dict[str, Any],
) -> bool:
    return (
        execution_record is not None
        and execution_record.get("exception") is None
        and any(
            predicate_matches(candidate, frozen, bindings=bindings)
            for frozen in predicates
        )
    )


def parse_execution_value(execution_record: dict[str, Any] | None) -> Any:
    if execution_record is None or execution_record.get("exception") is not None:
        return None
    try:
        return ast.literal_eval(str(execution_record.get("content") or ""))
    except (SyntaxError, ValueError):
        return None


def add_exogenous_prefix(
    context: Any, episode: dict[str, Any], use_truth: bool
) -> None:
    previous.add_exogenous_prefix(context, episode, use_truth)


def environment_projection(
    context: Any, baseline_context: Any, patch: dict[str, Any]
) -> dict[str, Any]:
    return previous.environment_projection(context, baseline_context, patch)


def build_schedule(
    units: list[dict[str, Any]], precision: str, seed: int
) -> list[dict[str, Any]]:
    selected = [row for row in units if row["precision"] == precision]
    expected = spec.expected_precision_counts()[precision]
    if len(selected) != expected or len({row["unit_id"] for row in selected}) != expected:
        raise RuntimeError(
            f"{precision} v11 轨迹应有 {expected} 个唯一逻辑单元，实际 {len(selected)}"
        )
    groups: dict[tuple[str, int, int], list[dict[str, Any]]] = {}
    for row in selected:
        key = (str(row["episode_id"]), int(row["distance"]), int(row["repeat"]))
        groups.setdefault(key, []).append(row)
    keys = sorted(groups)
    random.Random(seed).shuffle(keys)
    schedule: list[dict[str, Any]] = []
    for key in keys:
        block = sorted(groups[key], key=lambda row: row["unit_id"])
        random.Random(f"{seed}|{key}|{precision}|v11").shuffle(block)
        schedule.extend(block)
    return [dict(row, execution_order=index) for index, row in enumerate(schedule, 1)]


def load_initial_state(
    row: dict[str, Any],
    episode: dict[str, Any],
    snapshots_root: Path,
    use_truth: bool,
    logical_key: str,
) -> dict[str, Any]:
    from tool_sandbox.common.execution_context import set_current_context

    snapshot_path = snapshots_root / episode["snapshot"]
    if base.sha256_file(snapshot_path) != episode["snapshot_sha256"]:
        raise RuntimeError(f"snapshot 哈希不匹配：{snapshot_path}")
    initial_snapshot = json.loads(snapshot_path.read_text(encoding="utf-8"))
    context, baseline_context, environment = base.initialize_context(
        initial_snapshot, episode
    )
    set_current_context(context)
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
    provider = DeterministicUUID4(logical_key)
    install_uuid_provider(provider)
    return {
        "context": context,
        "baseline_context": baseline_context,
        "initial_snapshot": initial_snapshot,
        "environment": environment,
        "messages": messages,
        "successful_actions": [],
        "all_actions": [],
        "decisions": [],
        "total_tool_calls": 0,
        "commitment_debt": not use_truth,
        "bindings": copy.deepcopy(episode.get("dynamic_roles") or {}),
        "recovery_reached": False,
        "goal_completed": False,
        "correction": None,
        "uuid_provider": provider,
        "logical_key": logical_key,
        "prefix_observation": "truth" if use_truth else "false",
        "commitment_message": commitment_message,
        "started": time.time(),
        "last_early_completion": False,
    }


def clone_from_trunk(
    trunk: dict[str, Any],
    episode: dict[str, Any],
    logical_key: str,
) -> dict[str, Any]:
    from tool_sandbox.common.execution_context import set_current_context
    from tool_sandbox.roles.execution_environment import ExecutionEnvironment

    # ExecutionContext 的自定义 deepcopy 使用 dill，并连同已加载工具的
    # InteractiveConsole 一起克隆；普通 JSON snapshot 不含 console，不能用于
    # 可继续执行的 fork。环境角色本身无状态，后续读取当前克隆 context。
    context = copy.deepcopy(trunk["context"])
    baseline_context = copy.deepcopy(trunk["baseline_context"])
    set_current_context(context)
    environment = ExecutionEnvironment()
    provider = DeterministicUUID4(logical_key)
    install_uuid_provider(provider)
    state = {
        key: copy.deepcopy(value)
        for key, value in trunk.items()
        if key
        not in {
            "context",
            "baseline_context",
            "environment",
            "uuid_provider",
            "started",
        }
    }
    state.update(
        {
            "context": context,
            "baseline_context": baseline_context,
            "environment": environment,
            "uuid_provider": provider,
            "logical_key": logical_key,
            "started": time.time(),
        }
    )
    return state


def inject_boundary_treatment(
    state: dict[str, Any],
    row: dict[str, Any],
    episode: dict[str, Any],
    patch: dict[str, Any],
    authority: dict[tuple[str, str], dict[str, Any]],
) -> None:
    from tool_sandbox.common.execution_context import set_current_context

    context = state["context"]
    set_current_context(context)
    history = str(row["history"])
    record: dict[str, Any] = {
        "decision_boundary": int(row["distance"]),
        "history": history,
        "visible_message": None,
        "visible_message_sha256": None,
        "patch": None,
    }
    if history == "C_align":
        record["patch"] = base.apply_environment_patch(
            context, state["baseline_context"], patch
        )
    if history in {"N", "S", "C_text", "C_align"}:
        authority_row = authority[(episode["episode_id"], history)]
        content = authority_row["content"]
        actual_hash = hashlib.sha256(content.encode("utf-8")).hexdigest()
        if actual_hash != authority_row["content_sha256"]:
            raise RuntimeError("权威消息内容哈希不匹配")
        base.add_authority_message(context, content)
        state["messages"].append(
            {"role": authority_row["role"], "content": content}
        )
        record["visible_message"] = content
        record["visible_message_sha256"] = actual_hash
    state["correction"] = record
    if state["last_early_completion"]:
        base.add_continuation(context)
        state["messages"].append({"role": "user", "content": base.CONTINUATION})


def advance_decision(
    state: dict[str, Any],
    row: dict[str, Any],
    episode: dict[str, Any],
    predicate: dict[str, Any],
    patch: dict[str, Any],
    model_endpoint: str,
    max_new_tokens: int,
    decision_index: int,
    request_counter: dict[str, int],
) -> None:
    from tool_sandbox.common.execution_context import set_current_context

    context = state["context"]
    environment = state["environment"]
    set_current_context(context)
    install_uuid_provider(state["uuid_provider"])
    environment_before = base.flat_environment(context)
    request_id = (
        f"QH11-{row['precision']}-{row['episode_id']}-"
        f"d{row['distance']}-{state['logical_key']}-"
        f"r{row['repeat']}-decision-{decision_index}"
    )
    generated = base.generate_decision(
        model_endpoint,
        request_id,
        row["precision"],
        state["messages"],
        episode["tool_schema"],
        max_new_tokens,
    )
    request_counter["value"] += 1
    classified = v9.classify_generated_reply(
        generated, episode["tool_schema"], state["total_tool_calls"]
    )
    actions = classified["actions"]
    output_class = classified["output_class"]
    execution: list[dict[str, Any]] = []
    early_completion = output_class != "native-tool"
    if output_class == "native-tool":
        call_prefix = stable_call_prefix(state["logical_key"], decision_index)
        openai_calls, tool_messages, execution = base.execute_actions(
            context, environment, actions, call_prefix
        )
        state["messages"].append(
            {"role": "assistant", "content": "", "tool_calls": openai_calls}
        )
        state["messages"].extend(tool_messages)
        state["all_actions"].extend(actions)
        state["total_tool_calls"] += len(actions)
        early_completion = any(
            action["name"] == "end_conversation" for action in actions
        )
    else:
        content = str(
            generated.get("visible_content") or generated.get("raw_text") or ""
        )
        base.add_prose_action(context, content)
        state["messages"].append({"role": "assistant", "content": content})

    debt_before = bool(state["commitment_debt"])
    error_flags: list[bool] = []
    verification_flags: list[bool] = []
    recovery_flags: list[bool] = []
    completion_flags: list[bool] = []
    for index, candidate in enumerate(actions):
        execution_record = execution[index] if index < len(execution) else None
        execution_ok = (
            execution_record is not None
            and execution_record.get("exception") is None
        )
        error_flag = is_error_action(
            candidate,
            predicate["error_action"],
            environment_before,
            actions[:index],
            execution[:index],
            state["bindings"],
        )
        if (
            error_flag
            and execution_ok
            and predicate["error_action"].get("binds_success_result")
        ):
            value = parse_execution_value(execution_record)
            if value is not None:
                state["bindings"][
                    str(predicate["error_action"]["binds_success_result"])
                ] = value
        verification_flag = any(
            successful_truth_verification(candidate, execution_record, item)
            for item in predicate.get("verification_actions", [])
        )
        recovery_flag = successful_frozen_action(
            candidate,
            execution_record,
            predicate.get("recovery_actions", []),
            state["bindings"],
        )
        completion_flag = successful_frozen_action(
            candidate,
            execution_record,
            predicate.get("completion_actions", []),
            state["bindings"],
        )
        error_flags.append(error_flag)
        verification_flags.append(verification_flag)
        recovery_flags.append(recovery_flag)
        completion_flags.append(completion_flag)
        if execution_ok:
            state["successful_actions"].append(candidate)
        # 事件按真实动作顺序更新；后到 F 可重新激活已经清除的债务。
        if verification_flag or recovery_flag:
            state["commitment_debt"] = False
        if error_flag:
            state["commitment_debt"] = True
        state["recovery_reached"] = bool(
            state["recovery_reached"] or recovery_flag
        )
        state["goal_completed"] = bool(
            state["goal_completed"] or completion_flag
        )

    action_error = any(error_flags)
    verified_truth = any(verification_flags)
    recovery = any(recovery_flags)
    goal_completion = any(completion_flags)
    environment_debt = base.environment_debt(
        context, state["baseline_context"], patch
    )
    environment_state = environment_projection(
        context, state["baseline_context"], patch
    )
    oracle_reached, oracle_cursor = previous.oracle_progress(
        state["successful_actions"], predicate["oracle_action"]
    )
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
        "successful_recovery_certificate": recovery,
        "successful_goal_completion": goal_completion,
        "recovery_reached": bool(state["recovery_reached"]),
        "goal_completed": bool(state["goal_completed"]),
        "oracle_action_progress": oracle_reached,
        "oracle_progress_cursor": oracle_cursor,
        "terminal_before_goal_completion": (
            output_class == "terminal-text" and not state["goal_completed"]
        ),
        "commitment_debt_before": debt_before,
        "commitment_debt": bool(state["commitment_debt"]),
        "environment_debt": environment_debt,
        "environment_projection": environment_state,
        "dynamic_bindings": copy.deepcopy(state["bindings"]),
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
    state["decisions"].append(decision_record)
    state["last_early_completion"] = early_completion


def add_pre_boundary_continuation(state: dict[str, Any]) -> None:
    if state["last_early_completion"]:
        base.add_continuation(state["context"])
        state["messages"].append({"role": "user", "content": base.CONTINUATION})


def pre_boundary_artifact(state: dict[str, Any]) -> dict[str, Any]:
    snapshot = state["context"].to_dict(serialize_console=False)
    payload = {
        "messages": state["messages"],
        "context_snapshot_sha256": base.canonical_sha256(snapshot),
        "decisions": [
            {
                "decision_index": row["decision_index"],
                "decision_signature": row["decision_signature"],
                "error_consistent_action": row["error_consistent_action"],
                "successful_truth_verification": row[
                    "successful_truth_verification"
                ],
                "successful_recovery_certificate": row[
                    "successful_recovery_certificate"
                ],
                "commitment_debt": row["commitment_debt"],
                "environment_debt": row["environment_debt"],
            }
            for row in state["decisions"]
        ],
        "bindings": state["bindings"],
        "total_tool_calls": state["total_tool_calls"],
    }
    return {
        "artifact_sha256": base.canonical_sha256(payload),
        "messages_sha256": base.canonical_sha256(state["messages"]),
        "context_snapshot_sha256": payload["context_snapshot_sha256"],
        "decision_prefix_sha256": base.canonical_sha256(payload["decisions"]),
        "bindings_sha256": base.canonical_sha256(state["bindings"]),
        "total_tool_calls": state["total_tool_calls"],
    }


def normalize_dynamic_ids(value: Any, roles: dict[str, str]) -> Any:
    if isinstance(value, dict):
        return {
            key: normalize_dynamic_ids(child, roles)
            for key, child in sorted(value.items())
        }
    if isinstance(value, list):
        return [normalize_dynamic_ids(child, roles) for child in value]
    if isinstance(value, str):
        if value in roles:
            return {"opaque_role": roles[value]}
        return value
    return value


def scientific_signature(
    state: dict[str, Any], episode: dict[str, Any]
) -> tuple[str, dict[str, Any]]:
    roles: dict[str, str] = {}
    for role, value in (episode.get("dynamic_roles") or {}).items():
        if isinstance(value, str):
            roles[value] = role
    for role, value in state["bindings"].items():
        if isinstance(value, str):
            roles[value] = role
    decision_rows = []
    goal_seen = False
    for row in state["decisions"]:
        # 首次正确完成后的纯文本措辞是 nuisance；任何后续工具动作仍可能
        # 重新制造 F/E，必须进入科学签名而不能被“任务已完成”掩盖。
        if goal_seen and row["output_class"] != "native-tool":
            continue
        attempted = normalize_dynamic_ids(row["attempted_actions"], roles)
        decision_rows.append(
            {
                "decision_index": row["decision_index"],
                "output_class": row["output_class"],
                "attempted_actions": attempted,
                "execution_success": [
                    item.get("exception") is None for item in row["execution"]
                ],
                "error_consistent_action": row["error_consistent_action"],
                "successful_truth_verification": row[
                    "successful_truth_verification"
                ],
                "successful_recovery_certificate": row[
                    "successful_recovery_certificate"
                ],
                "successful_goal_completion": row[
                    "successful_goal_completion"
                ],
                "commitment_debt": row["commitment_debt"],
                "environment_debt": row["environment_debt"],
                "goal_completed": row["goal_completed"],
                "terminal_before_goal_completion": row[
                    "terminal_before_goal_completion"
                ],
                "pre_goal_terminal_text_sha256": (
                    row["decision_signature"]
                    if row["output_class"] != "native-tool"
                    else None
                ),
            }
        )
        goal_seen = bool(goal_seen or row["goal_completed"])
    payload = {
        "prefix_observation": state["prefix_observation"],
        "correction_message_sha256": (
            (state["correction"] or {}).get("visible_message_sha256")
        ),
        "correction_patch_operation": (
            ((state["correction"] or {}).get("patch") or {}).get("operation")
        ),
        "decisions_through_first_goal_completion_plus_later_tool_actions": decision_rows,
    }
    return base.canonical_sha256(payload), payload


def finalize_result(
    state: dict[str, Any],
    row: dict[str, Any],
    episode: dict[str, Any],
    scenario: Any,
    pre_boundary: dict[str, Any],
) -> dict[str, Any]:
    import attrs
    from tool_sandbox.common.execution_context import get_current_context, set_current_context

    set_current_context(state["context"])
    evaluation = scenario.evaluation.evaluate(
        execution_context=get_current_context(), max_turn_count=scenario.max_messages
    )
    ending_snapshot = state["context"].to_dict(serialize_console=False)
    decisions = state["decisions"]
    classes = Counter(item["output_class"] for item in decisions)
    signature_hash, signature_payload = scientific_signature(state, episode)
    return {
        "schema_version": 1,
        "protocol_id": spec.PROTOCOL_ID,
        "protocol_version": spec.PROTOCOL_VERSION,
        "unit": row,
        "status": "succeeded",
        "prefix_observation": state["prefix_observation"],
        "prefix_observation_sha256": (
            episode["prefix"]["truth_sha256"]
            if state["prefix_observation"] == "truth"
            else episode["prefix"]["false_sha256"]
        ),
        "prefix_commitment_sha256": hashlib.sha256(
            state["commitment_message"]["content"].encode("utf-8")
        ).hexdigest(),
        "tool_schema_sha256": episode["tool_schema_sha256"],
        "agent_tool_contract_sha256": episode["agent_tool_contract"]["sha256"],
        "pre_boundary_artifact": pre_boundary,
        "correction": state["correction"],
        "decisions": decisions,
        "scientific_signature": {
            "sha256": signature_hash,
            "payload": signature_payload,
            "excludes": [
                "raw UUID spelling after role normalization",
                "free prose, but not tool actions, after first successful goal completion",
                "continuous official similarity",
            ],
        },
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
            "successful_recovery_certificate_count": sum(
                item["successful_recovery_certificate"] for item in decisions
            ),
            "successful_goal_completion_count": sum(
                item["successful_goal_completion"] for item in decisions
            ),
            "recovery_certificate_coverage": float(state["recovery_reached"]),
            "goal_completion_coverage": float(state["goal_completed"]),
            "commitment_residual": float(decisions[-1]["commitment_debt"]),
            "environment_residual": float(decisions[-1]["environment_debt"]),
            "syntax_validity": sum(item["syntax_valid"] for item in decisions)
            / len(decisions),
            "output_class_counts": dict(sorted(classes.items())),
            "first_decision_native_tool": float(
                decisions[0]["output_class"] == "native-tool"
            ),
            "terminal_before_goal_completion_count": sum(
                item["terminal_before_goal_completion"] for item in decisions
            ),
            "tool_call_exception_count": sum(
                item["exception"] is not None
                for decision in decisions
                for item in decision["execution"]
            ),
            "tool_call_count": state["total_tool_calls"],
        },
        "evaluation": attrs.asdict(evaluation),
        "ending_snapshot": ending_snapshot,
        "ending_snapshot_sha256": base.canonical_sha256(ending_snapshot),
        "elapsed_seconds": round(time.time() - state["started"], 6),
    }


def run_group(
    rows: list[dict[str, Any]],
    episode: dict[str, Any],
    predicate: dict[str, Any],
    patch: dict[str, Any],
    authority: dict[tuple[str, str], dict[str, Any]],
    snapshots_root: Path,
    scenario: Any,
    model_endpoint: str,
    max_new_tokens: int,
    request_counter: dict[str, int],
) -> dict[str, dict[str, Any]]:
    if not rows:
        return {}
    distances = {int(row["distance"]) for row in rows}
    repeats = {int(row["repeat"]) for row in rows}
    episodes = {str(row["episode_id"]) for row in rows}
    if len(distances) != 1 or len(repeats) != 1 or len(episodes) != 1:
        raise RuntimeError("fork group 的 episode/distance/repeat 必须唯一")
    distance = next(iter(distances))
    histories = {str(row["history"]) for row in rows}
    if len(histories) != len(rows):
        raise RuntimeError("fork group 不得重复 history")
    by_history = {str(row["history"]): row for row in rows}
    results: dict[str, dict[str, Any]] = {}

    if "N" in by_history:
        row = by_history["N"]
        logical_key = logical_segment_key(
            episode["episode_id"], distance, "N", "all"
        )
        state = load_initial_state(
            row, episode, snapshots_root, True, logical_key
        )
        boundary = None
        for decision_index in range(1, distance + 4):
            advance_decision(
                state,
                row,
                episode,
                predicate,
                patch,
                model_endpoint,
                max_new_tokens,
                decision_index,
                request_counter,
            )
            if decision_index == distance:
                boundary = pre_boundary_artifact(state)
                inject_boundary_treatment(
                    state, row, episode, patch, authority
                )
            elif decision_index < distance:
                add_pre_boundary_continuation(state)
            elif decision_index < distance + 3 and state["last_early_completion"]:
                add_pre_boundary_continuation(state)
        if boundary is None:
            raise RuntimeError("N 分支未生成边界 artifact")
        results[row["unit_id"]] = finalize_result(
            state, row, episode, scenario, boundary
        )

    erroneous = [
        row for history, row in by_history.items() if history != "N"
    ]
    if erroneous:
        representative = sorted(erroneous, key=lambda row: row["unit_id"])[0]
        trunk_key = logical_segment_key(
            episode["episode_id"], distance, "ERR", "trunk"
        )
        trunk = load_initial_state(
            representative, episode, snapshots_root, False, trunk_key
        )
        for decision_index in range(1, distance + 1):
            advance_decision(
                trunk,
                representative,
                episode,
                predicate,
                patch,
                model_endpoint,
                max_new_tokens,
                decision_index,
                request_counter,
            )
            if decision_index < distance:
                add_pre_boundary_continuation(trunk)
        boundary = pre_boundary_artifact(trunk)
        for row in sorted(erroneous, key=lambda item: item["unit_id"]):
            history = str(row["history"])
            branch_key = logical_segment_key(
                episode["episode_id"], distance, history, "post"
            )
            state = clone_from_trunk(trunk, episode, branch_key)
            inject_boundary_treatment(state, row, episode, patch, authority)
            for decision_index in range(distance + 1, distance + 4):
                advance_decision(
                    state,
                    row,
                    episode,
                    predicate,
                    patch,
                    model_endpoint,
                    max_new_tokens,
                    decision_index,
                    request_counter,
                )
                if (
                    decision_index < distance + 3
                    and state["last_early_completion"]
                ):
                    add_pre_boundary_continuation(state)
            results[row["unit_id"]] = finalize_result(
                state, row, episode, scenario, boundary
            )
    return results


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--precision", choices=spec.TREATMENT_PRECISIONS, required=True)
    parser.add_argument("--assets", type=Path, required=True)
    parser.add_argument("--rendered", type=Path, required=True)
    parser.add_argument("--model-endpoint", required=True)
    parser.add_argument("--toolsandbox-source", type=Path, required=True)
    parser.add_argument("--toolsandbox-site-packages", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--seed", type=int, default=spec.SCHEDULE_SEED)
    parser.add_argument("--max-new-tokens", type=int, default=256)
    args = parser.parse_args()
    if args.output.exists() and any(args.output.iterdir()):
        raise RuntimeError(f"输出目录必须不存在或为空：{args.output}")
    args.output.mkdir(parents=True, exist_ok=True)

    base.PROTOCOL_VERSION = spec.PROTOCOL_VERSION
    base.MODEL_REVISION = spec.MODEL_REVISION
    runtime = base.prepare_toolsandbox(
        args.toolsandbox_source, args.toolsandbox_site_packages
    )
    from tool_sandbox.common.tool_discovery import ToolBackend
    from tool_sandbox.scenarios import named_scenarios

    started = time.time()
    summary: dict[str, Any] = {
        "schema_version": 1,
        "protocol_id": spec.PROTOCOL_ID,
        "protocol_version": spec.PROTOCOL_VERSION,
        "status": "running",
        "precision": args.precision,
        "seed": args.seed,
        "runtime": runtime,
        "software": {"python": sys.version},
        "model_endpoint": args.model_endpoint,
        "execution_design": "shared-erroneous-trunk-boundary-fork",
    }
    exit_code = 1
    try:
        asset_manifest = base.verify_manifest(args.assets)
        rendered_manifest = base.verify_manifest(args.rendered, require_checks=True)
        episodes = {
            row["episode_id"]: row
            for row in base.read_jsonl(args.assets / "episodes.jsonl")
        }
        predicates = {
            row["episode_id"]: row
            for row in base.read_jsonl(args.assets / "predicates.jsonl")
        }
        patches = {
            row["episode_id"]: row
            for row in base.read_jsonl(args.assets / "environment-patches.jsonl")
        }
        units = base.read_jsonl(args.assets / "trajectory-units.jsonl")
        authority = {
            (row["episode_id"], row["condition"]): row
            for row in base.read_jsonl(args.rendered / "authority-messages.jsonl")
        }
        schedule = build_schedule(units, args.precision, args.seed)
        base.write_json(args.output / "schedule.json", schedule)
        scenarios = named_scenarios(preferred_tool_backend=ToolBackend.DEFAULT)

        grouped: dict[tuple[str, int, int], list[dict[str, Any]]] = {}
        group_order: list[tuple[str, int, int]] = []
        for row in schedule:
            key = (
                str(row["episode_id"]),
                int(row["distance"]),
                int(row["repeat"]),
            )
            if key not in grouped:
                group_order.append(key)
            grouped.setdefault(key, []).append(row)

        request_counter = {"value": 0}
        unit_successes = 0
        invalid_units = 0
        attempted_units = 0
        for key in group_order:
            rows = grouped[key]
            try:
                group_results = run_group(
                    rows,
                    episodes[key[0]],
                    predicates[key[0]],
                    patches[key[0]],
                    authority,
                    args.assets,
                    scenarios[rows[0]["scenario"]],
                    args.model_endpoint,
                    args.max_new_tokens,
                    request_counter,
                )
            except Exception as error:
                group_results = {
                    row["unit_id"]: {
                        "schema_version": 1,
                        "protocol_id": spec.PROTOCOL_ID,
                        "protocol_version": spec.PROTOCOL_VERSION,
                        "unit": row,
                        "status": "invalid",
                        "error_type": type(error).__name__,
                        "error": str(error),
                        "traceback": traceback.format_exc(),
                    }
                    for row in rows
                }
            for row in sorted(rows, key=lambda item: item["execution_order"]):
                attempted_units += 1
                result = group_results[row["unit_id"]]
                unit_path = args.output / "units" / f"{row['unit_id']}.json"
                base.write_json(unit_path, result)
                if result["status"] == "succeeded":
                    unit_successes += 1
                else:
                    invalid_units += 1
                base.append_jsonl(
                    args.output / "results.jsonl",
                    {
                        "unit_id": row["unit_id"],
                        "status": result["status"],
                        "artifact": str(unit_path.relative_to(args.output)).replace(
                            "\\", "/"
                        ),
                        "artifact_sha256": base.sha256_file(unit_path),
                        "metrics": result.get("metrics"),
                        "scientific_signature_sha256": (
                            (result.get("scientific_signature") or {}).get("sha256")
                        ),
                        "pre_boundary_artifact_sha256": (
                            (result.get("pre_boundary_artifact") or {}).get(
                                "artifact_sha256"
                            )
                        ),
                        "elapsed_seconds": result.get("elapsed_seconds"),
                        "error_type": result.get("error_type"),
                        "error": result.get("error"),
                    },
                )
            gc.collect()
            if any(
                result["status"] == "invalid"
                for result in group_results.values()
            ):
                break

        expected_requests = spec.expected_unique_request_counts()[args.precision]
        request_count_ok = (
            invalid_units == 0 and request_counter["value"] == expected_requests
        )
        if invalid_units == 0 and not request_count_ok:
            invalid_units = 1
        summary.update(
            {
                "status": (
                    "succeeded"
                    if invalid_units == 0 and request_count_ok
                    else "failed"
                ),
                "expected_logical_units": len(schedule),
                "completed_logical_units": attempted_units,
                "succeeded_logical_units": unit_successes,
                "invalid_logical_units": invalid_units,
                "fork_groups": len(group_order),
                "unique_model_requests": request_counter["value"],
                "expected_unique_model_requests": expected_requests,
                "unique_model_request_count_ok": request_count_ok,
                "schedule_sha256": base.sha256_file(args.output / "schedule.json"),
                "results_sha256": base.sha256_file(args.output / "results.jsonl"),
                "asset_manifest_sha256": base.sha256_file(
                    args.assets / "manifest.json"
                ),
                "rendered_manifest_sha256": base.sha256_file(
                    args.rendered / "manifest.json"
                ),
                "asset_manifest_protocol": asset_manifest["protocol_version"],
                "rendered_manifest_protocol": rendered_manifest["protocol_version"],
            }
        )
        exit_code = 0 if summary["status"] == "succeeded" else 1
    except Exception as error:
        summary.update(
            {
                "status": "failed",
                "error_type": type(error).__name__,
                "error": str(error),
                "traceback": traceback.format_exc(),
            }
        )
    finally:
        summary["elapsed_seconds"] = round(time.time() - started, 6)
        base.write_json(args.output / "summary.json", summary)
        print(json.dumps(summary, ensure_ascii=False, indent=2, default=str))
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
