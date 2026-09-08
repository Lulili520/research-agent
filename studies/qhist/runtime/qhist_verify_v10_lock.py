#!/usr/bin/env python3
"""只读验证 Q-HIST v10 代码锁、冻结预检产物与测试日志。"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def verify(lock_path: Path, code_root: Path, runs_root: Path) -> dict:
    lock = json.loads(lock_path.read_text(encoding="utf-8"))
    checks: dict[str, bool] = {}
    observed: dict[str, str | None] = {}
    for name, expected in lock["code_sha256"].items():
        path = code_root / name
        actual = sha256_file(path) if path.is_file() else None
        observed[f"code/{name}"] = actual
        checks[f"code/{name}"] = actual == expected

    frozen = lock["frozen_inputs"]
    targets = {
        "assets_manifest": runs_root / frozen["assets"] / "manifest.json",
        "rendered_manifest": runs_root / frozen["rendered"] / "manifest.json",
        "toolsandbox_gate": runs_root / frozen["toolsandbox_gate"],
        "driver_gate": runs_root / frozen["driver_gate"],
    }
    expected_artifacts = {
        "assets_manifest": frozen["assets_manifest_sha256"],
        "rendered_manifest": frozen["rendered_manifest_sha256"],
        "toolsandbox_gate": frozen["toolsandbox_gate_sha256"],
        "driver_gate": frozen["driver_gate_sha256"],
    }
    for name, path in targets.items():
        actual = sha256_file(path) if path.is_file() else None
        observed[name] = actual
        checks[name] = actual == expected_artifacts[name]

    return {
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
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    result = verify(args.lock, args.code_root, args.runs_root)
    rendered = json.dumps(result, ensure_ascii=False, indent=2) + "\n"
    if args.output:
        if args.output.exists():
            raise RuntimeError(f"禁止覆盖 lock 审计：{args.output}")
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered, encoding="utf-8")
    print(rendered, end="")
    return 0 if result["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
