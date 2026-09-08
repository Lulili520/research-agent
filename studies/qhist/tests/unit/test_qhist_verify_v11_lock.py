import json
import tempfile
import unittest
from pathlib import Path

import qhist_verify_v11_lock as verifier


class QHistVerifyV11LockTests(unittest.TestCase):
    def test_detects_code_and_deterministic_id_gate_drift(self):
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            code = root / "code"
            runs = root / "runs"
            code.mkdir()
            for directory in ("assets", "rendered", "tool", "driver", "id"):
                (runs / directory).mkdir(parents=True)
            targets = [
                code / "x.py",
                runs / "assets" / "manifest.json",
                runs / "rendered" / "manifest.json",
                runs / "tool" / "report.json",
                runs / "driver" / "report.json",
                runs / "id" / "report.json",
            ]
            for path in targets:
                path.write_text("frozen\n", encoding="utf-8")
            digest = verifier.sha256_file(targets[0])
            lock = {
                "protocol_id": "QHIST-EXP",
                "protocol_version": 11,
                "code_sha256": {"x.py": digest},
                "frozen_inputs": {
                    "assets": "assets",
                    "assets_manifest_sha256": digest,
                    "rendered": "rendered",
                    "rendered_manifest_sha256": digest,
                    "toolsandbox_gate": "tool/report.json",
                    "toolsandbox_gate_sha256": digest,
                    "driver_gate": "driver/report.json",
                    "driver_gate_sha256": digest,
                    "deterministic_id_gate": "id/report.json",
                    "deterministic_id_gate_sha256": digest,
                },
            }
            lock_path = root / "lock.json"
            lock_path.write_text(json.dumps(lock), encoding="utf-8")
            self.assertTrue(verifier.verify(lock_path, code, runs)["passed"])
            (runs / "id" / "report.json").write_text("drift\n", encoding="utf-8")
            self.assertFalse(verifier.verify(lock_path, code, runs)["passed"])


if __name__ == "__main__":
    unittest.main()
