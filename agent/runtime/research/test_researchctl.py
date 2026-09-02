import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from agent.runtime.research.researchctl import ResearchRoot


SCRIPT = Path(__file__).with_name("researchctl.py")


class ResearchControlTests(unittest.TestCase):
    SCOPE = """- Topic: test
- Research question: does X affect Y
- Research type: benchmark
- Knowledge contribution: mechanism
- Unit of analysis: task
- Intervention or comparison: X versus baseline
- Primary outcome: score
- Population / system scope: tested agents
- In scope: agent evaluation
- Out of scope: humans
- Falsification condition: no effect
- Data constraints: public data
- Model constraints: open models
- Compute and time constraints: two GPU hours
- Ethics and permissions: no restricted data
- Deliverables: proposal and protocol
- Open decisions: none
- Scope version: 1
"""
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name) / "topic"
        self.invoke("init", str(self.root), "--topic", "test topic", "--research-type", "benchmark", "--gpu-hours", "2", "--cost", "10")
        self.internal = ResearchRoot(self.root / ".research")

    def tearDown(self):
        self.temp.cleanup()

    def invoke(self, *args, ok=True):
        env = dict(os.environ, PYTHONDONTWRITEBYTECODE="1")
        result = subprocess.run([sys.executable, str(SCRIPT), *args], text=True, capture_output=True, env=env)
        if ok and result.returncode != 0:
            self.fail(result.stdout + result.stderr)
        return result

    def advance_to_protocol(self):
        files = {
            "scope.md": self.SCOPE,
            "search-log.md": "Query: test\nDate: 2026-09-01",
            "literature.md": "literature",
            "evidence.md": "C1 evidence",
            "research-directions.md": "directions",
            "selected-direction.md": "selected",
            "theory.md": "- Proposal ID: P1\n- Theory version: 1\n- Theory gate: pass\nConstructs: agent score\nAssumptions: controlled setting\nMechanism: compression changes action selection\nCompeting explanations: generic accuracy loss\nPredictions: P1\nFalsifiers: no interaction\nExperiment mapping: E1\n",
            "theory-audit.md": "Theory gate: pass\nReviewer role: theory-skeptic\nReviewer stance: skeptical\nUnresolved threats: external validity\nIndependence statement: reviewed separately from theory construction\n",
            "literature/coverage.md": "coverage",
            "literature/nearest-neighbors.md": "nearest",
            "proposal.md": "- Topic: test\n- Proposal ID: P1\n- Search cutoff: 2026-09-01\n- Novelty status: audited\nConstructs: agents\nAssumptions: controlled\nMechanism: test\nCompeting explanations: null\nPredictions: effect\nFalsifiers: no effect\n",
            "proposal-audit.md": "Search cutoff: 2026-09-01\nDatabases: DBLP\nQuery families: task x mechanism\nUncovered scope: proprietary\nNovelty status: audited\n",
            "novelty-review.md": "Reviewer role: adversarial-novelty-reviewer\nReviewer stance: skeptical\nEquivalent-work criterion: same knowledge contribution\nAdversarial findings: none equivalent\nClaim withdrawals: broad claims removed\nUnresolved threats: proprietary work\nIndependence statement: reviewed separately from proposal construction\nDecision: pass\n",
        }
        for name, content in files.items():
            path = self.internal / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(content, encoding="utf-8")
        outputs = self.root / "outputs"
        review = "## 60 篇论文形成的整体认识\nsummary\n## 仍然存在的问题\ngaps\n" + "\n".join("#### 研究动机\na\n#### 方法介绍\nb\n#### 总结归纳\nc" for _ in range(20))
        (outputs / "01-文献调研总结.md").write_text(review, encoding="utf-8")
        proposal_sections = ("研究背景与问题重要性", "精确研究问题", "理论机制", "可证伪假设", "核心构念与测量", "最近邻与新颖性边界", "风险、失败结果与停止条件")
        public_proposal = "新颖性审计: pass\n理论可行性审计: pass\n" + "\n".join(f"## {name}\ncontent" for name in proposal_sections)
        (outputs / "02-验证后Proposal.md").write_text(public_proposal, encoding="utf-8")
        registries = {
            "proposal-candidates.jsonl": [
                {"candidate_id": "D1", "status": "selected", "knowledge_contribution": "mechanism"},
                {"candidate_id": "D2", "status": "rejected", "knowledge_contribution": "benchmark"},
            ],
            "proposal-claims.jsonl": [
                {"claim_id": "PC1", "type": "mechanism", "status": "retained", "evidence": ["C1"]},
            ],
            "proposal-rivals.jsonl": [
                {"rival_id": "R1", "mechanism": "generic accuracy loss", "distinguishing_pattern": "uniform degradation"},
            ],
            "proposal-threats.jsonl": [
                {"threat_id": "T1", "severity": "major", "status": "mitigated", "mitigation": "paired control"},
            ],
            "proposal-iterations.jsonl": [
                {
                    "iteration_id": f"I{index}", "proposal_id": "P1", "cycle_type": cycle,
                    "question": f"stress {cycle}", "inputs": ["C1"], "finding": "survives bounded test",
                    "decision": "retain", "proposal_changed": False, "change_summary": "no core change",
                    "unresolved": ["external validity"], "next_action": "continue gate",
                }
                for index, cycle in enumerate((
                    "candidate-comparison", "novelty-collision", "mechanism-falsification",
                    "protocol-feasibility", "adversarial-review",
                ), start=1)
            ],
        }
        for name, rows in registries.items():
            (self.internal / name).write_text("".join(json.dumps(row) + "\n" for row in rows), encoding="utf-8")
        with (self.internal / "literature/corpus.jsonl").open("w", encoding="utf-8") as stream:
            for index in range(50):
                item = {"source_id": f"p{index}", "title": f"Paper {index}", "year": 2026, "stable_url": f"https://example.org/{index}", "identity_verified": True, "screening_status": "included", "access_level": "full-text" if index < 20 else "abstract", "role": "core" if index < 20 else "context", "relevance_reason": "test"}
                stream.write(json.dumps(item) + "\n")
        papers = self.internal / "papers"
        papers.mkdir(exist_ok=True)
        for index in range(20):
            (papers / f"p{index}.md").write_text("full-text analysis", encoding="utf-8")
        theory_dir = self.internal / "theory"
        theory_dir.mkdir(exist_ok=True)
        claim = {"hypothesis_id": "H1", "claim_ids": ["C1"], "constructs": ["agent score"], "assumptions": ["controlled"], "mechanism": "compression changes action selection", "competing_explanations": ["generic accuracy loss"]}
        prediction = {"prediction_id": "P1", "hypothesis_id": "H1", "claim_ids": ["C1"], "observable": "interaction", "expected_pattern": "larger degradation on long trajectories", "rival_pattern": "uniform degradation", "scope": "tested models", "falsifier": "no interaction", "experiment_mapping": "factorial context experiment"}
        (theory_dir / "claims.jsonl").write_text(json.dumps(claim) + "\n", encoding="utf-8")
        (theory_dir / "predictions.jsonl").write_text(json.dumps(prediction) + "\n", encoding="utf-8")
        (self.internal / "search-log.md").write_text("Round: 1\nProposal changed: yes\nRound: 2\nProposal changed: no\nRound: 3\nProposal changed: no\nSaturation: reached\n", encoding="utf-8")
        for stage in ("problem-framing", "literature-mapping", "direction-audit", "theory-building", "experiment-protocol"):
            self.invoke("transition", str(self.root), stage, "--reason", "test progression")

    def write_protocol_artifacts(self):
        experiments = self.internal / "experiments"
        experiments.mkdir(exist_ok=True)
        protocol = """- Protocol ID: PR1
- Protocol version: 1
- Protocol gate: pass
- Proposal ID: P1
- Theory version: 1
- Claims: C1
- Hypotheses: H1
- Predictions: P1
- Experimental units: tasks
- Independent variables: context length
- Dependent variables: score
- Controls: model family
- Confounders: task difficulty
- Baselines: full precision
- Data splits: fixed test
- Leakage checks: deduplication
- Metrics: score
- Randomness: three seeds
- Analysis: paired comparison
- Failure criteria: invalid verifier
- Stopping rules: fixed budget
- Resource budget: two GPU hours
- Exploratory analyses: error taxonomy
- Deviations policy: version protocol
"""
        (experiments / "protocol.md").write_text(protocol, encoding="utf-8")
        design = {"protocol_id": "PR1", "protocol_version": 1, "research_type": "benchmark", "claims": ["C1"], "hypotheses": ["H1"], "predictions": ["P1"], "experimental_units": ["tasks"], "independent_variables": ["context"], "dependent_variables": ["score"], "controls": ["model"], "baselines": ["full precision"], "data_splits": ["test"], "leakage_checks": ["dedup"], "metrics": ["score"], "randomness": [1, 2, 3], "resource_budget": {"gpu_hours": 2}, "stopping_rules": ["fixed budget"]}
        (experiments / "design.json").write_text(json.dumps(design), encoding="utf-8")
        (experiments / "analysis-plan.md").write_text("Primary estimand: paired difference\nPrimary metrics: score\nAggregation unit: task\nUncertainty: bootstrap CI\nRandomness: three seeds\nMultiplicity: adjusted\nFailed runs: retained\nMissing data: reported\nExclusions: predeclared\nDecision rule: CI and effect\nExploratory boundary: labeled\n", encoding="utf-8")
        (experiments / "protocol-audit.md").write_text("Protocol gate: pass\nReviewer role: protocol-skeptic\nReviewer stance: skeptical\nUnresolved threats: external validity\nIndependence statement: reviewed separately from protocol design\nExecution authorization: not granted\n", encoding="utf-8")
        iterations = [
            {"iteration_id": f"TE{index}", "round": index, "cycle_type": "full-theory-experiment-cycle", "question": "full-cycle stress", "inputs": ["P1"], "finding": "bounded", "decision": "retain", "theory_review": "constructs checked", "rival_review": "rival differs", "identification_review": "controls checked", "experiment_review": "prediction mapped", "resource_review": "budget feasible", "paper_review": "positive and negative outcomes bounded", "theory_changed": index < 3, "protocol_changed": index < 4, "change_summary": "refined" if index < 4 else "no substantive change", "unresolved": [], "next_action": "continue" if index < 5 else "freeze"}
            for index in range(1, 6)
        ]
        (self.internal / "theory-experiment-iterations.jsonl").write_text("".join(json.dumps(row) + "\n" for row in iterations), encoding="utf-8")
        experiment_sections = ("理论构念与适用域", "机制推导与竞争解释", "可证伪预测", "预测—实验映射", "数据集选择", "历史错误构造", "具体实验方案", "指标与判定规则", "统计计划", "硬件资源要求", "人工部署与软件环境", "时间与运行量估算", "执行顺序与门禁")
        experiment_output = "实验协议审计: pass\n" + "\n".join(f"## {name}\ncontent" for name in experiment_sections) + "\nhttps://a.example https://b.example https://c.example\n"
        (self.root / "outputs/03-理论分析与实验探究.md").write_text(experiment_output, encoding="utf-8")

    def test_gate_and_event_integrity(self):
        self.invoke("transition", str(self.root), "problem-framing", "--reason", "start")
        denied = self.invoke("transition", str(self.root), "literature-mapping", "--reason", "ready", ok=False)
        self.assertNotEqual(denied.returncode, 0)
        (self.internal / "scope.md").write_text(self.SCOPE, encoding="utf-8")
        self.invoke("transition", str(self.root), "literature-mapping", "--reason", "scope frozen")
        self.invoke("verify-log", str(self.root))
        events = (self.internal / "events.jsonl").read_text(encoding="utf-8").splitlines()
        self.assertEqual(len(events), 3)

    def test_protocol_registry_budget_and_failure_preservation(self):
        self.advance_to_protocol()
        self.write_protocol_artifacts()
        experiments = self.internal / "experiments"
        self.invoke("freeze-protocol", str(self.root))
        self.invoke("register-experiment", str(self.root), "--id", "exp-1", "--claim", "C1", "--hypothesis", "H1", "--purpose", "falsification")
        duplicate = self.invoke("register-experiment", str(self.root), "--id", "exp-1", "--purpose", "duplicate", ok=False)
        self.assertNotEqual(duplicate.returncode, 0)
        (experiments / "pilot.md").write_text("Pilot gate: pending\n", encoding="utf-8")
        self.invoke("transition", str(self.root), "pilot", "--reason", "protocol frozen")
        (self.internal / "configs").mkdir()
        (self.internal / "configs/1.json").write_text("{}", encoding="utf-8")
        (self.internal / "configs/2.json").write_text("{}", encoding="utf-8")
        self.invoke("register-run", str(self.root), "--id", "run-1", "--experiment", "exp-1", "--config", "configs/1.json", "--code-revision", "abc", "--environment", "env-1", "--gpu-hours", "1", "--cost", "2")
        self.invoke("finish-run", str(self.root), "--id", "run-1", "--status", "failed", "--gpu-hours", "0.5", "--cost", "1", "--reason", "out of memory")
        outcomes = [json.loads(line) for line in (self.internal / "runs/outcomes.jsonl").read_text(encoding="utf-8").splitlines()]
        self.assertEqual(outcomes[0]["status"], "failed")
        over_budget = self.invoke("register-run", str(self.root), "--id", "run-2", "--experiment", "exp-1", "--config", "configs/2.json", "--code-revision", "abc", "--environment", "env-1", "--gpu-hours", "3", ok=False)
        self.assertNotEqual(over_budget.returncode, 0)

    def test_protocol_tamper_is_rejected(self):
        self.advance_to_protocol()
        self.write_protocol_artifacts()
        experiments = self.internal / "experiments"
        protocol = experiments / "protocol.md"
        self.invoke("freeze-protocol", str(self.root))
        protocol.write_text("changed after freeze", encoding="utf-8")
        denied = self.invoke("register-experiment", str(self.root), "--id", "exp-1", "--purpose", "test", ok=False)
        self.assertIn("changed after freezing", denied.stderr)

    def test_negative_budget_and_wrong_stage_are_rejected(self):
        denied = self.invoke("register-experiment", str(self.root), "--id", "exp-1", "--purpose", "too early", ok=False)
        self.assertIn("not allowed", denied.stderr)
        denied = self.invoke("init", str(self.root.parent / "bad"), "--topic", "bad", "--research-type", "benchmark", "--gpu-hours", "-1", ok=False)
        self.assertIn("non-negative", denied.stderr)

    def test_protocol_versions_are_archived(self):
        self.advance_to_protocol()
        self.write_protocol_artifacts()
        experiments = self.internal / "experiments"
        protocol = experiments / "protocol.md"
        self.invoke("freeze-protocol", str(self.root))
        version_one = protocol.read_text(encoding="utf-8")
        protocol.write_text("version two", encoding="utf-8")
        denied = self.invoke("freeze-protocol", str(self.root), ok=False)
        self.assertIn("protocol audit failed", denied.stderr)
        protocol.write_text(version_one.replace("Protocol version: 1", "Protocol version: 2"), encoding="utf-8")
        design_path = experiments / "design.json"
        design = json.loads(design_path.read_text(encoding="utf-8"))
        design["protocol_version"] = 2
        design_path.write_text(json.dumps(design), encoding="utf-8")
        self.invoke("freeze-protocol", str(self.root))
        self.assertEqual((experiments / "protocols/v001.md").read_text(encoding="utf-8"), version_one)
        self.assertIn("Protocol version: 2", (experiments / "protocols/v002.md").read_text(encoding="utf-8"))

    def test_completion_cannot_bypass_full_gate(self):
        state = json.loads((self.internal / "state.json").read_text(encoding="utf-8"))
        state["research_stage"] = "report-review"
        (self.internal / "state.json").write_text(json.dumps(state), encoding="utf-8")
        denied = self.invoke("transition", str(self.root), "complete", "--reason", "premature", ok=False)
        self.assertIn("completion audit failed", denied.stderr)

    def test_proposal_gate_requires_sufficient_verified_corpus(self):
        for name in ("scope.md", "search-log.md", "literature.md", "evidence.md"):
            (self.internal / name).write_text("evidence", encoding="utf-8")
        literature = self.internal / "literature"
        literature.mkdir()
        (literature / "coverage.md").write_text("coverage", encoding="utf-8")
        (literature / "corpus.jsonl").write_text(json.dumps({"source_id": "p1"}) + "\n", encoding="utf-8")
        denied = self.invoke("audit-proposal", str(self.root), ok=False)
        self.assertIn("missing fields", denied.stderr)

    def test_proposal_gate_rejects_unstable_final_search_rounds(self):
        self.advance_to_protocol()
        search = self.internal / "search-log.md"
        search.write_text("Round: 1\nProposal changed: no\nRound: 2\nProposal changed: yes\nSaturation: reached\n", encoding="utf-8")
        denied = self.invoke("audit-proposal", str(self.root), ok=False)
        self.assertIn("last two directed rounds", denied.stderr)

    def test_theory_gate_rejects_non_distinguishing_prediction(self):
        self.advance_to_protocol()
        state = json.loads((self.internal / "state.json").read_text(encoding="utf-8"))
        state["research_stage"] = "theory-building"
        (self.internal / "state.json").write_text(json.dumps(state), encoding="utf-8")
        prediction_path = self.internal / "theory/predictions.jsonl"
        prediction = json.loads(prediction_path.read_text(encoding="utf-8"))
        prediction["rival_pattern"] = prediction["expected_pattern"]
        prediction_path.write_text(json.dumps(prediction) + "\n", encoding="utf-8")
        denied = self.invoke("audit-theory", str(self.root), ok=False)
        self.assertIn("does not distinguish", denied.stderr)

    def test_scope_gate_rejects_incomplete_question(self):
        (self.internal / "scope.md").write_text("- Topic: vague topic\n", encoding="utf-8")
        denied = self.invoke("audit-scope", str(self.root), ok=False)
        self.assertIn("Research question", denied.stderr)

    def test_protocol_must_cover_every_theory_prediction(self):
        self.advance_to_protocol()
        self.write_protocol_artifacts()
        design_path = self.internal / "experiments/design.json"
        design = json.loads(design_path.read_text(encoding="utf-8"))
        design["predictions"] = ["P999"]
        design_path.write_text(json.dumps(design), encoding="utf-8")
        denied = self.invoke("audit-protocol", str(self.root), ok=False)
        self.assertIn("does not cover theory predictions: P1", denied.stderr)

    def test_pre_experiment_endpoint_requires_frozen_audited_protocol(self):
        self.advance_to_protocol()
        self.write_protocol_artifacts()
        denied = self.invoke("audit-pre-experiment", str(self.root), ok=False)
        self.assertIn("freeze the protocol", denied.stderr)
        self.invoke("freeze-protocol", str(self.root))
        result = self.invoke("audit-pre-experiment", str(self.root))
        self.assertIn("ready-for-explicit-execution-decision", result.stdout)

    def test_proposal_gate_accepts_dynamic_corpus_count_heading(self):
        self.advance_to_protocol()
        review_path = self.root / "outputs" / "01-文献调研总结.md"
        review_path.write_text(
            review_path.read_text(encoding="utf-8").replace(
                "60 篇论文形成的整体认识", "69 篇论文形成的整体认识"
            ),
            encoding="utf-8",
        )
        result = self.invoke("audit-proposal", str(self.root))
        self.assertIn('"status": "pass"', result.stdout)

    def test_proposal_gate_requires_every_reasoning_cycle(self):
        self.advance_to_protocol()
        iterations = self.internal / "proposal-iterations.jsonl"
        rows = [json.loads(line) for line in iterations.read_text(encoding="utf-8").splitlines()]
        iterations.write_text(
            "".join(json.dumps(row) + "\n" for row in rows if row["cycle_type"] != "protocol-feasibility"),
            encoding="utf-8",
        )
        denied = self.invoke("audit-proposal", str(self.root), ok=False)
        self.assertIn("protocol-feasibility", denied.stderr)


if __name__ == "__main__":
    unittest.main()
