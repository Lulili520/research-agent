#!/usr/bin/env python3
"""在单一冻结精度下执行 Q-HIST E0 处理轨迹并保存逐边界证据。"""

from __future__ import annotations

import argparse
import copy
import datetime as _datetime
import gc
import hashlib
import json
import os
import random
import subprocess
import sys
import time
import traceback
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

PROTOCOL_VERSION = 8
MODEL_REVISION = "9216db5781bf21249d130ec9da846c4624c16137"
REFERENCE_TIME_ISO = "2026-09-03T12:00:00+08:00"
REFERENCE_TIME_EPOCH = 1788408000.0
CONTINUATION = (
    "Continue the original task. If it is already complete, inspect the current "
    "state and do not repeat completed side effects."
)
PRECISIONS = ("P00", "P10", "P01", "P11")


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


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    return [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def verify_manifest(root: Path, require_checks: bool = False) -> dict[str, Any]:
    path = root / "manifest.json"
    manifest = json.loads(path.read_text(encoding="utf-8"))
    if manifest.get("protocol_version") != PROTOCOL_VERSION:
        raise RuntimeError(
            f"manifest protocol version 不匹配：{manifest.get('protocol_version')}"
        )
    if require_checks and manifest.get("all_checks_pass") is not True:
        raise RuntimeError("渲染刺激 manifest 未通过全部检查")
    for record in manifest.get("files", []):
        target = root / record["path"]
        if not target.is_file() or sha256_file(target) != record["sha256"]:
            raise RuntimeError(f"manifest 文件缺失或哈希不匹配：{target}")
    return manifest


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2, default=str) + "\n",
        encoding="utf-8",
    )


def append_jsonl(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8", newline="\n") as stream:
        stream.write(canonical_json(value) + "\n")
        stream.flush()
        os.fsync(stream.fileno())


def build_schedule(
    units: list[dict[str, Any]], precision: str, seed: int
) -> list[dict[str, Any]]:
    selected = [row for row in units if row["precision"] == precision]
    expected = 80 if precision == "P00" else 8
    if len(selected) != expected or len({row["unit_id"] for row in selected}) != expected:
        raise RuntimeError(
            f"{precision} 冻结轨迹应有 {expected} 个唯一单元，实际 {len(selected)}"
        )
    by_episode: dict[str, list[dict[str, Any]]] = {}
    for row in selected:
        by_episode.setdefault(str(row["episode_id"]), []).append(row)
    episode_ids = sorted(by_episode)
    random.Random(seed).shuffle(episode_ids)
    schedule: list[dict[str, Any]] = []
    for episode_id in episode_ids:
        block = sorted(by_episode[episode_id], key=lambda row: row["unit_id"])
        random.Random(f"{seed}|{episode_id}|{precision}").shuffle(block)
        schedule.extend(block)
    return [dict(row, execution_order=index) for index, row in enumerate(schedule, 1)]


def freeze_clock() -> None:
    os.environ["TZ"] = "Asia/Shanghai"
    if hasattr(time, "tzset"):
        time.tzset()
    real_datetime = _datetime.datetime
    reference = real_datetime.fromisoformat(REFERENCE_TIME_ISO)

    class FrozenDateTime(real_datetime):
        @classmethod
        def now(cls, tz=None):
            target = reference if tz is None else reference.astimezone(tz)
            if tz is None:
                target = target.replace(tzinfo=None)
            return cls(
                target.year,
                target.month,
                target.day,
                target.hour,
                target.minute,
                target.second,
                target.microsecond,
                tzinfo=target.tzinfo,
            )

    _datetime.datetime = FrozenDateTime


def prepare_toolsandbox(source: Path, site_packages: Path) -> dict[str, Any]:
    # append 而不是 prepend，确保冻结的 PyTorch/Transformers/NumPy 优先解析。
    sys.path.append(str(source))
    sys.path.append(str(site_packages))
    freeze_clock()
    import polars
    import tool_sandbox

    return {
        "tool_sandbox_file": str(Path(tool_sandbox.__file__).resolve()),
        "polars": polars.__version__,
        "reference_time_iso": REFERENCE_TIME_ISO,
        "reference_time_epoch": REFERENCE_TIME_EPOCH,
    }


def gpu_snapshot() -> dict[str, Any]:
    try:
        result = subprocess.run(
            [
                "nvidia-smi",
                "--query-gpu=index,name,memory.used,memory.total,utilization.gpu",
                "--format=csv,noheader,nounits",
            ],
            check=True,
            capture_output=True,
            text=True,
        )
        return {"raw": result.stdout.strip()}
    except Exception as error:
        return {"error": f"{type(error).__name__}: {error}"}


def arguments_contain(arguments: dict[str, Any], expected: dict[str, Any]) -> bool:
    return all(arguments.get(key) == value for key, value in expected.items())


def action_matches(
    action: dict[str, Any], predicate: dict[str, Any], environment: dict[str, Any]
) -> bool:
    if action.get("name") != predicate.get("tool"):
        return False
    if not arguments_contain(
        action.get("arguments") or {}, predicate.get("arguments_contains") or {}
    ):
        return False
    expected_environment = predicate.get("when_environment") or {}
    return all(environment.get(key) == value for key, value in expected_environment.items())


def ordered_oracle_progress(
    actions_so_far: list[dict[str, Any]], predicate: dict[str, Any]
) -> bool:
    ordered = predicate.get("ordered_tools")
    if ordered:
        names = [action.get("name") for action in actions_so_far]
        cursor = 0
        for name in names:
            if cursor < len(ordered) and name == ordered[cursor]:
                cursor += 1
        return cursor == len(ordered)
    return any(action_matches(action, predicate, {}) for action in actions_so_far)


def namespace_hash(context, namespace) -> str:
    rows = context.get_database(namespace).to_dicts()
    return canonical_sha256(rows)


def flat_environment(context) -> dict[str, Any]:
    from tool_sandbox.common.execution_context import DatabaseNamespace

    values: dict[str, Any] = {}
    for namespace in DatabaseNamespace:
        if namespace == DatabaseNamespace.SANDBOX:
            continue
        try:
            rows = context.get_database(namespace).to_dicts()
        except Exception:
            continue
        if len(rows) == 1:
            for key, value in rows[0].items():
                values[f"{namespace.name}.{key}"] = value
    return values


def environment_debt(context, baseline_context, patch: dict[str, Any]) -> bool:
    from tool_sandbox.common.execution_context import DatabaseNamespace

    operation = patch["operation"]
    if operation == "none":
        return False
    namespace = DatabaseNamespace[patch["namespace"]]
    current = context.get_database(namespace).to_dicts()
    baseline = baseline_context.get_database(namespace).to_dicts()
    if operation == "remove_rows_added_after_baseline":
        predicate = patch["predicate"]

        def match(row):
            return all(row.get(key) == value for key, value in predicate.items())

        current_matches = [row for row in current if match(row)]
        baseline_matches = [row for row in baseline if match(row)]
        return len(current_matches) > len(baseline_matches)
    if operation == "restore_baseline_row_if_missing_or_changed":
        key = patch["key"]

        def match(row):
            return all(row.get(name) == value for name, value in key.items())

        target = [row for row in current if match(row)]
        baseline_target = [row for row in baseline if match(row)]
        return target != baseline_target
    raise ValueError(f"未知 patch operation: {operation}")


def apply_environment_patch(context, baseline_context, patch: dict[str, Any]) -> dict[str, Any]:
    import polars as pl
    from tool_sandbox.common.execution_context import DatabaseNamespace

    operation = patch["operation"]
    if operation == "none":
        return {"operation": operation, "changed": False}
    namespace = DatabaseNamespace[patch["namespace"]]
    before_hash = namespace_hash(context, namespace)
    current = context.get_database(namespace)
    baseline = baseline_context.get_database(namespace)
    if operation == "remove_rows_added_after_baseline":
        predicate = patch["predicate"]
        expression = pl.lit(True)
        for key, value in predicate.items():
            expression &= pl.col(key) == value
        desired = pl.concat(
            [current.filter(~expression), baseline.filter(expression)],
            how="vertical",
        )
    elif operation == "restore_baseline_row_if_missing_or_changed":
        key = patch["key"]
        expression = pl.lit(True)
        for name, value in key.items():
            expression &= pl.col(name) == value
        desired = pl.concat(
            [current.filter(~expression), baseline.filter(expression)],
            how="vertical",
        )
    else:
        raise ValueError(f"未知 patch operation: {operation}")
    context.update_database(namespace, desired)
    after_hash = namespace_hash(context, namespace)
    return {
        "operation": operation,
        "namespace": namespace.name,
        "before_sha256": before_hash,
        "after_sha256": after_hash,
        "baseline_sha256": namespace_hash(baseline_context, namespace),
        "changed": before_hash != after_hash,
    }


def initialize_context(snapshot: dict[str, Any], episode: dict[str, Any]):
    from tool_sandbox.common.execution_context import (
        DatabaseNamespace,
        ExecutionContext,
        RoleType,
        set_current_context,
    )
    from tool_sandbox.common.message_conversion import Message
    from tool_sandbox.roles.execution_environment import ExecutionEnvironment

    context = ExecutionContext.from_dict(copy.deepcopy(snapshot))
    baseline_context = ExecutionContext.from_dict(copy.deepcopy(snapshot))
    set_current_context(context)
    environment = ExecutionEnvironment()
    sandbox = context.get_database(
        DatabaseNamespace.SANDBOX,
        get_all_history_snapshots=True,
        drop_sandbox_message_index=False,
    )
    original_max = context.max_sandbox_message_index
    for row in sandbox.to_dicts():
        if (
            row["sender"] == RoleType.SYSTEM
            and row["recipient"] == RoleType.EXECUTION_ENVIRONMENT
        ):
            environment.respond(ending_index=int(row["sandbox_message_index"]))
    if context.max_sandbox_message_index != original_max:
        raise RuntimeError("初始化系统工具时意外增加了消息")

    # ToolSandbox 的多轮 user simulator 不用于本实验；加入已冻结的确定性澄清。
    for message in episode["base_messages"][2:]:
        if message["role"] == "assistant":
            context.add_to_database(
                DatabaseNamespace.SANDBOX,
                [
                    {
                        "sender": RoleType.AGENT,
                        "recipient": RoleType.USER,
                        "content": message["content"],
                    }
                ],
            )
        elif message["role"] == "user":
            context.add_to_database(
                DatabaseNamespace.SANDBOX,
                [
                    {
                        "sender": RoleType.USER,
                        "recipient": RoleType.AGENT,
                        "content": message["content"],
                    }
                ],
            )
        else:
            raise RuntimeError(f"冻结澄清中出现未知 role: {message['role']}")
    return context, baseline_context, environment


def add_synthetic_prefix(context, episode: dict[str, Any], use_truth: bool) -> None:
    from tool_sandbox.common.execution_context import DatabaseNamespace, RoleType

    prefix = episode["prefix"]
    context.add_to_database(
        DatabaseNamespace.SANDBOX,
        [
            {
                "sender": RoleType.AGENT,
                "recipient": RoleType.EXECUTION_ENVIRONMENT,
                "content": prefix["python_code"],
                "openai_tool_call_id": prefix["call_id"],
                "openai_function_name": prefix["tool"],
            },
            {
                "sender": RoleType.EXECUTION_ENVIRONMENT,
                "recipient": RoleType.AGENT,
                "content": (
                    prefix["truth_message"]["content"]
                    if use_truth
                    else prefix["false_message"]["content"]
                ),
                "openai_tool_call_id": prefix["call_id"],
                "openai_function_name": prefix["tool"],
            },
        ],
    )


def add_authority_message(context, content: str) -> None:
    from tool_sandbox.common.execution_context import DatabaseNamespace, RoleType

    context.add_to_database(
        DatabaseNamespace.SANDBOX,
        [
            {
                "sender": RoleType.SYSTEM,
                "recipient": RoleType.AGENT,
                "content": content,
                "conversation_active": True,
            }
        ],
    )


def add_continuation(context) -> None:
    from tool_sandbox.common.execution_context import DatabaseNamespace, RoleType

    context.add_to_database(
        DatabaseNamespace.SANDBOX,
        [
            {
                "sender": RoleType.USER,
                "recipient": RoleType.AGENT,
                "content": CONTINUATION,
                "conversation_active": True,
            }
        ],
    )


def execute_actions(context, environment, actions: list[dict[str, Any]], call_prefix: str):
    from tool_sandbox.common.execution_context import DatabaseNamespace, RoleType

    available = context.get_available_tools(scrambling_allowed=False)
    call_rows = []
    openai_calls = []
    for index, action in enumerate(actions, start=1):
        name = action["name"]
        if name not in available:
            raise KeyError(f"模型调用未暴露工具：{name}")
        call_id = f"call_{call_prefix}_{index}"
        arguments = action["arguments"]
        code = (
            f"{call_id}_parameters = {arguments!r}\n"
            f"{call_id}_response = {name}(**{call_id}_parameters)\n"
            f"print(repr({call_id}_response))"
        )
        call_rows.append(
            {
                "sender": RoleType.AGENT,
                "recipient": RoleType.EXECUTION_ENVIRONMENT,
                "content": code,
                "openai_tool_call_id": call_id,
                "openai_function_name": name,
            }
        )
        openai_calls.append(
            {
                "id": call_id,
                "type": "function",
                "function": {
                    "name": name,
                    "arguments": canonical_json(arguments),
                },
            }
        )
    before_index = context.max_sandbox_message_index
    context.add_to_database(DatabaseNamespace.SANDBOX, call_rows)
    environment.respond()
    rows = context.get_database(
        DatabaseNamespace.SANDBOX,
        get_all_history_snapshots=True,
        drop_sandbox_message_index=False,
    ).filter(
        # 在导入时不依赖 polars；此处执行环境已经可用。
        __import__("polars").col("sandbox_message_index") > before_index
    ).to_dicts()
    tool_messages = [
        {
            "role": "tool",
            "tool_call_id": row["openai_tool_call_id"],
            "name": row["openai_function_name"],
            "content": row["content"],
        }
        for row in rows
        if row["sender"] == RoleType.EXECUTION_ENVIRONMENT
        and row["recipient"] == RoleType.AGENT
    ]
    execution = [
        {
            "tool_call_id": row["openai_tool_call_id"],
            "tool": row["openai_function_name"],
            "content": row["content"],
            "exception": row["tool_call_exception"],
            "tool_trace": row["tool_trace"],
        }
        for row in rows
        if row["sender"] == RoleType.EXECUTION_ENVIRONMENT
        and row["recipient"] == RoleType.AGENT
    ]
    return openai_calls, tool_messages, execution


def add_prose_action(context, content: str) -> None:
    from tool_sandbox.common.execution_context import DatabaseNamespace, RoleType

    context.add_to_database(
        DatabaseNamespace.SANDBOX,
        [
            {
                "sender": RoleType.AGENT,
                "recipient": RoleType.USER,
                "content": content,
            }
        ],
    )


def generate_decision(
    endpoint: str,
    request_id: str,
    expected_precision: str,
    messages,
    tools,
    max_new_tokens,
):
    payload = {
        "request_id": request_id,
        "expected_precision": expected_precision,
        "messages": messages,
        "tools": tools,
        "max_new_tokens": max_new_tokens,
    }
    request = urllib.request.Request(
        endpoint.rstrip("/") + "/generate",
        data=canonical_json(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=600) as response:
            result = json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as error:
        body = error.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"模型服务 HTTP {error.code}: {body}") from error
    if result.get("request_id") != request_id:
        raise RuntimeError("模型服务响应 request_id 漂移")
    if result.get("precision") != expected_precision:
        raise RuntimeError("模型服务响应 precision 漂移")
    if result.get("model_revision") != MODEL_REVISION:
        raise RuntimeError("模型服务响应 model revision 漂移")
    if result.get("tool_schema_sha256") != canonical_sha256(tools):
        raise RuntimeError("模型服务响应 tool schema hash 漂移")
    return result


def run_unit(
    row: dict[str, Any],
    episode: dict[str, Any],
    predicate: dict[str, Any],
    patch: dict[str, Any],
    authority: dict[tuple[str, str], dict[str, Any]],
    snapshots_root: Path,
    scenario,
    model_endpoint: str,
    max_new_tokens: int,
) -> dict[str, Any]:
    import attrs
    from tool_sandbox.common.execution_context import (
        DatabaseNamespace,
        get_current_context,
        set_current_context,
    )

    snapshot_path = snapshots_root / episode["snapshot"]
    if sha256_file(snapshot_path) != episode["snapshot_sha256"]:
        raise RuntimeError(f"snapshot 哈希不匹配：{snapshot_path}")
    snapshot = json.loads(snapshot_path.read_text(encoding="utf-8"))
    context, baseline_context, environment = initialize_context(snapshot, episode)
    set_current_context(context)
    history = row["history"]
    use_truth = history == "N"
    add_synthetic_prefix(context, episode, use_truth=use_truth)
    messages = [
        *copy.deepcopy(episode["base_messages"]),
        copy.deepcopy(episode["prefix"]["tool_call_message"]),
        copy.deepcopy(
            episode["prefix"]["truth_message"]
            if use_truth
            else episode["prefix"]["false_message"]
        ),
    ]
    total_decisions = int(row["distance"]) + 3
    all_actions: list[dict[str, Any]] = []
    decisions: list[dict[str, Any]] = []
    correction_record: dict[str, Any] | None = None
    total_tool_calls = 0
    invalid_format_count = 0
    unit_started = time.time()
    for decision_index in range(1, total_decisions + 1):
        environment_before = flat_environment(context)
        generated = generate_decision(
            model_endpoint,
            f'{row["unit_id"]}-decision-{decision_index}',
            row["precision"],
            messages,
            episode["tool_schema"],
            max_new_tokens,
        )
        actions = generated["parsed_actions"]
        valid_actions = (
            bool(actions)
            and total_tool_calls + len(actions) <= 16
            and all(
                action["name"]
                in context.get_available_tools(scrambling_allowed=False)
                for action in actions
            )
        )
        execution: list[dict[str, Any]] = []
        early_completion = False
        if valid_actions:
            call_prefix = (
                f'{row["unit_id"].lower().replace("-", "_")}_{decision_index}'
            )
            openai_calls, tool_messages, execution = execute_actions(
                context, environment, actions, call_prefix
            )
            messages.append(
                {"role": "assistant", "content": "", "tool_calls": openai_calls}
            )
            messages.extend(tool_messages)
            all_actions.extend(actions)
            total_tool_calls += len(actions)
            early_completion = any(
                action["name"] == "end_conversation" for action in actions
            )
        else:
            invalid_format_count += 1
            content = generated["visible_content"] or generated["raw_text"]
            add_prose_action(context, content)
            messages.append({"role": "assistant", "content": content})
            early_completion = True

        action_error = any(
            action_matches(action, predicate["error_action"], environment_before)
            for action in actions
        )
        debt = environment_debt(context, baseline_context, patch)
        v_components = {"error_action": float(action_error)}
        if patch["operation"] != "none":
            v_components["environment_debt"] = float(debt)
        decisions.append(
            {
                "decision_index": decision_index,
                **generated,
                "valid_native_tool_action": valid_actions,
                "execution": execution,
                "error_consistent_action": action_error,
                "oracle_action_progress": ordered_oracle_progress(
                    all_actions, predicate["oracle_action"]
                ),
                "environment_debt": debt,
                "v_components": v_components,
                "v_score": sum(v_components.values()) / len(v_components),
                "phase": (
                    "pre-correction"
                    if decision_index <= int(row["distance"])
                    else "post-correction"
                ),
            }
        )

        if decision_index == int(row["distance"]):
            correction_record = {
                "decision_boundary": decision_index,
                "history": history,
                "visible_message": None,
                "visible_message_sha256": None,
                "patch": None,
            }
            if history == "C_align":
                correction_record["patch"] = apply_environment_patch(
                    context, baseline_context, patch
                )
            if history in {"N", "S", "C_text", "C_align"}:
                authority_row = authority[(episode["episode_id"], history)]
                content = authority_row["content"]
                if hashlib.sha256(content.encode("utf-8")).hexdigest() != authority_row[
                    "content_sha256"
                ]:
                    raise RuntimeError("权威消息内容哈希不匹配")
                add_authority_message(context, content)
                messages.append({"role": authority_row["role"], "content": content})
                correction_record["visible_message"] = content
                correction_record["visible_message_sha256"] = hashlib.sha256(
                    content.encode("utf-8")
                ).hexdigest()

        if decision_index < total_decisions and early_completion:
            add_continuation(context)
            messages.append({"role": "user", "content": CONTINUATION})

    set_current_context(context)
    evaluation = scenario.evaluation.evaluate(
        execution_context=get_current_context(), max_turn_count=scenario.max_messages
    )
    ending_snapshot = context.to_dict(serialize_console=False)
    error_count = sum(row["error_consistent_action"] for row in decisions)
    debt_count = sum(row["environment_debt"] for row in decisions)
    return {
        "schema_version": 1,
        "protocol_id": "QHIST-EXP",
        "protocol_version": PROTOCOL_VERSION,
        "unit": row,
        "status": "succeeded",
        "prefix_observation": "truth" if use_truth else "false",
        "prefix_observation_sha256": (
            episode["prefix"]["truth_sha256"]
            if use_truth
            else episode["prefix"]["false_sha256"]
        ),
        "tool_schema_sha256": episode["tool_schema_sha256"],
        "correction": correction_record,
        "decisions": decisions,
        "metrics": {
            "normalized_q_auc": sum(row["v_score"] for row in decisions)
            / len(decisions),
            "adoption_alpha": float(decisions[0]["error_consistent_action"]),
            "error_action_count": error_count,
            "environment_debt_boundary_count": debt_count,
            "context_residual": float(decisions[-1]["error_consistent_action"]),
            "environment_residual": float(decisions[-1]["environment_debt"]),
            "format_validity": 1.0 - invalid_format_count / len(decisions),
            "tool_call_exception_count": sum(
                item["exception"] is not None
                for decision in decisions
                for item in decision["execution"]
            ),
            "tool_call_count": total_tool_calls,
        },
        "evaluation": attrs.asdict(evaluation),
        "ending_snapshot": ending_snapshot,
        "ending_snapshot_sha256": canonical_sha256(ending_snapshot),
        "elapsed_seconds": round(time.time() - unit_started, 6),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--precision", choices=PRECISIONS, required=True)
    parser.add_argument("--assets", type=Path, required=True)
    parser.add_argument("--rendered", type=Path, required=True)
    parser.add_argument("--model-endpoint", required=True)
    parser.add_argument("--toolsandbox-source", type=Path, required=True)
    parser.add_argument("--toolsandbox-site-packages", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--seed", type=int, default=20260903)
    parser.add_argument("--max-new-tokens", type=int, default=256)
    args = parser.parse_args()
    if args.output.exists() and any(args.output.iterdir()):
        raise RuntimeError(f"输出目录必须不存在或为空：{args.output}")
    args.output.mkdir(parents=True, exist_ok=True)
    runtime = prepare_toolsandbox(
        args.toolsandbox_source, args.toolsandbox_site_packages
    )

    from tool_sandbox.common.tool_discovery import ToolBackend
    from tool_sandbox.scenarios import named_scenarios
    started = time.time()
    summary: dict[str, Any] = {
        "schema_version": 1,
        "protocol_id": "QHIST-EXP",
        "protocol_version": PROTOCOL_VERSION,
        "status": "running",
        "precision": args.precision,
        "seed": args.seed,
        "runtime": runtime,
        "software": {"python": sys.version},
        "model_endpoint": args.model_endpoint,
    }
    exit_code = 1
    try:
        asset_manifest = verify_manifest(args.assets)
        rendered_manifest = verify_manifest(args.rendered, require_checks=True)
        episodes = {row["episode_id"]: row for row in read_jsonl(args.assets / "episodes.jsonl")}
        predicates = {row["episode_id"]: row for row in read_jsonl(args.assets / "predicates.jsonl")}
        patches = {row["episode_id"]: row for row in read_jsonl(args.assets / "environment-patches.jsonl")}
        units = read_jsonl(args.assets / "trajectory-units.jsonl")
        authority = {
            (row["episode_id"], row["condition"]): row
            for row in read_jsonl(args.rendered / "authority-messages.jsonl")
        }
        schedule = build_schedule(units, args.precision, args.seed)
        write_json(args.output / "schedule.json", schedule)
        scenarios = named_scenarios(preferred_tool_backend=ToolBackend.DEFAULT)
        unit_successes = 0
        invalid_units = 0
        attempted_units = 0
        for row in schedule:
            attempted_units += 1
            unit_id = row["unit_id"]
            unit_path = args.output / "units" / f"{unit_id}.json"
            try:
                result = run_unit(
                    row,
                    episodes[row["episode_id"]],
                    predicates[row["episode_id"]],
                    patches[row["episode_id"]],
                    authority,
                    args.assets,
                    scenarios[row["scenario"]],
                    args.model_endpoint,
                    args.max_new_tokens,
                )
                unit_successes += 1
            except Exception as error:
                invalid_units += 1
                result = {
                    "schema_version": 1,
                    "protocol_id": "QHIST-EXP",
                    "protocol_version": PROTOCOL_VERSION,
                    "unit": row,
                    "status": "invalid",
                    "error_type": type(error).__name__,
                    "error": str(error),
                    "traceback": traceback.format_exc(),
                }
            write_json(unit_path, result)
            append_jsonl(
                args.output / "results.jsonl",
                {
                    "unit_id": unit_id,
                    "status": result["status"],
                    "artifact": str(unit_path.relative_to(args.output)).replace("\\", "/"),
                    "artifact_sha256": sha256_file(unit_path),
                    "metrics": result.get("metrics"),
                    "elapsed_seconds": result.get("elapsed_seconds"),
                    "error_type": result.get("error_type"),
                    "error": result.get("error"),
                },
            )
            gc.collect()
            if result["status"] == "invalid":
                break
        summary.update(
            {
                "status": "succeeded" if invalid_units == 0 else "failed",
                "expected_units": len(schedule),
                "completed_units": attempted_units,
                "succeeded_units": unit_successes,
                "invalid_units": invalid_units,
                "schedule_sha256": sha256_file(args.output / "schedule.json"),
                "results_sha256": sha256_file(args.output / "results.jsonl"),
                "asset_manifest_sha256": sha256_file(args.assets / "manifest.json"),
                "rendered_manifest_sha256": sha256_file(
                    args.rendered / "manifest.json"
                ),
                "asset_manifest_protocol": asset_manifest["protocol_version"],
                "rendered_manifest_protocol": rendered_manifest[
                    "protocol_version"
                ],
            }
        )
        exit_code = 0 if invalid_units == 0 else 1
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
        summary["elapsed_seconds"] = round(time.time() - started, 6)
        write_json(args.output / "summary.json", summary)
        print(json.dumps(summary, ensure_ascii=False, indent=2, default=str))
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
