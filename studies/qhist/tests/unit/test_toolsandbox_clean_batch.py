import unittest

from toolsandbox_clean_batch import build_schedule, unit_qualified


class CleanBatchTests(unittest.TestCase):
    def test_requires_24_unique_episodes_and_is_deterministic(self) -> None:
        rows = [{"episode_id": f"E0-{number:02d}", "scenario": f"s{number}"} for number in range(1, 25)]
        self.assertEqual(build_schedule(rows, 7), build_schedule(rows, 7))
        self.assertNotEqual(build_schedule(rows, 7), rows)
        with self.assertRaises(RuntimeError):
            build_schedule(rows[:-1] + [rows[0]], 7)

    def test_qualification_threshold_boundaries(self) -> None:
        unit = {
            "status": "succeeded",
            "native_tool_call_count": 1,
            "tool_call_exception_count": 0,
            "evaluation": {
                "similarity": 0.75,
                "minefield_similarity": 0,
                "milestone_mapping": {"0": [3, 1.0], "1": [5, 0.5]},
            },
        }
        self.assertTrue(unit_qualified(0, unit))
        unit["evaluation"]["similarity"] = 0.749999
        self.assertFalse(unit_qualified(0, unit))
        unit["evaluation"]["similarity"] = 0.75
        unit["evaluation"]["milestone_mapping"]["1"][1] = 0.499999
        self.assertFalse(unit_qualified(0, unit))

    def test_qualification_rejects_errors_minefields_and_no_tools(self) -> None:
        base = {
            "status": "succeeded",
            "native_tool_call_count": 1,
            "tool_call_exception_count": 0,
            "evaluation": {
                "similarity": 1.0,
                "minefield_similarity": 0,
                "milestone_mapping": {"0": [3, 1.0]},
            },
        }
        self.assertFalse(unit_qualified(1, base))
        base["evaluation"]["minefield_similarity"] = 0.1
        self.assertFalse(unit_qualified(0, base))
        base["evaluation"]["minefield_similarity"] = 0
        base["native_tool_call_count"] = 0
        self.assertFalse(unit_qualified(0, base))
        base["native_tool_call_count"] = 1
        base["tool_call_exception_count"] = 1
        self.assertFalse(unit_qualified(0, base))


if __name__ == "__main__":
    unittest.main()
