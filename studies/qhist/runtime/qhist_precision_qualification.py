#!/usr/bin/env python3
"""Q-HIST E0 的 Hugging Face 精度/缓存资格运行。

每次进程只加载一个冻结精度条件，执行两个无历史原生工具调用 prompt 的三次
贪心重复，并保存输入 token、结构化动作、gold-action margin、实际权重量化模块、
缓存对象和 GPU 资源证据。该脚本不运行 Q-HIST 处理轨迹。
"""

from __future__ import annotations

import argparse
import hashlib
import importlib.metadata
import json
import os
import platform
import re
import subprocess
import sys
import time
import traceback
from pathlib import Path
from typing import Any


MODEL_ID = "Qwen/Qwen3-32B"
MODEL_REVISION = "9216db5781bf21249d130ec9da846c4624c16137"
PRECISIONS = ("P00", "P10", "P01", "P11", "K16-shadow")
K4_PRECISIONS = {"P01", "P11"}
W4_PRECISIONS = {"P10", "P11"}
TOOL_CALL_RE = re.compile(r"<tool_call>\s*(\{.*?\})\s*</tool_call>", re.DOTALL)


def canonical_json(value: Any) -> str:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        default=str,
    )


def canonical_sha256(value: Any) -> str:
    return hashlib.sha256(canonical_json(value).encode("utf-8")).hexdigest()


def package_version(name: str) -> str:
    """记录可复核版本；缺包由后续条件门判失败，而不是丢失 summary。"""

    try:
        return importlib.metadata.version(name)
    except importlib.metadata.PackageNotFoundError:
        return "not-installed"


def qualification_prompts() -> dict[str, dict[str, Any]]:
    return {
        "add": {
            "messages": [
                {
                    "role": "system",
                    "content": (
                        "You are a tool-using assistant. Use the supplied tool exactly "
                        "once and do not answer in prose."
                    ),
                },
                {
                    "role": "user",
                    "content": "Add 2 and 3 using the add tool.",
                },
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
            "gold": {"name": "add", "arguments": {"a": 2, "b": 3}},
            "alternative": {"name": "add", "arguments": {"a": 2, "b": 4}},
        },
        "lookup": {
            "messages": [
                {
                    "role": "system",
                    "content": (
                        "You are a tool-using assistant. Use the supplied tool exactly "
                        "once and do not answer in prose."
                    ),
                },
                {
                    "role": "user",
                    "content": (
                        "Look up inventory record SKU-0042 using the lookup_inventory tool."
                    ),
                },
            ],
            "tools": [
                {
                    "type": "function",
                    "function": {
                        "name": "lookup_inventory",
                        "description": "Look up one inventory record by its exact ID.",
                        "parameters": {
                            "type": "object",
                            "properties": {
                                "record_id": {"type": "string"},
                            },
                            "required": ["record_id"],
                            "additionalProperties": False,
                        },
                    },
                }
            ],
            "gold": {
                "name": "lookup_inventory",
                "arguments": {"record_id": "SKU-0042"},
            },
            "alternative": {
                "name": "lookup_inventory",
                "arguments": {"record_id": "SKU-0043"},
            },
        },
    }


def parse_tool_calls(text: str) -> list[dict[str, Any]]:
    calls: list[dict[str, Any]] = []
    for match in TOOL_CALL_RE.finditer(text):
        try:
            value = json.loads(match.group(1))
        except json.JSONDecodeError:
            continue
        if not isinstance(value, dict):
            continue
        name = value.get("name")
        arguments = value.get("arguments")
        if isinstance(name, str) and isinstance(arguments, dict):
            calls.append({"name": name, "arguments": arguments})
    return calls


def format_candidate(action: dict[str, Any]) -> str:
    return f"<tool_call>\n{canonical_json(action)}\n</tool_call>"


def make_cache(precision: str, config):
    from transformers.cache_utils import Cache, DynamicCache, QuantizedCache, QuantizedLayer

    if precision in {"P00", "P10"}:
        return DynamicCache(config=config)
    if precision in K4_PRECISIONS:
        return QuantizedCache(
            backend="hqq",
            config=config,
            nbits=4,
            axis_key=1,
            axis_value=1,
            q_group_size=64,
            residual_length=1,
        )
    if precision != "K16-shadow":
        raise ValueError(precision)

    class ShadowQuantizedLayer(QuantizedLayer):
        """复用 QuantizedLayer 分段路径，但只保存 BF16 克隆。"""

        def __init__(self) -> None:
            super().__init__(
                nbits=16,
                axis_key=1,
                axis_value=1,
                q_group_size=64,
                residual_length=1,
            )
            self.shadow_quantize_calls = 0
            self.shadow_dequantize_calls = 0

        def _quantize(self, tensor, axis):
            self.shadow_quantize_calls += 1
            return tensor.detach().clone()

        def _dequantize(self, q_tensor):
            self.shadow_dequantize_calls += 1
            return q_tensor

    text_config = config.get_text_config(decoder=True)
    return Cache(layers=[ShadowQuantizedLayer() for _ in range(text_config.num_hidden_layers)])


def tensor_summary(value: Any) -> dict[str, Any] | None:
    try:
        import torch

        if isinstance(value, torch.Tensor):
            return {
                "dtype": str(value.dtype),
                "shape": list(value.shape),
                "device": str(value.device),
                "numel": value.numel(),
            }
    except Exception:
        return None
    return None


def cache_evidence(cache) -> dict[str, Any]:
    evidence: dict[str, Any] = {
        "class": f"{type(cache).__module__}.{type(cache).__name__}",
        "layers": len(cache.layers),
    }
    if not cache.layers:
        return evidence
    layer = cache.layers[0]
    evidence["layer0"] = {
        "class": f"{type(layer).__module__}.{type(layer).__name__}",
        "nbits": getattr(layer, "nbits", None),
        "axis_key": getattr(layer, "axis_key", None),
        "axis_value": getattr(layer, "axis_value", None),
        "q_group_size": getattr(layer, "q_group_size", None),
        "residual_length": getattr(layer, "residual_length", None),
        "cumulative_length": getattr(layer, "cumulative_length", None),
        "keys": tensor_summary(getattr(layer, "keys", None)),
        "values": tensor_summary(getattr(layer, "values", None)),
        "shadow_quantize_calls": getattr(layer, "shadow_quantize_calls", None),
        "shadow_dequantize_calls": getattr(layer, "shadow_dequantize_calls", None),
    }
    for label in ("_quantized_keys", "_quantized_values"):
        value = getattr(layer, label, None)
        if isinstance(value, tuple) and len(value) == 2:
            tensor, meta = value
            meta_summary = {}
            if isinstance(meta, dict):
                for key in ("nbits", "axis", "group_size", "compute_dtype"):
                    if key in meta:
                        meta_summary[key] = str(meta[key])
                for key in ("scale", "zero"):
                    summary = tensor_summary(meta.get(key))
                    if summary is not None:
                        meta_summary[key] = summary
            evidence["layer0"][label] = {
                "payload": tensor_summary(tensor),
                "meta": meta_summary,
            }
        else:
            evidence["layer0"][label] = {"payload": tensor_summary(value)}
    return evidence


def model_weight_manifest(model) -> dict[str, Any]:
    modules: list[dict[str, Any]] = []
    quantized_names: list[str] = []
    for name, module in model.named_modules():
        class_name = f"{type(module).__module__}.{type(module).__name__}"
        lowered = class_name.lower()
        if "linear" not in lowered and "hqq" not in lowered:
            continue
        record = {"name": name, "class": class_name}
        for attr in ("nbits", "group_size", "axis"):
            value = getattr(module, attr, None)
            if isinstance(value, (str, int, float, bool)) or value is None:
                record[attr] = value
        modules.append(record)
        if "hqq" in lowered or "quant" in lowered:
            quantized_names.append(name)

    def module_weight(module) -> dict[str, Any] | None:
        return tensor_summary(getattr(module, "weight", None))

    norm_dtypes = sorted(
        {
            str(parameter.dtype)
            for name, parameter in model.named_parameters()
            if "norm" in name.lower()
        }
    )
    return {
        "module_count": len(modules),
        "quantized_module_count": len(quantized_names),
        "quantized_module_names": quantized_names,
        "modules": modules,
        "input_embedding": module_weight(model.get_input_embeddings()),
        "output_embedding": module_weight(model.get_output_embeddings()),
        "normalization_parameter_dtypes": norm_dtypes,
        "config_quantization": str(getattr(model.config, "quantization_config", None)),
    }


def render_prompt(tokenizer, item: dict[str, Any]):
    encoded = tokenizer.apply_chat_template(
        item["messages"],
        tools=item["tools"],
        tokenize=True,
        add_generation_prompt=True,
        return_tensors="pt",
        return_dict=True,
        enable_thinking=False,
    )
    return encoded


def sequence_logprob(model, input_ids, attention_mask, candidate_ids, precision: str):
    import torch

    cache = make_cache(precision, model.config)
    total = 0.0
    with torch.inference_mode():
        output = model(
            input_ids=input_ids,
            attention_mask=attention_mask,
            past_key_values=cache,
            use_cache=True,
        )
        logits = output.logits[:, -1, :]
        for index, token in enumerate(candidate_ids.tolist()):
            total += float(torch.log_softmax(logits.float(), dim=-1)[0, token].item())
            token_tensor = torch.tensor([[token]], dtype=torch.long, device=input_ids.device)
            step_mask = torch.ones(
                (1, input_ids.shape[1] + index + 1),
                dtype=attention_mask.dtype,
                device=input_ids.device,
            )
            output = model(
                input_ids=token_tensor,
                attention_mask=step_mask,
                past_key_values=output.past_key_values,
                use_cache=True,
            )
            logits = output.logits[:, -1, :]
    return total / max(1, len(candidate_ids)), cache_evidence(output.past_key_values)


def load_model(model_path: Path, precision: str):
    import torch
    from transformers import AutoModelForCausalLM, QuantoConfig

    kwargs: dict[str, Any] = {
        "local_files_only": True,
        "dtype": torch.bfloat16,
        "low_cpu_mem_usage": True,
        "device_map": {"": 0},
        "attn_implementation": "sdpa",
    }
    if precision in W4_PRECISIONS:
        kwargs["quantization_config"] = QuantoConfig(
            weights="int4",
            activations=None,
            modules_to_not_convert=["lm_head"],
        )
    model = AutoModelForCausalLM.from_pretrained(str(model_path), **kwargs)
    model.eval()
    return model


def gpu_snapshot() -> dict[str, Any]:
    command = [
        "nvidia-smi",
        "--query-gpu=index,name,memory.used,memory.total,utilization.gpu",
        "--format=csv,noheader,nounits",
    ]
    try:
        value = subprocess.run(command, check=True, capture_output=True, text=True)
        return {"raw": value.stdout.strip()}
    except Exception as error:
        return {"error": f"{type(error).__name__}: {error}"}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--precision", choices=PRECISIONS, required=True)
    parser.add_argument("--model-path", type=Path, required=True)
    parser.add_argument("--model-id", default=MODEL_ID)
    parser.add_argument("--model-revision", default=MODEL_REVISION)
    parser.add_argument("--seed", type=int, default=20260903)
    parser.add_argument("--max-new-tokens", type=int, default=128)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    if args.output.exists() and any(args.output.iterdir()):
        raise RuntimeError(f"输出目录必须不存在或为空：{args.output}")
    args.output.mkdir(parents=True, exist_ok=True)
    os.environ["HF_HUB_OFFLINE"] = "1"
    os.environ["TRANSFORMERS_OFFLINE"] = "1"
    os.environ["TOKENIZERS_PARALLELISM"] = "false"

    import numpy as np
    import torch
    import transformers
    from transformers import AutoTokenizer

    torch.manual_seed(args.seed)
    np.random.seed(args.seed % (2**32 - 1))
    started = time.time()
    summary: dict[str, Any] = {
        "schema_version": 1,
        "status": "running",
        "model_id": args.model_id,
        "model_revision": args.model_revision,
        "precision": args.precision,
        "seed": args.seed,
        "software": {
            "python": sys.version,
            "platform": platform.platform(),
            "torch": torch.__version__,
            "transformers": transformers.__version__,
            "numpy": np.__version__,
            "hqq": package_version("hqq"),
            "optimum_quanto": package_version("optimum-quanto"),
        },
        "gpu_before": gpu_snapshot(),
    }
    results: list[dict[str, Any]] = []
    exit_code = 1
    gpu_started = time.time()
    try:
        tokenizer = AutoTokenizer.from_pretrained(
            str(args.model_path), local_files_only=True, use_fast=True
        )
        model = load_model(args.model_path, args.precision)
        load_finished = time.time()
        weight_manifest = model_weight_manifest(model)
        (args.output / "weight-manifest.json").write_text(
            json.dumps(weight_manifest, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        device = model.get_input_embeddings().weight.device
        prompt_catalog = qualification_prompts()
        prompt_records = {}
        for prompt_id, item in prompt_catalog.items():
            encoded = render_prompt(tokenizer, item)
            input_ids = encoded["input_ids"].to(device)
            attention_mask = encoded["attention_mask"].to(device)
            input_hash = hashlib.sha256(
                input_ids.detach().cpu().numpy().tobytes()
            ).hexdigest()
            tool_hash = canonical_sha256(item["tools"])
            gold_ids = tokenizer.encode(
                format_candidate(item["gold"]), add_special_tokens=False
            )
            alt_ids = tokenizer.encode(
                format_candidate(item["alternative"]), add_special_tokens=False
            )
            gold_lp, gold_cache = sequence_logprob(
                model,
                input_ids,
                attention_mask,
                torch.tensor(gold_ids, dtype=torch.long, device=device),
                args.precision,
            )
            alt_lp, alt_cache = sequence_logprob(
                model,
                input_ids,
                attention_mask,
                torch.tensor(alt_ids, dtype=torch.long, device=device),
                args.precision,
            )
            actions = []
            for repeat in (1, 2, 3):
                cache = make_cache(args.precision, model.config)
                torch.cuda.reset_peak_memory_stats()
                generation_started = time.time()
                with torch.inference_mode():
                    generated = model.generate(
                        input_ids=input_ids,
                        attention_mask=attention_mask,
                        past_key_values=cache,
                        do_sample=False,
                        max_new_tokens=args.max_new_tokens,
                        pad_token_id=tokenizer.eos_token_id,
                        eos_token_id=tokenizer.eos_token_id,
                        return_dict_in_generate=True,
                    )
                torch.cuda.synchronize()
                new_ids = generated.sequences[0, input_ids.shape[1] :]
                text = tokenizer.decode(new_ids, skip_special_tokens=False)
                calls = parse_tool_calls(text)
                action = calls[0] if len(calls) == 1 else None
                passed = action == item["gold"]
                record = {
                    "unit_id": f"QUAL-{args.precision}-{prompt_id}-r{repeat}",
                    "precision": args.precision,
                    "prompt_id": prompt_id,
                    "repeat": repeat,
                    "input_token_count": int(input_ids.shape[1]),
                    "input_ids_sha256": input_hash,
                    "tool_schema_sha256": tool_hash,
                    "generated_token_count": int(new_ids.shape[0]),
                    "raw_text": text,
                    "parsed_calls": calls,
                    "action": action,
                    "gold": item["gold"],
                    "passed": passed,
                    "elapsed_seconds": round(time.time() - generation_started, 6),
                    "peak_memory_allocated_bytes": torch.cuda.max_memory_allocated(),
                    "peak_memory_reserved_bytes": torch.cuda.max_memory_reserved(),
                    "cache_evidence": cache_evidence(cache),
                }
                results.append(record)
                actions.append(canonical_json(action))
                with (args.output / "qualification-results.jsonl").open(
                    "a", encoding="utf-8", newline="\n"
                ) as stream:
                    stream.write(canonical_json(record) + "\n")
                    stream.flush()
                    os.fsync(stream.fileno())
            modal_count = max(actions.count(value) for value in set(actions))
            prompt_records[prompt_id] = {
                "input_token_count": int(input_ids.shape[1]),
                "input_ids_sha256": input_hash,
                "tool_schema_sha256": tool_hash,
                "gold_action_normalized_logprob": gold_lp,
                "alternative_action_normalized_logprob": alt_lp,
                "gold_action_margin": gold_lp - alt_lp,
                "gold_cache_evidence": gold_cache,
                "alternative_cache_evidence": alt_cache,
                "nondeterministic_branch_rate": 1.0 - modal_count / len(actions),
            }

        own_checks = {
            "six_units_completed": len(results) == 6,
            "all_native_tool_calls_parse_and_match_gold": all(
                row["passed"] for row in results
            ),
            "deterministic_branch_rate_at_most_0_05": all(
                row["nondeterministic_branch_rate"] <= 0.05
                for row in prompt_records.values()
            ),
            "weight_quantization_matches_condition": (
                weight_manifest["quantized_module_count"] > 0
                if args.precision in W4_PRECISIONS
                else weight_manifest["quantized_module_count"] == 0
            ),
            "cache_class_matches_condition": all(
                (
                    "QuantizedCache" in row["cache_evidence"]["class"]
                    if args.precision in K4_PRECISIONS
                    else (
                        "Shadow" in row["cache_evidence"]["layer0"]["class"]
                        if args.precision == "K16-shadow"
                        else "DynamicCache" in row["cache_evidence"]["class"]
                    )
                )
                for row in results
            ),
        }
        summary.update(
            {
                "status": "succeeded" if all(own_checks.values()) else "failed",
                "load_seconds": round(load_finished - gpu_started, 6),
                "prompt_records": prompt_records,
                "checks": own_checks,
                "completed_units": len(results),
                "passed_units": sum(bool(row["passed"]) for row in results),
                "weight_manifest_sha256": hashlib.sha256(
                    (args.output / "weight-manifest.json").read_bytes()
                ).hexdigest(),
            }
        )
        exit_code = 0 if summary["status"] == "succeeded" else 1
    except Exception as error:
        summary.update(
            {
                "status": "failed",
                "error_type": type(error).__name__,
                "error": str(error),
                "traceback": traceback.format_exc(),
            }
        )
    finally:
        if torch.cuda.is_available():
            try:
                torch.cuda.synchronize()
            except Exception:
                pass
            summary["gpu_peak_memory_allocated_bytes"] = torch.cuda.max_memory_allocated()
            summary["gpu_peak_memory_reserved_bytes"] = torch.cuda.max_memory_reserved()
        summary["gpu_resident_seconds"] = round(time.time() - gpu_started, 6)
        summary["elapsed_seconds"] = round(time.time() - started, 6)
        summary["gpu_after"] = gpu_snapshot()
        (args.output / "summary.json").write_text(
            json.dumps(summary, ensure_ascii=False, indent=2, default=str) + "\n",
            encoding="utf-8",
        )
        print(json.dumps(summary, ensure_ascii=False, indent=2, default=str))
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
