import json
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import call, patch


REPO_ROOT = Path(__file__).resolve().parents[2]


def repo_relative(path: Path) -> str:
    return path.relative_to(REPO_ROOT).as_posix()


class RunJudgeEntrypointsTests(unittest.TestCase):
    def setUp(self) -> None:
        self.portable_python_patch = patch(
            "validation.tools.run_judge_entrypoints.portable_python_command_argv",
            return_value=["python"],
        )
        self.portable_python_patch.start()
        self.addCleanup(self.portable_python_patch.stop)

    def test_runner_executes_selected_entrypoint_and_writes_readiness(self) -> None:
        from validation.tools import run_judge_entrypoints as runner

        temp_dir = Path(tempfile.mkdtemp(prefix="run-judge-entrypoints-", dir=REPO_ROOT / "target"))
        config_path = temp_dir / "flashdb-harness.json"
        out_path = temp_dir / "summary" / "judge-entrypoints-run-report.json"
        config_path.write_text(
            json.dumps(
                {
                    "schema_version": 1,
                    "manifest_kind": "judge-entrypoints",
                    "entrypoints": [
                        {
                            "id": "before_after_judge_demo",
                            "purpose": "core-translation-before-after-exhibit",
                            "command": "python3 -B -m validation.tools.judge_demo --run-id selected",
                        },
                        {
                            "id": "multi_worker_evaluate_profile",
                            "purpose": "harness-architecture-multi-worker-evaluate",
                            "command": "python3 -B -m validation.tools.opencode_agent_harness evaluate",
                        },
                        {
                            "id": "opencode_multi_worker_evaluate_profile",
                            "purpose": "harness-architecture-opencode-multi-worker-evaluate",
                            "command": "python3 -B -m validation.tools.opencode_agent_harness evaluate --mode opencode",
                        },
                    ],
                    "test_contract": {
                        "required_entrypoint_ids": [
                            "before_after_judge_demo",
                            "multi_worker_evaluate_profile",
                            "opencode_multi_worker_evaluate_profile",
                        ]
                    },
                },
                sort_keys=True,
            )
            + "\n",
            encoding="utf-8",
        )
        calls: list[list[str]] = []

        def fake_runner(argv: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
            calls.append(argv)
            return subprocess.CompletedProcess(argv, 0, stdout="ok\n", stderr="")

        def fake_write_readiness(result: dict, path: Path, *, repo_root: Path) -> dict:
            path.parent.mkdir(parents=True, exist_ok=True)
            payload = {
                "schema_version": 1,
                "report_kind": "judge-entrypoints-readiness",
                "status": result["status"],
            }
            path.write_text(json.dumps(payload, sort_keys=True) + "\n", encoding="utf-8")
            return payload

        with patch.object(
            runner.validator,
            "validate_config",
            side_effect=[{"status": "passed"}, {"status": "passed"}],
        ) as validate_config:
            with patch.object(runner.validator, "write_readiness_report", side_effect=fake_write_readiness):
                report = runner.run_judge_entrypoints(
                    config_path=config_path,
                    entrypoint_ids=["before_after_judge_demo"],
                    out_path=out_path,
                    command_runner=fake_runner,
                    repo_root=REPO_ROOT,
                )

        self.assertEqual(report["status"], "passed")
        self.assertEqual(report["entrypoint_count"], 1)
        self.assertFalse(report["summary"]["readiness"]["all_entrypoints_executed"])
        self.assertEqual(report["summary"]["readiness"]["executed_count"], 1)
        self.assertEqual(report["summary"]["readiness"]["configured_count"], 3)
        self.assertEqual(report["summary"]["entrypoints"][0]["id"], "before_after_judge_demo")
        self.assertEqual(report["summary"]["entrypoints"][0]["proof_class"], "unknown")
        self.assertEqual(report["entrypoints"][0]["id"], "before_after_judge_demo")
        self.assertEqual(calls, [["python", "-B", "-m", "validation.tools.judge_demo", "--run-id", "selected"]])
        validate_calls = validate_config.call_args_list
        self.assertEqual(validate_calls[0], call(config_path, require_local_artifacts=False, repo_root=REPO_ROOT))
        validation_config_path = validate_calls[1].args[0]
        self.assertNotEqual(validation_config_path, config_path)
        self.assertEqual(validate_calls[1].kwargs, {"require_local_artifacts": True, "repo_root": REPO_ROOT})
        validation_config = json.loads(Path(validation_config_path).read_text(encoding="utf-8"))
        self.assertEqual(
            [entry["id"] for entry in validation_config["entrypoints"]],
            ["before_after_judge_demo"],
        )
        self.assertEqual(
            validation_config["test_contract"]["required_entrypoint_ids"],
            ["before_after_judge_demo"],
        )
        self.assertNotIn(
            "opencode_multi_worker_evaluate_profile",
            [entry["id"] for entry in validation_config["entrypoints"]],
        )
        self.assertEqual(report["validation"]["status"], "passed")
        self.assertEqual(
            report["readiness_report"]["path"],
            repo_relative(out_path.parent / "judge-entrypoints-readiness.json"),
        )
        self.assertEqual(report["readiness_report"]["status"], "present")
        self.assertIn("sha256", report["readiness_report"])
        self.assertEqual(
            report["milestone_bundle"]["path"],
            repo_relative(out_path.parent / "judge-milestone-bundle.json"),
        )
        self.assertEqual(report["milestone_bundle"]["status"], "present")
        self.assertNotIn("sha256", report["milestone_bundle"])
        self.assertEqual(report["milestone_bundle"]["hash_boundary"], "bundle_hashes_this_run_report")
        self.assertEqual(
            report["milestone_release_notes"]["path"],
            repo_relative(out_path.parent / "milestone-release-notes.md"),
        )
        self.assertEqual(report["milestone_release_notes"]["status"], "derived_after_bundle")
        self.assertNotIn("sha256", report["milestone_release_notes"])
        self.assertEqual(report["milestone_release_notes"]["hash_boundary"], "release_notes_hashes_the_bundle")
        milestone_bundle = json.loads((out_path.parent / "judge-milestone-bundle.json").read_text(encoding="utf-8"))
        self.assertEqual(milestone_bundle["status"], "blocked")
        self.assertIn("not_all_entrypoints_executed", milestone_bundle["blockers"])
        self.assertEqual(milestone_bundle["judge_entrypoints_run_report"]["sha256"], runner.validator.sha256_file(out_path))
        release_notes = (out_path.parent / "milestone-release-notes.md").read_text(encoding="utf-8")
        self.assertIn("# FlashDB Harness MVP Release Notes", release_notes)
        self.assertIn("Translation coverage numerator: `0`", release_notes)
        stdout_log = out_path.parent / "logs" / "before_after_judge_demo.stdout.log"
        stderr_log = out_path.parent / "logs" / "before_after_judge_demo.stderr.log"
        self.assertEqual(report["entrypoints"][0]["logs"]["stdout"]["path"], repo_relative(stdout_log))
        self.assertEqual(report["entrypoints"][0]["logs"]["stdout"]["status"], "present")
        self.assertEqual(report["entrypoints"][0]["logs"]["stdout"]["sha256"], runner.validator.sha256_file(stdout_log))
        self.assertEqual(report["entrypoints"][0]["logs"]["stderr"]["sha256"], runner.validator.sha256_file(stderr_log))
        self.assertTrue(out_path.is_file())
        persisted = json.loads(out_path.read_text(encoding="utf-8"))
        self.assertFalse(persisted["claim_boundary"]["semantic_gate"])
        self.assertEqual(persisted["summary"], report["summary"])
        self.assertEqual(persisted["milestone_bundle"], report["milestone_bundle"])

    def test_runner_resolves_portable_python3_entrypoint_for_local_execution(self) -> None:
        from validation.tools import run_judge_entrypoints as runner

        temp_dir = Path(tempfile.mkdtemp(prefix="run-judge-portable-python-", dir=REPO_ROOT / "target"))
        log_dir = temp_dir / "logs"
        calls: list[list[str]] = []
        entry = {
            "id": "before_after_judge_demo",
            "purpose": "core-translation-before-after-exhibit",
            "command": "python3 -B -m validation.tools.judge_demo --run-id portable",
        }

        def fake_runner(argv: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
            calls.append(argv)
            return subprocess.CompletedProcess(argv, 0, stdout="ok\n", stderr="")

        with patch.object(runner, "portable_python_command_argv", return_value=["python"], create=True):
            result = runner.run_entrypoint_command(
                entry,
                dry_run=False,
                log_dir=log_dir,
                repo_root=REPO_ROOT,
                timeout_seconds=30,
                command_runner=fake_runner,
            )

        self.assertEqual(calls, [["python", "-B", "-m", "validation.tools.judge_demo", "--run-id", "portable"]])
        self.assertEqual(result["argv"], ["python3", "-B", "-m", "validation.tools.judge_demo", "--run-id", "portable"])
        self.assertEqual(
            result["effective_argv"],
            ["python", "-B", "-m", "validation.tools.judge_demo", "--run-id", "portable"],
        )
        self.assertEqual(result["status"], "passed")

    def test_all_entrypoints_report_has_judge_facing_summary(self) -> None:
        from validation.tools import run_judge_entrypoints as runner

        temp_dir = Path(tempfile.mkdtemp(prefix="run-judge-all-summary-", dir=REPO_ROOT / "target"))
        config_path = temp_dir / "flashdb-harness.json"
        out_path = temp_dir / "summary" / "judge-entrypoints-run-report.json"
        config_path.write_text(
            json.dumps(
                {
                    "entrypoints": [
                        {
                            "id": "competition_environment_smoke",
                            "priority": 0,
                            "purpose": "competition-environment-smoke",
                            "proof_class": "local-simulation",
                            "run_id": "smoke-run",
                            "command": "python3 -B validation/tools/run_competition_smoke.py",
                            "judge_focus": ["environment smoke", "semantic_gate=false"],
                            "expected_artifacts": {"competition_smoke_summary": "target/out/smoke.json"},
                        },
                        {
                            "id": "opencode_multi_worker_evaluate_profile",
                            "priority": 30,
                            "purpose": "harness-architecture-opencode-multi-worker-evaluate",
                            "proof_class": "local-simulation",
                            "run_id": "opencode-run",
                            "command": "python3 -B -m validation.tools.opencode_agent_harness evaluate",
                            "judge_focus": ["OpenCode multi-agent", "repair cap 5"],
                            "expected_artifacts": {
                                "judge_evidence_index": "target/out/index.json",
                                "opencode_safety_transform_attempt": (
                                    "target/out/workers/worker-a/harness/"
                                    "opencode-safety-transform-attempt-1.json"
                                ),
                            },
                        },
                    ],
                },
                sort_keys=True,
            )
            + "\n",
            encoding="utf-8",
        )

        def fake_runner(argv: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
            return subprocess.CompletedProcess(argv, 0, stdout="ok\n", stderr="")

        def fake_write_readiness(result: dict, path: Path, *, repo_root: Path) -> dict:
            path.parent.mkdir(parents=True, exist_ok=True)
            payload = {
                "schema_version": 1,
                "report_kind": "judge-entrypoints-readiness",
                "status": result["status"],
            }
            path.write_text(json.dumps(payload, sort_keys=True) + "\n", encoding="utf-8")
            return payload

        with patch.object(runner.validator, "validate_config", side_effect=[{"status": "passed"}, {"status": "passed"}]):
            with patch.object(runner.validator, "write_readiness_report", side_effect=fake_write_readiness):
                report = runner.run_judge_entrypoints(
                    config_path=config_path,
                    entrypoint_ids=[],
                    out_path=out_path,
                    command_runner=fake_runner,
                    repo_root=REPO_ROOT,
                )

        summary = report["summary"]
        self.assertIn("2/2", summary["headline"])
        self.assertFalse(summary["claim_boundary"]["semantic_gate"])
        self.assertTrue(summary["readiness"]["all_entrypoints_executed"])
        self.assertEqual(
            report["milestone_bundle"]["path"],
            repo_relative(out_path.parent / "judge-milestone-bundle.json"),
        )
        self.assertEqual(report["milestone_bundle"]["status"], "present")
        self.assertEqual(report["milestone_bundle"]["hash_boundary"], "bundle_hashes_this_run_report")
        self.assertEqual(
            report["milestone_release_notes"]["path"],
            repo_relative(out_path.parent / "milestone-release-notes.md"),
        )
        self.assertEqual(report["milestone_release_notes"]["status"], "derived_after_bundle")
        self.assertNotIn("sha256", report["milestone_release_notes"])
        self.assertEqual(report["milestone_release_notes"]["hash_boundary"], "release_notes_hashes_the_bundle")
        self.assertEqual(
            report["public_release_packet"]["path"],
            repo_relative(out_path.parent / "public-release-packet.json"),
        )
        self.assertEqual(report["public_release_packet"]["status"], "derived_after_release_notes")
        self.assertNotIn("sha256", report["public_release_packet"])
        self.assertEqual(
            report["public_release_packet"]["hash_boundary"],
            "packet_hashes_run_report_bundle_and_release_notes",
        )
        milestone_bundle = json.loads((out_path.parent / "judge-milestone-bundle.json").read_text(encoding="utf-8"))
        self.assertEqual(milestone_bundle["status"], "passed")
        self.assertTrue(milestone_bundle["summary"]["external_milestone_claim_ready"])
        self.assertFalse(milestone_bundle["claim_boundary"]["semantic_gate"])
        self.assertEqual(milestone_bundle["judge_entrypoints_run_report"]["sha256"], runner.validator.sha256_file(out_path))
        release_notes = (out_path.parent / "milestone-release-notes.md").read_text(encoding="utf-8")
        self.assertIn("# FlashDB Harness MVP Release Notes", release_notes)
        self.assertIn("Semantic gate: `false`", release_notes)
        public_packet = json.loads((out_path.parent / "public-release-packet.json").read_text(encoding="utf-8"))
        self.assertEqual(public_packet["report_kind"], "public-release-packet")
        self.assertEqual(public_packet["status"], "passed")
        self.assertEqual(public_packet["judge_entrypoints_run_report"]["sha256"], runner.validator.sha256_file(out_path))
        self.assertEqual(
            public_packet["judge_milestone_bundle"]["sha256"],
            runner.validator.sha256_file(out_path.parent / "judge-milestone-bundle.json"),
        )
        self.assertEqual(
            public_packet["milestone_release_notes"]["sha256"],
            runner.validator.sha256_file(out_path.parent / "milestone-release-notes.md"),
        )
        self.assertEqual(public_packet["readiness_report"]["sha256"], runner.validator.sha256_file(out_path.parent / "judge-entrypoints-readiness.json"))
        self.assertFalse(public_packet["claim_boundary"]["semantic_gate"])
        self.assertFalse(public_packet["claim_boundary"]["packet_is_semantic_gate"])
        self.assertEqual(public_packet["claim_boundary"]["translation_coverage_numerator"], 0)
        self.assertEqual(public_packet["competition_config_archive"]["status"], "present")
        archive_manifest_path = out_path.parent / "competition-config-archive" / "manifest.json"
        self.assertTrue(archive_manifest_path.is_file())
        archive_manifest_ref = public_packet["competition_config_archive"]["materialized_manifest"]
        self.assertEqual(archive_manifest_ref["path"], repo_relative(archive_manifest_path))
        self.assertEqual(archive_manifest_ref["status"], "present")
        self.assertEqual(archive_manifest_ref["sha256"], runner.validator.sha256_file(archive_manifest_path))
        self.assertEqual(report["competition_config_archive"]["materialized_manifest"], archive_manifest_ref)
        self.assertEqual(report["summary"]["competition_config_archive"]["materialized_manifest"], archive_manifest_ref)
        archive_manifest = json.loads(archive_manifest_path.read_text(encoding="utf-8"))
        self.assertEqual(archive_manifest["report_kind"], "competition-config-archive")
        self.assertEqual(archive_manifest["status"], "present")
        self.assertFalse(archive_manifest["claim_boundary"]["semantic_gate"])
        self.assertNotIn("materialized_manifest", archive_manifest)
        self.assertEqual(public_packet["summary"]["entrypoint_count"], 2)
        self.assertEqual(public_packet["summary"]["blockers"], milestone_bundle["blockers"])
        self.assertEqual(public_packet["summary"]["workflow_metrics"]["repair_activity"], milestone_bundle["workflow_metrics"]["rollup"]["repair_activity"])
        self.assertFalse(public_packet["summary"]["workflow_metrics"]["semantic_gate"])
        self.assertEqual(public_packet["summary"]["workflow_metrics"]["translation_coverage_numerator"], 0)
        self.assertEqual(public_packet["summary"]["progress_delta_ledger"], milestone_bundle["progress_delta_ledger"])
        self.assertEqual(public_packet["progress_delta_ledger"], milestone_bundle["progress_delta_ledger"])
        self.assertFalse(public_packet["progress_delta_ledger"]["semantic_gate"])
        self.assertEqual(public_packet["progress_delta_ledger"]["translation_coverage_numerator"], 0)
        self.assertIn("observed_repair_unit_count", public_packet["progress_delta_ledger"]["workflow_delta"])
        self.assertIn("rollback_evidence_count", public_packet["progress_delta_ledger"]["workflow_delta"])
        self.assertIn("before_after_repair_source_count", public_packet["progress_delta_ledger"]["workflow_delta"])
        self.assertIn("repair_delta_source_count", public_packet["progress_delta_ledger"]["workflow_delta"])
        self.assertEqual(public_packet["quantitative_evaluation"], milestone_bundle["quantitative_evaluation"])
        self.assertEqual(public_packet["before_after_repair_exhibit"], milestone_bundle["before_after_repair_exhibit"])
        self.assertFalse(public_packet["before_after_repair_exhibit"]["semantic_gate"])
        self.assertEqual(public_packet["before_after_repair_exhibit"]["translation_coverage_numerator"], 0)
        published_refs = public_packet["publication_manifest"]["published_artifact_refs"]
        ref_status = public_packet["summary"]["published_artifact_ref_status"]
        self.assertEqual(ref_status["total_count"], len(published_refs))
        expected_status_counts = {}
        expected_abnormal_refs = []
        for ref in published_refs:
            status = ref.get("status", "unknown")
            expected_status_counts[status] = expected_status_counts.get(status, 0) + 1
            if status != "present":
                expected_abnormal_refs.append(
                    {
                        "artifact_name": str(ref.get("artifact_name", "unknown")),
                        "path": str(ref.get("path", "unknown")),
                        "status": str(status),
                    }
                )
        self.assertEqual(ref_status["abnormal_ref_count"], len(expected_abnormal_refs))
        self.assertEqual(ref_status["abnormal_refs"], expected_abnormal_refs)
        self.assertEqual(ref_status["status_counts"], dict(sorted(expected_status_counts.items())))
        self.assertFalse(ref_status["semantic_gate"])
        self.assertEqual(ref_status["translation_coverage_numerator"], 0)
        self.assertIn(
            "opencode_safety_transform_attempt",
            {ref["artifact_name"] for ref in published_refs},
        )
        self.assertIn(
            "opencode_safety_transform_attempt",
            {
                ref["artifact_name"]
                for ref in milestone_bundle["publication_manifest"]["published_artifact_refs"]
            },
        )
        opencode_boundary = public_packet["opencode_patch_boundary"]
        self.assertEqual(opencode_boundary["report_kind"], "opencode-patch-boundary")
        self.assertFalse(opencode_boundary["semantic_gate"])
        self.assertFalse(opencode_boundary["chat_output_is_evidence"])
        self.assertEqual(opencode_boundary["translation_coverage_numerator"], 0)
        self.assertEqual(opencode_boundary["before_after_patch_sources"], [])
        self.assertIn("status", opencode_boundary["opencode_safety_transform_attempt"])
        self.assertFalse(public_packet["quantitative_evaluation"]["semantic_gate"])
        self.assertEqual(public_packet["quantitative_evaluation"]["translation_coverage_numerator"], 0)
        self.assertEqual(summary["readiness"]["executed_count"], 2)
        self.assertEqual(summary["readiness"]["configured_count"], 2)
        self.assertEqual(summary["readiness"]["validation_status"], "passed")
        self.assertEqual([entry["id"] for entry in summary["entrypoints"]], ["competition_environment_smoke", "opencode_multi_worker_evaluate_profile"])
        self.assertEqual(summary["entrypoints"][0]["judge_focus"], ["environment smoke", "semantic_gate=false"])
        self.assertEqual(
            summary["entrypoints"][1]["key_artifacts"],
            {
                "judge_evidence_index": "target/out/index.json",
                "opencode_safety_transform_attempt": (
                    "target/out/workers/worker-a/harness/opencode-safety-transform-attempt-1.json"
                ),
            },
        )
        persisted = json.loads(out_path.read_text(encoding="utf-8"))
        self.assertEqual(persisted["milestone_bundle"], report["milestone_bundle"])
        self.assertEqual(persisted["milestone_release_notes"], report["milestone_release_notes"])
        self.assertEqual(persisted["public_release_packet"], report["public_release_packet"])

    def test_public_packet_opencode_patch_boundary_summarizes_attempt_without_semantic_claim(self) -> None:
        from validation.tools import run_judge_entrypoints as runner

        temp_dir = Path(tempfile.mkdtemp(prefix="opencode-patch-boundary-", dir=REPO_ROOT / "target"))
        attempt_path = temp_dir / "workers" / "worker-a" / "harness" / "opencode-safety-transform-attempt-1.json"
        attempt_path.parent.mkdir(parents=True, exist_ok=True)
        attempt_payload = {
            "status": "accepted",
            "attempt_contract": {"max_repair_rounds": 5},
            "accepted_retry_hint": {"status": "not_exercised"},
            "rollback_ref_count": 0,
            "round_count": 1,
        }
        attempt_path.write_text(json.dumps(attempt_payload, sort_keys=True) + "\n", encoding="utf-8")
        preflight_summary = {
            "status": "passed",
            "required_when_opencode_runtime_enabled": True,
            "preflight_report": {
                "path": "target/opencode/harness/opencode-preflight-report.json",
                "status": "present",
                "sha256": "d" * 64,
            },
            "run_id": "opencode-run",
            "opencode_command": "opencode",
            "opencode_model": "GLM-5.1",
            "required_model": "GLM-5.1",
            "model_availability_status": "available",
            "model_listed": True,
            "model_probe_argv": ["opencode", "models"],
            "process_returncode": 0,
            "model_probe_logs": {
                "stdout": {
                    "path": "target/opencode/logs/opencode-models.stdout.log",
                    "status": "present",
                    "sha256": "e" * 64,
                },
                "stderr": {
                    "path": "target/opencode/logs/opencode-models.stderr.log",
                    "status": "present",
                    "sha256": "f" * 64,
                },
            },
            "contract_status": "executed",
            "marker_exists": True,
            "opencode_run_launched": True,
            "proof_class": "local-simulation",
            "chat_output_is_evidence": False,
            "semantic_gate": False,
            "translation_coverage_numerator": 0,
            "boundary": "OpenCode preflight proves GLM-5.1 command-contract availability only.",
        }

        boundary = runner.public_packet_opencode_patch_boundary(
            {
                "before_after_repair_exhibit": {
                    "sources": [
                        {
                            "before_after_units": [
                                {
                                    "patch_origin": {
                                        "source": "accepted_safe_evidence",
                                        "opencode_session_bound": False,
                                    }
                                }
                            ]
                        }
                    ]
                },
                "publication_manifest": {
                    "published_artifact_refs": [
                        {
                            "artifact_name": "opencode_safety_transform_attempt",
                            "path": repo_relative(attempt_path),
                            "sha256": runner.validator.sha256_file(attempt_path),
                            "status": "present",
                        }
                    ]
                },
                "opencode_runtime": {
                    "enabled_entrypoint_count": 1,
                    "preflight_proof_summary": preflight_summary,
                },
            },
            repo_root=REPO_ROOT,
        )

        self.assertEqual(boundary["report_kind"], "opencode-patch-boundary")
        self.assertTrue(boundary["opencode_runtime_enabled"])
        self.assertEqual(boundary["before_after_patch_sources"], ["accepted_safe_evidence"])
        self.assertEqual(boundary["before_after_opencode_session_bound_count"], 0)
        self.assertFalse(boundary["chat_output_is_evidence"])
        self.assertFalse(boundary["semantic_gate"])
        self.assertEqual(boundary["translation_coverage_numerator"], 0)
        self.assertEqual(boundary["opencode_safety_transform_attempt"]["status"], "present")
        self.assertEqual(boundary["opencode_safety_transform_attempt"]["attempt_status"], "accepted")
        self.assertEqual(boundary["opencode_safety_transform_attempt"]["accepted_retry_hint_status"], "not_exercised")
        self.assertEqual(boundary["opencode_safety_transform_attempt"]["rollback_ref_count"], 0)
        self.assertEqual(boundary["opencode_safety_transform_attempt"]["max_repair_rounds"], 5)
        self.assertEqual(boundary["opencode_preflight_proof_summary"], preflight_summary)

    def test_public_packet_opencode_patch_boundary_summarizes_unit_retry_hint(self) -> None:
        from validation.tools import run_judge_entrypoints as runner

        temp_dir = Path(tempfile.mkdtemp(prefix="opencode-unit-boundary-", dir=REPO_ROOT / "target"))
        attempt_path = temp_dir / "workers" / "worker-a" / "harness" / "opencode-safety-transform-attempt-1.json"
        attempt_path.parent.mkdir(parents=True, exist_ok=True)
        attempt_payload = {
            "status": "accepted",
            "attempt_contract": {"max_repair_rounds": 5},
            "safety_transform_units": [
                {
                    "status": "converged",
                    "accepted_retry_hint": {"status": "not_exercised"},
                    "rounds": [{"round": 1}],
                }
            ],
        }
        attempt_path.write_text(json.dumps(attempt_payload, sort_keys=True) + "\n", encoding="utf-8")

        summary = runner.public_packet_opencode_attempt_summary(
            {
                "path": repo_relative(attempt_path),
                "sha256": runner.validator.sha256_file(attempt_path),
                "status": "present",
            },
            repo_root=REPO_ROOT,
        )

        self.assertEqual(summary["artifact_read_status"], "passed")
        self.assertEqual(summary["attempt_status"], "accepted")
        self.assertEqual(summary["accepted_retry_hint_status"], "not_exercised")
        self.assertEqual(summary["accepted_retry_hint_statuses"], ["not_exercised"])
        self.assertEqual(summary["rollback_ref_count"], 0)
        self.assertEqual(summary["round_count"], 1)
        self.assertEqual(summary["unit_count"], 1)

    def test_release_notes_failure_does_not_mark_notes_present(self) -> None:
        from validation.tools import run_judge_entrypoints as runner

        temp_dir = Path(tempfile.mkdtemp(prefix="run-judge-notes-fail-", dir=REPO_ROOT / "target"))
        config_path = temp_dir / "flashdb-harness.json"
        out_path = temp_dir / "summary" / "judge-entrypoints-run-report.json"
        config_path.write_text(
            json.dumps(
                {
                    "entrypoints": [
                        {
                            "id": "competition_environment_smoke",
                            "command": "python3 -B validation/tools/run_competition_smoke.py",
                        }
                    ],
                },
                sort_keys=True,
            )
            + "\n",
            encoding="utf-8",
        )

        def fake_runner(argv: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
            return subprocess.CompletedProcess(argv, 0, stdout="ok\n", stderr="")

        def fake_write_readiness(result: dict, path: Path, *, repo_root: Path) -> dict:
            path.parent.mkdir(parents=True, exist_ok=True)
            payload = {
                "schema_version": 1,
                "report_kind": "judge-entrypoints-readiness",
                "status": result["status"],
            }
            path.write_text(json.dumps(payload, sort_keys=True) + "\n", encoding="utf-8")
            return payload

        with patch.object(runner.validator, "validate_config", side_effect=[{"status": "passed"}, {"status": "passed"}]):
            with patch.object(runner.validator, "write_readiness_report", side_effect=fake_write_readiness):
                with patch.object(
                    runner.milestone_release_notes,
                    "build_release_notes",
                    side_effect=SystemExit("release note boundary failed"),
                ):
                    with self.assertRaises(SystemExit):
                        runner.run_judge_entrypoints(
                            config_path=config_path,
                            entrypoint_ids=[],
                            out_path=out_path,
                            command_runner=fake_runner,
                            repo_root=REPO_ROOT,
                        )

        persisted = json.loads(out_path.read_text(encoding="utf-8"))
        self.assertEqual(persisted["milestone_release_notes"]["status"], "derived_after_bundle")
        self.assertNotEqual(persisted["milestone_release_notes"]["status"], "present")
        self.assertNotIn("sha256", persisted["milestone_release_notes"])
        self.assertEqual(persisted["milestone_release_notes"]["hash_boundary"], "release_notes_hashes_the_bundle")
        self.assertEqual(persisted["public_release_packet"]["status"], "derived_after_release_notes")
        self.assertFalse((out_path.parent / "public-release-packet.json").exists())
        self.assertTrue((out_path.parent / "judge-milestone-bundle.json").is_file())
        self.assertFalse((out_path.parent / "milestone-release-notes.md").exists())

    def test_public_release_packet_validation_failure_fails_closed(self) -> None:
        from validation.tools import run_judge_entrypoints as runner

        temp_dir = Path(tempfile.mkdtemp(prefix="run-judge-packet-fail-", dir=REPO_ROOT / "target"))
        config_path = temp_dir / "flashdb-harness.json"
        out_path = temp_dir / "summary" / "judge-entrypoints-run-report.json"
        config_path.write_text(
            json.dumps(
                {
                    "entrypoints": [
                        {
                            "id": "competition_environment_smoke",
                            "command": "python3 -B validation/tools/run_competition_smoke.py",
                        }
                    ],
                },
                sort_keys=True,
            )
            + "\n",
            encoding="utf-8",
        )

        def fake_runner(argv: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
            return subprocess.CompletedProcess(argv, 0, stdout="ok\n", stderr="")

        def fake_write_readiness(result: dict, path: Path, *, repo_root: Path) -> dict:
            path.parent.mkdir(parents=True, exist_ok=True)
            payload = {
                "schema_version": 1,
                "report_kind": "judge-entrypoints-readiness",
                "status": result["status"],
            }
            path.write_text(json.dumps(payload, sort_keys=True) + "\n", encoding="utf-8")
            return payload

        with patch.object(runner.validator, "validate_config", side_effect=[{"status": "passed"}, {"status": "passed"}]):
            with patch.object(runner.validator, "write_readiness_report", side_effect=fake_write_readiness):
                with patch.object(
                    runner.validate_public_release_packet,
                    "validate_packet",
                    return_value={"status": "failed", "errors": ["packet overclaim"]},
                ):
                    with self.assertRaisesRegex(SystemExit, "public release packet validation failed"):
                        runner.run_judge_entrypoints(
                            config_path=config_path,
                            entrypoint_ids=[],
                            out_path=out_path,
                            command_runner=fake_runner,
                            repo_root=REPO_ROOT,
                        )

        self.assertTrue((out_path.parent / "public-release-packet.json").is_file())

    def test_dry_run_plans_without_executing_or_validating(self) -> None:
        from validation.tools import run_judge_entrypoints as runner

        temp_dir = Path(tempfile.mkdtemp(prefix="run-judge-dry-", dir=REPO_ROOT / "target"))
        config_path = temp_dir / "flashdb-harness.json"
        out_path = temp_dir / "summary" / "judge-entrypoints-run-report.json"
        config_path.write_text(
            json.dumps(
                {
                    "entrypoints": [
                        {
                            "id": "before_after_judge_demo",
                            "command": "python3 -B -m validation.tools.judge_demo",
                        }
                    ],
                },
                sort_keys=True,
            )
            + "\n",
            encoding="utf-8",
        )

        def fail_if_called(*args: object, **kwargs: object) -> subprocess.CompletedProcess[str]:
            raise AssertionError("dry-run must not execute commands")

        with patch.object(runner.validator, "validate_config", return_value={"status": "passed"}) as validate_config:
            report = runner.run_judge_entrypoints(
                config_path=config_path,
                entrypoint_ids=[],
                out_path=out_path,
                dry_run=True,
                command_runner=fail_if_called,
                repo_root=REPO_ROOT,
            )

        validate_config.assert_called_once_with(config_path, require_local_artifacts=False, repo_root=REPO_ROOT)
        self.assertEqual(report["status"], "planned")
        self.assertEqual(report["validation"]["status"], "skipped")
        self.assertEqual(report["validation"]["reason"], "dry_run")
        self.assertEqual(report["entrypoints"][0]["status"], "planned")
        self.assertIsNone(report["entrypoints"][0]["exit_code"])
        self.assertEqual(report["entrypoints"][0]["logs"]["stdout"]["status"], "missing")
        archive = report["competition_config_archive"]
        self.assertEqual(archive["report_kind"], "competition-config-archive")
        self.assertEqual(archive["root"], "config/competition-env")
        self.assertEqual(archive["status"], "present")
        self.assertIn("config/competition-env/environment.json", archive["files"])
        self.assertIn("config/competition-env/judge-entrypoints/flashdb-harness.json", archive["files"])
        self.assertIn("config/competition-env/review-checklists/flashdb-harness-internal-review.json", archive["files"])
        self.assertIn("config/competition-env/planned-batches/flashdb-fdb-utils-before-after.json", archive["files"])
        self.assertIn("requirements.txt", archive["external_refs"])
        self.assertIn("opencode.json", archive["external_refs"])
        self.assertIn("scripts/bootstrap_flashdb_sources.sh", archive["external_refs"])
        self.assertIn(".github/workflows/core-translator-validation-ci.yml", archive["external_refs"])
        self.assertIn(".codex/skills/c2rust-migration/SKILL.md", archive["external_refs"])
        for file_ref in archive["files"].values():
            self.assertEqual(file_ref["status"], "present")
            self.assertRegex(file_ref["sha256"], r"^[0-9a-f]{64}$")
        for external_ref in archive["external_refs"].values():
            self.assertEqual(external_ref["status"], "present")
            self.assertRegex(external_ref["sha256"], r"^[0-9a-f]{64}$")
        self.assertEqual(report["summary"]["competition_config_archive"]["file_count"], archive["file_count"])
        self.assertTrue(out_path.is_file())

    def test_dry_run_does_not_reference_stale_logs(self) -> None:
        from validation.tools import run_judge_entrypoints as runner

        temp_dir = Path(tempfile.mkdtemp(prefix="run-judge-dry-stale-logs-", dir=REPO_ROOT / "target"))
        config_path = temp_dir / "flashdb-harness.json"
        out_path = temp_dir / "summary" / "judge-entrypoints-run-report.json"
        log_dir = out_path.parent / "logs"
        log_dir.mkdir(parents=True, exist_ok=True)
        (log_dir / "before_after_judge_demo.stdout.log").write_text("old stdout\n", encoding="utf-8")
        (log_dir / "before_after_judge_demo.stderr.log").write_text("old stderr\n", encoding="utf-8")
        config_path.write_text(
            json.dumps(
                {
                    "entrypoints": [
                        {
                            "id": "before_after_judge_demo",
                            "command": "python3 -B -m validation.tools.judge_demo",
                        }
                    ],
                },
                sort_keys=True,
            )
            + "\n",
            encoding="utf-8",
        )

        def fail_if_called(*args: object, **kwargs: object) -> subprocess.CompletedProcess[str]:
            raise AssertionError("dry-run must not execute commands")

        with patch.object(runner.validator, "validate_config", return_value={"status": "passed"}):
            report = runner.run_judge_entrypoints(
                config_path=config_path,
                entrypoint_ids=[],
                out_path=out_path,
                dry_run=True,
                command_runner=fail_if_called,
                repo_root=REPO_ROOT,
            )

        self.assertEqual(report["status"], "planned")
        stdout_ref = report["entrypoints"][0]["logs"]["stdout"]
        stderr_ref = report["entrypoints"][0]["logs"]["stderr"]
        self.assertEqual(stdout_ref["status"], "missing")
        self.assertEqual(stderr_ref["status"], "missing")
        self.assertNotIn("sha256", stdout_ref)
        self.assertNotIn("sha256", stderr_ref)

    def test_dry_run_removes_stale_publishable_artifacts(self) -> None:
        from validation.tools import run_judge_entrypoints as runner

        temp_dir = Path(tempfile.mkdtemp(prefix="run-judge-dry-stale-", dir=REPO_ROOT / "target"))
        config_path = temp_dir / "flashdb-harness.json"
        out_path = temp_dir / "summary" / "judge-entrypoints-run-report.json"
        config_path.write_text(
            json.dumps(
                {
                    "entrypoints": [
                        {
                            "id": "before_after_judge_demo",
                            "command": "python3 -B -m validation.tools.judge_demo",
                        }
                    ],
                },
                sort_keys=True,
            )
            + "\n",
            encoding="utf-8",
        )
        out_path.parent.mkdir(parents=True, exist_ok=True)
        stale_artifacts = [
            "judge-entrypoints-readiness.json",
            "judge-milestone-bundle.json",
            "milestone-release-notes.md",
            "public-release-packet.json",
            "selected-entrypoints-validation-config.json",
        ]
        for artifact_name in stale_artifacts:
            (out_path.parent / artifact_name).write_text('{"status":"stale"}\n', encoding="utf-8")
        stale_archive_dir = out_path.parent / "competition-config-archive"
        stale_archive_dir.mkdir()
        (stale_archive_dir / "manifest.json").write_text('{"status":"stale"}\n', encoding="utf-8")

        def fail_if_called(*args: object, **kwargs: object) -> subprocess.CompletedProcess[str]:
            raise AssertionError("dry-run must not execute commands")

        with patch.object(runner.validator, "validate_config", return_value={"status": "passed"}):
            report = runner.run_judge_entrypoints(
                config_path=config_path,
                entrypoint_ids=[],
                out_path=out_path,
                dry_run=True,
                command_runner=fail_if_called,
                repo_root=REPO_ROOT,
            )

        self.assertEqual(report["status"], "planned")
        for artifact_name in stale_artifacts:
            self.assertFalse((out_path.parent / artifact_name).exists(), artifact_name)
        self.assertFalse(stale_archive_dir.exists())
        self.assertNotIn("materialized_manifest", report["competition_config_archive"])

    def test_dry_run_preflight_failure_is_not_planned(self) -> None:
        from validation.tools import run_judge_entrypoints as runner

        temp_dir = Path(tempfile.mkdtemp(prefix="run-judge-dry-bad-", dir=REPO_ROOT / "target"))
        config_path = temp_dir / "flashdb-harness.json"
        out_path = temp_dir / "summary" / "judge-entrypoints-run-report.json"
        config_path.write_text(
            json.dumps(
                {
                    "entrypoints": [
                        {
                            "id": "bad_entrypoint",
                            "command": "python -m validation.tools.judge_demo",
                        }
                    ],
                },
                sort_keys=True,
            )
            + "\n",
            encoding="utf-8",
        )

        def fail_if_called(*args: object, **kwargs: object) -> subprocess.CompletedProcess[str]:
            raise AssertionError("preflight failure must not execute commands")

        with patch.object(
            runner.validator,
            "validate_config",
            return_value={"status": "failed", "errors": ["entrypoint command must use portable python3 -B"]},
        ):
            report = runner.run_judge_entrypoints(
                config_path=config_path,
                entrypoint_ids=[],
                out_path=out_path,
                dry_run=True,
                command_runner=fail_if_called,
                repo_root=REPO_ROOT,
            )

        self.assertEqual(report["status"], "failed")
        self.assertEqual(report["entrypoint_count"], 0)
        self.assertEqual(report["validation"]["reason"], "preflight_failed")
        self.assertTrue(out_path.is_file())

    def test_failed_command_skips_validator_and_readiness(self) -> None:
        from validation.tools import run_judge_entrypoints as runner

        temp_dir = Path(tempfile.mkdtemp(prefix="run-judge-fail-", dir=REPO_ROOT / "target"))
        config_path = temp_dir / "flashdb-harness.json"
        out_path = temp_dir / "summary" / "judge-entrypoints-run-report.json"
        config_path.write_text(
            json.dumps(
                {
                    "entrypoints": [
                        {
                            "id": "before_after_judge_demo",
                            "command": "python3 -B -m validation.tools.judge_demo",
                        }
                    ],
                },
                sort_keys=True,
            )
            + "\n",
            encoding="utf-8",
        )

        def failing_runner(argv: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
            return subprocess.CompletedProcess(argv, 2, stdout="bad\n", stderr="failed\n")

        with patch.object(runner.validator, "validate_config", return_value={"status": "passed"}) as validate_config:
            report = runner.run_judge_entrypoints(
                config_path=config_path,
                entrypoint_ids=[],
                out_path=out_path,
                command_runner=failing_runner,
                repo_root=REPO_ROOT,
            )

        validate_config.assert_called_once_with(config_path, require_local_artifacts=False, repo_root=REPO_ROOT)
        self.assertEqual(report["status"], "failed")
        self.assertEqual(report["validation"]["status"], "skipped")
        self.assertEqual(report["validation"]["reason"], "failed_command")
        self.assertIsNone(report["readiness_report"])
        self.assertEqual(report["entrypoints"][0]["exit_code"], 2)
        stdout_log = out_path.parent / "logs" / "before_after_judge_demo.stdout.log"
        stderr_log = out_path.parent / "logs" / "before_after_judge_demo.stderr.log"
        self.assertTrue(stdout_log.is_file())
        self.assertTrue(stderr_log.is_file())
        self.assertEqual(report["entrypoints"][0]["logs"]["stdout"]["sha256"], runner.validator.sha256_file(stdout_log))
        self.assertEqual(report["entrypoints"][0]["logs"]["stderr"]["sha256"], runner.validator.sha256_file(stderr_log))

    def test_entrypoint_command_receives_timeout_and_records_policy(self) -> None:
        from validation.tools import run_judge_entrypoints as runner

        temp_dir = Path(tempfile.mkdtemp(prefix="run-judge-timeout-policy-", dir=REPO_ROOT / "target"))
        config_path = temp_dir / "flashdb-harness.json"
        out_path = temp_dir / "summary" / "judge-entrypoints-run-report.json"
        config_path.write_text(
            json.dumps(
                {
                    "entrypoints": [
                        {
                            "id": "before_after_judge_demo",
                            "command": "python3 -B -m validation.tools.judge_demo",
                        }
                    ],
                },
                sort_keys=True,
            )
            + "\n",
            encoding="utf-8",
        )
        seen_kwargs: dict[str, object] = {}

        def passing_runner(argv: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
            seen_kwargs.update(kwargs)
            return subprocess.CompletedProcess(argv, 0, stdout="ok\n", stderr="")

        def fake_write_readiness(result: dict, path: Path, *, repo_root: Path) -> dict:
            path.parent.mkdir(parents=True, exist_ok=True)
            payload = {
                "schema_version": 1,
                "report_kind": "judge-entrypoints-readiness",
                "status": result["status"],
            }
            path.write_text(json.dumps(payload, sort_keys=True) + "\n", encoding="utf-8")
            return payload

        with patch.object(
            runner.validator,
            "validate_config",
            side_effect=[{"status": "passed"}, {"status": "passed"}],
        ):
            with patch.object(runner.validator, "write_readiness_report", side_effect=fake_write_readiness):
                report = runner.run_judge_entrypoints(
                    config_path=config_path,
                    entrypoint_ids=[],
                    out_path=out_path,
                    command_runner=passing_runner,
                    timeout_seconds=17,
                    repo_root=REPO_ROOT,
                )

        entrypoint = report["entrypoints"][0]
        self.assertEqual(seen_kwargs["cwd"], REPO_ROOT.resolve())
        self.assertIs(seen_kwargs["text"], True)
        self.assertIs(seen_kwargs["capture_output"], True)
        self.assertEqual(seen_kwargs["timeout"], 17)
        self.assertEqual(entrypoint["timeout_seconds"], 17)
        self.assertEqual(entrypoint["timeout_policy"]["timeout_seconds"], 17)
        self.assertEqual(entrypoint["timeout_policy"]["timeout_exit_code"], 124)
        self.assertEqual(entrypoint["timeout_policy"]["scope"], "entrypoint_command")

    def test_entrypoint_timeout_expired_records_124_and_process_timeout(self) -> None:
        from validation.tools import run_judge_entrypoints as runner

        temp_dir = Path(tempfile.mkdtemp(prefix="run-judge-timeout-expired-", dir=REPO_ROOT / "target"))
        config_path = temp_dir / "flashdb-harness.json"
        out_path = temp_dir / "summary" / "judge-entrypoints-run-report.json"
        config_path.write_text(
            json.dumps(
                {
                    "entrypoints": [
                        {
                            "id": "before_after_judge_demo",
                            "command": "python3 -B -m validation.tools.judge_demo",
                        }
                    ],
                },
                sort_keys=True,
            )
            + "\n",
            encoding="utf-8",
        )
        seen_kwargs: dict[str, object] = {}

        def timeout_runner(argv: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
            seen_kwargs.update(kwargs)
            raise subprocess.TimeoutExpired(
                cmd=argv,
                timeout=kwargs.get("timeout"),
                output="partial stdout\n",
                stderr="partial stderr\n",
            )

        with patch.object(runner.validator, "validate_config", return_value={"status": "passed"}):
            report = runner.run_judge_entrypoints(
                config_path=config_path,
                entrypoint_ids=[],
                out_path=out_path,
                command_runner=timeout_runner,
                timeout_seconds=19,
                repo_root=REPO_ROOT,
            )

        stdout_log = out_path.parent / "logs" / "before_after_judge_demo.stdout.log"
        stderr_log = out_path.parent / "logs" / "before_after_judge_demo.stderr.log"
        entrypoint = report["entrypoints"][0]
        self.assertEqual(seen_kwargs["timeout"], 19)
        self.assertEqual(report["status"], "failed")
        self.assertEqual(report["validation"], {"status": "skipped", "reason": "failed_command"})
        self.assertEqual(entrypoint["exit_code"], 124)
        self.assertEqual(entrypoint["status"], "failed")
        self.assertEqual(entrypoint["root_cause_key"], "process_timeout")
        self.assertEqual(entrypoint["error"]["type"], "TimeoutExpired")
        self.assertEqual(entrypoint["timeout_seconds"], 19)
        self.assertIn("partial stdout", stdout_log.read_text(encoding="utf-8"))
        self.assertIn("partial stderr", stderr_log.read_text(encoding="utf-8"))
        self.assertIn("TimeoutExpired", stderr_log.read_text(encoding="utf-8"))
        self.assertEqual(entrypoint["logs"]["stdout"]["sha256"], runner.validator.sha256_file(stdout_log))
        self.assertEqual(entrypoint["logs"]["stderr"]["sha256"], runner.validator.sha256_file(stderr_log))

    def test_write_run_report_is_atomic_when_replace_fails(self) -> None:
        from validation.tools import run_judge_entrypoints as runner

        temp_dir = Path(tempfile.mkdtemp(prefix="run-judge-atomic-report-", dir=REPO_ROOT / "target"))
        out_path = temp_dir / "summary" / "judge-entrypoints-run-report.json"
        out_path.parent.mkdir(parents=True, exist_ok=True)
        old_report = '{"status":"old"}\n'
        out_path.write_text(old_report, encoding="utf-8")

        with patch.object(runner.os, "replace", side_effect=OSError("simulated replace failure")):
            with self.assertRaisesRegex(OSError, "simulated replace failure"):
                runner.write_run_report(
                    out_path=out_path,
                    status="failed",
                    dry_run=True,
                    config_ref={"path": "config.json", "status": "present"},
                    configured_entrypoint_count=0,
                    config_archive={"status": "present"},
                    command_results=[],
                    preflight_validation={"status": "passed"},
                    validation={"status": "skipped", "reason": "dry_run"},
                    readiness_ref=None,
                )

        self.assertEqual(out_path.read_text(encoding="utf-8"), old_report)
        self.assertEqual(list(out_path.parent.glob(".judge-entrypoints-run-report.json.*.tmp")), [])

    def test_command_launch_exception_writes_failed_report_and_hashed_logs(self) -> None:
        from validation.tools import run_judge_entrypoints as runner

        temp_dir = Path(tempfile.mkdtemp(prefix="run-judge-exception-", dir=REPO_ROOT / "target"))
        config_path = temp_dir / "flashdb-harness.json"
        out_path = temp_dir / "summary" / "judge-entrypoints-run-report.json"
        config_path.write_text(
            json.dumps(
                {
                    "entrypoints": [
                        {
                            "id": "before_after_judge_demo",
                            "command": "python3 -B -m validation.tools.judge_demo",
                        }
                    ],
                },
                sort_keys=True,
            )
            + "\n",
            encoding="utf-8",
        )

        def raising_runner(argv: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
            raise FileNotFoundError("python executable missing")

        with patch.object(runner.validator, "validate_config", return_value={"status": "passed"}):
            report = runner.run_judge_entrypoints(
                config_path=config_path,
                entrypoint_ids=[],
                out_path=out_path,
                command_runner=raising_runner,
                repo_root=REPO_ROOT,
            )

        stderr_log = out_path.parent / "logs" / "before_after_judge_demo.stderr.log"
        self.assertEqual(report["status"], "failed")
        self.assertEqual(report["entrypoints"][0]["exit_code"], 127)
        self.assertEqual(report["entrypoints"][0]["error"]["type"], "FileNotFoundError")
        self.assertIn("python executable missing", stderr_log.read_text(encoding="utf-8"))
        self.assertEqual(report["entrypoints"][0]["logs"]["stderr"]["sha256"], runner.validator.sha256_file(stderr_log))

    def test_malformed_entrypoint_command_writes_failed_report(self) -> None:
        from validation.tools import run_judge_entrypoints as runner

        temp_dir = Path(tempfile.mkdtemp(prefix="run-judge-bad-command-", dir=REPO_ROOT / "target"))
        config_path = temp_dir / "flashdb-harness.json"
        out_path = temp_dir / "summary" / "judge-entrypoints-run-report.json"
        config_path.write_text(
            json.dumps(
                {
                    "entrypoints": [
                        {
                            "id": "bad_entrypoint",
                            "command": 'python3 -B -m validation.tools.judge_demo "unterminated',
                        }
                    ],
                },
                sort_keys=True,
            )
            + "\n",
            encoding="utf-8",
        )

        def fail_if_called(*args: object, **kwargs: object) -> subprocess.CompletedProcess[str]:
            raise AssertionError("malformed command must not execute")

        with patch.object(runner.validator, "validate_config", return_value={"status": "passed"}) as validate_config:
            report = runner.run_judge_entrypoints(
                config_path=config_path,
                entrypoint_ids=[],
                out_path=out_path,
                command_runner=fail_if_called,
                repo_root=REPO_ROOT,
            )

        validate_config.assert_called_once_with(config_path, require_local_artifacts=False, repo_root=REPO_ROOT)
        self.assertEqual(report["status"], "failed")
        self.assertEqual(report["validation"], {"status": "skipped", "reason": "failed_command"})
        self.assertTrue(out_path.is_file())
        self.assertEqual(report["entrypoints"][0]["id"], "bad_entrypoint")
        self.assertEqual(report["entrypoints"][0]["status"], "failed")
        self.assertEqual(report["entrypoints"][0]["exit_code"], 2)
        self.assertEqual(report["entrypoints"][0]["root_cause_key"], "invalid_entrypoint_command")
        self.assertEqual(report["entrypoints"][0]["error"]["type"], "ValueError")
        self.assertIsNone(report["readiness_report"])
        self.assertEqual(report["entrypoints"][0]["logs"]["stdout"]["status"], "missing")
        self.assertEqual(report["entrypoints"][0]["logs"]["stderr"]["status"], "missing")

    def test_skipped_validation_status_is_not_success(self) -> None:
        from validation.tools import run_judge_entrypoints as runner

        temp_dir = Path(tempfile.mkdtemp(prefix="run-judge-skip-", dir=REPO_ROOT / "target"))
        config_path = temp_dir / "flashdb-harness.json"
        out_path = temp_dir / "summary" / "judge-entrypoints-run-report.json"
        config_path.write_text(
            json.dumps(
                {
                    "entrypoints": [
                        {
                            "id": "before_after_judge_demo",
                            "command": "python3 -B -m validation.tools.judge_demo",
                        }
                    ],
                },
                sort_keys=True,
            )
            + "\n",
            encoding="utf-8",
        )

        def passing_runner(argv: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
            return subprocess.CompletedProcess(argv, 0, stdout="", stderr="")

        with patch.object(
            runner.validator,
            "validate_config",
            side_effect=[{"status": "passed"}, {"status": "skipped"}],
        ):
            report = runner.run_judge_entrypoints(
                config_path=config_path,
                entrypoint_ids=[],
                out_path=out_path,
                command_runner=passing_runner,
                repo_root=REPO_ROOT,
            )

        self.assertEqual(report["status"], "failed")
        self.assertEqual(report["validation"]["status"], "skipped")

    def test_unknown_entrypoint_id_fails_closed(self) -> None:
        from validation.tools import run_judge_entrypoints as runner

        with self.assertRaisesRegex(SystemExit, "unknown judge entrypoint id"):
            runner.select_entrypoints(
                {"entrypoints": [{"id": "known", "command": "python3 -B -m known"}]},
                ["missing"],
            )

    def test_run_unknown_entrypoint_id_fails_closed_before_command(self) -> None:
        from validation.tools import run_judge_entrypoints as runner

        temp_dir = Path(tempfile.mkdtemp(prefix="run-judge-unknown-", dir=REPO_ROOT / "target"))
        config_path = temp_dir / "flashdb-harness.json"
        out_path = temp_dir / "summary" / "judge-entrypoints-run-report.json"
        config_path.write_text(
            json.dumps(
                {
                    "entrypoints": [
                        {
                            "id": "known",
                            "command": "python3 -B -m validation.tools.judge_demo",
                        }
                    ],
                },
                sort_keys=True,
            )
            + "\n",
            encoding="utf-8",
        )

        def fail_if_called(*args: object, **kwargs: object) -> subprocess.CompletedProcess[str]:
            raise AssertionError("unknown entrypoint must not execute commands")

        with patch.object(runner.validator, "validate_config", return_value={"status": "passed"}):
            report = runner.run_judge_entrypoints(
                config_path=config_path,
                entrypoint_ids=["missing"],
                out_path=out_path,
                command_runner=fail_if_called,
                repo_root=REPO_ROOT,
            )

        self.assertEqual(report["status"], "failed")
        self.assertEqual(report["entrypoint_count"], 0)
        self.assertEqual(report["validation"]["reason"], "entrypoint_selection_failed")
        self.assertTrue(out_path.is_file())

    def test_artifact_ref_marks_missing_without_hashing(self) -> None:
        from validation.tools import run_judge_entrypoints as runner

        ref = runner.artifact_ref(REPO_ROOT / "target" / "missing-judge-entrypoint-artifact.json", repo_root=REPO_ROOT)
        self.assertEqual(ref["status"], "missing")
        self.assertNotIn("sha256", ref)

    def test_core_validation_ci_runs_judge_entrypoint_runner_tests(self) -> None:
        workflow = (REPO_ROOT / ".github/workflows/core-translator-validation-ci.yml").read_text(encoding="utf-8")
        self.assertIn("validation.tools.test_run_judge_entrypoints", workflow)
        self.assertIn("validation.tools.run_judge_entrypoints --dry-run", workflow)
        self.assertIn("git clone -c core.autocrlf=false --no-local", workflow)
        self.assertIn("target/repro-clone-lf-ci", workflow)
        self.assertIn(
            "validation.tools.validate_judge_entrypoints --config config/competition-env/judge-entrypoints/flashdb-harness.json",
            workflow,
        )


if __name__ == "__main__":
    unittest.main()
