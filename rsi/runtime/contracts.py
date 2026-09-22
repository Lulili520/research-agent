"""跨模型的协议与质量维度，不在这里给科学内容打分。"""

from __future__ import annotations

import hashlib
import json
import re
from typing import Any

VERSION = "rsi-evidence-1"
ROLES = {"leader", "searcher", "reader", "synthesizer", "designer", "theorist", "reviewer"}
SKILLS = {
    "leader": ("evidence-synthesis", "proposal-design"),
    "searcher": ("scholarly-search",),
    "reader": ("paper-analysis",),
    "synthesizer": ("evidence-synthesis",),
    "designer": ("proposal-design",),
    "theorist": ("proposal-design",),
    "reviewer": ("research-review",),
}
REPORTS = {"literature": "文献调研.md", "proposal": "方案设计.md"}
ARTIFACT_KINDS = {"source", "figure", "paper-note", "search-log", "literature", "proposal", "analysis"}
RUBRICS = {
    "literature": (
        "question-coverage", "source-fidelity", "method-understanding",
        "evidence-comparability", "synthesis-and-gaps", "explanation-quality",
    ),
    "proposal": (
        "scientific-value", "nearest-neighbor-difference", "mechanism-and-assumptions",
        "implementation-specificity", "discriminating-tests", "feasibility-and-risks",
    ),
}
DIMENSION_STATES = {"supported", "partial", "insufficient", "not-applicable"}
NODE_KINDS = {"question", "paper", "claim", "gap", "idea", "hypothesis", "argument", "decision"}


class ContractError(ValueError):
    pass


def canonical(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def required(value: Any, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ContractError(f"{label} 必须是非空文本")
    return value


def identifier(value: Any, label: str = "标识符") -> str:
    if not isinstance(value, str) or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,95}", value):
        raise ContractError(f"{label} 只能包含字母、数字、点、下划线和连字符")
    return value


def object_ref(value: Any) -> dict:
    if not isinstance(value, dict):
        raise ContractError("版本引用必须是对象")
    identifier(value.get("key"), "引用 key")
    if type(value.get("version")) is not int or value["version"] < 1:
        raise ContractError("引用必须指定正整数 version")
    if not isinstance(value.get("sha256"), str) or not re.fullmatch(r"[a-f0-9]{64}", value["sha256"]):
        raise ContractError("引用必须指定完整 sha256")
    return {key: value[key] for key in ("key", "version", "sha256")}


def ref(artifact: dict) -> dict:
    return {key: artifact[key] for key in ("key", "version", "sha256")}


def resolve(state: dict, value: dict, *, current: bool = False) -> dict:
    value = object_ref(value)
    versions = state["artifacts"].get(value["key"], [])
    if value["version"] > len(versions):
        raise ContractError(f"引用不存在: {value}")
    artifact = versions[value["version"] - 1]
    if artifact["sha256"] != value["sha256"]:
        raise ContractError("引用的内容哈希不匹配")
    if current and versions[-1]["version"] != value["version"]:
        raise ContractError(f"引用已过期: {value['key']}")
    return artifact


def fresh(state: dict, value: dict, visited: set | None = None) -> bool:
    visited = set() if visited is None else visited
    artifact = resolve(state, value)
    token = (artifact["key"], artifact["version"])
    if token in visited:
        return True
    visited.add(token)
    if state["artifacts"][artifact["key"]][-1]["version"] != artifact["version"]:
        return False
    return all(fresh(state, parent, visited) for parent in artifact["parents"])


def bundle(state: dict, target: dict) -> list[dict]:
    """显式依赖的传递闭包；评审收到同一批原始资料，不靠作者口头结论。"""
    collected: dict[tuple, dict] = {}

    def visit(value: dict) -> None:
        artifact = resolve(state, value)
        token = (artifact["key"], artifact["version"])
        if token in collected:
            return
        collected[token] = ref(artifact)
        for parent in artifact["parents"]:
            visit(parent)

    visit(target)
    return list(collected.values())
