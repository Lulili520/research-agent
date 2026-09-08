#!/usr/bin/env python3
"""执行 Q-HIST v14：首决策前冻结 A/R/E checkpoint，随后恰好四个决策。"""

from __future__ import annotations

import argparse
import ast
import copy
import gc
import hashlib
import json
import random
import sys
import time
import traceback
import uuid
from collections import Counter
from pathlib import Path
from typing import Any

import qhist_trajectory_batch as base
import qhist_trajectory_batch_v9 as parser
import qhist_v14_spec as spec


class DeterministicUUID4:
    """目标动作的 opaque ID；precision 与 technical repeat 不进入 key。"""

    def __init__(self, logical_key: str, predecessor: bool = False):
        self.logical_key = logical_key
        self.predecessor = predecessor
        self.counter = 0

    def __call__(self) -> uuid.UUID:
        self.counter += 1
        if self.predecessor:
            payload = f"QHIST-v14|{self.logical_key}|predecessor|{self.counter}"
        else:
            payload = f"QHIST-v14|{self.logical_key}|target|{self.counter}"
        return uuid.uuid5(uuid.NAMESPACE_URL, payload)


def install_uuid_provider(provider: DeterministicUUID4) -> None:
    import tool_sandbox.tools.contact as contact
    import tool_sandbox.tools.messaging as messaging
    import tool_sandbox.tools.reminder as reminder

    contact.uuid4 = provider
    messaging.uuid4 = provider
    reminder.uuid4 = provider


def logical_key(row: dict[str, Any]) -> str:
    return (
        f'{row["episode_id"]}|{row["module"]}|{row["condition"]}|g{row["gap"]}'
    )


def stable_call_prefix(key: str, decision_index: int) -> str:
    digest = hashlib.sha256(key.encode("utf-8")).hexdigest()[:16]
    return f"q12_{digest}_{decision_index}"


def parse_value(execution: dict[str, Any] | None) -> Any:
    if execution is None or execution.get("exception") is not None:
        return None
    try:
        return ast.literal_eval(str(execution.get("content") or ""))
    except (SyntaxError, ValueError):
        return execution.get("content")


def predicate_matches(
    candidate: dict[str, Any],
    predicate: dict[str, Any],
    bindings: dict[str, Any],
) -> bool:
    if candidate.get("name") != predicate.get("tool"):
        return False
    arguments = candidate.get("arguments") or {}
    if any(
        arguments.get(field) != value
        for field, value in predicate.get("arguments_contains", {}).items()
    ):
        return False
    if any(
        str(arguments.get(field, "")).casefold() != str(value).casefold()
        for field, value in predicate.get("arguments_casefold", {}).items()
    ):
        return False
    binding = predicate.get("binding_argument")
    if binding:
        if binding["binding"] not in bindings:
            return False
        if arguments.get(binding["argument"]) != bindings[binding["binding"]]:
            return False
    return True


def error_action(
    candidate: dict[str, Any],
    predicate: dict[str, Any],
    environment: dict[str, Any],
    prior_actions: list[dict[str, Any]],
    prior_execution: list[dict[str, Any]],
    bindings: dict[str, Any],
) -> bool:
    if not predicate_matches(candidate, predicate, bindings):
        return False
    if any(
        environment.get(field) != value
        for field, value in predicate.get("when_environment", {}).items()
    ):
        return False
    blocker = predicate.get("unless_preceded_by")
    if blocker:
        for index, previous in enumerate(prior_actions):
            execution = prior_execution[index] if index < len(prior_execution) else None
            if (
                predicate_matches(previous, blocker, bindings)
                and execution is not None
                and execution.get("exception") is None
            ):
                return False
    return True


def successful_verification(
    candidate: dict[str, Any],
    execution: dict[str, Any] | None,
    frozen: dict[str, Any],
    bindings: dict[str, Any],
) -> bool:
    return (
        execution is not None
        and execution.get("exception") is None
        and predicate_matches(candidate, frozen, bindings)
        and "expected_result" in frozen
        and parse_value(execution) == frozen["expected_result"]
    )


def successful_frozen_action(
    candidate: dict[str, Any],
    execution: dict[str, Any] | None,
    predicates: list[dict[str, Any]],
    bindings: dict[str, Any],
) -> bool:
    return (
        execution is not None
        and execution.get("exception") is None
        and any(predicate_matches(candidate, frozen, bindings) for frozen in predicates)
    )


def normalize(value: Any, reverse_roles: dict[str, str]) -> Any:
    if isinstance(value, dict):
        return {key: normalize(child, reverse_roles) for key, child in sorted(value.items())}
    if isinstance(value, list):
        return [normalize(child, reverse_roles) for child in value]
    if isinstance(value, float):
        return float(f"{value:.9f}")
    if isinstance(value, str) and value in reverse_roles:
        return {"opaque_role": reverse_roles[value]}
    return value


def semantic_projection(context: Any, bindings: dict[str, Any]) -> dict[str, Any]:
    from tool_sandbox.common.execution_context import DatabaseNamespace

    reverse_roles = {
        str(value): str(role)
        for role, value in bindings.items()
        if isinstance(value, str)
    }
    namespaces: dict[str, Any] = {}
    for name, fields in spec.SEMANTIC_ALLOWLIST.items():
        raw_rows = context.get_database(DatabaseNamespace[name]).to_dicts()
        rows = [
            {field: normalize(row.get(field), reverse_roles) for field in fields}
            for row in raw_rows
        ]
        rows.sort(key=spec.canonical_json)
        namespaces[name] = rows
    return {"namespaces": namespaces, "sha256": spec.canonical_sha256(namespaces)}


def row_matches(row: dict[str, Any], predicate: dict[str, Any]) -> bool:
    return all(row.get(field) == value for field, value in predicate.items())


def environment_debt(context: Any, baseline: Any, patch: dict[str, Any]) -> bool:
    from tool_sandbox.common.execution_context import DatabaseNamespace

    operation = patch["operation"]
    if operation == "none":
        return False
    namespace = DatabaseNamespace[patch["namespace"]]
    current = context.get_database(namespace).to_dicts()
    original = baseline.get_database(namespace).to_dicts()
    if operation == "remove_rows_added_after_baseline":
        predicate = patch["predicate"]
        return sum(row_matches(row, predicate) for row in current) > sum(row_matches(row, predicate) for row in original)
    if operation == "restore_baseline_row_if_missing_or_changed":
        key = patch["key"]
        return [row for row in current if row_matches(row, key)] != [row for row in original if row_matches(row, key)]
    raise ValueError(operation)


def goal_reached(context: Any, predicate: dict[str, Any]) -> bool:
    from tool_sandbox.common.execution_context import DatabaseNamespace

    kind = predicate["error_kind"]
    if kind == "weekday-target-timestamp-shift":
        return any(
            str(row.get("content") or "").casefold() == "buy chocolate milk"
            and row.get("reminder_timestamp") == predicate["oracle_value"]
            for row in context.get_database(DatabaseNamespace.REMINDER).to_dicts()
        )
    if kind == "last-outgoing-recipient-id-substitution":
        return any(
            row.get("person_id") == predicate["oracle_value"]
            and row.get("phone_number") == "+10293847563"
            for row in context.get_database(DatabaseNamespace.CONTACT).to_dicts()
        )
    if kind == "low-battery-boolean-negation":
        row = context.get_database(DatabaseNamespace.SETTING).to_dicts()[0]
        return row.get("low_battery_mode") is False and row.get("wifi") is True
    raise ValueError(kind)


def add_synthetic_messages(context: Any, messages: list[dict[str, Any]]) -> None:
    from tool_sandbox.common.execution_context import DatabaseNamespace, RoleType

    rows = []
    for message in messages:
        role = message.get("role")
        if role == "assistant" and message.get("tool_calls"):
            for call in message["tool_calls"]:
                name = call["function"]["name"]
                arguments = json.loads(call["function"]["arguments"])
                call_id = call["id"]
                rows.append(
                    {
                        "sender": RoleType.AGENT,
                        "recipient": RoleType.EXECUTION_ENVIRONMENT,
                        "content": (
                            f"{call_id}_parameters = {arguments!r}\n"
                            f"{call_id}_response = {name}(**{call_id}_parameters)\n"
                            f"print(repr({call_id}_response))"
                        ),
                        "openai_tool_call_id": call_id,
                        "openai_function_name": name,
                    }
                )
            if str(message.get("content") or ""):
                rows.append(
                    {
                        "sender": RoleType.AGENT,
                        "recipient": RoleType.USER,
                        "content": message["content"],
                        "conversation_active": True,
                    }
                )
        elif role == "assistant":
            rows.append(
                {
                    "sender": RoleType.AGENT,
                    "recipient": RoleType.USER,
                    "content": str(message.get("content") or ""),
                    "conversation_active": True,
                }
            )
        elif role == "tool":
            rows.append(
                {
                    "sender": RoleType.EXECUTION_ENVIRONMENT,
                    "recipient": RoleType.AGENT,
                    "content": message["content"],
                    "openai_tool_call_id": message["tool_call_id"],
                    "openai_function_name": message["name"],
                }
            )
        elif role == "system":
            rows.append(
                {
                    "sender": RoleType.SYSTEM,
                    "recipient": RoleType.AGENT,
                    "content": message["content"],
                    "conversation_active": True,
                }
            )
        elif role == "user":
            rows.append(
                {
                    "sender": RoleType.USER,
                    "recipient": RoleType.AGENT,
                    "content": message["content"],
                    "conversation_active": True,
                }
            )
        else:
            raise RuntimeError(f"无法注入未知历史 role：{role}")
    if rows:
        context.add_to_database(DatabaseNamespace.SANDBOX, rows)


def apply_environment_patch(context: Any, baseline: Any, patch: dict[str, Any]) -> dict[str, Any]:
    # runner 使用生产实现；独立 gate/auditor 另有不共享的重算实现。
    return base.apply_environment_patch(context, baseline, patch)


def initialize_state(
    row: dict[str, Any],
    episode: dict[str, Any],
    predicate: dict[str, Any],
    patch: dict[str, Any],
    stimulus: dict[str, Any],
    assets_root: Path,
) -> dict[str, Any]:
    from tool_sandbox.common.execution_context import set_current_context

    snapshot_path = assets_root / episode["snapshot"]
    if base.sha256_file(snapshot_path) != episode["snapshot_sha256"]:
        raise RuntimeError(f"snapshot 哈希漂移：{snapshot_path}")
    snapshot = json.loads(snapshot_path.read_text(encoding="utf-8"))
    context, baseline, environment = base.initialize_context(snapshot, episode)
    set_current_context(context)
    messages = copy.deepcopy(stimulus["messages"])
    if spec.canonical_sha256(messages) != stimulus["messages_sha256"]:
        raise RuntimeError("rendered messages 哈希漂移")
    base_length = len(episode["base_messages"])
    if messages[:base_length] != episode["base_messages"]:
        raise RuntimeError("stimulus base messages 漂移")
    history = messages[base_length:]
    bindings = copy.deepcopy(episode.get("dynamic_roles") or {})
    predecessor_record = None
    patch_record = None

    if row["module"] == "E":
        expected_assistant = episode["predecessor_checkpoint"]["assistant_message"]
        predecessor_call_id = expected_assistant["tool_calls"][0]["id"]
        predecessor_index = next(
            (
                index for index, message in enumerate(history)
                if message.get("role") == "assistant"
                and any(call.get("id") == predecessor_call_id for call in message.get("tool_calls") or [])
            ),
            None,
        )
        if predecessor_index is None:
            raise RuntimeError("E stimulus 缺少 predecessor action")
        add_synthetic_messages(context, history[:predecessor_index])
        install_uuid_provider(DeterministicUUID4(episode["episode_id"], predecessor=True))
        attempted = copy.deepcopy(episode["predecessor_checkpoint"]["attempted_action"])
        openai_calls, tool_messages, execution = base.execute_actions(
            context,
            environment,
            [attempted],
            f"q12_{episode['episode_id'].lower().replace('-', '_')}_pred",
        )
        actual_assistant = {"role": "assistant", "content": "", "tool_calls": openai_calls}
        expected_tools = episode["predecessor_checkpoint"]["tool_messages"]
        if actual_assistant != expected_assistant or tool_messages != expected_tools:
            raise RuntimeError("predecessor 可见工具记录与冻结资产不一致")
        predecessor_record = {"assistant": actual_assistant, "tools": tool_messages, "execution": execution}
        frozen_error = predicate["error_action"]
        if frozen_error.get("binds_success_result") and execution[0].get("exception") is None:
            bindings[frozen_error["binds_success_result"]] = parse_value(execution[0])
        skip = predecessor_index + 1 + len(expected_tools)
        if row["condition"] == "E_align":
            patch_record = apply_environment_patch(context, baseline, patch)
        elif row["condition"] != "E_text":
            raise RuntimeError(f"E module 未知 condition：{row['condition']}")
        add_synthetic_messages(context, history[skip:])
    else:
        add_synthetic_messages(context, history)

    set_current_context(context)
    provider = DeterministicUUID4(logical_key(row))
    install_uuid_provider(provider)
    initial_b = row["condition"] != "A_N"
    initial_projection = semantic_projection(context, bindings)
    initial_snapshot = context.to_dict(serialize_console=False)
    initial_e = environment_debt(context, baseline, patch)
    checkpoint = {
        "messages_sha256": spec.canonical_sha256(messages),
        "rendered_input_ids_sha256": stimulus["input_ids_sha256"],
        "rendered_input_token_count": stimulus["input_token_count"],
        "raw_snapshot_sha256": spec.canonical_sha256(initial_snapshot),
        "semantic_projection": initial_projection,
        "B": initial_b,
        "E": initial_e,
        "target_model_decisions_before_checkpoint": 0,
        "predecessor": predecessor_record,
        "patch": patch_record,
    }
    return {
        "context": context,
        "baseline": baseline,
        "environment": environment,
        "messages": messages,
        "bindings": bindings,
        "successful_actions": [],
        "all_actions": [],
        "decisions": [],
        "total_tool_calls": 0,
        "B": initial_b,
        "E": initial_e,
        "goal_completed": goal_reached(context, predicate),
        "uuid_provider": provider,
        "logical_key": logical_key(row),
        "last_early_completion": False,
        "checkpoint": checkpoint,
        "started": time.time(),
    }


def advance_decision(
    state: dict[str, Any],
    row: dict[str, Any],
    episode: dict[str, Any],
    predicate: dict[str, Any],
    patch: dict[str, Any],
    model_endpoint: str,
    max_new_tokens: int,
    decision_index: int,
) -> None:
    from tool_sandbox.common.execution_context import set_current_context

    context = state["context"]
    set_current_context(context)
    install_uuid_provider(state["uuid_provider"])
    raw_before = context.to_dict(serialize_console=False)
    semantic_before = semantic_projection(context, state["bindings"])
    environment_before = base.flat_environment(context)
    request_id = f"QH14-{row['precision']}-{row['unit_id']}-decision-{decision_index}"
    generated = base.generate_decision(
        model_endpoint,
        request_id,
        row["precision"],
        state["messages"],
        episode["tool_schema"],
        max_new_tokens,
    )
    if decision_index == 1:
        if generated.get("input_ids_sha256") != state["checkpoint"]["rendered_input_ids_sha256"]:
            raise RuntimeError("首决策 input_ids 与冻结 stimulus 不一致")
        if int(generated.get("input_token_count", -1)) != int(state["checkpoint"]["rendered_input_token_count"]):
            raise RuntimeError("首决策 input token 数与冻结 stimulus 不一致")
        if spec.canonical_sha256(raw_before) != state["checkpoint"]["raw_snapshot_sha256"]:
            raise RuntimeError("首决策前 raw checkpoint 漂移")
    classified = parser.classify_generated_reply(
        generated, episode["tool_schema"], state["total_tool_calls"]
    )
    actions = classified["actions"]
    execution: list[dict[str, Any]] = []
    output_class = classified["output_class"]
    early_completion = output_class != "native-tool"
    if output_class == "native-tool":
        openai_calls, tool_messages, execution = base.execute_actions(
            context,
            state["environment"],
            actions,
            stable_call_prefix(state["logical_key"], decision_index),
        )
        state["messages"].append({"role": "assistant", "content": "", "tool_calls": openai_calls})
        state["messages"].extend(tool_messages)
        state["all_actions"].extend(actions)
        state["total_tool_calls"] += len(actions)
        early_completion = any(action["name"] == "end_conversation" for action in actions)
    else:
        content = str(generated.get("visible_content") or generated.get("raw_text") or "")
        base.add_prose_action(context, content)
        state["messages"].append({"role": "assistant", "content": content})

    debt_before = bool(state["B"])
    f_flags: list[bool] = []
    v_flags: list[bool] = []
    g_flags: list[bool] = []
    completion_flags: list[bool] = []
    event_rows: list[dict[str, Any]] = []
    for index, candidate in enumerate(actions):
        record = execution[index] if index < len(execution) else None
        success = record is not None and record.get("exception") is None
        f_flag = error_action(
            candidate,
            predicate["error_action"],
            environment_before,
            actions[:index],
            execution[:index],
            state["bindings"],
        )
        if f_flag and success and predicate["error_action"].get("binds_success_result"):
            state["bindings"][predicate["error_action"]["binds_success_result"]] = parse_value(record)
        v_flag = any(
            successful_verification(candidate, record, frozen, state["bindings"])
            for frozen in predicate.get("verification_actions", [])
        )
        g_flag = successful_frozen_action(
            candidate, record, predicate.get("recovery_actions", []), state["bindings"]
        )
        completion_flag = successful_frozen_action(
            candidate, record, predicate.get("completion_actions", []), state["bindings"]
        )
        if v_flag or g_flag:
            state["B"] = False
        if f_flag:
            state["B"] = True
        if success:
            state["successful_actions"].append(copy.deepcopy(candidate))
        f_flags.append(f_flag)
        v_flags.append(v_flag)
        g_flags.append(g_flag)
        completion_flags.append(completion_flag)
        event_rows.append(
            {
                "action_index": index + 1,
                "F": f_flag,
                "V": v_flag,
                "G": g_flag,
                "B_after": bool(state["B"]),
                "execution_success": success,
            }
        )

    state["E"] = environment_debt(context, state["baseline"], patch)
    target = goal_reached(context, predicate)
    state["goal_completed"] = bool(state["goal_completed"] or target or any(completion_flags))
    raw_after = context.to_dict(serialize_console=False)
    semantic_after = semantic_projection(context, state["bindings"])
    decision = {
        "decision_index": decision_index,
        **generated,
        "output_class": output_class,
        "syntax_valid": bool(classified["syntax_valid"]),
        "tool_validation_failures": classified["validation_failures"],
        "attempted_actions": classified.get("attempted_actions", actions),
        "parsed_actions": actions,
        "execution": execution,
        "event_rows": event_rows,
        "F": any(f_flags),
        "V": any(v_flags),
        "G": any(g_flags),
        "B_before": debt_before,
        "B": bool(state["B"]),
        "E": bool(state["E"]),
        "T": target,
        "goal_completed": bool(state["goal_completed"]),
        "successful_goal_completion": bool(any(completion_flags) or target),
        "terminal_before_goal_completion": output_class == "terminal-text" and not state["goal_completed"],
        "environment_before_reply": environment_before,
        "dynamic_bindings": copy.deepcopy(state["bindings"]),
        "raw_snapshot_before": raw_before,
        "raw_snapshot_before_sha256": spec.canonical_sha256(raw_before),
        "raw_snapshot_after": raw_after,
        "raw_snapshot_after_sha256": spec.canonical_sha256(raw_after),
        "semantic_projection_before": semantic_before,
        "semantic_projection_after": semantic_after,
    }
    decision["decision_signature"] = parser.first_decision_signature(
        output_class,
        actions,
        str(generated.get("visible_content") or ""),
        str(generated.get("raw_text") or ""),
    )
    state["decisions"].append(decision)
    state["last_early_completion"] = early_completion


def route(decisions: list[dict[str, Any]]) -> str:
    first_v = next((index for index, row in enumerate(decisions) if row["V"]), None)
    first_g = next((index for index, row in enumerate(decisions) if row["G"]), None)
    clear_points = [value for value in (first_v, first_g) if value is not None]
    if clear_points and any(row["F"] for row in decisions[min(clear_points) + 1 :]):
        return "recover-then-relapse"
    if first_g is not None and first_v is None:
        return "direct-use"
    if first_v is not None and first_g is not None and first_v <= first_g:
        return "verify-then-recover"
    if first_v is not None:
        return "verify-only"
    return "no-recovery"


def scientific_signature(state: dict[str, Any]) -> tuple[str, dict[str, Any]]:
    reverse_roles = {
        str(value): str(role)
        for role, value in state["bindings"].items()
        if isinstance(value, str)
    }
    decisions = []
    for row in state["decisions"]:
        decisions.append(
            {
                "decision_index": row["decision_index"],
                "output_class": row["output_class"],
                "attempted_actions": normalize(row["attempted_actions"], reverse_roles),
                "execution": [
                    {
                        "tool": item.get("tool"),
                        "value": normalize(parse_value(item), reverse_roles),
                        "exception": item.get("exception") is not None,
                    }
                    for item in row["execution"]
                ],
                "F": row["F"],
                "V": row["V"],
                "G": row["G"],
                "B": row["B"],
                "E": row["E"],
                "T": row["T"],
                "goal_completed": row["goal_completed"],
                "terminal_before_goal_completion": row["terminal_before_goal_completion"],
                "non_tool_text_sha256": (
                    row["decision_signature"] if row["output_class"] != "native-tool" else None
                ),
            }
        )
    payload = {
        "initial_B": state["checkpoint"]["B"],
        "initial_E": state["checkpoint"]["E"],
        "decisions": decisions,
        "route": route(state["decisions"]),
    }
    return spec.canonical_sha256(payload), payload


def finalize(
    state: dict[str, Any],
    row: dict[str, Any],
    episode: dict[str, Any],
    scenario: Any,
) -> dict[str, Any]:
    import attrs
    from tool_sandbox.common.execution_context import set_current_context

    set_current_context(state["context"])
    evaluation = scenario.evaluation.evaluate(
        execution_context=state["context"], max_turn_count=scenario.max_messages
    )
    # 生产事实以 JSON 产物为边界。先转换到与落盘/重载完全相同的
    # JSON domain，避免内存中的 int key / tuple 与持久化后的 str key / list
    # 被误判为不同 evaluator 结果。
    evaluation_record = json.loads(
        spec.canonical_json(attrs.asdict(evaluation))
    )
    decisions = state["decisions"]
    if len(decisions) != spec.DECISIONS_PER_TRAJECTORY:
        raise RuntimeError("v14 轨迹必须恰含四个目标模型决策")
    signature_hash, signature_payload = scientific_signature(state)
    classes = Counter(row["output_class"] for row in decisions)
    ending = state["context"].to_dict(serialize_console=False)
    return {
        "schema_version": 1,
        "protocol_id": spec.PROTOCOL_ID,
        "protocol_version": spec.PROTOCOL_VERSION,
        "unit": spec.scientific_unit_identity(row),
        "schedule_metadata": spec.schedule_metadata(row),
        "status": "succeeded",
        "checkpoint": state["checkpoint"],
        "decisions": decisions,
        "route": route(decisions),
        "scientific_signature": {"sha256": signature_hash, "payload": signature_payload},
        "metrics": {
            "L_B": sum(float(item["B"]) for item in decisions) / 4.0,
            "L_E": sum(float(item["E"]) for item in decisions) / 4.0,
            "F_count": sum(item["F"] for item in decisions),
            "V_count": sum(item["V"] for item in decisions),
            "G_count": sum(item["G"] for item in decisions),
            "B_residual": float(decisions[-1]["B"]),
            "E_residual": float(decisions[-1]["E"]),
            "T": float(decisions[-1]["T"]),
            "syntax_validity": sum(item["syntax_valid"] for item in decisions) / 4.0,
            "first_decision_native_tool": float(decisions[0]["output_class"] == "native-tool"),
            "tool_call_count": state["total_tool_calls"],
            "tool_exception_count": sum(
                item.get("exception") is not None
                for decision in decisions for item in decision["execution"]
            ),
            "output_class_counts": dict(sorted(classes.items())),
        },
        "evaluation": evaluation_record,
        "ending_snapshot": ending,
        "ending_snapshot_sha256": spec.canonical_sha256(ending),
        "elapsed_seconds": round(time.time() - state["started"], 6),
    }


def run_unit(
    row: dict[str, Any],
    episode: dict[str, Any],
    predicate: dict[str, Any],
    patch: dict[str, Any],
    stimulus: dict[str, Any],
    assets_root: Path,
    scenario: Any,
    model_endpoint: str,
    max_new_tokens: int,
) -> dict[str, Any]:
    state = initialize_state(row, episode, predicate, patch, stimulus, assets_root)
    for decision_index in range(1, spec.DECISIONS_PER_TRAJECTORY + 1):
        advance_decision(
            state, row, episode, predicate, patch,
            model_endpoint, max_new_tokens, decision_index,
        )
        if decision_index < spec.DECISIONS_PER_TRAJECTORY and state["last_early_completion"]:
            base.add_continuation(state["context"])
            state["messages"].append({"role": "user", "content": base.CONTINUATION})
    result = finalize(state, row, episode, scenario)
    result["predicate_sha256"] = spec.canonical_sha256(predicate)
    return result


def build_schedule(units: list[dict[str, Any]], precision: str, seed: int) -> list[dict[str, Any]]:
    selected = [row for row in units if row["precision"] == precision]
    expected = spec.expected_precision_counts()[precision]
    if len(selected) != expected or len({row["unit_id"] for row in selected}) != expected:
        raise RuntimeError(f"{precision} 应含 {expected} 个 v14 单元，实际 {len(selected)}")
    blocks: dict[tuple[str, str], list[dict[str, Any]]] = {}
    for row in selected:
        blocks.setdefault((row["episode_id"], row["module"]), []).append(row)
    keys = sorted(blocks)
    random.Random(seed).shuffle(keys)
    schedule = []
    for key in keys:
        block = sorted(blocks[key], key=lambda row: row["unit_id"])
        random.Random(f"{seed}|{precision}|{key}|v14").shuffle(block)
        schedule.extend(block)
    return [dict(row, execution_order=index) for index, row in enumerate(schedule, start=1)]


def main() -> int:
    parser_cli = argparse.ArgumentParser(description=__doc__)
    parser_cli.add_argument("--precision", choices=spec.TREATMENT_PRECISIONS, required=True)
    parser_cli.add_argument("--assets", type=Path, required=True)
    parser_cli.add_argument("--rendered", type=Path, required=True)
    parser_cli.add_argument("--model-endpoint", required=True)
    parser_cli.add_argument("--toolsandbox-source", type=Path, required=True)
    parser_cli.add_argument("--toolsandbox-site-packages", type=Path, required=True)
    parser_cli.add_argument("--output", type=Path, required=True)
    parser_cli.add_argument("--seed", type=int, default=spec.SCHEDULE_SEED)
    parser_cli.add_argument("--max-new-tokens", type=int, default=256)
    args = parser_cli.parse_args()
    if args.output.exists() and any(args.output.iterdir()):
        raise RuntimeError(f"输出目录必须不存在或为空：{args.output}")
    args.output.mkdir(parents=True, exist_ok=True)

    base.PROTOCOL_VERSION = spec.PROTOCOL_VERSION
    base.MODEL_REVISION = spec.MODEL_REVISION
    runtime = base.prepare_toolsandbox(args.toolsandbox_source, args.toolsandbox_site_packages)
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
        "execution_design": "pre-target-factorial-checkpoint-four-decision",
    }
    exit_code = 1
    try:
        asset_manifest = base.verify_manifest(args.assets)
        rendered_manifest = base.verify_manifest(args.rendered, require_checks=True)
        episodes = {row["episode_id"]: row for row in base.read_jsonl(args.assets / "episodes.jsonl")}
        predicates = {row["episode_id"]: row for row in base.read_jsonl(args.assets / "predicates.jsonl")}
        patches = {row["episode_id"]: row for row in base.read_jsonl(args.assets / "environment-patches.jsonl")}
        stimuli = {
            (row["episode_id"], row["module"], row["condition"], int(row["gap"])): row
            for row in base.read_jsonl(args.rendered / "stimuli.jsonl")
        }
        units = base.read_jsonl(args.assets / "trajectory-units.jsonl")
        schedule = build_schedule(units, args.precision, args.seed)
        base.write_json(args.output / "schedule.json", schedule)
        scenarios = named_scenarios(preferred_tool_backend=ToolBackend.DEFAULT)
        successes = 0
        invalid = 0
        attempted = 0
        request_count = 0
        for row in schedule:
            try:
                result = run_unit(
                    row,
                    episodes[row["episode_id"]],
                    predicates[row["episode_id"]],
                    patches[row["episode_id"]],
                    stimuli[(row["episode_id"], row["module"], row["condition"], int(row["gap"]))],
                    args.assets,
                    scenarios[row["scenario"]],
                    args.model_endpoint,
                    args.max_new_tokens,
                )
                request_count += len(result["decisions"])
            except Exception as error:
                result = {
                    "schema_version": 1,
                    "protocol_id": spec.PROTOCOL_ID,
                    "protocol_version": spec.PROTOCOL_VERSION,
                    "unit": spec.scientific_unit_identity(row),
                    "schedule_metadata": spec.schedule_metadata(row),
                    "status": "invalid",
                    "error_type": type(error).__name__,
                    "error": str(error),
                    "traceback": traceback.format_exc(),
                }
            attempted += 1
            path = args.output / "units" / f"{row['unit_id']}.json"
            base.write_json(path, result)
            if result["status"] == "succeeded":
                successes += 1
            else:
                invalid += 1
            base.append_jsonl(
                args.output / "results.jsonl",
                {
                    "unit_id": row["unit_id"],
                    "status": result["status"],
                    "artifact": str(path.relative_to(args.output)).replace("\\", "/"),
                    "artifact_sha256": base.sha256_file(path),
                    "metrics": result.get("metrics"),
                    "scientific_signature_sha256": (result.get("scientific_signature") or {}).get("sha256"),
                    "checkpoint_sha256": spec.canonical_sha256(result.get("checkpoint")) if result.get("checkpoint") else None,
                    "elapsed_seconds": result.get("elapsed_seconds"),
                    "error_type": result.get("error_type"),
                    "error": result.get("error"),
                },
            )
            gc.collect()
            if result["status"] != "succeeded":
                break
        expected_units = spec.expected_precision_counts()[args.precision]
        expected_requests = spec.expected_unique_request_counts()[args.precision]
        count_ok = invalid == 0 and successes == expected_units and request_count == expected_requests
        summary.update(
            {
                "status": "succeeded" if count_ok else "failed",
                "expected_logical_units": expected_units,
                "completed_logical_units": attempted,
                "succeeded_logical_units": successes,
                "invalid_logical_units": invalid,
                "unique_model_requests": request_count,
                "expected_unique_model_requests": expected_requests,
                "unique_model_request_count_ok": count_ok,
                "schedule_sha256": base.sha256_file(args.output / "schedule.json"),
                "results_sha256": base.sha256_file(args.output / "results.jsonl"),
                "asset_manifest_sha256": base.sha256_file(args.assets / "manifest.json"),
                "rendered_manifest_sha256": base.sha256_file(args.rendered / "manifest.json"),
                "asset_manifest_protocol": asset_manifest["protocol_version"],
                "rendered_manifest_protocol": rendered_manifest["protocol_version"],
            }
        )
        exit_code = 0 if count_ok else 1
    except Exception as error:
        summary.update({"status": "failed", "error_type": type(error).__name__, "error": str(error), "traceback": traceback.format_exc()})
    finally:
        summary["elapsed_seconds"] = round(time.time() - started, 6)
        base.write_json(args.output / "summary.json", summary)
        print(json.dumps(summary, ensure_ascii=False, indent=2, default=str))
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
