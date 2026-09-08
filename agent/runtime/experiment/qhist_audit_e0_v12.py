#!/usr/bin/env python3
"""独立重算 Q-HIST v12 E0 的 F/V/G/B/E/T、clean、复现与资源门。"""

from __future__ import annotations

import argparse
import ast
import hashlib
import json
import math
import re
import shutil
from collections import defaultdict
from pathlib import Path
from typing import Any

import qhist_build_e0_assets as toolsandbox_base
import qhist_v12_spec as spec


TOOL_BLOCK_RE = re.compile(r"<tool_call>\s*(.*?)\s*</tool_call>", re.DOTALL)
TOOL_MARKERS = ("<tool_call", "</tool_call>", "<|tool_call|>")
RUN_PRECISIONS = ("P00", "P10", "P01", "P11")


def load(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def load_jsonl(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line]


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def json_type_matches(value: Any, expected: str) -> bool:
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


def validate_json(value: Any, schema: Any, path: str = "$") -> list[str]:
    if not isinstance(schema, dict):
        return [f"{path}:schema-not-object"]
    if "anyOf" in schema:
        branches = [validate_json(value, branch, path) for branch in schema["anyOf"]]
        if not any(not errors for errors in branches):
            return [f"{path}:anyOf-no-match"]
    if "oneOf" in schema:
        branches = [validate_json(value, branch, path) for branch in schema["oneOf"]]
        if sum(not errors for errors in branches) != 1:
            return [f"{path}:oneOf-not-exactly-one"]
    if "enum" in schema and value not in schema["enum"]:
        return [f"{path}:not-in-enum"]
    expected = schema.get("type")
    if expected is not None:
        expected_types = [expected] if isinstance(expected, str) else list(expected)
        if not any(json_type_matches(value, item) for item in expected_types):
            return [f"{path}:type"]
    errors: list[str] = []
    if isinstance(value, dict):
        properties = schema.get("properties") or {}
        for name in schema.get("required") or []:
            if name not in value:
                errors.append(f"{path}.{name}:required")
        additional = schema.get("additionalProperties", True)
        for name, child in value.items():
            if name in properties:
                errors.extend(validate_json(child, properties[name], f"{path}.{name}"))
            elif additional is False:
                errors.append(f"{path}.{name}:additional")
            elif isinstance(additional, dict):
                errors.extend(validate_json(child, additional, f"{path}.{name}"))
    if isinstance(value, list) and isinstance(schema.get("items"), dict):
        for index, child in enumerate(value):
            errors.extend(validate_json(child, schema["items"], f"{path}[{index}]"))
    return errors


def tool_schemas(tools: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    result = {}
    for item in tools:
        function = item.get("function") or {}
        name = function.get("name")
        if not isinstance(name, str) or name in result:
            raise RuntimeError("冻结 tool schema 身份无效")
        result[name] = function.get("parameters") or {"type": "object"}
    return result


def parse_output(raw: str, visible: str, tools: list[dict[str, Any]], tool_calls_so_far: int) -> dict[str, Any]:
    blocks = TOOL_BLOCK_RE.findall(raw)
    if not blocks:
        if any(marker in raw for marker in TOOL_MARKERS):
            return {"class": "malformed-tool-attempt", "syntax": False, "actions": [], "attempted": [], "failures": ["incomplete-tool-block"]}
        text = raw.replace("<|im_end|>", "").strip()
        output_class = "terminal-text" if visible.strip() or text else "empty"
        return {"class": output_class, "syntax": output_class == "terminal-text", "actions": [], "attempted": [], "failures": [] if output_class == "terminal-text" else ["empty"]}
    parsed = []
    for index, block in enumerate(blocks, start=1):
        try:
            parsed.append(json.loads(block))
        except json.JSONDecodeError as error:
            return {"class": "malformed-tool-attempt", "syntax": False, "actions": [], "attempted": [], "failures": [f"call-{index}:json:{error.msg}"]}
    schemas = tool_schemas(tools)
    attempted = []
    failures = []
    for index, value in enumerate(parsed, start=1):
        if not isinstance(value, dict):
            failures.append(f"call-{index}:not-object")
            continue
        name, arguments = value.get("name"), value.get("arguments")
        if not isinstance(name, str):
            failures.append(f"call-{index}:name")
            continue
        if name not in schemas:
            failures.append(f"call-{index}:unknown:{name}")
            continue
        if not isinstance(arguments, dict):
            failures.append(f"call-{index}:arguments")
            continue
        failures.extend(validate_json(arguments, schemas[name], f"call-{index}.arguments"))
        attempted.append({"name": name, "arguments": arguments})
    if tool_calls_so_far + len(parsed) > 16:
        failures.append("tool-cap")
    return {
        "class": "invalid-native-tool" if failures else "native-tool",
        "syntax": not failures,
        "actions": [] if failures else attempted,
        "attempted": attempted,
        "failures": failures,
    }


def current_rows(snapshot: dict[str, Any], namespace: str) -> list[dict[str, Any]]:
    rows = list((snapshot.get("_dbs") or {}).get(namespace) or [])
    if not rows:
        return []
    maximum = max(int(row.get("sandbox_message_index") or 0) for row in rows)
    fields = spec.SEMANTIC_ALLOWLIST[namespace]
    selected = [
        row for row in rows
        if int(row.get("sandbox_message_index") or 0) == maximum
        and any(row.get(field) is not None for field in fields)
    ]
    return selected


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


def projection(snapshot: dict[str, Any], bindings: dict[str, Any]) -> dict[str, Any]:
    reverse = {str(value): str(role) for role, value in bindings.items() if isinstance(value, str)}
    namespaces = {}
    for name, fields in spec.SEMANTIC_ALLOWLIST.items():
        rows = [
            {field: normalize(row.get(field), reverse) for field in fields}
            for row in current_rows(snapshot, name)
        ]
        rows.sort(key=spec.canonical_json)
        namespaces[name] = rows
    return {"namespaces": namespaces, "sha256": spec.canonical_sha256(namespaces)}


def row_matches(row: dict[str, Any], predicate: dict[str, Any]) -> bool:
    return all(row.get(field) == value for field, value in predicate.items())


def environment_debt(snapshot: dict[str, Any], baseline: dict[str, Any], patch: dict[str, Any]) -> bool:
    if patch["operation"] == "none":
        return False
    current = [
        {field: row.get(field) for field in spec.SEMANTIC_ALLOWLIST[patch["namespace"]]}
        for row in current_rows(snapshot, patch["namespace"])
    ]
    original = [
        {field: row.get(field) for field in spec.SEMANTIC_ALLOWLIST[patch["namespace"]]}
        for row in current_rows(baseline, patch["namespace"])
    ]
    if patch["operation"] == "remove_rows_added_after_baseline":
        predicate = patch["predicate"]
        return sum(row_matches(row, predicate) for row in current) > sum(row_matches(row, predicate) for row in original)
    if patch["operation"] == "restore_baseline_row_if_missing_or_changed":
        key = patch["key"]
        return [row for row in current if row_matches(row, key)] != [row for row in original if row_matches(row, key)]
    raise ValueError(patch["operation"])


def flat_environment(snapshot: dict[str, Any]) -> dict[str, Any]:
    values = {}
    for name in spec.SEMANTIC_ALLOWLIST:
        rows = current_rows(snapshot, name)
        if len(rows) == 1:
            for field, value in rows[0].items():
                values[f"{name}.{field}"] = value
    return values


def goal_reached(snapshot: dict[str, Any], predicate: dict[str, Any]) -> bool:
    kind = predicate["error_kind"]
    if kind == "weekday-target-timestamp-shift":
        return any(
            str(row.get("content") or "").casefold() == "buy chocolate milk"
            and row.get("reminder_timestamp") == predicate["oracle_value"]
            for row in current_rows(snapshot, "REMINDER")
        )
    if kind == "last-outgoing-recipient-id-substitution":
        return any(
            row.get("person_id") == predicate["oracle_value"]
            and row.get("phone_number") == "+10293847563"
            for row in current_rows(snapshot, "CONTACT")
        )
    if kind == "low-battery-boolean-negation":
        rows = current_rows(snapshot, "SETTING")
        return len(rows) == 1 and rows[0].get("low_battery_mode") is False and rows[0].get("wifi") is True
    raise ValueError(kind)


def parse_execution(execution: dict[str, Any] | None) -> Any:
    if execution is None or execution.get("exception") is not None:
        return None
    try:
        return ast.literal_eval(str(execution.get("content") or ""))
    except (SyntaxError, ValueError):
        return execution.get("content")


def action_matches(candidate: dict[str, Any], predicate: dict[str, Any], bindings: dict[str, Any]) -> bool:
    if candidate.get("name") != predicate.get("tool"):
        return False
    arguments = candidate.get("arguments") or {}
    if any(arguments.get(key) != value for key, value in predicate.get("arguments_contains", {}).items()):
        return False
    if any(str(arguments.get(key, "")).casefold() != str(value).casefold() for key, value in predicate.get("arguments_casefold", {}).items()):
        return False
    binding = predicate.get("binding_argument")
    if binding:
        return binding["binding"] in bindings and arguments.get(binding["argument"]) == bindings[binding["binding"]]
    return True


def f_event(candidate, error_predicate, environment, preceding, prior_execution, bindings) -> bool:
    if not action_matches(candidate, error_predicate, bindings):
        return False
    if any(environment.get(key) != value for key, value in error_predicate.get("when_environment", {}).items()):
        return False
    blocker = error_predicate.get("unless_preceded_by")
    if blocker:
        for index, action in enumerate(preceding):
            record = prior_execution[index] if index < len(prior_execution) else None
            if action_matches(action, blocker, bindings) and record is not None and record.get("exception") is None:
                return False
    return True


def route(decisions: list[dict[str, Any]]) -> str:
    first_v = next((i for i, row in enumerate(decisions) if row["V"]), None)
    first_g = next((i for i, row in enumerate(decisions) if row["G"]), None)
    clears = [value for value in (first_v, first_g) if value is not None]
    if clears and any(row["F"] for row in decisions[min(clears) + 1 :]):
        return "recover-then-relapse"
    if first_g is not None and first_v is None:
        return "direct-use"
    if first_v is not None and first_g is not None and first_v <= first_g:
        return "verify-then-recover"
    if first_v is not None:
        return "verify-only"
    return "no-recovery"


def decision_signature(output_class: str, actions: list[dict[str, Any]], visible: str, raw: str) -> str:
    if output_class == "native-tool":
        payload: Any = {"output_class": output_class, "actions": actions}
    else:
        text = visible if visible else raw
        payload = {"output_class": output_class, "visible_text_sha256": hashlib.sha256(text.encode()).hexdigest()}
    return spec.canonical_sha256(payload)


def independent_signature(decisions: list[dict[str, Any]], bindings: dict[str, Any], initial_b: bool, initial_e: bool) -> tuple[str, dict[str, Any]]:
    reverse = {str(value): str(role) for role, value in bindings.items() if isinstance(value, str)}
    rows = []
    for decision in decisions:
        rows.append(
            {
                "decision_index": decision["decision_index"],
                "output_class": decision["output_class"],
                "attempted_actions": normalize(decision["attempted_actions"], reverse),
                "execution": [
                    {
                        "tool": item.get("tool"),
                        "value": normalize(parse_execution(item), reverse),
                        "exception": item.get("exception") is not None,
                    }
                    for item in decision["execution"]
                ],
                "F": decision["F"], "V": decision["V"], "G": decision["G"],
                "B": decision["B"], "E": decision["E"], "T": decision["T"],
                "goal_completed": decision["goal_completed"],
                "terminal_before_goal_completion": decision["terminal_before_goal_completion"],
                "non_tool_text_sha256": decision_signature(
                    decision["output_class"], decision["actions"],
                    decision["visible"], decision["raw"],
                ) if decision["output_class"] != "native-tool" else None,
            }
        )
    payload = {"initial_B": initial_b, "initial_E": initial_e, "decisions": rows, "route": route(decisions)}
    return spec.canonical_sha256(payload), payload


def verify_unit(
    artifact: dict[str, Any],
    expected_unit: dict[str, Any],
    episode: dict[str, Any],
    predicate: dict[str, Any],
    patch: dict[str, Any],
    stimulus: dict[str, Any],
    baseline: dict[str, Any],
    scenario: Any,
) -> tuple[dict[str, Any], list[str]]:
    failures = []
    uid = expected_unit["unit_id"]
    if artifact.get("status") != "succeeded" or artifact.get("unit") != expected_unit:
        failures.append(f"{uid}:identity-or-status")
        return {}, failures
    raw_decisions = artifact.get("decisions") or []
    if len(raw_decisions) != 4:
        failures.append(f"{uid}:decision-count")
        return {}, failures
    checkpoint = artifact.get("checkpoint") or {}
    initial_b = expected_unit["condition"] != "A_N"
    first_before = raw_decisions[0].get("raw_snapshot_before")
    if not isinstance(first_before, dict):
        failures.append(f"{uid}:missing-first-snapshot")
        return {}, failures
    initial_e = environment_debt(first_before, baseline, patch)
    if checkpoint.get("B") is not initial_b or checkpoint.get("E") is not initial_e:
        failures.append(f"{uid}:checkpoint-BE")
    if checkpoint.get("target_model_decisions_before_checkpoint") != 0:
        failures.append(f"{uid}:pretarget-decision")
    if checkpoint.get("messages_sha256") != stimulus["messages_sha256"]:
        failures.append(f"{uid}:messages-hash")
    if raw_decisions[0].get("input_ids_sha256") != stimulus["input_ids_sha256"]:
        failures.append(f"{uid}:first-input-hash")
    if raw_decisions[0].get("input_token_count") != stimulus["input_token_count"]:
        failures.append(f"{uid}:first-input-count")
    if spec.canonical_sha256(first_before) != checkpoint.get("raw_snapshot_sha256"):
        failures.append(f"{uid}:checkpoint-raw-hash")

    bindings = dict(episode.get("dynamic_roles") or {})
    if expected_unit["module"] == "E":
        bindings.update(episode["predecessor_checkpoint"].get("dynamic_roles") or {})
    debt = initial_b
    recomputed = []
    total_tool_calls = 0
    goal_seen = goal_reached(first_before, predicate)
    for decision_index, source in enumerate(raw_decisions, start=1):
        raw_before = source.get("raw_snapshot_before")
        raw_after = source.get("raw_snapshot_after")
        if not isinstance(raw_before, dict) or not isinstance(raw_after, dict):
            failures.append(f"{uid}:decision-{decision_index}:snapshot")
            continue
        if spec.canonical_sha256(raw_before) != source.get("raw_snapshot_before_sha256"):
            failures.append(f"{uid}:decision-{decision_index}:before-hash")
        if spec.canonical_sha256(raw_after) != source.get("raw_snapshot_after_sha256"):
            failures.append(f"{uid}:decision-{decision_index}:after-hash")
        parsed = parse_output(
            str(source.get("raw_text") or ""),
            str(source.get("visible_content") or ""),
            episode["tool_schema"],
            total_tool_calls,
        )
        actions = parsed["actions"]
        attempted = parsed["attempted"] if parsed["class"] == "invalid-native-tool" else actions
        if parsed["class"] != source.get("output_class") or parsed["syntax"] != source.get("syntax_valid"):
            failures.append(f"{uid}:decision-{decision_index}:parser-class")
        if actions != source.get("parsed_actions"):
            failures.append(f"{uid}:decision-{decision_index}:parsed-actions")
        if attempted != source.get("attempted_actions"):
            failures.append(f"{uid}:decision-{decision_index}:attempted-actions")
        execution = source.get("execution") or []
        if parsed["class"] == "native-tool" and len(execution) != len(actions):
            failures.append(f"{uid}:decision-{decision_index}:execution-count")
        environment = flat_environment(raw_before)
        f_flags, v_flags, g_flags = [], [], []
        for index, candidate in enumerate(actions):
            record = execution[index] if index < len(execution) else None
            success = record is not None and record.get("exception") is None
            f_flag = f_event(candidate, predicate["error_action"], environment, actions[:index], execution[:index], bindings)
            if f_flag and success and predicate["error_action"].get("binds_success_result"):
                bindings[predicate["error_action"]["binds_success_result"]] = parse_execution(record)
            v_flag = any(
                success and action_matches(candidate, frozen, bindings) and parse_execution(record) == frozen.get("expected_result")
                for frozen in predicate.get("verification_actions", [])
            )
            g_flag = any(
                success and action_matches(candidate, frozen, bindings)
                for frozen in predicate.get("recovery_actions", [])
            )
            if v_flag or g_flag:
                debt = False
            if f_flag:
                debt = True
            f_flags.append(f_flag); v_flags.append(v_flag); g_flags.append(g_flag)
        total_tool_calls += len(actions)
        e_value = environment_debt(raw_after, baseline, patch)
        t_value = goal_reached(raw_after, predicate)
        goal_seen = goal_seen or t_value or any(
            (record is not None and record.get("exception") is None)
            and any(action_matches(candidate, frozen, bindings) for frozen in predicate.get("completion_actions", []))
            for candidate, record in zip(actions, execution)
        )
        terminal_before = parsed["class"] == "terminal-text" and not goal_seen
        decision = {
            "decision_index": decision_index,
            "output_class": parsed["class"],
            "actions": actions,
            "attempted_actions": attempted,
            "execution": execution,
            "F": any(f_flags), "V": any(v_flags), "G": any(g_flags),
            "B": debt, "E": e_value, "T": t_value,
            "goal_completed": goal_seen,
            "terminal_before_goal_completion": terminal_before,
            "visible": str(source.get("visible_content") or ""),
            "raw": str(source.get("raw_text") or ""),
        }
        recomputed.append(decision)
        for key, expected in (("F", decision["F"]), ("V", decision["V"]), ("G", decision["G"]), ("B", debt), ("E", e_value), ("T", t_value), ("goal_completed", goal_seen), ("terminal_before_goal_completion", terminal_before)):
            if source.get(key) is not expected:
                failures.append(f"{uid}:decision-{decision_index}:{key}")
        p = projection(raw_after, bindings)
        if p.get("sha256") != (source.get("semantic_projection_after") or {}).get("sha256"):
            failures.append(f"{uid}:decision-{decision_index}:semantic-projection")
    if len(recomputed) != 4:
        return {}, failures
    signature_hash, _ = independent_signature(recomputed, bindings, initial_b, initial_e)
    if signature_hash != (artifact.get("scientific_signature") or {}).get("sha256"):
        failures.append(f"{uid}:scientific-signature")
    if route(recomputed) != artifact.get("route"):
        failures.append(f"{uid}:route")
    metrics = {
        "L_B": sum(float(row["B"]) for row in recomputed) / 4.0,
        "L_E": sum(float(row["E"]) for row in recomputed) / 4.0,
        "F_count": sum(row["F"] for row in recomputed),
        "V_count": sum(row["V"] for row in recomputed),
        "G_count": sum(row["G"] for row in recomputed),
        "B_residual": float(recomputed[-1]["B"]),
        "E_residual": float(recomputed[-1]["E"]),
        "T": float(recomputed[-1]["T"]),
        "syntax_validity": sum(bool(source.get("syntax_valid")) for source in raw_decisions) / 4.0,
        "first_decision_native_tool": float(recomputed[0]["output_class"] == "native-tool"),
        "tool_call_count": total_tool_calls,
        "tool_exception_count": sum(item.get("exception") is not None for row in recomputed for item in row["execution"]),
    }
    reported_metrics = artifact.get("metrics") or {}
    for key, value in metrics.items():
        if reported_metrics.get(key) != value:
            failures.append(f"{uid}:metric:{key}")

    # 官方 evaluator 从最终原始状态独立复算。
    import attrs
    from tool_sandbox.common.execution_context import ExecutionContext

    final_context = ExecutionContext.from_dict(artifact["ending_snapshot"])
    official = attrs.asdict(
        scenario.evaluation.evaluate(execution_context=final_context, max_turn_count=scenario.max_messages)
    )
    if official != artifact.get("evaluation"):
        failures.append(f"{uid}:official-evaluator")
    return {
        "unit": expected_unit,
        "metrics": metrics,
        "route": route(recomputed),
        "scientific_signature_sha256": signature_hash,
        "first_input_ids_sha256": raw_decisions[0].get("input_ids_sha256"),
        "checkpoint_semantic_sha256": (checkpoint.get("semantic_projection") or {}).get("sha256"),
        "checkpoint_raw_sha256": checkpoint.get("raw_snapshot_sha256"),
        "official_similarity": float(official.get("similarity", 0.0)),
        "request_ids": [source.get("request_id") for source in raw_decisions],
    }, failures


def family_equal(rows: list[dict[str, Any]], value_key: str) -> float:
    by_family: dict[str, list[float]] = defaultdict(list)
    for row in rows:
        by_family[row["unit"]["family"]].append(float(row[value_key]))
    return sum(sum(values) / len(values) for values in by_family.values()) / len(by_family)


def descriptive_axes(rows: list[dict[str, Any]]) -> dict[str, Any]:
    base_rows = [row for row in rows if row["unit"]["repeat"] == 1]
    lookup = {
        (r["unit"]["episode_id"], r["unit"]["precision"], r["unit"]["module"], r["unit"]["condition"], r["unit"]["gap"]): r
        for r in base_rows
    }
    results = {}
    for precision in RUN_PRECISIONS:
        episodes = sorted({r["unit"]["episode_id"] for r in base_rows if r["unit"]["precision"] == precision})
        contrasts: dict[str, list[dict[str, Any]]] = {"a": [], "v": [], "c": []}
        for episode in episodes:
            family = next(r["unit"]["family"] for r in base_rows if r["unit"]["episode_id"] == episode)
            def mean_cell(module, condition, gaps):
                values = [lookup[(episode, precision, module, condition, gap)]["metrics"]["L_B"] for gap in gaps if (episode, precision, module, condition, gap) in lookup]
                return sum(values) / len(values) if values else None
            an, ae = mean_cell("A", "A_N", (0, 3)), mean_cell("A", "A_E", (0, 3))
            r0, ra, rf = mean_cell("R", "R0", (0, 3)), mean_cell("R", "R_audit", (0, 3)), mean_cell("R", "R_fact", (0, 3))
            if an is not None and ae is not None:
                contrasts["a"].append({"unit": {"family": family}, "value": ae - an})
            if r0 is not None and ra is not None:
                contrasts["v"].append({"unit": {"family": family}, "value": r0 - ra})
            if ra is not None and rf is not None:
                contrasts["c"].append({"unit": {"family": family}, "value": ra - rf})
        results[precision] = {
            axis: (family_equal(values, "value") if values else None)
            for axis, values in contrasts.items()
        }
    return {"scope": "development-descriptive-only-not-confirmatory-Theta_Q", "axes": results}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--runs-root", type=Path, required=True)
    parser.add_argument("--run-prefix", default="QHIST-E0-v12-traj")
    parser.add_argument("--assets", type=Path, required=True)
    parser.add_argument("--rendered", type=Path, required=True)
    parser.add_argument("--preflight", type=Path, required=True)
    parser.add_argument("--qualification-audit", type=Path, required=True)
    parser.add_argument("--toolsandbox-source", type=Path, required=True)
    parser.add_argument("--incremental-cost-usd", type=float, default=0.0)
    parser.add_argument("--stage-gpu-cap-hours", type=float, default=8.0)
    parser.add_argument("--minimum-free-disk-gb", type=float, default=50.0)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        raise RuntimeError(f"拒绝覆盖既有 E0 审计：{args.output}")
    args.output.parent.mkdir(parents=True, exist_ok=True)
    revision = __import__("subprocess").run(["git", "-C", str(args.toolsandbox_source), "rev-parse", "HEAD"], check=True, capture_output=True, text=True).stdout.strip()
    if revision != spec.UPSTREAM_COMMIT:
        raise RuntimeError("ToolSandbox revision 漂移")

    preflight = load(args.preflight)
    qualification = load(args.qualification_audit)
    episodes = {row["episode_id"]: row for row in load_jsonl(args.assets / "episodes.jsonl")}
    predicates = {row["episode_id"]: row for row in load_jsonl(args.assets / "predicates.jsonl")}
    patches = {row["episode_id"]: row for row in load_jsonl(args.assets / "environment-patches.jsonl")}
    stimuli = {(row["episode_id"], row["module"], row["condition"], int(row["gap"])): row for row in load_jsonl(args.rendered / "stimuli.jsonl")}
    expected_units = {row["unit_id"]: row for row in spec.build_trajectory_units()}
    baselines = {episode_id: load(args.assets / episode["snapshot"]) for episode_id, episode in episodes.items()}
    scenarios = toolsandbox_base.named_scenarios(preferred_tool_backend=toolsandbox_base.ToolBackend.DEFAULT)

    observed: dict[str, tuple[dict[str, Any], Path]] = {}
    summaries = {}
    server_summaries = {}
    artifact_failures = []
    for precision in RUN_PRECISIONS:
        root = args.runs_root / f"{args.run_prefix}-{precision}-r1"
        summaries[precision] = load(root / "summary.json")
        server_summaries[precision] = load(root / "server" / "summary.json")
        driver = root / "driver"
        driver_summary = load(driver / "summary.json")
        if driver_summary.get("status") != "succeeded":
            artifact_failures.append(f"{precision}:driver-summary")
        for row in load_jsonl(driver / "results.jsonl"):
            path = driver / row["artifact"]
            if not path.is_file() or sha256_file(path) != row["artifact_sha256"]:
                artifact_failures.append(f"{precision}:{row['unit_id']}:artifact")
                continue
            if row["unit_id"] in observed:
                artifact_failures.append(f"duplicate:{row['unit_id']}")
            else:
                observed[row["unit_id"]] = (load(path), path)

    missing = sorted(set(expected_units) - set(observed))
    extra = sorted(set(observed) - set(expected_units))
    failures = list(artifact_failures)
    failures.extend(f"missing:{uid}" for uid in missing)
    failures.extend(f"extra:{uid}" for uid in extra)
    verified_rows = []
    request_ids = []
    for uid in sorted(set(expected_units) & set(observed)):
        unit = expected_units[uid]
        artifact, _ = observed[uid]
        episode_id = unit["episode_id"]
        row, unit_failures = verify_unit(
            artifact, unit, episodes[episode_id], predicates[episode_id], patches[episode_id],
            stimuli[(episode_id, unit["module"], unit["condition"], int(unit["gap"]))],
            baselines[episode_id], scenarios[unit["scenario"]],
        )
        failures.extend(unit_failures)
        if row:
            verified_rows.append(row)
            request_ids.extend(row["request_ids"])

    implementation = {
        "all_192_units_present": len(observed) == len(expected_units) == 192 and not missing and not extra,
        "all_units_independently_recomputed": len(verified_rows) == 192 and not any(":decision-" in failure or ":metric:" in failure or ":scientific-signature" in failure or ":official-evaluator" in failure for failure in failures),
        "exactly_768_unique_requests": len(request_ids) == len(set(request_ids)) == 768,
        "all_combined_summaries_succeeded": all(summaries[p].get("status") == "succeeded" for p in RUN_PRECISIONS),
    }

    clean = {}
    clean_passes = []
    for precision in ("P00", "P11"):
        rows = [
            row for row in verified_rows
            if row["unit"]["precision"] == precision
            and row["unit"]["module"] == "A"
            and row["unit"]["condition"] == "A_N"
            and row["unit"]["gap"] == 3
            and row["unit"]["repeat"] == 1
        ]
        syntax = sum(row["metrics"]["syntax_validity"] for row in rows) / len(rows) if rows else 0.0
        native = sum(row["metrics"]["first_decision_native_tool"] for row in rows) / len(rows) if rows else 0.0
        positive = sum(row["official_similarity"] > 0 for row in rows)
        family_similarity = family_equal(rows, "official_similarity") if rows else 0.0
        precision_pass = len(rows) == 6 and syntax >= 0.95 and native >= 0.75 and positive >= 5
        clean_passes.append(precision_pass)
        clean[precision] = {
            "episodes": len(rows), "syntax_validity": syntax,
            "first_decision_native_tool_rate": native,
            "official_similarity_positive_episodes": positive,
            "family_equal_official_similarity": family_similarity,
            "per_precision_gate": precision_pass,
        }
    clean["P00_family_similarity_at_least_0_50"] = clean.get("P00", {}).get("family_equal_official_similarity", 0.0) >= 0.50
    drop = clean.get("P00", {}).get("family_equal_official_similarity", 0.0) - clean.get("P11", {}).get("family_equal_official_similarity", 0.0)
    clean["P00_minus_P11_similarity_drop"] = drop
    clean["drop_at_most_0_20"] = drop <= 0.20
    clean_pass = all(clean_passes) and clean["P00_family_similarity_at_least_0_50"] and clean["drop_at_most_0_20"]

    technical_cells = defaultdict(list)
    for row in verified_rows:
        unit = row["unit"]
        if unit["episode_id"] in spec.TECHNICAL_REPEAT_EPISODES and unit["module"] in {"A", "R"} and unit["condition"] in {"A_E", "R_fact"} and unit["gap"] == 3 and unit["precision"] in {"P00", "P11"}:
            technical_cells[(unit["episode_id"], unit["precision"], unit["module"], unit["condition"])].append(row)
    technical_details = []
    technical_pass = len(technical_cells) == 12
    for key, rows in sorted(technical_cells.items()):
        rows.sort(key=lambda row: row["unit"]["repeat"])
        checks = {
            "three_repeats": [row["unit"]["repeat"] for row in rows] == [1, 2, 3],
            "first_input_identical": len({row["first_input_ids_sha256"] for row in rows}) == 1,
            "semantic_checkpoint_identical": len({row["checkpoint_semantic_sha256"] for row in rows}) == 1,
            "scientific_signature_identical": len({row["scientific_signature_sha256"] for row in rows}) == 1,
            "L_B_range_at_most_0_02": max(row["metrics"]["L_B"] for row in rows) - min(row["metrics"]["L_B"] for row in rows) <= 0.02,
            "L_E_range_at_most_0_02": max(row["metrics"]["L_E"] for row in rows) - min(row["metrics"]["L_E"] for row in rows) <= 0.02,
        }
        technical_pass &= all(checks.values())
        technical_details.append({"cell": key, "checks": checks, "L_B": [row["metrics"]["L_B"] for row in rows], "L_E": [row["metrics"]["L_E"] for row in rows]})
    contrast_range = max(
        [max(item["L_B"]) - min(item["L_B"]) for item in technical_details] or [math.inf]
    )
    technical_pass &= contrast_range <= 0.01

    trajectory_gpu_seconds = sum(float(server_summaries[p].get("gpu_resident_seconds") or 0.0) for p in RUN_PRECISIONS)
    qualification_gpu_seconds = 0.0
    for item in qualification.get("artifacts", []):
        path = Path(item["path"])
        if path.name == "summary.json" and path.is_file():
            qualification_gpu_seconds += float(load(path).get("gpu_resident_seconds") or 0.0)
    gpu_hours = (trajectory_gpu_seconds + qualification_gpu_seconds) / 3600.0
    free_disk_gb = shutil.disk_usage(args.runs_root).free / (1024 ** 3)
    resource = {
        "trajectory_gpu_seconds": trajectory_gpu_seconds,
        "qualification_gpu_seconds": qualification_gpu_seconds,
        "stage_gpu_hours": gpu_hours,
        "stage_gpu_cap_hours": args.stage_gpu_cap_hours,
        "incremental_cost_usd": args.incremental_cost_usd,
        "free_disk_gb": free_disk_gb,
        "minimum_free_disk_gb": args.minimum_free_disk_gb,
        "passed": gpu_hours <= args.stage_gpu_cap_hours and args.incremental_cost_usd == 0.0 and free_disk_gb >= args.minimum_free_disk_gb,
    }

    gates = {
        "preflight": preflight.get("status") == "passed",
        "qualification_30_of_30": qualification.get("passed") is True and qualification.get("qualification_units") == 30,
        "implementation": all(implementation.values()) and not failures,
        "clean_configuration": clean_pass,
        "technical_reproducibility": technical_pass,
        "resource": resource["passed"],
        "target_effect_direction_used_as_gate": False,
    }
    passed = all(value for key, value in gates.items() if key != "target_effect_direction_used_as_gate") and gates["target_effect_direction_used_as_gate"] is False
    report = {
        "schema_version": 1,
        "protocol_id": spec.PROTOCOL_ID,
        "protocol_version": spec.PROTOCOL_VERSION,
        "status": "passed-enter-E1" if passed else "failed-stop-before-E1",
        "independence": {
            "imports_production_runner": False,
            "owns_output_parser": True,
            "owns_action_matcher": True,
            "owns_F_V_G_B_E_T_state_machine": True,
            "owns_semantic_projection": True,
            "reruns_official_evaluator": True,
        },
        "gates": gates,
        "implementation": implementation,
        "clean": clean,
        "technical": {"passed": technical_pass, "cells": technical_details, "maximum_development_contrast_repeat_range": contrast_range},
        "resource": resource,
        "descriptive_development_axes": descriptive_axes(verified_rows),
        "failures": failures,
        "missing_units": missing,
        "extra_units": extra,
        "verified_units": len(verified_rows),
        "unique_requests": len(set(request_ids)),
        "artifacts": {
            "preflight_sha256": sha256_file(args.preflight),
            "qualification_audit_sha256": sha256_file(args.qualification_audit),
            "assets_manifest_sha256": sha256_file(args.assets / "manifest.json"),
            "rendered_manifest_sha256": sha256_file(args.rendered / "manifest.json"),
        },
    }
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2, default=str) + "\n", encoding="utf-8")
    print(json.dumps({"status": report["status"], "gates": gates, "verified_units": len(verified_rows), "unique_requests": len(set(request_ids)), "failure_count": len(failures), "gpu_hours": gpu_hours, "free_disk_gb": free_disk_gb}, ensure_ascii=False, indent=2))
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
