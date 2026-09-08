#!/usr/bin/env python3
"""验证本地 OpenAI-compatible 服务的模型身份与原生工具调用能力。"""

from __future__ import annotations

import argparse
import json
import time
from pathlib import Path
from typing import Any

from openai import OpenAI


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", default="http://127.0.0.1:8000/v1")
    parser.add_argument("--model", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    client = OpenAI(api_key="EMPTY", base_url=args.base_url)
    started = time.time()
    record: dict[str, Any] = {
        "schema_version": 1,
        "base_url": args.base_url,
        "expected_model": args.model,
        "status": "failed",
    }
    try:
        models = client.models.list()
        model_ids = sorted(item.id for item in models.data)
        record["served_models"] = model_ids
        if args.model not in model_ids:
            raise RuntimeError(f"服务未暴露预期模型：{args.model}")

        request = {
            "model": args.model,
            "messages": [
                {
                    "role": "user",
                    "content": "必须调用 multiply 工具计算 6 乘以 7，不要自行回答。",
                }
            ],
            "tools": [
                {
                    "type": "function",
                    "function": {
                        "name": "multiply",
                        "description": "计算两个整数的乘积",
                        "parameters": {
                            "type": "object",
                            "properties": {
                                "a": {"type": "integer"},
                                "b": {"type": "integer"},
                            },
                            "required": ["a", "b"],
                            "additionalProperties": False,
                        },
                    },
                }
            ],
            "tool_choice": {
                "type": "function",
                "function": {"name": "multiply"},
            },
            "temperature": 0.0,
            "extra_body": {"chat_template_kwargs": {"enable_thinking": False}},
        }
        response = client.chat.completions.create(**request)
        dumped = response.model_dump(mode="json")
        record["request"] = request
        record["response"] = dumped
        calls = response.choices[0].message.tool_calls or []
        if len(calls) != 1 or calls[0].function.name != "multiply":
            raise RuntimeError("模型没有返回唯一的 multiply 结构化工具调用")
        arguments = json.loads(calls[0].function.arguments)
        if arguments != {"a": 6, "b": 7}:
            raise RuntimeError(f"工具参数不符合预期：{arguments}")
        record["validated_tool_call"] = {
            "name": calls[0].function.name,
            "arguments": arguments,
        }
        record["status"] = "succeeded"
        return_code = 0
    except Exception as error:
        record["error_type"] = type(error).__name__
        record["error"] = str(error)
        return_code = 1
    finally:
        record["elapsed_seconds"] = round(time.time() - started, 6)
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(
            json.dumps(record, ensure_ascii=False, indent=2, default=str) + "\n",
            encoding="utf-8",
        )
        print(json.dumps(record, ensure_ascii=False, indent=2, default=str))
    return return_code


if __name__ == "__main__":
    raise SystemExit(main())
