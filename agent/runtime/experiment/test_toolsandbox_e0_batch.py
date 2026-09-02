import unittest

from toolsandbox_e0_batch import build_schedule, paired_execution_seed


class E0BatchDesignTests(unittest.TestCase):
    def setUp(self) -> None:
        self.rows = [
            {"episode_id": f"E0-{episode:02d}", "condition": condition}
            for episode in range(1, 25)
            for condition in ("S+E+", "S-E+", "S+E-", "S-E-")
        ]

    def test_schedule_is_complete_unique_and_deterministic(self) -> None:
        first = build_schedule(self.rows, 2026090200)
        second = build_schedule(self.rows, 2026090200)
        self.assertEqual(first, second)
        self.assertEqual(len(first), 96)
        self.assertEqual(
            len({(row["episode_id"], row["condition"]) for row in first}), 96
        )
        self.assertNotEqual(first, self.rows)

    def test_all_conditions_in_episode_share_execution_seed(self) -> None:
        seeds = {
            paired_execution_seed(2026090200, row["episode_id"])
            for row in self.rows
            if row["episode_id"] == "E0-07"
        }
        self.assertEqual(seeds, {2026090207})

    def test_rejects_duplicate_or_incomplete_manifest(self) -> None:
        with self.assertRaises(RuntimeError):
            build_schedule(self.rows[:-1] + [self.rows[0]], 1)


if __name__ == "__main__":
    unittest.main()
