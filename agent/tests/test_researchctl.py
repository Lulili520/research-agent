import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from agent.runtime.research.researchctl import ResearchRoot


SCRIPT = Path(__file__).resolve().parents[2] / "agent/runtime/research/researchctl.py"


class ResearchControlTests(unittest.TestCase):
    TOPIC = "synthetic research question"
    RESEARCH_TYPE = "benchmark"
    SCOPE = """- Topic: test
- Research question: does X affect Y
- Research type: benchmark
- Theory mode: formal
- Knowledge contribution: mechanism
- Unit of analysis: task
- Intervention or comparison: X versus baseline
- Primary outcome: score
- Population / system scope: systems under study
- In scope: measurement validity
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
        self.invoke("init", str(self.root), "--topic", self.TOPIC, "--research-type", self.RESEARCH_TYPE, "--gpu-hours", "2", "--cost", "10")
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
            "scope.md": self.SCOPE.replace("Topic: test", "Topic: " + self.TOPIC).replace("Research type: benchmark", "Research type: " + self.RESEARCH_TYPE),
            "search-log.md": "Query: test\nDate: 2026-09-01",
            "literature.md": "literature",
            "evidence.md": "C1 evidence",
            "research-directions.md": "directions",
            "selected-direction.md": "selected",
            "theory.md": "- Proposal ID: P1\n- Theory version: 1\n- Theory gate: pass\n- Theory mode: formal\nConstructs: outcome Y\nAssumptions: controlled setting\nMechanism: factor X changes outcome Y\nCompeting explanations: nonspecific change in Y\nPredictions: P1\nFalsifiers: no interaction\nExperiment mapping: E1\n",
            "theory-audit.md": "Theory gate: pass\nReviewer role: theory-skeptic\nReviewer stance: skeptical\nUnresolved threats: external validity\nIndependence statement: reviewed separately from theory construction\n",
            "literature/coverage.md": "Coverage status: saturated\nCorpus size rationale: scoped corpus\nCore set rationale: nearest neighbors\nDirect-neighbor coverage: complete\n",
            "literature/nearest-neighbors.md": "nearest",
            "proposal.md": "- Topic: test\n- Proposal ID: P1\n- Search cutoff: 2026-09-01\n- Proposal decision: pass\n- Novelty status: audited\n- Empirical status: not-run\n- Execution readiness: designed\n- Paper sufficiency: proposal-ready\n- Depth gate: pass\n- Breadth gate: pass\nKnowledge question (Q): does X affect Y\nKnowledge claim (K): X changes Y through a separable mechanism\nMechanism (M): factor X changes mediator M\nDecisive test (D): paired factorial intervention\nScientific consequence (C): distinguishes mechanism from generic degradation\nCentral thesis: factor X changes outcome Y through mechanism M\nResearch-question tree: phenomenon, mechanism, and boundary\nContribution stack: measurement, mechanism, and decision principle\nConfirmatory core: paired factorial test\nBoundary program: factor intensity and population\nExternal-validity minimum: necessary population and operating-condition boundaries\nExpansion stop rule: stop when no claim or threat changes\nConstructs: system under study\nAssumptions: controlled\nMechanism: test\nCompeting explanations: nonspecific change in Y\nPredictions: effect\nFalsifiers: no effect\nPositive outcome: supports the bounded mechanism\nNull outcome: bounds the mechanism effect\nMixed outcome: identifies a boundary condition\nInconclusive outcome: exposes power or measurement limits\nFormal statement: bounded error increases risk\nProof obligations: derive the bound\nProof sketch: condition on task state\nCounterexample search: degenerate tasks checked\nEmpirical corollaries: larger effect at increased X\n",
            "proposal-depth-breadth.md": "Proposal ID: P1\nCentral thesis: factor X changes outcome Y through mechanism M\nResearch-question tree: phenomenon to mechanism to boundary\nNecessary subquestions: effect specificity, mechanism, boundary\nContribution stack: measurement, causal effect, mechanism, decision principle\nDepth target: mechanism and bounded design principle\nDepth chain: intervention X to mediator M to outcome Y\nCompeting explanations: nonspecific change in Y and parser failure\nDecisive discriminator: paired interaction and mechanism intervention\nBreadth floor: process, action, endpoint, and one boundary\nConfirmatory core: paired factorial test\nBoundary axes: factor intensity and population\nExternal-validity minimum: necessary population and operating-condition boundaries\nBreadth ceiling: no unrelated mechanisms or populations\nOut of scope: populations outside the declared scope\nEvidence package: construct validation, core effect, mechanism, boundary, artifact\nExpansion triggers: add an axis only when a claim or fatal threat requires it\nStop-expansion rule: stop when additions change no claim, rival, threat, or boundary\nDepth gate: pass\nBreadth gate: pass\n",
            "proposal-audit.md": "Search cutoff: 2026-09-01\nDatabases: DBLP\nQuery families: task x mechanism\nUncovered scope: proprietary\nNovelty status: audited\nEmpirical dependencies: manipulation and effect size remain not-run\nProposal gate: pass\n",
            "novelty-review.md": "Reviewer role: adversarial-novelty-reviewer\nReviewer model: isolated-review-model\nReviewer context isolation: fresh context\nIndependent search: yes\nReviewer stance: skeptical\nEquivalent-work criterion: same knowledge contribution\nAdversarial findings: none equivalent\nClaim withdrawals: broad claims removed\nUnresolved threats: proprietary work\nIndependence statement: reviewed separately from proposal construction\nDecision: pass\n",
        }
        for name, content in files.items():
            path = self.internal / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(content, encoding="utf-8")
        outputs = self.root / "outputs"
        review = "## 60 篇论文形成的整体认识\nsummary\n## 仍然存在的问题\ngaps\n" + "\n".join("#### 研究动机\na\n#### 方法介绍\nb\n#### 总结归纳\nc" for _ in range(20))
        (outputs / "01-文献调研总结.md").write_text(review, encoding="utf-8")
        proposal_sections = ("研究背景与问题重要性", "精确研究问题", "研究边界与必要广度", "论证深度与机制链", "理论机制", "可证伪假设", "核心构念与测量", "最近邻与新颖性边界", "完整论文证据包", "风险、失败结果与停止条件")
        public_proposal = "Proposal decision: pass\nNovelty status: audited\nEmpirical status: not-run\nExecution readiness: designed\n新颖性审计: pass\n理论可行性审计: pass\n" + "\n".join(f"## {name}\ncontent" for name in proposal_sections)
        (outputs / "02-验证后Proposal.md").write_text(public_proposal, encoding="utf-8")
        registries = {
            "proposal-candidates.jsonl": [
                {"candidate_id": "D1", "status": "selected", "knowledge_question": "does X affect Y", "knowledge_claim": "X changes Y through mechanism M", "mechanism": "mediator M", "decisive_test": "paired factorial intervention", "scientific_consequence": "identifies mechanism M"},
                {"candidate_id": "D2", "status": "rejected", "knowledge_question": "when does X fail", "knowledge_claim": "risk follows a threshold", "mechanism": "decision cost", "decisive_test": "risk by cost intervention", "scientific_consequence": "identifies the boundary"},
                {"candidate_id": "D3", "status": "reserve", "knowledge_question": "how often does X occur", "knowledge_claim": "natural incidence bounds deployed risk", "mechanism": "incidence times effect", "decisive_test": "naturalistic audit plus transport", "scientific_consequence": "bounds external relevance"},
            ],
            "proposal-claims.jsonl": [
                {"claim_id": "PC1", "type": "mechanism", "status": "retained", "claim": "X changes Y through a separable mechanism", "evidence": ["C1"], "scientific_consequence": "distinguishes mechanism from generic degradation"},
            ],
            "proposal-rivals.jsonl": [
                {"rival_id": "R1", "mechanism": "nonspecific change in Y", "distinguishing_pattern": "uniform degradation"},
            ],
            "proposal-threats.jsonl": [
                {"threat_id": "T1", "class": "proposal-fatal", "category": "identification", "severity": "fatal", "status": "resolved", "threat": "the treatment may be confounded", "mitigation": "paired factorial control"},
                {"threat_id": "T2", "class": "empirical-dependency", "category": "measurement", "severity": "major", "status": "deferred", "threat": "the manipulation may fail in practice", "mitigation": "pilot manipulation check"},
                {"threat_id": "T3", "class": "paper-stage", "category": "external-validity", "severity": "major", "status": "open", "threat": "cross-population generality is unknown", "mitigation": "planned robustness study"},
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
                    "protocol-feasibility", "paper-architecture", "adversarial-review",
                ), start=1)
            ] + [
                {
                    "iteration_id": f"F{index}", "proposal_id": "P1", "cycle_type": "full-proposal-cycle",
                    "round": index, "question": "recheck the complete proposal", "inputs": ["C1"],
                    "finding": "complete argument remains bounded", "decision": "retain",
                    "proposal_changed": index < 5, "change_summary": "refined complete argument" if index < 5 else "converged",
                    "unresolved": ["external validity"], "next_action": "continue" if index < 5 else "audit",
                    "breadth_review": "necessary subquestions and scope tiers checked",
                    "depth_review": "effect, mechanism, rival, and principle checked",
                    "novelty_review": "functional neighbors checked",
                    "mechanism_review": "distinct predictions checked",
                    "identification_review": "paired controls and oracle checked",
                    "paper_review": "core, boundary, negative result, and artifact path checked",
                }
                for index in range(1, 6)
            ],
        }
        for name, rows in registries.items():
            (self.internal / name).write_text("".join(json.dumps(row) + "\n" for row in rows), encoding="utf-8")
        with (self.internal / "literature/corpus.jsonl").open("w", encoding="utf-8") as stream:
            for index in range(50):
                item = {"source_id": f"p{index}", "title": f"Paper {index}", "year": 2026, "stable_url": f"https://example.org/{index}", "identity_verified": True, "screening_status": "included", "access_level": "full-text" if index < 20 else "abstract", "role": "core" if index < 20 else "factor X", "relevance_reason": "test"}
                stream.write(json.dumps(item) + "\n")
        papers = self.internal / "papers"
        papers.mkdir(exist_ok=True)
        for index in range(20):
            (papers / f"p{index}.md").write_text("full-text analysis", encoding="utf-8")
        theory_dir = self.internal / "theory"
        theory_dir.mkdir(exist_ok=True)
        claim = {"hypothesis_id": "H1", "claim_ids": ["C1"], "constructs": ["outcome Y"], "assumptions": ["controlled"], "mechanism": "factor X changes outcome Y", "competing_explanations": ["nonspecific change in Y"]}
        prediction = {"prediction_id": "P1", "hypothesis_id": "H1", "claim_ids": ["C1"], "observable": "interaction", "expected_pattern": "larger change in Y under increased X", "rival_pattern": "uniform degradation", "scope": "tested models", "falsifier": "no interaction", "experiment_mapping": "factorial intervention experiment"}
        (theory_dir / "claims.jsonl").write_text(json.dumps(claim) + "\n", encoding="utf-8")
        (theory_dir / "predictions.jsonl").write_text(json.dumps(prediction) + "\n", encoding="utf-8")
        (theory_dir / "formalization.md").write_text("definitions and theorem", encoding="utf-8")
        (theory_dir / "proofs.md").write_text("complete proof", encoding="utf-8")
        (theory_dir / "proof-audit.md").write_text("Proof gate: pass\nReviewer role: proof-skeptic\nReviewer model: isolated-review-model\nVerification level: manual-reconstruction\nIndependent reconstruction: yes\nIndependence statement: reviewed independently\nUnresolved proof issues: none\n", encoding="utf-8")
        (theory_dir / "counterexamples.jsonl").write_text(json.dumps({"case_id": "CE1", "result": "not-found"}) + "\n", encoding="utf-8")
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
- Independent variables: factor X
- Dependent variables: score
- Controls: system configuration
- Confounders: task difficulty
- Baselines: reference method
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
        design = {"protocol_id": "PR1", "protocol_version": 1, "research_type": self.RESEARCH_TYPE, "claims": ["C1"], "hypotheses": ["H1"], "predictions": ["P1"], "experimental_units": ["tasks"], "independent_variables": ["factor X"], "dependent_variables": ["score"], "controls": ["system configuration"], "baselines": ["reference method"], "data_splits": ["test"], "leakage_checks": ["dedup"], "metrics": ["score"], "randomness": [1, 2, 3], "resource_budget": {"gpu_hours": 2}, "stopping_rules": ["fixed budget"], "required_permissions": [], "research_materials": {"mode": "generated", "rationale": "controlled synthetic research units"}}
        (experiments / "design.json").write_text(json.dumps(design), encoding="utf-8")
        (experiments / "analysis-plan.md").write_text("Primary estimand: paired difference\nPrimary metrics: score\nAggregation unit: task\nUncertainty: bootstrap CI\nRandomness: three seeds\nMultiplicity: adjusted\nFailed runs: retained\nMissing data: reported\nExclusions: predeclared\nDecision rule: CI and effect\nExploratory boundary: labeled\n", encoding="utf-8")
        (experiments / "protocol-audit.md").write_text("Protocol ID: PR1\nProtocol version: 1\nProtocol gate: pass\nReviewer role: protocol-skeptic\nReviewer stance: skeptical\nUnresolved threats: external validity\nIndependence statement: reviewed separately from protocol design\nExecution authorization: not granted\n", encoding="utf-8")
        iterations = [
            {"iteration_id": f"TE{index}", "round": index, "cycle_type": "full-theory-experiment-cycle", "question": "full-cycle stress", "inputs": ["P1"], "finding": "bounded", "decision": "retain", "theory_review": "constructs checked", "rival_review": "rival differs", "identification_review": "controls checked", "experiment_review": "prediction mapped", "resource_review": "budget feasible", "paper_review": "positive and negative outcomes bounded", "theory_changed": index < 3, "protocol_changed": index < 4, "change_summary": "refined" if index < 4 else "no substantive change", "unresolved": [], "next_action": "continue" if index < 5 else "freeze"}
            for index in range(1, 6)
        ]
        (self.internal / "theory-experiment-iterations.jsonl").write_text("".join(json.dumps(row) + "\n" for row in iterations), encoding="utf-8")
        experiment_sections = ("理论构念与适用域", "机制推导与竞争解释", "可证伪预测", "预测—实验映射", "数据与研究材料", "具体实验方案", "指标与判定规则", "统计计划", "硬件资源要求", "人工部署与软件环境", "时间与运行量估算", "执行顺序与门禁")
        experiment_output = "实验协议审计: pass\n" + "\n".join(f"## {name}\ncontent" for name in experiment_sections) + "\nhttps://a.example https://b.example https://c.example\n"
        (self.root / "outputs/03-理论分析与实验探究.md").write_text(experiment_output, encoding="utf-8")

    def grant_execution(self):
        (self.internal / "control/user-execution.md").write_text("User explicitly requests execution of the frozen protocol.")
        self.invoke("authorize-execution", str(self.root), "true", "--evidence", "control/user-execution.md", "--reason", "explicit user instruction")

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
        state = json.loads((self.internal / "state.json").read_text(encoding="utf-8"))
        self.assertEqual(state["proposal_decision"], "pass")
        self.assertEqual(state["empirical_status"], "not-run")
        self.assertEqual(state["execution_readiness"], "designed")
        self.write_protocol_artifacts()
        experiments = self.internal / "experiments"
        self.invoke("freeze-protocol", str(self.root))
        self.invoke("register-experiment", str(self.root), "--id", "exp-1", "--claim", "C1", "--hypothesis", "H1", "--purpose", "falsification")
        duplicate = self.invoke("register-experiment", str(self.root), "--id", "exp-1", "--purpose", "duplicate", ok=False)
        self.assertNotEqual(duplicate.returncode, 0)
        (experiments / "pilot.md").write_text("Pilot gate: pending\n", encoding="utf-8")
        (self.internal / "proposal/novelty-refresh-pre-experiment.md").write_text("Search date: 2026-09-03\nDatabases: proceedings\nQuery families: nearest-neighbor refresh\nNew nearest neighbors: none\nClaim impact: unchanged\nRefresh decision: pass\n", encoding="utf-8")
        self.grant_execution()
        self.invoke("transition", str(self.root), "pilot", "--reason", "protocol frozen")
        state = json.loads((self.internal / "state.json").read_text(encoding="utf-8"))
        self.assertEqual(state["empirical_status"], "not-run")
        self.assertEqual(state["execution_readiness"], "deployable")
        (self.internal / "configs").mkdir()
        (self.internal / "configs/1.json").write_text("{}", encoding="utf-8")
        (self.internal / "configs/2.json").write_text("{}", encoding="utf-8")
        self.invoke("register-run", str(self.root), "--id", "run-1", "--experiment", "exp-1", "--config", "configs/1.json", "--code-revision", "abc", "--environment", "env-1", "--gpu-hours", "1", "--cost", "2")
        self.invoke("finish-run", str(self.root), "--id", "run-1", "--status", "failed", "--gpu-hours", "0.5", "--cost", "1", "--reason", "out of memory")
        outcomes = [json.loads(line) for line in (self.internal / "runs/outcomes.jsonl").read_text(encoding="utf-8").splitlines()]
        self.assertEqual(outcomes[0]["status"], "failed")
        over_budget = self.invoke("register-run", str(self.root), "--id", "run-2", "--experiment", "exp-1", "--config", "configs/2.json", "--code-revision", "abc", "--environment", "env-1", "--gpu-hours", "3", ok=False)
        self.assertNotEqual(over_budget.returncode, 0)

    def test_entering_and_leaving_pilot_without_runs_remains_not_run(self):
        self.advance_to_protocol()
        self.write_protocol_artifacts()
        (self.internal / "proposal/novelty-refresh-pre-experiment.md").write_text("Search date: 2026-09-03\nDatabases: proceedings\nQuery families: nearest-neighbor refresh\nNew nearest neighbors: none\nClaim impact: unchanged\nRefresh decision: pass\n", encoding="utf-8")
        self.invoke("freeze-protocol", str(self.root))
        self.grant_execution()
        self.invoke("transition", str(self.root), "pilot", "--reason", "start pilot")
        self.invoke("transition", str(self.root), "experiment-protocol", "--reason", "revise protocol")
        state = json.loads((self.internal / "state.json").read_text(encoding="utf-8"))
        self.assertEqual(state["empirical_status"], "not-run")
        self.assertEqual(state["execution_readiness"], "designed")

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
        audit_path = experiments / "protocol-audit.md"
        audit_path.write_text(audit_path.read_text(encoding="utf-8").replace("Protocol version: 1", "Protocol version: 2"), encoding="utf-8")
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
        (literature / "coverage.md").write_text("Coverage status: saturated\nCorpus size rationale: scoped corpus\nCore set rationale: nearest neighbors\nDirect-neighbor coverage: complete\n", encoding="utf-8")
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

    def test_protocol_audit_version_must_match_protocol(self):
        self.advance_to_protocol()
        self.write_protocol_artifacts()
        audit_path = self.internal / "experiments/protocol-audit.md"
        audit_path.write_text(audit_path.read_text(encoding="utf-8").replace("Protocol version: 1", "Protocol version: 2"), encoding="utf-8")
        denied = self.invoke("audit-protocol", str(self.root), ok=False)
        self.assertIn("protocol version differs between protocol.md and protocol-audit.md", denied.stderr)

    def test_pre_experiment_endpoint_requires_frozen_audited_protocol(self):
        self.advance_to_protocol()
        self.write_protocol_artifacts()
        (self.internal / "proposal/novelty-refresh-pre-experiment.md").write_text("Search date: 2026-09-03\nDatabases: proceedings\nQuery families: nearest-neighbor refresh\nNew nearest neighbors: none\nClaim impact: unchanged\nRefresh decision: pass\n", encoding="utf-8")
        denied = self.invoke("audit-pre-experiment", str(self.root), ok=False)
        self.assertIn("freeze the protocol", denied.stderr)
        self.invoke("freeze-protocol", str(self.root))
        result = self.invoke("audit-pre-experiment", str(self.root))
        self.assertIn("ready-for-explicit-execution-decision", result.stdout)

    def test_pre_experiment_requires_current_novelty_refresh(self):
        self.advance_to_protocol()
        self.write_protocol_artifacts()
        self.invoke("freeze-protocol", str(self.root))
        denied = self.invoke("audit-pre-experiment", str(self.root), ok=False)
        self.assertIn("novelty-refresh-pre-experiment", denied.stderr)

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
        self.assertIn('"empirical_status": "not-run"', result.stdout)

    def test_proposal_gate_allows_unrun_empirical_dependencies(self):
        self.advance_to_protocol()
        result = self.invoke("audit-proposal", str(self.root))
        self.assertIn('"proposal_decision": "pass"', result.stdout)
        self.assertIn('"empirical_status": "not-run"', result.stdout)

    def test_proposal_gate_rejects_unresolved_proposal_fatal(self):
        self.advance_to_protocol()
        threats_path = self.internal / "proposal-threats.jsonl"
        threats = [json.loads(line) for line in threats_path.read_text(encoding="utf-8").splitlines()]
        threats[0]["status"] = "open"
        threats_path.write_text("".join(json.dumps(row) + "\n" for row in threats), encoding="utf-8")
        denied = self.invoke("audit-proposal", str(self.root), ok=False)
        self.assertIn("unresolved proposal-fatal", denied.stderr)

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

    def test_proposal_gate_requires_depth_and_breadth_audit(self):
        self.advance_to_protocol()
        audit = self.internal / "proposal-depth-breadth.md"
        audit.write_text(
            audit.read_text(encoding="utf-8").replace("Depth gate: pass", "Depth gate: revise"),
            encoding="utf-8",
        )
        denied = self.invoke("audit-proposal", str(self.root), ok=False)
        self.assertIn("Depth gate: pass", denied.stderr)

    def test_proposal_gate_requires_five_full_cycles_for_current_proposal(self):
        self.advance_to_protocol()
        iterations = self.internal / "proposal-iterations.jsonl"
        rows = [json.loads(line) for line in iterations.read_text(encoding="utf-8").splitlines()]
        iterations.write_text(
            "".join(
                json.dumps(row) + "\n"
                for row in rows
                if row.get("cycle_type") != "full-proposal-cycle" or row.get("round") != 3
            ),
            encoding="utf-8",
        )
        denied = self.invoke("audit-proposal", str(self.root), ok=False)
        self.assertIn("five full-proposal-cycle", denied.stderr)

    def test_old_proposal_cycles_cannot_satisfy_current_proposal_gate(self):
        self.advance_to_protocol()
        iterations = self.internal / "proposal-iterations.jsonl"
        rows = [json.loads(line) for line in iterations.read_text(encoding="utf-8").splitlines()]
        for row in rows:
            if row["cycle_type"] in {
                "candidate-comparison", "novelty-collision", "mechanism-falsification",
                "protocol-feasibility", "paper-architecture", "adversarial-review",
            }:
                row["proposal_id"] = "P0"
        iterations.write_text("".join(json.dumps(row) + "\n" for row in rows), encoding="utf-8")
        denied = self.invoke("audit-proposal", str(self.root), ok=False)
        self.assertIn("current proposal iteration record missing cycles", denied.stderr)

    def test_policy_migration_blocks_mutation_until_revalidated(self):
        self.invoke("migrate-policy", str(self.root), "--reason", "gate policy upgraded")
        denied = self.invoke("transition", str(self.root), "problem-framing", "--reason", "start", ok=False)
        self.assertIn("migration-required", denied.stderr)
        self.invoke("revalidate-policy", str(self.root))
        self.invoke("transition", str(self.root), "problem-framing", "--reason", "start")


if __name__ == "__main__":
    unittest.main()
