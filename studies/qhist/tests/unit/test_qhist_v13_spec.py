import unittest
from copy import deepcopy

import qhist_v13_spec as spec


class V13SpecTests(unittest.TestCase):
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

    def test_execution_order_does_not_change_scientific_identity(self):
        unit = spec.build_trajectory_units()[0]
        first = dict(unit, execution_order=1)
        later = dict(unit, execution_order=191)
        self.assertEqual(
            spec.scientific_unit_identity(first),
            spec.scientific_unit_identity(later),
        )
        self.assertNotIn(
            "execution_order", spec.scientific_unit_identity(first)
        )

    def test_scientific_field_change_changes_identity(self):
        unit = dict(spec.build_trajectory_units()[0], execution_order=1)
        changed = deepcopy(unit)
        changed["condition"] = "counterexample-condition"
        self.assertNotEqual(
            spec.scientific_unit_identity(unit),
            spec.scientific_unit_identity(changed),
        )

    def test_schedule_metadata_requires_positive_integer(self):
        self.assertEqual(
            spec.schedule_metadata({"execution_order": 7}),
            {"execution_order": 7},
        )
        for invalid in (0, -1, True, 1.5, "1"):
            with self.assertRaises((TypeError, ValueError)):
                spec.schedule_metadata({"execution_order": invalid})
        with self.assertRaises(ValueError):
            spec.schedule_metadata({})


if __name__ == "__main__":
    unittest.main()
