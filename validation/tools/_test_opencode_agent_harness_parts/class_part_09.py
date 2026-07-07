class _OpenCodeAgentHarnessTestPart09:
    def test_run_worker_opencode_rejects_preflight_report_without_launch_policy_before_launch(self) -> None:
        with temp_repo_dir() as tmp:
            out_root = Path(tmp) / "competition-out"
            db_path = harness.init_run(
                out_root=out_root,
                run_id="run-test",
                proof_class="local-simulation",
                repo_root=REPO_ROOT,
            )
            harness.assign_slice(
                db_path=db_path,
                run_id="run-test",
                worker_id="worker-a",
                target_id="demo",
                slice_id="demo-add-one",
                source_repo_root=Path("external/demo"),
                source_file="src/demo.c",
                function="add_one",
                source_commit="abc123",
                out_root=out_root / "workers" / "worker-a",
                repo_root=REPO_ROOT,
            )
            preflight_report = out_root / "harness" / "opencode-preflight-report.json"
            preflight_report.parent.mkdir(parents=True, exist_ok=True)
            preflight_report.write_text(
                json.dumps(
                    {
                        "schema_version": 1,
                        "run_id": "run-test",
                        "status": "passed",
                        "exit_code": 0,
                        "marker_exists": True,
                        "contract_verification": {"status": "executed"},
                    },
                    sort_keys=True,
                )
                + "\n",
                encoding="utf-8",
            )
            calls: list[list[str]] = []

            def fake_runner(argv: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
                calls.append(argv)
                return subprocess.CompletedProcess(argv, 0, stdout="", stderr="")

            with self.assertRaisesRegex(SystemExit, "opencode preflight launch policy is missing"):
                harness.run_worker(
                    db_path=db_path,
                    run_id="run-test",
                    worker_id="worker-a",
                    mode="opencode",
                    opencode_preflight_report=preflight_report,
                    command_runner=fake_runner,
                    repo_root=REPO_ROOT,
                )

            self.assertEqual(calls, [])

    def test_run_worker_opencode_rejects_preflight_report_without_runtime_env_contract_before_launch(self) -> None:
        with temp_repo_dir() as tmp:
            out_root = Path(tmp) / "competition-out"
            db_path = harness.init_run(
                out_root=out_root,
                run_id="run-test",
                proof_class="local-simulation",
                repo_root=REPO_ROOT,
            )
            harness.assign_slice(
                db_path=db_path,
                run_id="run-test",
                worker_id="worker-a",
                target_id="demo",
                slice_id="demo-add-one",
                source_repo_root=Path("external/demo"),
                source_file="src/demo.c",
                function="add_one",
                source_commit="abc123",
                out_root=out_root / "workers" / "worker-a",
                repo_root=REPO_ROOT,
            )
            launch_policy = {
                "opencode_command": "opencode",
                "opencode_model": "GLM-5.1",
                "opencode_agent": "c2rust-migrator",
                "opencode_variant": "max",
                "opencode_skip_permissions": False,
            }
            preflight_report = out_root / "harness" / "opencode-preflight-report.json"
            preflight_report.parent.mkdir(parents=True, exist_ok=True)
            logs_dir = out_root / "logs"
            logs_dir.mkdir(parents=True, exist_ok=True)
            model_stdout = "GLM-5.1\n"
            model_stderr = ""
            model_stdout_path = logs_dir / "opencode-models.stdout.log"
            model_stderr_path = logs_dir / "opencode-models.stderr.log"
            model_stdout_path.write_text(model_stdout, encoding="utf-8")
            model_stderr_path.write_text(model_stderr, encoding="utf-8")
            preflight_report.write_text(
                json.dumps(
                    {
                        "schema_version": 1,
                        "run_id": "run-test",
                        "status": "passed",
                        "exit_code": 0,
                        "marker_exists": True,
                        "contract_verification": {"status": "executed"},
                        "launch_policy": launch_policy,
                        "launch_policy_sha256": harness.sha256_text(json.dumps(launch_policy, sort_keys=True)),
                        "opencode_model_availability": {
                            "status": "available",
                            "opencode_command": "opencode",
                            "required_model": "GLM-5.1",
                            "argv": ["opencode", "models"],
                            "process_returncode": 0,
                            "model_listed": True,
                            "stdout_sha256": harness.sha256_text(model_stdout),
                            "stderr_sha256": harness.sha256_text(model_stderr),
                            "logs": {
                                "stdout": repo_rel(model_stdout_path),
                                "stderr": repo_rel(model_stderr_path),
                            },
                        },
                    },
                    sort_keys=True,
                )
                + "\n",
                encoding="utf-8",
            )
            calls: list[list[str]] = []

            def fake_runner(argv: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
                calls.append(argv)
                return subprocess.CompletedProcess(argv, 0, stdout="", stderr="")

            with self.assertRaisesRegex(SystemExit, "opencode preflight report opencode_runtime_env is missing"):
                harness.run_worker(
                    db_path=db_path,
                    run_id="run-test",
                    worker_id="worker-a",
                    mode="opencode",
                    opencode_preflight_report=preflight_report,
                    command_runner=fake_runner,
                    repo_root=REPO_ROOT,
                )

            self.assertEqual(calls, [])

    def test_run_worker_opencode_rejects_preflight_launch_policy_mismatch_before_launch(self) -> None:
        with temp_repo_dir() as tmp:
            out_root = Path(tmp) / "competition-out"
            db_path = harness.init_run(
                out_root=out_root,
                run_id="run-test",
                proof_class="local-simulation",
                repo_root=REPO_ROOT,
            )
            harness.assign_slice(
                db_path=db_path,
                run_id="run-test",
                worker_id="worker-a",
                target_id="demo",
                slice_id="demo-add-one",
                source_repo_root=Path("external/demo"),
                source_file="src/demo.c",
                function="add_one",
                source_commit="abc123",
                out_root=out_root / "workers" / "worker-a",
                repo_root=REPO_ROOT,
            )
            preflight_report = write_passing_opencode_preflight_report(
                out_root / "harness" / "opencode-preflight-report.json",
                run_id="run-test",
            )
            calls: list[list[str]] = []

            def fake_runner(argv: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
                calls.append(argv)
                return subprocess.CompletedProcess(argv, 0, stdout="", stderr="")

            with self.assertRaisesRegex(SystemExit, "opencode_variant must be max"):
                harness.run_worker(
                    db_path=db_path,
                    run_id="run-test",
                    worker_id="worker-a",
                    mode="opencode",
                    opencode_preflight_report=preflight_report,
                    opencode_variant="lite",
                    command_runner=fake_runner,
                    repo_root=REPO_ROOT,
                )

            self.assertEqual(calls, [])

    def test_run_worker_opencode_rejects_self_consistent_non_max_variant_before_launch(self) -> None:
        with temp_repo_dir() as tmp:
            out_root = Path(tmp) / "competition-out"
            db_path = harness.init_run(
                out_root=out_root,
                run_id="run-test",
                proof_class="local-simulation",
                repo_root=REPO_ROOT,
            )
            harness.assign_slice(
                db_path=db_path,
                run_id="run-test",
                worker_id="worker-a",
                target_id="demo",
                slice_id="demo-add-one",
                source_repo_root=Path("external/demo"),
                source_file="src/demo.c",
                function="add_one",
                source_commit="abc123",
                out_root=out_root / "workers" / "worker-a",
                repo_root=REPO_ROOT,
            )
            preflight_report = write_passing_opencode_preflight_report(
                out_root / "harness" / "opencode-preflight-report.json",
                run_id="run-test",
                opencode_variant="lite",
            )
            calls: list[list[str]] = []

            def fake_runner(argv: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
                calls.append(argv)
                return subprocess.CompletedProcess(argv, 0, stdout="", stderr="")

            with self.assertRaisesRegex(SystemExit, "opencode_variant must be max"):
                harness.run_worker(
                    db_path=db_path,
                    run_id="run-test",
                    worker_id="worker-a",
                    mode="opencode",
                    opencode_preflight_report=preflight_report,
                    opencode_variant="lite",
                    command_runner=fake_runner,
                    repo_root=REPO_ROOT,
                )

            self.assertEqual(calls, [])

    def test_run_worker_opencode_rejects_preflight_report_run_id_mismatch_before_launch(self) -> None:
        with temp_repo_dir() as tmp:
            out_root = Path(tmp) / "competition-out"
            db_path = harness.init_run(
                out_root=out_root,
                run_id="run-test",
                proof_class="local-simulation",
                repo_root=REPO_ROOT,
            )
            harness.assign_slice(
                db_path=db_path,
                run_id="run-test",
                worker_id="worker-a",
                target_id="demo",
                slice_id="demo-add-one",
                source_repo_root=Path("external/demo"),
                source_file="src/demo.c",
                function="add_one",
                source_commit="abc123",
                out_root=out_root / "workers" / "worker-a",
                repo_root=REPO_ROOT,
            )
            preflight_report = write_passing_opencode_preflight_report(
                out_root / "harness" / "opencode-preflight-report.json",
                run_id="previous-run",
            )
            calls: list[list[str]] = []

            def fake_runner(argv: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
                calls.append(argv)
                return subprocess.CompletedProcess(argv, 0, stdout="", stderr="")

            with self.assertRaisesRegex(SystemExit, "opencode preflight run_id mismatch"):
                harness.run_worker(
                    db_path=db_path,
                    run_id="run-test",
                    worker_id="worker-a",
                    mode="opencode",
                    opencode_preflight_report=preflight_report,
                    command_runner=fake_runner,
                    repo_root=REPO_ROOT,
                )

            self.assertEqual(calls, [])

    def test_run_plan_opencode_rejects_preflight_launch_policy_mismatch_before_worker_fanout(self) -> None:
        with temp_repo_dir() as tmp:
            out_root = Path(tmp) / "competition-out"
            db_path = harness.init_run(
                out_root=out_root,
                run_id="run-test",
                proof_class="local-simulation",
                repo_root=REPO_ROOT,
            )
            source_root = out_root / "external" / "demo"
            source_file = source_root / "src" / "demo.c"
            source_file.parent.mkdir(parents=True, exist_ok=True)
            source_file.write_text("int first(void) { return 1; }\nint second(void) { return 2; }\n", encoding="utf-8")
            plan = harness.plan_source_file(
                db_path=db_path,
                run_id="run-test",
                target_id="demo",
                source_repo_root=source_root,
                source_file="src/demo.c",
                functions=[],
                source_commit="abc123",
                out_root=out_root,
                slice_id_prefix="demo",
                repo_root=REPO_ROOT,
            )
            preflight_report = write_passing_opencode_preflight_report(
                out_root / "harness" / "opencode-preflight-report.json",
                run_id="run-test",
            )

            with patch.object(harness, "run_worker") as runner:
                with self.assertRaisesRegex(SystemExit, "opencode_variant must be max"):
                    harness.run_plan(
                        db_path=db_path,
                        run_id="run-test",
                        plan_path=Path(str(plan["plan_path"])),
                        out_root=out_root,
                        proof_class="local-simulation",
                        mode="opencode",
                        opencode_preflight_report=preflight_report,
                        opencode_model="GLM-5.1",
                        opencode_variant="lite",
                        command_runner=lambda argv, **kwargs: subprocess.CompletedProcess(argv, 0, stdout="", stderr=""),
                        repo_root=REPO_ROOT,
                    )

            runner.assert_not_called()

    def test_run_plan_opencode_rejects_preflight_report_run_id_mismatch_before_worker_fanout(self) -> None:
        with temp_repo_dir() as tmp:
            out_root = Path(tmp) / "competition-out"
            db_path = harness.init_run(
                out_root=out_root,
                run_id="run-test",
                proof_class="local-simulation",
                repo_root=REPO_ROOT,
            )
            source_root = out_root / "external" / "demo"
            source_file = source_root / "src" / "demo.c"
            source_file.parent.mkdir(parents=True, exist_ok=True)
            source_file.write_text("int first(void) { return 1; }\n", encoding="utf-8")
            plan = harness.plan_source_file(
                db_path=db_path,
                run_id="run-test",
                target_id="demo",
                source_repo_root=source_root,
                source_file="src/demo.c",
                functions=[],
                source_commit="abc123",
                out_root=out_root,
                slice_id_prefix="demo",
                repo_root=REPO_ROOT,
            )
            preflight_report = write_passing_opencode_preflight_report(
                out_root / "harness" / "opencode-preflight-report.json",
                run_id="previous-run",
            )

            with patch.object(
                harness,
                "run_worker",
                return_value={
                    "worker_id": "worker-001",
                    "exit_code": 0,
                    "process_returncode": 0,
                    "summary_status": "passed",
                    "summary_path": "target/out/workers/worker-001/summary/competition-run-summary.json",
                    "report_path": "target/out/workers/worker-001/harness/run-worker-report.json",
                    "recorded": True,
                },
            ) as runner:
                with self.assertRaisesRegex(SystemExit, "opencode preflight run_id mismatch"):
                    harness.run_plan(
                        db_path=db_path,
                        run_id="run-test",
                        plan_path=Path(str(plan["plan_path"])),
                        out_root=out_root,
                        proof_class="local-simulation",
                        mode="opencode",
                        opencode_preflight_report=preflight_report,
                        command_runner=lambda argv, **kwargs: subprocess.CompletedProcess(argv, 0, stdout="", stderr=""),
                        repo_root=REPO_ROOT,
                    )

            runner.assert_not_called()

    def test_run_worker_opencode_binds_passing_preflight_report(self) -> None:
        with temp_repo_dir() as tmp:
            out_root = Path(tmp) / "competition-out"
            db_path = harness.init_run(
                out_root=out_root,
                run_id="run-test",
                proof_class="local-simulation",
                repo_root=REPO_ROOT,
            )
            harness.assign_slice(
                db_path=db_path,
                run_id="run-test",
                worker_id="worker-a",
                target_id="demo",
                slice_id="demo-add-one",
                source_repo_root=Path("external/demo"),
                source_file="src/demo.c",
                function="add_one",
                source_commit="abc123",
                out_root=out_root / "workers" / "worker-a",
                repo_root=REPO_ROOT,
            )
            preflight_report = write_passing_opencode_preflight_report(
                out_root / "harness" / "opencode-preflight-report.json",
                run_id="run-test",
            )

            def fake_runner(argv: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
                contract = json.loads(
                    (out_root / "workers" / "worker-a" / "harness" / "opencode-handoff-contract.json").read_text(
                        encoding="utf-8"
                    )
                )
                request = json.loads((REPO_ROOT / contract["request_path"]).read_text(encoding="utf-8"))
                summary_path = REPO_ROOT / request["out_root"] / "summary" / "competition-run-summary.json"
                write_worker_summary(summary_path, request["run_id"], status="passed", failed=0, semantic_pass=1)
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

            result = harness.run_worker(
                db_path=db_path,
                run_id="run-test",
                worker_id="worker-a",
                mode="opencode",
                opencode_preflight_report=preflight_report,
                command_runner=fake_runner,
                repo_root=REPO_ROOT,
            )

            self.assertEqual(result["exit_code"], 0)
            self.assertEqual(result["opencode_preflight_report"]["path"], repo_rel(preflight_report))
            self.assertEqual(result["opencode_preflight_report"]["sha256"], harness.sha256_file(preflight_report))
            self.assertEqual(result["opencode_preflight_report"]["launch_policy"]["opencode_variant"], "max")
            self.assertFalse(result["opencode_preflight_report"]["launch_policy"]["opencode_skip_permissions"])
            report = json.loads((REPO_ROOT / result["report_path"]).read_text(encoding="utf-8"))
            self.assertEqual(report["opencode_preflight_report"]["status"], "passed")
            event_payload = json.loads(
                fetch_rows(db_path, "select payload_json from events where event_type='worker_executed'")[-1][0]
            )
            self.assertEqual(event_payload["opencode_preflight_report"]["path"], repo_rel(preflight_report))
            artifact_rows = fetch_rows(db_path, "select kind, repo_rel_path, semantic_role from artifacts")
            self.assertIn(
                ("opencode-preflight-report", repo_rel(preflight_report), "agent-preflight-evidence"),
                artifact_rows,
            )

    def test_run_worker_opencode_retries_transient_database_lock_before_contract_failure(self) -> None:
        with temp_repo_dir() as tmp:
            out_root = Path(tmp) / "competition-out"
            db_path = harness.init_run(
                out_root=out_root,
                run_id="run-test",
                proof_class="local-simulation",
                repo_root=REPO_ROOT,
            )
            harness.assign_slice(
                db_path=db_path,
                run_id="run-test",
                worker_id="worker-a",
                target_id="demo",
                slice_id="demo-add-one",
                source_repo_root=Path("external/demo"),
                source_file="src/demo.c",
                function="add_one",
                source_commit="abc123",
                out_root=out_root / "workers" / "worker-a",
                repo_root=REPO_ROOT,
            )
            preflight_report = write_passing_opencode_preflight_report(out_root / "harness" / "opencode-preflight-report.json", run_id="run-test")
            calls: list[list[str]] = []

            def fake_runner(argv: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
                calls.append(argv)
                if len(calls) == 1:
                    return subprocess.CompletedProcess(argv, 1, stdout="", stderr="database is locked\n")
                contract = json.loads(
                    (out_root / "workers" / "worker-a" / "harness" / "opencode-handoff-contract.json").read_text(
                        encoding="utf-8"
                    )
                )
                request = json.loads((REPO_ROOT / contract["request_path"]).read_text(encoding="utf-8"))
                summary_path = REPO_ROOT / request["out_root"] / "summary" / "competition-run-summary.json"
                write_worker_summary(summary_path, request["run_id"], status="passed", failed=0, semantic_pass=1)
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

            result = harness.run_worker(
                db_path=db_path,
                run_id="run-test",
                worker_id="worker-a",
                mode="opencode",
                opencode_preflight_report=preflight_report,
                command_runner=fake_runner,
                repo_root=REPO_ROOT,
            )

            self.assertEqual(result["exit_code"], 0)
            self.assertEqual(len(calls), 2)
            self.assertEqual(result["opencode_process_retries"]["transient_lock_retry_count"], 1)
            self.assertEqual(result["opencode_process_retries"]["status"], "recovered")
            report = json.loads((REPO_ROOT / result["report_path"]).read_text(encoding="utf-8"))
            self.assertEqual(report["opencode_process_retries"], result["opencode_process_retries"])
            event_payload = json.loads(
                fetch_rows(db_path, "select payload_json from events where event_type='worker_executed'")[-1][0]
            )
            self.assertEqual(event_payload["opencode_process_retries"], result["opencode_process_retries"])

    def test_run_worker_opencode_database_lock_after_worker_command_does_not_retry(self) -> None:
        with temp_repo_dir() as tmp:
            out_root = Path(tmp) / "competition-out"
            db_path = harness.init_run(
                out_root=out_root,
                run_id="run-test",
                proof_class="local-simulation",
                repo_root=REPO_ROOT,
            )
            harness.assign_slice(
                db_path=db_path,
                run_id="run-test",
                worker_id="worker-a",
                target_id="demo",
                slice_id="demo-add-one",
                source_repo_root=Path("external/demo"),
                source_file="src/demo.c",
                function="add_one",
                source_commit="abc123",
                out_root=out_root / "workers" / "worker-a",
                repo_root=REPO_ROOT,
            )
            preflight_report = write_passing_opencode_preflight_report(
                out_root / "harness" / "opencode-preflight-report.json",
                run_id="run-test",
            )
            calls: list[list[str]] = []

            def fake_runner(argv: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
                calls.append(argv)
                contract = json.loads(
                    (out_root / "workers" / "worker-a" / "harness" / "opencode-handoff-contract.json").read_text(
                        encoding="utf-8"
                    )
                )
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
                return subprocess.CompletedProcess(argv, 1, stdout=stdout + "\n", stderr="database is locked\n")

            with patch.object(harness.time, "sleep", return_value=None):
                result = harness.run_worker(
                    db_path=db_path,
                    run_id="run-test",
                    worker_id="worker-a",
                    mode="opencode",
                    opencode_preflight_report=preflight_report,
                    command_runner=fake_runner,
                    repo_root=REPO_ROOT,
                )

            self.assertEqual(len(calls), 1)
            self.assertEqual(result["exit_code"], 1)
            self.assertEqual(result["process_returncode"], 1)
            self.assertNotIn("opencode_process_retries", result)
            self.assertEqual(result["opencode_contract_verification"]["status"], "executed")
            self.assertEqual(
                result["repair_hint"]["root_cause_key"],
                "opencode_database_locked_after_worker_command_seen",
            )

    def test_run_plan_opencode_passes_preflight_report_to_workers(self) -> None:
        with temp_repo_dir() as tmp:
            out_root = Path(tmp) / "competition-out"
            db_path = harness.init_run(
                out_root=out_root,
                run_id="run-test",
                proof_class="local-simulation",
                repo_root=REPO_ROOT,
            )
            source_root = out_root / "external" / "demo"
            source_file = source_root / "src" / "demo.c"
            source_file.parent.mkdir(parents=True, exist_ok=True)
            source_file.write_text("int first(void) { return 1; }\nint second(void) { return 2; }\n", encoding="utf-8")
            plan = harness.plan_source_file(
                db_path=db_path,
                run_id="run-test",
                target_id="demo",
                source_repo_root=source_root,
                source_file="src/demo.c",
                functions=[],
                source_commit="abc123",
                out_root=out_root,
                slice_id_prefix="demo",
                worker_prefix="worker",
                repo_root=REPO_ROOT,
            )
            preflight_report = write_passing_opencode_preflight_report(
                out_root / "harness" / "opencode-preflight-report.json",
                run_id="run-test",
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
                    "process_returncode": 0,
                    "summary_status": "passed",
                    "summary_path": "",
                    "report_path": "target/report.json",
                    "logs": {"stdout": "target/stdout.log", "stderr": "target/stderr.log"},
                    "recorded": False,
                    "handoff_contract": handoff_contract,
                    "opencode_session_evidence": session_evidence,
                    "opencode_contract_verification": contract_verification,
                    "opencode_preflight_report": preflight_binding,
                },
            ) as runner:
                result = harness.run_plan(
                    db_path=db_path,
                    run_id="run-test",
                    plan_path=Path(str(plan["plan_path"])),
                    out_root=out_root,
                    proof_class="local-simulation",
                    mode="opencode",
                    opencode_preflight_report=preflight_report,
                    repo_root=REPO_ROOT,
                )

            self.assertEqual(runner.call_count, 2)
            for call in runner.call_args_list:
                self.assertEqual(call.kwargs["opencode_preflight_report"], preflight_report)
            self.assertEqual(result["opencode_preflight_report"]["path"], repo_rel(preflight_report))
            self.assertEqual(result["opencode_preflight_report"]["sha256"], harness.sha256_file(preflight_report))
            self.assertEqual(result["opencode_preflight_report"]["launch_policy"]["opencode_variant"], "max")
            self.assertFalse(result["opencode_preflight_report"]["launch_policy"]["opencode_skip_permissions"])
            self.assertEqual(result["graph"]["opencode_worker"]["preflight_report"]["status"], "passed")
            self.assertEqual(result["graph"]["opencode_worker"]["preflight_report"]["contract_status"], "executed")
            self.assertEqual(result["graph"]["opencode_worker"]["opencode_variant"], "max")
            first_attempt = result["workers"][0]["attempts"][0]
            self.assertEqual(first_attempt["handoff_contract"], handoff_contract)
            self.assertEqual(first_attempt["opencode_session_evidence"], session_evidence)
            self.assertEqual(first_attempt["opencode_contract_verification"], contract_verification)
            self.assertEqual(first_attempt["opencode_preflight_report"], preflight_binding)
            report = json.loads((out_root / "harness" / "run-plan-report.json").read_text(encoding="utf-8"))
            self.assertEqual(report["opencode_preflight_report"], result["opencode_preflight_report"])

    def test_run_worker_ignores_stale_summary_from_before_execution(self) -> None:
        with temp_repo_dir() as tmp:
            out_root = Path(tmp) / "competition-out"
            db_path = harness.init_run(
                out_root=out_root,
                run_id="run-test",
                proof_class="local-simulation",
                repo_root=REPO_ROOT,
            )
            harness.assign_slice(
                db_path=db_path,
                run_id="run-test",
                worker_id="worker-a",
                target_id="demo",
                slice_id="demo-add-one",
                source_repo_root=Path("external/demo"),
                source_file="src/demo.c",
                function="add_one",
                source_commit="abc123",
                out_root=out_root / "workers" / "worker-a",
                repo_root=REPO_ROOT,
            )
            stale_summary = out_root / "workers" / "worker-a" / "summary" / "competition-run-summary.json"
            write_worker_summary(stale_summary, "stale-run", status="passed", failed=0, semantic_pass=1)

            def fake_runner(argv: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
                return subprocess.CompletedProcess(argv, 0, stdout="did not write summary\n", stderr="")

            result = harness.run_worker(
                db_path=db_path,
                run_id="run-test",
                worker_id="worker-a",
                command_runner=fake_runner,
                repo_root=REPO_ROOT,
            )

            self.assertEqual(result["exit_code"], 1)
            self.assertFalse(result["recorded"])
            self.assertEqual(result["summary_status"], "missing-summary")
            self.assertFalse(stale_summary.exists())

    def test_retry_worker_consumes_repair_hint_and_marks_revalidated_passed(self) -> None:
        with temp_repo_dir() as tmp:
            out_root = Path(tmp) / "competition-out"
            db_path = harness.init_run(
                out_root=out_root,
                run_id="run-test",
                proof_class="local-simulation",
                repo_root=REPO_ROOT,
            )
            harness.assign_slice(
                db_path=db_path,
                run_id="run-test",
                worker_id="worker-a",
                target_id="demo",
                slice_id="demo-add-one",
                source_repo_root=Path("external/demo"),
                source_file="src/demo.c",
                function="add_one",
                source_commit="abc123",
                out_root=out_root / "workers" / "worker-a",
                repo_root=REPO_ROOT,
            )
            call_count = 0

            def fake_runner(argv: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
                nonlocal call_count
                call_count += 1
                request_path = REPO_ROOT / argv[argv.index("--input") + 1]
                request = json.loads(request_path.read_text(encoding="utf-8"))
                summary_path = REPO_ROOT / request["out_root"] / "summary" / "competition-run-summary.json"
                if call_count == 1:
                    write_worker_summary(summary_path, request["run_id"], status="failed", failed=1, semantic_pass=0)
                else:
                    write_worker_summary(summary_path, request["run_id"], status="passed", failed=0, semantic_pass=1)
                return subprocess.CompletedProcess(argv, 0, stdout=f"worker attempt {call_count}\n", stderr="")

            first = harness.run_worker(
                db_path=db_path,
                run_id="run-test",
                worker_id="worker-a",
                command_runner=fake_runner,
                repo_root=REPO_ROOT,
            )
            self.assertEqual(first["exit_code"], 1)
            hint_id = fetch_rows(db_path, "select hint_id from repair_hints")[0][0]

            retry = harness.retry_worker(
                db_path=db_path,
                run_id="run-test",
                worker_id="worker-a",
                hint_id=hint_id,
                command_runner=fake_runner,
                repo_root=REPO_ROOT,
            )

            self.assertEqual(retry["exit_code"], 0)
            self.assertEqual(retry["hint_status"], "revalidated_passed")
            self.assertEqual(call_count, 2)
            hint_rows = fetch_rows(db_path, "select status from repair_hints where hint_id=?", (hint_id,))
            self.assertEqual(hint_rows, [("revalidated_passed",)])

    def test_retry_worker_enforces_five_round_cap_without_launching_worker(self) -> None:
        with temp_repo_dir() as tmp:
            out_root = Path(tmp) / "competition-out"
            db_path = harness.init_run(
                out_root=out_root,
                run_id="run-test",
                proof_class="local-simulation",
                repo_root=REPO_ROOT,
            )
            harness.assign_slice(
                db_path=db_path,
                run_id="run-test",
                worker_id="worker-a",
                target_id="demo",
                slice_id="demo-add-one",
                source_repo_root=Path("external/demo"),
                source_file="src/demo.c",
                function="add_one",
                source_commit="abc123",
                out_root=out_root / "workers" / "worker-a",
                repo_root=REPO_ROOT,
            )

            def failing_runner(argv: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
                return subprocess.CompletedProcess(argv, 1, stdout="", stderr="error[E0308]: mismatched types\n")

            first = harness.run_worker(
                db_path=db_path,
                run_id="run-test",
                worker_id="worker-a",
                command_runner=failing_runner,
                repo_root=REPO_ROOT,
            )
            self.assertEqual(first["exit_code"], 1)
            hint_id = fetch_rows(db_path, "select hint_id from repair_hints")[0][0]
            payload = json.loads(fetch_rows(db_path, "select payload_json from repair_hints where hint_id=?", (hint_id,))[0][0])
            payload["attempts"] = [
                {
                    "attempt": attempt,
                    "summary_status": "failed",
                    "process_returncode": 1,
                    "exit_code": 1,
                    "summary_path": first["summary_path"],
                    "worker_report_path": first["report_path"],
                    "logs": first["logs"],
                }
                for attempt in range(1, 7)
            ]
            connection = sqlite3.connect(db_path)
            try:
                connection.execute(
                    "update repair_hints set payload_json=? where hint_id=?",
                    (json.dumps(payload, sort_keys=True), hint_id),
                )
                connection.commit()
            finally:
                connection.close()
            call_count = 0

            def should_not_run(argv: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
                nonlocal call_count
                call_count += 1
                return subprocess.CompletedProcess(argv, 0, stdout="", stderr="")

            retry = harness.retry_worker(
                db_path=db_path,
                run_id="run-test",
                worker_id="worker-a",
                hint_id=hint_id,
                command_runner=should_not_run,
                repo_root=REPO_ROOT,
            )

            self.assertEqual(call_count, 0)
            self.assertEqual(retry["exit_code"], 1)
            self.assertEqual(retry["hint_status"], "retry_limit_exceeded")
            self.assertEqual(retry["repair_round_cap"], 5)
            payload = json.loads(fetch_rows(db_path, "select payload_json from repair_hints where hint_id=?", (hint_id,))[0][0])
            self.assertEqual(payload["status"], "retry_limit_exceeded")
            self.assertEqual(payload["retry_limit"]["max_repair_rounds"], 5)

    def test_retry_worker_records_attempt_history_and_rollback_evidence(self) -> None:
        with temp_repo_dir() as tmp:
            out_root = Path(tmp) / "competition-out"
            db_path = harness.init_run(
                out_root=out_root,
                run_id="run-test",
                proof_class="local-simulation",
                repo_root=REPO_ROOT,
            )
            harness.assign_slice(
                db_path=db_path,
                run_id="run-test",
                worker_id="worker-a",
                target_id="demo",
                slice_id="demo-add-one",
                source_repo_root=Path("external/demo"),
                source_file="src/demo.c",
                function="add_one",
                source_commit="abc123",
                out_root=out_root / "workers" / "worker-a",
                repo_root=REPO_ROOT,
            )
            call_count = 0
            seen_requests: list[dict[str, object]] = []
            repair_trace = {"mode": "baseline_repair_gate"}

            def fake_runner(argv: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
                nonlocal call_count
                call_count += 1
                request_path = REPO_ROOT / argv[argv.index("--input") + 1]
                request = json.loads(request_path.read_text(encoding="utf-8"))
                seen_requests.append({"path": request_path, "request": request})
                summary_path = REPO_ROOT / request["out_root"] / "summary" / "competition-run-summary.json"
                if call_count == 1:
                    write_worker_summary(summary_path, request["run_id"], status="failed", failed=1, semantic_pass=0)
                else:
                    write_worker_summary(summary_path, request["run_id"], status="passed", failed=0, semantic_pass=1)
                return subprocess.CompletedProcess(argv, 0, stdout=f"worker attempt {call_count}\n", stderr="")

            first = harness.run_worker(
                db_path=db_path,
                run_id="run-test",
                worker_id="worker-a",
                command_runner=fake_runner,
                repo_root=REPO_ROOT,
                repair_trace=repair_trace,
            )
            self.assertEqual(first["exit_code"], 1)
            hint_id = fetch_rows(db_path, "select hint_id from repair_hints")[0][0]

            retry = harness.retry_worker(
                db_path=db_path,
                run_id="run-test",
                worker_id="worker-a",
                hint_id=hint_id,
                command_runner=fake_runner,
                repo_root=REPO_ROOT,
                repair_trace=repair_trace,
            )

            self.assertEqual(retry["exit_code"], 0)
            self.assertEqual([item["request"]["harness_attempt_number"] for item in seen_requests], [1, 2])
            self.assertEqual(seen_requests[0]["request"]["harness_repair_trace"], repair_trace)
            self.assertNotIn("harness_repair_hint_id", seen_requests[0]["request"])
            self.assertEqual(seen_requests[1]["request"]["harness_repair_hint_id"], hint_id)
            self.assertEqual(seen_requests[1]["request"]["harness_retry_of"], hint_id)
            self.assertEqual(seen_requests[0]["path"].name, "worker-a-request-attempt-1.json")
            self.assertEqual(seen_requests[1]["path"].name, "worker-a-request-attempt-2.json")
            payload = json.loads(fetch_rows(db_path, "select payload_json from repair_hints where hint_id=?", (hint_id,))[0][0])
            self.assertEqual(payload["status"], "revalidated_passed")
            self.assertEqual([attempt["attempt"] for attempt in payload["attempts"]], [1, 2])
            self.assertEqual([attempt["summary_status"] for attempt in payload["attempts"]], ["failed", "passed"])
            self.assertEqual(payload["attempts"][0]["root_cause_key"], "final_gate_failed")
            self.assertEqual(payload["attempts"][1]["retry_of"], hint_id)
            rollback_path = REPO_ROOT / payload["attempts"][1]["rollback_evidence"]["path"]
            self.assertTrue(rollback_path.exists())
            rollback = json.loads(rollback_path.read_text(encoding="utf-8"))
            self.assertEqual(rollback["hint_id"], hint_id)
            self.assertEqual(rollback["worker_id"], "worker-a")
            self.assertEqual(rollback["action"], "removed_stale_summary_before_retry")
            self.assertEqual(rollback["removed_summary"]["path"], first["summary_path"])
            self.assertRegex(rollback["removed_summary"]["sha256"], r"^[0-9a-f]{64}$")
            self.assertEqual(rollback["last_good"]["status"], "not_available")
            events = [
                (event_type, json.loads(payload_json))
                for event_type, payload_json in fetch_rows(
                    db_path,
                    "select event_type, payload_json from events where event_type='worker_executed' order by event_id",
                )
            ]
            self.assertEqual([event[1]["attempt"] for event in events], [1, 2])
            self.assertEqual(events[1][1]["retry_of"], hint_id)
            self.assertEqual(events[1][1]["rollback_evidence"]["path"], payload["attempts"][1]["rollback_evidence"]["path"])
