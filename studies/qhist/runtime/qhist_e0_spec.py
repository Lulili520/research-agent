#!/usr/bin/env python3
"""Q-HIST v8 E0 的冻结因子、场景与运行清单。"""

from __future__ import annotations

import hashlib
import json
from typing import Any


PROTOCOL_ID = "QHIST-EXP"
PROTOCOL_VERSION = 8
SCHEDULE_SEED = 20260903
UPSTREAM_COMMIT = "165848b9a78cead7ca7fe7c89c688b58e6501219"
MODEL_ID = "Qwen/Qwen3-32B"
MODEL_REVISION = "9216db5781bf21249d130ec9da846c4624c16137"
REFERENCE_TIME_ISO = "2026-09-03T12:00:00+08:00"
REFERENCE_TIME_EPOCH = 1788408000.0

HISTORIES = ("N", "E", "S", "C_text", "C_align")
DISTANCES = (1, 3)
PRECISIONS = {
    "P00": {
        "weight_bits": 16,
        "weight_backend": "bfloat16",
        "kv_bits": 16,
        "cache_mode": "dynamic",
    },
    "P10": {
        "weight_bits": 4,
        "weight_backend": "optimum-quanto-0.2.7",
        "kv_bits": 16,
        "cache_mode": "dynamic",
    },
    "P01": {
        "weight_bits": 16,
        "weight_backend": "bfloat16",
        "kv_bits": 4,
        "cache_mode": "hqq",
    },
    "P11": {
        "weight_bits": 4,
        "weight_backend": "optimum-quanto-0.2.7",
        "kv_bits": 4,
        "cache_mode": "hqq",
    },
    "K16-shadow": {
        "weight_bits": 16,
        "weight_backend": "bfloat16",
        "kv_bits": 16,
        "cache_mode": "shadow-segmented",
    },
}

DEVELOPMENT_SCENARIOS = (
    {
        "episode_id": "QH-E0-01",
        "scenario": "send_message_with_contact_content_cellular_off",
        "prefix_tool": "search_contacts",
        "prefix_arguments": {"name": "Fredrik Thordendal"},
        "error_kind": "contact-phone-substitution",
        "mutability": "mutating",
    },
    {
        "episode_id": "QH-E0-02",
        "scenario": "send_message_with_contact_content_cellular_off_alt",
        "prefix_tool": "search_contacts",
        "prefix_arguments": {"name": "Fredrik Thordendal"},
        "error_kind": "contact-phone-substitution",
        "mutability": "mutating",
    },
    {
        "episode_id": "QH-E0-03",
        "scenario": "send_message_with_contact_content_cellular_off_multiple_user_turn",
        "prefix_tool": "search_contacts",
        "prefix_arguments": {"name": "Fredrik Thordendal"},
        "error_kind": "contact-phone-substitution",
        "mutability": "mutating",
    },
    {
        "episode_id": "QH-E0-04",
        "scenario": "send_message_with_contact_content_cellular_off_multiple_user_turn_alt",
        "prefix_tool": "search_contacts",
        "prefix_arguments": {"name": "Fredrik Thordendal"},
        "error_kind": "contact-phone-substitution",
        "mutability": "mutating",
    },
    {
        "episode_id": "QH-E0-05",
        "scenario": "turn_on_wifi_low_battery_mode",
        "prefix_tool": "get_low_battery_mode_status",
        "prefix_arguments": {},
        "error_kind": "boolean-negation",
        "mutability": "mutating",
    },
    {
        "episode_id": "QH-E0-06",
        "scenario": "turn_on_wifi_low_battery_mode_implicit",
        "prefix_tool": "get_low_battery_mode_status",
        "prefix_arguments": {},
        "error_kind": "boolean-negation",
        "mutability": "mutating",
    },
    {
        "episode_id": "QH-E0-07",
        "scenario": "remove_reminder_with_recency_latest",
        "prefix_tool": "search_reminder",
        "prefix_arguments": {"reminder_timestamp_lowerbound": 315529200.0},
        "error_kind": "reminder-time-substitution",
        "mutability": "mutating",
    },
    {
        "episode_id": "QH-E0-08",
        "scenario": "remove_reminder_with_recency_latest_alt",
        "prefix_tool": "search_reminder",
        "prefix_arguments": {"reminder_timestamp_lowerbound": 315529200.0},
        "error_kind": "reminder-time-substitution",
        "mutability": "mutating",
    },
)

ORTHOGONALITY_SCENARIOS = {
    "send_message_with_contact_content_cellular_off",
    "send_message_with_contact_content_cellular_off_multiple_user_turn",
    "turn_on_wifi_low_battery_mode",
    "remove_reminder_with_recency_latest",
}

FAMILY_SUFFIXES = (
    "_multiple_user_turn",
    "_implicit",
    "_alt",
    "_ambiguous",
    "_wifi_off",
)


def canonical_json(value: Any) -> str:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        default=str,
    )


def canonical_sha256(value: Any) -> str:
    return hashlib.sha256(canonical_json(value).encode("utf-8")).hexdigest()


def normalize_family(scenario: str) -> str:
    family = scenario
    changed = True
    while changed:
        changed = False
        for suffix in FAMILY_SUFFIXES:
            if family.endswith(suffix):
                family = family[: -len(suffix)]
                changed = True
                break
    return family


def build_trajectory_units() -> list[dict[str, Any]]:
    units: list[dict[str, Any]] = []
    for episode in DEVELOPMENT_SCENARIOS:
        for history in HISTORIES:
            for distance in DISTANCES:
                units.append(
                    {
                        "unit_id": (
                            f'{episode["episode_id"]}-P00-{history}-d{distance}'
                        ),
                        "episode_id": episode["episode_id"],
                        "scenario": episode["scenario"],
                        "family": normalize_family(str(episode["scenario"])),
                        "precision": "P00",
                        "history": history,
                        "distance": distance,
                    }
                )
    for episode in DEVELOPMENT_SCENARIOS:
        if episode["scenario"] not in ORTHOGONALITY_SCENARIOS:
            continue
        for precision in ("P10", "P01", "P11"):
            for history in ("N", "C_text"):
                units.append(
                    {
                        "unit_id": (
                            f'{episode["episode_id"]}-{precision}-{history}-d3'
                        ),
                        "episode_id": episode["episode_id"],
                        "scenario": episode["scenario"],
                        "family": normalize_family(str(episode["scenario"])),
                        "precision": precision,
                        "history": history,
                        "distance": 3,
                    }
                )
    identities = {item["unit_id"] for item in units}
    if len(units) != 104 or len(identities) != 104:
        raise RuntimeError(
            f"E0 轨迹清单必须是 104 个唯一单元，实际 {len(units)}/{len(identities)}"
        )
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
    if len(units) != 30 or len({item["unit_id"] for item in units}) != 30:
        raise RuntimeError("E0 资格清单必须是 30 个唯一单元")
    return units


def validate_frozen_design() -> dict[str, int]:
    trajectories = build_trajectory_units()
    qualifications = build_qualification_units()
    p00 = sum(item["precision"] == "P00" for item in trajectories)
    orthogonal = len(trajectories) - p00
    families = {normalize_family(str(item["scenario"])) for item in DEVELOPMENT_SCENARIOS}
    if (p00, orthogonal, len(families)) != (80, 24, 3):
        raise RuntimeError(
            f"冻结设计不一致：P00={p00}, orthogonal={orthogonal}, families={len(families)}"
        )
    return {
        "p00_trajectories": p00,
        "orthogonality_trajectories": orthogonal,
        "qualification_runs": len(qualifications),
        "total_e0_units": len(trajectories) + len(qualifications),
        "development_families": len(families),
    }
