#!/usr/bin/env python3
"""按冻结清单顺序随机化并运行 E0 的全部 ToolSandbox 轨迹。"""

from __future__ import annotations

import argparse
import hashlib
import json
import random
import subprocess
import sys
import time
from pathlib import Path
from typing import Any


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--stimuli-root", type=Path, required=True)
    parser.add_argument("--model", required=True)
    parser.add_argument("--base-url", default="http://127.0.0.1:8000/v1")
    parser.add_argument("--adapter", default="openai-tools")
    parser.add_argument("--seed", type=int, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    rows = [json.loads(line) for line in args.manifest.read_text(encoding="utf-8").splitlines() if line.strip()]
    identities = {(row["episode_id"], row["condition"]) for row in rows}
    if len(rows) != 96 or len(identities) != 96:
        raise RuntimeError(f"冻结 E0 清单必须包含 96 个唯一单元，实际为 {len(rows)}/{len(identities)}")

    rng = random.Random(args.seed)
    schedule = list(rows)
    rng.shuffle(schedule)
    args.output.mkdir(parents=True, exist_ok=True)
    if (args.output / "results.jsonl").exists():
        raise RuntimeError("输出目录已包含 results.jsonl；审计运行不得原地覆盖或追加")
    schedule_path = args.output / "schedule.jsonl"
    schedule_path.write_text(
        "".join(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n" for row in schedule),
        encoding="utf-8",
    )

    runner = Path(__file__).with_name("toolsandbox_local_run.py")
    started = time.time()
    results: list[dict[str, Any]] = []
    for order, row in enumerate(schedule, start=1):
        relative = Path(str(row["stimulus"]).replace("\\", "/"))
        memory_path = args.stimuli_root / relative
        if not memory_path.is_file():
            raise FileNotFoundError(memory_path)
        actual_sha = sha256_file(memory_path)
        if actual_sha != row["stimulus_sha256"]:
            raise RuntimeError(f"刺激哈希不匹配：{memory_path}")
        unit_name = f'{row["episode_id"]}_{row["condition"].replace("+", "p").replace("-", "m")}'
        unit_output = args.output / "units" / unit_name
        unit_output.mkdir(parents=True, exist_ok=False)
        command = [
            sys.executable,
            str(runner),
            "--scenario", str(row["scenario"]),
            "--seed", str(args.seed + order),
            "--model", args.model,
            "--base-url", args.base_url,
            "--adapter", args.adapter,
            "--memory-file", str(memory_path),
            "--output", str(unit_output),
        ]
        completed = subprocess.run(command, text=True, capture_output=True)
        (unit_output / "runner-stdout.log").write_text(completed.stdout, encoding="utf-8")
        (unit_output / "runner-stderr.log").write_text(completed.stderr, encoding="utf-8")
        summary_path = unit_output / "summary.json"
        unit_summary = json.loads(summary_path.read_text(encoding="utf-8")) if summary_path.is_file() else None
        result = {
            "order": order,
            "episode_id": row["episode_id"],
            "scenario": row["scenario"],
            "condition": row["condition"],
            "stimulus_sha256": actual_sha,
            "return_code": completed.returncode,
            "summary_status": unit_summary.get("status") if unit_summary else "missing",
            "retrieval_hit": unit_summary.get("retrieval_hit") if unit_summary else None,
            "elapsed_seconds": unit_summary.get("elapsed_seconds") if unit_summary else None,
        }
        results.append(result)
        with (args.output / "results.jsonl").open("a", encoding="utf-8") as stream:
            stream.write(json.dumps(result, ensure_ascii=False, sort_keys=True) + "\n")
            stream.flush()

    failed = [item for item in results if item["return_code"] != 0 or item["summary_status"] != "succeeded"]
    retrieval_misses = [item for item in results if item["retrieval_hit"] is not True]
    summary = {
        "schema_version": 1,
        "model": args.model,
        "adapter": args.adapter,
        "seed": args.seed,
        "manifest": str(args.manifest),
        "manifest_sha256": sha256_file(args.manifest),
        "schedule_sha256": sha256_file(schedule_path),
        "expected_units": 96,
        "completed_units": len(results),
        "succeeded_units": len(results) - len(failed),
        "failed_units": len(failed),
        "retrieval_misses": len(retrieval_misses),
        "retrieval_hit_rate": (len(results) - len(retrieval_misses)) / len(results),
        "elapsed_seconds": round(time.time() - started, 6),
        "status": "succeeded" if not failed and not retrieval_misses else "failed",
    }
    (args.output / "summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0 if summary["status"] == "succeeded" else 1


if __name__ == "__main__":
    raise SystemExit(main())
