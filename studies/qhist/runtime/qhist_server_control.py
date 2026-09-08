#!/usr/bin/env python3
"""等待或关闭 Q-HIST loopback 模型服务。"""

from __future__ import annotations

import argparse
import json
import time
import urllib.request
from pathlib import Path


MODEL_REVISION = "9216db5781bf21249d130ec9da846c4624c16137"


def request_json(url: str, payload=None):
    data = None if payload is None else json.dumps(payload).encode("utf-8")
    request = urllib.request.Request(
        url,
        data=data,
        headers={"Content-Type": "application/json"},
        method="GET" if payload is None else "POST",
    )
    with urllib.request.urlopen(request, timeout=10) as response:
        return json.loads(response.read().decode("utf-8"))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("wait", "shutdown"))
    parser.add_argument("--endpoint", required=True)
    parser.add_argument("--precision", required=True)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--timeout", type=int, default=180)
    args = parser.parse_args()
    endpoint = args.endpoint.rstrip("/")
    if args.action == "shutdown":
        result = request_json(endpoint + "/shutdown", {})
    else:
        deadline = time.time() + args.timeout
        last_error = None
        result = None
        while time.time() < deadline:
            try:
                candidate = request_json(endpoint + "/health")
                if (
                    candidate.get("status") == "ready"
                    and candidate.get("precision") == args.precision
                    and candidate.get("model_revision") == MODEL_REVISION
                ):
                    result = candidate
                    break
                last_error = RuntimeError(f"服务身份错误：{candidate}")
            except Exception as error:
                last_error = error
            time.sleep(1)
        if result is None:
            raise RuntimeError(f"模型服务未就绪：{last_error}")
    if args.output is not None:
        args.output.write_text(
            json.dumps(result, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
    print(json.dumps(result, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
