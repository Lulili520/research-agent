import unittest

import qhist_trajectory_batch_v11 as runner


class QHistV11TrajectoryTests(unittest.TestCase):
    def test_error_blocker_must_have_executed_successfully(self):
        candidate = {
            "name": "set_location_service_status",
            "arguments": {"on": True},
        }
        blocker_action = {
            "name": "set_low_battery_mode_status",
            "arguments": {"on": False},
        }
        predicate = {
            "tool": "set_location_service_status",
            "arguments_contains": {"on": True},
            "when_environment": {"low_battery_mode": True},
            "unless_preceded_by": {
                "tool": "set_low_battery_mode_status",
                "arguments_contains": {"on": False},
            },
        }
        environment = {"low_battery_mode": True}
        self.assertTrue(
            runner.is_error_action(
                candidate,
                predicate,
                environment,
                [blocker_action],
                [{"exception": "failed"}],
                {},
            )
        )
        self.assertFalse(
            runner.is_error_action(
                candidate,
                predicate,
                environment,
                [blocker_action],
                [{"exception": None}],
                {},
            )
        )

    def test_binding_predicate_requires_exact_dynamic_entity(self):
        predicate = {
            "tool": "modify_reminder",
            "arguments_contains": {"reminder_timestamp": 10.0},
            "binding_argument": {
                "argument": "reminder_id",
                "binding": "error_entity_id",
            },
        }
        candidate = {
            "name": "modify_reminder",
            "arguments": {"reminder_id": "r1", "reminder_timestamp": 10.0},
        }
        self.assertTrue(
            runner.predicate_matches(
                candidate, predicate, bindings={"error_entity_id": "r1"}
            )
        )
        self.assertFalse(
            runner.predicate_matches(
                candidate, predicate, bindings={"error_entity_id": "r2"}
            )
        )
        self.assertFalse(runner.predicate_matches(candidate, predicate, bindings={}))

    def test_recovery_requires_successful_execution(self):
        candidate = {"name": "repair", "arguments": {"target": "correct"}}
        frozen = [{"tool": "repair", "arguments_contains": {"target": "correct"}}]
        self.assertTrue(
            runner.successful_frozen_action(
                candidate, {"exception": None}, frozen, {}
            )
        )
        self.assertFalse(
            runner.successful_frozen_action(
                candidate, {"exception": "failure"}, frozen, {}
            )
        )

    def test_deterministic_uuid_excludes_runtime_labels(self):
        key = runner.logical_segment_key("episode", 3, "C_text", "post")
        first = runner.DeterministicUUID4(key)
        second = runner.DeterministicUUID4(key)
        self.assertEqual([first(), first()], [second(), second()])
        other = runner.DeterministicUUID4(
            runner.logical_segment_key("episode", 3, "S", "post")
        )
        self.assertNotEqual(first(), other())

    def test_scientific_signature_excludes_post_goal_prose_not_tools(self):
        state = {
            "prefix_observation": "false",
            "correction": {
                "visible_message_sha256": "message",
                "patch": None,
            },
            "bindings": {},
            "decisions": [
                {
                    "decision_index": 1,
                    "output_class": "native-tool",
                    "attempted_actions": [{"name": "repair", "arguments": {}}],
                    "execution": [{"exception": None}],
                    "error_consistent_action": False,
                    "successful_truth_verification": False,
                    "successful_recovery_certificate": True,
                    "successful_goal_completion": True,
                    "commitment_debt": False,
                    "environment_debt": False,
                    "goal_completed": True,
                    "terminal_before_goal_completion": False,
                    "decision_signature": "repair",
                },
                {
                    "decision_index": 2,
                    "output_class": "terminal-text",
                    "attempted_actions": [],
                    "execution": [],
                    "error_consistent_action": False,
                    "successful_truth_verification": False,
                    "successful_recovery_certificate": False,
                    "successful_goal_completion": False,
                    "commitment_debt": False,
                    "environment_debt": False,
                    "goal_completed": True,
                    "terminal_before_goal_completion": False,
                    "decision_signature": "ignored-prose",
                },
                {
                    "decision_index": 3,
                    "output_class": "native-tool",
                    "attempted_actions": [{"name": "wrong", "arguments": {}}],
                    "execution": [{"exception": "blocked"}],
                    "error_consistent_action": True,
                    "successful_truth_verification": False,
                    "successful_recovery_certificate": False,
                    "successful_goal_completion": False,
                    "commitment_debt": True,
                    "environment_debt": False,
                    "goal_completed": True,
                    "terminal_before_goal_completion": False,
                    "decision_signature": "wrong",
                },
            ],
        }
        _, payload = runner.scientific_signature(state, {"dynamic_roles": {}})
        rows = payload[
            "decisions_through_first_goal_completion_plus_later_tool_actions"
        ]
        self.assertEqual([row["decision_index"] for row in rows], [1, 3])


if __name__ == "__main__":
    unittest.main()
