import json
import tempfile
import unittest
from pathlib import Path

import jsonschema


REPO_ROOT = Path(__file__).resolve().parents[2]
SCHEMA_PATH = REPO_ROOT / "validation" / "judge-milestone-bundle.schema.json"


def repo_relative(path: Path) -> str:
    return path.relative_to(REPO_ROOT).as_posix()


def write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def route_metrics_payload(
    *,
    accepted_evidence_semantic_pass_count: int,
    tracked_route_decision_artifacts: int,
    tracked_slice_gate_contexts: int,
    s2_workflow_run_count: int,
    s2_reduced_by: int,
    blocked_repair_count: int = 0,
    blocked_repairs_status: str | None = None,
) -> dict:
    resolved_blocked_repairs_status = blocked_repairs_status or ("observed" if blocked_repair_count else "none")
    return {
        "schema_version": 1,
        "status": "passed",
        "report_kind": "route-governance-metrics",
        "inputs": {
            "translator_coverage_matrix": {
                "path": "validation/translator-coverage-matrix.json",
                "status": "passed",
                "capability_count": 11,
            },
            "evidence_governance": {
                "evidence_root": "validation/evidence",
                "status": "passed",
                "file_count": 1,
            },
        },
        "metrics": {
            "translation_coverage_numerator": 0,
            "accepted_evidence_semantic_pass_count": accepted_evidence_semantic_pass_count,
            "tracked_capability_delta_ledgers": 1,
            "tracked_capability_delta_count": 1,
            "tracked_route_decision_artifacts": tracked_route_decision_artifacts,
            "candidate_classification": {},
            "capability_delta_ledger": {},
            "s2_workflow_metrics": {
                "run_count": s2_workflow_run_count,
                "unsafe_reduction": {
                    "status": "measured" if s2_reduced_by else "not_measured",
                    "reduced_by": s2_reduced_by,
                },
            },
            "candidate_generation_inventory": {},
            "tracked_slice_gate_contexts": tracked_slice_gate_contexts,
            "slice_gate_contexts": [],
            "blocked_repairs": {
                "status": resolved_blocked_repairs_status,
                "blocked_repair_count": blocked_repair_count,
                "slice_count": 1 if blocked_repair_count else 0,
                "human_action_required_count": blocked_repair_count,
                "status_counts": {resolved_blocked_repairs_status: 1},
                "human_intervention_points": ["Bind external callee semantics before promotion."]
                if blocked_repair_count
                else [],
                "blocked_callees": ["helper_blocked"] if blocked_repair_count else [],
                "ir_feature_gap_kinds": {"external_direct_callee_context": blocked_repair_count}
                if blocked_repair_count
                else {},
                "forbidden_change_counts": {"missing_l1_evidence": blocked_repair_count}
                if blocked_repair_count
                else {},
                "smallest_next_tests": [
                    {
                        "kind": "callee_contract_replay",
                        "command": "python -B validation/tools/validate_auto_translation_evidence.py --target-id demo --slice-id refused --require-semantic-pass",
                        "expected_gate": "external callee contract is bound before candidate promotion",
                    }
                ]
                if blocked_repair_count
                else [],
                "next_actions": [
                    {
                        "repair_id": "repair-refused-1",
                        "target_id": "demo",
                        "slice_id": "refused",
                        "pipeline_id": "validation/evidence/demo/auto-translation/refused",
                        "route": "typed_ir",
                        "status": "blocked",
                        "next_action": "bind_external_callee_semantics",
                        "smallest_next_test_kind": "callee_contract_replay",
                        "smallest_next_test_command": "python -B validation/tools/validate_auto_translation_evidence.py --target-id demo --slice-id refused --require-semantic-pass",
                        "expected_gate": "external callee contract is bound before candidate promotion",
                        "human_intervention_point": "Bind external callee semantics before promotion.",
                    }
                ]
                if blocked_repair_count
                else [],
                "semantic_gate": False,
                "translation_coverage_numerator": 0,
                "boundary": "Blocked repair rollup is route-governance context only.",
            },
        },
        "denominators": {
            "capability_delta_ledger": "capability delta ledger artifacts",
            "candidate_generation_inventory": "route decision artifacts",
            "slice_gate_contexts": "slice gate contexts",
            "translation_coverage_numerator": "translator-generated semantic-pass named slices only",
            "accepted_evidence_semantic_pass_count": "accepted evidence semantic pass count is separate",
            "s2_workflow_metrics": "hash-bound competition run summaries",
            "blocked_repairs": "self-healing blocked repairs artifacts under validation/evidence",
        },
        "claim_boundary": "Route governance metrics are not semantic acceptance evidence.",
        "retention_policy": {
            "report_kind": "route-governance-metrics-retention-policy",
            "report_role": "p0-route-governance-and-capability-metrics",
            "target_artifacts": {
                "retention_class": "reproducible-local-output",
                "committed": False,
                "policy": "Regenerate from committed anchors.",
            },
            "committed_anchors": {
                "retention_class": "release-evidence",
                "policy": "Use validation/evidence manifests and config profiles.",
            },
            "claim_boundary": "Retention policy does not expand semantic acceptance or translation coverage.",
        },
    }


def evidence_governance_payload() -> dict:
    return {
        "schema_version": 1,
        "status": "passed",
        "evidence_root": "validation/evidence",
        "failed_gates": [],
        "portability": {
            "status": "passed",
            "claim_anchor_issue_count": 0,
            "profile_hash_issue_count": 0,
            "diagnostic_host_metadata_count": 3,
            "issues": [],
            "profile_hash_issues": [],
        },
        "inventory": {
            "file_count": 3,
            "total_bytes": 120,
            "retention_classes": {
                "committed_release": {"file_count": 2, "total_bytes": 100},
                "diagnostic_only": {"file_count": 1, "total_bytes": 20},
            },
            "pipelines": [
                {
                    "pipeline_id": "validation/evidence/flashdb/auto-translation/real-fdb-calc-crc32",
                    "artifact_count": 2,
                    "total_bytes": 100,
                    "runtime_ms": 40,
                    "retention_class": "committed_release",
                    "compression_policy": "do_not_compress_claim_anchors",
                    "prune_policy": "do_not_prune_without_manifest_update",
                },
                {
                    "pipeline_id": "validation/evidence/flashdb/auto-translation/diagnostic",
                    "artifact_count": 1,
                    "total_bytes": 20,
                    "runtime_ms": 5,
                    "retention_class": "diagnostic_only",
                    "compression_policy": "compress_when_large_or_superseded",
                    "prune_policy": "may_prune_after_replacement_evidence",
                },
            ],
            "runtime": {
                "observation_count": 2,
                "total_duration_ms": 45,
                "max_duration_ms": 40,
            },
            "retention_policy": {
                "compression_policy": "compress large diagnostic_only logs first",
                "prune_policy": "diagnostic_only may be pruned after replacement evidence is recorded",
            },
        },
    }


class JudgeMilestoneBundleTests(unittest.TestCase):
    def test_bundle_binds_all_entrypoints_metrics_and_opencode_runtime(self) -> None:
        from validation.tools import judge_milestone_bundle as bundle

        temp_dir = Path(tempfile.mkdtemp(prefix="judge-milestone-bundle-", dir=REPO_ROOT / "target"))
        readiness_path = temp_dir / "summary" / "judge-entrypoints-readiness.json"
        run_report_path = temp_dir / "summary" / "judge-entrypoints-run-report.json"
        out_path = temp_dir / "summary" / "judge-milestone-bundle.json"
        before_metrics_path = temp_dir / "before-after" / "summary" / "workflow-metrics.json"
        before_route_metrics_path = temp_dir / "before-after" / "summary" / "route-governance-metrics-report.json"
        evidence_governance_path = temp_dir / "competition-smoke" / "reports" / "evidence-governance.json"
        before_index_path = temp_dir / "before-after" / "harness" / "judge-evidence-index.json"
        opencode_metrics_path = temp_dir / "opencode" / "summary" / "workflow-metrics.json"
        opencode_route_metrics_path = temp_dir / "opencode" / "summary" / "route-governance-metrics-report.json"
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
                "per_unit_statuses": [
                    {
                        "unit_id": "flashdb/real-fdb-calc-crc32",
                        "repair_rounds": 1,
                        "auto_recovered": True,
                        "repair_history": {"rollback_ids": ["rollback-001"]},
                    }
                ],
            },
        )
        write_json(
            before_route_metrics_path,
            route_metrics_payload(
                accepted_evidence_semantic_pass_count=1,
                tracked_route_decision_artifacts=2,
                tracked_slice_gate_contexts=1,
                s2_workflow_run_count=1,
                s2_reduced_by=2,
            ),
        )
        write_json(evidence_governance_path, evidence_governance_payload())
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
                    "before_after_units": [
                        {
                            "unit_id": "flashdb/real-fdb-calc-crc32",
                            "status": "converged",
                            "baseline": {"path": "validation/evidence/baseline.rs", "sha256": "a" * 64},
                            "final": {"path": "validation/evidence/final.rs", "sha256": "b" * 64},
                            "accepted_patch": {"path": "validation/evidence/accepted.patch", "sha256": "c" * 64},
                            "oracle_evidence": {"path": "validation/evidence/final-verification.json", "sha256": "d" * 64},
                            "unsafe_reduction": {
                                "status": "measured",
                                "baseline_total_unsafe": 2,
                                "current_total_unsafe": 0,
                                "reduced_by": 2,
                            },
                        }
                    ],
                    "final_gate_status": "passed",
                    "repair_summary": {
                        "status": "verified",
                        "repair_round_cap": 5,
                        "observed_repair_unit_count": 1,
                        "auto_recovered_unit_count": 1,
                        "rollback_evidence_count": 1,
                    },
                    "semantic_pass_count": 1,
                    "translation_before_after": {
                        "status": "bound",
                        "unit_count": 1,
                        "measured_unsafe_unit_count": 1,
                        "accepted_patch_unit_count": 1,
                    },
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
                "per_unit_statuses": [
                    {"unit_id": "flashdb/real-fdb-blob-make", "repair_rounds": 0, "auto_recovered": False},
                    {"unit_id": "flashdb/real-fdb-kv-set", "repair_rounds": 0, "auto_recovered": False},
                ],
            },
        )
        write_json(
            opencode_route_metrics_path,
            route_metrics_payload(
                accepted_evidence_semantic_pass_count=2,
                tracked_route_decision_artifacts=2,
                tracked_slice_gate_contexts=2,
                s2_workflow_run_count=1,
                s2_reduced_by=0,
            ),
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
                "schema_version": 1,
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
                            "route_governance_metrics_report": repo_relative(before_route_metrics_path),
                            "evidence_governance_report": repo_relative(evidence_governance_path),
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
                            "route_governance_metrics_report": repo_relative(opencode_route_metrics_path),
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
        self.assertEqual(report["workflow_metrics"]["rollup"]["repair_activity"]["source_count"], 2)
        self.assertEqual(report["workflow_metrics"]["rollup"]["repair_activity"]["observed_source_count"], 1)
        self.assertEqual(report["workflow_metrics"]["rollup"]["repair_activity"]["repair_history_unit_count"], 1)
        self.assertEqual(report["workflow_metrics"]["rollup"]["repair_activity"]["auto_recovered_unit_count"], 1)
        self.assertAlmostEqual(report["workflow_metrics"]["rollup"]["repair_activity"]["avg_repair_rounds"], 1.0 / 3.0)
        self.assertAlmostEqual(report["workflow_metrics"]["rollup"]["repair_activity"]["auto_recovery_rate"], 1.0 / 3.0)
        self.assertIn("semantic gate", report["workflow_metrics"]["rollup"]["repair_activity"]["boundary"])
        self.assertEqual(report["route_governance_metrics"]["report_kind"], "route-governance-metrics-rollup")
        self.assertEqual(report["route_governance_metrics"]["rollup"]["source_count"], 2)
        self.assertEqual(report["route_governance_metrics"]["rollup"]["translation_coverage_numerator"], 0)
        self.assertEqual(report["route_governance_metrics"]["rollup"]["accepted_evidence_semantic_pass_count"], 3)
        self.assertEqual(report["route_governance_metrics"]["rollup"]["tracked_route_decision_artifacts"], 4)
        self.assertEqual(report["route_governance_metrics"]["rollup"]["tracked_slice_gate_contexts"], 3)
        self.assertEqual(report["blocked_repairs_rollup"]["rollup"]["blocked_repair_count"], 0)
        self.assertFalse(report["blocked_repairs_rollup"]["semantic_gate"])
        self.assertEqual(report["blocked_repairs_rollup"]["translation_coverage_numerator"], 0)
        self.assertTrue(report["route_governance_metrics"]["rollup"]["all_target_artifacts_reproducible"])
        self.assertTrue(report["route_governance_metrics"]["rollup"]["all_retention_policies_present"])
        self.assertEqual(report["evidence_cost_retention"]["report_kind"], "evidence-cost-retention-rollup")
        self.assertEqual(report["evidence_cost_retention"]["rollup"]["source_count"], 1)
        self.assertEqual(report["evidence_cost_retention"]["rollup"]["artifact_count"], 3)
        self.assertEqual(report["evidence_cost_retention"]["rollup"]["total_bytes"], 120)
        self.assertEqual(report["evidence_cost_retention"]["rollup"]["pipeline_count"], 2)
        self.assertEqual(report["evidence_cost_retention"]["rollup"]["runtime_ms"]["total"], 45)
        self.assertEqual(report["evidence_cost_retention"]["rollup"]["runtime_ms"]["max"], 40)
        self.assertEqual(
            report["evidence_cost_retention"]["rollup"]["retention_classes"]["committed_release"]["file_count"],
            2,
        )
        self.assertTrue(report["evidence_cost_retention"]["rollup"]["all_sources_passed"])
        self.assertEqual(report["evidence_cost_retention"]["rollup"]["portability_issue_count"], 0)
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
        self.assertIn("before_after_repair_exhibit", report)
        self.assertEqual(report["before_after_repair_exhibit"]["report_kind"], "before-after-repair-exhibit-rollup")
        self.assertEqual(report["before_after_repair_exhibit"]["rollup"]["source_count"], 1)
        self.assertEqual(report["before_after_repair_exhibit"]["rollup"]["bound_unit_count"], 1)
        self.assertEqual(report["before_after_repair_exhibit"]["rollup"]["verified_repair_source_count"], 1)
        self.assertEqual(report["before_after_repair_exhibit"]["rollup"]["auto_recovered_unit_count"], 1)
        self.assertEqual(report["before_after_repair_exhibit"]["rollup"]["unsafe_reduced_by"], 2)
        self.assertFalse(report["before_after_repair_exhibit"]["rollup"]["semantic_gate"])
        self.assertFalse(report["before_after_repair_exhibit"]["rollup"]["generated_draft_semantic_pass"])
        self.assertEqual(report["before_after_repair_exhibit"]["rollup"]["translation_coverage_numerator"], 0)
        self.assertEqual(
            report["before_after_repair_exhibit"]["sources"][0]["before_after_units"][0]["unit_id"],
            "flashdb/real-fdb-calc-crc32",
        )
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

    def test_bundle_matches_schema_and_rejects_expanded_claims(self) -> None:
        from validation.tools import judge_milestone_bundle as bundle

        temp_dir = Path(tempfile.mkdtemp(prefix="judge-milestone-schema-", dir=REPO_ROOT / "target"))
        run_report_path = temp_dir / "summary" / "judge-entrypoints-run-report.json"
        out_path = temp_dir / "summary" / "judge-milestone-bundle.json"
        metrics_path = temp_dir / "before-after" / "summary" / "workflow-metrics.json"
        index_path = temp_dir / "before-after" / "harness" / "judge-evidence-index.json"
        write_json(
            metrics_path,
            {
                "report_kind": "workflow-metrics",
                "units_total": 1,
                "units_converged": 1,
                "unsafe_reduction": {
                    "status": "measured",
                    "baseline_total_unsafe": 2,
                    "current_total_unsafe": 0,
                    "reduced_by": 2,
                },
            },
        )
        write_json(
            index_path,
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
            },
        )
        write_json(
            run_report_path,
            {
                "schema_version": 1,
                "report_kind": "judge-entrypoints-run-report",
                "status": "passed",
                "readiness_report": None,
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
                        "purpose": "core-translation-before-after-exhibit",
                        "status": "passed",
                        "exit_code": 0,
                        "proof_class": "local-simulation",
                        "run_id": "schema-test",
                        "key_artifacts": {
                            "workflow_metrics": repo_relative(metrics_path),
                            "judge_evidence_index": repo_relative(index_path),
                        },
                    }
                ],
            },
        )

        report = bundle.build_judge_milestone_bundle(
            run_report_path=run_report_path,
            out_path=out_path,
            repo_root=REPO_ROOT,
        )
        schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))

        jsonschema.validate(report, schema)

        expanded = json.loads(json.dumps(report))
        expanded["claim_scope"]["semantic_acceptance_ready"] = True
        with self.assertRaises(jsonschema.exceptions.ValidationError):
            jsonschema.validate(expanded, schema)

        expanded = json.loads(json.dumps(report))
        expanded["core_translation_quality"]["translation_coverage_numerator"] = 1
        with self.assertRaises(jsonschema.exceptions.ValidationError):
            jsonschema.validate(expanded, schema)

        missing_evidence_cost = json.loads(json.dumps(report))
        missing_evidence_cost.pop("evidence_cost_retention")
        with self.assertRaises(jsonschema.exceptions.ValidationError):
            jsonschema.validate(missing_evidence_cost, schema)

        missing_blocked_repairs = json.loads(json.dumps(report))
        missing_blocked_repairs.pop("blocked_repairs_rollup")
        with self.assertRaises(jsonschema.exceptions.ValidationError):
            jsonschema.validate(missing_blocked_repairs, schema)

        expanded = json.loads(json.dumps(report))
        expanded["blocked_repairs_rollup"]["semantic_gate"] = True
        with self.assertRaises(jsonschema.exceptions.ValidationError):
            jsonschema.validate(expanded, schema)

        missing_blocked_next_actions = json.loads(json.dumps(report))
        missing_blocked_next_actions["blocked_repairs_rollup"]["rollup"].pop("next_actions")
        with self.assertRaises(jsonschema.exceptions.ValidationError):
            jsonschema.validate(missing_blocked_next_actions, schema)

        missing_blocked_claim = json.loads(json.dumps(report))
        missing_blocked_claim["must_not_claim"].remove("blocked_repairs_are_not_translation_success")
        with self.assertRaises(jsonschema.exceptions.ValidationError):
            jsonschema.validate(missing_blocked_claim, schema)

    def test_bundle_blocks_malformed_run_report_contract(self) -> None:
        from validation.tools import judge_milestone_bundle as bundle

        temp_dir = Path(tempfile.mkdtemp(prefix="judge-milestone-malformed-run-report-", dir=REPO_ROOT / "target"))
        run_report_path = temp_dir / "summary" / "judge-entrypoints-run-report.json"
        out_path = temp_dir / "summary" / "judge-milestone-bundle.json"
        write_json(
            run_report_path,
            {
                "report_kind": "wrong-report-kind",
                "status": "passed",
                "entrypoint_count": 2,
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
        self.assertIn("run_report_schema_version_must_be_1", report["blockers"])
        self.assertIn("run_report_kind_must_be_judge_entrypoints_run_report", report["blockers"])
        self.assertIn("run_report_entrypoint_count_mismatch", report["blockers"])

    def test_bundle_blocks_proof_class_escalation_without_validation_contract(self) -> None:
        from validation.tools import judge_milestone_bundle as bundle

        temp_dir = Path(tempfile.mkdtemp(prefix="judge-milestone-proof-escalation-", dir=REPO_ROOT / "target"))
        run_report_path = temp_dir / "summary" / "judge-entrypoints-run-report.json"
        out_path = temp_dir / "summary" / "judge-milestone-bundle.json"
        write_json(
            run_report_path,
            {
                "schema_version": 1,
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
                        "id": "before_after_judge_demo",
                        "status": "passed",
                        "exit_code": 0,
                        "proof_class": "competition-exact",
                        "key_artifacts": {},
                    }
                ],
                "validation": {
                    "status": "passed",
                    "proof_class_contract": {
                        "status": "passed",
                        "entrypoints": {"before_after_judge_demo": "local-simulation"},
                    },
                },
            },
        )

        report = bundle.build_judge_milestone_bundle(
            run_report_path=run_report_path,
            out_path=out_path,
            repo_root=REPO_ROOT,
        )

        self.assertEqual(report["status"], "blocked")
        self.assertIn("proof_class_contract_mismatch:before_after_judge_demo", report["blockers"])
        self.assertEqual(report["proof_classes"]["all"], ["local-simulation"])
        self.assertFalse(report["claim_scope"]["competition_exact_ready"])
        self.assertFalse(report["publishability"]["competition_exact_publishable"])

    def test_bundle_blocks_focused_run_from_external_milestone_claim(self) -> None:
        from validation.tools import judge_milestone_bundle as bundle

        temp_dir = Path(tempfile.mkdtemp(prefix="judge-milestone-focused-", dir=REPO_ROOT / "target"))
        run_report_path = temp_dir / "summary" / "judge-entrypoints-run-report.json"
        out_path = temp_dir / "summary" / "judge-milestone-bundle.json"
        write_json(
            run_report_path,
            {
                "schema_version": 1,
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
                "schema_version": 1,
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
                "schema_version": 1,
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
                "schema_version": 1,
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

    def test_bundle_rolls_up_blocked_repairs_from_bound_route_metrics(self) -> None:
        from validation.tools import judge_milestone_bundle as bundle

        temp_dir = Path(tempfile.mkdtemp(prefix="judge-milestone-blocked-repairs-", dir=REPO_ROOT / "target"))
        run_report_path = temp_dir / "summary" / "judge-entrypoints-run-report.json"
        out_path = temp_dir / "summary" / "judge-milestone-bundle.json"
        route_metrics_path = temp_dir / "summary" / "route-governance-metrics-report.json"
        write_json(
            route_metrics_path,
            route_metrics_payload(
                accepted_evidence_semantic_pass_count=0,
                tracked_route_decision_artifacts=1,
                tracked_slice_gate_contexts=1,
                s2_workflow_run_count=0,
                s2_reduced_by=0,
                blocked_repair_count=2,
            ),
        )
        write_json(
            run_report_path,
            {
                "schema_version": 1,
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
                        "id": "before_after_judge_demo",
                        "status": "passed",
                        "exit_code": 0,
                        "proof_class": "local-simulation",
                        "key_artifacts": {"route_governance_metrics_report": repo_relative(route_metrics_path)},
                    }
                ],
            },
        )

        report = bundle.build_judge_milestone_bundle(
            run_report_path=run_report_path,
            out_path=out_path,
            repo_root=REPO_ROOT,
        )

        blocked = report["blocked_repairs_rollup"]["rollup"]
        self.assertEqual(report["status"], "passed")
        self.assertEqual(report["blocked_repairs_rollup"]["report_kind"], "blocked-repairs-rollup")
        self.assertEqual(blocked["source_count"], 1)
        self.assertEqual(blocked["blocked_repair_count"], 2)
        self.assertEqual(blocked["slice_count"], 1)
        self.assertEqual(blocked["human_action_required_count"], 2)
        self.assertEqual(blocked["human_intervention_points"], ["Bind external callee semantics before promotion."])
        self.assertEqual(blocked["blocked_callees"], ["helper_blocked"])
        self.assertEqual(blocked["ir_feature_gap_kinds"], {"external_direct_callee_context": 2})
        self.assertEqual(
            blocked["smallest_next_tests"],
            [
                {
                    "kind": "callee_contract_replay",
                    "command": "python -B validation/tools/validate_auto_translation_evidence.py --target-id demo --slice-id refused --require-semantic-pass",
                    "expected_gate": "external callee contract is bound before candidate promotion",
                }
            ],
        )
        self.assertEqual(
            blocked["next_actions"],
            [
                {
                    "entrypoint_id": "before_after_judge_demo",
                    "repair_id": "repair-refused-1",
                    "target_id": "demo",
                    "slice_id": "refused",
                    "pipeline_id": "validation/evidence/demo/auto-translation/refused",
                    "route": "typed_ir",
                    "status": "blocked",
                    "next_action": "bind_external_callee_semantics",
                    "smallest_next_test_kind": "callee_contract_replay",
                    "smallest_next_test_command": "python -B validation/tools/validate_auto_translation_evidence.py --target-id demo --slice-id refused --require-semantic-pass",
                    "expected_gate": "external callee contract is bound before candidate promotion",
                    "human_intervention_point": "Bind external callee semantics before promotion.",
                }
            ],
        )
        self.assertFalse(report["blocked_repairs_rollup"]["semantic_gate"])
        self.assertFalse(report["blocked_repairs_rollup"]["generated_draft_semantic_pass"])
        self.assertEqual(report["blocked_repairs_rollup"]["translation_coverage_numerator"], 0)
        self.assertFalse(blocked["semantic_gate"])
        self.assertEqual(blocked["translation_coverage_numerator"], 0)
        self.assertIn("blocked_repairs_are_not_translation_success", report["must_not_claim"])
        schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
        jsonschema.validate(report, schema)

        missing_next_action_route = json.loads(json.dumps(report))
        missing_next_action_route["blocked_repairs_rollup"]["rollup"]["next_actions"][0].pop("route")
        with self.assertRaises(jsonschema.exceptions.ValidationError):
            jsonschema.validate(missing_next_action_route, schema)

        missing_next_action_command = json.loads(json.dumps(report))
        missing_next_action_command["blocked_repairs_rollup"]["rollup"]["next_actions"][0].pop("next_action")
        with self.assertRaises(jsonschema.exceptions.ValidationError):
            jsonschema.validate(missing_next_action_command, schema)

    def test_bundle_blocks_stale_or_incomplete_blocked_repairs_rollup(self) -> None:
        from validation.tools import judge_milestone_bundle as bundle

        temp_dir = Path(tempfile.mkdtemp(prefix="judge-milestone-stale-blocked-repairs-", dir=REPO_ROOT / "target"))
        run_report_path = temp_dir / "summary" / "judge-entrypoints-run-report.json"
        out_path = temp_dir / "summary" / "judge-milestone-bundle.json"
        route_metrics_path = temp_dir / "summary" / "route-governance-metrics-report.json"
        write_json(
            route_metrics_path,
            route_metrics_payload(
                accepted_evidence_semantic_pass_count=0,
                tracked_route_decision_artifacts=1,
                tracked_slice_gate_contexts=1,
                s2_workflow_run_count=0,
                s2_reduced_by=0,
                blocked_repair_count=1,
                blocked_repairs_status="stale",
            ),
        )
        write_json(
            run_report_path,
            {
                "schema_version": 1,
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
                        "id": "before_after_judge_demo",
                        "status": "passed",
                        "exit_code": 0,
                        "proof_class": "local-simulation",
                        "key_artifacts": {"route_governance_metrics_report": repo_relative(route_metrics_path)},
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
        self.assertIn("blocked_repairs_rollup_stale_or_incomplete", report["blockers"])

    def test_bundle_blocks_inconsistent_repair_accounting_claims(self) -> None:
        from validation.tools import judge_milestone_bundle as bundle

        temp_dir = Path(tempfile.mkdtemp(prefix="judge-milestone-repair-accounting-", dir=REPO_ROOT / "target"))
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
                    "translation_coverage_numerator": 0,
                    "generated_draft_semantic_pass": False,
                    "repair_summary": {
                        "status": "verified",
                        "repair_round_cap": 5,
                        "observed_repair_unit_count": 1,
                        "auto_recovered_unit_count": 2,
                        "rollback_evidence_count": 0,
                    },
                    "unsafe_reduction": {
                        "status": "measured",
                        "baseline_total_unsafe": 1,
                        "current_total_unsafe": 0,
                        "reduced_by": 2,
                    },
                },
            },
        )
        write_json(
            run_report_path,
            {
                "schema_version": 1,
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

        expected_blockers = {
            "repair_accounting_auto_recovered_exceeds_observed",
            "repair_accounting_unsafe_reduced_by_exceeds_measured_baseline",
            "repair_accounting_rollback_evidence_missing_for_observed_repairs",
        }
        self.assertEqual(report["status"], "blocked")
        self.assertTrue(expected_blockers.issubset(set(report["blockers"])))
        self.assertTrue(expected_blockers.issubset(set(report["summary"]["blockers"])))

    def test_bundle_repair_accounting_does_not_require_final_gate_passed(self) -> None:
        from validation.tools import judge_milestone_bundle as bundle

        temp_dir = Path(
            tempfile.mkdtemp(
                prefix="judge-milestone-repair-accounting-failed-gate-",
                dir=REPO_ROOT / "target",
            )
        )
        run_report_path = temp_dir / "summary" / "judge-entrypoints-run-report.json"
        out_path = temp_dir / "summary" / "judge-milestone-bundle.json"
        index_path = temp_dir / "before-after" / "harness" / "judge-evidence-index.json"
        write_json(
            index_path,
            {
                "report_kind": "judge-evidence-index",
                "core_translation_quality": {
                    "final_gate_status": "failed",
                    "semantic_pass_count": 0,
                    "translation_coverage_numerator": 0,
                    "generated_draft_semantic_pass": False,
                    "repair_summary": {
                        "status": "verified",
                        "repair_round_cap": 5,
                        "observed_repair_unit_count": 1,
                        "auto_recovered_unit_count": 1,
                        "rollback_evidence_count": 1,
                    },
                    "unsafe_reduction": {
                        "status": "measured",
                        "baseline_total_unsafe": 2,
                        "current_total_unsafe": 1,
                        "reduced_by": 1,
                    },
                },
            },
        )
        write_json(
            run_report_path,
            {
                "schema_version": 1,
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

        repair_blockers = [blocker for blocker in report["blockers"] if blocker.startswith("repair_accounting_")]
        self.assertEqual(report["status"], "passed")
        self.assertEqual(repair_blockers, [])

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
                "schema_version": 1,
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
