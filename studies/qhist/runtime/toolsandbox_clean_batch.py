#!/usr/bin/env python3
"""运行冻结 episode 集合的 clean-no-memory 资格门禁。"""

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


def file_sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def build_schedule(rows: list[dict[str, Any]], seed: int) -> list[dict[str, Any]]:
    episode_ids = [str(row["episode_id"]) for row in rows]
    if len(rows) != 24 or len(set(episode_ids)) != 24:
        raise RuntimeError(f"clean 资格清单必须包含 24 个唯一 episode，实际为 {len(rows)}/{len(set(episode_ids))}")
    schedule = list(rows)
    random.Random(seed).shuffle(schedule)
    return schedule


def unit_qualified(return_code: int, unit: dict[str, Any]) -> bool:
    evaluation = unit.get("evaluation") or {}
    milestone_scores = [
        float(pair[1]) for pair in evaluation.get("milestone_mapping", {}).values()
    ]
    return (
        return_code == 0
        and unit.get("status") == "succeeded"
        and evaluation.get("similarity", 0.0) >= 0.75
        and bool(milestone_scores)
        and min(milestone_scores) >= 0.5
        and evaluation.get("minefield_similarity") == 0
        and unit.get("native_tool_call_count", 0) >= 1
        and unit.get("tool_call_exception_count") == 0
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--episodes", type=Path, required=True)
    parser.add_argument("--model", required=True)
    parser.add_argument("--base-url", default="http://127.0.0.1:8000/v1")
    parser.add_argument("--adapter", default="openai-tools")
    parser.add_argument("--seed", type=int, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    rows = [json.loads(line) for line in args.episodes.read_text(encoding="utf-8").splitlines() if line.strip()]
    schedule = build_schedule(rows, args.seed)
    args.output.mkdir(parents=True, exist_ok=True)
    if (args.output / "results.jsonl").exists():
        raise RuntimeError("输出目录已包含 results.jsonl；审计运行不得覆盖或追加")
    schedule_path = args.output / "schedule.jsonl"
    schedule_path.write_text(
        "".join(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n" for row in schedule),
        encoding="utf-8",
    )

    runner = Path(__file__).with_name("toolsandbox_local_run.py")
    started = time.time()
    results: list[dict[str, Any]] = []
    for order, row in enumerate(schedule, start=1):
        episode_id = str(row["episode_id"])
        episode_seed = args.seed + int(episode_id.split("-")[-1])
        unit_output = args.output / "units" / episode_id
        unit_output.mkdir(parents=True, exist_ok=False)
        command = [
            sys.executable, str(runner),
            "--scenario", str(row["scenario"]),
            "--seed", str(episode_seed),
            "--model", args.model,
            "--base-url", args.base_url,
            "--adapter", args.adapter,
            "--output", str(unit_output),
        ]
        completed = subprocess.run(command, text=True, capture_output=True)
        (unit_output / "runner-stdout.log").write_text(completed.stdout, encoding="utf-8")
        (unit_output / "runner-stderr.log").write_text(completed.stderr, encoding="utf-8")
        summary_path = unit_output / "summary.json"
        unit = json.loads(summary_path.read_text(encoding="utf-8")) if summary_path.is_file() else {}
        evaluation = unit.get("evaluation") or {}
        milestone_scores = [
            float(pair[1]) for pair in evaluation.get("milestone_mapping", {}).values()
        ]
        passed = unit_qualified(completed.returncode, unit)
        result = {
            "order": order,
            "episode_id": episode_id,
            "scenario": row["scenario"],
            "execution_seed": episode_seed,
            "return_code": completed.returncode,
            "summary_status": unit.get("status", "missing"),
            "similarity": evaluation.get("similarity"),
            "minefield_similarity": evaluation.get("minefield_similarity"),
            "minimum_milestone_similarity": min(milestone_scores) if milestone_scores else None,
            "native_tool_call_count": unit.get("native_tool_call_count", 0),
            "tool_call_exception_count": unit.get("tool_call_exception_count"),
            "passed": passed,
        }
        results.append(result)
        with (args.output / "results.jsonl").open("a", encoding="utf-8") as stream:
            stream.write(json.dumps(result, ensure_ascii=False, sort_keys=True) + "\n")
            stream.flush()

    failures = [item for item in results if not item["passed"]]
    summary = {
        "schema_version": 1,
        "model": args.model,
        "adapter": args.adapter,
        "seed": args.seed,
        "episodes_sha256": file_sha256(args.episodes),
        "schedule_sha256": file_sha256(schedule_path),
        "expected_units": 24,
        "completed_units": len(results),
        "passed_units": len(results) - len(failures),
        "failed_units": len(failures),
        "all_qualified": not failures,
        "qualification_thresholds": {
            "minimum_total_similarity": 0.75,
            "minimum_any_milestone_similarity": 0.5,
            "minefield_similarity": 0.0,
            "minimum_native_tool_calls": 1,
            "maximum_tool_call_exceptions": 0,
        },
        "elapsed_seconds": round(time.time() - started, 6),
        "status": "succeeded" if not failures else "failed",
    }
    (args.output / "summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0 if not failures else 1


if __name__ == "__main__":
    raise SystemExit(main())
