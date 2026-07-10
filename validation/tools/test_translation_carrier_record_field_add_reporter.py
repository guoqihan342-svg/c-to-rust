from __future__ import annotations

import copy
import json
import tempfile
import unittest
from pathlib import Path

from validation.tools._translation_carrier_reporter import emit_reports
from validation.tools._translation_carrier_reporter.contract import (
    ReporterError,
    parse_contract,
    validate_cases,
)
from validation.tools.record_field_add_reporter_test_support import (
    REPO_ROOT,
    build_reporter_layout,
)
from validation.tools.record_field_add_test_support import build_field_add_spec


class TranslationCarrierRecordFieldAddReporterTests(unittest.TestCase):
    def test_renamed_reporter_executes_add_to_sub_negative(self) -> None:
        target_root = REPO_ROOT / "target"
        target_root.mkdir(exist_ok=True)
        with tempfile.TemporaryDirectory(prefix="field-add-reporter-", dir=target_root) as tmp:
            layout = build_reporter_layout(Path(tmp))
            paths = emit_reports(**layout["emit_args"])
            reports = {
                name: json.loads(path.read_text(encoding="utf-8"))
                for name, path in paths.items()
            }

            self.assertEqual(reports["c_oracle"]["status"], "passed")
            self.assertEqual(reports["rust_report"]["status"], "passed")
            self.assertEqual(reports["diff"]["status"], "passed")
            self.assertEqual(reports["rust_report"]["cases"][1]["combined_fill"], 12)
            self.assertEqual(
                reports["rust_report"]["provenance"]["fixture_state_model"]["operation"],
                "wrapping_add",
            )

            negative = reports["negative_diff"]
            self.assertEqual(negative["status"], "expected_failed")
            self.assertEqual(negative["first_mismatch"]["field"], "combined_fill")
            self.assertEqual(
                negative["partition_detection"]["observable_mismatch_case_ids"],
                ["ordinary", "u32-wrap"],
            )
            execution = negative["actual_mutation_execution"]
            self.assertEqual(execution["mutation"]["operator_from"], "wrapping_add")
            self.assertEqual(execution["mutation"]["operator_to"], "wrapping_sub")
            self.assertNotEqual(
                execution["same_generated_replay_harness"]["run"]["returncode"], 0
            )
            mutated_ref = execution["mutation"]["mutated_draft"]
            mutated_path = REPO_ROOT / mutated_ref["path"]
            self.assertIn("wrapping_sub", mutated_path.read_text(encoding="utf-8"))

    def test_reporter_recomputes_contract_and_expected_outputs(self) -> None:
        spec, fixture = build_field_add_spec()
        contract = parse_contract(spec)
        self.assertEqual(validate_cases(fixture["cases"], contract)[1]["id"], "u32-wrap")

        operation = copy.deepcopy(spec)
        operation["replay_contract"]["state_update"]["operation"] = "saturating_add"
        with self.assertRaisesRegex(ReporterError, "operation must be wrapping_add"):
            parse_contract(operation)

        noalias = copy.deepcopy(spec)
        noalias["replay_contract"]["noalias_required"] = []
        noalias["c_boundary"]["pointer_contract"]["noalias_required"] = []
        with self.assertRaisesRegex(ReporterError, "complete mutable root pair"):
            parse_contract(noalias)

        expected = copy.deepcopy(fixture["cases"])
        expected[0]["expected_outputs"]["combined_fill"] += 1
        with self.assertRaisesRegex(ReporterError, "wrapping-add model"):
            validate_cases(expected, contract)


if __name__ == "__main__":
    unittest.main()
