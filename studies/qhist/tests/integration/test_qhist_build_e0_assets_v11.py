import unittest

import qhist_build_e0_assets_v11 as builder


class FakeContactContext:
    class Frame:
        def to_dicts(self):
            return [
                {
                    "person_id": "true-id",
                    "name": "Fredrik Thordendal",
                    "phone_number": "+12453344098",
                    "relationship": "friend",
                    "is_self": False,
                },
                {
                    "person_id": "false-id",
                    "name": "John Petrucci",
                    "phone_number": "+1234560987",
                    "relationship": "friend",
                    "is_self": False,
                },
            ]

    def get_database(self, namespace):
        return self.Frame()


class QHistV11AssetTests(unittest.TestCase):
    def test_contact_error_changes_only_id_and_has_direct_recovery(self):
        truth = [
            {
                "person_id": "true-id",
                "name": "Fredrik Thordendal",
                "phone_number": "+12453344098",
                "relationship": "friend",
                "is_self": False,
            }
        ]
        false, meta = builder.contact_id_error(truth, FakeContactContext())
        self.assertEqual(false[0]["person_id"], "false-id")
        self.assertEqual(false[0]["phone_number"], truth[0]["phone_number"])
        self.assertEqual(meta["error_action"]["arguments_contains"]["person_id"], "false-id")
        self.assertEqual(
            meta["recovery_actions"][0]["arguments_contains"]["person_id"], "true-id"
        )
        self.assertEqual(
            meta["patch"]["operation"], "restore_baseline_row_if_missing_or_changed"
        )

    def test_absolute_time_supports_add_or_bound_modify_recovery(self):
        false, meta = builder.absolute_time_error(1711098000.0)
        self.assertEqual(false, 1711184400.0)
        self.assertEqual(len(meta["recovery_actions"]), 2)
        modify = meta["recovery_actions"][1]
        self.assertEqual(modify["tool"], "modify_reminder")
        self.assertEqual(
            modify["binding_argument"]["binding"], "error_entity_id"
        )
        self.assertEqual(
            meta["error_action"]["binds_success_result"], "error_entity_id"
        )

    def test_location_recovery_and_goal_are_distinct(self):
        false, meta = builder.location_error(True)
        self.assertIs(false, False)
        self.assertEqual(meta["recovery_actions"][0]["tool"], "set_low_battery_mode_status")
        self.assertEqual(meta["completion_actions"][0]["tool"], "set_location_service_status")
        self.assertEqual(meta["patch"]["operation"], "none")


if __name__ == "__main__":
    unittest.main()
