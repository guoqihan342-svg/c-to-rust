class _JudgeEntrypointsValidatorTestsPart02:
    def test_judge_evidence_index_requires_opencode_graph_contract(self) -> None:
        payload = valid_opencode_judge_index_payload()
        payload["harness_architecture"]["graph_runtime"] = "plain-runtime"

        with self.assertRaisesRegex(ValueError, "judge_evidence_index.harness_architecture.graph_runtime must be opencode-harness-langgraph-inspired"):
            validator.validate_judge_evidence_index_contract(payload, path_text="target/out/harness/judge-evidence-index.json")

    def test_judge_evidence_index_requires_all_graph_nodes(self) -> None:
        payload = valid_opencode_judge_index_payload()
        payload["harness_architecture"]["graph_nodes"].remove("repair_retry")

        with self.assertRaisesRegex(ValueError, "graph_nodes missing required nodes: \\['repair_retry'\\]"):
            validator.validate_judge_evidence_index_contract(payload, path_text="target/out/harness/judge-evidence-index.json")

    def test_judge_evidence_index_rejects_unexpected_graph_nodes(self) -> None:
        payload = valid_opencode_judge_index_payload()
        payload["harness_architecture"]["graph_nodes"].append("unreviewed_stage")

        with self.assertRaisesRegex(
            ValueError,
            "judge_evidence_index.harness_architecture.graph_nodes must be "
            "\\['load_plan', 'fanout_workers', 'worker', 'repair_retry', 'merge', 'report'\\]",
        ):
            validator.validate_judge_evidence_index_contract(payload, path_text="target/out/harness/judge-evidence-index.json")

    def test_judge_evidence_index_requires_retry_checkpoint_and_round_cap(self) -> None:
        payload = valid_opencode_judge_index_payload()
        payload["harness_architecture"]["retry_policy"]["checkpoint"] = "sqlite"

        with self.assertRaisesRegex(ValueError, "retry_policy.checkpoint must be repair_hints"):
            validator.validate_judge_evidence_index_contract(payload, path_text="target/out/harness/judge-evidence-index.json")

        payload = valid_opencode_judge_index_payload()
        payload["harness_architecture"]["retry_policy"]["round_cap"] = 4

        with self.assertRaisesRegex(ValueError, "retry_policy.round_cap must be 5"):
            validator.validate_judge_evidence_index_contract(payload, path_text="target/out/harness/judge-evidence-index.json")

    def test_judge_evidence_index_refs_must_cover_expected_artifacts(self) -> None:
        payload = valid_opencode_judge_index_payload()
        del payload["evidence_artifact_refs"]["worker_plan"]
        expected_artifacts = {
            "competition_summary": "target/out/summary/competition-run-summary.json",
            "workflow_metrics": "target/out/summary/workflow-metrics.json",
            "worker_plan": "target/out/harness/plans/workers.json",
        }

        with self.assertRaisesRegex(ValueError, "judge_evidence_index.evidence_artifact_refs missing expected artifacts: \\['worker_plan'\\]"):
            validator.validate_judge_evidence_index_contract(
                payload,
                path_text="target/out/harness/judge-evidence-index.json",
                expected_artifacts=expected_artifacts,
            )

    def test_judge_evidence_index_rejects_unexpected_artifact_refs(self) -> None:
        payload = valid_opencode_judge_index_payload()
        payload["evidence_artifact_refs"]["demo_claim"] = artifact_ref(
            "target/out/summary/demo-claim.json",
            "8",
        )

        with self.assertRaisesRegex(
            ValueError,
            "judge_evidence_index.evidence_artifact_refs unexpected refs: \\['demo_claim'\\]",
        ):
            validator.validate_judge_evidence_index_contract(
                payload,
                path_text="target/out/harness/judge-evidence-index.json",
            )

    def test_judge_evidence_index_allows_review_checklist_artifact_refs_from_producer(self) -> None:
        payload = valid_deterministic_judge_index_payload()
        payload["evidence_artifact_refs"]["milestone_review_checklist"] = artifact_ref(
            "target/out/summary/milestone-review-checklist.json",
            "8",
        )
        payload["evidence_artifact_refs"]["internal_review_checklist"] = artifact_ref(
            "config/competition-env/review-checklists/flashdb-harness-internal-review.json",
            "9",
        )
        payload["evidence_artifact_refs"]["internal_review_checklist_2"] = artifact_ref(
            "config/competition-env/review-checklists/flashdb-harness-internal-review-2.json",
            "a",
        )

        result = validator.validate_judge_evidence_index_contract(
            payload,
            path_text="target/out/harness/judge-evidence-index.json",
        )

        self.assertEqual(result["evidence_artifact_refs"]["status"], "passed")
        self.assertIn("milestone_review_checklist", result["evidence_artifact_refs"]["refs"])
        self.assertIn("internal_review_checklist", result["evidence_artifact_refs"]["refs"])
        self.assertIn("internal_review_checklist_2", result["evidence_artifact_refs"]["refs"])

    def test_judge_evidence_index_requires_architecture_context_and_agent_refs_when_expected(self) -> None:
        payload = valid_deterministic_judge_index_payload()
        payload["evidence_artifact_refs"]["context_pack"] = artifact_ref("target/out/harness/context-pack.json", "6")
        payload["evidence_artifact_refs"]["agent_index"] = artifact_ref("target/out/harness/agent-index.json", "7")
        expected_artifacts = {
            "competition_summary": "target/out/summary/competition-run-summary.json",
            "workflow_metrics": "target/out/summary/workflow-metrics.json",
            "worker_plan": "target/out/harness/plans/workers.json",
            "context_pack": "target/out/harness/context-pack.json",
            "agent_index": "target/out/harness/agent-index.json",
        }

        with self.assertRaisesRegex(
            ValueError,
            "judge_evidence_index.harness_architecture.context_pack is required when expected_artifacts.context_pack is declared",
        ):
            validator.validate_judge_evidence_index_contract(
                payload,
                path_text="target/out/harness/judge-evidence-index.json",
                expected_artifacts=expected_artifacts,
            )

    def test_judge_evidence_index_requires_architecture_agent_ref_when_context_ref_is_present(self) -> None:
        payload = valid_deterministic_judge_index_payload()
        context_ref = artifact_ref("target/out/harness/context-pack.json", "6")
        payload["evidence_artifact_refs"]["context_pack"] = context_ref
        payload["evidence_artifact_refs"]["agent_index"] = artifact_ref("target/out/harness/agent-index.json", "7")
        payload["harness_architecture"]["context_pack"] = context_ref
        expected_artifacts = {
            "competition_summary": "target/out/summary/competition-run-summary.json",
            "workflow_metrics": "target/out/summary/workflow-metrics.json",
            "worker_plan": "target/out/harness/plans/workers.json",
            "context_pack": "target/out/harness/context-pack.json",
            "agent_index": "target/out/harness/agent-index.json",
        }

        with self.assertRaisesRegex(
            ValueError,
            "judge_evidence_index.harness_architecture.agent_index is required when expected_artifacts.agent_index is declared",
        ):
            validator.validate_judge_evidence_index_contract(
                payload,
                path_text="target/out/harness/judge-evidence-index.json",
                expected_artifacts=expected_artifacts,
            )

    def test_judge_evidence_index_expected_artifacts_reject_drive_prefix(self) -> None:
        payload = valid_opencode_judge_index_payload()

        with self.assertRaisesRegex(
            ValueError,
            "expected_artifacts.competition_summary: path must not use a drive prefix",
        ):
            validator.validate_judge_evidence_index_contract(
                payload,
                path_text="target/out/harness/judge-evidence-index.json",
                expected_artifacts={"competition_summary": "F:/agent/local/competition-run-summary.json"},
            )

    def test_judge_evidence_index_requires_opencode_preflight_ref(self) -> None:
        payload = valid_opencode_judge_index_payload()
        del payload["evidence_artifact_refs"]["opencode_preflight_report"]

        with self.assertRaisesRegex(ValueError, "missing required OpenCode ref: opencode_preflight_report"):
            validator.validate_judge_evidence_index_contract(
                payload,
                path_text="target/out/harness/judge-evidence-index.json",
            )

    def test_judge_evidence_index_preflight_ref_must_match_runtime(self) -> None:
        payload = valid_opencode_judge_index_payload()
        payload["evidence_artifact_refs"]["opencode_preflight_report"]["sha256"] = "7" * 64

        with self.assertRaisesRegex(ValueError, "evidence_artifact_refs.opencode_preflight_report must match path and sha256"):
            validator.validate_judge_evidence_index_contract(
                payload,
                path_text="target/out/harness/judge-evidence-index.json",
            )

    def test_judge_evidence_index_preflight_run_id_must_match_runtime(self) -> None:
        payload = valid_opencode_judge_index_payload()
        payload["opencode_agent_runtime"]["workers"][0]["opencode_preflight_report"]["run_id"] = "stale-run"

        with self.assertRaisesRegex(
            ValueError,
            "opencode_agent_runtime.workers\\[0\\].opencode_preflight_report.run_id must match opencode_agent_runtime.opencode_preflight_report",
        ):
            validator.validate_judge_evidence_index_contract(
                payload,
                path_text="target/out/harness/judge-evidence-index.json",
            )

    def test_judge_evidence_index_requires_opencode_launch_policy_binding(self) -> None:
        payload = valid_opencode_judge_index_payload()
        del payload["opencode_agent_runtime"]["opencode_preflight_report"]["launch_policy"]

        with self.assertRaisesRegex(ValueError, "opencode_agent_runtime.opencode_preflight_report.launch_policy must be an object"):
            validator.validate_judge_evidence_index_contract(
                payload,
                path_text="target/out/harness/judge-evidence-index.json",
            )

    def test_judge_evidence_index_rejects_opencode_launch_policy_drift_from_profile_ref(self) -> None:
        temp_dir = Path(tempfile.mkdtemp(prefix="judge-opencode-profile-drift-", dir=REPO_ROOT / "target"))
        payload = valid_opencode_judge_index_payload()
        profile_policy = opencode_launch_policy()
        profile_policy["opencode_skip_permissions"] = True
        profile_policy["auto_retry"] = True
        materialize_opencode_judge_index_artifacts(
            payload,
            temp_dir / "out",
            profile_payload={
                "schema_version": 1,
                "profile_id": "opencode-profile-drift",
                "mode": "opencode",
                **profile_policy,
            },
        )

        with self.assertRaisesRegex(
            ValueError,
            "opencode_agent_runtime.opencode_preflight_report.launch_policy must match profile launch policy",
        ):
            validator.validate_judge_evidence_index_contract(
                payload,
                path_text=repo_relative(temp_dir / "out" / "harness" / "judge-evidence-index.json"),
                repo_root=REPO_ROOT,
            )

    def test_judge_evidence_index_rejects_preflight_model_probe_argv_drift(self) -> None:
        temp_dir = Path(tempfile.mkdtemp(prefix="judge-opencode-model-argv-", dir=REPO_ROOT / "target"))
        payload = valid_opencode_judge_index_payload()
        materialize_opencode_judge_index_artifacts(
            payload,
            temp_dir / "out",
            profile_payload={
                "schema_version": 1,
                "profile_id": "opencode-profile",
                "mode": "opencode",
                **opencode_launch_policy(),
            },
        )
        preflight_path = temp_dir / "out" / "harness" / "opencode-preflight-report.json"
        preflight_payload = json.loads(preflight_path.read_text(encoding="utf-8"))
        preflight_payload["opencode_model_availability"]["argv"] = ["opencode", "list-models"]
        write_json(preflight_path, preflight_payload)
        new_sha = validator.sha256_file(preflight_path)
        payload["evidence_artifact_refs"]["opencode_preflight_report"]["sha256"] = new_sha
        payload["opencode_agent_runtime"]["opencode_preflight_report"]["sha256"] = new_sha
        payload["opencode_agent_runtime"]["workers"][0]["opencode_preflight_report"]["sha256"] = new_sha

        with self.assertRaisesRegex(ValueError, "opencode_model_availability.argv must be opencode models"):
            validator.validate_judge_evidence_index_contract(
                payload,
                path_text=repo_relative(temp_dir / "out" / "harness" / "judge-evidence-index.json"),
                repo_root=REPO_ROOT,
            )

    def test_judge_evidence_index_rejects_preflight_report_argv_drift_from_handoff(self) -> None:
        temp_dir = Path(tempfile.mkdtemp(prefix="judge-opencode-report-argv-", dir=REPO_ROOT / "target"))
        payload = valid_opencode_judge_index_payload()
        materialize_opencode_judge_index_artifacts(
            payload,
            temp_dir / "out",
            profile_payload={
                "schema_version": 1,
                "profile_id": "opencode-profile",
                "mode": "opencode",
                **opencode_launch_policy(),
            },
        )
        preflight_path = temp_dir / "out" / "harness" / "opencode-preflight-report.json"
        preflight_payload = json.loads(preflight_path.read_text(encoding="utf-8"))
        preflight_payload["argv"] = [
            "opencode",
            "run",
            "--dir",
            ".",
            "--format",
            "json",
            "--variant",
            "max",
            "--model",
            "openai/gpt-5.1",
            "Execute test preflight marker.",
        ]
        write_json(preflight_path, preflight_payload)
        refresh_all_opencode_preflight_ref_hashes(payload, preflight_path)

        with self.assertRaisesRegex(ValueError, r"opencode_preflight_report.argv must match handoff_contract.opencode_argv"):
            validator.validate_judge_evidence_index_contract(
                payload,
                path_text=repo_relative(temp_dir / "out" / "harness" / "judge-evidence-index.json"),
                repo_root=REPO_ROOT,
            )

    def test_judge_evidence_index_rejects_preflight_marker_payload_drift(self) -> None:
        temp_dir = Path(tempfile.mkdtemp(prefix="judge-opencode-marker-drift-", dir=REPO_ROOT / "target"))
        payload = valid_opencode_judge_index_payload()
        materialize_opencode_judge_index_artifacts(
            payload,
            temp_dir / "out",
            profile_payload={
                "schema_version": 1,
                "profile_id": "opencode-profile",
                "mode": "opencode",
                **opencode_launch_policy(),
            },
        )
        preflight_path = temp_dir / "out" / "harness" / "opencode-preflight-report.json"
        marker_path = preflight_marker_path(preflight_path)
        marker_payload = json.loads(marker_path.read_text(encoding="utf-8"))
        marker_payload["run_id"] = "different-run"
        write_json(marker_path, marker_payload)
        preflight_payload = json.loads(preflight_path.read_text(encoding="utf-8"))
        preflight_payload["marker"]["sha256"] = validator.sha256_file(marker_path)
        write_json(preflight_path, preflight_payload)
        refresh_all_opencode_preflight_ref_hashes(payload, preflight_path)

        with self.assertRaisesRegex(ValueError, "marker.run_id must match preflight run_id"):
            validator.validate_judge_evidence_index_contract(
                payload,
                path_text=repo_relative(temp_dir / "out" / "harness" / "judge-evidence-index.json"),
                repo_root=REPO_ROOT,
            )

    def test_judge_evidence_index_rejects_preflight_marker_hash_drift(self) -> None:
        temp_dir = Path(tempfile.mkdtemp(prefix="judge-opencode-marker-hash-drift-", dir=REPO_ROOT / "target"))
        payload = valid_opencode_judge_index_payload()
        materialize_opencode_judge_index_artifacts(
            payload,
            temp_dir / "out",
            profile_payload={
                "schema_version": 1,
                "profile_id": "opencode-profile",
                "mode": "opencode",
                **opencode_launch_policy(),
            },
        )
        preflight_path = temp_dir / "out" / "harness" / "opencode-preflight-report.json"
        marker_path = preflight_marker_path(preflight_path)
        marker_payload = json.loads(marker_path.read_text(encoding="utf-8"))
        marker_payload["tampered_after_preflight_report"] = True
        write_json(marker_path, marker_payload)

        with self.assertRaisesRegex(ValueError, r"opencode_preflight_report.marker sha256 mismatch"):
            validator.validate_judge_evidence_index_contract(
                payload,
                path_text=repo_relative(temp_dir / "out" / "harness" / "judge-evidence-index.json"),
                repo_root=REPO_ROOT,
            )

    def test_judge_evidence_index_rejects_absolute_preflight_model_probe_argv(self) -> None:
        temp_dir = Path(tempfile.mkdtemp(prefix="judge-opencode-model-argv-absolute-", dir=REPO_ROOT / "target"))
        payload = valid_opencode_judge_index_payload()
        materialize_opencode_judge_index_artifacts(
            payload,
            temp_dir / "out",
            profile_payload={
                "schema_version": 1,
                "profile_id": "opencode-profile",
                "mode": "opencode",
                **opencode_launch_policy(),
            },
        )
        preflight_path = temp_dir / "out" / "harness" / "opencode-preflight-report.json"
        preflight_payload = json.loads(preflight_path.read_text(encoding="utf-8"))
        preflight_payload["opencode_model_availability"]["argv"] = [
            "C:/Users/me/AppData/Roaming/npm/opencode.CMD",
            "models",
        ]
        write_json(preflight_path, preflight_payload)
        new_sha = validator.sha256_file(preflight_path)
        payload["evidence_artifact_refs"]["opencode_preflight_report"]["sha256"] = new_sha
        payload["opencode_agent_runtime"]["opencode_preflight_report"]["sha256"] = new_sha
        payload["opencode_agent_runtime"]["workers"][0]["opencode_preflight_report"]["sha256"] = new_sha

        with self.assertRaisesRegex(ValueError, "opencode_model_availability.argv must be opencode models"):
            validator.validate_judge_evidence_index_contract(
                payload,
                path_text=repo_relative(temp_dir / "out" / "harness" / "judge-evidence-index.json"),
                repo_root=REPO_ROOT,
            )

    def test_judge_evidence_index_rejects_preflight_model_probe_log_hash_drift(self) -> None:
        temp_dir = Path(tempfile.mkdtemp(prefix="judge-opencode-model-log-", dir=REPO_ROOT / "target"))
        payload = valid_opencode_judge_index_payload()
        materialize_opencode_judge_index_artifacts(
            payload,
            temp_dir / "out",
            profile_payload={
                "schema_version": 1,
                "profile_id": "opencode-profile",
                "mode": "opencode",
                **opencode_launch_policy(),
            },
        )
        preflight_path = temp_dir / "out" / "harness" / "opencode-preflight-report.json"
        preflight_payload = json.loads(preflight_path.read_text(encoding="utf-8"))
        stdout_path = REPO_ROOT / preflight_payload["opencode_model_availability"]["logs"]["stdout"]
        stdout_path.write_text("openai/gpt-5.1\n", encoding="utf-8")

        with self.assertRaisesRegex(ValueError, "opencode_model_availability.logs.stdout sha256 mismatch"):
            validator.validate_judge_evidence_index_contract(
                payload,
                path_text=repo_relative(temp_dir / "out" / "harness" / "judge-evidence-index.json"),
                repo_root=REPO_ROOT,
            )

    def test_judge_evidence_index_rejects_preflight_model_probe_stdout_without_glm(self) -> None:
        temp_dir = Path(tempfile.mkdtemp(prefix="judge-opencode-model-stdout-", dir=REPO_ROOT / "target"))
        payload = valid_opencode_judge_index_payload()
        materialize_opencode_judge_index_artifacts(
            payload,
            temp_dir / "out",
            profile_payload={
                "schema_version": 1,
                "profile_id": "opencode-profile",
                "mode": "opencode",
                **opencode_launch_policy(),
            },
        )
        preflight_path = temp_dir / "out" / "harness" / "opencode-preflight-report.json"
        preflight_payload = json.loads(preflight_path.read_text(encoding="utf-8"))
        stdout_text = "openai/gpt-5.1\nopencode/not-GLM-5.1\nzhipu/glm-5.1\n"
        stdout_path = REPO_ROOT / preflight_payload["opencode_model_availability"]["logs"]["stdout"]
        stdout_path.write_text(stdout_text, encoding="utf-8")
        preflight_payload["opencode_model_availability"]["stdout_sha256"] = validator.sha256_text(stdout_text)
        write_json(preflight_path, preflight_payload)
        new_sha = validator.sha256_file(preflight_path)
        payload["evidence_artifact_refs"]["opencode_preflight_report"]["sha256"] = new_sha
        payload["opencode_agent_runtime"]["opencode_preflight_report"]["sha256"] = new_sha
        payload["opencode_agent_runtime"]["workers"][0]["opencode_preflight_report"]["sha256"] = new_sha

        with self.assertRaisesRegex(ValueError, "opencode_model_availability.logs.stdout must list GLM-5.1"):
            validator.validate_judge_evidence_index_contract(
                payload,
                path_text=repo_relative(temp_dir / "out" / "harness" / "judge-evidence-index.json"),
                repo_root=REPO_ROOT,
            )

    def test_judge_evidence_index_rejects_preflight_without_opencode_launch(self) -> None:
        temp_dir = Path(tempfile.mkdtemp(prefix="judge-opencode-preflight-launch-", dir=REPO_ROOT / "target"))
        payload = valid_opencode_judge_index_payload()
        materialize_opencode_judge_index_artifacts(
            payload,
            temp_dir / "out",
            profile_payload={
                "schema_version": 1,
                "profile_id": "opencode-profile",
                "mode": "opencode",
                **opencode_launch_policy(),
            },
        )
        preflight_path = temp_dir / "out" / "harness" / "opencode-preflight-report.json"
        preflight_payload = json.loads(preflight_path.read_text(encoding="utf-8"))
        preflight_payload["opencode_run_launched"] = False
        write_json(preflight_path, preflight_payload)
        refresh_all_opencode_preflight_ref_hashes(payload, preflight_path)

        with self.assertRaisesRegex(ValueError, "opencode_run_launched must be true"):
            validator.validate_judge_evidence_index_contract(
                payload,
                path_text=repo_relative(temp_dir / "out" / "harness" / "judge-evidence-index.json"),
                repo_root=REPO_ROOT,
            )

    def test_judge_evidence_index_rejects_preflight_without_session_evidence(self) -> None:
        temp_dir = Path(tempfile.mkdtemp(prefix="judge-opencode-preflight-no-session-", dir=REPO_ROOT / "target"))
        payload = valid_opencode_judge_index_payload()
        materialize_opencode_judge_index_artifacts(
            payload,
            temp_dir / "out",
            profile_payload={
                "schema_version": 1,
                "profile_id": "opencode-profile",
                "mode": "opencode",
                **opencode_launch_policy(),
            },
        )
        preflight_path = temp_dir / "out" / "harness" / "opencode-preflight-report.json"
        preflight_payload = json.loads(preflight_path.read_text(encoding="utf-8"))
        preflight_payload.pop("opencode_session_evidence")
        write_json(preflight_path, preflight_payload)
        refresh_all_opencode_preflight_ref_hashes(payload, preflight_path)

        with self.assertRaisesRegex(ValueError, "opencode_session_evidence"):
            validator.validate_judge_evidence_index_contract(
                payload,
                path_text=repo_relative(temp_dir / "out" / "harness" / "judge-evidence-index.json"),
                repo_root=REPO_ROOT,
            )

    def test_judge_evidence_index_rejects_preflight_without_runtime_env(self) -> None:
        temp_dir = Path(tempfile.mkdtemp(prefix="judge-opencode-preflight-no-runtime-env-", dir=REPO_ROOT / "target"))
        payload = valid_opencode_judge_index_payload()
        materialize_opencode_judge_index_artifacts(
            payload,
            temp_dir / "out",
            profile_payload={
                "schema_version": 1,
                "profile_id": "opencode-profile",
                "mode": "opencode",
                **opencode_launch_policy(),
            },
        )
        preflight_path = temp_dir / "out" / "harness" / "opencode-preflight-report.json"
        preflight_payload = json.loads(preflight_path.read_text(encoding="utf-8"))
        preflight_payload.pop("opencode_runtime_env")
        write_json(preflight_path, preflight_payload)
        refresh_all_opencode_preflight_ref_hashes(payload, preflight_path)

        with self.assertRaisesRegex(ValueError, "opencode_preflight_report.opencode_runtime_env"):
            validator.validate_judge_evidence_index_contract(
                payload,
                path_text=repo_relative(temp_dir / "out" / "harness" / "judge-evidence-index.json"),
                repo_root=REPO_ROOT,
            )

    def test_judge_evidence_index_rejects_preflight_session_evidence_hash_drift(self) -> None:
        temp_dir = Path(tempfile.mkdtemp(prefix="judge-opencode-preflight-session-drift-", dir=REPO_ROOT / "target"))
        payload = valid_opencode_judge_index_payload()
        materialize_opencode_judge_index_artifacts(
            payload,
            temp_dir / "out",
            profile_payload={
                "schema_version": 1,
                "profile_id": "opencode-profile",
                "mode": "opencode",
                **opencode_launch_policy(),
            },
        )
        preflight_path = temp_dir / "out" / "harness" / "opencode-preflight-report.json"
        preflight_payload = json.loads(preflight_path.read_text(encoding="utf-8"))
        session_path = REPO_ROOT / preflight_payload["opencode_session_evidence"]["path"]
        session_payload = json.loads(session_path.read_text(encoding="utf-8"))
        session_payload["session_events"] = []
        write_json(session_path, session_payload)

        with self.assertRaisesRegex(ValueError, "opencode_session_evidence sha256 mismatch"):
            validator.validate_judge_evidence_index_contract(
                payload,
                path_text=repo_relative(temp_dir / "out" / "harness" / "judge-evidence-index.json"),
                repo_root=REPO_ROOT,
            )

    def test_judge_evidence_index_rejects_preflight_session_without_shell_call(self) -> None:
        temp_dir = Path(tempfile.mkdtemp(prefix="judge-opencode-preflight-no-shell-", dir=REPO_ROOT / "target"))
        payload = valid_opencode_judge_index_payload()
        materialize_opencode_judge_index_artifacts(
            payload,
            temp_dir / "out",
            profile_payload={
                "schema_version": 1,
                "profile_id": "opencode-profile",
                "mode": "opencode",
                **opencode_launch_policy(),
            },
        )
        preflight_path = temp_dir / "out" / "harness" / "opencode-preflight-report.json"
        rewrite_preflight_session_evidence(
            preflight_path,
            {
                "schema_version": 1,
                "process_returncode": 0,
                "parsed": True,
                "format": "jsonl",
                "session_events": [],
            },
        )
        refresh_all_opencode_preflight_ref_hashes(payload, preflight_path)

        with self.assertRaisesRegex(ValueError, "contract_verification.status recomputed from opencode_session_evidence must be executed"):
            validator.validate_judge_evidence_index_contract(
                payload,
                path_text=repo_relative(temp_dir / "out" / "harness" / "judge-evidence-index.json"),
                repo_root=REPO_ROOT,
            )

    def test_opencode_preflight_binding_rejects_failed_session_evidence_contract(self) -> None:
        cases = [
            ("nonzero_returncode", {"process_returncode": 1}, "process_returncode must be 0"),
            ("unparsed_session", {"parsed": False}, "parsed must be true"),
            ("non_jsonl_format", {"format": "text"}, "format must be jsonl"),
        ]
        for case_name, updates, expected_error in cases:
            with self.subTest(case=case_name):
                temp_dir = Path(tempfile.mkdtemp(prefix="judge-opencode-preflight-session-contract-", dir=REPO_ROOT / "target"))
                payload = valid_opencode_judge_index_payload()
                materialize_opencode_judge_index_artifacts(
                    payload,
                    temp_dir / "out",
                    profile_payload={
                        "schema_version": 1,
                        "profile_id": "opencode-profile",
                        "mode": "opencode",
                        **opencode_launch_policy(),
                    },
                )
                preflight_path = temp_dir / "out" / "harness" / "opencode-preflight-report.json"
                preflight_payload = json.loads(preflight_path.read_text(encoding="utf-8"))
                session_path = REPO_ROOT / preflight_payload["opencode_session_evidence"]["path"]
                session_payload = json.loads(session_path.read_text(encoding="utf-8"))
                session_payload.update(updates)
                rewrite_preflight_session_evidence(preflight_path, session_payload)
                payload["opencode_agent_runtime"]["opencode_preflight_report"]["sha256"] = validator.sha256_file(preflight_path)

                with self.assertRaisesRegex(
                    ValueError,
                    rf"opencode_agent_runtime\.opencode_preflight_report\.opencode_session_evidence\.{expected_error}",
                ):
                    validator.validate_opencode_preflight_binding(
                        payload["opencode_agent_runtime"]["opencode_preflight_report"],
                        "opencode_agent_runtime.opencode_preflight_report",
                        repo_root=REPO_ROOT,
                    )

    def test_judge_evidence_index_rejects_preflight_first_shell_mismatch_even_if_marker_runs_later(self) -> None:
        temp_dir = Path(tempfile.mkdtemp(prefix="judge-opencode-preflight-late-marker-", dir=REPO_ROOT / "target"))
        payload = valid_opencode_judge_index_payload()
        materialize_opencode_judge_index_artifacts(
            payload,
            temp_dir / "out",
            profile_payload={
                "schema_version": 1,
                "profile_id": "opencode-profile",
                "mode": "opencode",
                **opencode_launch_policy(),
            },
        )
        preflight_path = temp_dir / "out" / "harness" / "opencode-preflight-report.json"
        marker_command_line = preflight_marker_command_line(preflight_path)
        rewrite_preflight_session_evidence(
            preflight_path,
            {
                "schema_version": 1,
                "process_returncode": 0,
                "parsed": True,
                "format": "jsonl",
                "session_events": [
                    {
                        "part": {
                            "tool": "bash",
                            "state": {"input": {"command": "python3 -B -c 'print(1)'", "workdir": str(REPO_ROOT)}},
                        }
                    },
                    {
                        "part": {
                            "tool": "bash",
                            "state": {"input": {"command": marker_command_line, "workdir": str(REPO_ROOT)}},
                        }
                    },
                ],
            },
        )
        refresh_all_opencode_preflight_ref_hashes(payload, preflight_path)

        with self.assertRaisesRegex(ValueError, "first_shell_command_mismatch_worker_command_seen_later"):
            validator.validate_judge_evidence_index_contract(
                payload,
                path_text=repo_relative(temp_dir / "out" / "harness" / "judge-evidence-index.json"),
                repo_root=REPO_ROOT,
            )

    def test_judge_evidence_index_rejects_preflight_extra_shell_after_marker(self) -> None:
        temp_dir = Path(tempfile.mkdtemp(prefix="judge-opencode-preflight-extra-shell-", dir=REPO_ROOT / "target"))
        payload = valid_opencode_judge_index_payload()
        materialize_opencode_judge_index_artifacts(
            payload,
            temp_dir / "out",
            profile_payload={
                "schema_version": 1,
                "profile_id": "opencode-profile",
                "mode": "opencode",
                **opencode_launch_policy(),
            },
        )
        preflight_path = temp_dir / "out" / "harness" / "opencode-preflight-report.json"
        marker_command_line = preflight_marker_command_line(preflight_path)
        extra_command = "python3 -B validation/tools/opencode_agent_harness.py init-run --run-id unexpected"
        preflight_payload = rewrite_preflight_session_evidence(
            preflight_path,
            {
                "schema_version": 1,
                "process_returncode": 0,
                "parsed": True,
                "format": "jsonl",
                "session_events": [
                    {
                        "part": {
                            "tool": "bash",
                            "state": {"input": {"command": marker_command_line, "workdir": str(REPO_ROOT)}},
                        }
                    },
                    {
                        "part": {
                            "tool": "bash",
                            "state": {"input": {"command": extra_command, "workdir": str(REPO_ROOT)}},
                        }
                    },
                ],
            },
        )
        preflight_payload["contract_verification"]["executed_shell_command_count"] = 2
        preflight_payload["contract_verification"]["executed_shell_commands"] = [
            marker_command_line,
            extra_command,
        ]
        write_json(preflight_path, preflight_payload)
        refresh_all_opencode_preflight_ref_hashes(payload, preflight_path)

        with self.assertRaisesRegex(ValueError, "extra_shell_command_after_contract"):
            validator.validate_judge_evidence_index_contract(
                payload,
                path_text=repo_relative(temp_dir / "out" / "harness" / "judge-evidence-index.json"),
                repo_root=REPO_ROOT,
            )

    def test_judge_evidence_index_rejects_preflight_non_repo_workdir(self) -> None:
        temp_dir = Path(tempfile.mkdtemp(prefix="judge-opencode-preflight-workdir-", dir=REPO_ROOT / "target"))
        payload = valid_opencode_judge_index_payload()
        materialize_opencode_judge_index_artifacts(
            payload,
            temp_dir / "out",
            profile_payload={
                "schema_version": 1,
                "profile_id": "opencode-profile",
                "mode": "opencode",
                **opencode_launch_policy(),
            },
        )
        preflight_path = temp_dir / "out" / "harness" / "opencode-preflight-report.json"
        marker_command_line = preflight_marker_command_line(preflight_path)
        rewrite_preflight_session_evidence(
            preflight_path,
            {
                "schema_version": 1,
                "process_returncode": 0,
                "parsed": True,
                "format": "jsonl",
                "session_events": [
                    {
                        "part": {
                            "tool": "bash",
                            "state": {"input": {"command": marker_command_line, "workdir": str(REPO_ROOT.parent)}},
                        }
                    }
                ],
            },
        )
        refresh_all_opencode_preflight_ref_hashes(payload, preflight_path)

        with self.assertRaisesRegex(ValueError, "opencode_workdir_mismatch"):
            validator.validate_judge_evidence_index_contract(
                payload,
                path_text=repo_relative(temp_dir / "out" / "harness" / "judge-evidence-index.json"),
                repo_root=REPO_ROOT,
            )

    def test_judge_evidence_index_rejects_preflight_missing_workdir(self) -> None:
        temp_dir = Path(tempfile.mkdtemp(prefix="judge-opencode-preflight-missing-workdir-", dir=REPO_ROOT / "target"))
        payload = valid_opencode_judge_index_payload()
        materialize_opencode_judge_index_artifacts(
            payload,
            temp_dir / "out",
            profile_payload={
                "schema_version": 1,
                "profile_id": "opencode-profile",
                "mode": "opencode",
                **opencode_launch_policy(),
            },
        )
        preflight_path = temp_dir / "out" / "harness" / "opencode-preflight-report.json"
        marker_command_line = preflight_marker_command_line(preflight_path)
        rewrite_preflight_session_evidence(
            preflight_path,
            {
                "schema_version": 1,
                "process_returncode": 0,
                "parsed": True,
                "format": "jsonl",
                "session_events": [
                    {
                        "part": {
                            "tool": "bash",
                            "state": {"input": {"command": marker_command_line}},
                        }
                    }
                ],
            },
        )
        refresh_all_opencode_preflight_ref_hashes(payload, preflight_path)

        with self.assertRaisesRegex(ValueError, "opencode_workdir_mismatch"):
            validator.validate_judge_evidence_index_contract(
                payload,
                path_text=repo_relative(temp_dir / "out" / "harness" / "judge-evidence-index.json"),
                repo_root=REPO_ROOT,
            )

    def test_judge_evidence_index_rejects_worker_session_without_shell_call(self) -> None:
        temp_dir = Path(tempfile.mkdtemp(prefix="judge-opencode-worker-no-shell-", dir=REPO_ROOT / "target"))
        payload = valid_opencode_judge_index_payload()
        materialize_opencode_judge_index_artifacts(
            payload,
            temp_dir / "out",
            profile_payload={
                "schema_version": 1,
                "profile_id": "opencode-profile",
                "mode": "opencode",
                **opencode_launch_policy(),
            },
        )
        worker = payload["opencode_agent_runtime"]["workers"][0]
        rewrite_worker_session_evidence(
            worker,
            {
                "schema_version": 1,
                "process_returncode": 0,
                "parsed": True,
                "format": "jsonl",
                "session_events": [],
            },
        )

        with self.assertRaisesRegex(
            ValueError,
            "opencode_contract_verification.status recomputed from opencode_session_evidence must be executed",
        ):
            validator.validate_judge_evidence_index_contract(
                payload,
                path_text=repo_relative(temp_dir / "out" / "harness" / "judge-evidence-index.json"),
                repo_root=REPO_ROOT,
            )

    def test_opencode_agent_runtime_rejects_failed_worker_session_evidence_contract(self) -> None:
        cases = [
            ("nonzero_returncode", {"process_returncode": 1}, "process_returncode must be 0"),
            ("unparsed_session", {"parsed": False}, "parsed must be true"),
            ("non_jsonl_format", {"format": "text"}, "format must be jsonl"),
        ]
        for case_name, updates, expected_error in cases:
            with self.subTest(case=case_name):
                temp_dir = Path(tempfile.mkdtemp(prefix="judge-opencode-worker-session-contract-", dir=REPO_ROOT / "target"))
                payload = valid_opencode_judge_index_payload()
                materialize_opencode_judge_index_artifacts(
                    payload,
                    temp_dir / "out",
                    profile_payload={
                        "schema_version": 1,
                        "profile_id": "opencode-profile",
                        "mode": "opencode",
                        **opencode_launch_policy(),
                        "auto_retry": True,
                    },
                )
                worker = payload["opencode_agent_runtime"]["workers"][0]
                session_path = REPO_ROOT / worker["opencode_session_evidence"]["path"]
                session_payload = json.loads(session_path.read_text(encoding="utf-8"))
                session_payload.update(updates)
                rewrite_worker_session_evidence(worker, session_payload)

                with self.assertRaisesRegex(
                    ValueError,
                    rf"opencode_agent_runtime\.workers\[0\]\.opencode_session_evidence\.{expected_error}",
                ):
                    validator.validate_opencode_agent_runtime_contract(
                        payload["opencode_agent_runtime"],
                        repo_root=REPO_ROOT,
                    )

    def test_opencode_agent_runtime_rejects_session_evidence_not_reparsed_from_stdout(self) -> None:
        temp_dir = Path(tempfile.mkdtemp(prefix="judge-opencode-worker-session-raw-drift-", dir=REPO_ROOT / "target"))
        payload = valid_opencode_judge_index_payload()
        materialize_opencode_judge_index_artifacts(
            payload,
            temp_dir / "out",
            profile_payload={
                "schema_version": 1,
                "profile_id": "opencode-profile",
                "mode": "opencode",
                **opencode_launch_policy(),
                "auto_retry": True,
            },
        )
        worker = payload["opencode_agent_runtime"]["workers"][0]
        session_path = REPO_ROOT / worker["opencode_session_evidence"]["path"]
        session_payload = json.loads(session_path.read_text(encoding="utf-8"))
        stdout_path = REPO_ROOT / session_payload["stdout_path"]
        stdout_path.write_text(
            opencode_session_stdout_jsonl(
                [
                    {"type": "text", "part": {"text": "summary-only spoof"}},
                    {"type": "text", "part": {"text": "still no shell"}},
                ]
            ),
            encoding="utf-8",
            newline="\n",
        )
        session_payload["stdout_sha256"] = validator.sha256_file(stdout_path)
        worker["logs"]["stdout"]["sha256"] = validator.sha256_file(stdout_path)
        write_json(session_path, session_payload)
        worker["opencode_session_evidence"]["sha256"] = validator.sha256_file(session_path)

        with self.assertRaisesRegex(
            ValueError,
            r"opencode_agent_runtime\.workers\[0\]\.opencode_session_evidence\.session_events must match parsed stdout",
        ):
            validator.validate_opencode_agent_runtime_contract(
                payload["opencode_agent_runtime"],
                repo_root=REPO_ROOT,
            )
