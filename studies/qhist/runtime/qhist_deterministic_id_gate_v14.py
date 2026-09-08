#!/usr/bin/env python3
"""审计 v14 opaque ID 与调用前缀不受 precision/repeat 污染。"""

from __future__ import annotations

import argparse
import ast
import hashlib
import json
from pathlib import Path

import qhist_trajectory_batch_v14 as runner
import qhist_v14_spec as spec


def read_jsonl(path: Path):
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line]


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--assets", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        raise RuntimeError(f"拒绝覆盖既有 gate：{args.output}")
    args.output.parent.mkdir(parents=True, exist_ok=True)

    units = read_jsonl(args.assets / "trajectory-units.jsonl")
    episodes = {row["episode_id"]: row for row in read_jsonl(args.assets / "episodes.jsonl")}
    failures = []
    cells = {}
    for row in units:
        key = (row["episode_id"], row["module"], row["condition"], int(row["gap"]))
        provider = runner.DeterministicUUID4(runner.logical_key(row))
        values = [str(provider()) for _ in range(3)]
        call_prefixes = [runner.stable_call_prefix(runner.logical_key(row), index) for index in range(1, 5)]
        cells.setdefault(key, []).append(
            {
                "precision": row["precision"],
                "repeat": row["repeat"],
                "ids": values,
                "call_prefixes": call_prefixes,
            }
        )
    audited = []
    for key, rows in cells.items():
        if len(rows) < 2:
            continue
        id_sets = {tuple(row["ids"]) for row in rows}
        prefix_sets = {tuple(row["call_prefixes"]) for row in rows}
        passed = len(id_sets) == 1 and len(prefix_sets) == 1
        if not passed:
            failures.append(f"logical-cell-drift:{key}")
        audited.append({"cell": key, "conditions": rows, "passed": passed})

    predecessor = []
    for episode_id, episode in episodes.items():
        frozen = episode["predecessor_checkpoint"]
        provider = runner.DeterministicUUID4(episode_id, predecessor=True)
        expected_first = str(provider())
        binding = frozen.get("dynamic_roles", {}).get("error_entity_id")
        if binding is None:
            passed = True
        else:
            parsed = ast.literal_eval(frozen["execution"][0]["content"])
            passed = parsed == binding == expected_first
        if not passed:
            failures.append(f"predecessor-id:{episode_id}")
        predecessor.append(
            {
                "episode_id": episode_id,
                "has_dynamic_error_id": binding is not None,
                "expected_first": expected_first,
                "frozen_binding": binding,
                "passed": passed,
            }
        )

    report = {
        "schema_version": 1,
        "protocol_id": spec.PROTOCOL_ID,
        "protocol_version": spec.PROTOCOL_VERSION,
        "status": "passed" if not failures else "failed",
        "logical_cells_compared": len(audited),
        "cells": audited,
        "predecessor": predecessor,
        "artifacts": {
            "assets_manifest_sha256": sha256_file(args.assets / "manifest.json"),
            "id_gate_sha256": sha256_file(Path(__file__)),
            "production_runner_sha256": sha256_file(Path(runner.__file__)),
        },
        "failures": failures,
    }
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"status": report["status"], "cells": len(audited), "failures": failures}, ensure_ascii=False, indent=2))
    return 0 if report["status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
