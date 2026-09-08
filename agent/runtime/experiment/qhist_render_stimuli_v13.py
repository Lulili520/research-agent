#!/usr/bin/env python3
"""冻结 Q-HIST v13 的 72 个首决策输入并审计 token、泄漏和同源性。"""

from __future__ import annotations

import argparse
import copy
import hashlib
import json
from pathlib import Path
from typing import Any

import qhist_render_stimuli as base
import qhist_v13_spec as spec


PADDING_WORDS = (
    "register", "entry", "sequence", "marker", "ledger", "context", "record", "note"
)


def flatten_gap_blocks(episode: dict[str, Any], gap: int) -> list[dict[str, Any]]:
    if gap == 0:
        return []
    if gap != 3 or len(episode["gap_blocks"]) != 3:
        raise RuntimeError(f"非法 gap：{gap}")
    return [
        copy.deepcopy(message)
        for block in episode["gap_blocks"]
        for message in block
    ]


def prefix_messages(
    episode: dict[str, Any], truth: bool, commitment: str | None = None
) -> list[dict[str, Any]]:
    selected = (
        episode["prefix"]["truth_messages"]
        if truth
        else episode["prefix"]["false_messages"]
    )
    text = commitment if commitment is not None else (
        episode["prefix"]["truth_commitment"]
        if truth else episode["prefix"]["false_commitment"]
    )
    return [
        *copy.deepcopy(episode["base_messages"]),
        *copy.deepcopy(selected),
        {"role": "assistant", "content": text},
    ]


def encode(tokenizer: Any, messages: list[dict[str, Any]], tools: list[dict[str, Any]]):
    return tokenizer.apply_chat_template(
        messages,
        tools=tools,
        tokenize=True,
        add_generation_prompt=True,
        return_tensors="pt",
        return_dict=True,
        enable_thinking=False,
    )


def encoded_count(tokenizer: Any, messages: list[dict[str, Any]], tools: list[dict[str, Any]]) -> int:
    return int(encode(tokenizer, messages, tools)["input_ids"].shape[1])


def padded_text_candidates(text: str, limit: int = 192):
    yield text
    suffix: list[str] = []
    for index in range(limit):
        suffix.append(PADDING_WORDS[index % len(PADDING_WORDS)])
        yield text + " Administrative " + " ".join(suffix) + "."


def pad_at_index(
    tokenizer: Any,
    messages: list[dict[str, Any]],
    tools: list[dict[str, Any]],
    message_index: int,
    target: int,
) -> tuple[list[dict[str, Any]], int]:
    original = str(messages[message_index]["content"])
    best: tuple[int, int, str] | None = None
    for candidate in padded_text_candidates(original):
        trial = copy.deepcopy(messages)
        trial[message_index]["content"] = candidate
        count = encoded_count(tokenizer, trial, tools)
        score = (abs(count - target), len(candidate), candidate)
        if best is None or score < best:
            best = score
        if count == target:
            return trial, count
        if count > target + 8 and best[0] <= 2:
            break
    if best is None or best[0] > 2:
        raise RuntimeError(f"无法把首决策输入匹配到 {target} tokens")
    trial = copy.deepcopy(messages)
    trial[message_index]["content"] = best[2]
    return trial, encoded_count(tokenizer, trial, tools)


def balance_group(
    tokenizer: Any,
    variants: dict[str, tuple[list[dict[str, Any]], int]],
    tools: list[dict[str, Any]],
) -> dict[str, tuple[list[dict[str, Any]], int]]:
    base_counts = {
        name: encoded_count(tokenizer, messages, tools)
        for name, (messages, _) in variants.items()
    }
    target = max(base_counts.values())
    balanced = {
        name: pad_at_index(tokenizer, messages, tools, index, target)
        for name, (messages, index) in variants.items()
    }
    counts = [count for _, count in balanced.values()]
    if max(counts) - min(counts) > 2:
        raise RuntimeError(f"组内 token 差超过2：{dict(zip(balanced, counts))}")
    return balanced


def stimulus_row(
    tokenizer: Any,
    episode: dict[str, Any],
    module: str,
    condition: str,
    gap: int,
    messages: list[dict[str, Any]],
) -> dict[str, Any]:
    encoded = encode(tokenizer, messages, episode["tool_schema"])
    decoded = tokenizer.decode(encoded["input_ids"][0], skip_special_tokens=False)
    if spec.AGENT_TOOL_CONTRACT not in decoded:
        raise RuntimeError(f"{episode['episode_id']}/{condition} 丢失 agent contract")
    if str(messages[-1].get("content") or "") not in decoded:
        raise RuntimeError(f"{episode['episode_id']}/{condition} 丢失末条可见消息")
    return {
        "stimulus_id": f'{episode["episode_id"]}-{module}-{condition}-g{gap}',
        "episode_id": episode["episode_id"],
        "scenario": episode["scenario"],
        "family": episode["family"],
        "module": module,
        "condition": condition,
        "gap": gap,
        "messages": messages,
        "messages_sha256": spec.canonical_sha256(messages),
        "input_token_count": int(encoded["input_ids"].shape[1]),
        "input_ids_sha256": base.numpy_sha256(encoded["input_ids"]),
        "attention_mask_sha256": base.numpy_sha256(encoded["attention_mask"]),
        "tool_schema_sha256": episode["tool_schema_sha256"],
        "agent_tool_contract_sha256": episode["agent_tool_contract"]["sha256"],
        "gap_blocks_sha256": episode["gap_blocks_sha256"],
        "chat_template_preserves_content": True,
    }


def lexical_checks(episode: dict[str, Any], treatments: dict[str, str]) -> dict[str, Any]:
    r0 = treatments["R0"].lower()
    audit = treatments["R_audit"].lower()
    fact = treatments["R_fact"].lower()
    banned_r0 = (
        "target", "error", "false", "truth", "verify", "verified", "check",
        "audit", "repair", str(episode["scenario"]).lower(),
    )
    values = {
        str(episode["treatment_templates"]["R_fact"]).lower(),
    }
    predicate_values = []
    # R_audit 不得出现冻结真假值；对布尔值使用结构化 field/value 串而非普通 true。
    for raw in (
        episode.get("dynamic_roles") or {},
        episode["prefix"]["truth_commitment"],
        episode["prefix"]["false_commitment"],
    ):
        predicate_values.append(str(raw).lower())
    oracle_string = json.loads(
        episode["treatment_templates"]["R_fact"].split("request: ", 1)[1]
    )
    oracle_value = str(oracle_string["value"]).lower()
    false_value = None
    if "invalid" in fact:
        false_value = "not-rendered-in-template"
    return {
        "r0_has_no_target_or_audit_language": all(term not in r0 for term in banned_r0),
        "r_audit_has_no_oracle_value": oracle_value not in audit,
        "r_fact_contains_oracle_value": oracle_value in fact,
        "r_fact_marks_prior_invalid": "prior proposition invalid" in fact,
        "r_audit_requests_read_before_action": (
            "available read tool" in audit and "then finish" in audit
        ),
        "r0_template_sha256": hashlib.sha256(treatments["R0"].encode()).hexdigest(),
        "r_audit_template_sha256": hashlib.sha256(treatments["R_audit"].encode()).hexdigest(),
        "r_fact_template_sha256": hashlib.sha256(treatments["R_fact"].encode()).hexdigest(),
        "diagnostic_false_value": false_value,
        "diagnostic_inputs": predicate_values,
        "diagnostic_template_set": sorted(values),
    }


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
    episodes = base.read_jsonl(args.assets / "episodes.jsonl")
    stimuli: list[dict[str, Any]] = []
    checks: list[dict[str, Any]] = []

    for episode in episodes:
        by_key: dict[tuple[str, str, int], dict[str, Any]] = {}
        balanced_treatments: dict[tuple[int, str], str] = {}
        for gap in spec.GAPS:
            gap_messages = flatten_gap_blocks(episode, gap)
            a_variants: dict[str, tuple[list[dict[str, Any]], int]] = {}
            for condition, truth in (("A_N", True), ("A_E", False)):
                messages = prefix_messages(episode, truth)
                messages.extend(copy.deepcopy(gap_messages))
                commitment_index = len(prefix_messages(episode, truth)) - 1
                a_variants[condition] = (messages, commitment_index)
            for condition, (messages, _) in balance_group(
                tokenizer, a_variants, episode["tool_schema"]
            ).items():
                row = stimulus_row(tokenizer, episode, "A", condition, gap, messages)
                stimuli.append(row)
                by_key[("A", condition, gap)] = row

            r_variants: dict[str, tuple[list[dict[str, Any]], int]] = {}
            for condition in ("R0", "R_audit", "R_fact"):
                messages = prefix_messages(episode, False)
                messages.extend(copy.deepcopy(gap_messages))
                messages.append(
                    {"role": "system", "content": episode["treatment_templates"][condition]}
                )
                r_variants[condition] = (messages, len(messages) - 1)
            for condition, (messages, _) in balance_group(
                tokenizer, r_variants, episode["tool_schema"]
            ).items():
                balanced_treatments[(gap, condition)] = messages[-1]["content"]
                row = stimulus_row(tokenizer, episode, "R", condition, gap, messages)
                stimuli.append(row)
                by_key[("R", condition, gap)] = row

        e_messages = prefix_messages(episode, False)
        e_messages.append(copy.deepcopy(episode["predecessor_checkpoint"]["assistant_message"]))
        e_messages.extend(copy.deepcopy(episode["predecessor_checkpoint"]["tool_messages"]))
        e_messages.extend(flatten_gap_blocks(episode, 3))
        e_messages.append(
            {"role": "system", "content": balanced_treatments[(3, "R_fact")]}
        )
        for condition in ("E_text", "E_align"):
            row = stimulus_row(
                tokenizer, episode, "E", condition, 3, copy.deepcopy(e_messages)
            )
            stimuli.append(row)
            by_key[("E", condition, 3)] = row

        token_groups = {
            f"A-g{gap}": {
                condition: by_key[("A", condition, gap)]["input_token_count"]
                for condition in ("A_N", "A_E")
            }
            for gap in spec.GAPS
        }
        token_groups.update(
            {
                f"R-g{gap}": {
                    condition: by_key[("R", condition, gap)]["input_token_count"]
                    for condition in ("R0", "R_audit", "R_fact")
                }
                for gap in spec.GAPS
            }
        )
        token_ok = all(
            max(group.values()) - min(group.values()) <= 2
            for group in token_groups.values()
        )
        e_bytes_equal = (
            by_key[("E", "E_text", 3)]["messages_sha256"]
            == by_key[("E", "E_align", 3)]["messages_sha256"]
        )
        r_lexical = lexical_checks(
            episode,
            {condition: balanced_treatments[(3, condition)] for condition in ("R0", "R_audit", "R_fact")},
        )
        contract_once = (
            len([m for m in episode["base_messages"] if m.get("role") == "system"]) == 1
            and episode["base_messages"][0]["content"].count(spec.AGENT_TOOL_CONTRACT) == 1
        )
        gap_hashes = {
            gap: spec.canonical_sha256(flatten_gap_blocks(episode, gap))
            for gap in spec.GAPS
        }
        check = {
            "episode_id": episode["episode_id"],
            "stimulus_count": len(by_key),
            "token_groups": token_groups,
            "pairwise_token_gap_at_most_2": token_ok,
            "e_text_e_align_visible_bytes_identical": e_bytes_equal,
            "agent_contract_exactly_once": contract_once,
            "gap_blocks_hash": gap_hashes,
            "gap3_uses_three_external_read_only_blocks": len(episode["gap_blocks"]) == 3,
            "construct_screen_pass": all(
                episode["construct_screen"].get(field) is True
                for field in (
                    "complete_single_turn_intent", "programmatic_truth",
                    "single_false_leaf", "observable_F_V_G_B_E_T",
                    "unique_oracle_action_or_ordered_path",
                )
            ) and episode["construct_screen"].get("selection_uses_target_model_output") is False,
            **r_lexical,
        }
        checks.append(check)

    base.write_jsonl(args.output / "stimuli.jsonl", stimuli)
    base.write_jsonl(args.output / "checks.jsonl", checks)
    all_checks_pass = (
        len(stimuli) == 72
        and len({row["stimulus_id"] for row in stimuli}) == 72
        and len(checks) == 6
        and all(
            row["stimulus_count"] == 12
            and row["pairwise_token_gap_at_most_2"]
            and row["e_text_e_align_visible_bytes_identical"]
            and row["agent_contract_exactly_once"]
            and row["gap3_uses_three_external_read_only_blocks"]
            and row["construct_screen_pass"]
            and row["r0_has_no_target_or_audit_language"]
            and row["r_audit_has_no_oracle_value"]
            and row["r_fact_contains_oracle_value"]
            and row["r_fact_marks_prior_invalid"]
            and row["r_audit_requests_read_before_action"]
            for row in checks
        )
    )
    files = sorted(path for path in args.output.rglob("*") if path.is_file())
    script_dir = Path(__file__).resolve().parent
    manifest = {
        "schema_version": 1,
        "protocol_id": spec.PROTOCOL_ID,
        "protocol_version": spec.PROTOCOL_VERSION,
        "model_revision": spec.MODEL_REVISION,
        "schedule_seed": args.seed,
        "assets_manifest_sha256": base.sha256_file(args.assets / "manifest.json"),
        "stimulus_count": len(stimuli),
        "episode_count": len(episodes),
        "all_checks_pass": all_checks_pass,
        "generator_sha256": base.sha256_file(Path(__file__)),
        "helper_sha256": base.sha256_file(script_dir / "qhist_render_stimuli.py"),
        "v13_spec_sha256": base.sha256_file(script_dir / "qhist_v13_spec.py"),
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
