#!/usr/bin/env python3
"""用冻结的无历史 add prompt 验证 Q-HIST 本机模型服务协议。"""

from __future__ import annotations

import argparse
import json
import time
import urllib.request
from pathlib import Path

from qhist_precision_qualification import qualification_prompts


def request_json(url: str, payload=None):
    data = None if payload is None else json.dumps(payload).encode("utf-8")
    request = urllib.request.Request(
        url,
        data=data,
        headers={"Content-Type": "application/json"},
        method="GET" if payload is None else "POST",
    )
    with urllib.request.urlopen(request, timeout=600) as response:
        return json.loads(response.read().decode("utf-8"))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--endpoint", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    endpoint = args.endpoint.rstrip("/")
    health = None
    last_error = None
    for _ in range(180):
        try:
            health = request_json(endpoint + "/health")
            break
        except Exception as error:
            last_error = error
            time.sleep(1)
    if health is None:
        raise RuntimeError(f"模型服务 180 秒内未就绪：{last_error}")
    item = qualification_prompts()["add"]
    try:
        response = request_json(
            endpoint + "/generate",
            {
                "request_id": "engineering-smoke-add",
                "expected_precision": "P00",
                "messages": item["messages"],
                "tools": item["tools"],
                "max_new_tokens": 128,
            },
        )
    finally:
        request_json(endpoint + "/shutdown", {})
    result = {
        "health": health,
        "response": response,
        "passed": response.get("parsed_actions") == [item["gold"]],
    }
    args.output.write_text(
        json.dumps(result, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
