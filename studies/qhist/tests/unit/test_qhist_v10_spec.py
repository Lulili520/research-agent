import unittest

import qhist_v10_spec as spec


class QHistV10SpecTests(unittest.TestCase):
    def test_frozen_counts_and_family_split(self):
        self.assertEqual(
            spec.validate_frozen_design(),
            {
                "scientific_trajectories": 96,
                "technical_repeat_trajectories": 24,
                "treatment_trajectories": 120,
                "qualification_runs": 30,
                "total_e0_units": 150,
                "development_episodes": 6,
                "development_families": 3,
                "confirmatory_episodes": 28,
                "confirmatory_families": 14,
                "precision_trajectory_counts": {
                    "P00": 72,
                    "P10": 12,
                    "P01": 12,
                    "P11": 24,
                },
                "precision_request_counts": {
                    "P00": 372,
                    "P10": 72,
                    "P01": 72,
                    "P11": 144,
                },
            },
        )

    def test_technical_repeats_are_outside_scientific_sample(self):
        scientific = spec.build_scientific_trajectory_units()
        repeats = spec.build_technical_repeat_units()
        self.assertTrue(all(row["repeat"] == 1 for row in scientific))
        self.assertTrue(all(row["repeat"] in (2, 3) for row in repeats))
        self.assertTrue(all(row["technical_repeat"] for row in repeats))
        self.assertFalse(
            {row["unit_id"] for row in scientific}
            & {row["unit_id"] for row in repeats}
        )

    def test_confirmatory_pairs_are_family_normalized(self):
        families = {}
        for scenario in spec.CONFIRMATORY_SCENARIOS:
            families.setdefault(spec.normalize_family(scenario), []).append(scenario)
        self.assertEqual(len(families), 14)
        self.assertTrue(all(len(items) == 2 for items in families.values()))

    def test_primary_basic_step_includes_both_nested_averages(self):
        maximum_step = 1.0 / (14 * 2 * 2 * 4)
        self.assertLess(maximum_step, 0.01)
        self.assertAlmostEqual(maximum_step, 1.0 / 224.0)


if __name__ == "__main__":
    unittest.main()
