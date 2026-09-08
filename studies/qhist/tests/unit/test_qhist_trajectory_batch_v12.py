import unittest

import qhist_trajectory_batch_v12 as runner


class V12StateMachineTests(unittest.TestCase):
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


if __name__ == "__main__":
    unittest.main()
