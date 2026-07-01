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
                            "command": "python -B -m validation.tools.judge_demo --run-id selected",
                        },
                        {
                            "id": "multi_worker_evaluate_profile",
                            "purpose": "harness-architecture-multi-worker-evaluate",
                            "command": "python -B -m validation.tools.opencode_agent_harness evaluate",
                        },
                    ],
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
        self.assertEqual(report["summary"]["readiness"]["configured_count"], 2)
        self.assertEqual(report["summary"]["entrypoints"][0]["id"], "before_after_judge_demo")
        self.assertEqual(report["summary"]["entrypoints"][0]["proof_class"], "unknown")
        self.assertEqual(report["entrypoints"][0]["id"], "before_after_judge_demo")
        self.assertEqual(calls, [["python", "-B", "-m", "validation.tools.judge_demo", "--run-id", "selected"]])
        validate_config.assert_has_calls(
            [
                call(config_path, require_local_artifacts=False, repo_root=REPO_ROOT),
                call(config_path, require_local_artifacts=True, repo_root=REPO_ROOT),
            ]
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
        milestone_bundle = json.loads((out_path.parent / "judge-milestone-bundle.json").read_text(encoding="utf-8"))
        self.assertEqual(milestone_bundle["status"], "blocked")
        self.assertIn("not_all_entrypoints_executed", milestone_bundle["blockers"])
        self.assertEqual(milestone_bundle["judge_entrypoints_run_report"]["sha256"], runner.validator.sha256_file(out_path))
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
                            "command": "python -B validation/tools/run_competition_smoke.py",
                            "judge_focus": ["environment smoke", "semantic_gate=false"],
                            "expected_artifacts": {"competition_smoke_summary": "target/out/smoke.json"},
                        },
                        {
                            "id": "opencode_multi_worker_evaluate_profile",
                            "priority": 30,
                            "purpose": "harness-architecture-opencode-multi-worker-evaluate",
                            "proof_class": "local-simulation",
                            "run_id": "opencode-run",
                            "command": "python -B -m validation.tools.opencode_agent_harness evaluate",
                            "judge_focus": ["OpenCode multi-agent", "repair cap 5"],
                            "expected_artifacts": {"judge_evidence_index": "target/out/index.json"},
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

        with patch.object(runner.validator, "validate_config", side_effect=[{"status": "passed"}, {"status": "passed"}]):
            with patch.object(runner.validator, "write_readiness_report", return_value={"status": "passed"}):
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
        milestone_bundle = json.loads((out_path.parent / "judge-milestone-bundle.json").read_text(encoding="utf-8"))
        self.assertEqual(milestone_bundle["status"], "passed")
        self.assertTrue(milestone_bundle["summary"]["external_milestone_claim_ready"])
        self.assertFalse(milestone_bundle["claim_boundary"]["semantic_gate"])
        self.assertEqual(milestone_bundle["judge_entrypoints_run_report"]["sha256"], runner.validator.sha256_file(out_path))
        self.assertEqual(summary["readiness"]["executed_count"], 2)
        self.assertEqual(summary["readiness"]["configured_count"], 2)
        self.assertEqual(summary["readiness"]["validation_status"], "passed")
        self.assertEqual([entry["id"] for entry in summary["entrypoints"]], ["competition_environment_smoke", "opencode_multi_worker_evaluate_profile"])
        self.assertEqual(summary["entrypoints"][0]["judge_focus"], ["environment smoke", "semantic_gate=false"])
        self.assertEqual(summary["entrypoints"][1]["key_artifacts"], {"judge_evidence_index": "target/out/index.json"})
        persisted = json.loads(out_path.read_text(encoding="utf-8"))
        self.assertEqual(persisted["milestone_bundle"], report["milestone_bundle"])

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
                            "command": "python -B -m validation.tools.judge_demo",
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
        self.assertTrue(out_path.is_file())

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
            return_value={"status": "failed", "errors": ["entrypoint command must use python -B"]},
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
                            "command": "python -B -m validation.tools.judge_demo",
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
                            "command": "python -B -m validation.tools.judge_demo",
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
                            "command": "python -B -m validation.tools.judge_demo",
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
                {"entrypoints": [{"id": "known", "command": "python -B -m known"}]},
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
                            "command": "python -B -m validation.tools.judge_demo",
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


if __name__ == "__main__":
    unittest.main()
