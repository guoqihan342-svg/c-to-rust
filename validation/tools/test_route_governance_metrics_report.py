import json
import tempfile
import unittest
from pathlib import Path

from validation.tools import route_governance_metrics_report


class RouteGovernanceMetricsReportTests(unittest.TestCase):
    def test_report_combines_ledger_metrics_and_candidate_inventory_without_semantic_expansion(self) -> None:
        with tempfile.TemporaryDirectory(prefix="route-governance-metrics-") as tmp:
            root = Path(tmp)
            coverage_path = root / "coverage.json"
            coverage_path.write_text(json.dumps(self._coverage_report()), encoding="utf-8")
            self._write_json(
                root / "validation/evidence/demo/auto-translation/refused/l3-refused-route-decision.json",
                {
                    "schema_version": 1,
                    "status": "recorded",
                    "level": "L4",
                    "candidate_generation": {
                        "governance_summary": {
                            "route_level": "L4",
                            "route_status": "refused",
                        },
                        "selected_candidate_id": None,
                        "generated_draft_semantic_pass": False,
                        "candidate_set": [
                            {
                                "candidate_id": "compat:legacy-string-translator",
                                "kind": "legacy-string-translator",
                                "status": "generated",
                                "role": "compatibility_rust_draft",
                                "compatibility_only": True,
                                "semantic_pass": False,
                            },
                            {
                                "candidate_id": "typed-ir:clang-lowered",
                                "kind": "typed-ir",
                                "status": "not_available",
                                "role": "typed_ir_candidate_signal",
                                "semantic_pass": False,
                            },
                        ],
                    },
                },
            )
            self._write_json(
                root / "validation/evidence/demo/auto-translation/refused/l3-refused-evidence-manifest.json",
                {
                    "schema_version": 1,
                    "status": "incomplete",
                    "target_id": "demo",
                    "slice_id": "refused",
                    "fixture": {
                        "operation_count": 2,
                    },
                },
            )
            self._write_json(
                root / "validation/evidence/demo/auto-translation/refused/l3-refused-final-verification.json",
                {
                    "schema_version": 1,
                    "status": "incomplete",
                    "target_id": "demo",
                    "slice_id": "refused",
                    "semantic_pass": False,
                    "c_oracle_status": "SKIPPED_LOCAL_NO_C_TOOLCHAIN",
                    "skipped_gates": [
                        {"gate": "candidate_generation", "reason": "route_refused"},
                        {"gate": "c_oracle_diff", "reason": "SKIPPED_LOCAL_NO_C_TOOLCHAIN"},
                    ],
                },
            )
            self._write_json(
                root
                / "validation/evidence/demo/auto-translation/refused/l3-refused-self-healing-blocked-repairs.json",
                {
                    "schema_version": 1,
                    "status": "recorded",
                    "target_id": "demo",
                    "slice_id": "refused",
                    "blocked_repairs": [
                        {
                            "human_intervention_point": "Bind external callee semantics before promotion.",
                            "ir_feature_gap": {
                                "kind": "external_direct_callee_context",
                                "blocked_callees": ["helper_blocked"],
                            },
                        }
                    ],
                },
            )
            self._write_json(
                root / "validation/evidence/demo/auto-translation/refused/l3-refused-unsafe-scan.json",
                {
                    "schema_version": 1,
                    "status": "passed",
                    "target_id": "demo",
                    "slice_id": "refused",
                    "first_party_non_test_unsafe_count": 0,
                    "first_party_non_test_unsafe_ratio": 0.0,
                },
            )
            self._write_json(
                root / "validation/evidence/demo/auto-translation/refused/l3-refused-negative-diff.json",
                {
                    "schema_version": 1,
                    "status": "incomplete",
                    "target_id": "demo",
                    "slice_id": "refused",
                    "expected_failure": True,
                    "mutation_detected": False,
                    "reason_code": "missing_passed_schema_diff",
                    "blocked_by": ["schema_diff"],
                    "root_blocked_by": ["c_oracle"],
                },
            )
            self._write_json(
                root / "validation/evidence/demo/auto-translation/refused/l3-refused-performance-smoke.json",
                {
                    "schema_version": 1,
                    "status": "recorded",
                    "target_id": "demo",
                    "slice_id": "refused",
                    "secondary_only": True,
                    "semantic_pass": False,
                },
            )

            report = route_governance_metrics_report.build_report(
                root,
                coverage_report_path=coverage_path,
                evidence_root=Path("validation/evidence"),
            )

            self.assertEqual(report["status"], "passed")
            metrics = report["metrics"]
            self.assertEqual(metrics["translation_coverage_numerator"], 0)
            self.assertEqual(metrics["accepted_evidence_semantic_pass_count"], 1)
            self.assertEqual(metrics["tracked_capability_delta_ledgers"], 1)
            self.assertEqual(metrics["tracked_capability_delta_count"], 1)
            self.assertEqual(metrics["tracked_route_decision_artifacts"], 1)
            self.assertEqual(metrics["candidate_classification"]["refused_delta_count"], 1)
            self.assertEqual(metrics["candidate_classification"]["semantic_pass_delta_count"], 0)
            inventory = metrics["candidate_generation_inventory"]
            self.assertEqual(inventory["candidate_record_count"], 2)
            self.assertEqual(inventory["compatibility_only_candidate_count"], 1)
            self.assertEqual(inventory["by_kind"]["legacy-string-translator"]["compatibility_only_count"], 1)
            self.assertEqual(metrics["capability_delta_ledger"]["route_statuses"]["refused"], 1)
            self.assertEqual(metrics["tracked_slice_gate_contexts"], 1)
            context = metrics["slice_gate_contexts"][0]
            self.assertEqual(context["target_id"], "demo")
            self.assertEqual(context["slice_id"], "refused")
            self.assertEqual(context["route"], {"level": "L4", "status": "refused", "artifact_status": "recorded"})
            self.assertEqual(context["final_verification"]["status"], "incomplete")
            self.assertFalse(context["final_verification"]["semantic_pass"])
            self.assertIn("route_refused", context["failure_reasons"])
            self.assertIn("SKIPPED_LOCAL_NO_C_TOOLCHAIN", context["failure_reasons"])
            self.assertEqual(context["human_intervention_points"], ["Bind external callee semantics before promotion."])
            self.assertEqual(context["blocked_callees"], ["helper_blocked"])
            self.assertEqual(context["fixture"]["case_count"], 2)
            self.assertEqual(context["unsafe"]["first_party_non_test_unsafe_count"], 0)
            self.assertEqual(context["unsafe"]["first_party_non_test_unsafe_ratio"], 0.0)
            self.assertEqual(context["negative_diff"]["reason_code"], "missing_passed_schema_diff")
            self.assertEqual(context["negative_diff"]["blocked_by"], ["schema_diff"])
            self.assertEqual(context["negative_diff"]["root_blocked_by"], ["c_oracle"])
            self.assertEqual(context["performance_smoke"]["status"], "recorded")
            self.assertTrue(context["performance_smoke"]["secondary_only"])
            self.assertIn("not semantic acceptance evidence", report["claim_boundary"])

    def test_rejects_failed_coverage_report(self) -> None:
        with tempfile.TemporaryDirectory(prefix="route-governance-metrics-") as tmp:
            root = Path(tmp)
            coverage_path = root / "coverage.json"
            payload = self._coverage_report()
            payload["status"] = "failed"
            coverage_path.write_text(json.dumps(payload), encoding="utf-8")

            with self.assertRaises(SystemExit) as raised:
                route_governance_metrics_report.build_report(
                    root,
                    coverage_report_path=coverage_path,
                    evidence_root=Path("validation/evidence"),
                )

            self.assertIn("coverage report status must be passed", str(raised.exception))

    def test_core_ci_runs_route_governance_metrics_report_gate(self) -> None:
        workflow = Path(".github/workflows/core-translator-validation-ci.yml").read_text(encoding="utf-8")

        self.assertIn("python -m unittest validation.tools.test_route_governance_metrics_report", workflow)
        self.assertIn("python validation/tools/route_governance_metrics_report.py", workflow)

    def _coverage_report(self) -> dict:
        return {
            "schema_version": 1,
            "status": "passed",
            "matrix": {
                "path": "validation/translator-coverage-matrix.json",
                "capability_count": 11,
            },
            "capability_count": 11,
            "capability_delta_ledger": {
                "schema_version": 1,
                "status": "recorded",
                "ledger_count": 1,
                "delta_count": 1,
                "governance_delta_count": 1,
                "verification_command_count": 1,
                "semantic_pass_count": 0,
                "translator_generated_semantic_pass_count": 0,
                "accepted_evidence_semantic_pass_count": 1,
                "blocked_callee_count": 1,
                "generated_candidate_status": {"refused": 1},
                "route_levels": {"L4": 1},
                "route_statuses": {"refused": 1},
                "by_construct": {"external_direct_callee_context": {"refused": 1}},
                "ledgers": [
                    {
                        "path": "validation/evidence/demo/auto-translation/refused/l3-refused-capability-delta.json",
                        "target_id": "demo",
                        "slice_id": "refused",
                        "route_level": "L4",
                        "route_status": "refused",
                        "delta_count": 1,
                    }
                ],
                "claim_boundary": "Capability-delta ledger entries are not semantic acceptance evidence.",
            },
            "claim_boundary": "translator coverage matrix records representative regression evidence only.",
        }

    def _write_json(self, path: Path, payload: dict) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")


if __name__ == "__main__":
    unittest.main()
