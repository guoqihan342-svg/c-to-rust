def write_auto_route_profile(
    root: Path,
    *,
    mode: str = "auto",
    second_reuse_accepted_evidence: bool = True,
) -> tuple[Path, Path]:
    source_root = root / "source"
    source_path = source_root / "src" / "demo.c"
    source_path.parent.mkdir(parents=True, exist_ok=True)
    source_path.write_text(
        "int first_unit(int x) { return x + 1; }\nint second_unit(int x) { return x + 2; }\n",
        encoding="utf-8",
    )
    source_sha256 = harness.sha256_file(source_path)
    accepted_evidence_root = root / "accepted-evidence"
    accepted_evidence_root.mkdir(parents=True, exist_ok=True)
    workers = []
    for index, function_name in enumerate(("first_unit", "second_unit"), start=1):
        slice_id = f"demo-{function_name.replace('_', '-')}"
        spec_path = root / "slice-specs" / f"{function_name}.json"
        write_json(
            spec_path,
            {
                "schema_version": 1,
                "target_id": "demo",
                "slice_id": slice_id,
                "function_name": function_name,
                "source_commit": "commit-auto",
                "source": {
                    "source_commit": "commit-auto",
                    "source_file_hashes": {"src/demo.c": source_sha256},
                },
            },
        )
        worker = {
            "worker_id": f"auto-worker-{index:03d}-{function_name}",
            "source_repo_root": repo_rel(source_root),
            "source_file": "src/demo.c",
            "function": function_name,
            "slice_id": slice_id,
            "source_commit": "commit-auto",
            "slice_spec": repo_rel(spec_path),
        }
        if index == 2:
            worker["reuse_accepted_evidence"] = second_reuse_accepted_evidence
        workers.append(worker)
    profile_path = root / "auto-route-profile.json"
    write_json(
        profile_path,
        {
            "schema_version": 1,
            "profile_id": "auto-route-test",
            "proof_class": "local-simulation",
            "target_id": "demo",
            "mode": mode,
            "reuse_accepted_evidence": True,
            "accepted_evidence_root": repo_rel(accepted_evidence_root),
            "execute_merge": False,
            "auto_retry": False,
            "max_workers": 2,
            "workers": workers,
        },
    )
    return profile_path, source_path


class _OpenCodeAgentHarnessTestPart11:
    def test_auto_mode_routes_bound_workers_to_parallel_deterministic_execution(self) -> None:
        with temp_repo_dir() as tmp:
            root = Path(tmp)
            profile_path, _ = write_auto_route_profile(root)
            out_root = root / "out"
            barrier = threading.Barrier(2)
            calls: list[list[str]] = []

            def deterministic_runner(argv: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
                self.assertIn("scripts/c2rust-migrator.py", argv)
                self.assertNotEqual(argv[0], "opencode")
                calls.append(argv)
                barrier.wait(timeout=5)
                request_path = REPO_ROOT / argv[argv.index("--input") + 1]
                request = json.loads(request_path.read_text(encoding="utf-8"))
                summary_path = REPO_ROOT / request["out_root"] / "summary" / "competition-run-summary.json"
                write_worker_summary(summary_path, request["run_id"], status="passed", failed=0, semantic_pass=1)
                return subprocess.CompletedProcess(argv, 0, stdout="deterministic ok\n", stderr="")

            result = harness.run_batch_profile(
                profile_path=profile_path,
                run_id="run-auto-bound",
                out_root=out_root,
                command_runner=deterministic_runner,
                repo_root=REPO_ROOT,
            )

            self.assertEqual(len(calls), 2)
            self.assertEqual(result["status"], "completed")
            self.assertEqual(result["mode"], "deterministic")
            self.assertEqual(result["requested_mode"], "auto")
            self.assertEqual(result["effective_mode"], "deterministic")
            self.assertEqual(result["route_reason"], "all_workers_hash_bound_accepted_evidence")
            self.assertFalse(result["semantic_gate"])
            self.assertEqual(
                [worker["worker_id"] for worker in result["run_plan"]["workers"]],
                [
                    "auto-worker-001-first_unit",
                    "auto-worker-002-second_unit",
                ],
            )
            self.assertEqual(result["run_plan"]["requested_mode"], "auto")
            self.assertEqual(result["run_plan"]["effective_mode"], "deterministic")
            self.assertFalse(result["run_plan"]["semantic_gate"])
            context_pack = json.loads((REPO_ROOT / result["context_pack"]["path"]).read_text(encoding="utf-8"))
            self.assertEqual(context_pack["requested_mode"], "auto")
            self.assertEqual(context_pack["effective_mode"], "deterministic")
            self.assertEqual(context_pack["execution_route"], result["execution_route"])
            self.assertFalse(context_pack["semantic_gate"])
            artifact_rows = fetch_rows(
                REPO_ROOT / result["db_path"],
                "select agent_id from artifacts where kind='competition-run-summary' order by agent_id",
            )
            self.assertEqual(
                artifact_rows,
                [("auto-worker-001-first_unit",), ("auto-worker-002-second_unit",)],
            )

    def test_auto_mode_refuses_unbound_worker_before_preflight_or_fanout(self) -> None:
        with temp_repo_dir() as tmp:
            root = Path(tmp)
            profile_path, _ = write_auto_route_profile(root)
            profile = json.loads(profile_path.read_text(encoding="utf-8"))
            del profile["workers"][1]["slice_spec"]
            write_json(profile_path, profile)
            out_root = root / "out"
            call_count = 0

            def runner_should_not_run(argv: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
                nonlocal call_count
                call_count += 1
                raise AssertionError("auto_route_unbound must stop before preflight and fanout")

            result = harness.run_batch_profile(
                profile_path=profile_path,
                run_id="run-auto-unbound",
                out_root=out_root,
                command_runner=runner_should_not_run,
                repo_root=REPO_ROOT,
            )

            self.assertEqual(call_count, 0)
            self.assertEqual(result["status"], "blocked")
            self.assertEqual(result["root_cause_key"], "auto_route_unbound")
            self.assertEqual(result["blocked_phase"], "execution-route-admission")
            self.assertIsNone(result["effective_mode"])
            self.assertFalse(result["semantic_gate"])
            self.assertFalse((out_root / "state" / "opencode-agent-harness.sqlite3").exists())
            blocker_kinds = {blocker["kind"] for blocker in result["execution_route"]["blockers"]}
            self.assertIn("worker_not_deterministic_accepted_evidence_bound", blocker_kinds)

    def test_auto_mode_refuses_mixed_batch_before_fanout(self) -> None:
        with temp_repo_dir() as tmp:
            root = Path(tmp)
            profile_path, _ = write_auto_route_profile(
                root,
                second_reuse_accepted_evidence=False,
            )
            out_root = root / "out"
            result = harness.run_batch_profile(
                profile_path=profile_path,
                run_id="run-auto-mixed",
                out_root=out_root,
                command_runner=lambda *args, **kwargs: (_ for _ in ()).throw(
                    AssertionError("mixed auto batch must not fan out")
                ),
                repo_root=REPO_ROOT,
            )

            self.assertEqual(result["root_cause_key"], "auto_route_unbound")
            bindings = result["execution_route"]["worker_bindings"]
            self.assertEqual([binding["status"] for binding in bindings], ["bound", "unbound"])
            self.assertIn("reuse_accepted_evidence_not_enabled", bindings[1]["blockers"])
            self.assertFalse((out_root / "state" / "opencode-agent-harness.sqlite3").exists())

    def test_auto_mode_cannot_downgrade_competition_or_opencode_attestation(self) -> None:
        with temp_repo_dir() as tmp:
            root = Path(tmp)
            profile_path, _ = write_auto_route_profile(root)
            profile = json.loads(profile_path.read_text(encoding="utf-8"))
            competition_route = harness.resolve_batch_execution_route(
                profile,
                "competition-exact",
                repo_root=REPO_ROOT,
            )
            self.assertEqual(competition_route["status"], "blocked")
            self.assertIn(
                "competition_exact_requires_explicit_opencode",
                {blocker["kind"] for blocker in competition_route["blockers"]},
            )

            profile["opencode_preflight_report"] = "target/preflight.json"
            attested_route = harness.resolve_batch_execution_route(
                profile,
                "local-simulation",
                repo_root=REPO_ROOT,
            )
            self.assertEqual(attested_route["status"], "blocked")
            self.assertIn(
                "explicit_opencode_attestation_requires_explicit_opencode",
                {blocker["kind"] for blocker in attested_route["blockers"]},
            )

            profile.pop("opencode_preflight_report")
            profile["opencode_hostless_rehearsal"] = True
            hostless_route = harness.resolve_batch_execution_route(
                profile,
                "local-simulation",
                repo_root=REPO_ROOT,
            )
            self.assertEqual(hostless_route["status"], "blocked")
            self.assertIn(
                "hostless_rehearsal_requires_explicit_opencode",
                {blocker["kind"] for blocker in hostless_route["blockers"]},
            )

            profile.pop("opencode_hostless_rehearsal")
            profile["attempt_evidence_policy"] = {}
            repair_route = harness.resolve_batch_execution_route(
                profile,
                "local-simulation",
                repo_root=REPO_ROOT,
            )
            self.assertEqual(repair_route["status"], "blocked")
            self.assertIn(
                "attempt_evidence_policy_disables_auto_route",
                {blocker["kind"] for blocker in repair_route["blockers"]},
            )

    def test_explicit_modes_preserve_existing_routes_and_direct_auto_plan_refuses(self) -> None:
        explicit_deterministic = harness.resolve_batch_execution_route(
            {"mode": "deterministic"},
            "local-simulation",
            repo_root=REPO_ROOT,
        )
        explicit_opencode = harness.resolve_batch_execution_route(
            {"mode": "opencode"},
            "competition-exact",
            repo_root=REPO_ROOT,
        )
        self.assertEqual(explicit_deterministic["effective_mode"], "deterministic")
        self.assertEqual(explicit_opencode["effective_mode"], "opencode")
        self.assertEqual(explicit_opencode["reason"], "explicit_opencode")

        with temp_repo_dir() as tmp:
            root = Path(tmp)
            plan_path = root / "plan.json"
            write_json(plan_path, {"schema_version": 1, "run_id": "run-direct-auto", "units": [{}]})
            with self.assertRaisesRegex(SystemExit, "requires run-batch-profile admission"):
                harness.run_plan(
                    db_path=root / "state.sqlite3",
                    run_id="run-direct-auto",
                    plan_path=plan_path,
                    out_root=root / "out",
                    proof_class="local-simulation",
                    mode="auto",
                    repo_root=REPO_ROOT,
                )
