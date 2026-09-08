#!/usr/bin/env python3
"""Probe an OpenAI-compatible vLLM service and preserve machine-readable evidence."""

from __future__ import annotations

import argparse
import json
import urllib.request
from pathlib import Path


def request_json(url: str, api_key: str, payload: dict | None = None) -> dict:
    data = None if payload is None else json.dumps(payload).encode("utf-8")
    request = urllib.request.Request(url, data=data)
    request.add_header("Authorization", f"Bearer {api_key}")
    if data is not None:
        request.add_header("Content-Type", "application/json")
    with urllib.request.urlopen(request, timeout=120) as response:
        return json.load(response)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", default="http://127.0.0.1:8000")
    parser.add_argument("--api-key", default="EMPTY")
    parser.add_argument("--model", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    models = request_json(f"{args.base_url}/v1/models", args.api_key)
    model_ids = [item.get("id") for item in models.get("data", [])]
    payload = {
        "model": args.model,
        "messages": [
            {
                "role": "user",
                "content": "Call the add function with a=2 and b=3. Do not answer in text.",
            }
        ],
        "tools": [
            {
                "type": "function",
                "function": {
                    "name": "add",
                    "description": "Add two integers.",
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
        "tool_choice": {"type": "function", "function": {"name": "add"}},
        "temperature": 0,
        "max_tokens": 64,
        "chat_template_kwargs": {"enable_thinking": False},
    }
    completion = request_json(
        f"{args.base_url}/v1/chat/completions", args.api_key, payload
    )
    message = completion.get("choices", [{}])[0].get("message", {})
    tool_calls = message.get("tool_calls") or []
    function = tool_calls[0].get("function", {}) if tool_calls else {}
    try:
        arguments = json.loads(function.get("arguments", ""))
    except (TypeError, json.JSONDecodeError):
        arguments = None

    checks = {
        "v1_models_contains_exact_served_name": args.model in model_ids,
        "forced_native_tool_call_is_structured": bool(tool_calls)
        and tool_calls[0].get("type") == "function",
        "forced_native_tool_call_name_correct": function.get("name") == "add",
        "forced_native_tool_call_arguments_correct": arguments == {"a": 2, "b": 3},
    }
    result = {
        "schema_version": 1,
        "model": args.model,
        "checks": checks,
        "passed": all(checks.values()),
        "models_response": models,
        "completion_response": completion,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps({"passed": result["passed"], "checks": checks}))
    return 0 if result["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
