class _OpenCodeAgentHarnessTestPart02:
    def test_c_source_sha256_is_stable_across_line_endings(self) -> None:
        with temp_repo_dir() as tmp:
            source_file = Path(tmp) / "FlashDB" / "src" / "demo.c"
            source_file.parent.mkdir(parents=True)
            source_file.write_bytes(b"int first_unit(int value) {\r\n    return value + 1;\r\n}\r\n")

            expected = hashlib.sha256(b"int first_unit(int value) {\n    return value + 1;\n}\n").hexdigest()

            self.assertEqual(harness.sha256_file(source_file), expected)

    def test_run_batch_profile_opencode_passes_preflight_report_to_workers(self) -> None:
        with temp_repo_dir() as tmp:
            out_root = Path(tmp) / "competition-out"
            source_root = Path(tmp) / "FlashDB"
            source_file = source_root / "src" / "demo.c"
            source_file.parent.mkdir(parents=True)
            source_file.write_text(
                """
                int first_unit(int value) {
                    return value + 1;
                }
                """,
                encoding="utf-8",
            )
            profile_path = Path(tmp) / "planned-batch.json"
            preflight_report = write_passing_opencode_preflight_report(
                out_root / "harness" / "opencode-preflight-report.json",
                run_id="run-profile-opencode",
            )
            profile_path.write_text(
                json.dumps(
                    {
                        "schema_version": 1,
                        "profile_id": "demo-opencode-preflight",
                        "proof_class": "local-simulation",
                        "target_id": "demo",
                        "source_repo_root": repo_rel(source_root),
                        "source_file": "src/demo.c",
                        "source_commit": "abc123",
                        "functions": ["first_unit"],
                        "slice_id_prefix": "demo-opencode",
                        "worker_prefix": "worker",
                        "mode": "opencode",
                        "opencode_preflight_report": repo_rel(preflight_report),
                        "execute_merge": False,
                        "auto_retry": False,
                        "timeout_seconds": 13,
                        "emit_route_governance_metrics_report": False,
                    }
                ),
                encoding="utf-8",
            )

            handoff_contract = {"path": "target/opencode/handoff-contract.json", "sha256": "a" * 64}
            session_evidence = {"path": "target/opencode/session-evidence.json", "sha256": "b" * 64}
            contract_verification = {"status": "executed", "matched_command": "python3 -B scripts/c2rust-migrator.py"}
            preflight_binding = {
                "path": repo_rel(preflight_report),
                "sha256": harness.sha256_file(preflight_report),
                "status": "passed",
            }
            with patch.object(
                harness,
                "run_worker",
                return_value={
                    "exit_code": 0,
                    "summary_status": "passed",
                    "summary_path": "",
                    "report_path": "target/report.json",
                    "recorded": False,
                    "handoff_contract": handoff_contract,
                    "opencode_session_evidence": session_evidence,
                    "opencode_contract_verification": contract_verification,
                    "opencode_preflight_report": preflight_binding,
                },
            ) as runner:
                result = harness.run_batch_profile(
                    profile_path=profile_path,
                    run_id="run-profile-opencode",
                    out_root=out_root,
                    repo_root=REPO_ROOT,
                )

            self.assertEqual(result["mode"], "opencode")
            runner.assert_called_once()
            self.assertEqual(runner.call_args.kwargs["mode"], "opencode")
            self.assertEqual(runner.call_args.kwargs["opencode_preflight_report"], Path(repo_rel(preflight_report)))
            context_pack = json.loads((REPO_ROOT / result["context_pack"]["path"]).read_text(encoding="utf-8"))
            agent_index = json.loads((REPO_ROOT / result["agent_index"]["path"]).read_text(encoding="utf-8"))
            context_worker = context_pack["workers"][0]
            indexed_agent = agent_index["agents_by_worker_id"][context_worker["worker_id"]]
            self.assertEqual(context_pack["entrypoints"]["opencode_preflight_report"], repo_rel(preflight_report))
            self.assertEqual(agent_index["reports"]["opencode_preflight_report"]["path"], repo_rel(preflight_report))
            for indexed in (context_worker, indexed_agent):
                self.assertEqual(indexed["handoff_contract"], handoff_contract)
                self.assertEqual(indexed["opencode_session_evidence"], session_evidence)
                self.assertEqual(indexed["opencode_contract_verification"], contract_verification)
                self.assertEqual(indexed["opencode_preflight_report"], preflight_binding)

    def test_run_batch_profile_rejects_competition_exact_without_exact_host_before_preflight(self) -> None:
        with temp_repo_dir() as tmp:
            out_root = Path(tmp) / "competition-out"
            source_root = Path(tmp) / "FlashDB"
            source_file = source_root / "src" / "demo.c"
            source_file.parent.mkdir(parents=True)
            source_file.write_text("int first_unit(int value) { return value + 1; }\n", encoding="utf-8")
            profile_path = Path(tmp) / "planned-batch.json"
            profile_path.write_text(
                json.dumps(
                    {
                        "schema_version": 1,
                        "profile_id": "demo-opencode-competition-exact-overclaim",
                        "proof_class": "competition-exact",
                        "target_id": "demo",
                        "source_repo_root": repo_rel(source_root),
                        "source_file": "src/demo.c",
                        "source_commit": "abc123",
                        "functions": ["first_unit"],
                        "mode": "opencode",
                        "execute_merge": False,
                    }
                ),
                encoding="utf-8",
            )

            def fail_if_called(argv: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
                raise AssertionError(f"competition-exact overclaim should fail before launch: {argv}")

            with patch.dict(os.environ, {"COMPETITION_EXACT_HOST": "0"}):
                with self.assertRaisesRegex(SystemExit, "COMPETITION_EXACT_HOST=1"):
                    harness.run_batch_profile(
                        profile_path=profile_path,
                        run_id="run-profile-competition-exact-overclaim",
                        out_root=out_root,
                        command_runner=fail_if_called,
                        repo_root=REPO_ROOT,
                    )

            self.assertFalse((out_root / "state" / "opencode-agent-harness.sqlite3").exists())

    def test_run_batch_profile_rejects_cli_competition_exact_override_without_exact_host(self) -> None:
        with temp_repo_dir() as tmp:
            out_root = Path(tmp) / "competition-out"
            source_root = Path(tmp) / "FlashDB"
            source_file = source_root / "src" / "demo.c"
            source_file.parent.mkdir(parents=True)
            source_file.write_text("int first_unit(int value) { return value + 1; }\n", encoding="utf-8")
            profile_path = Path(tmp) / "planned-batch.json"
            profile_path.write_text(
                json.dumps(
                    {
                        "schema_version": 1,
                        "profile_id": "demo-opencode-cli-exact-override",
                        "proof_class": "local-simulation",
                        "target_id": "demo",
                        "source_repo_root": repo_rel(source_root),
                        "source_file": "src/demo.c",
                        "source_commit": "abc123",
                        "functions": ["first_unit"],
                        "mode": "opencode",
                        "execute_merge": False,
                    }
                ),
                encoding="utf-8",
            )

            def fail_if_called(argv: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
                raise AssertionError(f"competition-exact override should fail before launch: {argv}")

            with patch.dict(os.environ, {"COMPETITION_EXACT_HOST": ""}):
                with self.assertRaisesRegex(SystemExit, "COMPETITION_EXACT_HOST=1"):
                    harness.run_batch_profile(
                        profile_path=profile_path,
                        run_id="run-profile-cli-exact-override",
                        out_root=out_root,
                        proof_class_override="competition-exact",
                        command_runner=fail_if_called,
                        repo_root=REPO_ROOT,
                    )

            self.assertFalse((out_root / "state" / "opencode-agent-harness.sqlite3").exists())

    def test_run_batch_profile_records_cli_proof_class_override(self) -> None:
        with temp_repo_dir() as tmp:
            out_root = Path(tmp) / "competition-out"
            source_root = Path(tmp) / "FlashDB"
            source_file = source_root / "src" / "demo.c"
            source_file.parent.mkdir(parents=True)
            source_file.write_text("int first_unit(int value) { return value + 1; }\n", encoding="utf-8")
            profile_path = Path(tmp) / "planned-batch.json"
            profile_path.write_text(
                json.dumps(
                    {
                        "schema_version": 1,
                        "profile_id": "demo-cli-exact-override",
                        "proof_class": "local-simulation",
                        "target_id": "demo",
                        "source_repo_root": repo_rel(source_root),
                        "source_file": "src/demo.c",
                        "source_commit": "abc123",
                        "functions": ["first_unit"],
                        "slice_id_prefix": "demo",
                        "worker_prefix": "worker",
                        "mode": "deterministic",
                        "execute_merge": False,
                    }
                ),
                encoding="utf-8",
            )

            def fake_runner(argv: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
                if "scripts/c2rust-migrator.py" not in argv:
                    raise AssertionError(f"unexpected command for no-merge profile: {argv}")
                request_path = REPO_ROOT / argv[argv.index("--input") + 1]
                request = json.loads(request_path.read_text(encoding="utf-8"))
                summary_path = REPO_ROOT / request["out_root"] / "summary" / "competition-run-summary.json"
                write_worker_summary(summary_path, request["run_id"], status="passed", failed=0, semantic_pass=1)
                return subprocess.CompletedProcess(argv, 0, stdout="worker ok\n", stderr="")

            with patch.dict(os.environ, {"COMPETITION_EXACT_HOST": "1"}):
                result = harness.run_batch_profile(
                    profile_path=profile_path,
                    run_id="run-profile-cli-exact-override",
                    out_root=out_root,
                    proof_class_override="competition-exact",
                    command_runner=fake_runner,
                    repo_root=REPO_ROOT,
                )

            self.assertEqual(result["status"], "completed")
            self.assertEqual(result["profile_proof_class"], "local-simulation")
            self.assertEqual(result["proof_class"], "competition-exact")
            self.assertEqual(
                result["proof_class_resolution"],
                {
                    "source": "cli-override",
                    "profile_proof_class": "local-simulation",
                    "effective_proof_class": "competition-exact",
                    "override_requested": True,
                    "changed": True,
                    "override_proof_class": "competition-exact",
                },
            )
            rows = fetch_rows(
                Path(REPO_ROOT / result["db_path"]),
                "select proof_class from runs where run_id=?",
                ("run-profile-cli-exact-override",),
            )
            self.assertEqual(rows, [("competition-exact",)])
            report = json.loads((out_root / "harness" / "batch-profile-report.json").read_text(encoding="utf-8"))
            self.assertEqual(report["profile_proof_class"], "local-simulation")
            self.assertEqual(report["proof_class"], "competition-exact")
            self.assertEqual(report["proof_class_resolution"], result["proof_class_resolution"])
            context_pack = json.loads((REPO_ROOT / result["context_pack"]["path"]).read_text(encoding="utf-8"))
            agent_index = json.loads((REPO_ROOT / result["agent_index"]["path"]).read_text(encoding="utf-8"))
            self.assertEqual(context_pack["proof_class_resolution"], result["proof_class_resolution"])
            self.assertEqual(agent_index["proof_class_resolution"], result["proof_class_resolution"])

    def test_evaluate_rejects_competition_exact_without_exact_host_before_init_run(self) -> None:
        with temp_repo_dir() as tmp:
            out_root = Path(tmp) / "competition-out"
            source_root = Path(tmp) / "FlashDB"
            source_file = source_root / "src" / "demo.c"
            source_file.parent.mkdir(parents=True)
            source_file.write_text("int first_unit(int value) { return value + 1; }\n", encoding="utf-8")

            def fail_if_called(argv: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
                raise AssertionError(f"competition-exact overclaim should fail before worker launch: {argv}")

            with patch.dict(os.environ, {"COMPETITION_EXACT_HOST": ""}):
                with self.assertRaisesRegex(SystemExit, "COMPETITION_EXACT_HOST=1"):
                    harness.evaluate(
                        run_id="run-evaluate-competition-exact-overclaim",
                        target_id="demo",
                        source_repo_root=source_root,
                        source_file="src/demo.c",
                        source_commit="abc123",
                        out_root=out_root,
                        proof_class="competition-exact",
                        functions=["first_unit"],
                        mode="deterministic",
                        execute_merge=False,
                        command_runner=fail_if_called,
                        repo_root=REPO_ROOT,
                    )

            self.assertFalse((out_root / "state" / "opencode-agent-harness.sqlite3").exists())

    def test_run_batch_profile_opencode_auto_runs_preflight_when_profile_omits_report(self) -> None:
        with temp_repo_dir() as tmp:
            out_root = Path(tmp) / "competition-out"
            source_root = Path(tmp) / "FlashDB"
            source_file = source_root / "src" / "demo.c"
            source_file.parent.mkdir(parents=True)
            source_file.write_text("int first_unit(int value) { return value + 1; }\n", encoding="utf-8")
            profile_path = Path(tmp) / "planned-batch.json"
            profile_path.write_text(
                json.dumps(
                    {
                        "schema_version": 1,
                        "profile_id": "demo-opencode-auto-preflight",
                        "proof_class": "local-simulation",
                        "target_id": "demo",
                        "source_repo_root": repo_rel(source_root),
                        "source_file": "src/demo.c",
                        "source_commit": "abc123",
                        "functions": ["first_unit"],
                        "slice_id_prefix": "demo-opencode",
                        "worker_prefix": "worker",
                        "mode": "opencode",
                        "execute_merge": False,
                        "auto_retry": False,
                        "timeout_seconds": 13,
                        "emit_route_governance_metrics_report": False,
                    }
                ),
                encoding="utf-8",
            )

            preflight_kwargs: dict[str, object] = {}

            def fake_preflight_runner(argv: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
                preflight_kwargs.update(kwargs)
                if len(argv) >= 2 and argv[1] == "models":
                    return subprocess.CompletedProcess(argv, 0, stdout="GLM-5.1\n", stderr="")
                contract_path = out_root / "harness" / "opencode-preflight-contract.json"
                contract = json.loads(contract_path.read_text(encoding="utf-8"))
                marker_path = REPO_ROOT / contract["expected_marker_path"]
                write_valid_preflight_marker(marker_path, run_id="run-profile-opencode-auto")
                stdout = json.dumps(
                    {
                        "type": "tool_use",
                        "part": {
                            "tool": "bash",
                            "state": {
                                "input": {"command": contract["worker_command_line"], "workdir": str(REPO_ROOT)},
                                "status": "completed",
                            },
                        },
                    }
                )
                return subprocess.CompletedProcess(argv, 0, stdout=stdout + "\n", stderr="")

            preflight_report = out_root / "harness" / "opencode-preflight-report.json"
            preflight_binding = {
                "path": repo_rel(preflight_report),
                "sha256": "",
                "status": "passed",
            }

            with patch.object(
                harness,
                "run_worker",
                return_value={
                    "exit_code": 0,
                    "summary_status": "passed",
                    "summary_path": "",
                    "report_path": "target/report.json",
                    "recorded": False,
                    "opencode_preflight_report": preflight_binding,
                },
            ) as runner:
                result = harness.run_batch_profile(
                    profile_path=profile_path,
                    run_id="run-profile-opencode-auto",
                    out_root=out_root,
                    command_runner=fake_preflight_runner,
                    repo_root=REPO_ROOT,
                )

            preflight_report_payload = json.loads(preflight_report.read_text(encoding="utf-8"))
            expected_preflight_binding = {
                "path": repo_rel(preflight_report),
                "sha256": harness.sha256_file(preflight_report),
                "status": "passed",
                "run_id": "run-profile-opencode-auto",
                "contract_status": "executed",
                "launch_policy": {
                    "opencode_command": "opencode",
                    "opencode_model": "GLM-5.1",
                    "opencode_agent": "c2rust-migrator",
                    "opencode_variant": "max",
                    "opencode_skip_permissions": False,
                },
                "launch_policy_sha256": harness.sha256_text(
                    json.dumps(
                        {
                            "opencode_agent": "c2rust-migrator",
                            "opencode_command": "opencode",
                            "opencode_model": "GLM-5.1",
                            "opencode_skip_permissions": False,
                            "opencode_variant": "max",
                        },
                        sort_keys=True,
                    )
                ),
                "opencode_model_availability": {
                    "status": "available",
                    "opencode_command": "opencode",
                    "required_model": "GLM-5.1",
                    "argv": preflight_report_payload["opencode_model_availability"]["argv"],
                    "process_returncode": 0,
                    "model_listed": True,
                },
                "opencode_runtime_env": preflight_report_payload["opencode_runtime_env"],
                "evidence_boundary": "preflight proves exact-command compliance only; it is not semantic acceptance",
            }
            self.assertEqual(result["mode"], "opencode")
            self.assertEqual(result["opencode_preflight_report"], expected_preflight_binding)
            self.assertEqual(preflight_kwargs["timeout"], 13)
            runner.assert_called_once()
            self.assertEqual(runner.call_args.kwargs["opencode_preflight_report"], Path(repo_rel(preflight_report)))
            self.assertEqual(runner.call_args.kwargs["timeout_seconds"], 13)
            run_plan = result["run_plan"]
            self.assertEqual(run_plan["opencode_preflight_report"], expected_preflight_binding)
            self.assertEqual(
                run_plan["graph"]["opencode_worker"]["preflight_report"]["path"],
                repo_rel(preflight_report),
            )
            self.assertEqual(run_plan["graph"]["opencode_worker"]["opencode_variant"], "max")
            context_pack = json.loads((REPO_ROOT / result["context_pack"]["path"]).read_text(encoding="utf-8"))
            agent_index = json.loads((REPO_ROOT / result["agent_index"]["path"]).read_text(encoding="utf-8"))
            self.assertEqual(context_pack["entrypoints"]["opencode_preflight_report"], repo_rel(preflight_report))
            self.assertEqual(agent_index["reports"]["opencode_preflight_report"], expected_preflight_binding)

    def test_run_batch_profile_opencode_auto_preflight_failure_writes_blocked_report_before_planning(self) -> None:
        with temp_repo_dir() as tmp:
            out_root = Path(tmp) / "competition-out"
            source_root = Path(tmp) / "FlashDB"
            source_file = source_root / "src" / "demo.c"
            source_file.parent.mkdir(parents=True)
            source_file.write_text("int first_unit(int value) { return value + 1; }\n", encoding="utf-8")
            profile_path = Path(tmp) / "planned-batch.json"
            profile_path.write_text(
                json.dumps(
                    {
                        "schema_version": 1,
                        "profile_id": "demo-opencode-auto-preflight-blocked",
                        "proof_class": "local-simulation",
                        "target_id": "demo",
                        "source_repo_root": repo_rel(source_root),
                        "source_file": "src/demo.c",
                        "source_commit": "abc123",
                        "functions": ["first_unit"],
                        "slice_id_prefix": "demo-opencode",
                        "worker_prefix": "worker",
                        "mode": "opencode",
                        "opencode_model": "GLM-5.1",
                        "execute_merge": False,
                        "auto_retry": False,
                        "timeout_seconds": 13,
                        "emit_route_governance_metrics_report": False,
                    }
                ),
                encoding="utf-8",
            )
            stale_files = [
                out_root / "summary" / "competition-run-summary.json",
                out_root / "summary" / "workflow-metrics.json",
                out_root / "summary" / "route-governance-metrics-report.json",
                out_root / "harness" / "run-plan-report.json",
                out_root / "harness" / "judge-evidence-index.json",
                out_root / "harness" / "context-pack.json",
                out_root / "harness" / "agent-index.json",
                out_root / "state" / "opencode-agent-harness.sqlite3",
                out_root / "workers" / "old-worker" / "summary" / "competition-run-summary.json",
                out_root / "harness" / "plans" / "old-workers.json",
            ]
            for stale_file in stale_files:
                stale_file.parent.mkdir(parents=True, exist_ok=True)
                stale_file.write_text(json.dumps({"stale": True}), encoding="utf-8")

            def fake_preflight_runner(argv: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
                if len(argv) >= 2 and argv[1] == "models":
                    return subprocess.CompletedProcess(argv, 0, stdout="gpt-5.4\n", stderr="")
                raise AssertionError(f"batch preflight failure must not launch OpenCode worker or marker command: {argv}")

            result = harness.run_batch_profile(
                profile_path=profile_path,
                run_id="run-profile-opencode-preflight-blocked",
                out_root=out_root,
                command_runner=fake_preflight_runner,
                repo_root=REPO_ROOT,
            )

            self.assertEqual(result["report_kind"], "batch-profile-report")
            self.assertEqual(result["status"], "blocked")
            self.assertEqual(result["exit_code"], 1)
            self.assertEqual(result["blocked_phase"], "opencode-preflight")
            self.assertEqual(result["root_cause_key"], "opencode_model_unavailable")
            self.assertEqual(result["profile_proof_class"], "local-simulation")
            self.assertEqual(result["proof_class"], "local-simulation")
            self.assertEqual(
                result["proof_class_resolution"],
                {
                    "source": "profile",
                    "profile_proof_class": "local-simulation",
                    "effective_proof_class": "local-simulation",
                    "override_requested": False,
                    "changed": False,
                },
            )
            self.assertFalse(result["semantic_gate"])
            self.assertEqual(result["translation_coverage_numerator"], 0)
            self.assertFalse(result["local_simulation_closes_p0_h9"])
            self.assertEqual(result["worker_count"], 0)
            self.assertNotIn("run_plan", result)
            self.assertEqual(result["stale_artifact_cleanup"]["status"], "passed")
            self.assertEqual(
                sorted(result["stale_artifact_cleanup"]["removed_artifacts"]),
                sorted(
                    [
                        repo_rel(out_root / "summary" / "competition-run-summary.json"),
                        repo_rel(out_root / "summary" / "workflow-metrics.json"),
                        repo_rel(out_root / "summary" / "route-governance-metrics-report.json"),
                        repo_rel(out_root / "harness" / "run-plan-report.json"),
                        repo_rel(out_root / "harness" / "judge-evidence-index.json"),
                        repo_rel(out_root / "harness" / "context-pack.json"),
                        repo_rel(out_root / "harness" / "agent-index.json"),
                        repo_rel(out_root / "state" / "opencode-agent-harness.sqlite3"),
                        repo_rel(out_root / "workers"),
                        repo_rel(out_root / "harness" / "plans"),
                    ]
                ),
            )
            for stale_file in stale_files:
                self.assertFalse(stale_file.exists(), stale_file)
            self.assertFalse((out_root / "state" / "opencode-agent-harness.sqlite3").exists())
            self.assertFalse((out_root / "harness" / "plans").exists())

            preflight_report = out_root / "harness" / "opencode-preflight-report.json"
            self.assertTrue(preflight_report.exists())
            preflight_payload = json.loads(preflight_report.read_text(encoding="utf-8"))
            self.assertEqual(result["opencode_preflight_report"]["path"], repo_rel(preflight_report))
            self.assertEqual(result["opencode_preflight_report"]["status"], "failed")
            self.assertEqual(result["opencode_preflight_report"]["root_cause_key"], "opencode_model_unavailable")
            self.assertEqual(result["h9_blocker"], preflight_payload["h9_blocker"])
            self.assertFalse(result["h9_blocker"]["opencode_run_launched"])

            batch_report = out_root / "harness" / "batch-profile-report.json"
            self.assertEqual(json.loads(batch_report.read_text(encoding="utf-8")), result)

    def test_run_batch_profile_opencode_hostless_rehearsal_executes_auto_preflight_and_worker_contracts(self) -> None:
        with temp_repo_dir() as tmp:
            out_root = Path(tmp) / "competition-out"
            source_root = Path(tmp) / "FlashDB"
            source_file = source_root / "src" / "demo.c"
            source_file.parent.mkdir(parents=True)
            source_file.write_text("int first_unit(int value) { return value + 1; }\n", encoding="utf-8")
            profile_path = Path(tmp) / "planned-batch.json"
            profile_path.write_text(
                json.dumps(
                    {
                        "schema_version": 1,
                        "profile_id": "demo-opencode-hostless-rehearsal",
                        "proof_class": "local-simulation",
                        "target_id": "demo",
                        "source_repo_root": repo_rel(source_root),
                        "source_file": "src/demo.c",
                        "source_commit": "abc123",
                        "functions": ["first_unit"],
                        "slice_id_prefix": "demo-opencode",
                        "worker_prefix": "worker",
                        "mode": "opencode",
                        "opencode_command": "opencode",
                        "opencode_model": "GLM-5.1",
                        "opencode_variant": "max",
                        "opencode_skip_permissions": False,
                        "opencode_hostless_rehearsal": True,
                        "opencode_hostless_rehearsal_runner": "fake/fixture",
                        "execute_merge": False,
                        "auto_retry": False,
                        "max_workers": 1,
                        "timeout_seconds": 13,
                        "emit_route_governance_metrics_report": False,
                    }
                ),
                encoding="utf-8",
            )
            calls: list[list[str]] = []

            def fake_opencode_runner(argv: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
                calls.append(argv)
                if len(argv) >= 2 and argv[1] == "models":
                    return subprocess.CompletedProcess(argv, 0, stdout="GLM-5.1\n", stderr="")
                if len(calls) == 2:
                    contract_path = out_root / "harness" / "opencode-preflight-contract.json"
                    contract = json.loads(contract_path.read_text(encoding="utf-8"))
                    marker_path = REPO_ROOT / contract["expected_marker_path"]
                    write_valid_preflight_marker(marker_path, run_id="run-profile-opencode-hostless")
                    stdout = json.dumps(
                        {
                            "type": "tool_use",
                            "part": {
                                "tool": "bash",
                                "state": {
                                    "input": {
                                        "command": contract["worker_command_line"],
                                        "workdir": str(REPO_ROOT),
                                    },
                                    "status": "completed",
                                },
                            },
                        }
                    )
                    return subprocess.CompletedProcess(argv, 0, stdout=stdout + "\n", stderr="")

                handoff_paths = list(out_root.glob("workers/*/harness/opencode-handoff-contract.json"))
                self.assertEqual(len(handoff_paths), 1)
                contract = json.loads(handoff_paths[0].read_text(encoding="utf-8"))
                request = json.loads((REPO_ROOT / contract["request_path"]).read_text(encoding="utf-8"))
                summary_path = REPO_ROOT / contract["expected_summary_path"]
                write_worker_summary(summary_path, request["run_id"], status="passed", failed=0, semantic_pass=1)
                stdout = json.dumps(
                    {
                        "type": "tool_use",
                        "part": {
                            "tool": "bash",
                            "state": {
                                "input": {
                                    "command": contract["worker_command_line"],
                                    "workdir": str(REPO_ROOT),
                                },
                                "status": "completed",
                            },
                        },
                    }
                )
                return subprocess.CompletedProcess(argv, 0, stdout=stdout + "\n", stderr="")

            result = harness.run_batch_profile(
                profile_path=profile_path,
                run_id="run-profile-opencode-hostless",
                out_root=out_root,
                command_runner=fake_opencode_runner,
                repo_root=REPO_ROOT,
            )

            self.assertEqual(result["status"], "completed")
            self.assertEqual(result["exit_code"], 0)
            self.assertEqual([call[1] for call in calls], ["models", "run", "run"])
            rehearsal_ref = result["opencode_hostless_rehearsal_report"]
            rehearsal_path = REPO_ROOT / rehearsal_ref["path"]
            self.assertEqual(rehearsal_ref["sha256"], harness.sha256_file(rehearsal_path))
            rehearsal = json.loads(rehearsal_path.read_text(encoding="utf-8"))
            self.assertEqual(rehearsal["report_kind"], "opencode-hostless-rehearsal-report")
            self.assertEqual(rehearsal["proof_class"], "local-simulation")
            self.assertEqual(rehearsal["rehearsal_runner"], "fake/fixture")
            self.assertFalse(rehearsal["closes_p0_h9"])
            self.assertFalse(rehearsal["semantic_gate"])
            self.assertFalse(rehearsal["chat_output_is_evidence"])
            self.assertFalse(rehearsal["generated_draft_semantic_pass"])
            self.assertEqual(rehearsal["translation_coverage_numerator"], 0)
            self.assertEqual(rehearsal["h9_contract"]["status"], "blocked")
            self.assertEqual(rehearsal["h9_contract"]["required_agent_tool"], "opencode")
            self.assertEqual(rehearsal["h9_contract"]["required_agent"], "c2rust-migrator")
            self.assertEqual(rehearsal["h9_contract"]["required_model"], "GLM-5.1")
            self.assertEqual(rehearsal["h9_contract"]["required_variant"], "max")
            self.assertEqual(rehearsal["opencode_preflight_report"], result["opencode_preflight_report"])
            self.assertEqual(rehearsal["context_pack"], result["context_pack"])
            self.assertEqual(rehearsal["agent_index"], result["agent_index"])
            self.assertEqual(rehearsal["run_plan_report"]["path"], result["run_plan"]["report_path"])
            self.assertTrue(rehearsal["opencode_runtime"]["all_contracts_executed"])
            self.assertEqual(rehearsal["opencode_runtime"]["contract_status_counts"], {"executed": 1})
            self.assertEqual(rehearsal["workers"][0]["opencode_contract_verification"]["status"], "executed")
            self.assertEqual(rehearsal["workers"][0]["final_decision"], {"status": "accepted", "reason": "worker_summary_passed"})
            artifact_rows = fetch_rows(
                REPO_ROOT / result["db_path"],
                "select kind, repo_rel_path, semantic_role from artifacts",
            )
            self.assertIn(
                (
                    "opencode-hostless-rehearsal-report",
                    rehearsal_ref["path"],
                    "opencode-hostless-rehearsal",
                ),
                artifact_rows,
            )

    def test_opencode_preflight_uses_repo_local_runtime_env_contract(self) -> None:
        with temp_repo_dir() as tmp:
            out_root = Path(tmp) / "opencode-preflight"
            captured_env: dict[str, str] = {}

            def fake_preflight_runner(argv: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
                captured_env.update(kwargs["env"])  # type: ignore[arg-type]
                if len(argv) >= 2 and argv[1] == "models":
                    return subprocess.CompletedProcess(argv, 0, stdout="GLM-5.1\n", stderr="")
                contract = json.loads((out_root / "harness" / "opencode-preflight-contract.json").read_text(encoding="utf-8"))
                marker_path = REPO_ROOT / contract["expected_marker_path"]
                write_valid_preflight_marker(marker_path, run_id="preflight-env")
                stdout = json.dumps(
                    {
                        "type": "tool_use",
                        "part": {
                            "tool": "bash",
                            "state": {
                                "input": {"command": contract["worker_command_line"], "workdir": str(REPO_ROOT)},
                                "status": "completed",
                            },
                        },
                    }
                )
                return subprocess.CompletedProcess(argv, 0, stdout=stdout + "\n", stderr="")

            report = harness.run_opencode_preflight(
                out_root=out_root,
                run_id="preflight-env",
                command_runner=fake_preflight_runner,
                repo_root=REPO_ROOT,
            )

            self.assertEqual(report["status"], "passed")
            runtime_env = report["opencode_runtime_env"]
            self.assertEqual(runtime_env["status"], "isolated")
            self.assertEqual(runtime_env["scope"], "preflight")
            self.assertEqual(runtime_env["env"]["XDG_CONFIG_HOME"], repo_rel(out_root / "opencode-runtime" / "preflight" / "config"))
            self.assertEqual(captured_env["XDG_CONFIG_HOME"], str(out_root / "opencode-runtime" / "preflight" / "config"))
            self.assertEqual(captured_env["XDG_DATA_HOME"], str(out_root / "opencode-runtime" / "preflight" / "data"))
            self.assertEqual(captured_env["XDG_CACHE_HOME"], str(out_root / "opencode-runtime" / "preflight" / "cache"))
            self.assertEqual(captured_env["TMPDIR"], str(out_root / "opencode-runtime" / "preflight" / "tmp"))
            contract = json.loads((out_root / "harness" / "opencode-preflight-contract.json").read_text(encoding="utf-8"))
            self.assertEqual(contract["opencode_runtime_env"], runtime_env)
            session = json.loads((out_root / "logs" / "opencode-preflight-session-evidence.json").read_text(encoding="utf-8"))
            self.assertEqual(session["opencode_runtime_env"], runtime_env)

    def test_validate_opencode_runtime_env_contract_rejects_recomputed_wrong_runtime_root(self) -> None:
        with temp_repo_dir() as tmp:
            out_root = Path(tmp) / "competition-out"
            runtime_env = harness.opencode_runtime_env_contract(
                base_root=out_root,
                scope="worker-a",
                repo_root=REPO_ROOT,
            )
            bad_root = out_root / "wrong-runtime" / "worker-a"
            runtime_env["runtime_root"] = repo_rel(bad_root)
            runtime_env["env"] = {
                "XDG_CONFIG_HOME": repo_rel(bad_root / "config"),
                "XDG_DATA_HOME": repo_rel(bad_root / "data"),
                "XDG_CACHE_HOME": repo_rel(bad_root / "cache"),
                "TMPDIR": repo_rel(bad_root / "tmp"),
                "TEMP": repo_rel(bad_root / "tmp"),
                "TMP": repo_rel(bad_root / "tmp"),
            }
            runtime_env["env_sha256"] = harness.sha256_text(
                json.dumps(
                    {
                        "scope": runtime_env["scope"],
                        "runtime_root": runtime_env["runtime_root"],
                        "env": runtime_env["env"],
                    },
                    sort_keys=True,
                )
            )

            with self.assertRaisesRegex(SystemExit, "runtime_root must end with opencode-runtime/<scope>"):
                harness.validate_opencode_runtime_env_contract(
                    runtime_env,
                    context="unit-test",
                    repo_root=REPO_ROOT,
                )

    def test_evaluate_runs_planning_workers_and_merge_as_one_command(self) -> None:
        with temp_repo_dir() as tmp:
            out_root = Path(tmp) / "competition-out"
            source_root = Path(tmp) / "FlashDB"
            source_file = source_root / "src" / "demo.c"
            source_file.parent.mkdir(parents=True)
            source_file.write_text(
                """
                int first_unit(int value) {
                    return value + 1;
                }

                int second_unit(int value) {
                    return value + 2;
                }
                """,
                encoding="utf-8",
            )
            worker_run_ids: list[str] = []

            def fake_runner(argv: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
                if "scripts/c2rust-migrator.py" in argv:
                    request_path = REPO_ROOT / argv[argv.index("--input") + 1]
                    request = json.loads(request_path.read_text(encoding="utf-8"))
                    worker_run_ids.append(str(request["run_id"]))
                    summary_path = REPO_ROOT / request["out_root"] / "summary" / "competition-run-summary.json"
                    write_worker_summary(summary_path, request["run_id"], status="passed", failed=0, semantic_pass=1)
                    return subprocess.CompletedProcess(argv, 0, stdout="worker ok\n", stderr="")
                summary_path = out_root / "summary" / "competition-run-summary.json"
                write_worker_summary(
                    summary_path,
                    "run-evaluate",
                    status="passed",
                    failed=0,
                    semantic_pass=2,
                    workflow_metrics=before_after_worker_metrics(out_root, "run-evaluate"),
                )
                return subprocess.CompletedProcess(argv, 0, stdout="merge ok\n", stderr="")

            result = harness.evaluate(
                run_id="run-evaluate",
                target_id="flashdb",
                source_repo_root=source_root,
                source_file="src/demo.c",
                functions=["first_unit", "second_unit"],
                source_commit="abc123",
                out_root=out_root,
                proof_class="local-simulation",
                slice_id_prefix="eval-demo",
                worker_prefix="eval-worker",
                execute_merge=True,
                auto_retry=True,
                max_workers=2,
                command_runner=fake_runner,
                repo_root=REPO_ROOT,
            )

            self.assertEqual(result["status"], "completed")
            self.assertEqual(result["exit_code"], 0)
            self.assertEqual(result["entrypoint"], "evaluate")
            self.assertEqual(result["run_plan"]["parallelism"], {"max_workers": 2, "effective_workers": 2})
            self.assertEqual(result["run_plan"]["graph"]["runtime"], "opencode-harness-langgraph-inspired")
            self.assertEqual(len(worker_run_ids), 2)
            self.assertTrue((out_root / "summary" / "competition-run-summary.json").exists())
            judge_summary = result["judge_summary"]
            self.assertEqual(judge_summary["harness_architecture"]["entrypoint"], "evaluate")
            self.assertEqual(judge_summary["harness_architecture"]["graph_runtime"], "opencode-harness-langgraph-inspired")
            self.assertEqual(judge_summary["harness_architecture"]["parallelism"], {"max_workers": 2, "effective_workers": 2})
            self.assertEqual(judge_summary["harness_architecture"]["context_pack"]["path"], result["context_pack"]["path"])
            self.assertEqual(judge_summary["harness_architecture"]["agent_index"]["path"], result["agent_index"]["path"])
            self.assert_architecture_contracts(judge_summary["harness_architecture"]["architecture_contracts"])
            headline = result["judge_headline"]
            self.assertEqual(headline["report_kind"], "judge-headline")
            self.assertEqual(headline["entrypoint"], "evaluate")
            self.assertEqual(headline["status"], "completed")
            self.assertEqual(headline["graph_runtime"], "opencode-harness-langgraph-inspired")
            self.assertEqual(headline["worker_count"], 2)
            self.assertEqual(headline["parallelism"], {"max_workers": 2, "effective_workers": 2})
            self.assertEqual(headline["repair_round_cap"], 5)
            self.assertEqual(headline["semantic_claim_source"], "final_gate_and_worker_summaries")
            self.assertFalse(headline["semantic_gate"])
            self.assertEqual(headline["context_pack"], result["context_pack"])
            self.assertEqual(headline["agent_index"], result["agent_index"])
            self.assertEqual(judge_summary["core_translation_quality"]["final_gate_status"], "passed")
            self.assertEqual(judge_summary["core_translation_quality"]["semantic_pass_count"], 2)
            self.assertEqual(judge_summary["core_translation_quality"]["unsafe_reduction"]["reduced_by"], 3)
            self.assertEqual(judge_summary["core_translation_quality"]["translation_before_after"]["status"], "bound")
            self.assertEqual(judge_summary["core_translation_quality"]["translation_before_after"]["unit_count"], 1)
            self.assertEqual(judge_summary["core_translation_quality"]["repair_summary"]["repair_history_unit_count"], 0)
            self.assertEqual(
                [worker["summary_status"] for worker in judge_summary["core_translation_quality"]["workers"]],
                ["passed", "passed"],
            )
            self.assertEqual(
                [worker["final_decision"]["status"] for worker in judge_summary["core_translation_quality"]["workers"]],
                ["accepted", "accepted"],
            )
            context_pack_path = REPO_ROOT / result["context_pack"]["path"]
            agent_index_path = REPO_ROOT / result["agent_index"]["path"]
            context_pack = json.loads(context_pack_path.read_text(encoding="utf-8"))
            agent_index = json.loads(agent_index_path.read_text(encoding="utf-8"))
            self.assertEqual(context_pack["run_id"], "run-evaluate")
            self.assertEqual(context_pack["graph"]["runtime"], "opencode-harness-langgraph-inspired")
            self.assert_context_management_contract(context_pack["context_management_contract"])
            self.assertEqual(context_pack["entrypoints"]["evaluate_report"], result["report_path"])
            self.assertEqual(context_pack["entrypoints"]["merge_plan"], result["run_plan"]["merge_plan"]["path"])
            self.assertEqual(context_pack["entrypoints"]["merge_summary"], result["run_plan"]["merge_execution"]["summary_path"])
            self.assertEqual(len(context_pack["workers"]), 2)
            self.assertEqual(agent_index["run_id"], "run-evaluate")
            self.assert_agent_coordination_contract(agent_index["agent_coordination_contract"], expected_worker_count=2)
            planned_worker_ids = [unit["worker_id"] for unit in result["plan"]["units"]]
            self.assertEqual([worker["worker_id"] for worker in context_pack["workers"]], planned_worker_ids)
            self.assertEqual([agent["worker_id"] for agent in agent_index["agents"]], planned_worker_ids)
            self.assertEqual(sorted(agent_index["agents_by_worker_id"]), planned_worker_ids)
            for unit in result["plan"]["units"]:
                indexed_agent = agent_index["agents_by_worker_id"][unit["worker_id"]]
                self.assertEqual(indexed_agent["assignment_path"], unit["assignment_path"])
                self.assertEqual(indexed_agent["request_path"], unit["request_path"])
                self.assertIn("summary_path", indexed_agent)
                self.assertIn("report_path", indexed_agent)
            db_path = Path(REPO_ROOT / result["db_path"])
            context_rows = fetch_rows(
                db_path,
                """
                select context_pack_id, run_id, target_id, slice_id, depth, max_tokens,
                       artifact_path, artifact_sha256, payload_json
                from context_packs
                """,
            )
            self.assertEqual(len(context_rows), 1)
            context_row = context_rows[0]
            self.assertEqual(context_row[:8], ("run-evaluate-context-pack", "run-evaluate", "flashdb", None, 1, 20000, result["context_pack"]["path"], result["context_pack"]["sha256"]))
            self.assertEqual(json.loads(context_row[8]), context_pack)
            artifact_rows = fetch_rows(
                db_path,
                """
                select kind, agent_id, repo_rel_path, sha256, semantic_role
                from artifacts
                where kind in ('context-pack', 'agent-index', 'evaluate-report')
                order by kind
                """,
            )
            self.assertEqual(
                artifact_rows,
                [
                    ("agent-index", "planner", result["agent_index"]["path"], result["agent_index"]["sha256"], "agent-index"),
                    ("context-pack", "planner", result["context_pack"]["path"], result["context_pack"]["sha256"], "agent-context-pack"),
                    ("evaluate-report", "planner", result["report_path"], harness.sha256_file(REPO_ROOT / result["report_path"]), "evaluate-report"),
                ],
            )
            event_rows = fetch_rows(db_path, "select event_type from events where run_id=? order by event_id", ("run-evaluate",))
            self.assertIn(("context_pack_written",), event_rows)
            self.assertIn(("evaluate_executed",), event_rows)
            paths_to_check = [
                result["db_path"],
                result["report_path"],
                result["context_pack"]["path"],
                result["agent_index"]["path"],
                context_pack["entrypoints"]["evaluate_report"],
                context_pack["entrypoints"]["run_plan_report"],
                context_pack["entrypoints"]["worker_plan"],
                context_pack["entrypoints"]["merge_plan"],
                context_pack["entrypoints"]["merge_summary"],
                context_pack["entrypoints"]["agent_index"],
            ]
            for worker in context_pack["workers"]:
                paths_to_check.extend(
                    [
                        worker["out_root"],
                        worker["assignment_path"],
                        worker["request_path"],
                        worker["summary_path"],
                        worker["report_path"],
                    ]
                )
            for agent in agent_index["agents"]:
                paths_to_check.extend(
                    [
                        agent["isolated_out_root"],
                        agent["assignment_path"],
                        agent["request_path"],
                        agent["summary_path"],
                        agent["report_path"],
                    ]
                )
            for path_value in paths_to_check:
                if path_value is None:
                    continue
                self.assert_repo_relative_posix_path(path_value)
