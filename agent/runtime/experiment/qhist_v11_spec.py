#!/usr/bin/env python3
"""Q-HIST v11 的冻结任务划分、精度因子与 boundary-fork 运行清单。"""

from __future__ import annotations

from copy import deepcopy
from typing import Any

import qhist_v10_spec as v10


PROTOCOL_ID = v10.PROTOCOL_ID
PROTOCOL_VERSION = 11
SCHEDULE_SEED = 20260904
MODEL_ID = v10.MODEL_ID
MODEL_REVISION = v10.MODEL_REVISION
UPSTREAM_COMMIT = v10.UPSTREAM_COMMIT
REFERENCE_TIME_ISO = v10.REFERENCE_TIME_ISO
REFERENCE_TIME_EPOCH = v10.REFERENCE_TIME_EPOCH
DISTANCES = v10.DISTANCES
HISTORIES = v10.HISTORIES
PRECISIONS = deepcopy(v10.PRECISIONS)
TREATMENT_PRECISIONS = v10.TREATMENT_PRECISIONS
AGENT_TOOL_CONTRACT = v10.AGENT_TOOL_CONTRACT
canonical_json = v10.canonical_json
canonical_sha256 = v10.canonical_sha256
normalize_family = v10.normalize_family


# v10 的三个已观察 family 不得进入 v11；v11 再以三个从未运行过的 family
# 校准 F/V/G/B/E/T 与 boundary-fork。每个 family 固定两个单轮措辞变体。
DEVELOPMENT_SCENARIOS = (
    {
        "episode_id": "QH11-E0-01",
        "scenario": "remove_contact_by_phone",
        "prefix_tool": "search_contacts",
        "prefix_arguments": {"phone_number": "+12453344098"},
        "error_kind": "contact-id-substitution",
        "mutability": "mutating",
    },
    {
        "episode_id": "QH11-E0-02",
        "scenario": "remove_contact_by_phone_alt",
        "prefix_tool": "search_contacts",
        "prefix_arguments": {"phone_number": "+12453344098"},
        "error_kind": "contact-id-substitution",
        "mutability": "mutating",
    },
    {
        "episode_id": "QH11-E0-03",
        "scenario": "add_reminder_content_and_date_and_time",
        "prefix_tool": "datetime_info_to_timestamp",
        "prefix_arguments": {
            "year": 2024,
            "month": 3,
            "day": 22,
            "hour": 17,
            "minute": 0,
            "second": 0,
        },
        "error_kind": "absolute-time-shift",
        "mutability": "mutating",
    },
    {
        "episode_id": "QH11-E0-04",
        "scenario": "add_reminder_content_and_date_and_time_alt",
        "prefix_tool": "datetime_info_to_timestamp",
        "prefix_arguments": {
            "year": 2024,
            "month": 3,
            "day": 22,
            "hour": 17,
            "minute": 0,
            "second": 0,
        },
        "error_kind": "absolute-time-shift",
        "mutability": "mutating",
    },
    {
        "episode_id": "QH11-E0-05",
        "scenario": "turn_on_location_low_battery_mode",
        "prefix_tool": "get_low_battery_mode_status",
        "prefix_arguments": {},
        "error_kind": "boolean-negation-location",
        "mutability": "mutating-rejected-error",
    },
    {
        "episode_id": "QH11-E0-06",
        "scenario": "turn_on_location_low_battery_mode_implicit",
        "prefix_tool": "get_low_battery_mode_status",
        "prefix_arguments": {},
        "error_kind": "boolean-negation-location",
        "mutability": "mutating-rejected-error",
    },
)


# 从 v10 的结果盲确认清单移除 v11 development family。剩余 11 family、
# 每族两个 episode；宁可缩小有边界的有限 census，也不以歧义任务补数量。
_V11_DEVELOPMENT_NAMES = {row["scenario"] for row in DEVELOPMENT_SCENARIOS}
CONFIRMATORY_SCENARIOS = tuple(
    name for name in v10.CONFIRMATORY_SCENARIOS if name not in _V11_DEVELOPMENT_NAMES
)

TECHNICAL_REPEAT_EPISODES = ("QH11-E0-01", "QH11-E0-03", "QH11-E0-05")


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
        raise RuntimeError("v11 科学轨迹清单必须含 96 个唯一逻辑单元")
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
        raise RuntimeError("v11 技术重复清单必须含 24 个唯一逻辑单元")
    return units


def build_trajectory_units() -> list[dict[str, Any]]:
    units = build_scientific_trajectory_units() + build_technical_repeat_units()
    if len(units) != 120 or len({row["unit_id"] for row in units}) != 120:
        raise RuntimeError("v11 E0 必须含 120 个唯一逻辑轨迹")
    return units


def build_qualification_units() -> list[dict[str, Any]]:
    return v10.build_qualification_units()


def expected_precision_counts() -> dict[str, int]:
    units = build_trajectory_units()
    return {
        precision: sum(row["precision"] == precision for row in units)
        for precision in TREATMENT_PRECISIONS
    }


def expected_logical_decision_counts() -> dict[str, int]:
    units = build_trajectory_units()
    return {
        precision: sum(
            int(row["distance"]) + 3
            for row in units
            if row["precision"] == precision
        )
        for precision in TREATMENT_PRECISIONS
    }


def expected_unique_request_counts() -> dict[str, int]:
    """计算 shared erroneous trunk 后实际发送给模型的请求数。"""

    counts: dict[str, int] = {}
    units = build_trajectory_units()
    for precision in TREATMENT_PRECISIONS:
        groups: dict[tuple[str, int, int], list[dict[str, Any]]] = {}
        for row in units:
            if row["precision"] != precision:
                continue
            key = (str(row["episode_id"]), int(row["distance"]), int(row["repeat"]))
            groups.setdefault(key, []).append(row)
        total = 0
        for (_, distance, _), rows in groups.items():
            histories = {str(row["history"]) for row in rows}
            if "N" in histories:
                total += distance + 3
            erroneous = histories - {"N"}
            if erroneous:
                total += distance + 3 * len(erroneous)
        counts[precision] = total
    return counts


def validate_frozen_design() -> dict[str, Any]:
    scientific = build_scientific_trajectory_units()
    repeats = build_technical_repeat_units()
    precision_counts = expected_precision_counts()
    logical_decisions = expected_logical_decision_counts()
    unique_requests = expected_unique_request_counts()
    development_families = {
        normalize_family(str(row["scenario"])) for row in DEVELOPMENT_SCENARIOS
    }
    confirmatory_families = {
        normalize_family(scenario) for scenario in CONFIRMATORY_SCENARIOS
    }
    if precision_counts != {"P00": 72, "P10": 12, "P01": 12, "P11": 24}:
        raise RuntimeError(f"v11 precision 计数漂移：{precision_counts}")
    if logical_decisions != {"P00": 372, "P10": 72, "P01": 72, "P11": 144}:
        raise RuntimeError(f"v11 逻辑决策暴露计数漂移：{logical_decisions}")
    if unique_requests != {"P00": 300, "P10": 72, "P01": 72, "P11": 144}:
        raise RuntimeError(f"v11 唯一模型请求计数漂移：{unique_requests}")
    if len(development_families) != 3 or len(confirmatory_families) != 11:
        raise RuntimeError("v11 必须冻结 3 个 development 与 11 个 confirmatory family")
    if len(CONFIRMATORY_SCENARIOS) != 22:
        raise RuntimeError("v11 确认集必须含 22 个 episode")
    if development_families & confirmatory_families:
        raise RuntimeError("v11 development 与 confirmatory family 不得重叠")
    return {
        "scientific_logical_trajectories": len(scientific),
        "technical_repeat_logical_trajectories": len(repeats),
        "treatment_logical_trajectories": len(scientific) + len(repeats),
        "qualification_runs": len(build_qualification_units()),
        "total_e0_logical_units": (
            len(scientific) + len(repeats) + len(build_qualification_units())
        ),
        "development_episodes": len(DEVELOPMENT_SCENARIOS),
        "development_families": len(development_families),
        "confirmatory_episodes": len(CONFIRMATORY_SCENARIOS),
        "confirmatory_families": len(confirmatory_families),
        "precision_logical_trajectory_counts": precision_counts,
        "precision_logical_decision_counts": logical_decisions,
        "precision_unique_model_request_counts": unique_requests,
    }


if __name__ == "__main__":
    import json

    print(json.dumps(validate_frozen_design(), ensure_ascii=False, indent=2))
