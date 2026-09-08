#!/usr/bin/env python3
"""只读探测 Q-HIST v12 development 场景、冻结真值与官方 evaluator。

该脚本不调用目标模型，也不执行任何写工具。输出只用于在构建 v12 资产前
核验场景身份、只读 oracle、数据库初态和工具合同。
"""

from __future__ import annotations

import argparse
import inspect
import json
from pathlib import Path
from typing import Any

import qhist_build_e0_assets as base


SCENARIOS = (
    "add_reminder_content_and_weekday_delta_and_time",
    "add_reminder_content_and_weekday_delta_and_time_alt",
    "modify_contact_with_message_recency",
    "modify_contact_with_message_recency_alt",
    "turn_on_wifi_low_battery_mode",
    "turn_on_wifi_low_battery_mode_implicit",
)


def serializable(value: Any) -> Any:
    """尽量保留结构；无法 JSON 化的对象显式记录类型与 repr。"""

    try:
        json.dumps(value, default=str)
        return value
    except TypeError:
        return {
            "python_type": f"{type(value).__module__}.{type(value).__qualname__}",
            "repr": repr(value),
        }


def safe_call(tools: dict[str, Any], name: str, **arguments: Any) -> Any:
    if name not in tools:
        return {"unavailable": True}
    try:
        return {
            "ok": True,
            "arguments": arguments,
            "result": serializable(tools[name](**arguments)),
        }
    except Exception as error:  # 探针必须保存失败而不是中断其余场景
        return {
            "ok": False,
            "arguments": arguments,
            "error": f"{type(error).__name__}: {error}",
        }


def evaluation_description(scenario: Any) -> dict[str, Any]:
    evaluation = scenario.evaluation
    try:
        attributes = vars(evaluation)
    except TypeError:
        attributes = {
            name: getattr(evaluation, name)
            for name in dir(evaluation)
            if not name.startswith("_")
            and not callable(getattr(evaluation, name, None))
        }
    return {
        "python_type": f"{type(evaluation).__module__}.{type(evaluation).__qualname__}",
        "repr": repr(evaluation),
        "attributes": {
            key: serializable(value)
            for key, value in attributes.items()
            if not key.startswith("_")
        },
    }


def probe_scenario(name: str, scenario: Any) -> dict[str, Any]:
    context = base.initialise_context(scenario)
    tools = context.get_available_tools(scrambling_allowed=False)
    namespaces: dict[str, Any] = {}
    for namespace in base.DatabaseNamespace:
        try:
            namespaces[namespace.name] = context.get_database(
                namespace,
                get_all_history_snapshots=(namespace == base.DatabaseNamespace.SANDBOX),
                drop_sandbox_message_index=False,
            ).to_dicts()
        except Exception as error:
            namespaces[namespace.name] = {
                "error": f"{type(error).__name__}: {error}"
            }

    probes: dict[str, Any] = {}
    probes["current_timestamp"] = safe_call(tools, "get_current_timestamp")
    timestamp = probes["current_timestamp"].get("result")
    if isinstance(timestamp, (int, float)):
        probes["current_datetime"] = safe_call(
            tools, "timestamp_to_datetime_info", timestamp=float(timestamp)
        )
    # 冻结参考日是周四；ToolSandbox 的 next Friday oracle 是次日 17:00。
    probes["weekday_candidate_friday"] = safe_call(
        tools,
        "datetime_info_to_timestamp",
        year=2026,
        month=9,
        day=4,
        hour=17,
        minute=0,
        second=0,
    )
    probes["weekday_false_saturday"] = safe_call(
        tools,
        "datetime_info_to_timestamp",
        year=2026,
        month=9,
        day=5,
        hour=17,
        minute=0,
        second=0,
    )
    probes["all_messages"] = safe_call(tools, "search_messages")
    probes["all_contacts"] = safe_call(tools, "search_contacts")
    probes["low_battery"] = safe_call(tools, "get_low_battery_mode_status")
    probes["wifi"] = safe_call(tools, "get_wifi_status")

    tool_info = {
        tool_name: {
            "signature": str(inspect.signature(tools[tool_name])),
            "doc": inspect.getdoc(tools[tool_name]),
        }
        for tool_name in sorted(tools)
    }
    return {
        "scenario": name,
        "max_messages": scenario.max_messages,
        "agent_visible_messages": base.agent_visible_messages(context),
        "tools": tool_info,
        "probes": probes,
        "namespaces": namespaces,
        "evaluation": evaluation_description(scenario),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    scenarios = base.named_scenarios(preferred_tool_backend=base.ToolBackend.DEFAULT)
    missing = sorted(set(SCENARIOS) - set(scenarios))
    if missing:
        raise RuntimeError(f"冻结候选场景不存在：{missing}")
    report = [probe_scenario(name, scenarios[name]) for name in SCENARIOS]
    rendered = json.dumps(report, ensure_ascii=False, indent=2, default=str) + "\n"
    if args.output is None:
        print(rendered, end="")
    else:
        if args.output.exists():
            raise RuntimeError(f"拒绝覆盖既有探针：{args.output}")
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered, encoding="utf-8")
        print(json.dumps({"status": "succeeded", "output": str(args.output), "scenarios": len(report)}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
