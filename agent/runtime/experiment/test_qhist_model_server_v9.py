import unittest
from unittest.mock import patch

import qhist_model_server_v9 as server


class QHistModelServerV9Tests(unittest.TestCase):
    def test_summary_rebinds_only_protocol_version(self):
        parent = server.InferenceStateV9.__mro__[1]
        payload = {"status": "succeeded", "protocol_version": 8, "precision": "P00"}
        state = object.__new__(server.InferenceStateV9)
        with patch.object(parent, "summary", return_value=dict(payload)):
            result = state.summary()
        self.assertEqual(result["protocol_version"], 9)
        self.assertEqual(result["status"], "succeeded")
        self.assertEqual(result["precision"], "P00")


if __name__ == "__main__":
    unittest.main()
