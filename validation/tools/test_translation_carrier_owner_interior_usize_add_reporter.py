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
from validation.tools.owner_interior_usize_add_reporter_test_support import (
    REPO_ROOT,
    build_reporter_layout,
)
from validation.tools.owner_interior_usize_add_test_support import build_spec


class TranslationCarrierOwnerInteriorUsizeAddReporterTests(unittest.TestCase):
    def test_reporter_executes_wrapping_add_to_sub_negative(self) -> None:
        target_root = REPO_ROOT / "target"
        target_root.mkdir(exist_ok=True)
        with tempfile.TemporaryDirectory(prefix="owner-usize-add-reporter-", dir=target_root) as tmp:
            paths = emit_reports(**build_reporter_layout(Path(tmp))["emit_args"])
            reports = {
                name: json.loads(path.read_text(encoding="utf-8"))
                for name, path in paths.items()
            }
            self.assertEqual(reports["c_oracle"]["status"], "passed")
            self.assertEqual(reports["rust_report"]["status"], "passed")
            self.assertEqual(reports["diff"]["status"], "passed")
            self.assertEqual(reports["rust_report"]["cases"][2]["updated_total"], 1)
            model = reports["rust_report"]["provenance"]["fixture_state_model"]
            self.assertEqual((model["source_bits"], model["target_bits"]), (32, 64))

            negative = reports["negative_diff"]
            self.assertEqual(negative["status"], "expected_failed")
            self.assertEqual(
                negative["partition_detection"]["observable_mismatch_case_ids"],
                ["ordinary", "lp64-wrap"],
            )
            self.assertEqual(
                negative["partition_detection"]["mutation_equivalent_case_ids"],
                ["rhs-zero"],
            )
            execution = negative["actual_mutation_execution"]
            self.assertEqual(execution["mutation"]["operator_from"], "wrapping_add")
            self.assertEqual(execution["mutation"]["operator_to"], "wrapping_sub")
            mutated_path = REPO_ROOT / execution["mutation"]["mutated_draft"]["path"]
            self.assertIn("wrapping_sub", mutated_path.read_text(encoding="utf-8"))

    def test_reporter_recomputes_lp64_model_and_rejects_shape_drift(self) -> None:
        spec, fixture = build_spec()
        contract = parse_contract(spec)
        cases = validate_cases(fixture["cases"], contract)
        self.assertEqual(cases[1]["id"], "rhs-zero")
        self.assertEqual(cases[2]["expected_outputs"]["updated_total"], 1)

        overlap = copy.deepcopy(spec)
        overlap["replay_contract"]["projection_path"] = ["total"]
        with self.assertRaisesRegex(ReporterError, "nested records"):
            parse_contract(overlap)

        drift = copy.deepcopy(spec)
        drift["replay_contract"]["state_update"]["extra"] = True
        with self.assertRaisesRegex(ReporterError, "state_update"):
            parse_contract(drift)


if __name__ == "__main__":
    unittest.main()
