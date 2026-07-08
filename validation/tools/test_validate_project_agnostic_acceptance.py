import unittest

from validation.tools.validate_project_agnostic_acceptance import validate_acceptance_report


class ValidateProjectAgnosticAcceptanceTests(unittest.TestCase):
    def test_accepts_complete_project_agnostic_full_conversion_report(self) -> None:
        report = complete_report()

        validated = validate_acceptance_report(report)

        self.assertEqual(validated["status"], "passed")
        self.assertEqual(validated["source_functions_total"], 2)
        self.assertEqual(validated["accepted_functions_total"], 2)

    def test_rejects_flashdb_specific_harness_as_project_agnostic_acceptance(self) -> None:
        report = complete_report()
        report["hardcoded_target_references"] = {
            "status": "failed",
            "occurrences": [
                {
                    "path": "flashDB_rust/oracle/generate_c_oracle.sh",
                    "token": "FlashDB",
                }
            ],
        }

        with self.assertRaises(SystemExit) as raised:
            validate_acceptance_report(report)

        self.assertIn("hardcoded_target_references", str(raised.exception))

    def test_rejects_partial_function_coverage(self) -> None:
        report = complete_report()
        report["translation_coverage"]["accepted_functions_total"] = 1

        with self.assertRaises(SystemExit) as raised:
            validate_acceptance_report(report)

        self.assertIn("full function coverage", str(raised.exception))

    def test_rejects_accepted_layout_differences_for_complete_conversion(self) -> None:
        report = complete_report()
        report["diff"]["accepted_differences"] = [
            {
                "id": "layout-and-metadata",
                "reason": "project-specific layout was not migrated",
            }
        ]

        with self.assertRaises(SystemExit) as raised:
            validate_acceptance_report(report)

        self.assertIn("accepted_differences", str(raised.exception))


def complete_report() -> dict:
    return {
        "schema_version": 1,
        "status": "passed",
        "claim_scope": "project_agnostic_full_conversion",
        "input_project": {
            "project_id": "arbitrary-c-project",
            "source_root": "inputs/arbitrary-c-project",
            "source_files": ["src/a.c"],
            "compile_commands": ["compile_commands.json"],
            "generated_from_input_project": True,
        },
        "project_discovery": {
            "status": "passed",
            "method": "compile_commands_and_ast",
            "source_files_total": 1,
            "functions_total": 2,
        },
        "hardcoded_target_references": {
            "status": "passed",
            "occurrences": [],
        },
        "translation_coverage": {
            "status": "passed",
            "source_functions_total": 2,
            "translated_functions_total": 2,
            "accepted_functions_total": 2,
            "blocked": [],
            "untranslated": [],
        },
        "rust_build": {
            "status": "passed",
        },
        "oracle": {
            "status": "passed",
            "producer_generated_from_input_project": True,
            "project_specific_template": False,
        },
        "diff": {
            "status": "passed",
            "first_mismatch": None,
            "accepted_differences": [],
        },
        "negative_diff": {
            "status": "passed",
            "detected": True,
        },
        "unsafe_ledger": {
            "status": "passed",
            "unsafe_reduction": {
                "status": "measured",
            },
        },
    }


if __name__ == "__main__":
    unittest.main()
