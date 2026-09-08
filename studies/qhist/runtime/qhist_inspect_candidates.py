#!/usr/bin/env python3
"""只读导出 ToolSandbox 的 Q-HIST 候选任务结构，不运行目标模型。"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

import qhist_build_e0_assets as base


FORBIDDEN_TOOLS = {
    "convert_currency",
    "get_current_location",
    "search_lat_lon",
    "search_location_around_lat_lon",
    "search_stock",
    "search_weather_around_lat_lon",
    "calculate_lat_lon_distance",
}


def enum_text(value: Any) -> str:
    raw = getattr(value, "value", value)
    return str(raw)


def is_structural_candidate(scenario: Any) -> bool:
    categories = {enum_text(value).upper() for value in scenario.categories}
    tools = set(scenario.starting_context.tool_allow_list or [])
    return (
        any("MULTIPLE_TOOL_CALL" in value for value in categories)
        and not any("INSUFFICIENT_INFORMATION" in value for value in categories)
        and any("NO_DISTRACTION_TOOLS" in value for value in categories)
        and not (tools & FORBIDDEN_TOOLS)
    )


def summarize(name: str, scenario: Any) -> dict[str, Any]:
    context = base.initialise_context(scenario)
    messages = base.agent_visible_messages(context)
    return {
        "scenario": name,
        "family": base.normalize_family(name),
        "categories": sorted(enum_text(value) for value in scenario.categories),
        "tool_allow_list": list(scenario.starting_context.tool_allow_list or []),
        "agent_visible_messages": messages,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    scenarios = base.named_scenarios(preferred_tool_backend=base.ToolBackend.DEFAULT)
    rows = [
        summarize(name, scenario)
        for name, scenario in sorted(scenarios.items())
        if is_structural_candidate(scenario)
    ]
    payload = {
        "schema_version": 1,
        "filter": "MULTIPLE_TOOL_CALL and NO_DISTRACTION_TOOLS and not INSUFFICIENT_INFORMATION and no forbidden external/location/search tools",
        "count": len(rows),
        "candidates": rows,
    }
    rendered = json.dumps(payload, ensure_ascii=False, indent=2, default=str) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered, encoding="utf-8")
    else:
        print(rendered, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
