#!/usr/bin/env python3
"""Q-HIST v8 E0 只读审计器的纯函数测试。"""

from __future__ import annotations

import unittest

from qhist_audit_e0 import family_equal_mean, first_post_v


class QHistE0AuditTests(unittest.TestCase):
    def test_family_equal_mean_does_not_overweight_variants(self) -> None:
        point, families = family_equal_mean(
            [("a", 0.0), ("a", 1.0), ("a", 1.0), ("b", 0.0)]
        )
        self.assertAlmostEqual(families["a"], 2.0 / 3.0)
        self.assertAlmostEqual(families["b"], 0.0)
        self.assertAlmostEqual(point, 1.0 / 3.0)

    def test_first_post_v_uses_distance_plus_one_boundary(self) -> None:
        unit = {
            "unit": {"unit_id": "x", "distance": 3},
            "decisions": [
                {"decision_index": 1, "phase": "pre-correction", "v_score": 1.0},
                {"decision_index": 2, "phase": "pre-correction", "v_score": 0.5},
                {"decision_index": 3, "phase": "pre-correction", "v_score": 0.5},
                {"decision_index": 4, "phase": "post-correction", "v_score": 0.25},
                {"decision_index": 5, "phase": "post-correction", "v_score": 0.0},
                {"decision_index": 6, "phase": "post-correction", "v_score": 0.0},
            ],
        }
        self.assertEqual(first_post_v(unit), 0.25)

    def test_first_post_v_rejects_misaligned_horizon(self) -> None:
        unit = {
            "unit": {"unit_id": "x", "distance": 1},
            "decisions": [
                {"decision_index": 1, "phase": "pre-correction", "v_score": 1.0},
                {"decision_index": 2, "phase": "post-correction", "v_score": 0.0},
            ],
        }
        with self.assertRaises(RuntimeError):
            first_post_v(unit)


if __name__ == "__main__":
    unittest.main()
