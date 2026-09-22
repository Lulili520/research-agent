"""研究动作、共享知识、独立评审与定向修正的事务接口。"""

from __future__ import annotations

from pathlib import Path
from uuid import uuid4

from .contracts import (
    ARTIFACT_KINDS, ContractError, NODE_KINDS, REPORTS, ROLES, SKILLS, VERSION,
    bundle, fresh, identifier, object_ref, ref, required, resolve,
)
from .quality import quality_status, report_status, validate_review
from .store import Store


def uid(prefix: str) -> str:
    return f"{prefix}-{uuid4().hex[:16]}"


class Engine:
    def __init__(self, project: str | Path):
        self.store = Store(project)

    def initialize(self, topic: str, outcome: str = "both") -> dict:
        self.store.initialize(topic, outcome)
        self.add_task("leader", "明确用户问题、所需交付、关键分支和资源约束；分派实际检索与精读任务。"
                      "用争议和证据缺口驱动后续任务，不把完整计划当作研究完成。",
                      "记录问题与范围节点；启动能取得来源证据的任务。")
        return self.status()

    @staticmethod
    def _task(state: dict, role: str, objective: str, acceptance: str, inputs: list,
              *, dependencies: list | None = None, finding_id: str | None = None,
              target_key: str | None = None, action: str = "research") -> dict:
        if role not in ROLES:
            raise ContractError("未知角色")
        dependencies = dependencies or []
        for dependency in dependencies:
            if dependency not in state["tasks"]:
                raise ContractError("任务依赖不存在")
        for value in inputs:
            resolve(state, value, current=True)
        return {"id": uid("task"), "role": role, "objective": required(objective, "objective"),
                "acceptance": required(acceptance, "acceptance"), "inputs": inputs,
                "dependencies": dependencies, "finding_id": finding_id, "target_key": target_key,
                "action": action, "status": "pending", "attempts": 0, "worker": None}

    def add_task(self, role: str, objective: str, acceptance: str, inputs: list | None = None,
                 dependencies: list | None = None) -> dict:
        box = {}
        def build(state: dict) -> list:
            task = self._task(state, role, objective, acceptance, inputs or [], dependencies=dependencies)
            box.update(task)
            return [("task.created", task)]
        self.store.commit(build)
        return box

    def _artifact(self, state: dict, item: dict, actor: str, default_inputs: list) -> dict:
        key = identifier(item.get("key"))
        kind = item.get("kind")
        if kind not in ARTIFACT_KINDS:
            raise ContractError("未知材料种类")
        versions = state["artifacts"].get(key, [])
        if versions and versions[-1]["kind"] != kind:
            raise ContractError("同一材料 key 不能改变 kind")
        if kind in REPORTS and any(v[-1]["kind"] == kind and k != key for k, v in state["artifacts"].items()):
            raise ContractError("每类报告使用稳定 key；候选方案放 idea 节点或 analysis 材料")
        parents = []
        explicit = item.get("parents", [])
        explicit_keys = {value["key"] for value in explicit}
        # 上下文不等于证据依赖。来源抓取不依赖旧报告，精读也不反向依赖使用它的正文。
        inherited = [] if kind == "source" else [
            value for value in default_inputs
            if value["key"] not in explicit_keys
            and (resolve(state, value)["kind"] not in REPORTS
                 or (kind == "proposal" and resolve(state, value)["kind"] == "literature"))
        ]
        for value in inherited + explicit:
            value = object_ref(value)
            # 改写报告可读取它的旧版本，但不可把旧版本保留为 freshness 依赖。
            # 将旧版本的证据依赖展开，更新的上游引用必须显式提供。
            if value["key"] == key:
                continue
            resolve(state, value, current=True)
            if value not in parents:
                parents.append(value)
        if kind in REPORTS and not parents:
            raise ContractError("报告必须依赖实际证据材料；不能只有未取证的正文")
        if kind == "source":
            metadata = item.get("metadata", {})
            required(metadata.get("origin"), "source.metadata.origin")
            if metadata.get("access") not in {"abstract", "full-text", "data", "code"}:
                raise ContractError("来源必须声明实际访问层级，不自动把全文下载视为精读")
        else:
            metadata = item.get("metadata", {})
        if "reader_contract" in metadata:
            from .reader import validate_contract
            if kind not in REPORTS:
                raise ContractError("reader_contract 绑定正式报告，不替代来源阅读状态")
            validate_contract(metadata["reader_contract"])
        if (versions and versions[-1].get("metadata", {}).get("reader_contract")
                and versions[-1]['metadata']['reader_contract'] != metadata.get('reader_contract')):
            required(metadata.get("reader_contract_change_reason"),
                     "变更或移除原有读者契约须显式说明 reader_contract_change_reason")
        if kind == "figure" and metadata.get("format") not in {"png", "jpg", "svg", "webp"}:
            raise ContractError("方法图须标明可导出的 format: png/jpg/svg/webp")
        content = item.get("content")
        if isinstance(content, str):
            content = content.encode("utf-8")
        if not isinstance(content, bytes) or not content:
            raise ContractError("材料内容不能为空")
        checksum = self.store.put_blob(content)
        contributors = sorted({actor, *(versions[-1]["contributors"] if versions else [])})
        return {"key": key, "version": len(versions) + 1, "kind": kind,
                "title": required(item.get("title", key), "title"), "sha256": checksum,
                "parents": parents, "context_refs": default_inputs,
                "contributors": contributors, "metadata": metadata}

    def capture(self, item: dict, actor: str) -> dict:
        from .history import bind_system
        system_id = bind_system(self.store)
        identifier(actor, "actor")
        box = {}
        def build(state: dict) -> list:
            artifact = self._artifact(state, item, actor, [])
            artifact["system_id"] = system_id
            box.update(artifact)
            return [("artifact.captured", artifact)]
        self.store.commit(build)
        self.store.export()
        return box

    def _review_events(self, state: dict, data: dict, actor: str) -> list:
        review = validate_review(state, data, actor)
        review["id"] = uid("review")
        events = [("review.recorded", review)]
        for finding in review.get("findings", []):
            finding = {**finding, "id": uid("finding"), "review_id": review["id"],
                       "target_key": review["target"]["key"], "target_version": review["target"]["version"],
                       "status": "open"}
            events.append(("finding.created", finding))
            task = self._task(state, finding["role"], finding["action"], finding["closure_check"],
                              review["reviewed_refs"], finding_id=finding["id"],
                              target_key=finding["target_key"], action="repair")
            events.append(("task.created", task))
        for resolution in review.get("resolutions", []):
            if resolution["disposition"] != "retained":
                events.append(("finding.resolved", {"id": resolution["finding_id"],
                    "status": resolution["disposition"], "resolution": resolution,
                    "resolved_by": actor, "resolution_review": review["id"]}))
        return events

    def review(self, data: dict, reviewer: str) -> dict:
        from .history import bind_system
        data = {**data, "system_id": bind_system(self.store)}
        return self.store.commit(lambda state: self._review_events(state, data, reviewer))

    def claim(self, task_id: str, worker: str) -> dict:
        from .history import bind_system
        system_id = bind_system(self.store)
        identifier(worker, "worker")
        box = {}
        def build(state: dict) -> list:
            task = state["tasks"].get(task_id)
            if not task or task["status"] != "pending":
                raise ContractError("只能领取 pending 任务")
            if any(state["tasks"][key]["status"] != "completed" for key in task["dependencies"]):
                raise ContractError("前置任务未完成")
            if any(not fresh(state, value) for value in task["inputs"]):
                raise ContractError("任务输入已过期；先重规划，不能盲目继续")
            if task["role"] == "reviewer":
                for value in task["inputs"]:
                    artifact = resolve(state, value)
                    if artifact["kind"] in REPORTS and worker in artifact["contributors"]:
                        raise ContractError("配置的评审 Worker 是该报告贡献者")
            box.update(task, worker=worker, status="running", attempts=task["attempts"] + 1,
                       system_id=system_id,
                       base_artifact_versions={key: values[-1]["version"] for key, values in state["artifacts"].items()},
                       base_node_versions={key: values[-1]["version"] for key, values in state["nodes"].items()})
            return [("task.updated", box)]
        self.store.commit(build)
        return box

    def request(self, task_id: str) -> dict:
        state = self.store.read()
        task = state["tasks"][task_id]
        package_root = Path(__file__).resolve().parents[1]
        materials = []
        for value in task["inputs"]:
            artifact = resolve(state, value)
            materials.append({**artifact, "path": str(self.store.internal / "blobs" / artifact["sha256"])})
        # 不传生成者自评分；提供原始证据、待评正文和待复核问题。
        return {"protocol": VERSION, "project": state["project"], "task": task,
                "system_snapshot": state["systems"].get(task.get("system_id")),
                "root_instructions": str(package_root.parent / "AGENTS.md"),
                "skills": [str(package_root / "skills" / name / "SKILL.md") for name in SKILLS[task["role"]]],
                "materials": materials, "knowledge": state["nodes"], "relations": state["edges"],
                "open_findings": [f for f in state["findings"].values() if f["status"] == "open"],
                "authority": {"experiments": False, "paid_resources": False, "external_publication": False},
                "response_contract": str(package_root / "runtime" / "README.md")}

    def submit(self, task_id: str, worker: str, response: dict) -> dict:
        from .history import manifest, system_files
        current_system = manifest(system_files())["id"]
        def build(state: dict) -> list:
            task = state["tasks"].get(task_id)
            if not task or task["status"] != "running" or task["worker"] != worker:
                raise ContractError("任务必须由领取它的 Worker 回交")
            if task["system_id"] != current_system:
                raise ContractError("任务执行期间 Agent 实现或 Skills 已变化；请对账后重跑，不能混用版本")
            if any(not fresh(state, value) for value in task["inputs"]):
                raise ContractError("执行期间证据发生变化，结果不能直接提交")
            required(response.get("summary"), "summary")
            if response.get("status") == "blocked":
                required(response.get("needed"), "needed")
                return [("task.updated", {"id": task_id, "status": "blocked", "result": response})]
            if response.get("status") != "completed":
                raise ContractError("返回状态必须为 completed 或 blocked")
            events = []
            # 在同一事务的临时视图中依次验证新对象，允许一个结果包含相互关联的材料。
            working = state
            def add(kind: str, data: dict) -> None:
                nonlocal working
                events.append((kind, data))
                if kind == "artifact.captured":
                    working = {**working, "artifacts": {**working["artifacts"]}}
                    working["artifacts"][data["key"]] = [*working["artifacts"].get(data["key"], []), data]
                elif kind == "node.recorded":
                    working = {**working, "nodes": {**working["nodes"]}}
                    working["nodes"][data["id"]] = [*working["nodes"].get(data["id"], []), data]
                elif kind == "task.created":
                    working = {**working, "tasks": {**working["tasks"], data["id"]: data}}
            artifacts = response.get("artifacts", [])
            if task["role"] == "reviewer" and (artifacts or response.get("nodes") or response.get("tasks")):
                raise ContractError("评审上下文只回交判断，不代写报告或自行整改")
            output_keys = set()
            for item in artifacts:
                key = item.get("key")
                if key in output_keys:
                    raise ContractError("同一次提交不能重复改写同一材料")
                output_keys.add(key)
                current_version = state["artifacts"].get(key, [{}])[-1].get("version", 0)
                if current_version != task["base_artifact_versions"].get(key, 0):
                    raise ContractError("另一个任务已修改目标材料；请合并意见后重做，不能后写覆盖")
                artifact = self._artifact(working, item, worker, task["inputs"])
                artifact["system_id"] = task["system_id"]
                add("artifact.captured", artifact)
            output_nodes = set()
            for item in response.get("nodes", []):
                identifier(item.get("id"), "node.id")
                if item["id"] in output_nodes:
                    raise ContractError("同一次提交不能重复改写同一知识节点")
                output_nodes.add(item["id"])
                current_version = state["nodes"].get(item["id"], [{}])[-1].get("version", 0)
                if current_version != task["base_node_versions"].get(item["id"], 0):
                    raise ContractError("知识节点存在并发修订，须显式综合")
                if item.get("kind") not in NODE_KINDS:
                    raise ContractError("未知知识节点类型")
                required(item.get("text"), "node.text")
                if item.get("epistemic") not in {"reported", "derived", "inference", "proposal"}:
                    raise ContractError("知识节点须区分来源事实、推导、推断和假设")
                evidence = item.get("evidence", [])
                if item["epistemic"] != "proposal" and not evidence:
                    raise ContractError("非假设知识必须关联证据")
                for value in evidence:
                    resolve(working, value, current=True)
                    required(value.get("locator"), "node.evidence.locator")
                old = working["nodes"].get(item["id"], [])
                if old:
                    required(item.get("change_reason"), "知识修订原因")
                    if item["kind"] != old[-1]["kind"]:
                        raise ContractError("知识节点不能更换种类")
                add("node.recorded", {**item, "version": len(old) + 1, "author": worker})
            for edge in response.get("edges", []):
                for endpoint in ("from", "to"):
                    value = edge.get(endpoint, {})
                    versions = working["nodes"].get(value.get("id"), [])
                    if type(value.get("version")) is not int or not 1 <= value["version"] <= len(versions):
                        raise ContractError("知识关系必须指向明确的节点版本")
                required(edge.get("relation"), "edge.relation")
                required(edge.get("reason"), "edge.reason")
                add("edge.recorded", {**edge, "author": worker})
            if "review" in response:
                if task["role"] != "reviewer":
                    raise ContractError("生成角色不能提交独立评审")
                target_key = task.get("target_key")
                if target_key and response["review"]["target"]["key"] != target_key:
                    raise ContractError("评审目标与任务不一致")
                events.extend(self._review_events(working, {**response["review"], "system_id": task["system_id"]}, worker))
            elif task["role"] == "reviewer":
                raise ContractError("评审任务必须回交结构化 review")
            for item in response.get("tasks", []):
                new_task = self._task(working, item["role"], item["objective"], item["acceptance"],
                                      item.get("inputs", []), dependencies=item.get("dependencies", []))
                add("task.created", new_task)
            if not events:
                raise ContractError("完成任务需要实际材料、证据、评审或后继动作，不能只有总结")
            events.append(("task.updated", {"id": task_id, "status": "completed", "summary": response["summary"]}))
            return events
        result = self.store.commit(build)
        self.store.export()
        return result

    def recover(self, task_id: str, reason: str, *, retry: bool) -> dict:
        def build(state: dict) -> list:
            task = state["tasks"].get(task_id)
            if not task or task["status"] not in {"running", "blocked", "failed"}:
                raise ContractError("只能人工对账 running/blocked/failed 任务")
            return [("task.updated", {"id": task_id, "status": "pending" if retry else "cancelled",
                                      "recovery_reason": required(reason, "reason"), "worker": None})]
        return self.store.commit(build)

    def maintain(self) -> dict:
        """把材料变化和评审缺口变成任务；不以调度成功代替内容通过。"""
        def build(state: dict) -> list:
            events = []
            active = [t for t in state["tasks"].values() if t["status"] in {"pending", "running", "blocked", "failed"}]
            for task in active:
                if task["status"] == "pending" and any(not fresh(state, value) for value in task["inputs"]):
                    events.append(("task.updated", {"id": task["id"], "status": "cancelled", "reason": "input-version-changed"}))
            active = [t for t in active if not any(data.get("id") == t["id"] for _, data in events)]
            cancelled = [data["id"] for kind, data in events if kind == "task.updated"
                         and not state["tasks"][data["id"]].get("target_key")]
            if cancelled and not any(task["role"] == "leader" for task in active):
                inputs = [ref(values[-1]) for values in state["artifacts"].values()
                          if values[-1]["kind"] not in REPORTS and fresh(state, ref(values[-1]))]
                task = self._task(state, "leader", "输入更新导致旧任务失效：" + ", ".join(cancelled)
                                  + "。根据最新证据重排未解决问题，不能遗漏原任务需要回答的问题。",
                                  "为失效任务的问题给出替代取证动作或有证据的撤回理由。", inputs, action="replan")
                events.append(("task.created", task))
            for key, values in state["artifacts"].items():
                artifact = values[-1]
                if artifact["kind"] not in REPORTS or any(t.get("target_key") == key for t in active):
                    continue
                status = report_status(state, artifact["kind"])["status"]
                if status == "unreviewed":
                    task = self._task(state, "reviewer", "独立阅读正文及原始证据，执行内容核验；复核待关闭问题。",
                                      "提交版本绑定的六维评审、理解核验与可执行问题；不自签生成结论。",
                                      bundle(state, ref(artifact)), target_key=key, action="review")
                    events.append(("task.created", task))
                elif status == "stale":
                    # 使用当前证据闭包的叶材料，而不是把已过期报告再次当成可信输入。
                    inputs = [ref(v[-1]) for v in state["artifacts"].values()
                              if v[-1]["kind"] not in REPORTS and fresh(state, ref(v[-1]))]
                    if artifact["kind"] == "proposal":
                        inputs += [ref(v[-1]) for v in state["artifacts"].values()
                                   if v[-1]["kind"] == "literature" and fresh(state, ref(v[-1]))]
                    role = "synthesizer" if artifact["kind"] == "literature" else "designer"
                    task = self._task(state, role, f"上游证据变化，重新核验并更新 {key}；保留未受影响的理解，解释实质变化。",
                                      "新报告绑定当前证据；受影响主张重新判断，不只更换引用哈希。",
                                      inputs, target_key=key, action="refresh")
                    events.append(("task.created", task))
                elif status == "revise":
                    # 整改任务结束不关闭问题。若未产出新正文，返回负责人处理，避免假循环。
                    task = self._task(state, "leader", f"{key} 仍未通过内容审查；读取未解决问题和整改产物，分派补证/改写或说明真实阻塞。",
                                      "产生解决未通过维度的实际后继动作；不宣称任务结束即通过。",
                                      bundle(state, ref(artifact)), target_key=key, action="replan")
                    events.append(("task.created", task))
            if state["project"]["outcome"] == "both" and not any(
                values[-1]["kind"] == "proposal" for values in state["artifacts"].values()
            ) and not any(t["role"] == "designer" for t in active):
                literature = report_status(state, "literature")
                if literature["status"] == "review-cleared":
                    task = self._task(state, "designer", "依据已核验的调研构建竞争候选，比较直接近邻，产出具体可检验的方案设计。",
                                      "明确机制、实现、决定性检验、失败后果与资源限制，候选比较有来源。",
                                      bundle(state, literature["target"]), action="design")
                    events.append(("task.created", task))
            return events
        return self.store.commit(build)

    def status(self) -> dict:
        state = self.store.read()
        return {"topic": state["project"]["topic"], "revision": state["revision"],
                "quality": quality_status(state), "tasks": list(state["tasks"].values()),
                "open_findings": [f for f in state["findings"].values() if f["status"] == "open"],
                "last_pause": state["pauses"][-1] if state["pauses"] else None}
