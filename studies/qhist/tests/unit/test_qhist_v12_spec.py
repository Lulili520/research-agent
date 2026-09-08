import unittest

import qhist_v12_spec as spec


class V12SpecTests(unittest.TestCase):
    def test_frozen_counts(self):
        summary = spec.validate_frozen_design()
        self.assertEqual(summary["scientific_trajectories"], 168)
        self.assertEqual(summary["technical_repeat_trajectories"], 24)
        self.assertEqual(summary["trajectory_units_total"], 192)
        self.assertEqual(summary["unique_model_requests"], 768)
        self.assertEqual(
            summary["precision_trajectory_counts"],
            {"P00": 84, "P10": 24, "P01": 24, "P11": 60},
        )

    def test_split_is_family_disjoint(self):
        development = {
            spec.normalize_family(row["scenario"])
            for row in spec.DEVELOPMENT_SCENARIOS
        }
        confirmatory = {
            spec.normalize_family(name) for name in spec.CONFIRMATORY_SCENARIOS
        }
        self.assertEqual(len(development), 3)
        self.assertEqual(len(confirmatory), 8)
        self.assertFalse(development & confirmatory)

    def test_repeats_do_not_change_logical_cell(self):
        repeats = spec.build_technical_repeat_units()
        self.assertTrue(all(row["repeat"] in {2, 3} for row in repeats))
        cells = {
            (
                row["episode_id"], row["precision"], row["module"],
                row["condition"], row["gap"],
            )
            for row in repeats
        }
        self.assertEqual(len(cells), 12)


if __name__ == "__main__":
    unittest.main()
