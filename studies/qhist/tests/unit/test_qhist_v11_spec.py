import unittest

import qhist_v11_spec as spec


class QHistV11SpecTests(unittest.TestCase):
    def test_frozen_counts_and_fork_request_counts(self):
        design = spec.validate_frozen_design()
        self.assertEqual(design["treatment_logical_trajectories"], 120)
        self.assertEqual(design["qualification_runs"], 30)
        self.assertEqual(design["confirmatory_episodes"], 22)
        self.assertEqual(design["confirmatory_families"], 11)
        self.assertEqual(
            design["precision_unique_model_request_counts"],
            {"P00": 300, "P10": 72, "P01": 72, "P11": 144},
        )
        self.assertLess(
            design["precision_unique_model_request_counts"]["P00"],
            design["precision_logical_decision_counts"]["P00"],
        )

    def test_confirmatory_pairs_and_development_are_disjoint(self):
        confirmatory = {}
        for scenario in spec.CONFIRMATORY_SCENARIOS:
            confirmatory.setdefault(spec.normalize_family(scenario), []).append(scenario)
        development = {
            spec.normalize_family(row["scenario"])
            for row in spec.DEVELOPMENT_SCENARIOS
        }
        self.assertEqual(len(confirmatory), 11)
        self.assertTrue(all(len(items) == 2 for items in confirmatory.values()))
        self.assertFalse(development & set(confirmatory))

    def test_primary_resolution_still_distinguishes_thresholds(self):
        maximum_step = 1.0 / (11 * 2 * 2 * 4)
        self.assertLess(maximum_step, 0.01)
        self.assertAlmostEqual(maximum_step, 1.0 / 176.0)

    def test_technical_repeats_do_not_enter_scientific_sample(self):
        scientific = spec.build_scientific_trajectory_units()
        repeats = spec.build_technical_repeat_units()
        self.assertTrue(all(row["repeat"] == 1 for row in scientific))
        self.assertTrue(all(row["technical_repeat"] for row in repeats))
        self.assertFalse(
            {row["unit_id"] for row in scientific}
            & {row["unit_id"] for row in repeats}
        )


if __name__ == "__main__":
    unittest.main()
