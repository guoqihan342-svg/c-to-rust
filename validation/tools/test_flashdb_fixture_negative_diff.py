import unittest

from validation.tools.flashdb_fixture_negative_diff import (
    mutate_expected_report,
    validate_negative_diff_result,
)


class FlashDbFixtureNegativeDiffTests(unittest.TestCase):
    def test_mutates_first_behavior_field(self) -> None:
        report = {
            "steps": [
                {"id": "kv-001", "op": "kv.get", "status": "ok", "code": "OK", "value": "one"}
            ]
        }

        mutated, mutation = mutate_expected_report(report)

        self.assertEqual(mutation["step_id"], "kv-001")
        self.assertEqual(mutation["field"], "value")
        self.assertNotEqual(mutated["steps"][0]["value"], "one")

    def test_mutates_singleton_list_behavior_field(self) -> None:
        report = {
            "steps": [
                {"id": "kv-001", "op": "kv.entries", "entries": [{"key": "a"}]}
            ]
        }

        mutated, mutation = mutate_expected_report(report)

        self.assertEqual(mutation["field"], "entries")
        self.assertNotEqual(mutated["steps"][0]["entries"], [{"key": "a"}])

    def test_rejects_unexpected_success(self) -> None:
        with self.assertRaises(SystemExit) as raised:
            validate_negative_diff_result(0, {"status": "passed", "first_mismatch": None})

        self.assertIn("unexpectedly passed", str(raised.exception))

    def test_accepts_failed_diff_with_mismatch(self) -> None:
        summary = validate_negative_diff_result(
            1,
            {
                "status": "failed",
                "first_mismatch": {
                    "step_id": "kv-001",
                    "field_path": "steps.kv-001.value",
                },
            },
        )

        self.assertEqual(summary["status"], "passed")
        self.assertEqual(summary["diff_status"], "expected_failed")
        self.assertEqual(summary["first_mismatch"], "steps.kv-001.value")


if __name__ == "__main__":
    unittest.main()
