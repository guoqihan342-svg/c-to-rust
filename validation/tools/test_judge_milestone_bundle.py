import json
import tempfile
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]


def repo_relative(path: Path) -> str:
    return path.relative_to(REPO_ROOT).as_posix()


def write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


class JudgeMilestoneBundleTests(unittest.TestCase):
    def test_bundle_binds_all_entrypoints_metrics_and_opencode_runtime(self) -> None:
        from validation.tools import judge_milestone_bundle as bundle

        temp_dir = Path(tempfile.mkdtemp(prefix="judge-milestone-bundle-", dir=REPO_ROOT / "target"))
        readiness_path = temp_dir / "summary" / "judge-entrypoints-readiness.json"
        run_report_path = temp_dir / "summary" / "judge-entrypoints-run-report.json"
        out_path = temp_dir / "summary" / "judge-milestone-bundle.json"
        before_metrics_path = temp_dir / "before-after" / "summary" / "workflow-metrics.json"
        before_index_path = temp_dir / "before-after" / "harness" / "judge-evidence-index.json"
        opencode_metrics_path = temp_dir / "opencode" / "summary" / "workflow-metrics.json"
        opencode_index_path = temp_dir / "opencode" / "harness" / "judge-evidence-index.json"

        write_json(readiness_path, {"report_kind": "judge-entrypoints-readiness", "status": "passed"})
        write_json(
            before_metrics_path,
            {
                "report_kind": "workflow-metrics",
                "units_total": 1,
                "units_converged": 1,
                "avg_repair_rounds": 1.0,
                "auto_recovery_rate": 1.0,
                "human_interventions": 0,
                "llm_calls": 1,
                "unsafe_reduction": {
                    "status": "measured",
                    "baseline_total_unsafe": 2,
                    "current_total_unsafe": 0,
                    "reduced_by": 2,
                },
            },
        )
        write_json(
            before_index_path,
            {
                "report_kind": "judge-evidence-index",
                "harness_architecture": {
                    "graph_runtime": "opencode-harness-langgraph-inspired",
                    "graph_nodes": ["load_plan", "fanout_workers", "worker", "repair_retry", "merge", "report"],
                    "worker_count": 1,
                    "retry_policy": {"round_cap": 5, "checkpoint": "repair_hints"},
                    "architecture_contracts": {
                        "agent_coordination": {
                            "roles": ["planner", "worker", "repairer", "verifier", "reporter"],
                            "checkpoint_backend": "sqlite",
                            "chat_output_is_evidence": False,
                            "semantic_gate": False,
                        }
                    },
                },
                "core_translation_quality": {
                    "final_gate_status": "passed",
                    "semantic_pass_count": 1,
                    "translation_coverage_numerator": 0,
                    "generated_draft_semantic_pass": False,
                    "unsafe_reduction": {
                        "status": "measured",
                        "baseline_total_unsafe": 2,
                        "current_total_unsafe": 0,
                        "reduced_by": 2,
                    },
                },
                "judge_headline": {
                    "report_kind": "judge-headline",
                    "worker_count": 1,
                    "repair_round_cap": 5,
                    "semantic_gate": False,
                    "opencode_runtime": {"enabled": False, "semantic_gate": False},
                },
            },
        )
        write_json(
            opencode_metrics_path,
            {
                "report_kind": "workflow-metrics",
                "units_total": 2,
                "units_converged": 2,
                "avg_repair_rounds": 0.0,
                "auto_recovery_rate": 0.0,
                "human_interventions": 0,
                "llm_calls": 0,
                "unsafe_reduction": {"status": "not_measured"},
            },
        )
        write_json(
            opencode_index_path,
            {
                "report_kind": "judge-evidence-index",
                "judge_headline": {
                    "report_kind": "judge-headline",
                    "worker_count": 2,
                    "repair_round_cap": 5,
                    "semantic_gate": False,
                    "opencode_runtime": {
                        "enabled": True,
                        "worker_count": 2,
                        "all_contracts_executed": True,
                        "chat_output_is_evidence": False,
                        "semantic_gate": False,
                    },
                },
                "opencode_agent_runtime": {
                    "runtime": "opencode",
                    "worker_count": 2,
                    "all_contracts_executed": True,
                    "chat_output_is_evidence": False,
                    "semantic_gate": False,
                },
            },
        )
        write_json(
            run_report_path,
            {
                "report_kind": "judge-entrypoints-run-report",
                "status": "passed",
                "entrypoint_count": 2,
                "readiness_report": {"path": repo_relative(readiness_path), "status": "present"},
                "claim_boundary": {"semantic_gate": False, "semantic_claim_source": "validator-owned-artifacts"},
                "summary": {
                    "headline": "Judge entrypoints passed: 2/2 executed; semantic_gate=false",
                    "readiness": {
                        "all_entrypoints_executed": True,
                        "executed_count": 2,
                        "configured_count": 2,
                        "validation_status": "passed",
                    },
                    "claim_boundary": {
                        "semantic_gate": False,
                        "semantic_claim_source": "validator-owned-artifacts",
                        "generated_draft_semantic_pass": False,
                        "translation_coverage_numerator": 0,
                    },
                },
                "entrypoints": [
                    {
                        "id": "before_after_judge_demo",
                        "purpose": "core-translation-before-after-exhibit",
                        "status": "passed",
                        "exit_code": 0,
                        "proof_class": "local-simulation",
                        "run_id": "before-after",
                        "judge_focus": ["unsafe reduction"],
                        "key_artifacts": {
                            "workflow_metrics": repo_relative(before_metrics_path),
                            "judge_evidence_index": repo_relative(before_index_path),
                        },
                    },
                    {
                        "id": "opencode_multi_worker_evaluate_profile",
                        "purpose": "harness-architecture-opencode-multi-worker-evaluate",
                        "status": "passed",
                        "exit_code": 0,
                        "proof_class": "local-simulation",
                        "run_id": "opencode",
                        "judge_focus": ["OpenCode multi-worker runtime"],
                        "key_artifacts": {
                            "workflow_metrics": repo_relative(opencode_metrics_path),
                            "judge_evidence_index": repo_relative(opencode_index_path),
                        },
                    },
                ],
            },
        )

        report = bundle.build_judge_milestone_bundle(
            run_report_path=run_report_path,
            out_path=out_path,
            repo_root=REPO_ROOT,
        )

        self.assertEqual(report["report_kind"], "judge-milestone-bundle")
        self.assertEqual(report["status"], "passed")
        self.assertFalse(report["claim_boundary"]["semantic_gate"])
        self.assertFalse(report["claim_boundary"]["generated_draft_semantic_pass"])
        self.assertEqual(report["claim_boundary"]["translation_coverage_numerator"], 0)
        self.assertIn("2/2 executed", report["summary"]["headline"])
        self.assertEqual(report["judge_entrypoints_run_report"]["path"], repo_relative(run_report_path))
        self.assertEqual(report["entrypoints"][0]["artifacts"]["workflow_metrics"]["status"], "present")
        self.assertIn("sha256", report["entrypoints"][0]["artifacts"]["workflow_metrics"])
        self.assertEqual(report["workflow_metrics"]["rollup"]["source_count"], 2)
        self.assertEqual(report["workflow_metrics"]["rollup"]["units_total"], 3)
        self.assertEqual(report["workflow_metrics"]["rollup"]["units_converged"], 3)
        self.assertEqual(report["workflow_metrics"]["rollup"]["measured_unsafe_reduction_source_count"], 1)
        self.assertEqual(report["opencode_runtime"]["enabled_entrypoint_count"], 1)
        self.assertTrue(report["opencode_runtime"]["all_contracts_executed"])
        self.assertTrue(report["opencode_runtime"]["chat_output_is_evidence_false"])
        self.assertEqual(report["claim_scope"]["external_review_index_ready"], True)
        self.assertEqual(report["claim_scope"]["semantic_acceptance_ready"], False)
        self.assertEqual(report["claim_scope"]["competition_exact_ready"], False)
        self.assertEqual(report["claim_scope"]["translator_generated_coverage_ready"], False)
        self.assertEqual(report["publishability"]["all_entrypoints_run_publishable"], True)
        self.assertEqual(report["publishability"]["competition_exact_publishable"], False)
        self.assertEqual(report["unsafe_reduction_scope"]["scope"], "partial")
        self.assertFalse(report["unsafe_reduction_scope"]["all_sources_measured"])
        self.assertEqual(report["unsafe_reduction_scope"]["measured_units"], 1)
        self.assertEqual(report["unsafe_reduction_scope"]["total_units"], 3)
        self.assertEqual(report["semantic_evidence_rollup"]["translation_coverage_numerator"], 0)
        self.assertFalse(report["semantic_evidence_rollup"]["accepted_evidence_counts_as_translator_coverage"])
        self.assertEqual(report["core_translation_quality"]["final_gate_statuses"], ["passed"])
        self.assertEqual(report["core_translation_quality"]["unsafe_reduction"]["baseline_total_unsafe"], 2)
        self.assertEqual(report["core_translation_quality"]["unsafe_reduction"]["current_total_unsafe"], 0)
        self.assertFalse(report["core_translation_quality"]["generated_draft_semantic_pass"])
        self.assertEqual(report["harness_architecture_summary"]["graph_runtime"], "opencode-harness-langgraph-inspired")
        self.assertEqual(report["harness_architecture_summary"]["repair_round_cap"], 5)
        self.assertIn("planner", report["harness_architecture_summary"]["roles"])
        self.assertFalse(report["harness_architecture_summary"]["semantic_gate"])
        self.assertEqual(report["proof_classes"]["all"], ["local-simulation"])
        self.assertEqual(report["proof_class_rollup"]["highest_proof_class"], "local-simulation")
        self.assertFalse(report["proof_classes"]["has_competition_exact"])
        self.assertIn("local_simulation_not_competition_exact", [gap["gap_id"] for gap in report["known_gaps"]])
        self.assertIn("accepted_evidence_is_not_translator_generated_coverage", report["must_not_claim"])
        self.assertIn("opencode_chat_output_is_semantic_evidence", report["must_not_claim"])
        self.assertIn("run_judge_entrypoints", report["reproduction_commands"])
        self.assertEqual(len(report["reproduction_commands"]["entrypoints"]), 2)
        self.assertEqual(report["retention_policy"]["report_kind"], "milestone-retention-policy")
        self.assertTrue(out_path.is_file())
        self.assertEqual(json.loads(out_path.read_text(encoding="utf-8")), report)

    def test_bundle_blocks_focused_run_from_external_milestone_claim(self) -> None:
        from validation.tools import judge_milestone_bundle as bundle

        temp_dir = Path(tempfile.mkdtemp(prefix="judge-milestone-focused-", dir=REPO_ROOT / "target"))
        run_report_path = temp_dir / "summary" / "judge-entrypoints-run-report.json"
        out_path = temp_dir / "summary" / "judge-milestone-bundle.json"
        write_json(
            run_report_path,
            {
                "report_kind": "judge-entrypoints-run-report",
                "status": "passed",
                "entrypoint_count": 1,
                "claim_boundary": {"semantic_gate": False, "semantic_claim_source": "validator-owned-artifacts"},
                "summary": {
                    "headline": "Judge entrypoints passed: 1/4 executed; semantic_gate=false",
                    "readiness": {
                        "all_entrypoints_executed": False,
                        "executed_count": 1,
                        "configured_count": 4,
                        "validation_status": "passed",
                    },
                    "claim_boundary": {
                        "semantic_gate": False,
                        "generated_draft_semantic_pass": False,
                        "translation_coverage_numerator": 0,
                    },
                },
                "entrypoints": [
                    {
                        "id": "before_after_judge_demo",
                        "status": "passed",
                        "exit_code": 0,
                        "key_artifacts": {},
                    }
                ],
            },
        )

        report = bundle.build_judge_milestone_bundle(
            run_report_path=run_report_path,
            out_path=out_path,
            repo_root=REPO_ROOT,
        )

        self.assertEqual(report["status"], "blocked")
        self.assertIn("not_all_entrypoints_executed", report["blockers"])
        self.assertFalse(report["summary"]["external_milestone_claim_ready"])
        self.assertFalse(report["claim_boundary"]["semantic_gate"])

    def test_bundle_prefers_post_run_validation_artifact_refs_over_key_artifact_paths(self) -> None:
        from validation.tools import judge_milestone_bundle as bundle

        temp_dir = Path(tempfile.mkdtemp(prefix="judge-milestone-validated-refs-", dir=REPO_ROOT / "target"))
        run_report_path = temp_dir / "summary" / "judge-entrypoints-run-report.json"
        out_path = temp_dir / "summary" / "judge-milestone-bundle.json"
        metrics_path = temp_dir / "validated" / "summary" / "workflow-metrics.json"
        write_json(
            metrics_path,
            {
                "report_kind": "workflow-metrics",
                "units_total": 1,
                "units_converged": 1,
                "unsafe_reduction": {"status": "not_measured"},
            },
        )
        write_json(
            run_report_path,
            {
                "report_kind": "judge-entrypoints-run-report",
                "status": "passed",
                "entrypoint_count": 1,
                "claim_boundary": {"semantic_gate": False, "semantic_claim_source": "validator-owned-artifacts"},
                "summary": {
                    "readiness": {
                        "all_entrypoints_executed": True,
                        "executed_count": 1,
                        "configured_count": 1,
                        "validation_status": "passed",
                    },
                    "claim_boundary": {
                        "semantic_gate": False,
                        "generated_draft_semantic_pass": False,
                        "translation_coverage_numerator": 0,
                    },
                },
                "entrypoints": [
                    {
                        "id": "multi_worker_evaluate_profile",
                        "status": "passed",
                        "exit_code": 0,
                        "key_artifacts": {"workflow_metrics": "target/missing/path/workflow-metrics.json"},
                    }
                ],
                "validation": {
                    "status": "passed",
                    "entrypoints": [
                        {
                            "id": "multi_worker_evaluate_profile",
                            "expected_artifacts": {
                                "workflow_metrics": {
                                    "path": repo_relative(metrics_path),
                                    "sha256": bundle.validator.sha256_file(metrics_path),
                                    "status": "present",
                                }
                            },
                        }
                    ],
                },
            },
        )

        report = bundle.build_judge_milestone_bundle(
            run_report_path=run_report_path,
            out_path=out_path,
            repo_root=REPO_ROOT,
        )

        workflow_ref = report["entrypoints"][0]["artifacts"]["workflow_metrics"]
        self.assertEqual(workflow_ref["path"], repo_relative(metrics_path))
        self.assertEqual(workflow_ref["status"], "present")
        self.assertIn("sha256", workflow_ref)
        self.assertEqual(report["workflow_metrics"]["rollup"]["source_count"], 1)

    def test_bundle_blocks_source_translation_coverage_or_generated_semantic_claims(self) -> None:
        from validation.tools import judge_milestone_bundle as bundle

        temp_dir = Path(tempfile.mkdtemp(prefix="judge-milestone-overclaim-", dir=REPO_ROOT / "target"))
        run_report_path = temp_dir / "summary" / "judge-entrypoints-run-report.json"
        out_path = temp_dir / "summary" / "judge-milestone-bundle.json"
        write_json(
            run_report_path,
            {
                "report_kind": "judge-entrypoints-run-report",
                "status": "passed",
                "claim_boundary": {"semantic_gate": False, "semantic_claim_source": "validator-owned-artifacts"},
                "summary": {
                    "readiness": {
                        "all_entrypoints_executed": True,
                        "executed_count": 1,
                        "configured_count": 1,
                        "validation_status": "passed",
                    },
                    "claim_boundary": {
                        "semantic_gate": False,
                        "generated_draft_semantic_pass": True,
                        "translation_coverage_numerator": 1,
                    },
                },
                "entrypoints": [
                    {
                        "id": "before_after_judge_demo",
                        "status": "passed",
                        "exit_code": 0,
                        "proof_class": "local-simulation",
                        "key_artifacts": {},
                    }
                ],
            },
        )

        report = bundle.build_judge_milestone_bundle(
            run_report_path=run_report_path,
            out_path=out_path,
            repo_root=REPO_ROOT,
        )

        self.assertEqual(report["status"], "blocked")
        self.assertIn("source_generated_draft_semantic_pass_must_be_false", report["blockers"])
        self.assertIn("source_translation_coverage_numerator_must_be_zero", report["blockers"])
        self.assertFalse(report["claim_boundary"]["generated_draft_semantic_pass"])
        self.assertEqual(report["claim_boundary"]["translation_coverage_numerator"], 0)
        self.assertEqual(report["semantic_evidence_rollup"]["translator_generated_semantic_pass_count"], 0)
        self.assertEqual(report["semantic_evidence_rollup"]["source_translation_coverage_numerator"], 1)

    def test_bundle_blocks_core_quality_artifact_translation_coverage_claims(self) -> None:
        from validation.tools import judge_milestone_bundle as bundle

        temp_dir = Path(tempfile.mkdtemp(prefix="judge-milestone-core-quality-overclaim-", dir=REPO_ROOT / "target"))
        run_report_path = temp_dir / "summary" / "judge-entrypoints-run-report.json"
        out_path = temp_dir / "summary" / "judge-milestone-bundle.json"
        index_path = temp_dir / "before-after" / "harness" / "judge-evidence-index.json"
        write_json(
            index_path,
            {
                "report_kind": "judge-evidence-index",
                "core_translation_quality": {
                    "final_gate_status": "passed",
                    "semantic_pass_count": 1,
                    "translation_coverage_numerator": 1,
                    "generated_draft_semantic_pass": True,
                },
            },
        )
        write_json(
            run_report_path,
            {
                "report_kind": "judge-entrypoints-run-report",
                "status": "passed",
                "claim_boundary": {"semantic_gate": False, "semantic_claim_source": "validator-owned-artifacts"},
                "summary": {
                    "readiness": {
                        "all_entrypoints_executed": True,
                        "executed_count": 1,
                        "configured_count": 1,
                        "validation_status": "passed",
                    },
                    "claim_boundary": {
                        "semantic_gate": False,
                        "generated_draft_semantic_pass": False,
                        "translation_coverage_numerator": 0,
                    },
                },
                "entrypoints": [
                    {
                        "id": "before_after_judge_demo",
                        "status": "passed",
                        "exit_code": 0,
                        "proof_class": "local-simulation",
                        "key_artifacts": {"judge_evidence_index": repo_relative(index_path)},
                    }
                ],
            },
        )

        report = bundle.build_judge_milestone_bundle(
            run_report_path=run_report_path,
            out_path=out_path,
            repo_root=REPO_ROOT,
        )

        self.assertEqual(report["status"], "blocked")
        self.assertIn("core_quality_generated_draft_semantic_pass_must_be_false", report["blockers"])
        self.assertIn("core_quality_translation_coverage_numerator_must_be_zero", report["blockers"])

    def test_bundle_blocks_opencode_runtime_missing_explicit_evidence_boundary_fields(self) -> None:
        from validation.tools import judge_milestone_bundle as bundle

        temp_dir = Path(tempfile.mkdtemp(prefix="judge-milestone-opencode-missing-", dir=REPO_ROOT / "target"))
        run_report_path = temp_dir / "summary" / "judge-entrypoints-run-report.json"
        out_path = temp_dir / "summary" / "judge-milestone-bundle.json"
        opencode_index_path = temp_dir / "opencode" / "harness" / "judge-evidence-index.json"
        write_json(
            opencode_index_path,
            {
                "report_kind": "judge-evidence-index",
                "judge_headline": {
                    "opencode_runtime": {
                        "enabled": True,
                        "worker_count": 1,
                        "all_contracts_executed": True,
                    }
                },
                "opencode_agent_runtime": {
                    "runtime": "opencode",
                    "worker_count": 1,
                    "all_contracts_executed": True,
                },
            },
        )
        write_json(
            run_report_path,
            {
                "report_kind": "judge-entrypoints-run-report",
                "status": "passed",
                "claim_boundary": {"semantic_gate": False, "semantic_claim_source": "validator-owned-artifacts"},
                "summary": {
                    "readiness": {
                        "all_entrypoints_executed": True,
                        "executed_count": 1,
                        "configured_count": 1,
                        "validation_status": "passed",
                    },
                    "claim_boundary": {
                        "semantic_gate": False,
                        "generated_draft_semantic_pass": False,
                        "translation_coverage_numerator": 0,
                    },
                },
                "entrypoints": [
                    {
                        "id": "opencode_multi_worker_evaluate_profile",
                        "status": "passed",
                        "exit_code": 0,
                        "proof_class": "local-simulation",
                        "key_artifacts": {"judge_evidence_index": repo_relative(opencode_index_path)},
                    }
                ],
            },
        )

        report = bundle.build_judge_milestone_bundle(
            run_report_path=run_report_path,
            out_path=out_path,
            repo_root=REPO_ROOT,
        )

        self.assertEqual(report["status"], "blocked")
        self.assertIn("opencode_runtime_boundary_fields_missing", report["blockers"])
        self.assertFalse(report["opencode_evidence_policy"]["boundary_fields_explicit"])


if __name__ == "__main__":
    unittest.main()
