#!/usr/bin/env python3
"""只读审计 Q-HIST v8 E0 轨迹、构念、clean cliff、功效规则和资源门。"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import statistics
from collections import defaultdict
from pathlib import Path
from typing import Any, Iterable


PROTOCOL_ID = "QHIST-EXP"
PROTOCOL_VERSION = 8
MODEL_REVISION = "9216db5781bf21249d130ec9da846c4624c16137"
PRECISIONS = ("P00", "P10", "P01", "P11")
RUN_NAMES = {precision: f"QHIST-E0-v8-traj-{precision}-r1" for precision in PRECISIONS}
EXPECTED_UNITS = {"P00": 80, "P10": 8, "P01": 8, "P11": 8}
EXPECTED_REQUESTS = {"P00": 400, "P10": 48, "P01": 48, "P11": 48}
E0_STAGE_CAP_HOURS = 8.0
STAGE_CAPS = {"E1": 44.0, "E2": 8.0, "E3": 10.0, "E4": 8.0}
KAPPA_MINIMUM = 0.10
KAPPA_MINIMUM_CORRECT_EPISODES = 6
FORMAT_VALIDITY_MINIMUM = 0.95
CLEAN_SUCCESS_DROP_MAXIMUM = 0.20
POWER_MINIMUM_RATE = 0.80
MINIMUM_SCIENTIFIC_EFFECT = 0.10


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def load_json(path: Path) -> dict[str, Any]:
    if not path.is_file() or path.stat().st_size == 0:
        raise RuntimeError(f"JSON 产物缺失或为空：{path}")
    return json.loads(path.read_text(encoding="utf-8"))


def load_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.is_file() or path.stat().st_size == 0:
        raise RuntimeError(f"JSONL 产物缺失或为空：{path}")
    return [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def mean(values: Iterable[float]) -> float:
    materialized = list(values)
    if not materialized:
        raise RuntimeError("不能对空集合求均值")
    return statistics.fmean(materialized)


def family_equal_mean(records: Iterable[tuple[str, float]]) -> tuple[float, dict[str, float]]:
    grouped: dict[str, list[float]] = defaultdict(list)
    for family, value in records:
        grouped[family].append(float(value))
    if not grouped:
        raise RuntimeError("family 聚合输入为空")
    family_means = {family: mean(values) for family, values in sorted(grouped.items())}
    return mean(family_means.values()), family_means


def first_post_v(unit: dict[str, Any]) -> float:
    distance = int(unit["unit"]["distance"])
    decisions = unit["decisions"]
    if len(decisions) != distance + 3:
        raise RuntimeError(
            f'{unit["unit"]["unit_id"]} 的决策数应为 {distance + 3}，实际 {len(decisions)}'
        )
    decision = decisions[distance]
    if decision["decision_index"] != distance + 1 or decision["phase"] != "post-correction":
        raise RuntimeError(f'{unit["unit"]["unit_id"]} 的首个纠正后边界错位')
    return float(decision["v_score"])


def strict_task_success(unit: dict[str, Any]) -> float:
    """保守记录完整 ToolSandbox similarity；不替代未冻结的二值阈值。"""
    return float(float(unit["evaluation"]["similarity"]) >= 1.0 - 1e-12)


def verify_unit(
    unit: dict[str, Any],
    expected: dict[str, Any],
    precision: str,
) -> list[str]:
    failures: list[str] = []
    unit_id = expected["unit_id"]
    if unit.get("protocol_id") != PROTOCOL_ID or unit.get("protocol_version") != PROTOCOL_VERSION:
        failures.append(f"{unit_id}:protocol_identity")
    if unit.get("status") != "succeeded":
        failures.append(f"{unit_id}:status")
    observed_identity = unit.get("unit", {})
    if any(observed_identity.get(key) != value for key, value in expected.items()):
        failures.append(f"{unit_id}:unit_identity")
    decisions = unit.get("decisions", [])
    if len(decisions) != int(expected["distance"]) + 3:
        failures.append(f"{unit_id}:decision_count")
    for index, decision in enumerate(decisions, 1):
        if decision.get("decision_index") != index:
            failures.append(f"{unit_id}:decision_index:{index}")
        if decision.get("request_id") != f"{unit_id}-decision-{index}":
            failures.append(f"{unit_id}:request_id:{index}")
        if decision.get("precision") != precision:
            failures.append(f"{unit_id}:precision:{index}")
        if decision.get("model_revision") != MODEL_REVISION:
            failures.append(f"{unit_id}:model_revision:{index}")
        if decision.get("tool_schema_sha256") != unit.get("tool_schema_sha256"):
            failures.append(f"{unit_id}:tool_schema:{index}")
        components = decision.get("v_components", {})
        if not components or not math.isclose(
            float(decision.get("v_score", math.nan)),
            mean(float(value) for value in components.values()),
            abs_tol=1e-12,
        ):
            failures.append(f"{unit_id}:v_score:{index}")
    if unit.get("correction", {}).get("decision_boundary") != int(expected["distance"]):
        failures.append(f"{unit_id}:correction_boundary")
    return failures


def load_and_verify_trajectories(
    runs_root: Path,
    assets: Path,
) -> tuple[dict[tuple[str, str, str, int], dict[str, Any]], dict[str, Any]]:
    expected_rows = load_jsonl(assets / "trajectory-units.jsonl")
    expected_by_id = {row["unit_id"]: row for row in expected_rows}
    if len(expected_rows) != 104 or len(expected_by_id) != 104:
        raise RuntimeError("冻结 trajectory-units 必须包含 104 个唯一单元")

    units: dict[tuple[str, str, str, int], dict[str, Any]] = {}
    summaries: dict[str, Any] = {}
    observed_ids: set[str] = set()
    request_ids: set[str] = set()
    failures: list[str] = []
    artifacts: list[dict[str, str]] = []

    for precision in PRECISIONS:
        run_dir = runs_root / RUN_NAMES[precision]
        summary_path = run_dir / "summary.json"
        server_summary_path = run_dir / "server" / "summary.json"
        driver_summary_path = run_dir / "driver" / "summary.json"
        results_path = run_dir / "driver" / "results.jsonl"
        server_requests_path = run_dir / "server" / "requests.jsonl"
        for path in (
            summary_path,
            server_summary_path,
            driver_summary_path,
            results_path,
            server_requests_path,
        ):
            if not path.is_file() or path.stat().st_size == 0:
                raise RuntimeError(f"正式轨迹产物缺失或为空：{path}")
            artifacts.append({"path": str(path), "sha256": sha256_file(path)})

        summary = load_json(summary_path)
        server = load_json(server_summary_path)
        driver = load_json(driver_summary_path)
        result_rows = load_jsonl(results_path)
        server_requests = load_jsonl(server_requests_path)
        summaries[precision] = {"combined": summary, "server": server, "driver": driver}

        if summary.get("status") != "succeeded" or not all(summary.get("checks", {}).values()):
            failures.append(f"{precision}:combined_summary")
        if server.get("status") != "succeeded" or server.get("precision") != precision:
            failures.append(f"{precision}:server_summary")
        if server.get("failed_request_count") != 0:
            failures.append(f"{precision}:failed_model_requests")
        if driver.get("status") != "succeeded" or driver.get("precision") != precision:
            failures.append(f"{precision}:driver_summary")
        if len(result_rows) != EXPECTED_UNITS[precision]:
            failures.append(f"{precision}:result_count")
        if len(server_requests) != EXPECTED_REQUESTS[precision]:
            failures.append(f"{precision}:request_count")

        local_request_ids = [row.get("request_id") for row in server_requests]
        if len(local_request_ids) != len(set(local_request_ids)):
            failures.append(f"{precision}:duplicate_server_request")
        request_ids.update(str(value) for value in local_request_ids)

        for result in result_rows:
            unit_id = result["unit_id"]
            if unit_id in observed_ids:
                failures.append(f"{unit_id}:duplicate_unit")
                continue
            observed_ids.add(unit_id)
            expected = expected_by_id.get(unit_id)
            if expected is None:
                failures.append(f"{unit_id}:not_frozen")
                continue
            artifact_path = run_dir / "driver" / result["artifact"]
            if not artifact_path.is_file() or sha256_file(artifact_path) != result["artifact_sha256"]:
                failures.append(f"{unit_id}:artifact_hash")
                continue
            unit = load_json(artifact_path)
            failures.extend(verify_unit(unit, expected, precision))
            if unit.get("metrics") != result.get("metrics"):
                failures.append(f"{unit_id}:result_metrics")
            key = (
                precision,
                str(expected["episode_id"]),
                str(expected["history"]),
                int(expected["distance"]),
            )
            units[key] = unit

    expected_ids = set(expected_by_id)
    if observed_ids != expected_ids:
        failures.append("global:unit_set")
    if len(request_ids) != 544:
        failures.append("global:request_identity_set")

    return units, {
        "passed": not failures,
        "failures": failures,
        "observed_units": len(observed_ids),
        "expected_units": len(expected_ids),
        "unique_model_requests": len(request_ids),
        "expected_model_requests": 544,
        "summaries": summaries,
        "artifacts": artifacts,
    }


def verify_cross_condition_controls(
    units: dict[tuple[str, str, str, int], dict[str, Any]],
) -> dict[str, Any]:
    failures: list[str] = []
    orthogonal_episode_ids = sorted(
        {
            episode_id
            for precision, episode_id, _, distance in units
            if precision == "P11" and distance == 3
        }
    )
    for episode_id in orthogonal_episode_ids:
        for history in ("N", "C_text"):
            reference = units[("P00", episode_id, history, 3)]["decisions"][0]
            for precision in ("P10", "P01", "P11"):
                candidate = units[(precision, episode_id, history, 3)]["decisions"][0]
                if candidate["input_ids_sha256"] != reference["input_ids_sha256"]:
                    failures.append(f"{episode_id}:{history}:{precision}:first_input_hash")
                if candidate["tool_schema_sha256"] != reference["tool_schema_sha256"]:
                    failures.append(f"{episode_id}:{history}:{precision}:tool_schema_hash")

    c_align_terminal_debt_zero = True
    c_text_align_visible_identical = True
    for key, aligned in units.items():
        precision, episode_id, history, distance = key
        if precision != "P00" or history != "C_align":
            continue
        corrected = units[("P00", episode_id, "C_text", distance)]
        if aligned["correction"]["visible_message_sha256"] != corrected["correction"]["visible_message_sha256"]:
            c_text_align_visible_identical = False
            failures.append(f"{episode_id}:d{distance}:visible_correction_hash")
        if bool(aligned["decisions"][-1]["environment_debt"]):
            c_align_terminal_debt_zero = False
            failures.append(f"{episode_id}:d{distance}:terminal_environment_debt")

    return {
        "passed": not failures,
        "failures": failures,
        "orthogonal_episode_ids": orthogonal_episode_ids,
        "same_first_input_and_tool_hashes": not any(
            "first_input_hash" in item or "tool_schema_hash" in item for item in failures
        ),
        "c_text_c_align_visible_identical": c_text_align_visible_identical,
        "c_align_terminal_environment_debt_zero": c_align_terminal_debt_zero,
    }


def construct_metrics(
    units: dict[tuple[str, str, str, int], dict[str, Any]],
    programmatic_oracle_passed: bool,
) -> dict[str, Any]:
    episode_ids = sorted({episode_id for precision, episode_id, _, _ in units if precision == "P00"})
    episode_kappa: dict[str, float] = {}
    episode_family: dict[str, str] = {}
    distance_kappa: dict[str, dict[str, float]] = {}
    for episode_id in episode_ids:
        values: dict[str, float] = {}
        for distance in (1, 3):
            sham = units[("P00", episode_id, "S", distance)]
            correction = units[("P00", episode_id, "C_text", distance)]
            values[f"d{distance}"] = first_post_v(sham) - first_post_v(correction)
        distance_kappa[episode_id] = values
        episode_kappa[episode_id] = mean(values.values())
        episode_family[episode_id] = units[("P00", episode_id, "N", 1)]["unit"]["family"]

    family_weighted_kappa, family_kappa = family_equal_mean(
        (episode_family[episode_id], value) for episode_id, value in episode_kappa.items()
    )
    episode_weighted_kappa = mean(episode_kappa.values())
    correct_directions = sum(value > 0 for value in episode_kappa.values())
    kappa_passed = (
        family_weighted_kappa >= KAPPA_MINIMUM
        and correct_directions >= KAPPA_MINIMUM_CORRECT_EPISODES
    )
    return {
        "kappa_definition": "P00 中首个纠正后边界 V_S - V_C_text；先跨 d=1/3 在 episode 内等权，再按 family 等权",
        "family_weighted_kappa": family_weighted_kappa,
        "episode_weighted_kappa_sensitivity": episode_weighted_kappa,
        "family_kappa": family_kappa,
        "episode_kappa": episode_kappa,
        "distance_kappa": distance_kappa,
        "direction_correct_episodes": correct_directions,
        "total_episodes": len(episode_kappa),
        "thresholds": {
            "kappa_minimum": KAPPA_MINIMUM,
            "direction_correct_episodes_minimum": KAPPA_MINIMUM_CORRECT_EPISODES,
        },
        "kappa_gate_passed": kappa_passed,
        "programmatic_oracle_and_rollback_passed": programmatic_oracle_passed,
        "human_blind_rating": {
            "status": "pending",
            "required_raters": 2,
            "cohen_kappa_minimum": 0.80,
            "icc_2_k_minimum": 0.75,
            "passed": False,
        },
        "automated_construct_gate_passed": kappa_passed and programmatic_oracle_passed,
        "full_construct_gate_passed": False,
    }


def clean_cliff_metrics(
    units: dict[tuple[str, str, str, int], dict[str, Any]],
    orthogonal_episode_ids: list[str],
) -> dict[str, Any]:
    cells: dict[str, Any] = {}
    for precision in ("P00", "P11"):
        selected = [units[(precision, episode_id, "N", 3)] for episode_id in orthogonal_episode_ids]
        cells[precision] = {
            "n": len(selected),
            "mean_format_validity": mean(float(unit["metrics"]["format_validity"]) for unit in selected),
            "mean_toolsandbox_similarity": mean(float(unit["evaluation"]["similarity"]) for unit in selected),
            "strict_full_similarity_success_rate": mean(strict_task_success(unit) for unit in selected),
            "per_episode": {
                unit["unit"]["episode_id"]: {
                    "format_validity": float(unit["metrics"]["format_validity"]),
                    "toolsandbox_similarity": float(unit["evaluation"]["similarity"]),
                    "strict_full_similarity_success": strict_task_success(unit),
                }
                for unit in selected
            },
        }
    strict_success_drop = (
        cells["P00"]["strict_full_similarity_success_rate"]
        - cells["P11"]["strict_full_similarity_success_rate"]
    )
    format_cliff = cells["P11"]["mean_format_validity"] < FORMAT_VALIDITY_MINIMUM
    strict_success_cliff = strict_success_drop > CLEAN_SUCCESS_DROP_MAXIMUM
    return {
        "cells": cells,
        "strict_success_drop_p00_minus_p11": strict_success_drop,
        "thresholds": {
            "p11_n_format_validity_minimum": FORMAT_VALIDITY_MINIMUM,
            "p11_vs_p00_task_success_drop_maximum": CLEAN_SUCCESS_DROP_MAXIMUM,
        },
        "format_clean_cliff": format_cliff,
        "strict_success_clean_cliff_sensitivity": strict_success_cliff,
        "clean_cliff": format_cliff or strict_success_cliff,
        "task_success_note": (
            "冻结文本未指定 ToolSandbox similarity 的二值成功阈值，因此同时保留连续 similarity 与最严格的 similarity=1 敏感性；"
            "clean cliff 的格式分支不依赖该歧义。"
        ),
    }


def power_rule_audit(
    units: dict[tuple[str, str, str, int], dict[str, Any]],
    orthogonal_episode_ids: list[str],
) -> dict[str, Any]:
    episode_delta: dict[str, float] = {}
    family_records: list[tuple[str, float]] = []
    for episode_id in orthogonal_episode_ids:
        p11 = (
            float(units[("P11", episode_id, "C_text", 3)]["metrics"]["normalized_q_auc"])
            - float(units[("P11", episode_id, "N", 3)]["metrics"]["normalized_q_auc"])
        )
        p00 = (
            float(units[("P00", episode_id, "C_text", 3)]["metrics"]["normalized_q_auc"])
            - float(units[("P00", episode_id, "N", 3)]["metrics"]["normalized_q_auc"])
        )
        delta = p11 - p00
        episode_delta[episode_id] = delta
        family = units[("P00", episode_id, "N", 3)]["unit"]["family"]
        family_records.append((family, delta))

    delta_point, family_delta = family_equal_mean(family_records)
    family_values = list(family_delta.values())
    if len(family_values) != 3:
        raise RuntimeError(f"E0 方差审计要求 3 个 development family，实际 {len(family_values)}")
    s_dev = statistics.stdev(family_values)
    chi_square_df2_q10 = -2.0 * math.log(0.9)
    s_upper = s_dev * math.sqrt(2.0 / chi_square_df2_q10)
    s_effective = max(s_upper, 0.10)

    # 冻结规则在真实效应恰等于 MES 时还要求同方向点估计达到 MES。
    # 对 Normal 和中心化缩放 t(5) 的连续对称 family-effect DGP，样本均值
    # 关于真实均值对称，因此 P(hat_delta >= +MES)=0.5，负方向同理。
    # “95% CI 不含 0”只能缩小这个事件，不可能把正确方向命中率提高到 0.8。
    directional_hit_rate_upper_bound = 0.5
    logically_attainable = directional_hit_rate_upper_bound >= POWER_MINIMUM_RATE
    return {
        "pilot_delta_q_family_weighted": delta_point,
        "episode_delta_q": episode_delta,
        "family_delta_q": family_delta,
        "s_dev": s_dev,
        "chi_square_df2_q10": chi_square_df2_q10,
        "s_upper_one_sided_90pct": s_upper,
        "s_effective": s_effective,
        "frozen_simulation_cases": [
            "normal:+0.10",
            "normal:-0.10",
            "scaled-t5:+0.10",
            "scaled-t5:-0.10",
        ],
        "requested_outer_simulations_per_case": 5000,
        "simulation_executed": False,
        "directional_hit_rate_upper_bound": directional_hit_rate_upper_bound,
        "minimum_required_rate": POWER_MINIMUM_RATE,
        "logical_precheck_passed": logically_attainable,
        "power_gate_passed": False,
        "reason": (
            "冻结计划把真实效应设为 ±0.10，同时把正确方向 meaningful-effect 判定设为点估计绝对值至少 0.10。"
            "在两类连续对称 DGP 下，点估计跨过同方向边界的概率恰为 0.5；再加 CI 排除 0 只会降低命中率。"
            "因此 0.80 门在数学上不可达，5000 次蒙特卡洛不能改变裁决，必须先升版修正功效目标。"
        ),
    }


def resource_projection(
    trajectory_audit: dict[str, Any],
    runs_root: Path,
) -> dict[str, Any]:
    summaries = trajectory_audit["summaries"]
    seconds_per_trajectory = {
        precision: float(summaries[precision]["combined"]["gpu_resident_seconds"])
        / EXPECTED_UNITS[precision]
        for precision in PRECISIONS
    }
    seconds_per_request = {
        precision: float(summaries[precision]["combined"]["gpu_resident_seconds"])
        / EXPECTED_REQUESTS[precision]
        for precision in PRECISIONS
    }
    trajectory_seconds = sum(
        float(summaries[precision]["combined"]["gpu_resident_seconds"])
        for precision in PRECISIONS
    )
    qualification_seconds = sum(
        float(load_json(runs_root / f"QHIST-E0-v8-qual-{precision}-r1" / "summary.json")["gpu_resident_seconds"])
        for precision in ("P00", "K16-shadow", "P01", "P10", "P11")
    )
    ipc_seconds = float(
        load_json(runs_root / "QHIST-E0-v8-ipc-smoke-r1" / "server" / "summary.json")[
            "gpu_resident_seconds"
        ]
    )
    e0_actual_hours = (trajectory_seconds + qualification_seconds + ipc_seconds) / 3600.0

    e1_hours = sum(seconds_per_trajectory[p] * 320 for p in PRECISIONS) / 3600.0
    worst_trajectory_seconds = max(seconds_per_trajectory.values())
    worst_request_seconds = max(seconds_per_request.values())
    e2_hours = worst_request_seconds * 576 / 3600.0
    e3_hours = worst_trajectory_seconds * 96 / 3600.0
    e4_hours = worst_trajectory_seconds * 256 / 3600.0
    projections = {"E1": e1_hours, "E2": e2_hours, "E3": e3_hours, "E4": e4_hours}
    stage_checks = {
        stage: value <= STAGE_CAPS[stage] for stage, value in projections.items()
    }
    return {
        "e0_actual_gpu_hours_v8": e0_actual_hours,
        "e0_cap_gpu_hours": E0_STAGE_CAP_HOURS,
        "e0_cap_passed": e0_actual_hours <= E0_STAGE_CAP_HOURS,
        "gpu_seconds_per_trajectory": seconds_per_trajectory,
        "gpu_seconds_per_request": seconds_per_request,
        "projection_method": (
            "E1 使用各 precision 的 E0 resident-seconds/trajectory；E2 使用四条件最慢 resident-seconds/request；"
            "E3/E4 使用四条件最慢 resident-seconds/trajectory，且把 8B 也按 32B 最慢值保守上界。"
        ),
        "projected_gpu_hours": projections,
        "stage_caps_gpu_hours": STAGE_CAPS,
        "stage_cap_checks": stage_checks,
        "all_resource_gates_passed": e0_actual_hours <= E0_STAGE_CAP_HOURS and all(stage_checks.values()),
        "projected_total_including_conditional_e3_gpu_hours": e0_actual_hours + sum(projections.values()),
    }


def audit(
    runs_root: Path,
    assets: Path,
    rendered: Path,
    qualification_audit: Path,
    toolsandbox_gate: Path,
    driver_gate: Path,
) -> dict[str, Any]:
    qualification = load_json(qualification_audit)
    toolsandbox = load_json(toolsandbox_gate)
    driver = load_json(driver_gate)
    rendered_manifest = load_json(rendered / "manifest.json")
    units, trajectory = load_and_verify_trajectories(runs_root, assets)
    controls = verify_cross_condition_controls(units)
    programmatic_oracle_passed = bool(
        toolsandbox.get("passed")
        and toolsandbox.get("passed_episodes") == 8
        and driver.get("passed")
        and controls["c_align_terminal_environment_debt_zero"]
        and controls["c_text_c_align_visible_identical"]
    )
    construct = construct_metrics(units, programmatic_oracle_passed)
    clean = clean_cliff_metrics(units, controls["orthogonal_episode_ids"])
    power = power_rule_audit(units, controls["orthogonal_episode_ids"])
    resources = resource_projection(trajectory, runs_root)

    implementation_passed = bool(
        qualification.get("passed")
        and qualification.get("qualification_units") == 30
        and toolsandbox.get("passed")
        and driver.get("passed")
        and rendered_manifest.get("all_checks_pass")
        and trajectory["passed"]
        and controls["passed"]
    )
    gate = {
        "implementation": "pass" if implementation_passed else "fail",
        "automated_construct": "pass" if construct["automated_construct_gate_passed"] else "fail",
        "human_blind_rating": "pending",
        "clean_quality": "fail" if clean["clean_cliff"] else "pass",
        "power": "fail",
        "throughput_and_budget": "pass" if resources["all_resource_gates_passed"] else "fail",
        "overall": "fail-stop-before-E1",
    }
    return {
        "schema_version": 1,
        "protocol_id": PROTOCOL_ID,
        "protocol_version": PROTOCOL_VERSION,
        "analysis_scope": "E0 development only; not a P1 test and not mergeable with E1",
        "trajectory_integrity": trajectory,
        "cross_condition_controls": controls,
        "construct": construct,
        "clean_quality": clean,
        "power_rule_audit": power,
        "resources": resources,
        "gate": gate,
        "decision": {
            "enter_e1": False,
            "action": "stop-and-return-to-protocol",
            "reasons": [
                key for key, value in gate.items() if value == "fail"
            ]
            + ["human_blind_rating_pending"],
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--runs-root", type=Path, required=True)
    parser.add_argument("--assets", type=Path, required=True)
    parser.add_argument("--rendered", type=Path, required=True)
    parser.add_argument("--qualification-audit", type=Path, required=True)
    parser.add_argument("--toolsandbox-gate", type=Path, required=True)
    parser.add_argument("--driver-gate", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result = audit(
        args.runs_root,
        args.assets,
        args.rendered,
        args.qualification_audit,
        args.toolsandbox_gate,
        args.driver_gate,
    )
    if args.output.exists():
        raise RuntimeError(f"审计输出已存在，禁止覆盖：{args.output}")
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(result, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result["decision"]["enter_e1"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
