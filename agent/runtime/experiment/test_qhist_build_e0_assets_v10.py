import unittest

import qhist_build_e0_assets_v10 as builder
import qhist_v10_spec as spec


class FakeContactContext:
    class Frame:
        def to_dicts(self):
            return [
                {
                    "name": "Fredrik Thordendal",
                    "phone_number": "+12453344098",
                },
                {"name": "Another Person", "phone_number": "+10000000000"},
            ]

    def get_database(self, namespace):
        return self.Frame()


class QHistV10AssetTests(unittest.TestCase):
    def test_contact_oracle_contains_prerequisite_and_truth_result(self):
        truth = [
            {
                "person_id": "person",
                "name": "Fredrik Thordendal",
                "phone_number": "+12453344098",
                "relationship": "friend",
                "is_self": False,
            }
        ]
        false, meta = builder.contact_error(truth, FakeContactContext())
        self.assertEqual(false[0]["phone_number"], "+10000000000")
        self.assertEqual(
            [row["tool"] for row in meta["oracle_action"]["ordered_actions"]],
            [
                "search_contacts",
                "set_cellular_service_status",
                "send_message_with_phone_number",
            ],
        )
        self.assertEqual(meta["verification_actions"][0]["expected_result"], truth)
        self.assertIn("Fredrik Thordendal", meta["oracle_completion_message"])

    def test_relative_time_error_is_frozen_and_verifiable(self):
        false, meta = builder.relative_time_error(spec.REFERENCE_TIME_EPOCH)
        self.assertEqual(false, spec.REFERENCE_TIME_EPOCH + 86400)
        self.assertEqual(meta["oracle_value"], 1788512400.0)
        self.assertEqual(meta["false_value"], 1788598800.0)
        self.assertEqual(
            meta["verification_actions"][0]["expected_result"],
            spec.REFERENCE_TIME_EPOCH,
        )
        self.assertIsNone(meta["oracle_completion_message"])

    def test_cellular_error_keeps_policy_and_environment_distinct(self):
        false, meta = builder.cellular_error(True)
        self.assertIs(false, False)
        self.assertEqual(meta["patch"]["operation"], "none")
        self.assertEqual(len(meta["oracle_action"]["ordered_actions"]), 3)
        self.assertIs(meta["verification_actions"][0]["expected_result"], True)
        self.assertEqual(
            meta["oracle_completion_message"],
            "Cellular service has been turned on.",
        )


if __name__ == "__main__":
    unittest.main()
