"""Project-scoped history visibility and cross-project write regressions."""
import os
from pathlib import Path
import subprocess
import sys

import pytest

from agent.runtime.research.policy import ResearchRoot
from agent.runtime.research.storage import PROJECT_SCOPE_ENV


REPO = Path(__file__).resolve().parents[2]
CONTROL = REPO / "agent/runtime/research/researchctl.py"
AUDIT = REPO / "agent/runtime/research/audit.py"
COLLECTOR = REPO / "agent/runtime/research/collect_openalex.py"


def environment(scope: Path | None = None) -> dict[str, str]:
    result = dict(os.environ, PYTHONDONTWRITEBYTECODE="1", PYTHONUTF8="1")
    result.pop(PROJECT_SCOPE_ENV, None)
    if scope is not None:
        result[PROJECT_SCOPE_ENV] = str(scope.resolve())
    return result


def invoke(script: Path, *args: str, scope: Path | None = None) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(script), *args],
        text=True,
        capture_output=True,
        env=environment(scope),
    )


def initialize(path: Path, topic: str) -> None:
    result = invoke(
        CONTROL,
        "init",
        str(path),
        "--topic",
        topic,
        "--research-type",
        "benchmark",
    )
    assert result.returncode == 0, result.stderr


def snapshot(path: Path) -> dict[str, bytes]:
    return {
        item.relative_to(path).as_posix(): item.read_bytes()
        for item in path.rglob("*")
        if item.is_file()
    }


def test_history_reads_require_an_explicit_active_project(tmp_path):
    alpha = tmp_path / "alpha"
    initialize(alpha, "private alpha topic")

    denied = invoke(CONTROL, "status", str(alpha))

    assert denied.returncode != 0
    assert PROJECT_SCOPE_ENV in denied.stderr
    assert "private alpha topic" not in denied.stdout + denied.stderr


def test_active_project_cannot_read_sibling_history_or_identity(tmp_path):
    alpha, beta = tmp_path / "alpha", tmp_path / "beta"
    initialize(alpha, "alpha topic")
    initialize(beta, "secret beta topic")
    beta_history = ResearchRoot(beta / ".research") / "search-log.md"
    beta_history.parent.mkdir(parents=True, exist_ok=True)
    beta_history.write_text("BETA-HISTORY-SENTINEL", encoding="utf-8")

    allowed = invoke(CONTROL, "status", str(alpha), scope=alpha)
    denied_status = invoke(CONTROL, "status", str(beta), scope=alpha)
    denied_audit = invoke(AUDIT, "review", str(beta), scope=alpha)

    assert allowed.returncode == 0
    assert denied_status.returncode != 0
    assert denied_audit.returncode == 2
    disclosure = denied_status.stdout + denied_status.stderr + denied_audit.stdout + denied_audit.stderr
    assert "history isolation violation" in disclosure
    assert "secret beta topic" not in disclosure
    assert "BETA-HISTORY-SENTINEL" not in disclosure
    assert str(beta) not in disclosure


def test_project_paths_reject_parent_and_absolute_escape(tmp_path):
    alpha, beta = tmp_path / "alpha", tmp_path / "beta"
    root = ResearchRoot(alpha / ".research")

    with pytest.raises(ValueError, match="escapes"):
        _ = root / "../beta/.research/review/search-log.md"
    with pytest.raises(ValueError, match="relative"):
        _ = root / (beta / ".research/review/search-log.md")
    with pytest.raises(ValueError, match="escapes"):
        root.output("../beta/outputs/report.md")
    with pytest.raises(ValueError, match="relative"):
        root.output(beta / "outputs/report.md")


def test_mutating_one_project_leaves_sibling_history_unchanged(tmp_path):
    alpha, beta = tmp_path / "alpha", tmp_path / "beta"
    initialize(alpha, "alpha topic")
    initialize(beta, "beta topic")
    before = snapshot(beta / ".research")

    changed = invoke(
        CONTROL,
        "set-budget",
        str(alpha),
        "--gpu-hours",
        "1",
        "--cost",
        "0",
        "--reason",
        "alpha-only change",
        scope=alpha,
    )

    assert changed.returncode == 0, changed.stderr
    assert snapshot(beta / ".research") == before


@pytest.mark.parametrize(
    "option,value",
    [
        ("--queries", "../beta/.research/review/search-plan.json"),
        ("--output", "../beta/.research/review/candidates.jsonl"),
    ],
)
def test_literature_collector_cannot_cross_project_boundary(tmp_path, option, value):
    alpha = tmp_path / "alpha"
    initialize(alpha, "alpha topic")
    query = ResearchRoot(alpha / ".research") / "review/search-plan.json"
    query.parent.mkdir(parents=True, exist_ok=True)
    query.write_text('{"cluster": "query"}', encoding="utf-8")
    arguments = [
        str(alpha),
        "--queries",
        "review/search-plan.json",
        "--output",
        "review/literature/candidates.jsonl",
        "--mailto",
        "test@example.org",
        "--from-date",
        "2026-01-01",
    ]
    arguments[arguments.index(option) + 1] = value

    denied = invoke(COLLECTOR, *arguments, scope=alpha)

    assert denied.returncode == 2
    assert "active project" in denied.stderr
