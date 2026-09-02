#!/usr/bin/env python3
"""Deterministic control plane for long-running research projects."""

from __future__ import annotations

import argparse
import contextlib
import hashlib
import json
import os
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


LAYOUT = {
    "research.json": "control/project.json",
    "state.json": "control/state.json",
    "state.md": "control/state.md",
    "events.jsonl": "control/events.jsonl",
    "decisions.jsonl": "control/decisions.jsonl",
    ".research.lock": "control/.research.lock",
    "scope.md": "review/scope.md",
    "search-log.md": "review/search-log.md",
    "literature.md": "review/literature.md",
    "evidence.md": "review/evidence.md",
    "initial-design.md": "proposal/initial-design.md",
    "research-directions.md": "proposal/directions.md",
    "selected-direction.md": "proposal/selected-direction.md",
    "proposal.md": "proposal/proposal.md",
    "proposal-audit.md": "proposal/audit.md",
    "proposal-candidates.jsonl": "proposal/candidates.jsonl",
    "proposal-claims.jsonl": "proposal/claims.jsonl",
    "proposal-rivals.jsonl": "proposal/rivals.jsonl",
    "proposal-threats.jsonl": "proposal/threats.jsonl",
    "proposal-iterations.jsonl": "proposal/iterations.jsonl",
    "proposal-v1-rejected.md": "proposal/archive/v1-rejected.md",
    "novelty-review.md": "proposal/novelty.md",
    "theory.md": "theory/theory.md",
    "theory-audit.md": "theory/audit.md",
    "theory-experiment-iterations.jsonl": "theory/iterations.jsonl",
}


def layout_path(relative: str) -> str:
    normalized = relative.replace("\\", "/")
    if normalized in LAYOUT:
        return LAYOUT[normalized]
    directory_layout = {"literature": "review/literature", "papers": "review/papers", "sources": "review/sources"}
    if normalized in directory_layout:
        return directory_layout[normalized]
    for prefix, destination in (("literature/", "review/literature/"), ("papers/", "review/papers/"), ("sources/", "review/sources/")):
        if normalized.startswith(prefix):
            return destination + normalized[len(prefix):]
    return normalized


class ResearchRoot:
    """Path-like project root that centralizes the internal artifact layout."""

    def __init__(self, base: Path):
        self.base = base

    def __truediv__(self, relative: str | os.PathLike[str]) -> Path:
        return self.base / layout_path(os.fspath(relative))

    def __fspath__(self) -> str:
        return os.fspath(self.base)

    def __str__(self) -> str:
        return str(self.base)

    @property
    def parent(self) -> Path:
        return self.base.parent

    def mkdir(self, *args: Any, **kwargs: Any) -> None:
        self.base.mkdir(*args, **kwargs)


STAGES = [
    "initialized", "problem-framing", "literature-mapping", "direction-audit",
    "theory-building", "experiment-protocol", "pilot", "main-experiment",
    "robustness-analysis", "evidence-audit", "artifact-building",
    "artifact-validation", "report-writing", "report-review",
    "complete", "blocked", "terminated",
]

TRANSITIONS = {
    "initialized": {"problem-framing", "blocked", "terminated"},
    "problem-framing": {"literature-mapping", "blocked", "terminated"},
    "literature-mapping": {"direction-audit", "problem-framing", "blocked", "terminated"},
    "direction-audit": {"theory-building", "literature-mapping", "blocked", "terminated"},
    "theory-building": {"experiment-protocol", "direction-audit", "problem-framing", "blocked", "terminated"},
    "experiment-protocol": {"pilot", "theory-building", "blocked", "terminated"},
    "pilot": {"main-experiment", "experiment-protocol", "theory-building", "blocked", "terminated"},
    "main-experiment": {"robustness-analysis", "experiment-protocol", "theory-building", "blocked", "terminated"},
    "robustness-analysis": {"evidence-audit", "main-experiment", "experiment-protocol", "blocked", "terminated"},
    "evidence-audit": {"artifact-building", "robustness-analysis", "main-experiment", "direction-audit", "blocked", "terminated"},
    "artifact-building": {"artifact-validation", "main-experiment", "blocked", "terminated"},
    "artifact-validation": {"report-writing", "artifact-building", "main-experiment", "blocked", "terminated"},
    "report-writing": {"report-review", "evidence-audit", "blocked", "terminated"},
    "report-review": {"complete", "report-writing", "evidence-audit", "blocked", "terminated"},
    "blocked": set(STAGES[:-3]) | {"terminated"},
    "complete": set(),
    "terminated": set(),
}

GATES = {
    "literature-mapping": ["scope.md"],
    "direction-audit": ["search-log.md", "literature.md", "literature/corpus.jsonl", "literature/coverage.md", "evidence.md"],
    "theory-building": ["research-directions.md", "selected-direction.md", "proposal.md", "proposal-audit.md", "literature/nearest-neighbors.md"],
    "experiment-protocol": ["theory.md", "theory/claims.jsonl", "theory/predictions.jsonl", "theory-audit.md"],
    "pilot": ["experiments/protocol.md", "experiments/protocol.lock.json", "experiments/design.json", "experiments/analysis-plan.md", "experiments/protocol-audit.md"],
    "main-experiment": ["experiments/pilot.md"],
    "robustness-analysis": ["experiments/results.md", "runs/registry.jsonl"],
    "evidence-audit": ["analysis.md", "evidence.md"],
    "artifact-building": ["analysis.md", "evidence.md"],
    "artifact-validation": ["artifact/README.md"],
    "report-writing": ["artifact/README.md"],
    "report-review": ["report.md"],
}

PERMISSIONS = ("external_compute", "restricted_data", "human_subjects", "external_publish")
EXPERIMENT_STAGES = {"experiment-protocol", "pilot", "main-experiment", "robustness-analysis"}
RUN_STAGES = {"pilot", "main-experiment", "robustness-analysis"}


@contextlib.contextmanager
def project_lock(root: Path):
    """Serialize mutations within one project; the executor must use the same lock."""
    path = root / ".research.lock"
    path.parent.mkdir(parents=True, exist_ok=True)
    stream = path.open("a+b")
    try:
        if os.name == "nt":
            import msvcrt
            stream.seek(0)
            msvcrt.locking(stream.fileno(), msvcrt.LK_LOCK, 1)
        else:
            import fcntl
            fcntl.flock(stream.fileno(), fcntl.LOCK_EX)
        yield
    finally:
        if os.name == "nt":
            stream.seek(0)
            msvcrt.locking(stream.fileno(), msvcrt.LK_UNLCK, 1)
        else:
            import fcntl
            fcntl.flock(stream.fileno(), fcntl.LOCK_UN)
        stream.close()


def now() -> str:
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")


def read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json_atomic(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".new")
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    os.replace(temporary, path)


def append_jsonl(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8", newline="\n") as stream:
        stream.write(json.dumps(value, ensure_ascii=False, separators=(",", ":")) + "\n")
        stream.flush()
        os.fsync(stream.fileno())


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def project(path: str) -> ResearchRoot:
    outer = Path(path).resolve()
    for base in (outer / ".research", outer):
        root = ResearchRoot(base)
        if (root / "research.json").is_file() and (root / "state.json").is_file():
            return root
    raise SystemExit(f"not an initialized research project: {outer}")


def load_events(root: Path) -> list[dict[str, Any]]:
    path = root / "events.jsonl"
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def event_hash(record: dict[str, Any]) -> str:
    unsigned = {key: value for key, value in record.items() if key != "hash"}
    payload = json.dumps(unsigned, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def emit(root: Path, kind: str, actor: str, payload: dict[str, Any]) -> dict[str, Any]:
    events = load_events(root)
    record = {
        "seq": len(events) + 1,
        "time": now(),
        "type": kind,
        "actor": actor,
        "payload": payload,
        "prev_hash": events[-1]["hash"] if events else None,
    }
    record["hash"] = event_hash(record)
    append_jsonl(root / "events.jsonl", record)
    return record


def verify_events(root: Path) -> None:
    previous = None
    for index, record in enumerate(load_events(root), start=1):
        if record.get("seq") != index or record.get("prev_hash") != previous or record.get("hash") != event_hash(record):
            raise SystemExit(f"event log integrity failure at sequence {index}")
        previous = record["hash"]


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


def nonnegative(name: str, value: float) -> None:
    if value < 0:
        raise SystemExit(f"{name} must be non-negative")


def require_nonempty(root: Path, relative: str) -> Path:
    path = (root / relative).resolve()
    try:
        path.relative_to(root)
    except ValueError:
        raise SystemExit(f"path escapes research project: {relative}")
    if not path.is_file() or path.stat().st_size == 0:
        raise SystemExit(f"missing or empty artifact: {relative}")
    return path


def completion_errors(root: Path) -> list[str]:
    required = [
        "scope.md", "search-log.md", "literature.md", "literature/corpus.jsonl",
        "literature/coverage.md", "literature/nearest-neighbors.md",
        "research-directions.md", "selected-direction.md", "proposal.md",
        "proposal-audit.md", "theory.md", "theory/claims.jsonl",
        "theory/predictions.jsonl", "theory-audit.md", "experiments/protocol.md",
        "experiments/design.json", "experiments/analysis-plan.md", "experiments/protocol-audit.md",
        "experiments/protocol.lock.json", "experiments/pilot.md",
        "experiments/registry.jsonl", "runs/registry.jsonl", "runs/outcomes.jsonl",
        "experiments/results.md", "analysis.md", "evidence.md",
        "artifact/README.md", "report.md",
    ]
    errors = [item for item in required if not (root / item).is_file() or (root / item).stat().st_size == 0]
    if errors:
        return [f"missing or empty: {item}" for item in errors]
    try:
        verify_protocol(root)
    except SystemExit as error:
        errors.append(str(error))
    outcomes = {item.get("run_id"): item for item in read_jsonl(root / "runs/outcomes.jsonl")}
    for run in read_jsonl(root / "runs/registry.jsonl"):
        if run.get("run_id") not in outcomes:
            errors.append(f"run has no terminal outcome: {run.get('run_id')}")
    if not re.search(r"(?im)^Outcome:\s*(supported|refuted|mixed|inconclusive)\s*$", (root / "experiments/results.md").read_text(encoding="utf-8")):
        errors.append("experiments/results.md lacks a valid Outcome")
    if not re.search(r"\bC\d+\b", (root / "evidence.md").read_text(encoding="utf-8")):
        errors.append("evidence.md lacks stable claim IDs")
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
    if not 50 <= len(included) <= 100:
        errors.append(f"included corpus has {len(included)} papers; formal proposals require 50–100")
    core = [item for item in included if item["role"] == "core" and item["access_level"] == "full-text"]
    if not 20 <= len(core) <= 30:
        errors.append(f"{len(core)} core papers have full-text access; formal proposals require 20–30")
    for item in core:
        card = root / "papers" / f"{item['source_id']}.md"
        if not card.is_file() or card.stat().st_size == 0:
            errors.append(f"core paper lacks a non-empty full-text analysis card: {item['source_id']}")
    required_files = (
        "search-log.md", "literature/coverage.md", "literature/nearest-neighbors.md",
        "proposal-candidates.jsonl", "proposal-claims.jsonl", "proposal-rivals.jsonl",
        "proposal-threats.jsonl", "proposal-iterations.jsonl",
        "proposal.md", "proposal-audit.md", "novelty-review.md",
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
        if not (20 <= motivation_count <= 30 and motivation_count == method_count == summary_count):
            errors.append("outputs/01-文献调研总结.md must contain 20–30 matched motivation/method/summary full-text analyses")
        if not re.search(r"(?im)^##\s+.*\d+\s*篇论文形成的整体认识.*$", review):
            errors.append("outputs/01-文献调研总结.md missing corpus-level synthesis section")
        if not re.search(r"(?im)^##\s+.*仍然存在的问题.*$", review):
            errors.append("outputs/01-文献调研总结.md missing section: 仍然存在的问题")
    public_proposal = public / "02-验证后Proposal.md"
    if public_proposal.is_file() and public_proposal.stat().st_size > 0:
        text = public_proposal.read_text(encoding="utf-8")
        for heading in ("研究背景与问题重要性", "精确研究问题", "理论机制", "可证伪假设", "核心构念与测量", "最近邻与新颖性边界", "风险、失败结果与停止条件"):
            if not re.search(rf"(?im)^##\s+.*{re.escape(heading)}.*$", text):
                errors.append(f"outputs/02-验证后Proposal.md missing section: {heading}")
    if errors:
        return errors
    try:
        candidates = read_jsonl(root / "proposal-candidates.jsonl")
        claims = read_jsonl(root / "proposal-claims.jsonl")
        rivals = read_jsonl(root / "proposal-rivals.jsonl")
        threats = read_jsonl(root / "proposal-threats.jsonl")
        iterations = read_jsonl(root / "proposal-iterations.jsonl")
    except (json.JSONDecodeError, OSError) as error:
        return [f"invalid proposal iteration registry: {error}"]
    if len(candidates) < 2:
        errors.append("proposal-candidates.jsonl requires competing directions, not a single preselected idea")
    if not claims:
        errors.append("proposal-claims.jsonl contains no atomic contribution claims")
    if not rivals:
        errors.append("proposal-rivals.jsonl contains no competing mechanism")
    fatal_threats = [item for item in threats if item.get("severity") == "fatal" and item.get("status") != "resolved"]
    if fatal_threats:
        errors.append("proposal-threats.jsonl contains unresolved fatal threats")
    required_cycles = {
        "candidate-comparison", "novelty-collision", "mechanism-falsification",
        "protocol-feasibility", "adversarial-review",
    }
    seen_cycles: set[str] = set()
    iteration_fields = {
        "iteration_id", "proposal_id", "cycle_type", "question", "inputs", "finding",
        "decision", "proposal_changed", "change_summary", "unresolved", "next_action",
    }
    for index, item in enumerate(iterations, start=1):
        missing = iteration_fields - set(item)
        if missing:
            errors.append(f"proposal iteration row {index} missing fields: {', '.join(sorted(missing))}")
            continue
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
    missing_cycles = required_cycles - seen_cycles
    if missing_cycles:
        errors.append(f"proposal iteration record missing cycles: {', '.join(sorted(missing_cycles))}")
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
    proposal = (root / "proposal.md").read_text(encoding="utf-8")
    for label in ("Topic:", "Proposal ID:", "Search cutoff:", "Novelty status:", "Constructs:", "Assumptions:", "Mechanism:", "Competing explanations:", "Predictions:", "Falsifiers:"):
        if not re.search(rf"(?im)^\s*-?\s*{re.escape(label)}\s*\S.*$", proposal):
            errors.append(f"proposal.md missing field: {label}")
    if not re.search(r"(?im)^-?\s*Novelty status:\s*audited\s*$", proposal):
        errors.append("proposal.md requires `Novelty status: audited` before theory-building")
    audit = (root / "proposal-audit.md").read_text(encoding="utf-8")
    for label in ("Search cutoff:", "Databases:", "Query families:", "Uncovered scope:", "Novelty status:"):
        if not re.search(rf"(?im)^\s*-?\s*{re.escape(label)}\s*\S.*$", audit):
            errors.append(f"proposal-audit.md missing field: {label}")
    novelty_review = (root / "novelty-review.md").read_text(encoding="utf-8")
    for label in ("Reviewer role:", "Reviewer stance:", "Equivalent-work criterion:", "Adversarial findings:", "Claim withdrawals:", "Unresolved threats:", "Independence statement:"):
        if not re.search(rf"(?im)^\s*{re.escape(label)}\s*\S.*$", novelty_review):
            errors.append(f"novelty-review.md missing non-empty field: {label}")
    if not re.search(r"(?im)^Decision:\s*pass\s*$", novelty_review):
        errors.append("novelty-review.md requires `Decision: pass`")
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
        "Topic:", "Research question:", "Research type:", "Knowledge contribution:",
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
        for heading in ("理论构念与适用域", "机制推导与竞争解释", "可证伪预测", "预测—实验映射", "数据集选择", "历史错误构造", "具体实验方案", "指标与判定规则", "统计计划", "硬件资源要求", "人工部署与软件环境", "时间与运行量估算", "执行顺序与门禁"):
            if not re.search(rf"(?im)^##\s+.*{re.escape(heading)}.*$", experiment_text):
                errors.append(f"outputs/03-理论分析与实验探究.md missing section: {heading}")
        if len(re.findall(r"https?://", experiment_text)) < 3:
            errors.append("outputs/03-理论分析与实验探究.md must link at least three official dataset sources")
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
    for label in ("Reviewer role:", "Reviewer stance:", "Unresolved threats:", "Independence statement:", "Execution authorization:"):
        if not re.search(rf"(?im)^\s*{re.escape(label)}\s*\S.*$", audit):
            errors.append(f"experiments/protocol-audit.md missing non-empty field: {label}")
    experiment_output = root.parent / "outputs" / "03-理论分析与实验探究.md"
    if experiment_output.is_file():
        experiment_text = experiment_output.read_text(encoding="utf-8")
        if not re.search(r"(?im)^\s*-?\s*实验协议审计:\s*pass\s*$", experiment_text):
            errors.append("outputs/03-理论分析与实验探究.md requires `实验协议审计: pass`")
    return errors


def command_init(args: argparse.Namespace) -> None:
    outer = Path(args.directory).resolve()
    root = ResearchRoot(outer / ".research")
    if (root / "research.json").exists() or (root / "state.json").exists() or (outer / "research.json").exists():
        raise SystemExit(f"research project already initialized: {outer}")
    root.mkdir(parents=True, exist_ok=True)
    for directory in ("control", "review", "proposal", "theory", "experiments"):
        (root.base / directory).mkdir(exist_ok=True)
    (outer / "outputs").mkdir(exist_ok=True)
    nonnegative("gpu-hours", args.gpu_hours)
    nonnegative("cost", args.cost)
    config = {
        "schema_version": 1,
        "topic": args.topic,
        "research_type": args.research_type,
        "created_at": now(),
        "budget": {"gpu_hours": args.gpu_hours, "cost": args.cost},
        "permissions": {name: False for name in PERMISSIONS},
    }
    state = {
        "schema_version": 1,
        "workflow_status": "in-progress",
        "research_stage": "initialized",
        "novelty_status": "not-assessed",
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


def command_audit_proposal(args: argparse.Namespace) -> None:
    root = project(args.directory)
    verify_events(root)
    errors = proposal_errors(root)
    if errors:
        raise SystemExit("proposal audit failed: " + "; ".join(errors))
    corpus = [item for item in read_jsonl(root / "literature/corpus.jsonl") if item.get("screening_status") == "included"]
    core = [item for item in corpus if item.get("role") == "core" and item.get("access_level") == "full-text"]
    print(json.dumps({"status": "pass", "included": len(corpus), "core_full_text": len(core)}, ensure_ascii=False))


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
    errors = scope_errors(root) + proposal_errors(root) + theory_errors(root) + protocol_errors(root)
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
    state = read_json(root / "state.json")
    current = state["research_stage"]
    if args.target not in TRANSITIONS.get(current, set()):
        raise SystemExit(f"invalid transition: {current} -> {args.target}")
    require_gates(root, args.target)
    if args.target == "literature-mapping":
        errors = scope_errors(root)
        if errors:
            raise SystemExit("scope audit failed: " + "; ".join(errors))
    if args.target == "theory-building":
        errors = proposal_errors(root)
        if errors:
            raise SystemExit("proposal audit failed: " + "; ".join(errors))
    if args.target == "experiment-protocol":
        errors = theory_errors(root)
        if errors:
            raise SystemExit("theory audit failed: " + "; ".join(errors))
    if args.target == "pilot":
        errors = protocol_errors(root)
        if errors:
            raise SystemExit("protocol audit failed: " + "; ".join(errors))
    if args.target == "complete":
        errors = completion_errors(root)
        if errors:
            raise SystemExit("completion audit failed: " + "; ".join(errors))
    previous_status = state["workflow_status"]
    state["research_stage"] = args.target
    terminal_status = {"blocked": "blocked", "complete": "complete", "terminated": "terminated"}
    state["workflow_status"] = terminal_status.get(args.target, "in-progress")
    if STAGES.index(args.target) < STAGES.index(current) and args.target not in {"blocked", "terminated"}:
        state["iteration"] += 1
    state["updated_at"] = now()
    emit(root, "stage-transition", args.actor, {"from": current, "to": args.target, "reason": args.reason, "evidence": args.evidence, "previous_status": previous_status})
    write_json_atomic(root / "state.json", state)


def command_decide(args: argparse.Namespace) -> None:
    root = project(args.directory)
    verify_events(root)
    record = {"time": now(), "actor": args.actor, "decision": args.decision, "reason": args.reason, "evidence": args.evidence, "alternatives": args.alternative}
    append_jsonl(root / "decisions.jsonl", record)
    emit(root, "decision-recorded", args.actor, {"decision": args.decision})


def command_freeze(args: argparse.Namespace) -> None:
    root = project(args.directory)
    verify_events(root)
    protocol = root / "experiments/protocol.md"
    if not protocol.is_file():
        raise SystemExit("missing experiments/protocol.md")
    digest = hashlib.sha256(protocol.read_bytes()).hexdigest()
    state = read_json(root / "state.json")
    require_stage(state, {"experiment-protocol", "pilot", "main-experiment", "robustness-analysis"}, "freeze-protocol")
    errors = protocol_errors(root)
    if errors:
        raise SystemExit("protocol audit failed: " + "; ".join(errors))
    declared = re.search(r"(?im)^\s*-?\s*Protocol version:\s*(\d+)\s*$", protocol.read_text(encoding="utf-8"))
    expected_version = int(state.get("protocol_version") or 0) + 1
    if not declared or int(declared.group(1)) != expected_version:
        raise SystemExit(f"protocol must declare the next version: {expected_version}")
    version = int(state.get("protocol_version") or 0) + 1
    lock = {"version": version, "sha256": digest, "frozen_at": now(), "actor": args.actor}
    archive = root / "experiments/protocols" / f"v{version:03d}.md"
    archive.parent.mkdir(parents=True, exist_ok=True)
    if archive.exists():
        raise SystemExit(f"protocol archive already exists: {archive}")
    archive.write_bytes(protocol.read_bytes())
    lock["archive"] = archive.relative_to(root).as_posix()
    lock["archive_sha256"] = hashlib.sha256(archive.read_bytes()).hexdigest()
    write_json_atomic(archive.with_suffix(".lock.json"), lock)
    write_json_atomic(root / "experiments/protocol.lock.json", lock)
    state["protocol_version"] = version
    state["updated_at"] = now()
    write_json_atomic(root / "state.json", state)
    emit(root, "protocol-frozen", args.actor, lock)
    print(json.dumps(lock, indent=2))


def verify_protocol(root: Path) -> dict[str, Any]:
    protocol = root / "experiments/protocol.md"
    lock_path = root / "experiments/protocol.lock.json"
    if not protocol.is_file() or not lock_path.is_file():
        raise SystemExit("freeze the protocol before registering experiments or runs")
    lock = read_json(lock_path)
    if hashlib.sha256(protocol.read_bytes()).hexdigest() != lock["sha256"]:
        raise SystemExit("protocol changed after freezing; freeze a new version before continuing")
    return lock


def permission_required(config: dict[str, Any], permission: str) -> None:
    if permission != "none" and not config["permissions"].get(permission, False):
        raise SystemExit(f"permission not authorized: {permission}")


def command_experiment(args: argparse.Namespace) -> None:
    root = project(args.directory)
    verify_events(root)
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
    config = read_json(root / "research.json")
    state = read_json(root / "state.json")
    require_stage(state, RUN_STAGES, "register-run")
    nonnegative("gpu-hours", args.gpu_hours)
    nonnegative("cost", args.cost)
    verify_protocol(root)
    if not any(item.get("experiment_id") == args.experiment for item in read_jsonl(root / "experiments/registry.jsonl")):
        raise SystemExit(f"unknown experiment ID: {args.experiment}")
    if any(item.get("run_id") == args.id for item in read_jsonl(root / "runs/registry.jsonl")):
        raise SystemExit(f"duplicate run ID: {args.id}")
    permission_required(config, args.permission)
    if state["usage"]["gpu_hours"] + args.gpu_hours > config["budget"]["gpu_hours"]:
        raise SystemExit("GPU-hour budget exceeded")
    if state["usage"]["cost"] + args.cost > config["budget"]["cost"]:
        raise SystemExit("cost budget exceeded")
    config_path = require_nonempty(root, args.config)
    record = {"run_id": args.id, "experiment_id": args.experiment, "time": now(), "actor": args.actor, "protocol_version": state["protocol_version"], "config": args.config, "config_sha256": hashlib.sha256(config_path.read_bytes()).hexdigest(), "code_revision": args.code_revision, "environment": args.environment, "seeds": args.seed, "reserved_gpu_hours": args.gpu_hours, "reserved_cost": args.cost, "status": "queued"}
    append_jsonl(root / "runs/registry.jsonl", record)
    state["usage"]["gpu_hours"] += args.gpu_hours
    state["usage"]["cost"] += args.cost
    state["updated_at"] = now()
    write_json_atomic(root / "state.json", state)
    emit(root, "run-registered", args.actor, {"run_id": args.id, "experiment_id": args.experiment})


def command_finish_run(args: argparse.Namespace) -> None:
    root = project(args.directory)
    verify_events(root)
    registrations = read_jsonl(root / "runs/registry.jsonl")
    matches = [item for item in registrations if item.get("run_id") == args.id]
    if len(matches) != 1:
        raise SystemExit(f"run ID must have exactly one registration: {args.id}")
    if any(item.get("run_id") == args.id for item in read_jsonl(root / "runs/outcomes.jsonl")):
        raise SystemExit(f"run already finished: {args.id}")
    registered = matches[0]
    nonnegative("gpu-hours", args.gpu_hours)
    nonnegative("cost", args.cost)
    if args.status == "succeeded" and not args.artifact:
        raise SystemExit("a succeeded run requires --artifact")
    artifact_sha256 = None
    if args.artifact:
        artifact_path = require_nonempty(root, args.artifact)
        artifact_sha256 = hashlib.sha256(artifact_path.read_bytes()).hexdigest()
    state = read_json(root / "state.json")
    state["usage"]["gpu_hours"] = max(0.0, state["usage"]["gpu_hours"] - registered["reserved_gpu_hours"] + args.gpu_hours)
    state["usage"]["cost"] = max(0.0, state["usage"]["cost"] - registered["reserved_cost"] + args.cost)
    state["updated_at"] = now()
    write_json_atomic(root / "state.json", state)
    config = read_json(root / "research.json")
    budget_exceeded = state["usage"]["gpu_hours"] > config["budget"]["gpu_hours"] or state["usage"]["cost"] > config["budget"]["cost"]
    outcome = {"run_id": args.id, "time": now(), "actor": args.actor, "status": args.status, "actual_gpu_hours": args.gpu_hours, "actual_cost": args.cost, "artifact": args.artifact, "artifact_sha256": artifact_sha256, "budget_exceeded": budget_exceeded, "reason": args.reason}
    append_jsonl(root / "runs/outcomes.jsonl", outcome)
    emit(root, "run-finished", args.actor, outcome)


def command_authorize(args: argparse.Namespace) -> None:
    root = project(args.directory)
    verify_events(root)
    config = read_json(root / "research.json")
    config["permissions"][args.permission] = args.value == "true"
    write_json_atomic(root / "research.json", config)
    emit(root, "permission-changed", args.actor, {"permission": args.permission, "value": config["permissions"][args.permission], "reason": args.reason})


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(description=__doc__)
    commands = result.add_subparsers(dest="command", required=True)
    init = commands.add_parser("init")
    init.add_argument("directory"); init.add_argument("--topic", required=True); init.add_argument("--research-type", required=True)
    init.add_argument("--gpu-hours", type=float, default=0.0); init.add_argument("--cost", type=float, default=0.0); init.add_argument("--actor", default="research-director"); init.set_defaults(func=command_init)
    status = commands.add_parser("status"); status.add_argument("directory"); status.set_defaults(func=command_status)
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
    authorize = commands.add_parser("authorize"); authorize.add_argument("directory"); authorize.add_argument("permission", choices=PERMISSIONS); authorize.add_argument("value", choices=("true", "false")); authorize.add_argument("--reason", required=True); authorize.add_argument("--actor", default="user"); authorize.set_defaults(func=command_authorize)
    verify = commands.add_parser("verify-log"); verify.add_argument("directory"); verify.set_defaults(func=lambda args: verify_events(project(args.directory)))
    return result


if __name__ == "__main__":
    arguments = parser().parse_args()
    if arguments.command in {"status", "verify-log", "audit-scope", "audit-proposal", "audit-theory", "audit-protocol", "audit-pre-experiment", "init"}:
        arguments.func(arguments)
    else:
        root = project(arguments.directory)
        with project_lock(root):
            arguments.func(arguments)
