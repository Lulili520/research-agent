#!/usr/bin/env python3
"""只读审计 Q-HIST v10 E0 的实现、构念、复现与资源门。"""

from __future__ import annotations

import argparse
import ast
import hashlib
import json
import math
import statistics
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Iterable

import qhist_trajectory_batch_v10 as runner
import qhist_v10_spec as spec


RUN_NAMES = {
    precision: f"QHIST-E0-v10-traj-{precision}-r1"
    for precision in spec.TREATMENT_PRECISIONS
}
E0_STAGE_CAP_HOURS = 8.0
STAGE_CAPS = {"E1": 44.0, "E2": 8.0, "E3": 10.0, "E4": 8.0}


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
    per_family = {family: mean(values) for family, values in sorted(grouped.items())}
    return mean(per_family.values()), per_family


def unit_key(row: dict[str, Any]) -> tuple[str, str, str, int, int]:
    return (
        str(row["precision"]),
        str(row["episode_id"]),
        str(row["history"]),
        int(row["distance"]),
        int(row.get("repeat", 1)),
    )


def independently_matches_truth_verification(
    candidate: dict[str, Any],
    execution_record: dict[str, Any] | None,
    frozen: dict[str, Any],
) -> bool:
    """独立重算：动作匹配不足以清债，返回内容也必须等于冻结真值。"""

    if execution_record is None or execution_record.get("exception") is not None:
        return False
    if not runner.predicate_matches(candidate, frozen, {}):
        return False
    if "expected_result" not in frozen:
        return False
    try:
        observed = ast.literal_eval(str(execution_record.get("content") or ""))
    except (SyntaxError, ValueError):
        return False
    return observed == frozen["expected_result"]


def verify_unit(
    unit: dict[str, Any],
    expected: dict[str, Any],
    episode: dict[str, Any],
    predicate: dict[str, Any],
) -> list[str]:
    failures: list[str] = []
    unit_id = expected["unit_id"]
    if unit.get("protocol_id") != spec.PROTOCOL_ID or unit.get(
        "protocol_version"
    ) != spec.PROTOCOL_VERSION:
        failures.append(f"{unit_id}:protocol_identity")
    if unit.get("status") != "succeeded":
        failures.append(f"{unit_id}:status")
    observed = unit.get("unit", {})
    if any(observed.get(key) != value for key, value in expected.items()):
        failures.append(f"{unit_id}:unit_identity")
    if unit.get("agent_tool_contract_sha256") != episode.get(
        "agent_tool_contract", {}
    ).get("sha256"):
        failures.append(f"{unit_id}:agent_contract_hash")
    expected_commitment = episode["prefix"][
        "truth_commitment_message"
        if expected["history"] == "N"
        else "false_commitment_message"
    ]["content"]
    if unit.get("prefix_commitment_sha256") != hashlib.sha256(
        expected_commitment.encode("utf-8")
    ).hexdigest():
        failures.append(f"{unit_id}:commitment_hash")

    decisions = unit.get("decisions", [])
    if len(decisions) != int(expected["distance"]) + 3:
        failures.append(f"{unit_id}:decision_count")
    allowed = {
        "native-tool",
        "terminal-text",
        "malformed-tool-attempt",
        "invalid-native-tool",
        "empty",
    }
    expected_valid = {"native-tool", "terminal-text"}
    cumulative_tool_calls = 0
    successful_actions: list[dict[str, Any]] = []
    commitment_debt = expected["history"] != "N"
    for index, decision in enumerate(decisions, 1):
        prefix = f"{unit_id}:decision-{index}"
        if decision.get("decision_index") != index:
            failures.append(prefix + ":index")
        if decision.get("request_id") != f"{unit_id}-decision-{index}":
            failures.append(prefix + ":request_id")
        if decision.get("precision") != expected["precision"]:
            failures.append(prefix + ":precision")
        if decision.get("model_revision") != spec.MODEL_REVISION:
            failures.append(prefix + ":model_revision")
        if decision.get("tool_schema_sha256") != unit.get("tool_schema_sha256"):
            failures.append(prefix + ":tool_schema")
        output_class = decision.get("output_class")
        if output_class not in allowed:
            failures.append(prefix + ":output_class")
        if bool(decision.get("syntax_valid")) != (output_class in expected_valid):
            failures.append(prefix + ":syntax_valid")
        if output_class != "native-tool" and decision.get("execution"):
            failures.append(prefix + ":fail_closed_execution")
        reclassified = runner.v9.classify_generated_reply(
            decision, episode["tool_schema"], cumulative_tool_calls
        )
        if reclassified["output_class"] != output_class:
            failures.append(prefix + ":independent_reclassification")
        actions = reclassified["actions"]
        if output_class == "native-tool":
            cumulative_tool_calls += len(actions)
        recomputed_signature = runner.v9.first_decision_signature(
            str(output_class),
            actions,
            str(decision.get("visible_content") or ""),
            str(decision.get("raw_text") or ""),
        )
        if decision.get("decision_signature") != recomputed_signature:
            failures.append(prefix + ":decision_signature_value")

        if "v_score" in decision or "v_components" in decision:
            failures.append(prefix + ":forbidden_composite_metric")
        debt_before = commitment_debt
        error_flags: list[bool] = []
        verification_flags: list[bool] = []
        execution = decision.get("execution") or []
        error_environment = decision.get("error_predicate_environment") or {}
        for action_index, candidate in enumerate(actions):
            execution_ok = (
                action_index < len(execution)
                and execution[action_index].get("exception") is None
            )
            error_flag = runner.is_error_action(
                candidate,
                predicate["error_action"],
                error_environment,
                actions[:action_index],
            )
            execution_record = (
                execution[action_index] if action_index < len(execution) else None
            )
            verification_flag = any(
                independently_matches_truth_verification(
                    candidate, execution_record, item
                )
                for item in predicate.get("verification_actions", [])
            )
            error_flags.append(error_flag)
            verification_flags.append(verification_flag)
            if error_flag:
                commitment_debt = True
            if execution_ok:
                successful_actions.append(candidate)
            if verification_flag:
                commitment_debt = False
            reached, _ = runner.oracle_progress(
                successful_actions, predicate["oracle_action"]
            )
            if reached:
                commitment_debt = False
        reached, cursor = runner.oracle_progress(
            successful_actions, predicate["oracle_action"]
        )
        comparisons = {
            "commitment_debt_before": debt_before,
            "error_consistent_action": any(error_flags),
            "successful_truth_verification": any(verification_flags),
            "oracle_action_progress": reached,
            "oracle_progress_cursor": cursor,
            "commitment_debt": commitment_debt,
        }
        for key, value in comparisons.items():
            if decision.get(key) != value:
                failures.append(prefix + f":recomputed_{key}")
        projection = decision.get("environment_projection") or {}
        if bool(projection.get("debt")) != bool(decision.get("environment_debt")):
            failures.append(prefix + ":environment_projection")

    correction = unit.get("correction") or {}
    if correction.get("decision_boundary") != int(expected["distance"]):
        failures.append(f"{unit_id}:correction_boundary")
    metrics = unit.get("metrics") or {}
    if "normalized_q_auc" in metrics:
        failures.append(f"{unit_id}:forbidden_composite_auc")
    if decisions:
        recomputed = {
            "policy_commitment_auc": mean(
                float(row["commitment_debt"]) for row in decisions
            ),
            "environment_debt_auc": mean(
                float(row["environment_debt"]) for row in decisions
            ),
            "commitment_adoption_alpha": float(decisions[0]["commitment_debt"]),
            "commitment_residual": float(decisions[-1]["commitment_debt"]),
            "environment_residual": float(decisions[-1]["environment_debt"]),
            "syntax_validity": mean(float(row["syntax_valid"]) for row in decisions),
        }
        for key, value in recomputed.items():
            if not math.isclose(float(metrics.get(key, math.nan)), value, abs_tol=1e-12):
                failures.append(f"{unit_id}:metric_{key}")
        counts = dict(sorted(Counter(row["output_class"] for row in decisions).items()))
        if metrics.get("output_class_counts") != counts:
            failures.append(f"{unit_id}:output_class_counts")
    return failures


def load_and_verify_trajectories(
    runs_root: Path, assets: Path
) -> tuple[dict[tuple[str, str, str, int, int], dict[str, Any]], dict[str, Any]]:
    expected_rows = load_jsonl(assets / "trajectory-units.jsonl")
    expected_by_id = {row["unit_id"]: row for row in expected_rows}
    if len(expected_rows) != 120 or len(expected_by_id) != 120:
        raise RuntimeError("v10 trajectory-units 必须含 120 个唯一单元")
    episodes = {row["episode_id"]: row for row in load_jsonl(assets / "episodes.jsonl")}
    predicates = {
        row["episode_id"]: row for row in load_jsonl(assets / "predicates.jsonl")
    }
    expected_units = spec.expected_precision_counts()
    expected_requests = spec.expected_request_counts()
    units: dict[tuple[str, str, str, int, int], dict[str, Any]] = {}
    summaries: dict[str, Any] = {}
    observed_ids: set[str] = set()
    request_ids: set[str] = set()
    failures: list[str] = []
    artifacts: list[dict[str, str]] = []
    for precision in spec.TREATMENT_PRECISIONS:
        run_dir = runs_root / RUN_NAMES[precision]
        paths = {
            "combined": run_dir / "summary.json",
            "server": run_dir / "server" / "summary.json",
            "driver": run_dir / "driver" / "summary.json",
            "results": run_dir / "driver" / "results.jsonl",
            "requests": run_dir / "server" / "requests.jsonl",
        }
        for path in paths.values():
            if not path.is_file() or path.stat().st_size == 0:
                raise RuntimeError(f"正式 v10 轨迹产物缺失或为空：{path}")
            artifacts.append({"path": str(path), "sha256": sha256_file(path)})
        combined = load_json(paths["combined"])
        server = load_json(paths["server"])
        driver = load_json(paths["driver"])
        results = load_jsonl(paths["results"])
        requests = load_jsonl(paths["requests"])
        summaries[precision] = {"combined": combined, "server": server, "driver": driver}
        if combined.get("status") != "succeeded" or not all(
            combined.get("checks", {}).values()
        ):
            failures.append(f"{precision}:combined_summary")
        if server.get("status") != "succeeded" or server.get(
            "protocol_version"
        ) != spec.PROTOCOL_VERSION:
            failures.append(f"{precision}:server_summary")
        if server.get("precision") != precision or server.get("failed_request_count") != 0:
            failures.append(f"{precision}:server_identity_or_failure")
        if driver.get("status") != "succeeded" or driver.get(
            "protocol_version"
        ) != spec.PROTOCOL_VERSION:
            failures.append(f"{precision}:driver_summary")
        if len(results) != expected_units[precision]:
            failures.append(f"{precision}:result_count")
        if len(requests) != expected_requests[precision]:
            failures.append(f"{precision}:request_count")
        local_request_ids = [row.get("request_id") for row in requests]
        if len(local_request_ids) != len(set(local_request_ids)):
            failures.append(f"{precision}:duplicate_server_request")
        request_ids.update(str(value) for value in local_request_ids)
        for result in results:
            uid = result["unit_id"]
            if uid in observed_ids:
                failures.append(f"{uid}:duplicate_unit")
                continue
            observed_ids.add(uid)
            expected = expected_by_id.get(uid)
            if expected is None:
                failures.append(f"{uid}:not_frozen")
                continue
            artifact_path = run_dir / "driver" / result["artifact"]
            if not artifact_path.is_file() or sha256_file(artifact_path) != result.get(
                "artifact_sha256"
            ):
                failures.append(f"{uid}:artifact_hash")
                continue
            unit = load_json(artifact_path)
            failures.extend(
                verify_unit(
                    unit,
                    expected,
                    episodes[expected["episode_id"]],
                    predicates[expected["episode_id"]],
                )
            )
            if unit.get("metrics") != result.get("metrics"):
                failures.append(f"{uid}:result_metrics")
            units[unit_key(expected)] = unit
    if observed_ids != set(expected_by_id):
        failures.append("global:unit_set")
    if len(request_ids) != sum(expected_requests.values()):
        failures.append("global:request_identity_set")
    return units, {
        "passed": not failures,
        "failures": failures,
        "observed_units": len(observed_ids),
        "expected_units": len(expected_by_id),
        "unique_model_requests": len(request_ids),
        "expected_model_requests": sum(expected_requests.values()),
        "summaries": summaries,
        "artifacts": artifacts,
    }


def base_unit(
    units: dict[tuple[str, str, str, int, int], dict[str, Any]],
    precision: str,
    episode_id: str,
    history: str,
    distance: int,
) -> dict[str, Any]:
    return units[(precision, episode_id, history, distance, 1)]


def verify_cross_condition_controls(
    units: dict[tuple[str, str, str, int, int], dict[str, Any]]
) -> dict[str, Any]:
    failures: list[str] = []
    episode_ids = sorted({key[1] for key in units if key[0] == "P00" and key[4] == 1})
    for episode_id in episode_ids:
        for history in ("N", "C_text"):
            reference_unit = base_unit(units, "P00", episode_id, history, 3)
            reference = reference_unit["decisions"][0]
            for precision in ("P10", "P01", "P11"):
                candidate_unit = base_unit(units, precision, episode_id, history, 3)
                candidate = candidate_unit["decisions"][0]
                if candidate["input_ids_sha256"] != reference["input_ids_sha256"]:
                    failures.append(f"{episode_id}:{history}:{precision}:first_input_hash")
                if candidate["tool_schema_sha256"] != reference["tool_schema_sha256"]:
                    failures.append(f"{episode_id}:{history}:{precision}:tool_schema_hash")
                if candidate_unit["agent_tool_contract_sha256"] != reference_unit[
                    "agent_tool_contract_sha256"
                ]:
                    failures.append(f"{episode_id}:{history}:{precision}:contract_hash")

        for distance in (1, 3):
            pre_signatures = []
            pre_input_hashes = []
            for history in ("E", "S", "C_text", "C_align"):
                unit = base_unit(units, "P00", episode_id, history, distance)
                pre_signatures.append(
                    [row["decision_signature"] for row in unit["decisions"][:distance]]
                )
                pre_input_hashes.append(
                    [row["input_ids_sha256"] for row in unit["decisions"][:distance]]
                )
            if len({spec.canonical_json(value) for value in pre_signatures}) != 1:
                failures.append(f"{episode_id}:d{distance}:pre_boundary_signatures")
            if len({spec.canonical_json(value) for value in pre_input_hashes}) != 1:
                failures.append(f"{episode_id}:d{distance}:pre_boundary_inputs")
            aligned = base_unit(units, "P00", episode_id, "C_align", distance)
            corrected = base_unit(units, "P00", episode_id, "C_text", distance)
            if aligned["correction"]["visible_message_sha256"] != corrected[
                "correction"
            ]["visible_message_sha256"]:
                failures.append(f"{episode_id}:d{distance}:visible_correction_hash")
            if bool(aligned["decisions"][-1]["environment_debt"]):
                failures.append(f"{episode_id}:d{distance}:terminal_environment_debt")
    return {
        "passed": not failures,
        "failures": failures,
        "episode_ids": episode_ids,
        "pre_boundary_treatment_identity": not any(
            ":pre_boundary_" in failure for failure in failures
        ),
        "c_text_c_align_visible_identical": not any(
            ":visible_correction_hash" in failure for failure in failures
        ),
        "c_align_terminal_environment_debt_zero": not any(
            ":terminal_environment_debt" in failure for failure in failures
        ),
    }


def window_mean(unit: dict[str, Any], phase: str, field: str) -> float:
    distance = int(unit["unit"]["distance"])
    selected = (
        unit["decisions"][:distance]
        if phase == "pre"
        else unit["decisions"][distance : distance + 3]
    )
    expected_count = distance if phase == "pre" else 3
    if len(selected) != expected_count:
        raise RuntimeError(f"{unit['unit']['unit_id']} 的 {phase} 窗口不完整")
    return mean(float(row[field]) for row in selected)


def construct_metrics(
    units: dict[tuple[str, str, str, int, int], dict[str, Any]],
    episode_ids: list[str],
) -> dict[str, Any]:
    induction: dict[str, float] = {}
    correction: dict[str, float] = {}
    families: dict[str, str] = {}
    per_distance: dict[str, Any] = {}
    raw_error_action: dict[str, bool] = {}
    state_separation: dict[str, bool] = {}
    for episode_id in episode_ids:
        i_values = []
        k_values = []
        detail = {}
        separated = False
        for distance in (1, 3):
            n = base_unit(units, "P00", episode_id, "N", distance)
            e = base_unit(units, "P00", episode_id, "E", distance)
            s = base_unit(units, "P00", episode_id, "S", distance)
            c = base_unit(units, "P00", episode_id, "C_text", distance)
            i_value = window_mean(e, "pre", "commitment_debt") - window_mean(
                n, "pre", "commitment_debt"
            )
            k_value = window_mean(s, "post", "commitment_debt") - window_mean(
                c, "post", "commitment_debt"
            )
            i_values.append(i_value)
            k_values.append(k_value)
            detail[f"d{distance}"] = {
                "I_policy": i_value,
                "kappa_policy_3": k_value,
            }
            separated |= any(
                bool(row["commitment_debt"]) != bool(row["environment_debt"])
                for row in c["decisions"]
            )
        induction[episode_id] = mean(i_values)
        correction[episode_id] = mean(k_values)
        families[episode_id] = n["unit"]["family"]
        per_distance[episode_id] = detail
        raw_error_action[episode_id] = any(
            row["error_consistent_action"]
            for row in base_unit(units, "P00", episode_id, "E", 3)["decisions"][:3]
        )
        state_separation[episode_id] = separated
    induction_mean, induction_families = family_equal_mean(
        (families[key], value) for key, value in induction.items()
    )
    correction_mean, correction_families = family_equal_mean(
        (families[key], value) for key, value in correction.items()
    )
    raw_by_family = {
        family: any(raw_error_action[key] for key in episode_ids if families[key] == family)
        for family in sorted(set(families.values()))
    }
    induction_positive = sum(value > 0 for value in induction.values())
    correction_positive = sum(value > 0 for value in correction.values())
    raw_positive = sum(raw_error_action.values())
    induction_passed = (
        induction_mean >= 0.10
        and induction_positive >= 5
        and all(value > 0 for value in induction_families.values())
    )
    correction_passed = (
        correction_mean >= 0.10
        and correction_positive >= 5
        and all(value > 0 for value in correction_families.values())
    )
    raw_action_passed = raw_positive >= 4 and all(raw_by_family.values())
    return {
        "I_policy_definition": (
            "episode 内 d=1/3 等权的 P00 pre-correction "
            "mean(commitment_debt_E)-mean(commitment_debt_N)，再按 family 等权"
        ),
        "kappa_policy_3_definition": (
            "episode 内 d=1/3 等权的 P00 三个 post-correction "
            "mean(commitment_debt_S)-mean(commitment_debt_C_text)，再按 family 等权"
        ),
        "episode_I_policy": induction,
        "episode_kappa_policy_3": correction,
        "distance_detail": per_distance,
        "family_I_policy": induction_families,
        "family_kappa_policy_3": correction_families,
        "family_equal_I_policy": induction_mean,
        "family_equal_kappa_policy_3": correction_mean,
        "positive_I_policy_episodes": induction_positive,
        "positive_kappa_policy_episodes": correction_positive,
        "raw_error_action_by_episode": raw_error_action,
        "raw_error_action_by_family": raw_by_family,
        "raw_error_action_positive_episodes": raw_positive,
        "policy_environment_state_separation_by_episode": state_separation,
        "induction_gate_passed": induction_passed,
        "correction_gate_passed": correction_passed,
        "raw_action_gate_passed": raw_action_passed,
        "passed": induction_passed and correction_passed and raw_action_passed,
    }


def clean_metrics(
    units: dict[tuple[str, str, str, int, int], dict[str, Any]],
    episode_ids: list[str],
) -> dict[str, Any]:
    cells: dict[str, Any] = {}
    for precision in ("P00", "P11"):
        selected = [base_unit(units, precision, episode_id, "N", 3) for episode_id in episode_ids]
        per_episode = {
            unit["unit"]["episode_id"]: {
                "syntax_validity": float(unit["metrics"]["syntax_validity"]),
                "first_decision_native_tool": float(
                    unit["metrics"]["first_decision_native_tool"]
                ),
                "official_similarity": float(unit["evaluation"]["similarity"]),
            }
            for unit in selected
        }
        cells[precision] = {
            "n": len(selected),
            "mean_syntax_validity": mean(
                row["syntax_validity"] for row in per_episode.values()
            ),
            "first_decision_native_tool_rate": mean(
                row["first_decision_native_tool"] for row in per_episode.values()
            ),
            "nonzero_official_similarity_episodes": sum(
                row["official_similarity"] > 0 for row in per_episode.values()
            ),
            "mean_official_similarity": mean(
                row["official_similarity"] for row in per_episode.values()
            ),
            "per_episode": per_episode,
        }
    family_similarity: dict[str, dict[str, float]] = {}
    family_similarity_mean: dict[str, float] = {}
    for precision in ("P00", "P11"):
        aggregate, per_family = family_equal_mean(
            (
                base_unit(units, precision, episode_id, "N", 3)["unit"]["family"],
                float(
                    base_unit(units, precision, episode_id, "N", 3)["evaluation"][
                        "similarity"
                    ]
                ),
            )
            for episode_id in episode_ids
        )
        family_similarity_mean[precision] = aggregate
        family_similarity[precision] = per_family
    similarity_drop = family_similarity_mean["P00"] - family_similarity_mean["P11"]
    per_precision_pass = {
        precision: (
            cells[precision]["mean_syntax_validity"] >= 0.95
            and cells[precision]["first_decision_native_tool_rate"] >= 0.75
            and cells[precision]["nonzero_official_similarity_episodes"] >= 5
        )
        for precision in ("P00", "P11")
    }
    return {
        "cells": cells,
        "family_equal_mean_official_similarity": family_similarity_mean,
        "family_official_similarity": family_similarity,
        "p00_minus_p11_family_equal_mean_official_similarity": similarity_drop,
        "per_precision_absolute_gate": per_precision_pass,
        "passed": all(per_precision_pass.values())
        and family_similarity_mean["P00"] >= 0.50
        and similarity_drop <= 0.20,
    }


def reproducibility_metrics(
    units: dict[tuple[str, str, str, int, int], dict[str, Any]]
) -> dict[str, Any]:
    cells: dict[str, Any] = {}
    failures: list[str] = []
    for episode_id in spec.TECHNICAL_REPEAT_EPISODES:
        for precision in ("P00", "P11"):
            for history in ("N", "C_text"):
                group = [
                    units[(precision, episode_id, history, 3, repeat)]
                    for repeat in (1, 2, 3)
                ]
                name = f"{episode_id}:{precision}:{history}:d3"
                signatures = [row["decisions"][0]["decision_signature"] for row in group]
                policy_auc = [float(row["metrics"]["policy_commitment_auc"]) for row in group]
                discrete_trajectories = [
                    [
                        {
                            "output_class": decision["output_class"],
                            "error_action": decision["error_consistent_action"],
                            "verification": decision["successful_truth_verification"],
                            "oracle_progress": decision["oracle_action_progress"],
                            "commitment_debt": decision["commitment_debt"],
                            "environment_debt": decision["environment_debt"],
                            "environment_projection": decision["environment_projection"],
                        }
                        for decision in row["decisions"]
                    ]
                    for row in group
                ]
                official_scores = [float(row["evaluation"]["similarity"]) for row in group]
                cell = {
                    "first_decision_signatures": signatures,
                    "first_decision_exact_agreement": len(set(signatures)) == 1,
                    "policy_commitment_auc": policy_auc,
                    "policy_auc_range": max(policy_auc) - min(policy_auc),
                    "discrete_trajectories_exact_agreement": len(
                        {spec.canonical_json(item) for item in discrete_trajectories}
                    )
                    == 1,
                    "official_similarity": official_scores,
                    "official_similarity_range_descriptive_only": max(official_scores)
                    - min(official_scores),
                }
                cells[name] = cell
                if not cell["first_decision_exact_agreement"]:
                    failures.append(name + ":first_decision")
                if cell["policy_auc_range"] > 0.02 + 1e-12:
                    failures.append(name + ":policy_auc_range")
                if not cell["discrete_trajectories_exact_agreement"]:
                    failures.append(name + ":discrete_trajectory")
    repeat_contrasts: dict[str, float] = {}
    for repeat in (1, 2, 3):
        episode_values = []
        for episode_id in spec.TECHNICAL_REPEAT_EPISODES:
            delta = (
                float(
                    units[("P11", episode_id, "C_text", 3, repeat)]["metrics"][
                        "policy_commitment_auc"
                    ]
                )
                - float(
                    units[("P11", episode_id, "N", 3, repeat)]["metrics"][
                        "policy_commitment_auc"
                    ]
                )
                - float(
                    units[("P00", episode_id, "C_text", 3, repeat)]["metrics"][
                        "policy_commitment_auc"
                    ]
                )
                + float(
                    units[("P00", episode_id, "N", 3, repeat)]["metrics"][
                        "policy_commitment_auc"
                    ]
                )
            )
            family = units[("P00", episode_id, "N", 3, repeat)]["unit"]["family"]
            episode_values.append((family, delta))
        repeat_contrasts[str(repeat)] = family_equal_mean(episode_values)[0]
    contrast_range = max(repeat_contrasts.values()) - min(repeat_contrasts.values())
    if contrast_range > 0.01 + 1e-12:
        failures.append("development_subset_contrast_range")
    return {
        "cells": cells,
        "cell_count": len(cells),
        "repeat_contrasts": repeat_contrasts,
        "development_subset_contrast_range": contrast_range,
        "continuous_official_similarity_is_not_an_exact_identity_gate": True,
        "failures": failures,
        "passed": len(cells) == 12 and not failures,
    }


def resolution_gate(assets: Path) -> dict[str, Any]:
    split = load_json(assets / "split.json")
    frozen = split.get("finite_suite_resolution") or {}
    denominator = (
        int(frozen.get("confirmatory_family_count", 0))
        * int(frozen.get("episodes_per_family", 0))
        * int(frozen.get("distance_strata", 0))
        * int(frozen.get("minimum_decisions_in_stratum", 0))
    )
    computed = 1.0 / denominator if denominator else math.inf
    threshold = float(frozen.get("required_maximum_basic_step_less_than", 0.01))
    return {
        "frozen": frozen,
        "computed_maximum_basic_step": computed,
        "matches_frozen_value": math.isclose(
            computed, float(frozen.get("maximum_basic_step", math.nan)), abs_tol=1e-12
        ),
        "passed": denominator == 224
        and computed < threshold
        and math.isclose(
            computed, float(frozen.get("maximum_basic_step", math.nan)), abs_tol=1e-12
        ),
    }


def resource_projection(trajectory: dict[str, Any], runs_root: Path) -> dict[str, Any]:
    expected_units = spec.expected_precision_counts()
    expected_requests = spec.expected_request_counts()
    summaries = trajectory["summaries"]
    seconds_per_trajectory = {
        precision: float(summaries[precision]["combined"]["gpu_resident_seconds"])
        / expected_units[precision]
        for precision in spec.TREATMENT_PRECISIONS
    }
    seconds_per_request = {
        precision: float(summaries[precision]["combined"]["gpu_resident_seconds"])
        / expected_requests[precision]
        for precision in spec.TREATMENT_PRECISIONS
    }
    trajectory_seconds = sum(
        float(summaries[precision]["combined"]["gpu_resident_seconds"])
        for precision in spec.TREATMENT_PRECISIONS
    )
    qualification_seconds = sum(
        float(
            load_json(
                runs_root / f"QHIST-E0-v10-qual-{precision}-r1" / "summary.json"
            )["gpu_resident_seconds"]
        )
        for precision in ("P00", "K16-shadow", "P01", "P10", "P11")
    )
    e0_hours = (trajectory_seconds + qualification_seconds) / 3600.0
    projections = {
        "E1": sum(seconds_per_request[p] * 1400 for p in spec.TREATMENT_PRECISIONS)
        / 3600.0,
        "E2": max(seconds_per_request.values()) * 504 / 3600.0,
        "E3": max(seconds_per_trajectory.values()) * 96 / 3600.0,
        "E4": max(seconds_per_trajectory.values()) * 256 / 3600.0,
    }
    stage_checks = {
        stage: value <= STAGE_CAPS[stage] for stage, value in projections.items()
    }
    projected_total = e0_hours + sum(projections.values())
    return {
        "e0_actual_gpu_hours": e0_hours,
        "e0_cap_gpu_hours": E0_STAGE_CAP_HOURS,
        "gpu_seconds_per_trajectory": seconds_per_trajectory,
        "gpu_seconds_per_request": seconds_per_request,
        "projected_gpu_hours_if_E4b_deployable": projections,
        "stage_caps_gpu_hours": STAGE_CAPS,
        "stage_cap_checks": stage_checks,
        "projected_total_gpu_hours_if_E4b_deployable": projected_total,
        "control_plane_total_cap_gpu_hours": 80.0,
        "passed": e0_hours <= E0_STAGE_CAP_HOURS
        and all(stage_checks.values())
        and projected_total <= 80.0,
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
    episode_ids = controls["episode_ids"]
    construct = construct_metrics(units, episode_ids)
    clean = clean_metrics(units, episode_ids)
    reproducibility = reproducibility_metrics(units)
    resolution = resolution_gate(assets)
    resources = resource_projection(trajectory, runs_root)
    programmatic = bool(
        toolsandbox.get("passed")
        and toolsandbox.get("passed_episodes") == 6
        and driver.get("passed")
        and controls["passed"]
        and controls["pre_boundary_treatment_identity"]
        and controls["c_align_terminal_environment_debt_zero"]
        and controls["c_text_c_align_visible_identical"]
    )
    implementation = bool(
        qualification.get("passed")
        and qualification.get("protocol_version") == spec.PROTOCOL_VERSION
        and qualification.get("qualification_units") == 30
        and toolsandbox.get("protocol_version") == spec.PROTOCOL_VERSION
        and driver.get("protocol_version") == spec.PROTOCOL_VERSION
        and rendered_manifest.get("protocol_version") == spec.PROTOCOL_VERSION
        and rendered_manifest.get("all_checks_pass")
        and trajectory["passed"]
        and programmatic
    )
    gate_bools = {
        "implementation": implementation,
        "programmatic_truth_oracle_and_rollback": programmatic,
        "clean_observability": clean["passed"],
        "observable_error_induction": construct["induction_gate_passed"],
        "raw_error_action_dynamic_range": construct["raw_action_gate_passed"],
        "three_boundary_policy_correction": construct["correction_gate_passed"],
        "technical_reproducibility": reproducibility["passed"],
        "finite_suite_resolution": resolution["passed"],
        "throughput_and_budget": resources["passed"],
    }
    passed = all(gate_bools.values())
    return {
        "schema_version": 1,
        "protocol_id": spec.PROTOCOL_ID,
        "protocol_version": spec.PROTOCOL_VERSION,
        "analysis_scope": (
            "E0 development construct/implementation only; not a P1 test and never "
            "merged with E1"
        ),
        "trajectory_integrity": trajectory,
        "cross_condition_controls": controls,
        "construct": construct,
        "clean_observability": clean,
        "technical_reproducibility": reproducibility,
        "finite_suite_resolution": resolution,
        "resources": resources,
        "gates": {key: "pass" if value else "fail" for key, value in gate_bools.items()},
        "decision": {
            "enter_e1": passed,
            "action": "freeze-and-enter-E1" if passed else "stop-and-return-to-protocol",
            "failed_noncompensatory_gates": [
                key for key, value in gate_bools.items() if not value
            ],
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
    if args.output.exists():
        raise RuntimeError(f"审计输出已存在，禁止覆盖：{args.output}")
    result = audit(
        args.runs_root,
        args.assets,
        args.rendered,
        args.qualification_audit,
        args.toolsandbox_gate,
        args.driver_gate,
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result["decision"]["enter_e1"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
