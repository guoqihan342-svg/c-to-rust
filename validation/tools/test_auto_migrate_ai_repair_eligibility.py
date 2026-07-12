from __future__ import annotations

import unittest

from validation.tools._auto_migrate_ai_repair_eligibility import (
    classify_ai_repair_eligibility,
)


class AutoMigrateAiRepairEligibilityTests(unittest.TestCase):
    def test_candidate_failure_with_fresh_target_is_eligible(self) -> None:
        result = {
            "oracle_proof": {"status": "passed", "target_contract": {"kind": "exact"}},
            "repair_validation_result": {
                "schema_version": 1,
                "status": "failed",
                "failures": [{"gate": "rustc", "kind": "compile_failed"}],
            },
        }

        eligibility = classify_ai_repair_eligibility(result)

        self.assertEqual("eligible", eligibility["status"])
        self.assertEqual(0, eligibility["provider_invocations"])
        self.assertFalse(eligibility["semantic_gate"])

    def test_failed_oracle_is_not_candidate_repairable(self) -> None:
        for oracle in (
            {"status": "failed"},
            {"status": "blocked", "target_contract": {"kind": "exact"}},
            None,
        ):
            with self.subTest(oracle=oracle):
                eligibility = classify_ai_repair_eligibility(
                    {
                        "oracle_proof": oracle,
                        "repair_validation_result": {"status": "failed", "failures": [{}]},
                    }
                )

                self.assertEqual("skipped", eligibility["status"])
                self.assertEqual("fresh_oracle_not_passed", eligibility["reason"])
                self.assertEqual(0, eligibility["provider_invocations"])

    def test_missing_target_or_structured_failure_is_not_repaired(self) -> None:
        cases = (
            (
                {"oracle_proof": {"status": "passed"}},
                "target_contract_missing",
            ),
            (
                {
                    "oracle_proof": {
                        "status": "passed",
                        "target_contract": {"kind": "exact"},
                    },
                    "repair_validation_result": {"status": "passed", "failures": []},
                },
                "structured_candidate_failure_missing",
            ),
        )
        for result, reason in cases:
            with self.subTest(reason=reason):
                eligibility = classify_ai_repair_eligibility(result)
                self.assertEqual("skipped", eligibility["status"])
                self.assertEqual(reason, eligibility["reason"])
                self.assertFalse(eligibility["semantic_gate"])


if __name__ == "__main__":
    unittest.main()
