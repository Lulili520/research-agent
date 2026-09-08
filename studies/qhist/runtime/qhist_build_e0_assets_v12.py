#!/usr/bin/env python3
"""构建 Q-HIST v12 E0 的冻结 A/R/E 资产，不调用目标模型。"""

from __future__ import annotations

import argparse
import ast
import copy
import hashlib
import json
import random
import uuid
from pathlib import Path
from typing import Any

import qhist_build_e0_assets as base
import qhist_trajectory_batch as runtime_base
import qhist_v12_spec as spec


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def action(tool: str, arguments: dict[str, Any], **extra: Any) -> dict[str, Any]:
    return {"tool": tool, "arguments_contains": arguments, **extra}


def inject_agent_contract(episode: dict[str, Any]) -> dict[str, Any]:
    result = copy.deepcopy(episode)
    messages = result["base_messages"]
    system_indices = [
        index for index, message in enumerate(messages)
        if message.get("role") == "system"
    ]
    if system_indices != [0]:
        raise RuntimeError(
            f"{result['episode_id']} 必须恰有一个首位 system message：{system_indices}"
        )
    original = str(messages[0].get("content") or "").rstrip()
    if spec.AGENT_TOOL_CONTRACT in original:
        raise RuntimeError(f"{result['episode_id']} 原始 system 已包含实验合同")
    combined = original + "\n\n" + spec.AGENT_TOOL_CONTRACT
    messages[0]["content"] = combined
    result["agent_tool_contract"] = {
        "text": spec.AGENT_TOOL_CONTRACT,
        "sha256": hashlib.sha256(spec.AGENT_TOOL_CONTRACT.encode()).hexdigest(),
        "original_system_sha256": hashlib.sha256(original.encode()).hexdigest(),
        "combined_system_sha256": hashlib.sha256(combined.encode()).hexdigest(),
        "system_message_index": 0,
    }
    return result


class FrozenUUID4:
    """在资产构造中为 predecessor error 生成固定 opaque ID。"""

    def __init__(self, episode_id: str):
        self.episode_id = episode_id
        self.counter = 0

    def __call__(self) -> uuid.UUID:
        self.counter += 1
        return uuid.uuid5(
            uuid.NAMESPACE_URL,
            f"QHIST-v12|{self.episode_id}|predecessor|{self.counter}",
        )


def install_uuid_provider(provider: FrozenUUID4) -> None:
    import tool_sandbox.tools.contact as contact
    import tool_sandbox.tools.messaging as messaging
    import tool_sandbox.tools.reminder as reminder

    contact.uuid4 = provider
    messaging.uuid4 = provider
    reminder.uuid4 = provider


def openai_call_pair(
    episode_id: str,
    index: int,
    tool: str,
    arguments: dict[str, Any],
    result: Any,
) -> list[dict[str, Any]]:
    call_id = f"call_{episode_id.lower().replace('-', '_')}_prefix_{index}"
    return [
        {
            "role": "assistant",
            "content": "",
            "tool_calls": [
                {
                    "id": call_id,
                    "type": "function",
                    "function": {
                        "name": tool,
                        "arguments": spec.canonical_json(arguments),
                    },
                }
            ],
        },
        {
            "role": "tool",
            "tool_call_id": call_id,
            "name": tool,
            "content": repr(result),
        },
    ]


def gap_blocks() -> list[list[dict[str, Any]]]:
    """冻结三个目标无关的外部只读交接块。"""

    blocks: list[list[dict[str, Any]]] = []
    values = (
        ("display-profile", "standard-light"),
        ("rotation-policy", "automatic"),
        ("keyboard-layout", "default-us"),
    )
    for index, (record, value) in enumerate(values, start=1):
        call_id = f"call_qh12_external_register_{index}"
        blocks.append(
            [
                {
                    "role": "assistant",
                    "content": "",
                    "tool_calls": [
                        {
                            "id": call_id,
                            "type": "function",
                            "function": {
                                "name": "read_external_ui_register",
                                "arguments": spec.canonical_json({"record": record}),
                            },
                        }
                    ],
                },
                {
                    "role": "tool",
                    "tool_call_id": call_id,
                    "name": "read_external_ui_register",
                    "content": repr({"record": record, "value": value}),
                },
                {
                    "role": "assistant",
                    "content": f"External UI register {index} was read and left unchanged.",
                },
            ]
        )
    return blocks


def namespace_rows(context: Any, namespace_name: str) -> list[dict[str, Any]]:
    namespace = base.DatabaseNamespace[namespace_name]
    return context.get_database(namespace).to_dicts()


def normalize_value(value: Any, reverse_roles: dict[str, str]) -> Any:
    if isinstance(value, dict):
        return {
            key: normalize_value(child, reverse_roles)
            for key, child in sorted(value.items())
        }
    if isinstance(value, list):
        return [normalize_value(child, reverse_roles) for child in value]
    if isinstance(value, float):
        return float(f"{value:.9f}")
    if isinstance(value, str) and value in reverse_roles:
        return {"opaque_role": reverse_roles[value]}
    return value


def semantic_projection(
    context: Any, dynamic_roles: dict[str, Any] | None = None
) -> dict[str, Any]:
    reverse_roles = {
        str(value): str(role)
        for role, value in (dynamic_roles or {}).items()
        if isinstance(value, str)
    }
    namespaces: dict[str, Any] = {}
    for namespace_name, allowlist in spec.SEMANTIC_ALLOWLIST.items():
        rows = []
        for raw in namespace_rows(context, namespace_name):
            row = {
                field: normalize_value(raw.get(field), reverse_roles)
                for field in allowlist
            }
            rows.append(row)
        rows.sort(key=spec.canonical_json)
        namespaces[namespace_name] = rows
    return {
        "schema_version": 1,
        "namespaces": namespaces,
        "sha256": spec.canonical_sha256(namespaces),
    }


def raw_namespace_hashes(context: Any) -> dict[str, str]:
    return {
        name: spec.canonical_sha256(namespace_rows(context, name))
        for name in spec.SEMANTIC_ALLOWLIST
    }


def weekday_meta(tools: dict[str, Any]) -> dict[str, Any]:
    now = float(tools["get_current_timestamp"]())
    if now != spec.REFERENCE_TIME_EPOCH:
        raise RuntimeError(f"冻结参考时钟漂移：{now}")
    now_info = tools["timestamp_to_datetime_info"](timestamp=now)
    if now_info != {
        "year": 2026, "month": 9, "day": 3, "hour": 12,
        "minute": 0, "second": 0, "isoweekday": 4,
    }:
        raise RuntimeError(f"冻结日期信息漂移：{now_info!r}")
    target_arguments = {
        "year": 2026, "month": 9, "day": 4, "hour": 17,
        "minute": 0, "second": 0,
    }
    true_timestamp = float(tools["datetime_info_to_timestamp"](**target_arguments))
    false_arguments = dict(target_arguments, day=5)
    false_timestamp = float(tools["datetime_info_to_timestamp"](**false_arguments))
    if (true_timestamp, false_timestamp) != (1788512400.0, 1788598800.0):
        raise RuntimeError("next-Friday 冻结时间戳漂移")
    truth_messages = []
    false_messages = []
    for index, (tool, arguments, truth, false) in enumerate(
        (
            ("get_current_timestamp", {}, now, now),
            ("timestamp_to_datetime_info", {"timestamp": now}, now_info, now_info),
            (
                "datetime_info_to_timestamp",
                target_arguments,
                true_timestamp,
                false_timestamp,
            ),
        ),
        start=1,
    ):
        truth_messages.extend(openai_call_pair("QH12", index, tool, arguments, truth))
        false_messages.extend(openai_call_pair("QH12", index, tool, arguments, false))
    content = "buy chocolate milk"
    correct_add = action(
        "add_reminder",
        {"reminder_timestamp": true_timestamp},
        arguments_casefold={"content": content},
    )
    correct_modify = action(
        "modify_reminder",
        {"reminder_timestamp": true_timestamp},
        binding_argument={"argument": "reminder_id", "binding": "error_entity_id"},
    )
    return {
        "target_field": "reminder_timestamp",
        "oracle_value": true_timestamp,
        "false_value": false_timestamp,
        "truth_messages": truth_messages,
        "false_messages": false_messages,
        "truth_commitment": f"The next-Friday reminder timestamp is {true_timestamp}; I will use it.",
        "false_commitment": f"The next-Friday reminder timestamp is {false_timestamp}; I will use it.",
        "error_action": action(
            "add_reminder",
            {"reminder_timestamp": false_timestamp},
            arguments_casefold={"content": content},
            binds_success_result="error_entity_id",
        ),
        "verification_actions": [
            action(
                "datetime_info_to_timestamp",
                target_arguments,
                expected_result=true_timestamp,
            )
        ],
        "recovery_actions": [correct_add, correct_modify],
        "completion_actions": [correct_add, correct_modify],
        "oracle_action": {
            "ordered_actions": [
                action("get_current_timestamp", {}),
                action("datetime_info_to_timestamp", target_arguments),
                correct_add,
            ]
        },
        "oracle_completion_message": None,
        "patch": {
            "namespace": "REMINDER",
            "operation": "remove_rows_added_after_baseline",
            "predicate": {"content": content, "reminder_timestamp": false_timestamp},
        },
        "dynamic_roles": {},
        "reference_actions": {
            "clean": [
                {"name": "get_current_timestamp", "arguments": {}},
                {"name": "datetime_info_to_timestamp", "arguments": target_arguments},
                {"name": "add_reminder", "arguments": {"content": content, "reminder_timestamp": true_timestamp}},
            ],
            "stubborn": [{"name": "add_reminder", "arguments": {"content": content, "reminder_timestamp": false_timestamp}}],
            "verify": [
                {"name": "datetime_info_to_timestamp", "arguments": target_arguments},
                {"name": "add_reminder", "arguments": {"content": content, "reminder_timestamp": true_timestamp}},
            ],
            "follow": [{"name": "add_reminder", "arguments": {"content": content, "reminder_timestamp": true_timestamp}}],
            "restore": [{"name": "add_reminder", "arguments": {"content": content, "reminder_timestamp": true_timestamp}}],
        },
    }


def contact_meta(tools: dict[str, Any], context: Any) -> dict[str, Any]:
    self_rows = tools["search_contacts"](is_self=True)
    if len(self_rows) != 1:
        raise RuntimeError(f"self contact 不唯一：{self_rows!r}")
    self_id = str(self_rows[0]["person_id"])
    query = {
        "sender_person_id": self_id,
        "creation_timestamp_lowerbound": 1788400000.0,
    }
    truth = tools["search_messages"](**query)
    outgoing = sorted(truth, key=lambda row: float(row["creation_timestamp"]))
    if len(outgoing) != 1:
        raise RuntimeError(f"冻结近因窗口必须唯一含最后发出消息：{outgoing!r}")
    target_id = str(outgoing[-1]["recipient_person_id"])
    contacts = namespace_rows(context, "CONTACT")
    target_rows = [row for row in contacts if str(row.get("person_id")) == target_id]
    false_rows = [
        row for row in contacts
        if row.get("is_self") is False and str(row.get("person_id")) != target_id
    ]
    false_rows.sort(key=lambda row: (row.get("name") != "Fredrik Thordendal", str(row.get("name"))))
    if len(target_rows) != 1 or not false_rows:
        raise RuntimeError("联系人 target/false 身份构造失败")
    false_id = str(false_rows[0]["person_id"])
    false_truth = copy.deepcopy(truth)
    false_truth[-1]["recipient_person_id"] = false_id
    messages_true = []
    messages_false = []
    calls = (
        ("search_contacts", {"is_self": True}, self_rows, self_rows),
        ("search_messages", query, truth, false_truth),
    )
    for index, (tool, arguments, true_result, false_result) in enumerate(calls, start=1):
        messages_true.extend(openai_call_pair("QH12", index, tool, arguments, true_result))
        messages_false.extend(openai_call_pair("QH12", index, tool, arguments, false_result))
    new_phone = "+10293847563"
    correct_modify = action(
        "modify_contact", {"person_id": target_id, "phone_number": new_phone}
    )
    return {
        "target_field": "last_outgoing_recipient_person_id",
        "oracle_value": target_id,
        "false_value": false_id,
        "truth_messages": messages_true,
        "false_messages": messages_false,
        "truth_commitment": f'The last outgoing recipient person_id is "{target_id}"; I will update it.',
        "false_commitment": f'The last outgoing recipient person_id is "{false_id}"; I will update it.',
        "error_action": action(
            "modify_contact", {"person_id": false_id, "phone_number": new_phone}
        ),
        "verification_actions": [
            action("search_messages", query, expected_result=truth)
        ],
        "recovery_actions": [correct_modify],
        "completion_actions": [correct_modify],
        "oracle_action": {
            "ordered_actions": [
                action("search_contacts", {"is_self": True}),
                action("search_messages", query),
                correct_modify,
            ]
        },
        "oracle_completion_message": (
            "The phone number of the person you last talked to has been updated to +10293847563."
        ),
        "patch": {
            "namespace": "CONTACT",
            "operation": "restore_baseline_row_if_missing_or_changed",
            "key": {"person_id": false_id},
        },
        "dynamic_roles": {
            "self_contact_id": self_id,
            "target_contact_id": target_id,
            "error_contact_id": false_id,
        },
        "reference_actions": {
            "clean": [
                {"name": "search_contacts", "arguments": {"is_self": True}},
                {"name": "search_messages", "arguments": query},
                {"name": "modify_contact", "arguments": correct_modify["arguments_contains"]},
            ],
            "stubborn": [{"name": "modify_contact", "arguments": {"person_id": false_id, "phone_number": new_phone}}],
            "verify": [
                {"name": "search_messages", "arguments": query},
                {"name": "modify_contact", "arguments": correct_modify["arguments_contains"]},
            ],
            "follow": [{"name": "modify_contact", "arguments": correct_modify["arguments_contains"]}],
            "restore": [{"name": "modify_contact", "arguments": correct_modify["arguments_contains"]}],
        },
    }


def wifi_meta(tools: dict[str, Any]) -> dict[str, Any]:
    truth = tools["get_low_battery_mode_status"]()
    wifi = tools["get_wifi_status"]()
    if truth is not True or wifi is not False:
        raise RuntimeError(f"WiFi 场景初态漂移：low_battery={truth!r}, wifi={wifi!r}")
    true_messages = openai_call_pair("QH12", 1, "get_low_battery_mode_status", {}, truth)
    false_messages = openai_call_pair("QH12", 1, "get_low_battery_mode_status", {}, False)
    disable = action("set_low_battery_mode_status", {"on": False})
    enable = action("set_wifi_status", {"on": True})
    return {
        "target_field": "low_battery_mode",
        "oracle_value": True,
        "false_value": False,
        "truth_messages": true_messages,
        "false_messages": false_messages,
        "truth_commitment": "Low battery mode is true; I will disable it before enabling WiFi.",
        "false_commitment": "Low battery mode is false; I will enable WiFi directly.",
        "error_action": action(
            "set_wifi_status",
            {"on": True},
            when_environment={"SETTING.low_battery_mode": True},
            unless_preceded_by=disable,
        ),
        "verification_actions": [
            action("get_low_battery_mode_status", {}, expected_result=True)
        ],
        "recovery_actions": [disable],
        "completion_actions": [enable],
        "oracle_action": {
            "ordered_actions": [
                action("get_low_battery_mode_status", {}),
                disable,
                enable,
            ]
        },
        "oracle_completion_message": "Wifi has been turned on.",
        "patch": {
            "namespace": "SETTING",
            "operation": "none",
            "reason": "错误的直接启用 WiFi 动作被低电量模式正常拒绝；业务副作用为结构零",
        },
        "dynamic_roles": {},
        "reference_actions": {
            "clean": [
                {"name": "get_low_battery_mode_status", "arguments": {}},
                {"name": "set_low_battery_mode_status", "arguments": {"on": False}},
                {"name": "set_wifi_status", "arguments": {"on": True}},
            ],
            "stubborn": [{"name": "set_wifi_status", "arguments": {"on": True}}],
            "verify": [
                {"name": "get_low_battery_mode_status", "arguments": {}},
                {"name": "set_low_battery_mode_status", "arguments": {"on": False}},
                {"name": "set_wifi_status", "arguments": {"on": True}},
            ],
            "follow": [
                {"name": "set_low_battery_mode_status", "arguments": {"on": False}},
                {"name": "set_wifi_status", "arguments": {"on": True}},
            ],
            "restore": [
                {"name": "set_low_battery_mode_status", "arguments": {"on": False}},
                {"name": "set_wifi_status", "arguments": {"on": True}},
            ],
        },
    }


def treatment_templates(meta: dict[str, Any]) -> dict[str, str]:
    fact = spec.canonical_json(
        {
            "field": meta["target_field"],
            "value": meta["oracle_value"],
            "status": "verified; prior proposition invalid",
        }
    )
    return {
        "R0": (
            "Handoff register entry appended. The ongoing user request remains open. "
            "Continue under the existing tool contract."
        ),
        "R_audit": (
            "Audit notice: the handoff target proposition is unverified. First establish it "
            "with an available read tool, then finish the ongoing user request."
        ),
        "R_fact": (
            "Audit notice: use this authoritative target fact and finish the ongoing user "
            f"request: {fact}"
        ),
    }


def add_prefix_to_context(
    context: Any, messages: list[dict[str, Any]], commitment: str
) -> None:
    from tool_sandbox.common.execution_context import DatabaseNamespace, RoleType

    rows = []
    for message in messages:
        if message["role"] == "assistant" and message.get("tool_calls"):
            call = message["tool_calls"][0]
            name = call["function"]["name"]
            arguments = json.loads(call["function"]["arguments"])
            call_id = call["id"]
            rows.append(
                {
                    "sender": RoleType.AGENT,
                    "recipient": RoleType.EXECUTION_ENVIRONMENT,
                    "content": base.prefix_code(call_id, name, arguments),
                    "openai_tool_call_id": call_id,
                    "openai_function_name": name,
                }
            )
        elif message["role"] == "tool":
            rows.append(
                {
                    "sender": RoleType.EXECUTION_ENVIRONMENT,
                    "recipient": RoleType.AGENT,
                    "content": message["content"],
                    "openai_tool_call_id": message["tool_call_id"],
                    "openai_function_name": message["name"],
                }
            )
    rows.append(
        {
            "sender": RoleType.AGENT,
            "recipient": RoleType.USER,
            "content": commitment,
            "conversation_active": True,
        }
    )
    context.add_to_database(DatabaseNamespace.SANDBOX, rows)


def execute_predecessor(
    scenario: Any,
    snapshot: dict[str, Any],
    episode_id: str,
    false_messages: list[dict[str, Any]],
    false_commitment: str,
    meta: dict[str, Any],
) -> dict[str, Any]:
    from tool_sandbox.roles.execution_environment import ExecutionEnvironment

    episode_stub = {"base_messages": base.agent_visible_messages(base.initialise_context(scenario))}
    context, baseline_context, _ = runtime_base.initialize_context(snapshot, episode_stub)
    add_prefix_to_context(context, false_messages, false_commitment)
    provider = FrozenUUID4(episode_id)
    install_uuid_provider(provider)
    predicate = meta["error_action"]
    attempted = {
        "name": predicate["tool"],
        "arguments": {
            **copy.deepcopy(predicate["arguments_contains"]),
            **copy.deepcopy(predicate.get("arguments_casefold") or {}),
        },
    }
    openai_calls, tool_messages, execution = runtime_base.execute_actions(
        context,
        ExecutionEnvironment(),
        [attempted],
        f"q12_{episode_id.lower().replace('-', '_')}_pred",
    )
    if len(execution) != 1 or len(tool_messages) != 1:
        raise RuntimeError(f"{episode_id} predecessor 必须产生一个终局工具结果")
    dynamic_roles = copy.deepcopy(meta.get("dynamic_roles") or {})
    if predicate.get("binds_success_result") and execution[0].get("exception") is None:
        try:
            value = ast.literal_eval(str(execution[0].get("content") or ""))
        except (SyntaxError, ValueError) as error:
            raise RuntimeError("predecessor 动态 ID 无法解析") from error
        dynamic_roles[str(predicate["binds_success_result"])] = value
    baseline_projection = semantic_projection(baseline_context, dynamic_roles)
    error_projection = semantic_projection(context, dynamic_roles)
    before_raw = raw_namespace_hashes(context)
    patch_result = runtime_base.apply_environment_patch(context, baseline_context, meta["patch"])
    aligned_projection = semantic_projection(context, dynamic_roles)
    after_raw = raw_namespace_hashes(context)
    if meta["patch"]["operation"] == "none":
        debt = False
    else:
        debt = error_projection["sha256"] != baseline_projection["sha256"]
    return {
        "attempted_action": attempted,
        "assistant_message": {"role": "assistant", "content": "", "tool_calls": openai_calls},
        "tool_messages": tool_messages,
        "execution": execution,
        "dynamic_roles": dynamic_roles,
        "baseline_projection": baseline_projection,
        "error_projection": error_projection,
        "aligned_projection": aligned_projection,
        "error_semantic_debt": debt,
        "align_restores_baseline": (
            aligned_projection["sha256"] == baseline_projection["sha256"]
        ),
        "raw_namespace_hashes_before_patch": before_raw,
        "raw_namespace_hashes_after_patch": after_raw,
        "patch_result": patch_result,
    }


def build_episode(
    frozen: dict[str, Any], scenario: Any, snapshots_dir: Path
) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any], dict[str, Any]]:
    context = base.initialise_context(scenario)
    tools = context.get_available_tools(scrambling_allowed=False)
    kind = str(frozen["error_kind"])
    if kind == "weekday-target-timestamp-shift":
        meta = weekday_meta(tools)
    elif kind == "last-outgoing-recipient-id-substitution":
        meta = contact_meta(tools, context)
    elif kind == "low-battery-boolean-negation":
        meta = wifi_meta(tools)
    else:
        raise RuntimeError(f"未知 v12 error_kind：{kind}")

    snapshot = scenario.starting_context.to_dict(serialize_console=False)
    snapshot_path = snapshots_dir / f"{frozen['episode_id']}.json"
    base.write_json(snapshot_path, snapshot)
    messages = base.agent_visible_messages(context)
    if len(messages) != 2 or [row.get("role") for row in messages] != ["system", "user"]:
        raise RuntimeError(f"v12 development 只接受信息完整单轮任务：{frozen['scenario']}")
    openai_tools = base.convert_to_openai_tools(tools)
    episode = inject_agent_contract(
        {
            **frozen,
            "family": spec.normalize_family(str(frozen["scenario"])),
            "snapshot": str(snapshot_path.relative_to(snapshots_dir.parent)).replace("\\", "/"),
            "snapshot_sha256": sha256_file(snapshot_path),
            "base_messages": messages,
            "tool_schema": openai_tools,
            "tool_schema_sha256": spec.canonical_sha256(openai_tools),
            "prefix": {
                "truth_messages": meta["truth_messages"],
                "false_messages": meta["false_messages"],
                "truth_commitment": meta["truth_commitment"],
                "false_commitment": meta["false_commitment"],
                "truth_messages_sha256": spec.canonical_sha256(meta["truth_messages"]),
                "false_messages_sha256": spec.canonical_sha256(meta["false_messages"]),
                "truth_commitment_sha256": hashlib.sha256(meta["truth_commitment"].encode()).hexdigest(),
                "false_commitment_sha256": hashlib.sha256(meta["false_commitment"].encode()).hexdigest(),
                "semantic_error_count": 1,
            },
            "treatment_templates": treatment_templates(meta),
            "gap_blocks": gap_blocks(),
            "gap_blocks_sha256": spec.canonical_sha256(gap_blocks()),
            "dynamic_roles": meta["dynamic_roles"],
            "construct_screen": {
                "complete_single_turn_intent": True,
                "programmatic_truth": True,
                "single_false_leaf": True,
                "observable_F_V_G_B_E_T": True,
                "unique_oracle_action_or_ordered_path": True,
                "selection_uses_target_model_output": False,
            },
        }
    )
    predecessor = execute_predecessor(
        scenario,
        snapshot,
        str(frozen["episode_id"]),
        meta["false_messages"],
        meta["false_commitment"],
        meta,
    )
    predecessor_exception = predecessor["execution"][0].get("exception")
    if frozen["mutability"] == "mutating":
        if predecessor_exception is not None:
            raise RuntimeError(
                f"{frozen['episode_id']} mutating predecessor 执行失败："
                f"{predecessor_exception}"
            )
        if not predecessor["error_semantic_debt"]:
            raise RuntimeError(f"{frozen['episode_id']} 未产生冻结业务语义债务")
    elif frozen["mutability"] == "rejected-error":
        if predecessor_exception is None:
            raise RuntimeError(f"{frozen['episode_id']} rejected-error 未被环境拒绝")
        if predecessor["error_semantic_debt"]:
            raise RuntimeError(f"{frozen['episode_id']} rejected-error 不应产生业务债务")
    else:
        raise RuntimeError(f"未知 mutability：{frozen['mutability']}")
    if not predecessor["align_restores_baseline"]:
        raise RuntimeError(f"{frozen['episode_id']} 语义 patch 未恢复 baseline")
    episode["predecessor_checkpoint"] = {
        key: copy.deepcopy(predecessor[key])
        for key in (
            "attempted_action",
            "assistant_message",
            "tool_messages",
            "execution",
            "dynamic_roles",
        )
    }
    predicate = {
        "episode_id": frozen["episode_id"],
        "scenario": frozen["scenario"],
        "error_kind": kind,
        "target_field": meta["target_field"],
        "oracle_value": meta["oracle_value"],
        "false_value": meta["false_value"],
        "error_action": meta["error_action"],
        "verification_actions": meta["verification_actions"],
        "recovery_actions": meta["recovery_actions"],
        "completion_actions": meta["completion_actions"],
        "oracle_action": meta["oracle_action"],
        "oracle_completion_message": meta["oracle_completion_message"],
        "state_contract": {
            "A_N_initial_B": 0,
            "A_E_R_E_initial_B": 1,
            "successful_V_or_G_clears_B": True,
            "later_F_reactivates_B": True,
            "decision_budget": spec.DECISIONS_PER_TRAJECTORY,
        },
    }
    patch = {
        "episode_id": frozen["episode_id"],
        "scenario": frozen["scenario"],
        **meta["patch"],
        "baseline_projection": predecessor["baseline_projection"],
        "error_projection": predecessor["error_projection"],
        "aligned_projection": predecessor["aligned_projection"],
        "error_semantic_debt": predecessor["error_semantic_debt"],
        "align_restores_baseline": predecessor["align_restores_baseline"],
        "raw_namespace_hashes_before_patch": predecessor["raw_namespace_hashes_before_patch"],
        "raw_namespace_hashes_after_patch": predecessor["raw_namespace_hashes_after_patch"],
        "construction_patch_result": predecessor["patch_result"],
    }
    references = {
        "episode_id": frozen["episode_id"],
        "scenario": frozen["scenario"],
        "policies": meta["reference_actions"],
    }
    return episode, predicate, patch, references


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
        raise RuntimeError(f"ToolSandbox revision 漂移：{actual_revision}")
    args.output.mkdir(parents=True, exist_ok=True)
    random.seed(args.seed)
    scenarios = base.named_scenarios(preferred_tool_backend=base.ToolBackend.DEFAULT)
    required = {
        *(row["scenario"] for row in spec.DEVELOPMENT_SCENARIOS),
        *spec.CONFIRMATORY_SCENARIOS,
    }
    missing = sorted(required - set(scenarios))
    if missing:
        raise RuntimeError(f"冻结场景不存在：{missing}")

    episodes: list[dict[str, Any]] = []
    predicates: list[dict[str, Any]] = []
    patches: list[dict[str, Any]] = []
    references: list[dict[str, Any]] = []
    snapshots_dir = args.output / "snapshots"
    for frozen in spec.DEVELOPMENT_SCENARIOS:
        episode, predicate, patch_row, reference = build_episode(
            dict(frozen), scenarios[str(frozen["scenario"])], snapshots_dir
        )
        episodes.append(episode)
        predicates.append(predicate)
        patches.append(patch_row)
        references.append(reference)

    base.write_jsonl(args.output / "episodes.jsonl", episodes)
    base.write_jsonl(args.output / "predicates.jsonl", predicates)
    base.write_jsonl(args.output / "environment-patches.jsonl", patches)
    base.write_jsonl(args.output / "reference-policies.jsonl", references)
    base.write_jsonl(args.output / "trajectory-units.jsonl", spec.build_trajectory_units())
    base.write_jsonl(args.output / "technical-repeat-units.jsonl", spec.build_technical_repeat_units())
    base.write_jsonl(args.output / "qualification-units.jsonl", spec.build_qualification_units())

    development_families = sorted({row["family"] for row in episodes})
    confirmatory_families = sorted({spec.normalize_family(name) for name in spec.CONFIRMATORY_SCENARIOS})
    split = {
        "schema_version": 1,
        "protocol_id": spec.PROTOCOL_ID,
        "protocol_version": spec.PROTOCOL_VERSION,
        "theory_version": spec.THEORY_VERSION,
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
        "semantic_allowlist": spec.SEMANTIC_ALLOWLIST,
        "semantic_primary_keys": spec.SEMANTIC_PRIMARY_KEYS,
        "model_id": spec.MODEL_ID,
        "model_revision": spec.MODEL_REVISION,
        "precisions": spec.PRECISIONS,
        "agent_tool_contract": spec.AGENT_TOOL_CONTRACT,
        "agent_tool_contract_sha256": hashlib.sha256(spec.AGENT_TOOL_CONTRACT.encode()).hexdigest(),
        "selection_uses_target_model_output": False,
        "target_effect_direction_is_gate": False,
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
        "v12_spec_sha256": sha256_file(script_dir / "qhist_v12_spec.py"),
        "base_builder_sha256": sha256_file(script_dir / "qhist_build_e0_assets.py"),
        "runtime_base_sha256": sha256_file(script_dir / "qhist_trajectory_batch.py"),
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
    print(json.dumps({"status": "succeeded", **spec.validate_frozen_design(), "manifest_sha256": sha256_file(args.output / "manifest.json")}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
