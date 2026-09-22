from rsi.runtime.contracts import RUBRICS, bundle, ref


SOURCE = "SYNTHETIC TEST SOURCE. Eq. 1: weight = score / sum(scores). Table 1 uses matched compute."
GOOD = "# 文献调研\n\n合成测试材料。权重按总分归一化；这不是一篇真实论文。\n"
BAD = "# 文献调研\n\n合成测试材料。直接使用分数作为权重。\n"


def source(engine, *, access="full-text", content=SOURCE):
    return engine.capture({"key": "source-a", "kind": "source", "content": content,
                           "metadata": {"origin": "synthetic-test-only", "access": access}}, "finder")


def report(engine, source_artifact, *, content=GOOD, key="literature", kind="literature", actor="writer"):
    return engine.capture({"key": key, "kind": kind, "content": content,
                           "parents": [ref(source_artifact)]}, actor)


def review_record(state, target, *, bad=False):
    refs = bundle(state, ref(target))
    source_ref = next(value for value in refs if state["artifacts"][value["key"]][value["version"] - 1]["kind"] == "source")
    evidence = [{**source_ref, "locator": "synthetic Eq. 1"}]
    dimensions = {name: {"status": "supported", "reason": "仅用于验证契约的合成判断", "evidence": evidence}
                  for name in RUBRICS[target["kind"]]}
    result = {"target": ref(target), "reviewed_refs": refs, "dimensions": dimensions,
              "probes": [{"question": "合成公式是否归一化？", "answer": "有分母 sum(scores)",
                          "check": "直接核对合成来源 Eq. 1", "result": "supported", "evidence": evidence}],
              "findings": [], "resolutions": []}
    if bad:
        dimensions["method-understanding"]["status"] = "insufficient"
        result["findings"] = [{"dimension": "method-understanding", "severity": "major",
            "concern": "遗漏归一化分母", "location": "正文第一段", "impact": "改变了算法含义",
            "action": "根据 Eq. 1 修正归一化规则并走通例子", "role": "synthesizer",
            "closure_check": "新正文的规则与 Eq. 1 一致", "evidence": evidence}]
    return result
