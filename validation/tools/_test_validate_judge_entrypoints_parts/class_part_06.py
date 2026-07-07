class _JudgeEntrypointsValidatorTestsPart06:
    def test_context_agent_index_rejects_agents_by_worker_id_value_worker_id_drift(self) -> None:
        common_fields = {
            "worker_id": "worker-001",
            "assignment_path": "target/out/harness/assignments/worker-001.json",
            "request_path": "target/out/harness/assignments/worker-001-request.json",
            "summary_path": "target/out/workers/worker-001/summary/competition-run-summary.json",
            "report_path": "target/out/workers/worker-001/harness/run-worker-report.json",
            "isolated_out_root": "target/out/workers/worker-001",
            "slice_id": "demo-unit",
            "function": "demo_unit",
            "source_commit": "abc123",
            "source_sha256": "f" * 64,
        }
        context_payload = {"workers": [common_fields]}
        agent_payload = {
            "agents": [common_fields],
            "agents_by_worker_id": {
                "worker-001": {
                    **common_fields,
                    "worker_id": "stale-worker-999",
                }
            },
        }

        with self.assertRaisesRegex(
            ValueError,
            "agents_by_worker_id.worker-001.worker_id must match map key",
        ):
            validator.validate_context_agent_index_consistency(context_payload, agent_payload)

    def test_context_agent_index_consistency_rejects_context_out_root_drift(self) -> None:
        canonical_root = "target/out/workers/worker-001"
        stale_context_root = "target/out/stale-workers/worker-001"
        common_fields = {
            "worker_id": "worker-001",
            "assignment_path": "target/out/harness/assignments/worker-001.json",
            "request_path": "target/out/harness/assignments/worker-001-request.json",
            "summary_path": f"{canonical_root}/summary/competition-run-summary.json",
            "report_path": f"{canonical_root}/harness/run-worker-report.json",
            "slice_id": "demo-unit",
            "function": "demo_unit",
            "source_commit": "abc123",
            "source_sha256": "f" * 64,
        }
        context_payload = {"workers": [{**common_fields, "out_root": stale_context_root}]}
        agent_payload = {
            "agents": [{**common_fields, "isolated_out_root": canonical_root}],
            "agents_by_worker_id": {
                "worker-001": {**common_fields, "isolated_out_root": canonical_root}
            },
        }

        with self.assertRaisesRegex(
            ValueError,
            "worker worker-001 out_root must match isolated_out_root",
        ):
            validator.validate_context_agent_index_consistency(context_payload, agent_payload)

    def test_resume_manifest_rejects_failed_verified_unsafe_baseline_ref(self) -> None:
        target_dir = REPO_ROOT / "target"
        target_dir.mkdir(exist_ok=True)
        temp_dir = Path(tempfile.mkdtemp(prefix="resume-manifest-verified-baseline-", dir=target_dir))
        out_root = temp_dir / "out"
        context_pack = out_root / "harness" / "context-pack.json"
        agent_index = out_root / "harness" / "agent-index.json"
        resume_manifest = out_root / "harness" / "resume-manifest.json"
        ledger = out_root / "state" / "opencode-agent-harness.sqlite3"
        ledger.parent.mkdir(parents=True, exist_ok=True)
        ledger.write_text("{}\n", encoding="utf-8")
        verified_ref = write_verified_unsafe_baseline_ref(
            out_root / "evidence" / "verified-baseline.json",
            status="failed",
        )
        policy = {"baseline_attempt": {"verified_unsafe_baseline": verified_ref}}
        context_payload = {
            "entrypoints": {
                "resume_manifest": repo_relative(resume_manifest),
                "verified_unsafe_baseline": verified_ref["path"],
            },
            "attempt_evidence_policy": policy,
        }
        agent_payload = {
            "reports": {
                "resume_manifest": {"path": repo_relative(resume_manifest)},
                "verified_unsafe_baseline": verified_ref,
            },
            "attempt_evidence_policy": policy,
        }
        write_json(context_pack, context_payload)
        write_json(agent_index, agent_payload)
        payload = {
            "schema_version": 1,
            "report_kind": "resume-manifest",
            "run_id": "resume-verified-baseline",
            "status": "failed",
            "semantic_gate": False,
            "chat_output_is_evidence": False,
            "claim_boundary": {
                "semantic_gate": False,
                "chat_output_is_evidence": False,
                "generated_draft_semantic_pass": False,
                "translation_coverage_numerator": 0,
            },
            "ledger": {"path": repo_relative(ledger), "checkpoint_backend": "sqlite"},
            "context_pack": {"path": repo_relative(context_pack), "sha256": validator.sha256_file(context_pack)},
            "agent_index": {"path": repo_relative(agent_index), "sha256": validator.sha256_file(agent_index)},
            "entrypoints": {
                "resume_manifest": repo_relative(resume_manifest),
                "verified_unsafe_baseline": verified_ref["path"],
            },
            "attempt_evidence_policy": policy,
            "verified_unsafe_baseline": verified_ref,
            "resume_entrypoints": ["evaluate --profile", "run-plan --plan", "run-worker --assignment"],
            "workers": [],
            "worker_count": 0,
        }

        with self.assertRaisesRegex(ValueError, "resume_manifest.verified_unsafe_baseline.status must be passed"):
            validator.validate_resume_manifest_contract(
                payload,
                path_text=repo_relative(resume_manifest),
                expected_artifacts={
                    "context_pack": repo_relative(context_pack),
                    "agent_index": repo_relative(agent_index),
                    "resume_manifest": repo_relative(resume_manifest),
                    "verified_unsafe_baseline": verified_ref["path"],
                },
                context_payload=context_payload,
                agent_payload=agent_payload,
                repo_root=REPO_ROOT,
            )

    def test_resume_manifest_verified_unsafe_baseline_must_match_context_and_agent_policy(self) -> None:
        target_dir = REPO_ROOT / "target"
        target_dir.mkdir(exist_ok=True)
        temp_dir = Path(tempfile.mkdtemp(prefix="resume-manifest-verified-baseline-drift-", dir=target_dir))
        out_root = temp_dir / "out"
        context_pack = out_root / "harness" / "context-pack.json"
        agent_index = out_root / "harness" / "agent-index.json"
        resume_manifest = out_root / "harness" / "resume-manifest.json"
        ledger = out_root / "state" / "opencode-agent-harness.sqlite3"
        ledger.parent.mkdir(parents=True, exist_ok=True)
        ledger.write_text("{}\n", encoding="utf-8")
        verified_ref = write_verified_unsafe_baseline_ref(out_root / "evidence" / "verified-baseline.json")
        drifted_ref = dict(verified_ref)
        drifted_ref["sha256"] = "0" * 64
        context_payload = {
            "entrypoints": {
                "resume_manifest": repo_relative(resume_manifest),
                "verified_unsafe_baseline": verified_ref["path"],
            },
            "attempt_evidence_policy": {"baseline_attempt": {"verified_unsafe_baseline": verified_ref}},
        }
        agent_payload = {
            "reports": {
                "resume_manifest": {"path": repo_relative(resume_manifest)},
                "verified_unsafe_baseline": drifted_ref,
            },
            "attempt_evidence_policy": {"baseline_attempt": {"verified_unsafe_baseline": drifted_ref}},
        }
        write_json(context_pack, context_payload)
        write_json(agent_index, agent_payload)
        payload = {
            "schema_version": 1,
            "report_kind": "resume-manifest",
            "run_id": "resume-verified-baseline-drift",
            "status": "passed",
            "semantic_gate": False,
            "chat_output_is_evidence": False,
            "claim_boundary": {
                "semantic_gate": False,
                "chat_output_is_evidence": False,
                "generated_draft_semantic_pass": False,
                "translation_coverage_numerator": 0,
            },
            "ledger": {"path": repo_relative(ledger), "checkpoint_backend": "sqlite"},
            "context_pack": {"path": repo_relative(context_pack), "sha256": validator.sha256_file(context_pack)},
            "agent_index": {"path": repo_relative(agent_index), "sha256": validator.sha256_file(agent_index)},
            "entrypoints": {
                "resume_manifest": repo_relative(resume_manifest),
                "verified_unsafe_baseline": verified_ref["path"],
            },
            "attempt_evidence_policy": {"baseline_attempt": {"verified_unsafe_baseline": verified_ref}},
            "verified_unsafe_baseline": verified_ref,
            "resume_entrypoints": ["evaluate --profile", "run-plan --plan", "run-worker --assignment"],
            "workers": [],
            "worker_count": 0,
        }

        with self.assertRaisesRegex(
            ValueError,
            "verified_unsafe_baseline must match across resume_manifest, context_pack, and agent_index",
        ):
            validator.validate_resume_manifest_contract(
                payload,
                path_text=repo_relative(resume_manifest),
                expected_artifacts={
                    "context_pack": repo_relative(context_pack),
                    "agent_index": repo_relative(agent_index),
                    "resume_manifest": repo_relative(resume_manifest),
                    "verified_unsafe_baseline": verified_ref["path"],
                },
                context_payload=context_payload,
                agent_payload=agent_payload,
                repo_root=REPO_ROOT,
            )

    def test_resume_manifest_worker_replay_commands_are_required(self) -> None:
        target_dir = REPO_ROOT / "target"
        target_dir.mkdir(exist_ok=True)
        temp_dir = Path(tempfile.mkdtemp(prefix="resume-manifest-replay-missing-", dir=target_dir))
        out_root = temp_dir / "out"
        context_pack = out_root / "harness" / "context-pack.json"
        agent_index = out_root / "harness" / "agent-index.json"
        resume_manifest = out_root / "harness" / "resume-manifest.json"
        ledger = out_root / "state" / "opencode-agent-harness.sqlite3"
        worker_root = out_root / "workers" / "worker-001"
        assignment = out_root / "harness" / "assignments" / "worker-001.json"
        request = out_root / "harness" / "assignments" / "worker-001-request.json"
        summary = worker_root / "summary" / "competition-run-summary.json"
        report = worker_root / "harness" / "run-worker-report.json"
        for path in [ledger, assignment, request, summary, report]:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text("{}\n", encoding="utf-8")
        worker_fields = {
            "worker_id": "worker-001",
            "assignment_path": repo_relative(assignment),
            "request_path": repo_relative(request),
            "summary_path": repo_relative(summary),
            "report_path": repo_relative(report),
            "slice_id": "demo-unit",
            "function": "demo_unit",
            "source_commit": "abc123",
            "source_sha256": "f" * 64,
        }
        context_payload = {
            "entrypoints": {"resume_manifest": repo_relative(resume_manifest)},
            "workers": [worker_fields],
        }
        agent_payload = {
            "reports": {"resume_manifest": {"path": repo_relative(resume_manifest)}},
            "agents": [worker_fields],
            "agents_by_worker_id": {
                "worker-001": {
                    **worker_fields,
                    "isolated_out_root": repo_relative(worker_root),
                },
            },
        }
        write_json(context_pack, context_payload)
        write_json(agent_index, agent_payload)
        payload = {
            "schema_version": 1,
            "report_kind": "resume-manifest",
            "run_id": "resume-replay-missing",
            "status": "passed",
            "semantic_gate": False,
            "chat_output_is_evidence": False,
            "claim_boundary": {
                "semantic_gate": False,
                "chat_output_is_evidence": False,
                "generated_draft_semantic_pass": False,
                "translation_coverage_numerator": 0,
            },
            "ledger": {"path": repo_relative(ledger), "checkpoint_backend": "sqlite"},
            "context_pack": {"path": repo_relative(context_pack), "sha256": validator.sha256_file(context_pack)},
            "agent_index": {"path": repo_relative(agent_index), "sha256": validator.sha256_file(agent_index)},
            "resume_entrypoints": ["evaluate --profile", "run-plan --plan", "run-worker --assignment"],
            "workers": [
                {
                    **worker_fields,
                    "isolated_out_root": repo_relative(worker_root),
                }
            ],
            "worker_count": 1,
        }

        with self.assertRaisesRegex(
            ValueError,
            r"resume_manifest\.workers\[0\]\.replay_commands must be an object",
        ):
            validator.validate_resume_manifest_contract(
                payload,
                path_text=repo_relative(resume_manifest),
                expected_artifacts={
                    "context_pack": repo_relative(context_pack),
                    "agent_index": repo_relative(agent_index),
                    "resume_manifest": repo_relative(resume_manifest),
                },
                context_payload=context_payload,
                agent_payload=agent_payload,
                repo_root=REPO_ROOT,
            )

    def test_resume_manifest_retry_replay_hint_id_must_match_open_worker_hint(self) -> None:
        target_dir = REPO_ROOT / "target"
        target_dir.mkdir(exist_ok=True)
        temp_dir = Path(tempfile.mkdtemp(prefix="resume-manifest-retry-hint-", dir=target_dir))
        out_root = temp_dir / "out"
        context_pack = out_root / "harness" / "context-pack.json"
        agent_index = out_root / "harness" / "agent-index.json"
        resume_manifest = out_root / "harness" / "resume-manifest.json"
        ledger = out_root / "state" / "opencode-agent-harness.sqlite3"
        worker_root = out_root / "workers" / "worker-001"
        assignment = out_root / "harness" / "assignments" / "worker-001.json"
        request = out_root / "harness" / "assignments" / "worker-001-request.json"
        summary = worker_root / "summary" / "competition-run-summary.json"
        report = worker_root / "harness" / "run-worker-report.json"
        for path in [ledger, assignment, request, summary, report]:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text("{}\n", encoding="utf-8")
        worker_fields = {
            "worker_id": "worker-001",
            "assignment_path": repo_relative(assignment),
            "request_path": repo_relative(request),
            "summary_path": repo_relative(summary),
            "report_path": repo_relative(report),
            "isolated_out_root": repo_relative(worker_root),
            "slice_id": "demo-unit",
            "function": "demo_unit",
            "source_commit": "abc123",
            "source_sha256": "f" * 64,
        }
        context_payload = {
            "entrypoints": {"resume_manifest": repo_relative(resume_manifest)},
            "workers": [worker_fields],
        }
        agent_payload = {
            "reports": {"resume_manifest": {"path": repo_relative(resume_manifest)}},
            "agents": [worker_fields],
            "agents_by_worker_id": {"worker-001": worker_fields},
        }
        write_json(context_pack, context_payload)
        write_json(agent_index, agent_payload)
        run_id = "resume-retry-hint-binding"
        expected_hint = f"repair:{run_id}:worker-001:process_timeout"
        stale_hint = f"repair:{run_id}:worker-999:process_timeout"
        payload = {
            "schema_version": 1,
            "report_kind": "resume-manifest",
            "run_id": run_id,
            "status": "passed",
            "semantic_gate": False,
            "chat_output_is_evidence": False,
            "claim_boundary": {
                "semantic_gate": False,
                "chat_output_is_evidence": False,
                "generated_draft_semantic_pass": False,
                "translation_coverage_numerator": 0,
            },
            "ledger": {"path": repo_relative(ledger), "checkpoint_backend": "sqlite"},
            "context_pack": {"path": repo_relative(context_pack), "sha256": validator.sha256_file(context_pack)},
            "agent_index": {"path": repo_relative(agent_index), "sha256": validator.sha256_file(agent_index)},
            "resume_entrypoints": ["evaluate --profile", "run-plan --plan", "run-worker --assignment"],
            "repair_hints": {
                "source": "sqlite repair_hints",
                "open_count": 1,
                "hints": [
                    {
                        "hint_id": expected_hint,
                        "status": "open",
                        "worker_id": "worker-001",
                    }
                ],
            },
            "workers": [
                {
                    **worker_fields,
                    "replay_commands": resume_replay_commands(
                        ledger=ledger,
                        run_id=run_id,
                        worker_id="worker-001",
                        assignment=assignment,
                        request=request,
                        summary=summary,
                        report=report,
                        worker_root=worker_root,
                        retry_hint_id=stale_hint,
                    ),
                }
            ],
            "worker_count": 1,
        }

        with self.assertRaisesRegex(ValueError, "--hint-id must match an open repair_hints entry for worker"):
            validator.validate_resume_manifest_contract(
                payload,
                path_text=repo_relative(resume_manifest),
                expected_artifacts={
                    "context_pack": repo_relative(context_pack),
                    "agent_index": repo_relative(agent_index),
                    "resume_manifest": repo_relative(resume_manifest),
                },
                context_payload=context_payload,
                agent_payload=agent_payload,
                repo_root=REPO_ROOT,
            )

    def test_resume_manifest_opencode_replay_rejects_shallow_preflight_binding(self) -> None:
        target_dir = REPO_ROOT / "target"
        target_dir.mkdir(exist_ok=True)
        temp_dir = Path(tempfile.mkdtemp(prefix="resume-manifest-opencode-preflight-", dir=target_dir))
        out_root = temp_dir / "out"
        ledger = out_root / "state" / "opencode-agent-harness.sqlite3"
        preflight = out_root / "harness" / "opencode-preflight-report.json"
        assignment = out_root / "harness" / "assignments" / "worker-001.json"
        request = out_root / "harness" / "assignments" / "worker-001-request.json"
        summary = out_root / "workers" / "worker-001" / "summary" / "competition-run-summary.json"
        report = out_root / "workers" / "worker-001" / "harness" / "run-worker-report.json"
        runtime_env = opencode_runtime_env_contract(out_root, scope="preflight")
        preflight_binding = {
            "path": repo_relative(preflight),
            "sha256": "a" * 64,
            "status": "failed",
            "contract_status": "executed",
            "launch_policy": {
                "opencode_command": "opencode",
                "opencode_model": "GLM-5.1",
                "opencode_agent": "c2rust-migrator",
                "opencode_variant": "max",
                "opencode_skip_permissions": True,
            },
            "opencode_runtime_env": runtime_env,
            "opencode_model_availability": {
                "status": "available",
                "opencode_command": "opencode",
                "required_model": "GLM-5.1",
                "process_returncode": 0,
                "model_listed": True,
            },
        }
        worker = {
            "worker_id": "worker-001",
            "assignment_path": repo_relative(assignment),
            "request_path": repo_relative(request),
            "summary_path": repo_relative(summary),
            "report_path": repo_relative(report),
            "isolated_out_root": repo_relative(out_root / "workers" / "worker-001"),
            "opencode_preflight_report": preflight_binding,
        }
        argv = [
            "python3",
            "-B",
            "-m",
            "validation.tools.opencode_agent_harness",
            "run-worker",
            "--db",
            repo_relative(ledger),
            "--run-id",
            "run-resume",
            "--worker-id",
            "worker-001",
            "--mode",
            "opencode",
            "--opencode-model",
            "GLM-5.1",
            "--opencode-agent",
            "c2rust-migrator",
            "--opencode-variant",
            "max",
            "--opencode-preflight-report",
            repo_relative(preflight),
        ]
        command_payload = {
            "argv": argv,
            "command": shlex.join(argv),
            "assignment_path": repo_relative(assignment),
            "request_path": repo_relative(request),
            "summary_path": repo_relative(summary),
            "report_path": repo_relative(report),
            "out_root": repo_relative(out_root / "workers" / "worker-001"),
            "replay_safety": {
                "status": "ready",
                "reason": "opencode_preflight_contract_bound",
            },
        }

        with self.assertRaisesRegex(ValueError, "opencode_preflight_report.status must be passed"):
            validator.validate_resume_manifest_replay_command(
                command_payload,
                label="resume_manifest.workers[0].replay_commands.run_worker",
                expected_subcommand="run-worker",
                worker=worker,
                worker_id="worker-001",
                run_id="run-resume",
                ledger_path=repo_relative(ledger),
                require_hint=False,
            )

    def test_resume_manifest_opencode_replay_rejects_preflight_sha_drift(self) -> None:
        target_dir = REPO_ROOT / "target"
        target_dir.mkdir(exist_ok=True)
        temp_dir = Path(tempfile.mkdtemp(prefix="resume-manifest-opencode-preflight-sha-", dir=target_dir))
        out_root = temp_dir / "out"
        ledger = out_root / "state" / "opencode-agent-harness.sqlite3"
        preflight = out_root / "harness" / "opencode-preflight-report.json"
        assignment = out_root / "harness" / "assignments" / "worker-001.json"
        request = out_root / "harness" / "assignments" / "worker-001-request.json"
        summary = out_root / "workers" / "worker-001" / "summary" / "competition-run-summary.json"
        report = out_root / "workers" / "worker-001" / "harness" / "run-worker-report.json"
        preflight.parent.mkdir(parents=True, exist_ok=True)
        preflight.write_text('{"report_kind":"opencode-preflight"}\n', encoding="utf-8")
        runtime_env = opencode_runtime_env_contract(out_root, scope="preflight")
        preflight_binding = {
            "path": repo_relative(preflight),
            "sha256": "a" * 64,
            "status": "passed",
            "contract_status": "executed",
            "launch_policy": {
                "opencode_command": "opencode",
                "opencode_model": "GLM-5.1",
                "opencode_agent": "c2rust-migrator",
                "opencode_variant": "max",
                "opencode_skip_permissions": True,
            },
            "opencode_runtime_env": runtime_env,
            "opencode_model_availability": {
                "status": "available",
                "opencode_command": "opencode",
                "required_model": "GLM-5.1",
                "process_returncode": 0,
                "model_listed": True,
            },
        }
        worker = {
            "worker_id": "worker-001",
            "assignment_path": repo_relative(assignment),
            "request_path": repo_relative(request),
            "summary_path": repo_relative(summary),
            "report_path": repo_relative(report),
            "isolated_out_root": repo_relative(out_root / "workers" / "worker-001"),
            "opencode_preflight_report": preflight_binding,
        }
        argv = [
            "python3",
            "-B",
            "-m",
            "validation.tools.opencode_agent_harness",
            "run-worker",
            "--db",
            repo_relative(ledger),
            "--run-id",
            "run-resume",
            "--worker-id",
            "worker-001",
            "--mode",
            "opencode",
            "--opencode-model",
            "GLM-5.1",
            "--opencode-agent",
            "c2rust-migrator",
            "--opencode-variant",
            "max",
            "--opencode-preflight-report",
            repo_relative(preflight),
        ]
        command_payload = {
            "argv": argv,
            "command": shlex.join(argv),
            "assignment_path": repo_relative(assignment),
            "request_path": repo_relative(request),
            "summary_path": repo_relative(summary),
            "report_path": repo_relative(report),
            "out_root": repo_relative(out_root / "workers" / "worker-001"),
            "replay_safety": {
                "status": "ready",
                "reason": "opencode_preflight_contract_bound",
            },
        }

        with self.assertRaisesRegex(ValueError, "opencode_preflight_report.sha256 mismatch"):
            validator.validate_resume_manifest_replay_command(
                command_payload,
                label="resume_manifest.workers[0].replay_commands.run_worker",
                expected_subcommand="run-worker",
                worker=worker,
                worker_id="worker-001",
                run_id="run-resume",
                ledger_path=repo_relative(ledger),
                require_hint=False,
            )

    def test_resume_manifest_opencode_replay_deep_validates_preflight_file(self) -> None:
        target_dir = REPO_ROOT / "target"
        target_dir.mkdir(exist_ok=True)
        temp_dir = Path(tempfile.mkdtemp(prefix="resume-manifest-opencode-preflight-deep-", dir=target_dir))
        out_root = temp_dir / "out"
        ledger = out_root / "state" / "opencode-agent-harness.sqlite3"
        preflight = out_root / "harness" / "opencode-preflight-report.json"
        assignment = out_root / "harness" / "assignments" / "worker-001.json"
        request = out_root / "harness" / "assignments" / "worker-001-request.json"
        summary = out_root / "workers" / "worker-001" / "summary" / "competition-run-summary.json"
        report = out_root / "workers" / "worker-001" / "harness" / "run-worker-report.json"
        preflight.parent.mkdir(parents=True, exist_ok=True)
        write_json(
            preflight,
            {
                "report_kind": "opencode-preflight",
                "status": "passed",
            },
        )
        runtime_env = opencode_runtime_env_contract(out_root, scope="preflight")
        launch_policy = {
            "opencode_command": "opencode",
            "opencode_model": "GLM-5.1",
            "opencode_agent": "c2rust-migrator",
            "opencode_variant": "max",
            "opencode_skip_permissions": True,
        }
        preflight_binding = {
            "path": repo_relative(preflight),
            "sha256": validator.sha256_file(preflight),
            "status": "passed",
            "contract_status": "executed",
            "launch_policy": launch_policy,
            "launch_policy_sha256": validator.sha256_text(json.dumps(launch_policy, sort_keys=True)),
            "opencode_runtime_env": runtime_env,
            "opencode_model_availability": {
                "status": "available",
                "opencode_command": "opencode",
                "required_model": "GLM-5.1",
                "process_returncode": 0,
                "model_listed": True,
            },
        }
        worker = {
            "worker_id": "worker-001",
            "assignment_path": repo_relative(assignment),
            "request_path": repo_relative(request),
            "summary_path": repo_relative(summary),
            "report_path": repo_relative(report),
            "isolated_out_root": repo_relative(out_root / "workers" / "worker-001"),
            "opencode_preflight_report": preflight_binding,
        }
        argv = [
            "python3",
            "-B",
            "-m",
            "validation.tools.opencode_agent_harness",
            "run-worker",
            "--db",
            repo_relative(ledger),
            "--run-id",
            "run-resume",
            "--worker-id",
            "worker-001",
            "--mode",
            "opencode",
            "--opencode-model",
            "GLM-5.1",
            "--opencode-agent",
            "c2rust-migrator",
            "--opencode-variant",
            "max",
            "--opencode-preflight-report",
            repo_relative(preflight),
        ]
        command_payload = {
            "argv": argv,
            "command": shlex.join(argv),
            "assignment_path": repo_relative(assignment),
            "request_path": repo_relative(request),
            "summary_path": repo_relative(summary),
            "report_path": repo_relative(report),
            "out_root": repo_relative(out_root / "workers" / "worker-001"),
            "replay_safety": {
                "status": "ready",
                "reason": "opencode_preflight_contract_bound",
            },
        }

        with self.assertRaisesRegex(ValueError, "opencode_preflight_report file opencode_run_launched must be true"):
            validator.validate_resume_manifest_replay_command(
                command_payload,
                label="resume_manifest.workers[0].replay_commands.run_worker",
                expected_subcommand="run-worker",
                worker=worker,
                worker_id="worker-001",
                run_id="run-resume",
                ledger_path=repo_relative(ledger),
                require_hint=False,
            )

    def test_resume_manifest_opencode_replay_requires_repo_owned_preflight_agent(self) -> None:
        target_dir = REPO_ROOT / "target"
        target_dir.mkdir(exist_ok=True)
        temp_dir = Path(tempfile.mkdtemp(prefix="resume-manifest-opencode-agent-", dir=target_dir))
        out_root = temp_dir / "out"
        ledger = out_root / "state" / "opencode-agent-harness.sqlite3"
        preflight = out_root / "harness" / "opencode-preflight-report.json"
        assignment = out_root / "harness" / "assignments" / "worker-001.json"
        request = out_root / "harness" / "assignments" / "worker-001-request.json"
        summary = out_root / "workers" / "worker-001" / "summary" / "competition-run-summary.json"
        report = out_root / "workers" / "worker-001" / "harness" / "run-worker-report.json"
        preflight.parent.mkdir(parents=True, exist_ok=True)
        preflight.write_text('{"report_kind":"opencode-preflight"}\n', encoding="utf-8")
        runtime_env = opencode_runtime_env_contract(out_root, scope="preflight")
        preflight_binding = {
            "path": repo_relative(preflight),
            "sha256": validator.sha256_file(preflight),
            "status": "passed",
            "contract_status": "executed",
            "launch_policy": {
                "opencode_command": "opencode",
                "opencode_model": "GLM-5.1",
                "opencode_agent": None,
                "opencode_variant": "max",
                "opencode_skip_permissions": True,
            },
            "opencode_runtime_env": runtime_env,
            "opencode_model_availability": {
                "status": "available",
                "opencode_command": "opencode",
                "required_model": "GLM-5.1",
                "process_returncode": 0,
                "model_listed": True,
            },
        }
        worker = {
            "worker_id": "worker-001",
            "assignment_path": repo_relative(assignment),
            "request_path": repo_relative(request),
            "summary_path": repo_relative(summary),
            "report_path": repo_relative(report),
            "isolated_out_root": repo_relative(out_root / "workers" / "worker-001"),
            "opencode_preflight_report": preflight_binding,
        }
        argv = [
            "python3",
            "-B",
            "-m",
            "validation.tools.opencode_agent_harness",
            "run-worker",
            "--db",
            repo_relative(ledger),
            "--run-id",
            "run-resume",
            "--worker-id",
            "worker-001",
            "--mode",
            "opencode",
            "--opencode-model",
            "GLM-5.1",
            "--opencode-agent",
            "c2rust-migrator",
            "--opencode-variant",
            "max",
            "--opencode-preflight-report",
            repo_relative(preflight),
        ]
        command_payload = {
            "argv": argv,
            "command": shlex.join(argv),
            "assignment_path": repo_relative(assignment),
            "request_path": repo_relative(request),
            "summary_path": repo_relative(summary),
            "report_path": repo_relative(report),
            "out_root": repo_relative(out_root / "workers" / "worker-001"),
            "replay_safety": {
                "status": "ready",
                "reason": "opencode_preflight_contract_bound",
            },
        }

        with self.assertRaisesRegex(ValueError, "opencode_preflight_report.launch_policy.opencode_agent"):
            validator.validate_resume_manifest_replay_command(
                command_payload,
                label="resume_manifest.workers[0].replay_commands.run_worker",
                expected_subcommand="run-worker",
                worker=worker,
                worker_id="worker-001",
                run_id="run-resume",
                ledger_path=repo_relative(ledger),
                require_hint=False,
            )

    def test_worker_plan_units_must_match_context_and_agent_index_workers(self) -> None:
        target_dir = REPO_ROOT / "target"
        target_dir.mkdir(exist_ok=True)
        temp_dir = Path(tempfile.mkdtemp(prefix="worker-plan-drift-", dir=target_dir))
        out_root = temp_dir / "out"
        context_pack = out_root / "harness" / "context-pack.json"
        agent_index = out_root / "harness" / "agent-index.json"
        worker_plan = out_root / "harness" / "plans" / "workers.json"
        ledger = out_root / "state" / "opencode-agent-harness.sqlite3"
        worker_root = out_root / "workers" / "worker-001"
        assignment = out_root / "harness" / "assignments" / "worker-001.json"
        request = out_root / "harness" / "assignments" / "worker-001-request.json"
        summary = worker_root / "summary" / "competition-run-summary.json"
        report = worker_root / "harness" / "run-worker-report.json"

        for artifact in [assignment, request, summary, report]:
            artifact.parent.mkdir(parents=True, exist_ok=True)
            artifact.write_text("{}\n", encoding="utf-8")
        common_worker = {
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
        write_json(
            context_pack,
            {
                "report_kind": "context-pack",
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
                    "resume_protocol": {
                        "checkpoint_backend": "sqlite",
                        "ledger_path": repo_relative(ledger),
                        "worker_state_source": "agent-index.agents_by_worker_id",
                    },
                    "schema_version": 1,
                    "semantic_gate": False,
                },
                "entrypoints": {"worker_plan": repo_relative(worker_plan)},
                "workers": [common_worker],
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
                "agents": [common_worker],
                "agents_by_worker_id": {
                    "worker-001": {
                        **common_worker,
                        "isolated_out_root": repo_relative(worker_root),
                    }
                },
                "planner": {
                    "plan_path": repo_relative(worker_plan),
                    "worker_count": 1,
                },
            },
        )
        write_json(
            worker_plan,
            {
                "schema_version": 1,
                "planning_mode": "explicit_workers",
                "status": "planned",
                "target_id": "flashdb",
                "run_id": "worker-plan-drift",
                "plan_path": repo_relative(worker_plan),
                "units": [
                    {
                        **common_worker,
                        "out_root": repo_relative(worker_root),
                        "worker_id": "worker-002",
                    }
                ],
            },
        )
        write_minimal_context_ledger(
            ledger,
            run_id="worker-plan-drift",
            context_pack_path=context_pack,
            context_pack_payload=json.loads(context_pack.read_text(encoding="utf-8")),
            agent_index_path=agent_index,
        )

        with self.assertRaisesRegex(ValueError, "worker_plan.units worker ids must match context_pack.workers"):
            validator.validate_harness_artifact_contracts(
                {
                    "context_pack": repo_relative(context_pack),
                    "agent_index": repo_relative(agent_index),
                    "worker_plan": repo_relative(worker_plan),
                },
                require_local_artifacts=True,
                repo_root=REPO_ROOT,
            )
