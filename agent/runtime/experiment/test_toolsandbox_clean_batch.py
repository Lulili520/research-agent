import unittest

from toolsandbox_clean_batch import build_schedule


class CleanBatchTests(unittest.TestCase):
    def test_requires_24_unique_episodes_and_is_deterministic(self) -> None:
        rows = [{"episode_id": f"E0-{number:02d}", "scenario": f"s{number}"} for number in range(1, 25)]
        self.assertEqual(build_schedule(rows, 7), build_schedule(rows, 7))
        self.assertNotEqual(build_schedule(rows, 7), rows)
        with self.assertRaises(RuntimeError):
            build_schedule(rows[:-1] + [rows[0]], 7)


if __name__ == "__main__":
    unittest.main()
