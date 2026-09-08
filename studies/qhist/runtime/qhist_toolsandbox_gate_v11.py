#!/usr/bin/env python3
"""不调用模型，审计 Q-HIST v11 的真值、F/V/G、oracle 与回滚。"""

from __future__ import annotations

from typing import Any

import qhist_toolsandbox_gate_v10 as previous
import qhist_v11_spec as spec


def induce_error(
    context: Any, episode: dict[str, Any], patch: dict[str, Any]
) -> dict[str, Any]:
    from tool_sandbox.common.execution_context import set_current_context

    set_current_context(context)
    tools = context.get_available_tools(scrambling_allowed=False)
    kind = episode["error_kind"]
    outcome: dict[str, Any] = {"error_kind": kind, "operation": patch["operation"]}
    if kind == "contact-id-substitution":
        tools["remove_contact"](person_id=patch["key"]["person_id"])
        outcome["induced"] = True
    elif kind == "absolute-time-shift":
        tools["add_reminder"](
            content=patch["predicate"]["content"],
            reminder_timestamp=patch["predicate"]["reminder_timestamp"],
        )
        outcome["induced"] = True
    elif kind == "boolean-negation-location":
        try:
            tools["set_location_service_status"](on=True)
            outcome["expected_rejection"] = False
        except Exception as error:
            outcome["expected_rejection"] = True
            outcome["rejection_type"] = type(error).__name__
        outcome["induced"] = False
    else:
        raise ValueError(kind)
    return outcome


def main() -> int:
    # 复用已经过 v10 验证的官方执行轨迹审计壳；替换的只有冻结协议、任务与
    # 错误诱导函数。恢复证书的动态更新另由 v11 driver gate 独立验证。
    previous.spec = spec
    previous.induce_error = induce_error
    return previous.main()


if __name__ == "__main__":
    raise SystemExit(main())
