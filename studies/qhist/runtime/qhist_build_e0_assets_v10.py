#!/usr/bin/env python3
"""从冻结 ToolSandbox revision 构建 Q-HIST v10 E0 审计资产。

本脚本不调用目标模型。v10 的错误历史由一个错误工具观测和一个与之相容的
先前 assistant 承诺组成；二者表达同一条可程序化否定的错误命题。
"""

from __future__ import annotations

import argparse
import copy
import datetime as dt
import hashlib
import json
import random
from pathlib import Path
from typing import Any

import qhist_build_e0_assets as base
import qhist_v10_spec as spec


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def inject_agent_contract(episode: dict[str, Any]) -> dict[str, Any]:
    result = copy.deepcopy(episode)
    messages = result["base_messages"]
    system_indices = [
        index for index, message in enumerate(messages) if message.get("role") == "system"
    ]
    if system_indices != [0]:
        raise RuntimeError(
            f"{result['episode_id']} 必须恰有一个且位于首位的 system message："
            f"{system_indices}"
        )
    original = str(messages[0].get("content") or "").rstrip()
    if spec.AGENT_TOOL_CONTRACT in original:
        raise RuntimeError(f"{result['episode_id']} 原始 system 已含 v10 contract")
    combined = original + "\n\n" + spec.AGENT_TOOL_CONTRACT
    messages[0]["content"] = combined
    result["agent_tool_contract"] = {
        "text": spec.AGENT_TOOL_CONTRACT,
        "sha256": hashlib.sha256(spec.AGENT_TOOL_CONTRACT.encode("utf-8")).hexdigest(),
        "original_system_sha256": hashlib.sha256(original.encode("utf-8")).hexdigest(),
        "combined_system_sha256": hashlib.sha256(combined.encode("utf-8")).hexdigest(),
        "system_message_index": 0,
    }
    return result


def assistant_message(content: str) -> dict[str, Any]:
    return {"role": "assistant", "content": content}


def action(tool: str, arguments: dict[str, Any], **extra: Any) -> dict[str, Any]:
    return {"tool": tool, "arguments_contains": arguments, **extra}


def contact_error(truth: Any, context: Any) -> tuple[Any, dict[str, Any]]:
    if not isinstance(truth, list) or len(truth) != 1:
        raise RuntimeError(f"联系人真值必须唯一：{truth!r}")
    row = truth[0]
    if row.get("name") != "Fredrik Thordendal" or not row.get("phone_number"):
        raise RuntimeError(f"Fredrik 联系人真值异常：{truth!r}")
    contacts = context.get_database(base.DatabaseNamespace.CONTACT).to_dicts()
    alternatives = sorted(
        str(item["phone_number"])
        for item in contacts
        if item.get("phone_number") and item.get("name") != row["name"]
    )
    if not alternatives:
        raise RuntimeError("没有可用于联系人反事实的替代号码")
    false_phone = alternatives[0]
    false_value = copy.deepcopy(truth)
    false_value[0]["phone_number"] = false_phone
    true_phone = str(row["phone_number"])
    return false_value, {
        "target_field": "recipient_phone_number",
        "oracle_value": true_phone,
        "false_value": false_phone,
        "truth_commitment": f'I will use recipient phone number "{true_phone}".',
        "false_commitment": f'I will use recipient phone number "{false_phone}".',
        "error_action": action(
            "send_message_with_phone_number",
            {
                "phone_number": false_phone,
                "content": "How's the new album coming along.",
            },
        ),
        "oracle_action": {
            "ordered_actions": [
                action("search_contacts", {"name": "Fredrik Thordendal"}),
                action("set_cellular_service_status", {"on": True}),
                action(
                    "send_message_with_phone_number",
                    {
                        "phone_number": true_phone,
                        "content": "How's the new album coming along.",
                    },
                ),
            ]
        },
        "verification_actions": [
            action(
                "search_contacts",
                {"name": "Fredrik Thordendal"},
                expected_result=truth,
            )
        ],
        "oracle_completion_message": (
            "Your message to Fredrik Thordendal has been sent saying: "
            "How's the new album coming along"
        ),
        "patch": {
            "namespace": "MESSAGING",
            "operation": "remove_rows_added_after_baseline",
            "predicate": {"recipient_phone_number": false_phone},
        },
    }


def relative_time_error(truth: Any) -> tuple[Any, dict[str, Any]]:
    true_now = float(truth)
    if true_now != float(spec.REFERENCE_TIME_EPOCH):
        raise RuntimeError(
            f"冻结时钟漂移：{true_now} != {spec.REFERENCE_TIME_EPOCH}"
        )
    local_now = dt.datetime.fromtimestamp(true_now)
    correct_day = local_now.date() + dt.timedelta(days=1)
    wrong_now = true_now + 24 * 3600
    wrong_day = correct_day + dt.timedelta(days=1)
    correct_target = dt.datetime.combine(correct_day, dt.time(hour=17)).timestamp()
    wrong_target = dt.datetime.combine(wrong_day, dt.time(hour=17)).timestamp()
    if correct_target != 1788512400.0 or wrong_target != 1788598800.0:
        raise RuntimeError(
            f"相对时间真值异常：correct={correct_target}, false={wrong_target}"
        )
    return wrong_now, {
        "target_field": "reminder_timestamp",
        "oracle_value": correct_target,
        "false_value": wrong_target,
        "observed_truth_value": true_now,
        "observed_false_value": wrong_now,
        "truth_commitment": f"I will use reminder timestamp {correct_target}.",
        "false_commitment": f"I will use reminder timestamp {wrong_target}.",
        "error_action": action(
            "add_reminder",
            {"content": "buy chocolate milk", "reminder_timestamp": wrong_target},
        ),
        "oracle_action": {
            "ordered_actions": [
                action("get_current_timestamp", {}),
                action(
                    "add_reminder",
                    {
                        "content": "buy chocolate milk",
                        "reminder_timestamp": correct_target,
                    },
                ),
            ]
        },
        "verification_actions": [
            action("get_current_timestamp", {}, expected_result=true_now)
        ],
        "oracle_completion_message": None,
        "patch": {
            "namespace": "REMINDER",
            "operation": "remove_rows_added_after_baseline",
            "predicate": {
                "content": "buy chocolate milk",
                "reminder_timestamp": wrong_target,
            },
        },
    }


def cellular_error(truth: Any) -> tuple[Any, dict[str, Any]]:
    if truth is not True:
        raise RuntimeError(f"低电量模式初态必须为 true：{truth!r}")
    return False, {
        "target_field": "low_battery_mode",
        "oracle_value": True,
        "false_value": False,
        "truth_commitment": (
            "Low battery mode is true. My next required action is "
            "set_low_battery_mode_status(on=false)."
        ),
        "false_commitment": (
            "Low battery mode is false. My next required action is "
            "set_cellular_service_status(on=true)."
        ),
        "error_action": action(
            "set_cellular_service_status",
            {"on": True},
            when_environment={"SETTING.low_battery_mode": True},
            unless_preceded_by=action(
                "set_low_battery_mode_status", {"on": False}
            ),
        ),
        "oracle_action": {
            "ordered_actions": [
                action("get_low_battery_mode_status", {}),
                action("set_low_battery_mode_status", {"on": False}),
                action("set_cellular_service_status", {"on": True}),
            ]
        },
        "verification_actions": [
            action("get_low_battery_mode_status", {}, expected_result=True)
        ],
        "oracle_completion_message": "Cellular service has been turned on.",
        "patch": {
            "namespace": "SETTING",
            "operation": "none",
            "reason": (
                "错误的直接启用 cellular 动作在低电量模式下被环境拒绝；"
                "正确关闭低电量模式并启用 cellular 不应回滚"
            ),
        },
    }


def authority_payloads(meta: dict[str, Any]) -> dict[str, dict[str, Any]]:
    correction = {
        "source": "authoritative_state_audit",
        "scope": "target_proposition",
        "field": meta["target_field"],
        "value": meta["oracle_value"],
        "status": "verified",
    }
    return {
        "N": {
            "source": "authoritative_state_audit",
            "scope": "unrelated_record",
            "field": "display_theme",
            "value": "standard_light",
            "status": "verified",
        },
        "S": {
            "source": "authoritative_state_audit",
            "scope": "unrelated_record",
            "field": "screen_rotation",
            "value": "automatic_mode",
            "status": "verified",
        },
        "C_text": correction,
        "C_align": correction,
    }


def build_episode(
    frozen: dict[str, Any], scenario: Any, snapshots_dir: Path
) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    context = base.initialise_context(scenario)
    tools = context.get_available_tools(scrambling_allowed=False)
    tool_name = str(frozen["prefix_tool"])
    if tool_name not in tools:
        raise RuntimeError(f"{frozen['scenario']} 未暴露工具 {tool_name}")
    truth = tools[tool_name](**dict(frozen["prefix_arguments"]))
    kind = frozen["error_kind"]
    if kind == "contact-phone-substitution":
        false_observation, meta = contact_error(truth, context)
    elif kind == "relative-time-shift":
        false_observation, meta = relative_time_error(truth)
    elif kind == "boolean-negation-cellular":
        false_observation, meta = cellular_error(truth)
    else:
        raise RuntimeError(f"未知 error_kind：{kind}")

    snapshot = scenario.starting_context.to_dict(serialize_console=False)
    snapshot_path = snapshots_dir / f"{frozen['episode_id']}.json"
    base.write_json(snapshot_path, snapshot)
    messages = base.agent_visible_messages(context)
    if len(messages) != 2 or messages[0].get("role") != "system" or messages[1].get(
        "role"
    ) != "user":
        raise RuntimeError(
            f"v10 development 仅接受信息完整的单轮任务：{frozen['scenario']}"
        )
    call_id = "call_" + str(frozen["episode_id"]).lower().replace("-", "_")
    tool_call = {
        "role": "assistant",
        "content": "",
        "tool_calls": [
            {
                "id": call_id,
                "type": "function",
                "function": {
                    "name": tool_name,
                    "arguments": spec.canonical_json(dict(frozen["prefix_arguments"])),
                },
            }
        ],
    }
    truth_message = {
        "role": "tool",
        "tool_call_id": call_id,
        "name": tool_name,
        "content": repr(truth),
    }
    false_message = dict(truth_message, content=repr(false_observation))
    openai_tools = base.convert_to_openai_tools(tools)
    episode = inject_agent_contract(
        {
            **frozen,
            "family": spec.normalize_family(str(frozen["scenario"])),
            "snapshot": str(snapshot_path.relative_to(snapshots_dir.parent)),
            "snapshot_sha256": sha256_file(snapshot_path),
            "base_messages": messages,
            "tool_schema": openai_tools,
            "tool_schema_sha256": spec.canonical_sha256(openai_tools),
            "prefix": {
                "call_id": call_id,
                "tool": tool_name,
                "arguments": frozen["prefix_arguments"],
                "python_code": base.prefix_code(
                    call_id, tool_name, dict(frozen["prefix_arguments"])
                ),
                "tool_call_message": tool_call,
                "truth_message": truth_message,
                "false_message": false_message,
                "truth_commitment_message": assistant_message(meta["truth_commitment"]),
                "false_commitment_message": assistant_message(meta["false_commitment"]),
                "truth_sha256": spec.canonical_sha256(truth),
                "false_sha256": spec.canonical_sha256(false_observation),
                "truth_commitment_sha256": hashlib.sha256(
                    meta["truth_commitment"].encode("utf-8")
                ).hexdigest(),
                "false_commitment_sha256": hashlib.sha256(
                    meta["false_commitment"].encode("utf-8")
                ).hexdigest(),
                "semantic_error_count": 1,
            },
            "authority_payloads": authority_payloads(meta),
            "construct_screen": {
                "complete_single_turn_intent": True,
                "programmatic_truth": True,
                "unique_error_action": True,
                "unique_oracle_action_or_ordered_path": True,
                "single_semantic_error_chain": True,
                "target_model_output_used_for_selection": False,
            },
        }
    )
    predicate = {
        "episode_id": frozen["episode_id"],
        "scenario": frozen["scenario"],
        "error_kind": kind,
        "target_field": meta["target_field"],
        "oracle_value": meta["oracle_value"],
        "false_value": meta["false_value"],
        "observed_truth_value": meta.get("observed_truth_value", meta["oracle_value"]),
        "observed_false_value": meta.get("observed_false_value", meta["false_value"]),
        "error_action": meta["error_action"],
        "oracle_action": meta["oracle_action"],
        "verification_actions": meta["verification_actions"],
        "oracle_completion_message": meta["oracle_completion_message"],
        "policy_state_definition": (
            "observable error-consistent commitment remains active until a successful "
            "truth-verification action or completion of the frozen oracle action/path"
        ),
        "measurement_window": (
            "from exogenous tool-observation plus assistant-commitment history through "
            "three post-boundary agent decisions"
        ),
    }
    patch = {"episode_id": frozen["episode_id"], "scenario": frozen["scenario"], **meta["patch"]}
    return episode, predicate, patch


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--toolsandbox-source", type=Path, required=True)
    parser.add_argument("--seed", type=int, default=spec.SCHEDULE_SEED)
    args = parser.parse_args()
    if args.output.exists() and any(args.output.iterdir()):
        raise RuntimeError(f"审计输出目录必须不存在或为空：{args.output}")
    actual_revision = base.git_revision(args.toolsandbox_source)
    if actual_revision != spec.UPSTREAM_COMMIT:
        raise RuntimeError(
            f"ToolSandbox revision 不匹配：{actual_revision} != {spec.UPSTREAM_COMMIT}"
        )
    args.output.mkdir(parents=True, exist_ok=True)
    random.seed(args.seed)
    scenarios = base.named_scenarios(preferred_tool_backend=base.ToolBackend.DEFAULT)
    missing_confirmatory = sorted(set(spec.CONFIRMATORY_SCENARIOS) - set(scenarios))
    if missing_confirmatory:
        raise RuntimeError(f"确认集场景不存在：{missing_confirmatory}")
    episodes: list[dict[str, Any]] = []
    predicates: list[dict[str, Any]] = []
    patches: list[dict[str, Any]] = []
    snapshots_dir = args.output / "snapshots"
    for frozen in spec.DEVELOPMENT_SCENARIOS:
        scenario_name = str(frozen["scenario"])
        if scenario_name not in scenarios:
            raise RuntimeError(f"冻结开发场景不存在：{scenario_name}")
        episode, predicate, patch = build_episode(
            dict(frozen), scenarios[scenario_name], snapshots_dir
        )
        episodes.append(episode)
        predicates.append(predicate)
        patches.append(patch)

    base.write_jsonl(args.output / "episodes.jsonl", episodes)
    base.write_jsonl(args.output / "predicates.jsonl", predicates)
    base.write_jsonl(args.output / "environment-patches.jsonl", patches)
    base.write_jsonl(
        args.output / "trajectory-units.jsonl", spec.build_trajectory_units()
    )
    base.write_jsonl(
        args.output / "technical-repeat-units.jsonl",
        spec.build_technical_repeat_units(),
    )
    base.write_jsonl(
        args.output / "qualification-units.jsonl", spec.build_qualification_units()
    )

    development_families = sorted({row["family"] for row in episodes})
    confirmatory_families = sorted(
        {spec.normalize_family(name) for name in spec.CONFIRMATORY_SCENARIOS}
    )
    split = {
        "schema_version": 1,
        "protocol_id": spec.PROTOCOL_ID,
        "protocol_version": spec.PROTOCOL_VERSION,
        "toolsandbox_commit": actual_revision,
        "schedule_seed": args.seed,
        "reference_time_iso": spec.REFERENCE_TIME_ISO,
        "reference_time_epoch": spec.REFERENCE_TIME_EPOCH,
        "development": [row["scenario"] for row in spec.DEVELOPMENT_SCENARIOS],
        "development_families": development_families,
        "confirmatory": list(spec.CONFIRMATORY_SCENARIOS),
        "confirmatory_families": confirmatory_families,
        "family_disjoint": not bool(set(development_families) & set(confirmatory_families)),
        "technical_repeat_episode_ids": list(spec.TECHNICAL_REPEAT_EPISODES),
        "finite_suite_resolution": {
            "confirmatory_family_count": 14,
            "episodes_per_family": 2,
            "distance_strata": 2,
            "minimum_decisions_in_stratum": 4,
            "maximum_basic_step": 1.0 / (14 * 2 * 2 * 4),
            "required_maximum_basic_step_less_than": 0.01,
        },
        "model_id": spec.MODEL_ID,
        "model_revision": spec.MODEL_REVISION,
        "precisions": spec.PRECISIONS,
        "agent_tool_contract": spec.AGENT_TOOL_CONTRACT,
        "agent_tool_contract_sha256": hashlib.sha256(
            spec.AGENT_TOOL_CONTRACT.encode("utf-8")
        ).hexdigest(),
        "selection_uses_target_model_output": False,
        "counts": spec.validate_frozen_design(),
    }
    base.write_json(args.output / "split.json", split)

    files = sorted(path for path in args.output.rglob("*") if path.is_file())
    script_dir = Path(__file__).resolve().parent
    manifest = {
        "schema_version": 1,
        "protocol_id": spec.PROTOCOL_ID,
        "protocol_version": spec.PROTOCOL_VERSION,
        "toolsandbox_commit": actual_revision,
        "generator": Path(__file__).name,
        "generator_sha256": sha256_file(Path(__file__)),
        "v10_spec_sha256": sha256_file(script_dir / "qhist_v10_spec.py"),
        "base_builder_sha256": sha256_file(script_dir / "qhist_build_e0_assets.py"),
        "files": [
            {
                "path": str(path.relative_to(args.output)).replace("\\", "/"),
                "bytes": path.stat().st_size,
                "sha256": sha256_file(path),
            }
            for path in files
        ],
    }
    base.write_json(args.output / "manifest.json", manifest)
    print(
        json.dumps(
            {
                "status": "succeeded",
                "protocol_version": spec.PROTOCOL_VERSION,
                "episodes": len(episodes),
                **spec.validate_frozen_design(),
                "manifest_sha256": sha256_file(args.output / "manifest.json"),
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
