import unittest

from qhist_e0_spec import (
    DEVELOPMENT_SCENARIOS,
    ORTHOGONALITY_SCENARIOS,
    PRECISIONS,
    REFERENCE_TIME_EPOCH,
    REFERENCE_TIME_ISO,
    build_qualification_units,
    build_trajectory_units,
    normalize_family,
    validate_frozen_design,
)


class QHistE0SpecTests(unittest.TestCase):
    def test_frozen_counts(self) -> None:
        self.assertEqual(
            validate_frozen_design(),
            {
                "p00_trajectories": 80,
                "orthogonality_trajectories": 24,
                "qualification_runs": 30,
                "total_e0_units": 134,
                "development_families": 3,
            },
        )

    def test_units_are_unique(self) -> None:
        trajectories = build_trajectory_units()
        qualifications = build_qualification_units()
        self.assertEqual(len({row["unit_id"] for row in trajectories}), 104)
        self.assertEqual(len({row["unit_id"] for row in qualifications}), 30)

    def test_orthogonality_subset_covers_all_families(self) -> None:
        families = {normalize_family(name) for name in ORTHOGONALITY_SCENARIOS}
        self.assertEqual(len(families), 3)

    def test_family_normalization_is_recursive(self) -> None:
        self.assertEqual(
            normalize_family(
                "send_message_with_contact_content_cellular_off_multiple_user_turn_alt"
            ),
            "send_message_with_contact_content_cellular_off",
        )

    def test_reminder_prefix_is_schema_valid_and_nonselective(self) -> None:
        reminder_specs = [
            row for row in DEVELOPMENT_SCENARIOS if row["prefix_tool"] == "search_reminder"
        ]
        self.assertEqual(len(reminder_specs), 2)
        for row in reminder_specs:
            self.assertEqual(
                row["prefix_arguments"],
                {"reminder_timestamp_lowerbound": 315529200.0},
            )

    def test_reference_clock_is_frozen(self) -> None:
        self.assertEqual(REFERENCE_TIME_ISO, "2026-09-03T12:00:00+08:00")
        self.assertEqual(REFERENCE_TIME_EPOCH, 1788408000.0)

    def test_weight_backend_is_frozen_to_quanto_only_for_w4(self) -> None:
        self.assertEqual(
            PRECISIONS["P10"]["weight_backend"], "optimum-quanto-0.2.7"
        )
        self.assertEqual(
            PRECISIONS["P11"]["weight_backend"], "optimum-quanto-0.2.7"
        )
        self.assertEqual(PRECISIONS["P00"]["weight_backend"], "bfloat16")
        self.assertEqual(PRECISIONS["P01"]["weight_backend"], "bfloat16")


if __name__ == "__main__":
    unittest.main()
