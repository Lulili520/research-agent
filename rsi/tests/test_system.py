from copy import deepcopy
import json
from pathlib import Path
import sqlite3
import sys
from tempfile import TemporaryDirectory
import unittest

from rsi.runtime.contracts import ContractError, VERSION, bundle, fresh, ref
from rsi.runtime.engine import Engine
from rsi.runtime.history import VersionLibrary, checkpoint, compare, restore
from rsi.runtime.quality import quality_status
from rsi.runtime.workers import load_team, run
from rsi.tests.helpers import BAD, GOOD, SOURCE, report, review_record, source


class SystemTests(unittest.TestCase):
    def setUp(self):
        self.directory = TemporaryDirectory()
        self.root = Path(self.directory.name)
        self.engine = Engine(self.root / "project")
        self.engine.initialize("合成测试，不是研究默认方向", "literature")

    def tearDown(self):
        self.directory.cleanup()

    def setup_report(self, **options):
        self.source = source(self.engine)
        self.report = report(self.engine, self.source, **options)
        return review_record(self.engine.store.read(), self.report)

    def test_initialization_does_not_overwrite(self):
        with self.assertRaises(ContractError):
            self.engine.initialize("second")

    def test_old_report_blocks_accidental_initialization(self):
        folder = self.root / "old" / "outputs"
        folder.mkdir(parents=True)
        (folder / "文献调研.md").write_text("user work")
        with self.assertRaises(ContractError):
            Engine(folder.parent).initialize("topic")

    def test_valid_review_is_not_proof_of_science(self):
        record = self.setup_report()
        self.engine.review(record, "critic")
        status = self.engine.status()["quality"]
        self.assertTrue(status["ready"])
        self.assertFalse(status["automatic_semantic_verification"])

    def test_self_review_rejected(self):
        record = self.setup_report()
        with self.assertRaises(ContractError):
            self.engine.review(record, "writer")

    def test_all_not_applicable_cannot_pass(self):
        record = self.setup_report()
        for value in record["dimensions"].values():
            value.update(status="not-applicable", alternative_check="假装不适用")
        with self.assertRaises(ContractError):
            self.engine.review(record, "critic")

    def test_abstract_only_does_not_pass_method_reading(self):
        source_record = source(self.engine, access="abstract")
        target = report(self.engine, source_record)
        with self.assertRaises(ContractError):
            self.engine.review(review_record(self.engine.store.read(), target), "critic")

    def test_review_requires_whole_bundle(self):
        record = self.setup_report()
        record["reviewed_refs"] = [ref(self.report)]
        with self.assertRaises(ContractError):
            self.engine.review(record, "critic")

    def test_missing_locator_rejected(self):
        record = self.setup_report()
        record["probes"][0]["evidence"] = [ref(self.source)]
        with self.assertRaises(ContractError):
            self.engine.review(record, "critic")

    def test_insufficient_dimension_must_route_to_repair(self):
        record = self.setup_report()
        record["dimensions"]["method-understanding"]["status"] = "insufficient"
        with self.assertRaises(ContractError):
            self.engine.review(record, "critic")

    def test_failed_probe_requires_action(self):
        record = self.setup_report()
        record["probes"][0]["result"] = "failed"
        with self.assertRaises(ContractError):
            self.engine.review(record, "critic")

    def test_hash_mismatch_rejected(self):
        record = self.setup_report()
        record["target"]["sha256"] = "a" * 64
        with self.assertRaises(ContractError):
            self.engine.review(record, "critic")

    def test_source_update_invalidates_transitive_reports(self):
        record = self.setup_report()
        self.engine.review(record, "critic")
        proposal = report(self.engine, self.report, key="proposal", kind="proposal", actor="designer")
        self.assertTrue(fresh(self.engine.store.read(), ref(proposal)))
        source(self.engine, content=SOURCE + " updated")
        state = self.engine.store.read()
        self.assertFalse(fresh(state, ref(proposal)))
        self.assertEqual(self.engine.status()["quality"]["reports"]["literature"]["status"], "stale")
        with self.assertRaises(ContractError):
            self.engine.review(record, "another-critic")

    def test_new_report_needs_new_review(self):
        record = self.setup_report()
        self.engine.review(record, "critic")
        report(self.engine, self.source, content=GOOD + " new sentence")
        self.assertEqual(self.engine.status()["quality"]["reports"]["literature"]["status"], "unreviewed")

    def test_repair_task_does_not_close_finding(self):
        self.setup_report(content=BAD)
        self.engine.review(review_record(self.engine.store.read(), self.report, bad=True), "critic")
        state = self.engine.store.read()
        task = next(t for t in state["tasks"].values() if t["action"] == "repair")
        finding = next(iter(state["findings"].values()))
        self.engine.claim(task["id"], "repairer")
        self.engine.submit(task["id"], "repairer", {"status": "completed", "summary": "修复",
            "artifacts": [{"key": "literature", "kind": "literature", "content": GOOD}]})
        state = self.engine.store.read()
        self.assertEqual(state["findings"][finding["id"]]["status"], "open")
        new = state["artifacts"]["literature"][-1]
        record = review_record(state, new)
        record["resolutions"] = [{"finding_id": finding["id"], "disposition": "resolved",
                                   "reason": "复核新版本", "evidence": record["probes"][0]["evidence"]}]
        self.engine.review(record, "critic")
        self.assertTrue(self.engine.status()["quality"]["ready"])

    def test_unclosed_old_findings_block_new_good_review(self):
        self.setup_report(content=BAD)
        self.engine.review(review_record(self.engine.store.read(), self.report, bad=True), "critic")
        new = report(self.engine, self.source)
        self.engine.review(review_record(self.engine.store.read(), new), "critic")
        self.assertFalse(self.engine.status()["quality"]["ready"])

    def test_same_version_cannot_claim_repair(self):
        self.setup_report(content=BAD)
        self.engine.review(review_record(self.engine.store.read(), self.report, bad=True), "critic")
        state = self.engine.store.read()
        record = review_record(state, self.report)
        record["resolutions"] = [{"finding_id": next(iter(state["findings"])), "disposition": "resolved",
                                   "reason": "没有改过", "evidence": record["probes"][0]["evidence"]}]
        with self.assertRaises(ContractError):
            self.engine.review(record, "critic")

    def test_restore_preserves_history_without_old_clearance(self):
        record = self.setup_report()
        self.engine.review(record, "critic")
        checkpoint(self.engine, "v1", "合成基线")
        report(self.engine, self.source, content=BAD)
        restored = restore(self.engine, "literature", 1, "maintainer", "撤回错误")
        self.assertEqual(restored["version"], 3)
        self.assertEqual(self.engine.status()["quality"]["reports"]["literature"]["status"], "unreviewed")
        self.assertIn("直接使用", compare(self.engine, "literature", 1, 2)["diff"])
        state = self.engine.store.read()
        self.assertEqual(len(state["checkpoints"]), 1)
        self.assertEqual(len(state["reviews"]), 1)

    def test_restore_old_evidence_remains_stale(self):
        self.setup_report()
        source(self.engine, content=SOURCE + "new")
        restore(self.engine, "literature", 1, "maintainer", "追溯")
        self.assertEqual(self.engine.status()["quality"]["reports"]["literature"]["status"], "stale")

    def test_stale_pending_tasks_cancelled(self):
        old = source(self.engine)
        task = self.engine.add_task("reader", "read", "understand", [ref(old)])
        source(self.engine, content=SOURCE + "new")
        self.engine.maintain()
        self.assertEqual(self.engine.store.read()["tasks"][task["id"]]["status"], "cancelled")

    def test_event_tampering_detected(self):
        with sqlite3.connect(self.engine.store.database) as connection:
            connection.execute("UPDATE events SET body='{}' WHERE seq=1")
        with self.assertRaises(ContractError):
            self.engine.store.read()

    def test_blob_tampering_detected(self):
        item = source(self.engine)
        (self.engine.store.internal / "blobs" / item["sha256"]).write_text("tamper")
        with self.assertRaises(ContractError):
            self.engine.store.audit()

    def test_output_edit_not_treated_as_reviewed_version(self):
        self.setup_report()
        path = self.engine.store.root / "outputs" / "文献调研.md"
        path.write_text("unregistered")
        self.assertIn(str(path), self.engine.store.audit()["changed_or_missing_exports"])
        exported = self.engine.store.export()
        self.assertIn(str(path), exported["conflicts"])
        self.assertEqual(path.read_text(), "unregistered")

    def test_duplicate_report_key_rejected(self):
        self.setup_report()
        with self.assertRaises(ContractError):
            report(self.engine, self.source, key="another-literature")

    def test_known_source_not_same_as_report(self):
        task = self.engine.store.read()["tasks"]
        task_id = next(iter(task))
        self.engine.claim(task_id, "planner")
        with self.assertRaises(ContractError):
            self.engine.submit(task_id, "planner", {"status": "completed", "summary": "empty"})

    def test_reviewer_cannot_write_report(self):
        self.setup_report()
        self.engine.maintain()
        task = next(t for t in self.engine.store.read()["tasks"].values() if t["role"] == "reviewer")
        self.engine.claim(task["id"], "critic")
        with self.assertRaises(ContractError):
            self.engine.submit(task["id"], "critic", {"status": "completed", "summary": "代写",
                "artifacts": [{"key": "literature", "kind": "literature", "content": GOOD}]})

    def test_interrupted_work_not_automatically_retried(self):
        task = next(iter(self.engine.store.read()["tasks"]))
        self.engine.claim(task, "planner")
        result = run(self.engine, {"workers": {}}, max_tasks=1)
        self.assertEqual(result["run_status"], "needs-reconciliation")

    def test_missing_worker_does_not_fake_completion(self):
        result = run(self.engine, {"workers": {}}, max_tasks=1)
        self.assertEqual(result["run_status"], "missing-worker")
        self.assertFalse(result["quality"]["ready"])

    def test_team_requires_distinct_reviewer_identity(self):
        path = self.root / "team.json"
        path.write_text(json.dumps({"protocol": VERSION, "workers": {
            "leader": {"id": "same", "command": ["tool"]},
            "reviewer": {"id": "same", "command": ["tool"], "context_isolation": "fresh-process"}}}))
        with self.assertRaises(ContractError):
            load_team(path)

    def test_real_process_synthetic_two_loop_integration(self):
        engine = Engine(self.root / "both")
        engine.initialize("只用于集成验证的合成主题", "both")
        workers = {role: {"id": role, "command": [sys.executable, "-m", "rsi.tests.fake_worker"],
                          "context_isolation": "fresh-process"}
                   for role in ("leader", "searcher", "reader", "synthesizer", "designer", "reviewer")}
        result = run(engine, {"workers": workers}, max_tasks=16)
        self.assertEqual(result["run_status"], "review-cleared", result)
        state = engine.store.read()
        self.assertEqual(len(state["artifacts"]["literature"]), 2)
        self.assertEqual(len(state["artifacts"]["proposal"]), 1)
        self.assertEqual(next(iter(state["findings"].values()))["status"], "resolved")
        self.assertTrue(state["systems"])
        self.assertEqual(engine.store.audit()["changed_or_missing_exports"], [])

    def test_budget_stop_not_quality_pass(self):
        workers = {"leader": {"id": "planner", "command": [sys.executable, "-m", "rsi.tests.fake_worker"]}}
        result = run(self.engine, {"workers": workers}, max_tasks=1)
        self.assertEqual(result["run_status"], "paused-budget")
        self.assertFalse(result["quality"]["ready"])

    def test_parallel_writers_cannot_silently_overwrite(self):
        original = source(self.engine)
        a = self.engine.add_task("synthesizer", "draft A", "source grounded", [ref(original)])
        b = self.engine.add_task("synthesizer", "draft B", "source grounded", [ref(original)])
        self.engine.claim(a["id"], "author-a")
        self.engine.claim(b["id"], "author-b")
        response = {"status": "completed", "summary": "draft", "artifacts": [
            {"key": "literature", "kind": "literature", "content": GOOD}]}
        self.engine.submit(a["id"], "author-a", response)
        with self.assertRaises(ContractError):
            self.engine.submit(b["id"], "author-b", response)
        self.assertEqual(len(self.engine.store.read()["artifacts"]["literature"]), 1)

    def test_figures_export_as_versioned_assets(self):
        original = source(self.engine)
        figure = self.engine.capture({"key": "method", "kind": "figure", "title": "合成图",
            "content": '<svg xmlns="http://www.w3.org/2000/svg"/>', "parents": [ref(original)],
            "metadata": {"format": "svg", "caption": "合成测试不是作者原图"}}, "reader")
        self.assertTrue((self.engine.store.root / "outputs/assets/method-v1.svg").is_file())
        self.assertEqual(figure["parents"], [ref(original)])
        image = self.engine.store.root / "outputs/assets/method-v1.svg"
        image.write_text("user image edit")
        self.assertIn(str(image), self.engine.store.export()["conflicts"])
        self.assertEqual(image.read_text(), "user image edit")
        self.assertIn(str(image), self.engine.store.audit()["changed_or_missing_exports"])


if __name__ == "__main__":
    unittest.main()
