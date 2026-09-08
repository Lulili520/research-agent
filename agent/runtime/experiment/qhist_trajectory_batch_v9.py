#!/usr/bin/env python3
"""执行 Q-HIST v9 轨迹：分离语法、工具策略和任务结果。"""

from __future__ import annotations

import copy
import hashlib
import json
import re
import time
from collections import Counter
from typing import Any

import qhist_trajectory_batch as base
import qhist_v9_spec as spec


TOOL_BLOCK_RE = re.compile(r"<tool_call>\s*(.*?)\s*</tool_call>", re.DOTALL)
TOOL_MARKERS = ("<tool_call", "</tool_call>", "<|tool_call|>")


def _json_type_matches(value: Any, expected: str) -> bool:
    if expected == "object":
        return isinstance(value, dict)
    if expected == "array":
        return isinstance(value, list)
    if expected == "string":
        return isinstance(value, str)
    if expected == "integer":
        return isinstance(value, int) and not isinstance(value, bool)
    if expected == "number":
        return isinstance(value, (int, float)) and not isinstance(value, bool)
    if expected == "boolean":
        return isinstance(value, bool)
    if expected == "null":
        return value is None
    return False


def validate_json_value(value: Any, schema: Any, path: str = "$") -> list[str]:
    """验证协议冻结的 JSON Schema 子集，不做类型强制或默认值填充。"""

    if not isinstance(schema, dict):
        return [f"{path}:schema-not-object"]
    if "anyOf" in schema:
        branches = [validate_json_value(value, branch, path) for branch in schema["anyOf"]]
        if not any(not errors for errors in branches):
            return [f"{path}:anyOf-no-match"]
    if "oneOf" in schema:
        branches = [validate_json_value(value, branch, path) for branch in schema["oneOf"]]
        if sum(not errors for errors in branches) != 1:
            return [f"{path}:oneOf-not-exactly-one"]
    if "enum" in schema and value not in schema["enum"]:
        return [f"{path}:not-in-enum"]
    expected = schema.get("type")
    if expected is not None:
        expected_types = [expected] if isinstance(expected, str) else list(expected)
        if not any(_json_type_matches(value, item) for item in expected_types):
            return [f"{path}:type:{expected_types}"]
    errors: list[str] = []
    if isinstance(value, dict):
        properties = schema.get("properties") or {}
        required = schema.get("required") or []
        for name in required:
            if name not in value:
                errors.append(f"{path}.{name}:required")
        additional = schema.get("additionalProperties", True)
        for name, child in value.items():
            if name in properties:
                errors.extend(validate_json_value(child, properties[name], f"{path}.{name}"))
            elif additional is False:
                errors.append(f"{path}.{name}:additional-property")
            elif isinstance(additional, dict):
                errors.extend(validate_json_value(child, additional, f"{path}.{name}"))
    if isinstance(value, list) and isinstance(schema.get("items"), dict):
        for index, child in enumerate(value):
            errors.extend(validate_json_value(child, schema["items"], f"{path}[{index}]"))
    return errors


def tool_schemas(tools: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    schemas: dict[str, dict[str, Any]] = {}
    for item in tools:
        function = item.get("function") if isinstance(item, dict) else None
        if not isinstance(function, dict) or not isinstance(function.get("name"), str):
            raise RuntimeError("冻结 tool schema 含无效 function 定义")
        name = function["name"]
        if name in schemas:
            raise RuntimeError(f"冻结 tool schema 重复工具名：{name}")
        schemas[name] = function.get("parameters") or {"type": "object"}
    return schemas


def classify_generated_reply(
    generated: dict[str, Any],
    tools: list[dict[str, Any]],
    total_tool_calls: int,
    tool_cap: int = 16,
) -> dict[str, Any]:
    raw = str(generated.get("raw_text") or "")
    visible = str(generated.get("visible_content") or "")
    blocks = TOOL_BLOCK_RE.findall(raw)
    if not blocks:
        if any(marker in raw for marker in TOOL_MARKERS):
            return {
                "output_class": "malformed-tool-attempt",
                "syntax_valid": False,
                "actions": [],
                "validation_failures": ["incomplete-tool-block"],
            }
        # 仅有 Qwen 的不可见结束 token 不算普通终止文本。
        raw_without_wrappers = raw.replace("<|im_end|>", "").strip()
        output_class = "terminal-text" if (visible.strip() or raw_without_wrappers) else "empty"
        return {
            "output_class": output_class,
            "syntax_valid": output_class == "terminal-text",
            "actions": [],
            "validation_failures": [] if output_class == "terminal-text" else ["empty"],
        }

    parsed: list[Any] = []
    for index, block in enumerate(blocks, start=1):
        try:
            parsed.append(json.loads(block))
        except json.JSONDecodeError as error:
            return {
                "output_class": "malformed-tool-attempt",
                "syntax_valid": False,
                "actions": [],
                "validation_failures": [f"call-{index}:json:{error.msg}"],
            }
    schemas = tool_schemas(tools)
    actions: list[dict[str, Any]] = []
    failures: list[str] = []
    for index, value in enumerate(parsed, start=1):
        if not isinstance(value, dict):
            failures.append(f"call-{index}:not-object")
            continue
        name = value.get("name")
        arguments = value.get("arguments")
        if not isinstance(name, str):
            failures.append(f"call-{index}:name-not-string")
            continue
        if name not in schemas:
            failures.append(f"call-{index}:unknown-tool:{name}")
            continue
        if not isinstance(arguments, dict):
            failures.append(f"call-{index}:arguments-not-object")
            continue
        schema_errors = validate_json_value(arguments, schemas[name], f"call-{index}.arguments")
        failures.extend(schema_errors)
        actions.append({"name": name, "arguments": arguments})
    if total_tool_calls + len(parsed) > tool_cap:
        failures.append(f"tool-cap:{total_tool_calls}+{len(parsed)}>{tool_cap}")
    if failures:
        return {
            "output_class": "invalid-native-tool",
            "syntax_valid": False,
            "actions": [],
            "attempted_actions": actions,
            "validation_failures": failures,
        }
    return {
        "output_class": "native-tool",
        "syntax_valid": True,
        "actions": actions,
        "validation_failures": [],
    }


def first_decision_signature(
    output_class: str, actions: list[dict[str, Any]], visible: str, raw: str
) -> str:
    if output_class == "native-tool":
        payload: Any = {
            "output_class": output_class,
            "actions": actions,
        }
    else:
        text = visible if visible else raw
        payload = {
            "output_class": output_class,
            "visible_text_sha256": hashlib.sha256(text.encode("utf-8")).hexdigest(),
        }
    return base.canonical_sha256(payload)


def build_schedule(
    units: list[dict[str, Any]], precision: str, seed: int
) -> list[dict[str, Any]]:
    selected = [row for row in units if row["precision"] == precision]
    expected = spec.expected_precision_counts()[precision]
    if len(selected) != expected or len({row["unit_id"] for row in selected}) != expected:
        raise RuntimeError(
            f"{precision} v9 轨迹应有 {expected} 个唯一单元，实际 {len(selected)}"
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
        random.Random(f"{seed}|{episode_id}|{precision}|v9").shuffle(block)
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
    base.add_synthetic_prefix(context, episode, use_truth=use_truth)
    messages = [
        *copy.deepcopy(episode["base_messages"]),
        copy.deepcopy(episode["prefix"]["tool_call_message"]),
        copy.deepcopy(
            episode["prefix"]["truth_message"]
            if use_truth
            else episode["prefix"]["false_message"]
        ),
    ]
    total_decisions = int(row["distance"]) + 3
    all_actions: list[dict[str, Any]] = []
    decisions: list[dict[str, Any]] = []
    correction_record: dict[str, Any] | None = None
    total_tool_calls = 0
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
        classified = classify_generated_reply(
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
            content = str(generated.get("visible_content") or generated.get("raw_text") or "")
            base.add_prose_action(context, content)
            messages.append({"role": "assistant", "content": content})

        action_error = any(
            base.action_matches(action, predicate["error_action"], environment_before)
            for action in actions
        )
        debt = base.environment_debt(context, baseline_context, patch)
        v_components = {"error_action": float(action_error)}
        if patch["operation"] != "none":
            v_components["environment_debt"] = float(debt)
        oracle_progress = base.ordered_oracle_progress(
            all_actions, predicate["oracle_action"]
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
            "error_consistent_action": action_error,
            "oracle_action_progress": oracle_progress,
            "terminal_before_oracle_progress": (
                output_class == "terminal-text" and not oracle_progress
            ),
            "environment_debt": debt,
            "v_components": v_components,
            "v_score": sum(v_components.values()) / len(v_components),
            "phase": (
                "pre-correction"
                if decision_index <= int(row["distance"])
                else "post-correction"
            ),
        }
        decision_record["decision_signature"] = first_decision_signature(
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
    classes = Counter(row["output_class"] for row in decisions)
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
        "tool_schema_sha256": episode["tool_schema_sha256"],
        "agent_tool_contract_sha256": episode["agent_tool_contract"]["sha256"],
        "correction": correction_record,
        "decisions": decisions,
        "metrics": {
            "normalized_q_auc": sum(item["v_score"] for item in decisions)
            / len(decisions),
            "adoption_alpha": float(decisions[0]["error_consistent_action"]),
            "error_action_count": sum(item["error_consistent_action"] for item in decisions),
            "environment_debt_boundary_count": sum(item["environment_debt"] for item in decisions),
            "context_residual": float(decisions[-1]["error_consistent_action"]),
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
    # 复用 v8 的只写批处理外壳，但把全部协议敏感全局绑定到 v9 实现。
    base.PROTOCOL_VERSION = spec.PROTOCOL_VERSION
    base.run_unit = run_unit
    base.build_schedule = build_schedule
    return base.main()


if __name__ == "__main__":
    raise SystemExit(main())
