"""Read-only research validation shared by transitions, audits, and migrations."""
from __future__ import annotations
import json
import math
import re
from pathlib import Path
from typing import Any

try:
    from .policy import (layout_path, ResearchRoot, SCHEMA_VERSION, GATE_POLICY_VERSION, LAYOUT, STAGES, TRANSITIONS, GATES, PERMISSIONS, EXPERIMENT_STAGES, RUN_STAGES, QUALITY_DIMENSIONS, EMPIRICAL_ORDER)
    from .storage import (project_lock, now, read_json, write_json_atomic, append_jsonl, read_jsonl, project, load_events, event_hash, emit, verify_events)
except ImportError:
    from policy import (layout_path, ResearchRoot, SCHEMA_VERSION, GATE_POLICY_VERSION, LAYOUT, STAGES, TRANSITIONS, GATES, PERMISSIONS, EXPERIMENT_STAGES, RUN_STAGES, QUALITY_DIMENSIONS, EMPIRICAL_ORDER)
    from storage import (project_lock, now, read_json, write_json_atomic, append_jsonl, read_jsonl, project, load_events, event_hash, emit, verify_events)


try:
    from .execution import (BUNDLE_FILES, bundle_files, manifest_digest, verify_protocol,
        verify_execution_authorization, required_permissions, artifact_path, digest,
        empirical_status, verified_outcomes, require_pilot_evidence, require_main_evidence)
except ImportError:
    from execution import (BUNDLE_FILES, bundle_files, manifest_digest, verify_protocol,
        verify_execution_authorization, required_permissions, artifact_path, digest,
        empirical_status, verified_outcomes, require_pilot_evidence, require_main_evidence)


def require_gates(root: Path, target: str) -> None:
    missing = [item for item in GATES.get(target, []) if not (root / item).is_file() or (root / item).stat().st_size == 0]
    if missing:
        raise SystemExit(f"transition gate for {target} is missing: {', '.join(missing)}")
    if target == "main-experiment":
        text = (root / "experiments/pilot.md").read_text(encoding="utf-8")
        if not re.search(r"(?im)^Pilot gate:\s*pass\s*$", text):
            raise SystemExit("main-experiment requires `Pilot gate: pass` in experiments/pilot.md")


def require_stage(state: dict[str, Any], allowed: set[str], operation: str) -> None:
    if state["research_stage"] not in allowed:
        raise SystemExit(f"{operation} is not allowed in stage {state['research_stage']}")


def require_current_policy(root: Path) -> None:
    config = read_json(root / "research.json")
    state = read_json(root / "state.json")
    if (config.get("schema_version") != SCHEMA_VERSION or
            config.get("gate_policy_version") != GATE_POLICY_VERSION or
            state.get("schema_version") != SCHEMA_VERSION or
            state.get("policy_status") != "current"):
        raise SystemExit("project policy is migration-required; run migrate-policy and revalidate-policy")


def quality_errors(root: Path) -> list[str]:
    path = root / "paper/quality-audit.json"
    if not path.is_file() or path.stat().st_size == 0:
        return ["missing or empty: paper/quality-audit.json"]
    try:
        audit = read_json(path)
    except (json.JSONDecodeError, OSError) as error:
        return [f"invalid paper/quality-audit.json: {error}"]
    errors: list[str] = []
    dimensions = audit.get("dimensions", {})
    if set(dimensions) != QUALITY_DIMENSIONS:
        errors.append("quality audit must contain exactly the ten unified quality dimensions")
    for name in QUALITY_DIMENSIONS:
        item = dimensions.get(name, {})
        if item.get("status") not in {"pass", "not-applicable"}:
            errors.append(f"quality dimension {name} is not closed")
        if not str(item.get("rationale", "")).strip() or not item.get("evidence"):
            errors.append(f"quality dimension {name} requires rationale and evidence locators")
    if audit.get("fatal_issues") != []:
        errors.append("quality audit has unresolved fatal issues")
    independence = audit.get("review_independence", {})
    for field in ("reviewer_role", "reviewer_model", "context_isolation"):
        if not str(independence.get(field, "")).strip():
            errors.append(f"quality audit missing review_independence.{field}")
    if independence.get("independent_evidence_check") is not True:
        errors.append("quality audit requires an independent evidence check")
    return errors


def novelty_refresh_errors(root: Path, phase: str) -> list[str]:
    path = root / f"proposal/novelty-refresh-{phase}.md"
    if not path.is_file() or path.stat().st_size == 0:
        return [f"missing or empty: proposal/novelty-refresh-{phase}.md"]
    text = path.read_text(encoding="utf-8")
    errors: list[str] = []
    for label in ("Search date:", "Databases:", "Query families:", "New nearest neighbors:", "Claim impact:"):
        if not re.search(rf"(?im)^\s*{re.escape(label)}\s*\S.*$", text):
            errors.append(f"novelty refresh {phase} missing non-empty field: {label}")
    if not re.search(r"(?im)^Refresh decision:\s*(pass|return-to-proposal)\s*$", text):
        errors.append(f"novelty refresh {phase} lacks a valid decision")
    elif re.search(r"(?im)^Refresh decision:\s*return-to-proposal\s*$", text):
        errors.append(f"novelty refresh {phase} requires return to proposal")
    return errors


def nonnegative(name: str, value: float) -> None:
    if not math.isfinite(value) or value < 0:
        raise SystemExit(f"{name} must be finite and non-negative")


def markdown_field(text: str, label: str) -> str | None:
    match = re.search(rf"(?im)^\s*-?\s*{re.escape(label)}\s*(\S.*)$", text)
    return match.group(1).strip() if match else None


def proposal_metadata(root: Path) -> dict[str, str]:
    path = root / "proposal.md"
    if not path.is_file() or path.stat().st_size == 0:
        return {}
    text = path.read_text(encoding="utf-8")
    labels = ("Proposal decision:", "Novelty status:", "Empirical status:", "Execution readiness:", "Paper sufficiency:")
    return {label[:-1].lower().replace(" ", "_"): value for label in labels if (value := markdown_field(text, label))}


def later_empirical_status(first: str | None, second: str | None) -> str:
    values = [value for value in (first, second) if value in EMPIRICAL_ORDER]
    return max(values, key=EMPIRICAL_ORDER.get) if values else "not-run"


def require_nonempty(root: Path, relative: str) -> Path:
    return artifact_path(root, relative)


def completion_errors(root: Path) -> list[str]:
    required = [
        "scope.md", "search-log.md", "literature.md", "literature/corpus.jsonl",
        "literature/coverage.md", "literature/nearest-neighbors.md",
        "research-directions.md", "selected-direction.md", "proposal.md",
        "proposal-depth-breadth.md", "proposal-audit.md", "theory.md", "theory/claims.jsonl",
        "theory/predictions.jsonl", "theory-audit.md", "experiments/protocol.md",
        "experiments/design.json", "experiments/analysis-plan.md", "experiments/protocol-audit.md",
        "experiments/protocol.lock.json", "experiments/pilot.md",
        "experiments/registry.jsonl", "runs/registry.jsonl", "runs/outcomes.jsonl",
        "experiments/results.md", "analysis.md", "evidence.md",
        "artifact/README.md", "report.md", "paper/manuscript.md",
        "paper/claims.jsonl", "paper/iterations.jsonl", "paper/quality-audit.json", "paper/unified-quality-audit.md",
        "paper/review.md", "paper/reproducibility.md", "proposal/novelty-refresh-pre-paper.md",
    ]
    errors = [item for item in required if not (root / item).is_file() or (root / item).stat().st_size == 0]
    if errors:
        return [f"missing or empty: {item}" for item in errors]
    errors.extend(theory_errors(root))
    errors.extend(quality_errors(root))
    errors.extend(novelty_refresh_errors(root, "pre-paper"))
    try:
        verify_protocol(root)
    except SystemExit as error:
        errors.append(str(error))
    try:
        verified_outcomes(root, require_terminal=True)
        require_main_evidence(root)
    except (SystemExit, OSError, ValueError, KeyError) as error:
        errors.append(str(error))
    outcomes = {item.get("run_id"): item for item in read_jsonl(root / "runs/outcomes.jsonl")}
    for run in read_jsonl(root / "runs/registry.jsonl"):
        if run.get("run_id") not in outcomes:
            errors.append(f"run has no terminal outcome: {run.get('run_id')}")
    if not re.search(r"(?im)^Outcome:\s*(supported|refuted|mixed|inconclusive)\s*$", (root / "experiments/results.md").read_text(encoding="utf-8")):
        errors.append("experiments/results.md lacks a valid Outcome")
    if not re.search(r"\bC\d+\b", (root / "evidence.md").read_text(encoding="utf-8")):
        errors.append("evidence.md lacks stable claim IDs")
    paper_review = (root / "paper/review.md").read_text(encoding="utf-8")
    if not re.search(r"(?im)^Review decision:\s*agent-review-cleared\s*$", paper_review):
        errors.append("paper/review.md must record `Review decision: agent-review-cleared` before completion")
    public_audit = root.parent / "outputs" / "04-论文与投稿审计.md"
    if not public_audit.is_file() or public_audit.stat().st_size == 0:
        errors.append("missing or empty user deliverable: outputs/04-论文与投稿审计.md")
    return errors


def proposal_errors(root: Path) -> list[str]:
    errors: list[str] = []
    corpus_path = root / "literature/corpus.jsonl"
    if not corpus_path.is_file() or corpus_path.stat().st_size == 0:
        return ["missing or empty: literature/corpus.jsonl"]
    try:
        corpus = read_jsonl(corpus_path)
    except (json.JSONDecodeError, OSError) as error:
        return [f"invalid literature/corpus.jsonl: {error}"]
    required = {"source_id", "title", "year", "stable_url", "identity_verified", "screening_status", "access_level", "role", "relevance_reason"}
    included: list[dict[str, Any]] = []
    seen: set[str] = set()
    for index, item in enumerate(corpus, start=1):
        missing = required - set(item)
        if missing:
            errors.append(f"corpus row {index} missing fields: {', '.join(sorted(missing))}")
            continue
        source_id = str(item["source_id"])
        if source_id in seen:
            errors.append(f"duplicate source_id: {source_id}")
        seen.add(source_id)
        if item["screening_status"] == "included":
            included.append(item)
            if item["identity_verified"] is not True:
                errors.append(f"included source is not identity-verified: {source_id}")
            for field in ("title", "stable_url", "relevance_reason"):
                if not str(item[field]).strip():
                    errors.append(f"included source has empty {field}: {source_id}")
    core = [item for item in included if item["role"] == "core" and item["access_level"] == "full-text"]
    if not included:
        errors.append("included corpus is empty")
    if not core:
        errors.append("core full-text set is empty")
    for item in core:
        card = root / "papers" / f"{item['source_id']}.md"
        if not card.is_file() or card.stat().st_size == 0:
            errors.append(f"core paper lacks a non-empty full-text analysis card: {item['source_id']}")
    required_files = (
        "search-log.md", "literature/coverage.md", "literature/nearest-neighbors.md",
        "proposal-candidates.jsonl", "proposal-claims.jsonl", "proposal-rivals.jsonl",
        "proposal-threats.jsonl", "proposal-iterations.jsonl",
        "proposal.md", "proposal-depth-breadth.md", "proposal-audit.md", "novelty-review.md",
    )
    for relative in required_files:
        path = root / relative
        if not path.is_file() or path.stat().st_size == 0:
            errors.append(f"missing or empty: {relative}")
    public = root.parent / "outputs"
    for name in ("01-文献调研总结.md", "02-验证后Proposal.md"):
        path = public / name
        if not path.is_file() or path.stat().st_size == 0:
            errors.append(f"missing or empty user deliverable: outputs/{name}")
    review_path = public / "01-文献调研总结.md"
    if review_path.is_file() and review_path.stat().st_size > 0:
        review = review_path.read_text(encoding="utf-8")
        motivation_count = len(re.findall(r"(?im)^####\s+研究动机\s*$", review))
        method_count = len(re.findall(r"(?im)^####\s+方法介绍\s*$", review))
        summary_count = len(re.findall(r"(?im)^####\s+总结归纳\s*$", review))
        if not (motivation_count == method_count == summary_count == len(core)):
            errors.append("outputs/01-文献调研总结.md must contain one matched motivation/method/summary analysis for every core full-text paper")
        if not re.search(r"(?im)^##\s+.*\d+\s*篇论文形成的整体认识.*$", review):
            errors.append("outputs/01-文献调研总结.md missing corpus-level synthesis section")
        if not re.search(r"(?im)^##\s+.*仍然存在的问题.*$", review):
            errors.append("outputs/01-文献调研总结.md missing section: 仍然存在的问题")
    public_proposal = public / "02-验证后Proposal.md"
    if public_proposal.is_file() and public_proposal.stat().st_size > 0:
        text = public_proposal.read_text(encoding="utf-8")
        public_statuses = {
            "Proposal decision:": r"pass",
            "Novelty status:": r"audited",
            "Empirical status:": r"not-run|pilot|tested",
            "Execution readiness:": r"designed|deployable|blocked",
        }
        for label, allowed in public_statuses.items():
            if not re.search(rf"(?im)^\s*-?\s*{re.escape(label)}\s*(?:{allowed})\s*$", text):
                errors.append(f"outputs/02-验证后Proposal.md missing or invalid status: {label}")
        for heading in (
                "研究背景与问题重要性", "精确研究问题", "研究边界与必要广度",
                "论证深度与机制链", "理论机制", "可证伪假设", "核心构念与测量",
                "最近邻与新颖性边界", "完整论文证据包", "风险、失败结果与停止条件"):
            if not re.search(rf"(?im)^##\s+.*{re.escape(heading)}.*$", text):
                errors.append(f"outputs/02-验证后Proposal.md missing section: {heading}")
    if errors:
        return errors
    coverage = (root / "literature/coverage.md").read_text(encoding="utf-8")
    for label in ("Corpus size rationale:", "Core set rationale:", "Direct-neighbor coverage:"):
        if not re.search(rf"(?im)^\s*{re.escape(label)}\s*\S.*$", coverage):
            errors.append(f"literature/coverage.md missing non-empty field: {label}")
    if not re.search(r"(?im)^Coverage status:\s*saturated\s*$", coverage):
        errors.append("literature/coverage.md requires `Coverage status: saturated`")
    try:
        candidates = read_jsonl(root / "proposal-candidates.jsonl")
        claims = read_jsonl(root / "proposal-claims.jsonl")
        rivals = read_jsonl(root / "proposal-rivals.jsonl")
        threats = read_jsonl(root / "proposal-threats.jsonl")
        iterations = read_jsonl(root / "proposal-iterations.jsonl")
    except (json.JSONDecodeError, OSError) as error:
        return [f"invalid proposal iteration registry: {error}"]
    proposal_text = (root / "proposal.md").read_text(encoding="utf-8")
    current_proposal_id = markdown_field(proposal_text, "Proposal ID:")
    if not current_proposal_id:
        errors.append("proposal.md missing field: Proposal ID:")
    if len(candidates) < 3:
        errors.append("proposal-candidates.jsonl requires at least three knowledge-distinct directions")
    selected_candidates = [item for item in candidates if str(item.get("status", "")).startswith("selected")]
    if len(selected_candidates) != 1:
        errors.append("proposal-candidates.jsonl requires exactly one selected direction")
    seen_candidate_claims: set[str] = set()
    for index, item in enumerate(candidates, start=1):
        missing = {
            "candidate_id", "status", "knowledge_question", "knowledge_claim",
            "mechanism", "decisive_test", "scientific_consequence",
        } - set(item)
        if missing:
            errors.append(f"proposal candidate row {index} missing fields: {', '.join(sorted(missing))}")
            continue
        normalized_claim = re.sub(r"\s+", " ", str(item["knowledge_claim"]).strip().lower())
        if not normalized_claim:
            errors.append(f"proposal candidate row {index} has an empty knowledge claim")
        elif normalized_claim in seen_candidate_claims:
            errors.append(f"proposal candidate row {index} duplicates another knowledge claim")
        seen_candidate_claims.add(normalized_claim)
        for field in ("knowledge_question", "mechanism", "decisive_test", "scientific_consequence"):
            if not str(item[field]).strip():
                errors.append(f"proposal candidate row {index} has empty {field}")
    if not claims:
        errors.append("proposal-claims.jsonl contains no atomic contribution claims")
    for index, item in enumerate(claims, start=1):
        missing = {"claim_id", "type", "status", "claim", "evidence", "scientific_consequence"} - set(item)
        if missing:
            errors.append(f"proposal claim row {index} missing fields: {', '.join(sorted(missing))}")
            continue
        if item.get("status") != "withdrawn" and (not item.get("evidence") or not str(item.get("scientific_consequence", "")).strip()):
            errors.append(f"retained proposal claim lacks evidence or scientific consequence: {item.get('claim_id')}")
    if not rivals:
        errors.append("proposal-rivals.jsonl contains no competing mechanism")
    for index, item in enumerate(rivals, start=1):
        missing = {"rival_id", "mechanism", "distinguishing_pattern"} - set(item)
        if missing:
            errors.append(f"proposal rival row {index} missing fields: {', '.join(sorted(missing))}")
    if not threats:
        errors.append("proposal-threats.jsonl contains no threat analysis")
    valid_threat_classes = {"proposal-fatal", "empirical-dependency", "paper-stage"}
    valid_threat_statuses = {"open", "mitigated", "resolved", "deferred"}
    for index, item in enumerate(threats, start=1):
        missing = {"threat_id", "class", "category", "severity", "status", "threat", "mitigation"} - set(item)
        if missing:
            errors.append(f"proposal threat row {index} missing fields: {', '.join(sorted(missing))}")
            continue
        if item.get("class") not in valid_threat_classes:
            errors.append(f"proposal threat row {index} has invalid class")
        if item.get("status") not in valid_threat_statuses:
            errors.append(f"proposal threat row {index} has invalid status")
    fatal_threats = [item for item in threats if item.get("class") == "proposal-fatal" and item.get("status") != "resolved"]
    if fatal_threats:
        errors.append("proposal-threats.jsonl contains unresolved proposal-fatal threats")
    required_cycles = {
        "candidate-comparison", "novelty-collision", "mechanism-falsification",
        "protocol-feasibility", "paper-architecture", "adversarial-review",
    }
    seen_cycles: set[str] = set()
    full_cycle_rounds: list[int] = []
    full_cycle_fields = {
        "round", "breadth_review", "depth_review", "novelty_review",
        "mechanism_review", "identification_review", "paper_review",
    }
    iteration_fields = {
        "iteration_id", "proposal_id", "cycle_type", "question", "inputs", "finding",
        "decision", "proposal_changed", "change_summary", "unresolved", "next_action",
    }
    for index, item in enumerate(iterations, start=1):
        missing = iteration_fields - set(item)
        if missing:
            errors.append(f"proposal iteration row {index} missing fields: {', '.join(sorted(missing))}")
            continue
        if item.get("proposal_id") == current_proposal_id:
            seen_cycles.add(str(item["cycle_type"]))
        if not isinstance(item["proposal_changed"], bool):
            errors.append(f"proposal iteration row {index} has non-boolean proposal_changed")
        for field in ("question", "finding", "decision", "change_summary", "next_action"):
            if not str(item[field]).strip():
                errors.append(f"proposal iteration row {index} has empty {field}")
        if not isinstance(item["inputs"], list) or not item["inputs"]:
            errors.append(f"proposal iteration row {index} requires evidence inputs")
        if not isinstance(item["unresolved"], list):
            errors.append(f"proposal iteration row {index} unresolved must be a list")
        if item.get("proposal_id") == current_proposal_id and item.get("cycle_type") == "full-proposal-cycle":
            missing_full = full_cycle_fields - set(item)
            if missing_full:
                errors.append(f"full proposal cycle row {index} missing fields: {', '.join(sorted(missing_full))}")
                continue
            if not isinstance(item["round"], int) or item["round"] < 1:
                errors.append(f"full proposal cycle row {index} has invalid round")
            else:
                full_cycle_rounds.append(item["round"])
            for field in full_cycle_fields - {"round"}:
                if not str(item[field]).strip():
                    errors.append(f"full proposal cycle row {index} has empty {field}")
    missing_cycles = required_cycles - seen_cycles
    if missing_cycles:
        errors.append(f"current proposal iteration record missing cycles: {', '.join(sorted(missing_cycles))}")
    if len(full_cycle_rounds) != len(set(full_cycle_rounds)):
        errors.append("current proposal has duplicate full-proposal-cycle round numbers")
    distinct_full_rounds = sorted(set(full_cycle_rounds))
    if len(distinct_full_rounds) < 5:
        errors.append("current proposal requires at least five full-proposal-cycle rounds")
    elif distinct_full_rounds[-5:] != list(range(distinct_full_rounds[-1] - 4, distinct_full_rounds[-1] + 1)):
        errors.append("current proposal requires five consecutive full-proposal-cycle rounds")
    if errors:
        return errors
    search = (root / "search-log.md").read_text(encoding="utf-8")
    rounds = re.findall(r"(?im)^Round:\s*\S+", search)
    changes = [value.lower() for value in re.findall(r"(?im)^Proposal changed:\s*(yes|no)\s*$", search)]
    if len(rounds) < 2 or len(changes) != len(rounds):
        errors.append("every directed search round must record `Proposal changed: yes|no`")
    if len(changes) < 2 or changes[-2:] != ["no", "no"]:
        errors.append("novelty saturation requires the last two directed rounds to record `Proposal changed: no`")
    if not re.search(r"(?im)^Saturation:\s*reached\s*$", search):
        errors.append("search-log.md requires `Saturation: reached` only after two stable rounds")
    depth_breadth = (root / "proposal-depth-breadth.md").read_text(encoding="utf-8")
    for label in (
        "Proposal ID:", "Central thesis:", "Research-question tree:", "Necessary subquestions:",
        "Contribution stack:", "Depth target:", "Depth chain:", "Competing explanations:",
        "Decisive discriminator:", "Breadth floor:", "Confirmatory core:", "Boundary axes:",
        "External-validity minimum:", "Breadth ceiling:", "Out of scope:", "Evidence package:",
        "Expansion triggers:", "Stop-expansion rule:",
    ):
        if not re.search(rf"(?im)^\s*-?\s*{re.escape(label)}\s*\S.*$", depth_breadth):
            errors.append(f"proposal-depth-breadth.md missing field: {label}")
    if markdown_field(depth_breadth, "Proposal ID:") != current_proposal_id:
        errors.append("proposal-depth-breadth.md Proposal ID does not match proposal.md")
    if not re.search(r"(?im)^\s*-?\s*Depth gate:\s*pass\s*$", depth_breadth):
        errors.append("proposal-depth-breadth.md requires `Depth gate: pass`")
    if not re.search(r"(?im)^\s*-?\s*Breadth gate:\s*pass\s*$", depth_breadth):
        errors.append("proposal-depth-breadth.md requires `Breadth gate: pass`")
    proposal = proposal_text
    for label in (
        "Topic:", "Proposal ID:", "Search cutoff:", "Proposal decision:", "Novelty status:",
        "Empirical status:", "Execution readiness:", "Paper sufficiency:", "Depth gate:", "Breadth gate:",
        "Knowledge question (Q):", "Knowledge claim (K):", "Mechanism (M):",
        "Decisive test (D):", "Scientific consequence (C):", "Constructs:", "Assumptions:",
        "Mechanism:", "Competing explanations:", "Predictions:", "Falsifiers:",
        "Central thesis:", "Research-question tree:", "Contribution stack:",
        "Confirmatory core:", "Boundary program:", "External-validity minimum:", "Expansion stop rule:",
        "Positive outcome:", "Null outcome:", "Mixed outcome:", "Inconclusive outcome:",
    ):
        if not re.search(rf"(?im)^\s*-?\s*{re.escape(label)}\s*\S.*$", proposal):
            errors.append(f"proposal.md missing field: {label}")
    scope = (root / "scope.md").read_text(encoding="utf-8")
    if re.search(r"(?im)^\s*-?\s*Theory mode:\s*formal\s*$", scope):
        for label in ("Formal statement:", "Proof obligations:", "Proof sketch:", "Counterexample search:", "Empirical corollaries:"):
            if not re.search(rf"(?im)^\s*-?\s*{re.escape(label)}\s*\S.*$", proposal):
                errors.append(f"formal proposal missing theoretical precheck field: {label}")
    if not re.search(r"(?im)^-?\s*Proposal decision:\s*pass\s*$", proposal):
        errors.append("proposal.md requires `Proposal decision: pass` before theory-building")
    if not re.search(r"(?im)^-?\s*Novelty status:\s*audited\s*$", proposal):
        errors.append("proposal.md requires `Novelty status: audited` before theory-building")
    if not re.search(r"(?im)^-?\s*Empirical status:\s*(not-run|pilot|tested)\s*$", proposal):
        errors.append("proposal.md has invalid `Empirical status`")
    if not re.search(r"(?im)^-?\s*Execution readiness:\s*(designed|deployable|blocked)\s*$", proposal):
        errors.append("proposal.md has invalid `Execution readiness`")
    if not re.search(r"(?im)^-?\s*Paper sufficiency:\s*proposal-ready\s*$", proposal):
        errors.append("proposal.md requires `Paper sufficiency: proposal-ready` before theory-building")
    if not re.search(r"(?im)^-?\s*Depth gate:\s*pass\s*$", proposal):
        errors.append("proposal.md requires `Depth gate: pass` before theory-building")
    if not re.search(r"(?im)^-?\s*Breadth gate:\s*pass\s*$", proposal):
        errors.append("proposal.md requires `Breadth gate: pass` before theory-building")
    audit = (root / "proposal-audit.md").read_text(encoding="utf-8")
    for label in ("Search cutoff:", "Databases:", "Query families:", "Uncovered scope:", "Novelty status:", "Empirical dependencies:"):
        if not re.search(rf"(?im)^\s*-?\s*{re.escape(label)}\s*\S.*$", audit):
            errors.append(f"proposal-audit.md missing field: {label}")
    if not re.search(r"(?im)^\s*-?\s*Proposal gate:\s*pass\s*$", audit):
        errors.append("proposal-audit.md requires `Proposal gate: pass`")
    novelty_review = (root / "novelty-review.md").read_text(encoding="utf-8")
    for label in ("Reviewer role:", "Reviewer model:", "Reviewer context isolation:", "Independent search:", "Reviewer stance:", "Equivalent-work criterion:", "Adversarial findings:", "Claim withdrawals:", "Unresolved threats:", "Independence statement:"):
        if not re.search(rf"(?im)^\s*{re.escape(label)}\s*\S.*$", novelty_review):
            errors.append(f"novelty-review.md missing non-empty field: {label}")
    if not re.search(r"(?im)^Decision:\s*pass\s*$", novelty_review):
        errors.append("novelty-review.md requires `Decision: pass`")
    if not re.search(r"(?im)^Independent search:\s*yes\s*$", novelty_review):
        errors.append("novelty-review.md requires `Independent search: yes`")
    return errors


def theory_errors(root: Path) -> list[str]:
    errors: list[str] = []
    required_files = ("theory.md", "theory/claims.jsonl", "theory/predictions.jsonl", "theory-audit.md")
    for relative in required_files:
        path = root / relative
        if not path.is_file() or path.stat().st_size == 0:
            errors.append(f"missing or empty: {relative}")
    if errors:
        return errors
    theory = (root / "theory.md").read_text(encoding="utf-8")
    for label in ("Proposal ID:", "Theory version:", "Constructs:", "Assumptions:", "Mechanism:", "Competing explanations:", "Predictions:", "Falsifiers:", "Experiment mapping:"):
        if not re.search(rf"(?im)^\s*-?\s*{re.escape(label)}\s*\S.*$", theory):
            errors.append(f"theory.md missing non-empty field: {label}")
    if not re.search(r"(?im)^\s*-?\s*Theory gate:\s*pass\s*$", theory):
        errors.append("theory.md requires `Theory gate: pass`")
    mode_match = re.search(r"(?im)^\s*-?\s*Theory mode:\s*(formal|empirical-system)\s*$", theory)
    if not mode_match:
        errors.append("theory.md requires `Theory mode: formal|empirical-system`")
    elif mode_match.group(1).lower() == "formal":
        proof_files = (
            "theory/formalization.md", "theory/proofs.md",
            "theory/proof-audit.md", "theory/counterexamples.jsonl",
        )
        for relative in proof_files:
            path = root / relative
            if not path.is_file() or path.stat().st_size == 0:
                errors.append(f"missing or empty formal-theory artifact: {relative}")
        proof_audit_path = root / "theory/proof-audit.md"
        if proof_audit_path.is_file():
            proof_audit = proof_audit_path.read_text(encoding="utf-8")
            if not re.search(r"(?im)^Proof gate:\s*pass\s*$", proof_audit):
                errors.append("theory/proof-audit.md requires `Proof gate: pass`")
            for label in ("Reviewer role:", "Reviewer model:", "Verification level:", "Independent reconstruction:", "Independence statement:", "Unresolved proof issues:"):
                if not re.search(rf"(?im)^\s*{re.escape(label)}\s*\S.*$", proof_audit):
                    errors.append(f"theory/proof-audit.md missing non-empty field: {label}")
            if not re.search(r"(?im)^Independent reconstruction:\s*yes\s*$", proof_audit):
                errors.append("theory/proof-audit.md requires `Independent reconstruction: yes`")
    try:
        claims = read_jsonl(root / "theory/claims.jsonl")
        predictions = read_jsonl(root / "theory/predictions.jsonl")
    except (json.JSONDecodeError, OSError) as error:
        return errors + [f"invalid theory registry: {error}"]
    if not claims:
        errors.append("theory/claims.jsonl contains no hypotheses")
    if not predictions:
        errors.append("theory/predictions.jsonl contains no predictions")
    hypothesis_ids: set[str] = set()
    claim_ids: set[str] = set()
    for index, item in enumerate(claims, start=1):
        required = {"hypothesis_id", "claim_ids", "constructs", "assumptions", "mechanism", "competing_explanations"}
        missing = required - set(item)
        if missing:
            errors.append(f"theory claim row {index} missing fields: {', '.join(sorted(missing))}")
            continue
        hypothesis_id = str(item["hypothesis_id"])
        if not re.fullmatch(r"H\d+", hypothesis_id) or hypothesis_id in hypothesis_ids:
            errors.append(f"invalid or duplicate hypothesis_id: {hypothesis_id}")
        hypothesis_ids.add(hypothesis_id)
        row_claims = item["claim_ids"] if isinstance(item["claim_ids"], list) else []
        if not row_claims or any(not re.fullmatch(r"C\d+", str(value)) for value in row_claims):
            errors.append(f"hypothesis {hypothesis_id} has invalid claim_ids")
        claim_ids.update(str(value) for value in row_claims)
        rivals = item["competing_explanations"] if isinstance(item["competing_explanations"], list) else []
        if not rivals or any(not str(value).strip() for value in rivals):
            errors.append(f"hypothesis {hypothesis_id} lacks a substantive competing explanation")
        for field in ("constructs", "assumptions", "mechanism"):
            if not item[field]:
                errors.append(f"hypothesis {hypothesis_id} has empty {field}")
    prediction_ids: set[str] = set()
    covered_hypotheses: set[str] = set()
    for index, item in enumerate(predictions, start=1):
        required = {"prediction_id", "hypothesis_id", "claim_ids", "observable", "expected_pattern", "rival_pattern", "scope", "falsifier", "experiment_mapping"}
        missing = required - set(item)
        if missing:
            errors.append(f"theory prediction row {index} missing fields: {', '.join(sorted(missing))}")
            continue
        prediction_id = str(item["prediction_id"])
        if not re.fullmatch(r"P\d+", prediction_id) or prediction_id in prediction_ids:
            errors.append(f"invalid or duplicate prediction_id: {prediction_id}")
        prediction_ids.add(prediction_id)
        hypothesis_id = str(item["hypothesis_id"])
        if hypothesis_id not in hypothesis_ids:
            errors.append(f"prediction {prediction_id} references unknown hypothesis: {hypothesis_id}")
        covered_hypotheses.add(hypothesis_id)
        if str(item["expected_pattern"]).strip().lower() == str(item["rival_pattern"]).strip().lower():
            errors.append(f"prediction {prediction_id} does not distinguish the rival explanation")
        for field in ("observable", "expected_pattern", "rival_pattern", "scope", "falsifier", "experiment_mapping"):
            if not str(item[field]).strip():
                errors.append(f"prediction {prediction_id} has empty {field}")
        row_claims = item["claim_ids"] if isinstance(item["claim_ids"], list) else []
        if not row_claims or any(str(value) not in claim_ids for value in row_claims):
            errors.append(f"prediction {prediction_id} has unknown or empty claim_ids")
    uncovered = hypothesis_ids - covered_hypotheses
    if uncovered:
        errors.append("hypotheses without predictions: " + ", ".join(sorted(uncovered)))
    audit = (root / "theory-audit.md").read_text(encoding="utf-8")
    if not re.search(r"(?im)^Theory gate:\s*pass\s*$", audit):
        errors.append("theory-audit.md requires `Theory gate: pass`")
    for label in ("Reviewer role:", "Reviewer stance:", "Unresolved threats:", "Independence statement:"):
        if not re.search(rf"(?im)^\s*{re.escape(label)}\s*\S.*$", audit):
            errors.append(f"theory-audit.md missing non-empty field: {label}")
    public_proposal = root.parent / "outputs" / "02-验证后Proposal.md"
    if not public_proposal.is_file() or public_proposal.stat().st_size == 0:
        errors.append("missing or empty user deliverable: outputs/02-验证后Proposal.md")
    else:
        public_text = public_proposal.read_text(encoding="utf-8")
        for label in ("新颖性审计: pass", "理论可行性审计: pass"):
            if not re.search(rf"(?im)^\s*-?\s*{re.escape(label)}\s*$", public_text):
                errors.append(f"outputs/02-验证后Proposal.md missing status: {label}")
    return errors


def scope_errors(root: Path) -> list[str]:
    path = root / "scope.md"
    if not path.is_file() or path.stat().st_size == 0:
        return ["missing or empty: scope.md"]
    text = path.read_text(encoding="utf-8")
    labels = (
        "Topic:", "Research question:", "Research type:", "Theory mode:", "Knowledge contribution:",
        "Unit of analysis:", "Intervention or comparison:", "Primary outcome:",
        "Population / system scope:", "In scope:", "Out of scope:",
        "Falsification condition:", "Data constraints:", "Model constraints:",
        "Compute and time constraints:", "Ethics and permissions:", "Deliverables:",
        "Open decisions:", "Scope version:",
    )
    return [f"scope.md missing non-empty field: {label}" for label in labels if not re.search(rf"(?im)^\s*-?\s*{re.escape(label)}\s*\S.*$", text)]


def protocol_errors(root: Path) -> list[str]:
    errors: list[str] = []
    required_files = ("experiments/protocol.md", "experiments/design.json", "experiments/analysis-plan.md", "experiments/protocol-audit.md", "theory/predictions.jsonl", "theory-experiment-iterations.jsonl")
    for relative in required_files:
        path = root / relative
        if not path.is_file() or path.stat().st_size == 0:
            errors.append(f"missing or empty: {relative}")
    experiment_output = root.parent / "outputs" / "03-理论分析与实验探究.md"
    if not experiment_output.is_file() or experiment_output.stat().st_size == 0:
        errors.append("missing or empty user deliverable: outputs/03-理论分析与实验探究.md")
    else:
        experiment_text = experiment_output.read_text(encoding="utf-8")
        for heading in ("理论构念与适用域", "机制推导与竞争解释", "可证伪预测", "预测—实验映射", "数据与研究材料", "具体实验方案", "指标与判定规则", "统计计划", "硬件资源要求", "人工部署与软件环境", "时间与运行量估算", "执行顺序与门禁"):
            if not re.search(rf"(?im)^##\s+.*{re.escape(heading)}.*$", experiment_text):
                errors.append(f"outputs/03-理论分析与实验探究.md missing section: {heading}")

    if errors:
        return errors
    try:
        iterations = read_jsonl(root / "theory-experiment-iterations.jsonl")
    except (json.JSONDecodeError, OSError) as error:
        return errors + [f"invalid theory-experiment iteration registry: {error}"]
    required_iteration_fields = {
        "iteration_id", "round", "cycle_type", "question", "inputs", "finding", "decision",
        "theory_review", "rival_review", "identification_review", "experiment_review",
        "resource_review", "paper_review",
        "theory_changed", "protocol_changed", "change_summary", "unresolved", "next_action",
    }
    seen_rounds: list[int] = []
    for index, item in enumerate(iterations, start=1):
        missing = required_iteration_fields - set(item)
        if missing:
            errors.append(f"theory-experiment iteration row {index} missing fields: {', '.join(sorted(missing))}")
            continue
        if item.get("cycle_type") != "full-theory-experiment-cycle":
            errors.append(f"theory-experiment iteration row {index} must be a full-theory-experiment-cycle")
        if not isinstance(item.get("round"), int):
            errors.append(f"theory-experiment iteration row {index} round must be an integer")
        else:
            seen_rounds.append(item["round"])
        if not isinstance(item["theory_changed"], bool) or not isinstance(item["protocol_changed"], bool):
            errors.append(f"theory-experiment iteration row {index} change flags must be boolean")
        if not isinstance(item["inputs"], list) or not item["inputs"]:
            errors.append(f"theory-experiment iteration row {index} requires evidence inputs")
        if not isinstance(item["unresolved"], list):
            errors.append(f"theory-experiment iteration row {index} unresolved must be a list")
        for field in ("theory_review", "rival_review", "identification_review", "experiment_review", "resource_review", "paper_review"):
            if not str(item.get(field, "")).strip():
                errors.append(f"theory-experiment iteration row {index} has empty {field}")
    if len(iterations) < 5 or seen_rounds != list(range(1, len(iterations) + 1)):
        errors.append("theory-experiment work requires at least five consecutive full rounds starting at 1")
    if iterations and (iterations[-1].get("theory_changed") is not False or iterations[-1].get("protocol_changed") is not False):
        errors.append("theory-experiment work has not converged: the final full round still changes theory or protocol")
    protocol = (root / "experiments/protocol.md").read_text(encoding="utf-8")
    labels = (
        "Protocol ID:", "Protocol version:", "Proposal ID:", "Theory version:",
        "Claims:", "Hypotheses:", "Predictions:", "Experimental units:",
        "Independent variables:", "Dependent variables:", "Controls:", "Confounders:",
        "Baselines:", "Data splits:", "Leakage checks:", "Metrics:", "Randomness:",
        "Analysis:", "Failure criteria:", "Stopping rules:", "Resource budget:",
        "Exploratory analyses:", "Deviations policy:",
    )
    for label in labels:
        if not re.search(rf"(?im)^\s*-?\s*{re.escape(label)}\s*\S.*$", protocol):
            errors.append(f"experiments/protocol.md missing non-empty field: {label}")
    if not re.search(r"(?im)^\s*-?\s*Protocol gate:\s*pass\s*$", protocol):
        errors.append("experiments/protocol.md requires `Protocol gate: pass`")
    try:
        design = read_json(root / "experiments/design.json")
    except (json.JSONDecodeError, OSError) as error:
        return errors + [f"invalid experiments/design.json: {error}"]
    if design.get("research_type") != read_json(root / "research.json").get("research_type"):
        errors.append("design research_type differs from project scope")
    permissions = design.get("required_permissions")
    if not isinstance(permissions, list) or any(p not in PERMISSIONS for p in permissions):
        errors.append("design.json requires an explicit required_permissions list")
    materials = design.get("research_materials")
    if not isinstance(materials, dict) or materials.get("mode") not in {"external", "generated", "none"}:
        errors.append("design.json requires research_materials with mode external|generated|none")
    elif materials["mode"] == "external":
        sources = materials.get("sources")
        if not isinstance(sources, list) or not sources or any(
            not isinstance(item, dict) or not re.match(r"https?://", str(item.get("url", "")))
            or not str(item.get("version", "")).strip() or not str(item.get("selection", "")).strip()
            for item in sources
        ):
            errors.append("external research materials require source URL, fixed version and selection")
    elif not str(materials.get("rationale", "")).strip():
        errors.append("generated/no-data research requires an explicit materials rationale")
    design_fields = (
        "protocol_id", "protocol_version", "research_type", "claims", "hypotheses", "predictions",
        "experimental_units", "independent_variables", "dependent_variables", "controls", "baselines",
        "data_splits", "leakage_checks", "metrics", "randomness", "resource_budget", "stopping_rules",
    )
    for field in design_fields:
        if field not in design or design[field] in (None, "", [], {}):
            errors.append(f"experiments/design.json missing or empty field: {field}")
    protocol_id_match = re.search(r"(?im)^\s*-?\s*Protocol ID:\s*(\S.+)$", protocol)
    protocol_version_match = re.search(r"(?im)^\s*-?\s*Protocol version:\s*(\d+)\s*$", protocol)
    if protocol_id_match and str(design.get("protocol_id")) != protocol_id_match.group(1).strip():
        errors.append("protocol ID differs between protocol.md and design.json")
    if protocol_version_match and str(design.get("protocol_version")) != protocol_version_match.group(1):
        errors.append("protocol version differs between protocol.md and design.json")
    theory_predictions = {str(item.get("prediction_id")) for item in read_jsonl(root / "theory/predictions.jsonl")}
    mapped_predictions = {str(value) for value in design.get("predictions", [])} if isinstance(design.get("predictions"), list) else set()
    missing_predictions = theory_predictions - mapped_predictions
    if missing_predictions:
        errors.append("protocol does not cover theory predictions: " + ", ".join(sorted(missing_predictions)))
    analysis = (root / "experiments/analysis-plan.md").read_text(encoding="utf-8")
    for label in ("Primary estimand:", "Primary metrics:", "Aggregation unit:", "Uncertainty:", "Randomness:", "Multiplicity:", "Failed runs:", "Missing data:", "Exclusions:", "Decision rule:", "Exploratory boundary:"):
        if not re.search(rf"(?im)^\s*-?\s*{re.escape(label)}\s*\S.*$", analysis):
            errors.append(f"experiments/analysis-plan.md missing non-empty field: {label}")
    audit = (root / "experiments/protocol-audit.md").read_text(encoding="utf-8")
    if not re.search(r"(?im)^Protocol gate:\s*pass\s*$", audit):
        errors.append("experiments/protocol-audit.md requires `Protocol gate: pass`")
    for label in ("Protocol ID:", "Protocol version:", "Reviewer role:", "Reviewer stance:", "Unresolved threats:", "Independence statement:", "Execution authorization:"):
        if not re.search(rf"(?im)^\s*{re.escape(label)}\s*\S.*$", audit):
            errors.append(f"experiments/protocol-audit.md missing non-empty field: {label}")
    audit_id_match = re.search(r"(?im)^\s*Protocol ID:\s*(\S.+)$", audit)
    audit_version_match = re.search(r"(?im)^\s*Protocol version:\s*(\d+)\s*$", audit)
    if protocol_id_match and audit_id_match and audit_id_match.group(1).strip() != protocol_id_match.group(1).strip():
        errors.append("protocol ID differs between protocol.md and protocol-audit.md")
    if protocol_version_match and audit_version_match and audit_version_match.group(1) != protocol_version_match.group(1):
        errors.append("protocol version differs between protocol.md and protocol-audit.md")
    experiment_output = root.parent / "outputs" / "03-理论分析与实验探究.md"
    if experiment_output.is_file():
        experiment_text = experiment_output.read_text(encoding="utf-8")
        if not re.search(r"(?im)^\s*-?\s*实验协议审计:\s*pass\s*$", experiment_text):
            errors.append("outputs/03-理论分析与实验探究.md requires `实验协议审计: pass`")
    return errors


def stage_errors(root: Path, stage: str, *, entering: bool = False) -> list[str]:
    """Single semantic gate path for CLI transitions and read-only audits."""
    if stage in {"blocked", "terminated"}:
        if entering:
            return []
        previous = read_json(root / "state.json").get("resume_stage")
        return stage_errors(root, previous) if previous in STAGES and previous not in {"blocked", "terminated"} else []
    if stage not in STAGES:
        return [f"invalid research stage: {stage}"]
    errors: list[str] = []
    index = STAGES.index(stage)
    checks = [lambda root: require_gates(root, stage)]
    if index >= STAGES.index("literature-mapping"):
        checks.append(scope_errors)
    if index >= STAGES.index("theory-building"):
        checks.append(proposal_errors)
    if index >= STAGES.index("experiment-protocol"):
        checks.append(theory_errors)
    if index >= STAGES.index("pilot"):
        checks.extend([protocol_errors, verify_protocol])
        if entering and stage in RUN_STAGES:
            checks.append(verify_execution_authorization)
    if index >= STAGES.index("main-experiment"):
        checks.append(require_pilot_evidence)
    if index >= STAGES.index("robustness-analysis"):
        checks.append(require_main_evidence)
    if stage == "complete":
        checks.append(completion_errors)
    if entering and stage == "pilot":
        checks.append(lambda root: novelty_refresh_errors(root, "pre-experiment"))
    for check in checks:
        try:
            result = check(root)
            if isinstance(result, list):
                errors.extend(result)
        except (SystemExit, OSError, ValueError, KeyError, TypeError, AttributeError) as error:
            errors.append(f"{check.__name__}: {error}")
    return errors
