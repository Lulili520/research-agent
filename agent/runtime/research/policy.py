"""Project layout and versioned research policy; no topic-specific dependencies."""
import os
from typing import Any
from pathlib import Path

SCHEMA_VERSION = 4
GATE_POLICY_VERSION = "execution-contract-v6"

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
    "proposal-depth-breadth.md": "proposal/depth-breadth.md",
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
        self.base = Path(base).resolve()

    def path(self, relative: str | os.PathLike[str]) -> Path:
        """Resolve one project-relative path without allowing history escape."""
        mapped = Path(layout_path(os.fspath(relative)))
        if mapped.is_absolute():
            raise ValueError("research project paths must be relative")
        candidate = (self.base / mapped).resolve()
        if not candidate.is_relative_to(self.base):
            raise ValueError("research project path escapes the active project")
        return candidate

    def output(self, relative: str | os.PathLike[str] = "") -> Path:
        """Resolve one user-output path without following links to a sibling."""
        outer = self.base.parent if self.base.name == ".research" else self.base
        expected = outer / "outputs"
        output_root = expected.resolve()
        if output_root != expected:
            raise ValueError("research output directory escapes the active project")
        requested = Path(os.fspath(relative))
        if requested.is_absolute():
            raise ValueError("research output paths must be relative")
        candidate = (output_root / requested).resolve()
        if not candidate.is_relative_to(output_root):
            raise ValueError("research output path escapes the active project")
        return candidate

    def __truediv__(self, relative: str | os.PathLike[str]) -> Path:
        return self.path(relative)

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
    "theory-building": ["research-directions.md", "selected-direction.md", "proposal.md", "proposal-depth-breadth.md", "proposal-audit.md", "literature/nearest-neighbors.md"],
    "experiment-protocol": ["theory.md", "theory/claims.jsonl", "theory/predictions.jsonl", "theory-audit.md"],
    "pilot": ["experiments/protocol.md", "experiments/protocol.lock.json", "experiments/design.json", "experiments/analysis-plan.md", "experiments/protocol-audit.md", "proposal/novelty-refresh-pre-experiment.md"],
    "main-experiment": ["experiments/pilot.md"],
    "robustness-analysis": ["experiments/results.md", "runs/registry.jsonl"],
    "evidence-audit": ["analysis.md", "evidence.md"],
    "artifact-building": ["analysis.md", "evidence.md"],
    "artifact-validation": ["artifact/README.md"],
    "report-writing": ["artifact/README.md"],
    "report-review": [
        "report.md", "paper/manuscript.md", "paper/claims.jsonl",
        "paper/iterations.jsonl", "paper/quality-audit.json", "paper/unified-quality-audit.md",
        "paper/review.md", "paper/reproducibility.md", "proposal/novelty-refresh-pre-paper.md",
    ],
}

PERMISSIONS = ("external_compute", "restricted_data", "human_subjects", "external_publish")
EXPERIMENT_STAGES = {"experiment-protocol", "pilot", "main-experiment", "robustness-analysis"}
RUN_STAGES = {"pilot", "main-experiment", "robustness-analysis"}
QUALITY_DIMENSIONS = {
    "importance", "novelty", "depth", "theory", "correctness",
    "experimental_sufficiency", "robustness", "reproducibility", "ethics", "clarity",
}
EMPIRICAL_ORDER = {"not-run": 0, "pilot": 1, "tested": 2}
