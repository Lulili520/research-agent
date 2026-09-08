import unittest

import qhist_v9_spec as spec


class QHistV9SpecTests(unittest.TestCase):
    def test_counts_and_request_counts(self):
        design = spec.validate_frozen_design()
        self.assertEqual(design["scientific_trajectories"], 128)
        self.assertEqual(design["technical_repeat_trajectories"], 32)
        self.assertEqual(design["treatment_trajectories"], 160)
        self.assertEqual(design["total_e0_units"], 190)
        self.assertEqual(
            design["precision_trajectory_counts"],
            {"P00": 96, "P10": 16, "P01": 16, "P11": 32},
        )
        self.assertEqual(
            design["precision_request_counts"],
            {"P00": 496, "P10": 96, "P01": 96, "P11": 192},
        )

    def test_repeats_do_not_duplicate_scientific_ids(self):
        scientific = spec.build_scientific_trajectory_units()
        repeats = spec.build_technical_repeat_units()
        self.assertFalse(
            {row["unit_id"] for row in scientific}
            & {row["unit_id"] for row in repeats}
        )
        self.assertTrue(all(row["repeat"] in (2, 3) for row in repeats))
        self.assertTrue(all(row["technical_repeat"] for row in repeats))

    def test_contract_is_condition_invariant_text(self):
        self.assertNotIn("P00", spec.AGENT_TOOL_CONTRACT)
        self.assertNotIn("quant", spec.AGENT_TOOL_CONTRACT.lower())
        self.assertNotIn("correction", spec.AGENT_TOOL_CONTRACT.lower())
        self.assertIn("calling the available tools", spec.AGENT_TOOL_CONTRACT)


if __name__ == "__main__":
    unittest.main()
