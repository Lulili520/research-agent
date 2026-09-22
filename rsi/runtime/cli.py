"""独立 RSI 的命令行；本地运行不要求外部服务。"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from .contracts import ContractError, REPORTS, ROLES
from .engine import Engine
from .history import VersionLibrary, checkpoint, compare, restore
from .workers import load_team, run


def load(path: str):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def parser() -> argparse.ArgumentParser:
    root = argparse.ArgumentParser(description=__doc__)
    commands = root.add_subparsers(dest="command", required=True)
    init = commands.add_parser("init", help="创建独立课题；不覆盖历史目录")
    init.add_argument("project")
    init.add_argument("--topic", required=True)
    init.add_argument("--outcome", choices=["literature", "proposal", "both"], default="both")
    for name in ("status", "audit", "export", "maintain", "history"):
        command = commands.add_parser(name)
        command.add_argument("project")
    capture = commands.add_parser("capture", help="将真实来源/报告保存为不可变版本")
    capture.add_argument("project")
    capture.add_argument("--record", required=True, help="材料 JSON，包含 content 或 content_file")
    capture.add_argument("--actor", required=True)
    task = commands.add_parser("task", help="增加证据或设计任务")
    task.add_argument("project")
    task.add_argument("--record", required=True)
    claim = commands.add_parser("claim", help="宿主 Agent 领取任务并读取请求")
    claim.add_argument("project")
    claim.add_argument("task_id")
    claim.add_argument("--worker", required=True)
    submit = commands.add_parser("submit", help="提交被领取任务的结构化结果")
    submit.add_argument("project")
    submit.add_argument("task_id")
    submit.add_argument("--worker", required=True)
    submit.add_argument("--response", required=True)
    review = commands.add_parser("review", help="登记独立的人工/宿主评审")
    review.add_argument("project")
    review.add_argument("--record", required=True)
    review.add_argument("--reviewer", required=True)
    recovery = commands.add_parser("recover", help="对账中断任务，再决定重试或取消")
    recovery.add_argument("project")
    recovery.add_argument("task_id")
    recovery.add_argument("--reason", required=True)
    choice = recovery.add_mutually_exclusive_group(required=True)
    choice.add_argument("--retry", action="store_true")
    choice.add_argument("--cancel", action="store_true")
    execute = commands.add_parser("run", help="调用实际 Worker，自主推进直到通过、阻塞或预算耗尽")
    execute.add_argument("project")
    execute.add_argument("--team", required=True)
    execute.add_argument("--max-tasks", type=int, default=20)
    execute.add_argument("--parallel", type=int, default=3)
    check = commands.add_parser("checkpoint", help="保存带评估的研究历史节点")
    check.add_argument("project")
    check.add_argument("--label", required=True)
    check.add_argument("--reason", required=True)
    check.add_argument("--parent", action="append")
    diff = commands.add_parser("diff")
    diff.add_argument("project")
    diff.add_argument("key")
    diff.add_argument("before", type=int)
    diff.add_argument("after", type=int)
    rollback = commands.add_parser("restore", help="旧内容生成新版本；不恢复旧验收")
    rollback.add_argument("project")
    rollback.add_argument("key")
    rollback.add_argument("version", type=int)
    rollback.add_argument("--actor", required=True)
    rollback.add_argument("--reason", required=True)
    system = commands.add_parser("system", help="跨课题维护 Agent 候选版本及独立对照评估")
    system.add_argument("--library", required=True)
    sub = system.add_subparsers(dest="operation", required=True)
    snapshot = sub.add_parser("snapshot")
    snapshot.add_argument("--root", default=".")
    snapshot.add_argument("--label", required=True)
    snapshot.add_argument("--hypothesis", required=True)
    snapshot.add_argument("--author", required=True)
    snapshot.add_argument("--parent")
    evaluation = sub.add_parser("evaluate")
    evaluation.add_argument("--result", required=True)
    evaluation.add_argument("--assessor", required=True)
    promotion = sub.add_parser("promote")
    promotion.add_argument("evaluation_id")
    promotion.add_argument("--reason", required=True)
    back = sub.add_parser("rollback")
    back.add_argument("version")
    back.add_argument("--reason", required=True)
    checkout = sub.add_parser("checkout")
    checkout.add_argument("version")
    checkout.add_argument("destination")
    sub.add_parser("audit")
    sub.add_parser("list")
    return root


def execute(args):
    if args.command == "system":
        library = VersionLibrary(args.library)
        if args.operation == "snapshot":
            return library.snapshot(Path(args.root), args.label, args.hypothesis, args.author, args.parent)
        if args.operation == "evaluate":
            return library.evaluate(load(args.result), args.assessor)
        if args.operation == "promote":
            return library.promote(args.evaluation_id, args.reason)
        if args.operation == "rollback":
            return library.rollback(args.version, args.reason)
        if args.operation == "checkout":
            return library.checkout(args.version, Path(args.destination))
        if args.operation == "audit":
            return library.audit()
        return library.records()
    engine = Engine(args.project)
    if args.command == "init":
        return engine.initialize(args.topic, args.outcome)
    if args.command == "capture":
        record = load(args.record)
        if "content_file" in record:
            if "content" in record:
                raise ContractError("content 和 content_file 不能同时出现")
            source = Path(record.pop("content_file"))
            if not source.is_absolute():
                source = Path(args.record).resolve().parent / source
            record["content"] = source.read_bytes()
        return engine.capture(record, args.actor)
    if args.command == "task":
        return engine.add_task(**load(args.record))
    if args.command == "claim":
        engine.claim(args.task_id, args.worker)
        return engine.request(args.task_id)
    if args.command == "submit":
        engine.submit(args.task_id, args.worker, load(args.response))
        return engine.status()
    if args.command == "review":
        engine.review(load(args.record), args.reviewer)
        return engine.status()
    if args.command == "recover":
        engine.recover(args.task_id, args.reason, retry=args.retry)
        return engine.status()
    if args.command == "run":
        return run(engine, load_team(args.team), max_tasks=args.max_tasks, parallel=args.parallel)
    if args.command == "checkpoint":
        return checkpoint(engine, args.label, args.reason, args.parent)
    if args.command == "diff":
        return compare(engine, args.key, args.before, args.after)
    if args.command == "restore":
        return restore(engine, args.key, args.version, args.actor, args.reason)
    if args.command == "audit":
        return {"integrity": engine.store.audit(), "state": engine.status()}
    if args.command == "export":
        return engine.store.export()
    if args.command == "maintain":
        engine.maintain()
        return engine.status()
    if args.command == "history":
        state = engine.store.read()
        return {key: state[key] for key in ("checkpoints", "systems", "artifacts", "nodes", "reviews", "findings")}
    return engine.status()


def main() -> None:
    args = parser().parse_args()
    try:
        print(json.dumps(execute(args), ensure_ascii=False, indent=2))
    except (ContractError, OSError, KeyError, TypeError, json.JSONDecodeError) as error:
        raise SystemExit(f"RSI: {error}") from error
