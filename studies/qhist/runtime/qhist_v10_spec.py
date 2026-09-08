#!/usr/bin/env python3
"""Q-HIST v10 的冻结任务集合、精度因子与 E0 运行清单。"""

from __future__ import annotations

from copy import deepcopy
from typing import Any

from qhist_e0_spec import (
    DISTANCES,
    HISTORIES,
    MODEL_ID,
    MODEL_REVISION,
    PRECISIONS as V8_PRECISIONS,
    PROTOCOL_ID,
    REFERENCE_TIME_EPOCH,
    REFERENCE_TIME_ISO,
    UPSTREAM_COMMIT,
    canonical_json,
    canonical_sha256,
    normalize_family,
)


PROTOCOL_VERSION = 10
SCHEDULE_SEED = 20260904
PRECISIONS = deepcopy(V8_PRECISIONS)
TREATMENT_PRECISIONS = ("P00", "P10", "P01", "P11")

# v10 使用外生的“工具观测 + 先前 assistant 承诺”作为一条语义错误历史。
# 每个 family 只选两个信息完整、单轮、无外部网络依赖的措辞变体。
DEVELOPMENT_SCENARIOS = (
    {
        "episode_id": "QH10-E0-01",
        "scenario": "send_message_with_contact_content_cellular_off",
        "prefix_tool": "search_contacts",
        "prefix_arguments": {"name": "Fredrik Thordendal"},
        "error_kind": "contact-phone-substitution",
        "mutability": "mutating",
    },
    {
        "episode_id": "QH10-E0-02",
        "scenario": "send_message_with_contact_content_cellular_off_alt",
        "prefix_tool": "search_contacts",
        "prefix_arguments": {"name": "Fredrik Thordendal"},
        "error_kind": "contact-phone-substitution",
        "mutability": "mutating",
    },
    {
        "episode_id": "QH10-E0-03",
        "scenario": "add_reminder_content_and_week_delta_and_time",
        "prefix_tool": "get_current_timestamp",
        "prefix_arguments": {},
        "error_kind": "relative-time-shift",
        "mutability": "mutating",
    },
    {
        "episode_id": "QH10-E0-04",
        "scenario": "add_reminder_content_and_week_delta_and_time_alt",
        "prefix_tool": "get_current_timestamp",
        "prefix_arguments": {},
        "error_kind": "relative-time-shift",
        "mutability": "mutating",
    },
    {
        "episode_id": "QH10-E0-05",
        "scenario": "turn_on_cellular_low_battery_mode",
        "prefix_tool": "get_low_battery_mode_status",
        "prefix_arguments": {},
        "error_kind": "boolean-negation-cellular",
        "mutability": "mutating-rejected-error",
    },
    {
        "episode_id": "QH10-E0-06",
        "scenario": "turn_on_cellular_low_battery_mode_implicit",
        "prefix_tool": "get_low_battery_mode_status",
        "prefix_arguments": {},
        "error_kind": "boolean-negation-cellular",
        "mutability": "mutating-rejected-error",
    },
)

# 只冻结确认集身份；任何正式 E1 输出前仍须由同一静态构造门逐条生成和审计谓词。
# 这些 family 与 development 完全不重叠，并排除了歧义 remove-reminder 族和仅有单一
# 多轮变体的 update-contact-twice 族。
CONFIRMATORY_SCENARIOS = (
    "add_reminder_content_and_date_and_time",
    "add_reminder_content_and_date_and_time_alt",
    "add_reminder_content_and_weekday_delta_and_time",
    "add_reminder_content_and_weekday_delta_and_time_alt",
    "find_days_till_holiday",
    "find_days_till_holiday_alt",
    "modify_contact_with_message_recency",
    "modify_contact_with_message_recency_alt",
    "modify_reminder_with_recency_latest",
    "modify_reminder_with_recency_latest_alt",
    "remove_contact_by_phone",
    "remove_contact_by_phone_alt",
    "search_message_with_recency_latest",
    "search_message_with_recency_latest_alt",
    "search_message_with_recency_oldest",
    "search_message_with_recency_oldest_alt",
    "search_reminder_with_creation_recency_yesterday",
    "search_reminder_with_creation_recency_yesterday_implicit",
    "search_reminder_with_recency_upcoming",
    "search_reminder_with_recency_upcoming_implicit",
    "search_reminder_with_recency_yesterday",
    "search_reminder_with_recency_yesterday_implicit",
    "turn_on_location_low_battery_mode",
    "turn_on_location_low_battery_mode_implicit",
    "turn_on_wifi_low_battery_mode",
    "turn_on_wifi_low_battery_mode_implicit",
    "update_contact_relationship_with_relationship",
    "update_contact_relationship_with_relationship_alt",
)

TECHNICAL_REPEAT_EPISODES = ("QH10-E0-01", "QH10-E0-03", "QH10-E0-05")

AGENT_TOOL_CONTRACT = (
    "You are an autonomous tool-using agent in a sandbox. Complete the user's "
    "task by calling the available tools whenever a tool can make progress. Do "
    "not merely describe a tool action. Do not ask for information that is "
    "already present in the user request, conversation, or tool results. After "
    "a tool error, inspect state or use an available recovery tool. Use "
    "end_conversation or a plain final response only when the task is complete "
    "or cannot proceed with the available information and tools. Never repeat "
    "an irreversible side effect that has already succeeded."
)


def _unit(
    episode: dict[str, Any],
    precision: str,
    history: str,
    distance: int,
    repeat: int = 1,
) -> dict[str, Any]:
    suffix = "" if repeat == 1 else f"-r{repeat}"
    return {
        "unit_id": f'{episode["episode_id"]}-{precision}-{history}-d{distance}{suffix}',
        "episode_id": episode["episode_id"],
        "scenario": episode["scenario"],
        "family": normalize_family(str(episode["scenario"])),
        "precision": precision,
        "history": history,
        "distance": distance,
        "repeat": repeat,
        "technical_repeat": repeat > 1,
    }


def build_scientific_trajectory_units() -> list[dict[str, Any]]:
    units: list[dict[str, Any]] = []
    for episode in DEVELOPMENT_SCENARIOS:
        for history in HISTORIES:
            for distance in DISTANCES:
                units.append(_unit(episode, "P00", history, distance))
    for episode in DEVELOPMENT_SCENARIOS:
        for precision in ("P10", "P01", "P11"):
            for history in ("N", "C_text"):
                units.append(_unit(episode, precision, history, 3))
    if len(units) != 96 or len({row["unit_id"] for row in units}) != 96:
        raise RuntimeError("v10 科学轨迹清单必须含 96 个唯一单元")
    return units


def build_technical_repeat_units() -> list[dict[str, Any]]:
    by_id = {row["episode_id"]: row for row in DEVELOPMENT_SCENARIOS}
    units = [
        _unit(by_id[episode_id], precision, history, 3, repeat)
        for episode_id in TECHNICAL_REPEAT_EPISODES
        for precision in ("P00", "P11")
        for history in ("N", "C_text")
        for repeat in (2, 3)
    ]
    if len(units) != 24 or len({row["unit_id"] for row in units}) != 24:
        raise RuntimeError("v10 技术重复清单必须含 24 个唯一单元")
    return units


def build_trajectory_units() -> list[dict[str, Any]]:
    units = build_scientific_trajectory_units() + build_technical_repeat_units()
    if len(units) != 120 or len({row["unit_id"] for row in units}) != 120:
        raise RuntimeError("v10 E0 轨迹清单必须含 120 个唯一单元")
    return units


def build_qualification_units() -> list[dict[str, Any]]:
    units = [
        {
            "unit_id": f"QUAL-{precision}-{prompt_id}-r{repeat}",
            "precision": precision,
            "prompt_id": prompt_id,
            "repeat": repeat,
        }
        for precision in PRECISIONS
        for prompt_id in ("add", "lookup")
        for repeat in (1, 2, 3)
    ]
    if len(units) != 30 or len({row["unit_id"] for row in units}) != 30:
        raise RuntimeError("v10 资格清单必须含 30 个唯一单元")
    return units


def expected_precision_counts() -> dict[str, int]:
    units = build_trajectory_units()
    return {
        precision: sum(row["precision"] == precision for row in units)
        for precision in TREATMENT_PRECISIONS
    }


def expected_request_counts() -> dict[str, int]:
    units = build_trajectory_units()
    return {
        precision: sum(
            int(row["distance"]) + 3
            for row in units
            if row["precision"] == precision
        )
        for precision in TREATMENT_PRECISIONS
    }


def validate_frozen_design() -> dict[str, Any]:
    scientific = build_scientific_trajectory_units()
    repeats = build_technical_repeat_units()
    precision_counts = expected_precision_counts()
    request_counts = expected_request_counts()
    development_families = {
        normalize_family(str(row["scenario"])) for row in DEVELOPMENT_SCENARIOS
    }
    confirmatory_families = {
        normalize_family(scenario) for scenario in CONFIRMATORY_SCENARIOS
    }
    if precision_counts != {"P00": 72, "P10": 12, "P01": 12, "P11": 24}:
        raise RuntimeError(f"v10 precision 计数漂移：{precision_counts}")
    if request_counts != {"P00": 372, "P10": 72, "P01": 72, "P11": 144}:
        raise RuntimeError(f"v10 request 计数漂移：{request_counts}")
    if len(development_families) != 3 or len(confirmatory_families) != 14:
        raise RuntimeError("v10 必须冻结 3 个 development 与 14 个 confirmatory family")
    if development_families & confirmatory_families:
        raise RuntimeError("v10 development 与 confirmatory family 不得重叠")
    return {
        "scientific_trajectories": len(scientific),
        "technical_repeat_trajectories": len(repeats),
        "treatment_trajectories": len(scientific) + len(repeats),
        "qualification_runs": len(build_qualification_units()),
        "total_e0_units": len(scientific) + len(repeats) + len(build_qualification_units()),
        "development_episodes": len(DEVELOPMENT_SCENARIOS),
        "development_families": len(development_families),
        "confirmatory_episodes": len(CONFIRMATORY_SCENARIOS),
        "confirmatory_families": len(confirmatory_families),
        "precision_trajectory_counts": precision_counts,
        "precision_request_counts": request_counts,
    }
