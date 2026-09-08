#!/usr/bin/env python3
"""只读检查 Q-HIST v11 候选场景、工具签名与冻结初态。"""

from __future__ import annotations

import inspect
import json
from typing import Any

import qhist_build_e0_assets as base


SCENARIOS = (
    "remove_contact_by_phone",
    "remove_contact_by_phone_alt",
    "add_reminder_content_and_date_and_time",
    "add_reminder_content_and_date_and_time_alt",
    "turn_on_location_low_battery_mode",
    "turn_on_location_low_battery_mode_implicit",
)


def serializable(value: Any) -> Any:
    try:
        json.dumps(value, default=str)
        return value
    except TypeError:
        return repr(value)


def main() -> int:
    scenarios = base.named_scenarios(preferred_tool_backend=base.ToolBackend.DEFAULT)
    report: list[dict[str, Any]] = []
    for name in SCENARIOS:
        scenario = scenarios[name]
        context = base.initialise_context(scenario)
        tools = context.get_available_tools(scrambling_allowed=False)
        namespaces: dict[str, Any] = {}
        for namespace in base.DatabaseNamespace:
            if namespace == base.DatabaseNamespace.SANDBOX:
                continue
            try:
                namespaces[namespace.name] = context.get_database(namespace).to_dicts()
            except Exception as error:
                namespaces[namespace.name] = {"error": f"{type(error).__name__}: {error}"}
        tool_info = {
            tool_name: {
                "signature": str(inspect.signature(tools[tool_name])),
                "doc": inspect.getdoc(tools[tool_name]),
            }
            for tool_name in sorted(tools)
        }
        probes: dict[str, Any] = {}
        if "search_contacts" in tools:
            probes["search_contacts_by_phone"] = serializable(
                tools["search_contacts"](phone_number="+12453344098")
            )
        if "datetime_info_to_timestamp" in tools:
            probes["datetime_target"] = serializable(
                tools["datetime_info_to_timestamp"](
                    year=2024, month=3, day=22, hour=17, minute=0, second=0
                )
            )
        if "get_low_battery_mode_status" in tools:
            probes["low_battery"] = serializable(
                tools["get_low_battery_mode_status"]()
            )
        if "get_location_service_status" in tools:
            probes["location"] = serializable(
                tools["get_location_service_status"]()
            )
        report.append(
            {
                "scenario": name,
                "max_messages": scenario.max_messages,
                "agent_visible_messages": base.agent_visible_messages(context),
                "tools": tool_info,
                "probes": probes,
                "namespaces": namespaces,
            }
        )
    print(json.dumps(report, ensure_ascii=False, indent=2, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
