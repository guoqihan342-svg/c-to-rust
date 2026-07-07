class _JudgeEntrypointsValidatorTestsPart03:
    def test_opencode_agent_runtime_rejects_safety_attempt_not_bound_to_worker_report(self) -> None:
        temp_dir = Path(tempfile.mkdtemp(prefix="judge-opencode-worker-attempt-report-drift-", dir=REPO_ROOT / "target"))
        payload = valid_opencode_judge_index_payload()
        materialize_opencode_judge_index_artifacts(
            payload,
            temp_dir / "out",
            profile_payload={
                "schema_version": 1,
                "profile_id": "opencode-profile",
                "mode": "opencode",
                **opencode_launch_policy(),
                "auto_retry": True,
            },
        )
        worker = payload["opencode_agent_runtime"]["workers"][0]
        worker_report_path = REPO_ROOT / worker["worker_report"]["path"]
        attempt_path = temp_dir / "out" / "workers" / "worker-a" / "harness" / "opencode-safety-transform-attempt.json"
        other_attempt_path = (
            temp_dir / "out" / "workers" / "worker-a" / "harness" / "other-opencode-safety-transform-attempt.json"
        )
        write_json(attempt_path, {"report_kind": "test-opencode-safety-transform-attempt", "id": "expected"})
        write_json(other_attempt_path, {"report_kind": "test-opencode-safety-transform-attempt", "id": "drifted"})
        worker["opencode_safety_transform_attempt"] = {
            "path": repo_relative(attempt_path),
            "sha256": validator.sha256_file(attempt_path),
        }
        worker_report = json.loads(worker_report_path.read_text(encoding="utf-8"))
        worker_report["opencode_safety_transform_attempt"] = {
            "path": repo_relative(other_attempt_path),
            "sha256": validator.sha256_file(other_attempt_path),
        }
        write_json(worker_report_path, worker_report)
        worker["worker_report"]["sha256"] = validator.sha256_file(worker_report_path)

        with self.assertRaisesRegex(
            ValueError,
            r"opencode_agent_runtime\.workers\[0\]\.worker_report\.opencode_safety_transform_attempt "
            r"must match opencode_safety_transform_attempt",
        ):
            validator.validate_opencode_agent_runtime_contract(
                payload["opencode_agent_runtime"],
                repo_root=REPO_ROOT,
            )

    def test_opencode_agent_runtime_rejects_invalid_worker_summary_contract(self) -> None:
        temp_dir = Path(tempfile.mkdtemp(prefix="judge-opencode-worker-summary-contract-", dir=REPO_ROOT / "target"))
        payload = valid_opencode_judge_index_payload()
        materialize_opencode_judge_index_artifacts(
            payload,
            temp_dir / "out",
            profile_payload={
                "schema_version": 1,
                "profile_id": "opencode-profile",
                "mode": "opencode",
                **opencode_launch_policy(),
                "auto_retry": True,
            },
        )
        worker = payload["opencode_agent_runtime"]["workers"][0]
        summary_path = REPO_ROOT / worker["summary"]["path"]
        write_json(summary_path, {"final_gate": {"status": "passed"}})
        worker["summary"]["sha256"] = validator.sha256_file(summary_path)

        with self.assertRaisesRegex(
            ValueError,
            r"opencode_agent_runtime\.workers\[0\]\.summary must satisfy competition run summary contract",
        ):
            validator.validate_opencode_agent_runtime_contract(
                payload["opencode_agent_runtime"],
                repo_root=REPO_ROOT,
            )

    def test_judge_evidence_index_rejects_worker_session_missing_workdir(self) -> None:
        temp_dir = Path(tempfile.mkdtemp(prefix="judge-opencode-worker-missing-workdir-", dir=REPO_ROOT / "target"))
        payload = valid_opencode_judge_index_payload()
        materialize_opencode_judge_index_artifacts(
            payload,
            temp_dir / "out",
            profile_payload={
                "schema_version": 1,
                "profile_id": "opencode-profile",
                "mode": "opencode",
                **opencode_launch_policy(),
            },
        )
        worker = payload["opencode_agent_runtime"]["workers"][0]
        command_line = worker["opencode_contract_verification"]["expected_worker_command_line"]
        rewrite_worker_session_evidence(
            worker,
            {
                "schema_version": 1,
                "process_returncode": 0,
                "parsed": True,
                "format": "jsonl",
                "session_events": [
                    {
                        "part": {
                            "tool": "bash",
                            "state": {"input": {"command": command_line}},
                        }
                    }
                ],
            },
        )

        with self.assertRaisesRegex(ValueError, "opencode_workdir_mismatch"):
            validator.validate_judge_evidence_index_contract(
                payload,
                path_text=repo_relative(temp_dir / "out" / "harness" / "judge-evidence-index.json"),
                repo_root=REPO_ROOT,
            )

    def test_judge_evidence_index_rejects_worker_report_without_runtime_env(self) -> None:
        temp_dir = Path(tempfile.mkdtemp(prefix="judge-opencode-worker-report-no-runtime-env-", dir=REPO_ROOT / "target"))
        payload = valid_opencode_judge_index_payload()
        materialize_opencode_judge_index_artifacts(
            payload,
            temp_dir / "out",
            profile_payload={
                "schema_version": 1,
                "profile_id": "opencode-profile",
                "mode": "opencode",
                **opencode_launch_policy(),
            },
        )
        worker = payload["opencode_agent_runtime"]["workers"][0]
        worker_report_path = REPO_ROOT / worker["worker_report"]["path"]
        worker_report = json.loads(worker_report_path.read_text(encoding="utf-8"))
        worker_report.pop("opencode_runtime_env")
        write_json(worker_report_path, worker_report)
        worker["worker_report"]["sha256"] = validator.sha256_file(worker_report_path)

        with self.assertRaisesRegex(ValueError, "worker_report.opencode_runtime_env"):
            validator.validate_judge_evidence_index_contract(
                payload,
                path_text=repo_relative(temp_dir / "out" / "harness" / "judge-evidence-index.json"),
                repo_root=REPO_ROOT,
            )

    def test_judge_evidence_index_rejects_worker_report_identity_drift(self) -> None:
        temp_dir = Path(tempfile.mkdtemp(prefix="judge-opencode-worker-report-identity-", dir=REPO_ROOT / "target"))
        payload = valid_opencode_judge_index_payload()
        materialize_opencode_judge_index_artifacts(
            payload,
            temp_dir / "out",
            profile_payload={
                "schema_version": 1,
                "profile_id": "opencode-profile",
                "mode": "opencode",
                **opencode_launch_policy(),
            },
        )
        worker = payload["opencode_agent_runtime"]["workers"][0]
        worker_report_path = REPO_ROOT / worker["worker_report"]["path"]
        worker_report = json.loads(worker_report_path.read_text(encoding="utf-8"))
        worker_report["report_kind"] = "not-run-worker-report"
        worker_report["worker_id"] = "other-worker"
        write_json(worker_report_path, worker_report)
        worker["worker_report"]["sha256"] = validator.sha256_file(worker_report_path)

        with self.assertRaisesRegex(ValueError, "worker_report.report_kind must be run-worker-report"):
            validator.validate_judge_evidence_index_contract(
                payload,
                path_text=repo_relative(temp_dir / "out" / "harness" / "judge-evidence-index.json"),
                repo_root=REPO_ROOT,
            )

    def test_judge_evidence_index_rejects_worker_report_execution_state_drift(self) -> None:
        cases = [
            ("wrong_mode", {"mode": "deterministic"}, "worker_report.mode must be opencode"),
            ("not_recorded", {"recorded": False}, "worker_report.recorded must be true"),
            ("nonzero_exit_code", {"exit_code": 1}, "worker_report.exit_code must be 0"),
            (
                "nonzero_process_returncode",
                {"process_returncode": 1},
                "worker_report.process_returncode must be 0",
            ),
        ]
        for case_name, updates, expected_error in cases:
            with self.subTest(case=case_name):
                temp_dir = Path(
                    tempfile.mkdtemp(prefix="judge-opencode-worker-report-execution-", dir=REPO_ROOT / "target")
                )
                payload = valid_opencode_judge_index_payload()
                materialize_opencode_judge_index_artifacts(
                    payload,
                    temp_dir / "out",
                    profile_payload={
                        "schema_version": 1,
                        "profile_id": "opencode-profile",
                        "mode": "opencode",
                        **opencode_launch_policy(),
                    },
                )
                worker = payload["opencode_agent_runtime"]["workers"][0]
                worker_report_path = REPO_ROOT / worker["worker_report"]["path"]
                worker_report = json.loads(worker_report_path.read_text(encoding="utf-8"))
                worker_report.update(updates)
                write_json(worker_report_path, worker_report)
                worker["worker_report"]["sha256"] = validator.sha256_file(worker_report_path)

                with self.assertRaisesRegex(ValueError, expected_error):
                    validator.validate_opencode_agent_runtime_contract(
                        payload["opencode_agent_runtime"],
                        repo_root=REPO_ROOT,
                    )

    def test_judge_evidence_index_rejects_worker_handoff_opencode_argv_policy_drift(self) -> None:
        def materialized_payload(temp_dir: Path) -> dict:
            payload = valid_opencode_judge_index_payload()
            materialize_opencode_judge_index_artifacts(
                payload,
                temp_dir / "out",
                profile_payload={
                    "schema_version": 1,
                    "profile_id": "opencode-profile",
                    "mode": "opencode",
                    **opencode_launch_policy(),
                },
            )
            return payload

        with self.subTest(tamper="green_control"):
            temp_dir = Path(tempfile.mkdtemp(prefix="judge-opencode-worker-handoff-argv-", dir=REPO_ROOT / "target"))
            payload = materialized_payload(temp_dir)
            result = validator.validate_opencode_agent_runtime_contract(
                payload["opencode_agent_runtime"],
                repo_root=REPO_ROOT,
            )
            self.assertEqual(result["status"], "passed")

        def tamper_model(argv: list) -> None:
            argv[argv.index("--model") + 1] = "not-GLM-5.1"

        def tamper_variant(argv: list) -> None:
            argv[argv.index("--variant") + 1] = "lite"

        def tamper_extra_flag(argv: list) -> None:
            argv[-1:-1] = ["--profile", "dev"]

        cases = [
            (
                "non_glm_model",
                tamper_model,
                r"opencode_agent_runtime.workers\[0\].handoff_contract.opencode_argv --model must be GLM-5.1",
            ),
            (
                "non_max_variant",
                tamper_variant,
                r"opencode_agent_runtime.workers\[0\].handoff_contract.opencode_argv --variant must be max",
            ),
            (
                "unexpected_flag",
                tamper_extra_flag,
                r"opencode_agent_runtime.workers\[0\].handoff_contract.opencode_argv has unexpected flags: --profile",
            ),
        ]
        for name, tamper, expected_error in cases:
            with self.subTest(tamper=name):
                temp_dir = Path(tempfile.mkdtemp(prefix="judge-opencode-worker-handoff-argv-", dir=REPO_ROOT / "target"))
                payload = materialized_payload(temp_dir)
                worker = payload["opencode_agent_runtime"]["workers"][0]
                handoff_path = REPO_ROOT / worker["handoff_contract"]["path"]
                handoff_payload = json.loads(handoff_path.read_text(encoding="utf-8"))
                tamper(handoff_payload["opencode_argv"])
                handoff_payload["opencode_command_line"] = shlex.join(handoff_payload["opencode_argv"])
                write_json(handoff_path, handoff_payload)
                worker["handoff_contract"]["sha256"] = validator.sha256_file(handoff_path)

                with self.assertRaisesRegex(ValueError, expected_error):
                    validator.validate_judge_evidence_index_contract(
                        payload,
                        path_text=repo_relative(temp_dir / "out" / "harness" / "judge-evidence-index.json"),
                        repo_root=REPO_ROOT,
                    )

    def test_judge_evidence_index_requires_matching_worker_opencode_launch_policy(self) -> None:
        payload = valid_opencode_judge_index_payload()
        worker_preflight = payload["opencode_agent_runtime"]["workers"][0]["opencode_preflight_report"]
        worker_preflight["launch_policy"]["opencode_skip_permissions"] = True
        worker_preflight["launch_policy_sha256"] = opencode_launch_policy_sha256(worker_preflight["launch_policy"])

        with self.assertRaisesRegex(
            ValueError,
            "opencode_agent_runtime.workers\\[0\\].opencode_preflight_report.launch_policy must match opencode_agent_runtime.opencode_preflight_report",
        ):
            validator.validate_judge_evidence_index_contract(
                payload,
                path_text="target/out/harness/judge-evidence-index.json",
            )

    def test_judge_evidence_index_refs_must_be_repo_relative(self) -> None:
        payload = valid_opencode_judge_index_payload()
        payload["evidence_artifact_refs"]["workflow_metrics"]["path"] = "C:/tmp/workflow-metrics.json"

        with self.assertRaisesRegex(ValueError, "path must not use a drive prefix"):
            validator.validate_judge_evidence_index_contract(
                payload,
                path_text="target/out/harness/judge-evidence-index.json",
            )

    def test_judge_evidence_index_refs_reject_self_reference(self) -> None:
        payload = valid_opencode_judge_index_payload()
        payload["evidence_artifact_refs"]["judge_evidence_index"] = artifact_ref(
            "target/out/harness/judge-evidence-index.json",
            "6",
        )

        with self.assertRaisesRegex(ValueError, "must not include judge_evidence_index"):
            validator.validate_judge_evidence_index_contract(
                payload,
                path_text="target/out/harness/judge-evidence-index.json",
            )

    def test_require_local_artifacts_checks_expected_artifact_presence(self) -> None:
        config = load_default_config()
        config["entrypoints"] = [entrypoint_by_id(config, "before_after_judge_demo")]
        temp_config = write_temp_config(config)
        out_root = bind_entrypoint_to_out_root(config, temp_config, entry_index=0, out_root=temp_config.parent / "out")
        artifact = out_root / "harness" / "validator.txt"
        artifact.parent.mkdir(parents=True, exist_ok=True)
        artifact.write_text("validator\n", encoding="utf-8")
        config["entrypoints"][0]["expected_artifacts"] = {
            "validator": repo_relative(artifact)
        }
        config["test_contract"]["required_entrypoint_ids"] = ["before_after_judge_demo"]
        config["test_contract"]["required_expected_artifacts"] = ["validator"]
        write_json(temp_config, config)

        result = validator.validate_config(temp_config, require_local_artifacts=True, repo_root=REPO_ROOT)

        self.assertEqual(result["status"], "passed")
        artifacts = result["entrypoints"][0]["expected_artifacts"]
        self.assertEqual(artifacts["validator"]["status"], "present")
        self.assertIn("sha256", artifacts["validator"])

    def test_require_local_artifacts_rejects_competition_summary_entrypoint_drift(self) -> None:
        cases = [
            (
                "profile_sha256",
                {"profile_sha256": "b" * 64},
                "competition_summary profile_sha256 must match environment_profile.sha256",
            ),
            (
                "profile_id",
                {"profile_id": "drifted-profile"},
                "competition_summary profile_id must match environment_profile.profile_id",
            ),
            (
                "proof_class",
                {"proof_class": "competition-exact"},
                "competition_summary proof_class must match entrypoint proof_class",
            ),
            (
                "run_id",
                {"run_id": "stale-run"},
                "competition_summary run_id must match entrypoint run_id",
            ),
        ]
        for field, drift, expected_error in cases:
            with self.subTest(field=field):
                config = load_default_config()
                config["entrypoints"] = [entrypoint_by_id(config, "before_after_judge_demo")]
                config["test_contract"]["required_entrypoint_ids"] = ["before_after_judge_demo"]
                config["test_contract"]["required_expected_artifacts"] = ["competition_summary"]
                temp_config = write_temp_config(config)
                out_root = bind_entrypoint_to_out_root(
                    config,
                    temp_config,
                    entry_index=0,
                    out_root=temp_config.parent / f"out-{field}",
                )
                summary = out_root / "summary" / "competition-run-summary.json"
                payload = valid_competition_run_summary_payload(
                    run_id="competition-flashdb-before-after-exhibit",
                )
                payload.update(drift)
                write_competition_run_summary_with_workflow_metrics(summary, payload)
                config["entrypoints"][0]["expected_artifacts"] = {
                    "competition_summary": repo_relative(summary),
                }
                write_json(temp_config, config)

                result = validator.validate_config(temp_config, require_local_artifacts=True, repo_root=REPO_ROOT)

                self.assertEqual(result["status"], "failed")
                self.assertTrue(any(expected_error in error for error in result["errors"]), result["errors"])

    def test_require_local_artifacts_deep_validates_competition_summary_workflow_metrics(self) -> None:
        config = load_default_config()
        config["entrypoints"] = [entrypoint_by_id(config, "before_after_judge_demo")]
        config["test_contract"]["required_entrypoint_ids"] = ["before_after_judge_demo"]
        config["test_contract"]["required_expected_artifacts"] = ["competition_summary", "workflow_metrics"]
        temp_config = write_temp_config(config)
        out_root = bind_entrypoint_to_out_root(
            config,
            temp_config,
            entry_index=0,
            out_root=temp_config.parent / "out-deep-summary",
        )
        summary_path = out_root / "summary" / "competition-run-summary.json"
        summary_payload = valid_competition_run_summary_payload(
            run_id="competition-flashdb-before-after-exhibit",
        )
        metrics_path = write_competition_run_summary_with_workflow_metrics(summary_path, summary_payload)
        metrics_payload = json.loads(metrics_path.read_text(encoding="utf-8"))
        metrics_payload["units_total"] = 2
        write_json(metrics_path, metrics_payload)
        summary_payload["workflow_metrics"]["sha256"] = validator.sha256_file(metrics_path)
        write_json(summary_path, summary_payload)
        config["entrypoints"][0]["expected_artifacts"] = {
            "competition_summary": repo_relative(summary_path),
            "workflow_metrics": repo_relative(metrics_path),
        }
        write_json(temp_config, config)

        result = validator.validate_config(temp_config, require_local_artifacts=True, repo_root=REPO_ROOT)

        self.assertEqual(result["status"], "failed")
        self.assertTrue(
            any("workflow metrics artifact units_total does not match competition summary" in error for error in result["errors"]),
            result["errors"],
        )

    def test_require_local_artifacts_validates_vendored_clang_missing_summary_contract(self) -> None:
        with tempfile.TemporaryDirectory(prefix="judge-entrypoints-test-", dir=REPO_ROOT / "target") as tmp:
            root = Path(tmp)
            summary_path = root / "summary" / "competition-smoke-summary.json"
            vendored_path = root / "summary" / "vendored-clang-verification.json"
            evidence_governance = root / "reports" / "evidence-governance.json"
            coverage_matrix = root / "reports" / "translator-coverage-matrix.json"
            milestone = root / "reports" / "milestone-release-report.json"
            command_log = root / "logs" / "commands.jsonl"

            artifacts = {
                "competition_smoke_summary": repo_relative(summary_path),
                "vendored_clang_verification": repo_relative(vendored_path),
                "evidence_governance_report": repo_relative(evidence_governance),
                "translator_coverage_matrix": repo_relative(coverage_matrix),
                "milestone_release_report": repo_relative(milestone),
                "command_log": repo_relative(command_log),
            }
            payload = valid_competition_smoke_summary_payload()
            payload["run_id"] = "smoke-vendored-clang-contract-test"
            payload["competition_profile_match"]["clang_lane_verified"] = False
            payload["vendored_clang_verification"]["path"] = artifacts["vendored_clang_verification"]
            payload["reports"]["evidence_governance"]["path"] = artifacts["evidence_governance_report"]
            payload["reports"]["translator_coverage_matrix"]["path"] = artifacts["translator_coverage_matrix"]
            payload["milestone_release_report"]["path"] = artifacts["milestone_release_report"]
            payload["command_log"]["path"] = artifacts["command_log"]
            for step in payload["steps"]:
                step["log_path"] = artifacts["command_log"]

            write_json(summary_path, payload)
            write_json(
                vendored_path,
                {
                    "schema_version": 1,
                    "artifact_kind": "vendored-clang-verification",
                    "proof_class": "local-simulation",
                    "profile_id": "huawei-competition-ubuntu-24.04",
                    "profile_sha256": "a" * 64,
                    "status": "missing",
                    "clang": {"source": "missing", "path": None, "version": None},
                    "clang_required": False,
                    "clang_lane_verified": False,
                    "checks": {},
                    "command_logs": [],
                    "final_gate": {"status": "passed"},
                },
            )
            payload["command_log"]["sha256"] = write_valid_command_log(
                command_log,
                payload["steps"],
                run_id=payload["run_id"],
            )
            write_json(summary_path, payload)

            with self.assertRaisesRegex(
                ValueError,
                "vendored_clang_verification missing status requires reason=missing_clang_path",
            ):
                validator.validate_harness_artifact_contracts(
                    artifacts,
                    require_local_artifacts=True,
                    repo_root=REPO_ROOT,
                    environment_profile={
                        "profile_id": "huawei-competition-ubuntu-24.04",
                        "sha256": "a" * 64,
                    },
                    smoke_contract={
                        "proof_class": "local-simulation",
                        "run_id": "smoke-vendored-clang-contract-test",
                    },
                )

    def test_require_local_artifacts_rejects_vendored_clang_summary_drift(self) -> None:
        with tempfile.TemporaryDirectory(prefix="judge-entrypoints-test-", dir=REPO_ROOT / "target") as tmp:
            root = Path(tmp)
            summary_path = root / "summary" / "competition-smoke-summary.json"
            vendored_path = root / "summary" / "vendored-clang-verification.json"
            evidence_governance = root / "reports" / "evidence-governance.json"
            coverage_matrix = root / "reports" / "translator-coverage-matrix.json"
            milestone = root / "reports" / "milestone-release-report.json"
            command_log = root / "logs" / "commands.jsonl"

            artifacts = {
                "competition_smoke_summary": repo_relative(summary_path),
                "vendored_clang_verification": repo_relative(vendored_path),
                "evidence_governance_report": repo_relative(evidence_governance),
                "translator_coverage_matrix": repo_relative(coverage_matrix),
                "milestone_release_report": repo_relative(milestone),
                "command_log": repo_relative(command_log),
            }
            payload = valid_competition_smoke_summary_payload()
            payload["run_id"] = "smoke-vendored-clang-drift-test"
            payload["vendored_clang_verification"]["path"] = artifacts["vendored_clang_verification"]
            payload["reports"]["evidence_governance"]["path"] = artifacts["evidence_governance_report"]
            payload["reports"]["translator_coverage_matrix"]["path"] = artifacts["translator_coverage_matrix"]
            payload["milestone_release_report"]["path"] = artifacts["milestone_release_report"]
            payload["command_log"]["path"] = artifacts["command_log"]
            for step in payload["steps"]:
                step["log_path"] = artifacts["command_log"]

            write_json(summary_path, payload)
            write_json(
                vendored_path,
                {
                    "schema_version": 1,
                    "artifact_kind": "vendored-clang-verification",
                    "proof_class": "local-simulation",
                    "profile_id": "huawei-competition-ubuntu-24.04",
                    "profile_sha256": "a" * 64,
                    "status": "missing",
                    "reason": "missing_clang_path",
                    "clang": {"source": "missing", "path": None, "version": None},
                    "clang_required": False,
                    "clang_lane_verified": False,
                    "checks": {},
                    "command_logs": [],
                    "final_gate": {"status": "passed"},
                },
            )
            payload["command_log"]["sha256"] = write_valid_command_log(
                command_log,
                payload["steps"],
                run_id=payload["run_id"],
            )
            write_json(summary_path, payload)

            with self.assertRaisesRegex(
                ValueError,
                "vendored_clang_verification clang_lane_verified must match competition_smoke_summary",
            ):
                validator.validate_harness_artifact_contracts(
                    artifacts,
                    require_local_artifacts=True,
                    repo_root=REPO_ROOT,
                    environment_profile={
                        "profile_id": "huawei-competition-ubuntu-24.04",
                        "sha256": "a" * 64,
                    },
                    smoke_contract={
                        "proof_class": "local-simulation",
                        "run_id": "smoke-vendored-clang-drift-test",
                    },
                )

    def test_require_local_artifacts_rejects_malformed_competition_smoke_report_artifacts(self) -> None:
        cases = [
            (
                "evidence_governance_report",
                "evidence_governance_report.schema_version must be 1",
            ),
            (
                "translator_coverage_matrix",
                "translator_coverage_matrix.schema_version must be 1",
            ),
            (
                "milestone_release_report",
                "milestone_release_report.schema_version must be 1",
            ),
        ]
        for artifact_key, expected_error in cases:
            with self.subTest(artifact_key=artifact_key):
                with tempfile.TemporaryDirectory(prefix="judge-entrypoints-test-", dir=REPO_ROOT / "target") as tmp:
                    root = Path(tmp)
                    artifacts, _payload = write_exact_competition_smoke_fixture(
                        root,
                        run_id=f"smoke-report-artifacts-{artifact_key}-contract-test",
                    )
                    write_json(REPO_ROOT / artifacts[artifact_key], {})

                    with self.assertRaisesRegex(ValueError, expected_error):
                        validator.validate_harness_artifact_contracts(
                            artifacts,
                            require_local_artifacts=True,
                            repo_root=REPO_ROOT,
                            environment_profile={
                                "profile_id": "huawei-competition-ubuntu-24.04",
                                "sha256": "a" * 64,
                            },
                            smoke_contract={
                                "proof_class": "competition-exact",
                                "run_id": f"smoke-report-artifacts-{artifact_key}-contract-test",
                            },
                        )

    def test_require_local_artifacts_rejects_missing_command_log(self) -> None:
        with tempfile.TemporaryDirectory(prefix="judge-entrypoints-test-", dir=REPO_ROOT / "target") as tmp:
            root = Path(tmp)
            summary_path = root / "summary" / "competition-smoke-summary.json"
            vendored_path = root / "summary" / "vendored-clang-verification.json"
            evidence_governance = root / "reports" / "evidence-governance.json"
            coverage_matrix = root / "reports" / "translator-coverage-matrix.json"
            milestone = root / "reports" / "milestone-release-report.json"
            command_log = root / "logs" / "commands.jsonl"

            artifacts = {
                "competition_smoke_summary": repo_relative(summary_path),
                "vendored_clang_verification": repo_relative(vendored_path),
                "evidence_governance_report": repo_relative(evidence_governance),
                "translator_coverage_matrix": repo_relative(coverage_matrix),
                "milestone_release_report": repo_relative(milestone),
                "command_log": repo_relative(command_log),
            }
            payload = valid_competition_smoke_summary_payload()
            payload["run_id"] = "smoke-missing-command-log-contract-test"
            payload["vendored_clang_verification"]["path"] = artifacts["vendored_clang_verification"]
            payload["reports"]["evidence_governance"]["path"] = artifacts["evidence_governance_report"]
            payload["reports"]["translator_coverage_matrix"]["path"] = artifacts["translator_coverage_matrix"]
            payload["milestone_release_report"]["path"] = artifacts["milestone_release_report"]
            payload["command_log"]["path"] = artifacts["command_log"]
            for step in payload["steps"]:
                step["log_path"] = artifacts["command_log"]

            write_json(summary_path, payload)
            write_json(vendored_path, valid_vendored_clang_verification_payload())
            write_valid_competition_smoke_report_artifacts(evidence_governance, coverage_matrix, milestone)

            with self.assertRaisesRegex(
                ValueError,
                "competition_smoke_command_log path must exist",
            ):
                validator.validate_harness_artifact_contracts(
                    artifacts,
                    require_local_artifacts=True,
                    repo_root=REPO_ROOT,
                    environment_profile={
                        "profile_id": "huawei-competition-ubuntu-24.04",
                        "sha256": "a" * 64,
                    },
                    smoke_contract={
                        "proof_class": "local-simulation",
                        "run_id": "smoke-missing-command-log-contract-test",
                    },
                )

    def test_competition_smoke_summary_command_log_requires_sha256(self) -> None:
        payload = valid_competition_smoke_summary_payload()
        payload["command_log"].pop("sha256", None)

        with self.assertRaisesRegex(
            ValueError,
            "competition_smoke_summary.command_log.sha256",
        ):
            validator.validate_competition_smoke_summary_contract(
                payload,
                expected_artifacts=competition_smoke_expected_artifacts(),
                environment_profile={
                    "profile_id": "huawei-competition-ubuntu-24.04",
                    "sha256": "a" * 64,
                },
                entrypoint_proof_class="local-simulation",
                entrypoint_run_id=None,
            )

    def test_competition_smoke_summary_step_log_path_must_match_command_log(self) -> None:
        payload = valid_competition_smoke_summary_payload()
        payload["steps"][0]["log_path"] = "target/other-smoke/logs/commands.jsonl"

        with self.assertRaisesRegex(
            ValueError,
            "competition_smoke_summary step environment-check.log_path must match command_log.path",
        ):
            validator.validate_competition_smoke_summary_contract(
                payload,
                expected_artifacts=competition_smoke_expected_artifacts(),
                environment_profile={
                    "profile_id": "huawei-competition-ubuntu-24.04",
                    "sha256": "a" * 64,
                },
                entrypoint_proof_class="local-simulation",
                entrypoint_run_id=None,
            )

    def test_require_local_artifacts_rejects_command_log_sha256_drift(self) -> None:
        with tempfile.TemporaryDirectory(prefix="judge-entrypoints-test-", dir=REPO_ROOT / "target") as tmp:
            root = Path(tmp)
            summary_path = root / "summary" / "competition-smoke-summary.json"
            vendored_path = root / "summary" / "vendored-clang-verification.json"
            evidence_governance = root / "reports" / "evidence-governance.json"
            coverage_matrix = root / "reports" / "translator-coverage-matrix.json"
            milestone = root / "reports" / "milestone-release-report.json"
            command_log = root / "logs" / "commands.jsonl"

            artifacts = {
                "competition_smoke_summary": repo_relative(summary_path),
                "vendored_clang_verification": repo_relative(vendored_path),
                "evidence_governance_report": repo_relative(evidence_governance),
                "translator_coverage_matrix": repo_relative(coverage_matrix),
                "milestone_release_report": repo_relative(milestone),
                "command_log": repo_relative(command_log),
            }
            payload = valid_competition_smoke_summary_payload()
            payload["run_id"] = "smoke-command-log-sha-drift-test"
            payload["vendored_clang_verification"]["path"] = artifacts["vendored_clang_verification"]
            payload["reports"]["evidence_governance"]["path"] = artifacts["evidence_governance_report"]
            payload["reports"]["translator_coverage_matrix"]["path"] = artifacts["translator_coverage_matrix"]
            payload["milestone_release_report"]["path"] = artifacts["milestone_release_report"]
            payload["command_log"]["path"] = artifacts["command_log"]
            payload["command_log"]["sha256"] = "0" * 64
            for step in payload["steps"]:
                step["log_path"] = artifacts["command_log"]

            write_json(summary_path, payload)
            write_json(vendored_path, valid_vendored_clang_verification_payload())
            write_valid_competition_smoke_report_artifacts(evidence_governance, coverage_matrix, milestone)
            write_valid_command_log(command_log, run_id=payload["run_id"])

            with self.assertRaisesRegex(
                ValueError,
                "competition_smoke_summary.command_log.sha256 must match command_log artifact",
            ):
                validator.validate_harness_artifact_contracts(
                    artifacts,
                    require_local_artifacts=True,
                    repo_root=REPO_ROOT,
                    environment_profile={
                        "profile_id": "huawei-competition-ubuntu-24.04",
                        "sha256": "a" * 64,
                    },
                    smoke_contract={
                        "proof_class": "local-simulation",
                        "run_id": "smoke-command-log-sha-drift-test",
                    },
                )

    def test_require_local_artifacts_rejects_command_log_run_id_drift(self) -> None:
        with tempfile.TemporaryDirectory(prefix="judge-entrypoints-test-", dir=REPO_ROOT / "target") as tmp:
            root = Path(tmp)
            artifacts, payload = write_exact_competition_smoke_fixture(
                root,
                run_id="smoke-command-log-run-binding-test",
            )
            command_log = REPO_ROOT / artifacts["command_log"]
            entries = [json.loads(line) for line in command_log.read_text(encoding="utf-8").splitlines()]
            self.assertTrue(entries)
            entries[0]["run_id"] = "stale-smoke-run"
            entries[0]["canonical"] = True
            command_log.write_text(
                "".join(json.dumps(entry, sort_keys=True) + "\n" for entry in entries),
                encoding="utf-8",
            )
            payload["command_log"]["sha256"] = validator.sha256_file(command_log)
            write_json(REPO_ROOT / artifacts["competition_smoke_summary"], payload)

            with self.assertRaisesRegex(
                ValueError,
                "competition_smoke_command_log line 1 run_id must match smoke summary run_id",
            ):
                validator.validate_harness_artifact_contracts(
                    artifacts,
                    require_local_artifacts=True,
                    repo_root=REPO_ROOT,
                    environment_profile={
                        "profile_id": "huawei-competition-ubuntu-24.04",
                        "sha256": "a" * 64,
                    },
                    smoke_contract={
                        "proof_class": "competition-exact",
                        "run_id": "smoke-command-log-run-binding-test",
                    },
                )

    def test_require_local_artifacts_rejects_noncanonical_command_log_record(self) -> None:
        with tempfile.TemporaryDirectory(prefix="judge-entrypoints-test-", dir=REPO_ROOT / "target") as tmp:
            root = Path(tmp)
            artifacts, payload = write_exact_competition_smoke_fixture(
                root,
                run_id="smoke-command-log-canonical-binding-test",
            )
            command_log = REPO_ROOT / artifacts["command_log"]
            entries = [json.loads(line) for line in command_log.read_text(encoding="utf-8").splitlines()]
            self.assertTrue(entries)
            entries[0]["canonical"] = False
            command_log.write_text(
                "".join(json.dumps(entry, sort_keys=True) + "\n" for entry in entries),
                encoding="utf-8",
            )
            payload["command_log"]["sha256"] = validator.sha256_file(command_log)
            write_json(REPO_ROOT / artifacts["competition_smoke_summary"], payload)

            with self.assertRaisesRegex(
                ValueError,
                "competition_smoke_command_log line 1 canonical must be true",
            ):
                validator.validate_harness_artifact_contracts(
                    artifacts,
                    require_local_artifacts=True,
                    repo_root=REPO_ROOT,
                    environment_profile={
                        "profile_id": "huawei-competition-ubuntu-24.04",
                        "sha256": "a" * 64,
                    },
                    smoke_contract={
                        "proof_class": "competition-exact",
                        "run_id": "smoke-command-log-canonical-binding-test",
                    },
                )

    def test_require_local_artifacts_rejects_command_log_missing_summary_step(self) -> None:
        with tempfile.TemporaryDirectory(prefix="judge-entrypoints-test-", dir=REPO_ROOT / "target") as tmp:
            root = Path(tmp)
            summary_path = root / "summary" / "competition-smoke-summary.json"
            vendored_path = root / "summary" / "vendored-clang-verification.json"
            evidence_governance = root / "reports" / "evidence-governance.json"
            coverage_matrix = root / "reports" / "translator-coverage-matrix.json"
            milestone = root / "reports" / "milestone-release-report.json"
            command_log = root / "logs" / "commands.jsonl"

            artifacts = {
                "competition_smoke_summary": repo_relative(summary_path),
                "vendored_clang_verification": repo_relative(vendored_path),
                "evidence_governance_report": repo_relative(evidence_governance),
                "translator_coverage_matrix": repo_relative(coverage_matrix),
                "milestone_release_report": repo_relative(milestone),
                "command_log": repo_relative(command_log),
            }
            payload = valid_competition_smoke_summary_payload()
            payload["run_id"] = "smoke-command-log-step-coverage-test"
            payload["vendored_clang_verification"]["path"] = artifacts["vendored_clang_verification"]
            payload["reports"]["evidence_governance"]["path"] = artifacts["evidence_governance_report"]
            payload["reports"]["translator_coverage_matrix"]["path"] = artifacts["translator_coverage_matrix"]
            payload["milestone_release_report"]["path"] = artifacts["milestone_release_report"]
            payload["command_log"]["path"] = artifacts["command_log"]
            for step in payload["steps"]:
                step["log_path"] = artifacts["command_log"]

            write_json(summary_path, payload)
            write_json(vendored_path, valid_vendored_clang_verification_payload())
            write_valid_competition_smoke_report_artifacts(evidence_governance, coverage_matrix, milestone)
            command_log.parent.mkdir(parents=True, exist_ok=True)
            command_log.write_text(
                json.dumps(
                    {
                        "step": "environment-check",
                        "command": ["python3", "-B", "validation/tools/run_competition_smoke.py"],
                        "returncode": 1,
                        "stdout": "",
                        "stderr": "",
                        "workdir": ".",
                        "run_id": payload["run_id"],
                        "canonical": True,
                    },
                    sort_keys=True,
                )
                + "\n",
                encoding="utf-8",
            )
            payload["command_log"]["sha256"] = validator.sha256_file(command_log)
            write_json(summary_path, payload)

            with self.assertRaisesRegex(
                ValueError,
                "competition_smoke_command_log missing summary steps",
            ):
                validator.validate_harness_artifact_contracts(
                    artifacts,
                    require_local_artifacts=True,
                    repo_root=REPO_ROOT,
                    environment_profile={
                        "profile_id": "huawei-competition-ubuntu-24.04",
                        "sha256": "a" * 64,
                    },
                    smoke_contract={
                        "proof_class": "local-simulation",
                        "run_id": "smoke-command-log-step-coverage-test",
                    },
                )

    def test_require_local_artifacts_rejects_command_log_returncode_drift_from_summary(self) -> None:
        with tempfile.TemporaryDirectory(prefix="judge-entrypoints-test-", dir=REPO_ROOT / "target") as tmp:
            root = Path(tmp)
            summary_path = root / "summary" / "competition-smoke-summary.json"
            vendored_path = root / "summary" / "vendored-clang-verification.json"
            evidence_governance = root / "reports" / "evidence-governance.json"
            coverage_matrix = root / "reports" / "translator-coverage-matrix.json"
            milestone = root / "reports" / "milestone-release-report.json"
            command_log = root / "logs" / "commands.jsonl"

            artifacts = {
                "competition_smoke_summary": repo_relative(summary_path),
                "vendored_clang_verification": repo_relative(vendored_path),
                "evidence_governance_report": repo_relative(evidence_governance),
                "translator_coverage_matrix": repo_relative(coverage_matrix),
                "milestone_release_report": repo_relative(milestone),
                "command_log": repo_relative(command_log),
            }
            payload = valid_competition_smoke_summary_payload()
            payload["run_id"] = "smoke-command-log-returncode-drift-test"
            payload["vendored_clang_verification"]["path"] = artifacts["vendored_clang_verification"]
            payload["reports"]["evidence_governance"]["path"] = artifacts["evidence_governance_report"]
            payload["reports"]["translator_coverage_matrix"]["path"] = artifacts["translator_coverage_matrix"]
            payload["milestone_release_report"]["path"] = artifacts["milestone_release_report"]
            payload["command_log"]["path"] = artifacts["command_log"]
            for step in payload["steps"]:
                step["log_path"] = artifacts["command_log"]

            write_json(summary_path, payload)
            write_json(vendored_path, valid_vendored_clang_verification_payload())
            write_valid_competition_smoke_report_artifacts(evidence_governance, coverage_matrix, milestone)
            drifted_steps = [dict(step) for step in payload["steps"]]
            for step in drifted_steps:
                if step["step"] == "environment-check":
                    step["returncode"] = 0
            payload["command_log"]["sha256"] = write_valid_command_log(
                command_log,
                drifted_steps,
                run_id=payload["run_id"],
            )
            write_json(summary_path, payload)

            with self.assertRaisesRegex(
                ValueError,
                "competition_smoke_command_log step environment-check returncode must match summary",
            ):
                validator.validate_harness_artifact_contracts(
                    artifacts,
                    require_local_artifacts=True,
                    repo_root=REPO_ROOT,
                    environment_profile={
                        "profile_id": "huawei-competition-ubuntu-24.04",
                        "sha256": "a" * 64,
                    },
                    smoke_contract={
                        "proof_class": "local-simulation",
                        "run_id": "smoke-command-log-returncode-drift-test",
                    },
                )
