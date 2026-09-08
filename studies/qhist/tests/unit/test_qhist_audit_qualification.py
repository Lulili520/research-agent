import unittest

from qhist_audit_qualification import k4_evidence_is_real


class QHistQualificationAuditTests(unittest.TestCase):
    def test_k4_runtime_evidence_requires_payload_and_metadata(self) -> None:
        evidence = {
            "layer0": {
                "nbits": 4,
                "axis_key": 1,
                "axis_value": 1,
                "q_group_size": 64,
                "residual_length": 1,
                "_quantized_keys": {
                    "payload": {"dtype": "torch.uint8"},
                    "meta": {"nbits": "4", "axis": "1", "group_size": "64"},
                },
                "_quantized_values": {
                    "payload": {"dtype": "torch.uint8"},
                    "meta": {"nbits": "4", "axis": "1", "group_size": "64"},
                },
            }
        }
        self.assertTrue(k4_evidence_is_real(evidence))
        evidence["layer0"]["_quantized_keys"]["payload"]["dtype"] = "torch.bfloat16"
        self.assertFalse(k4_evidence_is_real(evidence))


if __name__ == "__main__":
    unittest.main()
