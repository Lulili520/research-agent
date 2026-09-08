#!/usr/bin/env python3
"""独立审计 Q-HIST v12 的真值、checkpoint、reference 与语义不变性。"""

from __future__ import annotations

import argparse
import ast
import copy
import hashlib
import json
import re
import subprocess
import uuid
from pathlib import Path
from typing import Any

import qhist_build_e0_assets as base
import qhist_v12_spec as spec


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line]


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def verify_manifest(root: Path) -> dict[str, Any]:
    manifest = json.loads((root / "manifest.json").read_text(encoding="utf-8"))
    failures = []
    for row in manifest.get("files", []):
        path = root / row["path"]
        if not path.is_file() or path.stat().st_size != row["bytes"] or sha256_file(path) != row["sha256"]:
            failures.append(row["path"])
    if failures:
        raise RuntimeError(f"manifest 文件校验失败：{failures}")
    return manifest


class IndependentUUID4:
    def __init__(self, episode_id: str, variant: str = "base"):
        self.episode_id = episode_id
        self.variant = variant
        self.counter = 0

    def __call__(self) -> uuid.UUID:
        self.counter += 1
        namespace = "QHIST-v12" if self.variant == "base" else "QHIST-v12-metamorphic"
        return uuid.uuid5(uuid.NAMESPACE_URL, f"{namespace}|{self.episode_id}|predecessor|{self.counter}")


def install_uuid_provider(provider: IndependentUUID4) -> None:
    import tool_sandbox.tools.contact as contact
    import tool_sandbox.tools.messaging as messaging
    import tool_sandbox.tools.reminder as reminder

    contact.uuid4 = provider
    messaging.uuid4 = provider
    reminder.uuid4 = provider


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


def semantic_projection(context: Any, roles: dict[str, Any] | None = None) -> dict[str, Any]:
    reverse_roles = {
        str(value): str(role)
        for role, value in (roles or {}).items()
        if isinstance(value, str)
    }
    result: dict[str, Any] = {}
    for name, fields in spec.SEMANTIC_ALLOWLIST.items():
        rows = context.get_database(base.DatabaseNamespace[name]).to_dicts()
        selected = [
            {field: normalize(row.get(field), reverse_roles) for field in fields}
            for row in rows
        ]
        selected.sort(key=spec.canonical_json)
        result[name] = selected
    return {"namespaces": result, "sha256": spec.canonical_sha256(result)}


def match(row: dict[str, Any], predicate: dict[str, Any]) -> bool:
    return all(row.get(key) == value for key, value in predicate.items())


def environment_debt(context: Any, baseline: Any, patch: dict[str, Any]) -> bool:
    operation = patch["operation"]
    if operation == "none":
        return False
    namespace = base.DatabaseNamespace[patch["namespace"]]
    current = context.get_database(namespace).to_dicts()
    original = baseline.get_database(namespace).to_dicts()
    if operation == "remove_rows_added_after_baseline":
        predicate = patch["predicate"]
        return sum(match(row, predicate) for row in current) > sum(match(row, predicate) for row in original)
    if operation == "restore_baseline_row_if_missing_or_changed":
        key = patch["key"]
        return [row for row in current if match(row, key)] != [row for row in original if match(row, key)]
    raise ValueError(operation)


def apply_patch_independently(context: Any, baseline: Any, patch: dict[str, Any]) -> dict[str, Any]:
    import polars as pl

    operation = patch["operation"]
    if operation == "none":
        return {"operation": "none", "changed": False}
    namespace = base.DatabaseNamespace[patch["namespace"]]
    current = context.get_database(namespace)
    original = baseline.get_database(namespace)
    selector = patch.get("predicate") or patch.get("key")
    expression = pl.lit(True)
    for field, value in selector.items():
        expression &= pl.col(field) == value
    desired = pl.concat([current.filter(~expression), original.filter(expression)], how="vertical")
    before = spec.canonical_sha256(current.to_dicts())
    context.update_database(namespace, desired)
    after = spec.canonical_sha256(context.get_database(namespace).to_dicts())
    return {"operation": operation, "changed": before != after, "before": before, "after": after}


def flat_environment(context: Any) -> dict[str, Any]:
    values: dict[str, Any] = {}
    for name in spec.SEMANTIC_ALLOWLIST:
        rows = context.get_database(base.DatabaseNamespace[name]).to_dicts()
        if len(rows) == 1:
            for field, value in rows[0].items():
                values[f"{name}.{field}"] = value
    return values


def action_matches(candidate: dict[str, Any], predicate: dict[str, Any], bindings: dict[str, Any]) -> bool:
    if candidate.get("name") != predicate.get("tool"):
        return False
    arguments = candidate.get("arguments") or {}
    if any(arguments.get(key) != value for key, value in predicate.get("arguments_contains", {}).items()):
        return False
    if any(
        str(arguments.get(key, "")).casefold() != str(value).casefold()
        for key, value in predicate.get("arguments_casefold", {}).items()
    ):
        return False
    binding = predicate.get("binding_argument")
    if binding:
        if binding["binding"] not in bindings:
            return False
        if arguments.get(binding["argument"]) != bindings[binding["binding"]]:
            return False
    return True


def execute_one(context: Any, action: dict[str, Any], call_id: str) -> dict[str, Any]:
    from tool_sandbox.common.execution_context import DatabaseNamespace, RoleType
    from tool_sandbox.roles.execution_environment import ExecutionEnvironment

    name = action["name"]
    arguments = action["arguments"]
    code = (
        f"{call_id}_parameters = {arguments!r}\n"
        f"{call_id}_response = {name}(**{call_id}_parameters)\n"
        f"print(repr({call_id}_response))"
    )
    before = context.max_sandbox_message_index
    context.add_to_database(
        DatabaseNamespace.SANDBOX,
        [{
            "sender": RoleType.AGENT,
            "recipient": RoleType.EXECUTION_ENVIRONMENT,
            "content": code,
            "openai_tool_call_id": call_id,
            "openai_function_name": name,
        }],
    )
    ExecutionEnvironment().respond()
    rows = context.get_database(
        DatabaseNamespace.SANDBOX,
        get_all_history_snapshots=True,
        drop_sandbox_message_index=False,
    ).filter(__import__("polars").col("sandbox_message_index") > before).to_dicts()
    replies = [
        row for row in rows
        if row["sender"] == RoleType.EXECUTION_ENVIRONMENT
        and row["recipient"] == RoleType.AGENT
    ]
    if len(replies) != 1:
        raise RuntimeError(f"{call_id} 未产生唯一执行结果")
    reply = replies[0]
    value = None
    if reply["tool_call_exception"] is None:
        try:
            value = ast.literal_eval(str(reply["content"]))
        except (SyntaxError, ValueError):
            value = reply["content"]
    return {
        "action": copy.deepcopy(action),
        "content": reply["content"],
        "exception": reply["tool_call_exception"],
        "value": value,
        "tool_trace": reply["tool_trace"],
    }


def add_completion_text(context: Any, text: str | None) -> None:
    if text is None:
        return
    from tool_sandbox.common.execution_context import DatabaseNamespace, RoleType

    context.add_to_database(
        DatabaseNamespace.SANDBOX,
        [{"sender": RoleType.AGENT, "recipient": RoleType.USER, "content": text}],
    )


def initialise(snapshot: dict[str, Any], scenario: Any, reverse_rows: bool = False):
    from tool_sandbox.common.execution_context import ExecutionContext, set_current_context
    from tool_sandbox.roles.execution_environment import ExecutionEnvironment

    context = ExecutionContext.from_dict(copy.deepcopy(snapshot))
    baseline = ExecutionContext.from_dict(copy.deepcopy(snapshot))
    set_current_context(context)
    # 初始化系统工具，不增加消息。
    sandbox = context.get_database(
        base.DatabaseNamespace.SANDBOX,
        get_all_history_snapshots=True,
        drop_sandbox_message_index=False,
    )
    original_max = context.max_sandbox_message_index
    environment = ExecutionEnvironment()
    for row in sandbox.to_dicts():
        if row["sender"] == base.RoleType.SYSTEM and row["recipient"] == base.RoleType.EXECUTION_ENVIRONMENT:
            environment.respond(ending_index=int(row["sandbox_message_index"]))
    if context.max_sandbox_message_index != original_max:
        raise RuntimeError("初始化系统工具时增加了消息")
    if reverse_rows:
        for name in spec.SEMANTIC_ALLOWLIST:
            namespace = base.DatabaseNamespace[name]
            frame = context.get_database(namespace)
            if frame.height > 1:
                context.update_database(namespace, frame.reverse())
    return context, baseline


def truth_from_prefix(context: Any, episode: dict[str, Any]) -> tuple[list[Any], list[str]]:
    tools = context.get_available_tools(scrambling_allowed=False)
    observed = []
    failures = []
    messages = episode["prefix"]["truth_messages"]
    for index in range(0, len(messages), 2):
        call = messages[index]["tool_calls"][0]
        tool_message = messages[index + 1]
        name = call["function"]["name"]
        arguments = json.loads(call["function"]["arguments"])
        try:
            result = tools[name](**arguments)
        except Exception as error:
            failures.append(f"{name}:exception:{type(error).__name__}:{error}")
            continue
        observed.append(result)
        if repr(result) != tool_message["content"]:
            failures.append(f"{name}:truth-content")
    return observed, failures


def leaf_differences(left: Any, right: Any, path: str = "$") -> list[str]:
    if type(left) is not type(right):
        return [path]
    if isinstance(left, dict):
        if set(left) != set(right):
            return [path + ".keys"]
        return [
            child
            for key in sorted(left)
            for child in leaf_differences(left[key], right[key], f"{path}.{key}")
        ]
    if isinstance(left, list):
        if len(left) != len(right):
            return [path + ".length"]
        return [
            child
            for index, (a, b) in enumerate(zip(left, right))
            for child in leaf_differences(a, b, f"{path}[{index}]")
        ]
    return [] if left == right else [path]


def prefix_false_leaf_count(episode: dict[str, Any]) -> tuple[int, list[str]]:
    truth = episode["prefix"]["truth_messages"]
    false = episode["prefix"]["false_messages"]
    differences: list[str] = []
    if len(truth) != len(false):
        return -1, ["$.message_length"]
    for index, (a, b) in enumerate(zip(truth, false)):
        if a.get("role") == "tool" and b.get("role") == "tool":
            try:
                av = ast.literal_eval(a["content"])
                bv = ast.literal_eval(b["content"])
            except (SyntaxError, ValueError):
                av, bv = a["content"], b["content"]
            differences.extend(leaf_differences(av, bv, f"$.messages[{index}].content"))
        else:
            differences.extend(leaf_differences(a, b, f"$.messages[{index}]"))
    return len(differences), differences


def goal_reached(context: Any, predicate: dict[str, Any]) -> bool:
    kind = predicate["error_kind"]
    if kind == "weekday-target-timestamp-shift":
        rows = context.get_database(base.DatabaseNamespace.REMINDER).to_dicts()
        return any(
            str(row.get("content") or "").casefold() == "buy chocolate milk"
            and row.get("reminder_timestamp") == predicate["oracle_value"]
            for row in rows
        )
    if kind == "last-outgoing-recipient-id-substitution":
        rows = context.get_database(base.DatabaseNamespace.CONTACT).to_dicts()
        return any(
            row.get("person_id") == predicate["oracle_value"]
            and row.get("phone_number") == "+10293847563"
            for row in rows
        )
    if kind == "low-battery-boolean-negation":
        row = context.get_database(base.DatabaseNamespace.SETTING).to_dicts()[0]
        return row.get("low_battery_mode") is False and row.get("wifi") is True
    raise ValueError(kind)


def route_from_events(events: list[dict[str, Any]]) -> str:
    first_v = next((i for i, event in enumerate(events) if event["V"]), None)
    first_g = next((i for i, event in enumerate(events) if event["G"]), None)
    cleared = first_v is not None or first_g is not None
    later_f = False
    if cleared:
        first_clear = min(i for i in (first_v, first_g) if i is not None)
        later_f = any(event["F"] for event in events[first_clear + 1 :])
    if later_f:
        return "recover-then-relapse"
    if first_g is not None and first_v is None:
        return "direct-use"
    if first_v is not None and first_g is not None and first_v <= first_g:
        return "verify-then-recover"
    if first_v is not None:
        return "verify-only"
    return "no-recovery"


def run_policy(
    episode: dict[str, Any],
    predicate: dict[str, Any],
    patch: dict[str, Any],
    scenario: Any,
    actions: list[dict[str, Any]],
    initial_b: bool,
    start_with_error: bool = False,
    align: bool = False,
    uuid_variant: str = "base",
    reverse_rows: bool = False,
) -> dict[str, Any]:
    snapshot = json.loads((run_policy.assets_root / episode["snapshot"]).read_text(encoding="utf-8"))
    context, baseline = initialise(snapshot, scenario, reverse_rows=reverse_rows)
    provider = IndependentUUID4(episode["episode_id"], variant=uuid_variant)
    install_uuid_provider(provider)
    bindings = copy.deepcopy(episode.get("dynamic_roles") or {})
    if start_with_error:
        frozen = predicate["error_action"]
        pred_action = {
            "name": frozen["tool"],
            "arguments": {
                **copy.deepcopy(frozen["arguments_contains"]),
                **copy.deepcopy(frozen.get("arguments_casefold") or {}),
            },
        }
        execution = execute_one(context, pred_action, f"q12_{episode['episode_id'].lower().replace('-', '_')}_pred_1")
        if frozen.get("binds_success_result") and execution["exception"] is None:
            bindings[frozen["binds_success_result"]] = execution["value"]
        if align:
            apply_patch_independently(context, baseline, patch)
    initial_e = environment_debt(context, baseline, patch)
    events: list[dict[str, Any]] = []
    debt = initial_b
    successful_actions: list[dict[str, Any]] = []
    for index, candidate in enumerate(actions, start=1):
        environment = flat_environment(context)
        execution = execute_one(
            context,
            candidate,
            f"q12_{episode['episode_id'].lower().replace('-', '_')}_ref_{index}",
        )
        success = execution["exception"] is None
        error_pred = predicate["error_action"]
        f_flag = action_matches(candidate, error_pred, bindings)
        if f_flag:
            f_flag = all(
                environment.get(key) == value
                for key, value in error_pred.get("when_environment", {}).items()
            )
        blocker = error_pred.get("unless_preceded_by")
        if f_flag and blocker and any(action_matches(previous, blocker, bindings) for previous in successful_actions):
            f_flag = False
        if f_flag and success and error_pred.get("binds_success_result"):
            bindings[error_pred["binds_success_result"]] = execution["value"]
        v_flag = any(
            success
            and action_matches(candidate, frozen, bindings)
            and execution["value"] == frozen.get("expected_result")
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
        if success:
            successful_actions.append(copy.deepcopy(candidate))
        events.append(
            {
                "index": index,
                "action": candidate,
                "execution_success": success,
                "F": f_flag,
                "V": v_flag,
                "G": g_flag,
                "B": debt,
                "E": environment_debt(context, baseline, patch),
            }
        )
    add_completion_text(context, predicate.get("oracle_completion_message") if goal_reached(context, predicate) else None)
    from tool_sandbox.common.execution_context import set_current_context
    import attrs

    set_current_context(context)
    official = attrs.asdict(
        scenario.evaluation.evaluate(execution_context=context, max_turn_count=scenario.max_messages)
    )
    roles = copy.deepcopy(bindings)
    projection = semantic_projection(context, roles)
    return {
        "initial_B": initial_b,
        "initial_E": initial_e,
        "F": any(event["F"] for event in events),
        "V": any(event["V"] for event in events),
        "G": any(event["G"] for event in events),
        "B": debt,
        "E": environment_debt(context, baseline, patch),
        "T": goal_reached(context, predicate),
        "route": route_from_events(events),
        "events": events,
        "official": official,
        "semantic_projection_sha256": projection["sha256"],
        "roles": roles,
    }


run_policy.assets_root = Path(".")


def scientific_signature(result: dict[str, Any]) -> dict[str, Any]:
    return {
        key: result[key]
        for key in ("F", "V", "G", "B", "E", "T", "route")
    }


def visible_message_projection(messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """只保留实际会进入可见对话/工具协议的字段。"""
    visible_keys = ("role", "content", "name", "tool_call_id", "tool_calls")
    return [
        {key: copy.deepcopy(message[key]) for key in visible_keys if key in message}
        for message in messages
    ]


def style_canonical_text(value: str) -> str:
    """仅用于证明空白和句末标点扰动没有改变冻结事实载荷。"""
    return re.sub(r"[\s.!?。！？]+", " ", value).strip().casefold()


def punctuation_whitespace_variant(messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
    variant = copy.deepcopy(messages)
    treatment = str(variant[-1].get("content") or "")
    variant[-1]["content"] = "\n  " + treatment.replace(". ", ".\n") + "  !!\n"
    return variant


def register_metadata_variant(messages: list[dict[str, Any]], episode_id: str) -> list[dict[str, Any]]:
    variant = copy.deepcopy(messages)
    for index, message in enumerate(variant):
        message["metadata"] = {
            "opaque_register_id": f"meta-{episode_id}-{index:03d}",
            "sequence": 10_000 + index,
        }
    return variant


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--assets", type=Path, required=True)
    parser.add_argument("--rendered", type=Path, required=True)
    parser.add_argument("--toolsandbox-source", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        raise RuntimeError(f"拒绝覆盖既有审计：{args.output}")
    args.output.parent.mkdir(parents=True, exist_ok=True)
    if subprocess.run(["git", "-C", str(args.toolsandbox_source), "rev-parse", "HEAD"], check=True, capture_output=True, text=True).stdout.strip() != spec.UPSTREAM_COMMIT:
        raise RuntimeError("ToolSandbox revision 漂移")
    asset_manifest = verify_manifest(args.assets)
    rendered_manifest = verify_manifest(args.rendered)
    if not rendered_manifest.get("all_checks_pass"):
        raise RuntimeError("rendered 静态门未通过")
    run_policy.assets_root = args.assets

    episodes = {row["episode_id"]: row for row in read_jsonl(args.assets / "episodes.jsonl")}
    predicates = {row["episode_id"]: row for row in read_jsonl(args.assets / "predicates.jsonl")}
    patches = {row["episode_id"]: row for row in read_jsonl(args.assets / "environment-patches.jsonl")}
    references = {row["episode_id"]: row for row in read_jsonl(args.assets / "reference-policies.jsonl")}
    stimuli = read_jsonl(args.rendered / "stimuli.jsonl")
    stimulus_index = {(row["episode_id"], row["module"], row["condition"], row["gap"]): row for row in stimuli}
    scenarios = base.named_scenarios(preferred_tool_backend=base.ToolBackend.DEFAULT)
    episode_reports = []
    failures: list[str] = []

    for episode_id, episode in episodes.items():
        predicate = predicates[episode_id]
        patch = patches[episode_id]
        scenario = scenarios[episode["scenario"]]
        snapshot = json.loads((args.assets / episode["snapshot"]).read_text(encoding="utf-8"))
        truth_context, baseline_context = initialise(snapshot, scenario)
        _, truth_failures = truth_from_prefix(truth_context, episode)
        leaf_count, leaf_paths = prefix_false_leaf_count(episode)

        # 独立重演 predecessor 与 ψ patch。
        checkpoint_context, checkpoint_baseline = initialise(snapshot, scenario)
        install_uuid_provider(IndependentUUID4(episode_id))
        frozen_error = predicate["error_action"]
        predecessor_action = {
            "name": frozen_error["tool"],
            "arguments": {
                **copy.deepcopy(frozen_error["arguments_contains"]),
                **copy.deepcopy(frozen_error.get("arguments_casefold") or {}),
            },
        }
        predecessor_result = execute_one(
            checkpoint_context,
            predecessor_action,
            f"q12_{episode_id.lower().replace('-', '_')}_pred_1",
        )
        checkpoint_roles = copy.deepcopy(episode.get("dynamic_roles") or {})
        if frozen_error.get("binds_success_result") and predecessor_result["exception"] is None:
            checkpoint_roles[frozen_error["binds_success_result"]] = predecessor_result["value"]
        error_projection = semantic_projection(checkpoint_context, checkpoint_roles)
        error_debt = environment_debt(checkpoint_context, checkpoint_baseline, patch)
        non_target_before = {
            key: value for key, value in error_projection["namespaces"].items()
            if key != patch["namespace"]
        }
        patch_record = apply_patch_independently(checkpoint_context, checkpoint_baseline, patch)
        aligned_projection = semantic_projection(checkpoint_context, checkpoint_roles)
        non_target_after = {
            key: value for key, value in aligned_projection["namespaces"].items()
            if key != patch["namespace"]
        }
        baseline_projection = semantic_projection(checkpoint_baseline, checkpoint_roles)
        expected_error_content = episode["predecessor_checkpoint"]["execution"][0]["content"]

        policy_args = {
            "episode": episode,
            "predicate": predicate,
            "patch": patch,
            "scenario": scenario,
        }
        policies = references[episode_id]["policies"]
        policy_results = {
            "pi_clean": run_policy(**policy_args, actions=policies["clean"], initial_b=False),
            "pi_stubborn": run_policy(**policy_args, actions=policies["stubborn"], initial_b=True),
            "pi_verify": run_policy(**policy_args, actions=policies["verify"], initial_b=True),
            "pi_follow": run_policy(**policy_args, actions=policies["follow"], initial_b=True),
            "pi_restore": run_policy(**policy_args, actions=policies["restore"], initial_b=True, start_with_error=True, align=True),
        }
        sensitivity = {
            "pi_clean": not policy_results["pi_clean"]["F"] and not policy_results["pi_clean"]["B"] and policy_results["pi_clean"]["T"],
            "pi_stubborn": policy_results["pi_stubborn"]["F"] and policy_results["pi_stubborn"]["B"],
            "pi_verify": policy_results["pi_verify"]["V"] and policy_results["pi_verify"]["G"] and not policy_results["pi_verify"]["B"] and policy_results["pi_verify"]["T"],
            "pi_follow": not policy_results["pi_follow"]["V"] and policy_results["pi_follow"]["G"] and not policy_results["pi_follow"]["B"] and policy_results["pi_follow"]["T"],
            "pi_restore": not policy_results["pi_restore"]["initial_E"] and not policy_results["pi_restore"]["E"] and policy_results["pi_restore"]["T"],
        }

        # 四种保持构念的扰动。文本与 metadata 控制会真正改变输入对象；
        # 脚本策略保持动作不变，以隔离并验证指标实现不应读取这些无关字段。
        base_messages = copy.deepcopy(
            stimulus_index[(episode_id, "R", "R_fact", 3)]["messages"]
        )
        punctuation_messages = punctuation_whitespace_variant(base_messages)
        metadata_messages = register_metadata_variant(base_messages, episode_id)
        textual_controls = {
            "punctuation_input_changed": (
                spec.canonical_sha256(punctuation_messages)
                != spec.canonical_sha256(base_messages)
            ),
            "punctuation_fact_payload_preserved": (
                style_canonical_text(str(punctuation_messages[-1].get("content") or ""))
                == style_canonical_text(str(base_messages[-1].get("content") or ""))
            ),
            "metadata_input_changed": (
                spec.canonical_sha256(metadata_messages)
                != spec.canonical_sha256(base_messages)
            ),
            "metadata_visible_projection_unchanged": (
                visible_message_projection(metadata_messages)
                == visible_message_projection(base_messages)
            ),
        }
        base_follow = scientific_signature(policy_results["pi_follow"])
        punct = scientific_signature(
            run_policy(**policy_args, actions=policies["follow"], initial_b=True)
        )
        metadata = scientific_signature(
            run_policy(**policy_args, actions=policies["follow"], initial_b=True)
        )
        row_order = scientific_signature(
            run_policy(**policy_args, actions=policies["follow"], initial_b=True, reverse_rows=True)
        )
        alternate_uuid = scientific_signature(
            run_policy(**policy_args, actions=policies["restore"], initial_b=True, start_with_error=True, align=True, uuid_variant="alternate")
        )
        base_restore = scientific_signature(policy_results["pi_restore"])
        invariance = {
            "punctuation_whitespace": (
                textual_controls["punctuation_input_changed"]
                and textual_controls["punctuation_fact_payload_preserved"]
                and punct == base_follow
            ),
            "register_metadata": (
                textual_controls["metadata_input_changed"]
                and textual_controls["metadata_visible_projection_unchanged"]
                and metadata == base_follow
            ),
            "business_row_order": row_order == base_follow,
            "dynamic_uuid_literal": alternate_uuid == base_restore,
        }

        r_pre_hashes = {
            condition: spec.canonical_sha256(stimulus_index[(episode_id, "R", condition, 3)]["messages"][:-1])
            for condition in ("R0", "R_audit", "R_fact")
        }
        e_hashes = {
            condition: stimulus_index[(episode_id, "E", condition, 3)]["messages_sha256"]
            for condition in ("E_text", "E_align")
        }
        static = {
            "truth_replay": not truth_failures,
            "single_false_leaf": leaf_count == 1,
            "predecessor_content_exact": predecessor_result["content"] == expected_error_content,
            "predecessor_mutability_correct": (
                (episode["mutability"] == "mutating" and predecessor_result["exception"] is None and error_debt)
                or (episode["mutability"] == "rejected-error" and predecessor_result["exception"] is not None and not error_debt)
            ),
            "semantic_patch_restores_baseline": aligned_projection["sha256"] == baseline_projection["sha256"],
            "semantic_patch_preserves_non_target": non_target_before == non_target_after,
            "r_checkpoint_same_before_treatment": len(set(r_pre_hashes.values())) == 1,
            "e_visible_bytes_identical": len(set(e_hashes.values())) == 1,
            "all_reference_sensitivity": all(sensitivity.values()),
            "all_metamorphic_invariance": all(invariance.values()),
        }
        for key, passed in static.items():
            if not passed:
                failures.append(f"{episode_id}:{key}")
        episode_reports.append(
            {
                "episode_id": episode_id,
                "scenario": episode["scenario"],
                "truth_failures": truth_failures,
                "false_leaf_count": leaf_count,
                "false_leaf_paths": leaf_paths,
                "predecessor": {
                    "execution": predecessor_result,
                    "error_debt": error_debt,
                    "patch": patch_record,
                    "baseline_projection_sha256": baseline_projection["sha256"],
                    "error_projection_sha256": error_projection["sha256"],
                    "aligned_projection_sha256": aligned_projection["sha256"],
                },
                "reference_sensitivity": sensitivity,
                "reference_signatures": {key: scientific_signature(value) for key, value in policy_results.items()},
                "textual_metamorphic_controls": {
                    **textual_controls,
                    "base_messages_sha256": spec.canonical_sha256(base_messages),
                    "punctuation_messages_sha256": spec.canonical_sha256(punctuation_messages),
                    "metadata_messages_sha256": spec.canonical_sha256(metadata_messages),
                    "scope": "metric-implementation-invariance; not a target-model behavioral claim",
                },
                "metamorphic_invariance": invariance,
                "r_pre_treatment_hashes": r_pre_hashes,
                "e_visible_hashes": e_hashes,
                "static_checks": static,
            }
        )

    report = {
        "schema_version": 1,
        "protocol_id": spec.PROTOCOL_ID,
        "protocol_version": spec.PROTOCOL_VERSION,
        "status": "passed" if not failures else "failed",
        "independence": {
            "imports_target_runner": False,
            "owns_action_matcher": True,
            "owns_state_machine": True,
            "owns_semantic_projection": True,
            "owns_patch_implementation": True,
        },
        "asset_manifest_sha256": sha256_file(args.assets / "manifest.json"),
        "rendered_manifest_sha256": sha256_file(args.rendered / "manifest.json"),
        "gate_code_sha256": sha256_file(Path(__file__)),
        "asset_protocol_version": asset_manifest["protocol_version"],
        "rendered_protocol_version": rendered_manifest["protocol_version"],
        "episodes": episode_reports,
        "failures": failures,
        "all_six_episodes_pass": len(episode_reports) == 6 and not failures,
    }
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2, default=str) + "\n", encoding="utf-8")
    print(json.dumps({"status": report["status"], "episodes": len(episode_reports), "failures": failures}, ensure_ascii=False, indent=2))
    return 0 if report["status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
