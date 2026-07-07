class _JudgeEntrypointsValidatorTestsPart01:
    def test_readiness_summary_classifies_required_model_not_listed_as_opencode_model_unavailable(self) -> None:
        summary = validator.build_readiness_summary(
            {
                "status": "failed",
                "entrypoint_count": 1,
                "entrypoints": [
                    {
                        "id": "opencode_multi_worker_evaluate_profile",
                        "purpose": "harness-architecture-opencode-multi-worker-evaluate",
                        "status": "failed",
                        "proof_class": "real-opencode-glm51",
                        "run_id": "harness-flashdb-opencode-explicit-workers-evaluate-profile-20260701",
                    }
                ],
                "claim_boundary": {
                    "semantic_claim_source": "accepted_evidence_binding",
                    "generated_draft_semantic_pass": False,
                    "translation_coverage_numerator": 0,
                },
                "errors": [
                    "opencode_model_availability.missing_model_reason required_model_not_listed"
                ],
            }
        )

        self.assertEqual(summary["readiness"]["blocker_count"], 1)
        self.assertEqual(
            summary["readiness"]["blocker_root_cause_counts"],
            {"opencode_model_unavailable": 1},
        )
        self.assertEqual(
            summary["blockers"][0]["recommended_action"],
            "rerun on an OpenCode runtime whose model list exposes GLM-5.1",
        )
        self.assertEqual(summary["blockers"][0]["proof_class_effect"], "h9_release_blocker")

    def test_readiness_summary_classifies_model_listed_contract_failure_as_opencode_model_unavailable(self) -> None:
        summary = validator.build_readiness_summary(
            {
                "status": "failed",
                "entrypoint_count": 1,
                "entrypoints": [
                    {
                        "id": "opencode_multi_worker_evaluate_profile",
                        "purpose": "harness-architecture-opencode-multi-worker-evaluate",
                        "status": "failed",
                        "proof_class": "real-opencode-glm51",
                        "run_id": "harness-flashdb-opencode-explicit-workers-evaluate-profile-20260701",
                    }
                ],
                "claim_boundary": {
                    "semantic_claim_source": "accepted_evidence_binding",
                    "generated_draft_semantic_pass": False,
                    "translation_coverage_numerator": 0,
                },
                "errors": ["opencode_model_availability.model_listed must be true"],
            }
        )

        self.assertEqual(
            summary["readiness"]["blocker_root_cause_counts"],
            {"opencode_model_unavailable": 1},
        )
        self.assertEqual(summary["blockers"][0]["proof_class_effect"], "h9_release_blocker")

    def test_validate_config_can_focus_selected_entrypoints(self) -> None:
        result = validator.validate_config(
            validator.DEFAULT_CONFIG,
            repo_root=REPO_ROOT,
            entrypoint_ids=["competition_environment_smoke", "before_after_judge_demo"],
        )

        self.assertEqual(result["status"], "passed")
        self.assertEqual(result["entrypoint_count"], 2)
        self.assertEqual(
            [entry["id"] for entry in result["entrypoints"]],
            ["competition_environment_smoke", "before_after_judge_demo"],
        )
        self.assertEqual(
            result["test_contract"]["required_entrypoint_ids"],
            ["competition_environment_smoke", "before_after_judge_demo"],
        )

    def test_validate_config_unknown_entrypoint_id_fails_closed(self) -> None:
        result = validator.validate_config(
            validator.DEFAULT_CONFIG,
            repo_root=REPO_ROOT,
            entrypoint_ids=["missing-entrypoint"],
        )

        self.assertEqual(result["status"], "failed")
        self.assertEqual(result["errors"], ["unknown entrypoint id: missing-entrypoint"])
        self.assertEqual(result["entrypoint_count"], 0)
        self.assertEqual(result["entrypoints"], [])

    def test_cli_entrypoint_id_writes_focused_readiness_report(self) -> None:
        target_dir = REPO_ROOT / "target"
        target_dir.mkdir(exist_ok=True)
        temp_dir = Path(tempfile.mkdtemp(prefix="judge-readiness-focused-", dir=target_dir))
        report_path = temp_dir / "summary" / "judge-entrypoints-readiness.json"

        completed = subprocess.run(
            [
                sys.executable,
                "-B",
                "-m",
                "validation.tools.validate_judge_entrypoints",
                "--config",
                validator.DEFAULT_CONFIG.relative_to(REPO_ROOT).as_posix(),
                "--entrypoint-id",
                "multi_worker_evaluate_profile",
                "--out",
                repo_relative(report_path),
            ],
            cwd=REPO_ROOT,
            capture_output=True,
            text=True,
            encoding="utf-8",
        )

        self.assertEqual(completed.returncode, 0, completed.stderr)
        report = json.loads(report_path.read_text(encoding="utf-8"))
        self.assertEqual(report["entrypoint_count"], 1)
        self.assertEqual(report["validation"]["entrypoints"][0]["id"], "multi_worker_evaluate_profile")
        self.assertEqual(
            report["validation"]["test_contract"]["required_entrypoint_ids"],
            ["multi_worker_evaluate_profile"],
        )
        self.assertIn("1 judge entrypoints ready", report["summary"]["headline"])
        self.assertEqual(report["summary"]["readiness"]["configured_count"], 1)
        self.assertEqual(report["summary"]["readiness"]["validation_status"], "passed")
        self.assertFalse(report["summary"]["claim_boundary"]["semantic_gate"])
        self.assertEqual(
            [entry["id"] for entry in report["summary"]["entrypoints"]],
            ["multi_worker_evaluate_profile"],
        )

    def test_competition_smoke_summary_contract_rejects_semantic_gate_claim(self) -> None:
        payload = {
            "schema_version": 1,
            "report_kind": "competition-smoke-summary",
            "proof_class": "local-simulation",
            "profile_id": "huawei-competition-ubuntu-24.04",
            "claim_boundary": {
                "semantic_gate": True,
                "generated_draft_semantic_pass": False,
                "translation_coverage_numerator": 0,
            },
            "smoke_entrypoint": {
                "semantic_acceptance_boundary": "does_not_translate_new_slices",
            },
            "vendored_clang_verification": {
                "path": "target/competition-smoke-flashdb-judge-entrypoint/summary/vendored-clang-verification.json",
            },
            "reports": {
                "evidence_governance": {
                    "path": "target/competition-smoke-flashdb-judge-entrypoint/reports/evidence-governance.json",
                },
                "translator_coverage_matrix": {
                    "path": "target/competition-smoke-flashdb-judge-entrypoint/reports/translator-coverage-matrix.json",
                },
            },
            "milestone_release_report": {
                "path": "target/competition-smoke-flashdb-judge-entrypoint/reports/milestone-release-report.json",
                "semantic_acceptance_claim": False,
            },
            "command_log": {
                "path": "target/competition-smoke-flashdb-judge-entrypoint/logs/commands.jsonl",
            },
            "final_gate": {"status": "passed"},
            "steps": [],
        }

        with self.assertRaisesRegex(ValueError, "competition_smoke_summary claim_boundary.semantic_gate must be false"):
            validator.validate_competition_smoke_summary_contract(
                payload,
                expected_artifacts=competition_smoke_expected_artifacts(),
            )

    def test_competition_smoke_summary_profile_sha256_must_match_environment_profile(self) -> None:
        payload = valid_competition_smoke_summary_payload()
        payload["profile_sha256"] = "b" * 64

        with self.assertRaisesRegex(
            ValueError,
            "competition_smoke_summary profile_sha256 must match environment_profile.sha256",
        ):
            validator.validate_competition_smoke_summary_contract(
                payload,
                expected_artifacts=competition_smoke_expected_artifacts(),
                environment_profile={
                    "profile_id": "huawei-competition-ubuntu-24.04",
                    "sha256": "a" * 64,
                },
            )

    def test_competition_smoke_summary_profile_id_must_match_environment_profile(self) -> None:
        payload = valid_competition_smoke_summary_payload()
        payload["profile_id"] = "drifted-profile"

        with self.assertRaisesRegex(
            ValueError,
            "competition_smoke_summary profile_id must match environment_profile.profile_id",
        ):
            validator.validate_competition_smoke_summary_contract(
                payload,
                expected_artifacts=competition_smoke_expected_artifacts(),
                environment_profile={
                    "profile_id": "huawei-competition-ubuntu-24.04",
                    "sha256": "a" * 64,
                },
            )

    def test_competition_smoke_summary_profile_match_profile_id_must_match_environment_profile(self) -> None:
        payload = valid_competition_smoke_summary_payload()
        payload["competition_profile_match"]["profile_id"] = "drifted-profile"

        with self.assertRaisesRegex(
            ValueError,
            "competition_smoke_summary competition_profile_match.profile_id must match environment_profile.profile_id",
        ):
            validator.validate_competition_smoke_summary_contract(
                payload,
                expected_artifacts=competition_smoke_expected_artifacts(),
                environment_profile={
                    "profile_id": "huawei-competition-ubuntu-24.04",
                    "sha256": "a" * 64,
                },
            )

    def test_vendored_clang_verification_rejects_local_absolute_clang_path(self) -> None:
        payload = valid_vendored_clang_verification_payload()
        payload["clang"]["path"] = "F:/agent/local/clang.exe"

        with self.assertRaisesRegex(
            ValueError,
            "vendored_clang_verification clang.path must be repo-relative POSIX",
        ):
            validator.validate_vendored_clang_verification_contract(
                payload,
                smoke_summary=valid_competition_smoke_summary_payload(),
                environment_profile={
                    "profile_id": "huawei-competition-ubuntu-24.04",
                    "sha256": "a" * 64,
                },
            )

    def test_competition_smoke_summary_profile_match_sha256_must_match_environment_profile(self) -> None:
        payload = valid_competition_smoke_summary_payload()
        payload["competition_profile_match"]["profile_sha256_actual"] = "b" * 64

        with self.assertRaisesRegex(
            ValueError,
            "competition_smoke_summary competition_profile_match.profile_sha256_actual must match environment_profile.sha256",
        ):
            validator.validate_competition_smoke_summary_contract(
                payload,
                expected_artifacts=competition_smoke_expected_artifacts(),
                environment_profile={
                    "profile_id": "huawei-competition-ubuntu-24.04",
                    "sha256": "a" * 64,
                },
            )

    def test_competition_smoke_summary_proof_class_must_match_entrypoint(self) -> None:
        payload = valid_competition_smoke_summary_payload()
        payload["proof_class"] = "competition-exact"

        with self.assertRaisesRegex(
            ValueError,
            "competition_smoke_summary proof_class must match entrypoint proof_class",
        ):
            validator.validate_competition_smoke_summary_contract(
                payload,
                expected_artifacts=competition_smoke_expected_artifacts(),
                entrypoint_proof_class="local-simulation",
            )

    def test_competition_smoke_summary_run_id_must_match_entrypoint(self) -> None:
        payload = valid_competition_smoke_summary_payload()
        payload["run_id"] = "unexpected-run"

        with self.assertRaisesRegex(
            ValueError,
            "competition_smoke_summary run_id must match entrypoint run_id",
        ):
            validator.validate_competition_smoke_summary_contract(
                payload,
                expected_artifacts=competition_smoke_expected_artifacts(),
                entrypoint_run_id="competition-flashdb-environment-smoke-20260701",
            )

    def test_competition_smoke_summary_artifact_path_rejects_local_absolute_path(self) -> None:
        payload = valid_competition_smoke_summary_payload()
        artifacts = competition_smoke_expected_artifacts()
        local_absolute = "F:/agent/local/commands.jsonl"
        payload["command_log"]["path"] = local_absolute
        artifacts["command_log"] = local_absolute

        with self.assertRaisesRegex(
            ValueError,
            "path must not use a drive prefix",
        ):
            validator.validate_competition_smoke_summary_contract(
                payload,
                expected_artifacts=artifacts,
            )

    def test_competition_smoke_summary_artifact_path_rejects_parent_traversal(self) -> None:
        payload = valid_competition_smoke_summary_payload()
        artifacts = competition_smoke_expected_artifacts()
        traversal = "target/competition-smoke-flashdb-judge-entrypoint/reports/../summary/vendored.json"
        payload["vendored_clang_verification"]["path"] = traversal
        artifacts["vendored_clang_verification"] = traversal

        with self.assertRaisesRegex(
            ValueError,
            "path must not contain parent traversal",
        ):
            validator.validate_competition_smoke_summary_contract(
                payload,
                expected_artifacts=artifacts,
            )

    def test_competition_smoke_summary_artifact_roots_reject_local_absolute_path(self) -> None:
        payload = valid_competition_smoke_summary_payload()
        payload["artifact_roots"] = ["target/competition-smoke/summary", "F:/agent/local/reports"]

        with self.assertRaisesRegex(
            ValueError,
            "path must not use a drive prefix",
        ):
            validator.validate_competition_smoke_summary_contract(
                payload,
                expected_artifacts=competition_smoke_expected_artifacts(),
            )

    def test_competition_smoke_summary_requires_timeout_policy(self) -> None:
        payload = valid_competition_smoke_summary_payload()
        payload.pop("timeout_policy")

        with self.assertRaisesRegex(
            ValueError,
            "competition_smoke_summary timeout_policy must be an object",
        ):
            validator.validate_competition_smoke_summary_contract(
                payload,
                expected_artifacts=competition_smoke_expected_artifacts(),
            )

    def test_competition_smoke_summary_timeout_must_fail_closed(self) -> None:
        payload = valid_competition_smoke_summary_payload()
        payload["timeout_policy"]["timeout_is_final_gate_failure"] = False

        with self.assertRaisesRegex(
            ValueError,
            "competition_smoke_summary timeout_policy.timeout_is_final_gate_failure must be true",
        ):
            validator.validate_competition_smoke_summary_contract(
                payload,
                expected_artifacts=competition_smoke_expected_artifacts(),
            )

    def test_competition_smoke_summary_requires_required_gate_steps(self) -> None:
        payload = valid_competition_smoke_summary_payload()
        payload["steps"] = [
            step for step in payload["steps"] if step["step"] != "translator-coverage-matrix"
        ]

        with self.assertRaisesRegex(
            ValueError,
            "competition_smoke_summary steps missing required gates",
        ):
            validator.validate_competition_smoke_summary_contract(
                payload,
                expected_artifacts=competition_smoke_expected_artifacts(),
            )

    def test_competition_smoke_summary_rejects_unexpected_gate_step(self) -> None:
        payload = valid_competition_smoke_summary_payload()
        payload["steps"].append(
            {
                "step": "unexpected-gate",
                "status": "passed",
                "returncode": 0,
                "log_path": "target/competition-smoke-flashdb-judge-entrypoint/logs/commands.jsonl",
            }
        )

        with self.assertRaisesRegex(
            ValueError,
            "competition_smoke_summary steps unexpected gates: \\['unexpected-gate'\\]",
        ):
            validator.validate_competition_smoke_summary_contract(
                payload,
                expected_artifacts=competition_smoke_expected_artifacts(),
            )

    def test_competition_exact_smoke_summary_rejects_local_wsl_or_ci_mislabel(self) -> None:
        cases = [
            ("windows-local", {"kind": "windows-local", "system": "Windows"}),
            ("wsl", {"kind": "wsl", "detected_wsl": True}),
            ("ci", {"kind": "linux-ci", "detected_ci": True}),
        ]

        for name, env_patch in cases:
            with self.subTest(name=name):
                payload = valid_competition_smoke_summary_payload()
                payload["proof_class"] = "competition-exact"
                payload["execution_environment"].update(env_patch)

                with self.assertRaisesRegex(
                    ValueError,
                    "competition_smoke_summary proof_class=competition-exact requires exact host evidence",
                ):
                    validator.validate_competition_smoke_summary_contract(
                        payload,
                        expected_artifacts=competition_smoke_expected_artifacts(),
                        entrypoint_proof_class="competition-exact",
                    )

    def test_competition_exact_smoke_summary_requires_full_profile_match(self) -> None:
        payload = valid_competition_smoke_summary_payload()
        payload["proof_class"] = "competition-exact"
        payload["competition_profile_match"]["kernel_match"] = False

        with self.assertRaisesRegex(
            ValueError,
            "competition_smoke_summary proof_class=competition-exact requires exact host evidence",
        ):
            validator.validate_competition_smoke_summary_contract(
                payload,
                expected_artifacts=competition_smoke_expected_artifacts(),
                entrypoint_proof_class="competition-exact",
            )

    def test_competition_exact_smoke_summary_requires_host_attestation(self) -> None:
        payload = valid_competition_smoke_summary_payload()
        payload["proof_class"] = "competition-exact"
        payload["execution_environment"]["competition_exact_host_attested"] = False
        for step in payload["steps"]:
            step["status"] = "passed"
            step["returncode"] = 0
            step.pop("proof_class_effect", None)

        with self.assertRaisesRegex(
            ValueError,
            "competition_smoke_summary proof_class=competition-exact requires exact host evidence",
        ):
            validator.validate_competition_smoke_summary_contract(
                payload,
                expected_artifacts=competition_smoke_expected_artifacts(),
                entrypoint_proof_class="competition-exact",
            )

    def test_competition_exact_smoke_summary_requires_opencode_glm_probe(self) -> None:
        payload = valid_competition_smoke_summary_payload()
        payload["proof_class"] = "competition-exact"
        payload["execution_environment"]["competition_exact_host_attested"] = True
        for step in payload["steps"]:
            step["status"] = "passed"
            step["returncode"] = 0
            step.pop("proof_class_effect", None)

        with self.assertRaisesRegex(
            ValueError,
            "competition_smoke_summary proof_class=competition-exact requires exact host evidence",
        ):
            validator.validate_competition_smoke_summary_contract(
                payload,
                expected_artifacts=competition_smoke_expected_artifacts(),
                entrypoint_proof_class="competition-exact",
            )

    def test_competition_exact_smoke_summary_requires_opencode_glm_probe_step(self) -> None:
        payload = valid_competition_smoke_summary_payload()
        payload["proof_class"] = "competition-exact"
        payload["execution_environment"]["competition_exact_host_attested"] = True
        payload["opencode_model_availability"] = {
            "status": "available",
            "required_model": "GLM-5.1",
            "model_listed": True,
            "opencode_command": "opencode",
            "argv": ["opencode", "models"],
            "process_returncode": 0,
        }
        for step in payload["steps"]:
            step["status"] = "passed"
            step["returncode"] = 0
            step.pop("proof_class_effect", None)

        with self.assertRaisesRegex(
            ValueError,
            "competition_smoke_summary proof_class=competition-exact requires exact host evidence",
        ):
            validator.validate_competition_smoke_summary_contract(
                payload,
                expected_artifacts=competition_smoke_expected_artifacts(),
                entrypoint_proof_class="competition-exact",
            )

    def test_ci_approximation_smoke_summary_rejects_non_ci_environment(self) -> None:
        payload = valid_competition_smoke_summary_payload()
        payload["proof_class"] = "ci-approximation"
        payload["execution_environment"].update(
            {
                "detected_ci": False,
                "detected_wsl": True,
                "kind": "wsl",
            }
        )

        with self.assertRaisesRegex(
            ValueError,
            "competition_smoke_summary proof_class=ci-approximation requires execution_environment.detected_ci=true",
        ):
            validator.validate_competition_smoke_summary_contract(
                payload,
                expected_artifacts=competition_smoke_expected_artifacts(),
                entrypoint_proof_class="ci-approximation",
            )

    def test_wsl_local_simulation_smoke_summary_rejects_non_wsl_environment(self) -> None:
        payload = valid_competition_smoke_summary_payload()
        payload["proof_class"] = "wsl-local-simulation"
        payload["execution_environment"].update(
            {
                "detected_ci": True,
                "detected_wsl": False,
                "kind": "linux-ci",
            }
        )

        with self.assertRaisesRegex(
            ValueError,
            "competition_smoke_summary proof_class=wsl-local-simulation requires execution_environment.detected_wsl=true",
        ):
            validator.validate_competition_smoke_summary_contract(
                payload,
                expected_artifacts=competition_smoke_expected_artifacts(),
                entrypoint_proof_class="wsl-local-simulation",
            )

    def test_judge_evidence_index_requires_valid_opencode_runtime_when_present(self) -> None:
        launch_policy = opencode_launch_policy()
        preflight = {
            "path": "target/out/harness/opencode-preflight-report.json",
            "sha256": "a" * 64,
            "status": "passed",
            "contract_status": "executed",
            "launch_policy": launch_policy,
            "launch_policy_sha256": opencode_launch_policy_sha256(launch_policy),
        }
        payload = {
            "schema_version": 1,
            "report_kind": "judge-evidence-index",
            "status": "completed",
            "claim_boundary": {
                "semantic_claim_source": "accepted_evidence_binding",
                "generated_draft_semantic_pass": False,
                "translation_coverage_numerator": 0,
                "index_is_semantic_gate": False,
            },
            "judge_headline": {
                "report_kind": "judge-headline",
                "semantic_gate": False,
                "semantic_claim_source": "accepted_evidence_binding",
                "generated_draft_semantic_pass": False,
                "translation_coverage_numerator": 0,
                "opencode_runtime": {
                    "enabled": False,
                    "worker_count": 0,
                    "all_contracts_executed": False,
                    "chat_output_is_evidence": False,
                    "semantic_gate": False,
                },
            },
            "harness_architecture": {
                "architecture_contracts": {
                    "context_management": {
                        "chat_output_is_evidence": False,
                        "semantic_gate": False,
                    },
                    "agent_coordination": {
                        "chat_output_is_evidence": False,
                        "semantic_gate": False,
                        "roles": ["planner", "worker", "repairer", "verifier", "reporter"],
                    },
                },
            },
            "opencode_agent_runtime": {
                "runtime": "opencode",
                "chat_output_is_evidence": False,
                "semantic_gate": False,
                "worker_count": 1,
                "contract_status_counts": {"not-executed": 1},
                "all_contracts_executed": False,
                "failed_or_missing_contract_workers": ["worker-a"],
                "opencode_preflight_report": json.loads(json.dumps(preflight)),
                "workers": [
                    {
                        "worker_id": "worker-a",
                        "chat_output_is_evidence": False,
                        "semantic_gate": False,
                        "summary": {"path": "target/out/workers/worker-a/summary/competition-run-summary.json", "sha256": "b" * 64},
                        "worker_report": {"path": "target/out/workers/worker-a/harness/run-worker-report.json", "sha256": "c" * 64},
                        "logs": {
                            "stdout": {"path": "target/out/workers/worker-a/logs/stdout.log", "sha256": "d" * 64},
                            "stderr": {"path": "target/out/workers/worker-a/logs/stderr.log", "sha256": "e" * 64},
                        },
                        "handoff_contract": {"path": "target/out/workers/worker-a/harness/opencode-handoff-contract.json", "sha256": "f" * 64},
                        "opencode_session_evidence": {"path": "target/out/workers/worker-a/logs/opencode-session-evidence.json", "sha256": "1" * 64},
                        "opencode_preflight_report": json.loads(json.dumps(preflight)),
                        "contract_verification_status": "not-executed",
                        "opencode_contract_verification": {"status": "not-executed"},
                    },
                ],
            },
        }

        with self.assertRaisesRegex(ValueError, "opencode_agent_runtime.all_contracts_executed must be true"):
            validator.validate_judge_evidence_index_contract(payload, path_text="target/out/harness/judge-evidence-index.json")

    def test_judge_evidence_index_requires_opencode_runtime_for_opencode_mode(self) -> None:
        payload = {
            "schema_version": 1,
            "report_kind": "judge-evidence-index",
            "status": "completed",
            "mode": "opencode",
            "claim_boundary": {
                "semantic_claim_source": "accepted_evidence_binding",
                "generated_draft_semantic_pass": False,
                "translation_coverage_numerator": 0,
                "index_is_semantic_gate": False,
            },
            "judge_headline": {
                "report_kind": "judge-headline",
                "semantic_gate": False,
                "semantic_claim_source": "accepted_evidence_binding",
                "generated_draft_semantic_pass": False,
                "translation_coverage_numerator": 0,
                "opencode_runtime": {
                    "enabled": False,
                    "worker_count": 0,
                    "all_contracts_executed": False,
                    "chat_output_is_evidence": False,
                    "semantic_gate": False,
                },
            },
            "harness_architecture": {
                "architecture_contracts": {
                    "context_management": {
                        "chat_output_is_evidence": False,
                        "semantic_gate": False,
                    },
                    "agent_coordination": {
                        "chat_output_is_evidence": False,
                        "semantic_gate": False,
                        "roles": ["planner", "worker", "repairer", "verifier", "reporter"],
                    },
                },
            },
        }

        with self.assertRaisesRegex(ValueError, "opencode_agent_runtime is required when judge_evidence_index.mode is opencode"):
            validator.validate_judge_evidence_index_contract(payload, path_text="target/out/harness/judge-evidence-index.json")

    def test_deterministic_judge_evidence_index_claim_boundary_fails_closed(self) -> None:
        mutations = [
            ("semantic_claim_source", "competition-run-summary.final_gate", "semantic_claim_source must be accepted_evidence_binding"),
            ("generated_draft_semantic_pass", True, "generated_draft_semantic_pass must be false"),
            ("translation_coverage_numerator", 1, "translation_coverage_numerator must be 0"),
            ("index_is_semantic_gate", True, "index_is_semantic_gate must be false"),
        ]

        for field, value, expected_error in mutations:
            with self.subTest(field=field):
                payload = valid_deterministic_judge_index_payload()
                payload["claim_boundary"][field] = value

                with self.assertRaisesRegex(ValueError, expected_error):
                    validator.validate_judge_evidence_index_contract(
                        payload,
                        path_text="target/out/harness/judge-evidence-index.json",
                    )

    def test_judge_evidence_index_requires_judge_headline(self) -> None:
        payload = valid_deterministic_judge_index_payload()
        payload.pop("judge_headline", None)

        with self.assertRaisesRegex(ValueError, "judge_evidence_index.judge_headline must be an object"):
            validator.validate_judge_evidence_index_contract(
                payload,
                path_text="target/out/harness/judge-evidence-index.json",
            )

    def test_judge_evidence_index_headline_must_match_boundary_and_architecture(self) -> None:
        payload = valid_deterministic_judge_index_payload()
        payload["judge_headline"]["worker_count"] = 2

        with self.assertRaisesRegex(ValueError, "judge_headline.worker_count must match harness_architecture.worker_count"):
            validator.validate_judge_evidence_index_contract(
                payload,
                path_text="target/out/harness/judge-evidence-index.json",
            )

    def test_judge_evidence_index_general_artifact_ref_hash_drift_fails(self) -> None:
        target_dir = REPO_ROOT / "target"
        target_dir.mkdir(exist_ok=True)
        temp_dir = Path(tempfile.mkdtemp(prefix="judge-ref-drift-", dir=target_dir))
        workflow_metrics = temp_dir / "summary" / "workflow-metrics.json"
        workflow_metrics.parent.mkdir(parents=True)
        workflow_metrics.write_text("{}\n", encoding="utf-8")
        payload = valid_deterministic_judge_index_payload()
        payload["evidence_artifact_refs"] = {
            "workflow_metrics": {
                "path": repo_relative(workflow_metrics),
                "sha256": "0" * 64,
            }
        }

        with self.assertRaisesRegex(ValueError, "sha256 mismatch"):
            validator.validate_judge_evidence_index_contract(
                payload,
                path_text="target/out/harness/judge-evidence-index.json",
                repo_root=REPO_ROOT,
            )

    def test_judge_evidence_index_rejects_failed_verified_unsafe_baseline_ref(self) -> None:
        target_dir = REPO_ROOT / "target"
        target_dir.mkdir(exist_ok=True)
        temp_dir = Path(tempfile.mkdtemp(prefix="judge-index-verified-baseline-", dir=target_dir))
        root = temp_dir / "out"
        payload = valid_deterministic_judge_index_payload()
        for ref_name, artifact_path in {
            "competition_run_summary": root / "summary" / "competition-run-summary.json",
            "workflow_metrics": root / "summary" / "workflow-metrics.json",
            "worker_plan": root / "harness" / "plans" / "workers.json",
            "profile": root / "profile.json",
        }.items():
            set_artifact_ref(payload["evidence_artifact_refs"][ref_name], artifact_path)
        payload["evidence_artifact_refs"]["verified_unsafe_baseline"] = write_verified_unsafe_baseline_ref(
            root / "evidence" / "verified-baseline.json",
            status="failed",
        )

        with self.assertRaisesRegex(ValueError, "verified_unsafe_baseline.status must be passed"):
            validator.validate_judge_evidence_index_contract(
                payload,
                path_text=repo_relative(root / "harness" / "judge-evidence-index.json"),
                repo_root=REPO_ROOT,
            )

    def test_verified_unsafe_baseline_ref_requires_same_output_gate_refs(self) -> None:
        target_dir = REPO_ROOT / "target"
        target_dir.mkdir(exist_ok=True)
        temp_dir = Path(tempfile.mkdtemp(prefix="judge-verified-baseline-deep-", dir=target_dir))
        verified_path = temp_dir / "verified-baseline.json"
        verified_ref = write_deep_verified_unsafe_baseline_ref(verified_path)
        payload = json.loads(verified_path.read_text(encoding="utf-8"))
        payload.pop("same_output_gate_refs", None)
        write_json(verified_path, payload)
        verified_ref["sha256"] = validator.sha256_file(verified_path)

        with self.assertRaisesRegex(ValueError, "same_output_gate_refs missing"):
            validator.validate_verified_unsafe_baseline_ref(
                verified_ref,
                "verified_unsafe_baseline",
                repo_root=REPO_ROOT,
            )

    def test_verified_unsafe_baseline_ref_rejects_same_output_gate_compile_artifact_drift(self) -> None:
        target_dir = REPO_ROOT / "target"
        target_dir.mkdir(exist_ok=True)
        temp_dir = Path(tempfile.mkdtemp(prefix="judge-verified-baseline-gate-drift-", dir=target_dir))
        verified_path = temp_dir / "verified-baseline.json"
        verified_ref = write_deep_verified_unsafe_baseline_ref(verified_path)
        payload = json.loads(verified_path.read_text(encoding="utf-8"))
        payload["same_output_gate_refs"]["unsafe_ledger"]["compile_artifact"]["sha256"] = "9" * 64
        write_json(verified_path, payload)
        verified_ref["sha256"] = validator.sha256_file(verified_path)

        with self.assertRaisesRegex(ValueError, "same_output_gate_refs.unsafe_ledger.compile_artifact"):
            validator.validate_verified_unsafe_baseline_ref(
                verified_ref,
                "verified_unsafe_baseline",
                repo_root=REPO_ROOT,
            )

    def test_verified_unsafe_baseline_ref_rejects_accepted_rust_report_as_replay_gate(self) -> None:
        target_dir = REPO_ROOT / "target"
        target_dir.mkdir(exist_ok=True)
        temp_dir = Path(tempfile.mkdtemp(prefix="judge-verified-baseline-rust-report-", dir=target_dir))
        verified_path = temp_dir / "verified-baseline.json"
        verified_ref = write_deep_verified_unsafe_baseline_ref(verified_path)
        payload = json.loads(verified_path.read_text(encoding="utf-8"))
        payload["same_output_gate_refs"]["rust_replay"]["path"] = "validation/evidence/demo/l3-demo-rust-report.json"
        payload["same_output_gate_refs"]["rust_replay"].pop("replay_kind", None)
        payload["same_output_gate_refs"]["rust_replay"].pop("correctness_role", None)
        write_json(verified_path, payload)
        verified_ref["sha256"] = validator.sha256_file(verified_path)

        with self.assertRaisesRegex(ValueError, "rust_replay.path must point to direct C2Rust replay evidence"):
            validator.validate_verified_unsafe_baseline_ref(
                verified_ref,
                "verified_unsafe_baseline",
                repo_root=REPO_ROOT,
            )

    def test_judge_evidence_index_route_governance_metrics_report_must_match_schema(self) -> None:
        target_dir = REPO_ROOT / "target"
        target_dir.mkdir(exist_ok=True)
        temp_dir = Path(tempfile.mkdtemp(prefix="judge-route-metrics-schema-", dir=target_dir))
        route_metrics = temp_dir / "summary" / "route-governance-metrics-report.json"
        write_json(
            route_metrics,
            {
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
                    "accepted_evidence_semantic_pass_count": 1,
                    "tracked_capability_delta_ledgers": 1,
                    "tracked_capability_delta_count": 1,
                    "tracked_route_decision_artifacts": 1,
                    "s2_workflow_metrics": {},
                    "candidate_generation_inventory": {},
                    "tracked_slice_gate_contexts": 1,
                    "slice_gate_contexts": [],
                    "c2rust_baseline": {
                        "report_kind": "c2rust-baseline-rollup",
                        "status": "none",
                        "manifest_count": 0,
                        "generated_output_count": 0,
                        "skipped_without_output_count": 0,
                        "compile_attempted_count": 0,
                        "compile_passed_count": 0,
                        "compile_semantic_pass_count": 0,
                        "status_counts": {},
                        "output_status_counts": {},
                        "compile_status_counts": {},
                        "manifests": [],
                        "semantic_gate": False,
                        "generated_draft_semantic_pass": False,
                        "translation_coverage_numerator": 0,
                        "boundary": "C2Rust baseline status is candidate context only.",
                    },
                    "blocked_repairs": {
                        "status": "none",
                        "blocked_repair_count": 0,
                        "slice_count": 0,
                        "human_action_required_count": 0,
                        "status_counts": {"none": 1},
                        "human_intervention_points": [],
                        "blocked_callees": [],
                        "ir_feature_gap_kinds": {},
                        "forbidden_change_counts": {},
                        "blocked_reason_counts": {},
                        "source_span_kind_counts": {},
                        "smallest_next_tests": [],
                        "next_actions": [],
                        "semantic_gate": False,
                        "translation_coverage_numerator": 0,
                        "boundary": "Blocked repairs are not semantic acceptance evidence.",
                    },
                },
                "denominators": {
                    "capability_delta_ledger": "capability delta ledger artifacts",
                    "candidate_generation_inventory": "route decision artifacts",
                    "slice_gate_contexts": "slice gate contexts",
                    "translation_coverage_numerator": "translator-generated only",
                    "accepted_evidence_semantic_pass_count": "separate accepted evidence count",
                    "s2_workflow_metrics": "competition summaries",
                    "c2rust_baseline": "candidate-context C2Rust baseline manifests",
                    "blocked_repairs": "self-healing blocked repairs artifacts",
                },
                "claim_boundary": "Route governance metrics are not semantic acceptance evidence.",
                "retention_policy": {
                    "report_kind": "route-governance-metrics-retention-policy",
                    "report_role": "p0-route-governance-and-capability-metrics",
                    "target_artifacts": {
                        "retention_class": "reproducible-local-output",
                        "committed": False,
                        "policy": "regenerate from summary inputs",
                    },
                    "committed_anchors": {
                        "retention_class": "release-evidence",
                        "policy": "commit only durable anchors",
                    },
                    "claim_boundary": "Retention policy does not change semantic acceptance.",
                },
            },
        )
        payload = valid_deterministic_judge_index_payload()
        payload["evidence_artifact_refs"] = {
            "route_governance_metrics_report": {
                "path": repo_relative(route_metrics),
                "sha256": validator.sha256_file(route_metrics),
            }
        }

        with self.assertRaisesRegex(ValueError, "route_governance_metrics_report.*s2_workflow_metrics"):
            validator.validate_judge_evidence_index_contract(
                payload,
                path_text="target/out/harness/judge-evidence-index.json",
                expected_artifacts={"route_governance_metrics_report": repo_relative(route_metrics)},
                repo_root=REPO_ROOT,
            )

        full_payload = json.loads(route_metrics.read_text(encoding="utf-8"))
        full_payload["metrics"]["s2_workflow_metrics"] = {
            "run_count": 1,
            "input_summaries": [],
            "units_total": 1,
            "units_converged": 1,
            "units_baseline_only": 0,
            "unsafe_reduction": {
                "status": "measured",
                "baseline_total_unsafe": 2,
                "current_total_unsafe": 0,
                "reduced_by": 2,
                "ratio": 0.0,
            },
            "translation_before_after": {
                "status": "not_provided",
                "input_run_count": 0,
                "unit_count": 0,
                "measured_unsafe_unit_count": 0,
                "accepted_patch_unit_count": 0,
            },
            "measured_unsafe_reduction_run_count": 1,
            "avg_repair_rounds": 1.0,
            "auto_recovery_rate": 1.0,
            "human_interventions": 0,
            "fail_closed_count": 0,
            "root_cause_counts": {},
            "wall_clock_seconds": 1,
            "llm_calls": 1,
            "repair_history_unit_count": 1,
            "auto_recovered_units": 1,
            "claim_boundary": "S2 workflow metrics are not semantic acceptance.",
        }
        write_json(route_metrics, full_payload)
        payload["evidence_artifact_refs"]["route_governance_metrics_report"]["sha256"] = validator.sha256_file(route_metrics)

        result = validator.validate_judge_evidence_index_contract(
            payload,
            path_text="target/out/harness/judge-evidence-index.json",
            expected_artifacts={"route_governance_metrics_report": repo_relative(route_metrics)},
            repo_root=REPO_ROOT,
        )
        self.assertEqual(
            result["evidence_artifact_refs"]["route_governance_metrics_report"]["status"],
            "passed",
        )
