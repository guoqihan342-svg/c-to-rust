import contextlib
import importlib.util
import io
import json
import re
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
SMOKE_RUNNER = REPO_ROOT / "validation" / "tools" / "run_competition_smoke.py"


def load_smoke_module():
    spec = importlib.util.spec_from_file_location("run_competition_smoke_under_test", SMOKE_RUNNER)
    if spec is None or spec.loader is None:
        raise AssertionError("could not load competition smoke module")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


LOCAL_ABSOLUTE_PATH = re.compile(r"(?:[A-Za-z]:[\\/]|/mnt/[A-Za-z]/|/home/|/Users/|/tmp/|/var/)")


def assert_no_local_absolute_command_arguments(testcase: unittest.TestCase, command_entries: list[dict]) -> None:
    for entry in command_entries:
        for argument in entry["command"]:
            if not isinstance(argument, str):
                continue
            testcase.assertNotRegex(argument, LOCAL_ABSOLUTE_PATH)
            testcase.assertFalse(Path(argument).is_absolute(), argument)


class FakeCommandRunner:
    def __init__(
        self,
        *,
        fail_commands_containing: set[str] | None = None,
        fail_stderr_by_marker: dict[str, str] | None = None,
        timeout_commands_containing: set[str] | None = None,
    ) -> None:
        self.commands: list[list[str]] = []
        self.kwargs: list[dict[str, object]] = []
        self.fail_commands_containing = fail_commands_containing or set()
        self.fail_stderr_by_marker = fail_stderr_by_marker or {}
        self.timeout_commands_containing = timeout_commands_containing or set()

    def __call__(self, command: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
        self.commands.append(command)
        self.kwargs.append(kwargs)
        command_text = " ".join(command)
        for marker in self.timeout_commands_containing:
            if marker in command_text:
                raise subprocess.TimeoutExpired(command, kwargs.get("timeout"), output="partial", stderr="timed out")
        for marker in self.fail_commands_containing:
            if marker in command_text:
                return subprocess.CompletedProcess(
                    command,
                    1,
                    "",
                    self.fail_stderr_by_marker.get(marker, f"failed {marker}"),
                )
        return subprocess.CompletedProcess(command, 0, "ok", "")


class RunCompetitionSmokeTests(unittest.TestCase):
    def test_smoke_runner_records_proof_class_deviations_and_common_gates(self) -> None:
        module = load_smoke_module()
        with tempfile.TemporaryDirectory(prefix="competition-smoke-test-") as tmp:
            out_root = Path(tmp) / "competition-smoke"
            fake_runner = FakeCommandRunner()

            result = module.run_competition_smoke(
                out_root=out_root,
                proof_class="local-simulation",
                command_runner=fake_runner,
                repo_root=REPO_ROOT,
                run_id="smoke-test",
            )

            self.assertEqual(result.exit_code, 0)
            command_texts = [" ".join(command) for command in fake_runner.commands]
            self.assertTrue(any("config/competition-env/env.sh" in text for text in command_texts))
            self.assertTrue(any("toolchain-check.sh" in text for text in command_texts))
            self.assertTrue(any("validate_auto_translation_evidence.py" in text for text in command_texts))
            self.assertTrue(any("verify_vendored_clang.py" in text for text in command_texts))
            self.assertTrue(any("evidence_governance.py" in text for text in command_texts))
            self.assertTrue(any("translator_coverage_matrix.py" in text for text in command_texts))
            self.assertTrue(any("milestone_release_report.py" in text for text in command_texts))
            self.assertTrue(any("-m unittest" in text for text in command_texts))

            summary = json.loads((out_root / "summary" / "competition-smoke-summary.json").read_text(encoding="utf-8"))
            self.assertEqual(summary["proof_class"], "local-simulation")
            self.assertEqual(summary["profile_id"], "huawei-competition-ubuntu-24.04")
            self.assertEqual(summary["final_gate"]["status"], "passed")
            self.assertGreaterEqual(len(summary["environment_deviations"]), 3)
            self.assertIn("os.kernel", {item["field"] for item in summary["environment_deviations"]})
            self.assertTrue(all(not Path(entry["log_path"]).is_absolute() for entry in summary["steps"]))
            self.assertTrue(all(entry["status"] == "passed" for entry in summary["steps"]))
            self.assertEqual(
                summary["vendored_clang_verification"]["path"],
                "summary/vendored-clang-verification.json",
            )
            self.assertEqual(
                summary["milestone_release_report"]["path"],
                "reports/milestone-release-report.json",
            )
            self.assertFalse(summary["milestone_release_report"]["semantic_acceptance_claim"])
            self.assertNotIn("slices", summary)

    def test_smoke_runner_requires_explicit_confirmation_for_competition_exact(self) -> None:
        module = load_smoke_module()
        with tempfile.TemporaryDirectory(prefix="competition-smoke-test-") as tmp:
            with self.assertRaises(SystemExit) as raised:
                module.run_competition_smoke(
                    out_root=Path(tmp) / "competition-smoke",
                    proof_class="competition-exact",
                    command_runner=FakeCommandRunner(),
                    repo_root=REPO_ROOT,
                    run_id="smoke-test",
                )

        self.assertIn("--confirm-competition-exact", str(raised.exception))

    def test_smoke_runner_marks_gate_failure_without_slice_count_claims(self) -> None:
        module = load_smoke_module()
        with tempfile.TemporaryDirectory(prefix="competition-smoke-test-") as tmp:
            out_root = Path(tmp) / "competition-smoke"
            result = module.run_competition_smoke(
                out_root=out_root,
                proof_class="local-simulation",
                command_runner=FakeCommandRunner(fail_commands_containing={"evidence_governance.py"}),
                repo_root=REPO_ROOT,
                run_id="smoke-test",
            )

            self.assertEqual(result.exit_code, 1)
            summary = json.loads((out_root / "summary" / "competition-smoke-summary.json").read_text(encoding="utf-8"))
            self.assertEqual(summary["final_gate"]["status"], "failed")
            self.assertNotIn("slices", summary)
            failed_steps = [step for step in summary["steps"] if step["status"] == "failed"]
            self.assertEqual([step["step"] for step in failed_steps], ["evidence-governance"])

    def test_non_exact_smoke_degrades_environment_drift_without_failing_gate(self) -> None:
        module = load_smoke_module()
        with tempfile.TemporaryDirectory(prefix="competition-smoke-test-") as tmp:
            out_root = Path(tmp) / "competition-smoke"
            result = module.run_competition_smoke(
                out_root=out_root,
                proof_class="local-simulation",
                command_runner=FakeCommandRunner(fail_commands_containing={"toolchain-check.sh"}),
                repo_root=REPO_ROOT,
                run_id="smoke-test",
            )

            self.assertEqual(result.exit_code, 0)
            summary = json.loads((out_root / "summary" / "competition-smoke-summary.json").read_text(encoding="utf-8"))
            self.assertEqual(summary["final_gate"]["status"], "passed")
            environment_step = next(step for step in summary["steps"] if step["step"] == "environment-check")
            self.assertEqual(environment_step["status"], "degraded")
            self.assertEqual(environment_step["proof_class_effect"], "exactness_blocker")

    def test_non_exact_proof_class_overclaim_fails_on_incompatible_environment(self) -> None:
        module = load_smoke_module()
        cases = [
            (
                "ci-approximation",
                {
                    "kind": "local-linux",
                    "detected_ci": False,
                    "detected_wsl": False,
                    "system": "Ubuntu",
                    "release": "5.10.0-182.0.0.95.r194_123.hce2.x86_64",
                    "version": "competition-host",
                    "machine": "x86_64",
                    "kernel": "5.10.0-182.0.0.95.r194_123.hce2.x86_64",
                    "python_version": "3.12.3",
                    "runner_name": "local",
                },
            ),
            (
                "wsl-local-simulation",
                {
                    "kind": "windows-local",
                    "detected_ci": False,
                    "detected_wsl": False,
                    "system": "Windows",
                    "release": "11",
                    "version": "10.0.26220",
                    "machine": "AMD64",
                    "kernel": "11",
                    "python_version": "3.14.2",
                    "runner_name": "local",
                },
            ),
        ]

        original_detect = module.detect_execution_environment
        try:
            for proof_class, environment in cases:
                with self.subTest(proof_class=proof_class):
                    module.detect_execution_environment = lambda environment=environment: dict(environment)
                    with tempfile.TemporaryDirectory(prefix="competition-smoke-test-") as tmp:
                        out_root = Path(tmp) / "competition-smoke"
                        result = module.run_competition_smoke(
                            out_root=out_root,
                            proof_class=proof_class,
                            command_runner=FakeCommandRunner(),
                            repo_root=REPO_ROOT,
                            run_id=f"smoke-{proof_class}-overclaim-test",
                        )

                        self.assertEqual(result.exit_code, 1)
                        summary = json.loads(
                            (out_root / "summary" / "competition-smoke-summary.json").read_text(encoding="utf-8")
                        )
                        self.assertEqual(summary["final_gate"]["status"], "failed")
                        self.assertIn("proof_class_incompatible_with_environment", summary["final_gate"]["reasons"])
        finally:
            module.detect_execution_environment = original_detect

    def test_required_c_compiler_missing_fails_all_proof_classes(self) -> None:
        module = load_smoke_module()
        with tempfile.TemporaryDirectory(prefix="competition-smoke-test-") as tmp:
            out_root = Path(tmp) / "competition-smoke"
            result = module.run_competition_smoke(
                out_root=out_root,
                proof_class="local-simulation",
                command_runner=FakeCommandRunner(
                    fail_commands_containing={"toolchain-check.sh"},
                    fail_stderr_by_marker={"toolchain-check.sh": "FAIL: gcc is not installed\n"},
                ),
                repo_root=REPO_ROOT,
                run_id="smoke-missing-compiler-test",
            )

            self.assertEqual(result.exit_code, 1)
            summary = json.loads((out_root / "summary" / "competition-smoke-summary.json").read_text(encoding="utf-8"))
            environment_step = next(step for step in summary["steps"] if step["step"] == "environment-check")
            self.assertEqual(environment_step["status"], "failed")
            self.assertEqual(environment_step["failure_class"], "required_c_compiler_missing")
            self.assertNotIn("proof_class_effect", environment_step)
            self.assertEqual(summary["final_gate"]["status"], "failed")
            self.assertIn("step_failed:environment-check", summary["final_gate"]["reasons"])
            self.assertIn("required_c_compiler_missing:environment-check", summary["final_gate"]["reasons"])

    def test_failed_vendored_clang_verification_keeps_clang_lane_unverified(self) -> None:
        module = load_smoke_module()
        with tempfile.TemporaryDirectory(prefix="competition-smoke-test-") as tmp:
            out_root = Path(tmp) / "competition-smoke"
            original_clang_source = module.clang_source
            try:
                module.clang_source = lambda _: "vendored"
                result = module.run_competition_smoke(
                    out_root=out_root,
                    proof_class="local-simulation",
                    command_runner=FakeCommandRunner(fail_commands_containing={"verify_vendored_clang.py"}),
                    repo_root=REPO_ROOT,
                    run_id="smoke-test",
                )
            finally:
                module.clang_source = original_clang_source

            summary = json.loads((out_root / "summary" / "competition-smoke-summary.json").read_text(encoding="utf-8"))
            self.assertEqual(result.exit_code, 1)
            self.assertEqual(summary["clang_source"], "vendored")
            self.assertFalse(summary["clang_lane_verified"])
            self.assertFalse(summary["competition_profile_match"]["clang_lane_verified"])

    def test_step_timeout_is_recorded_and_fails_closed(self) -> None:
        module = load_smoke_module()
        with tempfile.TemporaryDirectory(prefix="competition-smoke-test-") as tmp:
            out_root = Path(tmp) / "competition-smoke"
            fake_runner = FakeCommandRunner(timeout_commands_containing={"evidence_governance.py"})
            result = module.run_competition_smoke(
                out_root=out_root,
                proof_class="local-simulation",
                command_runner=fake_runner,
                repo_root=REPO_ROOT,
                run_id="smoke-timeout-test",
                timeout_seconds=3,
            )

            self.assertEqual(result.exit_code, 1)
            self.assertTrue(all(kwargs.get("timeout") == 3 for kwargs in fake_runner.kwargs))
            summary = json.loads((out_root / "summary" / "competition-smoke-summary.json").read_text(encoding="utf-8"))
            self.assertEqual(
                summary["timeout_policy"],
                {
                    "per_step_timeout_seconds": 3,
                    "timeout_exit_code": 124,
                    "timeout_is_final_gate_failure": True,
                },
            )
            self.assertEqual(summary["final_gate"]["status"], "failed")
            self.assertIn("step_failed:evidence-governance", summary["final_gate"]["reasons"])
            timed_out_step = next(step for step in summary["steps"] if step["step"] == "evidence-governance")
            self.assertEqual(timed_out_step["status"], "failed")
            self.assertTrue(timed_out_step["timed_out"])
            self.assertEqual(timed_out_step["timeout_seconds"], 3)
            command_log = out_root / "logs" / "commands.jsonl"
            log_entries = [json.loads(line) for line in command_log.read_text(encoding="utf-8").splitlines()]
            timed_out_log = next(entry for entry in log_entries if entry["step"] == "evidence-governance")
            self.assertTrue(timed_out_log["timed_out"])
            self.assertEqual(timed_out_log["timeout_seconds"], 3)

    def test_environment_check_timeout_fails_closed_for_non_exact_proof_class(self) -> None:
        module = load_smoke_module()
        with tempfile.TemporaryDirectory(prefix="competition-smoke-test-") as tmp:
            out_root = Path(tmp) / "competition-smoke"
            result = module.run_competition_smoke(
                out_root=out_root,
                proof_class="local-simulation",
                command_runner=FakeCommandRunner(timeout_commands_containing={"toolchain-check.sh"}),
                repo_root=REPO_ROOT,
                run_id="smoke-environment-timeout-test",
                timeout_seconds=3,
            )

            self.assertEqual(result.exit_code, 1)
            summary = json.loads((out_root / "summary" / "competition-smoke-summary.json").read_text(encoding="utf-8"))
            environment_step = next(step for step in summary["steps"] if step["step"] == "environment-check")
            self.assertEqual(environment_step["status"], "failed")
            self.assertTrue(environment_step["timed_out"])
            self.assertNotIn("proof_class_effect", environment_step)
            self.assertEqual(summary["final_gate"]["status"], "failed")
            self.assertIn("step_failed:environment-check", summary["final_gate"]["reasons"])

    def test_competition_exact_fails_on_environment_drift_even_when_confirmed(self) -> None:
        module = load_smoke_module()
        with tempfile.TemporaryDirectory(prefix="competition-smoke-test-") as tmp:
            out_root = Path(tmp) / "competition-smoke"
            result = module.run_competition_smoke(
                out_root=out_root,
                proof_class="competition-exact",
                confirm_competition_exact=True,
                command_runner=FakeCommandRunner(fail_commands_containing={"toolchain-check.sh"}),
                repo_root=REPO_ROOT,
                run_id="smoke-test",
            )

            self.assertEqual(result.exit_code, 1)
            summary = json.loads((out_root / "summary" / "competition-smoke-summary.json").read_text(encoding="utf-8"))
            self.assertEqual(summary["final_gate"]["status"], "failed")
            environment_step = next(step for step in summary["steps"] if step["step"] == "environment-check")
            self.assertEqual(environment_step["status"], "failed")

    def test_competition_exact_requires_vendored_clang_verification(self) -> None:
        module = load_smoke_module()
        with tempfile.TemporaryDirectory(prefix="competition-smoke-test-") as tmp:
            out_root = Path(tmp) / "competition-smoke"
            result = module.run_competition_smoke(
                out_root=out_root,
                proof_class="competition-exact",
                confirm_competition_exact=True,
                command_runner=FakeCommandRunner(fail_commands_containing={"--require-clang"}),
                repo_root=REPO_ROOT,
                run_id="smoke-test",
            )

            summary = json.loads((out_root / "summary" / "competition-smoke-summary.json").read_text(encoding="utf-8"))
            self.assertEqual(result.exit_code, 1)
            failed_steps = [step for step in summary["steps"] if step["status"] == "failed"]
            self.assertIn("vendored-clang-verification", [step["step"] for step in failed_steps])

    def test_competition_exact_fails_when_detected_environment_has_limiting_deviations(self) -> None:
        module = load_smoke_module()
        with tempfile.TemporaryDirectory(prefix="competition-smoke-test-") as tmp:
            out_root = Path(tmp) / "competition-smoke"
            original_detect = module.detect_execution_environment
            try:
                module.detect_execution_environment = lambda: {
                    "kind": "windows-local",
                    "detected_ci": False,
                    "detected_wsl": False,
                    "system": "Windows",
                    "release": "11",
                    "version": "10.0.26220",
                    "machine": "AMD64",
                    "kernel": "11",
                    "python_version": "3.14.2",
                    "runner_name": "local",
                }
                result = module.run_competition_smoke(
                    out_root=out_root,
                    proof_class="competition-exact",
                    confirm_competition_exact=True,
                    command_runner=FakeCommandRunner(),
                    repo_root=REPO_ROOT,
                    run_id="smoke-test",
                )
            finally:
                module.detect_execution_environment = original_detect

            summary = json.loads((out_root / "summary" / "competition-smoke-summary.json").read_text(encoding="utf-8"))
            limiting_deviations = [
                item for item in summary["environment_deviations"] if item["severity"] == "proof-class-limiting"
            ]
            self.assertTrue(limiting_deviations)
            self.assertEqual(result.exit_code, 1)
            self.assertEqual(summary["final_gate"]["status"], "failed")
            self.assertIn("proof_class_limited_by_environment", summary["final_gate"]["reasons"])

    def test_competition_exact_requires_host_attestation_even_when_profile_matches(self) -> None:
        module = load_smoke_module()
        profile = module.load_profile(REPO_ROOT)
        expected_os = profile["os"]
        expected_toolchain = profile["toolchain"]
        matching_environment = {
            "kind": "local-linux",
            "detected_ci": False,
            "detected_wsl": False,
            "system": expected_os["name"],
            "release": expected_os["kernel"],
            "version": "competition-host",
            "machine": "x86_64",
            "kernel": expected_os["kernel"],
            "python_version": expected_toolchain["python"],
            "runner_name": "local",
            "competition_exact_host_attested": False,
        }

        with tempfile.TemporaryDirectory(prefix="competition-smoke-test-") as tmp:
            out_root = Path(tmp) / "competition-smoke"
            original_detect = module.detect_execution_environment
            original_clang_source = module.clang_source
            try:
                module.detect_execution_environment = lambda: dict(matching_environment)
                module.clang_source = lambda _: "vendored"
                result = module.run_competition_smoke(
                    out_root=out_root,
                    proof_class="competition-exact",
                    confirm_competition_exact=True,
                    command_runner=FakeCommandRunner(),
                    repo_root=REPO_ROOT,
                    run_id="smoke-exact-attestation-test",
                )
            finally:
                module.detect_execution_environment = original_detect
                module.clang_source = original_clang_source

            self.assertEqual(result.exit_code, 1)
            summary = json.loads((out_root / "summary" / "competition-smoke-summary.json").read_text(encoding="utf-8"))
            self.assertEqual(summary["final_gate"]["status"], "failed")
            self.assertIn("proof_class_requires_exact_host_evidence", summary["final_gate"]["reasons"])

    def test_main_accepts_smoke_cli_args(self) -> None:
        module = load_smoke_module()
        calls: dict[str, object] = {}

        def fake_run_competition_smoke(**kwargs: object) -> object:
            calls.update(kwargs)
            return module.CompetitionSmokeResult(
                exit_code=0,
                summary_path=Path("summary.json"),
                summary={"status": "fake"},
            )

        original_argv = sys.argv
        original_runner = module.run_competition_smoke
        try:
            module.run_competition_smoke = fake_run_competition_smoke
            sys.argv = [
                "run_competition_smoke.py",
                "--proof-class",
                "wsl-local-simulation",
                "--out-root",
                "target/competition-smoke",
                "--run-id",
                "smoke-cli",
            ]
            with contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(module.main(), 0)
        finally:
            sys.argv = original_argv
            module.run_competition_smoke = original_runner

        self.assertEqual(calls["proof_class"], "wsl-local-simulation")
        self.assertEqual(calls["out_root"], Path("target/competition-smoke"))
        self.assertEqual(calls["run_id"], "smoke-cli")

    def test_core_ci_runs_competition_smoke_tests_and_gate(self) -> None:
        workflow = (REPO_ROOT / ".github" / "workflows" / "core-translator-validation-ci.yml").read_text(
            encoding="utf-8"
        )

        self.assertIn("validation.tools.test_run_competition_smoke", workflow)
        self.assertIn("validation.tools.test_verify_vendored_clang", workflow)
        self.assertIn("python validation/tools/run_competition_smoke.py", workflow)

    def test_clang_source_detects_windows_project_local_clang_exe(self) -> None:
        module = load_smoke_module()
        with tempfile.TemporaryDirectory(prefix="competition-smoke-test-") as tmp:
            repo_root = Path(tmp)
            clang = repo_root / "tools" / "llvm" / "bin" / "clang.exe"
            clang.parent.mkdir(parents=True)
            clang.write_text("", encoding="utf-8")

            self.assertEqual(module.clang_source(repo_root), "vendored")

    def test_slice_spec_outside_repo_is_rejected_before_command_log(self) -> None:
        module = load_smoke_module()
        with tempfile.TemporaryDirectory(prefix="competition-smoke-test-") as tmp:
            out_root = Path(tmp) / "competition-smoke"
            outside_slice_spec = Path(tmp) / "outside-slice.json"
            outside_slice_spec.write_text("{}", encoding="utf-8")

            with self.assertRaisesRegex(ValueError, "slice_spec must be repo-relative"):
                module.run_competition_smoke(
                    out_root=out_root,
                    proof_class="local-simulation",
                    command_runner=FakeCommandRunner(),
                    repo_root=REPO_ROOT,
                    run_id="smoke-outside-slice-spec-test",
                    slice_spec=outside_slice_spec,
                )

            self.assertFalse((out_root / "logs" / "commands.jsonl").exists())

    def test_command_log_omits_local_absolute_paths_for_external_out_root(self) -> None:
        module = load_smoke_module()
        with tempfile.TemporaryDirectory(prefix="competition-smoke-test-") as tmp:
            out_root = Path(tmp) / "competition-smoke"

            result = module.run_competition_smoke(
                out_root=out_root,
                proof_class="local-simulation",
                command_runner=FakeCommandRunner(),
                repo_root=REPO_ROOT,
                run_id="smoke-command-log-portability-test",
            )

            self.assertEqual(result.exit_code, 0)
            command_log = out_root / "logs" / "commands.jsonl"
            command_entries = [json.loads(line) for line in command_log.read_text(encoding="utf-8").splitlines()]
            assert_no_local_absolute_command_arguments(self, command_entries)
            logged_arguments = [
                argument
                for entry in command_entries
                for argument in entry["command"]
                if isinstance(argument, str)
            ]
            self.assertNotIn(sys.executable, logged_arguments)
            self.assertTrue(any(argument == "summary/vendored-clang-verification.json" for argument in logged_arguments))
            self.assertTrue(any(argument == "reports/evidence-governance.json" for argument in logged_arguments))

    def test_command_log_sanitizes_python_executable_with_spaces(self) -> None:
        module = load_smoke_module()
        original_executable = module.sys.executable
        module.sys.executable = r"C:\Program Files\Python314\python.exe"
        try:
            with tempfile.TemporaryDirectory(prefix="competition-smoke-test-") as tmp:
                out_root = Path(tmp) / "competition-smoke"

                result = module.run_competition_smoke(
                    out_root=out_root,
                    proof_class="local-simulation",
                    command_runner=FakeCommandRunner(),
                    repo_root=REPO_ROOT,
                    run_id="smoke-command-log-python-spaces-test",
                )

                self.assertEqual(result.exit_code, 0)
                command_entries = [
                    json.loads(line)
                    for line in (out_root / "logs" / "commands.jsonl").read_text(encoding="utf-8").splitlines()
                ]
                assert_no_local_absolute_command_arguments(self, command_entries)
                logged_arguments = [
                    argument
                    for entry in command_entries
                    for argument in entry["command"]
                    if isinstance(argument, str)
                ]
                self.assertNotIn(module.sys.executable, logged_arguments)
                self.assertIn("python.exe", logged_arguments)
        finally:
            module.sys.executable = original_executable

    def test_command_log_is_replaced_on_each_smoke_run(self) -> None:
        module = load_smoke_module()
        with tempfile.TemporaryDirectory(prefix="competition-smoke-test-") as tmp:
            out_root = Path(tmp) / "competition-smoke"
            command_log = out_root / "logs" / "commands.jsonl"
            command_log.parent.mkdir(parents=True)
            command_log.write_text(
                json.dumps({"step": "stale", "command": ["C:\\Python314\\python.exe"], "returncode": 0}) + "\n",
                encoding="utf-8",
            )

            result = module.run_competition_smoke(
                out_root=out_root,
                proof_class="local-simulation",
                command_runner=FakeCommandRunner(),
                repo_root=REPO_ROOT,
                run_id="smoke-command-log-replace-test",
            )

            self.assertEqual(result.exit_code, 0)
            command_entries = [json.loads(line) for line in command_log.read_text(encoding="utf-8").splitlines()]
            self.assertNotIn("stale", [entry["step"] for entry in command_entries])
            assert_no_local_absolute_command_arguments(self, command_entries)


if __name__ == "__main__":
    unittest.main()
