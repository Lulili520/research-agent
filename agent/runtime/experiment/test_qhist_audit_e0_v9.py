import unittest

import qhist_audit_e0_v9 as audit


class QHistAuditV9Tests(unittest.TestCase):
    def test_pre_and_post_windows(self):
        unit = {
            "unit": {"unit_id": "x", "distance": 3},
            "decisions": [
                {"v_score": 0.0, "phase": "pre-correction"},
                {"v_score": 0.5, "phase": "pre-correction"},
                {"v_score": 1.0, "phase": "pre-correction"},
                {"v_score": 0.6, "phase": "post-correction"},
                {"v_score": 0.3, "phase": "post-correction"},
                {"v_score": 0.0, "phase": "post-correction"},
            ],
        }
        self.assertAlmostEqual(audit.pre_mean(unit), 0.5)
        self.assertAlmostEqual(audit.post_three_mean(unit), 0.3)

    def test_family_equal_not_episode_equal(self):
        value, families = audit.family_equal_mean(
            [("large", 0.0), ("large", 0.0), ("small", 1.0)]
        )
        self.assertEqual(families, {"large": 0.0, "small": 1.0})
        self.assertEqual(value, 0.5)


if __name__ == "__main__":
    unittest.main()
