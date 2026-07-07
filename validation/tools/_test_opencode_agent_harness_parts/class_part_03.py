class _OpenCodeAgentHarnessTestPart03:
    def test_evaluate_opencode_passes_preflight_report_to_workers(self) -> None:
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
            preflight_report = write_passing_opencode_preflight_report(
                out_root / "harness" / "opencode-preflight-report.json",
                run_id="run-evaluate-opencode",
            )

            with patch.object(
                harness,
                "run_worker",
                return_value={
                    "exit_code": 0,
                    "summary_status": "passed",
                    "summary_path": "",
                    "report_path": "target/report.json",
                    "recorded": False,
                },
            ) as runner:
                result = harness.evaluate(
                    run_id="run-evaluate-opencode",
                    target_id="flashdb",
                    source_repo_root=source_root,
                    source_file="src/demo.c",
                    functions=["first_unit"],
                    source_commit="abc123",
                    out_root=out_root,
                    proof_class="local-simulation",
                    slice_id_prefix="eval-opencode",
                    worker_prefix="eval-worker",
                    mode="opencode",
                    opencode_preflight_report=preflight_report,
                    execute_merge=False,
                    auto_retry=False,
                    command_runner=subprocess.run,
                    repo_root=REPO_ROOT,
                )

            self.assertEqual(result["mode"], "opencode")
            runner.assert_called_once()
            self.assertEqual(runner.call_args.kwargs["mode"], "opencode")
            self.assertEqual(runner.call_args.kwargs["opencode_preflight_report"], preflight_report)

    def test_evaluate_context_pack_preserves_unrecorded_failed_worker(self) -> None:
        with temp_repo_dir() as tmp:
            out_root = Path(tmp) / "competition-out"
            source_root = Path(tmp) / "FlashDB"
            source_file = source_root / "src" / "demo.c"
            source_file.parent.mkdir(parents=True)
            source_file.write_text(
                """
                int missing_summary_unit(int value) {
                    return value + 1;
                }
                """,
                encoding="utf-8",
            )
            merge_called = False

            def fake_runner(argv: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
                nonlocal merge_called
                if "validation/tools/run_competition.py" in argv:
                    merge_called = True
                return subprocess.CompletedProcess(argv, 0, stdout="no summary written\n", stderr="")

            result = harness.evaluate(
                run_id="run-evaluate-failed",
                target_id="flashdb",
                source_repo_root=source_root,
                source_file="src/demo.c",
                functions=["missing_summary_unit"],
                source_commit="abc123",
                out_root=out_root,
                proof_class="local-simulation",
                slice_id_prefix="eval-failed",
                worker_prefix="eval-worker",
                execute_merge=True,
                auto_retry=False,
                command_runner=fake_runner,
                repo_root=REPO_ROOT,
            )

            self.assertEqual(result["status"], "failed")
            self.assertEqual(result["exit_code"], 1)
            self.assertFalse(merge_called)
            self.assertEqual(result["run_plan"]["merge_execution"]["status"], "skipped")
            self.assertEqual(result["run_plan"]["merge_execution"]["reason"], "unrecorded-worker-summaries")
            context_pack = json.loads((REPO_ROOT / result["context_pack"]["path"]).read_text(encoding="utf-8"))
            agent_index = json.loads((REPO_ROOT / result["agent_index"]["path"]).read_text(encoding="utf-8"))
            worker = context_pack["workers"][0]
            agent = agent_index["agents"][0]
            self.assertFalse(worker["recorded"])
            self.assertEqual(worker["exit_code"], 1)
            self.assertEqual(worker["summary_status"], "missing-summary")
            self.assert_repo_relative_posix_path(worker["summary_path"])
            self.assert_repo_relative_posix_path(worker["report_path"])
            self.assertFalse((REPO_ROOT / worker["summary_path"]).exists())
            self.assertTrue((REPO_ROOT / worker["report_path"]).exists())
            self.assertFalse(agent["recorded"])
            self.assertEqual(agent["status"], "missing-summary")
            self.assertEqual(context_pack["entrypoints"]["merge_summary"], None)
            self.assertEqual(context_pack["acceptance_boundary"]["semantic_acceptance"], "final verification and worker summaries decide acceptance; this pack is an index only")

    def test_run_batch_profile_binds_before_after_exhibit_report(self) -> None:
        with temp_repo_dir() as tmp:
            out_root = Path(tmp) / "competition-out"
            source_root = Path(tmp) / "demo-source"
            source_file = source_root / "src" / "demo.c"
            source_file.parent.mkdir(parents=True)
            source_file.write_text(
                """
                int store_add_one(int value, int* out) {
                    out[0] = value + 1;
                    return 0;
                }
                """,
                encoding="utf-8",
            )
            spec_path = write_slice_spec(
                Path(tmp) / "slice-specs" / "store-add-one.json",
                "demo",
                "store-add-one",
                "store_add_one",
                "abc123",
            )
            profile_path = Path(tmp) / "planned-batch.json"
            profile_path.write_text(
                json.dumps(
                    {
                        "schema_version": 1,
                        "profile_id": "demo-before-after",
                        "proof_class": "local-simulation",
                        "target_id": "demo",
                        "source_repo_root": repo_rel(source_root),
                        "source_file": "src/demo.c",
                        "source_commit": "abc123",
                        "functions": ["store_add_one"],
                        "slice_specs": [repo_rel(spec_path)],
                        "reuse_accepted_evidence": True,
                        "accepted_evidence_root": "validation/evidence",
                        "slice_id_prefix": "demo",
                        "worker_prefix": "worker",
                        "mode": "deterministic",
                        "execute_merge": True,
                        "emit_before_after_exhibit_report": True,
                        "acceptance_boundary": {
                            "semantic_claim_source": "accepted_evidence_binding",
                            "generated_draft_semantic_pass": False,
                            "claim": "test before/after exhibit",
                        },
                    }
                ),
                encoding="utf-8",
            )

            def fake_runner(argv: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
                if "scripts/c2rust-migrator.py" in argv:
                    request_path = REPO_ROOT / argv[argv.index("--input") + 1]
                    request = json.loads(request_path.read_text(encoding="utf-8"))
                    summary_path = REPO_ROOT / request["out_root"] / "summary" / "competition-run-summary.json"
                    write_worker_summary(summary_path, request["run_id"], status="passed", failed=0, semantic_pass=1)
                    return subprocess.CompletedProcess(argv, 0, stdout="worker ok\n", stderr="")
                summary_path = out_root / "summary" / "competition-run-summary.json"
                write_worker_summary(
                    summary_path,
                    "run-before-after",
                    status="passed",
                    failed=0,
                    semantic_pass=1,
                    workflow_metrics=before_after_worker_metrics(out_root, "run-before-after"),
                )
                return subprocess.CompletedProcess(argv, 0, stdout="merge ok\n", stderr="")

            result = harness.run_batch_profile(
                profile_path=profile_path,
                run_id="run-before-after",
                out_root=out_root,
                command_runner=fake_runner,
                repo_root=REPO_ROOT,
            )

            exhibit_ref = result["before_after_exhibit_report"]
            exhibit_path = REPO_ROOT / exhibit_ref["path"]
            self.assertTrue(exhibit_path.exists())
            self.assertEqual(exhibit_ref["sha256"], harness.sha256_file(exhibit_path))
            self.assertEqual(exhibit_ref["status"], "passed")
            self.assertEqual(exhibit_ref["unit_count"], 1)
            exhibit = json.loads(exhibit_path.read_text(encoding="utf-8"))
            self.assertEqual(exhibit["report_kind"], "before-after-exhibit")
            self.assertEqual(exhibit["status"], "passed")
            self.assertEqual(set(exhibit["stage_contracts"]), {"planner", "worker", "verifier", "repairer", "reporter"})
            self.assertEqual(exhibit["stage_contracts"]["planner"]["status"], "planned")
            self.assertEqual(exhibit["stage_contracts"]["planner"]["units"][0]["slice_id"], "store-add-one")
            self.assertEqual(exhibit["translation_before_after"]["status"], "bound")
            self.assertEqual(exhibit["translation_before_after"]["unit_count"], 1)
            unit = exhibit["units"][0]
            self.assertEqual(unit["unsafe_reduction"]["reduced_by"], 3)
            self.assertEqual(unit["patch_origin"]["source"], "accepted_safe_evidence")
            self.assertFalse(unit["patch_origin"]["opencode_session_bound"])
            self.assertEqual(unit["patch_origin"]["semantic_claim_source"], "accepted_evidence_binding")
            self.assertFalse(unit["patch_origin"]["generated_draft_semantic_pass"])
            provenance = unit["safety_loop_provenance"]
            self.assertEqual(provenance["status"], "accepted_evidence_bound")
            self.assertEqual(provenance["patch_source"], "accepted_safe_evidence")
            self.assertEqual(provenance["unsafe_delta"]["reduced_by"], 3)
            self.assertFalse(provenance["opencode_session_bound"])
            self.assertFalse(provenance["repair_history_bound"])
            self.assertFalse(provenance["semantic_gate"])
            self.assertEqual(provenance["translation_coverage_numerator"], 0)
            rollup = exhibit["safety_loop_provenance"]
            self.assertEqual(rollup["status"], "bound")
            self.assertEqual(rollup["unit_count"], 1)
            self.assertEqual(rollup["accepted_evidence_bound_unit_count"], 1)
            self.assertEqual(rollup["opencode_session_bound_unit_count"], 0)
            self.assertEqual(rollup["repair_history_bound_unit_count"], 0)
            self.assertEqual(rollup["measured_unsafe_reduction_unit_count"], 1)
            self.assertFalse(rollup["semantic_gate"])
            self.assertEqual(rollup["translation_coverage_numerator"], 0)
            self.assertIn("run-batch-profile", exhibit["reproduction"]["run_command"])
            self.assertIn("validate_competition_run_summary.py", exhibit["reproduction"]["verify_command"])
            judge_summary = result["judge_summary"]
            self.assertEqual(judge_summary["harness_architecture"]["entrypoint"], "run-batch-profile")
            self.assertEqual(judge_summary["harness_architecture"]["context_pack"]["path"], result["context_pack"]["path"])
            self.assertEqual(judge_summary["core_translation_quality"]["final_gate_status"], "passed")
            self.assertEqual(judge_summary["core_translation_quality"]["semantic_claim_source"], "accepted_evidence_binding")
            self.assertFalse(judge_summary["core_translation_quality"]["generated_draft_semantic_pass"])
            self.assertEqual(judge_summary["core_translation_quality"]["before_after_exhibit"]["status"], "passed")
            self.assertEqual(judge_summary["core_translation_quality"]["before_after_exhibit"]["unit_count"], 1)
            self.assertEqual(judge_summary["core_translation_quality"]["unsafe_reduction"]["reduced_by"], 3)
            persisted_report = json.loads((out_root / "harness" / "batch-profile-report.json").read_text(encoding="utf-8"))
            self.assertEqual(persisted_report["judge_summary"], judge_summary)
            artifact_rows = fetch_rows(
                result["db_path"],
                "select kind, repo_rel_path, semantic_role from artifacts where kind='before-after-exhibit-report'",
            )
            self.assertEqual(
                artifact_rows,
                [("before-after-exhibit-report", exhibit_ref["path"], "before-after-exhibit")],
            )

    def test_before_after_exhibit_surfaces_bound_repair_history(self) -> None:
        with temp_repo_dir() as tmp:
            out_root = Path(tmp) / "competition-out"
            summary_path = out_root / "summary" / "competition-run-summary.json"
            profile_path = Path(tmp) / "planned-batch.json"
            verified_baseline_ref = verified_unsafe_baseline_ref_for_tests()
            profile = {
                "schema_version": 1,
                "profile_id": "demo-before-after-repair",
                "emit_before_after_exhibit_report": True,
                "require_repair_trace": True,
                "attempt_evidence_policy": {
                    "mode": "baseline_repair_gate",
                    "baseline_attempt": {
                        "verified_unsafe_baseline": verified_baseline_ref,
                    },
                },
                "acceptance_boundary": {
                    "semantic_claim_source": "accepted_evidence_binding",
                    "generated_draft_semantic_pass": False,
                },
            }
            profile_path.write_text(json.dumps(profile), encoding="utf-8")
            workflow_metrics = before_after_worker_metrics(
                out_root,
                "run-before-after-repair",
                baseline_verification=verified_baseline_ref,
            )
            history_path = summary_path.parent / "retry-repair-history-demo.jsonl"
            history_path.parent.mkdir(parents=True, exist_ok=True)
            history_path.write_text(
                json.dumps({"attempt": 1, "status": "failed", "root_cause_key": "rustc_compile_failed"})
                + "\n"
                + json.dumps({"attempt": 2, "status": "verified", "summary_status": "passed"})
                + "\n",
                encoding="utf-8",
            )
            unit = workflow_metrics["per_unit_statuses"][0]
            unit["repair_rounds"] = 1
            unit["auto_recovered"] = True
            unit["root_cause_key"] = "rustc_compile_failed"
            unit["repair_history"] = {
                "patch_events_path": history_path.name,
                "patch_events_sha256": harness.sha256_file(history_path),
                "statuses": ["failed", "verified"],
                "rollback_ids": ["target/competition-out/workers/worker-a/harness/rollback-before-retry.json"],
                "verified": True,
            }
            workflow_metrics["avg_repair_rounds"] = 1.0
            workflow_metrics["auto_recovery_rate"] = 1.0
            workflow_metrics["root_cause_counts"] = {"rustc_compile_failed": 1}
            write_worker_summary(
                summary_path,
                "run-before-after-repair",
                status="passed",
                failed=0,
                semantic_pass=1,
                workflow_metrics=workflow_metrics,
            )

            result = harness.write_before_after_exhibit_profile_report(
                profile=profile,
                profile_path=profile_path,
                run_id="run-before-after-repair",
                proof_class="local-simulation",
                mode="deterministic",
                plan={"status": "planned", "units": [{"slice_id": "store-add-one"}]},
                run_result={"workers": [{"worker_id": "worker-a", "exit_code": 0}]},
                route_metrics_artifact=None,
                out_root=out_root,
                repo_root=REPO_ROOT,
            )

            self.assertIsNotNone(result)
            exhibit = result["payload"]
            unit_exhibit = exhibit["units"][0]
            self.assertEqual(unit_exhibit["repair_rounds"], 1)
            self.assertTrue(unit_exhibit["auto_recovered"])
            self.assertEqual(unit_exhibit["baseline_verification"], verified_baseline_ref)
            self.assertEqual(unit_exhibit["repair_history"]["patch_events_sha256"], harness.sha256_file(history_path))
            self.assertEqual(unit_exhibit["root_cause_key"], "rustc_compile_failed")
            self.assertEqual(unit_exhibit["patch_origin"]["source"], "accepted_safe_evidence")
            self.assertTrue(unit_exhibit["patch_origin"]["accepted_patch_bound"])
            self.assertFalse(unit_exhibit["patch_origin"]["opencode_session_bound"])
            self.assertTrue(unit_exhibit["patch_origin"]["repair_history_bound"])
            self.assertFalse(unit_exhibit["patch_origin"]["semantic_gate"])
            self.assertEqual(unit_exhibit["patch_origin"]["translation_coverage_numerator"], 0)
            self.assertEqual(unit_exhibit["safety_loop_provenance"]["status"], "accepted_evidence_bound")
            self.assertEqual(unit_exhibit["safety_loop_provenance"]["patch_source"], "accepted_safe_evidence")
            self.assertTrue(unit_exhibit["safety_loop_provenance"]["repair_history_bound"])
            self.assertEqual(unit_exhibit["safety_loop_provenance"]["repair_rounds"], 1)
            self.assertTrue(unit_exhibit["safety_loop_provenance"]["auto_recovered"])
            self.assertEqual(unit_exhibit["safety_loop_provenance"]["unsafe_delta"]["reduced_by"], 3)
            self.assertFalse(unit_exhibit["safety_loop_provenance"]["semantic_gate"])
            self.assertEqual(unit_exhibit["safety_loop_provenance"]["translation_coverage_numerator"], 0)
            repairer = exhibit["stage_contracts"]["repairer"]
            self.assertEqual(repairer["status"], "verified")
            self.assertEqual(repairer["repair_round_cap"], 5)
            self.assertEqual(repairer["observed_repair_unit_count"], 1)
            self.assertEqual(repairer["avg_repair_rounds"], 1.0)
            self.assertEqual(repairer["auto_recovery_rate"], 1.0)
            self.assertEqual(repairer["root_cause_counts"], {"rustc_compile_failed": 1})
            self.assertEqual(repairer["histories"][0]["unit_id"], "demo/store-add-one")

    def test_before_after_exhibit_requires_verified_baseline_when_repair_trace_is_required(self) -> None:
        with temp_repo_dir() as tmp:
            out_root = Path(tmp) / "competition-out"
            summary_path = out_root / "summary" / "competition-run-summary.json"
            profile_path = Path(tmp) / "planned-batch.json"
            verified_baseline = verified_unsafe_baseline_ref_for_tests()
            profile = {
                "schema_version": 1,
                "profile_id": "demo-before-after-strict-baseline",
                "emit_before_after_exhibit_report": True,
                "require_repair_trace": True,
                "attempt_evidence_policy": {
                    "mode": "baseline_repair_gate",
                    "baseline_attempt": {
                        "verified_unsafe_baseline": verified_baseline,
                    },
                },
                "acceptance_boundary": {
                    "semantic_claim_source": "accepted_evidence_binding",
                    "generated_draft_semantic_pass": False,
                },
            }
            profile_path.write_text(json.dumps(profile), encoding="utf-8")
            workflow_metrics = before_after_worker_metrics(out_root, "run-before-after-strict-baseline")
            history_path = summary_path.parent / "retry-repair-history-demo.jsonl"
            history_path.parent.mkdir(parents=True, exist_ok=True)
            history_path.write_text(
                json.dumps({"attempt": 1, "status": "failed", "root_cause_key": "rustc_compile_failed"})
                + "\n"
                + json.dumps({"attempt": 2, "status": "verified", "summary_status": "passed"})
                + "\n",
                encoding="utf-8",
            )
            unit = workflow_metrics["per_unit_statuses"][0]
            unit["repair_rounds"] = 1
            unit["auto_recovered"] = True
            unit["root_cause_key"] = "rustc_compile_failed"
            unit["repair_history"] = {
                "patch_events_path": history_path.name,
                "patch_events_sha256": harness.sha256_file(history_path),
                "statuses": ["failed", "verified"],
                "rollback_ids": ["target/competition-out/workers/worker-a/harness/rollback-before-retry.json"],
                "verified": True,
            }
            workflow_metrics["avg_repair_rounds"] = 1.0
            workflow_metrics["auto_recovery_rate"] = 1.0
            workflow_metrics["root_cause_counts"] = {"rustc_compile_failed": 1}
            write_worker_summary(
                summary_path,
                "run-before-after-strict-baseline",
                status="passed",
                failed=0,
                semantic_pass=1,
                workflow_metrics=workflow_metrics,
            )

            with self.assertRaisesRegex(SystemExit, "requires baseline_verification"):
                harness.write_before_after_exhibit_profile_report(
                    profile=profile,
                    profile_path=profile_path,
                    run_id="run-before-after-strict-baseline",
                    proof_class="local-simulation",
                    mode="deterministic",
                    plan={"status": "planned", "units": [{"slice_id": "store-add-one"}]},
                    run_result={"workers": [{"worker_id": "worker-a", "exit_code": 0}]},
                    route_metrics_artifact=None,
                    out_root=out_root,
                    repo_root=REPO_ROOT,
                )

    def test_before_after_exhibit_requires_declared_verified_baseline_when_repair_trace_is_required(self) -> None:
        with temp_repo_dir() as tmp:
            out_root = Path(tmp) / "competition-out"
            summary_path = out_root / "summary" / "competition-run-summary.json"
            profile_path = Path(tmp) / "planned-batch.json"
            profile = {
                "schema_version": 1,
                "profile_id": "demo-before-after-missing-baseline-policy",
                "emit_before_after_exhibit_report": True,
                "require_repair_trace": True,
                "acceptance_boundary": {
                    "semantic_claim_source": "accepted_evidence_binding",
                    "generated_draft_semantic_pass": False,
                },
            }
            profile_path.write_text(json.dumps(profile), encoding="utf-8")
            workflow_metrics = before_after_worker_metrics(out_root, "run-before-after-missing-baseline-policy")
            history_path = summary_path.parent / "retry-repair-history-demo.jsonl"
            history_path.parent.mkdir(parents=True, exist_ok=True)
            history_path.write_text(
                json.dumps({"attempt": 1, "status": "failed", "root_cause_key": "rustc_compile_failed"})
                + "\n"
                + json.dumps({"attempt": 2, "status": "verified", "summary_status": "passed"})
                + "\n",
                encoding="utf-8",
            )
            unit = workflow_metrics["per_unit_statuses"][0]
            unit["repair_rounds"] = 1
            unit["auto_recovered"] = True
            unit["root_cause_key"] = "rustc_compile_failed"
            unit["repair_history"] = {
                "patch_events_path": history_path.name,
                "patch_events_sha256": harness.sha256_file(history_path),
                "statuses": ["failed", "verified"],
                "rollback_ids": ["target/competition-out/workers/worker-a/harness/rollback-before-retry.json"],
                "verified": True,
            }
            workflow_metrics["avg_repair_rounds"] = 1.0
            workflow_metrics["auto_recovery_rate"] = 1.0
            workflow_metrics["root_cause_counts"] = {"rustc_compile_failed": 1}
            write_worker_summary(
                summary_path,
                "run-before-after-missing-baseline-policy",
                status="passed",
                failed=0,
                semantic_pass=1,
                workflow_metrics=workflow_metrics,
            )

            with self.assertRaisesRegex(SystemExit, "requires verified unsafe baseline"):
                harness.write_before_after_exhibit_profile_report(
                    profile=profile,
                    profile_path=profile_path,
                    run_id="run-before-after-missing-baseline-policy",
                    proof_class="local-simulation",
                    mode="deterministic",
                    plan={"status": "planned", "units": [{"slice_id": "store-add-one"}]},
                    run_result={"workers": [{"worker_id": "worker-a", "exit_code": 0}]},
                    route_metrics_artifact=None,
                    out_root=out_root,
                    repo_root=REPO_ROOT,
                )

    def test_before_after_exhibit_rejects_baseline_verification_drift(self) -> None:
        with temp_repo_dir() as tmp:
            out_root = Path(tmp) / "competition-out"
            summary_path = out_root / "summary" / "competition-run-summary.json"
            profile_path = Path(tmp) / "planned-batch.json"
            verified_baseline = verified_unsafe_baseline_ref_for_tests()
            drifted_baseline_path = summary_path.parent / "drifted-baseline-verification.json"
            drifted_baseline_path.parent.mkdir(parents=True, exist_ok=True)
            drifted_baseline_path.write_text(
                json.dumps(
                    {
                        "status": "passed",
                        "semantic_pass": True,
                        "semantic_claim_source": "verified_unsafe_baseline_gates",
                        "generated_draft_semantic_pass": False,
                    }
                )
                + "\n",
                encoding="utf-8",
            )
            drifted_baseline = {
                "path": drifted_baseline_path.name,
                "sha256": harness.sha256_file(drifted_baseline_path),
                "status": "passed",
                "semantic_pass": True,
                "semantic_claim_source": "verified_unsafe_baseline_gates",
                "generated_draft_semantic_pass": False,
            }
            profile = {
                "schema_version": 1,
                "profile_id": "demo-before-after-drifted-baseline",
                "emit_before_after_exhibit_report": True,
                "require_repair_trace": True,
                "attempt_evidence_policy": {
                    "mode": "baseline_repair_gate",
                    "baseline_attempt": {
                        "verified_unsafe_baseline": verified_baseline,
                    },
                },
                "acceptance_boundary": {
                    "semantic_claim_source": "accepted_evidence_binding",
                    "generated_draft_semantic_pass": False,
                },
            }
            profile_path.write_text(json.dumps(profile), encoding="utf-8")
            workflow_metrics = before_after_worker_metrics(
                out_root,
                "run-before-after-drifted-baseline",
                baseline_verification=drifted_baseline,
            )
            history_path = summary_path.parent / "retry-repair-history-demo.jsonl"
            history_path.parent.mkdir(parents=True, exist_ok=True)
            history_path.write_text(
                json.dumps({"attempt": 1, "status": "failed", "root_cause_key": "rustc_compile_failed"})
                + "\n"
                + json.dumps({"attempt": 2, "status": "verified", "summary_status": "passed"})
                + "\n",
                encoding="utf-8",
            )
            unit = workflow_metrics["per_unit_statuses"][0]
            unit["repair_rounds"] = 1
            unit["auto_recovered"] = True
            unit["root_cause_key"] = "rustc_compile_failed"
            unit["repair_history"] = {
                "patch_events_path": history_path.name,
                "patch_events_sha256": harness.sha256_file(history_path),
                "statuses": ["failed", "verified"],
                "rollback_ids": ["target/competition-out/workers/worker-a/harness/rollback-before-retry.json"],
                "verified": True,
            }
            workflow_metrics["avg_repair_rounds"] = 1.0
            workflow_metrics["auto_recovery_rate"] = 1.0
            workflow_metrics["root_cause_counts"] = {"rustc_compile_failed": 1}
            write_worker_summary(
                summary_path,
                "run-before-after-drifted-baseline",
                status="passed",
                failed=0,
                semantic_pass=1,
                workflow_metrics=workflow_metrics,
            )

            with self.assertRaisesRegex(SystemExit, "baseline_verification must match verified unsafe baseline"):
                harness.write_before_after_exhibit_profile_report(
                    profile=profile,
                    profile_path=profile_path,
                    run_id="run-before-after-drifted-baseline",
                    proof_class="local-simulation",
                    mode="deterministic",
                    plan={"status": "planned", "units": [{"slice_id": "store-add-one"}]},
                    run_result={"workers": [{"worker_id": "worker-a", "exit_code": 0}]},
                    route_metrics_artifact=None,
                    out_root=out_root,
                    repo_root=REPO_ROOT,
                )

    def test_before_after_exhibit_requires_verified_repair_trace_when_profile_demands_it(self) -> None:
        with temp_repo_dir() as tmp:
            out_root = Path(tmp) / "competition-out"
            summary_path = out_root / "summary" / "competition-run-summary.json"
            profile_path = Path(tmp) / "planned-batch.json"
            profile = {
                "schema_version": 1,
                "profile_id": "demo-before-after-strict-repair",
                "emit_before_after_exhibit_report": True,
                "require_repair_trace": True,
                "acceptance_boundary": {
                    "semantic_claim_source": "accepted_evidence_binding",
                    "generated_draft_semantic_pass": False,
                },
            }
            profile_path.write_text(json.dumps(profile), encoding="utf-8")
            write_worker_summary(
                summary_path,
                "run-before-after-strict-repair",
                status="passed",
                failed=0,
                semantic_pass=1,
                workflow_metrics=before_after_worker_metrics(out_root, "run-before-after-strict-repair"),
            )

            with self.assertRaisesRegex(SystemExit, "requires verified repair trace"):
                harness.write_before_after_exhibit_profile_report(
                    profile=profile,
                    profile_path=profile_path,
                    run_id="run-before-after-strict-repair",
                    proof_class="local-simulation",
                    mode="deterministic",
                    plan={"status": "planned", "units": [{"slice_id": "store-add-one"}]},
                    run_result={"workers": [{"worker_id": "worker-a", "exit_code": 0}]},
                    route_metrics_artifact=None,
                    out_root=out_root,
                    repo_root=REPO_ROOT,
                )

    def test_flashdb_before_after_profile_fails_closed_without_repair_trace(self) -> None:
        with temp_repo_dir() as tmp:
            out_root = Path(tmp) / "competition-out"
            summary_path = out_root / "summary" / "competition-run-summary.json"
            profile_path = REPO_ROOT / "config/competition-env/planned-batches/flashdb-fdb-utils-before-after.json"
            profile = json.loads(profile_path.read_text(encoding="utf-8"))
            self.assertTrue(profile["require_repair_trace"])
            self.assertEqual(profile["attempt_evidence_policy"]["mode"], "baseline_repair_gate")
            self.assertEqual(
                profile["attempt_evidence_policy"]["translation_before_after"]["path"],
                profile["acceptance_boundary"]["translation_before_after"],
            )
            self.assertEqual(
                profile["attempt_evidence_policy"]["baseline_attempt"]["root_cause_key"],
                "unsafe_baseline_requires_repair",
            )
            write_worker_summary(
                summary_path,
                "run-flashdb-before-after-strict-repair",
                status="passed",
                failed=0,
                semantic_pass=1,
                workflow_metrics=before_after_worker_metrics(out_root, "run-flashdb-before-after-strict-repair"),
            )

            with self.assertRaisesRegex(SystemExit, "requires verified repair trace"):
                harness.write_before_after_exhibit_profile_report(
                    profile=profile,
                    profile_path=profile_path,
                    run_id="run-flashdb-before-after-strict-repair",
                    proof_class="local-simulation",
                    mode="deterministic",
                    plan={"status": "planned", "units": [{"slice_id": "real-fdb-calc-crc32"}]},
                    run_result={"workers": [{"worker_id": "flashdb-worker-001-fdb-calc-crc32", "exit_code": 0}]},
                    route_metrics_artifact=None,
                    out_root=out_root,
                    repo_root=REPO_ROOT,
                )

    def test_flashdb_before_after_profile_run_batch_fails_closed_without_repair_trace(self) -> None:
        with temp_repo_dir() as tmp:
            out_root = Path(tmp) / "competition-out"
            profile_path = REPO_ROOT / "config/competition-env/planned-batches/flashdb-fdb-utils-before-after.json"

            def fake_runner(argv: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
                if "scripts/c2rust-migrator.py" in argv:
                    request_path = REPO_ROOT / argv[argv.index("--input") + 1]
                    request = json.loads(request_path.read_text(encoding="utf-8"))
                    summary_path = REPO_ROOT / request["out_root"] / "summary" / "competition-run-summary.json"
                    write_worker_summary(summary_path, request["run_id"], status="passed", failed=0, semantic_pass=1)
                    return subprocess.CompletedProcess(argv, 0, stdout="worker ok\n", stderr="")
                summary_path = out_root / "summary" / "competition-run-summary.json"
                write_worker_summary(
                    summary_path,
                    "run-flashdb-before-after-profile-strict",
                    status="passed",
                    failed=0,
                    semantic_pass=1,
                    workflow_metrics=before_after_worker_metrics(out_root, "run-flashdb-before-after-profile-strict"),
                )
                return subprocess.CompletedProcess(argv, 0, stdout="merge ok\n", stderr="")

            with self.assertRaisesRegex(SystemExit, "requires verified repair trace"):
                harness.run_batch_profile(
                    profile_path=profile_path,
                    run_id="run-flashdb-before-after-profile-strict",
                    out_root=out_root,
                    command_runner=fake_runner,
                    repo_root=REPO_ROOT,
                )

            self.assertFalse((out_root / "summary" / "before-after-exhibit.json").exists())
            self.assertFalse((out_root / "harness" / "batch-profile-report.json").exists())

    def test_run_batch_profile_auto_retry_produces_verified_before_after_repair_exhibit(self) -> None:
        with temp_repo_dir() as tmp:
            out_root = Path(tmp) / "competition-out"
            source_root = Path(tmp) / "demo-source"
            source_file = source_root / "src" / "demo.c"
            source_file.parent.mkdir(parents=True)
            source_file.write_text(
                """
                int store_add_one(int value, int* out) {
                    out[0] = value + 1;
                    return 0;
                }
                """,
                encoding="utf-8",
            )
            spec_path = write_slice_spec(
                Path(tmp) / "slice-specs" / "store-add-one.json",
                "demo",
                "store-add-one",
                "store_add_one",
                "abc123",
            )
            verified_baseline_ref = verified_unsafe_baseline_ref_for_tests()
            profile_path = Path(tmp) / "planned-batch.json"
            profile_path.write_text(
                json.dumps(
                    {
                        "schema_version": 1,
                        "profile_id": "demo-before-after-auto-repair",
                        "proof_class": "local-simulation",
                        "target_id": "demo",
                        "source_repo_root": repo_rel(source_root),
                        "source_file": "src/demo.c",
                        "source_commit": "abc123",
                        "functions": ["store_add_one"],
                        "slice_specs": [repo_rel(spec_path)],
                        "reuse_accepted_evidence": True,
                        "accepted_evidence_root": "validation/evidence",
                        "slice_id_prefix": "demo",
                        "worker_prefix": "worker",
                        "mode": "deterministic",
                        "execute_merge": True,
                        "auto_retry": True,
                        "emit_before_after_exhibit_report": True,
                        "require_repair_trace": True,
                        "attempt_evidence_policy": {
                            "mode": "baseline_repair_gate",
                            "baseline_attempt": {
                                "attempt_number": 1,
                                "verified_unsafe_baseline": verified_baseline_ref,
                            },
                            "accepted_attempt": {"min_attempt_number": 2, "require_hint_id": True},
                        },
                        "acceptance_boundary": {
                            "semantic_claim_source": "accepted_evidence_binding",
                            "generated_draft_semantic_pass": False,
                            "claim": "test auto-retry before/after exhibit",
                        },
                    }
                ),
                encoding="utf-8",
            )
            worker_attempts = 0
            seen_requests: list[dict] = []

            def fake_runner(argv: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
                nonlocal worker_attempts
                if "scripts/c2rust-migrator.py" in argv:
                    worker_attempts += 1
                    request_path = REPO_ROOT / argv[argv.index("--input") + 1]
                    request = json.loads(request_path.read_text(encoding="utf-8"))
                    seen_requests.append(request)
                    summary_path = REPO_ROOT / request["out_root"] / "summary" / "competition-run-summary.json"
                    if worker_attempts == 1:
                        write_worker_summary(summary_path, request["run_id"], status="failed", failed=1, semantic_pass=0)
                    else:
                        write_worker_summary(
                            summary_path,
                            request["run_id"],
                            status="passed",
                            failed=0,
                            semantic_pass=1,
                            workflow_metrics=before_after_worker_metrics(
                                out_root,
                                request["run_id"],
                                baseline_verification=verified_baseline_ref,
                            ),
                        )
                    return subprocess.CompletedProcess(argv, 0, stdout=f"worker attempt {worker_attempts}\n", stderr="")
                if "validation/tools/run_competition.py" in argv:
                    runtime_argv = [sys.executable, *argv[1:]]
                    return subprocess.run(
                        runtime_argv,
                        cwd=REPO_ROOT,
                        text=True,
                        encoding="utf-8",
                        errors="replace",
                        capture_output=True,
                    )
                return subprocess.run(
                    argv,
                    cwd=REPO_ROOT,
                    text=True,
                    encoding="utf-8",
                    errors="replace",
                    capture_output=True,
                )

            result = harness.run_batch_profile(
                profile_path=profile_path,
                run_id="run-before-after-auto-repair",
                out_root=out_root,
                command_runner=fake_runner,
                repo_root=REPO_ROOT,
            )

            run_plan_detail = result.get("run_plan") or {}
            merge_execution = run_plan_detail.get("merge_execution") or {}
            merge_logs = {}
            for stream, log_path in (merge_execution.get("logs") or {}).items():
                try:
                    merge_logs[stream] = (REPO_ROOT / str(log_path)).read_text(
                        encoding="utf-8", errors="replace"
                    )[-4000:]
                except OSError as error:
                    merge_logs[stream] = f"<unreadable: {error}>"
            self.assertEqual(
                result["status"],
                "completed",
                json.dumps(
                    {
                        "failed_workers": run_plan_detail.get("failed_workers"),
                        "merge_execution": merge_execution,
                        "merge_logs": merge_logs,
                    },
                    ensure_ascii=False,
                    default=str,
                ),
            )
            self.assertEqual(worker_attempts, 2)
            self.assertEqual(
                seen_requests[0]["harness_repair_trace"]["baseline_attempt"]["verified_unsafe_baseline"],
                verified_baseline_ref,
            )
            self.assertEqual(
                seen_requests[1]["harness_repair_trace"]["baseline_attempt"]["verified_unsafe_baseline"],
                verified_baseline_ref,
            )
            self.assertEqual(result["run_plan"]["auto_retry"]["retried_worker_count"], 1)
            exhibit_ref = result["before_after_exhibit_report"]
            exhibit = json.loads((out_root / "summary" / "before-after-exhibit.json").read_text(encoding="utf-8"))
            repairer = exhibit["stage_contracts"]["repairer"]
            self.assertEqual(repairer["status"], "verified")
            self.assertTrue(repairer["verified_baseline_required"])
            self.assertEqual(repairer["verified_baseline"]["path"], verified_baseline_ref["path"])
            self.assertEqual(repairer["verified_baseline"]["sha256"], verified_baseline_ref["sha256"])
            self.assertEqual(repairer["baseline_verification_unit_count"], 1)
            self.assertEqual(repairer["baseline_verification_status"], "verified")
            self.assertEqual(repairer["observed_repair_unit_count"], 1)
            self.assertEqual(repairer["histories"][0]["repair_rounds"], 1)
            self.assertTrue(repairer["histories"][0]["auto_recovered"])
            repair_history = repairer["histories"][0]["repair_history"]
            self.assertTrue(repair_history["verified"])
            self.assertIn("verified", repair_history["statuses"])
            self.assertRegex(repair_history["patch_events_sha256"], r"^[0-9a-f]{64}$")
            self.assertEqual(len(repair_history["rollback_ids"]), 1)
            self.assertTrue((REPO_ROOT / repair_history["patch_events_path"]).exists())
            unit = exhibit["units"][0]
            self.assertEqual(unit["unsafe_reduction"]["reduced_by"], 3)
            self.assertEqual(unit["baseline_verification"], verified_baseline_ref)
            self.assertEqual(unit["repair_history"], repair_history)
            summary_metrics = json.loads((out_root / "summary" / "workflow-metrics.json").read_text(encoding="utf-8"))
            self.assertEqual(summary_metrics["translation_before_after"]["status"], "bound")
            self.assertEqual(
                summary_metrics["translation_before_after"]["units"][0]["baseline_verification"],
                verified_baseline_ref,
            )
            self.assertEqual(summary_metrics["root_cause_counts"], {"final_gate_failed": 1})
            self.assertEqual(summary_metrics["per_unit_statuses"][0]["root_cause_key"], "final_gate_failed")
            self.assertEqual(summary_metrics["per_unit_statuses"][0]["repair_history"], repair_history)
            context_pack = json.loads((REPO_ROOT / result["context_pack"]["path"]).read_text(encoding="utf-8"))
            agent_index = json.loads((REPO_ROOT / result["agent_index"]["path"]).read_text(encoding="utf-8"))
            self.assertEqual(context_pack["attempt_evidence_policy"]["mode"], "baseline_repair_gate")
            self.assertEqual(agent_index["attempt_evidence_policy"]["mode"], "baseline_repair_gate")
            self.assertEqual(
                context_pack["attempt_evidence_policy"]["baseline_attempt"]["verified_unsafe_baseline"],
                verified_baseline_ref,
            )
            self.assertEqual(
                agent_index["attempt_evidence_policy"]["baseline_attempt"]["verified_unsafe_baseline"],
                verified_baseline_ref,
            )
            self.assertEqual(context_pack["entrypoints"]["before_after_exhibit_report"], exhibit_ref["path"])
            self.assertEqual(context_pack["report_artifacts"]["before_after_exhibit_report"], exhibit_ref)
            self.assertEqual(agent_index["reports"]["before_after_exhibit_report"], exhibit_ref)

            worker_attempts = 0
            seen_requests.clear()
            rerun = harness.run_batch_profile(
                profile_path=profile_path,
                run_id="run-before-after-auto-repair",
                out_root=out_root,
                command_runner=fake_runner,
                repo_root=REPO_ROOT,
            )

            self.assertEqual(rerun["status"], "completed")
            self.assertEqual(worker_attempts, 2)
            self.assertEqual(rerun["run_plan"]["auto_retry"]["retried_worker_count"], 1)
            rerun_exhibit = json.loads((out_root / "summary" / "before-after-exhibit.json").read_text(encoding="utf-8"))
            rerun_repairer = rerun_exhibit["stage_contracts"]["repairer"]
            self.assertEqual(rerun_repairer["status"], "verified")
            self.assertEqual(rerun_repairer["histories"][0]["repair_rounds"], 1)
