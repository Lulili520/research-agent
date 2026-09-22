from copy import deepcopy
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from rsi.runtime.contracts import ContractError, digest
from rsi.runtime.history import VersionLibrary


class HistoryTests(unittest.TestCase):
    def setUp(self):
        self.temp = TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.source = self.root / "system"
        (self.source / "rsi" / "runtime").mkdir(parents=True)
        (self.source / "AGENTS.md").write_text("Synthetic instructions")
        self.code = self.source / "rsi" / "runtime" / "engine.py"
        self.code.write_text("VERSION = 1")
        self.library = VersionLibrary(self.root / "history")
        self.baseline = self.library.snapshot(self.source, "baseline", "合成基线", "author")
        self.code.write_text("VERSION = 2")
        self.candidate = self.library.snapshot(self.source, "candidate", "合成改进假设", "author", self.baseline["id"])

    def tearDown(self):
        self.temp.cleanup()

    def result(self):
        attachments = {}
        for name in ("protocol", "cases", "judge", "cost", "old-output", "new-output", "review", "mapping"):
            path = self.root / f"{name}.txt"
            path.write_text("SYNTHETIC TEST ONLY: " + name)
            attachments[name] = str(path)
        return {"baseline": self.baseline["id"], "candidate": self.candidate["id"],
                **{name + "_hash": digest(Path(attachments[name]).read_bytes()) for name in ("protocol", "cases", "judge")},
                "attachments": attachments,
                "budget": "synthetic matched budget", "budget_evidence": "cost",
                "held_out_analysis": "仅合成测试，不是真实保留集", "limitations": "验证登记机制，不验证提升",
                "decision": "adopt", "pairs": [{"case": "synthetic-1", "baseline_output": "old-output",
                    "candidate_output": "new-output", "blind_mapping": "mapping",
                    "evidence": "review", "outcome": "candidate", "critical_regression": False}]}

    def test_content_identity_not_label(self):
        with self.assertRaises(ContractError):
            self.library.snapshot(self.source, "new label", "no change", "author")

    def test_unknown_parent_rejected(self):
        self.code.write_text("VERSION = 3")
        with self.assertRaises(ContractError):
            self.library.snapshot(self.source, "third", "test", "author", "unknown")

    def test_author_cannot_self_certify(self):
        with self.assertRaises(ContractError):
            self.library.evaluate(self.result(), "author")

    def test_regression_prevents_adoption(self):
        result = self.result()
        result["pairs"][0]["critical_regression"] = True
        with self.assertRaises(ContractError):
            self.library.evaluate(result, "independent")

    def test_no_gain_prevents_adoption(self):
        result = self.result()
        result["pairs"][0]["outcome"] = "tie"
        with self.assertRaises(ContractError):
            self.library.evaluate(result, "independent")

    def test_uncertainty_is_preserved_not_passed(self):
        result = self.result()
        result["pairs"][0]["outcome"] = "uncertain"
        result["decision"] = "inconclusive"
        record = self.library.evaluate(result, "independent")
        with self.assertRaises(ContractError):
            self.library.promote(record["id"], "force adoption")

    def test_fixed_comparison_metadata_required(self):
        result = self.result()
        result["judge_hash"] = "changed evaluator"
        with self.assertRaises(ContractError):
            self.library.evaluate(result, "independent")

    def test_promotion_and_rollback_do_not_overwrite_tree(self):
        record = self.library.evaluate(self.result(), "independent")
        self.library.promote(record["id"], "synthetic decision")
        self.library.rollback(self.baseline["id"], "synthetic regression")
        self.assertEqual(self.code.read_text(), "VERSION = 2")
        self.assertEqual(self.library.records()[-1]["kind"], "rollback")
        self.assertEqual(len(self.library.records()), 5)

    def test_unaccepted_candidate_cannot_be_activated_by_rollback(self):
        with self.assertRaises(ContractError):
            self.library.rollback(self.candidate["id"], "bypass review")

    def test_checkout_reconstructs_exact_version(self):
        destination = self.root / "isolated"
        self.library.checkout(self.baseline["id"], destination)
        self.assertEqual((destination / "rsi/runtime/engine.py").read_text(), "VERSION = 1")
        with self.assertRaises(ContractError):
            self.library.checkout(self.candidate["id"], destination)

    def test_audit_detects_missing_system_blob(self):
        checksum = self.baseline["files"]["rsi/runtime/engine.py"]
        (self.library.root / "blobs" / checksum).unlink()
        with self.assertRaises(ContractError):
            self.library.audit()

    def test_old_comparison_cannot_skip_active_baseline(self):
        first = self.library.evaluate(self.result(), "independent")
        self.library.promote(first["id"], "first")
        with self.assertRaises(ContractError):
            self.library.promote(first["id"], "same comparison again")

    def test_evaluation_without_actual_outputs_rejected(self):
        result = self.result()
        result["attachments"].pop("old-output")
        with self.assertRaises(ContractError):
            self.library.evaluate(result, "independent")

    def test_evaluation_output_tampering_detected(self):
        evaluation = self.library.evaluate(self.result(), "independent")
        checksum = evaluation["attachments"]["new-output"]
        (self.library.root / "blobs" / checksum).write_text("tampered result")
        with self.assertRaises(ContractError):
            self.library.audit()


if __name__ == "__main__":
    unittest.main()
