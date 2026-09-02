#!/usr/bin/env python3
"""导出 ToolSandbox 原始场景目录，供冻结 Pilot episode 使用。"""

from __future__ import annotations

import argparse
import json
import random
from pathlib import Path

from tool_sandbox.common.execution_context import DatabaseNamespace, RoleType
from tool_sandbox.common.tool_discovery import ToolBackend
from tool_sandbox.scenarios import named_scenarios


AUGMENTED_SUFFIXES = (
    "_3_distraction_tools",
    "_10_distraction_tools",
    "_all_tools",
    "_tool_description_scrambled",
    "_arg_type_scrambled",
    "_arg_description_scrambled",
    "_tool_name_scrambled",
)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--seed", type=int, default=42)
    args = parser.parse_args()

    random.seed(args.seed)
    scenarios = named_scenarios(preferred_tool_backend=ToolBackend.DEFAULT)
    records = []
    for name, scenario in sorted(scenarios.items()):
        if any(marker in name for marker in AUGMENTED_SUFFIXES):
            continue
        sandbox = scenario.starting_context.get_database(
            DatabaseNamespace.SANDBOX,
            drop_sandbox_message_index=False,
            get_all_history_snapshots=True,
        )
        user_messages = sandbox.filter(
            (sandbox["sender"] == RoleType.USER)
            & (sandbox["recipient"] == RoleType.AGENT)
        )["content"].to_list()
        records.append(
            {
                "scenario": name,
                "user_messages": user_messages,
                "tool_allow_list": scenario.starting_context.tool_allow_list,
                "categories": [str(item) for item in scenario.categories],
                "max_messages": scenario.max_messages,
                "multiple_user_turn": "multiple_user_turn" in name,
            }
        )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        "\n".join(json.dumps(item, ensure_ascii=False) for item in records) + "\n",
        encoding="utf-8",
    )
    print(json.dumps({"scenario_count": len(records), "output": str(args.output)}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
