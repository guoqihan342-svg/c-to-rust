class _OpenCodeAgentHarnessTestPart05:
    def test_write_evaluate_profile_report_updates_context_index_and_ledger(self) -> None:
        with temp_repo_dir() as tmp:
            out_root = Path(tmp) / "competition-out"
            db_path = harness.init_run(
                out_root=out_root,
                run_id="run-evaluate-profile",
                proof_class="local-simulation",
                repo_root=REPO_ROOT,
            )
            verified_baseline_ref = verified_unsafe_baseline_ref_for_tests()
            profile_path = out_root / "profile.json"
            profile_path.write_text(
                json.dumps({"schema_version": 1, "profile_id": "demo-profile"}),
                encoding="utf-8",
            )
            batch_report_path = out_root / "harness" / "batch-profile-report.json"
            batch_report_path.parent.mkdir(parents=True)
            batch_report_path.write_text(
                json.dumps(
                    {
                        "report_kind": "batch-profile-report",
                        "judge_summary": {
                            "harness_architecture": {
                                "context_pack": {"path": "old", "sha256": "old"},
                                "agent_index": {"path": "old", "sha256": "old"},
                            }
                        },
                    },
                    sort_keys=True,
                ),
                encoding="utf-8",
            )
            context_pack_path = out_root / "harness" / "context-pack.json"
            context_pack_path.write_text(
                json.dumps(
                    {
                        "schema_version": 1,
                        "report_kind": "context-pack",
                        "context_pack_id": "run-evaluate-profile-context-pack",
                        "run_id": "run-evaluate-profile",
                        "target_id": "demo",
                        "budget": {"depth": 1, "max_tokens": 20000},
                        "entrypoints": {"primary_report": repo_rel(batch_report_path)},
                        "attempt_evidence_policy": {
                            "baseline_attempt": {
                                "verified_unsafe_baseline": verified_baseline_ref,
                            }
                        },
                    },
                    sort_keys=True,
                ),
                encoding="utf-8",
            )
            agent_index_path = out_root / "harness" / "agent-index.json"
            agent_index_path.write_text(
                json.dumps(
                    {
                        "schema_version": 1,
                        "report_kind": "agent-index",
                        "run_id": "run-evaluate-profile",
                        "target_id": "demo",
                        "reports": {},
                        "attempt_evidence_policy": {
                            "baseline_attempt": {
                                "verified_unsafe_baseline": verified_baseline_ref,
                            }
                        },
                    },
                    sort_keys=True,
                ),
                encoding="utf-8",
            )
            summary_path = out_root / "summary" / "competition-run-summary.json"
            write_worker_summary(
                summary_path,
                "run-evaluate-profile",
                status="passed",
                failed=0,
                semantic_pass=1,
                workflow_metrics=measured_unsafe_worker_metrics("run-evaluate-profile"),
            )
            workflow_metrics_path = summary_path.parent / "workflow-metrics.json"
            summary_payload = json.loads(summary_path.read_text(encoding="utf-8"))
            summary_payload["workflow_metrics"]["path"] = repo_rel(workflow_metrics_path)
            summary_path.write_text(json.dumps(summary_payload, sort_keys=True) + "\n", encoding="utf-8")
            run_plan_report_path = out_root / "harness" / "run-plan-report.json"
            merge_plan_path = out_root / "harness" / "merge-plan.json"
            worker_plan_path = out_root / "harness" / "plans" / "workers.json"
            for path, payload in [
                (run_plan_report_path, {"report_kind": "run-plan-report"}),
                (merge_plan_path, {"report_kind": "merge-plan"}),
                (worker_plan_path, {"report_kind": "worker-plan"}),
            ]:
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(json.dumps(payload, sort_keys=True) + "\n", encoding="utf-8")
            batch_result = {
                "status": "completed",
                "exit_code": 0,
                "run_id": "run-evaluate-profile",
                "out_root": repo_rel(out_root),
                "db_path": repo_rel(db_path),
                "profile_id": "demo-profile",
                "proof_class": "local-simulation",
                "mode": "deterministic",
                "report_path": repo_rel(batch_report_path),
                "plan_path": repo_rel(worker_plan_path),
                "run_plan": {
                    "report_path": repo_rel(run_plan_report_path),
                    "merge_plan": {"path": repo_rel(merge_plan_path)},
                    "merge_execution": {"summary_path": repo_rel(summary_path)},
                },
                "acceptance_boundary": {
                    "semantic_claim_source": "accepted_evidence_binding",
                    "generated_draft_semantic_pass": False,
                },
                "context_pack": {"path": repo_rel(context_pack_path), "sha256": "old"},
                "agent_index": {"path": repo_rel(agent_index_path), "sha256": "old"},
                "attempt_evidence_policy": {
                    "baseline_attempt": {
                        "verified_unsafe_baseline": verified_baseline_ref,
                    }
                },
                "judge_summary": {
                    "entrypoint": "run-batch-profile",
                    "harness_architecture": {"entrypoint": "run-batch-profile"},
                    "core_translation_quality": {
                        "semantic_claim_source": "accepted_evidence_binding",
                        "generated_draft_semantic_pass": False,
                        "semantic_pass_count": 1,
                    },
                },
            }

            result = harness.write_evaluate_profile_report(
                batch_result=batch_result,
                profile_path=profile_path,
                run_id="run-evaluate-profile",
                out_root=out_root,
                repo_root=REPO_ROOT,
            )

            report_path = out_root / "harness" / "evaluate-report.json"
            index_path = out_root / "harness" / "judge-evidence-index.json"
            resume_manifest_path = out_root / "harness" / "resume-manifest.json"
            self.assertTrue(report_path.exists())
            report = json.loads(report_path.read_text(encoding="utf-8"))
            self.assertEqual(result["report_path"], repo_rel(report_path))
            self.assertEqual(report["entrypoint"], "evaluate --profile")
            self.assertEqual(report["judge_summary"]["entrypoint"], "evaluate")
            self.assertEqual(report["judge_summary"]["harness_architecture"]["entrypoint"], "evaluate")
            self.assertEqual(report["batch_profile_report"]["path"], repo_rel(batch_report_path))
            self.assertEqual(report["judge_summary"]["harness_architecture"]["context_pack"], report["context_pack"])
            self.assertEqual(report["judge_summary"]["harness_architecture"]["agent_index"], report["agent_index"])
            self.assert_architecture_contracts(report["judge_summary"]["harness_architecture"]["architecture_contracts"])
            self.assertEqual(report["summary_validation"]["semantic_pass"], 1)
            headline = report["judge_headline"]
            self.assertEqual(headline["report_kind"], "judge-headline")
            self.assertEqual(headline["entrypoint"], "evaluate")
            self.assertEqual(headline["status"], "completed")
            self.assertEqual(headline["semantic_claim_source"], "accepted_evidence_binding")
            self.assertFalse(headline["semantic_gate"])
            self.assertFalse(headline["generated_draft_semantic_pass"])
            self.assertEqual(headline["translation_coverage_numerator"], 0)
            self.assertEqual(headline["context_pack"], report["context_pack"])
            self.assertEqual(headline["agent_index"], report["agent_index"])
            self.assertEqual(report["sidecar_reports"]["judge_evidence_index"]["path"], repo_rel(index_path))
            self.assertNotIn("sha256", report["sidecar_reports"]["judge_evidence_index"])
            self.assertEqual(report["resume_manifest"]["path"], repo_rel(resume_manifest_path))
            self.assertEqual(report["resume_manifest"]["report_kind"], "resume-manifest")
            self.assertEqual(report["resume_manifest"]["status"], "completed")
            self.assertRegex(report["resume_manifest"]["sha256"], r"^[0-9a-f]{64}$")

            context_pack = json.loads(context_pack_path.read_text(encoding="utf-8"))
            self.assertEqual(context_pack["entrypoints"]["primary_report"], repo_rel(report_path))
            self.assertEqual(context_pack["entrypoints"]["evaluate_report"], repo_rel(report_path))
            self.assertEqual(context_pack["entrypoints"]["batch_profile_report"], repo_rel(batch_report_path))
            self.assertEqual(context_pack["entrypoints"]["judge_evidence_index"], repo_rel(index_path))
            self.assertEqual(context_pack["entrypoints"]["resume_manifest"], repo_rel(resume_manifest_path))
            self.assertEqual(context_pack["entrypoints"]["verified_unsafe_baseline"], verified_baseline_ref["path"])
            self.assertEqual(context_pack["report_artifacts"]["verified_unsafe_baseline"], verified_baseline_ref)
            self.assertEqual(
                context_pack["attempt_evidence_policy"]["baseline_attempt"]["verified_unsafe_baseline"],
                verified_baseline_ref,
            )
            self.assert_context_management_contract(context_pack["context_management_contract"])
            agent_index = json.loads(agent_index_path.read_text(encoding="utf-8"))
            self.assertEqual(agent_index["reports"]["evaluate_report"]["path"], repo_rel(report_path))
            self.assertEqual(agent_index["reports"]["batch_profile_report"]["path"], repo_rel(batch_report_path))
            self.assertEqual(agent_index["reports"]["judge_evidence_index"]["path"], repo_rel(index_path))
            self.assertNotIn("sha256", agent_index["reports"]["judge_evidence_index"])
            self.assertEqual(agent_index["reports"]["resume_manifest"]["path"], repo_rel(resume_manifest_path))
            self.assertNotIn("sha256", agent_index["reports"]["resume_manifest"])
            self.assertEqual(agent_index["reports"]["verified_unsafe_baseline"], verified_baseline_ref)
            self.assertEqual(
                agent_index["attempt_evidence_policy"]["baseline_attempt"]["verified_unsafe_baseline"],
                verified_baseline_ref,
            )
            self.assert_agent_coordination_contract(agent_index["agent_coordination_contract"], expected_worker_count=0)
            resume_manifest = json.loads(resume_manifest_path.read_text(encoding="utf-8"))
            self.assertEqual(resume_manifest["report_kind"], "resume-manifest")
            self.assertEqual(resume_manifest["run_id"], "run-evaluate-profile")
            self.assertFalse(resume_manifest["claim_boundary"]["semantic_gate"])
            self.assertFalse(resume_manifest["claim_boundary"]["chat_output_is_evidence"])
            self.assertFalse(resume_manifest["claim_boundary"]["generated_draft_semantic_pass"])
            self.assertEqual(resume_manifest["claim_boundary"]["translation_coverage_numerator"], 0)
            self.assertEqual(resume_manifest["ledger"]["path"], repo_rel(db_path))
            self.assertEqual(resume_manifest["ledger"]["checkpoint_backend"], "sqlite")
            self.assertEqual(resume_manifest["context_pack"]["path"], repo_rel(context_pack_path))
            self.assertEqual(resume_manifest["context_pack"]["sha256"], harness.sha256_file(context_pack_path))
            self.assertEqual(resume_manifest["agent_index"]["path"], repo_rel(agent_index_path))
            self.assertEqual(resume_manifest["agent_index"]["sha256"], harness.sha256_file(agent_index_path))
            self.assertEqual(resume_manifest["expected_judge_evidence_index"], repo_rel(index_path))
            self.assertEqual(resume_manifest["entrypoints"]["verified_unsafe_baseline"], verified_baseline_ref["path"])
            self.assertEqual(resume_manifest["verified_unsafe_baseline"], verified_baseline_ref)
            self.assertEqual(
                resume_manifest["attempt_evidence_policy"]["baseline_attempt"]["verified_unsafe_baseline"],
                verified_baseline_ref,
            )
            self.assertIn("evaluate --profile", resume_manifest["resume_entrypoints"])
            self.assertIn("run-plan --plan", resume_manifest["resume_entrypoints"])
            self.assertIn("run-worker --assignment", resume_manifest["resume_entrypoints"])
            self.assertEqual(resume_manifest["worker_count"], 0)
            batch_report = json.loads(batch_report_path.read_text(encoding="utf-8"))
            self.assertEqual(batch_report["context_pack"], report["context_pack"])
            self.assertEqual(batch_report["agent_index"], report["agent_index"])
            self.assertEqual(
                batch_report["judge_summary"]["harness_architecture"]["context_pack"],
                report["context_pack"],
            )
            self.assertTrue(index_path.exists())
            index = json.loads(index_path.read_text(encoding="utf-8"))
            self.assertEqual(index["report_kind"], "judge-evidence-index")
            self.assertEqual(index["entrypoint"], "evaluate --profile")
            self.assertEqual(index["profile_id"], "demo-profile")
            self.assertFalse(index["claim_boundary"]["index_is_semantic_gate"])
            self.assertFalse(index["claim_boundary"]["generated_draft_semantic_pass"])
            self.assertEqual(index["claim_boundary"]["translation_coverage_numerator"], 0)
            self.assertIn("does not add a semantic acceptance gate", index["claim_boundary"]["boundary"])
            self.assertEqual(index["harness_architecture"]["entrypoint"], "evaluate")
            self.assert_architecture_contracts(index["harness_architecture"]["architecture_contracts"])
            self.assertEqual(index["core_translation_quality"]["semantic_pass_count"], 1)
            self.assertEqual(index["judge_headline"], report["judge_headline"])
            artifact_refs = index["evidence_artifact_refs"]
            self.assertNotIn("judge_evidence_index", artifact_refs)
            self.assertNotIn("context_management_contract", artifact_refs)
            self.assertNotIn("agent_coordination_contract", artifact_refs)
            self.assertEqual(artifact_refs["evaluate_report"]["path"], repo_rel(report_path))
            self.assertEqual(artifact_refs["evaluate_report"]["sha256"], harness.sha256_file(report_path))
            self.assertEqual(artifact_refs["batch_profile_report"]["path"], repo_rel(batch_report_path))
            self.assertEqual(artifact_refs["context_pack"]["path"], report["context_pack"]["path"])
            self.assertEqual(artifact_refs["context_pack"]["sha256"], harness.sha256_file(context_pack_path))
            self.assertEqual(artifact_refs["agent_index"]["path"], report["agent_index"]["path"])
            self.assertEqual(artifact_refs["agent_index"]["sha256"], harness.sha256_file(agent_index_path))
            self.assertEqual(artifact_refs["resume_manifest"]["path"], report["resume_manifest"]["path"])
            self.assertEqual(artifact_refs["resume_manifest"]["sha256"], harness.sha256_file(resume_manifest_path))
            self.assertEqual(artifact_refs["verified_unsafe_baseline"]["path"], verified_baseline_ref["path"])
            self.assertEqual(artifact_refs["verified_unsafe_baseline"]["sha256"], verified_baseline_ref["sha256"])
            self.assertEqual(
                artifact_refs["verified_unsafe_baseline"]["semantic_claim_source"],
                "verified_unsafe_baseline_gates",
            )
            self.assertEqual(artifact_refs["competition_run_summary"]["path"], repo_rel(summary_path))
            self.assertEqual(artifact_refs["workflow_metrics"]["path"], repo_rel(workflow_metrics_path))
            self.assertEqual(
                artifact_refs["workflow_metrics"]["sha256"],
                summary_payload["workflow_metrics"]["sha256"],
            )
            self.assertEqual(artifact_refs["run_plan_report"]["path"], repo_rel(run_plan_report_path))
            self.assertEqual(artifact_refs["merge_plan"]["path"], repo_rel(merge_plan_path))
            self.assertEqual(artifact_refs["worker_plan"]["path"], repo_rel(worker_plan_path))
            self.assertIn("--summary " + repo_rel(summary_path), index["reproduction_commands"]["summary_validation"])

            artifact_rows = fetch_rows(
                db_path,
                "select kind, repo_rel_path, semantic_role from artifacts where kind in ('evaluate-report', 'context-pack', 'agent-index', 'judge-evidence-index', 'resume-manifest') order by kind",
            )
            self.assertEqual(
                artifact_rows,
                [
                    ("agent-index", repo_rel(agent_index_path), "agent-index"),
                    ("context-pack", repo_rel(context_pack_path), "agent-context-pack"),
                    ("evaluate-report", repo_rel(report_path), "evaluate-report"),
                    ("judge-evidence-index", repo_rel(index_path), "judge-evidence-index"),
                    ("resume-manifest", repo_rel(resume_manifest_path), "resume-manifest"),
                ],
            )
            event_rows = fetch_rows(
                db_path,
                "select event_type from events where event_type in ('evaluate_profile_context_refs_updated', 'evaluate_profile_executed', 'judge_evidence_index_written', 'resume_manifest_written') order by event_type",
            )
            self.assertEqual(
                event_rows,
                [
                    ("evaluate_profile_context_refs_updated",),
                    ("evaluate_profile_executed",),
                    ("judge_evidence_index_written",),
                    ("resume_manifest_written",),
                ],
            )

    def test_write_judge_evidence_index_records_opencode_runtime_without_semantic_gate(self) -> None:
        with temp_repo_dir() as tmp:
            out_root = Path(tmp) / "competition-out"
            harness_dir = out_root / "harness"
            harness_dir.mkdir(parents=True, exist_ok=True)
            profile_path = out_root / "profile.json"
            evaluate_report_path = harness_dir / "evaluate-report.json"
            run_plan_report_path = harness_dir / "run-plan-report.json"
            worker_plan_path = harness_dir / "worker-plan.json"
            preflight_report = harness_dir / "opencode-preflight-report.json"
            handoff_a = out_root / "workers" / "worker-a" / "harness" / "opencode-handoff-contract.json"
            handoff_b = out_root / "workers" / "worker-b" / "harness" / "opencode-handoff-contract.json"
            session_a = out_root / "workers" / "worker-a" / "logs" / "opencode-session-evidence.json"
            session_b = out_root / "workers" / "worker-b" / "logs" / "opencode-session-evidence.json"
            safety_attempt_a = (
                out_root
                / "workers"
                / "worker-a"
                / "harness"
                / "opencode-safety-transform-attempt-1.json"
            )
            summary_a = out_root / "workers" / "worker-a" / "summary" / "competition-run-summary.json"
            summary_b = out_root / "workers" / "worker-b" / "summary" / "competition-run-summary.json"
            worker_report_a = out_root / "workers" / "worker-a" / "harness" / "run-worker-report.json"
            worker_report_b = out_root / "workers" / "worker-b" / "harness" / "run-worker-report.json"
            stdout_a = out_root / "workers" / "worker-a" / "logs" / "harness-worker-executor.stdout.log"
            stderr_a = out_root / "workers" / "worker-a" / "logs" / "harness-worker-executor.stderr.log"
            stdout_b = out_root / "workers" / "worker-b" / "logs" / "harness-worker-executor.stdout.log"
            stderr_b = out_root / "workers" / "worker-b" / "logs" / "harness-worker-executor.stderr.log"
            for path, payload in [
                (profile_path, {"schema_version": 1, "profile_id": "demo-opencode"}),
                (evaluate_report_path, {"report_kind": "evaluate-report"}),
                (run_plan_report_path, {"report_kind": "run-plan-report"}),
                (worker_plan_path, {"report_kind": "worker-plan"}),
                (preflight_report, {"report_kind": "opencode-preflight-report", "status": "passed"}),
                (handoff_a, {"report_kind": "opencode-handoff-contract", "worker_id": "worker-a"}),
                (handoff_b, {"report_kind": "opencode-handoff-contract", "worker_id": "worker-b"}),
                (session_a, {"report_kind": "opencode-session-evidence", "worker_id": "worker-a"}),
                (session_b, {"report_kind": "opencode-session-evidence", "worker_id": "worker-b"}),
                (
                    safety_attempt_a,
                    {
                        "report_kind": "opencode-safety-transform-attempt",
                        "worker_id": "worker-a",
                        "attempt": 1,
                        "semantic_gate": False,
                        "translation_coverage_numerator": 0,
                    },
                ),
                (summary_a, {"report_kind": "competition-run-summary", "worker_id": "worker-a"}),
                (summary_b, {"report_kind": "competition-run-summary", "worker_id": "worker-b"}),
                (worker_report_a, {"report_kind": "run-worker-report", "worker_id": "worker-a"}),
                (worker_report_b, {"report_kind": "run-worker-report", "worker_id": "worker-b"}),
                (stdout_a, {"log": "stdout-a"}),
                (stderr_a, {"log": "stderr-a"}),
                (stdout_b, {"log": "stdout-b"}),
                (stderr_b, {"log": "stderr-b"}),
            ]:
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(json.dumps(payload, sort_keys=True) + "\n", encoding="utf-8")

            preflight_binding = {
                "path": repo_rel(preflight_report),
                "sha256": harness.sha256_file(preflight_report),
                "status": "passed",
                "run_id": "run-opencode-index",
                "contract_status": "executed",
            }
            handoff_a_binding = {"path": repo_rel(handoff_a), "sha256": harness.sha256_file(handoff_a)}
            handoff_b_binding = {"path": repo_rel(handoff_b), "sha256": harness.sha256_file(handoff_b)}
            session_a_binding = {"path": repo_rel(session_a), "sha256": harness.sha256_file(session_a)}
            session_b_binding = {"path": repo_rel(session_b), "sha256": harness.sha256_file(session_b)}
            safety_attempt_a_binding = {
                "path": repo_rel(safety_attempt_a),
                "sha256": harness.sha256_file(safety_attempt_a),
            }
            batch_result = {
                "status": "completed",
                "exit_code": 0,
                "profile_id": "demo-opencode",
                "proof_class": "local-simulation",
                "mode": "opencode",
                "plan_path": repo_rel(worker_plan_path),
                "opencode_preflight_report": preflight_binding,
                "run_plan": {
                    "report_path": repo_rel(run_plan_report_path),
                    "opencode_preflight_report": preflight_binding,
                    "workers": [
                        {
                            "worker_id": "worker-a",
                            "summary_path": repo_rel(summary_a),
                            "report_path": repo_rel(worker_report_a),
                            "logs": {"stdout": repo_rel(stdout_a), "stderr": repo_rel(stderr_a)},
                            "handoff_contract": handoff_a_binding,
                            "opencode_session_evidence": session_a_binding,
                            "opencode_safety_transform_attempt": safety_attempt_a_binding,
                            "opencode_preflight_report": preflight_binding,
                            "final_decision": {"status": "accepted", "reason": "worker_summary_passed"},
                            "opencode_contract_verification": {"status": "executed", "matched_command": "cmd-a"},
                        },
                        {
                            "worker_id": "worker-b",
                            "summary_path": repo_rel(summary_b),
                            "report_path": repo_rel(worker_report_b),
                            "logs": {"stdout": repo_rel(stdout_b), "stderr": repo_rel(stderr_b)},
                            "handoff_contract": handoff_b_binding,
                            "opencode_session_evidence": session_b_binding,
                            "opencode_preflight_report": preflight_binding,
                            "final_decision": {"status": "accepted", "reason": "worker_summary_passed"},
                            "opencode_contract_verification": {"status": "executed", "matched_command": "cmd-b"},
                        },
                    ],
                },
            }
            evaluate_report = {
                "status": "completed",
                "exit_code": 0,
                "profile_id": "demo-opencode",
                "proof_class": "local-simulation",
                "mode": "opencode",
                "opencode_preflight_report": preflight_binding,
                "judge_summary": {
                    "harness_architecture": {"entrypoint": "evaluate"},
                    "core_translation_quality": {
                        "semantic_claim_source": "accepted_evidence_binding",
                        "generated_draft_semantic_pass": False,
                    },
                },
            }

            result = harness.write_judge_evidence_index(
                evaluate_report=evaluate_report,
                evaluate_report_path=evaluate_report_path,
                batch_result=batch_result,
                profile_path=profile_path,
                run_id="run-opencode-index",
                out_root=out_root,
                repo_root=REPO_ROOT,
            )

            payload = result["payload"]
            runtime = payload["opencode_agent_runtime"]
            self.assertFalse(runtime["chat_output_is_evidence"])
            self.assertFalse(runtime["semantic_gate"])
            self.assertEqual(runtime["opencode_preflight_report"], preflight_binding)
            self.assertEqual(runtime["worker_count"], 2)
            self.assertEqual(runtime["contract_status_counts"], {"executed": 2})
            self.assertTrue(runtime["all_contracts_executed"])
            self.assertEqual(runtime["failed_or_missing_contract_workers"], [])
            self.assertEqual([worker["worker_id"] for worker in runtime["workers"]], ["worker-a", "worker-b"])
            self.assertEqual(
                [worker["contract_verification_status"] for worker in runtime["workers"]],
                ["executed", "executed"],
            )
            self.assertFalse(runtime["workers"][0]["chat_output_is_evidence"])
            self.assertFalse(runtime["workers"][0]["semantic_gate"])
            self.assertEqual(runtime["workers"][0]["handoff_contract"], handoff_a_binding)
            self.assertEqual(runtime["workers"][0]["opencode_session_evidence"], session_a_binding)
            self.assertEqual(runtime["workers"][0]["summary"], {"path": repo_rel(summary_a), "sha256": harness.sha256_file(summary_a)})
            self.assertEqual(
                runtime["workers"][0]["worker_report"],
                {"path": repo_rel(worker_report_a), "sha256": harness.sha256_file(worker_report_a)},
            )
            self.assertEqual(
                runtime["workers"][0]["logs"]["stdout"],
                {"path": repo_rel(stdout_a), "sha256": harness.sha256_file(stdout_a)},
            )
            self.assertEqual(
                runtime["workers"][0]["logs"]["stderr"],
                {"path": repo_rel(stderr_a), "sha256": harness.sha256_file(stderr_a)},
            )
            self.assertEqual(runtime["workers"][0]["final_decision"]["status"], "accepted")
            self.assertEqual(payload["evidence_artifact_refs"]["opencode_preflight_report"], preflight_binding)
            self.assertEqual(
                runtime["workers"][0]["opencode_safety_transform_attempt"],
                safety_attempt_a_binding,
            )
            self.assertEqual(
                payload["evidence_artifact_refs"]["opencode_safety_transform_attempt"],
                safety_attempt_a_binding,
            )
            self.assertFalse(payload["claim_boundary"]["index_is_semantic_gate"])

    def test_plan_source_file_cli_dispatches_planner_flags(self) -> None:
        argv = [
            "opencode_agent_harness.py",
            "plan-source-file",
            "--db",
            "target/competition-out/state/opencode-agent-harness.sqlite3",
            "--run-id",
            "run-test",
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
            "--source-commit",
            "f9d0421315c564fb890a1b14eee77b290e0d7bbe",
            "--require-source-commit",
            "f9d0421315c564fb890a1b14eee77b290e0d7bbe",
            "--slice-spec",
            "validation/slice-specs/flashdb-real-fdb-calc-crc32.json",
            "--compiler-command-source",
            "compile_commands.json",
            "--include-path",
            "inc",
            "--define",
            "FDB_USING_KVDB",
            "--out-root",
            "target/competition-out",
            "--slice-id-prefix",
            "real-fdb-utils",
            "--worker-prefix",
            "flashdb-worker",
            "--limit",
            "2",
        ]

        with patch("sys.argv", argv), patch("sys.stdout", io.StringIO()), patch.object(
            harness,
            "plan_source_file",
            return_value={"status": "planned"},
        ) as planner:
            self.assertEqual(harness.main(), 0)

        planner.assert_called_once()
        self.assertEqual(planner.call_args.kwargs["target_id"], "flashdb")
        self.assertEqual(planner.call_args.kwargs["source_repository"], "https://gitcode.com/xwxf/FlashDB.git")
        self.assertEqual(planner.call_args.kwargs["source_branch"], "competition")
        self.assertEqual(
            planner.call_args.kwargs["require_source_commit"],
            "f9d0421315c564fb890a1b14eee77b290e0d7bbe",
        )
        self.assertEqual(planner.call_args.kwargs["include_paths"], ["inc"])
        self.assertEqual(planner.call_args.kwargs["defines"], ["FDB_USING_KVDB"])
        self.assertEqual(planner.call_args.kwargs["slice_id_prefix"], "real-fdb-utils")
        self.assertEqual(planner.call_args.kwargs["worker_prefix"], "flashdb-worker")
        self.assertEqual(planner.call_args.kwargs["limit"], 2)
        self.assertEqual(planner.call_args.kwargs["functions"], ["fdb_calc_crc32"])
        self.assertEqual(
            planner.call_args.kwargs["slice_specs"],
            ["validation/slice-specs/flashdb-real-fdb-calc-crc32.json"],
        )

    def test_run_plan_cli_dispatches_batch_flags(self) -> None:
        argv = [
            "opencode_agent_harness.py",
            "run-plan",
            "--db",
            "target/competition-out/state/opencode-agent-harness.sqlite3",
            "--run-id",
            "run-test",
            "--plan",
            "target/competition-out/harness/plans/flashdb-fdb-utils-workers.json",
            "--out-root",
            "target/competition-out",
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
            "--execute-merge",
            "--auto-retry",
            "--max-workers",
            "3",
            "--timeout-seconds",
            "42",
        ]

        with patch("sys.argv", argv), patch("sys.stdout", io.StringIO()) as stdout, patch.object(
            harness,
            "run_plan",
            return_value={"status": "failed", "exit_code": 1},
        ) as runner:
            exit_code = harness.main()

        self.assertEqual(exit_code, 1)
        payload = json.loads(stdout.getvalue())
        self.assertEqual(payload["status"], "failed")
        runner.assert_called_once()
        self.assertEqual(runner.call_args.kwargs["run_id"], "run-test")
        self.assertEqual(
            runner.call_args.kwargs["plan_path"],
            Path("target/competition-out/harness/plans/flashdb-fdb-utils-workers.json"),
        )
        self.assertEqual(runner.call_args.kwargs["proof_class"], "local-simulation")
        self.assertEqual(runner.call_args.kwargs["mode"], "opencode")
        self.assertEqual(runner.call_args.kwargs["opencode_model"], "GLM-5.1")
        self.assertEqual(runner.call_args.kwargs["opencode_agent"], "c2rust-migrator")
        self.assertTrue(runner.call_args.kwargs["opencode_skip_permissions"])
        self.assertTrue(runner.call_args.kwargs["execute_merge"])
        self.assertTrue(runner.call_args.kwargs["auto_retry"])
        self.assertEqual(runner.call_args.kwargs["max_workers"], 3)
        self.assertEqual(runner.call_args.kwargs["timeout_seconds"], 42)

    def test_plan_source_file_direct_script_cli_runs_from_repo_root(self) -> None:
        with temp_repo_dir() as tmp:
            out_root = Path(tmp) / "competition-out"
            source_root = Path(tmp) / "source"
            source_file = source_root / "src" / "demo.c"
            source_file.parent.mkdir(parents=True)
            source_file.write_text("int add_one(int value) { return value + 1; }\n", encoding="utf-8")
            db_path = harness.init_run(
                out_root=out_root,
                run_id="run-test",
                proof_class="local-simulation",
                repo_root=REPO_ROOT,
            )

            completed = subprocess.run(
                [
                    sys.executable,
                    "validation/tools/opencode_agent_harness.py",
                    "plan-source-file",
                    "--db",
                    repo_rel(db_path),
                    "--run-id",
                    "run-test",
                    "--target-id",
                    "demo",
                    "--source-repo-root",
                    repo_rel(source_root),
                    "--source-file",
                    "src/demo.c",
                    "--source-commit",
                    "abc123",
                    "--out-root",
                    repo_rel(out_root),
                    "--slice-id-prefix",
                    "demo",
                    "--limit",
                    "1",
                ],
                cwd=REPO_ROOT,
                text=True,
                capture_output=True,
                check=False,
            )

            self.assertEqual(completed.returncode, 0, completed.stderr + completed.stdout)
            payload = json.loads(completed.stdout)
            self.assertEqual(payload["status"], "planned")
            self.assertEqual(payload["units"][0]["function"], "add_one")

    def test_record_worker_summary_indexes_artifact_and_merge_plan(self) -> None:
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
            worker_request = json.loads(request_path.read_text(encoding="utf-8"))
            summary_path = out_root / "workers" / "worker-a" / "summary" / "competition-run-summary.json"
            summary_path.parent.mkdir(parents=True, exist_ok=True)
            summary_path.write_text(
                json.dumps(
                    {
                        "schema_version": 1,
                        "run_id": worker_request["run_id"],
                        "proof_class": "local-simulation",
                        "final_gate": {"status": "passed", "validator": "validate_auto_translation_evidence.py --require-semantic-pass"},
                        "slices": {"attempted": 1, "typed_ir_generated": 1, "compiled": 1, "semantic_pass": 1, "refused": 0, "blocked": 0, "failed": 0},
                    },
                    sort_keys=True,
                )
                + "\n",
                encoding="utf-8",
            )

            harness.record_worker_summary(
                db_path=db_path,
                run_id="run-test",
                worker_id="worker-a",
                summary_path=summary_path,
                repo_root=REPO_ROOT,
            )
            merge_plan = harness.write_merge_plan(
                db_path=db_path,
                run_id="run-test",
                out_root=out_root,
                proof_class="local-simulation",
                repo_root=REPO_ROOT,
            )

            self.assertEqual(
                merge_plan["worker_summaries"],
                [repo_rel(summary_path)],
            )
            expected_merge_prefix = harness.portable_python_script_argv("validation/tools/run_competition.py")
            self.assertEqual(merge_plan["argv"][: len(expected_merge_prefix)], expected_merge_prefix)
            self.assertIn("--worker-summary", merge_plan["argv"])
            self.assertIn("--run-id", merge_plan["argv"])
            run_id_idx = merge_plan["argv"].index("--run-id")
            self.assertEqual(merge_plan["argv"][run_id_idx + 1], "run-test")
            artifact_rows = fetch_rows(db_path, "select kind, repo_rel_path, semantic_role from artifacts")
            self.assertEqual(artifact_rows, [("competition-run-summary", repo_rel(summary_path), "run-summary")])

    def test_record_worker_summary_rejects_summary_run_id_mismatch_with_assignment(self) -> None:
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
            worker_request = json.loads(request_path.read_text(encoding="utf-8"))
            summary_path = out_root / "workers" / "worker-a" / "summary" / "competition-run-summary.json"
            write_worker_summary(
                summary_path,
                "stale-run",
                status="passed",
                failed=0,
                semantic_pass=1,
                workflow_metrics=measured_unsafe_worker_metrics("stale-run"),
            )

            with self.assertRaisesRegex(
                SystemExit,
                f"worker summary run_id stale-run does not match assigned worker run_id {worker_request['run_id']}",
            ):
                harness.record_worker_summary(
                    db_path=db_path,
                    run_id="run-test",
                    worker_id="worker-a",
                    summary_path=summary_path,
                    repo_root=REPO_ROOT,
                )

            artifact_rows = fetch_rows(db_path, "select kind, repo_rel_path from artifacts")
            self.assertEqual(artifact_rows, [])

    def test_record_artifact_conflict_refreshes_identity_metadata(self) -> None:
        with temp_repo_dir() as tmp:
            out_root = Path(tmp) / "competition-out"
            db_path = harness.init_run(
                out_root=out_root,
                run_id="run-old",
                proof_class="local-simulation",
                repo_root=REPO_ROOT,
            )
            artifact_path = out_root / "harness" / "shared.json"
            write_json(artifact_path, {"version": 1})
            connection = harness.connect(db_path)
            try:
                harness.record_artifact(
                    connection,
                    run_id="run-old",
                    worker_id="worker-a",
                    kind="old-kind",
                    path=artifact_path,
                    status="old",
                    semantic_role="old-role",
                    payload={"version": 1},
                    repo_root=REPO_ROOT,
                )
                connection.commit()

                write_json(artifact_path, {"version": 2})
                harness.record_artifact(
                    connection,
                    run_id="run-new",
                    worker_id="planner",
                    kind="context-pack",
                    path=artifact_path,
                    status="completed",
                    semantic_role="agent-context-pack",
                    payload={"version": 2},
                    repo_root=REPO_ROOT,
                )
                connection.commit()
            finally:
                connection.close()

            artifact_rows = fetch_rows(
                db_path,
                """
                select run_id, agent_id, kind, semantic_role, status
                from artifacts
                where repo_rel_path=?
                """,
                (repo_rel(artifact_path),),
            )
            self.assertEqual(
                artifact_rows,
                [("run-new", "planner", "context-pack", "agent-context-pack", "completed")],
            )

    def test_context_pack_conflict_refreshes_sqlite_metadata(self) -> None:
        with temp_repo_dir() as tmp:
            out_root = Path(tmp) / "competition-out"
            db_path = harness.init_run(
                out_root=out_root,
                run_id="run-context",
                proof_class="local-simulation",
                repo_root=REPO_ROOT,
            )
            primary_report = out_root / "harness" / "batch-profile-report.json"
            primary_report.parent.mkdir(parents=True, exist_ok=True)
            primary_report.write_text("{}\n", encoding="utf-8")
            plan = {
                "planning_mode": "source_file",
                "plan_path": repo_rel(out_root / "harness" / "plans" / "workers.json"),
                "units": [],
            }
            run_result = {
                "status": "passed",
                "workers": [],
                "parallelism": {"max_workers": 0, "effective_workers": 0},
                "graph": {"checkpoint_backend": "sqlite"},
            }
            harness.write_context_pack_and_agent_index(
                db_path=db_path,
                run_id="run-context",
                target_id="old-target",
                proof_class="local-simulation",
                mode="deterministic",
                out_root=out_root,
                plan=plan,
                run_result=run_result,
                primary_report_path=primary_report,
                report_entrypoint="batch_profile_report",
                repo_root=REPO_ROOT,
            )
            context_ref = harness.write_context_pack_and_agent_index(
                db_path=db_path,
                run_id="run-context",
                target_id="new-target",
                proof_class="local-simulation",
                mode="deterministic",
                out_root=out_root,
                plan=plan,
                run_result=run_result,
                primary_report_path=primary_report,
                report_entrypoint="batch_profile_report",
                repo_root=REPO_ROOT,
            )["context_pack"]

            context_rows = fetch_rows(
                db_path,
                """
                select run_id, target_id, artifact_path, artifact_sha256
                from context_packs
                where context_pack_id=?
                """,
                ("run-context-context-pack",),
            )
            self.assertEqual(
                context_rows,
                [("run-context", "new-target", context_ref["path"], context_ref["sha256"])],
            )

    def test_record_worker_summary_rejects_unassigned_summary_path(self) -> None:
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
            summary_path = out_root / "workers" / "worker-b" / "summary" / "competition-run-summary.json"
            write_worker_summary(summary_path, "run-worker-b", status="passed", failed=0, semantic_pass=1)

            with self.assertRaisesRegex(SystemExit, "worker summary path .* does not match assigned"):
                harness.record_worker_summary(
                    db_path=db_path,
                    run_id="run-test",
                    worker_id="worker-a",
                    summary_path=summary_path,
                    repo_root=REPO_ROOT,
                )
