"""SQLite 事务事件日志 + 按内容寻址的快照。事件是唯一机器事实源。"""

from __future__ import annotations

import json
import os
from pathlib import Path
import sqlite3
import tempfile
from datetime import datetime, timezone
from typing import Callable

from .contracts import ContractError, REPORTS, VERSION, canonical, digest, identifier


def reduce_events(events: list[dict]) -> dict:
    state = {"revision": 0, "project": None, "artifacts": {}, "tasks": {},
             "reviews": {}, "findings": {}, "nodes": {}, "edges": [], "pauses": [],
             "systems": {}, "checkpoints": {}}
    for event in events:
        kind, data = event["kind"], event["data"]
        if kind == "project.created":
            state["project"] = data
        elif kind == "artifact.captured":
            state["artifacts"].setdefault(data["key"], []).append(data)
        elif kind == "task.created":
            state["tasks"][data["id"]] = data
        elif kind == "task.updated":
            state["tasks"][data["id"]].update(data)
        elif kind == "review.recorded":
            state["reviews"][data["id"]] = data
        elif kind == "finding.created":
            state["findings"][data["id"]] = data
        elif kind == "finding.resolved":
            state["findings"][data["id"]].update(data)
        elif kind == "node.recorded":
            state["nodes"].setdefault(data["id"], []).append(data)
        elif kind == "edge.recorded":
            state["edges"].append(data)
        elif kind == "run.paused":
            state["pauses"].append(data)
        elif kind == "system.captured":
            state["systems"][data["id"]] = data
        elif kind == "checkpoint.created":
            state["checkpoints"][data["id"]] = data
        else:
            raise ContractError(f"未知事件类型: {kind}")
        state["revision"] = event["seq"]
    if state["project"] and state["project"]["contract"] != VERSION:
        raise ContractError("项目协议不匹配；需要显式迁移，不继承旧验收")
    return state


class Store:
    def __init__(self, project: str | Path):
        self.root = Path(project).resolve()
        self.internal = self.root / ".rsi"
        self.database = self.internal / "state.sqlite3"

    def _connect(self) -> sqlite3.Connection:
        if not self.database.is_file():
            raise ContractError("项目未初始化；请先运行 init")
        connection = sqlite3.connect(self.database, timeout=30)
        connection.execute("PRAGMA journal_mode=WAL")
        return connection

    @staticmethod
    def _events(connection: sqlite3.Connection) -> list[dict]:
        previous, result = "0" * 64, []
        for seq, body, parent, checksum in connection.execute("SELECT seq,body,parent,digest FROM events ORDER BY seq"):
            if parent != previous or digest((parent + body).encode()) != checksum:
                raise ContractError(f"事件链损坏: {seq}")
            event = json.loads(body)
            if event["seq"] != seq:
                raise ContractError("事件序号不一致")
            result.append(event)
            previous = checksum
        return result

    def read(self) -> dict:
        connection = self._connect()
        try:
            return reduce_events(self._events(connection))
        finally:
            connection.close()

    def commit(self, build: Callable[[dict], list[tuple[str, dict]]], *, expected: int | None = None) -> dict:
        connection = self._connect()
        try:
            connection.execute("BEGIN IMMEDIATE")
            events = self._events(connection)
            state = reduce_events(events)
            if expected is not None and expected != state["revision"]:
                raise ContractError("状态已变化；重新读取后提交，禁止覆盖其他 Agent 的工作")
            additions = build(state)
            last = connection.execute("SELECT digest FROM events ORDER BY seq DESC LIMIT 1").fetchone()
            parent = last[0] if last else "0" * 64
            seq = state["revision"]
            for kind, data in additions:
                seq += 1
                event = {"seq": seq, "kind": kind, "data": data,
                         "time": datetime.now(timezone.utc).isoformat()}
                body = canonical(event)
                checksum = digest((parent + body).encode())
                connection.execute("INSERT INTO events VALUES(?,?,?,?)", (seq, body, parent, checksum))
                events.append(event)
                parent = checksum
            result = reduce_events(events)
            connection.commit()
            return result
        except BaseException:
            connection.rollback()
            raise
        finally:
            connection.close()

    def initialize(self, topic: str, outcome: str) -> dict:
        if not topic.strip() or outcome not in {"literature", "proposal", "both"}:
            raise ContractError("需要非空研究方向，交付选择 literature/proposal/both")
        if self.internal.exists():
            raise ContractError("已有 .rsi，不能重新初始化或覆盖")
        if any((self.root / "outputs" / name).exists() for name in REPORTS.values()):
            raise ContractError("已有同名报告；请指定新目录或显式导入材料，避免覆盖")
        self.internal.mkdir(parents=True)
        with sqlite3.connect(self.database) as connection:
            connection.execute("CREATE TABLE events(seq INTEGER PRIMARY KEY, body TEXT NOT NULL, parent TEXT NOT NULL, digest TEXT NOT NULL)")
        return self.commit(lambda _: [("project.created", {
            "topic": topic, "outcome": outcome, "contract": VERSION,
            "execution_authorized": False,
        })])

    def put_blob(self, content: bytes) -> str:
        if len(content) > 64 * 1024 * 1024:
            raise ContractError("单份材料超过 64 MiB；先分割或使用外部受控存储")
        checksum = digest(content)
        directory = self.internal / "blobs"
        directory.mkdir(parents=True, exist_ok=True)
        target = directory / checksum
        if target.exists():
            if digest(target.read_bytes()) != checksum:
                raise ContractError("已有快照遭到修改")
            return checksum
        fd, temporary = tempfile.mkstemp(prefix="capture-", dir=directory)
        try:
            with os.fdopen(fd, "wb") as handle:
                handle.write(content)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temporary, target)
        finally:
            if os.path.exists(temporary):
                os.unlink(temporary)
        return checksum

    def blob(self, checksum: str) -> bytes:
        if len(checksum) != 64 or any(char not in "0123456789abcdef" for char in checksum):
            raise ContractError("非法快照哈希")
        content = (self.internal / "blobs" / checksum).read_bytes()
        if digest(content) != checksum:
            raise ContractError("材料快照损坏")
        return content

    def export(self) -> dict:
        """报告是快照的派生视图；不把手改正文冒充已评审版本。"""
        state = self.read()
        outputs = self.root / "outputs"
        if outputs.is_symlink():
            raise ContractError("outputs 不能是指向其他位置的符号链接")
        outputs.mkdir(exist_ok=True)
        paths, conflicts = [], []
        for versions in state["artifacts"].values():
            for figure in versions:
                if figure["kind"] != "figure":
                    continue
                assets = outputs / "assets"
                if assets.is_symlink():
                    raise ContractError("assets 不能是符号链接")
                assets.mkdir(exist_ok=True)
                name = f"{figure['key']}-v{figure['version']}.{figure['metadata']['format']}"
                path = assets / name
                if path.is_symlink():
                    raise ContractError("图片导出路径不能是符号链接")
                content = self.blob(figure["sha256"])
                if path.exists() and digest(path.read_bytes()) != figure["sha256"]:
                    conflicts.append(str(path))
                    continue
                if not path.exists():
                    path.write_bytes(content)
                paths.append(str(path))
            artifact = versions[-1]
            if artifact["kind"] not in REPORTS:
                continue
            name = REPORTS[artifact["kind"]]
            path = outputs / name
            if path.is_symlink():
                raise ContractError("交付路径不能是符号链接")
            if path.exists() and digest(path.read_bytes()) not in {value["sha256"] for value in versions}:
                conflicts.append(str(path))
                continue
            fd, temporary = tempfile.mkstemp(prefix="export-", dir=outputs)
            try:
                with os.fdopen(fd, "wb") as handle:
                    handle.write(self.blob(artifact["sha256"]))
                os.replace(temporary, path)
            finally:
                if os.path.exists(temporary):
                    os.unlink(temporary)
            paths.append(str(path))
        return {"exported": paths, "conflicts": conflicts}

    def audit(self) -> dict:
        state = self.read()
        checked = set()
        for versions in state["artifacts"].values():
            for artifact in versions:
                self.blob(artifact["sha256"])
                checked.add(artifact["sha256"])
        for system in state["systems"].values():
            for checksum in system["files"].values():
                self.blob(checksum)
                checked.add(checksum)
        changed = []
        for versions in state["artifacts"].values():
            for figure in versions:
                if figure["kind"] == "figure":
                    filename = f"{figure['key']}-v{figure['version']}.{figure['metadata']['format']}"
                    path = self.root / "outputs" / "assets" / filename
                    if not path.is_file() or digest(path.read_bytes()) != figure["sha256"]:
                        changed.append(str(path))
            artifact = versions[-1]
            if artifact["kind"] in REPORTS:
                path = self.root / "outputs" / REPORTS[artifact["kind"]]
                if not path.is_file() or digest(path.read_bytes()) != artifact["sha256"]:
                    changed.append(str(path))
        return {"event_chain": "valid", "checked_blobs": len(checked),
                "changed_or_missing_exports": changed,
                "scientific_correctness": "not-established-by-structural-audit"}
