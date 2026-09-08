#!/usr/bin/env python3
"""汇总 Q-HIST v13 的静态、reference、runner 和 ID 非补偿门。"""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
from pathlib import Path

import qhist_v13_spec as spec


def load(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--assets", type=Path, required=True)
    parser.add_argument("--rendered", type=Path, required=True)
    parser.add_argument("--toolsandbox-gate", type=Path, required=True)
    parser.add_argument("--driver-gate", type=Path, required=True)
    parser.add_argument("--id-gate", type=Path, required=True)
    parser.add_argument("--code-root", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        raise RuntimeError(f"拒绝覆盖既有 preflight：{args.output}")
    args.output.parent.mkdir(parents=True, exist_ok=True)

    asset_manifest = load(args.assets / "manifest.json")
    rendered_manifest = load(args.rendered / "manifest.json")
    toolsandbox = load(args.toolsandbox_gate)
    driver = load(args.driver_gate)
    id_gate = load(args.id_gate)
    patches = [json.loads(line) for line in (args.assets / "environment-patches.jsonl").read_text(encoding="utf-8").splitlines() if line]
    counts = spec.validate_frozen_design()
    asset_manifest_path = args.assets / "manifest.json"
    rendered_manifest_path = args.rendered / "manifest.json"
    asset_manifest_sha256 = sha256(asset_manifest_path)
    rendered_manifest_sha256 = sha256(rendered_manifest_path)
    checks = {
        "asset_protocol_v13": asset_manifest.get("protocol_version") == 13,
        "rendered_protocol_v13": rendered_manifest.get("protocol_version") == 13,
        "all_gate_protocols_v13": all(
            report.get("protocol_id") == spec.PROTOCOL_ID
            and report.get("protocol_version") == spec.PROTOCOL_VERSION
            for report in (toolsandbox, driver, id_gate)
        ),
        "six_asset_episodes": len(patches) == 6,
        "all_mutating_debts_and_patches_valid": all(
            row.get("align_restores_baseline") is True
            and (
                (row["operation"] != "none" and row.get("error_semantic_debt") is True)
                or (row["operation"] == "none" and row.get("error_semantic_debt") is False)
            )
            for row in patches
        ),
        "rendered_has_72_stimuli": rendered_manifest.get("stimulus_count") == 72,
        "rendered_checks_pass": rendered_manifest.get("all_checks_pass") is True,
        "independent_toolsandbox_gate_pass": toolsandbox.get("status") == "passed" and toolsandbox.get("all_six_episodes_pass") is True,
        "independent_gate_does_not_import_runner": toolsandbox.get("independence", {}).get("imports_target_runner") is False,
        "scripted_driver_gate_pass": (
            driver.get("status") == "passed"
            and driver.get("scripted_units") == 42
            and driver.get("scripted_decisions") == 168
            and driver.get("integration_scope", {}).get("production_runner_exercised") is True
            and driver.get("integration_scope", {}).get("independent_auditor_exercised") is True
            and driver.get("integration_scope", {}).get("uses_scripted_policies_not_target_model") is True
            and driver.get("integration_scope", {}).get("scheduled_rows_exercised") is True
            and driver.get("integration_scope", {}).get("scientific_identity_and_schedule_audited_separately") is True
            and all(
                row.get("checks", {}).get("scientific_identity_matches_spec") is True
                and row.get("checks", {}).get("execution_order_not_in_scientific_identity") is True
                and row.get("checks", {}).get("schedule_metadata_matches_scheduled_asset") is True
                for row in driver.get("results", [])
            )
        ),
        "deterministic_id_gate_pass": id_gate.get("status") == "passed",
        "frozen_counts": counts["trajectory_units_total"] == 192 and counts["unique_model_requests"] == 768 and counts["qualification_units"] == 30,
        "target_effect_direction_not_gate": load(args.assets / "split.json").get("target_effect_direction_is_gate") is False,
        "rendered_links_exact_asset_manifest": rendered_manifest.get("assets_manifest_sha256") == asset_manifest_sha256,
        "toolsandbox_gate_links_exact_inputs": (
            toolsandbox.get("asset_manifest_sha256") == asset_manifest_sha256
            and toolsandbox.get("rendered_manifest_sha256") == rendered_manifest_sha256
        ),
        "driver_gate_links_exact_inputs": (
            driver.get("artifacts", {}).get("assets_manifest_sha256") == asset_manifest_sha256
            and driver.get("artifacts", {}).get("rendered_manifest_sha256") == rendered_manifest_sha256
        ),
        "id_gate_links_exact_asset_manifest": (
            id_gate.get("artifacts", {}).get("assets_manifest_sha256") == asset_manifest_sha256
        ),
    }
    code_names = (
        "qhist_e0_spec.py",
        "qhist_v9_spec.py",
        "qhist_v10_spec.py",
        "qhist_v13_spec.py",
        "qhist_build_e0_assets.py",
        "qhist_build_e0_assets_v13.py",
        "qhist_render_stimuli.py",
        "qhist_render_stimuli_v13.py",
        "qhist_toolsandbox_gate_v13.py",
        "qhist_trajectory_batch.py",
        "qhist_trajectory_batch_v9.py",
        "qhist_trajectory_batch_v13.py",
        "qhist_driver_integration_gate_v13.py",
        "qhist_deterministic_id_gate_v13.py",
        "qhist_precision_qualification.py",
        "qhist_audit_qualification.py",
        "qhist_verify_precision_env.py",
        "qhist_server_control.py",
        "qhist_model_server.py",
        "qhist_model_server_v13.py",
        "qhist_combine_trajectory_batch.py",
        "qhist_combine_trajectory_batch_v13.py",
        "qhist_audit_e0_v13.py",
        "qhist_preflight_audit_v13.py",
        "qhist_verify_v13_lock.py",
        "run_qhist_v13_preflight.sh",
        "run_qhist_v13_qualification.sh",
        "run_qhist_v13_trajectory.sh",
        "run_qhist_v13_audit.sh",
        "test_qhist_v13_spec.py",
        "test_qhist_trajectory_batch_v13.py",
        "test_qhist_audit_e0_v13.py",
        "test_qhist_verify_v13_lock.py",
    )
    code = []
    missing = []
    for name in code_names:
        path = args.code_root / name
        if not path.is_file():
            missing.append(name)
        else:
            code.append({"path": name, "bytes": path.stat().st_size, "sha256": sha256(path)})
    checks["all_production_and_audit_code_present"] = not missing
    checks["asset_manifest_sources_match_code"] = not missing and all(
        (
            asset_manifest.get("generator_sha256") == sha256(args.code_root / "qhist_build_e0_assets_v13.py"),
            asset_manifest.get("v13_spec_sha256") == sha256(args.code_root / "qhist_v13_spec.py"),
            asset_manifest.get("base_builder_sha256") == sha256(args.code_root / "qhist_build_e0_assets.py"),
            asset_manifest.get("runtime_base_sha256") == sha256(args.code_root / "qhist_trajectory_batch.py"),
        )
    )
    checks["rendered_manifest_sources_match_code"] = not missing and all(
        (
            rendered_manifest.get("generator_sha256") == sha256(args.code_root / "qhist_render_stimuli_v13.py"),
            rendered_manifest.get("helper_sha256") == sha256(args.code_root / "qhist_render_stimuli.py"),
            rendered_manifest.get("v13_spec_sha256") == sha256(args.code_root / "qhist_v13_spec.py"),
        )
    )
    checks["driver_gate_sources_match_code"] = not missing and (
        driver.get("artifacts", {}).get("production_runner_sha256")
        == sha256(args.code_root / "qhist_trajectory_batch_v13.py")
        and driver.get("artifacts", {}).get("independent_auditor_sha256")
        == sha256(args.code_root / "qhist_audit_e0_v13.py")
        and driver.get("artifacts", {}).get("integration_gate_sha256")
        == sha256(args.code_root / "qhist_driver_integration_gate_v13.py")
    )
    checks["id_gate_source_matches_code"] = not missing and (
        id_gate.get("artifacts", {}).get("production_runner_sha256")
        == sha256(args.code_root / "qhist_trajectory_batch_v13.py")
        and id_gate.get("artifacts", {}).get("id_gate_sha256")
        == sha256(args.code_root / "qhist_deterministic_id_gate_v13.py")
    )
    checks["toolsandbox_gate_source_matches_code"] = not missing and (
        toolsandbox.get("gate_code_sha256")
        == sha256(args.code_root / "qhist_toolsandbox_gate_v13.py")
    )
    compile_result = subprocess.run(
        [
            sys.executable,
            "-m",
            "py_compile",
            *[
                str(args.code_root / name)
                for name in code_names
                if name not in missing and name.endswith(".py")
            ],
        ],
        capture_output=True,
        text=True,
    )
    checks["all_locked_python_code_compiles"] = compile_result.returncode == 0
    report = {
        "schema_version": 1,
        "protocol_id": spec.PROTOCOL_ID,
        "protocol_version": spec.PROTOCOL_VERSION,
        "status": "passed" if all(checks.values()) else "failed",
        "checks": checks,
        "counts": counts,
        "artifacts": {
            "asset_manifest": asset_manifest_sha256,
            "rendered_manifest": rendered_manifest_sha256,
            "toolsandbox_gate": sha256(args.toolsandbox_gate),
            "driver_gate": sha256(args.driver_gate),
            "id_gate": sha256(args.id_gate),
        },
        "code": code,
        "missing_code": missing,
        "compile": {
            "returncode": compile_result.returncode,
            "stdout": compile_result.stdout,
            "stderr": compile_result.stderr,
        },
        "failures": [name for name, passed in checks.items() if not passed],
    }
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"status": report["status"], "checks": checks, "missing_code": missing}, ensure_ascii=False, indent=2))
    return 0 if report["status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
