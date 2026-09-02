#!/usr/bin/env python3
"""ToolSandbox 无模型基础设施自检。

该脚本不调用任何模型服务，只验证固定随机种子下场景构造、初始快照序列化、
深拷贝隔离和未执行状态的判分确定性。结果以 JSON 输出，便于登记实验运行。
"""

from __future__ import annotations

import argparse
import copy
import hashlib
import json
import random
from pathlib import Path
from typing import Any

import attrs

from tool_sandbox.common.tool_discovery import ToolBackend
from tool_sandbox.scenarios import named_scenarios


def canonical_hash(value: Any) -> str:
    payload = json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        default=str,
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def build_scenario(name: str, seed: int):
    random.seed(seed)
    scenarios = named_scenarios(preferred_tool_backend=ToolBackend.DEFAULT)
    if name not in scenarios:
        suggestions = sorted(item for item in scenarios if name in item)[:10]
        raise KeyError(f"未知场景 {name!r}；近似候选：{suggestions}")
    return scenarios[name], len(scenarios)


def run_smoke(name: str, seed: int) -> dict[str, Any]:
    first, scenario_count = build_scenario(name, seed)
    second, _ = build_scenario(name, seed)

    first_snapshot = first.starting_context.to_dict(serialize_console=False)
    second_snapshot = second.starting_context.to_dict(serialize_console=False)
    copied_context = copy.deepcopy(first.starting_context)
    copied_snapshot = copied_context.to_dict(serialize_console=False)

    first_eval = attrs.asdict(
        first.evaluation.evaluate(first.starting_context, first.max_messages)
    )
    copied_eval = attrs.asdict(
        first.evaluation.evaluate(copied_context, first.max_messages)
    )

    checks = {
        "seeded_scenario_rebuild": canonical_hash(first_snapshot)
        == canonical_hash(second_snapshot),
        "deepcopy_snapshot": canonical_hash(first_snapshot)
        == canonical_hash(copied_snapshot),
        "untouched_evaluation_replay": canonical_hash(first_eval)
        == canonical_hash(copied_eval),
    }
    return {
        "schema_version": 1,
        "profile": "toolsandbox-local-no-model",
        "scenario": name,
        "seed": seed,
        "scenario_count": scenario_count,
        "snapshot_sha256": canonical_hash(first_snapshot),
        "untouched_evaluation_sha256": canonical_hash(first_eval),
        "checks": checks,
        "passed": all(checks.values()),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--scenario", default="add_contact_with_name_and_phone_number"
    )
    parser.add_argument("--seed", type=int, default=20260902)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()

    result = run_smoke(args.scenario, args.seed)
    rendered = json.dumps(result, ensure_ascii=False, indent=2)
    if args.output is not None:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered + "\n", encoding="utf-8")
    print(rendered)
    return 0 if result["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
