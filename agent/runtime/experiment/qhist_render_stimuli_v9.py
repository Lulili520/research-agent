#!/usr/bin/env python3
"""冻结并审计 Q-HIST v9 的权威消息、Agent 合同与静态前缀。"""

from __future__ import annotations

import argparse
import hashlib
import json
from itertools import combinations
from pathlib import Path
from typing import Any

import qhist_render_stimuli as base
import qhist_v9_spec as spec


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--assets", type=Path, required=True)
    parser.add_argument("--model-path", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--seed", type=int, default=spec.SCHEDULE_SEED)
    args = parser.parse_args()
    if args.output.exists() and any(args.output.iterdir()):
        raise RuntimeError(f"输出目录必须不存在或为空：{args.output}")
    args.output.mkdir(parents=True, exist_ok=True)

    from transformers import AutoTokenizer

    tokenizer = AutoTokenizer.from_pretrained(
        str(args.model_path), local_files_only=True, use_fast=True
    )

    def token_count(text: str) -> int:
        return len(tokenizer.encode(text, add_special_tokens=False))

    episodes = base.read_jsonl(args.assets / "episodes.jsonl")
    authority_rows: list[dict[str, Any]] = []
    static_rows: list[dict[str, Any]] = []
    checks: list[dict[str, Any]] = []
    expected_contract_hash = hashlib.sha256(
        spec.AGENT_TOOL_CONTRACT.encode("utf-8")
    ).hexdigest()

    for episode in episodes:
        system_messages = [
            row for row in episode["base_messages"] if row.get("role") == "system"
        ]
        contract_metadata = episode.get("agent_tool_contract") or {}
        contract_once = (
            len(system_messages) == 1
            and str(system_messages[0].get("content") or "").count(
                spec.AGENT_TOOL_CONTRACT
            )
            == 1
            and contract_metadata.get("sha256") == expected_contract_hash
        )
        correction = episode["authority_payloads"]["C_text"]
        correction_text = base.render_authority(
            correction["field"], correction["value"]
        )
        correction_tokens = token_count(correction_text)
        neutral, sham = base.choose_neutral_pair(correction_tokens, token_count)
        rendered = {
            "N": base.render_authority(neutral[0], neutral[1]),
            "S": base.render_authority(sham[0], sham[1]),
            "C_text": correction_text,
            "C_align": correction_text,
        }
        lengths = {
            condition: token_count(text) for condition, text in rendered.items()
        }
        target_terms = {
            str(correction["field"]).lower(),
            str(correction["field"]).replace("_", " ").lower(),
            str(correction["value"]).lower(),
        }
        neutral_text = (rendered["N"] + "\n" + rendered["S"]).lower()
        no_target_leak = all(term not in neutral_text for term in target_terms)
        pairwise_ok = all(
            abs(lengths[a] - lengths[b]) <= 2
            for a, b in combinations(("N", "S", "C_text"), 2)
        )
        contract_preserved_all = True
        for condition, text in rendered.items():
            prefix_observation = (
                episode["prefix"]["truth_message"]
                if condition == "N"
                else episode["prefix"]["false_message"]
            )
            probe = tokenizer.apply_chat_template(
                [
                    *episode["base_messages"],
                    episode["prefix"]["tool_call_message"],
                    prefix_observation,
                    {"role": "system", "content": text},
                ],
                tools=episode["tool_schema"],
                tokenize=True,
                add_generation_prompt=True,
                return_tensors="pt",
                return_dict=True,
                enable_thinking=False,
            )
            decoded = tokenizer.decode(
                probe["input_ids"][0], skip_special_tokens=False
            )
            content_present = text in decoded
            contract_present = spec.AGENT_TOOL_CONTRACT in decoded
            contract_preserved_all &= contract_present
            if not content_present or not contract_present:
                raise RuntimeError(
                    f"chat template 未保留 {episode['episode_id']}/{condition} "
                    "的权威消息或 Agent 合同"
                )
            authority_rows.append(
                {
                    "episode_id": episode["episode_id"],
                    "condition": condition,
                    "role": "system",
                    "content": text,
                    "content_sha256": base.sha256_bytes(text.encode("utf-8")),
                    "token_count": lengths[condition],
                    "chat_template_probe_token_count": int(
                        probe["input_ids"].shape[1]
                    ),
                    "chat_template_probe_sha256": base.numpy_sha256(
                        probe["input_ids"]
                    ),
                    "chat_template_preserves_content": content_present,
                    "chat_template_preserves_agent_contract": contract_present,
                }
            )

        for history in ("N", "E"):
            prefix_observation = (
                episode["prefix"]["truth_message"]
                if history == "N"
                else episode["prefix"]["false_message"]
            )
            encoded = tokenizer.apply_chat_template(
                [
                    *episode["base_messages"],
                    episode["prefix"]["tool_call_message"],
                    prefix_observation,
                ],
                tools=episode["tool_schema"],
                tokenize=True,
                add_generation_prompt=True,
                return_tensors="pt",
                return_dict=True,
                enable_thinking=False,
            )
            decoded = tokenizer.decode(
                encoded["input_ids"][0], skip_special_tokens=False
            )
            static_rows.append(
                {
                    "episode_id": episode["episode_id"],
                    "prefix_history": history,
                    "input_token_count": int(encoded["input_ids"].shape[1]),
                    "input_ids_sha256": base.numpy_sha256(encoded["input_ids"]),
                    "attention_mask_sha256": base.numpy_sha256(
                        encoded["attention_mask"]
                    ),
                    "tool_schema_sha256": episode["tool_schema_sha256"],
                    "agent_tool_contract_sha256": expected_contract_hash,
                    "chat_template_preserves_agent_contract": (
                        spec.AGENT_TOOL_CONTRACT in decoded
                    ),
                }
            )

        checks.append(
            {
                "episode_id": episode["episode_id"],
                "pairwise_token_length_ok": pairwise_ok,
                "neutral_target_leak_free": no_target_leak,
                "c_text_c_align_byte_identical": (
                    rendered["C_text"].encode("utf-8")
                    == rendered["C_align"].encode("utf-8")
                ),
                "agent_contract_exactly_once": contract_once,
                "chat_template_preserves_agent_contract": contract_preserved_all,
                "token_lengths": lengths,
            }
        )

    base.write_jsonl(args.output / "authority-messages.jsonl", authority_rows)
    base.write_jsonl(args.output / "static-prefixes.jsonl", static_rows)
    base.write_jsonl(args.output / "checks.jsonl", checks)
    files = sorted(path for path in args.output.rglob("*") if path.is_file())
    all_checks_pass = bool(checks) and all(
        row["pairwise_token_length_ok"]
        and row["neutral_target_leak_free"]
        and row["c_text_c_align_byte_identical"]
        and row["agent_contract_exactly_once"]
        and row["chat_template_preserves_agent_contract"]
        for row in checks
    ) and all(
        row["chat_template_preserves_agent_contract"] for row in static_rows
    )
    script_dir = Path(__file__).resolve().parent
    manifest = {
        "schema_version": 1,
        "protocol_id": spec.PROTOCOL_ID,
        "protocol_version": spec.PROTOCOL_VERSION,
        "model_revision": spec.MODEL_REVISION,
        "schedule_seed": args.seed,
        "episodes_sha256": base.sha256_file(args.assets / "episodes.jsonl"),
        "asset_manifest_sha256": base.sha256_file(args.assets / "manifest.json"),
        "agent_tool_contract_sha256": expected_contract_hash,
        "all_checks_pass": all_checks_pass,
        "episode_count": len(episodes),
        "authority_message_count": len(authority_rows),
        "static_prefix_count": len(static_rows),
        "generator_sha256": base.sha256_file(Path(__file__)),
        "helper_sha256": base.sha256_file(
            script_dir / "qhist_render_stimuli.py"
        ),
        "v9_spec_sha256": base.sha256_file(script_dir / "qhist_v9_spec.py"),
        "files": [
            {
                "path": str(path.relative_to(args.output)).replace("\\", "/"),
                "bytes": path.stat().st_size,
                "sha256": base.sha256_file(path),
            }
            for path in files
        ],
    }
    (args.output / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(manifest, ensure_ascii=False, indent=2))
    return 0 if all_checks_pass else 1


if __name__ == "__main__":
    raise SystemExit(main())
