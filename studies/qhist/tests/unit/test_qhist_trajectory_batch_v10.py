import unittest

import qhist_trajectory_batch_v10 as runner


class QHistV10TrajectoryTests(unittest.TestCase):
    def test_error_action_respects_same_reply_blocker(self):
        predicate = {
            "tool": "set_cellular_service_status",
            "arguments_contains": {"on": True},
            "when_environment": {"SETTING.low_battery_mode": True},
            "unless_preceded_by": {
                "tool": "set_low_battery_mode_status",
                "arguments_contains": {"on": False},
            },
        }
        candidate = {
            "name": "set_cellular_service_status",
            "arguments": {"on": True},
        }
        environment = {"SETTING.low_battery_mode": True}
        self.assertTrue(runner.is_error_action(candidate, predicate, environment, []))
        self.assertFalse(
            runner.is_error_action(
                candidate,
                predicate,
                environment,
                [
                    {
                        "name": "set_low_battery_mode_status",
                        "arguments": {"on": False},
                    }
                ],
            )
        )

    def test_ordered_oracle_requires_successful_order(self):
        oracle = {
            "ordered_actions": [
                {"tool": "first", "arguments_contains": {"x": 1}},
                {"tool": "second", "arguments_contains": {"y": 2}},
            ]
        }
        actions = [
            {"name": "second", "arguments": {"y": 2}},
            {"name": "first", "arguments": {"x": 1}},
        ]
        self.assertEqual(runner.oracle_progress(actions, oracle), (False, 1))
        actions.append({"name": "second", "arguments": {"y": 2}})
        self.assertEqual(runner.oracle_progress(actions, oracle), (True, 2))

    def test_truth_verification_requires_success_and_matching_result(self):
        action = {"name": "get_flag", "arguments": {}}
        frozen = {
            "tool": "get_flag",
            "arguments_contains": {},
            "expected_result": True,
        }
        self.assertTrue(
            runner.successful_truth_verification(
                action, {"content": "True", "exception": None}, frozen
            )
        )
        self.assertFalse(
            runner.successful_truth_verification(
                action, {"content": "False", "exception": None}, frozen
            )
        )
        self.assertFalse(
            runner.successful_truth_verification(
                action, {"content": "True", "exception": "failure"}, frozen
            )
        )
        self.assertFalse(
            runner.successful_truth_verification(
                action, {"content": "unparseable", "exception": None}, frozen
            )
        )


if __name__ == "__main__":
    unittest.main()
