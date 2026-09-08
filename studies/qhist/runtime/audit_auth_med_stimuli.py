#!/usr/bin/env python3
"""审计 AUTH-MED 四条件刺激中可机器复核的结构不变量。"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
from collections import defaultdict
from pathlib import Path


CONDITIONS = {"S+E+", "S-E+", "S+E-", "S-E-"}
FIELD_PATTERN = re.compile(
    r"^Record: (?P<record>[^\n]+)$.*^Counterevidence retained: (?P<counter>[^\n]+)$",
    re.MULTILINE | re.DOTALL,
)


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--max-token-spread", type=int, default=2)
    args = parser.parse_args()

    rows = [
        json.loads(line)
        for line in args.manifest.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    grouped = defaultdict(list)
    failures = []
    for row in rows:
        grouped[row["episode_id"]].append(row)

    episode_results = []
    for episode_id, items in sorted(grouped.items()):
        seen = {item["condition"] for item in items}
        texts = {}
        fields = {}
        hashes_ok = True
        leaked = False
        for item in items:
            path = args.manifest.parent / item["stimulus"]
            raw = path.read_bytes()
            text = raw.decode("utf-8")
            texts[item["condition"]] = text
            hashes_ok &= digest(raw) == item["stimulus_sha256"]
            leaked |= any(label in text for label in CONDITIONS)
            match = FIELD_PATTERN.search(text)
            if match is None:
                failures.append(f"{episode_id}/{item['condition']}: 字段解析失败")
            else:
                fields[item["condition"]] = match.groupdict()
        token_counts = [len(text.split()) for text in texts.values()]
        complete = seen == CONDITIONS and len(items) == 4
        proposition_fixed = (
            len({value["record"] for value in fields.values()}) == 1
            and len({value["counter"] for value in fields.values()}) == 1
            and len(fields) == 4
        )
        token_spread = max(token_counts) - min(token_counts) if token_counts else 999
        checks = {
            "four_conditions": complete,
            "hashes": hashes_ok,
            "condition_label_hidden": not leaked,
            "record_and_counterevidence_fixed": proposition_fixed,
            "token_spread": token_spread <= args.max_token_spread,
        }
        if not all(checks.values()):
            failures.append(f"{episode_id}: {checks}")
        episode_results.append(
            {
                "episode_id": episode_id,
                "checks": checks,
                "token_min": min(token_counts) if token_counts else None,
                "token_max": max(token_counts) if token_counts else None,
                "token_spread": token_spread,
            }
        )

    result = {
        "schema_version": 1,
        "episodes": len(grouped),
        "stimuli": len(rows),
        "max_token_spread": args.max_token_spread,
        "episode_results": episode_results,
        "failures": failures,
        "passed": len(grouped) == 24 and len(rows) == 96 and not failures,
        "scope_note": "仅覆盖结构不变量；不替代语义等价盲评、目标操纵 AUC 或自然度评价。",
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
