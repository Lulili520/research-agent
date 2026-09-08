#!/usr/bin/env python3
"""在不调用目标模型的前提下核验 v10 候选任务的真值与工具结构。"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

import qhist_build_e0_assets as base


CANDIDATES = (
    "send_message_with_contact_content_cellular_off",
    "send_message_with_contact_content_cellular_off_alt",
    "add_reminder_content_and_week_delta_and_time",
    "add_reminder_content_and_week_delta_and_time_alt",
    "turn_on_cellular_low_battery_mode",
    "turn_on_cellular_low_battery_mode_implicit",
)


def jsonable(value: Any) -> Any:
    try:
        json.dumps(value)
        return value
    except TypeError:
        return repr(value)


def probe(name: str, scenario: Any) -> dict[str, Any]:
    context = base.initialise_context(scenario)
    tools = context.get_available_tools(scrambling_allowed=False)
    messages = base.agent_visible_messages(context)
    observations: dict[str, Any] = {}
    for tool_name, arguments in (
        ("get_current_timestamp", {}),
        ("get_low_battery_mode_status", {}),
        ("get_cellular_service_status", {}),
        ("search_contacts", {"name": "Fredrik Thordendal"}),
    ):
        if tool_name in tools:
            observations[tool_name] = jsonable(tools[tool_name](**arguments))
    schemas = base.convert_to_openai_tools(tools)
    return {
        "scenario": name,
        "family": base.normalize_family(name),
        "messages": messages,
        "available_tools": sorted(tools),
        "observations": observations,
        "tool_schemas": {
            row["function"]["name"]: row["function"]["parameters"]
            for row in schemas
            if row["function"]["name"]
            in {
                "send_message_with_phone_number",
                "add_reminder",
                "datetime_info_to_timestamp",
                "set_cellular_service_status",
                "set_low_battery_mode_status",
            }
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    scenarios = base.named_scenarios(preferred_tool_backend=base.ToolBackend.DEFAULT)
    missing = sorted(set(CANDIDATES) - set(scenarios))
    if missing:
        raise RuntimeError(f"候选场景不存在：{missing}")
    payload = {
        "schema_version": 1,
        "target_model_called": False,
        "candidates": [probe(name, scenarios[name]) for name in CANDIDATES],
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, default=str) + "\n",
        encoding="utf-8",
    )
    print(json.dumps({"candidate_count": len(CANDIDATES)}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
