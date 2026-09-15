#!/usr/bin/env python3
"""Deterministic control plane for long-running research projects."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
from pathlib import Path
from typing import Any

try:
    from .policy import (layout_path, ResearchRoot, SCHEMA_VERSION, GATE_POLICY_VERSION, LAYOUT, STAGES, TRANSITIONS, GATES, PERMISSIONS, EXPERIMENT_STAGES, RUN_STAGES, QUALITY_DIMENSIONS, EMPIRICAL_ORDER)
    from .storage import (project_lock, now, read_json, write_json_atomic, append_jsonl, read_jsonl, project, load_events, event_hash, emit, verify_events)
    from .stdio import configure_utf8_stdio
except ImportError:
    from policy import (layout_path, ResearchRoot, SCHEMA_VERSION, GATE_POLICY_VERSION, LAYOUT, STAGES, TRANSITIONS, GATES, PERMISSIONS, EXPERIMENT_STAGES, RUN_STAGES, QUALITY_DIMENSIONS, EMPIRICAL_ORDER)
    from storage import (project_lock, now, read_json, write_json_atomic, append_jsonl, read_jsonl, project, load_events, event_hash, emit, verify_events)
    from stdio import configure_utf8_stdio


try:
    from .execution import (BUNDLE_FILES, bundle_files, manifest_digest, verify_protocol,
        verify_execution_authorization, required_permissions, artifact_path, artifact_files, digest,
        empirical_status, verified_outcomes, require_pilot_evidence, require_main_evidence)
except ImportError:
    from execution import (BUNDLE_FILES, bundle_files, manifest_digest, verify_protocol,
        verify_execution_authorization, required_permissions, artifact_path, artifact_files, digest,
        empirical_status, verified_outcomes, require_pilot_evidence, require_main_evidence)


try:
    from .gates import (require_gates, require_stage, require_current_policy, quality_errors, novelty_refresh_errors, nonnegative, markdown_field, proposal_metadata, later_empirical_status, require_nonempty, completion_errors, proposal_errors, theory_errors, scope_errors, protocol_errors, stage_errors)
except ImportError:
    from gates import (require_gates, require_stage, require_current_policy, quality_errors, novelty_refresh_errors, nonnegative, markdown_field, proposal_metadata, later_empirical_status, require_nonempty, completion_errors, proposal_errors, theory_errors, scope_errors, protocol_errors, stage_errors)


def command_init(args: argparse.Namespace) -> None:
    outer = Path(args.directory).resolve()
    root = ResearchRoot(outer / ".research")
    if (root / "research.json").exists() or (root / "state.json").exists() or (outer / "research.json").exists():
        raise SystemExit(f"research project already initialized: {outer}")
    root.mkdir(parents=True, exist_ok=True)
    for directory in ("control", "review", "proposal", "theory", "experiments", "paper"):
        (root.base / directory).mkdir(exist_ok=True)
    (outer / "outputs").mkdir(exist_ok=True)
    nonnegative("gpu-hours", args.gpu_hours)
    nonnegative("cost", args.cost)
    config = {
        "schema_version": SCHEMA_VERSION,
        "gate_policy_version": GATE_POLICY_VERSION,
        "topic": args.topic,
        "research_type": args.research_type,
        "created_at": now(),
        "budget": {"gpu_hours": args.gpu_hours, "cost": args.cost},
        "permissions": {name: False for name in PERMISSIONS},
    }
    state = {
        "schema_version": SCHEMA_VERSION,
        "policy_status": "current",
        "workflow_status": "in-progress",
        "research_stage": "initialized",
        "proposal_decision": "not-assessed",
        "novelty_status": "not-assessed",
        "empirical_status": "not-run",
        "execution_readiness": "not-assessed",
        "iteration": 0,
        "protocol_version": None,
        "usage": {"gpu_hours": 0.0, "cost": 0.0},
        "updated_at": now(),
    }
    write_json_atomic(root / "research.json", config)
    write_json_atomic(root / "state.json", state)
    (root / "events.jsonl").touch(exist_ok=False)
    (root / "decisions.jsonl").touch(exist_ok=False)
    emit(root, "project-initialized", args.actor, {"topic": args.topic, "research_type": args.research_type})
    print(outer)


def command_status(args: argparse.Namespace) -> None:
    root = project(args.directory)
    verify_events(root)
    print(json.dumps({"research": read_json(root / "research.json"), "state": read_json(root / "state.json")}, ensure_ascii=False, indent=2))


def command_migrate_policy(args: argparse.Namespace) -> None:
    root = project(args.directory)
    verify_events(root)
    config, state = read_json(root / "research.json"), read_json(root / "state.json")
    previous = {"schema_version": config.get("schema_version"), "gate_policy_version": config.get("gate_policy_version")}
    migration_dir = root / "control/migrations"
    migration_dir.mkdir(parents=True, exist_ok=True)
    archive_path = migration_dir / f"before-{len(load_events(root)) + 1}.json"
    write_json_atomic(archive_path, {"project": config, "state": state})
    stage = state["research_stage"]
    if stage == "blocked":
        stage = state.get("resume_stage", "experiment-protocol")
    if stage in STAGES and STAGES.index(stage) >= STAGES.index("pilot"):
        state["research_stage"] = "experiment-protocol"
        state["workflow_status"] = "in-progress"
    lock_path = root / "experiments/protocol.lock.json"
    if lock_path.exists():
        lock_path.rename(migration_dir / f"protocol-lock-{len(load_events(root)) + 1}.json")
    config.update({"schema_version": SCHEMA_VERSION, "gate_policy_version": GATE_POLICY_VERSION})
    state.update({
        "schema_version": SCHEMA_VERSION,
        "policy_status": "migration-required",
        "proposal_decision": "not-assessed",
        "empirical_status": "not-run",
        "execution_readiness": "not-assessed",
        "updated_at": now(),
    })
    write_json_atomic(root / "research.json", config); write_json_atomic(root / "state.json", state)
    emit(root, "policy-migration-started", args.actor, {"previous": previous, "reason": args.reason})


def command_revalidate_policy(args: argparse.Namespace) -> None:
    root = project(args.directory)
    verify_events(root)
    config, state = read_json(root / "research.json"), read_json(root / "state.json")
    if config.get("schema_version") != SCHEMA_VERSION or config.get("gate_policy_version") != GATE_POLICY_VERSION:
        raise SystemExit("run migrate-policy first")
    stage = state["research_stage"]
    errors = stage_errors(root, stage)
    if errors:
        raise SystemExit("policy revalidation failed: " + "; ".join(errors))
    if stage not in {"initialized", "problem-framing", "literature-mapping", "direction-audit", "blocked", "terminated"}:
        metadata = proposal_metadata(root)
        state.update({
            "proposal_decision": "pass",
            "novelty_status": "audited",
            "empirical_status": empirical_status(root),
            "execution_readiness": metadata.get("execution_readiness", "designed"),
        })
    state.update({"policy_status": "current", "updated_at": now()})
    write_json_atomic(root / "state.json", state)
    emit(root, "policy-revalidated", args.actor, {"stage": stage})


def command_audit_proposal(args: argparse.Namespace) -> None:
    root = project(args.directory)
    verify_events(root)
    errors = proposal_errors(root)
    if errors:
        raise SystemExit("proposal audit failed: " + "; ".join(errors))
    corpus = [item for item in read_jsonl(root / "literature/corpus.jsonl") if item.get("screening_status") == "included"]
    core = [item for item in corpus if item.get("role") == "core" and item.get("access_level") == "full-text"]
    metadata = proposal_metadata(root)
    print(json.dumps({
        "status": "pass",
        "proposal_decision": metadata.get("proposal_decision", "pass"),
        "novelty_status": metadata.get("novelty_status", "audited"),
        "empirical_status": empirical_status(root),
        "execution_readiness": metadata.get("execution_readiness", "designed"),
        "included": len(corpus),
        "core_full_text": len(core),
    }, ensure_ascii=False))


def command_audit_theory(args: argparse.Namespace) -> None:
    root = project(args.directory)
    verify_events(root)
    errors = theory_errors(root)
    if errors:
        raise SystemExit("theory audit failed: " + "; ".join(errors))
    print(json.dumps({"status": "pass", "hypotheses": len(read_jsonl(root / "theory/claims.jsonl")), "predictions": len(read_jsonl(root / "theory/predictions.jsonl"))}, ensure_ascii=False))


def command_audit_scope(args: argparse.Namespace) -> None:
    root = project(args.directory)
    verify_events(root)
    errors = scope_errors(root)
    if errors:
        raise SystemExit("scope audit failed: " + "; ".join(errors))
    print(json.dumps({"status": "pass"}))


def command_audit_protocol(args: argparse.Namespace) -> None:
    root = project(args.directory)
    verify_events(root)
    errors = protocol_errors(root)
    if errors:
        raise SystemExit("protocol audit failed: " + "; ".join(errors))
    print(json.dumps({"status": "pass", "predictions": len(read_jsonl(root / "theory/predictions.jsonl"))}))


def command_audit_pre_experiment(args: argparse.Namespace) -> None:
    root = project(args.directory)
    verify_events(root)
    state = read_json(root / "state.json")
    errors = scope_errors(root) + proposal_errors(root) + theory_errors(root) + protocol_errors(root) + novelty_refresh_errors(root, "pre-experiment")
    if state["research_stage"] != "experiment-protocol":
        errors.append(f"research stage must be experiment-protocol, got {state['research_stage']}")
    try:
        verify_protocol(root)
    except SystemExit as error:
        errors.append(str(error))
    if errors:
        raise SystemExit("pre-experiment audit failed: " + "; ".join(errors))
    print(json.dumps({"status": "ready-for-explicit-execution-decision", "protocol_version": state["protocol_version"]}, ensure_ascii=False))


def command_transition(args: argparse.Namespace) -> None:
    root = project(args.directory)
    verify_events(root)
    require_current_policy(root)
    state = read_json(root / "state.json")
    current = state["research_stage"]
    if current == "blocked" and args.target != "terminated" and args.target != state.get("resume_stage"):
        raise SystemExit("blocked projects must resume their recorded stage before changing direction")
    if args.target not in TRANSITIONS.get(current, set()):
        raise SystemExit(f"invalid transition: {current} -> {args.target}")
    errors = stage_errors(root, args.target, entering=True)
    if errors:
        label = "completion audit failed" if args.target == "complete" else "stage audit failed"
        raise SystemExit(label + ": " + "; ".join(errors))
    if args.target == "blocked":
        state["resume_stage"] = current
    previous_status = state["workflow_status"]
    state["research_stage"] = args.target
    terminal_status = {"blocked": "blocked", "complete": "complete", "terminated": "terminated"}
    state["workflow_status"] = terminal_status.get(args.target, "in-progress")
    if args.target in {"literature-mapping", "direction-audit"}:
        state.update({"proposal_decision": "not-assessed", "execution_readiness": "not-assessed"})
        if args.target == "literature-mapping":
            state["novelty_status"] = "not-assessed"
        elif state.get("novelty_status") == "audited":
            state["novelty_status"] = "provisional"
    if args.target == "theory-building":
        metadata = proposal_metadata(root)
        state.update({
            "proposal_decision": "pass",
            "novelty_status": "audited",
            "empirical_status": empirical_status(root),
            "execution_readiness": metadata.get("execution_readiness", "designed"),
        })
    if args.target == "experiment-protocol":
        state["execution_readiness"] = "designed"
    if args.target == "pilot":
        state["execution_readiness"] = "deployable"
    state["empirical_status"] = empirical_status(root)
    if STAGES.index(args.target) < STAGES.index(current) and args.target not in {"blocked", "terminated"}:
        state["iteration"] += 1
    state["updated_at"] = now()
    emit(root, "stage-transition", args.actor, {"from": current, "to": args.target, "reason": args.reason, "evidence": args.evidence, "previous_status": previous_status})
    write_json_atomic(root / "state.json", state)


def command_decide(args: argparse.Namespace) -> None:
    root = project(args.directory)
    verify_events(root)
    require_current_policy(root)
    record = {"time": now(), "actor": args.actor, "decision": args.decision, "reason": args.reason, "evidence": args.evidence, "alternatives": args.alternative}
    append_jsonl(root / "decisions.jsonl", record)
    emit(root, "decision-recorded", args.actor, {"decision": args.decision})


def command_freeze(args: argparse.Namespace) -> None:
    root = project(args.directory)
    verify_events(root)
    require_current_policy(root)
    protocol = root / "experiments/protocol.md"
    if not protocol.is_file():
        raise SystemExit("missing experiments/protocol.md")
    digest = hashlib.sha256(protocol.read_bytes()).hexdigest()
    state = read_json(root / "state.json")
    require_stage(state, {"experiment-protocol"}, "freeze-protocol")
    verified_outcomes(root, require_terminal=True)
    errors = protocol_errors(root)
    if errors:
        raise SystemExit("protocol audit failed: " + "; ".join(errors))
    declared = re.search(r"(?im)^\s*-?\s*Protocol version:\s*(\d+)\s*$", protocol.read_text(encoding="utf-8"))
    expected_version = int(state.get("protocol_version") or 0) + 1
    if not declared or int(declared.group(1)) != expected_version:
        raise SystemExit(f"protocol must declare the next version: {expected_version}")
    version = int(state.get("protocol_version") or 0) + 1
    files = bundle_files(root)
    lock = {"lock_schema": 2, "version": version, "sha256": digest,
            "files_sha256": files, "bundle_sha256": manifest_digest(files),
            "frozen_at": now(), "actor": args.actor}
    archive = root / "experiments/protocols" / f"v{version:03d}.md"
    bundle = root / "experiments/protocols" / f"v{version:03d}.bundle"
    if archive.exists() or bundle.exists():
        raise SystemExit(f"protocol archive already exists: {archive}")
    archive.parent.mkdir(parents=True, exist_ok=True)
    archive.write_bytes(protocol.read_bytes())
    for name in BUNDLE_FILES:
        target = bundle / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes((root / name).read_bytes())
    lock["archive"] = archive.relative_to(root).as_posix()
    lock["archive_sha256"] = hashlib.sha256(archive.read_bytes()).hexdigest()
    write_json_atomic(archive.with_suffix(".lock.json"), lock)
    write_json_atomic(root / "experiments/protocol.lock.json", lock)
    state["protocol_version"] = version
    state["updated_at"] = now()
    write_json_atomic(root / "state.json", state)
    emit(root, "protocol-frozen", args.actor, lock)
    print(json.dumps(lock, indent=2))


def permission_required(config: dict[str, Any], permission: str) -> None:
    if permission != "none" and not config["permissions"].get(permission, False):
        raise SystemExit(f"permission not authorized: {permission}")


def command_experiment(args: argparse.Namespace) -> None:
    root = project(args.directory)
    verify_events(root)
    require_current_policy(root)
    state = read_json(root / "state.json")
    require_stage(state, EXPERIMENT_STAGES, "register-experiment")
    verify_protocol(root)
    registry = root / "experiments/registry.jsonl"
    if any(item.get("experiment_id") == args.id for item in read_jsonl(registry)):
        raise SystemExit(f"duplicate experiment ID: {args.id}")
    record = {"experiment_id": args.id, "time": now(), "actor": args.actor, "protocol_version": state["protocol_version"], "claim_ids": args.claim, "hypothesis_ids": args.hypothesis, "purpose": args.purpose, "status": "registered"}
    append_jsonl(root / "experiments/registry.jsonl", record)
    emit(root, "experiment-registered", args.actor, {"experiment_id": args.id})


def command_run(args: argparse.Namespace) -> None:
    root = project(args.directory)
    verify_events(root)
    require_current_policy(root)
    config = read_json(root / "research.json")
    state = read_json(root / "state.json")
    require_stage(state, RUN_STAGES, "register-run")
    errors = stage_errors(root, state["research_stage"])
    if errors:
        raise SystemExit("run admission failed: " + "; ".join(errors))
    nonnegative("gpu-hours", args.gpu_hours)
    nonnegative("cost", args.cost)
    lock = verify_protocol(root)
    verify_execution_authorization(root)
    if not any(item.get("experiment_id") == args.experiment and item.get("protocol_version") == lock["version"] for item in read_jsonl(root / "experiments/registry.jsonl")):
        raise SystemExit(f"unknown experiment ID: {args.experiment}")
    if any(item.get("run_id") == args.id for item in read_jsonl(root / "runs/registry.jsonl")):
        raise SystemExit(f"duplicate run ID: {args.id}")
    permission_required(config, args.permission)
    if state["usage"]["gpu_hours"] + args.gpu_hours > config["budget"]["gpu_hours"]:
        raise SystemExit("GPU-hour budget exceeded")
    if state["usage"]["cost"] + args.cost > config["budget"]["cost"]:
        raise SystemExit("cost budget exceeded")
    config_path = require_nonempty(root, args.config)
    record = {"record_schema": 2, "run_id": args.id, "stage": state["research_stage"], "bundle_sha256": lock["bundle_sha256"], "experiment_id": args.experiment, "time": now(), "actor": args.actor, "protocol_version": state["protocol_version"], "config": args.config, "config_sha256": hashlib.sha256(config_path.read_bytes()).hexdigest(), "code_revision": args.code_revision, "environment": args.environment, "seeds": args.seed, "reserved_gpu_hours": args.gpu_hours, "reserved_cost": args.cost, "status": "queued"}
    append_jsonl(root / "runs/registry.jsonl", record)
    state["usage"]["gpu_hours"] += args.gpu_hours
    state["usage"]["cost"] += args.cost
    state["updated_at"] = now()
    write_json_atomic(root / "state.json", state)
    emit(root, "run-registered", args.actor, record)


def command_finish_run(args: argparse.Namespace) -> None:
    root = project(args.directory)
    verify_events(root)
    verified_outcomes(root)
    registrations = read_jsonl(root / "runs/registry.jsonl")
    matches = [item for item in registrations if item.get("run_id") == args.id]
    if len(matches) != 1:
        raise SystemExit(f"run ID must have exactly one registration: {args.id}")
    if any(item.get("run_id") == args.id for item in read_jsonl(root / "runs/outcomes.jsonl")):
        raise SystemExit(f"run already finished: {args.id}")
    registered = matches[0]
    try:
        observed_config_sha256 = digest(artifact_path(root, registered["config"]))
    except SystemExit:
        if args.status not in {"invalid", "cancelled"}:
            raise
        observed_config_sha256 = None
    config_changed = observed_config_sha256 != registered["config_sha256"]
    if config_changed and args.status not in {"invalid", "cancelled"}:
        raise SystemExit("run config changed after registration; close as invalid or cancelled")
    nonnegative("gpu-hours", args.gpu_hours)
    nonnegative("cost", args.cost)
    if args.status == "succeeded" and not args.artifact:
        raise SystemExit("a succeeded run requires --artifact")
    artifact_sha256 = None
    files = None
    if args.artifact:
        files = artifact_files(root, args.artifact)
        artifact_sha256 = files[args.artifact]
    state = read_json(root / "state.json")
    state["usage"]["gpu_hours"] = max(0.0, state["usage"]["gpu_hours"] - registered["reserved_gpu_hours"] + args.gpu_hours)
    state["usage"]["cost"] = max(0.0, state["usage"]["cost"] - registered["reserved_cost"] + args.cost)
    state["updated_at"] = now()
    config = read_json(root / "research.json")
    budget_exceeded = state["usage"]["gpu_hours"] > config["budget"]["gpu_hours"] or state["usage"]["cost"] > config["budget"]["cost"]
    outcome = {"run_id": args.id, "time": now(), "actor": args.actor, "status": args.status, "actual_gpu_hours": args.gpu_hours, "actual_cost": args.cost, "artifact": args.artifact, "artifact_sha256": artifact_sha256, "artifact_files_sha256": files, "config_changed": config_changed, "observed_config_sha256": observed_config_sha256, "budget_exceeded": budget_exceeded, "reason": args.reason}
    append_jsonl(root / "runs/outcomes.jsonl", outcome)
    emit(root, "run-finished", args.actor, outcome)
    state["empirical_status"] = empirical_status(root)
    write_json_atomic(root / "state.json", state)


def command_authorize_execution(args: argparse.Namespace) -> None:
    root = project(args.directory)
    verify_events(root)
    require_current_policy(root)
    evidence = artifact_path(root, args.evidence)
    payload = {"granted": args.value == "true", "reason": args.reason,
               "evidence": args.evidence, "evidence_sha256": digest(evidence)}
    if payload["granted"]:
        require_stage(read_json(root / "state.json"), {"experiment-protocol", "pilot", "main-experiment", "robustness-analysis"}, "authorize-execution")
        lock = verify_protocol(root)
        for permission in required_permissions(root):
            permission_required(read_json(root / "research.json"), permission)
        payload.update(protocol_version=lock["version"], bundle_sha256=lock["bundle_sha256"])
    emit(root, "execution-authorized", args.actor, payload)


def command_authorize(args: argparse.Namespace) -> None:
    root = project(args.directory)
    verify_events(root)
    require_current_policy(root)
    config = read_json(root / "research.json")
    config["permissions"][args.permission] = args.value == "true"
    write_json_atomic(root / "research.json", config)
    emit(root, "permission-changed", args.actor, {"permission": args.permission, "value": config["permissions"][args.permission], "reason": args.reason})


def command_set_budget(args: argparse.Namespace) -> None:
    root = project(args.directory)
    verify_events(root)
    require_current_policy(root)
    nonnegative("gpu-hours", args.gpu_hours)
    nonnegative("cost", args.cost)
    config = read_json(root / "research.json")
    state = read_json(root / "state.json")
    if args.gpu_hours < state["usage"]["gpu_hours"] or args.cost < state["usage"]["cost"]:
        raise SystemExit("budget cannot be lower than recorded usage")
    previous = dict(config["budget"])
    config["budget"] = {"gpu_hours": args.gpu_hours, "cost": args.cost}
    write_json_atomic(root / "research.json", config)
    emit(root, "budget-changed", args.actor, {"previous": previous, "current": config["budget"], "reason": args.reason})


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(description=__doc__)
    commands = result.add_subparsers(dest="command", required=True)
    init = commands.add_parser("init")
    init.add_argument("directory"); init.add_argument("--topic", required=True); init.add_argument("--research-type", required=True)
    init.add_argument("--gpu-hours", type=float, default=0.0); init.add_argument("--cost", type=float, default=0.0); init.add_argument("--actor", default="research-director"); init.set_defaults(func=command_init)
    status = commands.add_parser("status"); status.add_argument("directory"); status.set_defaults(func=command_status)
    migrate = commands.add_parser("migrate-policy"); migrate.add_argument("directory"); migrate.add_argument("--reason", required=True); migrate.add_argument("--actor", default="orchestrator"); migrate.set_defaults(func=command_migrate_policy)
    revalidate = commands.add_parser("revalidate-policy"); revalidate.add_argument("directory"); revalidate.add_argument("--actor", default="orchestrator"); revalidate.set_defaults(func=command_revalidate_policy)
    scope_audit = commands.add_parser("audit-scope"); scope_audit.add_argument("directory"); scope_audit.set_defaults(func=command_audit_scope)
    proposal_audit = commands.add_parser("audit-proposal"); proposal_audit.add_argument("directory"); proposal_audit.set_defaults(func=command_audit_proposal)
    theory_audit = commands.add_parser("audit-theory"); theory_audit.add_argument("directory"); theory_audit.set_defaults(func=command_audit_theory)
    protocol_audit = commands.add_parser("audit-protocol"); protocol_audit.add_argument("directory"); protocol_audit.set_defaults(func=command_audit_protocol)
    pre_experiment = commands.add_parser("audit-pre-experiment"); pre_experiment.add_argument("directory"); pre_experiment.set_defaults(func=command_audit_pre_experiment)
    transition = commands.add_parser("transition"); transition.add_argument("directory"); transition.add_argument("target", choices=STAGES); transition.add_argument("--reason", required=True); transition.add_argument("--evidence", action="append", default=[]); transition.add_argument("--actor", default="orchestrator"); transition.set_defaults(func=command_transition)
    decide = commands.add_parser("decide"); decide.add_argument("directory"); decide.add_argument("--decision", required=True); decide.add_argument("--reason", required=True); decide.add_argument("--evidence", action="append", default=[]); decide.add_argument("--alternative", action="append", default=[]); decide.add_argument("--actor", default="research-director"); decide.set_defaults(func=command_decide)
    freeze = commands.add_parser("freeze-protocol"); freeze.add_argument("directory"); freeze.add_argument("--actor", default="experimental-designer"); freeze.set_defaults(func=command_freeze)
    experiment = commands.add_parser("register-experiment"); experiment.add_argument("directory"); experiment.add_argument("--id", required=True); experiment.add_argument("--claim", action="append", default=[]); experiment.add_argument("--hypothesis", action="append", default=[]); experiment.add_argument("--purpose", required=True); experiment.add_argument("--actor", default="experimental-designer"); experiment.set_defaults(func=command_experiment)
    run = commands.add_parser("register-run"); run.add_argument("directory"); run.add_argument("--id", required=True); run.add_argument("--experiment", required=True); run.add_argument("--config", required=True); run.add_argument("--code-revision", required=True); run.add_argument("--environment", required=True); run.add_argument("--seed", action="append", default=[]); run.add_argument("--gpu-hours", type=float, default=0.0); run.add_argument("--cost", type=float, default=0.0); run.add_argument("--permission", choices=("none",) + PERMISSIONS, default="none"); run.add_argument("--actor", default="experiment-manager"); run.set_defaults(func=command_run)
    finish = commands.add_parser("finish-run"); finish.add_argument("directory"); finish.add_argument("--id", required=True); finish.add_argument("--status", choices=("succeeded", "failed", "timed-out", "cancelled", "invalid"), required=True); finish.add_argument("--gpu-hours", type=float, default=0.0); finish.add_argument("--cost", type=float, default=0.0); finish.add_argument("--artifact"); finish.add_argument("--reason", required=True); finish.add_argument("--actor", default="experiment-manager"); finish.set_defaults(func=command_finish_run)
    execution = commands.add_parser("authorize-execution"); execution.add_argument("directory"); execution.add_argument("value", choices=("true", "false")); execution.add_argument("--evidence", required=True); execution.add_argument("--reason", required=True); execution.add_argument("--actor", default="user"); execution.set_defaults(func=command_authorize_execution)
    authorize = commands.add_parser("authorize"); authorize.add_argument("directory"); authorize.add_argument("permission", choices=PERMISSIONS); authorize.add_argument("value", choices=("true", "false")); authorize.add_argument("--reason", required=True); authorize.add_argument("--actor", default="user"); authorize.set_defaults(func=command_authorize)
    budget = commands.add_parser("set-budget"); budget.add_argument("directory"); budget.add_argument("--gpu-hours", type=float, required=True); budget.add_argument("--cost", type=float, required=True); budget.add_argument("--reason", required=True); budget.add_argument("--actor", default="research-director"); budget.set_defaults(func=command_set_budget)
    verify = commands.add_parser("verify-log"); verify.add_argument("directory"); verify.set_defaults(func=lambda args: verify_events(project(args.directory)))
    return result


if __name__ == "__main__":
    configure_utf8_stdio()
    arguments = parser().parse_args()
    if arguments.command in {"status", "verify-log", "audit-scope", "audit-proposal", "audit-theory", "audit-protocol", "audit-pre-experiment", "init"}:
        arguments.func(arguments)
    else:
        root = project(arguments.directory)
        with project_lock(root):
            arguments.func(arguments)
