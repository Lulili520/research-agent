import unittest

import qhist_audit_e0_v11 as audit


class QHistV11AuditTests(unittest.TestCase):
    def test_truth_verification_requires_exact_return_value(self):
        action = {"name": "lookup", "arguments": {"key": "k"}}
        frozen = {
            "tool": "lookup",
            "arguments_contains": {"key": "k"},
            "expected_result": {"value": 7},
        }
        self.assertTrue(
            audit.independent_truth_verification(
                action,
                {"content": "{'value': 7}", "exception": None},
                frozen,
                {},
            )
        )
        self.assertFalse(
            audit.independent_truth_verification(
                action,
                {"content": "{'value': 8}", "exception": None},
                frozen,
                {},
            )
        )

    def test_dynamic_binding_is_not_wildcarded(self):
        frozen = {
            "tool": "modify",
            "binding_argument": {
                "binding": "error_entity_id",
                "argument": "entity_id",
            },
        }
        self.assertTrue(
            audit.independent_action_matches(
                {"name": "modify", "arguments": {"entity_id": "wrong-id"}},
                frozen,
                {},
                {"error_entity_id": "wrong-id"},
            )
        )
        self.assertFalse(
            audit.independent_action_matches(
                {"name": "modify", "arguments": {"entity_id": "other-id"}},
                frozen,
                {},
                {"error_entity_id": "wrong-id"},
            )
        )

    def test_family_equal_mean_prevents_episode_count_weighting(self):
        overall, families = audit.family_equal_mean(
            [("large", 1.0), ("large", 1.0), ("small", 0.0)]
        )
        self.assertEqual(families, {"large": 1.0, "small": 0.0})
        self.assertEqual(overall, 0.5)


if __name__ == "__main__":
    unittest.main()
