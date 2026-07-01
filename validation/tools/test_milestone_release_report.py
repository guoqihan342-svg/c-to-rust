import hashlib
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
            self.assertEqual(report["metrics"]["capability_delta_ledger"]["translator_generated_semantic_pass_count"], 0)
            self.assertEqual(report["metrics"]["capability_delta_ledger"]["semantic_pass_count"], 0)
            self.assertEqual(report["metrics"]["capability_delta_ledger"]["accepted_evidence_semantic_pass_count"], 0)
            self.assertEqual(report["metrics"]["translation_coverage_numerator"], 0)
            self.assertEqual(report["metrics"]["candidate_classification"]["refused_delta_count"], 1)
            self.assertEqual(report["metrics"]["candidate_classification"]["generated_candidate_delta_count"], 0)
            self.assertEqual(report["metrics"]["candidate_classification"]["semantic_pass_delta_count"], 0)
            self.assertFalse(report["metrics"]["native_build_catalogue_included_in_translation_coverage"])
            self.assertFalse(report["metrics"]["handwritten_reference_included_in_translation_coverage"])
            self.assertIn("no_translator_generated_semantic_pass", report["readiness"]["blockers"])
            self.assertIn("not semantic acceptance evidence", report["claim_boundary"])
            self.assertIn("capability_delta_ledger", report["release_note_inputs"])

    def test_report_classifies_generated_candidates_without_counting_them_as_acceptance(self) -> None:
        with tempfile.TemporaryDirectory(prefix="milestone-release-report-") as tmp:
            root = Path(tmp)
            payload = self._coverage_report()
            payload["capability_delta_ledger"]["generated_candidate_status"] = {
                "generated": 2,
                "refused": 1,
            }
            payload["capability_delta_ledger"]["route_levels"] = {"L2": 2, "L4": 1}
            payload["capability_delta_ledger"]["route_statuses"] = {"candidate": 2, "refused": 1}
            payload["capability_delta_ledger"]["delta_count"] = 3
            coverage_path = root / "coverage.json"
            coverage_path.write_text(json.dumps(payload), encoding="utf-8")

            report = milestone_release_report.build_report(root, coverage_report_path=coverage_path)

            classes = report["metrics"]["candidate_classification"]
            self.assertEqual(classes["generated_candidate_delta_count"], 2)
            self.assertEqual(classes["refused_delta_count"], 1)
            self.assertEqual(classes["semantic_pass_delta_count"], 0)
            self.assertEqual(report["metrics"]["translation_coverage_numerator"], 0)
            self.assertIn("no_translator_generated_semantic_pass", report["readiness"]["blockers"])

    def test_report_exposes_accepted_evidence_without_translation_numerator(self) -> None:
        with tempfile.TemporaryDirectory(prefix="milestone-release-report-") as tmp:
            root = Path(tmp)
            payload = self._coverage_report()
            payload["capability_delta_ledger"]["accepted_evidence_semantic_pass_count"] = 1
            coverage_path = root / "coverage.json"
            coverage_path.write_text(json.dumps(payload), encoding="utf-8")

            report = milestone_release_report.build_report(root, coverage_report_path=coverage_path)

            self.assertEqual(report["metrics"]["accepted_evidence_semantic_pass_count"], 1)
            self.assertEqual(report["metrics"]["capability_delta_ledger"]["accepted_evidence_semantic_pass_count"], 1)
            self.assertEqual(report["metrics"]["translation_coverage_numerator"], 0)
            self.assertIn("no_translator_generated_semantic_pass", report["readiness"]["blockers"])

    def test_report_summarizes_bound_s2_workflow_metrics_without_semantic_expansion(self) -> None:
        with tempfile.TemporaryDirectory(prefix="milestone-release-report-") as tmp:
            root = Path(tmp)
            coverage_path = root / "coverage.json"
            coverage_path.write_text(json.dumps(self._coverage_report()), encoding="utf-8")
            summary_path = root / "target/competition-out/summary/competition-run-summary.json"
            self._write_competition_summary_with_metrics(summary_path, self._measured_workflow_metrics())

            report = milestone_release_report.build_report(
                root,
                coverage_report_path=coverage_path,
                competition_summary_paths=[summary_path],
            )

            s2 = report["metrics"]["s2_workflow_metrics"]
            self.assertEqual(s2["run_count"], 1)
            self.assertEqual(s2["units_total"], 2)
            self.assertEqual(s2["units_converged"], 2)
            self.assertEqual(s2["unsafe_reduction"]["status"], "measured")
            self.assertEqual(s2["unsafe_reduction"]["baseline_total_unsafe"], 5)
            self.assertEqual(s2["unsafe_reduction"]["current_total_unsafe"], 2)
            self.assertEqual(s2["unsafe_reduction"]["reduced_by"], 3)
            self.assertEqual(s2["translation_before_after"]["status"], "not_provided")
            self.assertEqual(s2["translation_before_after"]["unit_count"], 0)
            self.assertEqual(s2["avg_repair_rounds"], 1.5)
            self.assertEqual(s2["auto_recovery_rate"], 0.5)
            self.assertEqual(s2["repair_history_unit_count"], 1)
            self.assertEqual(s2["auto_recovered_units"], 1)
            self.assertEqual(s2["root_cause_counts"], {"rustc_compile_error": 1})
            self.assertEqual(report["release_note_inputs"]["s2_workflow_metrics"], s2)
            self.assertEqual(report["metrics"]["translation_coverage_numerator"], 0)
            self.assertEqual(report["harness_architecture"]["entrypoint"], "milestone-release-report")
            self.assertEqual(report["harness_architecture"]["workflow_run_count"], 1)
            self.assertEqual(report["harness_architecture"]["before_after_report_count"], 0)
            self.assertEqual(report["core_translation_quality"]["translation_coverage_numerator"], 0)
            self.assertEqual(report["core_translation_quality"]["unsafe_reduction"]["reduced_by"], 3)
            self.assertEqual(report["core_translation_quality"]["translation_before_after"]["status"], "not_provided")
            self.assertIn("no_translator_generated_semantic_pass", report["readiness"]["blockers"])

    def test_report_binds_before_after_exhibit_from_batch_profile_report(self) -> None:
        with tempfile.TemporaryDirectory(prefix="milestone-release-report-") as tmp:
            root = Path(tmp)
            coverage_path = root / "coverage.json"
            coverage_path.write_text(json.dumps(self._coverage_report()), encoding="utf-8")
            summary_path = root / "target/competition-out/summary/competition-run-summary.json"
            workflow_metrics = self._before_after_workflow_metrics()
            self._write_competition_summary_with_metrics(summary_path, workflow_metrics)
            batch_profile_report = self._write_batch_profile_report_with_exhibit(summary_path, workflow_metrics)

            report = milestone_release_report.build_report(
                root,
                coverage_report_path=coverage_path,
                competition_summary_paths=[summary_path],
                batch_profile_report_paths=[batch_profile_report],
            )

            exhibits = report["metrics"]["before_after_exhibits"]
            self.assertEqual(exhibits["status"], "bound")
            self.assertEqual(exhibits["report_count"], 1)
            self.assertEqual(exhibits["passed_report_count"], 1)
            self.assertEqual(exhibits["unit_count"], 1)
            self.assertEqual(exhibits["measured_unsafe_unit_count"], 1)
            self.assertEqual(exhibits["accepted_patch_unit_count"], 1)
            self.assertEqual(
                exhibits["input_reports"][0]["batch_profile_report_path"],
                "target/competition-out/harness/batch-profile-report.json",
            )
            self.assertEqual(
                exhibits["input_reports"][0]["before_after_exhibit_path"],
                "target/competition-out/summary/before-after-exhibit.json",
            )
            self.assertEqual(exhibits["input_reports"][0]["status"], "passed")
            self.assertEqual(exhibits["input_reports"][0]["units"][0]["unit_id"], "demo/store-add-one")
            self.assertEqual(exhibits["input_reports"][0]["units"][0]["baseline"]["path"], "evidence/before-after/baseline-unsafe.rs")
            self.assertEqual(exhibits["input_reports"][0]["units"][0]["final"]["path"], "evidence/before-after/final-safe.rs")
            self.assertEqual(exhibits["input_reports"][0]["units"][0]["oracle_evidence"]["path"], "evidence/before-after/oracle-diff.json")
            self.assertEqual(exhibits["input_reports"][0]["units"][0]["accepted_patch"]["path"], "evidence/before-after/accepted.patch")
            self.assertEqual(exhibits["input_reports"][0]["units"][0]["patch_log"]["path"], "evidence/before-after/step-log.jsonl")
            self.assertEqual(exhibits["input_reports"][0]["units"][0]["unsafe_reduction"]["reduced_by"], 3)
            self.assertEqual(report["release_note_inputs"]["before_after_exhibits"], exhibits)
            self.assertEqual(report["metrics"]["translation_coverage_numerator"], 0)
            self.assertEqual(report["harness_architecture"]["before_after_report_count"], 1)
            self.assertEqual(report["core_translation_quality"]["before_after_exhibits"], exhibits)
            self.assertEqual(report["core_translation_quality"]["translation_before_after"]["status"], "bound")

    def test_report_rejects_before_after_exhibit_hash_drift(self) -> None:
        with tempfile.TemporaryDirectory(prefix="milestone-release-report-") as tmp:
            root = Path(tmp)
            coverage_path = root / "coverage.json"
            coverage_path.write_text(json.dumps(self._coverage_report()), encoding="utf-8")
            summary_path = root / "target/competition-out/summary/competition-run-summary.json"
            workflow_metrics = self._before_after_workflow_metrics()
            self._write_competition_summary_with_metrics(summary_path, workflow_metrics)
            batch_profile_report = self._write_batch_profile_report_with_exhibit(
                summary_path,
                workflow_metrics,
                exhibit_sha256="0" * 64,
            )

            with self.assertRaises(SystemExit) as raised:
                milestone_release_report.build_report(
                    root,
                    coverage_report_path=coverage_path,
                    competition_summary_paths=[summary_path],
                    batch_profile_report_paths=[batch_profile_report],
                )

            self.assertIn("before_after_exhibit_report.sha256", str(raised.exception))

    def test_report_rejects_before_after_unit_artifact_hash_drift(self) -> None:
        with tempfile.TemporaryDirectory(prefix="milestone-release-report-") as tmp:
            root = Path(tmp)
            coverage_path = root / "coverage.json"
            coverage_path.write_text(json.dumps(self._coverage_report()), encoding="utf-8")
            summary_path = root / "target/competition-out/summary/competition-run-summary.json"
            workflow_metrics = self._before_after_workflow_metrics()
            self._write_competition_summary_with_metrics(summary_path, workflow_metrics)
            batch_profile_report = self._write_batch_profile_report_with_exhibit(summary_path, workflow_metrics)
            exhibit_path = root / "target/competition-out/summary/before-after-exhibit.json"
            exhibit = json.loads(exhibit_path.read_text(encoding="utf-8"))
            exhibit["units"][0]["baseline"]["sha256"] = "f" * 64
            exhibit_path.write_text(json.dumps(exhibit, indent=2, sort_keys=True) + "\n", encoding="utf-8")
            batch = json.loads(batch_profile_report.read_text(encoding="utf-8"))
            batch["before_after_exhibit_report"]["sha256"] = sha256_file(exhibit_path)
            batch_profile_report.write_text(json.dumps(batch, indent=2, sort_keys=True) + "\n", encoding="utf-8")

            with self.assertRaises(SystemExit) as raised:
                milestone_release_report.build_report(
                    root,
                    coverage_report_path=coverage_path,
                    competition_summary_paths=[summary_path],
                    batch_profile_report_paths=[batch_profile_report],
                )

            self.assertIn("units[0].baseline.sha256", str(raised.exception))

    def test_report_rejects_before_after_repair_history_hash_drift(self) -> None:
        with tempfile.TemporaryDirectory(prefix="milestone-release-report-") as tmp:
            root = Path(tmp)
            coverage_path = root / "coverage.json"
            coverage_path.write_text(json.dumps(self._coverage_report()), encoding="utf-8")
            summary_path = root / "target/competition-out/summary/competition-run-summary.json"
            workflow_metrics = self._before_after_workflow_metrics()
            self._write_competition_summary_with_metrics(summary_path, workflow_metrics)
            batch_profile_report = self._write_batch_profile_report_with_exhibit(summary_path, workflow_metrics)
            exhibit_path = root / "target/competition-out/summary/before-after-exhibit.json"
            exhibit = json.loads(exhibit_path.read_text(encoding="utf-8"))
            exhibit["units"][0]["repair_history"]["patch_events_sha256"] = "f" * 64
            exhibit_path.write_text(json.dumps(exhibit, indent=2, sort_keys=True) + "\n", encoding="utf-8")
            batch = json.loads(batch_profile_report.read_text(encoding="utf-8"))
            batch["before_after_exhibit_report"]["sha256"] = sha256_file(exhibit_path)
            batch_profile_report.write_text(json.dumps(batch, indent=2, sort_keys=True) + "\n", encoding="utf-8")

            with self.assertRaises(SystemExit) as raised:
                milestone_release_report.build_report(
                    root,
                    coverage_report_path=coverage_path,
                    competition_summary_paths=[summary_path],
                    batch_profile_report_paths=[batch_profile_report],
                )

            self.assertIn("repair_history.patch_events_sha256", str(raised.exception))

    def test_report_rejects_before_after_unit_retargeted_away_from_workflow_metrics(self) -> None:
        with tempfile.TemporaryDirectory(prefix="milestone-release-report-") as tmp:
            root = Path(tmp)
            coverage_path = root / "coverage.json"
            coverage_path.write_text(json.dumps(self._coverage_report()), encoding="utf-8")
            summary_path = root / "target/competition-out/summary/competition-run-summary.json"
            workflow_metrics = self._before_after_workflow_metrics()
            self._write_competition_summary_with_metrics(summary_path, workflow_metrics)
            batch_profile_report = self._write_batch_profile_report_with_exhibit(summary_path, workflow_metrics)
            exhibit_path = root / "target/competition-out/summary/before-after-exhibit.json"
            exhibit = json.loads(exhibit_path.read_text(encoding="utf-8"))
            exhibit["units"][0]["baseline"] = dict(exhibit["units"][0]["final"])
            exhibit_path.write_text(json.dumps(exhibit, indent=2, sort_keys=True) + "\n", encoding="utf-8")
            batch = json.loads(batch_profile_report.read_text(encoding="utf-8"))
            batch["before_after_exhibit_report"]["sha256"] = sha256_file(exhibit_path)
            batch_profile_report.write_text(json.dumps(batch, indent=2, sort_keys=True) + "\n", encoding="utf-8")

            with self.assertRaises(SystemExit) as raised:
                milestone_release_report.build_report(
                    root,
                    coverage_report_path=coverage_path,
                    competition_summary_paths=[summary_path],
                    batch_profile_report_paths=[batch_profile_report],
                )

            self.assertIn("baseline must match workflow metrics", str(raised.exception))

    def test_report_rejects_verified_repairer_history_without_repair_history_binding(self) -> None:
        with tempfile.TemporaryDirectory(prefix="milestone-release-report-") as tmp:
            root = Path(tmp)
            coverage_path = root / "coverage.json"
            coverage_path.write_text(json.dumps(self._coverage_report()), encoding="utf-8")
            summary_path = root / "target/competition-out/summary/competition-run-summary.json"
            workflow_metrics = self._before_after_workflow_metrics()
            self._write_competition_summary_with_metrics(summary_path, workflow_metrics)
            batch_profile_report = self._write_batch_profile_report_with_exhibit(summary_path, workflow_metrics)
            exhibit_path = root / "target/competition-out/summary/before-after-exhibit.json"
            exhibit = json.loads(exhibit_path.read_text(encoding="utf-8"))
            del exhibit["stage_contracts"]["repairer"]["histories"][0]["repair_history"]
            exhibit_path.write_text(json.dumps(exhibit, indent=2, sort_keys=True) + "\n", encoding="utf-8")
            batch = json.loads(batch_profile_report.read_text(encoding="utf-8"))
            batch["before_after_exhibit_report"]["sha256"] = sha256_file(exhibit_path)
            batch_profile_report.write_text(json.dumps(batch, indent=2, sort_keys=True) + "\n", encoding="utf-8")

            with self.assertRaises(SystemExit) as raised:
                milestone_release_report.build_report(
                    root,
                    coverage_report_path=coverage_path,
                    competition_summary_paths=[summary_path],
                    batch_profile_report_paths=[batch_profile_report],
                )

            self.assertIn("repair_history is required", str(raised.exception))

    def test_report_rejects_competition_summary_workflow_metrics_hash_drift(self) -> None:
        with tempfile.TemporaryDirectory(prefix="milestone-release-report-") as tmp:
            root = Path(tmp)
            coverage_path = root / "coverage.json"
            coverage_path.write_text(json.dumps(self._coverage_report()), encoding="utf-8")
            summary_path = root / "target/competition-out/summary/competition-run-summary.json"
            self._write_competition_summary_with_metrics(
                summary_path,
                self._measured_workflow_metrics(),
                metrics_sha256="0" * 64,
            )

            with self.assertRaises(SystemExit) as raised:
                milestone_release_report.build_report(
                    root,
                    coverage_report_path=coverage_path,
                    competition_summary_paths=[summary_path],
                )

            self.assertIn("workflow_metrics.sha256", str(raised.exception))

    def test_translation_coverage_numerator_uses_canonical_translator_generated_count(self) -> None:
        with tempfile.TemporaryDirectory(prefix="milestone-release-report-") as tmp:
            root = Path(tmp)
            payload = self._coverage_report()
            payload["capability_delta_ledger"]["translator_generated_semantic_pass_count"] = 0
            payload["capability_delta_ledger"]["semantic_pass_count"] = 1
            payload["capability_delta_ledger"]["accepted_evidence_semantic_pass_count"] = 1
            payload["capability_delta_ledger"]["generated_candidate_status"] = {"semantic_pass": 1}
            payload["capability_delta_ledger"]["route_levels"] = {"L4": 1}
            payload["capability_delta_ledger"]["route_statuses"] = {"refused": 1}
            coverage_path = root / "coverage.json"
            coverage_path.write_text(json.dumps(payload), encoding="utf-8")

            report = milestone_release_report.build_report(root, coverage_report_path=coverage_path)

            self.assertEqual(report["metrics"]["translation_coverage_numerator"], 0)
            self.assertEqual(report["metrics"]["accepted_evidence_semantic_pass_count"], 1)
            self.assertIn("no_translator_generated_semantic_pass", report["readiness"]["blockers"])

    def test_report_defaults_missing_accepted_evidence_count_for_legacy_coverage_json(self) -> None:
        with tempfile.TemporaryDirectory(prefix="milestone-release-report-") as tmp:
            root = Path(tmp)
            payload = self._coverage_report()
            payload["capability_delta_ledger"].pop("accepted_evidence_semantic_pass_count")
            coverage_path = root / "coverage.json"
            coverage_path.write_text(json.dumps(payload), encoding="utf-8")

            report = milestone_release_report.build_report(root, coverage_report_path=coverage_path)

            self.assertEqual(report["metrics"]["accepted_evidence_semantic_pass_count"], 0)

    def test_report_classifies_l3_semantic_pass_as_translation_numerator(self) -> None:
        with tempfile.TemporaryDirectory(prefix="milestone-release-report-") as tmp:
            root = Path(tmp)
            payload = self._coverage_report()
            payload["capability_delta_ledger"]["generated_candidate_status"] = {"semantic_pass": 3}
            payload["capability_delta_ledger"]["route_levels"] = {"L3": 3}
            payload["capability_delta_ledger"]["route_statuses"] = {"accepted": 3}
            payload["capability_delta_ledger"]["translator_generated_semantic_pass_count"] = 3
            payload["capability_delta_ledger"]["semantic_pass_count"] = 3
            payload["capability_delta_ledger"]["delta_count"] = 3
            payload["capability_delta_ledger"]["ledgers"] = [
                {
                    "path": f"validation/evidence/demo/auto-translation/slice-{index}/l3-slice-{index}-capability-delta.json",
                    "target_id": "demo",
                    "slice_id": f"slice-{index}",
                    "route_level": "L3",
                    "route_status": "accepted",
                    "delta_count": 1,
                }
                for index in range(3)
            ]
            coverage_path = root / "coverage.json"
            coverage_path.write_text(json.dumps(payload), encoding="utf-8")

            report = milestone_release_report.build_report(root, coverage_report_path=coverage_path)

            classes = report["metrics"]["candidate_classification"]
            self.assertEqual(classes["semantic_pass_delta_count"], 3)
            self.assertEqual(classes["generated_candidate_delta_count"], 0)
            self.assertEqual(report["metrics"]["translation_coverage_numerator"], 3)
            self.assertNotIn("no_translator_generated_semantic_pass", report["readiness"]["blockers"])
            self.assertNotIn("translator_generated_semantic_pass_below_p0_minimum", report["readiness"]["blockers"])

    def test_report_accepts_review_checklist_and_clears_external_review_blocker(self) -> None:
        with tempfile.TemporaryDirectory(prefix="milestone-release-report-") as tmp:
            root = Path(tmp)
            payload = self._coverage_report()
            payload["capability_delta_ledger"]["generated_candidate_status"] = {"semantic_pass": 3}
            payload["capability_delta_ledger"]["route_levels"] = {"L3": 3}
            payload["capability_delta_ledger"]["route_statuses"] = {"accepted": 3}
            payload["capability_delta_ledger"]["translator_generated_semantic_pass_count"] = 3
            payload["capability_delta_ledger"]["semantic_pass_count"] = 3
            payload["capability_delta_ledger"]["delta_count"] = 3
            payload["capability_delta_ledger"]["ledgers"] = [
                {
                    "path": f"validation/evidence/demo/auto-translation/slice-{index}/l3-slice-{index}-capability-delta.json",
                    "target_id": "demo",
                    "slice_id": f"slice-{index}",
                    "route_level": "L3",
                    "route_status": "accepted",
                    "delta_count": 1,
                }
                for index in range(3)
            ]
            coverage_path = root / "coverage.json"
            coverage_path.write_text(json.dumps(payload), encoding="utf-8")
            review_path = root / "review-checklist.json"
            review_path.write_text(json.dumps(self._review_checklist(), sort_keys=True), encoding="utf-8")

            report = milestone_release_report.build_report(
                root,
                coverage_report_path=coverage_path,
                review_checklist_paths=[review_path],
            )

            self.assertEqual(report["status"], "release_candidate")
            self.assertEqual(report["review_gate"]["status"], "passed")
            self.assertEqual(report["review_gate"]["review_count"], 1)
            self.assertNotIn("external_review_not_recorded", report["readiness"]["blockers"])
            self.assertEqual(report["release_note_inputs"]["review_gate"], report["review_gate"])

    def test_report_rejects_review_checklist_claiming_semantic_gate(self) -> None:
        with tempfile.TemporaryDirectory(prefix="milestone-release-report-") as tmp:
            root = Path(tmp)
            coverage_path = root / "coverage.json"
            coverage_path.write_text(json.dumps(self._coverage_report()), encoding="utf-8")
            review = self._review_checklist()
            review["claim_boundary"]["semantic_gate"] = True
            review_path = root / "review-checklist.json"
            review_path.write_text(json.dumps(review, sort_keys=True), encoding="utf-8")

            with self.assertRaises(SystemExit) as raised:
                milestone_release_report.build_report(
                    root,
                    coverage_report_path=coverage_path,
                    review_checklist_paths=[review_path],
                )

            self.assertIn("semantic_gate must be false", str(raised.exception))

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
            payload["capability_delta_ledger"]["generated_candidate_status"] = {"semantic_pass": 1}
            payload["capability_delta_ledger"]["route_levels"] = {"L4": 1}
            payload["capability_delta_ledger"]["route_statuses"] = {"refused": 1}
            payload["capability_delta_ledger"]["translator_generated_semantic_pass_count"] = 1
            payload["capability_delta_ledger"]["semantic_pass_count"] = 1
            coverage_path = root / "coverage.json"
            coverage_path.write_text(json.dumps(payload), encoding="utf-8")

            with self.assertRaises(SystemExit) as raised:
                milestone_release_report.build_report(root, coverage_report_path=coverage_path)

            self.assertIn("L4/refused", str(raised.exception))

    def test_rejects_semantic_count_without_semantic_status_backing(self) -> None:
        with tempfile.TemporaryDirectory(prefix="milestone-release-report-") as tmp:
            root = Path(tmp)
            payload = self._coverage_report()
            payload["capability_delta_ledger"]["generated_candidate_status"] = {"generated": 1}
            payload["capability_delta_ledger"]["route_levels"] = {"L3": 1}
            payload["capability_delta_ledger"]["route_statuses"] = {"accepted": 1}
            payload["capability_delta_ledger"]["translator_generated_semantic_pass_count"] = 1
            payload["capability_delta_ledger"]["semantic_pass_count"] = 1
            payload["capability_delta_ledger"]["ledgers"] = [
                {
                    "path": "validation/evidence/demo/auto-translation/slice/l3-slice-capability-delta.json",
                    "target_id": "demo",
                    "slice_id": "slice",
                    "route_level": "L3",
                    "route_status": "accepted",
                    "delta_count": 1,
                }
            ]
            coverage_path = root / "coverage.json"
            coverage_path.write_text(json.dumps(payload), encoding="utf-8")

            with self.assertRaises(SystemExit) as raised:
                milestone_release_report.build_report(root, coverage_report_path=coverage_path)

            self.assertIn("semantic_pass_count", str(raised.exception))

    def test_committed_flashdb_harness_review_checklist_is_valid(self) -> None:
        repo_root = Path(__file__).resolve().parents[2]
        review_path = Path("config/competition-env/review-checklists/flashdb-harness-internal-review.json")

        reviews = milestone_release_report.load_review_checklists(
            repo_root,
            review_checklist_paths=[review_path],
        )

        self.assertEqual(reviews[0]["status"], "passed")
        self.assertEqual(reviews[0]["path"], review_path.as_posix())
        self.assertFalse(reviews[0]["claim_boundary"]["semantic_gate"])
        self.assertEqual(set(reviews[0]["required_items"]), set(milestone_release_report.REQUIRED_REVIEW_CHECKLIST_ITEMS))

    def test_core_ci_runs_milestone_release_report_gate(self) -> None:
        workflow = Path(".github/workflows/core-translator-validation-ci.yml")
        text = workflow.read_text(encoding="utf-8")

        self.assertIn("python -m unittest validation.tools.test_milestone_release_report", text)
        self.assertIn("python validation/tools/milestone_release_report.py", text)
        self.assertIn("--review-checklist config/competition-env/review-checklists/flashdb-harness-internal-review.json", text)

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
                "translator_generated_semantic_pass_count": 0,
                "accepted_evidence_semantic_pass_count": 0,
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

    def _review_checklist(self) -> dict:
        required_items = [
            "harness_architecture",
            "unsafe_ledger",
            "test_coverage_matrix",
            "real_slice_evidence",
            "public_claim_boundary",
            "known_refusals",
        ]
        return {
            "schema_version": 1,
            "report_kind": "milestone-review-checklist",
            "status": "passed",
            "review_id": "review-001",
            "reviewer": {
                "kind": "internal",
                "id": "local-reviewer",
            },
            "checklist": {
                item: {
                    "status": "passed",
                    "evidence": [f"review/{item}.md"],
                    "notes": f"{item} checked",
                }
                for item in required_items
            },
            "claim_boundary": {
                "semantic_gate": False,
                "review_is_semantic_acceptance": False,
            },
        }

    def _write_competition_summary_with_metrics(
        self,
        summary_path: Path,
        workflow_metrics: dict,
        *,
        metrics_sha256: str | None = None,
    ) -> None:
        summary_path.parent.mkdir(parents=True, exist_ok=True)
        self._write_bound_patch_events(summary_path, workflow_metrics)
        self._write_bound_before_after_artifacts(summary_path, workflow_metrics)
        metrics_path = summary_path.parent / "workflow-metrics.json"
        metrics_path.write_text(json.dumps(workflow_metrics, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        summary_path.write_text(
            json.dumps(
                {
                    "schema_version": 1,
                    "run_id": workflow_metrics["run_id"],
                    "proof_class": workflow_metrics["proof_class"],
                    "profile_id": "huawei-competition-ubuntu-24.04",
                    "profile_sha256": "0" * 64,
                    "clang_source": "missing",
                    "cargo_mirror_activation": {
                        "method": "CARGO_HOME",
                        "path": "config/competition-env/cargo",
                        "config_file": "config/competition-env/cargo/config.toml",
                    },
                    "elapsed_seconds": workflow_metrics["wall_clock_seconds"],
                    "translator_version": "test",
                    "slices": {
                        "attempted": workflow_metrics["units_total"],
                        "typed_ir_generated": workflow_metrics["units_converged"],
                        "compiled": workflow_metrics["units_total"],
                        "semantic_pass": workflow_metrics["units_converged"],
                        "refused": 0,
                        "blocked": 0,
                        "failed": 0,
                    },
                    "unsafe_budget": {
                        "status": "passed",
                        "total_first_party_non_test_unsafe": workflow_metrics["unsafe_reduction"][
                            "current_total_unsafe"
                        ],
                        "ratio": workflow_metrics["unsafe_reduction"]["ratio"],
                    },
                    "workflow_metrics": {
                        "path": "workflow-metrics.json",
                        "sha256": metrics_sha256 or sha256_file(metrics_path),
                    },
                    "artifact_roots": [
                        "target/competition-out/evidence",
                        "target/competition-out/summary",
                        "target/competition-out/logs",
                    ],
                    "final_gate": {
                        "status": "passed",
                        "validator": "validate_auto_translation_evidence.py --require-semantic-pass",
                    },
                },
                indent=2,
                sort_keys=True,
            )
            + "\n",
            encoding="utf-8",
        )

    def _write_bound_patch_events(self, summary_path: Path, workflow_metrics: dict) -> None:
        for unit in workflow_metrics.get("per_unit_statuses", []):
            repair_history = unit.get("repair_history") if isinstance(unit, dict) else None
            if not isinstance(repair_history, dict):
                continue
            patch_events_path = summary_path.parent / repair_history["patch_events_path"]
            patch_events_path.write_text('{"status":"verified"}\n', encoding="utf-8")
            repair_history["patch_events_sha256"] = sha256_file(patch_events_path)

    def _write_bound_before_after_artifacts(self, summary_path: Path, workflow_metrics: dict) -> None:
        for unit in workflow_metrics.get("per_unit_statuses", []):
            before_after = unit.get("translation_before_after") if isinstance(unit, dict) else None
            if not isinstance(before_after, dict):
                continue
            for key in ["baseline", "final", "oracle_evidence", "accepted_patch", "patch_log"]:
                artifact = before_after.get(key)
                if not isinstance(artifact, dict) or not isinstance(artifact.get("path"), str):
                    continue
                artifact_path = summary_path.parent.parent / artifact["path"]
                artifact_path.parent.mkdir(parents=True, exist_ok=True)
                artifact_path.write_text(f"{key}\n", encoding="utf-8")
                artifact["sha256"] = sha256_file(artifact_path)

    def _write_batch_profile_report_with_exhibit(
        self,
        summary_path: Path,
        workflow_metrics: dict,
        *,
        exhibit_sha256: str | None = None,
    ) -> Path:
        root = summary_path.parents[3]
        workflow_metrics_path = summary_path.parent / "workflow-metrics.json"
        exhibit_path = summary_path.parent / "before-after-exhibit.json"
        profile_path = summary_path.parent.parent / "harness" / "planned-batch.json"
        profile_path.parent.mkdir(parents=True, exist_ok=True)
        profile_path.write_text(
            json.dumps({"schema_version": 1, "profile_id": "demo-before-after"}, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        before_after_unit = workflow_metrics["per_unit_statuses"][0]["translation_before_after"]
        repair_history = workflow_metrics["per_unit_statuses"][0].get("repair_history")
        exhibit_unit = {
            "unit_id": "demo/store-add-one",
            "status": "converged",
            "baseline": before_after_unit["baseline"],
            "final": before_after_unit["final"],
            "oracle_evidence": before_after_unit["oracle_evidence"],
            "accepted_patch": before_after_unit["accepted_patch"],
            "patch_log": before_after_unit["patch_log"],
            "unsafe_reduction": before_after_unit["unsafe_reduction"],
        }
        if isinstance(repair_history, dict):
            exhibit_unit["repair_history"] = repair_history
        repairer = {"stage": "repairer", "status": "not_exercised"}
        if isinstance(repair_history, dict):
            repairer = {
                "stage": "repairer",
                "status": "verified",
                "repair_round_cap": 5,
                "observed_repair_unit_count": 1,
                "avg_repair_rounds": workflow_metrics["avg_repair_rounds"],
                "auto_recovery_rate": workflow_metrics["auto_recovery_rate"],
                "root_cause_counts": workflow_metrics["root_cause_counts"],
                "histories": [
                    {
                        "unit_id": "demo/store-add-one",
                        "source": "opencode-worker",
                        "status": "converged",
                        "repair_rounds": workflow_metrics["per_unit_statuses"][0]["repair_rounds"],
                        "auto_recovered": True,
                        "verified": True,
                        "repair_history": repair_history,
                    }
                ],
            }
        exhibit_payload = {
            "schema_version": 1,
            "report_kind": "before-after-exhibit",
            "status": "passed",
            "run_id": workflow_metrics["run_id"],
            "profile_id": "demo-before-after",
            "proof_class": workflow_metrics["proof_class"],
            "mode": "deterministic",
            "inputs": {
                "profile": {
                    "path": self._repo_rel(root, profile_path),
                    "sha256": sha256_file(profile_path),
                },
                "competition_summary": {
                    "path": self._repo_rel(root, summary_path),
                    "sha256": sha256_file(summary_path),
                },
                "workflow_metrics": {
                    "path": self._repo_rel(root, workflow_metrics_path),
                    "sha256": sha256_file(workflow_metrics_path),
                },
            },
            "translation_before_after": {
                "status": "bound",
                "unit_count": 1,
                "measured_unsafe_unit_count": 1,
                "accepted_patch_unit_count": 1,
            },
            "stage_contracts": {
                "planner": {"stage": "planner", "status": "planned"},
                "worker": {"stage": "worker", "status": "passed"},
                "verifier": {"stage": "verifier", "status": "passed"},
                "repairer": repairer,
                "reporter": {"stage": "reporter", "status": "passed"},
            },
            "units": [exhibit_unit],
        }
        exhibit_path.write_text(json.dumps(exhibit_payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        batch_profile_report = summary_path.parent.parent / "harness" / "batch-profile-report.json"
        batch_profile_report.parent.mkdir(parents=True, exist_ok=True)
        batch_payload = {
            "schema_version": 1,
            "status": "completed",
            "run_id": workflow_metrics["run_id"],
            "before_after_exhibit_report": {
                "path": self._repo_rel(root, exhibit_path),
                "sha256": exhibit_sha256 or sha256_file(exhibit_path),
                "status": "passed",
                "report_kind": "before-after-exhibit",
                "unit_count": 1,
                "measured_unsafe_unit_count": 1,
                "accepted_patch_unit_count": 1,
            },
        }
        batch_profile_report.write_text(json.dumps(batch_payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        return batch_profile_report

    def _measured_workflow_metrics(self) -> dict:
        return {
            "schema_version": 1,
            "run_id": "run-measured",
            "proof_class": "local-simulation",
            "units_total": 2,
            "units_converged": 2,
            "units_baseline_only": 0,
            "unsafe_reduction": {
                "status": "measured",
                "baseline_total_unsafe": 5,
                "current_total_unsafe": 2,
                "reduced_by": 3,
                "ratio": 0.4,
            },
            "translation_before_after": {
                "status": "not_provided",
                "unit_count": 0,
                "measured_unsafe_unit_count": 0,
                "accepted_patch_unit_count": 0,
                "units": [],
            },
            "avg_repair_rounds": 1.5,
            "auto_recovery_rate": 0.5,
            "human_interventions": 0,
            "always_compiles": True,
            "always_equivalent": True,
            "fail_closed_count": 0,
            "root_cause_counts": {"rustc_compile_error": 1},
            "wall_clock_seconds": 12,
            "llm_calls": 4,
            "per_unit_statuses": [
                {
                    "unit_id": "demo/a",
                    "status": "converged",
                    "repair_rounds": 2,
                    "auto_recovered": True,
                    "repair_history": {
                        "patch_events_path": "retry-repair-history-a.jsonl",
                        "patch_events_sha256": "1" * 64,
                        "statuses": ["failed", "verified"],
                        "rollback_ids": ["target/competition-out/workers/worker-a/harness/rollback.json"],
                        "verified": True,
                    },
                    "root_cause_key": "rustc_compile_error",
                },
                {
                    "unit_id": "demo/b",
                    "status": "converged",
                    "auto_recovered": False,
                },
            ],
        }

    def _before_after_workflow_metrics(self) -> dict:
        payload = self._measured_workflow_metrics()
        before_after = {
            "status": "bound",
            "baseline": {"path": "evidence/before-after/baseline-unsafe.rs", "sha256": "0" * 64},
            "final": {"path": "evidence/before-after/final-safe.rs", "sha256": "0" * 64},
            "oracle_evidence": {"path": "evidence/before-after/oracle-diff.json", "sha256": "0" * 64},
            "accepted_patch": {"path": "evidence/before-after/accepted.patch", "sha256": "0" * 64},
            "patch_log": {"path": "evidence/before-after/step-log.jsonl", "sha256": "0" * 64},
            "unsafe_reduction": {
                "status": "measured",
                "baseline_total_unsafe": 3,
                "current_total_unsafe": 0,
                "reduced_by": 3,
                "ratio": 0.0,
            },
        }
        payload["per_unit_statuses"][0]["unit_id"] = "demo/store-add-one"
        payload["translation_before_after"] = {
            "status": "bound",
            "unit_count": 1,
            "measured_unsafe_unit_count": 1,
            "accepted_patch_unit_count": 1,
            "units": [
                {
                    "unit_id": "demo/store-add-one",
                    "status": "bound",
                    "unsafe_reduction": {
                        "status": "measured",
                        "baseline_total_unsafe": 3,
                        "current_total_unsafe": 0,
                        "reduced_by": 3,
                        "ratio": 0.0,
                    },
                }
            ],
        }
        payload["per_unit_statuses"][0]["translation_before_after"] = before_after
        return payload

    def _repo_rel(self, root: Path, path: Path) -> str:
        return path.relative_to(root).as_posix()


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


if __name__ == "__main__":
    unittest.main()
