#!/usr/bin/env python3
"""对 E0 episode 清单逐项验证冻结快照复制与未执行判分回放。"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from toolsandbox_smoke import run_smoke


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--episodes", type=Path, required=True)
    parser.add_argument("--seed", type=int, default=20260902)
    parser.add_argument("--threshold", type=float, default=0.98)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if not 0 <= args.threshold <= 1:
        raise ValueError("threshold 必须在 [0, 1] 内")

    episodes = [
        json.loads(line)
        for line in args.episodes.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    if not episodes:
        raise ValueError("episode 清单为空")
    episode_ids = [row["episode_id"] for row in episodes]
    if len(episode_ids) != len(set(episode_ids)):
        raise ValueError("episode_id 必须唯一")

    results = []
    for index, episode in enumerate(episodes):
        check = run_smoke(episode["scenario"], args.seed + index)
        results.append(
            {
                "episode_id": episode["episode_id"],
                "scenario": episode["scenario"],
                "seed": args.seed + index,
                "snapshot_sha256": check["snapshot_sha256"],
                "untouched_evaluation_sha256": check[
                    "untouched_evaluation_sha256"
                ],
                "checks": check["checks"],
                "passed": check["passed"],
            }
        )
    passed_count = sum(row["passed"] for row in results)
    replay_rate = passed_count / len(results)
    report = {
        "schema_version": 1,
        "profile": "toolsandbox-frozen-snapshot-replay-audit",
        "episodes": len(results),
        "passed_episodes": passed_count,
        "replay_rate": replay_rate,
        "threshold": args.threshold,
        "gate_passed": replay_rate >= args.threshold,
        "required_checks": ["deepcopy_snapshot", "untouched_evaluation_replay"],
        "diagnostic_only": ["seeded_scenario_rebuild"],
        "results": results,
        "scope_note": (
            "只验证 ToolSandbox 冻结快照复制和判分回放；模型服务、检索投递与行为轨迹另行验证。"
        ),
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(
        json.dumps(
            {
                "episodes": len(results),
                "passed": passed_count,
                "replay_rate": replay_rate,
                "gate_passed": report["gate_passed"],
            },
            ensure_ascii=False,
        )
    )
    return 0 if report["gate_passed"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
