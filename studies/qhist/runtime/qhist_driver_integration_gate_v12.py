#!/usr/bin/env python3
"""用结果无关的脚本策略贯通 Q-HIST v12 production runner。"""

from __future__ import annotations

import argparse
import copy
import hashlib
import json
from pathlib import Path
from typing import Any

import qhist_trajectory_batch_v12 as runner
import qhist_audit_e0_v12 as independent_audit
import qhist_v12_spec as spec


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line]


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def mock_generated(
    request_id: str,
    precision: str,
    tools: list[dict[str, Any]],
    action: dict[str, Any] | None,
    input_hash: str,
    input_count: int,
) -> dict[str, Any]:
    if action is None:
        raw = "Done.<|im_end|>"
        visible = "Done."
        parsed = []
    else:
        payload = json.dumps(action, ensure_ascii=False, separators=(",", ":"))
        raw = f"<tool_call>\n{payload}\n</tool_call><|im_end|>"
        visible = f"<tool_call>\n{payload}\n</tool_call>"
        parsed = [action]
    return {
        "request_id": request_id,
        "precision": precision,
        "model_revision": spec.MODEL_REVISION,
        "tool_schema_sha256": spec.canonical_sha256(tools),
        "input_ids_sha256": input_hash,
        "input_token_count": input_count,
        "generated_token_count": 1,
        "elapsed_seconds": 0.0,
        "raw_text": raw,
        "visible_content": visible,
        "parsed_actions": parsed,
        "cache_evidence": {"integration_mock": True},
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--assets", type=Path, required=True)
    parser.add_argument("--rendered", type=Path, required=True)
    parser.add_argument("--toolsandbox-source", type=Path, required=True)
    parser.add_argument("--toolsandbox-site-packages", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        raise RuntimeError(f"拒绝覆盖既有 gate：{args.output}")
    args.output.parent.mkdir(parents=True, exist_ok=True)

    runner.base.PROTOCOL_VERSION = spec.PROTOCOL_VERSION
    runner.base.MODEL_REVISION = spec.MODEL_REVISION
    runtime = runner.base.prepare_toolsandbox(
        args.toolsandbox_source, args.toolsandbox_site_packages
    )
    from tool_sandbox.common.tool_discovery import ToolBackend
    from tool_sandbox.scenarios import named_scenarios

    episodes = {row["episode_id"]: row for row in read_jsonl(args.assets / "episodes.jsonl")}
    predicates = {row["episode_id"]: row for row in read_jsonl(args.assets / "predicates.jsonl")}
    patches = {row["episode_id"]: row for row in read_jsonl(args.assets / "environment-patches.jsonl")}
    references = {row["episode_id"]: row for row in read_jsonl(args.assets / "reference-policies.jsonl")}
    stimuli = {
        (row["episode_id"], row["module"], row["condition"], int(row["gap"])): row
        for row in read_jsonl(args.rendered / "stimuli.jsonl")
    }
    units = read_jsonl(args.assets / "trajectory-units.jsonl")
    unit_index = {
        (row["episode_id"], row["module"], row["condition"], int(row["gap"])): row
        for row in units
        if row["precision"] == "P00" and int(row["repeat"]) == 1
    }
    scenarios = named_scenarios(preferred_tool_backend=ToolBackend.DEFAULT)
    baselines = {
        episode_id: json.loads((args.assets / episode["snapshot"]).read_text(encoding="utf-8"))
        for episode_id, episode in episodes.items()
    }
    condition_policy = {
        ("A", "A_N"): "clean",
        ("A", "A_E"): "stubborn",
        ("R", "R0"): "stubborn",
        ("R", "R_audit"): "verify",
        ("R", "R_fact"): "follow",
        ("E", "E_text"): "follow",
        ("E", "E_align"): "restore",
    }
    failures: list[str] = []
    results: list[dict[str, Any]] = []

    for episode_id, episode in episodes.items():
        for (module, condition), policy_name in condition_policy.items():
            gap = 3
            row = copy.deepcopy(unit_index[(episode_id, module, condition, gap)])
            actions = copy.deepcopy(references[episode_id]["policies"][policy_name])
            stimulus = stimuli[(episode_id, module, condition, gap)]
            call_index = {"value": 0}

            def fake_generate(endpoint, request_id, precision, messages, tools, max_new_tokens):
                call_index["value"] += 1
                index = call_index["value"] - 1
                action = actions[index] if index < len(actions) else None
                input_hash = (
                    stimulus["input_ids_sha256"]
                    if index == 0
                    else hashlib.sha256(f"{row['unit_id']}|{index + 1}".encode()).hexdigest()
                )
                return mock_generated(
                    request_id,
                    precision,
                    tools,
                    action,
                    input_hash,
                    stimulus["input_token_count"] if index == 0 else 1,
                )

            original_generate = runner.base.generate_decision
            runner.base.generate_decision = fake_generate
            try:
                result = runner.run_unit(
                    row,
                    episode,
                    predicates[episode_id],
                    patches[episode_id],
                    stimulus,
                    args.assets,
                    scenarios[episode["scenario"]],
                    "mock://integration",
                    64,
                )
            finally:
                runner.base.generate_decision = original_generate
            checks = {
                "four_decisions": len(result["decisions"]) == 4 and call_index["value"] == 4,
                "first_input_hash": result["decisions"][0]["input_ids_sha256"] == stimulus["input_ids_sha256"],
                "checkpoint_has_no_target_decision": result["checkpoint"]["target_model_decisions_before_checkpoint"] == 0,
                "runner_signature_present": len(result["scientific_signature"]["sha256"]) == 64,
            }
            audited, audit_failures = independent_audit.verify_unit(
                result,
                row,
                episode,
                predicates[episode_id],
                patches[episode_id],
                stimulus,
                baselines[episode_id],
                scenarios[episode["scenario"]],
            )
            checks["independent_auditor_recomputes_unit"] = (
                not audit_failures
                and bool(audited)
                and audited.get("scientific_signature_sha256")
                == result["scientific_signature"]["sha256"]
            )
            if condition == "A_N":
                checks["expected_construct"] = (
                    result["checkpoint"]["B"] is False
                    and result["metrics"]["B_residual"] == 0.0
                    and result["metrics"]["T"] == 1.0
                )
            elif condition in {"A_E", "R0"}:
                checks["expected_construct"] = (
                    result["metrics"]["F_count"] >= 1
                    and result["metrics"]["B_residual"] == 1.0
                )
            elif condition == "R_audit":
                checks["expected_construct"] = (
                    result["metrics"]["V_count"] >= 1
                    and result["metrics"]["G_count"] >= 1
                    and result["metrics"]["B_residual"] == 0.0
                    and result["metrics"]["T"] == 1.0
                )
            elif condition == "R_fact":
                checks["expected_construct"] = (
                    result["metrics"]["V_count"] == 0
                    and result["metrics"]["G_count"] >= 1
                    and result["metrics"]["B_residual"] == 0.0
                    and result["metrics"]["T"] == 1.0
                )
            elif condition == "E_text":
                expected_e = episode["mutability"] == "mutating"
                checks["expected_construct"] = (
                    bool(result["checkpoint"]["E"]) == expected_e
                    and bool(result["metrics"]["E_residual"]) == expected_e
                    and result["metrics"]["T"] == 1.0
                )
            elif condition == "E_align":
                checks["expected_construct"] = (
                    result["checkpoint"]["E"] is False
                    and result["metrics"]["E_residual"] == 0.0
                    and result["metrics"]["T"] == 1.0
                )
            if not all(checks.values()):
                failures.extend(
                    f"{episode_id}:{module}:{condition}:{name}"
                    for name, passed in checks.items() if not passed
                )
            results.append(
                {
                    "episode_id": episode_id,
                    "module": module,
                    "condition": condition,
                    "checks": checks,
                    "metrics": result["metrics"],
                    "route": result["route"],
                    "checkpoint": {
                        "messages_sha256": result["checkpoint"]["messages_sha256"],
                        "semantic_projection_sha256": result["checkpoint"]["semantic_projection"]["sha256"],
                        "B": result["checkpoint"]["B"],
                        "E": result["checkpoint"]["E"],
                    },
                    "scientific_signature_sha256": result["scientific_signature"]["sha256"],
                    "independent_audit_failures": audit_failures,
                }
            )

    report = {
        "schema_version": 1,
        "protocol_id": spec.PROTOCOL_ID,
        "protocol_version": spec.PROTOCOL_VERSION,
        "status": "passed" if not failures else "failed",
        "runtime": runtime,
        "scripted_units": len(results),
        "scripted_decisions": len(results) * 4,
        "conditions_per_episode": len(condition_policy),
        "integration_scope": {
            "production_runner_exercised": True,
            "independent_auditor_exercised": True,
            "uses_scripted_policies_not_target_model": True,
        },
        "artifacts": {
            "assets_manifest_sha256": sha256_file(args.assets / "manifest.json"),
            "rendered_manifest_sha256": sha256_file(args.rendered / "manifest.json"),
            "integration_gate_sha256": sha256_file(Path(__file__)),
            "production_runner_sha256": sha256_file(Path(runner.__file__)),
            "independent_auditor_sha256": sha256_file(Path(independent_audit.__file__)),
        },
        "results": results,
        "failures": failures,
    }
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2, default=str) + "\n", encoding="utf-8")
    print(json.dumps({"status": report["status"], "units": len(results), "failures": failures}, ensure_ascii=False, indent=2))
    return 0 if report["status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
