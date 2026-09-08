#!/usr/bin/env python3
"""验证 v11 动态 reminder ID、binding repair 与跨 repeat 科学复现。"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

import qhist_trajectory_batch_v11 as runner
import qhist_v11_spec as spec


def read_jsonl(path: Path):
    return [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def generated(request_id, precision, tools, raw):
    return {
        "request_id": request_id,
        "precision": precision,
        "model_revision": spec.MODEL_REVISION,
        "raw_text": raw,
        "visible_content": raw.replace("<|im_end|>", ""),
        "parsed_actions": [],
        "input_token_count": 1,
        "generated_token_count": 1,
        "input_ids_sha256": hashlib.sha256(request_id.encode()).hexdigest(),
        "tool_schema_sha256": runner.base.canonical_sha256(tools),
        "cache_evidence": {"class": "deterministic-id-gate"},
        "elapsed_seconds": 0.0,
    }


def tool_reply(request_id, precision, tools, action):
    return generated(
        request_id,
        precision,
        tools,
        "<tool_call>" + json.dumps(action) + "</tool_call><|im_end|>",
    )


def make_row(episode, repeat):
    return {
        "unit_id": f"ID-GATE-{episode['episode_id']}-P00-C_text-d1-r{repeat}",
        "episode_id": episode["episode_id"],
        "scenario": episode["scenario"],
        "family": episode["family"],
        "precision": "P00",
        "history": "C_text",
        "distance": 1,
        "repeat": repeat,
        "technical_repeat": repeat > 1,
        "execution_order": 1,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--assets", type=Path, required=True)
    parser.add_argument("--rendered", type=Path, required=True)
    parser.add_argument("--toolsandbox-source", type=Path, required=True)
    parser.add_argument("--toolsandbox-site-packages", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        raise RuntimeError(f"输出文件已存在：{args.output}")

    runner.base.PROTOCOL_VERSION = spec.PROTOCOL_VERSION
    runner.base.MODEL_REVISION = spec.MODEL_REVISION
    runtime = runner.base.prepare_toolsandbox(
        args.toolsandbox_source, args.toolsandbox_site_packages
    )
    from tool_sandbox.common.tool_discovery import ToolBackend
    from tool_sandbox.scenarios import named_scenarios

    episodes = {
        item["episode_id"]: item
        for item in read_jsonl(args.assets / "episodes.jsonl")
    }
    predicates = {
        item["episode_id"]: item
        for item in read_jsonl(args.assets / "predicates.jsonl")
    }
    patches = {
        item["episode_id"]: item
        for item in read_jsonl(args.assets / "environment-patches.jsonl")
    }
    authority = {
        (item["episode_id"], item["condition"]): item
        for item in read_jsonl(args.rendered / "authority-messages.jsonl")
    }
    episode = episodes["QH11-E0-04"]
    predicate = predicates[episode["episode_id"]]
    patch = patches[episode["episode_id"]]
    scenario = named_scenarios(preferred_tool_backend=ToolBackend.DEFAULT)[
        episode["scenario"]
    ]
    provider = runner.DeterministicUUID4(
        runner.logical_segment_key(episode["episode_id"], 1, "ERR", "trunk")
    )
    expected_error_id = str(provider())
    wrong_time = predicate["false_value"]
    correct_time = predicate["oracle_value"]

    def fixed_generate(
        endpoint, request_id, expected_precision, messages, tools, max_new_tokens
    ):
        decision = int(request_id.rsplit("-decision-", 1)[1])
        if "|ERR|trunk" in request_id:
            return tool_reply(
                request_id,
                expected_precision,
                tools,
                {
                    "name": "add_reminder",
                    "arguments": {
                        "content": "buy chocolate milk",
                        "reminder_timestamp": wrong_time,
                    },
                },
            )
        if decision == 2:
            return tool_reply(
                request_id,
                expected_precision,
                tools,
                {
                    "name": "modify_reminder",
                    "arguments": {
                        "reminder_id": expected_error_id,
                        "reminder_timestamp": correct_time,
                    },
                },
            )
        return generated(
            request_id,
            expected_precision,
            tools,
            "The reminder has been corrected.<|im_end|>",
        )

    runner.base.generate_decision = fixed_generate
    results = []
    for repeat in (1, 2):
        current_row = make_row(episode, repeat)
        counter = {"value": 0}
        result = runner.run_group(
            [current_row],
            episode,
            predicate,
            patch,
            authority,
            args.assets,
            scenario,
            "fixed-action://deterministic-id",
            256,
            counter,
        )[current_row["unit_id"]]
        results.append((result, counter["value"]))

    first, second = results[0][0], results[1][0]
    first_trunk = first["decisions"][0]
    first_repair = first["decisions"][1]
    checks = {
        "four_requests_each": results[0][1] == 4 and results[1][1] == 4,
        "error_id_matches_frozen_provider": (
            first_trunk["dynamic_bindings"].get("error_entity_id")
            == expected_error_id
        ),
        "error_id_same_across_repeats": (
            first["decisions"][0]["dynamic_bindings"].get("error_entity_id")
            == second["decisions"][0]["dynamic_bindings"].get("error_entity_id")
        ),
        "binding_based_modify_succeeds": (
            first_repair["execution"]
            and first_repair["execution"][0]["exception"] is None
        ),
        "modify_is_recovery_certificate": first_repair[
            "successful_recovery_certificate"
        ],
        "modify_clears_policy_debt": not first_repair["commitment_debt"],
        "modify_clears_environment_debt": not first_repair["environment_debt"],
        "pre_boundary_repeat_exact": (
            first["pre_boundary_artifact"]["artifact_sha256"]
            == second["pre_boundary_artifact"]["artifact_sha256"]
        ),
        "scientific_signature_repeat_exact": (
            first["scientific_signature"]["sha256"]
            == second["scientific_signature"]["sha256"]
        ),
    }
    report = {
        "schema_version": 1,
        "protocol_id": spec.PROTOCOL_ID,
        "protocol_version": spec.PROTOCOL_VERSION,
        "runtime": runtime,
        "expected_error_entity_id": expected_error_id,
        "checks": checks,
        "passed": all(checks.values()),
        "repeat_1": first,
        "repeat_2": second,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(report, ensure_ascii=False, indent=2, default=str) + "\n",
        encoding="utf-8",
    )
    print(json.dumps({"checks": checks, "passed": report["passed"]}, indent=2))
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
