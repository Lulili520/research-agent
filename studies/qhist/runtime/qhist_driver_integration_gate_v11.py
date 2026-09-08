#!/usr/bin/env python3
"""以 fixed actions 验证 v11 boundary-fork、F/V/G/B/E 与 fail-closed。"""

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


def generated_result(request_id, precision, tools, raw):
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
        "cache_evidence": {"class": "fixed-action-integration-gate"},
        "elapsed_seconds": 0.0,
    }


def tool_reply(request_id, precision, tools, action):
    raw = "<tool_call>" + json.dumps(action) + "</tool_call><|im_end|>"
    return generated_result(request_id, precision, tools, raw)


def text_reply(request_id, precision, tools, text):
    return generated_result(request_id, precision, tools, text + "<|im_end|>")


def row(episode, history, repeat=1):
    suffix = "" if repeat == 1 else f"-r{repeat}"
    return {
        "unit_id": f"ENGINEERING-{episode['episode_id']}-P00-{history}-d1{suffix}",
        "episode_id": episode["episode_id"],
        "scenario": episode["scenario"],
        "family": episode["family"],
        "precision": "P00",
        "history": history,
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
    episode = episodes["QH11-E0-01"]
    predicate = predicates[episode["episode_id"]]
    false_id = predicate["false_value"]
    true_id = predicate["oracle_value"]
    completion_text = predicate["oracle_completion_message"]

    def fixed_generate(
        endpoint, request_id, expected_precision, messages, tools, max_new_tokens
    ):
        decision = int(request_id.rsplit("-decision-", 1)[1])
        if "|ERR|trunk" in request_id:
            return tool_reply(
                request_id,
                expected_precision,
                tools,
                {"name": "remove_contact", "arguments": {"person_id": false_id}},
            )
        if "|C_text|post" in request_id or "|C_align|post" in request_id:
            if decision == 2:
                return tool_reply(
                    request_id,
                    expected_precision,
                    tools,
                    {"name": "remove_contact", "arguments": {"person_id": true_id}},
                )
            if decision == 3:
                return tool_reply(
                    request_id,
                    expected_precision,
                    tools,
                    {"name": "remove_contact", "arguments": {"person_id": false_id}},
                )
            return text_reply(request_id, expected_precision, tools, completion_text)
        return text_reply(
            request_id,
            expected_precision,
            tools,
            "I cannot resolve the target from the available record.",
        )

    runner.base.generate_decision = fixed_generate
    scenarios = named_scenarios(preferred_tool_backend=ToolBackend.DEFAULT)
    scenario = scenarios[episode["scenario"]]
    rows = [row(episode, history) for history in ("E", "S", "C_text", "C_align")]
    requests = {"value": 0}
    valid = runner.run_group(
        rows,
        episode,
        predicate,
        patches[episode["episode_id"]],
        authority,
        args.assets,
        scenario,
        "fixed-action://v11-valid",
        256,
        requests,
    )

    repeat_requests = {"value": 0}
    repeated = runner.run_group(
        [row(episode, "C_text", repeat=2)],
        episode,
        predicate,
        patches[episode["episode_id"]],
        authority,
        args.assets,
        scenario,
        "fixed-action://v11-repeat",
        256,
        repeat_requests,
    )[row(episode, "C_text", repeat=2)["unit_id"]]

    c_text = valid[row(episode, "C_text")["unit_id"]]
    c_align = valid[row(episode, "C_align")["unit_id"]]
    error_branch = valid[row(episode, "E")["unit_id"]]
    pre_hashes = {
        item["pre_boundary_artifact"]["artifact_sha256"]
        for item in valid.values()
    }

    invalid_cursor = {"value": 0}

    def invalid_generate(
        endpoint, request_id, expected_precision, messages, tools, max_new_tokens
    ):
        invalid_cursor["value"] += 1
        if invalid_cursor["value"] == 1:
            valid_action = {
                "name": "remove_contact",
                "arguments": {"person_id": false_id},
            }
            invalid_action = {"name": "qhist_nonexistent_tool", "arguments": {}}
            raw = "".join(
                "<tool_call>" + json.dumps(item) + "</tool_call>"
                for item in (valid_action, invalid_action)
            )
            return generated_result(request_id, expected_precision, tools, raw)
        return text_reply(
            request_id, expected_precision, tools, "Cannot proceed."
        )

    runner.base.generate_decision = invalid_generate
    invalid_row = row(episode, "N")
    invalid = runner.run_group(
        [invalid_row],
        episode,
        predicate,
        patches[episode["episode_id"]],
        authority,
        args.assets,
        scenario,
        "fixed-action://v11-invalid",
        256,
        {"value": 0},
    )[invalid_row["unit_id"]]

    checks = {
        "shared_trunk_one_request_plus_four_branches": requests["value"] == 13,
        "all_erroneous_branches_share_pre_boundary_artifact": len(pre_hashes) == 1,
        "false_action_detected": error_branch["decisions"][0][
            "error_consistent_action"
        ],
        "false_action_activates_policy_debt": error_branch["decisions"][0][
            "commitment_debt"
        ],
        "false_action_creates_environment_debt": error_branch["decisions"][0][
            "environment_debt"
        ],
        "direct_successful_recovery_detected": c_text["decisions"][1][
            "successful_recovery_certificate"
        ],
        "direct_recovery_without_verification": (
            not c_text["decisions"][1]["successful_truth_verification"]
        ),
        "successful_recovery_clears_policy_debt": (
            not c_text["decisions"][1]["commitment_debt"]
        ),
        "later_error_action_reactivates_policy_debt": (
            c_text["decisions"][2]["error_consistent_action"]
            and c_text["decisions"][2]["commitment_debt"]
        ),
        "c_text_preserves_environment_debt": c_text["decisions"][1][
            "environment_debt"
        ],
        "c_align_patch_changed_only_error_descendant": (
            c_align["correction"]["patch"]["changed"]
            and not c_align["decisions"][1]["environment_debt"]
        ),
        "c_text_c_align_visible_bytes_identical": (
            c_text["correction"]["visible_message_sha256"]
            == c_align["correction"]["visible_message_sha256"]
        ),
        "policy_environment_metrics_separate": (
            "policy_commitment_auc" in c_text["metrics"]
            and "environment_debt_auc" in c_text["metrics"]
            and "normalized_q_auc" not in c_text["metrics"]
        ),
        "scientific_signature_repeat_exact": (
            c_text["scientific_signature"]["sha256"]
            == repeated["scientific_signature"]["sha256"]
        ),
        "pre_boundary_repeat_exact": (
            c_text["pre_boundary_artifact"]["artifact_sha256"]
            == repeated["pre_boundary_artifact"]["artifact_sha256"]
        ),
        "invalid_reply_classified": (
            invalid["decisions"][0]["output_class"] == "invalid-native-tool"
        ),
        "invalid_reply_executes_zero_calls": (
            invalid["decisions"][0]["execution"] == []
            and invalid["metrics"]["tool_call_count"] == 0
        ),
        "invalid_reply_side_effect_absent": (
            not invalid["decisions"][0]["environment_debt"]
        ),
        "invalid_reply_records_schema_reason": bool(
            invalid["decisions"][0]["tool_validation_failures"]
        ),
    }
    report = {
        "schema_version": 1,
        "protocol_id": spec.PROTOCOL_ID,
        "protocol_version": spec.PROTOCOL_VERSION,
        "runtime": runtime,
        "checks": checks,
        "passed": all(checks.values()),
        "valid_trajectories": valid,
        "technical_repeat": repeated,
        "fail_closed_trajectory": invalid,
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
