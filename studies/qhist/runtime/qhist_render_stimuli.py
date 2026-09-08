#!/usr/bin/env python3
"""冻结并审计 Q-HIST v7 的可见权威消息和静态前缀。"""

from __future__ import annotations

import argparse
import hashlib
import json
import random
from itertools import combinations
from pathlib import Path
from typing import Any, Callable


PROTOCOL_VERSION = 8
SCHEDULE_SEED = 20260903

NEUTRAL_FACTS = (
    ("display theme", "light"),
    ("screen rotation", "automatic"),
    ("text size", "standard"),
    ("system language", "English"),
    ("keyboard layout", "standard QWERTY"),
    ("date format", "year month day"),
    ("time zone display", "local standard time"),
    ("notification preview", "enabled on lock screen"),
    ("sound profile", "normal with media alerts"),
    ("contrast setting", "standard accessibility contrast"),
    ("home screen layout", "default four column grid"),
    ("interface animation speed", "standard one-times scale"),
    ("wallpaper mode", "static light landscape image"),
    ("keyboard feedback mode", "visual feedback with standard intensity"),
    (
        "accessibility spoken content voice",
        "English United States enhanced voice number two",
    ),
    (
        "keyboard autocorrection language",
        "English United States with the standard dictionary",
    ),
    (
        "home screen icon arrangement",
        "four columns with labels shown below every application icon",
    ),
    (
        "document preview rendering preference",
        "fit the full page width while retaining standard document margins",
    ),
    (
        "media caption appearance preset",
        "white text displayed on a translucent solid black background",
    ),
    (
        "accessibility visual feedback profile",
        "standard intensity with no custom animation override currently enabled",
    ),
)


def canonical_json(value: Any) -> str:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        default=str,
    )


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def render_authority(field: str, value: Any) -> str:
    label = field.replace("_", " ")
    rendered_value = json.dumps(value, ensure_ascii=False, separators=(",", ":"))
    return (
        "Authoritative state audit: verified field "
        f'"{label}" has value {rendered_value}.'
    )


def choose_neutral_pair(
    target_tokens: int,
    token_count: Callable[[str], int],
) -> tuple[tuple[str, str, int], tuple[str, str, int]]:
    candidates = [
        (field, value, token_count(render_authority(field, value)))
        for field, value in NEUTRAL_FACTS
    ]
    feasible = [
        pair
        for pair in combinations(candidates, 2)
        if abs(pair[0][2] - target_tokens) <= 2
        and abs(pair[1][2] - target_tokens) <= 2
        and abs(pair[0][2] - pair[1][2]) <= 2
    ]
    if not feasible:
        raise RuntimeError(
            "没有与纠正消息长度相差不超过 2 tokens 的两条独立中性事实："
            f"target={target_tokens}, candidates="
            + canonical_json(
                [{"field": field, "tokens": count} for field, _, count in candidates]
            )
        )
    return min(
        feasible,
        key=lambda pair: (
            abs(pair[0][2] - target_tokens)
            + abs(pair[1][2] - target_tokens),
            max(pair[0][2], pair[1][2]),
            pair[0][0],
            pair[1][0],
        ),
    )


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    return [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "".join(canonical_json(row) + "\n" for row in rows),
        encoding="utf-8",
    )


def numpy_sha256(tensor) -> str:
    return sha256_bytes(tensor.detach().cpu().numpy().tobytes())


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--assets", type=Path, required=True)
    parser.add_argument("--model-path", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--seed", type=int, default=SCHEDULE_SEED)
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

    episodes = read_jsonl(args.assets / "episodes.jsonl")
    predicates = {
        row["episode_id"]: row
        for row in read_jsonl(args.assets / "predicates.jsonl")
    }
    authority_rows: list[dict[str, Any]] = []
    static_rows: list[dict[str, Any]] = []
    blind_public: list[dict[str, Any]] = []
    blind_key: list[dict[str, Any]] = []
    checks: list[dict[str, Any]] = []
    for episode in episodes:
        correction = episode["authority_payloads"]["C_text"]
        correction_text = render_authority(correction["field"], correction["value"])
        correction_tokens = token_count(correction_text)
        neutral, sham = choose_neutral_pair(correction_tokens, token_count)
        rendered = {
            "N": render_authority(neutral[0], neutral[1]),
            "S": render_authority(sham[0], sham[1]),
            "C_text": correction_text,
            "C_align": correction_text,
        }
        lengths = {condition: token_count(text) for condition, text in rendered.items()}
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
        checks.append(
            {
                "episode_id": episode["episode_id"],
                "pairwise_token_length_ok": pairwise_ok,
                "neutral_target_leak_free": no_target_leak,
                "c_text_c_align_byte_identical": rendered["C_text"].encode("utf-8")
                == rendered["C_align"].encode("utf-8"),
                "token_lengths": lengths,
            }
        )
        for condition, text in rendered.items():
            prefix_observation = (
                episode["prefix"]["truth_message"]
                if condition == "N"
                else episode["prefix"]["false_message"]
            )
            authority_probe = tokenizer.apply_chat_template(
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
            decoded_probe = tokenizer.decode(
                authority_probe["input_ids"][0], skip_special_tokens=False
            )
            content_present = text in decoded_probe
            if not content_present:
                raise RuntimeError(
                    f"chat template 未保留 {episode['episode_id']}/{condition} 的权威消息"
                )
            authority_rows.append(
                {
                    "episode_id": episode["episode_id"],
                    "condition": condition,
                    "role": "system",
                    "content": text,
                    "content_sha256": sha256_bytes(text.encode("utf-8")),
                    "token_count": lengths[condition],
                    "chat_template_probe_token_count": int(
                        authority_probe["input_ids"].shape[1]
                    ),
                    "chat_template_probe_sha256": numpy_sha256(
                        authority_probe["input_ids"]
                    ),
                    "chat_template_preserves_content": content_present,
                }
            )

        for history in ("N", "E"):
            prefix_observation = (
                episode["prefix"]["truth_message"]
                if history == "N"
                else episode["prefix"]["false_message"]
            )
            messages = [
                *episode["base_messages"],
                episode["prefix"]["tool_call_message"],
                prefix_observation,
            ]
            encoded = tokenizer.apply_chat_template(
                messages,
                tools=episode["tool_schema"],
                tokenize=True,
                add_generation_prompt=True,
                return_tensors="pt",
                return_dict=True,
                enable_thinking=False,
            )
            static_rows.append(
                {
                    "episode_id": episode["episode_id"],
                    "prefix_history": history,
                    "input_token_count": int(encoded["input_ids"].shape[1]),
                    "input_ids_sha256": numpy_sha256(encoded["input_ids"]),
                    "attention_mask_sha256": numpy_sha256(encoded["attention_mask"]),
                    "tool_schema_sha256": episode["tool_schema_sha256"],
                }
            )

        # 盲评公开表不含 condition 标签，且每个 episode 独立打乱；密钥另存。
        blind_conditions = ["N", "S", "C_text"]
        random.Random(f"{args.seed}|{episode['episode_id']}").shuffle(
            blind_conditions
        )
        for index, condition in enumerate(blind_conditions, start=1):
            blind_id = f'{episode["episode_id"]}-R{index}'
            blind_public.append(
                {
                    "blind_id": blind_id,
                    "task_context": episode["base_messages"],
                    "oracle_tool_observation": episode["prefix"]["truth_message"],
                    "candidate_prefix_observation": (
                        episode["prefix"]["truth_message"]
                        if condition == "N"
                        else episode["prefix"]["false_message"]
                    ),
                    "message": rendered[condition],
                    "error_descendant_predicate": predicates[
                        episode["episode_id"]
                    ]["error_action"],
                    "questions": [
                        "candidate_prefix_is_false_yes_no",
                        "message_corrects_target_yes_no",
                        "message_is_target_irrelevant_yes_no",
                        "message_is_natural_1_to_5",
                        "message_is_actionable_1_to_5",
                        "message_is_authority_shaped_yes_no",
                        "message_reveals_experimental_condition_yes_no",
                        "error_descendant_predicate_is_complete_yes_no",
                    ],
                }
            )
            blind_key.append(
                {
                    "blind_id": blind_id,
                    "episode_id": episode["episode_id"],
                    "condition": condition,
                }
            )

    write_jsonl(args.output / "authority-messages.jsonl", authority_rows)
    write_jsonl(args.output / "static-prefixes.jsonl", static_rows)
    write_jsonl(args.output / "blind-rating-items.jsonl", blind_public)
    write_jsonl(args.output / "sealed-blind-key.jsonl", blind_key)
    write_jsonl(args.output / "checks.jsonl", checks)
    files = sorted(path for path in args.output.rglob("*") if path.is_file())
    all_checks_pass = all(
        row["pairwise_token_length_ok"]
        and row["neutral_target_leak_free"]
        and row["c_text_c_align_byte_identical"]
        for row in checks
    )
    manifest = {
        "schema_version": 1,
        "protocol_id": "QHIST-EXP",
        "protocol_version": PROTOCOL_VERSION,
        "model_revision": "9216db5781bf21249d130ec9da846c4624c16137",
        "schedule_seed": args.seed,
        "episodes_sha256": sha256_file(args.assets / "episodes.jsonl"),
        "all_checks_pass": all_checks_pass,
        "episode_count": len(episodes),
        "authority_message_count": len(authority_rows),
        "static_prefix_count": len(static_rows),
        "files": [
            {
                "path": str(path.relative_to(args.output)).replace("\\", "/"),
                "bytes": path.stat().st_size,
                "sha256": sha256_file(path),
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
