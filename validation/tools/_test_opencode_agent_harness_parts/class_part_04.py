class _OpenCodeAgentHarnessTestPart04:
    def test_run_batch_profile_cli_dispatches_profile_flags(self) -> None:
        argv = [
            "opencode_agent_harness.py",
            "run-batch-profile",
            "--profile",
            "config/competition-env/planned-batches/flashdb-fdb-utils-accepted-evidence.json",
            "--run-id",
            "run-profile",
            "--out-root",
            "target/competition-out-profile",
        ]

        with patch("sys.argv", argv), patch("sys.stdout", io.StringIO()) as stdout, patch.object(
            harness,
            "run_batch_profile",
            return_value={"status": "completed", "exit_code": 0},
        ) as runner:
            self.assertEqual(harness.main(), 0)

        payload = json.loads(stdout.getvalue())
        self.assertEqual(payload["status"], "completed")
        runner.assert_called_once()
        self.assertEqual(
            runner.call_args.kwargs["profile_path"],
            Path("config/competition-env/planned-batches/flashdb-fdb-utils-accepted-evidence.json"),
        )
        self.assertEqual(runner.call_args.kwargs["run_id"], "run-profile")
        self.assertEqual(runner.call_args.kwargs["out_root"], Path("target/competition-out-profile"))

    def test_evaluate_cli_dispatches_h1_h5_flags(self) -> None:
        argv = [
            "opencode_agent_harness.py",
            "evaluate",
            "--run-id",
            "run-evaluate-cli",
            "--target-id",
            "flashdb",
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
            "--function",
            "fdb_blob_make",
            "--source-commit",
            "abc123",
            "--require-source-commit",
            "abc123",
            "--slice-spec",
            "validation/slice-specs/flashdb-real-fdb-calc-crc32.json",
            "--compiler-command-source",
            "compile_commands.json",
            "--include-path",
            "inc",
            "--define",
            "FDB_USING_KVDB",
            "--reuse-accepted-evidence",
            "--accepted-evidence-root",
            "validation/evidence",
            "--out-root",
            "target/competition-out-evaluate",
            "--slice-id-prefix",
            "flashdb-fdb-utils",
            "--worker-prefix",
            "flashdb-worker",
            "--limit",
            "2",
            "--proof-class",
            "local-simulation",
            "--mode",
            "opencode",
            "--opencode-command",
            "opencode",
            "--opencode-model",
            "GLM-5.1",
            "--opencode-agent",
            "c2rust-migrator",
            "--opencode-variant",
            "max",
            "--opencode-skip-permissions",
            "--opencode-preflight-report",
            "target/opencode-preflight/harness/opencode-preflight-report.json",
            "--no-execute-merge",
            "--no-auto-retry",
            "--max-workers",
            "4",
        ]

        with patch("sys.argv", argv), patch("sys.stdout", io.StringIO()) as stdout, patch.object(
            harness,
            "evaluate",
            return_value={"status": "completed", "exit_code": 0},
        ) as runner:
            self.assertEqual(harness.main(), 0)

        payload = json.loads(stdout.getvalue())
        self.assertEqual(payload["status"], "completed")
        runner.assert_called_once()
        kwargs = runner.call_args.kwargs
        self.assertEqual(kwargs["run_id"], "run-evaluate-cli")
        self.assertEqual(kwargs["target_id"], "flashdb")
        self.assertEqual(kwargs["source_repo_root"], Path("sources/FlashDB"))
        self.assertEqual(kwargs["source_repository"], "https://gitcode.com/xwxf/FlashDB.git")
        self.assertEqual(kwargs["source_branch"], "competition")
        self.assertEqual(kwargs["source_file"], "src/fdb_utils.c")
        self.assertEqual(kwargs["functions"], ["fdb_calc_crc32", "fdb_blob_make"])
        self.assertEqual(kwargs["source_commit"], "abc123")
        self.assertEqual(kwargs["require_source_commit"], "abc123")
        self.assertEqual(kwargs["slice_specs"], ["validation/slice-specs/flashdb-real-fdb-calc-crc32.json"])
        self.assertEqual(kwargs["compiler_command_source"], "compile_commands.json")
        self.assertEqual(kwargs["include_paths"], ["inc"])
        self.assertEqual(kwargs["defines"], ["FDB_USING_KVDB"])
        self.assertTrue(kwargs["reuse_accepted_evidence"])
        self.assertEqual(kwargs["accepted_evidence_root"], "validation/evidence")
        self.assertEqual(kwargs["out_root"], Path("target/competition-out-evaluate"))
        self.assertEqual(kwargs["slice_id_prefix"], "flashdb-fdb-utils")
        self.assertEqual(kwargs["worker_prefix"], "flashdb-worker")
        self.assertEqual(kwargs["limit"], 2)
        self.assertEqual(kwargs["proof_class"], "local-simulation")
        self.assertEqual(kwargs["mode"], "opencode")
        self.assertEqual(kwargs["opencode_command"], "opencode")
        self.assertEqual(kwargs["opencode_model"], "GLM-5.1")
        self.assertEqual(kwargs["opencode_agent"], "c2rust-migrator")
        self.assertEqual(kwargs["opencode_variant"], "max")
        self.assertTrue(kwargs["opencode_skip_permissions"])
        self.assertEqual(
            kwargs["opencode_preflight_report"],
            Path("target/opencode-preflight/harness/opencode-preflight-report.json"),
        )
        self.assertFalse(kwargs["execute_merge"])
        self.assertFalse(kwargs["auto_retry"])
        self.assertEqual(kwargs["max_workers"], 4)

    def test_evaluate_cli_profile_dispatches_full_batch_profile_path(self) -> None:
        argv = [
            "opencode_agent_harness.py",
            "evaluate",
            "--profile",
            "config/competition-env/planned-batches/flashdb-fdb-utils-before-after.json",
            "--run-id",
            "run-evaluate-profile",
            "--out-root",
            "target/competition-out-evaluate-profile",
        ]

        with patch("sys.argv", argv), patch("sys.stdout", io.StringIO()) as stdout, patch.object(
            harness,
            "run_batch_profile",
            return_value={"status": "completed", "exit_code": 0},
        ) as batch_runner, patch.object(
            harness,
            "write_evaluate_profile_report",
            return_value={"status": "completed", "exit_code": 0, "report_kind": "evaluate-report"},
        ) as evaluate_profile_report, patch.object(harness, "evaluate") as direct_evaluate:
            self.assertEqual(harness.main(), 0)

        payload = json.loads(stdout.getvalue())
        self.assertEqual(payload["status"], "completed")
        self.assertEqual(payload["report_kind"], "evaluate-report")
        batch_runner.assert_called_once()
        evaluate_profile_report.assert_called_once()
        direct_evaluate.assert_not_called()
        self.assertEqual(
            batch_runner.call_args.kwargs["profile_path"],
            Path("config/competition-env/planned-batches/flashdb-fdb-utils-before-after.json"),
        )
        self.assertEqual(batch_runner.call_args.kwargs["run_id"], "run-evaluate-profile")
        self.assertEqual(batch_runner.call_args.kwargs["out_root"], Path("target/competition-out-evaluate-profile"))
        self.assertIsNone(batch_runner.call_args.kwargs["proof_class_override"])
        self.assertEqual(evaluate_profile_report.call_args.kwargs["batch_result"], {"status": "completed", "exit_code": 0})
        self.assertEqual(
            evaluate_profile_report.call_args.kwargs["profile_path"],
            Path("config/competition-env/planned-batches/flashdb-fdb-utils-before-after.json"),
        )

    def test_evaluate_cli_profile_dispatches_proof_class_override(self) -> None:
        argv = [
            "opencode_agent_harness.py",
            "evaluate",
            "--profile",
            "config/competition-env/planned-batches/flashdb-fdb-utils-opencode-explicit-workers.json",
            "--run-id",
            "run-evaluate-profile-exact",
            "--out-root",
            "target/competition-out-evaluate-profile-exact",
            "--proof-class",
            "competition-exact",
        ]

        with patch("sys.argv", argv), patch("sys.stdout", io.StringIO()) as stdout, patch.object(
            harness,
            "run_batch_profile",
            return_value={"status": "blocked", "exit_code": 1},
        ) as batch_runner, patch.object(
            harness,
            "write_evaluate_profile_report",
            return_value={"status": "blocked", "exit_code": 1, "report_kind": "evaluate-report"},
        ) as evaluate_profile_report:
            self.assertEqual(harness.main(), 1)

        payload = json.loads(stdout.getvalue())
        self.assertEqual(payload["status"], "blocked")
        self.assertEqual(payload["report_kind"], "evaluate-report")
        self.assertEqual(batch_runner.call_args.kwargs["proof_class_override"], "competition-exact")
        self.assertEqual(
            batch_runner.call_args.kwargs["profile_path"],
            Path("config/competition-env/planned-batches/flashdb-fdb-utils-opencode-explicit-workers.json"),
        )
        evaluate_profile_report.assert_called_once()

    def test_run_batch_profile_cli_dispatches_proof_class_override(self) -> None:
        argv = [
            "opencode_agent_harness.py",
            "run-batch-profile",
            "--profile",
            "config/competition-env/planned-batches/flashdb-fdb-utils-opencode-explicit-workers.json",
            "--run-id",
            "run-batch-profile-exact",
            "--out-root",
            "target/competition-out-batch-profile-exact",
            "--proof-class",
            "competition-exact",
        ]

        with patch("sys.argv", argv), patch("sys.stdout", io.StringIO()) as stdout, patch.object(
            harness,
            "run_batch_profile",
            return_value={"status": "blocked", "exit_code": 1},
        ) as batch_runner:
            self.assertEqual(harness.main(), 1)

        payload = json.loads(stdout.getvalue())
        self.assertEqual(payload["status"], "blocked")
        self.assertEqual(batch_runner.call_args.kwargs["proof_class_override"], "competition-exact")
        self.assertEqual(batch_runner.call_args.kwargs["run_id"], "run-batch-profile-exact")
        self.assertEqual(batch_runner.call_args.kwargs["out_root"], Path("target/competition-out-batch-profile-exact"))

    def test_build_resume_manifest_records_worker_replay_commands(self) -> None:
        with temp_repo_dir() as tmp:
            out_root = Path(tmp) / "competition-out"
            db_path = out_root / "state" / "opencode-agent-harness.sqlite3"
            worker_root = out_root / "workers" / "worker-001"
            assignment = out_root / "harness" / "assignments" / "worker-001.json"
            request = out_root / "harness" / "assignments" / "worker-001-request.json"
            summary = worker_root / "summary" / "competition-run-summary.json"
            report = worker_root / "harness" / "run-worker-report.json"
            preflight = out_root / "harness" / "opencode-preflight-report.json"
            evaluate_report = out_root / "harness" / "evaluate-report.json"
            judge_index = out_root / "harness" / "judge-evidence-index.json"
            resume_manifest = out_root / "harness" / "resume-manifest.json"
            verified_baseline_ref = verified_unsafe_baseline_ref_for_tests()
            for path in [db_path, assignment, request, summary, report, preflight, evaluate_report, judge_index]:
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text("{}\n", encoding="utf-8")
            preflight.write_text(
                json.dumps(
                    {
                        "report_kind": "opencode-preflight",
                        "status": "passed",
                        "contract_verification": {"status": "executed"},
                    }
                )
                + "\n",
                encoding="utf-8",
            )

            runtime_env = harness.opencode_runtime_env_contract(
                base_root=out_root,
                scope="preflight",
                repo_root=REPO_ROOT,
            )
            worker_fields = {
                "worker_id": "worker-001",
                "slice_id": "demo-unit",
                "function": "demo_unit",
                "assignment_path": repo_rel(assignment),
                "request_path": repo_rel(request),
                "summary_path": repo_rel(summary),
                "report_path": repo_rel(report),
                "out_root": repo_rel(worker_root),
                "source_commit": "abc123",
                "source_sha256": "f" * 64,
                "summary_status": "failed",
                "opencode_preflight_report": {
                    "path": repo_rel(preflight),
                    "sha256": harness.sha256_file(preflight),
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
                },
            }
            manifest = harness.build_resume_manifest(
                db_path=db_path,
                run_id="run-resume",
                out_root=out_root,
                status="failed",
                context_pack={
                    "entrypoints": {},
                    "attempt_evidence_policy": {
                        "baseline_attempt": {
                            "verified_unsafe_baseline": verified_baseline_ref,
                        }
                    },
                    "workers": [worker_fields],
                },
                context_pack_ref={"path": "target/context-pack.json", "sha256": "a" * 64},
                agent_index={
                    "attempt_evidence_policy": {
                        "baseline_attempt": {
                            "verified_unsafe_baseline": verified_baseline_ref,
                        }
                    },
                    "agents_by_worker_id": {
                        "worker-001": {
                            **worker_fields,
                            "isolated_out_root": repo_rel(worker_root),
                        }
                    }
                },
                agent_index_ref={"path": "target/agent-index.json", "sha256": "b" * 64},
                evaluate_report_path=evaluate_report,
                batch_profile_report_path="target/batch-profile-report.json",
                judge_evidence_index_path=judge_index,
                resume_manifest_path=resume_manifest,
                repair_hints={
                    "source": "sqlite repair_hints",
                    "open_count": 1,
                    "hints": [
                        {
                            "hint_id": "repair:run-resume:worker-001:process_timeout",
                            "status": "open",
                            "worker_id": "worker-001",
                        }
                    ],
                },
                repo_root=REPO_ROOT,
            )

            self.assertEqual(
                manifest["attempt_evidence_policy"]["baseline_attempt"]["verified_unsafe_baseline"],
                verified_baseline_ref,
            )
            self.assertEqual(manifest["verified_unsafe_baseline"], verified_baseline_ref)
            self.assertEqual(manifest["entrypoints"]["verified_unsafe_baseline"], verified_baseline_ref["path"])
            self.assertEqual(manifest["worker_ids"], ["worker-001"])
            worker = manifest["workers"][0]
            replay = worker["replay_commands"]
            run_worker = replay["run_worker"]
            self.assertEqual(
                run_worker["argv"][:5],
                ["python3", "-B", "-m", "validation.tools.opencode_agent_harness", "run-worker"],
            )
            self.assertEqual(run_worker["argv"][run_worker["argv"].index("--db") + 1], repo_rel(db_path))
            self.assertEqual(run_worker["argv"][run_worker["argv"].index("--run-id") + 1], "run-resume")
            self.assertEqual(run_worker["argv"][run_worker["argv"].index("--worker-id") + 1], "worker-001")
            self.assertEqual(run_worker["argv"][run_worker["argv"].index("--mode") + 1], "opencode")
            self.assertEqual(run_worker["argv"][run_worker["argv"].index("--opencode-model") + 1], "GLM-5.1")
            self.assertEqual(
                run_worker["argv"][run_worker["argv"].index("--opencode-agent") + 1],
                "c2rust-migrator",
            )
            self.assertIn("--opencode-skip-permissions", run_worker["argv"])
            self.assertEqual(
                run_worker["argv"][run_worker["argv"].index("--opencode-preflight-report") + 1],
                repo_rel(preflight),
            )
            self.assertEqual(run_worker["replay_safety"]["status"], "ready")
            self.assertEqual(run_worker["replay_safety"]["reason"], "opencode_preflight_contract_bound")
            self.assertEqual(run_worker["replay_safety"]["preflight_report"], repo_rel(preflight))
            self.assertEqual(run_worker["replay_safety"]["opencode_runtime_env_sha256"], runtime_env["env_sha256"])
            self.assertEqual(run_worker["assignment_path"], repo_rel(assignment))
            self.assertEqual(run_worker["request_path"], repo_rel(request))
            self.assertEqual(run_worker["summary_path"], repo_rel(summary))
            self.assertEqual(run_worker["out_root"], repo_rel(worker_root))
            self.assertEqual(run_worker["command"], shlex.join(run_worker["argv"]))

            retry_worker = replay["retry_worker"]
            self.assertEqual(
                retry_worker["argv"][:5],
                ["python3", "-B", "-m", "validation.tools.opencode_agent_harness", "retry-worker"],
            )
            self.assertEqual(
                retry_worker["argv"][retry_worker["argv"].index("--hint-id") + 1],
                "repair:run-resume:worker-001:process_timeout",
            )
            self.assertEqual(
                retry_worker["argv"][retry_worker["argv"].index("--opencode-agent") + 1],
                "c2rust-migrator",
            )
            self.assertEqual(retry_worker["command"], shlex.join(retry_worker["argv"]))

    def test_build_resume_manifest_records_stable_worker_ids_for_multi_worker_resume(self) -> None:
        with temp_repo_dir() as tmp:
            out_root = Path(tmp) / "competition-out"
            db_path = out_root / "state" / "opencode-agent-harness.sqlite3"
            evaluate_report = out_root / "harness" / "evaluate-report.json"
            judge_index = out_root / "harness" / "judge-evidence-index.json"
            resume_manifest = out_root / "harness" / "resume-manifest.json"
            verified_baseline_ref = verified_unsafe_baseline_ref_for_tests()

            workers = []
            agents = []
            agents_by_worker_id = {}
            for index, worker_id in enumerate(["worker-a", "worker-b"], start=1):
                worker_root = out_root / "workers" / worker_id
                assignment = out_root / "harness" / "assignments" / f"{worker_id}.json"
                request = out_root / "harness" / "assignments" / f"{worker_id}-request.json"
                summary = worker_root / "summary" / "competition-run-summary.json"
                report = worker_root / "harness" / "run-worker-report.json"
                worker = {
                    "worker_id": worker_id,
                    "slice_id": f"demo-unit-{index}",
                    "function": f"demo_unit_{index}",
                    "assignment_path": repo_rel(assignment),
                    "request_path": repo_rel(request),
                    "summary_path": repo_rel(summary),
                    "report_path": repo_rel(report),
                    "out_root": repo_rel(worker_root),
                    "source_commit": f"abc12{index}",
                    "source_sha256": str(index) * 64,
                    "summary_status": "failed",
                }
                workers.append(worker)
                agent = {**worker, "isolated_out_root": repo_rel(worker_root), "mode": "deterministic"}
                agents.append(agent)
                agents_by_worker_id[worker_id] = agent

            manifest = harness.build_resume_manifest(
                db_path=db_path,
                run_id="run-resume-two-workers",
                out_root=out_root,
                status="failed",
                context_pack={
                    "mode": "deterministic",
                    "entrypoints": {},
                    "attempt_evidence_policy": {
                        "baseline_attempt": {
                            "verified_unsafe_baseline": verified_baseline_ref,
                        }
                    },
                    "workers": workers,
                },
                context_pack_ref={"path": "target/context-pack.json", "sha256": "a" * 64},
                agent_index={
                    "mode": "deterministic",
                    "attempt_evidence_policy": {
                        "baseline_attempt": {
                            "verified_unsafe_baseline": verified_baseline_ref,
                        }
                    },
                    "agents": agents,
                    "agents_by_worker_id": agents_by_worker_id,
                },
                agent_index_ref={"path": "target/agent-index.json", "sha256": "b" * 64},
                evaluate_report_path=evaluate_report,
                batch_profile_report_path="target/batch-profile-report.json",
                judge_evidence_index_path=judge_index,
                resume_manifest_path=resume_manifest,
                repair_hints={"source": "sqlite repair_hints", "open_count": 0, "hints": []},
                repo_root=REPO_ROOT,
            )

            self.assertEqual(manifest["worker_count"], 2)
            self.assertEqual(manifest["worker_ids"], ["worker-a", "worker-b"])
            self.assertEqual([worker["worker_id"] for worker in manifest["workers"]], manifest["worker_ids"])
            for worker in manifest["workers"]:
                run_worker = worker["replay_commands"]["run_worker"]
                flags = {
                    argument: run_worker["argv"][index + 1]
                    for index, argument in enumerate(run_worker["argv"][:-1])
                    if argument.startswith("--") and not run_worker["argv"][index + 1].startswith("--")
                }
                self.assertEqual(flags["--worker-id"], worker["worker_id"])
                self.assertEqual(run_worker["replay_safety"]["status"], "ready")

    def test_resume_manifest_blocks_opencode_replay_when_preflight_model_is_missing(self) -> None:
        with temp_repo_dir() as tmp:
            out_root = Path(tmp) / "competition-out"
            preflight = out_root / "harness" / "opencode-preflight-report.json"
            runtime_env = harness.opencode_runtime_env_contract(
                base_root=out_root,
                scope="preflight",
                repo_root=REPO_ROOT,
            )
            worker = {
                "worker_id": "worker-001",
                "opencode_preflight_report": {
                    "path": repo_rel(preflight),
                    "launch_policy": {
                        "opencode_command": "opencode",
                        "opencode_model": None,
                        "opencode_agent": "default",
                        "opencode_variant": "max",
                        "opencode_skip_permissions": True,
                    },
                    "opencode_runtime_env": runtime_env,
                },
            }

            replay = harness.resume_worker_replay_command(
                "run-worker",
                worker=worker,
                db_path=out_root / "state" / "opencode-agent-harness.sqlite3",
                run_id="run-resume",
                mode="opencode",
                repo_root=REPO_ROOT,
            )

            self.assertEqual(replay["argv"][replay["argv"].index("--opencode-model") + 1], "GLM-5.1")
            self.assertEqual(replay["replay_safety"]["status"], "blocked")
            self.assertEqual(replay["replay_safety"]["reason"], "opencode_preflight_required_for_replay")
            self.assertIn(
                "opencode_preflight_report.launch_policy.opencode_model",
                replay["replay_safety"]["missing_constraints"],
            )

    def test_resume_manifest_blocks_opencode_replay_when_preflight_binding_is_not_passed(self) -> None:
        with temp_repo_dir() as tmp:
            out_root = Path(tmp) / "competition-out"
            preflight = out_root / "harness" / "opencode-preflight-report.json"
            runtime_env = harness.opencode_runtime_env_contract(
                base_root=out_root,
                scope="preflight",
                repo_root=REPO_ROOT,
            )
            base_preflight = {
                "path": repo_rel(preflight),
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
            cases = [
                ("failed-status", {"status": "failed"}, "opencode_preflight_report.status"),
                ("not-executed-contract", {"contract_status": "not-executed"}, "opencode_preflight_report.contract_status"),
                ("missing-sha", {"sha256": None}, "opencode_preflight_report.sha256"),
            ]
            for _name, patch_payload, missing_constraint in cases:
                preflight_payload = json.loads(json.dumps(base_preflight))
                for key, value in patch_payload.items():
                    if value is None:
                        preflight_payload.pop(key, None)
                    else:
                        preflight_payload[key] = value
                worker = {
                    "worker_id": "worker-001",
                    "opencode_preflight_report": preflight_payload,
                }

                replay = harness.resume_worker_replay_command(
                    "run-worker",
                    worker=worker,
                    db_path=out_root / "state" / "opencode-agent-harness.sqlite3",
                    run_id="run-resume",
                    mode="opencode",
                    repo_root=REPO_ROOT,
                )

                self.assertEqual(replay["replay_safety"]["status"], "blocked")
                self.assertEqual(replay["replay_safety"]["reason"], "opencode_preflight_required_for_replay")
                self.assertIn(missing_constraint, replay["replay_safety"]["missing_constraints"])

    def test_resume_manifest_blocks_opencode_replay_when_preflight_sha_mismatches_file(self) -> None:
        with temp_repo_dir() as tmp:
            out_root = Path(tmp) / "competition-out"
            preflight = out_root / "harness" / "opencode-preflight-report.json"
            preflight.parent.mkdir(parents=True, exist_ok=True)
            preflight.write_text('{"report_kind":"opencode-preflight"}\n', encoding="utf-8")
            runtime_env = harness.opencode_runtime_env_contract(
                base_root=out_root,
                scope="preflight",
                repo_root=REPO_ROOT,
            )
            worker = {
                "worker_id": "worker-001",
                "opencode_preflight_report": {
                    "path": repo_rel(preflight),
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
                },
            }

            replay = harness.resume_worker_replay_command(
                "run-worker",
                worker=worker,
                db_path=out_root / "state" / "opencode-agent-harness.sqlite3",
                run_id="run-resume",
                mode="opencode",
                repo_root=REPO_ROOT,
            )

            self.assertEqual(replay["replay_safety"]["status"], "blocked")
            self.assertEqual(replay["replay_safety"]["reason"], "opencode_preflight_required_for_replay")
            self.assertIn(
                "opencode_preflight_report.sha256_mismatch",
                replay["replay_safety"]["missing_constraints"],
            )

    def test_resume_manifest_blocks_opencode_replay_when_preflight_file_status_drifts(self) -> None:
        with temp_repo_dir() as tmp:
            out_root = Path(tmp) / "competition-out"
            preflight = out_root / "harness" / "opencode-preflight-report.json"
            preflight.parent.mkdir(parents=True, exist_ok=True)
            preflight.write_text(
                json.dumps(
                    {
                        "report_kind": "opencode-preflight",
                        "status": "failed",
                        "contract_verification": {"status": "not-observed"},
                    }
                )
                + "\n",
                encoding="utf-8",
            )
            runtime_env = harness.opencode_runtime_env_contract(
                base_root=out_root,
                scope="preflight",
                repo_root=REPO_ROOT,
            )
            worker = {
                "worker_id": "worker-001",
                "opencode_preflight_report": {
                    "path": repo_rel(preflight),
                    "sha256": harness.sha256_file(preflight),
                    "status": "passed",
                    "contract_status": "executed",
                    "launch_policy": {
                        "opencode_command": "opencode",
                        "opencode_model": "GLM-5.1",
                        "opencode_agent": "c2rust-migrator",
                        "opencode_variant": "max",
                        "opencode_skip_permissions": False,
                    },
                    "opencode_runtime_env": runtime_env,
                    "opencode_model_availability": {
                        "status": "available",
                        "opencode_command": "opencode",
                        "required_model": "GLM-5.1",
                        "process_returncode": 0,
                        "model_listed": True,
                    },
                },
            }

            replay = harness.resume_worker_replay_command(
                "run-worker",
                worker=worker,
                db_path=out_root / "state" / "opencode-agent-harness.sqlite3",
                run_id="run-resume",
                mode="opencode",
                repo_root=REPO_ROOT,
            )

            self.assertEqual(replay["replay_safety"]["status"], "blocked")
            self.assertEqual(replay["replay_safety"]["reason"], "opencode_preflight_required_for_replay")
            self.assertIn(
                "opencode_preflight_report.file_status",
                replay["replay_safety"]["missing_constraints"],
            )

    def test_resume_manifest_blocks_opencode_replay_when_preflight_command_is_not_opencode(self) -> None:
        with temp_repo_dir() as tmp:
            out_root = Path(tmp) / "competition-out"
            preflight = out_root / "harness" / "opencode-preflight-report.json"
            runtime_env = harness.opencode_runtime_env_contract(
                base_root=out_root,
                scope="preflight",
                repo_root=REPO_ROOT,
            )
            worker = {
                "worker_id": "worker-001",
                "opencode_preflight_report": {
                    "path": repo_rel(preflight),
                    "launch_policy": {
                        "opencode_command": "codex",
                        "opencode_model": "GLM-5.1",
                        "opencode_agent": "c2rust-migrator",
                        "opencode_variant": "max",
                        "opencode_skip_permissions": True,
                    },
                    "opencode_runtime_env": runtime_env,
                    "opencode_model_availability": {
                        "status": "available",
                        "opencode_command": "codex",
                        "required_model": "GLM-5.1",
                        "process_returncode": 0,
                        "model_listed": True,
                    },
                },
            }

            replay = harness.resume_worker_replay_command(
                "run-worker",
                worker=worker,
                db_path=out_root / "state" / "opencode-agent-harness.sqlite3",
                run_id="run-resume",
                mode="opencode",
                repo_root=REPO_ROOT,
            )

            self.assertEqual(replay["argv"][replay["argv"].index("--opencode-command") + 1], "codex")
            self.assertEqual(replay["replay_safety"]["status"], "blocked")
            self.assertEqual(replay["replay_safety"]["reason"], "opencode_preflight_required_for_replay")
            self.assertIn(
                "opencode_preflight_report.launch_policy.opencode_command",
                replay["replay_safety"]["missing_constraints"],
            )

    def test_resume_manifest_blocks_opencode_replay_when_preflight_agent_is_not_repo_owned(self) -> None:
        with temp_repo_dir() as tmp:
            out_root = Path(tmp) / "competition-out"
            preflight = out_root / "harness" / "opencode-preflight-report.json"
            runtime_env = harness.opencode_runtime_env_contract(
                base_root=out_root,
                scope="preflight",
                repo_root=REPO_ROOT,
            )
            worker = {
                "worker_id": "worker-001",
                "opencode_preflight_report": {
                    "path": repo_rel(preflight),
                    "sha256": "a" * 64,
                    "status": "passed",
                    "contract_status": "executed",
                    "launch_policy": {
                        "opencode_command": "opencode",
                        "opencode_model": "GLM-5.1",
                        "opencode_agent": "default",
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
                },
            }

            replay = harness.resume_worker_replay_command(
                "run-worker",
                worker=worker,
                db_path=out_root / "state" / "opencode-agent-harness.sqlite3",
                run_id="run-resume",
                mode="opencode",
                repo_root=REPO_ROOT,
            )

            self.assertEqual(replay["replay_safety"]["status"], "blocked")
            self.assertEqual(replay["replay_safety"]["reason"], "opencode_preflight_required_for_replay")
            self.assertIn(
                "opencode_preflight_report.launch_policy.opencode_agent",
                replay["replay_safety"]["missing_constraints"],
            )

    def test_resume_manifest_blocks_opencode_replay_when_preflight_variant_is_not_competition_max(self) -> None:
        with temp_repo_dir() as tmp:
            out_root = Path(tmp) / "competition-out"
            preflight = out_root / "harness" / "opencode-preflight-report.json"
            runtime_env = harness.opencode_runtime_env_contract(
                base_root=out_root,
                scope="preflight",
                repo_root=REPO_ROOT,
            )
            worker = {
                "worker_id": "worker-001",
                "opencode_preflight_report": {
                    "path": repo_rel(preflight),
                    "launch_policy": {
                        "opencode_command": "opencode",
                        "opencode_model": "GLM-5.1",
                        "opencode_agent": "c2rust-migrator",
                        "opencode_variant": "lite",
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
                },
            }

            replay = harness.resume_worker_replay_command(
                "run-worker",
                worker=worker,
                db_path=out_root / "state" / "opencode-agent-harness.sqlite3",
                run_id="run-resume",
                mode="opencode",
                repo_root=REPO_ROOT,
            )

            self.assertEqual(replay["argv"][replay["argv"].index("--opencode-variant") + 1], "lite")
            self.assertEqual(replay["replay_safety"]["status"], "blocked")
            self.assertEqual(replay["replay_safety"]["reason"], "opencode_preflight_required_for_replay")
            self.assertIn(
                "opencode_preflight_report.launch_policy.opencode_variant",
                replay["replay_safety"]["missing_constraints"],
            )

    def test_resume_manifest_blocks_opencode_replay_when_model_availability_is_missing(self) -> None:
        with temp_repo_dir() as tmp:
            out_root = Path(tmp) / "competition-out"
            preflight = out_root / "harness" / "opencode-preflight-report.json"
            runtime_env = harness.opencode_runtime_env_contract(
                base_root=out_root,
                scope="preflight",
                repo_root=REPO_ROOT,
            )
            worker = {
                "worker_id": "worker-001",
                "opencode_preflight_report": {
                    "path": repo_rel(preflight),
                    "launch_policy": {
                        "opencode_command": "opencode",
                        "opencode_model": "GLM-5.1",
                        "opencode_agent": "c2rust-migrator",
                        "opencode_variant": "max",
                        "opencode_skip_permissions": True,
                    },
                    "opencode_runtime_env": runtime_env,
                },
            }

            replay = harness.resume_worker_replay_command(
                "run-worker",
                worker=worker,
                db_path=out_root / "state" / "opencode-agent-harness.sqlite3",
                run_id="run-resume",
                mode="opencode",
                repo_root=REPO_ROOT,
            )

            self.assertIn("--opencode-model", replay["argv"])
            self.assertEqual(replay["replay_safety"]["status"], "blocked")
            self.assertEqual(replay["replay_safety"]["reason"], "opencode_preflight_required_for_replay")
            self.assertIn(
                "opencode_preflight_report.opencode_model_availability",
                replay["replay_safety"]["missing_constraints"],
            )

    def test_resume_manifest_marks_opencode_replay_blocked_without_preflight_contract(self) -> None:
        with temp_repo_dir() as tmp:
            out_root = Path(tmp) / "competition-out"
            db_path = out_root / "state" / "opencode-agent-harness.sqlite3"
            worker_root = out_root / "workers" / "worker-001"
            assignment = out_root / "harness" / "assignments" / "worker-001.json"
            request = out_root / "harness" / "assignments" / "worker-001-request.json"
            summary = worker_root / "summary" / "competition-run-summary.json"
            report = worker_root / "harness" / "run-worker-report.json"
            evaluate_report = out_root / "harness" / "evaluate-report.json"
            judge_index = out_root / "harness" / "judge-evidence-index.json"
            resume_manifest = out_root / "harness" / "resume-manifest.json"
            for path in [db_path, assignment, request, summary, report, evaluate_report, judge_index]:
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text("{}\n", encoding="utf-8")

            worker_fields = {
                "worker_id": "worker-001",
                "slice_id": "demo-unit",
                "function": "demo_unit",
                "assignment_path": repo_rel(assignment),
                "request_path": repo_rel(request),
                "summary_path": repo_rel(summary),
                "report_path": repo_rel(report),
                "out_root": repo_rel(worker_root),
                "source_commit": "abc123",
                "source_sha256": "f" * 64,
                "summary_status": "failed",
                "runtime": "opencode",
            }
            manifest = harness.build_resume_manifest(
                db_path=db_path,
                run_id="run-resume",
                out_root=out_root,
                status="failed",
                context_pack={"entrypoints": {}, "mode": "opencode", "workers": [worker_fields]},
                context_pack_ref={"path": "target/context-pack.json", "sha256": "a" * 64},
                agent_index={
                    "agents_by_worker_id": {
                        "worker-001": {
                            **worker_fields,
                            "isolated_out_root": repo_rel(worker_root),
                        }
                    }
                },
                agent_index_ref={"path": "target/agent-index.json", "sha256": "b" * 64},
                evaluate_report_path=evaluate_report,
                batch_profile_report_path="target/batch-profile-report.json",
                judge_evidence_index_path=judge_index,
                resume_manifest_path=resume_manifest,
                repair_hints={
                    "source": "sqlite repair_hints",
                    "open_count": 1,
                    "hints": [
                        {
                            "hint_id": "repair:run-resume:worker-001:process_timeout",
                            "status": "open",
                            "worker_id": "worker-001",
                        }
                    ],
                },
                repo_root=REPO_ROOT,
            )

            replay = manifest["workers"][0]["replay_commands"]
            for command in [replay["run_worker"], replay["retry_worker"]]:
                self.assertEqual(command["argv"][command["argv"].index("--mode") + 1], "opencode")
                self.assertEqual(command["replay_safety"]["status"], "blocked")
                self.assertEqual(command["replay_safety"]["reason"], "opencode_preflight_required_for_replay")
                self.assertIn("opencode_preflight_report", command["replay_safety"]["missing_constraints"])
