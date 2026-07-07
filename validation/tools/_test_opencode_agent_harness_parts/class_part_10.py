class _OpenCodeAgentHarnessTestPart10:
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
