#!/usr/bin/env python3
"""只读验证 Q-HIST v13 的代码、协议文件与冻结预检输入。"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def verify(
    lock_path: Path,
    code_root: Path,
    runs_root: Path,
    protocol_root: Path,
) -> dict:
    lock = json.loads(lock_path.read_text(encoding="utf-8"))
    checks: dict[str, bool] = {}
    observed: dict[str, str | None] = {}

    for name, expected in lock["code_sha256"].items():
        path = code_root / name
        actual = sha256_file(path) if path.is_file() else None
        observed[f"code/{name}"] = actual
        checks[f"code/{name}"] = actual == expected

    for name, expected in lock["protocol_documents_sha256"].items():
        path = protocol_root / name
        actual = sha256_file(path) if path.is_file() else None
        observed[f"protocol/{name}"] = actual
        checks[f"protocol/{name}"] = actual == expected

    frozen = lock["frozen_inputs"]
    targets = {
        "assets_manifest": runs_root / frozen["assets"] / "manifest.json",
        "rendered_manifest": runs_root / frozen["rendered"] / "manifest.json",
        "toolsandbox_gate": runs_root / frozen["toolsandbox_gate"],
        "driver_gate": runs_root / frozen["driver_gate"],
        "deterministic_id_gate": runs_root / frozen["deterministic_id_gate"],
        "preflight": runs_root / frozen["preflight"],
    }
    for name, path in targets.items():
        actual = sha256_file(path) if path.is_file() else None
        observed[name] = actual
        checks[name] = actual == frozen[f"{name}_sha256"]

    return {
        "schema_version": 1,
        "protocol_id": lock.get("protocol_id"),
        "protocol_version": lock.get("protocol_version"),
        "lock_sha256": sha256_file(lock_path),
        "checks": checks,
        "observed_sha256": observed,
        "passed": bool(checks) and all(checks.values()),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--lock", type=Path, required=True)
    parser.add_argument("--code-root", type=Path, required=True)
    parser.add_argument("--runs-root", type=Path, required=True)
    parser.add_argument("--protocol-root", type=Path, required=True)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    result = verify(args.lock, args.code_root, args.runs_root, args.protocol_root)
    rendered = json.dumps(result, ensure_ascii=False, indent=2) + "\n"
    if args.output:
        if args.output.exists():
            raise RuntimeError(f"拒绝覆盖已有 lock 审计：{args.output}")
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered, encoding="utf-8")
    print(rendered, end="")
    return 0 if result["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
