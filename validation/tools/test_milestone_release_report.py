import json
import tempfile
import unittest
from pathlib import Path

from validation.tools import milestone_release_report


class MilestoneReleaseReportTests(unittest.TestCase):
    def test_report_promotes_capability_ledger_without_semantic_claim_expansion(self) -> None:
        with tempfile.TemporaryDirectory(prefix="milestone-release-report-") as tmp:
            root = Path(tmp)
            coverage_path = root / "coverage.json"
            coverage_path.write_text(json.dumps(self._coverage_report()), encoding="utf-8")

            report = milestone_release_report.build_report(root, coverage_report_path=coverage_path)

            self.assertEqual(report["status"], "internal_preview")
            self.assertEqual(report["metrics"]["capability_delta_ledger"]["ledger_count"], 1)
            self.assertEqual(report["metrics"]["capability_delta_ledger"]["semantic_pass_count"], 0)
            self.assertEqual(report["metrics"]["translation_coverage_numerator"], 0)
            self.assertFalse(report["metrics"]["native_build_catalogue_included_in_translation_coverage"])
            self.assertFalse(report["metrics"]["handwritten_reference_included_in_translation_coverage"])
            self.assertIn("no_translator_generated_semantic_pass", report["readiness"]["blockers"])
            self.assertIn("not semantic acceptance evidence", report["claim_boundary"])
            self.assertIn("capability_delta_ledger", report["release_note_inputs"])

    def test_rejects_coverage_report_without_capability_delta_ledger(self) -> None:
        with tempfile.TemporaryDirectory(prefix="milestone-release-report-") as tmp:
            root = Path(tmp)
            payload = self._coverage_report()
            payload.pop("capability_delta_ledger")
            coverage_path = root / "coverage.json"
            coverage_path.write_text(json.dumps(payload), encoding="utf-8")

            with self.assertRaises(SystemExit) as raised:
                milestone_release_report.build_report(root, coverage_report_path=coverage_path)

            self.assertIn("capability_delta_ledger", str(raised.exception))

    def test_rejects_l4_refused_ledger_counted_as_translation_numerator(self) -> None:
        with tempfile.TemporaryDirectory(prefix="milestone-release-report-") as tmp:
            root = Path(tmp)
            payload = self._coverage_report()
            payload["capability_delta_ledger"]["route_statuses"] = {"refused": 1}
            payload["capability_delta_ledger"]["semantic_pass_count"] = 1
            coverage_path = root / "coverage.json"
            coverage_path.write_text(json.dumps(payload), encoding="utf-8")

            with self.assertRaises(SystemExit) as raised:
                milestone_release_report.build_report(root, coverage_report_path=coverage_path)

            self.assertIn("L4/refused", str(raised.exception))

    def test_core_ci_runs_milestone_release_report_gate(self) -> None:
        workflow = Path(".github/workflows/core-translator-validation-ci.yml")
        text = workflow.read_text(encoding="utf-8")

        self.assertIn("python -m unittest validation.tools.test_milestone_release_report", text)
        self.assertIn("python validation/tools/milestone_release_report.py", text)

    def _coverage_report(self) -> dict:
        return {
            "schema_version": 1,
            "status": "passed",
            "matrix": {
                "path": "validation/translator-coverage-matrix.json",
                "capability_count": 11,
            },
            "capability_count": 11,
            "dimensions": {
                "clang_fixture_replay": {"covered": 9, "gap": 0, "not_applicable": 2},
                "handwritten_ir": {"covered": 7, "gap": 0, "not_applicable": 4},
            },
            "capability_delta_ledger": {
                "schema_version": 1,
                "status": "recorded",
                "ledger_count": 1,
                "delta_count": 1,
                "governance_delta_count": 1,
                "verification_command_count": 1,
                "semantic_pass_count": 0,
                "blocked_callee_count": 4,
                "generated_candidate_status": {"refused": 1},
                "route_levels": {"L4": 1},
                "route_statuses": {"refused": 1},
                "by_construct": {"external_direct_callee_context": {"refused": 1}},
                "ledgers": [
                    {
                        "path": "validation/evidence/flashdb/auto-translation/real-fdb-kv-set/l3-real-fdb-kv-set-capability-delta.json",
                        "target_id": "flashdb",
                        "slice_id": "real-fdb-kv-set",
                        "route_level": "L4",
                        "route_status": "refused",
                        "delta_count": 1,
                    }
                ],
                "claim_boundary": "Capability-delta ledger entries are not semantic acceptance evidence.",
            },
            "claim_boundary": "translator coverage matrix records representative regression evidence only.",
        }


if __name__ == "__main__":
    unittest.main()
