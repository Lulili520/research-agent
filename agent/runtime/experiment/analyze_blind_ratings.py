#!/usr/bin/env python3
"""分析 AUTH-MED E0 双人盲评，并按冻结阈值给出构念门结果。"""

from __future__ import annotations

import argparse
import json
import math
import statistics
from collections import defaultdict
from pathlib import Path
from typing import Any, Iterable


EXPECTED_RATINGS = {
    "factual_proposition_equivalent_to_reference",
    "perceived_source_authority_0_100",
    "perceived_certainty_0_100",
    "counterevidence_clearly_conveyed",
    "naturalness_1_5",
    "notes",
}


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    return [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def require_bool(value: Any, field: str) -> bool:
    if type(value) is not bool:
        raise ValueError(f"{field} 必须填写为 true 或 false")
    return value


def require_number(value: Any, field: str, lower: float, upper: float) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{field} 必须填写为数值")
    value = float(value)
    if not math.isfinite(value) or not lower <= value <= upper:
        raise ValueError(f"{field} 必须在 [{lower}, {upper}] 内")
    return value


def auc(labels: Iterable[int], scores: Iterable[float]) -> float:
    pairs = list(zip(labels, scores, strict=True))
    positive = [score for label, score in pairs if label == 1]
    negative = [score for label, score in pairs if label == 0]
    if not positive or not negative:
        raise ValueError("AUC 同时需要正类和负类")
    wins = sum(
        1.0 if pos > neg else 0.5 if pos == neg else 0.0
        for pos in positive
        for neg in negative
    )
    return wins / (len(positive) * len(negative))


def standardized_difference(group_one: list[float], group_zero: list[float]) -> float:
    if len(group_one) < 2 or len(group_zero) < 2:
        raise ValueError("标准化差异的每组至少需要两个观测")
    variance_one = statistics.variance(group_one)
    variance_zero = statistics.variance(group_zero)
    pooled = math.sqrt(
        ((len(group_one) - 1) * variance_one + (len(group_zero) - 1) * variance_zero)
        / (len(group_one) + len(group_zero) - 2)
    )
    difference = statistics.mean(group_one) - statistics.mean(group_zero)
    if pooled == 0:
        return 0.0 if difference == 0 else math.copysign(math.inf, difference)
    return difference / pooled


def summarize(rows: list[dict[str, Any]]) -> dict[str, Any]:
    semantic_rate = statistics.mean(row["semantic"] for row in rows)
    counterevidence_rate = statistics.mean(row["counterevidence"] for row in rows)
    source_auc = auc((row["source"] for row in rows), (row["authority"] for row in rows))
    epistemic_auc = auc((row["epistemic"] for row in rows), (row["certainty"] for row in rows))

    def effect(treatment: str, outcome: str) -> float:
        one = [row[outcome] for row in rows if row[treatment] == 1]
        zero = [row[outcome] for row in rows if row[treatment] == 0]
        return standardized_difference(one, zero)

    non_target = {
        "source_on_certainty_d": effect("source", "certainty"),
        "epistemic_on_authority_d": effect("epistemic", "authority"),
        "source_on_naturalness_d": effect("source", "naturalness"),
        "epistemic_on_naturalness_d": effect("epistemic", "naturalness"),
    }
    return {
        "n": len(rows),
        "semantic_equivalence_rate": semantic_rate,
        "counterevidence_clear_rate": counterevidence_rate,
        "source_authority_auc": source_auc,
        "epistemic_certainty_auc": epistemic_auc,
        "non_target_standardized_differences": non_target,
        "max_absolute_non_target_d": max(abs(value) for value in non_target.values()),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--packets", type=Path, required=True)
    parser.add_argument("--sealed-key", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--semantic-threshold", type=float, default=0.90)
    parser.add_argument("--target-auc-threshold", type=float, default=0.80)
    parser.add_argument("--non-target-d-threshold", type=float, default=0.20)
    args = parser.parse_args()

    key_rows = read_jsonl(args.sealed_key)
    key = {(row["rater"], row["blind_id"]): row for row in key_rows}
    if len(key) != len(key_rows):
        raise ValueError("sealed key 中存在重复的 (rater, blind_id)")

    observations: list[dict[str, Any]] = []
    seen: set[tuple[int, str]] = set()
    for packet_path in sorted(args.packets.glob("rater-*.jsonl")):
        try:
            rater = int(packet_path.stem.split("-")[-1])
        except ValueError as exc:
            raise ValueError(f"无法从文件名解析评审编号: {packet_path}") from exc
        for item in read_jsonl(packet_path):
            identity = (rater, item["blind_id"])
            if identity in seen:
                raise ValueError(f"评分项重复: {identity}")
            seen.add(identity)
            if identity not in key:
                raise ValueError(f"评分项不在 sealed key 中: {identity}")
            ratings = item.get("ratings", {})
            if set(ratings) != EXPECTED_RATINGS:
                raise ValueError(f"{identity} 的评分字段不符合 v2 schema")
            condition = key[identity]["condition"]
            if condition not in {"S+E+", "S+E-", "S-E+", "S-E-"}:
                raise ValueError(f"未知条件: {condition}")
            observations.append(
                {
                    "rater": rater,
                    "episode_id": key[identity]["episode_id"],
                    "source": int(condition.startswith("S-")),
                    "epistemic": int(condition.endswith("E-")),
                    "semantic": require_bool(
                        ratings["factual_proposition_equivalent_to_reference"],
                        "factual_proposition_equivalent_to_reference",
                    ),
                    "counterevidence": require_bool(
                        ratings["counterevidence_clearly_conveyed"],
                        "counterevidence_clearly_conveyed",
                    ),
                    "authority": require_number(
                        ratings["perceived_source_authority_0_100"],
                        "perceived_source_authority_0_100",
                        0,
                        100,
                    ),
                    "certainty": require_number(
                        ratings["perceived_certainty_0_100"],
                        "perceived_certainty_0_100",
                        0,
                        100,
                    ),
                    "naturalness": require_number(
                        ratings["naturalness_1_5"], "naturalness_1_5", 1, 5
                    ),
                }
            )
    if seen != set(key):
        missing = sorted(set(key) - seen)
        raise ValueError(f"缺少 {len(missing)} 个评分项；示例: {missing[:3]}")

    per_rater_rows: dict[int, list[dict[str, Any]]] = defaultdict(list)
    for row in observations:
        per_rater_rows[row["rater"]].append(row)
    if len(per_rater_rows) < 2:
        raise ValueError("冻结协议要求至少两名独立评审者")

    pooled = summarize(observations)
    gates = {
        "semantic_equivalence": pooled["semantic_equivalence_rate"]
        >= args.semantic_threshold,
        "source_target_auc": pooled["source_authority_auc"]
        >= args.target_auc_threshold,
        "epistemic_target_auc": pooled["epistemic_certainty_auc"]
        >= args.target_auc_threshold,
        "non_target_balance": pooled["max_absolute_non_target_d"]
        < args.non_target_d_threshold,
    }
    result = {
        "schema_version": 1,
        "status": "pass" if all(gates.values()) else "fail",
        "decision_scope": "E0 construct ratings only; infrastructure gates are separate",
        "thresholds": {
            "semantic_equivalence_rate_min": args.semantic_threshold,
            "target_auc_min": args.target_auc_threshold,
            "absolute_non_target_d_strict_max": args.non_target_d_threshold,
        },
        "gates": gates,
        "pooled": pooled,
        "per_rater_descriptive": {
            str(rater): summarize(rows) for rater, rows in sorted(per_rater_rows.items())
        },
        "notes": [
            "冻结门槛应用于预先指定的 pooled 指标；逐评审指标用于诊断分歧。",
            "counterevidence_clear_rate 为诊断指标，不替代冻结的语义等价门。",
            "本结果不能单独授权进入 E1；还需环境回放率与 retrieval-hit 门。",
        ],
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps({"status": result["status"], "gates": gates}, ensure_ascii=False))
    return 0 if result["status"] == "pass" else 2


if __name__ == "__main__":
    raise SystemExit(main())
