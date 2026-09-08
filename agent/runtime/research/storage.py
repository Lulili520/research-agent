"""Filesystem primitives, project locks, and append-only event records."""
import contextlib
import hashlib
import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
try:
    from .policy import ResearchRoot
except ImportError:
    from policy import ResearchRoot

@contextlib.contextmanager
def project_lock(root: Path):
    """Serialize mutations within one project; the executor must use the same lock."""
    path = root / ".research.lock"
    path.parent.mkdir(parents=True, exist_ok=True)
    stream = path.open("a+b")
    try:
        if os.name == "nt":
            import msvcrt
            stream.seek(0)
            msvcrt.locking(stream.fileno(), msvcrt.LK_LOCK, 1)
        else:
            import fcntl
            fcntl.flock(stream.fileno(), fcntl.LOCK_EX)
        yield
    finally:
        if os.name == "nt":
            stream.seek(0)
            msvcrt.locking(stream.fileno(), msvcrt.LK_UNLCK, 1)
        else:
            import fcntl
            fcntl.flock(stream.fileno(), fcntl.LOCK_UN)
        stream.close()


def now() -> str:
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")


def read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json_atomic(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".new")
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    os.replace(temporary, path)


def append_jsonl(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8", newline="\n") as stream:
        stream.write(json.dumps(value, ensure_ascii=False, separators=(",", ":")) + "\n")
        stream.flush()
        os.fsync(stream.fileno())


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def project(path: str) -> ResearchRoot:
    outer = Path(path).resolve()
    for base in (outer / ".research", outer):
        root = ResearchRoot(base)
        if (root / "research.json").is_file() and (root / "state.json").is_file():
            return root
    raise SystemExit(f"not an initialized research project: {outer}")


def load_events(root: Path) -> list[dict[str, Any]]:
    path = root / "events.jsonl"
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def event_hash(record: dict[str, Any]) -> str:
    unsigned = {key: value for key, value in record.items() if key != "hash"}
    payload = json.dumps(unsigned, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def emit(root: Path, kind: str, actor: str, payload: dict[str, Any]) -> dict[str, Any]:
    events = load_events(root)
    record = {
        "seq": len(events) + 1,
        "time": now(),
        "type": kind,
        "actor": actor,
        "payload": payload,
        "prev_hash": events[-1]["hash"] if events else None,
    }
    record["hash"] = event_hash(record)
    append_jsonl(root / "events.jsonl", record)
    return record


def verify_events(root: Path) -> None:
    previous = None
    for index, record in enumerate(load_events(root), start=1):
        if record.get("seq") != index or record.get("prev_hash") != previous or record.get("hash") != event_hash(record):
            raise SystemExit(f"event log integrity failure at sequence {index}")
        previous = record["hash"]
