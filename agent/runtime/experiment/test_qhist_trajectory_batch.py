import unittest
import hashlib
import json
import tempfile
from pathlib import Path

from qhist_trajectory_batch import (
    action_matches,
    build_schedule,
    ordered_oracle_progress,
    verify_manifest,
)


class QHistTrajectoryBatchTests(unittest.TestCase):
    def test_schedule_is_deterministic_and_episode_blocked(self) -> None:
        units = []
        for episode in range(8):
            for history in ("N", "E", "S", "C_text", "C_align"):
                for distance in (1, 3):
                    units.append(
                        {
                            "unit_id": f"u-{episode}-{history}-{distance}",
                            "episode_id": f"e-{episode}",
                            "precision": "P00",
                        }
                    )
        first = build_schedule(units, "P00", 9)
        second = build_schedule(units, "P00", 9)
        self.assertEqual(first, second)
        positions = {}
        for index, row in enumerate(first):
            positions.setdefault(row["episode_id"], []).append(index)
        self.assertTrue(
            all(max(values) - min(values) == 9 for values in positions.values())
        )

    def test_action_predicate_checks_arguments_and_environment(self) -> None:
        action = {"name": "set_wifi_status", "arguments": {"on": True}}
        predicate = {
            "tool": "set_wifi_status",
            "arguments_contains": {"on": True},
            "when_environment": {"SETTING.low_battery_mode": True},
        }
        self.assertTrue(
            action_matches(action, predicate, {"SETTING.low_battery_mode": True})
        )
        self.assertFalse(action_matches(action, predicate, {}))

    def test_ordered_oracle_progress_is_subsequence(self) -> None:
        actions = [
            {"name": "inspect", "arguments": {}},
            {"name": "disable", "arguments": {}},
            {"name": "enable", "arguments": {}},
        ]
        self.assertTrue(
            ordered_oracle_progress(
                actions, {"ordered_tools": ["disable", "enable"]}
            )
        )

    def test_manifest_verification_rejects_hash_drift(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "data.txt").write_text("stable", encoding="utf-8")
            digest = hashlib.sha256(b"stable").hexdigest()
            (root / "manifest.json").write_text(
                json.dumps(
                    {
                        "protocol_version": 8,
                        "all_checks_pass": True,
                        "files": [{"path": "data.txt", "sha256": digest}],
                    }
                ),
                encoding="utf-8",
            )
            verify_manifest(root, require_checks=True)
            (root / "data.txt").write_text("drift", encoding="utf-8")
            with self.assertRaises(RuntimeError):
                verify_manifest(root, require_checks=True)

if __name__ == "__main__":
    unittest.main()
