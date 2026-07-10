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
from validation.tools.record_constant_state_reporter_test_support import (
    REPO_ROOT,
    build_reporter_layout,
)
from validation.tools.record_constant_state_test_support import build_constant_state_spec


class TranslationCarrierRecordConstantStateReporterTests(unittest.TestCase):
    def test_reporter_executes_real_zero_to_one_mutation(self) -> None:
        target_root = REPO_ROOT / "target"
        target_root.mkdir(exist_ok=True)
        with tempfile.TemporaryDirectory(prefix="constant-state-reporter-", dir=target_root) as tmp:
            layout = build_reporter_layout(Path(tmp))
            paths = emit_reports(**layout["emit_args"])
            reports = {
                name: json.loads(path.read_text(encoding="utf-8"))
                for name, path in paths.items()
            }
            self.assertEqual(reports["c_oracle"]["status"], "passed")
            self.assertEqual(reports["rust_report"]["status"], "passed")
            self.assertEqual(reports["diff"]["status"], "passed")
            self.assertEqual(reports["rust_report"]["cases"][1]["cleared_marker"], 0)
            self.assertEqual(
                reports["rust_report"]["provenance"]["fixture_state_model"]["operation"],
                "constant_assign",
            )
            negative = reports["negative_diff"]
            self.assertEqual(negative["status"], "expected_failed")
            self.assertEqual(negative["first_mismatch"]["field"], "cleared_marker")
            self.assertEqual(
                negative["partition_detection"]["observable_mismatch_case_ids"],
                ["ordinary", "maximum"],
            )
            execution = negative["actual_mutation_execution"]
            self.assertEqual(execution["mutation"]["operator_from"], "0")
            self.assertEqual(execution["mutation"]["operator_to"], "1")
            self.assertNotEqual(
                execution["same_generated_replay_harness"]["run"]["returncode"], 0
            )
            mutated_path = REPO_ROOT / execution["mutation"]["mutated_draft"]["path"]
            self.assertIn("parcel.route.marker = 1;", mutated_path.read_text(encoding="utf-8"))

    def test_reporter_recomputes_contract_cases_and_provenance(self) -> None:
        spec, fixture = build_constant_state_spec()
        contract = parse_contract(spec)
        self.assertEqual(validate_cases(fixture["cases"], contract)[1]["id"], "maximum")

        constant = copy.deepcopy(spec)
        constant["replay_contract"]["state_update"]["value"] = 1
        with self.assertRaisesRegex(ReporterError, "constant 0"):
            parse_contract(constant)

        pointer = copy.deepcopy(spec)
        pointer["c_boundary"]["pointer_contract"]["aliasing_proven"] = False
        with self.assertRaisesRegex(ReporterError, "not proven"):
            parse_contract(pointer)

        expected = copy.deepcopy(fixture["cases"])
        expected[0]["expected_outputs"]["cleared_marker"] = 1
        with self.assertRaisesRegex(ReporterError, "constant-state model"):
            validate_cases(expected, contract)


if __name__ == "__main__":
    unittest.main()
