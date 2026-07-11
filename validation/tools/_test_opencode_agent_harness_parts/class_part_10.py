def empty_passing_route_governance_report() -> dict:
    return {
        "schema_version": 1,
        "report_kind": "route-governance-metrics",
        "status": "passed",
        "metrics": {
            "translation_coverage_numerator": 0,
            "accepted_evidence_semantic_pass_count": 0,
            "tracked_slice_gate_contexts": 0,
            "s2_workflow_metrics": {
                "run_count": 1,
                "unsafe_reduction": {
                    "status": "measured",
                    "baseline_total_unsafe": 3,
                    "current_total_unsafe": 1,
                    "reduced_by": 2,
                    "ratio": 1 / 3,
                },
                "translation_before_after": {
                    "status": "not_provided",
                    "unit_count": 0,
                    "measured_unsafe_unit_count": 0,
                    "accepted_patch_unit_count": 0,
                },
            },
        },
    }


def write_inherited_env_preflight_report(path: Path, *, run_id: str) -> Path:
    path = write_passing_opencode_preflight_report(path, run_id=run_id)
    payload = json.loads(path.read_text(encoding="utf-8"))
    credential_source = {
        "kind": "inherited-env",
        "env_name": "OPENCODE_AUTH_CONTENT",
        "present": True,
    }
    payload["launch_policy"]["opencode_credential_source"] = credential_source
    payload["launch_policy_sha256"] = harness.opencode_launch_policy_sha256(payload["launch_policy"])
    contract_path = REPO_ROOT / payload["handoff_contract"]["path"]
    contract = json.loads(contract_path.read_text(encoding="utf-8"))
    contract["launch_policy"]["opencode_credential_source"] = credential_source
    contract["launch_policy_sha256"] = harness.opencode_launch_policy_sha256(contract["launch_policy"])
    write_json(contract_path, contract)
    payload["handoff_contract"]["sha256"] = harness.sha256_file(contract_path)
    write_json(path, payload)
    return path


class _OpenCodeAgentHarnessTestPart10:
    def test_opencode_credential_source_cli_dispatches_through_worker_plan_and_batch(self) -> None:
        cases = [
            (
                "run-worker",
                ["--db", "target/state.sqlite3", "--run-id", "run-a", "--worker-id", "worker-a"],
                "run_worker",
            ),
            (
                "retry-worker",
                ["--db", "target/state.sqlite3", "--run-id", "run-a", "--worker-id", "worker-a"],
                "retry_worker",
            ),
            (
                "run-plan",
                [
                    "--db",
                    "target/state.sqlite3",
                    "--run-id",
                    "run-a",
                    "--plan",
                    "target/plan.json",
                    "--proof-class",
                    "local-simulation",
                ],
                "run_plan",
            ),
            (
                "run-batch-profile",
                [
                    "--profile",
                    "target/profile.json",
                    "--run-id",
                    "run-a",
                    "--out-root",
                    "target/out",
                ],
                "run_batch_profile",
            ),
        ]
        for subcommand, required_args, function_name in cases:
            argv = [
                "opencode_agent_harness.py",
                subcommand,
                *required_args,
                "--opencode-credential-source",
                "inherited-env",
            ]
            with self.subTest(subcommand=subcommand), patch("sys.argv", argv), patch(
                "sys.stdout",
                io.StringIO(),
            ), patch.object(
                harness,
                function_name,
                return_value={"exit_code": 0, "status": "passed"},
            ) as entrypoint:
                self.assertEqual(harness.main(), 0)
                self.assertEqual(
                    entrypoint.call_args.kwargs["opencode_credential_source"],
                    "inherited-env",
                )

    def test_opencode_runtime_process_env_removes_undeclared_credential(self) -> None:
        with temp_repo_dir() as tmp, patch.dict(
            os.environ,
            {"OPENCODE_AUTH_CONTENT": "synthetic-secret-never-persisted"},
            clear=False,
        ):
            runtime_env = harness.opencode_runtime_env_contract(
                base_root=Path(tmp) / "runtime",
                scope="worker-a",
                repo_root=REPO_ROOT,
            )
            process_env = harness.opencode_runtime_process_env(
                runtime_env,
                opencode_credential_source="none",
                repo_root=REPO_ROOT,
            )
            inherited_process_env = harness.opencode_runtime_process_env(
                runtime_env,
                opencode_credential_source="inherited-env",
                repo_root=REPO_ROOT,
            )

        self.assertNotIn("OPENCODE_AUTH_CONTENT", process_env)
        self.assertIn("OPENCODE_AUTH_CONTENT", inherited_process_env)

    def test_run_worker_inherited_env_rejects_missing_or_mismatched_preflight_without_launch(self) -> None:
        with temp_repo_dir() as tmp:
            out_root = Path(tmp) / "competition-out"
            db_path = harness.init_run(
                out_root=out_root,
                run_id="run-credential-check",
                proof_class="local-simulation",
                repo_root=REPO_ROOT,
            )
            harness.assign_slice(
                db_path=db_path,
                run_id="run-credential-check",
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
            inherited_preflight = write_inherited_env_preflight_report(
                out_root / "preflight-inherited" / "harness" / "opencode-preflight-report.json",
                run_id="run-credential-check",
            )
            calls: list[list[str]] = []

            def runner_should_not_run(argv: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
                calls.append(argv)
                raise AssertionError("worker must not launch when credential metadata is inconsistent")

            with patch.dict(os.environ, {}, clear=True), self.assertRaisesRegex(
                SystemExit,
                "OPENCODE_AUTH_CONTENT is required",
            ):
                harness.run_worker(
                    db_path=db_path,
                    run_id="run-credential-check",
                    worker_id="worker-a",
                    mode="opencode",
                    opencode_credential_source="inherited-env",
                    opencode_preflight_report=inherited_preflight,
                    command_runner=runner_should_not_run,
                    repo_root=REPO_ROOT,
                )

            none_preflight = write_passing_opencode_preflight_report(
                out_root / "preflight-none" / "harness" / "opencode-preflight-report.json",
                run_id="run-credential-check",
            )
            with patch.dict(
                os.environ,
                {"OPENCODE_AUTH_CONTENT": "synthetic-source-mismatch"},
                clear=False,
            ), self.assertRaisesRegex(SystemExit, "launch policy mismatch"):
                harness.run_worker(
                    db_path=db_path,
                    run_id="run-credential-check",
                    worker_id="worker-a",
                    mode="opencode",
                    opencode_credential_source="inherited-env",
                    opencode_preflight_report=none_preflight,
                    command_runner=runner_should_not_run,
                    repo_root=REPO_ROOT,
                )

            self.assertEqual(calls, [])

    def test_run_worker_inherited_env_redacts_all_persisted_outputs_and_fails_closed(self) -> None:
        with temp_repo_dir() as tmp:
            out_root = Path(tmp) / "competition-out"
            db_path = harness.init_run(
                out_root=out_root,
                run_id="run-redaction",
                proof_class="local-simulation",
                repo_root=REPO_ROOT,
            )
            harness.assign_slice(
                db_path=db_path,
                run_id="run-redaction",
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
            preflight_report = write_inherited_env_preflight_report(
                out_root / "preflight" / "harness" / "opencode-preflight-report.json",
                run_id="run-redaction",
            )
            secret = "synthetic-worker-secret-for-redaction"

            def fake_runner(argv: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
                self.assertIn("OPENCODE_AUTH_CONTENT", kwargs["env"])
                contract_path = out_root / "workers" / "worker-a" / "harness" / "opencode-handoff-contract.json"
                contract = json.loads(contract_path.read_text(encoding="utf-8"))
                request = json.loads((REPO_ROOT / contract["request_path"]).read_text(encoding="utf-8"))
                summary_path = REPO_ROOT / request["out_root"] / "summary" / "competition-run-summary.json"
                write_worker_summary(summary_path, request["run_id"], status="passed", failed=0, semantic_pass=1)
                summary = json.loads(summary_path.read_text(encoding="utf-8"))
                summary["credential_echo"] = secret
                write_json(summary_path, summary)
                stdout = json.dumps(
                    {
                        "type": "tool_use",
                        "message": secret,
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
                return subprocess.CompletedProcess(
                    argv,
                    0,
                    stdout=stdout + "\n",
                    stderr=f"diagnostic {secret}\n",
                )

            with patch.dict(os.environ, {"OPENCODE_AUTH_CONTENT": secret}, clear=False):
                result = harness.run_worker(
                    db_path=db_path,
                    run_id="run-redaction",
                    worker_id="worker-a",
                    mode="opencode",
                    opencode_credential_source="inherited-env",
                    opencode_preflight_report=preflight_report,
                    command_runner=fake_runner,
                    repo_root=REPO_ROOT,
                )

            credential_metadata = {
                "kind": "inherited-env",
                "env_name": "OPENCODE_AUTH_CONTENT",
                "present": True,
            }
            self.assertEqual(result["exit_code"], 1)
            self.assertEqual(result["opencode_credential_source"], credential_metadata)
            self.assertEqual(result["artifact_redaction_count"], 1)
            self.assertGreaterEqual(result["redaction_count"], 3)
            self.assertEqual(
                result["repair_hint"]["root_cause_key"],
                "opencode_credential_redacted_from_worker_artifacts",
            )
            persisted = b"\n".join(
                path.read_bytes()
                for path in out_root.rglob("*")
                if path.is_file()
            )
            self.assertNotIn(secret.encode("utf-8"), persisted)
            self.assertIn(b"[REDACTED]", persisted)

    def test_opencode_preflight_cli_dispatches_inherited_env_credential_source(self) -> None:
        argv = [
            "opencode_agent_harness.py",
            "opencode-preflight",
            "--run-id",
            "preflight-run",
            "--out-root",
            "target/opencode-preflight",
            "--opencode-credential-source",
            "inherited-env",
        ]

        with patch("sys.argv", argv), patch("sys.stdout", io.StringIO()), patch.object(
            harness,
            "run_opencode_preflight",
            return_value={"exit_code": 0, "status": "passed"},
        ) as preflight:
            self.assertEqual(harness.main(), 0)

        self.assertEqual(preflight.call_args.kwargs["opencode_credential_source"], "inherited-env")

    def test_opencode_preflight_inherited_env_fails_before_model_probe_when_missing(self) -> None:
        with temp_repo_dir() as tmp:
            calls: list[list[str]] = []

            def runner_should_not_run(argv: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
                calls.append(argv)
                raise AssertionError("OpenCode must not run without the inherited credential env")

            with patch.dict(os.environ, {}, clear=True), self.assertRaisesRegex(
                SystemExit,
                "OPENCODE_AUTH_CONTENT is required",
            ):
                harness.run_opencode_preflight(
                    out_root=Path(tmp) / "opencode-preflight",
                    run_id="preflight-run",
                    opencode_credential_source="inherited-env",
                    command_runner=runner_should_not_run,
                    repo_root=REPO_ROOT,
                )

            self.assertEqual(calls, [])

    def test_opencode_preflight_inherited_env_records_metadata_and_redacts_outputs(self) -> None:
        with temp_repo_dir() as tmp:
            out_root = Path(tmp) / "opencode-preflight"
            secret = "synthetic-opencode-secret-for-redaction"

            def fake_runner(argv: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
                if len(argv) >= 2 and argv[1] == "models":
                    return subprocess.CompletedProcess(
                        argv,
                        0,
                        stdout=f"GLM-5.1 {secret}\n",
                        stderr=f"probe diagnostic {secret}\n",
                    )
                contract_path = out_root / "harness" / "opencode-preflight-contract.json"
                contract = json.loads(contract_path.read_text(encoding="utf-8"))
                marker_path = REPO_ROOT / contract["expected_marker_path"]
                write_valid_preflight_marker(marker_path, run_id="preflight-run")
                stdout = json.dumps(
                    {
                        "type": "tool_use",
                        "message": secret,
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
                return subprocess.CompletedProcess(
                    argv,
                    0,
                    stdout=stdout + "\n",
                    stderr=f"session diagnostic {secret}\n",
                )

            with patch.dict(os.environ, {"OPENCODE_AUTH_CONTENT": secret}, clear=False):
                result = harness.run_opencode_preflight(
                    out_root=out_root,
                    run_id="preflight-run",
                    opencode_credential_source="inherited-env",
                    command_runner=fake_runner,
                    repo_root=REPO_ROOT,
                )

            credential_metadata = {
                "kind": "inherited-env",
                "env_name": "OPENCODE_AUTH_CONTENT",
                "present": True,
            }
            self.assertEqual(result["status"], "passed")
            self.assertEqual(result["launch_policy"]["opencode_credential_source"], credential_metadata)
            self.assertEqual(result["redaction_count"], 4)
            self.assertEqual(result["opencode_model_availability"]["redaction_count"], 2)
            session_path = REPO_ROOT / result["opencode_session_evidence"]["path"]
            session = json.loads(session_path.read_text(encoding="utf-8"))
            self.assertEqual(session["redaction_count"], 2)

            artifact_text = "\n".join(
                path.read_text(encoding="utf-8")
                for path in out_root.rglob("*")
                if path.is_file()
            )
            self.assertNotIn(secret, artifact_text)
            self.assertIn("[REDACTED]", artifact_text)

    def test_retry_worker_annotates_measured_unsafe_reduction_metrics_for_parent_merge(self) -> None:
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
                    write_worker_summary(
                        summary_path,
                        request["run_id"],
                        status="passed",
                        failed=0,
                        semantic_pass=1,
                        workflow_metrics=measured_unsafe_worker_metrics(request["run_id"]),
                    )
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
            summary_path = out_root / "workers" / "worker-a" / "summary" / "competition-run-summary.json"
            self.assertEqual(summary_validator.validate_summary(summary_path, repo_root=REPO_ROOT)["status"], "passed")
            summary = json.loads(summary_path.read_text(encoding="utf-8"))
            metrics_path = summary_path.parent / "workflow-metrics.json"
            metrics = json.loads(metrics_path.read_text(encoding="utf-8"))
            self.assertEqual(summary["workflow_metrics"]["sha256"], harness.sha256_file(metrics_path))
            self.assertEqual(metrics["unsafe_reduction"]["status"], "measured")
            self.assertEqual(metrics["unsafe_reduction"]["baseline_total_unsafe"], 3)
            self.assertEqual(metrics["unsafe_reduction"]["current_total_unsafe"], 1)
            self.assertEqual(metrics["unsafe_reduction"]["reduced_by"], 2)
            self.assertEqual(metrics["avg_repair_rounds"], 1.0)
            self.assertEqual(metrics["auto_recovery_rate"], 1.0)
            unit = metrics["per_unit_statuses"][0]
            self.assertEqual(unit["repair_rounds"], 1)
            self.assertTrue(unit["auto_recovered"])
            repair_history = unit["repair_history"]
            repair_history_path = REPO_ROOT / repair_history["patch_events_path"]
            self.assertTrue(repair_history_path.exists())
            self.assertEqual(repair_history["patch_events_sha256"], harness.sha256_file(repair_history_path))
            self.assertIn("verified", repair_history["statuses"])
            self.assertEqual(repair_history["rollback_ids"], [retry["rollback_evidence"]["path"]])
            payload = json.loads(fetch_rows(db_path, "select payload_json from repair_hints where hint_id=?", (hint_id,))[0][0])
            self.assertEqual(payload["status"], "revalidated_passed")
            self.assertEqual(call_count, 2)
            self.assertEqual(len(payload["attempts"]), 2)
            for attempt in payload["attempts"]:
                self.assertRegex(attempt["effective_input_sha256"], r"^[0-9a-f]{64}$")
                self.assertRegex(attempt["failure_sha256"], r"^[0-9a-f]{64}$")

    def test_retry_worker_cli_dispatches_and_returns_retry_exit_code(self) -> None:
        argv = [
            "opencode_agent_harness.py",
            "retry-worker",
            "--db",
            "target/competition-out/state/opencode-agent-harness.sqlite3",
            "--run-id",
            "run-test",
            "--worker-id",
            "worker-a",
            "--hint-id",
            "repair:run-test:worker-a:final_gate_failed",
        ]

        with patch("sys.argv", argv), patch("sys.stdout", io.StringIO()), patch.object(
            harness,
            "retry_worker",
            return_value={"exit_code": 7, "status": "retry-test"},
        ) as retry:
            self.assertEqual(harness.main(), 7)

        retry.assert_called_once()
        self.assertEqual(retry.call_args.kwargs["hint_id"], "repair:run-test:worker-a:final_gate_failed")

    def test_run_worker_rejects_missing_out_root(self) -> None:
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
            request_path = harness.assignment_file_path(db_path, "worker-a").with_name("worker-a-request.json")
            request = json.loads(request_path.read_text(encoding="utf-8"))
            del request["out_root"]
            request_path.write_text(json.dumps(request, indent=2, sort_keys=True) + "\n", encoding="utf-8")

            with self.assertRaisesRegex(SystemExit, "worker out_root is required"):
                harness.run_worker(
                    db_path=db_path,
                    run_id="run-test",
                    worker_id="worker-a",
                    repo_root=REPO_ROOT,
                )

    def test_run_worker_rejects_request_out_root_mismatch_with_ledger(self) -> None:
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
            request_path = harness.assignment_file_path(db_path, "worker-a").with_name("worker-a-request.json")
            request = json.loads(request_path.read_text(encoding="utf-8"))
            request["out_root"] = repo_rel(out_root / "workers" / "worker-b")
            request_path.write_text(json.dumps(request, indent=2, sort_keys=True) + "\n", encoding="utf-8")

            def runner_should_not_run(argv: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
                raise AssertionError("worker command should not run when request out_root mismatches ledger")

            with self.assertRaisesRegex(SystemExit, "worker request out_root .* does not match ledger"):
                harness.run_worker(
                    db_path=db_path,
                    run_id="run-test",
                    worker_id="worker-a",
                    command_runner=runner_should_not_run,
                    repo_root=REPO_ROOT,
                )

    def test_rejects_absolute_or_escaping_paths(self) -> None:
        with temp_repo_dir() as tmp:
            out_root = Path(tmp) / "competition-out"
            db_path = harness.init_run(
                out_root=out_root,
                run_id="run-test",
                proof_class="local-simulation",
                repo_root=REPO_ROOT,
            )

            with self.assertRaises(SystemExit):
                harness.assign_slice(
                    db_path=db_path,
                    run_id="run-test",
                    worker_id="worker-a",
                    target_id="demo",
                    slice_id="escape",
                    source_repo_root=Path("external/demo"),
                    source_file="../src/demo.c",
                    function="add_one",
                    source_commit="abc123",
                    out_root=out_root / "workers" / "worker-a",
                    repo_root=REPO_ROOT,
                )

            with self.assertRaises(SystemExit):
                harness.record_worker_summary(
                    db_path=db_path,
                    run_id="run-test",
                    worker_id="worker-a",
                    summary_path=Path("C:/temp/summary.json"),
                    repo_root=REPO_ROOT,
                )

    def test_retry_worker_suppresses_third_identical_non_transient_launch(self) -> None:
        with temp_repo_dir() as tmp:
            out_root = Path(tmp) / "competition-out"
            source_root = Path(tmp) / "source"
            source_root.mkdir(parents=True)
            (source_root / "demo.c").write_text("int add_one(int x) { return x + 1; }\n", encoding="utf-8")
            db_path = harness.init_run(
                out_root=out_root,
                run_id="run-no-progress",
                proof_class="local-simulation",
                repo_root=REPO_ROOT,
            )
            harness.assign_slice(
                db_path=db_path,
                run_id="run-no-progress",
                worker_id="worker-a",
                target_id="demo",
                slice_id="demo-add-one",
                source_repo_root=Path(repo_rel(source_root)),
                source_file="demo.c",
                function="add_one",
                source_commit="abc123",
                out_root=out_root / "workers" / "worker-a",
                repo_root=REPO_ROOT,
            )
            call_count = 0

            def failing_runner(argv: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
                nonlocal call_count
                call_count += 1
                request_path = REPO_ROOT / argv[argv.index("--input") + 1]
                request = json.loads(request_path.read_text(encoding="utf-8"))
                summary_path = REPO_ROOT / request["out_root"] / "summary" / "competition-run-summary.json"
                write_worker_summary(
                    summary_path,
                    request["run_id"],
                    status="failed",
                    failed=1,
                    semantic_pass=0,
                    workflow_metrics={"root_cause_counts": {"rust_type_mismatch": 1}},
                )
                return subprocess.CompletedProcess(
                    argv,
                    0,
                    stdout=f"worker attempt {call_count}\n",
                    stderr="error[E0308]: mismatched types\n",
                )

            first = harness.run_worker(
                db_path=db_path,
                run_id="run-no-progress",
                worker_id="worker-a",
                command_runner=failing_runner,
                repo_root=REPO_ROOT,
            )
            hint_id = first["repair_hint"]["hint_id"]
            second = harness.retry_worker(
                db_path=db_path,
                run_id="run-no-progress",
                worker_id="worker-a",
                hint_id=hint_id,
                command_runner=failing_runner,
                repo_root=REPO_ROOT,
                keep_open_on_failure=True,
            )
            suppressed = harness.retry_worker(
                db_path=db_path,
                run_id="run-no-progress",
                worker_id="worker-a",
                hint_id=hint_id,
                command_runner=failing_runner,
                repo_root=REPO_ROOT,
                keep_open_on_failure=True,
            )

            self.assertEqual(first["exit_code"], 1)
            self.assertEqual(second["exit_code"], 1)
            self.assertEqual(call_count, 2)
            self.assertEqual(suppressed["status"], "retry_suppressed_no_progress")
            self.assertEqual(suppressed["final_decision"], {"status": "refused", "reason": "retry_input_unchanged"})
            self.assertEqual(suppressed["retry_suppression"]["compared_attempts"], [1, 2])
            payload = json.loads(
                fetch_rows(
                    db_path,
                    "select payload_json from repair_hints where hint_id=?",
                    (hint_id,),
                )[0][0]
            )
            self.assertEqual(payload["status"], "retry_suppressed_no_progress")
            self.assertIsNone(payload["retry_command"])
            self.assertEqual(len(payload["attempts"]), 2)
            events = fetch_rows(
                db_path,
                "select event_type, payload_json from events where event_type='repair_retry_suppressed'",
            )
            self.assertEqual(len(events), 1)
            self.assertEqual(json.loads(events[0][1])["reason"], "retry_input_unchanged")
            connection = sqlite3.connect(db_path)
            try:
                resume_hints = harness.repair_hint_resume_summary(connection, run_id="run-no-progress")
            finally:
                connection.close()
            self.assertEqual(resume_hints["open_count"], 0)
            self.assertEqual(
                harness.open_repair_hints_by_worker_id(resume_hints, run_id="run-no-progress"),
                {},
            )
            self.assertEqual(
                harness.run_plan_worker_final_decision(
                    {"exit_code": 1, "recorded": True, "auto_retry_suppressed": suppressed["retry_suppression"]}
                ),
                {"status": "refused", "reason": "retry_input_unchanged"},
            )

    def test_no_progress_hashes_allow_effective_input_and_failure_changes(self) -> None:
        with temp_repo_dir() as tmp:
            source_root = Path(tmp) / "source"
            source_root.mkdir(parents=True)
            source_path = source_root / "demo.c"
            spec_path = source_root / "slice.json"
            source_path.write_text("int add_one(int x) { return x + 1; }\n", encoding="utf-8")
            spec_path.write_text('{"function_name":"add_one"}\n', encoding="utf-8")
            request = {
                "source_repo_root": repo_rel(source_root),
                "source_file": "demo.c",
                "slice_specs": [repo_rel(spec_path)],
                "function": "add_one",
                "target_id": "demo",
                "slice_id": "demo-add-one",
                "source_commit": "abc123",
                "proof_class": "local-simulation",
                "out_root": repo_rel(Path(tmp) / "worker"),
                "run_id": "run-input-worker-a",
            }

            def effective_hash(trace: dict[str, object] | None) -> str:
                return harness.worker_effective_input_sha256(
                    request=request,
                    mode="deterministic",
                    repair_trace=trace,
                    opencode_command="opencode",
                    opencode_model=None,
                    opencode_agent=None,
                    opencode_variant="max",
                    opencode_skip_permissions=False,
                    opencode_allow_non_competition_model=False,
                    opencode_credential_source="none",
                    opencode_preflight_report=None,
                    repo_root=REPO_ROOT,
                )

            initial_input = effective_hash({"action": "adjust type", "attempt": 1, "hint_id": "hint-a"})
            transient_only_change = effective_hash(
                {"action": "adjust type", "attempt": 99, "hint_id": "hint-b", "retry_of": "hint-a"}
            )
            changed_trace = effective_hash({"action": "add cast"})
            self.assertEqual(initial_input, transient_only_change)
            self.assertNotEqual(initial_input, changed_trace)

            source_path.write_text("int add_one(int x) { return (int)(x + 1); }\n", encoding="utf-8")
            changed_source = effective_hash({"action": "adjust type"})
            self.assertNotEqual(initial_input, changed_source)
            source_path.write_text("int add_one(int x) { return x + 1; }\n", encoding="utf-8")
            spec_path.write_text('{"function_name":"add_one","mode":"strict"}\n', encoding="utf-8")
            changed_spec = effective_hash({"action": "adjust type"})
            self.assertNotEqual(initial_input, changed_spec)

            diagnostics_a = {
                "root_cause_key": "rust_type_mismatch",
                "process_returncode": 1,
                "stdout_tail": "worker attempt 1",
                "stderr_tail": "error[E0308]: mismatched types",
                "primary_error": {"kind": "rustc", "code": "E0308", "message": "mismatched types"},
            }
            diagnostics_attempt_noise = {**diagnostics_a, "stdout_tail": "worker attempt 2"}
            diagnostics_changed = {
                **diagnostics_a,
                "stderr_tail": "error[E0382]: borrow of moved value",
                "primary_error": {"kind": "rustc", "code": "E0382", "message": "borrow of moved value"},
            }
            failure_a = harness.worker_failure_sha256(
                root_cause_key="rust_type_mismatch",
                summary_status="failed",
                process_returncode=1,
                diagnostics=diagnostics_a,
            )
            failure_attempt_noise = harness.worker_failure_sha256(
                root_cause_key="rust_type_mismatch",
                summary_status="failed",
                process_returncode=1,
                diagnostics=diagnostics_attempt_noise,
            )
            failure_changed = harness.worker_failure_sha256(
                root_cause_key="rust_borrow_error",
                summary_status="failed",
                process_returncode=1,
                diagnostics=diagnostics_changed,
            )
            self.assertEqual(failure_a, failure_attempt_noise)
            self.assertNotEqual(failure_a, failure_changed)

            attempt_a = {
                "attempt": 1,
                "root_cause_key": "rust_type_mismatch",
                "diagnostics": diagnostics_a,
                "effective_input_sha256": initial_input,
                "failure_sha256": failure_a,
            }
            attempt_b = {**attempt_a, "attempt": 2}
            hint = {"attempts": [attempt_a, attempt_b]}
            self.assertIsNotNone(
                harness.no_progress_retry_suppression(
                    hint,
                    current_effective_input_sha256=initial_input,
                )
            )
            self.assertIsNone(
                harness.no_progress_retry_suppression(
                    hint,
                    current_effective_input_sha256=changed_trace,
                )
            )
            failure_drift_hint = {
                "attempts": [attempt_a, {**attempt_b, "failure_sha256": failure_changed}]
            }
            self.assertIsNone(
                harness.no_progress_retry_suppression(
                    failure_drift_hint,
                    current_effective_input_sha256=initial_input,
                )
            )

    def test_no_progress_suppression_preserves_transient_and_incomplete_hash_retries(self) -> None:
        effective_input_sha256 = "a" * 64
        failure_sha256 = "b" * 64
        diagnostics = {
            "primary_error": {"kind": "process", "message": "retryable infrastructure failure"}
        }
        transient_roots = [
            "process_timeout",
            "sqlite_database_locked",
            "opencode_database_locked",
            "opencode_preflight_failed",
            "credential_unavailable",
            "opencode_contract_not_executed",
            "environment_missing_dependency",
        ]
        for root_cause_key in transient_roots:
            with self.subTest(root_cause_key=root_cause_key):
                attempts = [
                    {
                        "attempt": attempt,
                        "root_cause_key": root_cause_key,
                        "diagnostics": diagnostics,
                        "effective_input_sha256": effective_input_sha256,
                        "failure_sha256": failure_sha256,
                    }
                    for attempt in (1, 2)
                ]
                self.assertIsNone(
                    harness.no_progress_retry_suppression(
                        {"attempts": attempts},
                        current_effective_input_sha256=effective_input_sha256,
                    )
                )

        incomplete_attempts = [
            {
                "attempt": 1,
                "root_cause_key": "rust_type_mismatch",
                "diagnostics": diagnostics,
                "effective_input_sha256": effective_input_sha256,
            },
            {
                "attempt": 2,
                "root_cause_key": "rust_type_mismatch",
                "diagnostics": diagnostics,
                "effective_input_sha256": effective_input_sha256,
                "failure_sha256": failure_sha256,
            },
        ]
        self.assertIsNone(
            harness.no_progress_retry_suppression(
                {"attempts": incomplete_attempts},
                current_effective_input_sha256=effective_input_sha256,
            )
        )

    def test_finalize_run_updates_run_record_with_summary(self) -> None:
        with temp_repo_dir() as tmp:
            out_root = Path(tmp) / "competition-out"
            db_path = harness.init_run(
                out_root=out_root,
                run_id="run-test",
                proof_class="local-simulation",
                repo_root=REPO_ROOT,
            )
            summary_path = out_root / "summary" / "competition-run-summary.json"
            summary_path.parent.mkdir(parents=True, exist_ok=True)
            summary_path.write_text(
                json.dumps(
                    {
                        "schema_version": 1,
                        "run_id": "run-test",
                        "proof_class": "local-simulation",
                        "final_gate": {"status": "passed"},
                        "slices": {"attempted": 1, "semantic_pass": 1},
                    },
                    sort_keys=True,
                )
                + "\n",
                encoding="utf-8",
            )

            result = harness.finalize_run(
                db_path=db_path,
                run_id="run-test",
                status="completed",
                summary_path=summary_path,
                final_gate_status="passed",
                repo_root=REPO_ROOT,
            )

            self.assertEqual(result["status"], "finalized")
            self.assertEqual(result["run_id"], "run-test")
            run_rows = fetch_rows(
                db_path,
                "select run_id, status, final_gate_status, summary_path, summary_sha256, ended_at from runs",
            )
            self.assertEqual(len(run_rows), 1)
            run_row = run_rows[0]
            self.assertEqual(run_row[0], "run-test")
            self.assertEqual(run_row[1], "completed")
            self.assertEqual(run_row[2], "passed")
            self.assertIsNotNone(run_row[3])
            self.assertIsNotNone(run_row[4])
            self.assertIsNotNone(run_row[5])
