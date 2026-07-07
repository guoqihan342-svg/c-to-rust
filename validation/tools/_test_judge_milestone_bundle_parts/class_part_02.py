class _JudgeMilestoneBundleTestsPart02:
    def test_bundle_blocks_unvalidated_key_artifacts_without_validation_expected_refs(self) -> None:
        from validation.tools import judge_milestone_bundle as bundle

        temp_dir = Path(tempfile.mkdtemp(prefix="judge-milestone-unvalidated-key-artifact-", dir=REPO_ROOT / "target"))
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
                    "headline": "Judge entrypoints passed: 1/1 executed; semantic_gate=false",
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
                        "key_artifacts": {
                            "judge_evidence_index": "target/unvalidated/judge-evidence-index.json",
                        },
                    }
                ],
                "validation": {
                    "status": "passed",
                    "entrypoints": [
                        {
                            "id": "before_after_judge_demo",
                            "expected_artifacts": {},
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

        self.assertEqual(report["status"], "blocked")
        self.assertIn(
            "validated_artifact_binding_missing:before_after_judge_demo:judge_evidence_index",
            report["blockers"],
        )

    def test_bundle_blocks_nested_before_after_exhibit_sha_drift(self) -> None:
        from validation.tools import judge_milestone_bundle as bundle

        temp_dir = Path(tempfile.mkdtemp(prefix="judge-milestone-nested-before-after-drift-", dir=REPO_ROOT / "target"))
        run_report_path = temp_dir / "summary" / "judge-entrypoints-run-report.json"
        out_path = temp_dir / "summary" / "judge-milestone-bundle.json"
        index_path = temp_dir / "before-after" / "harness" / "judge-evidence-index.json"
        before_exhibit_path = temp_dir / "before-after" / "reports" / "before-after-exhibit.json"
        write_json(before_exhibit_path, {"units": [{"unit_id": "flashdb/real-fdb-calc-crc32"}]})
        before_exhibit_ref = artifact_ref(before_exhibit_path)
        write_json(
            index_path,
            {
                "report_kind": "judge-evidence-index",
                "evidence_artifact_refs": {
                    "before_after_exhibit": before_exhibit_ref,
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
                                "baseline_total_unsafe": 1,
                                "current_total_unsafe": 0,
                                "reduced_by": 1,
                            },
                        }
                    ],
                    "final_gate_status": "passed",
                    "repair_summary": {
                        "status": "not_provided",
                        "repair_round_cap": 5,
                        "observed_repair_unit_count": 0,
                        "auto_recovered_unit_count": 0,
                        "rollback_evidence_count": 0,
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
                        "baseline_total_unsafe": 1,
                        "current_total_unsafe": 0,
                        "reduced_by": 1,
                    },
                },
            },
        )
        write_json(
            before_exhibit_path,
            {
                "units": [
                    {
                        "unit_id": "flashdb/real-fdb-calc-crc32",
                        "baseline_verification": {
                            "path": "validation/evidence/baseline-verification.json",
                            "sha256": "e" * 64,
                            "status": "passed",
                            "semantic_pass": True,
                            "semantic_claim_source": "verified_unsafe_baseline_gates",
                            "generated_draft_semantic_pass": False,
                        },
                    }
                ]
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
                "validation": {
                    "status": "passed",
                    "entrypoints": [
                        {
                            "id": "before_after_judge_demo",
                            "expected_artifacts": {"judge_evidence_index": artifact_ref(index_path)},
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

        known_gap_ids = [gap["gap_id"] for gap in report["known_gaps"]]
        self.assertEqual(report["status"], "blocked")
        self.assertIn(
            "nested_artifact_sha256_mismatch:before_after_judge_demo:before_after_exhibit",
            report["blockers"],
        )
        self.assertIn("c2rust_baseline_output_still_not_verified_here", known_gap_ids)
        self.assertEqual(report["before_after_repair_exhibit"]["rollup"]["verified_baseline_unit_count"], 0)

    def test_bundle_blocks_before_after_unit_ref_drift_or_missing_from_workflow_metrics(self) -> None:
        from validation.tools import judge_milestone_bundle as bundle

        temp_dir = Path(tempfile.mkdtemp(prefix="judge-milestone-before-after-workflow-drift-", dir=REPO_ROOT / "target"))
        run_report_path = temp_dir / "summary" / "judge-entrypoints-run-report.json"
        out_path = temp_dir / "summary" / "judge-milestone-bundle.json"
        metrics_path = temp_dir / "before-after" / "workflow-metrics.json"
        index_path = temp_dir / "before-after" / "harness" / "judge-evidence-index.json"
        unit_id = "flashdb/real-fdb-calc-crc32"
        good_refs = {
            "baseline": {"path": "validation/evidence/baseline.rs", "sha256": "a" * 64},
            "final": {"path": "validation/evidence/final.rs", "sha256": "b" * 64},
            "accepted_patch": {"path": "validation/evidence/accepted.patch", "sha256": "c" * 64},
            "oracle_evidence": {"path": "validation/evidence/final-verification.json", "sha256": "d" * 64},
        }
        unsafe_reduction = {
            "status": "measured",
            "baseline_total_unsafe": 1,
            "current_total_unsafe": 0,
            "reduced_by": 1,
        }
        write_json(
            metrics_path,
            {
                "report_kind": "workflow-metrics",
                "units_total": 1,
                "units_converged": 1,
                "avg_repair_rounds": 1.0,
                "auto_recovery_rate": 1.0,
                "human_interventions": 0,
                "llm_calls": 1,
                "unsafe_reduction": unsafe_reduction,
                "per_unit_statuses": [
                    {
                        "unit_id": unit_id,
                        "repair_rounds": 1,
                        "auto_recovered": True,
                        "translation_before_after": {
                            "status": "bound",
                            **good_refs,
                            "unsafe_reduction": unsafe_reduction,
                        },
                    }
                ],
            },
        )
        drifted_refs = dict(good_refs)
        drifted_refs["accepted_patch"] = {
            "path": "validation/evidence/accepted.patch",
            "sha256": "f" * 64,
        }
        drifted_unsafe_reduction = {
            "status": "measured",
            "baseline_total_unsafe": 1,
            "current_total_unsafe": 1,
            "reduced_by": 0,
        }
        write_json(
            index_path,
            {
                "report_kind": "judge-evidence-index",
                "core_translation_quality": {
                    "before_after_units": [
                        {
                            "unit_id": unit_id,
                            "status": "converged",
                            **drifted_refs,
                            "unsafe_reduction": drifted_unsafe_reduction,
                        }
                    ],
                    "final_gate_status": "passed",
                    "repair_summary": {
                        "status": "not_provided",
                        "repair_round_cap": 5,
                        "observed_repair_unit_count": 0,
                        "auto_recovered_unit_count": 0,
                        "rollback_evidence_count": 0,
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
                    "unsafe_reduction": unsafe_reduction,
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
                        "key_artifacts": {
                            "workflow_metrics": repo_relative(metrics_path),
                            "judge_evidence_index": repo_relative(index_path),
                        },
                    }
                ],
                "validation": {
                    "status": "passed",
                    "entrypoints": [
                        {
                            "id": "before_after_judge_demo",
                            "expected_artifacts": {
                                "workflow_metrics": artifact_ref(metrics_path),
                                "judge_evidence_index": artifact_ref(index_path),
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

        self.assertEqual(report["status"], "blocked")
        self.assertIn(
            "before_after_exhibit_workflow_metrics_ref_mismatch:"
            "before_after_judge_demo:flashdb/real-fdb-calc-crc32:accepted_patch",
            report["blockers"],
        )
        self.assertIn(
            "before_after_exhibit_workflow_metrics_unsafe_reduction_mismatch:"
            "before_after_judge_demo:flashdb/real-fdb-calc-crc32",
            report["blockers"],
        )
        workflow_unit = report["workflow_metrics"]["sources"][0]["before_after_units"][0]
        self.assertEqual(workflow_unit["unit_id"], unit_id)
        self.assertEqual(workflow_unit["accepted_patch"]["sha256"], "c" * 64)

        missing_index_path = temp_dir / "before-after-missing-unit" / "harness" / "judge-evidence-index.json"
        missing_run_report_path = temp_dir / "summary" / "judge-entrypoints-run-report-missing-unit.json"
        missing_out_path = temp_dir / "summary" / "judge-milestone-bundle-missing-unit.json"
        write_json(
            missing_index_path,
            {
                "report_kind": "judge-evidence-index",
                "core_translation_quality": {
                    "before_after_units": [],
                    "final_gate_status": "passed",
                    "repair_summary": {
                        "status": "not_provided",
                        "repair_round_cap": 5,
                        "observed_repair_unit_count": 0,
                        "auto_recovered_unit_count": 0,
                        "rollback_evidence_count": 0,
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
                    "unsafe_reduction": unsafe_reduction,
                },
            },
        )
        write_json(
            missing_run_report_path,
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
                        "key_artifacts": {
                            "workflow_metrics": repo_relative(metrics_path),
                            "judge_evidence_index": repo_relative(missing_index_path),
                        },
                    }
                ],
                "validation": {
                    "status": "passed",
                    "entrypoints": [
                        {
                            "id": "before_after_judge_demo",
                            "expected_artifacts": {
                                "workflow_metrics": artifact_ref(metrics_path),
                                "judge_evidence_index": artifact_ref(missing_index_path),
                            },
                        }
                    ],
                },
            },
        )

        missing_report = bundle.build_judge_milestone_bundle(
            run_report_path=missing_run_report_path,
            out_path=missing_out_path,
            repo_root=REPO_ROOT,
        )

        self.assertEqual(missing_report["status"], "blocked")
        self.assertIn(
            "before_after_exhibit_workflow_metrics_unit_missing:"
            "before_after_judge_demo:flashdb/real-fdb-calc-crc32",
            missing_report["blockers"],
        )

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
        self.assertEqual(report["publishability"]["status"], "blocked")
        self.assertEqual(report["publishability"]["scope"], "blocked")
        self.assertEqual(report["publishability"]["publication_scope"], "blocked")
        self.assertFalse(report["publishability"]["external_milestone_claim_ready"])
        self.assertFalse(report["publishability"]["external_milestone"])
        self.assertEqual(report["publishability"]["required_agent"], "c2rust-migrator")
        self.assertEqual(report["publishability"]["blocker_count"], len(report["blockers"]))
        self.assertEqual(report["publishability"]["blockers"], report["blockers"])
        self.assertFalse(report["publishability"]["competition_exact_publishable"])

    def test_bundle_revalidates_exact_host_attestation_before_external_ready(self) -> None:
        from validation.tools import judge_milestone_bundle as bundle

        temp_dir = Path(tempfile.mkdtemp(prefix="judge-milestone-forged-exact-host-", dir=REPO_ROOT / "target"))
        run_report_path = temp_dir / "summary" / "judge-entrypoints-run-report.json"
        out_path = temp_dir / "summary" / "judge-milestone-bundle.json"
        fake_config_path = temp_dir / "missing-judge-entrypoints.json"
        preflight_fixture = write_opencode_preflight_fixture(temp_dir / "opencode", run_id="forged-exact-host")
        preflight_path = Path(preflight_fixture["preflight_path"])
        preflight_ref = {
            "path": repo_relative(preflight_path),
            "sha256": bundle.validator.sha256_file(preflight_path),
            "status": "present",
        }
        judge_index_path = temp_dir / "opencode" / "harness" / "judge-evidence-index.json"
        write_json(
            judge_index_path,
            {
                "judge_headline": {
                    "worker_count": 1,
                    "repair_round_cap": 5,
                    "semantic_gate": False,
                    "opencode_runtime": {
                        "enabled": True,
                        "worker_count": 1,
                        "all_contracts_executed": True,
                        "chat_output_is_evidence": False,
                        "semantic_gate": False,
                    },
                },
                "opencode_agent_runtime": {
                    "runtime": "opencode",
                    "worker_count": 1,
                    "all_contracts_executed": True,
                    "chat_output_is_evidence": False,
                    "semantic_gate": False,
                    "opencode_preflight_report": preflight_ref,
                },
                "evidence_artifact_refs": {
                    "opencode_preflight_report": preflight_ref,
                },
            },
        )
        smoke_path = temp_dir / "smoke" / "summary" / "competition-smoke-summary.json"
        write_json(
            smoke_path,
            {
                "proof_class": "competition-exact",
                "run_id": "forged-exact-host",
                "execution_environment": {
                    "kind": "competition-host",
                    "system": "Linux",
                    "detected_ci": False,
                    "detected_wsl": False,
                    "competition_exact_host_attested": True,
                },
            },
        )
        write_json(
            run_report_path,
            {
                "schema_version": 1,
                "report_kind": "judge-entrypoints-run-report",
                "status": "passed",
                "dry_run": False,
                "config": {
                    "path": repo_relative(fake_config_path),
                    "status": "present",
                    "sha256": "0" * 64,
                },
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
                        "id": "competition_environment_smoke",
                        "status": "passed",
                        "exit_code": 0,
                        "proof_class": "competition-exact",
                        "run_id": "forged-exact-host",
                        "key_artifacts": {},
                    }
                ],
                "validation": {
                    "status": "passed",
                    "proof_class_contract": {
                        "status": "passed",
                        "entrypoints": {"competition_environment_smoke": "competition-exact"},
                    },
                    "entrypoints": [
                        {
                            "id": "competition_environment_smoke",
                            "expected_artifacts": {
                                "judge_evidence_index": {
                                    "path": repo_relative(judge_index_path),
                                    "status": "present",
                                    "sha256": bundle.validator.sha256_file(judge_index_path),
                                },
                                "competition_smoke_summary": {
                                    "path": repo_relative(smoke_path),
                                    "status": "present",
                                    "sha256": bundle.validator.sha256_file(smoke_path),
                                },
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

        self.assertEqual(report["status"], "blocked")
        self.assertIn("run_report_exact_host_revalidation_failed", report["blockers"])
        self.assertFalse(report["claim_scope"]["competition_exact_ready"])
        self.assertEqual(report["publishability"]["status"], "blocked")
        self.assertFalse(report["publishability"]["external_milestone_claim_ready"])
        self.assertFalse(report["competition_host_readiness"]["competition_exact_host_verified"])

    def test_exact_host_revalidation_rejects_bound_config_sha_drift(self) -> None:
        from validation.tools import judge_milestone_bundle as bundle

        temp_dir = Path(tempfile.mkdtemp(prefix="judge-milestone-config-ref-drift-", dir=REPO_ROOT / "target"))
        config_path = temp_dir / "judge-entrypoints.json"
        write_json(config_path, {"schema_version": 1, "entrypoints": []})
        run_report = {
            "config": {
                "path": repo_relative(config_path),
                "status": "present",
                "sha256": "0" * 64,
            }
        }
        entrypoints = [
            {
                "id": "competition_environment_smoke",
                "proof_class": "competition-exact",
                "competition_exact_host_attested": True,
            }
        ]

        with mock.patch.object(
            bundle.validator,
            "validate_config",
            return_value={
                "status": "passed",
                "config": {"path": repo_relative(config_path)},
                "errors": [],
                "proof_class_contract": {
                    "status": "passed",
                    "entrypoints": {"competition_environment_smoke": "competition-exact"},
                },
            },
        ) as validate_config:
            result = bundle.build_exact_host_revalidation(run_report, entrypoints, repo_root=REPO_ROOT)

        self.assertEqual(result["status"], "failed")
        self.assertTrue(any("run_report.config" in error and "sha256" in error for error in result["errors"]))
        validate_config.assert_not_called()

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

    def test_standalone_bundle_removes_stale_publication_siblings(self) -> None:
        from validation.tools import judge_milestone_bundle as bundle

        temp_dir = Path(tempfile.mkdtemp(prefix="judge-milestone-stale-publication-", dir=REPO_ROOT / "target"))
        run_report_path = temp_dir / "summary" / "judge-entrypoints-run-report.json"
        out_path = temp_dir / "summary" / "judge-milestone-bundle.json"
        stale_packet = temp_dir / "summary" / "public-release-packet.json"
        stale_notes = temp_dir / "summary" / "milestone-release-notes.md"
        stale_packet.parent.mkdir(parents=True, exist_ok=True)
        stale_packet.write_text('{"report_kind":"stale-public-release-packet"}\n', encoding="utf-8")
        stale_notes.write_text("# stale release notes\n", encoding="utf-8")
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
        self.assertFalse(stale_packet.exists())
        self.assertFalse(stale_notes.exists())

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

    def test_bundle_blocks_validator_expected_artifact_hash_drift(self) -> None:
        from validation.tools import judge_milestone_bundle as bundle

        temp_dir = Path(tempfile.mkdtemp(prefix="judge-milestone-validated-drift-", dir=REPO_ROOT / "target"))
        run_report_path = temp_dir / "summary" / "judge-entrypoints-run-report.json"
        out_path = temp_dir / "summary" / "judge-milestone-bundle.json"
        index_path = temp_dir / "validated" / "harness" / "judge-evidence-index.json"
        write_json(index_path, {"report_kind": "judge-evidence-index", "judge_headline": {"opencode_runtime": {"enabled": False}}})
        validated_sha = bundle.validator.sha256_file(index_path)
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
                        "key_artifacts": {},
                    }
                ],
                "validation": {
                    "status": "passed",
                    "entrypoints": [
                        {
                            "id": "before_after_judge_demo",
                            "expected_artifacts": {
                                "judge_evidence_index": {
                                    "path": repo_relative(index_path),
                                    "sha256": validated_sha,
                                    "status": "present",
                                }
                            },
                        }
                    ],
                },
            },
        )
        write_json(
            index_path,
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

        report = bundle.build_judge_milestone_bundle(
            run_report_path=run_report_path,
            out_path=out_path,
            repo_root=REPO_ROOT,
        )

        artifact_ref = report["entrypoints"][0]["artifacts"]["judge_evidence_index"]
        self.assertEqual(report["status"], "blocked")
        self.assertEqual(artifact_ref["status"], "sha256_mismatch")
        self.assertEqual(artifact_ref["expected_sha256"], validated_sha)
        self.assertIn("validated_artifact_sha256_mismatch:before_after_judge_demo:judge_evidence_index", report["blockers"])
        self.assertEqual(report["opencode_runtime"]["enabled_entrypoint_count"], 0)
