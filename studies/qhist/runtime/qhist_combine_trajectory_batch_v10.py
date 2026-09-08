#!/usr/bin/env python3
"""合并 Q-HIST v10 模型服务和 driver 的批次摘要。"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import qhist_combine_trajectory_batch as base
import qhist_v10_spec as spec


def combine(precision: str, server_path: Path, driver_path: Path) -> dict:
    server = json.loads(server_path.read_text(encoding="utf-8"))
    driver = json.loads(driver_path.read_text(encoding="utf-8"))
    expected_units = spec.expected_precision_counts()[precision]
    expected_requests = spec.expected_request_counts()[precision]
    checks = {
        "server_succeeded": server.get("status") == "succeeded",
        "driver_succeeded": driver.get("status") == "succeeded",
        "protocol_matches": server.get("protocol_version") == spec.PROTOCOL_VERSION
        and driver.get("protocol_version") == spec.PROTOCOL_VERSION,
        "precision_matches": server.get("precision") == precision
        and driver.get("precision") == precision,
        "all_units_completed": driver.get("completed_units") == expected_units
        and driver.get("succeeded_units") == expected_units,
        "all_decisions_served": server.get("request_count") == expected_requests,
        "no_failed_model_request": server.get("failed_request_count") == 0,
    }
    return {
        "schema_version": 1,
        "protocol_id": spec.PROTOCOL_ID,
        "protocol_version": spec.PROTOCOL_VERSION,
        "precision": precision,
        "status": "succeeded" if all(checks.values()) else "failed",
        "checks": checks,
        "expected_units": expected_units,
        "expected_model_requests": expected_requests,
        "gpu_resident_seconds": server.get("gpu_resident_seconds"),
        "generation_seconds": server.get("generation_seconds"),
        "server_summary_sha256": base.sha256_file(server_path),
        "driver_summary_sha256": base.sha256_file(driver_path),
        "weight_manifest_sha256": server.get("weight_manifest_sha256"),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--precision", choices=spec.TREATMENT_PRECISIONS, required=True)
    parser.add_argument("--server", type=Path, required=True)
    parser.add_argument("--driver", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        raise RuntimeError(f"禁止覆盖批次摘要：{args.output}")
    result = combine(args.precision, args.server, args.driver)
    args.output.write_text(
        json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result["status"] == "succeeded" else 1


if __name__ == "__main__":
    raise SystemExit(main())
