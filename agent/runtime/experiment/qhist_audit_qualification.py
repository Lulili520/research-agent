#!/usr/bin/env python3
"""审计 Q-HIST E0 五种精度条件的 30 个资格单元。"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any


PRECISIONS = ("P00", "K16-shadow", "P01", "P10", "P11")
PROMPTS = ("add", "lookup")


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def load_jsonl(path: Path) -> list[dict[str, Any]]:
    return [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def k4_evidence_is_real(evidence: dict[str, Any]) -> bool:
    layer = evidence.get("layer0", {})
    for key in ("_quantized_keys", "_quantized_values"):
        quantized = layer.get(key, {})
        payload = quantized.get("payload") or {}
        meta = quantized.get("meta") or {}
        if payload.get("dtype") != "torch.uint8":
            return False
        if str(meta.get("nbits")) != "4":
            return False
        if str(meta.get("axis")) != "1":
            return False
        if str(meta.get("group_size")) != "64":
            return False
    return (
        layer.get("nbits") == 4
        and layer.get("axis_key") == 1
        and layer.get("axis_value") == 1
        and layer.get("q_group_size") == 64
        and layer.get("residual_length") == 1
    )


def audit(
    root: Path,
    run_prefix: str = "QHIST-E0-v8-qual",
    protocol_version: int = 8,
) -> dict[str, Any]:
    summaries: dict[str, dict[str, Any]] = {}
    manifests: dict[str, dict[str, Any]] = {}
    results: dict[str, list[dict[str, Any]]] = {}
    artifacts: list[dict[str, str]] = []
    for precision in PRECISIONS:
        run_dir = root / f"{run_prefix}-{precision}-r1"
        summary_path = run_dir / "summary.json"
        manifest_path = run_dir / "weight-manifest.json"
        results_path = run_dir / "qualification-results.jsonl"
        for path in (summary_path, manifest_path, results_path):
            if not path.is_file() or path.stat().st_size == 0:
                raise RuntimeError(f"资格产物缺失或为空：{path}")
            artifacts.append(
                {"path": str(path), "sha256": sha256_file(path)}
            )
        summaries[precision] = load_json(summary_path)
        manifests[precision] = load_json(manifest_path)
        results[precision] = load_jsonl(results_path)

    checks: dict[str, bool] = {}
    checks["all_conditions_succeeded"] = all(
        summaries[p].get("status") == "succeeded" for p in PRECISIONS
    )
    checks["exactly_30_units"] = (
        sum(len(results[p]) for p in PRECISIONS) == 30
        and all(len(results[p]) == 6 for p in PRECISIONS)
    )
    checks["all_actions_parse_and_match_gold"] = all(
        row.get("passed") is True
        and isinstance(row.get("action"), dict)
        and row.get("action") == row.get("gold")
        for p in PRECISIONS
        for row in results[p]
    )
    checks["all_branch_rates_at_most_0_05"] = all(
        summaries[p]["prompt_records"][prompt]["nondeterministic_branch_rate"]
        <= 0.05
        for p in PRECISIONS
        for prompt in PROMPTS
    )
    checks["same_input_and_tool_hashes"] = all(
        len(
            {
                (
                    summaries[p]["prompt_records"][prompt]["input_ids_sha256"],
                    summaries[p]["prompt_records"][prompt]["tool_schema_sha256"],
                )
                for p in PRECISIONS
            }
        )
        == 1
        for prompt in PROMPTS
    )
    shadow_margin_differences = {
        prompt: abs(
            summaries["K16-shadow"]["prompt_records"][prompt][
                "gold_action_margin"
            ]
            - summaries["P00"]["prompt_records"][prompt]["gold_action_margin"]
        )
        for prompt in PROMPTS
    }
    checks["k16_shadow_margin_difference_at_most_0_01"] = all(
        value <= 0.01 for value in shadow_margin_differences.values()
    )
    p10_names = manifests["P10"].get("quantized_module_names", [])
    p11_names = manifests["P11"].get("quantized_module_names", [])
    checks["p10_p11_identical_nonzero_quantized_modules"] = (
        len(p10_names) > 0 and p10_names == p11_names
    )
    checks["w4_non_target_components_bfloat16"] = all(
        manifests[p].get("input_embedding", {}).get("dtype") == "torch.bfloat16"
        and manifests[p].get("output_embedding", {}).get("dtype")
        == "torch.bfloat16"
        and manifests[p].get("normalization_parameter_dtypes")
        == ["torch.bfloat16"]
        for p in ("P10", "P11")
    )
    checks["k4_runtime_evidence_valid"] = all(
        k4_evidence_is_real(row["cache_evidence"])
        for p in ("P01", "P11")
        for row in results[p]
    )
    checks["k16_shadow_remains_bfloat16"] = all(
        row["cache_evidence"]["layer0"]["_quantized_keys"]["payload"].get(
            "dtype"
        )
        == "torch.bfloat16"
        and row["cache_evidence"]["layer0"]["_quantized_values"][
            "payload"
        ].get("dtype")
        == "torch.bfloat16"
        for row in results["K16-shadow"]
    )
    return {
        "schema_version": 1,
        "protocol_id": "QHIST-EXP",
        "protocol_version": protocol_version,
        "qualification_units": sum(len(results[p]) for p in PRECISIONS),
        "checks": checks,
        "passed": all(checks.values()),
        "shadow_margin_absolute_differences": shadow_margin_differences,
        "w4_quantized_module_count": len(p10_names),
        "artifacts": artifacts,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--runs-root", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--run-prefix", default="QHIST-E0-v8-qual")
    parser.add_argument("--protocol-version", type=int, default=8)
    args = parser.parse_args()
    result = audit(args.runs_root, args.run_prefix, args.protocol_version)
    if args.output.exists():
        raise RuntimeError(f"审计输出已存在，禁止覆盖：{args.output}")
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(result, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
