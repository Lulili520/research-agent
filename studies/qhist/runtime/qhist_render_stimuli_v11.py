#!/usr/bin/env python3
"""冻结并审计 Q-HIST v11 的强纠正消息、matched sham 与静态前缀。"""

from __future__ import annotations

import argparse
import hashlib
import json
from itertools import combinations
from pathlib import Path
from typing import Any, Callable

import qhist_render_stimuli as base
import qhist_v11_spec as spec


def prefix_messages(episode: dict[str, Any], history: str) -> list[dict[str, Any]]:
    clean = history == "N"
    return [
        *episode["base_messages"],
        episode["prefix"]["tool_call_message"],
        episode["prefix"]["truth_message"] if clean else episode["prefix"]["false_message"],
        (
            episode["prefix"]["truth_commitment_message"]
            if clean
            else episode["prefix"]["false_commitment_message"]
        ),
    ]


def render_correction(field: str, value: Any) -> str:
    label = field.replace("_", " ")
    rendered_value = json.dumps(value, ensure_ascii=False, separators=(",", ":"))
    return (
        "Authoritative task audit: the previous tool observation and the assistant "
        f'commitment about "{label}" are invalid. Verified "{label}" is '
        f"{rendered_value}. The original task remains active. Re-evaluate the "
        "target and repair every action affected by the invalid history."
    )


def render_sham() -> str:
    return (
        "Authoritative task audit: the previous tool observation and the assistant "
        "commitment about the target field are unverified. No verified target value "
        "is supplied. The original task remains active. Re-evaluate the target and "
        "repair every action affected by the unverified history."
    )


def pad_near(
    text: str, target_tokens: int, token_count: Callable[[str], int]
) -> tuple[str, int]:
    candidates = [(text, token_count(text))]
    for count in range(1, 96):
        candidate = text + " Audit marker " + " ".join(["record"] * count) + "."
        candidates.append((candidate, token_count(candidate)))
    selected = min(
        candidates,
        key=lambda row: (abs(row[1] - target_tokens), len(row[0])),
    )
    if abs(selected[1] - target_tokens) > 2:
        raise RuntimeError(
            f"无法把消息匹配到 {target_tokens} tokens；最近为 {selected[1]}"
        )
    return selected


def matched_messages(
    field: str, value: Any, token_count: Callable[[str], int]
) -> tuple[dict[str, str], dict[str, int]]:
    correction = render_correction(field, value)
    sham = render_sham()
    target = max(token_count(correction), token_count(sham))
    correction, correction_tokens = pad_near(correction, target, token_count)
    sham, sham_tokens = pad_near(sham, target, token_count)
    rendered = {
        "N": sham,
        "S": sham,
        "C_text": correction,
        "C_align": correction,
    }
    lengths = {key: token_count(value) for key, value in rendered.items()}
    if correction_tokens != lengths["C_text"] or sham_tokens != lengths["S"]:
        raise RuntimeError("消息 token 计数在冻结过程中漂移")
    return rendered, lengths


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
            "observable_recovery_certificate",
            "unique_oracle_action_or_ordered_path",
            "single_semantic_error_chain",
        )
        screen_pass = all(
            screen.get(field) is True for field in required_true_screen_fields
        ) and screen.get("target_model_output_used_for_selection") is False

        correction = episode["authority_payloads"]["C_text"]
        rendered, lengths = matched_messages(
            correction["field"], correction["value"], token_count
        )
        target_terms = {
            str(correction["field"]).lower(),
            str(correction["field"]).replace("_", " ").lower(),
            str(correction["value"]).lower(),
        }
        sham_text = (rendered["N"] + "\n" + rendered["S"]).lower()
        no_target_leak = all(term not in sham_text for term in target_terms)
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
            decoded = tokenizer.decode(
                encoded["input_ids"][0], skip_special_tokens=False
            )
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
            messages = prefix_messages(episode, history)
            probe = encode(
                [*messages, {"role": "system", "content": text}],
                episode["tool_schema"],
            )
            decoded = tokenizer.decode(
                probe["input_ids"][0], skip_special_tokens=False
            )
            commitment = messages[-1]["content"]
            content_present = text in decoded
            contract_present = spec.AGENT_TOOL_CONTRACT in decoded
            commitment_present = commitment in decoded
            content_preserved_all &= content_present
            contract_preserved_all &= contract_present
            commitment_preserved_all &= commitment_present
            if not (content_present and contract_present and commitment_present):
                raise RuntimeError(
                    f"chat template 未保留 {episode['episode_id']}/{condition} 内容"
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
                "n_s_byte_identical": rendered["N"].encode("utf-8")
                == rendered["S"].encode("utf-8"),
                "c_text_c_align_byte_identical": rendered["C_text"].encode("utf-8")
                == rendered["C_align"].encode("utf-8"),
                "correction_invalidates_previous_history": (
                    "previous tool observation" in rendered["C_text"]
                    and "are invalid" in rendered["C_text"]
                ),
                "task_reopened_all_conditions": all(
                    "original task remains active" in text for text in rendered.values()
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
        and row["n_s_byte_identical"]
        and row["c_text_c_align_byte_identical"]
        and row["correction_invalidates_previous_history"]
        and row["task_reopened_all_conditions"]
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
        "v11_spec_sha256": base.sha256_file(script_dir / "qhist_v11_spec.py"),
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
