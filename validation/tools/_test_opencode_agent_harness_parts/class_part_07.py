class _OpenCodeAgentHarnessTestPart07:
    def test_opencode_run_worker_classifies_wrong_shell_command_as_contract_not_executed(self) -> None:
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

            wrong_command = (
                "python -m validation.tools.opencode_agent_harness init-run "
                "--out-root target/competition-out --run-id wrong-run --proof-class local-simulation"
            )
            stdout = json.dumps(
                {
                    "type": "tool_use",
                    "part": {
                        "tool": "bash",
                        "state": {
                            "input": {"command": wrong_command},
                            "status": "completed",
                        },
                    },
                }
            )

            def fake_runner(argv: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
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

            self.assertEqual(result["summary_status"], "blocked")
            self.assertEqual(result["repair_hint"]["root_cause_key"], "opencode_contract_not_executed")
            verification = result["opencode_contract_verification"]
            self.assertEqual(verification["status"], "not-executed")
            self.assertFalse(verification["worker_command_seen"])
            self.assertEqual(verification["executed_shell_commands"], [wrong_command])
            hint_payload = json.loads(fetch_rows(db_path, "select payload_json from repair_hints")[0][0])
            self.assertEqual(hint_payload["root_cause_key"], "opencode_contract_not_executed")
            self.assertEqual(hint_payload["opencode_contract_verification"]["status"], "not-executed")

    def test_opencode_contract_failure_writes_blocked_worker_summary_for_parent_merge(self) -> None:
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
            wrong_command = "python -m validation.tools.opencode_agent_harness init-run --run-id wrong"
            stdout = json.dumps(
                {
                    "type": "tool_use",
                    "part": {"tool": "bash", "state": {"input": {"command": wrong_command}, "status": "completed"}},
                }
            )

            def fake_runner(argv: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
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

            self.assertEqual(result["summary_status"], "blocked")
            self.assertTrue(result["recorded"])
            summary_path = out_root / "workers" / "worker-a" / "summary" / "competition-run-summary.json"
            summary = json.loads(summary_path.read_text(encoding="utf-8"))
            self.assertEqual(summary["final_gate"]["status"], "blocked")
            self.assertEqual(summary["slices"]["blocked"], 1)
            metrics_path = summary_path.parent / "workflow-metrics.json"
            self.assertTrue(metrics_path.exists())
            self.assertEqual(summary["workflow_metrics"]["path"], "workflow-metrics.json")
            self.assertEqual(summary["workflow_metrics"]["sha256"], harness.sha256_file(metrics_path))
            metrics = json.loads(metrics_path.read_text(encoding="utf-8"))
            self.assertEqual(metrics["fail_closed_count"], 1)
            self.assertEqual(metrics["per_unit_statuses"][0]["root_cause_key"], "opencode_contract_not_executed")
            self.assertEqual(metrics["per_unit_statuses"][0]["opencode_contract_verification"]["status"], "not-executed")

    def test_opencode_contract_failure_overrides_passing_summary(self) -> None:
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
            request_path = out_root / "harness" / "assignments" / "worker-a-request.json"
            expected_command = harness.shell_command_line(
                [
                    "python3",
                    "-B",
                    "scripts/c2rust-migrator.py",
                    "--phase",
                    "migrate",
                    "--input",
                    repo_rel(request_path),
                ]
            )
            wrong_command = "python -m validation.tools.opencode_agent_harness init-run --run-id wrong"
            stdout = "\n".join(
                [
                    json.dumps(
                        {
                            "type": "tool_use",
                            "part": {
                                "tool": "bash",
                                "state": {"input": {"command": wrong_command}, "status": "completed"},
                            },
                        }
                    ),
                    json.dumps(
                        {
                            "type": "tool_use",
                            "part": {
                                "tool": "bash",
                                "state": {"input": {"command": expected_command}, "status": "completed"},
                            },
                        }
                    ),
                ]
            )

            def fake_runner(argv: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
                summary_path = out_root / "workers" / "worker-a" / "summary" / "competition-run-summary.json"
                write_worker_summary(summary_path, "run-test", status="passed", failed=0, semantic_pass=1)
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

            self.assertEqual(result["exit_code"], 1)
            self.assertEqual(result["summary_status"], "blocked")
            self.assertEqual(result["repair_hint"]["root_cause_key"], "opencode_contract_not_executed")
            summary_path = out_root / "workers" / "worker-a" / "summary" / "competition-run-summary.json"
            summary = json.loads(summary_path.read_text(encoding="utf-8"))
            self.assertEqual(summary["final_gate"]["status"], "blocked")
            self.assertEqual(summary["slices"]["semantic_pass"], 0)
            self.assertEqual(summary["slices"]["blocked"], 1)
            report = json.loads((REPO_ROOT / result["report_path"]).read_text(encoding="utf-8"))
            self.assertEqual(report["opencode_contract_verification"]["status"], "not-executed")
            rejected = report["rejected_summary_evidence"]
            rejected_path = REPO_ROOT / rejected["path"]
            self.assertTrue(rejected_path.exists())
            rejected_payload = json.loads(rejected_path.read_text(encoding="utf-8"))
            self.assertEqual(rejected_payload["action"], "rejected_summary_due_to_opencode_contract")
            self.assertEqual(rejected_payload["rejected_summary"]["path"], repo_rel(summary_path))
            hint_payload = json.loads(fetch_rows(db_path, "select payload_json from repair_hints")[0][0])
            self.assertEqual(hint_payload["rejected_summary_evidence"], rejected)

    def test_opencode_session_evidence_parses_json_lines_stdout(self) -> None:
        with temp_repo_dir() as tmp:
            out_root = Path(tmp) / "competition-out"
            logs_dir = out_root / "workers" / "worker-a" / "logs"
            logs_dir.mkdir(parents=True)
            stdout_path = logs_dir / "stdout.log"
            stderr_path = logs_dir / "stderr.log"
            stdout = "\n".join(
                [
                    json.dumps({"type": "step_start", "sessionID": "session-1"}),
                    json.dumps({"type": "text", "part": {"text": "done"}}),
                    "",
                ]
            )
            stdout_path.write_text(stdout, encoding="utf-8")
            stderr_path.write_text("", encoding="utf-8")

            binding = harness.write_opencode_session_evidence(
                completed=subprocess.CompletedProcess(["opencode"], 0, stdout, ""),
                evidence_path=logs_dir / "opencode-session-evidence.json",
                stdout_path=stdout_path,
                stderr_path=stderr_path,
                repo_root=REPO_ROOT,
            )

            evidence = json.loads((REPO_ROOT / binding["path"]).read_text(encoding="utf-8"))
            self.assertIs(evidence["parsed"], True)
            self.assertEqual(evidence["format"], "jsonl")
            self.assertEqual(evidence["stdout_sha256"], harness.sha256_file(stdout_path))
            self.assertEqual(evidence["stderr_sha256"], harness.sha256_file(stderr_path))
            self.assertEqual([event["type"] for event in evidence["session_events"]], ["step_start", "text"])

    def test_opencode_worker_prompt_forces_exact_command_and_fresh_summary(self) -> None:
        argv = harness.build_opencode_run_argv(
            opencode_command="opencode",
            opencode_model=None,
            opencode_agent="c2rust-migrator",
            opencode_variant="max",
            opencode_skip_permissions=True,
            worker_command=[
                sys.executable,
                "scripts/c2rust-migrator.py",
                "--phase",
                "migrate",
                "--input",
                "target/out/harness/assignments/worker-a-request.json",
            ],
            request_path=REPO_ROOT / "target/out/harness/assignments/worker-a-request.json",
            summary_path=REPO_ROOT / "target/out/workers/worker-a/summary/competition-run-summary.json",
            repo_root=REPO_ROOT,
        )

        prompt = argv[-1]
        self.assertNotIn("\n", prompt)
        self.assertIn("Use the shell/bash tool to run exactly the Command line string below.", prompt)
        self.assertIn("The first shell/bash/powershell/cmd tool call must be exactly the Command line string.", prompt)
        self.assertIn("Do not run init-run, assign-slice, retry-worker, or any other substitute harness command.", prompt)
        self.assertIn("Do not inspect an existing summary before running the command.", prompt)
        self.assertNotIn("Delete the expected summary file if it already exists", prompt)
        self.assertIn("The harness has already removed any stale expected summary before launching OpenCode.", prompt)
        self.assertIn("Do not call glob/read/grep/list/edit or any non-shell tool before the exact Command line.", prompt)
        self.assertIn("Do not explore files, spawn subagents, or infer a different slice before executing the command.", prompt)
        self.assertIn("Do not run substitute diagnostics instead of the command.", prompt)
        self.assertIn("scripts/c2rust-migrator.py", prompt)

    def test_opencode_preflight_prompt_is_single_cli_argument_without_newlines(self) -> None:
        marker_command = [
            sys.executable,
            "validation/tools/opencode_agent_harness.py",
            "write-preflight-marker",
            "--marker",
            "target/out/harness/opencode-preflight-marker.json",
            "--run-id",
            "preflight-run",
        ]

        argv = harness.build_opencode_preflight_argv(
            opencode_command="opencode",
            opencode_model=None,
            opencode_agent="c2rust-migrator",
            opencode_variant="max",
            opencode_skip_permissions=True,
            marker_command=marker_command,
            marker_path=REPO_ROOT / "target/out/harness/opencode-preflight-marker.json",
            contract_path=REPO_ROOT / "target/out/harness/opencode-preflight-contract.json",
            repo_root=REPO_ROOT,
        )

        prompt = argv[-1]
        self.assertNotIn("\n", prompt)
        self.assertIn("Execute this OpenCode preflight command exactly once.", prompt)
        self.assertIn("Command line:", prompt)
        self.assertIn("write-preflight-marker", prompt)

    def test_opencode_contract_requires_first_shell_command_to_match_worker_command(self) -> None:
        worker_command = [
            sys.executable,
            "scripts/c2rust-migrator.py",
            "--phase",
            "migrate",
            "--input",
            "target/out/harness/assignments/worker-a-request.json",
        ]
        expected_command = harness.shell_command_line(worker_command)
        wrong_command = "python -m validation.tools.opencode_agent_harness init-run --run-id wrong"
        session_evidence = {
            "session_events": [
                {
                    "type": "tool_use",
                    "part": {"tool": "bash", "state": {"input": {"command": wrong_command, "workdir": str(REPO_ROOT)}}},
                },
                {
                    "type": "tool_use",
                    "part": {"tool": "bash", "state": {"input": {"command": expected_command, "workdir": str(REPO_ROOT)}}},
                },
            ],
        }

        verification = harness.verify_opencode_contract_execution(
            session_evidence=session_evidence,
            worker_command=worker_command,
            summary_path=REPO_ROOT / "target/out/workers/worker-a/summary/competition-run-summary.json",
            repo_root=REPO_ROOT,
        )

        self.assertEqual(verification["status"], "not-executed")
        self.assertTrue(verification["worker_command_seen"])
        self.assertEqual(verification["first_shell_command"], wrong_command)
        self.assertFalse(verification["first_shell_command_matches_worker_command"])
        self.assertEqual(verification["first_tool_name"], "bash")
        self.assertEqual(verification["tools_before_first_shell"], [])
        self.assertEqual(verification["contract_failure_reason"], "first_shell_command_mismatch_worker_command_seen_later")

    def test_opencode_contract_accepts_argv_equivalent_quoted_worker_command(self) -> None:
        worker_command = [
            "python3",
            "-B",
            "scripts/c2rust-migrator.py",
            "--phase",
            "migrate",
            "--input",
            "target/out/workers/worker-a/harness/worker-a-request-attempt-1.json",
        ]
        quoted_command = (
            'python3 -B scripts/c2rust-migrator.py --phase migrate --input '
            '"target/out/workers/worker-a/harness/worker-a-request-attempt-1.json"'
        )
        session_evidence = {
            "session_events": [
                {
                    "type": "tool_use",
                    "part": {"tool": "bash", "state": {"input": {"command": quoted_command, "workdir": str(REPO_ROOT)}}},
                },
            ],
        }

        verification = harness.verify_opencode_contract_execution(
            session_evidence=session_evidence,
            worker_command=worker_command,
            summary_path=REPO_ROOT / "target/out/workers/worker-a/summary/competition-run-summary.json",
            repo_root=REPO_ROOT,
        )

        self.assertEqual(verification["status"], "executed")
        self.assertTrue(verification["worker_command_seen"])
        self.assertEqual(verification["first_shell_command"], quoted_command)
        self.assertTrue(verification["first_shell_command_matches_worker_command"])
        self.assertEqual(verification["contract_failure_reason"], "")

    def test_opencode_contract_rejects_extra_shell_command_after_expected_worker_command(self) -> None:
        worker_command = [
            "python3",
            "-B",
            "scripts/c2rust-migrator.py",
            "--phase",
            "migrate",
            "--input",
            "target/out/workers/worker-a/harness/worker-a-request-attempt-1.json",
        ]
        expected_command = harness.shell_command_line(worker_command)
        extra_command = "python3 -B validation/tools/opencode_agent_harness.py init-run --run-id unexpected"
        session_evidence = {
            "session_events": [
                {
                    "type": "tool_use",
                    "part": {
                        "tool": "bash",
                        "state": {"input": {"command": expected_command, "workdir": str(REPO_ROOT)}},
                    },
                },
                {
                    "type": "tool_use",
                    "part": {
                        "tool": "bash",
                        "state": {"input": {"command": extra_command, "workdir": str(REPO_ROOT)}},
                    },
                },
            ],
        }

        verification = harness.verify_opencode_contract_execution(
            session_evidence=session_evidence,
            worker_command=worker_command,
            summary_path=REPO_ROOT / "target/out/workers/worker-a/summary/competition-run-summary.json",
            repo_root=REPO_ROOT,
        )

        self.assertEqual(verification["status"], "not-executed")
        self.assertTrue(verification["worker_command_seen"])
        self.assertEqual(verification["executed_shell_command_count"], 2)
        self.assertEqual(verification["executed_shell_commands"], [expected_command, extra_command])
        self.assertEqual(verification["contract_failure_reason"], "extra_shell_command_after_contract")

    def test_opencode_preflight_contract_accepts_post_contract_marker_inspection(self) -> None:
        with temp_repo_dir() as tmp:
            marker_path = Path(tmp) / "harness" / "opencode-preflight-marker.json"
            write_valid_preflight_marker(marker_path, run_id="preflight-run")
            worker_command = [
                "python3",
                "-B",
                "validation/tools/opencode_agent_harness.py",
                "write-preflight-marker",
                "--marker",
                repo_rel(marker_path),
                "--run-id",
                "preflight-run",
            ]
            expected_command = harness.shell_command_line(worker_command)
            inspection_command = (
                f'Get-Item -LiteralPath "{repo_rel(marker_path)}" | '
                "Select-Object FullName, Length, LastWriteTime"
            )
            session_evidence = {
                "session_events": [
                    {
                        "type": "tool_use",
                        "part": {
                            "tool": "bash",
                            "state": {"input": {"command": expected_command, "workdir": str(REPO_ROOT)}},
                        },
                    },
                    {
                        "type": "tool_use",
                        "part": {
                            "tool": "bash",
                            "state": {"input": {"command": inspection_command, "workdir": str(REPO_ROOT)}},
                        },
                    },
                ],
            }

            verification = harness.verify_opencode_contract_execution(
                session_evidence=session_evidence,
                worker_command=worker_command,
                summary_path=marker_path,
                repo_root=REPO_ROOT,
                allow_post_contract_artifact_inspection=True,
            )

        self.assertEqual(verification["status"], "executed")
        self.assertEqual(verification["contract_failure_reason"], "")
        self.assertEqual(verification["post_contract_shell_command_count"], 1)
        self.assertTrue(verification["post_contract_artifact_inspection_only"])

    def test_opencode_preflight_contract_rejects_non_inspection_extra_shell_command(self) -> None:
        with temp_repo_dir() as tmp:
            marker_path = Path(tmp) / "harness" / "opencode-preflight-marker.json"
            write_valid_preflight_marker(marker_path, run_id="preflight-run")
            worker_command = [
                "python3",
                "-B",
                "validation/tools/opencode_agent_harness.py",
                "write-preflight-marker",
                "--marker",
                repo_rel(marker_path),
                "--run-id",
                "preflight-run",
            ]
            expected_command = harness.shell_command_line(worker_command)
            session_evidence = {
                "session_events": [
                    {
                        "type": "tool_use",
                        "part": {
                            "tool": "bash",
                            "state": {"input": {"command": expected_command, "workdir": str(REPO_ROOT)}},
                        },
                    },
                    {
                        "type": "tool_use",
                        "part": {
                            "tool": "bash",
                            "state": {
                                "input": {
                                    "command": (
                                        "python3 -B validation/tools/opencode_agent_harness.py "
                                        "init-run --run-id unexpected"
                                    ),
                                    "workdir": str(REPO_ROOT),
                                },
                            },
                        },
                    },
                ],
            }

            verification = harness.verify_opencode_contract_execution(
                session_evidence=session_evidence,
                worker_command=worker_command,
                summary_path=marker_path,
                repo_root=REPO_ROOT,
                allow_post_contract_artifact_inspection=True,
            )

        self.assertEqual(verification["status"], "not-executed")
        self.assertEqual(
            verification["contract_failure_reason"],
            "non_artifact_inspection_shell_command_after_contract",
        )

    def test_opencode_contract_uses_posix_shell_join_for_prompt_and_verification(self) -> None:
        worker_command = [
            "python3",
            "-B",
            "scripts/c2rust-migrator.py",
            "--phase",
            "migrate",
            "--input",
            "target/out/workers/worker a/harness/request 1.json",
        ]
        expected_command_line = shlex.join(worker_command)
        argv = harness.build_opencode_run_argv(
            opencode_command="opencode",
            opencode_model=None,
            opencode_agent="c2rust-migrator",
            opencode_variant="max",
            opencode_skip_permissions=False,
            worker_command=worker_command,
            request_path=REPO_ROOT / "target/out/workers/worker a/harness/request 1.json",
            summary_path=REPO_ROOT / "target/out/workers/worker a/summary/competition-run-summary.json",
            repo_root=REPO_ROOT,
        )
        self.assertIn(f"Command line: {expected_command_line}", argv[-1])

        verification = harness.verify_opencode_contract_execution(
            session_evidence={
                "session_events": [
                    {
                        "type": "tool_use",
                        "part": {
                            "tool": "bash",
                            "state": {"input": {"command": expected_command_line, "workdir": str(REPO_ROOT)}},
                        },
                    }
                ]
            },
            worker_command=worker_command,
            summary_path=REPO_ROOT / "target/out/workers/worker a/summary/competition-run-summary.json",
            repo_root=REPO_ROOT,
        )

        self.assertEqual(verification["status"], "executed")
        self.assertEqual(verification["expected_worker_command_line"], expected_command_line)

    def test_portable_python_script_argv_uses_runnable_non_absolute_interpreter(self) -> None:
        argv = harness.portable_python_script_argv("-c", "print('portable-python-ok')")

        self.assertFalse(Path(argv[0]).is_absolute())
        completed = subprocess.run(
            argv,
            cwd=REPO_ROOT,
            text=True,
            encoding="utf-8",
            errors="replace",
            capture_output=True,
        )

        self.assertEqual(
            completed.returncode,
            0,
            f"argv={argv!r} stdout={completed.stdout!r} stderr={completed.stderr!r}",
        )
        self.assertIn("portable-python-ok", completed.stdout)

    def test_opencode_contract_rejects_shell_command_from_wrong_workdir(self) -> None:
        worker_command = [
            "python3",
            "-B",
            "scripts/c2rust-migrator.py",
            "--phase",
            "migrate",
            "--input",
            "target/out/workers/worker-a/harness/worker-a-request-attempt-1.json",
        ]
        session_evidence = {
            "session_events": [
                {
                    "type": "tool_use",
                    "part": {
                        "tool": "bash",
                        "state": {
                            "input": {
                                "command": harness.shell_command_line(worker_command),
                                "workdir": str(REPO_ROOT.parent / "0625ctr"),
                            }
                        },
                    },
                },
            ],
        }

        verification = harness.verify_opencode_contract_execution(
            session_evidence=session_evidence,
            worker_command=worker_command,
            summary_path=REPO_ROOT / "target/out/workers/worker-a/summary/competition-run-summary.json",
            repo_root=REPO_ROOT,
        )

        self.assertEqual(verification["status"], "not-executed")
        self.assertTrue(verification["worker_command_seen"])
        self.assertTrue(verification["first_shell_command_matches_worker_command"])
        self.assertEqual(verification["contract_failure_reason"], "opencode_workdir_mismatch")
        self.assertEqual(verification["first_shell_workdir_status"], "non_repo_root")
        self.assertEqual(verification["expected_workdir_status"], "repo_root")

    def test_opencode_contract_accepts_missing_workdir_when_expected_artifact_exists(self) -> None:
        with temp_repo_dir() as tmp:
            summary_path = Path(tmp) / "harness" / "opencode-preflight-marker.json"
            write_json(
                summary_path,
                {
                    "schema_version": 1,
                    "report_kind": "opencode-preflight-marker",
                    "status": "written",
                },
            )
            worker_command = [
                "python3",
                "-B",
                "validation/tools/opencode_agent_harness.py",
                "write-preflight-marker",
                "--marker",
                repo_rel(summary_path),
                "--run-id",
                "run-test",
            ]
            session_evidence = {
                "session_events": [
                    {
                        "type": "tool_use",
                        "part": {
                            "tool": "bash",
                            "state": {"input": {"command": harness.shell_command_line(worker_command)}},
                        },
                    },
                ],
            }

            verification = harness.verify_opencode_contract_execution(
                session_evidence=session_evidence,
                worker_command=worker_command,
                summary_path=summary_path,
                repo_root=REPO_ROOT,
            )

        self.assertEqual(verification["status"], "executed")
        self.assertTrue(verification["worker_command_seen"])
        self.assertTrue(verification["first_shell_command_matches_worker_command"])
        self.assertEqual(verification["contract_failure_reason"], "")
        self.assertEqual(verification["first_shell_workdir_status"], "repo_root_inferred_from_expected_artifact")
        self.assertTrue(verification["first_shell_workdir_matches_repo_root"])

    def test_opencode_contract_rejects_shell_command_without_workdir(self) -> None:
        worker_command = [
            "python3",
            "-B",
            "scripts/c2rust-migrator.py",
            "--phase",
            "migrate",
            "--input",
            "target/out/workers/worker-a/harness/worker-a-request-attempt-1.json",
        ]
        session_evidence = {
            "session_events": [
                {
                    "type": "tool_use",
                    "part": {
                        "tool": "bash",
                        "state": {"input": {"command": harness.shell_command_line(worker_command)}},
                    },
                },
            ],
        }

        verification = harness.verify_opencode_contract_execution(
            session_evidence=session_evidence,
            worker_command=worker_command,
            summary_path=REPO_ROOT / "target/out/workers/worker-a/summary/competition-run-summary.json",
            repo_root=REPO_ROOT,
        )

        self.assertEqual(verification["status"], "not-executed")
        self.assertTrue(verification["worker_command_seen"])
        self.assertTrue(verification["first_shell_command_matches_worker_command"])
        self.assertEqual(verification["contract_failure_reason"], "opencode_workdir_mismatch")
        self.assertEqual(verification["first_shell_workdir_status"], "non_repo_root")
        self.assertFalse(verification["first_shell_workdir_matches_repo_root"])

    def test_opencode_contract_rejects_any_tool_before_first_shell_command(self) -> None:
        worker_command = [
            sys.executable,
            "scripts/c2rust-migrator.py",
            "--phase",
            "migrate",
            "--input",
            "target/out/harness/assignments/worker-a-request.json",
        ]
        expected_command = harness.shell_command_line(worker_command)
        session_evidence = {
            "session_events": [
                {
                    "type": "tool_use",
                    "part": {"tool": "read", "state": {"input": {"file": "README.md"}}},
                },
                {
                    "type": "tool_use",
                    "part": {"tool": "bash", "state": {"input": {"command": expected_command}}},
                },
            ],
        }

        verification = harness.verify_opencode_contract_execution(
            session_evidence=session_evidence,
            worker_command=worker_command,
            summary_path=REPO_ROOT / "target/out/workers/worker-a/summary/competition-run-summary.json",
            repo_root=REPO_ROOT,
        )

        self.assertEqual(verification["status"], "not-executed")
        self.assertEqual(verification["first_tool_name"], "read")
        self.assertEqual(verification["first_shell_tool_name"], "bash")
        self.assertEqual(verification["tools_before_first_shell"], ["read"])
        self.assertEqual(verification["contract_failure_reason"], "tool_before_first_shell_command")

    def test_opencode_worker_argv_resolves_path_command_before_launch(self) -> None:
        with tempfile.TemporaryDirectory(prefix="opencode-command-shim-") as tmp:
            shim_name = "opencode.cmd" if os.name == "nt" else "opencode"
            shim_path = Path(tmp) / shim_name
            shim_path.write_text("@echo off\n" if os.name == "nt" else "#!/bin/sh\n", encoding="utf-8")
            if os.name != "nt":
                shim_path.chmod(0o755)
            old_path = os.environ.get("PATH", "")
            os.environ["PATH"] = str(Path(tmp)) + os.pathsep + old_path
            try:
                argv = harness.build_opencode_run_argv(
                    opencode_command="opencode",
                    opencode_model=None,
                    opencode_agent="c2rust-migrator",
                    opencode_variant="max",
                    opencode_skip_permissions=False,
                    worker_command=[
                        sys.executable,
                        "scripts/c2rust-migrator.py",
                        "--phase",
                        "migrate",
                        "--input",
                        "target/out/harness/assignments/worker-a-request.json",
                    ],
                    request_path=REPO_ROOT / "target/out/harness/assignments/worker-a-request.json",
                    summary_path=REPO_ROOT / "target/out/workers/worker-a/summary/competition-run-summary.json",
                    repo_root=REPO_ROOT,
                )
            finally:
                os.environ["PATH"] = old_path

            self.assertEqual(Path(argv[0]).resolve(), shim_path.resolve())

    def test_opencode_worker_argv_rejects_non_opencode_command(self) -> None:
        with self.assertRaisesRegex(SystemExit, "opencode_command must be opencode"):
            harness.build_opencode_run_argv(
                opencode_command="codex",
                opencode_model="GLM-5.1",
                opencode_agent="c2rust-migrator",
                opencode_variant="max",
                opencode_skip_permissions=False,
                worker_command=[
                    sys.executable,
                    "scripts/c2rust-migrator.py",
                    "--phase",
                    "migrate",
                    "--input",
                    "target/out/harness/assignments/worker-a-request.json",
                ],
                request_path=REPO_ROOT / "target/out/harness/assignments/worker-a-request.json",
                summary_path=REPO_ROOT / "target/out/workers/worker-a/summary/competition-run-summary.json",
                repo_root=REPO_ROOT,
            )

    def test_opencode_worker_argv_rejects_non_max_variant(self) -> None:
        with self.assertRaisesRegex(SystemExit, "opencode_variant must be max"):
            harness.build_opencode_run_argv(
                opencode_command="opencode",
                opencode_model="GLM-5.1",
                opencode_agent="c2rust-migrator",
                opencode_variant="lite",
                opencode_skip_permissions=False,
                worker_command=[
                    sys.executable,
                    "scripts/c2rust-migrator.py",
                    "--phase",
                    "migrate",
                    "--input",
                    "target/out/harness/assignments/worker-a-request.json",
                ],
                request_path=REPO_ROOT / "target/out/harness/assignments/worker-a-request.json",
                summary_path=REPO_ROOT / "target/out/workers/worker-a/summary/competition-run-summary.json",
                repo_root=REPO_ROOT,
            )

    def test_opencode_preflight_requires_exact_first_shell_command_and_marker(self) -> None:
        with temp_repo_dir() as tmp:
            out_root = Path(tmp) / "opencode-preflight"

            def fake_runner(argv: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
                if len(argv) >= 2 and argv[1] == "models":
                    return subprocess.CompletedProcess(argv, 0, stdout="GLM-5.1\n", stderr="")
                contract_path = out_root / "harness" / "opencode-preflight-contract.json"
                contract = json.loads(contract_path.read_text(encoding="utf-8"))
                marker_path = REPO_ROOT / contract["expected_marker_path"]
                write_valid_preflight_marker(marker_path, run_id="preflight-run")
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

            result = harness.run_opencode_preflight(
                out_root=out_root,
                run_id="preflight-run",
                opencode_model="GLM-5.1",
                opencode_agent="c2rust-migrator",
                opencode_skip_permissions=True,
                command_runner=fake_runner,
                repo_root=REPO_ROOT,
            )

            self.assertEqual(result["status"], "passed")
            self.assertEqual(result["exit_code"], 0)
            self.assertEqual(result["contract_verification"]["status"], "executed")
            self.assertTrue(result["marker_exists"])
            self.assertTrue((REPO_ROOT / result["marker_path"]).exists())
            report = json.loads((REPO_ROOT / result["report_path"]).read_text(encoding="utf-8"))
            self.assertEqual(report["status"], "passed")
            self.assertEqual(report["contract_verification"]["status"], "executed")
            expected_policy = {
                "opencode_command": "opencode",
                "opencode_model": "GLM-5.1",
                "opencode_agent": "c2rust-migrator",
                "opencode_variant": "max",
                "opencode_skip_permissions": True,
            }
            self.assertEqual(report["launch_policy"], expected_policy)
            self.assertRegex(report["launch_policy_sha256"], r"^[0-9a-f]{64}$")
            contract = json.loads((out_root / "harness" / "opencode-preflight-contract.json").read_text(encoding="utf-8"))
            self.assertEqual(contract["launch_policy"], expected_policy)

    def test_opencode_preflight_rejects_invalid_marker_payload(self) -> None:
        with temp_repo_dir() as tmp:
            out_root = Path(tmp) / "opencode-preflight"

            def fake_runner(argv: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
                if len(argv) >= 2 and argv[1] == "models":
                    return subprocess.CompletedProcess(argv, 0, stdout="GLM-5.1\n", stderr="")
                contract_path = out_root / "harness" / "opencode-preflight-contract.json"
                contract = json.loads(contract_path.read_text(encoding="utf-8"))
                marker_path = REPO_ROOT / contract["expected_marker_path"]
                marker_path.parent.mkdir(parents=True, exist_ok=True)
                marker_path.write_text(
                    json.dumps({"schema_version": 1, "run_id": "preflight-run", "status": "written"}, sort_keys=True)
                    + "\n",
                    encoding="utf-8",
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

            result = harness.run_opencode_preflight(
                out_root=out_root,
                run_id="preflight-run",
                command_runner=fake_runner,
                repo_root=REPO_ROOT,
            )

            self.assertEqual(result["status"], "failed")
            self.assertEqual(result["exit_code"], 1)
            self.assertEqual(result["root_cause_key"], "invalid_preflight_marker")
            self.assertEqual(result["contract_verification"]["status"], "executed")
            self.assertTrue(result["marker_exists"])
