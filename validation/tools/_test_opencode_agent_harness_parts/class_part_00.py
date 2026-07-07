class _OpenCodeAgentHarnessTestPart00:
    def assert_repo_relative_posix_path(self, value: str) -> None:
        self.assertIsInstance(value, str)
        self.assertTrue(value)
        self.assertNotIn("\\", value)
        self.assertFalse(value.startswith("/"))
        self.assertFalse(value.startswith("~"))
        self.assertFalse(len(value) >= 2 and value[1] == ":")
        self.assertNotIn("..", Path(value).parts)

    def assert_context_management_contract(self, contract: dict) -> None:
        self.assertEqual(contract["contract_kind"], "context-management")
        self.assertEqual(contract["role"], "context-index-and-resume-map")
        self.assertEqual(contract["evidence_policy"], "on-disk-artifacts-only")
        self.assertFalse(contract["semantic_gate"])
        self.assertFalse(contract["chat_output_is_evidence"])
        self.assertIn("entrypoints", contract["managed_state"])
        self.assertIn("worker handoffs", contract["managed_state"])
        pipeline = contract["pipeline"]
        self.assertEqual([stage["stage"] for stage in pipeline], ["plan", "translate", "verify", "repair"])
        self.assertEqual([stage["role"] for stage in pipeline], ["planner", "worker", "verifier", "repairer"])
        self.assertEqual(pipeline[0]["evidence"], "entrypoints.worker_plan")
        self.assertEqual(pipeline[1]["evidence"], "workers[*].summary_path")
        self.assertTrue(pipeline[1]["fanout"])
        self.assertEqual(pipeline[2]["reduce"], "merge")
        self.assertEqual(pipeline[3]["loopback_to"], "translate")
        self.assertEqual(pipeline[3]["max_rounds"], 5)
        resume_protocol = contract["resume_protocol"]
        self.assertEqual(resume_protocol["checkpoint_backend"], "sqlite")
        self.assertEqual(resume_protocol["worker_state_source"], "agent-index.agents_by_worker_id")
        self.assertIn("repair_hints", resume_protocol["open_repair_hint_source"])
        self.assertIn("worker summaries", resume_protocol["merge_precondition"])

    def assert_agent_coordination_contract(self, contract: dict, *, expected_worker_count: int | None = None) -> None:
        self.assertEqual(contract["contract_kind"], "agent-coordination")
        self.assertEqual(contract["coordination_state"], "sqlite-ledger-and-on-disk-reports")
        self.assertEqual(contract["checkpoint_backend"], "sqlite")
        self.assertFalse(contract["semantic_gate"])
        self.assertFalse(contract["chat_output_is_evidence"])
        self.assertEqual(contract["planner_ownership"]["mode"], "single-planner-per-run")
        self.assertIn("BEGIN IMMEDIATE", contract["planner_ownership"]["assignment_transaction"])
        self.assertEqual(contract["lease_policy"]["fencing_token"], "audit-only-monotonic-counter")
        self.assertTrue(contract["lease_policy"]["not_acceptance_gate"])
        if expected_worker_count is not None:
            self.assertEqual(contract["worker_count"], expected_worker_count)
        roles = contract["roles"]
        self.assertEqual(set(roles), {"planner", "worker", "repairer", "verifier", "reporter"})
        self.assertEqual(roles["worker"]["isolation"], "per-worker out_root")
        self.assertEqual(roles["repairer"]["round_cap"], 5)
        self.assertEqual(roles["verifier"]["acceptance_authority"], "competition-run-summary validator")
        self.assertEqual(roles["reporter"]["acceptance_authority"], "none")
        resume_protocol = contract["resume_protocol"]
        self.assertIn("evaluate --profile", resume_protocol["resume_entrypoints"])
        self.assertEqual(resume_protocol["worker_state_source"], "agent-index.agents_by_worker_id")

    def test_write_preflight_marker_emits_judge_required_report_kind(self) -> None:
        target_dir = REPO_ROOT / "target"
        target_dir.mkdir(exist_ok=True)
        with tempfile.TemporaryDirectory(prefix="opencode-marker-test-", dir=target_dir) as tmp:
            marker_path = Path(tmp) / "harness" / "opencode-preflight-marker.json"
            marker_rel = Path(harness.repo_relative(marker_path, repo_root=REPO_ROOT))

            result = harness.write_opencode_preflight_marker(
                marker_path=marker_rel,
                run_id="preflight-marker-kind-test",
                repo_root=REPO_ROOT,
            )

            payload = json.loads(marker_path.read_text(encoding="utf-8"))
            self.assertEqual(result["status"], "written")
            self.assertEqual(payload.get("report_kind"), "opencode-preflight-marker")
            self.assertEqual(payload.get("run_id"), "preflight-marker-kind-test")
            self.assertEqual(payload.get("status"), "written")

    def assert_architecture_contracts(self, contracts: dict) -> None:
        context_contract = contracts["context_management"]
        self.assertEqual(context_contract["contract_kind"], "context-management")
        self.assertEqual(context_contract["evidence_policy"], "on-disk-artifacts-only")
        self.assertFalse(context_contract["semantic_gate"])
        self.assertFalse(context_contract["chat_output_is_evidence"])
        self.assertEqual(
            [stage["stage"] for stage in context_contract["pipeline"]],
            ["plan", "translate", "verify", "repair"],
        )
        agent_contract = contracts["agent_coordination"]
        self.assertEqual(agent_contract["contract_kind"], "agent-coordination")
        self.assertEqual(set(agent_contract["roles"]), {"planner", "worker", "repairer", "verifier", "reporter"})
        self.assertEqual(agent_contract["planner_ownership"]["mode"], "single-planner-per-run")
        self.assertEqual(agent_contract["lease_policy"]["fencing_token"], "audit-only-monotonic-counter")
        self.assertFalse(agent_contract["semantic_gate"])
        self.assertFalse(agent_contract["chat_output_is_evidence"])

    def test_init_run_creates_sqlite_ledger_with_run_and_profile(self) -> None:
        with temp_repo_dir() as tmp:
            out_root = Path(tmp) / "competition-out"

            db_path = harness.init_run(
                out_root=out_root,
                run_id="run-test",
                proof_class="local-simulation",
                repo_root=REPO_ROOT,
            )

            self.assertEqual(db_path, out_root / "state" / "opencode-agent-harness.sqlite3")
            rows = fetch_rows(db_path, "select run_id, out_root, proof_class, profile_id from runs")
            self.assertEqual(
                rows,
                [
                    (
                        "run-test",
                        repo_rel(out_root),
                        "local-simulation",
                        "huawei-competition-ubuntu-24.04",
                    )
                ],
            )
            profile_rows = fetch_rows(db_path, "select profile_id, profile_path from profiles")
            self.assertEqual(profile_rows, [("huawei-competition-ubuntu-24.04", "config/competition-env/environment.json")])

    def test_sqlite_connection_sets_parallel_worker_busy_timeout(self) -> None:
        with temp_repo_dir() as tmp:
            db_path = Path(tmp) / "parallel.sqlite3"

            connection = harness.connect(db_path)
            try:
                busy_timeout = connection.execute("pragma busy_timeout").fetchone()[0]
            finally:
                connection.close()

            self.assertEqual(busy_timeout, 30000)

    def test_assign_slice_creates_worker_task_slice_lease_and_assignment_file(self) -> None:
        with temp_repo_dir() as tmp:
            out_root = Path(tmp) / "competition-out"
            spec_path = out_root / "slice-specs" / "demo-add-one.json"
            spec_path.parent.mkdir(parents=True)
            spec_path.write_text(json.dumps({"target_id": "demo", "slice_id": "demo-add-one"}), encoding="utf-8")
            db_path = harness.init_run(
                out_root=out_root,
                run_id="run-test",
                proof_class="local-simulation",
                repo_root=REPO_ROOT,
            )

            assignment = harness.assign_slice(
                db_path=db_path,
                run_id="run-test",
                worker_id="worker-a",
                target_id="demo",
                slice_id="demo-add-one",
                source_repo_root=Path("external/demo"),
                source_file="src/demo.c",
                function="add_one",
                source_commit="abc123",
                source_repository="https://gitcode.com/example/demo.git",
                source_branch="competition",
                require_source_commit="abc123",
                compiler_command_source="compile_commands.json",
                include_paths=["include", "src/include"],
                defines=["DEMO=1", "USE_FAST"],
                reuse_accepted_evidence=True,
                accepted_evidence_root="validation/evidence",
                slice_spec=repo_rel(spec_path),
                out_root=out_root / "workers" / "worker-a",
                lease_ttl_seconds=900,
                repo_root=REPO_ROOT,
            )

            self.assertEqual(assignment["worker_id"], "worker-a")
            self.assertEqual(assignment["run_id"], "run-test")
            self.assertEqual(assignment["slice"]["slice_id"], "demo-add-one")
            self.assertEqual(assignment["slice"]["source_repository"], "https://gitcode.com/example/demo.git")
            self.assertEqual(assignment["slice"]["source_branch"], "competition")
            self.assertEqual(assignment["slice"]["require_source_commit"], "abc123")
            self.assertEqual(assignment["out_root"], repo_rel(out_root / "workers" / "worker-a"))
            self.assertTrue((out_root / "harness" / "assignments" / "worker-a.json").exists())
            request_path = out_root / "harness" / "assignments" / "worker-a-request.json"
            self.assertTrue(request_path.exists())
            request = json.loads(request_path.read_text(encoding="utf-8"))
            self.assertEqual(request["source_repo_root"], "external/demo")
            self.assertEqual(request["source_repository"], "https://gitcode.com/example/demo.git")
            self.assertEqual(request["source_branch"], "competition")
            self.assertEqual(request["require_source_commit"], "abc123")
            self.assertEqual(request["source_file"], "src/demo.c")
            self.assertEqual(request["out_root"], repo_rel(out_root / "workers" / "worker-a"))
            self.assertEqual(request["compiler_command_source"], "compile_commands.json")
            self.assertEqual(request["include_paths"], ["include", "src/include"])
            self.assertEqual(request["defines"], ["DEMO=1", "USE_FAST"])
            self.assertIs(request["reuse_accepted_evidence"], True)
            self.assertEqual(request["accepted_evidence_root"], "validation/evidence")
            self.assertEqual(request["slice_specs"], [repo_rel(spec_path)])
            task_rows = fetch_rows(db_path, "select worker_name, role, status from agents")
            self.assertEqual(task_rows, [("worker-a", "slice-worker", "assigned")])
            slice_rows = fetch_rows(db_path, "select slice_spec_path, slice_spec_sha256 from slices")
            self.assertEqual(slice_rows[0][0], repo_rel(spec_path))
            self.assertIsNotNone(slice_rows[0][1])
            lease_rows = fetch_rows(db_path, "select resource_key, lease_owner, status from leases")
            self.assertEqual(lease_rows, [("slice:demo/demo-add-one", "worker-a", "active")])

            with self.assertRaises(SystemExit) as raised:
                harness.assign_slice(
                    db_path=db_path,
                    run_id="run-test",
                    worker_id="worker-b",
                    target_id="demo",
                    slice_id="demo-add-one",
                    source_repo_root=Path("external/demo"),
                    source_file="src/demo.c",
                    function="add_one",
                    source_commit="abc123",
                    out_root=out_root / "workers" / "worker-b",
                    repo_root=REPO_ROOT,
                )
            self.assertIn("active lease already exists", str(raised.exception))

    def test_assign_slice_rejects_duplicate_isolated_out_root_for_different_workers_in_run(self) -> None:
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
                out_root=out_root / "workers" / "shared",
                repo_root=REPO_ROOT,
            )

            with self.assertRaisesRegex(SystemExit, "isolated out_root already assigned"):
                harness.assign_slice(
                    db_path=db_path,
                    run_id="run-test",
                    worker_id="worker-b",
                    target_id="demo",
                    slice_id="demo-add-two",
                    source_repo_root=Path("external/demo"),
                    source_file="src/demo.c",
                    function="add_two",
                    source_commit="abc123",
                    out_root=out_root / "workers" / "shared",
                    repo_root=REPO_ROOT,
                )

    def test_assign_slice_cli_dispatches_source_pin_flags(self) -> None:
        argv = [
            "opencode_agent_harness.py",
            "assign-slice",
            "--db",
            "target/competition-out/state/opencode-agent-harness.sqlite3",
            "--run-id",
            "run-test",
            "--worker-id",
            "worker-a",
            "--target-id",
            "flashdb",
            "--slice-id",
            "real-fdb-calc-crc32",
            "--source-repo-root",
            "sources/FlashDB",
            "--source-repository",
            "https://gitcode.com/xwxf/FlashDB.git",
            "--source-branch",
            "competition",
            "--source-file",
            "src/fdb_utils.c",
            "--function",
            "fdb_calc_crc32",
            "--source-commit",
            "f9d0421315c564fb890a1b14eee77b290e0d7bbe",
            "--require-source-commit",
            "f9d0421315c564fb890a1b14eee77b290e0d7bbe",
            "--out-root",
            "target/competition-out/workers/worker-a",
        ]

        with patch("sys.argv", argv), patch("sys.stdout", io.StringIO()), patch.object(
            harness,
            "assign_slice",
            return_value={"status": "assigned"},
        ) as assign:
            self.assertEqual(harness.main(), 0)

        assign.assert_called_once()
        self.assertEqual(assign.call_args.kwargs["source_repository"], "https://gitcode.com/xwxf/FlashDB.git")
        self.assertEqual(assign.call_args.kwargs["source_branch"], "competition")
        self.assertEqual(
            assign.call_args.kwargs["require_source_commit"],
            "f9d0421315c564fb890a1b14eee77b290e0d7bbe",
        )

    def test_plan_source_file_creates_ordered_worker_assignments_from_c_functions(self) -> None:
        with temp_repo_dir() as tmp:
            out_root = Path(tmp) / "competition-out"
            source_root = Path(tmp) / "FlashDB"
            source_file = source_root / "src" / "demo.c"
            source_file.parent.mkdir(parents=True)
            source_file.write_text(
                """
                int first_unit(int value) {
                    if (value > 0) {
                        return value + 1;
                    }
                    return value;
                }

                static int second_unit(void)
                {
                    return first_unit(1);
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
                source_repository="https://gitcode.com/xwxf/FlashDB.git",
                source_branch="competition",
                require_source_commit="abc123",
                compiler_command_source="compile_commands.json",
                include_paths=["inc"],
                defines=["FDB_USING_KVDB"],
                out_root=out_root,
                slice_id_prefix="real-demo",
                worker_prefix="worker",
                repo_root=REPO_ROOT,
            )

            self.assertEqual(plan["status"], "planned")
            self.assertEqual([unit["function"] for unit in plan["units"]], ["first_unit", "second_unit"])
            self.assertEqual([unit["slice_id"] for unit in plan["units"]], ["real-demo-first-unit", "real-demo-second-unit"])
            self.assertEqual([unit["worker_id"] for unit in plan["units"]], ["worker-001-first-unit", "worker-002-second-unit"])
            plan_path = REPO_ROOT / plan["plan_path"]
            self.assertTrue(plan_path.exists())

            first_request = out_root / "harness" / "assignments" / "worker-001-first-unit-request.json"
            second_request = out_root / "harness" / "assignments" / "worker-002-second-unit-request.json"
            self.assertTrue(first_request.exists())
            self.assertTrue(second_request.exists())
            first_payload = json.loads(first_request.read_text(encoding="utf-8"))
            self.assertEqual(first_payload["function"], "first_unit")
            self.assertEqual(first_payload["slice_id"], "real-demo-first-unit")
            self.assertEqual(first_payload["out_root"], repo_rel(out_root / "workers" / "worker-001-first-unit"))
            self.assertEqual(first_payload["source_repository"], "https://gitcode.com/xwxf/FlashDB.git")
            self.assertEqual(first_payload["source_branch"], "competition")
            self.assertEqual(first_payload["require_source_commit"], "abc123")
            self.assertEqual(first_payload["compiler_command_source"], "compile_commands.json")
            self.assertEqual(first_payload["include_paths"], ["inc"])
            self.assertEqual(first_payload["defines"], ["FDB_USING_KVDB"])

            rows = fetch_rows(db_path, "select agent_id, isolated_out_root from agents order by agent_id")
            self.assertEqual(
                rows,
                [
                    ("worker-001-first-unit", repo_rel(out_root / "workers" / "worker-001-first-unit")),
                    ("worker-002-second-unit", repo_rel(out_root / "workers" / "worker-002-second-unit")),
                ],
            )

    def test_plan_source_file_filters_functions_and_binds_slice_specs(self) -> None:
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
            spec_path = Path(tmp) / "slice-specs" / "second-unit.json"
            spec_path.parent.mkdir(parents=True)
            spec_path.write_text(
                json.dumps(
                    {
                        "target_id": "flashdb",
                        "slice_id": "real-demo-second-unit",
                        "function_name": "second_unit",
                        "source_commit": "abc123",
                    }
                ),
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
                reuse_accepted_evidence=True,
                accepted_evidence_root="validation/evidence",
                out_root=out_root,
                slice_id_prefix="wrong-prefix",
                worker_prefix="worker",
                functions=["second_unit"],
                slice_specs=[repo_rel(spec_path)],
                repo_root=REPO_ROOT,
            )

            self.assertEqual([unit["function"] for unit in plan["units"]], ["second_unit"])
            self.assertEqual([unit["slice_id"] for unit in plan["units"]], ["real-demo-second-unit"])
            self.assertEqual(plan["units"][0]["slice_spec"], repo_rel(spec_path))
            request_path = out_root / "harness" / "assignments" / "worker-001-second-unit-request.json"
            request = json.loads(request_path.read_text(encoding="utf-8"))
            self.assertEqual(request["function"], "second_unit")
            self.assertEqual(request["slice_id"], "real-demo-second-unit")
            self.assertIs(request["reuse_accepted_evidence"], True)
            self.assertEqual(request["accepted_evidence_root"], "validation/evidence")
            self.assertEqual(request["slice_specs"], [repo_rel(spec_path)])
            rows = fetch_rows(db_path, "select slice_id, function_name, slice_spec_path from slices")
            self.assertEqual(rows, [("real-demo-second-unit", "second_unit", repo_rel(spec_path))])

    def test_plan_source_file_rejects_mismatched_slice_spec_binding(self) -> None:
        with temp_repo_dir() as tmp:
            out_root = Path(tmp) / "competition-out"
            source_root = Path(tmp) / "FlashDB"
            source_file = source_root / "src" / "demo.c"
            source_file.parent.mkdir(parents=True)
            source_file.write_text("int second_unit(int value) { return value + 2; }\n", encoding="utf-8")
            spec_path = Path(tmp) / "slice-specs" / "second-unit.json"
            spec_path.parent.mkdir(parents=True)
            spec_path.write_text(
                json.dumps(
                    {
                        "target_id": "other-target",
                        "slice_id": "real-demo-second-unit",
                        "function_name": "second_unit",
                        "source_commit": "abc123",
                    }
                ),
                encoding="utf-8",
            )
            db_path = harness.init_run(
                out_root=out_root,
                run_id="run-test",
                proof_class="local-simulation",
                repo_root=REPO_ROOT,
            )

            with self.assertRaises(SystemExit) as raised:
                harness.plan_source_file(
                    db_path=db_path,
                    run_id="run-test",
                    target_id="flashdb",
                    source_repo_root=source_root,
                    source_file="src/demo.c",
                    source_commit="abc123",
                    out_root=out_root,
                    slice_id_prefix="real-demo",
                    functions=["second_unit"],
                    slice_specs=[repo_rel(spec_path)],
                    repo_root=REPO_ROOT,
                )

            self.assertIn("slice spec target_id mismatch", str(raised.exception))

    def test_run_plan_executes_planned_workers_and_writes_merge_plan(self) -> None:
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
                out_root=out_root,
                slice_id_prefix="real-demo",
                worker_prefix="worker",
                repo_root=REPO_ROOT,
            )
            calls: list[str] = []

            def fake_runner(argv: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
                request_path = REPO_ROOT / argv[argv.index("--input") + 1]
                request = json.loads(request_path.read_text(encoding="utf-8"))
                worker_id = Path(request["out_root"]).name
                calls.append(worker_id)
                summary_path = REPO_ROOT / request["out_root"] / "summary" / "competition-run-summary.json"
                write_worker_summary(summary_path, request["run_id"], status="passed", failed=0, semantic_pass=1)
                return subprocess.CompletedProcess(argv, 0, stdout=f"{worker_id} ok\n", stderr="")

            result = harness.run_plan(
                db_path=db_path,
                run_id="run-test",
                plan_path=REPO_ROOT / plan["plan_path"],
                out_root=out_root,
                proof_class="local-simulation",
                command_runner=fake_runner,
                repo_root=REPO_ROOT,
            )

            self.assertEqual(result["status"], "completed")
            self.assertEqual(result["exit_code"], 0)
            self.assertEqual(calls, ["worker-001-first-unit", "worker-002-second-unit"])
            self.assertEqual([worker["exit_code"] for worker in result["workers"]], [0, 0])
            self.assertEqual(
                [worker["summary_status"] for worker in result["workers"]],
                ["passed", "passed"],
            )
            report_path = REPO_ROOT / result["report_path"]
            self.assertTrue(report_path.exists())
            report = json.loads(report_path.read_text(encoding="utf-8"))
            self.assertEqual(report["plan_path"], plan["plan_path"])
            self.assertEqual(report["worker_count"], 2)
            self.assertEqual(report["failed_workers"], 0)
            merge_plan_path = out_root / "harness" / "merge-plan.json"
            self.assertTrue(merge_plan_path.exists())
            merge_plan = json.loads(merge_plan_path.read_text(encoding="utf-8"))
            first_summary = out_root / "workers" / "worker-001-first-unit" / "summary" / "competition-run-summary.json"
            second_summary = out_root / "workers" / "worker-002-second-unit" / "summary" / "competition-run-summary.json"
            self.assertEqual(
                merge_plan["worker_summaries"],
                [repo_rel(first_summary), repo_rel(second_summary)],
            )

    def test_run_plan_auto_retries_failed_worker_before_merge(self) -> None:
        with temp_repo_dir() as tmp:
            out_root = Path(tmp) / "competition-out"
            source_root = Path(tmp) / "FlashDB"
            source_file = source_root / "src" / "demo.c"
            source_file.parent.mkdir(parents=True)
            source_file.write_text(
                """
                int repairable_unit(int value) {
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
            worker_attempts = 0
            merge_calls: list[list[str]] = []

            def fake_runner(argv: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
                nonlocal worker_attempts
                if "scripts/c2rust-migrator.py" in argv:
                    worker_attempts += 1
                    request_path = REPO_ROOT / argv[argv.index("--input") + 1]
                    request = json.loads(request_path.read_text(encoding="utf-8"))
                    summary_path = REPO_ROOT / request["out_root"] / "summary" / "competition-run-summary.json"
                    if worker_attempts < 3:
                        write_worker_summary(summary_path, request["run_id"], status="failed", failed=1, semantic_pass=0)
                    else:
                        write_worker_summary(summary_path, request["run_id"], status="passed", failed=0, semantic_pass=1)
                    return subprocess.CompletedProcess(argv, 0, stdout=f"worker attempt {worker_attempts}\n", stderr="")
                merge_calls.append(argv)
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
                auto_retry=True,
                command_runner=fake_runner,
                repo_root=REPO_ROOT,
            )

            self.assertEqual(result["status"], "completed")
            self.assertEqual(result["exit_code"], 0)
            self.assertEqual(worker_attempts, 3)
            self.assertEqual(len(merge_calls), 1)
            self.assertEqual(result["failed_workers"], 0)
            self.assertEqual(result["workers"][0]["summary_status"], "passed")
            self.assertEqual(result["workers"][0]["auto_retry"]["attempt_count"], 2)
            self.assertEqual(result["workers"][0]["auto_retry"]["final_hint_status"], "revalidated_passed")
            hint_rows = fetch_rows(db_path, "select status from repair_hints")
            self.assertEqual(hint_rows, [("revalidated_passed",)])

    def test_run_plan_auto_retry_suppresses_after_command_database_lock(self) -> None:
        with temp_repo_dir() as tmp:
            out_root = Path(tmp) / "competition-out"
            db_path = harness.init_run(
                out_root=out_root,
                run_id="run-after-command-lock",
                proof_class="local-simulation",
                repo_root=REPO_ROOT,
            )
            plan_path = out_root / "harness" / "worker-plan.json"
            plan_path.parent.mkdir(parents=True, exist_ok=True)
            plan_path.write_text(
                json.dumps(
                    {
                        "schema_version": 1,
                        "run_id": "run-after-command-lock",
                        "plan_path": repo_rel(plan_path),
                        "units": [{"worker_id": "worker-a", "slice_id": "demo-add-one", "function": "add_one"}],
                    },
                    sort_keys=True,
                )
                + "\n",
                encoding="utf-8",
            )

            def fake_run_worker(**kwargs: object) -> dict[str, object]:
                return {
                    "exit_code": 1,
                    "process_returncode": 1,
                    "summary_status": "blocked",
                    "summary_path": repo_rel(out_root / "workers" / "worker-a" / "summary" / "competition-run-summary.json"),
                    "report_path": repo_rel(out_root / "workers" / "worker-a" / "harness" / "run-worker-report.json"),
                    "logs": {},
                    "recorded": False,
                    "repair_hint": {
                        "hint_id": "repair:run-after-command-lock:worker-a:database_locked_after_command",
                        "root_cause_key": "opencode_database_locked_after_worker_command_seen",
                    },
                    "opencode_contract_verification": {"status": "executed"},
                }

            def fake_retry_worker(**kwargs: object) -> dict[str, object]:
                raise AssertionError("run-plan must not relaunch a worker command after it reached the shell")

            with patch.object(harness, "run_worker", side_effect=fake_run_worker), patch.object(
                harness, "retry_worker", side_effect=fake_retry_worker
            ):
                result = harness.run_plan(
                    db_path=db_path,
                    run_id="run-after-command-lock",
                    plan_path=plan_path,
                    out_root=out_root,
                    proof_class="local-simulation",
                    auto_retry=True,
                    repo_root=REPO_ROOT,
                )

            worker = result["workers"][0]
            self.assertNotIn("auto_retry", worker)
            self.assertEqual([attempt["attempt"] for attempt in worker["attempts"]], [1])
            self.assertEqual(
                worker["auto_retry_suppressed"],
                {
                    "status": "suppressed",
                    "hint_id": "repair:run-after-command-lock:worker-a:database_locked_after_command",
                    "root_cause_key": "opencode_database_locked_after_worker_command_seen",
                    "reason": "assigned worker command already reached the shell; retry would risk duplicate execution",
                    "evidence_boundary": "opencode_contract_verification.status=executed",
                },
            )

    def test_run_plan_auto_retry_has_defensive_outer_cap_if_retry_worker_regresses(self) -> None:
        with temp_repo_dir() as tmp:
            out_root = Path(tmp) / "competition-out"
            db_path = harness.init_run(
                out_root=out_root,
                run_id="run-outer-cap",
                proof_class="local-simulation",
                repo_root=REPO_ROOT,
            )
            plan_path = out_root / "harness" / "worker-plan.json"
            plan_path.parent.mkdir(parents=True, exist_ok=True)
            plan_path.write_text(
                json.dumps(
                    {
                        "schema_version": 1,
                        "run_id": "run-outer-cap",
                        "plan_path": repo_rel(plan_path),
                        "units": [{"worker_id": "worker-a", "slice_id": "demo-add-one", "function": "add_one"}],
                    },
                    sort_keys=True,
                )
                + "\n",
                encoding="utf-8",
            )
            outer_cap = harness.REPAIR_ROUND_CAP + 2
            retry_calls = 0

            def fake_run_worker(**kwargs: object) -> dict[str, object]:
                return {
                    "exit_code": 1,
                    "process_returncode": 1,
                    "summary_status": "failed",
                    "summary_path": repo_rel(out_root / "workers" / "worker-a" / "summary" / "competition-run-summary.json"),
                    "report_path": repo_rel(out_root / "workers" / "worker-a" / "harness" / "run-worker-report.json"),
                    "logs": {},
                    "recorded": False,
                    "repair_hint": {"hint_id": "repair:run-outer-cap:worker-a:compile_failed"},
                }

            def fake_retry_worker(**kwargs: object) -> dict[str, object]:
                nonlocal retry_calls
                retry_calls += 1
                if retry_calls > outer_cap:
                    raise AssertionError("run_plan auto_retry did not stop at the defensive outer cap")
                return {
                    "exit_code": 1,
                    "process_returncode": 1,
                    "status": "revalidated_failed",
                    "hint_id": "repair:run-outer-cap:worker-a:compile_failed",
                    "hint_status": "revalidated_failed",
                    "summary_status": "failed",
                    "summary_path": repo_rel(out_root / "workers" / "worker-a" / "summary" / "competition-run-summary.json"),
                    "report_path": repo_rel(out_root / "workers" / "worker-a" / "harness" / "run-worker-report.json"),
                    "logs": {},
                    "recorded": False,
                }

            with patch.object(harness, "run_worker", side_effect=fake_run_worker), patch.object(
                harness, "retry_worker", side_effect=fake_retry_worker
            ):
                result = harness.run_plan(
                    db_path=db_path,
                    run_id="run-outer-cap",
                    plan_path=plan_path,
                    out_root=out_root,
                    proof_class="local-simulation",
                    auto_retry=True,
                    repo_root=REPO_ROOT,
                )

            worker = result["workers"][0]
            self.assertEqual(retry_calls, outer_cap)
            self.assertEqual(worker["auto_retry"]["attempt_count"], outer_cap)
            self.assertEqual(worker["auto_retry"]["outer_round_cap"], outer_cap)
            self.assertEqual(worker["auto_retry"]["final_hint_status"], "outer_retry_limit_exceeded")
            self.assertEqual(
                worker["auto_retry"]["attempts"][-1]["outer_retry_limit"],
                {
                    "max_outer_rounds": outer_cap,
                    "reason": "retry_worker did not return success or retry_limit_exceeded",
                },
            )

    def test_run_plan_report_preserves_retry_attempt_timeline_rollback_and_final_decision(self) -> None:
        with temp_repo_dir() as tmp:
            out_root = Path(tmp) / "competition-out"
            source_root = Path(tmp) / "FlashDB"
            source_file = source_root / "src" / "demo.c"
            source_file.parent.mkdir(parents=True)
            source_file.write_text(
                """
                int repairable_unit(int value) {
                    return value + 1;
                }
                """,
                encoding="utf-8",
            )
            db_path = harness.init_run(
                out_root=out_root,
                run_id="run-retry-timeline",
                proof_class="local-simulation",
                repo_root=REPO_ROOT,
            )
            plan = harness.plan_source_file(
                db_path=db_path,
                run_id="run-retry-timeline",
                target_id="flashdb",
                source_repo_root=source_root,
                source_file="src/demo.c",
                source_commit="abc123",
                out_root=out_root,
                slice_id_prefix="timeline",
                worker_prefix="worker",
                repo_root=REPO_ROOT,
            )
            worker_attempts = 0

            def fake_runner(argv: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
                nonlocal worker_attempts
                if "scripts/c2rust-migrator.py" in argv:
                    worker_attempts += 1
                    request_path = REPO_ROOT / argv[argv.index("--input") + 1]
                    request = json.loads(request_path.read_text(encoding="utf-8"))
                    summary_path = REPO_ROOT / request["out_root"] / "summary" / "competition-run-summary.json"
                    if worker_attempts == 1:
                        write_worker_summary(summary_path, request["run_id"], status="failed", failed=1, semantic_pass=0)
                    else:
                        write_worker_summary(summary_path, request["run_id"], status="passed", failed=0, semantic_pass=1)
                    return subprocess.CompletedProcess(argv, 0, stdout=f"worker attempt {worker_attempts}\n", stderr="")
                summary_path = out_root / "summary" / "competition-run-summary.json"
                write_worker_summary(summary_path, "run-retry-timeline", status="passed", failed=0, semantic_pass=1)
                return subprocess.CompletedProcess(argv, 0, stdout="merge ok\n", stderr="")

            result = harness.run_plan(
                db_path=db_path,
                run_id="run-retry-timeline",
                plan_path=REPO_ROOT / plan["plan_path"],
                out_root=out_root,
                proof_class="local-simulation",
                execute_merge=True,
                auto_retry=True,
                command_runner=fake_runner,
                repo_root=REPO_ROOT,
            )

            worker = result["workers"][0]
            self.assertEqual(result["status"], "completed")
            self.assertEqual(worker["final_decision"], {"status": "accepted", "reason": "worker_summary_passed"})
            self.assertEqual([attempt["attempt"] for attempt in worker["attempts"]], [1, 2])
            self.assertEqual([attempt["summary_status"] for attempt in worker["attempts"]], ["failed", "passed"])
            self.assertEqual(worker["attempts"][0]["hint_status"], "opened")
            self.assertEqual(worker["attempts"][1]["hint_status"], "revalidated_passed")
            rollback = worker["attempts"][1]["rollback_evidence"]
            self.assertRegex(rollback["sha256"], r"^[0-9a-f]{64}$")
            self.assertTrue((REPO_ROOT / rollback["path"]).exists())
            persisted = json.loads((out_root / "harness" / "run-plan-report.json").read_text(encoding="utf-8"))
            self.assertEqual(persisted["workers"][0]["attempts"], worker["attempts"])
            self.assertEqual(persisted["workers"][0]["final_decision"], worker["final_decision"])

    def test_evaluate_context_pack_records_auto_retry_success(self) -> None:
        with temp_repo_dir() as tmp:
            out_root = Path(tmp) / "competition-out"
            source_root = Path(tmp) / "FlashDB"
            source_file = source_root / "src" / "demo.c"
            source_file.parent.mkdir(parents=True)
            source_file.write_text(
                """
                int repairable_unit(int value) {
                    return value + 1;
                }
                """,
                encoding="utf-8",
            )
            worker_attempts = 0

            def fake_runner(argv: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
                nonlocal worker_attempts
                if "scripts/c2rust-migrator.py" in argv:
                    worker_attempts += 1
                    request_path = REPO_ROOT / argv[argv.index("--input") + 1]
                    request = json.loads(request_path.read_text(encoding="utf-8"))
                    summary_path = REPO_ROOT / request["out_root"] / "summary" / "competition-run-summary.json"
                    if worker_attempts < 3:
                        write_worker_summary(summary_path, request["run_id"], status="failed", failed=1, semantic_pass=0)
                    else:
                        write_worker_summary(summary_path, request["run_id"], status="passed", failed=0, semantic_pass=1)
                    return subprocess.CompletedProcess(argv, 0, stdout=f"worker attempt {worker_attempts}\n", stderr="")
                summary_path = out_root / "summary" / "competition-run-summary.json"
                write_worker_summary(summary_path, "run-evaluate-retry", status="passed", failed=0, semantic_pass=1)
                return subprocess.CompletedProcess(argv, 0, stdout="merge ok\n", stderr="")

            result = harness.evaluate(
                run_id="run-evaluate-retry",
                target_id="flashdb",
                source_repo_root=source_root,
                source_file="src/demo.c",
                functions=["repairable_unit"],
                source_commit="abc123",
                out_root=out_root,
                proof_class="local-simulation",
                slice_id_prefix="eval-retry",
                worker_prefix="eval-worker",
                execute_merge=True,
                auto_retry=True,
                command_runner=fake_runner,
                repo_root=REPO_ROOT,
            )

            self.assertEqual(result["status"], "completed")
            self.assertEqual(worker_attempts, 3)
            context_pack = json.loads((REPO_ROOT / result["context_pack"]["path"]).read_text(encoding="utf-8"))
            agent_index = json.loads((REPO_ROOT / result["agent_index"]["path"]).read_text(encoding="utf-8"))
            worker = context_pack["workers"][0]
            agent = agent_index["agents"][0]
            self.assertTrue(worker["recorded"])
            self.assertEqual(worker["summary_status"], "passed")
            self.assertEqual(worker["auto_retry"]["attempt_count"], 2)
            self.assertEqual(worker["auto_retry"]["final_hint_status"], "revalidated_passed")
            self.assertEqual([attempt["hint_status"] for attempt in worker["auto_retry"]["attempts"]], ["revalidated_failed", "revalidated_passed"])
            self.assertEqual(worker["final_decision"], {"status": "accepted", "reason": "worker_summary_passed"})
            self.assertEqual([attempt["summary_status"] for attempt in worker["attempts"]], ["failed", "failed", "passed"])
            self.assertEqual([attempt["hint_status"] for attempt in worker["attempts"]], ["opened", "revalidated_failed", "revalidated_passed"])
            self.assertEqual(agent["status"], "passed")
            self.assertTrue(agent["recorded"])
            self.assertEqual(agent["final_decision"], worker["final_decision"])
            self.assertEqual(agent["attempts"], worker["attempts"])
            hint_rows = fetch_rows(Path(REPO_ROOT / result["db_path"]), "select status from repair_hints")
            self.assertEqual(hint_rows, [("revalidated_passed",)])
