#!/usr/bin/env python3
"""使用本地 OpenAI-compatible 模型运行单个 ToolSandbox 场景。

该入口不需要云端 API key。它冻结初始快照、完整保留 ToolSandbox 轨迹与判分，
并使用确定性用户在 Agent 给出最终答复后结束单轮场景。多轮用户场景不应使用本入口。
"""

from __future__ import annotations

import argparse
import attrs
import hashlib
import json
import os
import random
import sys
import time
from pathlib import Path
from typing import Any, Optional

import polars as pl

from tool_sandbox.common.execution_context import DatabaseNamespace, RoleType
from tool_sandbox.common.message_conversion import Message
from tool_sandbox.common.tool_discovery import ToolBackend
from tool_sandbox.roles.base_role import BaseRole
from tool_sandbox.roles.execution_environment import ExecutionEnvironment
from tool_sandbox.roles.hermes_api_agent import HermesAPIAgent
from tool_sandbox.scenarios import named_scenarios


def json_bytes(value: Any) -> bytes:
    return json.dumps(
        value, ensure_ascii=False, sort_keys=True, default=str
    ).encode("utf-8")


class DeterministicEndUser(BaseRole):
    """在单轮任务收到最终答复后调用 ToolSandbox 的结束工具。"""

    role_type = RoleType.USER

    def respond(self, ending_index: Optional[int] = None) -> None:
        messages = self.get_messages(ending_index=ending_index)
        self.messages_validation(messages)
        if messages[-1].sender == RoleType.SYSTEM:
            return
        self.add_messages(
            [
                Message(
                    sender=RoleType.USER,
                    recipient=RoleType.EXECUTION_ENVIRONMENT,
                    content="print(repr(end_conversation()))",
                )
            ]
        )


class AuditedHermesAPIAgent(HermesAPIAgent):
    """保持官方严格解析行为，同时在解析前保存模型原始 completion。"""

    def __init__(self, model_name: str, audit_path: Path) -> None:
        super().__init__(model_name=model_name)
        self.audit_path = audit_path

    def model_inference(self, openai_messages, openai_tools):
        response = super().model_inference(openai_messages, openai_tools)
        record = {
            "request": {
                "messages": openai_messages,
                "tools": openai_tools,
            },
            "response": response.model_dump(mode="json"),
        }
        with self.audit_path.open("a", encoding="utf-8", newline="\n") as stream:
            stream.write(json.dumps(record, ensure_ascii=False, default=str) + "\n")
            stream.flush()
            os.fsync(stream.fileno())
        return response


def inject_retrieved_memory(scenario, memory: str) -> None:
    """把固定命中的记忆置于当前用户请求之前，并保留为系统可见证据。"""

    context = scenario.starting_context
    sandbox = context._dbs[DatabaseNamespace.SANDBOX]  # ToolSandbox 无公开插入 API。
    message_index = context.max_sandbox_message_index
    memory_row = {
        "sandbox_message_index": message_index,
        "sender": RoleType.SYSTEM,
        "recipient": RoleType.AGENT,
        "content": memory,
        "conversation_active": True,
        "openai_tool_call_id": None,
        "openai_function_name": None,
        "tool_call_exception": None,
        "tool_trace": None,
        "visible_to": [RoleType.SYSTEM, RoleType.AGENT],
    }
    before = sandbox.filter(pl.col("sandbox_message_index") < message_index)
    after = sandbox.filter(pl.col("sandbox_message_index") >= message_index).with_columns(
        (pl.col("sandbox_message_index") + 1).alias("sandbox_message_index")
    )
    inserted = pl.DataFrame(
        [memory_row], schema=context.dbs_schemas[DatabaseNamespace.SANDBOX]
    )
    context._dbs[DatabaseNamespace.SANDBOX] = pl.concat(
        [before, inserted, after], how="vertical"
    )


def verify_retrieved_memory_delivery(scenario, memory: str) -> dict[str, Any]:
    """验证记忆在冻结输入中紧邻当前用户请求，而非只验证调用方传了文件。"""

    sandbox = scenario.starting_context._dbs[DatabaseNamespace.SANDBOX]
    memory_rows = sandbox.filter(
        (pl.col("sender") == RoleType.SYSTEM)
        & (pl.col("recipient") == RoleType.AGENT)
        & (pl.col("content") == memory)
    ).to_dicts()
    if len(memory_rows) != 1:
        raise RuntimeError(f"检索记忆必须且只能投递一次，实际为 {len(memory_rows)} 次")
    memory_index = int(memory_rows[0]["sandbox_message_index"])
    next_rows = sandbox.filter(
        pl.col("sandbox_message_index") == memory_index + 1
    ).to_dicts()
    if len(next_rows) != 1:
        raise RuntimeError("检索记忆之后没有唯一的当前用户请求")
    current_request = next_rows[0]
    verified = (
        current_request["sender"] == RoleType.USER
        and current_request["recipient"] == RoleType.AGENT
    )
    if not verified:
        raise RuntimeError("检索记忆没有紧邻置于当前 USER→AGENT 请求之前")
    return {
        "verified": True,
        "memory_message_index": memory_index,
        "current_request_message_index": memory_index + 1,
        "current_request_sha256": hashlib.sha256(
            str(current_request["content"]).encode("utf-8")
        ).hexdigest(),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--scenario", required=True)
    parser.add_argument("--seed", type=int, required=True)
    parser.add_argument("--model", required=True)
    parser.add_argument("--base-url", default="http://127.0.0.1:8000/v1")
    parser.add_argument(
        "--memory-file",
        type=Path,
        help="UTF-8 文本；提供时作为固定命中的检索记忆插入当前请求之前",
    )
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    os.environ["OPENAI_BASE_URL"] = args.base_url
    random.seed(args.seed)
    scenarios = named_scenarios(preferred_tool_backend=ToolBackend.DEFAULT)
    if args.scenario not in scenarios:
        raise KeyError(f"未知或不受支持的场景：{args.scenario}")
    scenario = scenarios[args.scenario]
    if "multiple_user_turn" in args.scenario:
        raise ValueError("确定性用户仅适用于单轮场景")
    memory = None
    delivery: dict[str, Any] | None = None
    if args.memory_file is not None:
        memory = args.memory_file.read_text(encoding="utf-8").strip()
        if not memory:
            raise ValueError("memory-file 不得为空")
        inject_retrieved_memory(scenario, memory)
        delivery = verify_retrieved_memory_delivery(scenario, memory)

    args.output.mkdir(parents=True, exist_ok=True)
    raw_completions_path = args.output / "raw-completions.jsonl"
    snapshot = scenario.starting_context.to_dict(serialize_console=False)
    snapshot_path = args.output / "starting_snapshot.json"
    snapshot_path.write_text(
        json.dumps(snapshot, ensure_ascii=False, indent=2, default=str) + "\n",
        encoding="utf-8",
    )
    started = time.time()
    summary: dict[str, Any] = {
        "schema_version": 1,
        "scenario": args.scenario,
        "seed": args.seed,
        "model": args.model,
        "base_url": args.base_url,
        "snapshot_sha256": hashlib.sha256(json_bytes(snapshot)).hexdigest(),
        "memory_supplied": memory is not None,
        "retrieval_hit": delivery["verified"] if delivery is not None else None,
        "retrieval_delivery": delivery,
        "memory_sha256": hashlib.sha256(memory.encode("utf-8")).hexdigest()
        if memory is not None
        else None,
        "status": "running",
    }
    try:
        result = scenario.play_and_evaluate(
            roles={
                RoleType.USER: DeterministicEndUser(),
                RoleType.EXECUTION_ENVIRONMENT: ExecutionEnvironment(),
                RoleType.AGENT: AuditedHermesAPIAgent(
                    model_name=args.model, audit_path=raw_completions_path
                ),
            },
            output_directory=args.output,
            scenario_name=args.scenario,
        )
        summary["evaluation"] = attrs.asdict(result.evaluation_result)
        summary["status"] = "succeeded"
        return_code = 0
    except Exception as error:  # 失败也必须落盘，供运行注册表审计。
        summary["status"] = "failed"
        summary["error_type"] = type(error).__name__
        summary["error"] = str(error)
        return_code = 1
    finally:
        summary["elapsed_seconds"] = round(time.time() - started, 6)
        (args.output / "summary.json").write_text(
            json.dumps(summary, ensure_ascii=False, indent=2, default=str) + "\n",
            encoding="utf-8",
        )
        print(json.dumps(summary, ensure_ascii=False, indent=2, default=str))
    return return_code


if __name__ == "__main__":
    sys.exit(main())
