import unittest

import qhist_audit_e0_v10 as audit


class QHistV10AuditTests(unittest.TestCase):
    def test_independent_verifier_checks_return_value(self):
        action = {"name": "lookup", "arguments": {"key": "k"}}
        frozen = {
            "tool": "lookup",
            "arguments_contains": {"key": "k"},
            "expected_result": {"value": 7},
        }
        self.assertTrue(
            audit.independently_matches_truth_verification(
                action,
                {"content": "{'value': 7}", "exception": None},
                frozen,
            )
        )
        self.assertFalse(
            audit.independently_matches_truth_verification(
                action,
                {"content": "{'value': 8}", "exception": None},
                frozen,
            )
        )

    def test_family_equal_mean_does_not_weight_large_family_more(self):
        overall, families = audit.family_equal_mean(
            [("large", 1.0), ("large", 1.0), ("small", 0.0)]
        )
        self.assertEqual(families, {"large": 1.0, "small": 0.0})
        self.assertEqual(overall, 0.5)


if __name__ == "__main__":
    unittest.main()
