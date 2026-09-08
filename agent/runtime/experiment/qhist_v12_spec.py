#!/usr/bin/env python3
"""Q-HIST v12 的冻结任务划分、A/R/E 单元与运行清单。"""

from __future__ import annotations

from copy import deepcopy
from typing import Any

import qhist_v10_spec as v10


PROTOCOL_ID = v10.PROTOCOL_ID
PROTOCOL_VERSION = 12
THEORY_VERSION = "QH-T1.4"
SCHEDULE_SEED = 20260904
MODEL_ID = v10.MODEL_ID
MODEL_REVISION = v10.MODEL_REVISION
UPSTREAM_COMMIT = v10.UPSTREAM_COMMIT
REFERENCE_TIME_ISO = v10.REFERENCE_TIME_ISO
REFERENCE_TIME_EPOCH = v10.REFERENCE_TIME_EPOCH
PRECISIONS = deepcopy(v10.PRECISIONS)
TREATMENT_PRECISIONS = ("P00", "P10", "P01", "P11")
AGENT_TOOL_CONTRACT = v10.AGENT_TOOL_CONTRACT
canonical_json = v10.canonical_json
canonical_sha256 = v10.canonical_sha256
normalize_family = v10.normalize_family

DECISIONS_PER_TRAJECTORY = 4
GAPS = (0, 3)

# ψ 只投影业务状态；SANDBOX 的消息索引、调用 ID、异常文本与行序不是业务债务。
SEMANTIC_ALLOWLIST = {
    "SETTING": (
        "device_id",
        "cellular",
        "wifi",
        "location_service",
        "low_battery_mode",
        "latitude",
        "longitude",
    ),
    "CONTACT": (
        "person_id",
        "name",
        "phone_number",
        "relationship",
        "is_self",
    ),
    "MESSAGING": (
        "message_id",
        "sender_person_id",
        "sender_phone_number",
        "recipient_person_id",
        "recipient_phone_number",
        "content",
        "creation_timestamp",
    ),
    "REMINDER": (
        "reminder_id",
        "content",
        "creation_timestamp",
        "reminder_timestamp",
        "latitude",
        "longitude",
    ),
}
SEMANTIC_PRIMARY_KEYS = {
    "SETTING": ("device_id",),
    "CONTACT": ("person_id",),
    "MESSAGING": ("message_id", "creation_timestamp"),
    "REMINDER": ("reminder_id",),
}


DEVELOPMENT_SCENARIOS = (
    {
        "episode_id": "QH12-E0-01",
        "scenario": "add_reminder_content_and_weekday_delta_and_time",
        "error_kind": "weekday-target-timestamp-shift",
        "mutability": "mutating",
    },
    {
        "episode_id": "QH12-E0-02",
        "scenario": "add_reminder_content_and_weekday_delta_and_time_alt",
        "error_kind": "weekday-target-timestamp-shift",
        "mutability": "mutating",
    },
    {
        "episode_id": "QH12-E0-03",
        "scenario": "modify_contact_with_message_recency",
        "error_kind": "last-outgoing-recipient-id-substitution",
        "mutability": "mutating",
    },
    {
        "episode_id": "QH12-E0-04",
        "scenario": "modify_contact_with_message_recency_alt",
        "error_kind": "last-outgoing-recipient-id-substitution",
        "mutability": "mutating",
    },
    {
        "episode_id": "QH12-E0-05",
        "scenario": "turn_on_wifi_low_battery_mode",
        "error_kind": "low-battery-boolean-negation",
        "mutability": "rejected-error",
    },
    {
        "episode_id": "QH12-E0-06",
        "scenario": "turn_on_wifi_low_battery_mode_implicit",
        "error_kind": "low-battery-boolean-negation",
        "mutability": "rejected-error",
    },
)


CONFIRMATORY_SCENARIOS = (
    "find_days_till_holiday",
    "find_days_till_holiday_alt",
    "modify_reminder_with_recency_latest",
    "modify_reminder_with_recency_latest_alt",
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
    "update_contact_relationship_with_relationship",
    "update_contact_relationship_with_relationship_alt",
)

TECHNICAL_REPEAT_EPISODES = ("QH12-E0-01", "QH12-E0-03", "QH12-E0-05")


def _unit(
    episode: dict[str, Any],
    precision: str,
    module: str,
    condition: str,
    gap: int,
    repeat: int = 1,
) -> dict[str, Any]:
    suffix = "" if repeat == 1 else f"-r{repeat}"
    return {
        "unit_id": (
            f'{episode["episode_id"]}-{precision}-{module}-{condition}-g{gap}{suffix}'
        ),
        "episode_id": episode["episode_id"],
        "scenario": episode["scenario"],
        "family": normalize_family(str(episode["scenario"])),
        "precision": precision,
        "module": module,
        "condition": condition,
        "gap": gap,
        "repeat": repeat,
        "technical_repeat": repeat > 1,
        "decision_budget": DECISIONS_PER_TRAJECTORY,
    }


def _all_cells(episode: dict[str, Any], precision: str) -> list[dict[str, Any]]:
    units: list[dict[str, Any]] = []
    if precision in {"P00", "P11"}:
        for condition in ("A_N", "A_E"):
            for gap in GAPS:
                units.append(_unit(episode, precision, "A", condition, gap))
    else:
        for condition in ("A_N", "A_E"):
            units.append(_unit(episode, precision, "A", condition, 3))

    if precision == "P00":
        for condition in ("R0", "R_audit", "R_fact"):
            for gap in GAPS:
                units.append(_unit(episode, precision, "R", condition, gap))
    else:
        for condition in ("R_audit", "R_fact"):
            units.append(_unit(episode, precision, "R", condition, 3))

    if precision in {"P00", "P11"}:
        for condition in ("E_text", "E_align"):
            units.append(_unit(episode, precision, "E", condition, 3))
    return units


def build_scientific_trajectory_units() -> list[dict[str, Any]]:
    units = [
        row
        for episode in DEVELOPMENT_SCENARIOS
        for precision in TREATMENT_PRECISIONS
        for row in _all_cells(dict(episode), precision)
    ]
    if len(units) != 168 or len({row["unit_id"] for row in units}) != 168:
        raise RuntimeError("v12 E0 科学清单必须含 168 条唯一轨迹")
    return units


def build_technical_repeat_units() -> list[dict[str, Any]]:
    by_id = {row["episode_id"]: dict(row) for row in DEVELOPMENT_SCENARIOS}
    cells = (("A", "A_E"), ("R", "R_fact"))
    units = [
        _unit(by_id[episode_id], precision, module, condition, 3, repeat)
        for episode_id in TECHNICAL_REPEAT_EPISODES
        for precision in ("P00", "P11")
        for module, condition in cells
        for repeat in (2, 3)
    ]
    if len(units) != 24 or len({row["unit_id"] for row in units}) != 24:
        raise RuntimeError("v12 E0 技术重复清单必须含 24 条唯一轨迹")
    return units


def build_trajectory_units() -> list[dict[str, Any]]:
    units = build_scientific_trajectory_units() + build_technical_repeat_units()
    if len(units) != 192 or len({row["unit_id"] for row in units}) != 192:
        raise RuntimeError("v12 E0 必须含 192 条唯一轨迹")
    return units


def build_qualification_units() -> list[dict[str, Any]]:
    return v10.build_qualification_units()


def expected_precision_counts() -> dict[str, int]:
    units = build_trajectory_units()
    return {
        precision: sum(row["precision"] == precision for row in units)
        for precision in TREATMENT_PRECISIONS
    }


def expected_unique_request_counts() -> dict[str, int]:
    return {
        precision: count * DECISIONS_PER_TRAJECTORY
        for precision, count in expected_precision_counts().items()
    }


def validate_frozen_design() -> dict[str, Any]:
    scientific = build_scientific_trajectory_units()
    repeats = build_technical_repeat_units()
    counts = expected_precision_counts()
    requests = expected_unique_request_counts()
    development_families = {
        normalize_family(str(row["scenario"])) for row in DEVELOPMENT_SCENARIOS
    }
    confirmatory_families = {
        normalize_family(name) for name in CONFIRMATORY_SCENARIOS
    }
    if counts != {"P00": 84, "P10": 24, "P01": 24, "P11": 60}:
        raise RuntimeError(f"v12 precision 计数漂移：{counts}")
    if requests != {"P00": 336, "P10": 96, "P01": 96, "P11": 240}:
        raise RuntimeError(f"v12 request 计数漂移：{requests}")
    if len(development_families) != 3 or len(confirmatory_families) != 8:
        raise RuntimeError("v12 必须冻结 3 个 development 与 8 个 confirmatory family")
    if len(CONFIRMATORY_SCENARIOS) != 16:
        raise RuntimeError("v12 confirmatory 必须含 16 个 episode")
    if development_families & confirmatory_families:
        raise RuntimeError("v12 development 与 confirmatory family 不得重叠")
    return {
        "scientific_trajectories": len(scientific),
        "technical_repeat_trajectories": len(repeats),
        "trajectory_units_total": len(scientific) + len(repeats),
        "decisions_per_trajectory": DECISIONS_PER_TRAJECTORY,
        "unique_model_requests": sum(requests.values()),
        "qualification_units": len(build_qualification_units()),
        "precision_trajectory_counts": counts,
        "precision_request_counts": requests,
        "development_episodes": len(DEVELOPMENT_SCENARIOS),
        "development_families": len(development_families),
        "confirmatory_episodes": len(CONFIRMATORY_SCENARIOS),
        "confirmatory_families": len(confirmatory_families),
    }


if __name__ == "__main__":
    import json

    print(json.dumps(validate_frozen_design(), ensure_ascii=False, indent=2))
