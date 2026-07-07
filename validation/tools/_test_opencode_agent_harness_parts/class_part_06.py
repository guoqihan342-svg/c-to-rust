class _OpenCodeAgentHarnessTestPart06:
    def test_run_worker_executes_assignment_and_records_summary(self) -> None:
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
            calls: list[list[str]] = []

            def fake_runner(argv: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
                calls.append(argv)
                request_path = REPO_ROOT / argv[argv.index("--input") + 1]
                request = json.loads(request_path.read_text(encoding="utf-8"))
                summary_path = REPO_ROOT / request["out_root"] / "summary" / "competition-run-summary.json"
                summary_path.parent.mkdir(parents=True, exist_ok=True)
                summary_path.write_text(
                    json.dumps(
                        {
                            "schema_version": 1,
                            "run_id": request["run_id"],
                            "proof_class": "local-simulation",
                            "profile_id": "huawei-competition-ubuntu-24.04",
                            "profile_sha256": "0" * 64,
                            "clang_source": "missing",
                            "cargo_mirror_activation": {
                                "method": "CARGO_HOME",
                                "path": "config/competition-env/cargo",
                                "config_file": "config/competition-env/cargo/config.toml",
                            },
                            "elapsed_seconds": 0,
                            "translator_version": "test",
                            "slices": {
                                "attempted": 1,
                                "typed_ir_generated": 1,
                                "compiled": 1,
                                "semantic_pass": 1,
                                "refused": 0,
                                "blocked": 0,
                                "failed": 0,
                            },
                            "unsafe_budget": {
                                "status": "passed",
                                "total_first_party_non_test_unsafe": 0,
                                "ratio": 0,
                            },
                            "artifact_roots": [
                                "target/competition-out/evidence",
                                "target/competition-out/summary",
                                "target/competition-out/logs",
                            ],
                            "final_gate": {
                                "status": "passed",
                                "validator": "validate_auto_translation_evidence.py --require-semantic-pass",
                            },
                        },
                        sort_keys=True,
                    )
                    + "\n",
                    encoding="utf-8",
                )
                return subprocess.CompletedProcess(argv, 0, stdout="worker ok\n", stderr="")

            result = harness.run_worker(
                db_path=db_path,
                run_id="run-test",
                worker_id="worker-a",
                command_runner=fake_runner,
                repo_root=REPO_ROOT,
            )

            self.assertEqual(result["exit_code"], 0)
            self.assertTrue(result["recorded"])
            self.assertEqual(result["summary_status"], "passed")
            self.assertEqual(len(calls), 1)
            self.assertIn("scripts/c2rust-migrator.py", calls[0])
            report_path = REPO_ROOT / result["report_path"]
            self.assertTrue(report_path.exists())
            report = json.loads(report_path.read_text(encoding="utf-8"))
            self.assertEqual(report["report_kind"], "run-worker-report")
            self.assertEqual(report["mode"], "deterministic")
            self.assertEqual(report["runner_kind"], "repo-local-c2rust-migrator")
            report_rel = repo_rel(report_path)
            report_sha = harness.sha256_file(report_path)
            artifact_rows = fetch_rows(db_path, "select kind, repo_rel_path, sha256, status, semantic_role from artifacts")
            self.assertEqual(
                artifact_rows,
                [
                    (
                        "competition-run-summary",
                        repo_rel(out_root / "workers" / "worker-a" / "summary" / "competition-run-summary.json"),
                        harness.sha256_file(out_root / "workers" / "worker-a" / "summary" / "competition-run-summary.json"),
                        "passed",
                        "run-summary",
                    ),
                    (
                        "run-worker-report",
                        report_rel,
                        report_sha,
                        "passed",
                        "worker-execution-report",
                    )
                ],
            )
            event_rows = fetch_rows(db_path, "select event_type, payload_json from events order by event_id")
            self.assertIn("worker_executed", [row[0] for row in event_rows])
            worker_event = json.loads(event_rows[-1][1])
            self.assertEqual(worker_event["worker_report"], {"path": report_rel, "sha256": report_sha})
            self.assertEqual(worker_event["report_path"], report_rel)

    def test_run_worker_fails_when_recorded_summary_final_gate_fails(self) -> None:
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

            def fake_runner(argv: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
                request_path = REPO_ROOT / argv[argv.index("--input") + 1]
                request = json.loads(request_path.read_text(encoding="utf-8"))
                summary_path = REPO_ROOT / request["out_root"] / "summary" / "competition-run-summary.json"
                summary_path.parent.mkdir(parents=True, exist_ok=True)
                summary_path.write_text(
                    json.dumps(
                        {
                            "schema_version": 1,
                            "run_id": request["run_id"],
                            "proof_class": "local-simulation",
                            "profile_id": "huawei-competition-ubuntu-24.04",
                            "profile_sha256": "0" * 64,
                            "clang_source": "missing",
                            "cargo_mirror_activation": {
                                "method": "CARGO_HOME",
                                "path": "config/competition-env/cargo",
                                "config_file": "config/competition-env/cargo/config.toml",
                            },
                            "elapsed_seconds": 0,
                            "translator_version": "test",
                            "slices": {
                                "attempted": 1,
                                "typed_ir_generated": 1,
                                "compiled": 0,
                                "semantic_pass": 0,
                                "refused": 0,
                                "blocked": 0,
                                "failed": 1,
                            },
                            "unsafe_budget": {
                                "status": "passed",
                                "total_first_party_non_test_unsafe": 0,
                                "ratio": 0,
                            },
                            "artifact_roots": [
                                "target/competition-out/evidence",
                                "target/competition-out/summary",
                                "target/competition-out/logs",
                            ],
                            "final_gate": {
                                "status": "failed",
                                "validator": "validate_auto_translation_evidence.py --require-semantic-pass",
                            },
                        },
                        sort_keys=True,
                    )
                    + "\n",
                    encoding="utf-8",
                )
                return subprocess.CompletedProcess(argv, 0, stdout="worker reported success\n", stderr="")

            result = harness.run_worker(
                db_path=db_path,
                run_id="run-test",
                worker_id="worker-a",
                command_runner=fake_runner,
                repo_root=REPO_ROOT,
            )

            self.assertEqual(result["exit_code"], 1)
            self.assertTrue(result["recorded"])
            self.assertEqual(result["summary_status"], "failed")
            report = json.loads((REPO_ROOT / result["report_path"]).read_text(encoding="utf-8"))
            self.assertEqual(report["exit_code"], 1)

    def test_run_worker_records_repair_hint_when_final_gate_fails(self) -> None:
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

            def fake_runner(argv: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
                request_path = REPO_ROOT / argv[argv.index("--input") + 1]
                request = json.loads(request_path.read_text(encoding="utf-8"))
                summary_path = REPO_ROOT / request["out_root"] / "summary" / "competition-run-summary.json"
                write_worker_summary(summary_path, request["run_id"], status="failed", failed=1, semantic_pass=0)
                return subprocess.CompletedProcess(argv, 0, stdout="worker reported success\n", stderr="")

            result = harness.run_worker(
                db_path=db_path,
                run_id="run-test",
                worker_id="worker-a",
                command_runner=fake_runner,
                repo_root=REPO_ROOT,
            )

            self.assertEqual(result["exit_code"], 1)
            hint_rows = fetch_rows(
                db_path,
                "select target_id, slice_id, root_cause_key, status, payload_json from repair_hints",
            )
            self.assertEqual(len(hint_rows), 1)
            self.assertEqual(hint_rows[0][:4], ("demo", "demo-add-one", "final_gate_failed", "open"))
            payload = json.loads(hint_rows[0][4])
            self.assertEqual(payload["worker_id"], "worker-a")
            expected_retry_prefix = harness.portable_python_script_argv(
                "validation/tools/opencode_agent_harness.py",
                "retry-worker",
                "--db",
            )
            self.assertEqual(payload["retry_command"][: len(expected_retry_prefix)], expected_retry_prefix)
            self.assertEqual(payload["revalidate_gate"], "competition-run-summary.final_gate.status == passed")

    def test_run_worker_records_structured_error_stack_in_repair_hint_from_stderr(self) -> None:
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

            def fake_runner(argv: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
                stderr = (
                    "error[E0133]: call to unsafe function `std::ptr::read` is unsafe and requires unsafe block\n"
                    "  --> candidate.rs:17:9\n"
                    "Traceback (most recent call last):\n"
                    "  File \"scripts/c2rust-migrator.py\", line 42, in <module>\n"
                    "RuntimeError: rustc failed\n"
                )
                return subprocess.CompletedProcess(argv, 1, stdout="compile failed\n", stderr=stderr)

            result = harness.run_worker(
                db_path=db_path,
                run_id="run-test",
                worker_id="worker-a",
                command_runner=fake_runner,
                repo_root=REPO_ROOT,
            )

            self.assertEqual(result["exit_code"], 1)
            payload = json.loads(fetch_rows(db_path, "select payload_json from repair_hints")[0][0])
            diagnostics = payload["diagnostics"]
            self.assertEqual(diagnostics["primary_error"]["kind"], "rustc")
            self.assertEqual(diagnostics["primary_error"]["code"], "E0133")
            self.assertIn("candidate.rs:17:9", diagnostics["stderr_tail"])
            self.assertIn("RuntimeError: rustc failed", diagnostics["python_traceback"])
            self.assertEqual(payload["attempts"][0]["diagnostics"]["primary_error"]["code"], "E0133")

    def test_run_worker_stale_summary_cleanup_failure_fails_closed_without_launch(self) -> None:
        with temp_repo_dir() as tmp:
            out_root = Path(tmp) / "competition-out"
            worker_out_root = out_root / "workers" / "worker-a"
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
                out_root=worker_out_root,
                repo_root=REPO_ROOT,
            )
            summary_path = worker_out_root / "summary" / "competition-run-summary.json"
            write_worker_summary(summary_path, "run-test-worker-a", status="passed", failed=0, semantic_pass=1)
            launched = False

            def fake_runner(argv: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
                nonlocal launched
                launched = True
                return subprocess.CompletedProcess(argv, 0, stdout="unexpected launch\n", stderr="")

            original_unlink = Path.unlink

            def fail_for_stale_summary(path: Path, *args: object, **kwargs: object) -> None:
                if path.resolve() == summary_path.resolve():
                    raise PermissionError("locked stale summary")
                original_unlink(path, *args, **kwargs)

            with patch.object(Path, "unlink", fail_for_stale_summary):
                result = harness.run_worker(
                    db_path=db_path,
                    run_id="run-test",
                    worker_id="worker-a",
                    command_runner=fake_runner,
                    repo_root=REPO_ROOT,
                )

            self.assertFalse(launched)
            self.assertEqual(result["exit_code"], 1)
            self.assertEqual(result["runner_kind"], "stale-summary-cleanup")
            self.assertEqual(result["summary_status"], "stale-summary-cleanup-failed")
            self.assertFalse(result["recorded"])
            self.assertEqual(result["repair_hint"]["root_cause_key"], "stale_summary_cleanup_failed")
            stderr = (worker_out_root / "logs" / "harness-worker-executor.stderr.log").read_text(encoding="utf-8")
            self.assertIn("locked stale summary", stderr)
            hint_rows = fetch_rows(db_path, "select root_cause_key, status from repair_hints")
            self.assertEqual(hint_rows, [("stale_summary_cleanup_failed", "open")])

    def test_worker_repair_diagnostics_redacts_local_absolute_paths(self) -> None:
        with temp_repo_dir() as tmp:
            stdout_path = Path(tmp) / "stdout.log"
            stderr_path = Path(tmp) / "stderr.log"
            stdout_path.write_text(
                'tool output workdir="F:\\agent\\crustpaper\\0625ctr" failed\n',
                encoding="utf-8",
            )
            stderr_path.write_text(
                "Traceback (most recent call last):\n"
                '  File "F:\\agent\\crustpaper\\0630\\scripts\\c2rust-migrator.py", line 42, in <module>\n'
                "FileNotFoundError: missing request under /mnt/c/Users/Administrator/Desktop\n",
                encoding="utf-8",
            )

            diagnostics = harness.worker_repair_diagnostics(
                stdout_path=stdout_path,
                stderr_path=stderr_path,
                process_returncode=0,
                root_cause_key="missing_summary",
            )
            serialized = json.dumps(diagnostics, sort_keys=True)

            self.assertNotIn("F:\\agent", serialized)
            self.assertNotIn("/mnt/c/Users", serialized)
            self.assertIn("<local-absolute-path>", serialized)
            self.assertEqual(diagnostics["primary_error"]["kind"], "python")
            self.assertEqual(diagnostics["root_cause_key"], "missing_summary")

    def test_run_worker_records_report_when_worker_command_cannot_launch(self) -> None:
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

            def missing_runner(argv: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
                raise FileNotFoundError("missing opencode command")

            preflight_report = write_passing_opencode_preflight_report(
                out_root / "harness" / "opencode-preflight-report.json",
                run_id="run-test",
            )
            result = harness.run_worker(
                db_path=db_path,
                run_id="run-test",
                worker_id="worker-a",
                mode="opencode",
                opencode_preflight_report=preflight_report,
                command_runner=missing_runner,
                repo_root=REPO_ROOT,
            )

            self.assertEqual(result["exit_code"], 127)
            self.assertEqual(result["process_returncode"], 127)
            self.assertEqual(result["summary_status"], "missing-summary")
            self.assertFalse(result["recorded"])
            report = json.loads((REPO_ROOT / result["report_path"]).read_text(encoding="utf-8"))
            self.assertEqual(report["runner_kind"], "opencode-run")
            self.assertEqual(report["process_returncode"], 127)
            stderr = (REPO_ROOT / report["logs"]["stderr"]).read_text(encoding="utf-8")
            self.assertIn("missing opencode command", stderr)
            hint_rows = fetch_rows(
                db_path,
                "select target_id, slice_id, root_cause_key, status from repair_hints",
            )
            self.assertEqual(hint_rows, [("demo", "demo-add-one", "worker_process_failed", "open")])

    def test_opencode_run_worker_writes_machine_readable_handoff_contract(self) -> None:
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

            def fake_runner(argv: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
                return subprocess.CompletedProcess(argv, 0, stdout="opencode did not write summary\n", stderr="")

            preflight_report = write_passing_opencode_preflight_report(
                out_root / "harness" / "opencode-preflight-report.json",
                run_id="run-test",
            )
            result = harness.run_worker(
                db_path=db_path,
                run_id="run-test",
                worker_id="worker-a",
                mode="opencode",
                opencode_preflight_report=preflight_report,
                command_runner=fake_runner,
                repo_root=REPO_ROOT,
            )

            self.assertEqual(result["summary_status"], "blocked")
            self.assertTrue(result["recorded"])
            self.assertEqual(result["repair_hint"]["root_cause_key"], "opencode_contract_not_executed")
            report = json.loads((REPO_ROOT / result["report_path"]).read_text(encoding="utf-8"))
            self.assertEqual(report["opencode_contract_verification"]["status"], "not-observed")
            contract_binding = report["handoff_contract"]
            contract_path = REPO_ROOT / contract_binding["path"]
            self.assertTrue(contract_path.exists())
            self.assertRegex(contract_binding["sha256"], r"^[0-9a-f]{64}$")
            self.assertEqual(contract_binding["sha256"], harness.sha256_file(contract_path))
            contract = json.loads(contract_path.read_text(encoding="utf-8"))
            self.assertEqual(contract["runner_kind"], "opencode-run")
            self.assertEqual(
                contract["request_path"],
                repo_rel(out_root / "workers" / "worker-a" / "harness" / "worker-a-request-attempt-1.json"),
            )
            self.assertEqual(
                contract["assignment_request_path"],
                repo_rel(out_root / "harness" / "assignments" / "worker-a-request.json"),
            )
            self.assertEqual(
                contract["expected_summary_path"],
                repo_rel(out_root / "workers" / "worker-a" / "summary" / "competition-run-summary.json"),
            )
            expected_worker_prefix = harness.portable_python_script_argv(
                "scripts/c2rust-migrator.py",
                "--phase",
                "migrate",
            )
            self.assertEqual(contract["worker_command"][: len(expected_worker_prefix)], expected_worker_prefix)
            self.assertEqual(contract["opencode_argv"], result["argv"])
            self.assertNotIn("Read the handoff contract before running the command.", contract["prompt"])
            self.assertIn("Handoff contract is audit metadata; do not inspect it before the first command.", contract["prompt"])
            self.assertIn("Do not call glob/read/grep/list/edit or any non-shell tool before the exact Command line.", contract["prompt"])
            self.assertIn(contract_binding["path"], contract["prompt"])
            session_binding = report["opencode_session_evidence"]
            session_path = REPO_ROOT / session_binding["path"]
            self.assertTrue(session_path.exists())
            self.assertEqual(session_binding["sha256"], harness.sha256_file(session_path))
            session = json.loads(session_path.read_text(encoding="utf-8"))
            self.assertIs(session["parsed"], False)
            self.assertEqual(session["process_returncode"], 0)
            self.assertIn("opencode did not write summary", session["raw_output"])
            summary_path = out_root / "workers" / "worker-a" / "summary" / "competition-run-summary.json"
            summary = json.loads(summary_path.read_text(encoding="utf-8"))
            self.assertEqual(summary["final_gate"]["status"], "blocked")
            hint_payload = json.loads(fetch_rows(db_path, "select payload_json from repair_hints")[0][0])
            self.assertEqual(hint_payload["handoff_contract"], contract_binding)
            self.assertEqual(hint_payload["opencode_session_evidence"], session_binding)
            event_payload = json.loads(
                fetch_rows(db_path, "select payload_json from events where event_type='worker_executed'")[-1][0]
            )
            self.assertEqual(event_payload["handoff_contract"], contract_binding)
            self.assertEqual(event_payload["opencode_session_evidence"], session_binding)
            artifact_rows = fetch_rows(db_path, "select kind, repo_rel_path, semantic_role from artifacts")
            self.assertIn(
                ("opencode-handoff-contract", contract_binding["path"], "agent-command-contract"),
                artifact_rows,
            )
            self.assertIn(
                ("opencode-session-evidence", session_binding["path"], "agent-session-evidence"),
                artifact_rows,
            )

    def test_opencode_run_worker_uses_repo_local_runtime_env_contract(self) -> None:
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
            captured_env: dict[str, str] = {}

            def fake_runner(argv: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
                captured_env.update(kwargs["env"])  # type: ignore[arg-type]
                contract = json.loads(
                    (out_root / "workers" / "worker-a" / "harness" / "opencode-handoff-contract.json").read_text(
                        encoding="utf-8"
                    )
                )
                summary_path = REPO_ROOT / contract["expected_summary_path"]
                request = json.loads((REPO_ROOT / contract["request_path"]).read_text(encoding="utf-8"))
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

            preflight_report = write_passing_opencode_preflight_report(
                out_root / "harness" / "opencode-preflight-report.json",
                run_id="run-test",
            )
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
            runtime_env = result["opencode_runtime_env"]
            runtime_root = out_root / "workers" / "worker-a" / "opencode-runtime" / "worker-a"
            self.assertEqual(runtime_env["status"], "isolated")
            self.assertEqual(runtime_env["scope"], "worker-a")
            self.assertEqual(runtime_env["runtime_root"], repo_rel(runtime_root))
            self.assertEqual(runtime_env["env"]["XDG_CONFIG_HOME"], repo_rel(runtime_root / "config"))
            self.assertEqual(captured_env["XDG_CONFIG_HOME"], str(runtime_root / "config"))
            self.assertEqual(captured_env["XDG_DATA_HOME"], str(runtime_root / "data"))
            self.assertEqual(captured_env["XDG_CACHE_HOME"], str(runtime_root / "cache"))
            self.assertEqual(captured_env["TMPDIR"], str(runtime_root / "tmp"))
            self.assertEqual(captured_env["TEMP"], str(runtime_root / "tmp"))
            self.assertEqual(captured_env["TMP"], str(runtime_root / "tmp"))
            contract = json.loads(
                (out_root / "workers" / "worker-a" / "harness" / "opencode-handoff-contract.json").read_text(
                    encoding="utf-8"
                )
            )
            self.assertEqual(contract["opencode_runtime_env"], runtime_env)
            session = json.loads(
                (out_root / "workers" / "worker-a" / "logs" / "opencode-session-evidence.json").read_text(
                    encoding="utf-8"
                )
            )
            self.assertEqual(session["opencode_runtime_env"], runtime_env)
            event_payload = json.loads(
                fetch_rows(db_path, "select payload_json from events where event_type='worker_executed'")[-1][0]
            )
            self.assertEqual(event_payload["opencode_runtime_env"], runtime_env)

    def test_opencode_run_worker_binds_session_evidence_into_successful_before_after_metrics(self) -> None:
        with temp_repo_dir() as tmp:
            out_root = Path(tmp) / "competition-out"
            worker_out_root = out_root / "workers" / "worker-a"
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
                slice_id="store-add-one",
                source_repo_root=Path("external/demo"),
                source_file="src/demo.c",
                function="store_add_one",
                source_commit="abc123",
                out_root=worker_out_root,
                repo_root=REPO_ROOT,
            )

            def fake_runner(argv: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
                contract = json.loads(
                    (worker_out_root / "harness" / "opencode-handoff-contract.json").read_text(encoding="utf-8")
                )
                summary_path = REPO_ROOT / contract["expected_summary_path"]
                request = json.loads((REPO_ROOT / contract["request_path"]).read_text(encoding="utf-8"))
                write_worker_summary(
                    summary_path,
                    request["run_id"],
                    status="passed",
                    failed=0,
                    semantic_pass=1,
                    workflow_metrics=before_after_worker_metrics(worker_out_root, request["run_id"]),
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
                return subprocess.CompletedProcess(argv, 0, stdout=stdout + "\n", stderr="")

            preflight_report = write_passing_opencode_preflight_report(
                out_root / "harness" / "opencode-preflight-report.json",
                run_id="run-test",
            )
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
            self.assertEqual(result["summary_status"], "passed")
            self.assertIn("opencode_safety_transform_attempt", result)
            attempt_binding = result["opencode_safety_transform_attempt"]
            self.assertEqual(Path(attempt_binding["path"]).name, "opencode-safety-transform-attempt-1.json")
            latest_attempt = worker_out_root / "harness" / "opencode-safety-transform-attempt.json"
            self.assertTrue(latest_attempt.exists())
            attempt = json.loads((REPO_ROOT / attempt_binding["path"]).read_text(encoding="utf-8"))
            self.assertEqual(json.loads(latest_attempt.read_text(encoding="utf-8")), attempt)
            self.assertEqual(attempt["report_kind"], "opencode-safety-transform-attempt")
            self.assertEqual(attempt["status"], "accepted")
            self.assertEqual(attempt["contract_verification"]["status"], "executed")
            self.assertFalse(attempt["semantic_gate"])
            self.assertFalse(attempt["chat_output_is_evidence"])
            self.assertEqual(attempt["translation_coverage_numerator"], 0)
            self.assertEqual(
                attempt["attempt_contract"],
                {
                    "single_patch_per_round": True,
                    "max_repair_rounds": 5,
                    "semantic_gate": False,
                    "translation_coverage_numerator": 0,
                },
            )
            self.assertEqual(attempt["safety_transform_unit_count"], 1)
            safety_unit = attempt["safety_transform_units"][0]
            self.assertEqual(safety_unit["unit_id"], "demo/store-add-one")
            self.assertTrue(safety_unit["round_contract"]["single_patch_per_round"])
            self.assertEqual(safety_unit["round_contract"]["max_repair_rounds"], 5)
            self.assertEqual(safety_unit["patch_evidence"]["baseline"]["path"], "evidence/before-after/baseline-unsafe.rs")
            self.assertEqual(safety_unit["patch_evidence"]["final"]["path"], "evidence/before-after/final-safe.rs")
            self.assertEqual(safety_unit["patch_evidence"]["accepted_patch"]["path"], "evidence/before-after/accepted.patch")
            self.assertEqual(safety_unit["patch_evidence"]["patch_log"]["path"], "evidence/before-after/step-log.jsonl")
            self.assertEqual(safety_unit["verification_delta"]["oracle_evidence"]["path"], "evidence/before-after/oracle-diff.json")
            self.assertEqual(safety_unit["verification_delta"]["unsafe_reduction"]["reduced_by"], 3)
            self.assertTrue(safety_unit["verification_delta"]["compiled"])
            self.assertEqual(
                safety_unit["verification_delta"]["unsafe_scan_evidence"]["path"],
                "evidence/before-after/unsafe-scan.json",
            )
            self.assertEqual(
                safety_unit["verification_delta"]["semantic_evidence"]["schema_diff"]["path"],
                "evidence/before-after/schema-diff.json",
            )
            self.assertEqual(len(safety_unit["rounds"]), 1)
            self.assertEqual(safety_unit["rounds"][0]["round"], 1)
            self.assertEqual(safety_unit["rounds"][0]["patch"]["path"], "evidence/before-after/accepted.patch")
            self.assertEqual(safety_unit["rounds"][0]["patch_log"]["path"], "evidence/before-after/step-log.jsonl")
            self.assertEqual(safety_unit["rounds"][0]["oracle_evidence"]["path"], "evidence/before-after/oracle-diff.json")
            self.assertEqual(safety_unit["rounds"][0]["unsafe_delta"]["reduced_by"], 3)
            self.assertEqual(safety_unit["rounds"][0]["schema_diff"]["path"], "evidence/before-after/schema-diff.json")
            self.assertEqual(safety_unit["accepted_retry_hint"]["status"], "not_exercised")
            self.assertFalse(safety_unit["semantic_gate"])
            self.assertEqual(safety_unit["translation_coverage_numerator"], 0)
            metrics = json.loads((worker_out_root / "summary" / "workflow-metrics.json").read_text(encoding="utf-8"))
            unit = metrics["per_unit_statuses"][0]
            self.assertIn("handoff_contract", unit)
            self.assertIn("opencode_session_evidence", unit)
            self.assertEqual(unit["opencode_contract_verification"]["status"], "executed")
            exhibit_unit = harness.before_after_exhibit_units(metrics)[0]
            self.assertTrue(exhibit_unit["patch_origin"]["opencode_session_bound"])
            self.assertEqual(exhibit_unit["safety_loop_provenance"]["status"], "opencode_session_bound")
            artifact_rows = fetch_rows(
                db_path,
                "select sha256 from artifacts where kind='competition-run-summary' and repo_rel_path=?",
                (repo_rel(worker_out_root / "summary" / "competition-run-summary.json"),),
            )
            self.assertEqual(artifact_rows, [(harness.sha256_file(worker_out_root / "summary" / "competition-run-summary.json"),)])
            attempt_rows = fetch_rows(
                db_path,
                "select kind, repo_rel_path, semantic_role from artifacts where kind='opencode-safety-transform-attempt'",
            )
            self.assertEqual(
                attempt_rows,
                [("opencode-safety-transform-attempt", attempt_binding["path"], "agent-safety-transform-attempt")],
            )

    def test_opencode_safety_transform_attempt_binds_retry_repair_history_and_rollback(self) -> None:
        with temp_repo_dir() as tmp:
            worker_out_root = Path(tmp) / "competition-out" / "workers" / "worker-a"
            summary_path = worker_out_root / "summary" / "competition-run-summary.json"
            metrics = before_after_worker_metrics(worker_out_root, "run-test")
            rollback_path = worker_out_root / "harness" / "rollback-before-retry-demo.json"
            rollback_path.parent.mkdir(parents=True, exist_ok=True)
            rollback_path.write_text(json.dumps({"action": "removed_stale_summary_before_retry"}), encoding="utf-8")
            history_path = summary_path.parent / "retry-repair-history-demo.jsonl"
            history_path.parent.mkdir(parents=True, exist_ok=True)
            history_path.write_text(
                json.dumps({"attempt": 1, "status": "failed", "root_cause_key": "rustc_compile_failed"})
                + "\n"
                + json.dumps({"attempt": 2, "status": "verified", "summary_status": "passed"})
                + "\n",
                encoding="utf-8",
            )
            unit = metrics["per_unit_statuses"][0]
            unit["repair_rounds"] = 1
            unit["auto_recovered"] = True
            unit["root_cause_key"] = "rustc_compile_failed"
            unit["repair_history"] = {
                "patch_events_path": repo_rel(history_path),
                "patch_events_sha256": harness.sha256_file(history_path),
                "statuses": ["failed", "verified"],
                "rollback_ids": [repo_rel(rollback_path)],
                "verified": True,
            }
            write_worker_summary(
                summary_path,
                "run-test",
                status="passed",
                failed=0,
                semantic_pass=1,
                workflow_metrics=metrics,
            )

            binding = harness.write_opencode_safety_transform_attempt(
                run_id="run-test",
                worker_id="worker-a",
                attempt_number=2,
                attempt_path=worker_out_root / "harness" / "opencode-safety-transform-attempt.json",
                summary_path=summary_path,
                summary_payload=json.loads(summary_path.read_text(encoding="utf-8")),
                handoff_contract=None,
                opencode_session_evidence=None,
                opencode_contract_verification={"status": "executed"},
                repo_root=REPO_ROOT,
            )

            self.assertEqual(Path(binding["path"]).name, "opencode-safety-transform-attempt-2.json")
            latest_attempt = worker_out_root / "harness" / "opencode-safety-transform-attempt.json"
            self.assertTrue(latest_attempt.exists())
            attempt = json.loads((REPO_ROOT / binding["path"]).read_text(encoding="utf-8"))
            self.assertEqual(json.loads(latest_attempt.read_text(encoding="utf-8")), attempt)
            safety_unit = attempt["safety_transform_units"][0]
            self.assertEqual(safety_unit["accepted_retry_hint"]["status"], "revalidated_passed")
            self.assertEqual(safety_unit["accepted_retry_hint"]["repair_rounds"], 1)
            self.assertEqual(safety_unit["accepted_retry_hint"]["rollback_ids"], [repo_rel(rollback_path)])
            self.assertEqual(
                safety_unit["accepted_retry_hint"]["rollback_evidence"],
                [{"path": repo_rel(rollback_path), "sha256": harness.sha256_file(rollback_path)}],
            )
            self.assertEqual(safety_unit["repair_history"]["patch_events_sha256"], harness.sha256_file(history_path))
            self.assertEqual(safety_unit["root_cause_key"], "rustc_compile_failed")

    def test_opencode_safety_transform_attempt_does_not_accept_missing_rollback_evidence(self) -> None:
        with temp_repo_dir() as tmp:
            worker_out_root = Path(tmp) / "competition-out" / "workers" / "worker-a"
            summary_path = worker_out_root / "summary" / "competition-run-summary.json"
            metrics = before_after_worker_metrics(worker_out_root, "run-test")
            missing_rollback_path = worker_out_root / "harness" / "missing-rollback.json"
            history_path = summary_path.parent / "retry-repair-history-demo.jsonl"
            history_path.parent.mkdir(parents=True, exist_ok=True)
            history_path.write_text(
                json.dumps({"attempt": 1, "status": "failed", "root_cause_key": "rustc_compile_failed"})
                + "\n"
                + json.dumps({"attempt": 2, "status": "verified", "summary_status": "passed"})
                + "\n",
                encoding="utf-8",
            )
            unit = metrics["per_unit_statuses"][0]
            unit["repair_rounds"] = 1
            unit["auto_recovered"] = True
            unit["repair_history"] = {
                "patch_events_path": repo_rel(history_path),
                "patch_events_sha256": harness.sha256_file(history_path),
                "statuses": ["failed", "verified"],
                "rollback_ids": [repo_rel(missing_rollback_path)],
                "verified": True,
            }
            write_worker_summary(
                summary_path,
                "run-test",
                status="passed",
                failed=0,
                semantic_pass=1,
                workflow_metrics=metrics,
            )

            binding = harness.write_opencode_safety_transform_attempt(
                run_id="run-test",
                worker_id="worker-a",
                attempt_number=2,
                attempt_path=worker_out_root / "harness" / "opencode-safety-transform-attempt.json",
                summary_path=summary_path,
                summary_payload=json.loads(summary_path.read_text(encoding="utf-8")),
                handoff_contract=None,
                opencode_session_evidence=None,
                opencode_contract_verification={"status": "executed"},
                repo_root=REPO_ROOT,
            )

            attempt = json.loads((REPO_ROOT / binding["path"]).read_text(encoding="utf-8"))
            retry_hint = attempt["safety_transform_units"][0]["accepted_retry_hint"]
            self.assertEqual(retry_hint["status"], "verified")
            self.assertEqual(retry_hint["rollback_ids"], [repo_rel(missing_rollback_path)])
            self.assertEqual(retry_hint["rollback_evidence"], [{"path": repo_rel(missing_rollback_path)}])
