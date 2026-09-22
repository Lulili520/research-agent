"""研究检查点与 Agent 版本库。候选、比较结果、接纳决策各自留痕。"""

from __future__ import annotations

from difflib import unified_diff
import json
from pathlib import Path
import sqlite3
from datetime import datetime, timezone

from .contracts import ContractError, canonical, digest, identifier, ref, required
from .quality import quality_status


def system_files(root: Path | None = None) -> dict[str, bytes]:
    root = root or Path(__file__).resolve().parents[2]
    paths = [root / "AGENTS.md"]
    paths += [path for path in (root / "rsi").rglob("*")
              if path.is_file() and "__pycache__" not in path.parts
              and path.suffix in {".py", ".md", ".json", ".yaml"}]
    return {str(path.relative_to(root)): path.read_bytes() for path in sorted(paths) if path.is_file()}


def manifest(files: dict[str, bytes]) -> dict:
    entries = {path: digest(content) for path, content in files.items()}
    return {"id": digest(canonical(entries).encode()), "files": entries}


def bind_system(store) -> str:
    files = system_files()
    snapshot = manifest(files)
    state = store.read()
    if snapshot["id"] not in state["systems"]:
        for content in files.values():
            store.put_blob(content)
        store.commit(lambda current: [] if snapshot["id"] in current["systems"] else [("system.captured", snapshot)])
    return snapshot["id"]


def checkpoint(engine, label: str, reason: str, parents: list[str] | None = None) -> dict:
    system_id = bind_system(engine.store)
    box = {}
    def build(state: dict) -> list:
        lineage = parents
        if lineage is None:
            lineage = list(state["checkpoints"])[-1:]
        for parent in lineage:
            if parent not in state["checkpoints"]:
                raise ContractError("检查点父版本不存在")
        item = {"label": required(label, "label"), "reason": required(reason, "reason"),
                "parents": lineage, "state_revision": state["revision"], "system_id": system_id,
                "artifacts": [ref(values[-1]) for values in state["artifacts"].values()],
                "nodes": [{"id": key, "version": values[-1]["version"]} for key, values in state["nodes"].items()],
                "quality": quality_status(state),
                "open_findings": [key for key, value in state["findings"].items() if value["status"] == "open"]}
        item["id"] = "checkpoint-" + digest(canonical(item).encode())[:24]
        if item["id"] in state["checkpoints"]:
            raise ContractError("检查点已存在；请说明新的变化")
        box.update(item)
        return [("checkpoint.created", item)]
    engine.store.commit(build)
    return box


def restore(engine, key: str, version: int, actor: str, reason: str) -> dict:
    state = engine.store.read()
    versions = state["artifacts"].get(key, [])
    if not 1 <= version <= len(versions):
        raise ContractError("待恢复版本不存在")
    artifact = versions[version - 1]
    # 不能自动把旧证据替换成新来源后继续沿用旧结论。
    # 允许恢复正文，但原始依赖保持旧版本；freshness 会要求重新核验。
    checksum = engine.store.put_blob(engine.store.blob(artifact["sha256"]))
    # 恢复的是旧内容及其来源，不把当前用户的读者要求一起降回旧标准。
    metadata = dict(artifact.get("metadata", {}))
    current_reader = versions[-1].get("metadata", {}).get("reader_contract")
    if current_reader is not None:
        metadata["reader_contract"] = current_reader
        metadata["reader_contract_change_reason"] = "恢复旧内容，保留当前版本读者要求并重新评审"
    box = {**artifact, "version": len(versions) + 1, "sha256": checksum,
           "metadata": metadata,
           "contributors": sorted({*versions[-1]["contributors"], actor}),
           "restored_from": ref(artifact), "change_reason": required(reason, "reason")}
    identifier(actor)
    engine.store.commit(lambda _: [("artifact.captured", box)], expected=state["revision"])
    engine.store.export()
    return box


def compare(engine, key: str, before: int, after: int) -> dict:
    versions = engine.store.read()["artifacts"].get(key, [])
    if not (1 <= before <= len(versions) and 1 <= after <= len(versions)):
        raise ContractError("对比版本不存在")
    old, new = versions[before - 1], versions[after - 1]
    old_text = engine.store.blob(old["sha256"]).decode("utf-8", errors="replace")
    new_text = engine.store.blob(new["sha256"]).decode("utf-8", errors="replace")
    return {"before": old, "after": new,
            "diff": "".join(unified_diff(old_text.splitlines(True), new_text.splitlines(True),
                                        fromfile=f"{key}@{before}", tofile=f"{key}@{after}"))}


class VersionLibrary:
    """跨课题的框架版本库；不把科研系统开发伪装成一个新研究课题。"""

    def __init__(self, directory: str | Path):
        self.root = Path(directory).resolve()
        self.root.mkdir(parents=True, exist_ok=True)
        self.database = self.root / "versions.sqlite3"
        with self.connect() as connection:
            connection.execute("CREATE TABLE IF NOT EXISTS records(seq INTEGER PRIMARY KEY, kind TEXT NOT NULL, body TEXT NOT NULL, parent TEXT NOT NULL, checksum TEXT NOT NULL)")

    def connect(self):
        connection = sqlite3.connect(self.database, timeout=30)
        connection.execute("PRAGMA journal_mode=WAL")
        return connection

    @staticmethod
    def _read(connection) -> list:
        result, previous = [], "0" * 64
        for kind, body, parent, checksum in connection.execute("SELECT kind,body,parent,checksum FROM records ORDER BY seq"):
            if parent != previous or digest((parent + kind + body).encode()) != checksum:
                raise ContractError("系统版本历史链损坏")
            result.append({"kind": kind, **json.loads(body)})
            previous = checksum
        return result

    def records(self) -> list:
        connection = self.connect()
        try:
            return self._read(connection)
        finally:
            connection.close()

    def _append(self, kind: str, build) -> dict:
        connection = self.connect()
        try:
            connection.execute("BEGIN IMMEDIATE")
            records = self._read(connection)
            item = build(records)
            item["time"] = datetime.now(timezone.utc).isoformat()
            body = canonical(item)
            row = connection.execute("SELECT checksum FROM records ORDER BY seq DESC LIMIT 1").fetchone()
            parent = row[0] if row else "0" * 64
            checksum = digest((parent + kind + body).encode())
            connection.execute("INSERT INTO records(kind,body,parent,checksum) VALUES(?,?,?,?)", (kind, body, parent, checksum))
            connection.commit()
            return {"kind": kind, **item}
        except BaseException:
            connection.rollback()
            raise
        finally:
            connection.close()

    def snapshot(self, root: Path, label: str, hypothesis: str, author: str, parent: str | None = None) -> dict:
        files = system_files(root.resolve())
        if not files or "AGENTS.md" not in files or "rsi/runtime/engine.py" not in files:
            raise ContractError("需要包含新系统代码和 Skills 的仓库根目录")
        item = {**manifest(files), "label": required(label, "label"),
                "hypothesis": required(hypothesis, "hypothesis"), "author": identifier(author), "parent": parent}
        blob_root = self.root / "blobs"
        blob_root.mkdir(exist_ok=True)
        for name, content in files.items():
            target = blob_root / item["files"][name]
            if target.exists():
                if digest(target.read_bytes()) != target.name:
                    raise ContractError("版本库快照已损坏")
            else:
                with target.open("xb") as handle:
                    handle.write(content)
        def build(records):
            snapshots = {r["id"]: r for r in records if r["kind"] == "snapshot"}
            if item["id"] in snapshots:
                raise ContractError("相同内容已有版本；修改标签不构成新版本")
            if parent and parent not in snapshots:
                raise ContractError("系统父版本不存在")
            return item
        return self._append("snapshot", build)

    def evaluate(self, result: dict, assessor: str) -> dict:
        """登记独立、同条件的对照评估，保留不胜出和无法判定。"""
        attachments = result.get("attachments", {})
        if not isinstance(attachments, dict) or not attachments:
            raise ContractError("对照评估需要实际的协议、输入、输出和审阅记录附件，不能只有结论")
        captured = {}
        for name, filename in attachments.items():
            identifier(name, "attachment.id")
            path = Path(required(filename, "attachment.path"))
            if not path.is_file():
                raise ContractError(f"评估附件不存在: {name}")
            content = path.read_bytes()
            if not content or len(content) > 64 * 1024 * 1024:
                raise ContractError("评估附件不能为空或超过 64 MiB")
            checksum = digest(content)
            target = self.root / "blobs" / checksum
            target.parent.mkdir(exist_ok=True)
            if target.exists():
                if digest(target.read_bytes()) != checksum:
                    raise ContractError("已有评估附件损坏")
            else:
                with target.open("xb") as handle:
                    handle.write(content)
            captured[name] = checksum
        def build(records):
            versions = {r["id"]: r for r in records if r["kind"] == "snapshot"}
            baseline, candidate = result.get("baseline"), result.get("candidate")
            if baseline == candidate or baseline not in versions or candidate not in versions:
                raise ContractError("需要不同的已保存基线和候选版本")
            if assessor in {versions[baseline]["author"], versions[candidate]["author"]}:
                raise ContractError("版本作者不能签独立对照评估")
            for field in ("protocol_hash", "cases_hash", "judge_hash"):
                value = result.get(field, "")
                if len(value) != 64 or any(char not in "0123456789abcdef" for char in value):
                    raise ContractError(f"{field} 需要固定协议/任务/评估器的 SHA256")
                if captured.get(field.removesuffix("_hash")) != value:
                    raise ContractError(f"{field} 与实际附件不一致")
            required(result.get("budget"), "budget")
            required(result.get("budget_evidence"), "budget_evidence")
            if result["budget_evidence"] not in captured:
                raise ContractError("budget_evidence 必须指向已捕获的成本记录附件")
            required(result.get("held_out_analysis"), "held_out_analysis")
            required(result.get("limitations"), "limitations")
            if result.get("decision") not in {"adopt", "reject", "inconclusive"}:
                raise ContractError("对照决策为 adopt/reject/inconclusive")
            pairs = result.get("pairs", [])
            if not isinstance(pairs, list) or not pairs:
                raise ContractError("必须提交配对任务的输出及评估记录")
            ids = set()
            for pair in pairs:
                if pair.get("case") in ids:
                    raise ContractError("重复对照任务")
                ids.add(required(pair.get("case"), "case"))
                for field in ("baseline_output", "candidate_output", "evidence", "blind_mapping"):
                    required(pair.get(field), f"pair.{field}")
                    if pair[field] not in captured:
                        raise ContractError(f"pair.{field} 必须引用实际附件")
                if pair.get("outcome") not in {"candidate", "baseline", "tie", "uncertain"}:
                    raise ContractError("配对结果非法")
                if type(pair.get("critical_regression")) is not bool:
                    raise ContractError("须明确检查严重回归")
            if result["decision"] == "adopt":
                if any(p["critical_regression"] or p["outcome"] in {"baseline", "uncertain"} for p in pairs):
                    raise ContractError("有未解决回归或不确定任务，不能自动接纳候选版本")
                if not any(p["outcome"] == "candidate" for p in pairs):
                    raise ContractError("未观察到改进，不能仅凭代码变化宣布提升")
            item = {**result, "attachments": captured, "assessor": identifier(assessor)}
            item["id"] = "evaluation-" + digest(canonical(item).encode())[:24]
            return item
        return self._append("evaluation", build)

    def promote(self, evaluation_id: str, reason: str) -> dict:
        def build(records):
            evaluations = [r for r in records if r["kind"] == "evaluation" and r["id"] == evaluation_id]
            if not evaluations or evaluations[-1]["decision"] != "adopt":
                raise ContractError("只有独立对照评估建议 adopt 的候选可以接纳")
            evaluation = evaluations[-1]
            active = [r["candidate"] for r in records if r["kind"] in {"promotion", "rollback"}]
            if active and active[-1] != evaluation["baseline"]:
                raise ContractError("对照基线不是当前接纳版本；须重新比较，不能跨过中间改动")
            return {"candidate": evaluation["candidate"], "baseline": evaluation["baseline"],
                    "evaluation": evaluation_id, "reason": required(reason, "reason"),
                    "effect": "accepted-reference-only; working-tree-not-modified"}
        return self._append("promotion", build)

    def rollback(self, version: str, reason: str) -> dict:
        def build(records):
            eligible = {r["candidate"] for r in records if r["kind"] == "promotion"}
            eligible |= {r["baseline"] for r in records if r["kind"] == "promotion"}
            if version not in eligible:
                raise ContractError("只可回退到已有接纳链上的版本，不能借回退启用未验证候选")
            return {"candidate": version, "reason": required(reason, "reason"),
                    "effect": "accepted-reference-only; working-tree-not-modified"}
        return self._append("rollback", build)

    def audit(self) -> dict:
        records = self.records()
        checked = set()
        for record in records:
            if record["kind"] == "evaluation":
                for checksum in record["attachments"].values():
                    path = self.root / "blobs" / checksum
                    if not path.is_file() or digest(path.read_bytes()) != checksum:
                        raise ContractError("对照评估原始材料丢失或损坏")
                    checked.add(checksum)
            if record["kind"] != "snapshot":
                continue
            if digest(canonical(record["files"]).encode()) != record["id"]:
                raise ContractError("系统清单与版本 ID 不一致")
            for checksum in record["files"].values():
                path = self.root / "blobs" / checksum
                if not path.is_file() or digest(path.read_bytes()) != checksum:
                    raise ContractError("系统历史内容丢失或损坏")
                checked.add(checksum)
        return {"records": len(records), "checked_blobs": len(checked), "integrity": "valid",
                "improvement_validity": "requires-independent-content-evaluation"}

    def checkout(self, version: str, destination: Path) -> dict:
        """只导出到新目录，绝不覆盖工作树；运行旧版本仍需显式选择目录。"""
        records = self.records()
        snapshots = [record for record in records if record["kind"] == "snapshot" and record["id"] == version]
        if not snapshots:
            raise ContractError("历史版本不存在")
        destination = destination.resolve()
        if destination.exists():
            raise ContractError("版本导出目录必须不存在，避免覆盖任何当前工作")
        self.audit()
        destination.mkdir(parents=True)
        for name, checksum in snapshots[0]["files"].items():
            relative = Path(name)
            if relative.is_absolute() or ".." in relative.parts:
                raise ContractError("非法版本库路径")
            target = destination / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes((self.root / "blobs" / checksum).read_bytes())
        return {"version": version, "directory": str(destination), "activated": False}
