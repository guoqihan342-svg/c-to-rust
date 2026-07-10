class _JudgeEntrypointsValidatorTestsPart09:
    def test_judge_index_allows_bound_c2rust_safety_claim_source(self) -> None:
        payload = valid_opencode_judge_index_payload()
        source = "c2rust_safety_transform_replay_with_accepted_c_oracle"
        payload["claim_boundary"]["semantic_claim_source"] = source
        payload["judge_headline"]["semantic_claim_source"] = source
        payload["core_translation_quality"] = {
            "semantic_claim_source": source,
            "translation_coverage_numerator": 0,
        }

        result = validator.validate_judge_evidence_index_contract(
            payload,
            path_text="target/judge-evidence-index.json",
        )

        self.assertEqual(result["status"], "passed")

    def test_judge_index_rejects_unbound_c2rust_safety_claim_source(self) -> None:
        payload = valid_opencode_judge_index_payload()
        source = "c2rust_safety_transform_replay_with_accepted_c_oracle"
        payload["claim_boundary"]["semantic_claim_source"] = source
        payload["judge_headline"]["semantic_claim_source"] = source
        payload["core_translation_quality"] = {
            "semantic_claim_source": "accepted_evidence_binding",
            "translation_coverage_numerator": 0,
        }

        with self.assertRaisesRegex(ValueError, "core_translation_quality.semantic_claim_source must match"):
            validator.validate_judge_evidence_index_contract(
                payload,
                path_text="target/judge-evidence-index.json",
            )

    def test_judge_index_rejects_unknown_semantic_claim_source(self) -> None:
        payload = valid_opencode_judge_index_payload()
        payload["claim_boundary"]["semantic_claim_source"] = "unbound_claim_source"
        payload["judge_headline"]["semantic_claim_source"] = "unbound_claim_source"

        with self.assertRaisesRegex(ValueError, "must be a supported bound source"):
            validator.validate_judge_evidence_index_contract(
                payload,
                path_text="target/judge-evidence-index.json",
            )

    def test_judge_index_rejects_coverage_numerator_core_quality_drift(self) -> None:
        payload = valid_opencode_judge_index_payload()
        payload["claim_boundary"]["translation_coverage_numerator"] = 21
        payload["judge_headline"]["translation_coverage_numerator"] = 21
        payload["core_translation_quality"] = {
            "semantic_claim_source": "accepted_evidence_binding",
            "translation_coverage_numerator": 20,
        }

        with self.assertRaisesRegex(ValueError, "core_translation_quality.translation_coverage_numerator must match"):
            validator.validate_judge_evidence_index_contract(
                payload,
                path_text="target/judge-evidence-index.json",
            )

    def test_merge_execution_argv_allows_host_trace(self) -> None:
        result = validator.validate_local_absolute_path_policy(
            {"merge_execution": {"argv": ["C:\\Python314\\python.exe", "validation/tools/run_competition.py"]}},
            label="merge-execution",
        )

        self.assertEqual(result["status"], "passed")
        self.assertEqual(result["host_trace_allowed_locations"], ["$.merge_execution.argv.0"])

    def test_diagnostic_host_metadata_allows_host_trace(self) -> None:
        result = validator.validate_local_absolute_path_policy(
            {
                "portability": {
                    "diagnostic_host_metadata": [
                        {"code": "diagnostic_host_metadata_path", "value": "F:\\agent\\crustpaper\\0630"}
                    ]
                }
            },
            label="evidence-governance",
        )

        self.assertEqual(result["status"], "passed")
        self.assertEqual(
            result["host_trace_allowed_locations"],
            ["$.portability.diagnostic_host_metadata.0.value"],
        )

    def test_judge_evidence_reproduction_commands_reject_local_absolute_paths(self) -> None:
        payload = {
            "report_kind": "judge-evidence-index",
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
                }
            },
            "reproduction_commands": {
                "evaluate_profile": "C:\\Python314\\python.exe -m validation.tools.opencode_agent_harness evaluate"
            },
        }

        with self.assertRaisesRegex(ValueError, "local absolute path"):
            validator.validate_judge_evidence_index_contract(payload, path_text="target/judge-evidence-index.json")

    def test_core_validation_ci_runs_judge_entrypoints_validator_tests(self) -> None:
        workflow = (REPO_ROOT / ".github/workflows/core-translator-validation-ci.yml").read_text(encoding="utf-8")
        self.assertIn("validation.tools.test_validate_judge_entrypoints", workflow)
