class _JudgeEntrypointsValidatorTestsPart07:
    def test_source_file_worker_plan_infers_planning_mode(self) -> None:
        worker_plan_path = "target/out/harness/plans/source-workers.json"
        common_worker = {
            "assignment_path": "target/out/harness/assignments/worker-001.json",
            "function": "demo_unit",
            "request_path": "target/out/harness/assignments/worker-001-request.json",
            "slice_id": "demo-unit",
            "source_commit": "abc123",
            "source_file": "src/demo.c",
            "source_repo_root": "sources/Demo",
            "source_sha256": "f" * 64,
            "worker_id": "worker-001",
        }
        result = validator.validate_worker_plan_contract(
            {
                "schema_version": 1,
                "status": "planned",
                "target_id": "demo",
                "run_id": "source-plan",
                "plan_path": worker_plan_path,
                "source_file": "src/demo.c",
                "units": [
                    {
                        **common_worker,
                        "out_root": "target/out/workers/worker-001",
                        "slice_spec": "validation/slice-specs/demo.json",
                    }
                ],
            },
            {
                "entrypoints": {"worker_plan": worker_plan_path},
                "workers": [common_worker],
            },
            {
                "agents": [common_worker],
                "agents_by_worker_id": {
                    "worker-001": {
                        **common_worker,
                        "isolated_out_root": "target/out/workers/worker-001",
                    }
                },
                "planner": {
                    "plan_path": worker_plan_path,
                    "worker_count": 1,
                },
            },
            path_text=worker_plan_path,
        )

        self.assertEqual(result["status"], "passed")
        self.assertEqual(result["planning_mode"], "source_file")
        self.assertEqual(result["worker_count"], 1)

    def test_multi_worker_entrypoint_worker_plan_must_match_profile_workers(self) -> None:
        temp_config = write_temp_config(load_default_config())
        temp_dir = temp_config.parent
        out_root = temp_dir / "out"
        context_pack = out_root / "harness" / "context-pack.json"
        agent_index = out_root / "harness" / "agent-index.json"
        worker_plan = out_root / "harness" / "plans" / "workers.json"
        ledger = out_root / "state" / "opencode-agent-harness.sqlite3"
        profile_path = temp_dir / "profile.json"
        artifact_workers = []
        for worker_id in ("artifact-worker-001", "artifact-worker-002"):
            worker_root = out_root / "workers" / worker_id
            assignment = out_root / "harness" / "assignments" / f"{worker_id}.json"
            request = out_root / "harness" / "assignments" / f"{worker_id}-request.json"
            summary = worker_root / "summary" / "competition-run-summary.json"
            report = worker_root / "harness" / "run-worker-report.json"
            for path in (assignment, request, summary, report):
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text("{}\n", encoding="utf-8")
            artifact_workers.append(
                {
                    "assignment_path": repo_relative(assignment),
                    "function": "demo_unit",
                    "out_root": repo_relative(worker_root),
                    "report_path": repo_relative(report),
                    "require_source_commit": "abc123",
                    "request_path": repo_relative(request),
                    "slice_id": f"demo/{worker_id}",
                    "slice_spec": "validation/slice-specs/demo.json",
                    "source_commit": "abc123",
                    "source_file": "src/demo.c",
                    "source_repo_root": "sources/Demo",
                    "source_sha256": "f" * 64,
                    "summary_path": repo_relative(summary),
                    "target_id": "demo",
                    "worker_id": worker_id,
                }
            )
        write_json(
            profile_path,
            {
                "profile_id": "drifted-profile-workers",
                "max_workers": 2,
                "workers": [
                    {"worker_id": "profile-worker-001"},
                    {"worker_id": "profile-worker-002"},
                ],
            },
        )
        write_json(
            context_pack,
            {
                "report_kind": "context-pack",
                "context_management_contract": {
                    "agent_index": repo_relative(agent_index),
                    "chat_output_is_evidence": False,
                    "context_pack": repo_relative(context_pack),
                    "contract_kind": "context-management",
                    "evidence_policy": "on-disk-artifacts-only",
                    "pipeline": [
                        {"stage": "plan", "role": "planner", "evidence": "entrypoints.worker_plan"},
                        {"stage": "translate", "role": "worker", "fanout": True},
                        {"stage": "verify", "role": "verifier", "reduce": "merge"},
                        {"stage": "repair", "role": "repairer", "max_rounds": 5},
                    ],
                    "resume_protocol": {
                        "checkpoint_backend": "sqlite",
                        "ledger_path": repo_relative(ledger),
                        "worker_state_source": "agent-index.agents_by_worker_id",
                    },
                    "schema_version": 1,
                    "semantic_gate": False,
                },
                "entrypoints": {"worker_plan": repo_relative(worker_plan)},
                "workers": artifact_workers,
            },
        )
        write_json(
            agent_index,
            {
                "report_kind": "agent-index",
                "agent_coordination_contract": {
                    "chat_output_is_evidence": False,
                    "checkpoint_backend": "sqlite",
                    "contract_kind": "agent-coordination",
                    "roles": {
                        "planner": {},
                        "worker": {"isolation": "per-worker out_root"},
                        "repairer": {"round_cap": 5},
                        "verifier": {},
                        "reporter": {},
                    },
                    "schema_version": 1,
                    "semantic_gate": False,
                    "worker_count": 2,
                },
                "agents": artifact_workers,
                "agents_by_worker_id": {
                    worker["worker_id"]: {**worker, "isolated_out_root": worker["out_root"]}
                    for worker in artifact_workers
                },
                "planner": {
                    "plan_path": repo_relative(worker_plan),
                    "worker_count": 2,
                },
            },
        )
        write_json(
            worker_plan,
            {
                "schema_version": 1,
                "planning_mode": "explicit_workers",
                "status": "planned",
                "target_id": "demo",
                "run_id": "profile-worker-drift",
                "plan_path": repo_relative(worker_plan),
                "units": artifact_workers,
            },
        )
        write_minimal_context_ledger(
            ledger,
            run_id="profile-worker-drift",
            context_pack_path=context_pack,
            context_pack_payload=json.loads(context_pack.read_text(encoding="utf-8")),
            agent_index_path=agent_index,
        )

        with self.assertRaisesRegex(ValueError, "worker_plan.units worker ids must match entrypoint profile workers"):
            validator.validate_harness_artifact_contracts(
                {
                    "context_pack": repo_relative(context_pack),
                    "agent_index": repo_relative(agent_index),
                    "worker_plan": repo_relative(worker_plan),
                },
                require_local_artifacts=True,
                repo_root=REPO_ROOT,
                entrypoint={
                    "id": "multi_worker_evaluate_profile",
                    "purpose": "harness-architecture-multi-worker-evaluate",
                    "profile": {
                        "path": repo_relative(profile_path),
                        "sha256": validator.sha256_file(profile_path),
                    },
                },
            )

        write_json(
            profile_path,
            {
                "profile_id": "stale-profile-worker-tuples",
                "max_workers": 2,
                "workers": [
                    {
                        "worker_id": artifact_workers[0]["worker_id"],
                        "target_id": "demo",
                        "source_repo_root": "sources/Demo",
                        "source_file": "src/demo.c",
                        "function": "demo_unit",
                        "slice_id": "demo/stale-slice",
                        "source_commit": "def456",
                        "require_source_commit": "def456",
                        "slice_spec": "validation/slice-specs/stale-demo.json",
                    },
                    {
                        "worker_id": artifact_workers[1]["worker_id"],
                        "target_id": "demo",
                        "source_repo_root": "sources/Demo",
                        "source_file": "src/demo.c",
                        "function": "demo_unit",
                        "slice_id": artifact_workers[1]["slice_id"],
                        "source_commit": "abc123",
                        "require_source_commit": "abc123",
                    },
                ],
            },
        )
        with self.assertRaisesRegex(ValueError, "worker_plan.units worker tuple must match entrypoint profile workers"):
            validator.validate_harness_artifact_contracts(
                {
                    "context_pack": repo_relative(context_pack),
                    "agent_index": repo_relative(agent_index),
                    "worker_plan": repo_relative(worker_plan),
                },
                require_local_artifacts=True,
                repo_root=REPO_ROOT,
                entrypoint={
                    "id": "multi_worker_evaluate_profile",
                    "purpose": "harness-architecture-multi-worker-evaluate",
                    "profile": {
                        "path": repo_relative(profile_path),
                        "sha256": validator.sha256_file(profile_path),
                    },
                },
            )

    def test_context_pack_ledger_path_must_exist(self) -> None:
        temp_config = write_temp_config(load_default_config())
        temp_dir = temp_config.parent
        context_pack = temp_dir / "out" / "harness" / "context-pack.json"
        agent_index = temp_dir / "out" / "harness" / "agent-index.json"
        missing_ledger = temp_dir / "out" / "state" / "missing.sqlite3"
        write_json(
            context_pack,
            {
                "context_management_contract": {
                    "resume_protocol": {
                        "checkpoint_backend": "sqlite",
                        "ledger_path": repo_relative(missing_ledger),
                    },
                }
            },
        )
        write_json(agent_index, {"report_kind": "agent-index"})

        with self.assertRaisesRegex(ValueError, "ledger_path does not exist"):
            validator.validate_context_ledger_contract(
                json.loads(context_pack.read_text(encoding="utf-8")),
                {},
                context_path_text=repo_relative(context_pack),
                agent_path_text=repo_relative(agent_index),
                repo_root=REPO_ROOT,
            )

    def test_context_ledger_worker_summary_hash_drift_fails(self) -> None:
        temp_config = write_temp_config(load_default_config())
        temp_dir = temp_config.parent
        context_pack = temp_dir / "out" / "harness" / "context-pack.json"
        agent_index = temp_dir / "out" / "harness" / "agent-index.json"
        ledger = temp_dir / "out" / "state" / "opencode-agent-harness.sqlite3"
        summary = temp_dir / "out" / "workers" / "worker-001" / "summary" / "competition-run-summary.json"
        summary.parent.mkdir(parents=True, exist_ok=True)
        summary.write_text('{"status":"passed"}\n', encoding="utf-8")
        context_payload = {
            "context_management_contract": {
                "resume_protocol": {
                    "checkpoint_backend": "sqlite",
                    "ledger_path": repo_relative(ledger),
                },
            },
            "workers": [
                {
                    "worker_id": "worker-001",
                    "summary_path": repo_relative(summary),
                }
            ],
        }
        agent_payload = {
            "agents_by_worker_id": {
                "worker-001": {
                    "worker_id": "worker-001",
                    "summary_path": repo_relative(summary),
                }
            }
        }
        write_json(context_pack, context_payload)
        write_json(agent_index, agent_payload)
        write_minimal_context_ledger(
            ledger,
            run_id="competition-flashdb-before-after-exhibit",
            context_pack_path=context_pack,
            context_pack_payload=context_payload,
            agent_index_path=agent_index,
        )
        summary.write_text('{"status":"tampered"}\n', encoding="utf-8")

        with self.assertRaisesRegex(ValueError, "worker summary sha256 must match"):
            validator.validate_context_ledger_contract(
                context_payload,
                agent_payload,
                context_path_text=repo_relative(context_pack),
                agent_path_text=repo_relative(agent_index),
                repo_root=REPO_ROOT,
            )

    def test_context_ledger_missing_worker_report_artifact_fails(self) -> None:
        temp_config = write_temp_config(load_default_config())
        temp_dir = temp_config.parent
        context_pack = temp_dir / "out" / "harness" / "context-pack.json"
        agent_index = temp_dir / "out" / "harness" / "agent-index.json"
        ledger = temp_dir / "out" / "state" / "opencode-agent-harness.sqlite3"
        summary = temp_dir / "out" / "workers" / "worker-001" / "summary" / "competition-run-summary.json"
        report = temp_dir / "out" / "workers" / "worker-001" / "harness" / "run-worker-report.json"
        write_json(summary, {"status": "passed"})
        write_json(report, {"report_kind": "run-worker-report", "worker_id": "worker-001"})
        worker = {
            "worker_id": "worker-001",
            "summary_path": repo_relative(summary),
            "report_path": repo_relative(report),
        }
        context_payload = {
            "context_management_contract": {
                "resume_protocol": {
                    "checkpoint_backend": "sqlite",
                    "ledger_path": repo_relative(ledger),
                },
            },
            "workers": [worker],
        }
        agent_payload = {"agents_by_worker_id": {"worker-001": worker}}
        write_json(context_pack, context_payload)
        write_json(agent_index, agent_payload)
        write_minimal_context_ledger(
            ledger,
            run_id="competition-flashdb-before-after-exhibit",
            context_pack_path=context_pack,
            context_pack_payload=context_payload,
            agent_index_path=agent_index,
        )
        with closing(sqlite3.connect(ledger)) as connection:
            connection.execute("delete from artifacts where kind='run-worker-report'")
            connection.commit()

        with self.assertRaisesRegex(ValueError, "missing artifacts row for worker report") as captured:
            validator.validate_context_ledger_contract(
                context_payload,
                agent_payload,
                context_path_text=repo_relative(context_pack),
                agent_path_text=repo_relative(agent_index),
                repo_root=REPO_ROOT,
            )
        message = str(captured.exception)
        self.assertIn("worker_id=worker-001", message)
        self.assertIn(f"repo_rel_path={repo_relative(report)}", message)
        self.assertIn(f"ledger_path={repo_relative(ledger)}", message)
        self.assertIn("expected kind=run-worker-report", message)
        self.assertIn("regenerate OpenCode artifacts", message)

    def test_context_ledger_opencode_safety_attempt_requires_artifact_row(self) -> None:
        target_dir = REPO_ROOT / "target"
        target_dir.mkdir(exist_ok=True)
        temp_dir = Path(tempfile.mkdtemp(prefix="ledger-safety-attempt-row-", dir=target_dir))
        case = write_context_ledger_case(temp_dir)
        worker = case["agent_payload"]["agents_by_worker_id"]["worker-001"]
        report_path = REPO_ROOT / worker["report_path"]
        attempt_path = temp_dir / "out" / "workers" / "worker-001" / "harness" / "opencode-safety-transform-attempt.json"
        write_json(
            attempt_path,
            {
                "report_kind": "opencode-safety-transform-attempt",
                "run_id": case["context_payload"]["run_id"],
                "worker_id": "worker-001",
            },
        )
        attempt_ref = {
            "path": repo_relative(attempt_path),
            "sha256": validator.sha256_file(attempt_path),
        }
        worker["opencode_safety_transform_attempt"] = json.loads(json.dumps(attempt_ref))
        write_json(case["agent_index"], case["agent_payload"])
        report_payload = json.loads(report_path.read_text(encoding="utf-8"))
        report_payload["opencode_safety_transform_attempt"] = json.loads(json.dumps(attempt_ref))
        write_json(report_path, report_payload)
        with closing(sqlite3.connect(case["ledger"])) as connection:
            connection.execute(
                "update artifacts set sha256=?, payload_json=? where kind='agent-index'",
                (
                    validator.sha256_file(case["agent_index"]),
                    json.dumps(case["agent_payload"], sort_keys=True),
                ),
            )
            connection.execute(
                "update artifacts set sha256=?, payload_json=? where kind='run-worker-report'",
                (
                    validator.sha256_file(report_path),
                    json.dumps(report_payload, sort_keys=True),
                ),
            )
            connection.commit()

        with self.assertRaisesRegex(
            ValueError,
            "context ledger missing artifacts row for opencode safety transform attempt",
        ):
            validate_context_ledger_case(case)

    def test_context_ledger_opencode_safety_attempt_requires_worker_executed_event_binding(self) -> None:
        target_dir = REPO_ROOT / "target"
        target_dir.mkdir(exist_ok=True)
        temp_dir = Path(tempfile.mkdtemp(prefix="ledger-safety-attempt-event-", dir=target_dir))
        case = write_context_ledger_case(temp_dir)
        run_id = case["context_payload"]["run_id"]
        worker = case["agent_payload"]["agents_by_worker_id"]["worker-001"]
        report_path = REPO_ROOT / worker["report_path"]
        attempt_path = temp_dir / "out" / "workers" / "worker-001" / "harness" / "opencode-safety-transform-attempt.json"
        other_attempt_path = temp_dir / "out" / "workers" / "worker-001" / "harness" / "other-opencode-safety-transform-attempt.json"
        write_json(attempt_path, {"report_kind": "opencode-safety-transform-attempt", "run_id": run_id, "worker_id": "worker-001"})
        write_json(
            other_attempt_path,
            {"report_kind": "opencode-safety-transform-attempt", "run_id": run_id, "worker_id": "worker-001"},
        )
        attempt_ref = {"path": repo_relative(attempt_path), "sha256": validator.sha256_file(attempt_path)}
        other_attempt_ref = {"path": repo_relative(other_attempt_path), "sha256": validator.sha256_file(other_attempt_path)}
        worker["opencode_safety_transform_attempt"] = json.loads(json.dumps(attempt_ref))
        write_json(case["agent_index"], case["agent_payload"])
        report_payload = json.loads(report_path.read_text(encoding="utf-8"))
        report_payload["opencode_safety_transform_attempt"] = json.loads(json.dumps(attempt_ref))
        write_json(report_path, report_payload)
        report_ref = {"path": repo_relative(report_path), "sha256": validator.sha256_file(report_path)}
        with closing(sqlite3.connect(case["ledger"])) as connection:
            connection.execute(
                "update artifacts set sha256=?, payload_json=? where kind='agent-index'",
                (validator.sha256_file(case["agent_index"]), json.dumps(case["agent_payload"], sort_keys=True)),
            )
            connection.execute(
                "update artifacts set sha256=?, payload_json=? where kind='run-worker-report'",
                (validator.sha256_file(report_path), json.dumps(report_payload, sort_keys=True)),
            )
            connection.execute(
                """
                insert into artifacts(
                  run_id, agent_id, kind, repo_rel_path, sha256, status, semantic_role, payload_json, created_at
                ) values (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    run_id,
                    "worker-001",
                    "opencode-safety-transform-attempt",
                    attempt_ref["path"],
                    attempt_ref["sha256"],
                    "passed",
                    "agent-safety-transform-attempt",
                    json.dumps({"report_kind": "opencode-safety-transform-attempt"}, sort_keys=True),
                    "2026-07-01T00:00:00Z",
                ),
            )
            connection.execute(
                """
                create table events(
                  event_id integer primary key autoincrement,
                  run_id text not null,
                  event_type text not null,
                  payload_json text not null,
                  created_at text not null
                )
                """
            )
            connection.execute(
                "insert into events(run_id, event_type, payload_json, created_at) values (?, ?, ?, ?)",
                (
                    run_id,
                    "worker_executed",
                    json.dumps(
                        {
                            "worker_id": "worker-001",
                            "worker_report": report_ref,
                            "opencode_safety_transform_attempt": other_attempt_ref,
                        },
                        sort_keys=True,
                    ),
                    "2026-07-01T00:00:00Z",
                ),
            )
            connection.commit()

        with self.assertRaisesRegex(
            ValueError,
            "context ledger worker_executed event opencode_safety_transform_attempt must match",
        ):
            validate_context_ledger_case(case)

    def test_context_ledger_agent_index_payload_json_drift_fails(self) -> None:
        target_dir = REPO_ROOT / "target"
        target_dir.mkdir(exist_ok=True)
        temp_dir = Path(tempfile.mkdtemp(prefix="ledger-agent-payload-drift-", dir=target_dir))
        case = write_context_ledger_case(temp_dir)

        self.assertEqual(validate_context_ledger_case(case)["status"], "passed")

        with closing(sqlite3.connect(case["ledger"])) as connection:
            connection.execute(
                "update artifacts set payload_json=? where kind='agent-index'",
                (json.dumps({"forged": True}),),
            )
            connection.commit()

        with self.assertRaisesRegex(ValueError, "agent-index payload_json must match agent_index"):
            validate_context_ledger_case(case)

        with closing(sqlite3.connect(case["ledger"])) as connection:
            connection.execute(
                "update artifacts set payload_json=? where kind='agent-index'",
                ("{not-json",),
            )
            connection.commit()

        with self.assertRaisesRegex(ValueError, "agent-index payload_json must be valid JSON"):
            validate_context_ledger_case(case)

    def test_context_ledger_run_id_drift_fails_closed(self) -> None:
        target_dir = REPO_ROOT / "target"
        target_dir.mkdir(exist_ok=True)

        with self.subTest(drift="context_packs_row_run_id"):
            temp_dir = Path(tempfile.mkdtemp(prefix="ledger-run-id-drift-", dir=target_dir))
            case = write_context_ledger_case(temp_dir, ledger_run_id="forged-run")

            with self.assertRaisesRegex(ValueError, "context_packs run_id must match context_pack run_id"):
                validate_context_ledger_case(case)

        for kind, expected_error in (
            ("agent-index", "agent-index artifact run_id must match context_packs run_id"),
            ("competition-run-summary", "worker summary run_id must match context_packs run_id"),
            ("run-worker-report", "worker report run_id must match context_packs run_id"),
        ):
            with self.subTest(drift=kind):
                temp_dir = Path(tempfile.mkdtemp(prefix="ledger-run-id-drift-", dir=target_dir))
                case = write_context_ledger_case(temp_dir)

                self.assertEqual(validate_context_ledger_case(case)["status"], "passed")

                with closing(sqlite3.connect(case["ledger"])) as connection:
                    connection.execute(
                        "update artifacts set run_id=? where kind=?",
                        ("forged-run", kind),
                    )
                    connection.commit()

                with self.assertRaisesRegex(ValueError, expected_error):
                    validate_context_ledger_case(case)

    def test_context_ledger_worker_rows_must_bind_worker_identity(self) -> None:
        target_dir = REPO_ROOT / "target"
        target_dir.mkdir(exist_ok=True)

        with self.subTest(drift="summary_agent_id"):
            temp_dir = Path(tempfile.mkdtemp(prefix="ledger-worker-identity-", dir=target_dir))
            case = write_context_ledger_case(temp_dir)

            self.assertEqual(validate_context_ledger_case(case)["status"], "passed")

            with closing(sqlite3.connect(case["ledger"])) as connection:
                connection.execute(
                    "update artifacts set agent_id=? where kind='competition-run-summary'",
                    ("worker-999",),
                )
                connection.commit()

            with self.assertRaisesRegex(ValueError, "worker summary agent_id must match worker_id"):
                validate_context_ledger_case(case)

        with self.subTest(drift="isolated_out_root"):
            temp_dir = Path(tempfile.mkdtemp(prefix="ledger-worker-identity-", dir=target_dir))
            case = write_context_ledger_case(
                temp_dir,
                isolated_out_root=repo_relative(temp_dir / "out" / "workers" / "worker-002"),
            )

            with self.assertRaisesRegex(ValueError, "worker summary path must be under agent isolated_out_root"):
                validate_context_ledger_case(case)

    def test_context_pack_workers_must_match_agent_index_workers(self) -> None:
        config = load_default_config()
        config["entrypoints"] = [entrypoint_by_id(config, "before_after_judge_demo")]
        config["test_contract"]["required_entrypoint_ids"] = ["before_after_judge_demo"]
        temp_config = write_temp_config(config)
        temp_dir = temp_config.parent
        out_root = bind_entrypoint_to_out_root(config, temp_config, entry_index=0, out_root=temp_dir / "out")
        context_pack = out_root / "harness" / "context-pack.json"
        agent_index = out_root / "harness" / "agent-index.json"
        placeholder = out_root / "summary" / "placeholder.json"
        request = out_root / "harness" / "assignments" / "worker-001-request.json"
        other_request = out_root / "harness" / "assignments" / "worker-001-other-request.json"
        assignment = out_root / "harness" / "assignments" / "worker-001.json"
        summary = out_root / "workers" / "worker-001" / "summary" / "competition-run-summary.json"
        report = out_root / "workers" / "worker-001" / "harness" / "run-worker-report.json"
        for artifact in [placeholder, request, other_request, assignment, summary, report]:
            artifact.parent.mkdir(parents=True, exist_ok=True)
            artifact.write_text("{}\n", encoding="utf-8")
        config["entrypoints"][0]["expected_artifacts"] = {
            "competition_summary": repo_relative(placeholder),
            "workflow_metrics": repo_relative(placeholder),
            "context_pack": repo_relative(context_pack),
            "agent_index": repo_relative(agent_index),
        }
        write_json(temp_config, config)
        common_worker = {
            "assignment_path": repo_relative(assignment),
            "function": "demo_unit",
            "report_path": repo_relative(report),
            "request_path": repo_relative(request),
            "slice_id": "demo-unit",
            "source_commit": "abc123",
            "source_sha256": "f" * 64,
            "summary_path": repo_relative(summary),
            "worker_id": "worker-001",
        }
        write_json(
            context_pack,
            {
                "report_kind": "context-pack",
                "entrypoints": {
                    "primary_report": repo_relative(placeholder),
                    "evaluate_report": repo_relative(placeholder),
                    "worker_plan": None,
                },
                "context_management_contract": {
                    "agent_index": repo_relative(agent_index),
                    "chat_output_is_evidence": False,
                    "context_pack": repo_relative(context_pack),
                    "contract_kind": "context-management",
                    "evidence_policy": "on-disk-artifacts-only",
                    "pipeline": [
                        {"stage": "plan", "role": "planner"},
                        {"stage": "translate", "role": "worker", "fanout": True},
                        {"stage": "verify", "role": "verifier"},
                        {"stage": "repair", "role": "repairer", "max_rounds": 5},
                    ],
                    "resume_protocol": {
                        "checkpoint_backend": "sqlite",
                        "worker_state_source": "agent-index.agents_by_worker_id",
                    },
                    "schema_version": 1,
                    "semantic_gate": False,
                },
                "workers": [common_worker],
            },
        )
        drifted_worker = dict(common_worker)
        drifted_worker["request_path"] = repo_relative(other_request)
        write_json(
            agent_index,
            {
                "report_kind": "agent-index",
                "agent_coordination_contract": {
                    "chat_output_is_evidence": False,
                    "checkpoint_backend": "sqlite",
                    "contract_kind": "agent-coordination",
                    "roles": {
                        "planner": {},
                        "worker": {"isolation": "per-worker out_root"},
                        "repairer": {"round_cap": 5},
                        "verifier": {},
                        "reporter": {},
                    },
                    "schema_version": 1,
                    "semantic_gate": False,
                    "worker_count": 1,
                },
                "agents": [drifted_worker],
                "agents_by_worker_id": {
                    "worker-001": {
                        **drifted_worker,
                        "isolated_out_root": repo_relative(out_root / "workers" / "worker-001"),
                    }
                },
            },
        )

        result = validator.validate_config(temp_config, require_local_artifacts=True, repo_root=REPO_ROOT)

        self.assertEqual(result["status"], "failed")
        self.assertTrue(
            any("field request_path must match" in error for error in result["errors"]),
            result["errors"],
        )

    def test_context_pack_semantic_gate_fails_closed(self) -> None:
        config = load_default_config()
        config["entrypoints"] = [entrypoint_by_id(config, "before_after_judge_demo")]
        config["test_contract"]["required_entrypoint_ids"] = ["before_after_judge_demo"]
        temp_config = write_temp_config(config)
        temp_dir = temp_config.parent
        out_root = bind_entrypoint_to_out_root(config, temp_config, entry_index=0, out_root=temp_dir / "out")
        context_pack = out_root / "harness" / "context-pack.json"
        agent_index = out_root / "harness" / "agent-index.json"
        placeholder = out_root / "summary" / "placeholder.json"
        placeholder.parent.mkdir(parents=True, exist_ok=True)
        placeholder.write_text("{}\n", encoding="utf-8")
        config["entrypoints"][0]["expected_artifacts"] = {
            "competition_summary": repo_relative(placeholder),
            "workflow_metrics": repo_relative(placeholder),
            "context_pack": repo_relative(context_pack),
            "agent_index": repo_relative(agent_index),
        }
        write_json(temp_config, config)
        write_json(
            context_pack,
            {
                "report_kind": "context-pack",
                "context_management_contract": {
                    "agent_index": repo_relative(agent_index),
                    "chat_output_is_evidence": False,
                    "context_pack": repo_relative(context_pack),
                    "contract_kind": "context-management",
                    "evidence_policy": "on-disk-artifacts-only",
                    "pipeline": [
                        {"stage": "plan"},
                        {"stage": "translate", "fanout": True},
                        {"stage": "verify"},
                        {"stage": "repair", "max_rounds": 5},
                    ],
                    "resume_protocol": {
                        "checkpoint_backend": "sqlite",
                        "worker_state_source": "agent-index.agents_by_worker_id",
                    },
                    "schema_version": 1,
                    "semantic_gate": True,
                },
            },
        )
        write_json(
            agent_index,
            {
                "report_kind": "agent-index",
                "agent_coordination_contract": {
                    "chat_output_is_evidence": False,
                    "checkpoint_backend": "sqlite",
                    "contract_kind": "agent-coordination",
                    "roles": {
                        "planner": {},
                        "worker": {"isolation": "per-worker out_root"},
                        "repairer": {"round_cap": 5},
                        "verifier": {},
                        "reporter": {},
                    },
                    "schema_version": 1,
                    "semantic_gate": False,
                    "worker_count": 0,
                },
                "agents": [],
                "agents_by_worker_id": {},
            },
        )

        result = validator.validate_config(temp_config, require_local_artifacts=True, repo_root=REPO_ROOT)

        self.assertEqual(result["status"], "failed")
        self.assertTrue(
            any("context_management_contract.semantic_gate must be false" in error for error in result["errors"]),
            result["errors"],
        )

    def test_generated_draft_semantic_pass_claim_fails_closed(self) -> None:
        config = load_default_config()
        config["claim_boundary"]["generated_draft_semantic_pass"] = True
        path = write_temp_config(config)

        result = validator.validate_config(path, repo_root=REPO_ROOT)

        self.assertEqual(result["status"], "failed")
        self.assertTrue(
            any("generated_draft_semantic_pass must be false" in error for error in result["errors"]),
            result["errors"],
        )

    def test_entrypoint_proof_class_must_be_allowed(self) -> None:
        config = load_default_config()
        config["entrypoints"][0]["proof_class"] = "unlisted-proof"
        path = write_temp_config(config)

        result = validator.validate_config(path, repo_root=REPO_ROOT)

        self.assertEqual(result["status"], "failed")
        self.assertTrue(
            any("entrypoint proof_class must be allowed" in error for error in result["errors"]),
            result["errors"],
        )

    def test_profile_contract_accepts_command_proof_class_override(self) -> None:
        temp_config = write_temp_config(load_default_config())
        profile_path = temp_config.parent / "profile.json"
        write_json(
            profile_path,
            {
                "profile_id": "demo-profile",
                "proof_class": "local-simulation",
                "target_id": "demo",
                "source_repository": "https://example.com/FlashDB.git",
                "source_branch": "competition",
                "source_commit": "abc123",
                "mode": "deterministic",
            },
        )
        entry = {
            "id": "demo_exact_profile",
            "profile": {"path": repo_relative(profile_path), "profile_id": "demo-profile"},
            "proof_class": "competition-exact",
            "run_id": "run-demo-exact",
            "command": (
                "python3 -B -m validation.tools.opencode_agent_harness evaluate "
                f"--profile {repo_relative(profile_path)} --run-id run-demo-exact "
                "--out-root target/demo-exact --proof-class competition-exact"
            ),
        }

        result = validator.validate_entrypoint_profile_contract(
            entry,
            config={"target_id": "demo"},
            source_pin_contract={
                "repository": "https://example.com/FlashDB.git",
                "branch": "competition",
                "allowed_commits": ["abc123"],
            },
            repo_root=REPO_ROOT,
        )

        self.assertEqual(result["profile_proof_class"], "local-simulation")
        self.assertEqual(result["proof_class"], "competition-exact")
        self.assertEqual(result["proof_class_resolution"]["source"], "cli-override")
        self.assertTrue(result["proof_class_resolution"]["changed"])

    def test_profile_contract_rejects_command_proof_class_mismatch(self) -> None:
        temp_config = write_temp_config(load_default_config())
        profile_path = temp_config.parent / "profile.json"
        write_json(
            profile_path,
            {
                "profile_id": "demo-profile",
                "proof_class": "local-simulation",
                "target_id": "demo",
                "source_commit": "abc123",
            },
        )
        entry = {
            "id": "demo_exact_profile",
            "profile": {"path": repo_relative(profile_path), "profile_id": "demo-profile"},
            "proof_class": "competition-exact",
            "run_id": "run-demo-exact",
            "command": (
                "python3 -B -m validation.tools.opencode_agent_harness evaluate "
                f"--profile {repo_relative(profile_path)} --run-id run-demo-exact "
                "--out-root target/demo-exact --proof-class local-simulation"
            ),
        }

        with self.assertRaisesRegex(ValueError, "command --proof-class must match entrypoint proof_class"):
            validator.validate_entrypoint_profile_contract(
                entry,
                config={"target_id": "demo"},
                source_pin_contract={
                    "repository": "https://example.com/FlashDB.git",
                    "branch": "competition",
                    "allowed_commits": ["abc123"],
                },
                repo_root=REPO_ROOT,
            )

    def test_command_flags_reject_duplicate_proof_class(self) -> None:
        with self.assertRaisesRegex(ValueError, "command must not repeat --proof-class"):
            validator.parsed_command_flags(
                "python3 -B -m validation.tools.opencode_agent_harness evaluate "
                "--profile config/demo.json --run-id run --out-root target/out "
                "--proof-class local-simulation --proof-class competition-exact"
            )

    def test_default_entrypoint_commands_use_portable_python3_b_contract(self) -> None:
        config = load_default_config()

        for entry in config["entrypoints"]:
            argv = shlex.split(entry["command"])
            self.assertGreaterEqual(len(argv), 3, entry["id"])
            self.assertEqual(argv[:2], ["python3", "-B"], entry["id"])
