import json
import tempfile
import unittest
from pathlib import Path

import qhist_combine_trajectory_batch_v9 as combine


class QHistCombineV9Tests(unittest.TestCase):
    def test_expected_p11_counts(self):
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            server = root / "server.json"
            driver = root / "driver.json"
            server.write_text(
                json.dumps(
                    {
                        "status": "succeeded",
                        "protocol_version": 9,
                        "precision": "P11",
                        "request_count": 192,
                        "failed_request_count": 0,
                        "gpu_resident_seconds": 10,
                    }
                ),
                encoding="utf-8",
            )
            driver.write_text(
                json.dumps(
                    {
                        "status": "succeeded",
                        "protocol_version": 9,
                        "precision": "P11",
                        "completed_units": 32,
                        "succeeded_units": 32,
                    }
                ),
                encoding="utf-8",
            )
            result = combine.combine("P11", server, driver)
            self.assertEqual(result["status"], "succeeded")
            self.assertEqual(result["expected_units"], 32)
            self.assertEqual(result["expected_model_requests"], 192)


if __name__ == "__main__":
    unittest.main()
