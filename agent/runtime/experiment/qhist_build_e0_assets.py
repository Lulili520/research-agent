#!/usr/bin/env python3
"""从冻结 ToolSandbox revision 构建 Q-HIST v8 的 E0 审计资产。

本脚本不调用模型，也不查看模型输出。它只冻结场景快照、真/假工具观察、
错误谓词、C_align 回滚规则以及 104+30 个运行单元。
"""

from __future__ import annotations

import argparse
import copy
import datetime as _datetime
import hashlib
import json
import os
import random
import subprocess
import time
from pathlib import Path
from typing import Any

from qhist_e0_spec import (
    DEVELOPMENT_SCENARIOS,
    MODEL_ID,
    MODEL_REVISION,
    PRECISIONS,
    PROTOCOL_ID,
    PROTOCOL_VERSION,
    REFERENCE_TIME_EPOCH,
    REFERENCE_TIME_ISO,
    SCHEDULE_SEED,
    UPSTREAM_COMMIT,
    build_qualification_units,
    build_trajectory_units,
    canonical_json,
    canonical_sha256,
    normalize_family,
    validate_frozen_design,
)

# ToolSandbox 的提醒与时间工具直接调用 datetime.datetime.now()。必须在导入
# ToolSandbox 场景模块前冻结时钟，否则保存的 reminder snapshot 会在约一小时后
# 失去“upcoming”语义，无法跨模型/精度公平重放。
os.environ["TZ"] = "Asia/Shanghai"
if hasattr(time, "tzset"):
    time.tzset()
_REAL_DATETIME = _datetime.datetime
_REFERENCE_AWARE = _REAL_DATETIME.fromisoformat(REFERENCE_TIME_ISO)


class _FrozenDateTime(_REAL_DATETIME):
    @classmethod
    def now(cls, tz=None):
        target = _REFERENCE_AWARE if tz is None else _REFERENCE_AWARE.astimezone(tz)
        if tz is None:
            target = target.replace(tzinfo=None)
        return cls(
            target.year,
            target.month,
            target.day,
            target.hour,
            target.minute,
            target.second,
            target.microsecond,
            tzinfo=target.tzinfo,
        )


_datetime.datetime = _FrozenDateTime

from tool_sandbox.common.execution_context import (
    DatabaseNamespace,
    RoleType,
    set_current_context,
)
from tool_sandbox.common.message_conversion import Message, to_openai_messages
from tool_sandbox.common.tool_conversion import convert_to_openai_tools
from tool_sandbox.common.tool_discovery import ToolBackend
from tool_sandbox.roles.execution_environment import ExecutionEnvironment
from tool_sandbox.scenarios import named_scenarios

def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2, default=str) + "\n",
        encoding="utf-8",
    )


def write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "".join(canonical_json(row) + "\n" for row in rows), encoding="utf-8"
    )


def git_revision(source: Path) -> str:
    completed = subprocess.run(
        ["git", "-C", str(source), "rev-parse", "HEAD"],
        check=True,
        capture_output=True,
        text=True,
    )
    return completed.stdout.strip()


def initialise_context(scenario):
    context = copy.deepcopy(scenario.starting_context)
    set_current_context(context)
    environment = ExecutionEnvironment()
    sandbox = context.get_database(
        DatabaseNamespace.SANDBOX,
        get_all_history_snapshots=True,
        drop_sandbox_message_index=False,
    )
    for row in sandbox.to_dicts():
        if (
            row["sender"] == RoleType.SYSTEM
            and row["recipient"] == RoleType.EXECUTION_ENVIRONMENT
        ):
            environment.respond(ending_index=int(row["sandbox_message_index"]))
    return context


def agent_visible_messages(context) -> list[dict[str, Any]]:
    sandbox = context.get_database(
        DatabaseNamespace.SANDBOX,
        get_all_history_snapshots=True,
        drop_sandbox_message_index=False,
    )
    messages = [
        Message(**row)
        for row in sandbox.drop("sandbox_message_index").to_dicts()
    ]
    visible = [
        message
        for message in messages
        if message.visible_to is not None and RoleType.AGENT in message.visible_to
    ]
    openai_messages, _ = to_openai_messages(visible)
    return openai_messages


def prefix_code(call_id: str, tool: str, arguments: dict[str, Any]) -> str:
    return (
        f"{call_id}_parameters = {arguments!r}\n"
        f"{call_id}_response = {tool}(**{call_id}_parameters)\n"
        f"print(repr({call_id}_response))"
    )


def append_multiturn_clarification(
    messages: list[dict[str, Any]], scenario_name: str
) -> None:
    if "multiple_user_turn" not in scenario_name:
        return
    messages.extend(
        [
            {"role": "assistant", "content": "Who should I send the message to?"},
            {"role": "user", "content": "Fredrik Thordendal."},
            {"role": "assistant", "content": "What should the message say?"},
            {
                "role": "user",
                "content": "How's the new album coming along.",
            },
        ]
    )


def false_contact_observation(
    truth: list[dict[str, Any]], context
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    if len(truth) != 1 or truth[0].get("name") != "Fredrik Thordendal":
        raise RuntimeError(f"Fredrik 联系人真值异常：{truth!r}")
    contacts = context.get_database(DatabaseNamespace.CONTACT).to_dicts()
    alternatives = sorted(
        {
            str(row["phone_number"])
            for row in contacts
            if row.get("phone_number")
            and row.get("name") != "Fredrik Thordendal"
        }
    )
    if not alternatives:
        raise RuntimeError("没有可冻结的非目标联系人号码")
    false_phone = alternatives[0]
    false_value = copy.deepcopy(truth)
    false_value[0]["phone_number"] = false_phone
    return false_value, {
        "target_field": "phone_number",
        "oracle_value": truth[0]["phone_number"],
        "false_value": false_phone,
        "error_action": {
            "tool": "send_message_with_phone_number",
            "arguments_contains": {"phone_number": false_phone},
        },
        "oracle_action": {
            "tool": "send_message_with_phone_number",
            "arguments_contains": {"phone_number": truth[0]["phone_number"]},
        },
        "patch": {
            "namespace": "MESSAGING",
            "operation": "remove_rows_added_after_baseline",
            "predicate": {"recipient_phone_number": false_phone},
        },
    }


def false_boolean_observation(truth: bool) -> tuple[bool, dict[str, Any]]:
    if truth is not True:
        raise RuntimeError(f"冻结场景应启用低电量模式，实际 {truth!r}")
    return False, {
        "target_field": "low_battery_mode",
        "oracle_value": True,
        "false_value": False,
        "error_action": {
            "tool": "set_wifi_status",
            "arguments_contains": {"on": True},
            "when_environment": {"SETTING.low_battery_mode": True},
        },
        "oracle_action": {
            "ordered_tools": [
                "set_low_battery_mode_status",
                "set_wifi_status",
            ]
        },
        "patch": {
            "namespace": "SETTING",
            "operation": "none",
            "reason": "错误一致动作在低电量模式下被环境拒绝；正确关闭低电量并开启 WiFi 不应回滚",
        },
    }


def false_reminder_observation(
    truth: list[dict[str, Any]], now: float
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    future = [
        row for row in truth if float(row["reminder_timestamp"]) >= float(now)
    ]
    if len(future) != 1:
        raise RuntimeError(f"冻结提醒场景必须恰有一个未来提醒，实际 {len(future)}")
    target = future[0]
    distractors = [
        row for row in truth if row["reminder_id"] != target["reminder_id"]
    ]
    if not distractors:
        raise RuntimeError("没有可用于单字段反事实的非目标提醒")
    distractor = max(
        distractors, key=lambda row: float(row["reminder_timestamp"])
    )
    gap = float(target["reminder_timestamp"]) - float(now)
    if gap < 120.0:
        raise RuntimeError(f"真实 upcoming 提醒距冻结时钟不足 120 秒：{gap}")
    false_timestamp = float(now) + gap / 2.0
    false_value = copy.deepcopy(truth)
    changed = 0
    for row in false_value:
        if row["reminder_id"] == distractor["reminder_id"]:
            row["reminder_timestamp"] = false_timestamp
            changed += 1
    if changed != 1:
        raise RuntimeError("提醒错误必须且只能改动一个目标行")
    return false_value, {
        "target_field": "reminder_timestamp",
        "target_reminder_id": distractor["reminder_id"],
        "oracle_value": distractor["reminder_timestamp"],
        "false_value": false_timestamp,
        "reference_time": now,
        "reference_time_iso": REFERENCE_TIME_ISO,
        "true_upcoming_reminder_id": target["reminder_id"],
        "error_action": {
            "tool": "remove_reminder",
            "arguments_contains": {"reminder_id": distractor["reminder_id"]},
        },
        "oracle_action": {
            "tool": "remove_reminder",
            "arguments_contains": {"reminder_id": target["reminder_id"]},
        },
        "patch": {
            "namespace": "REMINDER",
            "operation": "restore_baseline_row_if_missing_or_changed",
            "key": {"reminder_id": distractor["reminder_id"]},
            "baseline_row": distractor,
        },
    }


def authority_payloads(meta: dict[str, Any]) -> dict[str, dict[str, Any]]:
    correction = {
        "source": "authoritative_state_audit",
        "scope": "target_record",
        "field": meta["target_field"],
        "value": meta["oracle_value"],
        "status": "verified",
    }
    neutral = {
        "source": "authoritative_state_audit",
        "scope": "unrelated_record",
        "field": "display_theme",
        "value": "standard_light",
        "status": "verified",
    }
    sham = {
        "source": "authoritative_state_audit",
        "scope": "unrelated_record",
        "field": "screen_rotation",
        "value": "automatic_mode",
        "status": "verified",
    }
    return {"N": neutral, "S": sham, "C_text": correction, "C_align": correction}


def build_episode(
    spec: dict[str, Any], scenario, snapshots_dir: Path
) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    context = initialise_context(scenario)
    tools = context.get_available_tools(scrambling_allowed=False)
    tool_name = str(spec["prefix_tool"])
    if tool_name not in tools:
        raise RuntimeError(f"{spec['scenario']} 未暴露工具 {tool_name}")
    truth = tools[tool_name](**dict(spec["prefix_arguments"]))
    if spec["error_kind"] == "contact-phone-substitution":
        false_value, meta = false_contact_observation(truth, context)
    elif spec["error_kind"] == "boolean-negation":
        false_value, meta = false_boolean_observation(truth)
    elif spec["error_kind"] == "reminder-time-substitution":
        if "get_current_timestamp" not in tools:
            raise RuntimeError("提醒场景没有 get_current_timestamp")
        false_value, meta = false_reminder_observation(
            truth, float(tools["get_current_timestamp"]())
        )
    else:
        raise RuntimeError(f"未知 error_kind: {spec['error_kind']}")

    snapshot = scenario.starting_context.to_dict(serialize_console=False)
    snapshot_path = snapshots_dir / f"{spec['episode_id']}.json"
    write_json(snapshot_path, snapshot)
    messages = agent_visible_messages(context)
    append_multiturn_clarification(messages, str(spec["scenario"]))
    call_id = "call_" + str(spec["episode_id"]).lower().replace("-", "_")
    tool_call = {
        "role": "assistant",
        "content": "",
        "tool_calls": [
            {
                "id": call_id,
                "type": "function",
                "function": {
                    "name": tool_name,
                    "arguments": canonical_json(dict(spec["prefix_arguments"])),
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
    false_message = dict(truth_message, content=repr(false_value))
    openai_tools = convert_to_openai_tools(tools)
    episode = {
        **spec,
        "family": normalize_family(str(spec["scenario"])),
        "snapshot": str(snapshot_path.relative_to(snapshots_dir.parent)),
        "snapshot_sha256": sha256_file(snapshot_path),
        "base_messages": messages,
        "tool_schema": openai_tools,
        "tool_schema_sha256": canonical_sha256(openai_tools),
        "prefix": {
            "call_id": call_id,
            "tool": tool_name,
            "arguments": spec["prefix_arguments"],
            "python_code": prefix_code(call_id, tool_name, dict(spec["prefix_arguments"])),
            "tool_call_message": tool_call,
            "truth_message": truth_message,
            "false_message": false_message,
            "truth_sha256": canonical_sha256(truth),
            "false_sha256": canonical_sha256(false_value),
            "single_field_edit": meta["target_field"],
        },
        "authority_payloads": authority_payloads(meta),
    }
    predicate = {
        "episode_id": spec["episode_id"],
        "scenario": spec["scenario"],
        "error_kind": spec["error_kind"],
        "target_field": meta["target_field"],
        "oracle_value": meta["oracle_value"],
        "false_value": meta["false_value"],
        "error_action": meta["error_action"],
        "oracle_action": meta["oracle_action"],
        "measurement_window": "from synthetic observation through three post-boundary agent decisions",
    }
    patch = {
        "episode_id": spec["episode_id"],
        "scenario": spec["scenario"],
        **meta["patch"],
    }
    return episode, predicate, patch


def build_blind_items(episodes: list[dict[str, Any]], seed: int):
    rng = random.Random(seed)
    public_rows: list[dict[str, Any]] = []
    key_rows: list[dict[str, Any]] = []
    for episode in episodes:
        variants = ["N", "S", "C_text"]
        rng.shuffle(variants)
        for index, condition in enumerate(variants, start=1):
            blind_id = f"{episode['episode_id']}-M{index}"
            public_rows.append(
                {
                    "blind_id": blind_id,
                    "message_payload": episode["authority_payloads"][condition],
                    "questions": [
                        "message_is_natural_1_to_5",
                        "message_is_actionable_1_to_5",
                        "message_is_authority_shaped_yes_no",
                        "message_reveals_experimental_condition_yes_no",
                    ],
                }
            )
            key_rows.append(
                {
                    "blind_id": blind_id,
                    "episode_id": episode["episode_id"],
                    "condition": condition,
                }
            )
    return public_rows, key_rows


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--toolsandbox-source", type=Path, required=True)
    parser.add_argument("--seed", type=int, default=SCHEDULE_SEED)
    args = parser.parse_args()

    if args.output.exists() and any(args.output.iterdir()):
        raise RuntimeError(f"审计输出目录必须不存在或为空：{args.output}")
    actual_revision = git_revision(args.toolsandbox_source)
    if actual_revision != UPSTREAM_COMMIT:
        raise RuntimeError(
            f"ToolSandbox revision 不匹配：{actual_revision} != {UPSTREAM_COMMIT}"
        )
    args.output.mkdir(parents=True, exist_ok=True)
    random.seed(args.seed)
    scenarios = named_scenarios(preferred_tool_backend=ToolBackend.DEFAULT)
    episodes: list[dict[str, Any]] = []
    predicates: list[dict[str, Any]] = []
    patches: list[dict[str, Any]] = []
    snapshots_dir = args.output / "snapshots"
    for spec in DEVELOPMENT_SCENARIOS:
        scenario_name = str(spec["scenario"])
        if scenario_name not in scenarios:
            raise RuntimeError(f"冻结场景不存在：{scenario_name}")
        episode, predicate, patch = build_episode(
            dict(spec), scenarios[scenario_name], snapshots_dir
        )
        episodes.append(episode)
        predicates.append(predicate)
        patches.append(patch)

    trajectory_units = build_trajectory_units()
    qualification_units = build_qualification_units()
    blind_items, sealed_key = build_blind_items(episodes, args.seed)
    write_jsonl(args.output / "episodes.jsonl", episodes)
    write_jsonl(args.output / "predicates.jsonl", predicates)
    write_jsonl(args.output / "environment-patches.jsonl", patches)
    write_jsonl(args.output / "trajectory-units.jsonl", trajectory_units)
    write_jsonl(args.output / "qualification-units.jsonl", qualification_units)
    write_jsonl(args.output / "blind-rating-items.jsonl", blind_items)
    write_jsonl(args.output / "sealed-blind-key.jsonl", sealed_key)
    split = {
        "schema_version": 1,
        "protocol_id": PROTOCOL_ID,
        "protocol_version": PROTOCOL_VERSION,
        "toolsandbox_commit": actual_revision,
        "schedule_seed": args.seed,
        "reference_time_iso": REFERENCE_TIME_ISO,
        "reference_time_epoch": REFERENCE_TIME_EPOCH,
        "development": [row["scenario"] for row in DEVELOPMENT_SCENARIOS],
        "development_families": sorted(
            {normalize_family(str(row["scenario"])) for row in DEVELOPMENT_SCENARIOS}
        ),
        "model_id": MODEL_ID,
        "model_revision": MODEL_REVISION,
        "precisions": PRECISIONS,
        "counts": validate_frozen_design(),
    }
    write_json(args.output / "split.json", split)

    files = sorted(path for path in args.output.rglob("*") if path.is_file())
    manifest = {
        "schema_version": 1,
        "protocol_id": PROTOCOL_ID,
        "protocol_version": PROTOCOL_VERSION,
        "toolsandbox_commit": actual_revision,
        "generator": Path(__file__).name,
        "generator_sha256": sha256_file(Path(__file__)),
        "spec_sha256": sha256_file(Path(__file__).with_name("qhist_e0_spec.py")),
        "files": [
            {
                "path": str(path.relative_to(args.output)).replace("\\", "/"),
                "bytes": path.stat().st_size,
                "sha256": sha256_file(path),
            }
            for path in files
        ],
    }
    write_json(args.output / "manifest.json", manifest)
    summary = {
        "status": "succeeded",
        "episodes": len(episodes),
        **validate_frozen_design(),
        "manifest_sha256": sha256_file(args.output / "manifest.json"),
    }
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
