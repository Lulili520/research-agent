"""独立进程 Worker；不内置模型、搜索服务、密钥或研究主题。"""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
import json
from pathlib import Path
import subprocess

from .contracts import ContractError, ROLES, VERSION, canonical, identifier, required
from .engine import Engine
from .quality import quality_status


def load_team(path: str | Path) -> dict:
    team = json.loads(Path(path).read_text(encoding="utf-8"))
    if team.get("protocol") != VERSION or not isinstance(team.get("workers"), dict):
        raise ContractError("Team 需要匹配 protocol 和 workers 对象")
    authors, reviewers = set(), set()
    for role, config in team["workers"].items():
        if role not in ROLES:
            raise ContractError(f"未知角色: {role}")
        identifier(config.get("id"), "worker.id")
        command = config.get("command")
        if not isinstance(command, list) or not command or any(not isinstance(x, str) or not x for x in command):
            raise ContractError("Worker command 必须是非空 argv 数组；不经 shell 执行")
        timeout = config.get("timeout_seconds", 300)
        if type(timeout) is not int or not 1 <= timeout <= 3600:
            raise ContractError("timeout_seconds 应在 1..3600")
        if role == "reviewer":
            reviewers.add(config["id"])
            if config.get("context_isolation") != "fresh-process":
                raise ContractError("评审必须声明 fresh-process；适配器须真正隔离会话")
        else:
            authors.add(config["id"])
    if authors & reviewers:
        raise ContractError("评审与生成 Worker 不能共用身份")
    return team


def run_worker(config: dict, request: dict) -> dict:
    completed = subprocess.run(
        config["command"], input=canonical(request), text=True, encoding="utf-8",
        stdout=subprocess.PIPE, stderr=subprocess.PIPE, shell=False,
        timeout=config.get("timeout_seconds", 300), check=False,
    )
    if completed.returncode:
        # 不回显 stderr，避免泄露适配器环境或令牌。
        raise ContractError(f"Worker 退出码 {completed.returncode}；请在本地检查适配器日志")
    if len(completed.stdout.encode()) > 16 * 1024 * 1024:
        raise ContractError("Worker 响应超过 16 MiB")
    response = json.loads(completed.stdout)
    if not isinstance(response, dict):
        raise ContractError("Worker 必须返回单个 JSON 对象")
    return response


def run(engine: Engine, team: dict, *, max_tasks: int = 20, parallel: int = 3) -> dict:
    if type(max_tasks) is not int or max_tasks < 1 or type(parallel) is not int or not 1 <= parallel <= 16:
        raise ContractError("max_tasks 必须为正整数，parallel 为 1..16")
    count = 0

    def pause(reason: str, detail: str) -> dict:
        engine.store.commit(lambda _: [("run.paused", {"reason": reason, "detail": detail,
                                                        "tasks_executed": count})])
        return {"run_status": reason, "tasks_executed": count, **engine.status()}

    while count < max_tasks:
        state = engine.maintain()
        tasks = list(state["tasks"].values())
        if any(task["status"] == "running" for task in tasks):
            return pause("needs-reconciliation", "存在上次中断的 running 任务；核验外部副作用后显式恢复，不自动重复执行")
        if quality_status(state)["ready"] and not any(t["status"] in {"pending", "blocked", "failed"} for t in tasks):
            exported = engine.store.export()
            if exported["conflicts"]:
                return pause("output-conflict", "输出存在未登记的用户修改；先捕获为新版本，不能覆盖或冒充已审阅")
            return {"run_status": "review-cleared", "tasks_executed": count, **engine.status()}
        pending = [task for task in tasks if task["status"] == "pending" and all(
            state["tasks"][key]["status"] == "completed" for key in task["dependencies"])]
        if not pending:
            return pause("blocked", "当前没有可执行任务；查看被阻塞任务或补充证据动作，不代表质量通过")
        # 同一正文的整改串行，独立分支可并行。合并冲突时保留结果状态并要求对账。
        selected, targets = [], set()
        for task in pending:
            target = task.get("target_key")
            if target and target in targets:
                continue
            if task["role"] not in team["workers"]:
                continue
            selected.append(task)
            if target:
                targets.add(target)
            if len(selected) >= min(parallel, max_tasks - count):
                break
        if not selected:
            missing = sorted({task["role"] for task in pending})
            return pause("missing-worker", f"缺少已配置的角色适配器: {', '.join(missing)}")
        with ThreadPoolExecutor(max_workers=len(selected)) as pool:
            futures = []
            for task in selected:
                config = team["workers"][task["role"]]
                engine.claim(task["id"], config["id"])
                futures.append((task, config, pool.submit(run_worker, config, engine.request(task["id"]))))
            for task, config, future in futures:
                count += 1
                try:
                    response = future.result()
                    engine.submit(task["id"], config["id"], response)
                except (OSError, ValueError, RuntimeError, subprocess.TimeoutExpired, KeyError, TypeError) as error:
                    engine.store.commit(lambda _, task=task, error=error: [("task.updated", {
                        "id": task["id"], "status": "failed", "error": type(error).__name__ + ": " + str(error)[:500],
                    })])
    # 预算耗尽与研究成功是两种事实，即使最后一份评审刚到，也单独返回质量状态。
    return pause("paused-budget", "本轮执行预算用尽；已保存进度，未据此宣布科研完成")
