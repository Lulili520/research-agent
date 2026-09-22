"""仅测试用确定性 Worker，不是模型适配器，不产生真实调研。"""
import json
import sys

from rsi.runtime.contracts import RUBRICS, digest, ref
from rsi.tests.helpers import SOURCE, GOOD, BAD


def respond(request):
    role = request["task"]["role"]
    materials = request["materials"]
    if role == "leader":
        return {"status": "completed", "summary": "启动合成工作流", "tasks": [
            {"role": "searcher", "objective": "构建合成来源", "acceptance": "保存来源"}]}
    if role == "searcher":
        value = {"key": "source-a", "version": 1, "sha256": digest(SOURCE.encode())}
        return {"status": "completed", "summary": "合成来源", "artifacts": [
            {"key": "source-a", "kind": "source", "content": SOURCE,
             "metadata": {"origin": "synthetic-test-only", "access": "full-text"}}], "tasks": [
            {"role": "reader", "objective": "读取合成材料", "acceptance": "记录规则", "inputs": [value]}]}
    if role == "reader":
        content = "合成公式中的分母是所有分数之和。"
        note = {"key": "note-a", "version": 1, "sha256": digest(content.encode())}
        return {"status": "completed", "summary": "合成精读", "artifacts": [
            {"key": "note-a", "kind": "paper-note", "content": content}], "tasks": [
            {"role": "synthesizer", "objective": "生成合成调研", "acceptance": "回到来源", "inputs": [note]}]}
    if role == "synthesizer":
        return {"status": "completed", "summary": "合成初稿/修复", "artifacts": [
            {"key": "literature", "kind": "literature", "content": GOOD if request["task"]["action"] == "repair" else BAD}]}
    if role == "designer":
        return {"status": "completed", "summary": "合成方案", "artifacts": [
            {"key": "proposal", "kind": "proposal", "content": "# 方案设计\n合成方案，不是真实研究。"}],
            "nodes": [{"id": "idea-a", "kind": "idea", "text": "合成候选", "epistemic": "proposal", "evidence": []}]}
    target = next(item for item in materials if item["key"] == request["task"]["target_key"])
    source_ref = next(ref(item) for item in materials if item["kind"] == "source")
    evidence = [{**source_ref, "locator": "synthetic Eq. 1"}]
    review = {"target": ref(target), "reviewed_refs": [ref(item) for item in materials],
              "dimensions": {name: {"status": "supported", "reason": "合成检查", "evidence": evidence}
                             for name in RUBRICS[target["kind"]]},
              "probes": [{"question": "检查合成规则", "answer": "必须归一化", "check": "合成公式一致性",
                          "result": "supported", "evidence": evidence}], "findings": [], "resolutions": []}
    if target["kind"] == "literature" and target["version"] == 1:
        review["dimensions"]["method-understanding"]["status"] = "insufficient"
        review["findings"] = [{"dimension": "method-understanding", "severity": "major", "concern": "遗漏分母",
            "location": "第一段", "impact": "方法错误", "action": "修复归一化规则", "role": "synthesizer",
            "closure_check": "新版本解释分母", "evidence": evidence}]
    else:
        review["resolutions"] = [{"finding_id": finding["id"], "disposition": "resolved",
                                   "reason": "合成新版本已经修复", "evidence": evidence}
                                  for finding in request["open_findings"] if finding["target_key"] == target["key"]]
    return {"status": "completed", "summary": "合成评审", "review": review}


if __name__ == "__main__":
    print(json.dumps(respond(json.load(sys.stdin)), ensure_ascii=False))
