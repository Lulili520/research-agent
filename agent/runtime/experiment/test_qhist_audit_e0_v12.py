import unittest

import qhist_audit_e0_v12 as audit


class QHistV12AuditTests(unittest.TestCase):
    def test_schema_validation_rejects_bool_as_integer_and_extra_field(self):
        schema = {
            "type": "object",
            "properties": {"count": {"type": "integer"}},
            "required": ["count"],
            "additionalProperties": False,
        }
        self.assertEqual(audit.validate_json({"count": 2}, schema), [])
        self.assertTrue(audit.validate_json({"count": True}, schema))
        self.assertTrue(audit.validate_json({"count": 2, "extra": 1}, schema))

    def test_action_match_requires_binding_and_supports_casefold(self):
        predicate = {
            "tool": "modify_reminder",
            "arguments_casefold": {"content": "Buy Chocolate Milk"},
            "binding_argument": {
                "binding": "error_entity_id",
                "argument": "reminder_id",
            },
        }
        action = {
            "name": "modify_reminder",
            "arguments": {
                "content": "buy chocolate milk",
                "reminder_id": "opaque-id",
            },
        }
        self.assertTrue(
            audit.action_matches(action, predicate, {"error_entity_id": "opaque-id"})
        )
        self.assertFalse(audit.action_matches(action, predicate, {}))

    def test_route_distinguishes_direct_recovery_and_relapse(self):
        direct = [
            {"F": False, "V": False, "G": True},
            {"F": False, "V": False, "G": False},
        ]
        relapse = [
            {"F": False, "V": True, "G": False},
            {"F": True, "V": False, "G": False},
        ]
        self.assertEqual(audit.route(direct), "direct-use")
        self.assertEqual(audit.route(relapse), "recover-then-relapse")

    def test_family_equal_mean_does_not_overweight_large_family(self):
        rows = [
            {"unit": {"family": "large"}, "score": 1.0},
            {"unit": {"family": "large"}, "score": 1.0},
            {"unit": {"family": "small"}, "score": 0.0},
        ]
        self.assertEqual(audit.family_equal(rows, "score"), 0.5)

    def test_current_rows_uses_latest_snapshot_only(self):
        snapshot = {
            "_dbs": {
                "SETTING": [
                    {"sandbox_message_index": 1, "device_id": "d", "wifi": False},
                    {"sandbox_message_index": 2, "device_id": "d", "wifi": True},
                ]
            }
        }
        rows = audit.current_rows(snapshot, "SETTING")
        self.assertEqual(len(rows), 1)
        self.assertTrue(rows[0]["wifi"])


if __name__ == "__main__":
    unittest.main()
