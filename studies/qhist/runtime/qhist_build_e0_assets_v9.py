#!/usr/bin/env python3
"""从冻结 ToolSandbox revision 构建 Q-HIST v9 E0 的审计资产。"""

from __future__ import annotations

import argparse
import copy
import hashlib
import json
import random
from pathlib import Path
from typing import Any

import qhist_v9_spec as spec


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def inject_agent_contract(episode: dict[str, Any]) -> dict[str, Any]:
    result = copy.deepcopy(episode)
    messages = result["base_messages"]
    system_indices = [
        index for index, message in enumerate(messages) if message.get("role") == "system"
    ]
    if system_indices != [0]:
        raise RuntimeError(
            f"{result['episode_id']} 必须恰有一个且位于首位的 system message："
            f"{system_indices}"
        )
    original = str(messages[0].get("content") or "").rstrip()
    if spec.AGENT_TOOL_CONTRACT in original:
        raise RuntimeError(f"{result['episode_id']} 原始 system 已含 v9 contract")
    combined = original + "\n\n" + spec.AGENT_TOOL_CONTRACT
    messages[0]["content"] = combined
    result["agent_tool_contract"] = {
        "text": spec.AGENT_TOOL_CONTRACT,
        "sha256": hashlib.sha256(spec.AGENT_TOOL_CONTRACT.encode("utf-8")).hexdigest(),
        "original_system_sha256": hashlib.sha256(original.encode("utf-8")).hexdigest(),
        "combined_system_sha256": hashlib.sha256(combined.encode("utf-8")).hexdigest(),
        "system_message_index": 0,
    }
    return result


def main() -> int:
    # ToolSandbox 只存在于冻结的远端环境，延迟导入使纯合同单元测试可在
    # 控制机运行；base 在导入场景前同时冻结协议时钟。
    import qhist_build_e0_assets as base

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--toolsandbox-source", type=Path, required=True)
    parser.add_argument("--seed", type=int, default=spec.SCHEDULE_SEED)
    args = parser.parse_args()

    if args.output.exists() and any(args.output.iterdir()):
        raise RuntimeError(f"审计输出目录必须不存在或为空：{args.output}")
    actual_revision = base.git_revision(args.toolsandbox_source)
    if actual_revision != spec.UPSTREAM_COMMIT:
        raise RuntimeError(
            f"ToolSandbox revision 不匹配：{actual_revision} != {spec.UPSTREAM_COMMIT}"
        )
    args.output.mkdir(parents=True, exist_ok=True)
    random.seed(args.seed)
    scenarios = base.named_scenarios(preferred_tool_backend=base.ToolBackend.DEFAULT)
    episodes: list[dict[str, Any]] = []
    predicates: list[dict[str, Any]] = []
    patches: list[dict[str, Any]] = []
    snapshots_dir = args.output / "snapshots"
    for frozen in spec.DEVELOPMENT_SCENARIOS:
        scenario_name = str(frozen["scenario"])
        if scenario_name not in scenarios:
            raise RuntimeError(f"冻结场景不存在：{scenario_name}")
        episode, predicate, patch = base.build_episode(
            dict(frozen), scenarios[scenario_name], snapshots_dir
        )
        episodes.append(inject_agent_contract(episode))
        predicates.append(predicate)
        patches.append(patch)

    trajectory_units = spec.build_trajectory_units()
    repeat_units = spec.build_technical_repeat_units()
    qualification_units = spec.build_qualification_units()
    base.write_jsonl(args.output / "episodes.jsonl", episodes)
    base.write_jsonl(args.output / "predicates.jsonl", predicates)
    base.write_jsonl(args.output / "environment-patches.jsonl", patches)
    base.write_jsonl(args.output / "trajectory-units.jsonl", trajectory_units)
    base.write_jsonl(args.output / "technical-repeat-units.jsonl", repeat_units)
    base.write_jsonl(args.output / "qualification-units.jsonl", qualification_units)

    contract_hashes = {
        row["agent_tool_contract"]["sha256"] for row in episodes
    }
    if contract_hashes != {
        hashlib.sha256(spec.AGENT_TOOL_CONTRACT.encode("utf-8")).hexdigest()
    }:
        raise RuntimeError("v9 contract 未在全部 episode 保持一致")

    split = {
        "schema_version": 1,
        "protocol_id": spec.PROTOCOL_ID,
        "protocol_version": spec.PROTOCOL_VERSION,
        "toolsandbox_commit": actual_revision,
        "schedule_seed": args.seed,
        "reference_time_iso": spec.REFERENCE_TIME_ISO,
        "reference_time_epoch": spec.REFERENCE_TIME_EPOCH,
        "development": [row["scenario"] for row in spec.DEVELOPMENT_SCENARIOS],
        "development_families": sorted(
            {
                spec.normalize_family(str(row["scenario"]))
                for row in spec.DEVELOPMENT_SCENARIOS
            }
        ),
        "technical_repeat_episode_ids": list(spec.TECHNICAL_REPEAT_EPISODES),
        "finite_suite_resolution": {
            "confirmatory_family_count": 15,
            "distance_strata": 2,
            "minimum_decisions_in_stratum": 4,
            "maximum_basic_step": 1.0 / (15 * 2 * 4),
            "required_maximum_basic_step_less_than": 0.01,
        },
        "model_id": spec.MODEL_ID,
        "model_revision": spec.MODEL_REVISION,
        "precisions": spec.PRECISIONS,
        "agent_tool_contract": spec.AGENT_TOOL_CONTRACT,
        "agent_tool_contract_sha256": next(iter(contract_hashes)),
        "counts": spec.validate_frozen_design(),
    }
    base.write_json(args.output / "split.json", split)

    files = sorted(path for path in args.output.rglob("*") if path.is_file())
    script_dir = Path(__file__).resolve().parent
    manifest = {
        "schema_version": 1,
        "protocol_id": spec.PROTOCOL_ID,
        "protocol_version": spec.PROTOCOL_VERSION,
        "toolsandbox_commit": actual_revision,
        "generator": Path(__file__).name,
        "generator_sha256": sha256_file(Path(__file__)),
        "v9_spec_sha256": sha256_file(script_dir / "qhist_v9_spec.py"),
        "base_builder_sha256": sha256_file(script_dir / "qhist_build_e0_assets.py"),
        "v8_spec_dependency_sha256": sha256_file(script_dir / "qhist_e0_spec.py"),
        "agent_tool_contract_sha256": next(iter(contract_hashes)),
        "files": [
            {
                "path": str(path.relative_to(args.output)).replace("\\", "/"),
                "bytes": path.stat().st_size,
                "sha256": sha256_file(path),
            }
            for path in files
        ],
    }
    base.write_json(args.output / "manifest.json", manifest)
    summary = {
        "status": "succeeded",
        "protocol_version": spec.PROTOCOL_VERSION,
        "episodes": len(episodes),
        **spec.validate_frozen_design(),
        "manifest_sha256": sha256_file(args.output / "manifest.json"),
    }
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
