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
from validation.tools.interior_projection_reporter_test_support import (
    REPO_ROOT,
    build_reporter_layout,
)
from validation.tools.interior_projection_test_support import (
    build_projection_spec,
    unsafe_rust_draft,
)


class TranslationCarrierInteriorProjectionReporterTests(unittest.TestCase):
    def test_reporter_replays_safe_projection_and_real_zero_to_one_mutation(self) -> None:
        target_root = REPO_ROOT / "target"
        target_root.mkdir(exist_ok=True)
        with tempfile.TemporaryDirectory(prefix="projection-reporter-", dir=target_root) as tmp:
            layout = build_reporter_layout(Path(tmp))
            paths = emit_reports(**layout["emit_args"])
            reports = {
                name: json.loads(path.read_text(encoding="utf-8"))
                for name, path in paths.items()
            }
            self.assertEqual(reports["c_oracle"]["status"], "passed")
            self.assertEqual(reports["rust_report"]["status"], "passed")
            self.assertEqual(reports["diff"]["status"], "passed")
            self.assertEqual(reports["rust_report"]["cases"][1]["observed_phase"], 0)
            safety = reports["rust_report"]["provenance"]["safe_mutable_projection"]
            self.assertEqual(safety["projection_mode"], "safe_mutable_reference")
            self.assertEqual(safety["pointer_root_count"], 1)
            self.assertEqual(safety["raw_pointer_count"], 0)
            self.assertEqual(safety["unsafe_count"], 0)

            negative = reports["negative_diff"]
            self.assertEqual(negative["status"], "expected_failed")
            self.assertEqual(negative["first_mismatch"]["field"], "observed_phase")
            self.assertEqual(
                negative["partition_detection"]["observable_mismatch_case_ids"],
                ["ordinary", "maximum"],
            )
            execution = negative["actual_mutation_execution"]
            self.assertEqual(execution["mutation"]["operator_from"], "0")
            self.assertEqual(execution["mutation"]["operator_to"], "1")
            self.assertNotEqual(execution["same_generated_replay_harness"]["run"]["returncode"], 0)
            mutated = REPO_ROOT / execution["mutation"]["mutated_draft"]["path"]
            self.assertIn(
                "cursor.telemetry.phase = (1i32 as u32);",
                mutated.read_text(encoding="utf-8"),
            )
            claim = reports["diff"]["claim_boundary"]["interior_projection"]
            self.assertEqual(claim["owner_parameter"], "owner")
            self.assertEqual(claim["noalias_required"], [])

    def test_reporter_rejects_unsafe_raw_pointer_draft(self) -> None:
        target_root = REPO_ROOT / "target"
        target_root.mkdir(exist_ok=True)
        with tempfile.TemporaryDirectory(prefix="projection-unsafe-", dir=target_root) as tmp:
            layout = build_reporter_layout(Path(tmp))
            draft = Path(layout["auto_dir"]) / "l3-reset-current-phase-rust-draft.rs"
            draft.write_text(unsafe_rust_draft(), encoding="utf-8")
            with self.assertRaisesRegex(ReporterError, "unsafe, raw_pointer"):
                emit_reports(**layout["emit_args"])

    def test_reporter_rejects_owner_state_equality_return(self) -> None:
        target_root = REPO_ROOT / "target"
        target_root.mkdir(exist_ok=True)
        with tempfile.TemporaryDirectory(prefix="projection-equality-", dir=target_root) as tmp:
            layout = build_reporter_layout(Path(tmp))
            draft = Path(layout["auto_dir"]) / "l3-reset-current-phase-rust-draft.rs"
            equality = draft.read_text(encoding="utf-8").replace(
                "    true\n", "    owner.current.telemetry.phase == 0\n"
            )
            draft.write_text(equality, encoding="utf-8")
            with self.assertRaisesRegex(ReporterError, "fixed bool return"):
                emit_reports(**layout["emit_args"])

    def test_reporter_recomputes_contract_cases_and_single_root(self) -> None:
        spec, fixture = build_projection_spec()
        contract = parse_contract(spec)
        self.assertEqual(validate_cases(fixture["cases"], contract)[1]["id"], "maximum")

        expected = copy.deepcopy(fixture["cases"])
        expected[0]["expected_outputs"]["observed_phase"] = 1
        with self.assertRaisesRegex(ReporterError, "projection model"):
            validate_cases(expected, contract)

        pointer = copy.deepcopy(spec)
        pointer["c_boundary"]["pointer_contract"]["aliasing_proven"] = False
        with self.assertRaisesRegex(ReporterError, "proven pointer root"):
            parse_contract(pointer)

        noalias = copy.deepcopy(spec)
        noalias["replay_contract"]["noalias_required"] = [["owner", "other"]]
        with self.assertRaisesRegex(ReporterError, "must be empty"):
            parse_contract(noalias)


if __name__ == "__main__":
    unittest.main()
