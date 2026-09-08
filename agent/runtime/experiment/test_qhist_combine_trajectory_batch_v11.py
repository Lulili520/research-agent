import json
import tempfile
import unittest
from pathlib import Path

import qhist_combine_trajectory_batch_v11 as combine
import qhist_v11_spec as spec


class QHistV11CombineTests(unittest.TestCase):
    def test_combine_uses_unique_request_count_not_logical_decision_count(self):
        precision = "P00"
        expected_units = spec.expected_precision_counts()[precision]
        expected_requests = spec.expected_unique_request_counts()[precision]
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            server = root / "server.json"
            driver = root / "driver.json"
            server.write_text(
                json.dumps(
                    {
                        "status": "succeeded",
                        "protocol_version": spec.PROTOCOL_VERSION,
                        "precision": precision,
                        "request_count": expected_requests,
                        "failed_request_count": 0,
                        "gpu_resident_seconds": 12.0,
                        "generation_seconds": 10.0,
                        "weight_manifest_sha256": "a" * 64,
                    }
                ),
                encoding="utf-8",
            )
            driver.write_text(
                json.dumps(
                    {
                        "status": "succeeded",
                        "protocol_version": spec.PROTOCOL_VERSION,
                        "precision": precision,
                        "completed_logical_units": expected_units,
                        "succeeded_logical_units": expected_units,
                        "unique_model_requests": expected_requests,
                        "unique_model_request_count_ok": True,
                        "execution_design": "shared-erroneous-trunk-boundary-fork",
                    }
                ),
                encoding="utf-8",
            )
            result = combine.combine(precision, server, driver)
        self.assertEqual(result["status"], "succeeded")
        self.assertEqual(result["expected_unique_model_requests"], 300)


if __name__ == "__main__":
    unittest.main()
