#!/usr/bin/env python3
"""冻结并审计 Q-HIST v10 的外生承诺前缀与权威纠正消息。"""

from __future__ import annotations

import argparse
import hashlib
import json
from itertools import combinations
from pathlib import Path
from typing import Any

import qhist_render_stimuli as base
import qhist_v10_spec as spec


def prefix_messages(episode: dict[str, Any], history: str) -> list[dict[str, Any]]:
    clean = history == "N"
    return [
        *episode["base_messages"],
        episode["prefix"]["tool_call_message"],
        (
            episode["prefix"]["truth_message"]
            if clean
            else episode["prefix"]["false_message"]
        ),
        (
            episode["prefix"]["truth_commitment_message"]
            if clean
            else episode["prefix"]["false_commitment_message"]
        ),
    ]


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

    def encode(messages: list[dict[str, Any]], tools: list[dict[str, Any]]):
        return tokenizer.apply_chat_template(
            messages,
            tools=tools,
            tokenize=True,
            add_generation_prompt=True,
            return_tensors="pt",
            return_dict=True,
            enable_thinking=False,
        )

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
        screen = episode.get("construct_screen") or {}
        required_true_screen_fields = (
            "complete_single_turn_intent",
            "programmatic_truth",
            "unique_error_action",
            "unique_oracle_action_or_ordered_path",
            "single_semantic_error_chain",
        )
        screen_pass = all(
            screen.get(field) is True for field in required_true_screen_fields
        ) and screen.get("target_model_output_used_for_selection") is False
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
        authority_pairwise_ok = all(
            abs(lengths[a] - lengths[b]) <= 2
            for a, b in combinations(("N", "S", "C_text"), 2)
        )

        prefix_counts: dict[str, int] = {}
        prefix_hashes: dict[str, str] = {}
        content_preserved_all = True
        contract_preserved_all = True
        commitment_preserved_all = True
        for history in ("N", "E"):
            messages = prefix_messages(episode, history)
            encoded = encode(messages, episode["tool_schema"])
            decoded = tokenizer.decode(encoded["input_ids"][0], skip_special_tokens=False)
            commitment = messages[-1]["content"]
            prefix_counts[history] = int(encoded["input_ids"].shape[1])
            prefix_hashes[history] = base.numpy_sha256(encoded["input_ids"])
            contract_present = spec.AGENT_TOOL_CONTRACT in decoded
            commitment_present = commitment in decoded
            contract_preserved_all &= contract_present
            commitment_preserved_all &= commitment_present
            static_rows.append(
                {
                    "episode_id": episode["episode_id"],
                    "prefix_history": history,
                    "input_token_count": prefix_counts[history],
                    "input_ids_sha256": prefix_hashes[history],
                    "attention_mask_sha256": base.numpy_sha256(
                        encoded["attention_mask"]
                    ),
                    "tool_schema_sha256": episode["tool_schema_sha256"],
                    "agent_tool_contract_sha256": expected_contract_hash,
                    "commitment_sha256": hashlib.sha256(
                        commitment.encode("utf-8")
                    ).hexdigest(),
                    "chat_template_preserves_agent_contract": contract_present,
                    "chat_template_preserves_commitment": commitment_present,
                }
            )

        for condition, text in rendered.items():
            history = "N" if condition == "N" else "E"
            probe = encode(
                [
                    *prefix_messages(episode, history),
                    {"role": "system", "content": text},
                ],
                episode["tool_schema"],
            )
            decoded = tokenizer.decode(probe["input_ids"][0], skip_special_tokens=False)
            commitment = prefix_messages(episode, history)[-1]["content"]
            content_present = text in decoded
            contract_present = spec.AGENT_TOOL_CONTRACT in decoded
            commitment_present = commitment in decoded
            content_preserved_all &= content_present
            contract_preserved_all &= contract_present
            commitment_preserved_all &= commitment_present
            if not (content_present and contract_present and commitment_present):
                raise RuntimeError(
                    f"chat template 未保留 {episode['episode_id']}/{condition} 的合同、"
                    "承诺或权威消息"
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
                    "chat_template_preserves_commitment": commitment_present,
                }
            )

        prefix_length_gap = abs(prefix_counts["N"] - prefix_counts["E"])
        checks.append(
            {
                "episode_id": episode["episode_id"],
                "authority_pairwise_token_length_ok": authority_pairwise_ok,
                "neutral_target_leak_free": no_target_leak,
                "c_text_c_align_byte_identical": (
                    rendered["C_text"].encode("utf-8")
                    == rendered["C_align"].encode("utf-8")
                ),
                "agent_contract_exactly_once": contract_once,
                "construct_screen_pass": screen_pass,
                "chat_template_preserves_all_content": content_preserved_all,
                "chat_template_preserves_agent_contract": contract_preserved_all,
                "chat_template_preserves_commitment": commitment_preserved_all,
                "clean_error_prefix_token_gap": prefix_length_gap,
                "clean_error_prefix_token_gap_ok": prefix_length_gap <= 2,
                "authority_token_lengths": lengths,
                "prefix_token_lengths": prefix_counts,
                "prefix_input_hashes": prefix_hashes,
            }
        )

    base.write_jsonl(args.output / "authority-messages.jsonl", authority_rows)
    base.write_jsonl(args.output / "static-prefixes.jsonl", static_rows)
    base.write_jsonl(args.output / "checks.jsonl", checks)
    all_checks_pass = bool(checks) and all(
        row["authority_pairwise_token_length_ok"]
        and row["neutral_target_leak_free"]
        and row["c_text_c_align_byte_identical"]
        and row["agent_contract_exactly_once"]
        and row["construct_screen_pass"]
        and row["chat_template_preserves_all_content"]
        and row["chat_template_preserves_agent_contract"]
        and row["chat_template_preserves_commitment"]
        and row["clean_error_prefix_token_gap_ok"]
        for row in checks
    )
    files = sorted(path for path in args.output.rglob("*") if path.is_file())
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
        "helper_sha256": base.sha256_file(script_dir / "qhist_render_stimuli.py"),
        "v10_spec_sha256": base.sha256_file(script_dir / "qhist_v10_spec.py"),
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
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps(manifest, ensure_ascii=False, indent=2))
    return 0 if all_checks_pass else 1


if __name__ == "__main__":
    raise SystemExit(main())
