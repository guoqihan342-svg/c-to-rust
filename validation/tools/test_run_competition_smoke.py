import contextlib
import hashlib
import importlib.util
import io
import json
import re
import subprocess
import sys
import tempfile
import unittest
from unittest import mock
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


LOCAL_ABSOLUTE_PATH = re.compile(
    r"(?:[A-Za-z]:[\\/]|/mnt/[A-Za-z]/|/home/|/Users/|/tmp/|/var/|/root/|/usr/|/workspace/|/__w/|/opt/|/builds/|\\\\wsl\$\\|//wsl\$/|\\\\wsl\.localhost\\|//wsl\.localhost/|\\\\[^\\/\s]+\\[^\\/\s]+\\|(?<!:)//[^/\s]+/[^/\s]+/)"
)


def assert_no_local_absolute_command_arguments(testcase: unittest.TestCase, command_entries: list[dict]) -> None:
    for entry in command_entries:
        for argument in entry["command"]:
            if not isinstance(argument, str):
                continue
            testcase.assertNotRegex(argument, LOCAL_ABSOLUTE_PATH)
            testcase.assertFalse(Path(argument).is_absolute(), argument)


def assert_no_local_absolute_command_log_text(testcase: unittest.TestCase, command_entries: list[dict]) -> None:
    for entry in command_entries:
        for field in ("stdout", "stderr", "cwd", "workdir"):
            value = entry.get(field, "")
            if isinstance(value, str):
                testcase.assertNotRegex(value, LOCAL_ABSOLUTE_PATH)


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


class FakeGlmCommandRunner(FakeCommandRunner):
    def __call__(self, command: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
        if command == ["opencode", "models"]:
            self.commands.append(command)
            self.kwargs.append(kwargs)
            return subprocess.CompletedProcess(command, 0, "provider/GLM-5.1\n", "")
        return super().__call__(command, **kwargs)


class FakeNonGlmCommandRunner(FakeCommandRunner):
    def __call__(self, command: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
        if command == ["opencode", "models"]:
            self.commands.append(command)
            self.kwargs.append(kwargs)
            return subprocess.CompletedProcess(command, 0, "openai/gpt-5.1\nopencode/not-GLM-5.1\n", "")
        return super().__call__(command, **kwargs)


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
            self.assertTrue(any("evidence_governance.py" in text and "--policy-tier ci" in text for text in command_texts))
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

    def test_non_exact_smoke_does_not_require_opencode_glm(self) -> None:
        module = load_smoke_module()
        with tempfile.TemporaryDirectory(prefix="competition-smoke-test-") as tmp:
            out_root = Path(tmp) / "competition-smoke"
            fake_runner = FakeCommandRunner()

            result = module.run_competition_smoke(
                out_root=out_root,
                proof_class="local-simulation",
                command_runner=fake_runner,
                repo_root=REPO_ROOT,
                run_id="smoke-non-exact-no-glm-test",
            )

            self.assertEqual(result.exit_code, 0)
            command_text = "\n".join(" ".join(command) for command in fake_runner.commands)
            self.assertNotIn("REQUIRE_OPENCODE_GLM=1", command_text)
            self.assertNotIn("opencode models", command_text)
            summary = json.loads((out_root / "summary" / "competition-smoke-summary.json").read_text(encoding="utf-8"))
            self.assertNotIn("opencode_model_availability", summary)

    def test_lf_stable_sha256_normalizes_crlf_for_jsonl_artifacts(self) -> None:
        module = load_smoke_module()
        with tempfile.TemporaryDirectory(prefix="competition-smoke-test-") as tmp:
            artifact = Path(tmp) / "commands.jsonl"
            artifact.write_bytes(b'{"step":"one"}\r\n{"step":"two"}\r\n')

            expected = hashlib.sha256(b'{"step":"one"}\n{"step":"two"}\n').hexdigest()
            self.assertEqual(module.sha256_lf_stable(artifact), expected)

    def test_smoke_summary_command_log_sha256_uses_lf_stable_hash(self) -> None:
        module = load_smoke_module()
        with tempfile.TemporaryDirectory(prefix="competition-smoke-test-") as tmp:
            out_root = Path(tmp) / "competition-smoke"

            result = module.run_competition_smoke(
                out_root=out_root,
                proof_class="local-simulation",
                command_runner=FakeCommandRunner(),
                repo_root=REPO_ROOT,
                run_id="smoke-command-log-hash-test",
            )

            self.assertEqual(result.exit_code, 0)
            command_log = out_root / "logs" / "commands.jsonl"
            summary = json.loads((out_root / "summary" / "competition-smoke-summary.json").read_text(encoding="utf-8"))
            self.assertEqual(summary["command_log"]["sha256"], module.sha256_lf_stable(command_log))

    def test_smoke_summary_publication_is_atomic_when_replace_fails(self) -> None:
        module = load_smoke_module()
        with tempfile.TemporaryDirectory(prefix="competition-smoke-test-") as tmp:
            out_root = Path(tmp) / "competition-smoke"
            summary_path = out_root / "summary" / "competition-smoke-summary.json"
            original_replace = module.os.replace

            def failing_replace(source: object, destination: object) -> None:
                if Path(destination) == summary_path:
                    raise OSError("simulated atomic replace failure")
                original_replace(source, destination)

            module.os.replace = failing_replace
            try:
                with self.assertRaisesRegex(OSError, "simulated atomic replace failure"):
                    module.run_competition_smoke(
                        out_root=out_root,
                        proof_class="local-simulation",
                        command_runner=FakeCommandRunner(),
                        repo_root=REPO_ROOT,
                        run_id="smoke-summary-atomic-test",
                    )
            finally:
                module.os.replace = original_replace

            self.assertFalse(summary_path.exists())
            self.assertEqual(list(summary_path.parent.glob("*.tmp")), [])

    def test_smoke_runner_internal_python_commands_use_portable_python3_b(self) -> None:
        module = load_smoke_module()
        with tempfile.TemporaryDirectory(prefix="competition-smoke-test-") as tmp:
            out_root = Path(tmp) / "competition-smoke"
            fake_runner = FakeCommandRunner()

            module.run_competition_smoke(
                out_root=out_root,
                proof_class="local-simulation",
                command_runner=fake_runner,
                repo_root=REPO_ROOT,
                run_id="smoke-portable-python-test",
            )

            python_commands = [
                command
                for command in fake_runner.commands
                if any(argument.endswith(".py") for argument in command) or command[1:3] == ["-m", "unittest"]
            ]
            self.assertGreater(len(python_commands), 0)
            for command in python_commands:
                self.assertEqual(command[:2], ["python3", "-B"])
                self.assertNotIn(sys.executable, command)

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

    def test_detect_execution_environment_requires_exact_host_env_value_one(self) -> None:
        module = load_smoke_module()

        with mock.patch.dict(module.os.environ, {"COMPETITION_EXACT_HOST": "0"}, clear=False):
            self.assertFalse(module.detect_execution_environment()["competition_exact_host_attested"])
        with mock.patch.dict(module.os.environ, {"COMPETITION_EXACT_HOST": "false"}, clear=False):
            self.assertFalse(module.detect_execution_environment()["competition_exact_host_attested"])
        with mock.patch.dict(module.os.environ, {"COMPETITION_EXACT_HOST": "1"}, clear=False):
            self.assertTrue(module.detect_execution_environment()["competition_exact_host_attested"])

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
            with mock.patch.dict(module.os.environ, {"COMPETITION_EXACT_HOST": "1"}, clear=False):
                result = module.run_competition_smoke(
                    out_root=out_root,
                    proof_class="competition-exact",
                    confirm_competition_exact=True,
                    command_runner=FakeGlmCommandRunner(fail_commands_containing={"toolchain-check.sh"}),
                    repo_root=REPO_ROOT,
                    run_id="smoke-test",
                )

            self.assertEqual(result.exit_code, 1)
            summary = json.loads((out_root / "summary" / "competition-smoke-summary.json").read_text(encoding="utf-8"))
            self.assertEqual(summary["final_gate"]["status"], "failed")
            environment_step = next(step for step in summary["steps"] if step["step"] == "environment-check")
            self.assertEqual(environment_step["status"], "failed")

    def test_competition_exact_environment_check_requires_opencode_glm(self) -> None:
        module = load_smoke_module()
        with tempfile.TemporaryDirectory(prefix="competition-smoke-test-") as tmp:
            out_root = Path(tmp) / "competition-smoke"
            fake_runner = FakeGlmCommandRunner()

            with mock.patch.dict(module.os.environ, {"COMPETITION_EXACT_HOST": "1"}, clear=False):
                module.run_competition_smoke(
                    out_root=out_root,
                    proof_class="competition-exact",
                    confirm_competition_exact=True,
                    command_runner=fake_runner,
                    repo_root=REPO_ROOT,
                    run_id="smoke-opencode-glm-required-test",
                )

            environment_command = next(
                command for command in fake_runner.commands if "toolchain-check.sh" in " ".join(command)
            )
            self.assertIn("REQUIRE_OPENCODE_GLM=1", " ".join(environment_command))

    def test_competition_exact_summary_records_opencode_glm_model_probe(self) -> None:
        module = load_smoke_module()
        profile = module.load_profile(REPO_ROOT)
        expected_os = profile["os"]
        expected_toolchain = profile["toolchain"]
        original_detect = module.detect_execution_environment
        try:
            module.detect_execution_environment = lambda: {
                "kind": "competition-host",
                "detected_ci": False,
                "detected_wsl": False,
                "competition_exact_host_attested": True,
                "system": expected_os["name"],
                "release": expected_os["kernel"],
                "version": "competition-host",
                "machine": "x86_64",
                "kernel": expected_os["kernel"],
                "python_version": expected_toolchain["python"],
                "runner_name": "competition",
            }
            with tempfile.TemporaryDirectory(prefix="competition-smoke-test-") as tmp:
                out_root = Path(tmp) / "competition-smoke"
                result = module.run_competition_smoke(
                    out_root=out_root,
                    proof_class="competition-exact",
                    confirm_competition_exact=True,
                    command_runner=FakeGlmCommandRunner(),
                    repo_root=REPO_ROOT,
                    run_id="smoke-opencode-glm-probe-test",
                )
                self.assertEqual(result.exit_code, 0)
                summary = json.loads((out_root / "summary" / "competition-smoke-summary.json").read_text(encoding="utf-8"))
                availability = summary["opencode_model_availability"]
                stdout_text = (out_root / availability["logs"]["stdout"]).read_text(encoding="utf-8")
                stderr_text = (out_root / availability["logs"]["stderr"]).read_text(encoding="utf-8")
        finally:
            module.detect_execution_environment = original_detect

        self.assertIn("opencode_model_availability", summary)
        availability = summary["opencode_model_availability"]
        self.assertEqual(availability["status"], "available")
        self.assertEqual(availability["required_model"], "GLM-5.1")
        self.assertTrue(availability["model_listed"])
        self.assertEqual(availability["argv"], ["opencode", "models"])
        self.assertEqual(
            availability["logs"],
            {
                "stdout": "logs/opencode-models.stdout.log",
                "stderr": "logs/opencode-models.stderr.log",
            },
        )
        self.assertEqual(stdout_text, "provider/GLM-5.1\n")
        self.assertEqual(stderr_text, "")
        self.assertEqual(availability["stdout_sha256"], hashlib.sha256(b"provider/GLM-5.1\n").hexdigest())
        self.assertEqual(availability["stderr_sha256"], hashlib.sha256(b"").hexdigest())

    def test_competition_exact_requires_vendored_clang_verification(self) -> None:
        module = load_smoke_module()
        with tempfile.TemporaryDirectory(prefix="competition-smoke-test-") as tmp:
            out_root = Path(tmp) / "competition-smoke"
            with mock.patch.dict(module.os.environ, {"COMPETITION_EXACT_HOST": "1"}, clear=False):
                result = module.run_competition_smoke(
                    out_root=out_root,
                    proof_class="competition-exact",
                    confirm_competition_exact=True,
                    command_runner=FakeGlmCommandRunner(fail_commands_containing={"--require-clang"}),
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
                    "competition_exact_host_attested": True,
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
                    command_runner=FakeGlmCommandRunner(),
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
            fake_runner = FakeCommandRunner()
            original_detect = module.detect_execution_environment
            original_clang_source = module.clang_source
            try:
                module.detect_execution_environment = lambda: dict(matching_environment)
                module.clang_source = lambda _: "vendored"
                with self.assertRaises(SystemExit) as raised:
                    module.run_competition_smoke(
                        out_root=out_root,
                        proof_class="competition-exact",
                        confirm_competition_exact=True,
                        command_runner=fake_runner,
                        repo_root=REPO_ROOT,
                        run_id="smoke-exact-attestation-test",
                    )
            finally:
                module.detect_execution_environment = original_detect
                module.clang_source = original_clang_source

            self.assertIn("COMPETITION_EXACT_HOST=1", str(raised.exception))
            self.assertEqual(fake_runner.commands, [])
            self.assertFalse((out_root / "summary" / "competition-smoke-summary.json").exists())

    def test_competition_exact_stops_after_glm_probe_when_model_missing(self) -> None:
        module = load_smoke_module()
        profile = module.load_profile(REPO_ROOT)
        expected_os = profile["os"]
        expected_toolchain = profile["toolchain"]
        original_detect = module.detect_execution_environment
        try:
            module.detect_execution_environment = lambda: {
                "kind": "competition-host",
                "detected_ci": False,
                "detected_wsl": False,
                "competition_exact_host_attested": True,
                "system": expected_os["name"],
                "release": expected_os["kernel"],
                "version": "competition-host",
                "machine": "x86_64",
                "kernel": expected_os["kernel"],
                "python_version": expected_toolchain["python"],
                "runner_name": "competition",
            }
            with tempfile.TemporaryDirectory(prefix="competition-smoke-test-") as tmp:
                out_root = Path(tmp) / "competition-smoke"
                fake_runner = FakeNonGlmCommandRunner()
                with self.assertRaises(SystemExit) as raised:
                    module.run_competition_smoke(
                        out_root=out_root,
                        proof_class="competition-exact",
                        confirm_competition_exact=True,
                        command_runner=fake_runner,
                        repo_root=REPO_ROOT,
                        run_id="smoke-exact-missing-glm-test",
                    )
        finally:
            module.detect_execution_environment = original_detect

        self.assertIn("opencode_model_unavailable", str(raised.exception))
        self.assertEqual(len(fake_runner.commands), 2)
        self.assertTrue(any("toolchain-check.sh" in " ".join(command) for command in fake_runner.commands))
        self.assertEqual(fake_runner.commands[-1], ["opencode", "models"])
        self.assertFalse((out_root / "summary" / "competition-smoke-summary.json").exists())

    def test_competition_exact_model_probe_failure_removes_stale_summary(self) -> None:
        module = load_smoke_module()
        profile = module.load_profile(REPO_ROOT)
        expected_os = profile["os"]
        expected_toolchain = profile["toolchain"]
        original_detect = module.detect_execution_environment
        try:
            module.detect_execution_environment = lambda: {
                "kind": "competition-host",
                "detected_ci": False,
                "detected_wsl": False,
                "competition_exact_host_attested": True,
                "system": expected_os["name"],
                "release": expected_os["kernel"],
                "version": "competition-host",
                "machine": "x86_64",
                "kernel": expected_os["kernel"],
                "python_version": expected_toolchain["python"],
                "runner_name": "competition",
            }
            with tempfile.TemporaryDirectory(prefix="competition-smoke-test-") as tmp:
                out_root = Path(tmp) / "competition-smoke"
                stale_summary = out_root / "summary" / "competition-smoke-summary.json"
                stale_summary.parent.mkdir(parents=True)
                stale_summary.write_text(
                    json.dumps(
                        {
                            "report_kind": "competition-smoke-summary",
                            "final_gate": {"status": "passed"},
                        },
                        sort_keys=True,
                    )
                    + "\n",
                    encoding="utf-8",
                )

                with self.assertRaises(SystemExit):
                    module.run_competition_smoke(
                        out_root=out_root,
                        proof_class="competition-exact",
                        confirm_competition_exact=True,
                        command_runner=FakeNonGlmCommandRunner(),
                        repo_root=REPO_ROOT,
                        run_id="smoke-exact-stale-summary-test",
                    )
                self.assertFalse(stale_summary.exists())
        finally:
            module.detect_execution_environment = original_detect

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
        self.assertIn("python3 -B validation/tools/run_competition_smoke.py", workflow)

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

    def test_slice_spec_with_tilde_is_rejected_before_command_log(self) -> None:
        module = load_smoke_module()
        with tempfile.TemporaryDirectory(prefix="competition-smoke-test-") as tmp:
            out_root = Path(tmp) / "competition-smoke"

            with self.assertRaisesRegex(ValueError, "slice_spec must be repo-relative POSIX"):
                module.run_competition_smoke(
                    out_root=out_root,
                    proof_class="local-simulation",
                    command_runner=FakeCommandRunner(),
                    repo_root=REPO_ROOT,
                    run_id="smoke-tilde-slice-spec-test",
                    slice_spec=Path("~/slice.json"),
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
            self.assertTrue(
                any(argument == "out-root:summary/vendored-clang-verification.json" for argument in logged_arguments)
            )
            self.assertTrue(any(argument == "out-root:reports/evidence-governance.json" for argument in logged_arguments))
            self.assertFalse(
                any(
                    argument in {"summary/vendored-clang-verification.json", "reports/evidence-governance.json"}
                    for argument in logged_arguments
                )
            )

    def test_external_out_root_command_paths_match_logged_workdir(self) -> None:
        module = load_smoke_module()
        with tempfile.TemporaryDirectory(prefix="competition-smoke-test-") as tmp:
            out_root = Path(tmp) / "competition-smoke"

            result = module.run_competition_smoke(
                out_root=out_root,
                proof_class="local-simulation",
                command_runner=FakeCommandRunner(),
                repo_root=REPO_ROOT,
                run_id="smoke-command-log-replayability-test",
            )

            self.assertEqual(result.exit_code, 0)
            command_entries = [
                json.loads(line)
                for line in (out_root / "logs" / "commands.jsonl").read_text(encoding="utf-8").splitlines()
            ]
            output_flags = {"--out", "--output", "--coverage-report"}
            for entry in command_entries:
                command = entry["command"]
                if entry.get("workdir") != ".":
                    continue
                for index, argument in enumerate(command[:-1]):
                    if argument in output_flags:
                        self.assertTrue(command[index + 1].startswith("out-root:"), command)

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
                self.assertNotIn("python.exe", logged_arguments)
                self.assertIn("python3", logged_arguments)
                self.assertIn("-B", logged_arguments)
        finally:
            module.sys.executable = original_executable

    def test_command_argument_for_log_sanitizes_shell_fragment_host_paths(self) -> None:
        module = load_smoke_module()
        cases = {
            "echo ok; /mnt/c/Users/me/tool.exe": "echo ok; tool.exe",
            "cc -I/mnt/c -L/workspace --sysroot=/opt": "cc -Ic -Lworkspace --sysroot=opt",
            "-I/mnt/c": "-Ic",
            "--sysroot=/opt": "--sysroot=opt",
            r"echo ok && \\wsl$\Ubuntu\home\me\tool.exe": "echo ok && tool.exe",
            "echo ok | //wsl.localhost/Ubuntu/home/me/python3": "echo ok | python3",
            "echo ok | //wsl$/Ubuntu/home/me/python3": "echo ok | python3",
            "echo ok | /workspace/project/tools/python3": "echo ok | python3",
            "echo ok; /root/work/project/tools/python3": "echo ok; python3",
            "echo ok | /usr/bin/clang": "echo ok | clang",
            r"echo ok && \\server\share\tool.exe": "echo ok && tool.exe",
            r"ld -L\\server\share": "ld -Lshare",
            r"-L\\server\share": "-Lshare",
            "echo ok && //server/share/tool": "echo ok && tool",
            "ld -L//server/share": "ld -Lshare",
            "-L//server/share": "-Lshare",
            r'echo ok; "C:\Program Files\Python314\python.exe"': 'echo ok; "python.exe"',
        }

        for argument, expected in cases.items():
            with self.subTest(argument=argument):
                logged = module.command_argument_for_log(
                    argument,
                    repo_root=REPO_ROOT,
                    out_root=REPO_ROOT / "target" / "competition-smoke",
                )

                self.assertEqual(logged, expected)
                self.assertNotRegex(logged, LOCAL_ABSOLUTE_PATH)

    def test_command_argument_for_log_sanitizes_home_and_users_host_paths(self) -> None:
        # Drift matrix boundary: the shell-fragment sanitizer test never
        # exercises a standalone /home or /Users (macOS) absolute path, nor a
        # WSL/host path attached to include/source/output-style flags. These
        # cells must scrub to a basename so a Windows/macOS/WSL producer never
        # leaks host roots into commands.jsonl consumed on the judge host.
        module = load_smoke_module()
        cases = {
            "echo ok; /home/runner/project/tool.py": "echo ok; tool.py",
            "echo ok | /Users/me/project/tool": "echo ok | tool",
            "cc -I/home/runner/FlashDB/include": "cc -Iinclude",
            "-I/home/runner/FlashDB/include": "-Iinclude",
            "cc -c /home/runner/project/src/fdb.c": "cc -c fdb.c",
            "-o/mnt/c/Users/runner/target/out.json": "-oout.json",
            r"-o\\wsl$\Ubuntu\home\runner\target\out.json": "-oout.json",
        }
        for argument, expected in cases.items():
            with self.subTest(argument=argument):
                logged = module.command_argument_for_log(
                    argument,
                    repo_root=REPO_ROOT,
                    out_root=REPO_ROOT / "target" / "competition-smoke",
                )

                self.assertEqual(logged, expected)
                self.assertNotRegex(logged, LOCAL_ABSOLUTE_PATH)

    def test_command_log_sanitizes_stdout_and_stderr_host_paths(self) -> None:
        module = load_smoke_module()

        def noisy_runner(command: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
            return subprocess.CompletedProcess(
                command,
                0,
                (
                    "include path: /mnt/c/Users/me/FlashDB/inc\n"
                    "cwd: //wsl.localhost/Ubuntu/home/me/project\n"
                    "source: //wsl$/Ubuntu/home/me/project/src/fdb.c\n"
                    "ci source: /workspace/project/src/fdb.c\n"
                    "unc source: //server/share/project/src/fdb.c\n"
                ),
                r"output path: \\wsl$\Ubuntu\home\me\project\target\out.json and \\server\share\project\target\out.json",
            )

        with tempfile.TemporaryDirectory(prefix="competition-smoke-test-") as tmp:
            out_root = Path(tmp) / "competition-smoke"

            result = module.run_competition_smoke(
                out_root=out_root,
                proof_class="local-simulation",
                command_runner=noisy_runner,
                repo_root=REPO_ROOT,
                run_id="smoke-command-log-output-sanitize-test",
            )

            self.assertEqual(result.exit_code, 0)
            command_entries = [
                json.loads(line)
                for line in (out_root / "logs" / "commands.jsonl").read_text(encoding="utf-8").splitlines()
            ]
            assert_no_local_absolute_command_arguments(self, command_entries)
            assert_no_local_absolute_command_log_text(self, command_entries)
            joined_output = "\n".join(
                str(entry.get(field, ""))
                for entry in command_entries
                for field in ("stdout", "stderr")
            )
            self.assertIn("inc", joined_output)
            self.assertIn("project", joined_output)
            self.assertIn("fdb.c", joined_output)
            self.assertNotIn("//wsl$", joined_output)
            self.assertIn("out.json", joined_output)

    def test_output_text_for_log_sanitizes_container_absolute_paths(self) -> None:
        module = load_smoke_module()

        logged = module.output_text_for_log(
            "cwd: /root/work/project; source: /root/work/project/src/fdb.c; compiler: /usr/bin/clang"
        )

        self.assertIn("project", logged)
        self.assertIn("fdb.c", logged)
        self.assertIn("clang", logged)
        self.assertNotIn("/root/", logged)
        self.assertNotIn("/usr/", logged)
        self.assertNotRegex(logged, LOCAL_ABSOLUTE_PATH)

    def test_command_log_records_repo_relative_workdir(self) -> None:
        module = load_smoke_module()
        with tempfile.TemporaryDirectory(prefix="competition-smoke-test-") as tmp:
            out_root = Path(tmp) / "competition-smoke"

            result = module.run_competition_smoke(
                out_root=out_root,
                proof_class="local-simulation",
                command_runner=(fake_runner := FakeCommandRunner()),
                repo_root=REPO_ROOT,
                run_id="smoke-command-log-workdir-test",
            )

            self.assertEqual(result.exit_code, 0)
            command_entries = [
                json.loads(line)
                for line in (out_root / "logs" / "commands.jsonl").read_text(encoding="utf-8").splitlines()
            ]
            self.assertTrue(command_entries)
            self.assertTrue(all(entry.get("workdir") == "." for entry in command_entries))
            self.assertTrue(all("cwd" not in entry for entry in command_entries))
            self.assertTrue(all(kwargs.get("cwd") == REPO_ROOT for kwargs in fake_runner.kwargs))
            assert_no_local_absolute_command_log_text(self, command_entries)

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
