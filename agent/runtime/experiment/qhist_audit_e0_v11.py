#!/usr/bin/env python3
"""只读审计 Q-HIST v11 E0 的实现、F/V/G/B/E 构念、fork 与资源门。"""

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

import qhist_audit_e0_v10 as previous
import qhist_trajectory_batch_v11 as runner
import qhist_v11_spec as spec


RUN_NAMES = {
    precision: f"QHIST-E0-v11-traj-{precision}-r1"
    for precision in spec.TREATMENT_PRECISIONS
}
E0_STAGE_CAP_HOURS = 8.0
STAGE_CAPS = {"E1": 44.0, "E2": 8.0, "E3": 10.0, "E4": 8.0}


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


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def mean(values: Iterable[float]) -> float:
    materialized = list(values)
    if not materialized:
        raise RuntimeError("不能对空集合求均值")
    return statistics.fmean(materialized)


def family_equal_mean(
    records: Iterable[tuple[str, float]]
) -> tuple[float, dict[str, float]]:
    grouped: dict[str, list[float]] = defaultdict(list)
    for family, value in records:
        grouped[family].append(float(value))
    if not grouped:
        raise RuntimeError("family 聚合输入为空")
    per_family = {
        family: mean(values) for family, values in sorted(grouped.items())
    }
    return mean(per_family.values()), per_family


def unit_key(row: dict[str, Any]) -> tuple[str, str, str, int, int]:
    return (
        str(row["precision"]),
        str(row["episode_id"]),
        str(row["history"]),
        int(row["distance"]),
        int(row.get("repeat", 1)),
    )


def base_unit(
    units: dict[tuple[str, str, str, int, int], dict[str, Any]],
    precision: str,
    episode_id: str,
    history: str,
    distance: int,
) -> dict[str, Any]:
    return units[(precision, episode_id, history, distance, 1)]


def independent_action_matches(
    action: dict[str, Any],
    frozen: dict[str, Any],
    environment: dict[str, Any] | None,
    bindings: dict[str, Any],
) -> bool:
    if action.get("name") != frozen.get("tool"):
        return False
    arguments = action.get("arguments") or {}
    if any(
        arguments.get(key) != value
        for key, value in (frozen.get("arguments_contains") or {}).items()
    ):
        return False
    if any(
        (environment or {}).get(key) != value
        for key, value in (frozen.get("when_environment") or {}).items()
    ):
        return False
    binding_rule = frozen.get("binding_argument")
    if binding_rule:
        binding = str(binding_rule["binding"])
        argument = str(binding_rule["argument"])
        if binding not in bindings or arguments.get(argument) != bindings[binding]:
            return False
    return True


def independent_truth_verification(
    action: dict[str, Any],
    execution: dict[str, Any] | None,
    frozen: dict[str, Any],
    bindings: dict[str, Any],
) -> bool:
    if execution is None or execution.get("exception") is not None:
        return False
    if not independent_action_matches(action, frozen, {}, bindings):
        return False
    if "expected_result" not in frozen:
        return False
    try:
        observed = ast.literal_eval(str(execution.get("content") or ""))
    except (SyntaxError, ValueError):
        return False
    return observed == frozen["expected_result"]


def parse_execution_value(execution: dict[str, Any] | None) -> Any:
    if execution is None or execution.get("exception") is not None:
        return None
    try:
        return ast.literal_eval(str(execution.get("content") or ""))
    except (SyntaxError, ValueError):
        return None


def normalize_ids(value: Any, roles: dict[str, str]) -> Any:
    if isinstance(value, dict):
        return {key: normalize_ids(child, roles) for key, child in sorted(value.items())}
    if isinstance(value, list):
        return [normalize_ids(child, roles) for child in value]
    if isinstance(value, str) and value in roles:
        return {"opaque_role": roles[value]}
    return value


def independently_rebuild_scientific_signature(
    unit: dict[str, Any], episode: dict[str, Any], bindings: dict[str, Any]
) -> dict[str, Any]:
    roles: dict[str, str] = {}
    for role, value in (episode.get("dynamic_roles") or {}).items():
        if isinstance(value, str):
            roles[value] = role
    for role, value in bindings.items():
        if isinstance(value, str):
            roles[value] = role
    rows = []
    goal_seen = False
    for decision in unit["decisions"]:
        if goal_seen and decision["output_class"] != "native-tool":
            continue
        rows.append(
            {
                "decision_index": decision["decision_index"],
                "output_class": decision["output_class"],
                "attempted_actions": normalize_ids(
                    decision["attempted_actions"], roles
                ),
                "execution_success": [
                    record.get("exception") is None
                    for record in decision.get("execution") or []
                ],
                "error_consistent_action": decision["error_consistent_action"],
                "successful_truth_verification": decision[
                    "successful_truth_verification"
                ],
                "successful_recovery_certificate": decision[
                    "successful_recovery_certificate"
                ],
                "successful_goal_completion": decision[
                    "successful_goal_completion"
                ],
                "commitment_debt": decision["commitment_debt"],
                "environment_debt": decision["environment_debt"],
                "goal_completed": decision["goal_completed"],
                "terminal_before_goal_completion": decision[
                    "terminal_before_goal_completion"
                ],
                "pre_goal_terminal_text_sha256": (
                    decision["decision_signature"]
                    if decision["output_class"] != "native-tool"
                    else None
                ),
            }
        )
        goal_seen = bool(goal_seen or decision["goal_completed"])
    correction = unit.get("correction") or {}
    return {
        "prefix_observation": unit["prefix_observation"],
        "correction_message_sha256": correction.get("visible_message_sha256"),
        "correction_patch_operation": (
            (correction.get("patch") or {}).get("operation")
        ),
        "decisions_through_first_goal_completion_plus_later_tool_actions": rows,
    }


def verify_unit(
    unit: dict[str, Any],
    expected: dict[str, Any],
    episode: dict[str, Any],
    predicate: dict[str, Any],
) -> list[str]:
    failures: list[str] = []
    unit_id = expected["unit_id"]
    if (
        unit.get("protocol_id") != spec.PROTOCOL_ID
        or unit.get("protocol_version") != spec.PROTOCOL_VERSION
    ):
        failures.append(f"{unit_id}:protocol_identity")
    if unit.get("status") != "succeeded":
        failures.append(f"{unit_id}:status")
    observed = unit.get("unit") or {}
    if any(observed.get(key) != value for key, value in expected.items()):
        failures.append(f"{unit_id}:unit_identity")
    if unit.get("agent_tool_contract_sha256") != (
        episode.get("agent_tool_contract") or {}
    ).get("sha256"):
        failures.append(f"{unit_id}:agent_contract_hash")
    expected_commitment = episode["prefix"][
        "truth_commitment_message"
        if expected["history"] == "N"
        else "false_commitment_message"
    ]["content"]
    expected_observation = "truth" if expected["history"] == "N" else "false"
    if unit.get("prefix_observation") != expected_observation:
        failures.append(f"{unit_id}:prefix_observation")
    expected_observation_hash = episode["prefix"][
        "truth_sha256" if expected["history"] == "N" else "false_sha256"
    ]
    if unit.get("prefix_observation_sha256") != expected_observation_hash:
        failures.append(f"{unit_id}:prefix_observation_hash")
    if unit.get("prefix_commitment_sha256") != hashlib.sha256(
        expected_commitment.encode("utf-8")
    ).hexdigest():
        failures.append(f"{unit_id}:commitment_hash")

    decisions = unit.get("decisions") or []
    if len(decisions) != int(expected["distance"]) + 3:
        failures.append(f"{unit_id}:decision_count")
    allowed = {
        "native-tool",
        "terminal-text",
        "malformed-tool-attempt",
        "invalid-native-tool",
        "empty",
    }
    valid_classes = {"native-tool", "terminal-text"}
    cumulative_calls = 0
    debt = expected["history"] != "N"
    bindings = dict(episode.get("dynamic_roles") or {})
    recovery_reached = False
    goal_completed = False
    for index, decision in enumerate(decisions, 1):
        prefix = f"{unit_id}:decision-{index}"
        if decision.get("decision_index") != index:
            failures.append(prefix + ":index")
        if decision.get("precision") != expected["precision"]:
            failures.append(prefix + ":precision")
        if decision.get("model_revision") != spec.MODEL_REVISION:
            failures.append(prefix + ":model_revision")
        if decision.get("tool_schema_sha256") != unit.get("tool_schema_sha256"):
            failures.append(prefix + ":tool_schema")
        output_class = decision.get("output_class")
        if output_class not in allowed:
            failures.append(prefix + ":output_class")
        if bool(decision.get("syntax_valid")) != (output_class in valid_classes):
            failures.append(prefix + ":syntax_valid")
        if output_class != "native-tool" and decision.get("execution"):
            failures.append(prefix + ":fail_closed_execution")
        reclassified = runner.v9.classify_generated_reply(
            decision, episode["tool_schema"], cumulative_calls
        )
        if reclassified["output_class"] != output_class:
            failures.append(prefix + ":independent_reclassification")
        actions = reclassified["actions"]
        if output_class == "native-tool":
            cumulative_calls += len(actions)
        signature = runner.v9.first_decision_signature(
            str(output_class),
            actions,
            str(decision.get("visible_content") or ""),
            str(decision.get("raw_text") or ""),
        )
        if decision.get("decision_signature") != signature:
            failures.append(prefix + ":decision_signature")
        if "v_score" in decision or "v_components" in decision:
            failures.append(prefix + ":forbidden_composite")

        execution = decision.get("execution") or []
        if output_class == "native-tool" and len(execution) != len(actions):
            failures.append(prefix + ":execution_cardinality")
        environment = decision.get("error_predicate_environment") or {}
        debt_before = debt
        error_flags = []
        verification_flags = []
        recovery_flags = []
        completion_flags = []
        for action_index, candidate in enumerate(actions):
            record = execution[action_index] if action_index < len(execution) else None
            execution_ok = (
                record is not None and record.get("exception") is None
            )
            error_flag = independent_action_matches(
                candidate,
                predicate["error_action"],
                environment,
                bindings,
            )
            blocker = predicate["error_action"].get("unless_preceded_by")
            if error_flag and blocker:
                for prior_index, prior in enumerate(actions[:action_index]):
                    prior_record = (
                        execution[prior_index]
                        if prior_index < len(execution)
                        else None
                    )
                    if (
                        independent_action_matches(
                            prior, blocker, environment, bindings
                        )
                        and prior_record is not None
                        and prior_record.get("exception") is None
                    ):
                        error_flag = False
                        break
            if (
                error_flag
                and execution_ok
                and predicate["error_action"].get("binds_success_result")
            ):
                value = parse_execution_value(record)
                if value is not None:
                    bindings[
                        str(predicate["error_action"]["binds_success_result"])
                    ] = value
            verification = any(
                independent_truth_verification(
                    candidate, record, frozen, bindings
                )
                for frozen in predicate.get("verification_actions", [])
            )
            recovery = execution_ok and any(
                independent_action_matches(candidate, frozen, {}, bindings)
                for frozen in predicate.get("recovery_actions", [])
            )
            completion = execution_ok and any(
                independent_action_matches(candidate, frozen, {}, bindings)
                for frozen in predicate.get("completion_actions", [])
            )
            if verification or recovery:
                debt = False
            if error_flag:
                debt = True
            recovery_reached = bool(recovery_reached or recovery)
            goal_completed = bool(goal_completed or completion)
            error_flags.append(error_flag)
            verification_flags.append(verification)
            recovery_flags.append(recovery)
            completion_flags.append(completion)
        comparisons = {
            "commitment_debt_before": debt_before,
            "error_consistent_action": any(error_flags),
            "successful_truth_verification": any(verification_flags),
            "successful_recovery_certificate": any(recovery_flags),
            "successful_goal_completion": any(completion_flags),
            "recovery_reached": recovery_reached,
            "goal_completed": goal_completed,
            "commitment_debt": debt,
        }
        for key, value in comparisons.items():
            if decision.get(key) != value:
                failures.append(prefix + f":recomputed_{key}")
        projection = decision.get("environment_projection") or {}
        if bool(projection.get("debt")) != bool(decision.get("environment_debt")):
            failures.append(prefix + ":environment_projection")
        if decision.get("dynamic_bindings") != bindings:
            failures.append(prefix + ":dynamic_bindings")

    correction = unit.get("correction") or {}
    if correction.get("decision_boundary") != int(expected["distance"]):
        failures.append(f"{unit_id}:correction_boundary")
    pre_boundary = unit.get("pre_boundary_artifact") or {}
    if not all(
        isinstance(pre_boundary.get(key), str)
        and len(pre_boundary[key]) == 64
        for key in (
            "artifact_sha256",
            "messages_sha256",
            "context_snapshot_sha256",
            "decision_prefix_sha256",
            "bindings_sha256",
        )
    ):
        failures.append(f"{unit_id}:pre_boundary_artifact")

    metrics = unit.get("metrics") or {}
    if "normalized_q_auc" in metrics:
        failures.append(f"{unit_id}:forbidden_composite_auc")
    if decisions:
        recomputed = {
            "policy_commitment_auc": mean(
                float(item["commitment_debt"]) for item in decisions
            ),
            "environment_debt_auc": mean(
                float(item["environment_debt"]) for item in decisions
            ),
            "commitment_adoption_alpha": float(
                decisions[0]["commitment_debt"]
            ),
            "error_action_count": float(
                sum(item["error_consistent_action"] for item in decisions)
            ),
            "successful_truth_verification_count": float(
                sum(item["successful_truth_verification"] for item in decisions)
            ),
            "successful_recovery_certificate_count": float(
                sum(
                    item["successful_recovery_certificate"]
                    for item in decisions
                )
            ),
            "successful_goal_completion_count": float(
                sum(item["successful_goal_completion"] for item in decisions)
            ),
            "recovery_certificate_coverage": float(
                any(item["successful_recovery_certificate"] for item in decisions)
            ),
            "goal_completion_coverage": float(
                any(item["successful_goal_completion"] for item in decisions)
            ),
            "commitment_residual": float(decisions[-1]["commitment_debt"]),
            "environment_residual": float(decisions[-1]["environment_debt"]),
            "syntax_validity": mean(
                float(item["syntax_valid"]) for item in decisions
            ),
            "first_decision_native_tool": float(
                decisions[0]["output_class"] == "native-tool"
            ),
            "terminal_before_goal_completion_count": float(
                sum(item["terminal_before_goal_completion"] for item in decisions)
            ),
            "tool_call_exception_count": float(
                sum(
                    record.get("exception") is not None
                    for item in decisions
                    for record in item.get("execution") or []
                )
            ),
            "tool_call_count": float(
                sum(len(item.get("execution") or []) for item in decisions)
            ),
        }
        for key, value in recomputed.items():
            if not math.isclose(
                float(metrics.get(key, math.nan)), value, abs_tol=1e-12
            ):
                failures.append(f"{unit_id}:metric_{key}")
        classes = dict(
            sorted(Counter(item["output_class"] for item in decisions).items())
        )
        if metrics.get("output_class_counts") != classes:
            failures.append(f"{unit_id}:output_class_counts")

    expected_signature = independently_rebuild_scientific_signature(
        unit, episode, bindings
    )
    reported_signature = unit.get("scientific_signature") or {}
    if reported_signature.get("payload") != expected_signature:
        failures.append(f"{unit_id}:scientific_signature_payload")
    if reported_signature.get("sha256") != spec.canonical_sha256(
        expected_signature
    ):
        failures.append(f"{unit_id}:scientific_signature_hash")
    ending_snapshot = unit.get("ending_snapshot")
    if not isinstance(ending_snapshot, dict) or unit.get(
        "ending_snapshot_sha256"
    ) != spec.canonical_sha256(ending_snapshot):
        failures.append(f"{unit_id}:ending_snapshot_hash")
    return failures


def load_and_verify_trajectories(
    runs_root: Path, assets: Path
) -> tuple[
    dict[tuple[str, str, str, int, int], dict[str, Any]],
    dict[str, Any],
]:
    expected_rows = load_jsonl(assets / "trajectory-units.jsonl")
    expected_by_id = {row["unit_id"]: row for row in expected_rows}
    if len(expected_rows) != 120 or len(expected_by_id) != 120:
        raise RuntimeError("v11 trajectory-units 必须含 120 个唯一逻辑单元")
    episodes = {
        row["episode_id"]: row for row in load_jsonl(assets / "episodes.jsonl")
    }
    predicates = {
        row["episode_id"]: row
        for row in load_jsonl(assets / "predicates.jsonl")
    }
    expected_units = spec.expected_precision_counts()
    expected_requests = spec.expected_unique_request_counts()
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
                raise RuntimeError(f"正式 v11 轨迹产物缺失或为空：{path}")
            artifacts.append({"path": str(path), "sha256": sha256_file(path)})
        combined = load_json(paths["combined"])
        server = load_json(paths["server"])
        driver = load_json(paths["driver"])
        results = load_jsonl(paths["results"])
        requests = load_jsonl(paths["requests"])
        summaries[precision] = {
            "combined": combined,
            "server": server,
            "driver": driver,
        }
        if combined.get("status") != "succeeded" or not all(
            (combined.get("checks") or {}).values()
        ):
            failures.append(f"{precision}:combined_summary")
        if (
            server.get("status") != "succeeded"
            or server.get("protocol_version") != spec.PROTOCOL_VERSION
        ):
            failures.append(f"{precision}:server_summary")
        if (
            server.get("precision") != precision
            or server.get("failed_request_count") != 0
        ):
            failures.append(f"{precision}:server_identity_or_failure")
        if (
            driver.get("status") != "succeeded"
            or driver.get("protocol_version") != spec.PROTOCOL_VERSION
        ):
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
            if (
                not artifact_path.is_file()
                or sha256_file(artifact_path) != result.get("artifact_sha256")
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
            if (unit.get("scientific_signature") or {}).get("sha256") != result.get(
                "scientific_signature_sha256"
            ):
                failures.append(f"{uid}:result_scientific_signature")
            units[unit_key(expected)] = unit
    if observed_ids != set(expected_by_id):
        failures.append("global:unit_set")
    if len(request_ids) != sum(expected_requests.values()):
        failures.append("global:request_identity_set")
    return units, {
        "passed": not failures,
        "failures": failures,
        "observed_logical_units": len(observed_ids),
        "expected_logical_units": len(expected_by_id),
        "unique_model_requests": len(request_ids),
        "expected_unique_model_requests": sum(expected_requests.values()),
        "summaries": summaries,
        "artifacts": artifacts,
    }


def verify_cross_condition_controls(
    units: dict[tuple[str, str, str, int, int], dict[str, Any]]
) -> dict[str, Any]:
    failures: list[str] = []
    episode_ids = sorted(
        {key[1] for key in units if key[0] == "P00" and key[4] == 1}
    )
    for episode_id in episode_ids:
        for history in ("N", "C_text"):
            reference = base_unit(units, "P00", episode_id, history, 3)
            for precision in ("P10", "P01", "P11"):
                candidate = base_unit(units, precision, episode_id, history, 3)
                if (
                    candidate["decisions"][0]["input_ids_sha256"]
                    != reference["decisions"][0]["input_ids_sha256"]
                ):
                    failures.append(
                        f"{episode_id}:{history}:{precision}:first_input_hash"
                    )
                if candidate["tool_schema_sha256"] != reference[
                    "tool_schema_sha256"
                ]:
                    failures.append(
                        f"{episode_id}:{history}:{precision}:tool_schema_hash"
                    )
        for distance in (1, 3):
            branches = [
                base_unit(units, "P00", episode_id, history, distance)
                for history in ("E", "S", "C_text", "C_align")
            ]
            hashes = {
                unit["pre_boundary_artifact"]["artifact_sha256"]
                for unit in branches
            }
            if len(hashes) != 1:
                failures.append(f"{episode_id}:d{distance}:fork_artifact")
            prefixes = {
                spec.canonical_sha256(
                    [
                        {
                            "request_id": row["request_id"],
                            "input_ids_sha256": row["input_ids_sha256"],
                            "decision_signature": row["decision_signature"],
                        }
                        for row in unit["decisions"][:distance]
                    ]
                )
                for unit in branches
            }
            if len(prefixes) != 1:
                failures.append(f"{episode_id}:d{distance}:fork_decisions")
            corrected = base_unit(
                units, "P00", episode_id, "C_text", distance
            )
            aligned = base_unit(
                units, "P00", episode_id, "C_align", distance
            )
            if corrected["correction"]["visible_message_sha256"] != aligned[
                "correction"
            ]["visible_message_sha256"]:
                failures.append(f"{episode_id}:d{distance}:visible_message")
            patch = aligned["correction"].get("patch") or {}
            if patch.get("operation") != "none" and patch.get(
                "after_sha256"
            ) != patch.get("baseline_sha256"):
                failures.append(f"{episode_id}:d{distance}:patch_not_baseline")
    return {
        "episode_ids": episode_ids,
        "failure_details": failures,
        "shared_boundary_fork_identity": not any(
            "fork_" in item for item in failures
        ),
        "c_text_c_align_visible_identical": not any(
            "visible_message" in item for item in failures
        ),
        "patch_restores_error_descendant_baseline": not any(
            "patch_not_baseline" in item for item in failures
        ),
        "passed": len(episode_ids) == 6 and not failures,
    }


def window_mean(unit: dict[str, Any], phase: str, field: str) -> float:
    selected = [
        float(row[field])
        for row in unit["decisions"]
        if row["phase"] == phase
    ]
    return mean(selected)


def construct_metrics(
    units: dict[tuple[str, str, str, int, int], dict[str, Any]],
    episode_ids: list[str],
) -> dict[str, Any]:
    induction: dict[str, float] = {}
    correction: dict[str, float] = {}
    raw_error: dict[str, bool] = {}
    recovery: dict[str, bool] = {}
    separation: dict[str, bool] = {}
    details: dict[str, Any] = {}
    families: dict[str, str] = {}
    for episode_id in episode_ids:
        i_values = []
        k_values = []
        raw_by_distance = []
        recovery_by_distance = []
        separate_by_distance = []
        per_distance = {}
        for distance in (1, 3):
            n = base_unit(units, "P00", episode_id, "N", distance)
            e = base_unit(units, "P00", episode_id, "E", distance)
            s = base_unit(units, "P00", episode_id, "S", distance)
            c = base_unit(units, "P00", episode_id, "C_text", distance)
            i_value = window_mean(e, "pre-correction", "commitment_debt") - window_mean(
                n, "pre-correction", "commitment_debt"
            )
            k_value = window_mean(s, "post-correction", "commitment_debt") - window_mean(
                c, "post-correction", "commitment_debt"
            )
            raw_value = any(
                row["phase"] == "pre-correction"
                and row["error_consistent_action"]
                for row in e["decisions"]
            )
            recovery_value = any(
                row["phase"] == "post-correction"
                and row["successful_recovery_certificate"]
                for row in c["decisions"]
            )
            separate_value = any(
                row["commitment_debt"] != row["environment_debt"]
                for unit in (e, s, c)
                for row in unit["decisions"]
            )
            i_values.append(i_value)
            k_values.append(k_value)
            raw_by_distance.append(raw_value)
            recovery_by_distance.append(recovery_value)
            separate_by_distance.append(separate_value)
            per_distance[str(distance)] = {
                "I_policy": i_value,
                "kappa_policy_3": k_value,
                "raw_error_action": raw_value,
                "c_text_recovery_certificate": recovery_value,
                "policy_environment_separation": separate_value,
            }
        induction[episode_id] = mean(i_values)
        correction[episode_id] = mean(k_values)
        raw_error[episode_id] = any(raw_by_distance)
        recovery[episode_id] = any(recovery_by_distance)
        separation[episode_id] = any(separate_by_distance)
        details[episode_id] = per_distance
        families[episode_id] = base_unit(
            units, "P00", episode_id, "N", 1
        )["unit"]["family"]

    induction_mean, induction_families = family_equal_mean(
        (families[key], value) for key, value in induction.items()
    )
    correction_mean, correction_families = family_equal_mean(
        (families[key], value) for key, value in correction.items()
    )
    family_names = sorted(set(families.values()))
    raw_by_family = {
        family: any(
            raw_error[key] for key in episode_ids if families[key] == family
        )
        for family in family_names
    }
    recovery_by_family = {
        family: any(
            recovery[key] for key in episode_ids if families[key] == family
        )
        for family in family_names
    }
    induction_positive = sum(value > 0 for value in induction.values())
    correction_positive = sum(value > 0 for value in correction.values())
    raw_positive = sum(raw_error.values())
    recovery_positive = sum(recovery.values())
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
    raw_passed = raw_positive >= 4 and all(raw_by_family.values())
    recovery_passed = (
        recovery_positive >= 4 and all(recovery_by_family.values())
    )
    separation_passed = any(separation.values())
    return {
        "I_policy_definition": (
            "episode内d=1/3等权的P00 pre-correction "
            "mean(B_E)-mean(B_N)，再按family等权"
        ),
        "kappa_policy_3_definition": (
            "episode内d=1/3等权的P00三个post-correction "
            "mean(B_S)-mean(B_C_text)，再按family等权"
        ),
        "recovery_coverage_definition": (
            "C_text在任一冻结distance的post-correction窗口至少出现一次成功G"
        ),
        "episode_I_policy": induction,
        "episode_kappa_policy_3": correction,
        "distance_detail": details,
        "family_I_policy": induction_families,
        "family_kappa_policy_3": correction_families,
        "family_equal_I_policy": induction_mean,
        "family_equal_kappa_policy_3": correction_mean,
        "positive_I_policy_episodes": induction_positive,
        "positive_kappa_policy_episodes": correction_positive,
        "raw_error_action_by_episode": raw_error,
        "raw_error_action_by_family": raw_by_family,
        "raw_error_action_positive_episodes": raw_positive,
        "recovery_certificate_by_episode": recovery,
        "recovery_certificate_by_family": recovery_by_family,
        "recovery_certificate_positive_episodes": recovery_positive,
        "policy_environment_state_separation_by_episode": separation,
        "policy_environment_state_separation_passed": separation_passed,
        "induction_gate_passed": induction_passed,
        "correction_gate_passed": correction_passed,
        "raw_action_gate_passed": raw_passed,
        "recovery_certificate_gate_passed": recovery_passed,
        "passed": (
            induction_passed
            and correction_passed
            and raw_passed
            and recovery_passed
            and separation_passed
        ),
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
                science = [
                    row["scientific_signature"]["sha256"] for row in group
                ]
                boundary = [
                    row["pre_boundary_artifact"]["artifact_sha256"]
                    for row in group
                ]
                policy_auc = [
                    float(row["metrics"]["policy_commitment_auc"])
                    for row in group
                ]
                official = [
                    float(row["evaluation"]["similarity"]) for row in group
                ]
                cell = {
                    "scientific_signatures": science,
                    "scientific_signature_exact_agreement": len(set(science)) == 1,
                    "pre_boundary_artifacts": boundary,
                    "pre_boundary_exact_agreement": len(set(boundary)) == 1,
                    "policy_commitment_auc": policy_auc,
                    "policy_auc_range": max(policy_auc) - min(policy_auc),
                    "official_similarity": official,
                    "official_similarity_range_descriptive_only": (
                        max(official) - min(official)
                    ),
                }
                cells[name] = cell
                if not cell["scientific_signature_exact_agreement"]:
                    failures.append(name + ":scientific_signature")
                if not cell["pre_boundary_exact_agreement"]:
                    failures.append(name + ":pre_boundary")
                if cell["policy_auc_range"] > 0.02 + 1e-12:
                    failures.append(name + ":policy_auc_range")

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
            family = units[("P00", episode_id, "N", 3, repeat)]["unit"][
                "family"
            ]
            episode_values.append((family, delta))
        repeat_contrasts[str(repeat)] = family_equal_mean(episode_values)[0]
    contrast_range = max(repeat_contrasts.values()) - min(
        repeat_contrasts.values()
    )
    if contrast_range > 0.01 + 1e-12:
        failures.append("development_subset_contrast_range")
    return {
        "cells": cells,
        "cell_count": len(cells),
        "repeat_contrasts": repeat_contrasts,
        "development_subset_contrast_range": contrast_range,
        "continuous_official_similarity_is_not_an_exact_identity_gate": True,
        "post_completion_prose_excluded_but_tool_actions_retained": True,
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
    threshold = float(
        frozen.get("required_maximum_basic_step_less_than", 0.01)
    )
    return {
        "frozen": frozen,
        "computed_maximum_basic_step": computed,
        "matches_frozen_value": math.isclose(
            computed,
            float(frozen.get("maximum_basic_step", math.nan)),
            abs_tol=1e-12,
        ),
        "passed": (
            denominator == 176
            and computed < threshold
            and math.isclose(
                computed,
                float(frozen.get("maximum_basic_step", math.nan)),
                abs_tol=1e-12,
            )
        ),
    }


def clean_metrics(
    units: dict[tuple[str, str, str, int, int], dict[str, Any]],
    episode_ids: list[str],
) -> dict[str, Any]:
    # v10 clean 门只读取 N、语法、首动作与 official similarity，语义未改变。
    return previous.clean_metrics(units, episode_ids)


def resource_projection(
    trajectory: dict[str, Any], runs_root: Path
) -> dict[str, Any]:
    expected_units = spec.expected_precision_counts()
    expected_requests = spec.expected_unique_request_counts()
    summaries = trajectory["summaries"]
    seconds_per_trajectory = {
        precision: float(
            summaries[precision]["combined"]["gpu_resident_seconds"]
        )
        / expected_units[precision]
        for precision in spec.TREATMENT_PRECISIONS
    }
    seconds_per_request = {
        precision: float(
            summaries[precision]["combined"]["gpu_resident_seconds"]
        )
        / expected_requests[precision]
        for precision in spec.TREATMENT_PRECISIONS
    }
    trajectory_seconds = sum(
        float(summaries[p]["combined"]["gpu_resident_seconds"])
        for p in spec.TREATMENT_PRECISIONS
    )
    qualification_seconds = sum(
        float(
            load_json(
                runs_root / f"QHIST-E0-v11-qual-{precision}-r1" / "summary.json"
            )["gpu_resident_seconds"]
        )
        for precision in ("P00", "K16-shadow", "P01", "P10", "P11")
    )
    e0_hours = (trajectory_seconds + qualification_seconds) / 3600.0
    e1_requests_per_precision = 22 * 38
    projections = {
        "E1": sum(
            seconds_per_request[p] * e1_requests_per_precision
            for p in spec.TREATMENT_PRECISIONS
        )
        / 3600.0,
        "E2": max(seconds_per_request.values()) * 396 / 3600.0,
        "E3": max(seconds_per_trajectory.values()) * 96 / 3600.0,
        "E4": max(seconds_per_trajectory.values()) * 256 / 3600.0,
    }
    stage_checks = {
        stage: value <= STAGE_CAPS[stage] for stage, value in projections.items()
    }
    total = e0_hours + sum(projections.values())
    return {
        "e0_actual_gpu_hours": e0_hours,
        "e0_cap_gpu_hours": E0_STAGE_CAP_HOURS,
        "gpu_seconds_per_logical_trajectory": seconds_per_trajectory,
        "gpu_seconds_per_unique_request": seconds_per_request,
        "e1_unique_request_projection": 4 * e1_requests_per_precision,
        "projected_gpu_hours_if_E4b_deployable": projections,
        "stage_caps_gpu_hours": STAGE_CAPS,
        "stage_cap_checks": stage_checks,
        "projected_total_gpu_hours_if_E4b_deployable": total,
        "control_plane_total_cap_gpu_hours": 80.0,
        "passed": (
            e0_hours <= E0_STAGE_CAP_HOURS
            and all(stage_checks.values())
            and total <= 80.0
        ),
    }


def audit(
    runs_root: Path,
    assets: Path,
    rendered: Path,
    qualification_audit: Path,
    toolsandbox_gate: Path,
    driver_gate: Path,
    id_gate: Path,
) -> dict[str, Any]:
    qualification = load_json(qualification_audit)
    toolsandbox = load_json(toolsandbox_gate)
    driver = load_json(driver_gate)
    deterministic_id = load_json(id_gate)
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
        and deterministic_id.get("passed")
        and controls["passed"]
        and controls["shared_boundary_fork_identity"]
        and controls["c_text_c_align_visible_identical"]
        and controls["patch_restores_error_descendant_baseline"]
    )
    implementation = bool(
        qualification.get("passed")
        and qualification.get("protocol_version") == spec.PROTOCOL_VERSION
        and qualification.get("qualification_units") == 30
        and toolsandbox.get("protocol_version") == spec.PROTOCOL_VERSION
        and driver.get("protocol_version") == spec.PROTOCOL_VERSION
        and deterministic_id.get("protocol_version") == spec.PROTOCOL_VERSION
        and rendered_manifest.get("protocol_version") == spec.PROTOCOL_VERSION
        and rendered_manifest.get("all_checks_pass")
        and trajectory["passed"]
        and programmatic
    )
    gates = {
        "implementation": implementation,
        "programmatic_truth_oracle_fork_id_and_rollback": programmatic,
        "clean_observability": clean["passed"],
        "observable_error_induction": construct["induction_gate_passed"],
        "raw_error_action_dynamic_range": construct["raw_action_gate_passed"],
        "three_boundary_policy_correction": construct[
            "correction_gate_passed"
        ],
        "successful_recovery_certificate_dynamic_range": construct[
            "recovery_certificate_gate_passed"
        ],
        "policy_environment_state_separation": construct[
            "policy_environment_state_separation_passed"
        ],
        "technical_scientific_reproducibility": reproducibility["passed"],
        "finite_suite_resolution": resolution["passed"],
        "throughput_and_budget": resources["passed"],
    }
    passed = all(gates.values())
    return {
        "schema_version": 1,
        "protocol_id": spec.PROTOCOL_ID,
        "protocol_version": spec.PROTOCOL_VERSION,
        "analysis_scope": (
            "E0 development construct/implementation only; not a P1 test and "
            "never merged with E1"
        ),
        "trajectory_integrity": trajectory,
        "cross_condition_controls": controls,
        "construct": construct,
        "clean_observability": clean,
        "technical_reproducibility": reproducibility,
        "finite_suite_resolution": resolution,
        "resources": resources,
        "gates": {
            key: "pass" if value else "fail" for key, value in gates.items()
        },
        "decision": {
            "enter_e1": passed,
            "action": (
                "freeze-and-enter-E1"
                if passed
                else "stop-and-return-to-theory-or-protocol"
            ),
            "failed_noncompensatory_gates": [
                key for key, value in gates.items() if not value
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
    parser.add_argument("--id-gate", type=Path, required=True)
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
        args.id_gate,
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(result, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result["decision"]["enter_e1"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
