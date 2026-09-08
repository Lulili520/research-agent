#!/usr/bin/env python3
"""只读诊断 Q-HIST v8 的输出类型与多步构念响应。

本脚本不改变 v8 的既有裁决。它把旧 ``format_validity`` 中的无工具输出
拆成正常终止文本、真正的工具格式尝试失败、非法原生调用和空输出，并用完整
的三个纠正后决策边界重算 development 构念描述量，供下一版协议设计使用。
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
from collections import Counter
from pathlib import Path
from statistics import mean
from typing import Any


PRECISIONS = ("P00", "P10", "P01", "P11")
RUN_NAMES = {
    precision: f"QHIST-E0-v8-traj-{precision}-r1" for precision in PRECISIONS
}
ORTHOGONAL_EPISODES = ("QH-E0-01", "QH-E0-03", "QH-E0-05", "QH-E0-07")
TOOLISH_RE = re.compile(
    r"<\/?tool_call\b|(?:^|[\s{,])['\"]?(?:name|arguments)['\"]?\s*:",
    re.IGNORECASE,
)


def canonical_json(value: Any) -> str:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        default=str,
    )


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def classify_decision(decision: dict[str, Any]) -> str:
    """把模型输出按语法形态分类，不判断任务语义是否正确。"""

    if decision.get("valid_native_tool_action"):
        return "native-tool"
    if decision.get("parsed_actions"):
        return "invalid-native-tool"
    text = str(decision.get("visible_content") or decision.get("raw_text") or "").strip()
    if not text:
        return "empty"
    if TOOLISH_RE.search(text):
        return "malformed-tool-attempt"
    return "terminal-text"


def syntactically_valid(output_class: str) -> bool:
    return output_class in {"native-tool", "terminal-text"}


def phase_mean(unit: dict[str, Any], phase: str) -> float:
    distance = int(unit["unit"]["distance"])
    values = [float(row["v_score"]) for row in unit["decisions"]]
    selected = values[:distance] if phase == "pre" else values[distance : distance + 3]
    if not selected:
        raise ValueError(f"缺少 {phase} 决策：{unit['unit']['unit_id']}")
    return mean(selected)


def load_units(runs_root: Path, precision: str) -> list[dict[str, Any]]:
    unit_root = runs_root / RUN_NAMES[precision] / "driver" / "units"
    paths = sorted(unit_root.glob("*.json"))
    if not paths:
        raise FileNotFoundError(f"未找到 {precision} unit：{unit_root}")
    return [json.loads(path.read_text(encoding="utf-8")) for path in paths]


def summarize_precision(units: list[dict[str, Any]]) -> dict[str, Any]:
    decisions = [decision for unit in units for decision in unit["decisions"]]
    classes = [classify_decision(decision) for decision in decisions]
    legacy_false_invalid = sum(
        cls == "terminal-text" and not decision.get("valid_native_tool_action")
        for cls, decision in zip(classes, decisions)
    )
    return {
        "units": len(units),
        "decisions": len(decisions),
        "output_class_counts": dict(sorted(Counter(classes).items())),
        "legacy_format_validity_mean": mean(
            float(unit["metrics"]["format_validity"]) for unit in units
        ),
        "syntactic_validity": mean(float(syntactically_valid(cls)) for cls in classes),
        "terminal_text_counted_invalid_by_v8": legacy_false_invalid,
        "actual_malformed_or_empty_count": sum(
            cls in {"malformed-tool-attempt", "invalid-native-tool", "empty"}
            for cls in classes
        ),
    }


def p00_construct(units: list[dict[str, Any]]) -> dict[str, Any]:
    index = {
        (
            unit["unit"]["episode_id"],
            unit["unit"]["history"],
            int(unit["unit"]["distance"]),
        ): unit
        for unit in units
    }
    episode_ids = sorted({unit["unit"]["episode_id"] for unit in units})
    per_episode: dict[str, Any] = {}
    for episode_id in episode_ids:
        induction = []
        correction = []
        sham_shift = []
        align_increment = []
        for distance in (1, 3):
            n = index[(episode_id, "N", distance)]
            e = index[(episode_id, "E", distance)]
            s = index[(episode_id, "S", distance)]
            c_text = index[(episode_id, "C_text", distance)]
            c_align = index[(episode_id, "C_align", distance)]
            induction.append(phase_mean(e, "pre") - phase_mean(n, "pre"))
            correction.append(phase_mean(s, "post") - phase_mean(c_text, "post"))
            sham_shift.append(phase_mean(s, "post") - phase_mean(e, "post"))
            align_increment.append(
                phase_mean(c_text, "post") - phase_mean(c_align, "post")
            )
        per_episode[episode_id] = {
            "pre_error_induction_E_minus_N": mean(induction),
            "three_boundary_correction_S_minus_C_text": mean(correction),
            "three_boundary_sham_shift_S_minus_E": mean(sham_shift),
            "three_boundary_environment_alignment_C_text_minus_C_align": mean(
                align_increment
            ),
        }
    return {
        "definition": (
            "每个 episode 先在 d=1/3 内等权；induction 使用纠正前 E-N，"
            "correction 使用三个纠正后边界的 S-C_text"
        ),
        "per_episode": per_episode,
        "positive_induction_episodes": sum(
            row["pre_error_induction_E_minus_N"] > 0 for row in per_episode.values()
        ),
        "positive_correction_episodes": sum(
            row["three_boundary_correction_S_minus_C_text"] > 0
            for row in per_episode.values()
        ),
        "episodes": len(per_episode),
    }


def clean_subset(units_by_precision: dict[str, list[dict[str, Any]]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for precision in ("P00", "P11"):
        selected = [
            unit
            for unit in units_by_precision[precision]
            if unit["unit"]["episode_id"] in ORTHOGONAL_EPISODES
            and unit["unit"]["history"] == "N"
            and int(unit["unit"]["distance"]) == 3
        ]
        classes = [classify_decision(row) for unit in selected for row in unit["decisions"]]
        result[precision] = {
            "units": len(selected),
            "syntactic_validity": mean(float(syntactically_valid(cls)) for cls in classes),
            "native_tool_rate": mean(float(cls == "native-tool") for cls in classes),
            "terminal_text_rate": mean(float(cls == "terminal-text") for cls in classes),
            "mean_toolsandbox_similarity": mean(
                float(unit["evaluation"]["similarity"]) for unit in selected
            ),
            "nonzero_similarity_episodes": sum(
                float(unit["evaluation"]["similarity"]) > 0 for unit in selected
            ),
        }
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--runs-root", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        raise RuntimeError(f"禁止覆盖诊断产物：{args.output}")
    units_by_precision = {
        precision: load_units(args.runs_root, precision) for precision in PRECISIONS
    }
    result = {
        "schema_version": 1,
        "analysis_scope": "QHIST-EXP v8 E0 development diagnosis only",
        "changes_v8_decision": False,
        "source_runs": {
            precision: RUN_NAMES[precision] for precision in PRECISIONS
        },
        "precision_summaries": {
            precision: summarize_precision(units)
            for precision, units in units_by_precision.items()
        },
        "clean_orthogonal_subset": clean_subset(units_by_precision),
        "p00_multistep_construct": p00_construct(units_by_precision["P00"]),
        "interpretation": {
            "format_metric": (
                "v8 把普通非空终止文本与真正语法损坏一并计为 invalid；输出语法、"
                "工具策略和任务成功必须在新协议中分轴。"
            ),
            "construct_metric": (
                "单个首个纠正后边界不能覆盖需要多个工具动作的修复；新协议仍须在"
                "独立版本中预先冻结完整后窗口指标，不能改写 v8 裁决。"
            ),
        },
        "source_artifacts": [],
    }
    for precision, run_name in RUN_NAMES.items():
        summary = args.runs_root / run_name / "driver" / "summary.json"
        result["source_artifacts"].append(
            {"precision": precision, "path": str(summary), "sha256": sha256_file(summary)}
        )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(canonical_json({"status": "succeeded", "output": str(args.output)}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
