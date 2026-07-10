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
from validation.tools.record_field_scalar_add_reporter_test_support import (
    REPO_ROOT,
    build_reporter_layout,
)
from validation.tools.record_field_scalar_add_test_support import build_field_scalar_add_spec


class TranslationCarrierRecordFieldScalarAddReporterTests(unittest.TestCase):
    def test_reporter_executes_add_to_sub_mutation_for_every_case(self) -> None:
        target_root = REPO_ROOT / "target"
        target_root.mkdir(exist_ok=True)
        with tempfile.TemporaryDirectory(prefix="field-scalar-reporter-", dir=target_root) as tmp:
            paths = emit_reports(**build_reporter_layout(Path(tmp))["emit_args"])
            reports = {
                name: json.loads(path.read_text(encoding="utf-8"))
                for name, path in paths.items()
            }
            self.assertEqual(reports["c_oracle"]["status"], "passed")
            self.assertEqual(reports["rust_report"]["status"], "passed")
            self.assertEqual(reports["diff"]["status"], "passed")
            self.assertEqual(reports["rust_report"]["cases"][2]["updated_total"], 12)
            claim_text = json.dumps(reports["rust_report"]["claim_boundary"]).lower()
            self.assertNotRegex(claim_text, r"sizeof|alignof|alignment|layout")

            negative = reports["negative_diff"]
            self.assertEqual(negative["status"], "expected_failed")
            self.assertEqual(
                negative["partition_detection"]["observable_mismatch_case_ids"],
                ["ordinary", "carry", "u32-wrap"],
            )
            execution = negative["actual_mutation_execution"]
            self.assertEqual(execution["mutation"]["operator_from"], "wrapping_add")
            self.assertEqual(execution["mutation"]["operator_to"], "wrapping_sub")
            self.assertNotEqual(execution["same_generated_replay_harness"]["run"]["returncode"], 0)
            mutated_path = REPO_ROOT / execution["mutation"]["mutated_draft"]["path"]
            self.assertIn("wrapping_sub", mutated_path.read_text(encoding="utf-8"))

    def test_reporter_recomputes_structured_bindings_and_provenance(self) -> None:
        spec, fixture = build_field_scalar_add_spec()
        contract = parse_contract(spec)
        self.assertEqual(validate_cases(fixture["cases"], contract)[2]["id"], "u32-wrap")
        self.assertEqual(contract["entry_arguments"][1]["pass_mode"], "value")
        self.assertEqual(contract["entry_arguments"][2]["rust_type"], "u32")

        operation = copy.deepcopy(spec)
        operation["replay_contract"]["state_update"]["operation"] = "checked_add"
        with self.assertRaisesRegex(ReporterError, "operation must be wrapping_add"):
            parse_contract(operation)

        pointer = copy.deepcopy(spec)
        pointer["c_boundary"]["pointer_contract"]["aliasing_proven"] = False
        with self.assertRaisesRegex(ReporterError, "not proven"):
            parse_contract(pointer)

        expected = copy.deepcopy(fixture["cases"])
        expected[0]["expected_outputs"]["updated_total"] += 1
        with self.assertRaisesRegex(ReporterError, "field-scalar add model"):
            validate_cases(expected, contract)


if __name__ == "__main__":
    unittest.main()
