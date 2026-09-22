"""读者契约与正文落点检查；不声称程序能测量人的理解。"""

from .contracts import ContractError, identifier, object_ref, ref, required


def strings(value, name, *, nonempty=False):
    if not isinstance(value, list) or (nonempty and not value):
        raise ContractError(f"{name} 必须是{'非空' if nonempty else ''}数组")
    for item in value:
        required(item, name)
    return value


def validate_contract(value):
    if not isinstance(value, dict):
        raise ContractError("reader_contract 必须是对象")
    required(value.get("audience"), "reader_contract.audience")
    strings(value.get("assumed_knowledge"), "reader_contract.assumed_knowledge")
    checks = strings(value.get("required_checks"), "reader_contract.required_checks", nonempty=True)
    for name in checks:
        identifier(name, "reader check id")
    if len(set(checks)) != len(checks):
        raise ContractError("reader_contract 检查项不能重复")


def validate_reader_check(target, review, state, expected_bundle, cite):
    contract = target.get("metadata", {}).get("reader_contract")
    if contract is None:
        return  # 历史报告不被静默补上新的读者验收。
    validate_contract(contract)
    check = review.get("reader_check")
    if not isinstance(check, dict):
        raise ContractError("报告声明了 reader_contract，评审必须实际完成 reader_check")
    if check.get("audience") != contract["audience"]:
        raise ContractError("读者检查必须面向报告声明的 audience")
    if check.get("method") != "model-text-audit":
        raise ContractError("当前接口记录 model-text-audit，不冒充真实人类读者实验")
    required(check.get("limitations"), "reader_check.limitations")
    exercises = check.get("exercises")
    if not isinstance(exercises, list) or not exercises:
        raise ContractError("reader_check 需要实际正文任务与回答")
    covered = set()
    for exercise in exercises:
        check_id = exercise.get("check_id")
        if check_id not in contract["required_checks"]:
            raise ContractError("正文任务必须对应声明的 required_checks")
        covered.add(check_id)
        for field in ("question", "response"):
            required(exercise.get(field), f"reader exercise.{field}")
        result = exercise.get("result")
        if result not in {"supported", "partial", "failed"}:
            raise ContractError("正文任务 result 必须是 supported/partial/failed")
        evidence = exercise.get("evidence", [])
        cite(state, evidence, expected_bundle)
        if not any(object_ref(item) == ref(target) for item in evidence):
            raise ContractError("理解回答必须定位当前正文，不能只引用原论文或旧报告")
        gaps = strings(exercise.get("gaps"), "reader exercise.gaps")
        outside = strings(exercise.get("outside_knowledge"), "reader exercise.outside_knowledge")
        if result == "supported" and (gaps or outside):
            raise ContractError("依赖未解释背景或仍有理解缺口的任务不能记为 supported")
        if result != "supported" and not (gaps or outside):
            raise ContractError("正文任务未通过时应定位缺口或未提供的背景")
        if result != "supported":
            links = strings(exercise.get("finding_refs"), "reader exercise.finding_refs", nonempty=True)
            for link in links:
                matches = [f for f in review.get("findings", []) if f.get("review_note_id") == link]
                if len(matches) != 1:
                    raise ContractError("未通过的读者任务必须唯一关联本次评审的实质整改")
                finding = matches[0]
                if (finding.get("reader_check_id") != check_id
                        or finding.get("severity") not in {"major", "fatal"}
                        or not any(object_ref(e) == ref(target) for e in finding.get("evidence", []))):
                    raise ContractError("关联实质整改必须针对同一读者任务、重大缺口和当前正文")
    if covered != set(contract["required_checks"]):
        raise ContractError("reader_check 未覆盖报告声明的理解任务")


def reader_status(target, review):
    if target.get("metadata", {}).get("reader_contract") is None:
        return {"status": "not-assessed", "meaning": "此历史版本没有声明正文读者契约"}
    check = review.get("reader_check")
    if not check:
        return {"status": "missing", "meaning": "缺少声明读者所需的正文检查"}
    passed = all(item["result"] == "supported" for item in check["exercises"])
    return {"status": "text-audit-cleared" if passed else "revise",
            "audience": check["audience"], "method": check["method"],
            "limitations": check["limitations"],
            "meaning": "仅正文可追踪性审计，不是人类理解率或科学正确性证明"}
