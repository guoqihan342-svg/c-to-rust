class _JudgeEntrypointsValidatorTestsPart04:
    def test_require_local_artifacts_rejects_exact_glm_probe_stdout_without_required_model(self) -> None:
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
            payload["proof_class"] = "competition-exact"
            payload["run_id"] = "smoke-exact-glm-command-log-test"
            payload["execution_environment"].update(
                {
                    "competition_exact_host_attested": True,
                    "detected_ci": False,
                    "detected_wsl": False,
                    "kind": "competition-host",
                    "system": "Linux",
                }
            )
            payload["competition_profile_match"].update(
                {
                    "cargo_mirror_config_present": True,
                    "clang_lane_verified": True,
                    "kernel_match": True,
                    "os_name_match": True,
                    "python_version_match": True,
                }
            )
            payload["vendored_clang_verification"]["path"] = artifacts["vendored_clang_verification"]
            payload["reports"]["evidence_governance"]["path"] = artifacts["evidence_governance_report"]
            payload["reports"]["translator_coverage_matrix"]["path"] = artifacts["translator_coverage_matrix"]
            payload["milestone_release_report"]["path"] = artifacts["milestone_release_report"]
            payload["command_log"]["path"] = artifacts["command_log"]
            for step in payload["steps"]:
                step["status"] = "passed"
                step["returncode"] = 0
                step["log_path"] = artifacts["command_log"]
                step.pop("proof_class_effect", None)
            payload["steps"].append(
                {
                    "step": "opencode-glm-model-probe",
                    "status": "passed",
                    "returncode": 0,
                    "log_path": artifacts["command_log"],
                }
            )
            payload["opencode_model_availability"] = {
                "status": "available",
                "required_model": "GLM-5.1",
                "model_listed": True,
                "opencode_command": "opencode",
                "argv": ["opencode", "models"],
                "process_returncode": 0,
                **write_opencode_model_probe_logs(root),
            }

            write_json(summary_path, payload)
            write_json(
                vendored_path,
                {
                    **valid_vendored_clang_verification_payload(),
                    "proof_class": "competition-exact",
                    "clang_required": True,
                },
            )
            write_valid_competition_smoke_report_artifacts(evidence_governance, coverage_matrix, milestone)
            command_log.parent.mkdir(parents=True, exist_ok=True)
            command_log_entries = []
            for step in payload["steps"]:
                name = step["step"]
                if name == "opencode-glm-model-probe":
                    command = ["opencode", "models"]
                    stdout = "zhipu/GLM-5.10\nopencode/not-GLM-5.1\n"
                else:
                    command = valid_competition_smoke_step_command(name)
                    stdout = ""
                command_log_entries.append(
                    json.dumps(
                        {
                            "step": name,
                            "command": command,
                            "returncode": 0,
                            "stdout": stdout,
                            "stderr": "",
                            "workdir": ".",
                            "run_id": payload["run_id"],
                            "canonical": True,
                        },
                        sort_keys=True,
                    )
                )
            command_log.write_text("\n".join(command_log_entries) + "\n", encoding="utf-8")
            payload["command_log"]["sha256"] = validator.sha256_file(command_log)
            write_json(summary_path, payload)

            with self.assertRaisesRegex(
                ValueError,
                "competition_smoke_command_log opencode-glm-model-probe stdout must list GLM-5.1",
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
                        "run_id": "smoke-exact-glm-command-log-test",
                    },
                )

    def test_require_local_artifacts_rejects_exact_glm_probe_missing_hash_bound_logs(self) -> None:
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
            payload["proof_class"] = "competition-exact"
            payload["run_id"] = "smoke-exact-glm-missing-hash-logs-test"
            payload["execution_environment"].update(
                {
                    "competition_exact_host_attested": True,
                    "detected_ci": False,
                    "detected_wsl": False,
                    "kind": "competition-host",
                    "system": "Linux",
                }
            )
            payload["competition_profile_match"].update(
                {
                    "cargo_mirror_config_present": True,
                    "clang_lane_verified": True,
                    "kernel_match": True,
                    "os_name_match": True,
                    "python_version_match": True,
                }
            )
            payload["vendored_clang_verification"]["path"] = artifacts["vendored_clang_verification"]
            payload["reports"]["evidence_governance"]["path"] = artifacts["evidence_governance_report"]
            payload["reports"]["translator_coverage_matrix"]["path"] = artifacts["translator_coverage_matrix"]
            payload["milestone_release_report"]["path"] = artifacts["milestone_release_report"]
            payload["command_log"]["path"] = artifacts["command_log"]
            for step in payload["steps"]:
                step["status"] = "passed"
                step["returncode"] = 0
                step["log_path"] = artifacts["command_log"]
                step.pop("proof_class_effect", None)
            payload["steps"].append(
                {
                    "step": "opencode-glm-model-probe",
                    "status": "passed",
                    "returncode": 0,
                    "log_path": artifacts["command_log"],
                }
            )
            payload["opencode_model_availability"] = {
                "status": "available",
                "required_model": "GLM-5.1",
                "model_listed": True,
                "opencode_command": "opencode",
                "argv": ["opencode", "models"],
                "process_returncode": 0,
            }

            write_json(summary_path, payload)
            write_json(
                vendored_path,
                {
                    **valid_vendored_clang_verification_payload(),
                    "proof_class": "competition-exact",
                    "clang_required": True,
                },
            )
            write_valid_competition_smoke_report_artifacts(evidence_governance, coverage_matrix, milestone)
            command_log.parent.mkdir(parents=True, exist_ok=True)
            command_log.write_text(
                "".join(
                    json.dumps(
                        {
                            "step": step["step"],
                            "command": (
                                ["opencode", "models"]
                                if step["step"] == "opencode-glm-model-probe"
                                else valid_competition_smoke_step_command(step["step"])
                            ),
                            "returncode": 0,
                            "stdout": "provider/GLM-5.1\n" if step["step"] == "opencode-glm-model-probe" else "",
                            "stderr": "",
                            "workdir": ".",
                            "run_id": payload["run_id"],
                            "canonical": True,
                        },
                        sort_keys=True,
                    )
                    + "\n"
                    for step in payload["steps"]
                ),
                encoding="utf-8",
            )
            payload["command_log"]["sha256"] = validator.sha256_file(command_log)
            write_json(summary_path, payload)

            with self.assertRaisesRegex(
                ValueError,
                "competition_smoke_summary.opencode_model_availability.logs",
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
                        "run_id": "smoke-exact-glm-missing-hash-logs-test",
                    },
                )

    def test_require_local_artifacts_rejects_exact_glm_probe_log_sha256_drift(self) -> None:
        with tempfile.TemporaryDirectory(prefix="judge-entrypoints-test-", dir=REPO_ROOT / "target") as tmp:
            root = Path(tmp)
            artifacts, payload = write_exact_competition_smoke_fixture(
                root,
                run_id="smoke-exact-glm-log-sha-drift-test",
            )
            stdout_path = REPO_ROOT / payload["opencode_model_availability"]["logs"]["stdout"]
            stdout_path.write_text("provider/GLM-5.1\ntampered\n", encoding="utf-8", newline="\n")

            with self.assertRaisesRegex(
                ValueError,
                "competition_smoke_summary.opencode_model_availability.logs.stdout sha256 mismatch",
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
                        "run_id": "smoke-exact-glm-log-sha-drift-test",
                    },
                )

    def test_require_local_artifacts_rejects_exact_glm_probe_hash_bound_stdout_without_required_model(self) -> None:
        with tempfile.TemporaryDirectory(prefix="judge-entrypoints-test-", dir=REPO_ROOT / "target") as tmp:
            root = Path(tmp)
            artifacts, _payload = write_exact_competition_smoke_fixture(
                root,
                run_id="smoke-exact-glm-hash-bound-stdout-test",
                availability_stdout="provider/GLM-5.10\nopencode/not-GLM-5.1\nglm-5.1\n",
                command_log_stdout="provider/GLM-5.1\n",
            )

            with self.assertRaisesRegex(
                ValueError,
                "competition_smoke_summary.opencode_model_availability.logs.stdout must list GLM-5.1",
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
                        "run_id": "smoke-exact-glm-hash-bound-stdout-test",
                    },
                )

    def test_require_local_artifacts_rejects_command_log_local_absolute_command(self) -> None:
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
            payload["run_id"] = "smoke-command-log-path-contract-test"
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
                        "step": "core-auto-evidence-validator",
                        "command": ["C:\\Python314\\python.exe", "validation/tools/validator.py"],
                        "returncode": 0,
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
                "competition_smoke_command_log command contains forbidden local absolute path",
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
                        "run_id": "smoke-command-log-path-contract-test",
                    },
                )

    def test_require_local_artifacts_validates_context_and_agent_contracts(self) -> None:
        config = load_default_config()
        config["entrypoints"] = [entrypoint_by_id(config, "before_after_judge_demo")]
        config["test_contract"]["required_entrypoint_ids"] = ["before_after_judge_demo"]
        temp_config = write_temp_config(config)
        temp_dir = temp_config.parent
        out_root = bind_entrypoint_to_out_root(config, temp_config, entry_index=0, out_root=temp_dir / "out")
        context_pack = out_root / "harness" / "context-pack.json"
        agent_index = out_root / "harness" / "agent-index.json"
        resume_manifest = out_root / "harness" / "resume-manifest.json"
        competition_summary = out_root / "summary" / "competition-run-summary.json"
        workflow_metrics = out_root / "summary" / "workflow-metrics.json"
        verified_baseline = out_root / "evidence" / "verified-baseline.json"
        before_after = out_root / "evidence" / "translation-before-after.json"
        ledger = out_root / "state" / "opencode-agent-harness.sqlite3"
        worker_root = out_root / "workers" / "worker-001"
        assignment = out_root / "harness" / "assignments" / "worker-001.json"
        request = out_root / "harness" / "assignments" / "worker-001-request.json"
        summary = worker_root / "summary" / "competition-run-summary.json"
        report = worker_root / "harness" / "run-worker-report.json"

        competition_summary.parent.mkdir(parents=True, exist_ok=True)
        write_competition_run_summary_with_workflow_metrics(
            competition_summary,
            valid_competition_run_summary_payload(run_id="competition-flashdb-before-after-exhibit"),
        )
        for artifact in [assignment, request, summary, report]:
            artifact.parent.mkdir(parents=True, exist_ok=True)
            artifact.write_text("{}\n", encoding="utf-8")
        verified_ref = write_verified_unsafe_baseline_ref(verified_baseline)
        before_after_ref = write_repair_before_after_ref(before_after, verified_ref)

        config["entrypoints"][0]["expected_artifacts"] = {
            "competition_summary": repo_relative(competition_summary),
            "workflow_metrics": repo_relative(workflow_metrics),
            "context_pack": repo_relative(context_pack),
            "agent_index": repo_relative(agent_index),
            "resume_manifest": repo_relative(resume_manifest),
        }
        config["test_contract"]["required_expected_artifacts"] = [
            "competition_summary",
            "workflow_metrics",
            "context_pack",
            "agent_index",
        ]
        write_json(temp_config, config)
        write_json(
            context_pack,
            {
                "report_kind": "context-pack",
                "attempt_evidence_policy": {
                    "accepted_attempt": {
                        "min_attempt_number": 2,
                        "require_hint_id": True,
                    },
                    "baseline_attempt": {
                        "attempt_number": 1,
                        "expected_final_gate": "failed",
                        "root_cause_key": "unsafe_baseline_requires_repair",
                        "verified_unsafe_baseline": verified_ref,
                    },
                    "mode": "baseline_repair_gate",
                    "translation_before_after": before_after_ref,
                },
                "context_management_contract": {
                    "agent_index": repo_relative(agent_index),
                    "chat_output_is_evidence": False,
                    "context_pack": repo_relative(context_pack),
                    "contract_kind": "context-management",
                    "evidence_policy": "on-disk-artifacts-only",
                    "pipeline": [
                        {"stage": "plan", "role": "planner", "evidence": "entrypoints.worker_plan"},
                        {"stage": "translate", "role": "worker", "fanout": True},
                        {"stage": "verify", "role": "verifier", "reduce": "merge"},
                        {"stage": "repair", "role": "repairer", "max_rounds": 5},
                    ],
                    "primary_report": repo_relative(competition_summary),
                    "resume_protocol": {
                        "checkpoint_backend": "sqlite",
                        "ledger_path": repo_relative(ledger),
                        "worker_state_source": "agent-index.agents_by_worker_id",
                    },
                    "schema_version": 1,
                    "semantic_gate": False,
                },
                "entrypoints": {
                    "resume_manifest": repo_relative(resume_manifest),
                },
                "workers": [
                    {
                        "assignment_path": repo_relative(assignment),
                        "function": "demo_unit",
                        "report_path": repo_relative(report),
                        "request_path": repo_relative(request),
                        "slice_id": "demo-unit",
                        "source_commit": "abc123",
                        "source_sha256": "f" * 64,
                        "summary_path": repo_relative(summary),
                        "worker_id": "worker-001",
                        "attempts": [
                            {
                                "attempt": 1,
                                "exit_code": 1,
                                "hint_id": "repair:test:worker-001:unsafe_baseline_requires_repair",
                                "hint_status": "opened",
                                "root_cause_key": "unsafe_baseline_requires_repair",
                                "summary_status": "failed",
                            },
                            {
                                "attempt": 2,
                                "exit_code": 0,
                                "hint_id": "repair:test:worker-001:unsafe_baseline_requires_repair",
                                "hint_status": "revalidated_passed",
                                "retry_of": "repair:test:worker-001:unsafe_baseline_requires_repair",
                                "rollback_evidence": {
                                    "path": repo_relative(report),
                                    "sha256": validator.sha256_file(report),
                                },
                                "summary_status": "passed",
                            },
                        ],
                        "final_decision": {"status": "accepted", "reason": "worker_summary_passed"},
                    }
                ],
            },
        )
        write_json(
            agent_index,
            {
                "report_kind": "agent-index",
                "agent_coordination_contract": {
                    "chat_output_is_evidence": False,
                    "checkpoint_backend": "sqlite",
                    "contract_kind": "agent-coordination",
                    "roles": {
                        "planner": {},
                        "worker": {"isolation": "per-worker out_root"},
                        "repairer": {"round_cap": 5},
                        "verifier": {},
                        "reporter": {},
                    },
                    "schema_version": 1,
                    "semantic_gate": False,
                    "worker_count": 1,
                },
                "agents": [
                    {
                        "assignment_path": repo_relative(assignment),
                        "function": "demo_unit",
                        "report_path": repo_relative(report),
                        "request_path": repo_relative(request),
                        "slice_id": "demo-unit",
                        "source_commit": "abc123",
                        "source_sha256": "f" * 64,
                        "summary_path": repo_relative(summary),
                        "worker_id": "worker-001",
                    }
                ],
                "agents_by_worker_id": {
                    "worker-001": {
                        "assignment_path": repo_relative(assignment),
                        "function": "demo_unit",
                        "isolated_out_root": repo_relative(worker_root),
                        "report_path": repo_relative(report),
                        "request_path": repo_relative(request),
                        "slice_id": "demo-unit",
                        "source_commit": "abc123",
                        "source_sha256": "f" * 64,
                        "summary_path": repo_relative(summary),
                        "worker_id": "worker-001",
                    }
                },
                "reports": {
                    "resume_manifest": {
                        "path": repo_relative(resume_manifest),
                        "report_kind": "resume-manifest",
                        "status": "passed",
                    },
                },
            },
        )
        write_json(
            resume_manifest,
            {
                "schema_version": 1,
                "report_kind": "resume-manifest",
                "run_id": "competition-flashdb-before-after-exhibit",
                "status": "passed",
                "semantic_gate": False,
                "chat_output_is_evidence": False,
                "claim_boundary": {
                    "semantic_gate": False,
                    "chat_output_is_evidence": False,
                    "generated_draft_semantic_pass": False,
                    "translation_coverage_numerator": 0,
                },
                "ledger": {
                    "path": repo_relative(ledger),
                    "checkpoint_backend": "sqlite",
                },
                "context_pack": {
                    "path": repo_relative(context_pack),
                    "sha256": validator.sha256_file(context_pack),
                },
                "agent_index": {
                    "path": repo_relative(agent_index),
                    "sha256": validator.sha256_file(agent_index),
                },
                "resume_entrypoints": [
                    "evaluate --profile",
                    "run-plan --plan",
                    "run-worker --assignment",
                ],
                "workers": [
                    {
                        "worker_id": "worker-001",
                        "assignment_path": repo_relative(assignment),
                        "request_path": repo_relative(request),
                        "summary_path": repo_relative(summary),
                        "report_path": repo_relative(report),
                        "isolated_out_root": repo_relative(worker_root),
                        "replay_commands": resume_replay_commands(
                            ledger=ledger,
                            run_id="competition-flashdb-before-after-exhibit",
                            worker_id="worker-001",
                            assignment=assignment,
                            request=request,
                            summary=summary,
                            report=report,
                            worker_root=worker_root,
                        ),
                    }
                ],
                "worker_count": 1,
                "boundary": "Resume manifest is an index only and not a semantic acceptance gate.",
            },
        )
        write_minimal_context_ledger(
            ledger,
            run_id="competition-flashdb-before-after-exhibit",
            context_pack_path=context_pack,
            context_pack_payload=json.loads(context_pack.read_text(encoding="utf-8")),
            agent_index_path=agent_index,
        )
        write_json(
            summary,
            {
                "final_gate": {
                    "status": "failed",
                    "validator": "baseline_repair_gate",
                },
                "slices": {
                    "attempted": 1,
                    "failed": 1,
                    "semantic_pass": 0,
                },
            },
        )
        with closing(sqlite3.connect(ledger)) as connection:
            connection.execute(
                "update artifacts set sha256=?, status=? where kind='competition-run-summary'",
                (validator.sha256_file(summary), "failed"),
            )
            connection.commit()

        result = validator.validate_config(temp_config, require_local_artifacts=True, repo_root=REPO_ROOT)

        self.assertEqual(result["status"], "passed", result["errors"])
        contracts = result["entrypoints"][0]["harness_contracts"]
        self.assertEqual(contracts["context_pack"]["repair_round_cap"], 5)
        self.assertEqual(contracts["agent_index"]["worker_count"], 1)
        self.assertEqual(contracts["resume_manifest"]["status"], "passed")
        self.assertEqual(contracts["resume_manifest"]["worker_count"], 1)
        self.assertEqual(contracts["context_agent_consistency"]["worker_count"], 1)
        self.assertEqual(contracts["ledger_context_index"]["status"], "passed")
        self.assertEqual(contracts["repair_self_heal"]["checked_workers"], 1)

    def test_repair_self_heal_contract_requires_bound_baseline_verification(self) -> None:
        target_dir = REPO_ROOT / "target"
        target_dir.mkdir(exist_ok=True)
        temp_dir = Path(tempfile.mkdtemp(prefix="repair-self-heal-contract-", dir=target_dir))
        verified_ref = write_verified_unsafe_baseline_ref(temp_dir / "verified-baseline.json")
        other_verified_ref = write_verified_unsafe_baseline_ref(temp_dir / "other-verified-baseline.json")
        before_after_ref = write_repair_before_after_ref(
            temp_dir / "translation-before-after.json",
            verified_ref,
            baseline_verification=other_verified_ref,
        )
        context_payload = valid_repair_self_heal_context_payload(
            verified_ref=verified_ref,
            before_after_ref=before_after_ref,
        )

        with self.assertRaisesRegex(ValueError, "baseline_verification must match.*verified_unsafe_baseline"):
            validator.validate_repair_self_heal_contract(context_payload, repo_root=REPO_ROOT)

    def test_repair_self_heal_contract_requires_measured_unsafe_reduction(self) -> None:
        target_dir = REPO_ROOT / "target"
        target_dir.mkdir(exist_ok=True)
        temp_dir = Path(tempfile.mkdtemp(prefix="repair-self-heal-contract-", dir=target_dir))
        verified_ref = write_verified_unsafe_baseline_ref(temp_dir / "verified-baseline.json")
        before_after_ref = write_repair_before_after_ref(
            temp_dir / "translation-before-after.json",
            verified_ref,
            unsafe_status="not_measured",
            reduced_by=None,
        )
        context_payload = valid_repair_self_heal_context_payload(
            verified_ref=verified_ref,
            before_after_ref=before_after_ref,
        )

        with self.assertRaisesRegex(ValueError, "translation_before_after.unsafe_reduction.status must be measured"):
            validator.validate_repair_self_heal_contract(context_payload, repo_root=REPO_ROOT)

    def test_repair_self_heal_contract_requires_positive_unsafe_reduction(self) -> None:
        target_dir = REPO_ROOT / "target"
        target_dir.mkdir(exist_ok=True)
        temp_dir = Path(tempfile.mkdtemp(prefix="repair-self-heal-contract-", dir=target_dir))
        verified_ref = write_verified_unsafe_baseline_ref(temp_dir / "verified-baseline.json")
        before_after_ref = write_repair_before_after_ref(
            temp_dir / "translation-before-after.json",
            verified_ref,
            reduced_by=0,
        )
        context_payload = valid_repair_self_heal_context_payload(
            verified_ref=verified_ref,
            before_after_ref=before_after_ref,
        )

        with self.assertRaisesRegex(ValueError, "translation_before_after.unsafe_reduction.reduced_by must be > 0"):
            validator.validate_repair_self_heal_contract(context_payload, repo_root=REPO_ROOT)

    def test_repair_self_heal_contract_requires_revalidated_retry_hint_status(self) -> None:
        target_dir = REPO_ROOT / "target"
        target_dir.mkdir(exist_ok=True)
        temp_dir = Path(tempfile.mkdtemp(prefix="repair-self-heal-contract-", dir=target_dir))
        verified_ref = write_verified_unsafe_baseline_ref(temp_dir / "verified-baseline.json")
        before_after_ref = write_repair_before_after_ref(temp_dir / "translation-before-after.json", verified_ref)
        context_payload = valid_repair_self_heal_context_payload(
            verified_ref=verified_ref,
            before_after_ref=before_after_ref,
        )
        retry_attempt_from_repair_context(context_payload)["hint_status"] = "opened"

        with self.assertRaisesRegex(ValueError, "accepted retry hint_status must be revalidated_passed"):
            validator.validate_repair_self_heal_contract(context_payload, repo_root=REPO_ROOT)

    def test_repair_self_heal_contract_rejects_rollback_evidence_sha_mismatch(self) -> None:
        target_dir = REPO_ROOT / "target"
        target_dir.mkdir(exist_ok=True)
        temp_dir = Path(tempfile.mkdtemp(prefix="repair-self-heal-contract-", dir=target_dir))
        verified_ref = write_verified_unsafe_baseline_ref(temp_dir / "verified-baseline.json")
        before_after_ref = write_repair_before_after_ref(temp_dir / "translation-before-after.json", verified_ref)
        rollback = temp_dir / "rollback.json"
        write_json(rollback, {"rollback": "before retry"})
        context_payload = valid_repair_self_heal_context_payload(
            verified_ref=verified_ref,
            before_after_ref=before_after_ref,
        )
        retry_attempt_from_repair_context(context_payload)["rollback_evidence"] = {
            "path": repo_relative(rollback),
            "sha256": "0" * 64,
        }

        with self.assertRaisesRegex(ValueError, "rollback_evidence.sha256 does not match artifact"):
            validator.validate_repair_self_heal_contract(context_payload, repo_root=REPO_ROOT)

    def test_opencode_safety_transform_attempt_contract_accepts_per_round_patch_delta_and_rollback(self) -> None:
        target_dir = REPO_ROOT / "target"
        target_dir.mkdir(exist_ok=True)
        temp_dir = Path(tempfile.mkdtemp(prefix="opencode-safety-attempt-", dir=target_dir))
        attempt_ref = write_opencode_safety_transform_attempt_ref(
            temp_dir / "opencode-safety-transform-attempt-2.json"
        )

        result = validator.validate_opencode_safety_transform_attempt_contract(attempt_ref, repo_root=REPO_ROOT)

        self.assertEqual(result["status"], "passed")
        self.assertEqual(result["unit_count"], 1)
        self.assertEqual(result["round_count"], 1)
        self.assertEqual(result["repair_round_cap"], 5)
        self.assertFalse(result["semantic_gate"])
        self.assertEqual(result["translation_coverage_numerator"], 0)

    def test_opencode_safety_transform_attempt_rejects_retry_hint_without_bound_rollback_ids(self) -> None:
        target_dir = REPO_ROOT / "target"
        target_dir.mkdir(exist_ok=True)
        temp_dir = Path(tempfile.mkdtemp(prefix="opencode-safety-attempt-", dir=target_dir))
        attempt_ref = write_opencode_safety_transform_attempt_ref(
            temp_dir / "opencode-safety-transform-attempt-2.json"
        )
        attempt_path = REPO_ROOT / attempt_ref["path"]
        payload = json.loads(attempt_path.read_text(encoding="utf-8"))
        payload["safety_transform_units"][0]["accepted_retry_hint"].pop("rollback_ids")
        write_json(attempt_path, payload)
        attempt_ref["sha256"] = validator.sha256_file(attempt_path)

        with self.assertRaisesRegex(ValueError, r"accepted_retry_hint\.rollback_ids"):
            validator.validate_opencode_safety_transform_attempt_contract(attempt_ref, repo_root=REPO_ROOT)

    def test_opencode_safety_transform_attempt_contract_rejects_shallow_contract_without_session_evidence(self) -> None:
        target_dir = REPO_ROOT / "target"
        target_dir.mkdir(exist_ok=True)
        temp_dir = Path(tempfile.mkdtemp(prefix="opencode-safety-attempt-", dir=target_dir))
        attempt_ref = write_opencode_safety_transform_attempt_ref(
            temp_dir / "opencode-safety-transform-attempt-2.json"
        )
        attempt_path = REPO_ROOT / attempt_ref["path"]
        payload = json.loads(attempt_path.read_text(encoding="utf-8"))
        payload.pop("opencode_session_evidence")
        write_json(attempt_path, payload)
        attempt_ref["sha256"] = validator.sha256_file(attempt_path)

        with self.assertRaisesRegex(ValueError, "opencode_safety_transform_attempt.*opencode_session_evidence"):
            validator.validate_opencode_safety_transform_attempt_contract(attempt_ref, repo_root=REPO_ROOT)

    def test_opencode_safety_transform_attempt_rejects_failed_session_evidence_contract(self) -> None:
        cases = [
            ("nonzero_returncode", {"process_returncode": 1}, "process_returncode must be 0"),
            ("unparsed_session", {"parsed": False}, "parsed must be true"),
            ("non_jsonl_format", {"format": "text"}, "format must be jsonl"),
        ]
        for case_name, updates, expected_error in cases:
            with self.subTest(case=case_name):
                target_dir = REPO_ROOT / "target"
                target_dir.mkdir(exist_ok=True)
                temp_dir = Path(tempfile.mkdtemp(prefix="opencode-safety-attempt-session-contract-", dir=target_dir))
                attempt_ref = write_opencode_safety_transform_attempt_ref(
                    temp_dir / "opencode-safety-transform-attempt-2.json"
                )
                attempt_path = REPO_ROOT / attempt_ref["path"]
                payload = json.loads(attempt_path.read_text(encoding="utf-8"))
                session_path = REPO_ROOT / payload["opencode_session_evidence"]["path"]
                session_payload = json.loads(session_path.read_text(encoding="utf-8"))
                session_payload.update(updates)
                write_json(session_path, session_payload)
                payload["opencode_session_evidence"]["sha256"] = validator.sha256_file(session_path)
                write_json(attempt_path, payload)
                attempt_ref["sha256"] = validator.sha256_file(attempt_path)

                with self.assertRaisesRegex(
                    ValueError,
                    rf"opencode_safety_transform_attempt\.opencode_session_evidence\.{expected_error}",
                ):
                    validator.validate_opencode_safety_transform_attempt_contract(attempt_ref, repo_root=REPO_ROOT)

    def test_opencode_safety_transform_attempt_contract_requires_glm_51_handoff(self) -> None:
        target_dir = REPO_ROOT / "target"
        target_dir.mkdir(exist_ok=True)
        temp_dir = Path(tempfile.mkdtemp(prefix="opencode-safety-attempt-", dir=target_dir))
        attempt_ref = write_opencode_safety_transform_attempt_ref(
            temp_dir / "opencode-safety-transform-attempt-2.json"
        )
        attempt_path = REPO_ROOT / attempt_ref["path"]
        payload = json.loads(attempt_path.read_text(encoding="utf-8"))
        handoff_path = REPO_ROOT / payload["handoff_contract"]["path"]
        handoff_payload = json.loads(handoff_path.read_text(encoding="utf-8"))
        handoff_payload["launch_policy"]["opencode_model"] = "not-GLM-5.1"
        handoff_payload["launch_policy_sha256"] = opencode_launch_policy_sha256(handoff_payload["launch_policy"])
        write_json(handoff_path, handoff_payload)
        payload["handoff_contract"]["sha256"] = validator.sha256_file(handoff_path)
        write_json(attempt_path, payload)
        attempt_ref["sha256"] = validator.sha256_file(attempt_path)

        with self.assertRaisesRegex(ValueError, "opencode_model must be GLM-5.1"):
            validator.validate_opencode_safety_transform_attempt_contract(attempt_ref, repo_root=REPO_ROOT)

    def test_opencode_safety_transform_attempt_contract_requires_max_handoff_variant(self) -> None:
        target_dir = REPO_ROOT / "target"
        target_dir.mkdir(exist_ok=True)
        temp_dir = Path(tempfile.mkdtemp(prefix="opencode-safety-attempt-", dir=target_dir))
        attempt_ref = write_opencode_safety_transform_attempt_ref(
            temp_dir / "opencode-safety-transform-attempt-2.json"
        )
        attempt_path = REPO_ROOT / attempt_ref["path"]
        payload = json.loads(attempt_path.read_text(encoding="utf-8"))
        handoff_path = REPO_ROOT / payload["handoff_contract"]["path"]
        handoff_payload = json.loads(handoff_path.read_text(encoding="utf-8"))
        handoff_payload["launch_policy"]["opencode_variant"] = "lite"
        handoff_payload["launch_policy_sha256"] = opencode_launch_policy_sha256(handoff_payload["launch_policy"])
        variant_index = handoff_payload["opencode_argv"].index("--variant") + 1
        handoff_payload["opencode_argv"][variant_index] = "lite"
        handoff_payload["opencode_command_line"] = shlex.join(handoff_payload["opencode_argv"])
        write_json(handoff_path, handoff_payload)
        payload["handoff_contract"]["sha256"] = validator.sha256_file(handoff_path)
        write_json(attempt_path, payload)
        attempt_ref["sha256"] = validator.sha256_file(attempt_path)

        with self.assertRaisesRegex(ValueError, "opencode_variant must be max"):
            validator.validate_opencode_safety_transform_attempt_contract(attempt_ref, repo_root=REPO_ROOT)

    def test_opencode_safety_transform_attempt_rejects_summary_final_gate_drift(self) -> None:
        target_dir = REPO_ROOT / "target"
        target_dir.mkdir(exist_ok=True)
        temp_dir = Path(tempfile.mkdtemp(prefix="opencode-safety-attempt-", dir=target_dir))
        attempt_ref = write_opencode_safety_transform_attempt_ref(
            temp_dir / "opencode-safety-transform-attempt-2.json"
        )
        attempt_path = REPO_ROOT / attempt_ref["path"]
        payload = json.loads(attempt_path.read_text(encoding="utf-8"))
        summary_path = REPO_ROOT / payload["summary"]["path"]
        summary_payload = json.loads(summary_path.read_text(encoding="utf-8"))
        summary_payload["final_gate"]["status"] = "failed"
        write_json(summary_path, summary_payload)
        payload["summary"]["sha256"] = validator.sha256_file(summary_path)
        write_json(attempt_path, payload)
        attempt_ref["sha256"] = validator.sha256_file(attempt_path)

        with self.assertRaisesRegex(ValueError, "summary.final_gate_status must match worker summary final_gate.status"):
            validator.validate_opencode_safety_transform_attempt_contract(attempt_ref, repo_root=REPO_ROOT)

    def test_opencode_safety_transform_attempt_rejects_summary_run_id_drift(self) -> None:
        target_dir = REPO_ROOT / "target"
        target_dir.mkdir(exist_ok=True)
        temp_dir = Path(tempfile.mkdtemp(prefix="opencode-safety-attempt-", dir=target_dir))
        attempt_ref = write_opencode_safety_transform_attempt_ref(
            temp_dir / "opencode-safety-transform-attempt-2.json"
        )
        attempt_path = REPO_ROOT / attempt_ref["path"]
        payload = json.loads(attempt_path.read_text(encoding="utf-8"))
        summary_path = REPO_ROOT / payload["summary"]["path"]
        summary_payload = json.loads(summary_path.read_text(encoding="utf-8"))
        summary_payload["run_id"] = "drifted-run"

        workflow_metrics_path = REPO_ROOT / summary_payload["workflow_metrics"]["path"]
        workflow_metrics_payload = json.loads(workflow_metrics_path.read_text(encoding="utf-8"))
        workflow_metrics_payload["run_id"] = "drifted-run"
        write_json(workflow_metrics_path, workflow_metrics_payload)
        summary_payload["workflow_metrics"]["sha256"] = validator.sha256_file(workflow_metrics_path)

        command_log_path = REPO_ROOT / summary_payload["command_log"]["path"]
        command_log_entries = [
            json.loads(line) for line in command_log_path.read_text(encoding="utf-8").splitlines() if line
        ]
        for entry in command_log_entries:
            entry["run_id"] = "drifted-run"
        command_log_path.write_text(
            "\n".join(json.dumps(entry, sort_keys=True) for entry in command_log_entries) + "\n",
            encoding="utf-8",
        )
        summary_payload["command_log"]["sha256"] = validator.sha256_file(command_log_path)

        write_json(summary_path, summary_payload)
        payload["summary"]["sha256"] = validator.sha256_file(summary_path)
        write_json(attempt_path, payload)
        attempt_ref["sha256"] = validator.sha256_file(attempt_path)

        with self.assertRaisesRegex(ValueError, "summary.run_id must match run_id"):
            validator.validate_opencode_safety_transform_attempt_contract(attempt_ref, repo_root=REPO_ROOT)
