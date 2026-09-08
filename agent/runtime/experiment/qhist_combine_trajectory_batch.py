#!/usr/bin/env python3
"""合并 Q-HIST 模型服务与 ToolSandbox driver 的批次审计摘要。"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--precision", required=True)
    parser.add_argument("--server", type=Path, required=True)
    parser.add_argument("--driver", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    server = json.loads(args.server.read_text(encoding="utf-8"))
    driver = json.loads(args.driver.read_text(encoding="utf-8"))
    expected_units = 80 if args.precision == "P00" else 8
    expected_requests = 400 if args.precision == "P00" else 48
    checks = {
        "server_succeeded": server.get("status") == "succeeded",
        "driver_succeeded": driver.get("status") == "succeeded",
        "precision_matches": server.get("precision") == args.precision
        and driver.get("precision") == args.precision,
        "all_units_completed": driver.get("completed_units") == expected_units
        and driver.get("succeeded_units") == expected_units,
        "all_decisions_served": server.get("request_count") == expected_requests,
        "no_failed_model_request": server.get("failed_request_count") == 0,
    }
    result = {
        "schema_version": 1,
        "protocol_id": "QHIST-EXP",
        "protocol_version": 8,
        "precision": args.precision,
        "status": "succeeded" if all(checks.values()) else "failed",
        "checks": checks,
        "expected_units": expected_units,
        "expected_model_requests": expected_requests,
        "gpu_resident_seconds": server.get("gpu_resident_seconds"),
        "generation_seconds": server.get("generation_seconds"),
        "server_summary_sha256": sha256_file(args.server),
        "driver_summary_sha256": sha256_file(args.driver),
        "weight_manifest_sha256": server.get("weight_manifest_sha256"),
    }
    if args.output.exists():
        raise RuntimeError(f"禁止覆盖批次摘要：{args.output}")
    args.output.write_text(
        json.dumps(result, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result["status"] == "succeeded" else 1


if __name__ == "__main__":
    raise SystemExit(main())
