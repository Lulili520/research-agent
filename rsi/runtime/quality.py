"""版本绑定的研究评审。程序检查可追溯性；科学判断仍由评审负责。"""

from __future__ import annotations

from .contracts import (
    ContractError, DIMENSION_STATES, REPORTS, ROLES, RUBRICS,
    bundle, fresh, identifier, object_ref, ref, required, resolve,
)
from .reader import reader_status, validate_reader_check


def citations(state: dict, items: list, allowed: list[dict]) -> None:
    if not isinstance(items, list) or not items:
        raise ContractError("判断必须提供可定位的证据引用")
    for item in items:
        value = object_ref(item)
        resolve(state, value, current=True)
        if value not in allowed:
            raise ContractError("评审引用必须来自实际审阅的材料包；新增材料应先纳入正文版本")
        required(item.get("locator"), "证据位置 locator")


def validate_review(state: dict, review: dict, reviewer: str) -> dict:
    """评审不能由生成者自签；所有闭合意见也绑定当前版本及原始证据。"""
    identifier(reviewer, "reviewer")
    target = resolve(state, review.get("target"), current=True)
    kind = target["kind"]
    if kind not in REPORTS or not fresh(state, ref(target)):
        raise ContractError("只能评审依赖未过期的当前报告")
    if reviewer in target["contributors"]:
        raise ContractError("报告贡献者不能为同一报告签独立评审")
    expected_bundle = bundle(state, ref(target))
    reviewed = review.get("reviewed_refs", [])
    if {tuple(sorted(object_ref(item).items())) for item in reviewed} != {
        tuple(sorted(item.items())) for item in expected_bundle
    }:
        raise ContractError("评审必须声明完整的版本化材料包；不能仅审摘要或作者自评")
    dimensions = review.get("dimensions", {})
    if set(dimensions) != set(RUBRICS[kind]):
        raise ContractError(f"评审维度应为: {', '.join(RUBRICS[kind])}")
    for name, item in dimensions.items():
        if item.get("status") not in DIMENSION_STATES:
            raise ContractError(f"非法维度状态: {name}")
        required(item.get("reason"), f"{name}.reason")
        if item["status"] in {"supported", "partial"}:
            citations(state, item.get("evidence", []), expected_bundle)
        if item["status"] == "not-applicable":
            required(item.get("alternative_check"), f"{name}.alternative_check")
            if name in {"question-coverage", "source-fidelity", "explanation-quality",
                        "scientific-value", "nearest-neighbor-difference", "discriminating-tests"}:
                raise ContractError(f"{name} 是该交付的必要要求，不能整体标记不适用")
    sources = [resolve(state, value) for value in expected_bundle
               if resolve(state, value)["kind"] == "source"]
    if kind == "literature" and dimensions["method-understanding"]["status"] == "supported":
        if not any(source["metadata"]["access"] != "abstract" for source in sources):
            raise ContractError("只有摘要层面来源，不能确认全文方法理解")
    probes = review.get("probes", [])
    if not isinstance(probes, list) or not probes:
        raise ContractError("需要实际理解/反证核验记录，不能只有量表结论")
    for probe in probes:
        for field in ("question", "answer", "check"):
            required(probe.get(field), f"probe.{field}")
        if probe.get("result") not in {"supported", "partial", "failed"}:
            raise ContractError("理解核验 result 必须是 supported/partial/failed")
        citations(state, probe.get("evidence", []), expected_bundle)
    findings = review.get("findings", [])
    if not isinstance(findings, list):
        raise ContractError("findings 必须是数组")
    for finding in findings:
        if finding.get("dimension") not in dimensions:
            raise ContractError("问题必须关联评审维度")
        if finding.get("severity") not in {"fatal", "major", "minor"}:
            raise ContractError("问题严重性为 fatal/major/minor")
        if finding.get("role") not in ROLES - {"reviewer"}:
            raise ContractError("整改任务须分配给生成/取证角色，不能由同一评审代写")
        for field in ("concern", "location", "impact", "action", "closure_check"):
            required(finding.get(field), f"finding.{field}")
        citations(state, finding.get("evidence", []), expected_bundle)
    for name, item in dimensions.items():
        if item["status"] in {"partial", "insufficient"} and not any(
            finding["dimension"] == name and finding["severity"] in {"major", "fatal"}
            for finding in findings
        ):
            raise ContractError(f"未达成维度 {name} 必须转为实质整改任务")
    if any(probe["result"] != "supported" for probe in probes) and not any(
        finding["severity"] in {"major", "fatal"} for finding in findings
    ):
        raise ContractError("理解核验失败必须产生可执行的实质问题")
    validate_reader_check(target, review, state, expected_bundle, citations)
    resolutions = review.get("resolutions", [])
    if not isinstance(resolutions, list):
        raise ContractError("resolutions 必须是数组")
    seen = set()
    for resolution in resolutions:
        finding_id = resolution.get("finding_id")
        if finding_id in seen or finding_id not in state["findings"]:
            raise ContractError("复核引用未知或重复问题")
        seen.add(finding_id)
        finding = state["findings"][finding_id]
        if finding["target_key"] != target["key"] or finding["status"] != "open":
            raise ContractError("只能复核这份报告仍未关闭的问题")
        if resolution.get("disposition") not in {"resolved", "retained", "withdrawn"}:
            raise ContractError("复核处置必须为 resolved/retained/withdrawn")
        if resolution["disposition"] == "resolved" and target["version"] <= finding["target_version"]:
            raise ContractError("修复完成必须核验新版本；误报则明确 withdrawn")
        required(resolution.get("reason"), "resolution.reason")
        citations(state, resolution.get("evidence", []), expected_bundle)
    return {**review, "reviewer": reviewer, "kind": kind, "target": ref(target),
            "reviewed_refs": expected_bundle, "verification": "independent-review-record"}


def report_status(state: dict, kind: str) -> dict:
    reports = [values[-1] for values in state["artifacts"].values() if values[-1]["kind"] == kind]
    if not reports:
        return {"status": "missing", "reasons": ["报告尚未形成"]}
    target = reports[0]
    if not fresh(state, ref(target)):
        return {"status": "stale", "target": ref(target), "reasons": ["所依赖证据已更新，须重做受影响判断"]}
    reviews = [r for r in state["reviews"].values() if r["target"] == ref(target)]
    if not reviews:
        return {"status": "unreviewed", "target": ref(target), "reasons": ["当前版本没有独立评审"]}
    # 最新一次评审不会被较早的好评覆盖；不做多数票。
    review = reviews[-1]
    reader = reader_status(target, review)
    reasons = [f"{name}: {item['status']}" for name, item in review["dimensions"].items()
               if item["status"] not in {"supported", "not-applicable"}]
    if any(item["result"] != "supported" for item in review["probes"]):
        reasons.append("仍有理解/反证核验未通过")
    if reader["status"] in {"missing", "revise"}:
        reasons.append("目标读者的正文理解检查未完成")
    reasons.extend(f"{f['id']}: {f['concern']}" for f in state["findings"].values()
                   if f["target_key"] == target["key"] and f["status"] == "open"
                   and f["severity"] in {"major", "fatal"})
    return {"status": "revise" if reasons else "review-cleared", "target": ref(target),
            "review_id": review["id"], "reasons": reasons,
            "reader": reader,
            "meaning": "记录通过独立审阅，不等于已证明科学正确或创新"}


def quality_status(state: dict) -> dict:
    outcome = state["project"]["outcome"]
    kinds = list(REPORTS) if outcome == "both" else [outcome]
    reports = {kind: report_status(state, kind) for kind in kinds}
    return {"reports": reports,
            "ready": all(report["status"] == "review-cleared" for report in reports.values()),
            "automatic_semantic_verification": False}
