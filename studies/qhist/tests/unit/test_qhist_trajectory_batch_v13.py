import unittest

import qhist_trajectory_batch_v13 as runner
import qhist_v13_spec as spec


class V13StateMachineTests(unittest.TestCase):
    def test_casefold_argument_and_binding_match(self):
        predicate = {
            "tool": "add_reminder",
            "arguments_contains": {"reminder_timestamp": 10.0},
            "arguments_casefold": {"content": "buy chocolate milk"},
        }
        self.assertTrue(
            runner.predicate_matches(
                {
                    "name": "add_reminder",
                    "arguments": {
                        "content": "Buy Chocolate Milk",
                        "reminder_timestamp": 10.0,
                    },
                },
                predicate,
                {},
            )
        )
        self.assertFalse(
            runner.predicate_matches(
                {"name": "add_reminder", "arguments": {"content": "milk", "reminder_timestamp": 10.0}},
                predicate,
                {},
            )
        )

    def test_environment_blocker_prevents_false_positive(self):
        predicate = {
            "tool": "set_wifi_status",
            "arguments_contains": {"on": True},
            "when_environment": {"SETTING.low_battery_mode": True},
            "unless_preceded_by": {
                "tool": "set_low_battery_mode_status",
                "arguments_contains": {"on": False},
            },
        }
        candidate = {"name": "set_wifi_status", "arguments": {"on": True}}
        self.assertTrue(
            runner.error_action(
                candidate,
                predicate,
                {"SETTING.low_battery_mode": True},
                [],
                [],
                {},
            )
        )
        self.assertFalse(
            runner.error_action(
                candidate,
                predicate,
                {"SETTING.low_battery_mode": True},
                [{"name": "set_low_battery_mode_status", "arguments": {"on": False}}],
                [{"exception": None}],
                {},
            )
        )

    def test_route_uses_order_and_detects_relapse(self):
        self.assertEqual(
            runner.route([
                {"F": False, "V": True, "G": False},
                {"F": False, "V": False, "G": True},
            ]),
            "verify-then-recover",
        )
        self.assertEqual(
            runner.route([
                {"F": False, "V": False, "G": True},
                {"F": True, "V": False, "G": False},
            ]),
            "recover-then-relapse",
        )

    def test_uuid_key_excludes_precision_and_repeat_by_construction(self):
        row_a = {
            "episode_id": "E1", "module": "R", "condition": "R_fact",
            "gap": 3, "precision": "P00", "repeat": 1,
        }
        row_b = dict(row_a, precision="P11", repeat=3)
        self.assertEqual(runner.logical_key(row_a), runner.logical_key(row_b))

    def test_schedule_adds_only_separate_order_metadata(self):
        units = spec.build_trajectory_units()
        expected = {
            row["unit_id"]: spec.scientific_unit_identity(row)
            for row in units if row["precision"] == "P00"
        }
        scheduled = runner.build_schedule(units, "P00", spec.SCHEDULE_SEED)
        self.assertEqual(
            [row["execution_order"] for row in scheduled],
            list(range(1, len(scheduled) + 1)),
        )
        self.assertEqual(len({row["unit_id"] for row in scheduled}), len(scheduled))
        for row in scheduled:
            self.assertEqual(
                spec.scientific_unit_identity(row), expected[row["unit_id"]]
            )
            self.assertEqual(
                spec.schedule_metadata(row),
                {"execution_order": row["execution_order"]},
            )


if __name__ == "__main__":
    unittest.main()
