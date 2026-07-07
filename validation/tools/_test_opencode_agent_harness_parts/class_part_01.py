class _OpenCodeAgentHarnessTestPart01:
    def test_evaluate_context_pack_records_retry_limit_exceeded(self) -> None:
        with temp_repo_dir() as tmp:
            out_root = Path(tmp) / "competition-out"
            source_root = Path(tmp) / "FlashDB"
            source_file = source_root / "src" / "demo.c"
            source_file.parent.mkdir(parents=True)
            source_file.write_text(
                """
                int never_recovers(int value) {
                    return value + 1;
                }
                """,
                encoding="utf-8",
            )
            worker_attempts = 0
            merge_called = False

            def fake_runner(argv: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
                nonlocal worker_attempts, merge_called
                if "scripts/c2rust-migrator.py" in argv:
                    worker_attempts += 1
                    request_path = REPO_ROOT / argv[argv.index("--input") + 1]
                    request = json.loads(request_path.read_text(encoding="utf-8"))
                    summary_path = REPO_ROOT / request["out_root"] / "summary" / "competition-run-summary.json"
                    write_worker_summary(summary_path, request["run_id"], status="failed", failed=1, semantic_pass=0)
                    return subprocess.CompletedProcess(argv, 0, stdout=f"worker attempt {worker_attempts}\n", stderr="")
                if "validation/tools/run_competition.py" in argv:
                    merge_called = True
                return subprocess.CompletedProcess(argv, 0, stdout="merge should not run\n", stderr="")

            result = harness.evaluate(
                run_id="run-evaluate-retry-limit",
                target_id="flashdb",
                source_repo_root=source_root,
                source_file="src/demo.c",
                functions=["never_recovers"],
                source_commit="abc123",
                out_root=out_root,
                proof_class="local-simulation",
                slice_id_prefix="eval-retry-limit",
                worker_prefix="eval-worker",
                execute_merge=True,
                auto_retry=True,
                command_runner=fake_runner,
                repo_root=REPO_ROOT,
            )

            self.assertEqual(result["status"], "failed")
            self.assertEqual(result["exit_code"], 1)
            self.assertEqual(worker_attempts, 6)
            self.assertTrue(merge_called)
            self.assertEqual(result["run_plan"]["merge_execution"]["exit_code"], 1)
            self.assertFalse(result["run_plan"]["merge_execution"]["summary_exists"])
            context_pack = json.loads((REPO_ROOT / result["context_pack"]["path"]).read_text(encoding="utf-8"))
            agent_index = json.loads((REPO_ROOT / result["agent_index"]["path"]).read_text(encoding="utf-8"))
            worker = context_pack["workers"][0]
            agent = agent_index["agents"][0]
            self.assertTrue(worker["recorded"])
            self.assertEqual(worker["summary_status"], "failed")
            self.assertEqual(worker["auto_retry"]["attempt_count"], 6)
            self.assertEqual(worker["auto_retry"]["final_hint_status"], "retry_limit_exceeded")
            self.assertEqual(worker["auto_retry"]["attempts"][-1]["hint_status"], "retry_limit_exceeded")
            self.assertEqual(worker["auto_retry"]["attempts"][-1]["exit_code"], 1)
            self.assertEqual(worker["auto_retry"]["attempts"][-1]["repair_round_cap"], 5)
            self.assertEqual(worker["auto_retry"]["attempts"][-1]["repair_rounds"], 5)
            self.assertEqual(worker["auto_retry"]["attempts"][-1]["retry_limit"]["max_repair_rounds"], 5)
            self.assertEqual(agent["status"], "failed")
            self.assertTrue(agent["recorded"])
            self.assertEqual(agent["auto_retry"]["final_hint_status"], "retry_limit_exceeded")
            self.assertEqual(agent["auto_retry"]["attempts"][-1]["repair_round_cap"], 5)
            hint_rows = fetch_rows(Path(REPO_ROOT / result["db_path"]), "select status, payload_json from repair_hints")
            self.assertEqual(len(hint_rows), 1)
            self.assertEqual(hint_rows[0][0], "retry_limit_exceeded")
            hint_payload = json.loads(hint_rows[0][1])
            self.assertEqual(hint_payload["retry_limit"]["max_repair_rounds"], 5)

    def test_run_plan_executes_workers_in_parallel_when_max_workers_allows(self) -> None:
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
            db_path = harness.init_run(
                out_root=out_root,
                run_id="run-test",
                proof_class="local-simulation",
                repo_root=REPO_ROOT,
            )
            plan = harness.plan_source_file(
                db_path=db_path,
                run_id="run-test",
                target_id="flashdb",
                source_repo_root=source_root,
                source_file="src/demo.c",
                source_commit="abc123",
                functions=["first_unit", "second_unit"],
                out_root=out_root,
                slice_id_prefix="real-demo",
                worker_prefix="worker",
                repo_root=REPO_ROOT,
            )
            worker_started: list[str] = []
            both_workers_started = threading.Event()
            worker_lock = threading.Lock()

            def fake_runner(argv: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
                if "scripts/c2rust-migrator.py" in argv:
                    request_path = REPO_ROOT / argv[argv.index("--input") + 1]
                    request = json.loads(request_path.read_text(encoding="utf-8"))
                    with worker_lock:
                        worker_started.append(str(request["run_id"]))
                        if len(worker_started) == 2:
                            both_workers_started.set()
                    self.assertTrue(both_workers_started.wait(2), "run-plan did not overlap worker execution")
                    summary_path = REPO_ROOT / request["out_root"] / "summary" / "competition-run-summary.json"
                    write_worker_summary(summary_path, request["run_id"], status="passed", failed=0, semantic_pass=1)
                    return subprocess.CompletedProcess(argv, 0, stdout="worker ok\n", stderr="")
                summary_path = out_root / "summary" / "competition-run-summary.json"
                write_worker_summary(summary_path, "run-test", status="passed", failed=0, semantic_pass=2)
                return subprocess.CompletedProcess(argv, 0, stdout="merge ok\n", stderr="")

            result = harness.run_plan(
                db_path=db_path,
                run_id="run-test",
                plan_path=REPO_ROOT / plan["plan_path"],
                out_root=out_root,
                proof_class="local-simulation",
                execute_merge=True,
                max_workers=2,
                command_runner=fake_runner,
                repo_root=REPO_ROOT,
            )

            self.assertEqual(result["status"], "completed")
            self.assertEqual(result["parallelism"], {"max_workers": 2, "effective_workers": 2})
            self.assertEqual(result["graph"]["runtime"], "opencode-harness-langgraph-inspired")
            self.assertEqual(result["graph"]["checkpoint_backend"], "sqlite")
            self.assertIn("fanout_workers", result["graph"]["nodes"])
            self.assertIn("repair_retry", result["graph"]["nodes"])
            self.assertIn(
                {
                    "from": "worker",
                    "to": "repair_retry",
                    "condition": "exit_code != 0 and auto_retry",
                },
                result["graph"]["edges"],
            )
            self.assertEqual(result["graph"]["parallel_map"]["max_workers"], 2)
            self.assertEqual(result["graph"]["parallel_map"]["result_order"], "planner_order")
            self.assertEqual([worker["worker_id"] for worker in result["workers"]], [unit["worker_id"] for unit in plan["units"]])
            self.assertEqual(len(worker_started), 2)

    def test_run_plan_can_execute_final_merge_and_finalize_run(self) -> None:
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
            db_path = harness.init_run(
                out_root=out_root,
                run_id="run-test",
                proof_class="local-simulation",
                repo_root=REPO_ROOT,
            )
            plan = harness.plan_source_file(
                db_path=db_path,
                run_id="run-test",
                target_id="flashdb",
                source_repo_root=source_root,
                source_file="src/demo.c",
                source_commit="abc123",
                out_root=out_root,
                slice_id_prefix="real-demo",
                worker_prefix="worker",
                repo_root=REPO_ROOT,
            )
            merge_calls: list[list[str]] = []

            def fake_runner(argv: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
                if "scripts/c2rust-migrator.py" in argv:
                    request_path = REPO_ROOT / argv[argv.index("--input") + 1]
                    request = json.loads(request_path.read_text(encoding="utf-8"))
                    summary_path = REPO_ROOT / request["out_root"] / "summary" / "competition-run-summary.json"
                    write_worker_summary(summary_path, request["run_id"], status="passed", failed=0, semantic_pass=1)
                    return subprocess.CompletedProcess(argv, 0, stdout="worker ok\n", stderr="")
                merge_calls.append(argv)
                self.assertIn("validation/tools/run_competition.py", argv)
                self.assertIn("--worker-summary", argv)
                summary_path = out_root / "summary" / "competition-run-summary.json"
                write_worker_summary(summary_path, "run-test", status="passed", failed=0, semantic_pass=1)
                return subprocess.CompletedProcess(argv, 0, stdout="merge ok\n", stderr="")

            result = harness.run_plan(
                db_path=db_path,
                run_id="run-test",
                plan_path=REPO_ROOT / plan["plan_path"],
                out_root=out_root,
                proof_class="local-simulation",
                execute_merge=True,
                command_runner=fake_runner,
                repo_root=REPO_ROOT,
            )

            self.assertEqual(result["status"], "completed")
            self.assertEqual(result["exit_code"], 0)
            self.assertEqual(len(merge_calls), 1)
            self.assertEqual(result["merge_execution"]["exit_code"], 0)
            self.assertEqual(
                result["merge_execution"]["summary_path"],
                repo_rel(out_root / "summary" / "competition-run-summary.json"),
            )
            self.assertTrue((out_root / "harness" / "run-plan-merge.stdout.log").exists())
            run_rows = fetch_rows(
                db_path,
                "select status, final_gate_status, summary_path from runs where run_id=?",
                ("run-test",),
            )
            self.assertEqual(
                run_rows,
                [("completed", "passed", repo_rel(out_root / "summary" / "competition-run-summary.json"))],
            )

    def test_run_plan_execute_merge_skips_partial_worker_summaries(self) -> None:
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
            db_path = harness.init_run(
                out_root=out_root,
                run_id="run-test",
                proof_class="local-simulation",
                repo_root=REPO_ROOT,
            )
            plan = harness.plan_source_file(
                db_path=db_path,
                run_id="run-test",
                target_id="flashdb",
                source_repo_root=source_root,
                source_file="src/demo.c",
                source_commit="abc123",
                out_root=out_root,
                slice_id_prefix="real-demo",
                worker_prefix="worker",
                repo_root=REPO_ROOT,
            )
            merge_called = False

            def fake_runner(argv: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
                nonlocal merge_called
                if "validation/tools/run_competition.py" in argv:
                    merge_called = True
                return subprocess.CompletedProcess(argv, 0, stdout="ok\n", stderr="")

            result = harness.run_plan(
                db_path=db_path,
                run_id="run-test",
                plan_path=REPO_ROOT / plan["plan_path"],
                out_root=out_root,
                proof_class="local-simulation",
                execute_merge=True,
                command_runner=fake_runner,
                repo_root=REPO_ROOT,
            )

            self.assertEqual(result["status"], "failed")
            self.assertEqual(result["exit_code"], 1)
            self.assertFalse(merge_called)
            self.assertEqual(result["merge_execution"]["status"], "skipped")
            self.assertEqual(result["merge_execution"]["reason"], "unrecorded-worker-summaries")

    def test_run_batch_profile_initializes_plans_and_executes_merge(self) -> None:
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
            spec_root = Path(tmp) / "slice-specs"
            spec_root.mkdir()
            first_spec = write_slice_spec(spec_root / "first-unit.json", "demo", "demo-first", "first_unit", "abc123")
            second_spec = write_slice_spec(spec_root / "second-unit.json", "demo", "demo-second", "second_unit", "abc123")
            profile_path = Path(tmp) / "planned-batch.json"
            profile_path.write_text(
                json.dumps(
                    {
                        "schema_version": 1,
                        "profile_id": "demo-two-unit-accepted-evidence",
                        "proof_class": "local-simulation",
                        "target_id": "demo",
                        "source_repo_root": repo_rel(source_root),
                        "source_file": "src/demo.c",
                        "source_commit": "abc123",
                        "require_source_commit": "abc123",
                        "functions": ["first_unit", "second_unit"],
                        "slice_specs": [repo_rel(first_spec), repo_rel(second_spec)],
                        "reuse_accepted_evidence": True,
                        "accepted_evidence_root": "validation/evidence",
                        "slice_id_prefix": "wrong-prefix",
                        "worker_prefix": "worker",
                        "mode": "deterministic",
                        "execute_merge": True,
                        "auto_retry": True,
                        "max_workers": 2,
                        "emit_route_governance_metrics_report": True,
                        "acceptance_boundary": {
                            "semantic_claim_source": "accepted_evidence_binding",
                            "generated_draft_semantic_pass": False,
                        },
                    }
                ),
                encoding="utf-8",
            )
            merge_calls: list[list[str]] = []

            def fake_runner(argv: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
                if "scripts/c2rust-migrator.py" in argv:
                    request_path = REPO_ROOT / argv[argv.index("--input") + 1]
                    request = json.loads(request_path.read_text(encoding="utf-8"))
                    summary_path = REPO_ROOT / request["out_root"] / "summary" / "competition-run-summary.json"
                    write_worker_summary(summary_path, request["run_id"], status="passed", failed=0, semantic_pass=1)
                    return subprocess.CompletedProcess(argv, 0, stdout="worker ok\n", stderr="")
                merge_calls.append(argv)
                summary_path = out_root / "summary" / "competition-run-summary.json"
                write_worker_summary(
                    summary_path,
                    "run-profile",
                    status="passed",
                    failed=0,
                    semantic_pass=1,
                    workflow_metrics=measured_unsafe_worker_metrics("run-profile"),
                )
                return subprocess.CompletedProcess(argv, 0, stdout="merge ok\n", stderr="")

            result = harness.run_batch_profile(
                profile_path=profile_path,
                run_id="run-profile",
                out_root=out_root,
                command_runner=fake_runner,
                repo_root=REPO_ROOT,
            )

            self.assertEqual(result["status"], "completed")
            self.assertEqual(result["exit_code"], 0)
            self.assertEqual(result["profile_id"], "demo-two-unit-accepted-evidence")
            self.assertTrue(result["profile_sha256"])
            self.assertEqual(
                result["acceptance_boundary"],
                {
                    "semantic_claim_source": "accepted_evidence_binding",
                    "generated_draft_semantic_pass": False,
                },
            )
            self.assertEqual(result["worker_count"], 2)
            self.assertEqual(len(merge_calls), 1)
            self.assertEqual(
                [unit["slice_id"] for unit in result["plan"]["units"]],
                ["demo-first", "demo-second"],
            )
            self.assertEqual(result["run_plan"]["merge_execution"]["final_gate_status"], "passed")
            self.assertEqual(result["run_plan"]["auto_retry"], {"enabled": True, "retried_worker_count": 0})
            self.assertEqual(result["run_plan"]["parallelism"], {"max_workers": 2, "effective_workers": 2})
            self.assertEqual(result["run_plan"]["graph"]["parallel_map"]["max_workers"], 2)
            self.assertTrue((out_root / "summary" / "competition-run-summary.json").exists())
            route_report_ref = result["route_governance_metrics_report"]
            route_report_path = REPO_ROOT / route_report_ref["path"]
            self.assertTrue(route_report_path.exists())
            self.assertEqual(route_report_ref["sha256"], harness.sha256_file(route_report_path))
            route_report = json.loads(route_report_path.read_text(encoding="utf-8"))
            self.assertEqual(route_report["report_kind"], "route-governance-metrics")
            self.assertEqual(route_report["status"], "passed")
            self.assertIn("translation_coverage_numerator", route_report["metrics"])
            self.assertEqual(route_report["metrics"]["s2_workflow_metrics"]["run_count"], 1)
            self.assertEqual(route_report_ref["s2_workflow_run_count"], 1)
            self.assertEqual(route_report_ref["s2_unsafe_reduction_status"], "measured")
            self.assertEqual(route_report_ref["s2_translation_before_after_status"], "not_provided")
            self.assertEqual(route_report_ref["s2_translation_before_after_unit_count"], 0)
            artifact_rows = fetch_rows(
                result["db_path"],
                "select kind, repo_rel_path, semantic_role from artifacts where kind='route-governance-metrics-report'",
            )
            self.assertEqual(
                artifact_rows,
                [
                    (
                        "route-governance-metrics-report",
                        route_report_ref["path"],
                        "route-governance-metrics",
                    )
                ],
            )
            report = json.loads((out_root / "harness" / "batch-profile-report.json").read_text(encoding="utf-8"))
            self.assertEqual(report["report_path"], result["report_path"])
            self.assertEqual(report["acceptance_boundary"], result["acceptance_boundary"])
            self.assertEqual(report["route_governance_metrics_report"], route_report_ref)
            self.assertEqual(report["context_pack"], result["context_pack"])
            self.assertEqual(report["agent_index"], result["agent_index"])
            context_pack = json.loads((REPO_ROOT / result["context_pack"]["path"]).read_text(encoding="utf-8"))
            agent_index = json.loads((REPO_ROOT / result["agent_index"]["path"]).read_text(encoding="utf-8"))
            self.assertEqual(context_pack["run_id"], "run-profile")
            self.assertEqual(context_pack["entrypoints"]["primary_report"], result["report_path"])
            self.assertEqual(context_pack["entrypoints"]["batch_profile_report"], result["report_path"])
            self.assertEqual(context_pack["entrypoints"]["route_governance_metrics_report"], route_report_ref["path"])
            self.assertEqual(context_pack["entrypoints"]["merge_plan"], result["run_plan"]["merge_plan"]["path"])
            self.assertEqual(context_pack["source"]["require_source_commit"], "abc123")
            self.assert_context_management_contract(context_pack["context_management_contract"])
            self.assertEqual(context_pack["acceptance_boundary"]["profile"], result["acceptance_boundary"])
            self.assertEqual(context_pack["report_artifacts"]["route_governance_metrics_report"], route_report_ref)
            self.assert_agent_coordination_contract(agent_index["agent_coordination_contract"], expected_worker_count=2)
            self.assertEqual(agent_index["reports"]["route_governance_metrics_report"], route_report_ref)
            self.assertEqual([worker["worker_id"] for worker in context_pack["workers"]], [unit["worker_id"] for unit in result["plan"]["units"]])
            self.assertEqual([agent["worker_id"] for agent in agent_index["agents"]], [unit["worker_id"] for unit in result["plan"]["units"]])
            self.assertEqual(sorted(agent_index["agents_by_worker_id"]), [unit["worker_id"] for unit in result["plan"]["units"]])
            for unit in result["plan"]["units"]:
                indexed_agent = agent_index["agents_by_worker_id"][unit["worker_id"]]
                self.assertEqual(indexed_agent["assignment_path"], unit["assignment_path"])
                self.assertEqual(indexed_agent["request_path"], unit["request_path"])
                self.assertIn("summary_path", indexed_agent)
                self.assertIn("report_path", indexed_agent)
            context_rows = fetch_rows(
                Path(REPO_ROOT / result["db_path"]),
                "select context_pack_id, artifact_path, artifact_sha256, payload_json from context_packs",
            )
            self.assertEqual(len(context_rows), 1)
            self.assertEqual(
                context_rows[0][:3],
                ("run-profile-context-pack", result["context_pack"]["path"], result["context_pack"]["sha256"]),
            )
            self.assertEqual(json.loads(context_rows[0][3]), context_pack)
            artifact_rows = fetch_rows(
                Path(REPO_ROOT / result["db_path"]),
                """
                select kind, agent_id, repo_rel_path, sha256, semantic_role
                from artifacts
                where kind in ('context-pack', 'agent-index')
                order by kind
                """,
            )
            self.assertEqual(
                artifact_rows,
                [
                    ("agent-index", "planner", result["agent_index"]["path"], result["agent_index"]["sha256"], "agent-index"),
                    ("context-pack", "planner", result["context_pack"]["path"], result["context_pack"]["sha256"], "agent-context-pack"),
                ],
            )
            for path_value in [
                result["context_pack"]["path"],
                result["agent_index"]["path"],
                context_pack["entrypoints"]["primary_report"],
                context_pack["entrypoints"]["batch_profile_report"],
                context_pack["entrypoints"]["run_plan_report"],
                context_pack["entrypoints"]["worker_plan"],
                context_pack["entrypoints"]["merge_plan"],
                context_pack["entrypoints"]["merge_summary"],
                context_pack["entrypoints"]["route_governance_metrics_report"],
            ]:
                self.assert_repo_relative_posix_path(path_value)

    def test_before_after_exhibit_profile_report_fails_closed_when_summary_missing(self) -> None:
        with temp_repo_dir() as tmp:
            out_root = Path(tmp) / "competition-out"
            profile_path = Path(tmp) / "planned-batch.json"
            profile = {
                "schema_version": 1,
                "profile_id": "demo-before-after",
                "proof_class": "local-simulation",
                "target_id": "demo",
                "emit_before_after_exhibit_report": True,
                "require_repair_trace": True,
            }
            profile_path.write_text(json.dumps(profile), encoding="utf-8")

            artifact = harness.write_before_after_exhibit_profile_report(
                profile=profile,
                profile_path=profile_path,
                run_id="run-missing-summary",
                proof_class="local-simulation",
                mode="deterministic",
                plan={"units": []},
                run_result={
                    "status": "failed",
                    "exit_code": 1,
                    "merge_execution": {
                        "summary_path": repo_rel(out_root / "summary" / "competition-run-summary.json"),
                        "summary_exists": False,
                    },
                },
                route_metrics_artifact=None,
                out_root=out_root,
                repo_root=REPO_ROOT,
            )

            self.assertIsNotNone(artifact)
            self.assertEqual(artifact["binding"]["status"], "failed")
            self.assertEqual(artifact["binding"]["reason"], "competition_summary_missing")
            report_path = REPO_ROOT / artifact["binding"]["path"]
            report = json.loads(report_path.read_text(encoding="utf-8"))
            self.assertEqual(report["status"], "failed")
            self.assertEqual(report["reason"], "competition_summary_missing")
            self.assertEqual(report["core_translation_quality"]["final_gate_status"], "missing")
            self.assertEqual(report["harness_architecture"]["command_status"], "failed")
            self.assertEqual(report["failure_path"]["baseline_role"], "handwritten_or_accepted_evidence_baseline")
            self.assertEqual(report["failure_path"]["next_repair_hint"]["root_cause_key"], "competition_summary_missing")

    def test_before_after_reproduction_command_preserves_proof_class_override(self) -> None:
        with temp_repo_dir() as tmp:
            out_root = Path(tmp) / "competition-out"
            profile_path = Path(tmp) / "planned-batch.json"
            summary_path = out_root / "summary" / "competition-run-summary.json"
            profile_path.write_text("{}\n", encoding="utf-8")

            commands = harness.before_after_reproduction_commands(
                profile_path=profile_path,
                run_id="run-exact",
                out_root=out_root,
                summary_path=summary_path,
                proof_class_resolution={
                    "source": "cli-override",
                    "profile_proof_class": "local-simulation",
                    "effective_proof_class": "competition-exact",
                    "override_requested": True,
                    "changed": True,
                    "override_proof_class": "competition-exact",
                },
                repo_root=REPO_ROOT,
            )

            self.assertIn("--proof-class competition-exact", commands["run_command"])

    def test_judge_evidence_index_reproduction_commands_preserve_proof_class_override(self) -> None:
        with temp_repo_dir() as tmp:
            out_root = Path(tmp) / "competition-out"
            profile_path = Path(tmp) / "planned-batch.json"
            evaluate_report_path = out_root / "harness" / "evaluate-report.json"
            profile_path.write_text(
                json.dumps({"schema_version": 1, "profile_id": "demo", "proof_class": "local-simulation"}),
                encoding="utf-8",
            )
            evaluate_report_path.parent.mkdir(parents=True, exist_ok=True)
            evaluate_report_path.write_text("{}\n", encoding="utf-8")

            artifact = harness.write_judge_evidence_index(
                evaluate_report={
                    "status": "blocked",
                    "exit_code": 1,
                    "profile_id": "demo",
                    "proof_class": "competition-exact",
                    "mode": "opencode",
                    "proof_class_resolution": {
                        "source": "cli-override",
                        "profile_proof_class": "local-simulation",
                        "effective_proof_class": "competition-exact",
                        "override_requested": True,
                        "changed": True,
                        "override_proof_class": "competition-exact",
                    },
                    "judge_summary": {},
                },
                evaluate_report_path=evaluate_report_path,
                batch_result={"status": "blocked", "exit_code": 1},
                profile_path=profile_path,
                run_id="run-exact",
                out_root=out_root,
                repo_root=REPO_ROOT,
            )

            commands = artifact["payload"]["reproduction_commands"]
            self.assertIn("--proof-class competition-exact", commands["evaluate_profile"])
            self.assertIn("--proof-class competition-exact", commands["run_batch_profile"])

    def test_before_after_exhibit_labels_unbound_baseline_as_harness_exhibit(self) -> None:
        with temp_repo_dir() as tmp:
            out_root = Path(tmp) / "competition-out"
            summary_path = out_root / "summary" / "competition-run-summary.json"
            profile_path = Path(tmp) / "planned-batch.json"
            profile = {
                "schema_version": 1,
                "profile_id": "demo-before-after-unbound",
                "proof_class": "local-simulation",
                "target_id": "demo",
                "emit_before_after_exhibit_report": True,
                "acceptance_boundary": {
                    "semantic_claim_source": "accepted_evidence_binding",
                    "translation_before_after": "validation/evidence/demo/auto-translation/store-add-one/missing.json",
                },
            }
            profile_path.write_text(json.dumps(profile), encoding="utf-8")
            workflow_metrics = measured_unsafe_worker_metrics("run-unbound-before-after")
            write_worker_summary(
                summary_path,
                "run-unbound-before-after",
                status="passed",
                failed=0,
                semantic_pass=1,
                workflow_metrics=workflow_metrics,
            )

            artifact = harness.write_before_after_exhibit_profile_report(
                profile=profile,
                profile_path=profile_path,
                run_id="run-unbound-before-after",
                proof_class="local-simulation",
                mode="deterministic",
                plan={"status": "planned", "units": [{"slice_id": "store-add-one"}]},
                run_result={"status": "completed", "workers": [{"worker_id": "worker-a", "exit_code": 0}]},
                route_metrics_artifact=None,
                out_root=out_root,
                repo_root=REPO_ROOT,
            )

            self.assertIsNotNone(artifact)
            self.assertEqual(artifact["binding"]["status"], "not_provided")
            report = artifact["payload"]
            self.assertEqual(report["status"], "not_provided")
            self.assertEqual(report["translation_before_after"]["status"], "not_provided")
            failure_path = report["failure_path"]
            self.assertEqual(failure_path["baseline_role"], "handwritten_or_accepted_evidence_baseline")
            self.assertEqual(failure_path["status"], "harness_exhibit_only")
            self.assertEqual(failure_path["next_repair_hint"]["root_cause_key"], "before_after_not_bound")
            self.assertEqual(failure_path["observable_diff"]["status"], "not_available")
            self.assertIn("run-batch-profile", failure_path["smallest_replay_command"]["command"])
            self.assertIn("validate_competition_run_summary.py", failure_path["smallest_replay_command"]["verify_command"])

    def test_run_batch_profile_supports_explicit_worker_source_pins(self) -> None:
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
            spec_root = Path(tmp) / "slice-specs"
            first_spec = write_slice_spec(spec_root / "first-unit.json", "demo", "demo-first", "first_unit", "commit-one")
            second_spec = write_slice_spec(spec_root / "second-unit.json", "demo", "demo-second", "second_unit", "commit-two")
            worker_profiles = [
                {
                    "worker_id": "explicit-worker-001-first-unit",
                    "target_id": "demo",
                    "source_repo_root": repo_rel(source_root),
                    "source_repository": "https://gitcode.com/example/FlashDB.git",
                    "source_branch": "competition",
                    "source_file": "src/demo.c",
                    "function": "first_unit",
                    "slice_id": "demo-first",
                    "source_commit": "commit-one",
                    "require_source_commit": "commit-one",
                    "slice_spec": repo_rel(first_spec),
                },
                {
                    "worker_id": "explicit-worker-002-second-unit",
                    "target_id": "demo",
                    "source_repo_root": repo_rel(source_root),
                    "source_repository": "https://gitcode.com/example/FlashDB.git",
                    "source_branch": "competition",
                    "source_file": "src/demo.c",
                    "function": "second_unit",
                    "slice_id": "demo-second",
                    "source_commit": "commit-two",
                    "require_source_commit": "commit-two",
                    "slice_spec": repo_rel(second_spec),
                },
            ]
            profile_path = Path(tmp) / "planned-batch-explicit-workers.json"
            profile_path.write_text(
                json.dumps(
                    {
                        "schema_version": 1,
                        "profile_id": "demo-explicit-workers",
                        "proof_class": "local-simulation",
                        "target_id": "demo",
                        "source_repository": "https://gitcode.com/example/FlashDB.git",
                        "source_branch": "competition",
                        "reuse_accepted_evidence": True,
                        "accepted_evidence_root": "validation/evidence",
                        "worker_prefix": "explicit-worker",
                        "mode": "deterministic",
                        "execute_merge": True,
                        "auto_retry": False,
                        "max_workers": 2,
                        "acceptance_boundary": {
                            "semantic_claim_source": "accepted_evidence_binding",
                            "generated_draft_semantic_pass": False,
                        },
                        "workers": worker_profiles,
                    }
                ),
                encoding="utf-8",
            )
            merge_calls: list[list[str]] = []

            def fake_runner(argv: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
                if "scripts/c2rust-migrator.py" in argv:
                    request_path = REPO_ROOT / argv[argv.index("--input") + 1]
                    request = json.loads(request_path.read_text(encoding="utf-8"))
                    summary_path = REPO_ROOT / request["out_root"] / "summary" / "competition-run-summary.json"
                    write_worker_summary(summary_path, request["run_id"], status="passed", failed=0, semantic_pass=1)
                    return subprocess.CompletedProcess(argv, 0, stdout=f"{request['function']} ok\n", stderr="")
                merge_calls.append(argv)
                summary_path = out_root / "summary" / "competition-run-summary.json"
                write_worker_summary(
                    summary_path,
                    "run-explicit",
                    status="passed",
                    failed=0,
                    semantic_pass=2,
                    workflow_metrics=measured_unsafe_worker_metrics("run-explicit"),
                )
                return subprocess.CompletedProcess(argv, 0, stdout="merge ok\n", stderr="")

            result = harness.run_batch_profile(
                profile_path=profile_path,
                run_id="run-explicit",
                out_root=out_root,
                command_runner=fake_runner,
                repo_root=REPO_ROOT,
            )

            self.assertEqual(result["status"], "completed")
            self.assertEqual(result["worker_count"], 2)
            self.assertEqual(result["plan"]["planning_mode"], "explicit_workers")
            self.assertEqual(
                [unit["worker_id"] for unit in result["plan"]["units"]],
                ["explicit-worker-001-first-unit", "explicit-worker-002-second-unit"],
            )
            self.assertEqual([unit["source_commit"] for unit in result["plan"]["units"]], ["commit-one", "commit-two"])
            self.assertEqual(
                [unit["require_source_commit"] for unit in result["plan"]["units"]],
                ["commit-one", "commit-two"],
            )
            self.assertEqual(result["run_plan"]["graph"]["parallel_map"]["effective_workers"], 2)
            self.assertEqual(result["run_plan"]["graph"]["parallel_map"]["result_order"], "planner_order")
            self.assertEqual(result["judge_summary"]["harness_architecture"]["planning_mode"], "explicit_workers")
            self.assertEqual(
                result["judge_summary"]["harness_architecture"]["pipeline"],
                ["init-run", "plan-explicit-workers", "run-plan", "merge", "report"],
            )

            self.assertEqual(len(merge_calls), 1)
            merge_worker_summaries = [
                merge_calls[0][index + 1]
                for index, arg in enumerate(merge_calls[0])
                if arg == "--worker-summary"
            ]
            self.assertEqual(
                merge_worker_summaries,
                [worker["summary_path"] for worker in result["run_plan"]["workers"]],
            )

            for unit in result["plan"]["units"]:
                request = json.loads((REPO_ROOT / unit["request_path"]).read_text(encoding="utf-8"))
                self.assertEqual(request["require_source_commit"], unit["require_source_commit"])
                self.assertEqual(request["source_commit"], unit["source_commit"])
                self.assertEqual(request["source_sha256"], unit["source_sha256"])
                self.assertEqual(request["slice_specs"], [unit["slice_spec"]])

            context_pack = json.loads((REPO_ROOT / result["context_pack"]["path"]).read_text(encoding="utf-8"))
            agent_index = json.loads((REPO_ROOT / result["agent_index"]["path"]).read_text(encoding="utf-8"))
            self.assertEqual(context_pack["source"]["planning_mode"], "explicit_workers")
            self.assertEqual(
                [source["source_commit"] for source in context_pack["source"]["worker_sources"]],
                ["commit-one", "commit-two"],
            )
            self.assertEqual(
                [worker["require_source_commit"] for worker in context_pack["workers"]],
                ["commit-one", "commit-two"],
            )
            self.assertEqual(
                [agent["source_commit"] for agent in agent_index["agents"]],
                ["commit-one", "commit-two"],
            )

    def test_run_batch_profile_rejects_explicit_worker_slice_spec_mismatch(self) -> None:
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
            spec_root = Path(tmp) / "slice-specs"
            mismatched_spec = write_slice_spec(
                spec_root / "first-unit.json",
                "demo",
                "demo-first",
                "first_unit",
                "commit-one",
            )
            profile_path = Path(tmp) / "planned-batch-explicit-workers.json"
            profile_path.write_text(
                json.dumps(
                    {
                        "schema_version": 1,
                        "profile_id": "demo-explicit-workers-bad-spec",
                        "proof_class": "local-simulation",
                        "target_id": "demo",
                        "mode": "deterministic",
                        "execute_merge": False,
                        "max_workers": 1,
                        "workers": [
                            {
                                "worker_id": "explicit-worker-001-second-unit",
                                "target_id": "demo",
                                "source_repo_root": repo_rel(source_root),
                                "source_file": "src/demo.c",
                                "function": "second_unit",
                                "slice_id": "demo-second",
                                "source_commit": "commit-one",
                                "require_source_commit": "commit-one",
                                "slice_spec": repo_rel(mismatched_spec),
                            }
                        ],
                    }
                ),
                encoding="utf-8",
            )

            def fail_if_called(argv: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
                raise AssertionError(f"worker should not run for mismatched slice spec: {argv}")

            with self.assertRaisesRegex(SystemExit, "slice spec function_name mismatch"):
                harness.run_batch_profile(
                    profile_path=profile_path,
                    run_id="run-explicit-bad-spec",
                    out_root=out_root,
                    command_runner=fail_if_called,
                    repo_root=REPO_ROOT,
                )

    def test_run_batch_profile_rejects_explicit_worker_source_hash_mismatch(self) -> None:
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
            spec_root = Path(tmp) / "slice-specs"
            spec_path = write_slice_spec(spec_root / "first-unit.json", "demo", "demo-first", "first_unit", "commit-one")
            spec = json.loads(spec_path.read_text(encoding="utf-8"))
            spec["source"] = {
                "source_commit": "commit-one",
                "source_file_hashes": {
                    "src/demo.c": "0" * 64,
                },
            }
            spec_path.write_text(json.dumps(spec, sort_keys=True) + "\n", encoding="utf-8")
            profile_path = Path(tmp) / "planned-batch-explicit-workers.json"
            profile_path.write_text(
                json.dumps(
                    {
                        "schema_version": 1,
                        "profile_id": "demo-explicit-workers-bad-source-hash",
                        "proof_class": "local-simulation",
                        "target_id": "demo",
                        "mode": "deterministic",
                        "execute_merge": False,
                        "max_workers": 1,
                        "workers": [
                            {
                                "worker_id": "explicit-worker-001-first-unit",
                                "target_id": "demo",
                                "source_repo_root": repo_rel(source_root),
                                "source_file": "src/demo.c",
                                "function": "first_unit",
                                "slice_id": "demo-first",
                                "source_commit": "commit-one",
                                "require_source_commit": "commit-one",
                                "slice_spec": repo_rel(spec_path),
                            }
                        ],
                    }
                ),
                encoding="utf-8",
            )

            def fail_if_called(argv: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
                raise AssertionError(f"worker should not run for mismatched source hash: {argv}")

            with self.assertRaisesRegex(SystemExit, "source file sha256 mismatch"):
                harness.run_batch_profile(
                    profile_path=profile_path,
                    run_id="run-explicit-bad-source-hash",
                    out_root=out_root,
                    command_runner=fail_if_called,
                    repo_root=REPO_ROOT,
                )
