#!/usr/bin/env python3
"""从冻结 ToolSandbox revision 构建 Q-HIST v11 E0 审计资产。

本脚本不调用目标模型。它只冻结新 development family 的真实初态、单一
错误命题、F/V/G 谓词、完整 oracle、环境 patch 与 boundary-fork 清单。
"""

from __future__ import annotations

import argparse
import copy
import hashlib
import json
import random
from pathlib import Path
from typing import Any

import qhist_build_e0_assets_v10 as previous
import qhist_v11_spec as spec


base = previous.base
action = previous.action
assistant_message = previous.assistant_message
inject_agent_contract = previous.inject_agent_contract
sha256_file = previous.sha256_file


def contact_id_error(truth: Any, context: Any) -> tuple[Any, dict[str, Any]]:
    if not isinstance(truth, list) or len(truth) != 1:
        raise RuntimeError(f"目标电话号码必须唯一命中联系人：{truth!r}")
    target = truth[0]
    if target.get("phone_number") != "+12453344098" or not target.get("person_id"):
        raise RuntimeError(f"目标联系人真值异常：{truth!r}")
    contacts = context.get_database(base.DatabaseNamespace.CONTACT).to_dicts()
    alternatives = sorted(
        (
            row
            for row in contacts
            if row.get("person_id") != target["person_id"] and row.get("is_self") is False
        ),
        key=lambda row: (
            row.get("name") != "John Petrucci",
            str(row.get("name")),
            str(row.get("person_id")),
        ),
    )
    if not alternatives:
        raise RuntimeError("没有可用于 person_id 反事实的非本人联系人")
    wrong = alternatives[0]
    false_observation = copy.deepcopy(truth)
    false_observation[0]["person_id"] = wrong["person_id"]
    true_id = str(target["person_id"])
    false_id = str(wrong["person_id"])
    target_lookup = {"phone_number": "+12453344098"}
    correct_remove = action("remove_contact", {"person_id": true_id})
    return false_observation, {
        "target_field": "contact_person_id",
        "oracle_value": true_id,
        "false_value": false_id,
        "truth_commitment": (
            f'The verified contact person_id is "{true_id}". '
            "I will remove that person_id."
        ),
        "false_commitment": (
            f'The verified contact person_id is "{false_id}". '
            "I will remove that person_id."
        ),
        "error_action": action("remove_contact", {"person_id": false_id}),
        "recovery_actions": [correct_remove],
        "completion_actions": [correct_remove],
        "oracle_action": {
            "ordered_actions": [
                action("search_contacts", target_lookup),
                correct_remove,
            ]
        },
        "verification_actions": [
            action("search_contacts", target_lookup, expected_result=truth)
        ],
        "oracle_completion_message": (
            "Phone number +12453344098 has been removed from your contact"
        ),
        "patch": {
            "namespace": "CONTACT",
            "operation": "restore_baseline_row_if_missing_or_changed",
            "key": {"person_id": false_id},
        },
        "dynamic_roles": {
            "target_contact_id": true_id,
            "error_contact_id": false_id,
        },
    }


def absolute_time_error(truth: Any) -> tuple[Any, dict[str, Any]]:
    true_timestamp = float(truth)
    if true_timestamp != 1711098000.0:
        raise RuntimeError(f"冻结绝对时间真值异常：{true_timestamp}")
    false_timestamp = true_timestamp + 24 * 3600
    content = "buy chocolate milk"
    correct_add = action(
        "add_reminder",
        {"content": content, "reminder_timestamp": true_timestamp},
    )
    correct_modify = action(
        "modify_reminder",
        {"reminder_timestamp": true_timestamp},
        binding_argument={
            "argument": "reminder_id",
            "binding": "error_entity_id",
        },
    )
    return false_timestamp, {
        "target_field": "reminder_timestamp",
        "oracle_value": true_timestamp,
        "false_value": false_timestamp,
        "truth_commitment": f"I will use reminder timestamp {true_timestamp}.",
        "false_commitment": f"I will use reminder timestamp {false_timestamp}.",
        "error_action": action(
            "add_reminder",
            {"content": content, "reminder_timestamp": false_timestamp},
            binds_success_result="error_entity_id",
        ),
        "recovery_actions": [correct_add, correct_modify],
        "completion_actions": [correct_add, correct_modify],
        "oracle_action": {
            "ordered_actions": [
                action(
                    "datetime_info_to_timestamp",
                    dict(spec.DEVELOPMENT_SCENARIOS[2]["prefix_arguments"]),
                ),
                correct_add,
            ]
        },
        "verification_actions": [
            action(
                "datetime_info_to_timestamp",
                dict(spec.DEVELOPMENT_SCENARIOS[2]["prefix_arguments"]),
                expected_result=true_timestamp,
            )
        ],
        "oracle_completion_message": None,
        "patch": {
            "namespace": "REMINDER",
            "operation": "remove_rows_added_after_baseline",
            "predicate": {
                "content": content,
                "reminder_timestamp": false_timestamp,
            },
        },
        "dynamic_roles": {},
    }


def location_error(truth: Any) -> tuple[Any, dict[str, Any]]:
    if truth is not True:
        raise RuntimeError(f"低电量模式初态必须为 true：{truth!r}")
    disable_low_battery = action("set_low_battery_mode_status", {"on": False})
    enable_location = action("set_location_service_status", {"on": True})
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
            "set_location_service_status(on=true)."
        ),
        "error_action": action(
            "set_location_service_status",
            {"on": True},
            when_environment={"SETTING.low_battery_mode": True},
            unless_preceded_by=disable_low_battery,
        ),
        "recovery_actions": [disable_low_battery],
        "completion_actions": [enable_location],
        "oracle_action": {
            "ordered_actions": [
                action("get_low_battery_mode_status", {}),
                disable_low_battery,
                enable_location,
            ]
        },
        "verification_actions": [
            action("get_low_battery_mode_status", {}, expected_result=True)
        ],
        "oracle_completion_message": "Location service has been turned on.",
        "patch": {
            "namespace": "SETTING",
            "operation": "none",
            "reason": (
                "错误的直接启用 location 动作在低电量模式下被环境拒绝；"
                "正确关闭低电量模式并启用 location 不应回滚"
            ),
        },
        "dynamic_roles": {},
    }


def authority_payloads(meta: dict[str, Any]) -> dict[str, dict[str, Any]]:
    correction = {
        "source": "authoritative_task_audit",
        "scope": "target_proposition",
        "field": meta["target_field"],
        "value": meta["oracle_value"],
        "status": "previous_observation_and_commitment_invalid",
        "task_status": "active_reassess_and_repair",
    }
    sham = {
        "source": "authoritative_task_audit",
        "scope": "target_proposition",
        "field": "withheld_target_value",
        "value": "not_supplied",
        "status": "previous_observation_and_commitment_unverified",
        "task_status": "active_reassess_and_repair",
    }
    return {"N": sham, "S": sham, "C_text": correction, "C_align": correction}


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
    if kind == "contact-id-substitution":
        false_observation, meta = contact_id_error(truth, context)
    elif kind == "absolute-time-shift":
        false_observation, meta = absolute_time_error(truth)
    elif kind == "boolean-negation-location":
        false_observation, meta = location_error(truth)
    else:
        raise RuntimeError(f"未知 error_kind：{kind}")

    snapshot = scenario.starting_context.to_dict(serialize_console=False)
    snapshot_path = snapshots_dir / f"{frozen['episode_id']}.json"
    base.write_json(snapshot_path, snapshot)
    messages = base.agent_visible_messages(context)
    if (
        len(messages) != 2
        or messages[0].get("role") != "system"
        or messages[1].get("role") != "user"
    ):
        raise RuntimeError(
            f"v11 development 仅接受信息完整的单轮任务：{frozen['scenario']}"
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
            "dynamic_roles": meta["dynamic_roles"],
            "construct_screen": {
                "complete_single_turn_intent": True,
                "programmatic_truth": True,
                "unique_error_action": True,
                "observable_recovery_certificate": True,
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
        "observed_truth_value": truth,
        "observed_false_value": false_observation,
        "error_action": meta["error_action"],
        "recovery_actions": meta["recovery_actions"],
        "completion_actions": meta["completion_actions"],
        "oracle_action": meta["oracle_action"],
        "verification_actions": meta["verification_actions"],
        "oracle_completion_message": meta["oracle_completion_message"],
        "policy_state_definition": (
            "error-consistent policy debt starts active under erroneous history, "
            "clears only on successful frozen truth verification or successful "
            "recovery certificate, and reactivates on any later error action"
        ),
        "measurement_window": (
            "shared erroneous trunk through distance d, then three post-boundary "
            "agent decisions per forked condition"
        ),
    }
    patch = {
        "episode_id": frozen["episode_id"],
        "scenario": frozen["scenario"],
        **meta["patch"],
    }
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
    base.write_jsonl(args.output / "trajectory-units.jsonl", spec.build_trajectory_units())
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
        "family_disjoint": not bool(
            set(development_families) & set(confirmatory_families)
        ),
        "technical_repeat_episode_ids": list(spec.TECHNICAL_REPEAT_EPISODES),
        "finite_suite_resolution": {
            "confirmatory_family_count": 11,
            "episodes_per_family": 2,
            "distance_strata": 2,
            "minimum_decisions_in_stratum": 4,
            "maximum_basic_step": 1.0 / (11 * 2 * 2 * 4),
            "required_maximum_basic_step_less_than": 0.01,
        },
        "boundary_fork": {
            "erroneous_histories": ["E", "S", "C_text", "C_align"],
            "shared_through_decision": "distance",
            "post_boundary_decisions": 3,
            "independent_clean_branch": True,
        },
        "deterministic_opaque_id_seed_excludes": ["precision", "technical_repeat"],
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
        "v11_spec_sha256": sha256_file(script_dir / "qhist_v11_spec.py"),
        "base_builder_sha256": sha256_file(script_dir / "qhist_build_e0_assets.py"),
        "previous_builder_sha256": sha256_file(
            script_dir / "qhist_build_e0_assets_v10.py"
        ),
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
