#!/usr/bin/env python3
"""Q-HIST v9 E0 的冻结因子、运行清单与通用 Agent 合同。"""

from __future__ import annotations

from copy import deepcopy
from typing import Any

from qhist_e0_spec import (
    DEVELOPMENT_SCENARIOS as V8_DEVELOPMENT_SCENARIOS,
    DISTANCES,
    HISTORIES,
    MODEL_ID,
    MODEL_REVISION,
    PRECISIONS as V8_PRECISIONS,
    PROTOCOL_ID,
    REFERENCE_TIME_EPOCH,
    REFERENCE_TIME_ISO,
    SCHEDULE_SEED,
    UPSTREAM_COMMIT,
    canonical_json,
    canonical_sha256,
    normalize_family,
)


PROTOCOL_VERSION = 9
DEVELOPMENT_SCENARIOS = tuple(deepcopy(V8_DEVELOPMENT_SCENARIOS))
PRECISIONS = deepcopy(V8_PRECISIONS)
TREATMENT_PRECISIONS = ("P00", "P10", "P01", "P11")
TECHNICAL_REPEAT_EPISODES = (
    "QH-E0-01",
    "QH-E0-03",
    "QH-E0-05",
    "QH-E0-07",
)

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
        "unit_id": (
            f'{episode["episode_id"]}-{precision}-{history}-d{distance}{suffix}'
        ),
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
    """返回 128 个科学单元；技术重复不属于独立科学样本。"""

    units: list[dict[str, Any]] = []
    for episode in DEVELOPMENT_SCENARIOS:
        for history in HISTORIES:
            for distance in DISTANCES:
                units.append(_unit(episode, "P00", history, distance))
    for episode in DEVELOPMENT_SCENARIOS:
        for precision in ("P10", "P01", "P11"):
            for history in ("N", "C_text"):
                units.append(_unit(episode, precision, history, 3))
    if len(units) != 128 or len({row["unit_id"] for row in units}) != 128:
        raise RuntimeError("v9 科学轨迹清单必须是 128 个唯一单元")
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
    if len(units) != 32 or len({row["unit_id"] for row in units}) != 32:
        raise RuntimeError("v9 技术重复清单必须是 32 个唯一单元")
    return units


def build_trajectory_units() -> list[dict[str, Any]]:
    units = build_scientific_trajectory_units() + build_technical_repeat_units()
    if len(units) != 160 or len({row["unit_id"] for row in units}) != 160:
        raise RuntimeError("v9 E0 轨迹清单必须是 160 个唯一单元")
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
        raise RuntimeError("v9 E0 资格清单必须是 30 个唯一单元")
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
    trajectories = scientific + repeats
    precision_counts = expected_precision_counts()
    request_counts = expected_request_counts()
    families = {
        normalize_family(str(row["scenario"])) for row in DEVELOPMENT_SCENARIOS
    }
    if precision_counts != {"P00": 96, "P10": 16, "P01": 16, "P11": 32}:
        raise RuntimeError(f"v9 precision 计数漂移：{precision_counts}")
    if request_counts != {"P00": 496, "P10": 96, "P01": 96, "P11": 192}:
        raise RuntimeError(f"v9 request 计数漂移：{request_counts}")
    if len(families) != 3:
        raise RuntimeError(f"v9 development family 应为 3，实际 {len(families)}")
    return {
        "scientific_trajectories": len(scientific),
        "technical_repeat_trajectories": len(repeats),
        "treatment_trajectories": len(trajectories),
        "qualification_runs": len(build_qualification_units()),
        "total_e0_units": len(trajectories) + len(build_qualification_units()),
        "development_families": len(families),
        "precision_trajectory_counts": precision_counts,
        "precision_request_counts": request_counts,
    }
