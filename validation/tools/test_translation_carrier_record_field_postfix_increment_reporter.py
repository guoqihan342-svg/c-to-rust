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
from validation.tools.record_field_postfix_increment_reporter_test_support import (
    build_reporter_layout,
)
from validation.tools.record_field_postfix_increment_test_support import (
    REPO_ROOT,
    build_postfix_increment_spec,
)


class TranslationCarrierRecordFieldPostfixIncrementReporterTests(unittest.TestCase):
    def test_reporter_executes_increment_to_decrement_mutation(self) -> None:
        target_root = REPO_ROOT / "target"
        target_root.mkdir(exist_ok=True)
        with tempfile.TemporaryDirectory(prefix="postfix-reporter-", dir=target_root) as tmp:
            paths = emit_reports(**build_reporter_layout(Path(tmp))["emit_args"])
            reports = {
                name: json.loads(path.read_text(encoding="utf-8"))
                for name, path in paths.items()
            }
            self.assertEqual(reports["c_oracle"]["status"], "passed")
            self.assertEqual(reports["rust_report"]["status"], "passed")
            self.assertEqual(reports["diff"]["status"], "passed")
            self.assertEqual(reports["rust_report"]["cases"][2]["updated_count"], 0)
            negative = reports["negative_diff"]
            self.assertEqual(negative["status"], "expected_failed")
            self.assertEqual(
                negative["partition_detection"]["observable_mismatch_case_ids"],
                ["zero", "ordinary", "u32-wrap"],
            )
            self.assertEqual(
                negative["actual_mutation_execution"]["mutation"]["operator_to"],
                "wrapping_sub",
            )

    def test_reporter_contract_rejects_model_and_source_shape_drift(self) -> None:
        spec, fixture = build_postfix_increment_spec()
        contract = parse_contract(spec)
        self.assertEqual(validate_cases(fixture["cases"], contract)[2]["id"], "u32-wrap")

        update = copy.deepcopy(spec)
        update["replay_contract"]["state_update"]["operation"] = "checked_add"
        with self.assertRaisesRegex(ReporterError, "fixed wrapping_add increment 1"):
            parse_contract(update)

        inputs = copy.deepcopy(fixture["cases"])
        inputs[0]["inputs"]["scalar"] = 1
        with self.assertRaisesRegex(ReporterError, "only the record initial field"):
            validate_cases(inputs, contract)


if __name__ == "__main__":
    unittest.main()
