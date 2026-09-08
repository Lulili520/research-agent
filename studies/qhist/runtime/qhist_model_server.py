#!/usr/bin/env python3
"""Q-HIST 的本机只读 Hugging Face 推理服务；每进程固定一种精度。"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import threading
import time
import traceback
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

from qhist_precision_qualification import (
    PRECISIONS,
    cache_evidence,
    load_model,
    make_cache,
    model_weight_manifest,
    parse_tool_calls,
)


def canonical_json(value: Any) -> str:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        default=str,
    )


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def append_jsonl(path: Path, value: Any) -> None:
    with path.open("a", encoding="utf-8", newline="\n") as stream:
        stream.write(canonical_json(value) + "\n")
        stream.flush()
        os.fsync(stream.fileno())


def visible_content(text: str) -> str:
    value = text.replace("<|im_end|>", "").strip()
    if value.startswith("<think>") and "</think>" in value:
        value = value.split("</think>", 1)[1].strip()
    return value


class InferenceState:
    def __init__(self, args: argparse.Namespace) -> None:
        import numpy as np
        import torch
        import transformers
        from transformers import AutoTokenizer

        self.args = args
        self.torch = torch
        self.lock = threading.Lock()
        self.started = time.time()
        self.request_count = 0
        self.failed_request_count = 0
        self.request_ids: set[str] = set()
        self.generation_seconds = 0.0
        torch.manual_seed(args.seed)
        np.random.seed(args.seed % (2**32 - 1))
        self.software = {
            "python": os.sys.version,
            "torch": torch.__version__,
            "transformers": transformers.__version__,
            "numpy": np.__version__,
        }
        self.tokenizer = AutoTokenizer.from_pretrained(
            str(args.model_path), local_files_only=True, use_fast=True
        )
        self.model = load_model(args.model_path, args.precision)
        self.weight_manifest = model_weight_manifest(self.model)
        self.weight_manifest_path = args.output / "weight-manifest.json"
        self.weight_manifest_path.write_text(
            json.dumps(self.weight_manifest, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        self.loaded_at = time.time()

    def generate(self, payload: dict[str, Any]) -> dict[str, Any]:
        torch = self.torch
        request_id = str(payload["request_id"])
        if request_id in self.request_ids:
            raise ValueError(f"重复 request_id：{request_id}")
        messages = payload["messages"]
        tools = payload["tools"]
        max_new_tokens = int(payload.get("max_new_tokens", 256))
        if payload.get("expected_precision") != self.args.precision:
            raise ValueError(
                "请求精度与服务进程不一致："
                f"{payload.get('expected_precision')} != {self.args.precision}"
            )
        if not 1 <= max_new_tokens <= 256:
            raise ValueError("max_new_tokens 必须位于 [1,256]")
        encoded = self.tokenizer.apply_chat_template(
            messages,
            tools=tools,
            tokenize=True,
            add_generation_prompt=True,
            return_tensors="pt",
            return_dict=True,
            enable_thinking=False,
        )
        if int(encoded["input_ids"].shape[1]) > 8192:
            raise ValueError(
                f"输入超过冻结的 8192-token 上限：{encoded['input_ids'].shape[1]}"
            )
        device = self.model.get_input_embeddings().weight.device
        input_ids = encoded["input_ids"].to(device)
        attention_mask = encoded["attention_mask"].to(device)
        cache = make_cache(self.args.precision, self.model.config)
        started = time.time()
        with torch.inference_mode():
            output = self.model.generate(
                input_ids=input_ids,
                attention_mask=attention_mask,
                past_key_values=cache,
                do_sample=False,
                max_new_tokens=max_new_tokens,
                pad_token_id=self.tokenizer.eos_token_id,
                eos_token_id=self.tokenizer.eos_token_id,
                return_dict_in_generate=True,
            )
        torch.cuda.synchronize()
        elapsed = time.time() - started
        new_ids = output.sequences[0, input_ids.shape[1] :]
        raw_text = self.tokenizer.decode(new_ids, skip_special_tokens=False)
        result = {
            "request_id": request_id,
            "precision": self.args.precision,
            "model_revision": self.args.model_revision,
            "raw_text": raw_text,
            "visible_content": visible_content(raw_text),
            "parsed_actions": parse_tool_calls(raw_text),
            "input_token_count": int(input_ids.shape[1]),
            "generated_token_count": int(new_ids.shape[0]),
            "input_ids_sha256": hashlib.sha256(
                input_ids.detach().cpu().numpy().tobytes()
            ).hexdigest(),
            "tool_schema_sha256": hashlib.sha256(
                canonical_json(tools).encode("utf-8")
            ).hexdigest(),
            "cache_evidence": cache_evidence(cache),
            "elapsed_seconds": round(elapsed, 6),
        }
        self.request_count += 1
        self.request_ids.add(request_id)
        self.generation_seconds += elapsed
        append_jsonl(
            self.args.output / "requests.jsonl",
            {
                "request_id": request_id,
                "request_sha256": hashlib.sha256(
                    canonical_json(payload).encode("utf-8")
                ).hexdigest(),
                "response_sha256": hashlib.sha256(
                    canonical_json(result).encode("utf-8")
                ).hexdigest(),
                "input_token_count": result["input_token_count"],
                "generated_token_count": result["generated_token_count"],
                "elapsed_seconds": result["elapsed_seconds"],
            },
        )
        return result

    def summary(self) -> dict[str, Any]:
        torch = self.torch
        return {
            "schema_version": 1,
            "protocol_id": "QHIST-EXP",
            "protocol_version": 8,
            "status": "succeeded" if self.failed_request_count == 0 else "failed",
            "precision": self.args.precision,
            "host": self.args.host,
            "port": self.args.port,
            "software": self.software,
            "model_load_seconds": round(self.loaded_at - self.started, 6),
            "request_count": self.request_count,
            "failed_request_count": self.failed_request_count,
            "generation_seconds": round(self.generation_seconds, 6),
            "gpu_resident_seconds": round(time.time() - self.started, 6),
            "gpu_peak_memory_allocated_bytes": torch.cuda.max_memory_allocated(),
            "gpu_peak_memory_reserved_bytes": torch.cuda.max_memory_reserved(),
            "weight_manifest_sha256": sha256_file(self.weight_manifest_path),
        }


def make_handler(state: InferenceState):
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, format, *args):
            return

        def send_json(self, status: int, value: Any) -> None:
            body = json.dumps(value, ensure_ascii=False, default=str).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def do_GET(self):
            if self.path != "/health":
                self.send_json(404, {"error": "not-found"})
                return
            self.send_json(
                200,
                {
                    "status": "ready",
                    "precision": state.args.precision,
                    "model_revision": state.args.model_revision,
                    "weight_manifest_sha256": sha256_file(
                        state.weight_manifest_path
                    ),
                },
            )

        def do_POST(self):
            if self.path == "/shutdown":
                self.send_json(200, {"status": "shutting-down"})
                threading.Thread(target=self.server.shutdown, daemon=True).start()
                return
            if self.path != "/generate":
                self.send_json(404, {"error": "not-found"})
                return
            try:
                length = int(self.headers.get("Content-Length", "0"))
                payload = json.loads(self.rfile.read(length).decode("utf-8"))
                with state.lock:
                    result = state.generate(payload)
                self.send_json(200, result)
            except Exception as error:
                state.failed_request_count += 1
                append_jsonl(
                    state.args.output / "errors.jsonl",
                    {
                        "error_type": type(error).__name__,
                        "error": str(error),
                        "traceback": traceback.format_exc(),
                    },
                )
                self.send_json(
                    500,
                    {"error_type": type(error).__name__, "error": str(error)},
                )

    return Handler


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--precision", choices=PRECISIONS, required=True)
    parser.add_argument("--model-path", type=Path, required=True)
    parser.add_argument("--model-revision", required=True)
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, required=True)
    parser.add_argument("--seed", type=int, default=20260903)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists() and any(args.output.iterdir()):
        raise RuntimeError(f"服务输出目录必须不存在或为空：{args.output}")
    args.output.mkdir(parents=True, exist_ok=True)
    os.environ["HF_HUB_OFFLINE"] = "1"
    os.environ["TRANSFORMERS_OFFLINE"] = "1"
    os.environ["TOKENIZERS_PARALLELISM"] = "false"
    state = InferenceState(args)
    server = ThreadingHTTPServer((args.host, args.port), make_handler(state))
    try:
        server.serve_forever()
    finally:
        server.server_close()
        (args.output / "summary.json").write_text(
            json.dumps(state.summary(), ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
